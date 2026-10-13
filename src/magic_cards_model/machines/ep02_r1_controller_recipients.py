"""EP-02 R1 T4: readers for four gaps EP-01-R3 left open.

1. **The controller of a referenced object as a recipient.** "Whenever enchanted
   land becomes tapped, its controller loses 2 life", "Whenever a creature
   attacks you, that creature's controller loses 1 life", "Destroy target
   creature. Its controller mills cards equal to that creature's power." The
   recipient is the controller of the object the text (or its trigger event)
   just named (CR 109.5 for "you"/"your"; CR 303.4e: an Aura's controller and
   the enchanted object's controller need not be the same). Taken before the
   text moves the object (CR 608.2h), from last known information once it is
   gone (CR 603.10a).
2. **"Destroy it"** for the object a trigger's event names (Spreading Algae).
3. **Attach, then a rider** ("you may attach it to target creature you control.
   If you do, that creature gains first strike until end of turn and must be
   blocked this turn if able.", CR 509.1c).
4. **"Permanents of the chosen color"** in a board condition (CR 603.8 state
   trigger, CR 614.12a choice read back).

The amounts ("equal to its toughness") are read by `ep02_r1_referenced_stat`
(T6); this module only adds who receives them.
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from .amount_sentences import change_life, mill_players, parse_life_clause, parse_mill_clause
from .ep02_r1_referenced_stat import (
    Anchor,
    Referent,
    default_referent,
    normalize,
    parse_stat_phrase,
    snapshot_of,
    stat_value,
)

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack

# --------------------------------------------------------------------------
# The recipient sentence: "<its controller> <verb phrase>"
# --------------------------------------------------------------------------

#: "its controller", "that creature's controller", "that permanent's controller"
#: (and the land/artifact/enchantment/card forms): CR 109.5 - the controller of
#: the object the text or its trigger named.
CONTROLLER_ANAPHOR = (
    r"(?:its|that (?:creature|permanent|land|artifact|enchantment|card|planeswalker)'s) controller"
)
_RECIPIENT_RE = re.compile(rf"^{CONTROLLER_ANAPHOR} (?P<predicate>.+)$", re.IGNORECASE)


#: `(game, recipient, referent, source name, source id)`.
Run = Callable[["Game", Player, "Referent | None", str, "str | None"], None]


@dataclass(frozen=True)
class Predicate:
    """What happens to the recipient."""

    run: Run
    stat: str | None = None
    """The characteristic of the referent the amount reads, or `None`."""
    new: bool = False
    """True for a verb phrase `effects/text._parse_referent_clause` cannot read
    (a mill, or an amount that is a characteristic), so a whole-text reader
    claims only the texts the older pair parsers could not."""


def _lose_or_gain(gains: bool, amount: int | None, stat: str | None) -> Run:
    def run(
        game: "Game", player: Player, referent: Referent | None, name: str, source_id: str | None
    ) -> None:
        count = amount if stat is None else stat_value(referent, stat)
        change_life(game, [player], [count or 0], gains)  # CR 107.1b: a negative amount is zero

    return run


def _mill(amount: int | None, stat: str | None) -> Run:
    def run(
        game: "Game", player: Player, referent: Referent | None, name: str, source_id: str | None
    ) -> None:
        mill_players(game, [player], [amount if stat is None else stat_value(referent, stat)])

    return run


def _anaphor_stat(expr: str | None) -> str | None:
    ref = parse_stat_phrase(expr or "")
    return None if ref is None or ref.anchor is not Anchor.ANAPHOR else ref.stat


@functools.cache
def parse_predicate(text: str) -> Predicate | None:
    """The verb phrase of a recipient sentence ("loses 2 life", "mills three
    cards", "loses life equal to its toughness"), or `None`; the wording is
    `amount_sentences`'. Other verbs ("draws a card", "creates a Treasure
    token") have their own readers."""
    life = parse_life_clause(text)
    if life is not None and life.subject is None:
        if life.kind == "fixed":
            return Predicate(_lose_or_gain(life.gains, life.n, None))
        if life.kind == "equal" and (stat := _anaphor_stat(life.expr)) is not None:
            return Predicate(_lose_or_gain(life.gains, None, stat), stat, True)
        return None
    mill = parse_mill_clause(text)
    if mill is not None and mill.subject is None:
        if mill.kind == "fixed":
            return Predicate(_mill(mill.n, None), None, True)
        if mill.kind == "equal" and (stat := _anaphor_stat(mill.expr)) is not None:
            return Predicate(_mill(None, stat), stat, True)
    return None


# --------------------------------------------------------------------------
# A trigger's own event as the referent
# --------------------------------------------------------------------------

_BLOCKS_OBJECT_RE = re.compile(r"\bblocks (?:a|an|another|target|one|that)\b", re.IGNORECASE)


def event_referent_card(game: "Game", ability: "AbilityOnStack") -> CardState | None:
    """The object "its" / "that creature" / "that land" names for an ability:
    the event's subject, except that a block event names two objects (subject:
    the blocker, related: the blocked attacker) and "blocks a creature" is
    about the attacker, "becomes blocked by a creature" and a bare "blocks"
    about the blocker (CR 509.1). An ability with no event ("Tap target
    creature. Its controller loses 2 life.") names its own first target."""
    from .abilities import TriggerEvent

    event = ability.event
    if event is None:
        return next((t for t in game.resolve_targets(ability) if isinstance(t, CardState)), None)
    wanted = event.subject_id
    if event.event is TriggerEvent.BLOCKS:
        condition = getattr(getattr(ability, "ability", None), "condition", "") or ""
        if _BLOCKS_OBJECT_RE.search(condition) and "becomes blocked" not in condition.lower():
            wanted = event.related_id
    elif event.event is TriggerEvent.DEALS_DAMAGE:
        wanted = event.target_id or event.subject_id
    return None if wanted is None else game.find_by_id(wanted)


def controller_username(game: "Game", card: CardState, event_subject_controller: str | None = None):
    """Who controls `card` as it last existed: the computed controller while it
    is on the battlefield or the stack (CR 613.5), the controller the event
    recorded as it left (CR 603.10a), otherwise its owner (CR 108.3)."""
    if card.zone in (Zone.BATTLEFIELD, Zone.STACK):
        return game.controller_of(card).username
    return event_subject_controller or card.owner


def event_recipient(game: "Game", ability: "AbilityOnStack") -> Player | None:
    """The player "its controller" names for `ability`."""
    event = ability.event
    card = event_referent_card(game, ability)
    if card is None:
        return None
    known = event.subject_controller if event is not None and card.id == event.subject_id else None
    username = controller_username(game, card, known)
    return None if username is None else game.player(username)


def _source_name(stack_object: Any) -> str:
    return getattr(stack_object, "source_name", None) or getattr(stack_object, "name", "")


def event_controller_clause(clause: str) -> Callable[["Game", Any], None] | None:
    """A trigger effect clause "<its controller> <verb phrase>" read against
    the trigger's event, or `None`."""
    from .decisions import source_id_of

    match = _RECIPIENT_RE.fullmatch(" ".join(clause.strip().rstrip(".").split()))
    if match is None:
        return None
    predicate = parse_predicate(match.group("predicate"))
    if predicate is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        recipient = event_recipient(game, ability)
        if recipient is None:
            return
        referent = None
        if predicate.stat is not None:
            card = event_referent_card(game, ability)
            referent = (
                default_referent(game, ability, Anchor.ANAPHOR)
                if card is None
                else snapshot_of(game, card)
            )
        predicate.run(game, recipient, referent, _source_name(ability), source_id_of(ability))

    return effect


# --------------------------------------------------------------------------
# "<Opening about target X>. <Its controller> <verb phrase>."
# --------------------------------------------------------------------------


def target_controller_effect(text: str, *, for_spell: bool) -> Callable[["Game", Any], None] | None:
    """An opening instruction about one target ("Destroy target nonartifact
    creature.", "Up to one target creature gets -2/-0 until end of turn.",
    "Counter target spell.") followed by sentences whose recipient is that
    target's controller (CR 608.2c), when one of them is a verb phrase the
    older pair parsers cannot read (a mill, an amount that is a
    characteristic). The target's controller, and its characteristics when an
    amount needs them, are taken before the opening moves it (CR 608.2h)."""
    lowered = text.lower()
    if " controller " not in lowered and "its controller" not in lowered:
        return None
    from .decisions import source_id_of
    from .effects import parse_mixed_effect, parse_mixed_effect_for_spell
    from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble

    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(" ".join(text.split())))
    split = next(
        (i for i, sentence in enumerate(sentences) if _RECIPIENT_RE.match(normalize(sentence))),
        None,
    )
    if split is None or split == 0:
        return None
    predicates: list[Predicate] = []
    for sentence in sentences[split:]:
        match = _RECIPIENT_RE.fullmatch(normalize(sentence))
        predicate = None if match is None else parse_predicate(match.group("predicate"))
        if predicate is None:
            return None
        predicates.append(predicate)
    if not any(predicate.new for predicate in predicates):
        return None
    opening = " ".join(sentences[:split])
    if "target" not in opening.lower():
        return None
    first = (parse_mixed_effect_for_spell if for_spell else parse_mixed_effect)(opening)
    if first is None:
        return None
    wants_stat = any(predicate.stat is not None for predicate in predicates)

    def effect(game: "Game", stack_object: Any) -> None:
        targets = [t for t in game.resolve_targets(stack_object) if isinstance(t, CardState)]
        if not targets:
            return  # CR 608.2b: nothing legal left to refer to
        target = targets[0]
        username = controller_username(game, target)
        referent = snapshot_of(game, target) if wants_stat else None
        first(game, stack_object)
        if username is None:
            return
        recipient = game.player(username)
        for predicate in predicates:
            predicate.run(
                game, recipient, referent, _source_name(stack_object), source_id_of(stack_object)
            )

    return effect


