"""Exiling a spell as it resolves, and casting free out of a counter-marked
pile in exile (ECL).

**"Exile that card [with a `<kind>` counter on it] instead of putting it into
your graveyard as it resolves[. If you do, `<rider>`.]"** - the effect of a
cast trigger (CR 603.2) that sets up a CR 614.1a replacement for the one
spell its event names: Goliath Daydreamer's "exile that card with a dream
counter on it ...", Feather, the Redeemed's "... If you do, return it to your
hand at the beginning of the next end step." and Lilah, Undefeated
Slickshot's "... If you do, it becomes plotted." The trigger resolves before
the spell (it is above it on the stack, CR 603.3b), so the replacement is
recorded on the spell itself - as one canonical line on its
`CardState.granted_ability_texts` (`resolving_exile_line`) - and read back by
`machines/replacement._stack_replacements` only when the spell is put into
the graveyard *as it resolves* (CR 608.2n): a countered spell doesn't resolve
(CR 701.6a) and goes to the graveyard as usual. The counter is placed as the
card arrives in exile (CR 122.1); "If you do" runs only when the replacement
did exile it (CR 608.2c).

**"You may cast a[n] [`<quality>`] spell from among cards you own in exile
with `<kind>` counters on them without paying its mana cost."** - Goliath
Daydreamer's attack trigger and Dragon-Kami's Egg's dies trigger: a cast
during the trigger's resolution (CR 608.2g) without paying its mana cost
(CR 118.9), out of the cards in exile that the controller owns and that
carry at least one counter of that kind.
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState, ExileMarker
from ..models.zone import Zone
from .decisions import source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

_COUNTER_KIND = r"[a-z][a-z+/-]*"

#: The printed instruction on the cast trigger.
_EXILE_AS_IT_RESOLVES_RE = re.compile(
    r"^exile (?:that card|that spell|it)"
    rf"(?: with an? (?P<kind>{_COUNTER_KIND}) counter on it)? "
    r"instead of putting it into your graveyard as it resolves\."
    r"(?:\s*if you do, (?P<rider>.+?)\.?)?$",
    re.IGNORECASE,
)
#: The canonical line written onto the spell, read back by the replacement.
_GRANTED_LINE_RE = re.compile(
    r"^As this spell resolves, exile it"
    rf"(?: with an? (?P<kind>{_COUNTER_KIND}) counter on it)? "
    r"instead of putting it into your graveyard\."
    r"(?: If you do, (?P<rider>.+?)\.)?$"
)
#: The riders "If you do" may carry.
_RETURN_TO_HAND_AT_NEXT_END_STEP_RE = re.compile(
    r"^return it to your hand at the beginning of the next end step$", re.IGNORECASE
)
_BECOMES_PLOTTED_RE = re.compile(r"^it becomes plotted$", re.IGNORECASE)

_CAST_FROM_COUNTER_PILE_RE = re.compile(
    r"^you may cast an? (?:(?P<quality>[a-z][a-z ]*?) )?spell from among cards you own in "
    rf"exile with (?P<kind>{_COUNTER_KIND}) counters on them without paying its mana cost\.?$",
    re.IGNORECASE,
)

#: CR 207.2's reminder text, which carries no rules meaning.
_REMINDER_RE = re.compile(r"\s*\([^()]*\)")


def _rider_is_readable(rider: str | None) -> bool:
    return rider is None or bool(
        _RETURN_TO_HAND_AT_NEXT_END_STEP_RE.fullmatch(rider) or _BECOMES_PLOTTED_RE.fullmatch(rider)
    )


def resolving_exile_line(kind: str | None, rider: str | None) -> str:
    """The canonical line `parse_exile_as_it_resolves_clause` writes."""
    counter = f" with a {kind} counter on it" if kind else ""
    line = f"As this spell resolves, exile it{counter} instead of putting it into your graveyard."
    if rider:
        line += f" If you do, {rider}."
    return line


def resolving_exile_of(card: CardState) -> tuple[str | None, str | None] | None:
    """`(counter kind, rider)` when `card` carries the line, else None."""
    for line in card.granted_ability_texts:
        match = _GRANTED_LINE_RE.fullmatch(line)
        if match is not None:
            return match.group("kind"), match.group("rider")
    return None


def parse_exile_as_it_resolves_clause(text: str) -> Any:
    """The cast trigger's own effect: mark the spell its event names."""
    cleaned = " ".join(_REMINDER_RE.sub("", text).split())
    match = _EXILE_AS_IT_RESOLVES_RE.fullmatch(cleaned)
    if match is None:
        return None
    kind = (match.group("kind") or "").lower() or None
    rider = match.group("rider")
    if rider is not None:
        rider = rider.strip().rstrip(".").lower()
    if not _rider_is_readable(rider):
        return None
    line = resolving_exile_line(kind, rider)

    def effect(game: "Game", ability: Any) -> None:
        event = getattr(ability, "event", None)
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        if line not in spell.granted_ability_texts:
            spell.granted_ability_texts = (*spell.granted_ability_texts, line)

    return effect


