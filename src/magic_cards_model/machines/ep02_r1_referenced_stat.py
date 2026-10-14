"""EP-02 R1 T6: the power, toughness or mana value of a referenced object, used
as an amount.

"You gain life equal to its power" (a creature that just died), "draw cards
equal to that creature's power" (the creature an edict made a player
sacrifice), "deals damage equal to the sacrificed creature's power" (what an
activation cost sacrificed), "gain life equal to the power of target creature
you control", "put X +1/+1 counters on ..., where X is the power of the
creature that died".

Three things make up the reader, and this module is the one place all of them
live:

- `parse_stat_phrase` reads the amount phrase into a `StatRef` (which object,
  which characteristic).
- `Referent` is the object as it last existed (CR 608.2h) - taken from the
  layer-computed battlefield while the object is there (CR 613.5), from its
  last known information once it is gone (CR 603.10a).
- `referenced_stat_effect` is the whole-text reader a family module registers
  on the `ABILITY_TEXT`/`SPELL_TEXT` ladders: a sentence naming the amount, or
  an earlier sentence naming the object ("Destroy target creature.", "Target
  player sacrifices a creature of their choice.") followed by sentences that
  use its characteristic.

A negative characteristic counts as zero (CR 107.1b).
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from magic_cards_model.text_norm import collapsed

from ..models.card import Type
from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from .amount_sentences import (
    apply_life,
    apply_mill,
    parse_cards_clause,
    parse_damage_clause,
    parse_life_clause,
    parse_mill_clause,
    parse_put_counters,
)

if TYPE_CHECKING:
    from ..models.game import Game

# --------------------------------------------------------------------------
# The amount phrase
# --------------------------------------------------------------------------


class Anchor(StrEnum):
    """Which object an amount phrase names."""

    ANAPHOR = "anaphor"
    """"its", "that creature's", "that card's": the object an earlier part of
    the same text, or the trigger event, named (CR 608.2c)."""
    SACRIFICED = "sacrificed"
    """"the sacrificed creature's": what the cost, or an earlier sacrifice,
    moved (CR 602.2b, CR 701.21a)."""
    TARGET = "target"
    """"the power of target creature you control": the ability's own target."""
    DIED = "died"
    """"the power of the creature that died": the dies event's subject."""


@dataclass(frozen=True)
class StatRef:
    anchor: Anchor
    stat: str
    """One of "power", "toughness", "mana value", "power plus toughness"."""


_STAT = r"power plus (?:its|that creature's|that card's) toughness|power|toughness|mana value"
_STAT_PHRASE_RE = re.compile(
    rf"^(?:(?P<anaphor>its|that (?:creature|card|permanent|artifact)'s)"
    rf"|(?P<sacrificed>the sacrificed (?:creature|permanent|artifact|card)'s)) "
    rf"(?P<stat>{_STAT})$"
    r"|^the (?P<stat_of>power|toughness|mana value) of "
    r"(?:(?P<of_target>target creature(?: you control)?)"
    r"|(?P<of_died>the creature that died)"
    r"|(?P<of_sacrificed>the sacrificed (?:creature|permanent|artifact|card))"
    r"|(?P<of_anaphor>that (?:creature|card|permanent)|it))$"
)


@functools.cache
def parse_stat_phrase(phrase: str) -> StatRef | None:
    """`phrase` ("its toughness", "the sacrificed creature's power", "the
    power of target creature you control") as a `StatRef`, or `None`."""
    match = _STAT_PHRASE_RE.fullmatch(phrase.strip().rstrip(".").lower())
    if match is None:
        return None
    if match.group("stat_of") is not None:
        stat = match.group("stat_of")
        if match.group("of_target"):
            return StatRef(Anchor.TARGET, stat)
        if match.group("of_died"):
            return StatRef(Anchor.DIED, stat)
        if match.group("of_sacrificed"):
            return StatRef(Anchor.SACRIFICED, stat)
        return StatRef(Anchor.ANAPHOR, stat)
    stat = match.group("stat")
    if stat.startswith("power plus"):
        stat = "power plus toughness"
    return StatRef(Anchor.SACRIFICED if match.group("sacrificed") else Anchor.ANAPHOR, stat)