# --------------------------------------------------------------------------
# "Destroy it" - the object a trigger's event names
# --------------------------------------------------------------------------

_DESTROY_IT_RE = re.compile(r"^destroy it\.?$", re.IGNORECASE)


def destroy_event_subject_effect(text: str) -> Callable[["Game", Any], None] | None:
    """ "When enchanted land becomes tapped, destroy it." - the whole effect is
    "destroy it", so "it" can only be the object the event names (CR 603.2); it
    is destroyed only while it is still on the battlefield (CR 608.2b)."""
    if "destroy it" not in text.lower() or _DESTROY_IT_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        card = event_referent_card(game, ability)
        if card is not None and card.zone is Zone.BATTLEFIELD:
            game.destroy(card)

    return effect


# --------------------------------------------------------------------------
# "you may attach it to target creature you control. If you do, that creature
# <rider>."
# --------------------------------------------------------------------------

_ATTACH_MAY_THEN_RIDER_RE = re.compile(
    r"^you may attach (?P<what>it|this (?:aura|equipment|fortification|permanent)) "
    r"to (?:up to one )?(?P<target>target [^.]*)\.\s*if you do,\s*"
    r"(?P<rider>that (?:creature|permanent|land) [^.]*|untap that (?:creature|permanent|land))\.?$",
    re.IGNORECASE,
)
_MUST_BE_BLOCKED_TAIL_RE = re.compile(
    r"^(?P<head>.*?)(?:,? and |^)must be blocked this turn if able$", re.IGNORECASE
)
_THAT_OBJECT_RE = re.compile(r"\bthat (?:creature|permanent|land)\b", re.IGNORECASE)