def apply_resolving_exile(game: "Game", card: CardState, event: Any) -> None:
    """The replacement's own apply: exile instead (CR 614.1a), with the
    counter and the rider the line names."""
    marked = resolving_exile_of(card)
    if marked is None:
        return
    kind, rider = marked
    event.destination = Zone.EXILE
    if kind:
        event.exile_counters = {**getattr(event, "exile_counters", {}), kind: 1}
    if rider and _BECOMES_PLOTTED_RE.fullmatch(rider):
        event.exile_marker = ExileMarker.PLOTTED
    elif rider:
        event.exile_rider = rider
        event.exile_rider_controller = card.controller


def after_resolving_exile(game: "Game", card: CardState, event: Any) -> None:
    """What happens once the card is in exile: its counters (CR 122.1) and a
    delayed rider ("If you do, return it to your hand at the beginning of the
    next end step", CR 603.7)."""
    for kind, amount in (getattr(event, "exile_counters", None) or {}).items():
        card.add_counters(kind, amount)
    rider = getattr(event, "exile_rider", None)
    if rider and _RETURN_TO_HAND_AT_NEXT_END_STEP_RE.fullmatch(rider):
        from ..machines import Step
        from .abilities import TriggerEvent
        from .delayed import DelayedTrigger, return_subject_to_hand

        controller = getattr(event, "exile_rider_controller", None) or card.owner
        game.delayed_triggers.create(
            DelayedTrigger(
                text="At the beginning of the next end step, return it to your hand.",
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=controller,
                source_id=card.id,
                source_name=card.name,
                subject_id=card.id,
                expected_zone=Zone.EXILE,  # CR 603.7c
                expected_stamp=card.zone_change_stamp,
                effect=return_subject_to_hand,
            )
        )


def parse_cast_from_counter_pile_clause(text: str) -> Any:
    """`_CAST_FROM_COUNTER_PILE_RE`'s effect."""
    match = _CAST_FROM_COUNTER_PILE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    quality = (match.group("quality") or "").strip().lower()
    if quality:
        from .next_spell import spell_quality_is_readable

        if not spell_quality_is_readable(quality):
            return None
    kind = match.group("kind").lower()

    def effect(game: "Game", ability: Any) -> None:
        from .effects import _offer_free_casts_from_among
        from .next_spell import spell_has_quality

        controller = game.controller_of(ability).username
        pile = [
            card
            for card in game.exile
            if card.owner == controller
            and card.counters[kind] > 0
            and not card.card.is_land
            and (not quality or spell_has_quality(card, quality))
        ]
        if not pile:
            return
        _offer_free_casts_from_among(
            game,
            pile,
            controller,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
            play=False,
            limit=1,
        )

    return effect


def resolving_exile_ability_effect(effect_text: str) -> Any:
    """This module's ability readers, or None."""
    for reader in (parse_exile_as_it_resolves_clause, parse_cast_from_counter_pile_clause):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None