# --------------------------------------------------------------------------
# The referenced object, as it last existed
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Referent:
    """A referenced object's characteristics, fixed at one moment (CR 608.2h).

    Taken before the first part of a text moves the object, so a destroyed,
    exiled or sacrificed creature still reports the power and toughness it had
    on the battlefield, counters and continuous effects included.
    """

    card_id: UUID | None
    power: int | None
    toughness: int | None
    mana_value: int
    types: frozenset[str]
    subtypes: frozenset[str]

    def is_a(self, word: str) -> bool:
        lowered = word.lower()
        return lowered in self.types or lowered in self.subtypes


def snapshot_of(game: "Game", card: CardState) -> Referent:
    """`card` as it is now (battlefield: the computed board, CR 613.5) or as it
    last existed (CR 608.2h)."""
    characteristics = game.characteristics_of(card)
    if card.zone is Zone.BATTLEFIELD:
        power, toughness = characteristics.power, characteristics.toughness
    else:
        power, toughness = card.last_known_power_toughness()
    return Referent(
        card_id=card.id,
        power=power,
        toughness=toughness,
        mana_value=int(game.last_known_mana_value(card)),
        types=frozenset(str(kind.value).lower() for kind in characteristics.types),
        subtypes=frozenset(sub.lower() for sub in characteristics.subtypes),
    )


def stat_value(referent: Referent | None, stat: str) -> int:
    """The characteristic `stat` names, never negative (CR 107.1b); a
    characteristic that is not a number (a `*` nothing computed) counts as 0."""
    if referent is None:
        return 0
    if stat == "power":
        value = referent.power or 0
    elif stat == "toughness":
        value = referent.toughness or 0
    elif stat == "mana value":
        value = referent.mana_value
    else:
        value = (referent.power or 0) + (referent.toughness or 0)
    return max(value, 0)


def discard_equal_to_stat(
    game: "Game",
    username: str,
    referent: Referent | None,
    stat: str,
    source_name: str,
    source_id: Any,
) -> None:
    """`username` discards cards equal to `referent`'s `stat`, of their own
    choice (CR 701.9b); a hand shorter than that discards what it has."""
    from .effects.draw_discard import _discard_cards

    _discard_cards(
        game,
        game.player(username),
        stat_value(referent, stat),
        source_name,
        source_id=None if source_id is None else str(source_id),
    )


def _sacrificed_referent(game: "Game", stack_object: Any) -> Referent | None:
    """What the resolving object's own cost sacrificed (CR 602.2b for an
    ability, CR 601.2h for a spell's additional cost), as the cost snapshotted
    it when paid - the sacrificed object is gone by now and a token has ceased
    to exist (CR 704.5d)."""
    ids = getattr(stack_object, "cost_sacrificed_card_ids", ())
    if ids:
        card = game.find_by_id(ids[0])
        base = snapshot_of(game, card) if card is not None else None
        powers = stack_object.cost_sacrificed_powers
        toughnesses = stack_object.cost_sacrificed_toughnesses
        values = stack_object.cost_sacrificed_mana_values
        return Referent(
            card_id=ids[0],
            power=powers[0] if powers else (base.power if base else None),
            toughness=toughnesses[0] if toughnesses else (base.toughness if base else None),
            mana_value=int(values[0]) if values else (base.mana_value if base else 0),
            types=base.types if base else frozenset(),
            subtypes=base.subtypes if base else frozenset(),
        )
    record = game.cast_record_of(stack_object) if isinstance(stack_object, CardState) else None
    if record is not None and record.additional_cost_cards:
        card = game.find_by_id(record.additional_cost_cards[0])
        if card is None:
            return None
        base = snapshot_of(game, card)
        powers = record.additional_cost_powers
        values = record.additional_cost_mana_values
        return Referent(
            card_id=card.id,
            power=int(powers[0]) if powers else base.power,
            toughness=base.toughness,
            mana_value=int(values[0]) if values else base.mana_value,
            types=base.types,
            subtypes=base.subtypes,
        )
    return None