def attach_may_then_rider_effect(text: str) -> Callable[["Game", Any], None] | None:
    """ "You may attach it to target creature you control. If you do, that
    creature gains first strike until end of turn and must be blocked this turn
    if able." - CR 701.3a's attach offered as an ordinary "you may" (CR 608.2d),
    then, only if the attach happened ("if you do", CR 608.2c), a rider on the
    attached-to object: a gain, a pump or an untap read by the ordinary clause
    parsers about "target creature", and CR 509.1c's "must be blocked this turn
    if able" granted as the printed "must be blocked if able" line until end of
    turn (CR 611.2a)."""
    match = _ATTACH_MAY_THEN_RIDER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .effects import parse_mixed_effect

    rider = match.group("rider").strip()
    must_be_blocked = False
    tail = _MUST_BE_BLOCKED_TAIL_RE.fullmatch(rider)
    if tail is not None:
        must_be_blocked = True
        rider = tail.group("head").strip()
    inner = None
    if rider:
        # "that creature gains first strike until end of turn" restates the
        # sentence about "target creature", so it acts on exactly the
        # announced target the attach used.
        restated = _THAT_OBJECT_RE.sub(
            lambda m: "target creature" if m.start() else "Target creature", rider, count=1
        )
        if restated.lower().startswith("untap"):
            restated = "Untap target creature"
        inner = parse_mixed_effect(restated.rstrip(".") + ".")
        if inner is None:
            return None
    elif not must_be_blocked:
        return None

    def effect(game: "Game", ability: Any) -> None:
        from .decisions import source_id_of
        from .effects.continuous import _grant_keywords_to, attach_permanent

        source = ability.source(game)
        target = next((t for t in game.resolve_targets(ability) if isinstance(t, CardState)), None)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or target is None
            or target.zone is not Zone.BATTLEFIELD
        ):
            return  # CR 608.2b: nothing legal left to attach to (or to attach)
        controller = game.controller_of(ability)
        if not game.may(
            controller,
            f"attach {source.name} to {target.name}",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        if not attach_permanent(game, source, target):
            return  # CR 608.2c: "if you do" - it did not happen, so no rider
        if inner is not None:
            inner(game, ability)
        if must_be_blocked:
            _grant_keywords_to(
                game,
                target,
                ["This creature must be blocked if able."],
                "until end of turn",
                controller=controller.username,
                source_name=ability.source_name,
            )

    return effect


# --------------------------------------------------------------------------
# "<quality> of the chosen color" in a board condition
# --------------------------------------------------------------------------


def chosen_color_quality(context: Any, state: CardState, characteristics: Any) -> bool:
    """Whether `state` is at least one of the colors the condition's source
    chose as it entered (CR 614.12a), read on the computed characteristics
    (CR 105.2, CR 613.5). A source that chose nothing has no chosen color, so
    nothing is of it."""
    from .conditions.objects import _chosen_colors

    source = context.source
    if source is None:
        return False
    chosen = set(_chosen_colors(source))
    return any(color in chosen for color in characteristics.colors)