def default_referent(game: "Game", stack_object: Any, anchor: Anchor) -> Referent | None:
    """The object `anchor` names for a text that has no earlier sentence
    naming one: the cost's sacrifice, the event's subject (CR 603.2), or the
    ability's own first object target."""
    if anchor is Anchor.SACRIFICED:
        return _sacrificed_referent(game, stack_object)
    event = getattr(stack_object, "event", None)
    if anchor is not Anchor.TARGET and event is not None and event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)
        if subject is not None:
            return snapshot_of(game, subject)
    if anchor is Anchor.DIED:
        return None
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState):
            return snapshot_of(game, target)
    return None


# --------------------------------------------------------------------------
# One sentence that uses the amount
# --------------------------------------------------------------------------

#: `(game, stack_object, referent) -> None`.
Action = Callable[["Game", Any, "Referent | None"], None]

#: The players an amount sentence names.
_PLAYER_WORDS = frozenset({"you", "target player", "target opponent", "that player"})
_MAY_PREFIX_RE = re.compile(r"^you may ")
_IF_RE = re.compile(r"^if (?P<condition>.+?), (?P<rest>.+)$")
_WAS_A_RE = re.compile(r"^(?:that creature|it|that card) was an? (?P<kind>[a-z]+)$")


def normalize(sentence: str) -> str:
    """`sentence` lowercased, with straight apostrophes, no closing full stop
    and single spaces."""
    return collapsed(sentence.replace("’", "'")).rstrip(".").lower()


def _source_of(game: "Game", stack_object: Any) -> CardState | None:
    if isinstance(stack_object, CardState):
        return stack_object
    return stack_object.source_or_last_known(game)


def _parse_effect_sentence(sentence: str) -> tuple[Action, StatRef, bool] | None:
    """`sentence` (normalised, no leading "if"/"you may") as an `Action`, the
    `StatRef` its amount uses and whether it targets a player."""
    if (life := parse_life_clause(sentence)) is not None:
        ref = parse_stat_phrase(life.expr or "") if life.kind == "equal" else None
        if ref is None or life.who not in _PLAYER_WORDS:
            return None
        gains, who = life.gains, life.who

        def life_change(game: "Game", stack_object: Any, referent: Referent | None) -> None:
            amount = stat_value(referent, ref.stat)
            apply_life(game, stack_object, who, gains, lambda *_: amount)

        return life_change, ref, who.startswith("target")
    if (cards := parse_cards_clause(sentence)) is not None:
        ref = parse_stat_phrase(cards.expr or "") if cards.kind == "equal" else None
        if ref is None or cards.who not in ("", "you", "target player", "target opponent"):
            return None
        who = cards.who
        if cards.draws:
            if who not in ("", "you"):
                return None

            def draw(game: "Game", stack_object: Any, referent: Referent | None) -> None:
                game.draw_cards(game.controller_of(stack_object), stat_value(referent, ref.stat))

            return draw, ref, False

        def discard(game: "Game", stack_object: Any, referent: Referent | None) -> None:
            from .decisions import source_id_of

            player = game.controller_of(stack_object)
            if who.startswith("target"):
                player = next(
                    (t for t in game.resolve_targets(stack_object) if isinstance(t, Player)), None
                )
                if player is None:
                    return
            discard_equal_to_stat(
                game,
                player.username,
                referent,
                ref.stat,
                getattr(stack_object, "source_name", None) or getattr(stack_object, "name", ""),
                source_id_of(stack_object),
            )

        return discard, ref, who.startswith("target")
    if (mill := parse_mill_clause(sentence)) is not None:
        ref = parse_stat_phrase(mill.expr or "") if mill.kind == "equal" else None
        if ref is None or mill.who not in ("you", "target player", "target opponent"):
            return None
        who = mill.who

        def mill_cards(game: "Game", stack_object: Any, referent: Referent | None) -> None:
            amount = stat_value(referent, ref.stat)
            apply_mill(game, stack_object, who, lambda *_: amount)

        return mill_cards, ref, who.startswith("target")
    if (damage := parse_damage_clause(sentence)) is not None:
        ref = parse_stat_phrase(damage.expr or "") if damage.expr is not None else None
        if ref is None or ref.anchor is not Anchor.SACRIFICED or "," in damage.source:
            # Damage equal to the source's own, a target's or a bitten
            # creature's characteristic is the established damage rungs'.
            return None
        from .effects._common import _targets_understood

        if not re.search(r"\btarget\b", damage.to) or not _targets_understood(
            damage.to, allow_player_targets=True
        ):
            return None

        def deal(game: "Game", stack_object: Any, referent: Referent | None) -> None:
            amount = stat_value(referent, ref.stat)
            source = _source_of(game, stack_object)
            for target in game.resolve_targets(stack_object):
                game.deal_damage(target, amount, source=source)

        return deal, ref, False
    if (put := parse_put_counters(sentence)) is not None:
        ref = parse_stat_phrase(put.expr or "") if put.x else None
        if (
            ref is None
            or put.kind not in ("+1/+1", "-1/-1")
            or put.on != "target creature you control"
        ):
            return None
        kind = put.kind

        def counters(game: "Game", stack_object: Any, referent: Referent | None) -> None:
            amount = stat_value(referent, ref.stat)
            if amount <= 0:
                return
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                    game.add_counters(target, kind, amount)

        return counters, ref, False
    return None


def _condition_check(condition: str) -> Callable[["Game", Any, "Referent | None"], bool] | None:
    """A leading "if <condition>," as a check made when the sentence runs."""
    if (match := _WAS_A_RE.fullmatch(condition)) is not None:
        kind = match.group("kind")
        return lambda _game, _stack_object, referent: referent is not None and referent.is_a(kind)
    from .conditions import claims

    if not claims(condition):
        return None

    def holds(game: "Game", stack_object: Any, _referent: "Referent | None") -> bool:
        controller = game.controller_of(stack_object).username
        return bool(game.condition_holds(controller, condition, _source_of(game, stack_object)))

    return holds


@dataclass(frozen=True)
class AmountSentence:
    """One parsed sentence: what it does with the referent."""

    action: Action
    ref: StatRef
    optional: bool
    targets_player: bool
    prompt: str
    check: Callable[["Game", Any, "Referent | None"], bool] | None = None

    def run(self, game: "Game", stack_object: Any, referent: "Referent | None") -> None:
        if self.check is not None and not self.check(game, stack_object, referent):
            return
        if self.optional:
            from .decisions import source_id_of

            if not game.may(
                game.controller_of(stack_object),
                self.prompt,
                source=getattr(stack_object, "source_name", None)
                or getattr(stack_object, "name", None),
                source_id=source_id_of(stack_object),
            ):
                return
        self.action(game, stack_object, referent)


@functools.cache
def parse_amount_sentence(sentence: str) -> AmountSentence | None:
    """One sentence that spends a referenced characteristic, or `None`."""
    text = normalize(sentence)
    if " equal to " not in text and ", where x is " not in text:
        return None
    check = None
    if (conditional := _IF_RE.fullmatch(text)) is not None:
        if conditional.group("condition") == "you do":
            return None  # a rider on an action the text just took, not a board condition
        check = _condition_check(conditional.group("condition"))
        if check is None:
            return None
        text = conditional.group("rest")
    optional = _MAY_PREFIX_RE.match(text) is not None
    if optional:
        text = _MAY_PREFIX_RE.sub("", text, count=1)
        text = f"you {text}" if not text.startswith(("you ", "target ")) else text
    parsed = _parse_effect_sentence(text)
    if parsed is None:
        return None
    action, ref, targets_player = parsed
    return AmountSentence(action, ref, optional, targets_player, text, check)


# --------------------------------------------------------------------------
# The whole text
# --------------------------------------------------------------------------

_EDICT_RE = re.compile(r"^target (?:player|opponent) sacrifices a creature(?: of their choice)?$")
_EDICT_THEN_RE = re.compile(
    r"^(?P<edict>target (?:player|opponent) sacrifices a creature(?: of their choice)?), "
    r"then (?P<verb>gains|loses) life equal to (?P<amount>.+?)\.?$",
    re.IGNORECASE,
)


def _split_edict_then(sentence: str) -> list[str]:
    """ "Target player sacrifices a creature of their choice, then gains life
    equal to that creature's toughness." as the edict and "that player gains
    ..." (CR 608.2c): the player who sacrificed is the one who gains."""
    match = _EDICT_THEN_RE.fullmatch(sentence.strip())
    if match is None:
        return [sentence]
    return [
        f"{match.group('edict')}.",
        f"That player {match.group('verb')} life equal to {match.group('amount')}.",
    ]


def referenced_stat_effect(text: str, *, for_spell: bool) -> Callable[["Game", Any], None] | None:
    """The effect of `text` when it spends a referenced characteristic, or
    `None` when it is anything else.

    Either one sentence that names the object itself (a dies or enters trigger,
    a sacrificed cost, "target creature you control"), or an opening part that
    does something to one object ("Destroy target creature.", "Target player
    sacrifices a creature of their choice.") followed by sentences about "its"
    or "that creature's" characteristic (CR 608.2c). The object is fixed before
    the opening part moves it, so a destroyed creature's toughness is the
    toughness it had on the battlefield (CR 608.2h).
    """
    lowered = text.lower()
    if " equal to " not in lowered and "where x is" not in lowered:
        return None
    if not any(word in lowered for word in ("power", "toughness", "mana value")):
        return None
    from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble

    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(collapsed(text)))
    sentences = [part for sentence in sentences for part in _split_edict_then(sentence)]
    segments: list[str | AmountSentence] = []
    for sentence in sentences:
        amount = parse_amount_sentence(sentence)
        if amount is not None:
            segments.append(amount)
        elif segments and isinstance(segments[-1], str):
            segments[-1] = f"{segments[-1]} {sentence}"
        else:
            segments.append(sentence)
    amounts = [segment for segment in segments if isinstance(segment, AmountSentence)]
    if not amounts:
        return None
    if len(segments) == 1:
        sentence = amounts[0]

        def single(game: "Game", stack_object: Any) -> None:
            sentence.run(
                game, stack_object, default_referent(game, stack_object, sentence.ref.anchor)
            )

        return single
    opening = segments[0]
    if (
        len(segments) >= 3
        and isinstance(opening, str)
        and isinstance(segments[-1], str)
        and all(isinstance(middle, AmountSentence) for middle in segments[1:-1])
    ):
        return _exile_return_discard(opening, tuple(amounts), segments[-1])
    if not isinstance(opening, str) or any(
        not isinstance(rest, AmountSentence) or rest.ref.anchor is not Anchor.ANAPHOR
        for rest in segments[1:]
    ):
        return None
    from .effects import parse_mixed_effect, parse_mixed_effect_for_spell

    first = (parse_mixed_effect_for_spell if for_spell else parse_mixed_effect)(opening)
    if first is None:
        return None
    follow_ups = tuple(amounts)
    if _EDICT_RE.fullmatch(normalize(opening)) is not None:
        return _edict_then(first, follow_ups)
    if "target" not in opening.lower():
        return None
    return _target_then(first, follow_ups)


def _target_then(first: Callable[..., Any], follow_ups: tuple[AmountSentence, ...]):
    def effect(game: "Game", stack_object: Any) -> None:
        targets = [t for t in game.resolve_targets(stack_object) if isinstance(t, CardState)]
        if not targets:
            return  # CR 608.2b: nothing legal left to refer to
        referent = snapshot_of(game, targets[0])
        first(game, stack_object)
        for sentence in follow_ups:
            sentence.run(game, stack_object, referent)

    return effect


def _edict_then(first: Callable[..., Any], follow_ups: tuple[AmountSentence, ...]):
    def effect(game: "Game", stack_object: Any) -> None:
        players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        if not players:
            return
        creatures = {
            permanent.id: snapshot_of(game, permanent)
            for permanent in game.permanents_controlled_by(players[0].username)
            if Type.CREATURE in game.characteristics_of(permanent).types
        }
        first(game, stack_object)
        referent = None
        for card_id, snapshot in creatures.items():
            card = game.find_by_id(card_id)
            if card is None or card.zone is not Zone.BATTLEFIELD:
                referent = snapshot  # CR 701.21a: the one it sacrificed
                break
        for sentence in follow_ups:
            sentence.run(game, stack_object, referent)

    return effect


_RETURN_THAT_CARD_RE = re.compile(
    r"^return (?:it|that card|that creature|that permanent) to the battlefield "
    r"under its owner's control$"
)


def _exile_return_discard(opening: str, amounts: tuple[AmountSentence, ...], tail: str):
    """ "Exile target creature. You draw cards equal to that creature's power.
    At the beginning of your next upkeep, return that card to the battlefield
    under its owner's control. If you do, discard cards equal to that
    creature's toughness." - the exile, the amounts read from the creature as
    it was exiled (CR 608.2h), and a delayed return (CR 603.7) whose "if you
    do" rider reads the returned creature's own characteristic."""
    from .effects._common import _EXILE_TARGET_RE as exile_re
    from .effects._common import (
        _parse_delayed_timing_clause,
        _targets_understood,
    )
    from .effects.text import _plain_resolution_sentences

    exile = exile_re.fullmatch(opening.strip().rstrip("."))
    if exile is None or not _targets_understood(
        exile.group("phrase"), count_agnostic=True, battlefield_only=False
    ):
        return None
    if any(amount.ref.anchor is not Anchor.ANAPHOR for amount in amounts):
        return None
    sentences = _plain_resolution_sentences(tail)
    if len(sentences) != 2:
        return None
    timing = _parse_delayed_timing_clause(sentences[0])
    if timing is None or _RETURN_THAT_CARD_RE.fullmatch(normalize(timing[1])) is None:
        return None
    rider_text = normalize(sentences[1])
    rider = (
        parse_cards_clause(rider_text.removeprefix("if you do, "))
        if rider_text.startswith("if you do, ")
        else None
    )
    rider_ref = (
        None
        if rider is None or rider.draws or rider.kind != "equal" or rider.subject is not None
        else parse_stat_phrase(rider.expr or "")
    )
    if rider_ref is None or rider_ref.anchor is not Anchor.ANAPHOR:
        return None
    step = timing[0]
    own_turn = "your next" in sentences[0].lower()
    stat = rider_ref.stat

    def effect(game: "Game", stack_object: Any) -> None:
        from .abilities import TriggerEvent
        from .delayed import DelayedTrigger, ReturnSubjectThenDiscardItsStat

        targets = [t for t in game.resolve_targets(stack_object) if isinstance(t, CardState)]
        if not targets:
            return
        target = targets[0]
        referent = snapshot_of(game, target)
        game.exile_permanent(target)
        for amount in amounts:
            amount.run(game, stack_object, referent)
        if target.zone is not Zone.EXILE:
            return  # CR 111.8: a token that left the battlefield cannot come back
        controller = game.controller_of(stack_object).username
        is_spell = isinstance(stack_object, CardState)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=tail,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=controller,
                source_id=stack_object.id if is_spell else stack_object.source_id,
                source_name=stack_object.name if is_spell else stack_object.source_name,
                subject_id=target.id,
                only_when_active=controller if own_turn else None,
                expected_zone=Zone.EXILE,
                expected_stamp=target.zone_change_stamp,
                effect=ReturnSubjectThenDiscardItsStat(stat=stat),
            )
        )

    return effect
