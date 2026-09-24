"""Teamwork N: an optional additional cost printed as a keyword line with a
number, in the same "Word N" shape CR 702's own numbered keywords use
(Annihilator N, Afflict N) - `machines.abilities.KeywordAbility.count` reads
the number the same way for any of them.

The keyword itself carries no Comprehensive Rules number - it is specific to
the Marvel Super Heroes set this task's cards are drawn from - so what
actually governs paying it is the general machinery every other optional
additional cost already goes through: CR 601.2b's "the player announces
their intentions to pay any ... additional costs", CR 118.8a/b's "additional
costs" and "some additional costs are optional", and CR 701.26a's tap action
itself. Every printing in the pool spells the cost out identically, in its
own reminder text: "As an additional cost to cast this spell, you may tap
any number of creatures you control with total power N or more." Nothing
requires the tapped creatures to be free of summoning sickness - the
reminder text says only "creatures you control", the same "whether or not
it's affected by summoning sickness" allowance CR 702.51a spells out for
convoke's own tap - so a creature that entered this turn may still pay it;
`pay_teamwork` (`machines/casting.py`) enforces nothing about summoning
sickness, the same way `machines/cost.ComponentKind.TAP` already lets
convoke tap a summoning-sick creature.

"If this spell was cast using teamwork" is CR 601.2b's own kind of rider -
"was kicked"/"a replicate cost was paid" are the templates it is built the
same way as - read by `machines/triggers.intervening_if_holds` and by
`Game.modal_alternative_applies` off `CastRecord.cast_using_teamwork`,
exactly as `CastRecord.kicked` already backs "if this spell was kicked".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..models.card import Card
from .abilities import KeywordAbility, keyword_ability

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game

#: The one keyword this module reads (case-insensitive, matching
#: `KeywordAbility.canonical`'s Scryfall spelling).
TEAMWORK_KEYWORD = "teamwork"


def teamwork_ability(card: Card) -> KeywordAbility | None:
    """This printing's own `Teamwork N` line, or `None` if it has none."""
    return keyword_ability(card, TEAMWORK_KEYWORD)


def teamwork_threshold(card: Card) -> int | None:
    """The `N` in `Teamwork N` - the total power the tapped creatures must
    reach or beat - or `None` for a card with no Teamwork ability at all."""
    ability = teamwork_ability(card)
    if ability is None:
        return None
    return ability.count


def total_power_of(game: Game | None, creatures: Sequence[CardState]) -> int:
    """The combined power of `creatures` right now (CR 208.1), read off the
    computed board (CR 613.5) when a `Game` is available - a continuous
    effect that has already pumped one of the tapped creatures counts
    toward the threshold - and off each `CardState`'s own printed power
    otherwise, the same fallback `machines/cost.py`'s other component
    validators use for a bare, game-less unit test."""
    total = 0
    for creature in creatures:
        power = None
        if game is not None:
            try:
                power = game.characteristics_of(creature).power
            except KeyError:
                power = None
        if power is None:
            power = creature.power
        total += power or 0
    return total


#: "`<verb>` `<target phrase>`[, restriction]. If this spell was cast using
#: teamwork, instead `<verb>` `<target phrase>`[ ...]." - Too Evil to Stay
#: Dead's own "Choose target creature card in your graveyard with mana
#: value 4 or less. If this spell was cast using teamwork, instead choose
#: target creature card in your graveyard." and Cruel Alliance's own "Exile
#: target creature with mana value 3 or less. If this spell was cast using
#: teamwork, instead exile target creature and you gain 3 life." The
#: teamwork twin of `machines/targeting._KICKED_INSTEAD_TARGETS_RE`
#: (CR 601.2c: "A spell may require some targets only if an alternative or
#: additional cost ... is paid" - the same rule kicker's own reader is built
#: on, applied to Teamwork's additional cost instead), kept here rather than
#: in `machines/targeting.py` itself since that module is another task's own
#: file in this round - this is Teamwork's own reader, called from
#: `machines/casting.py` and `models/game.py` the identical way
#: `kicked_instead_target_text` already is.
#:
#: Wider than the kicker reader in one way: the kicker shape's own only pool
#: printing always opens with "Choose", but Teamwork's own cards open with
#: whichever verb the base instruction actually is ("Exile", "Choose") -
#: `(?P<lead_verb>[a-z]+)` reads it once and the backreference `(?P=lead_
#: verb)` requires the alternative sentence to repeat the identical word,
#: so a coincidental "target ..." phrase elsewhere in the text is never
#: mistaken for this shape. Each target phrase is captured only up to the
#: first comma, "and", or full stop after it - a printed restriction
#: ("with mana value N or less") or a trailing rider ("and you gain N
#: life") is left for the ordinary spell-effect parser to read on its own,
#: the same way a trailing shared consequence sentence (Too Evil to Stay
#: Dead's own "Return the chosen card to the battlefield.") already is.
_TEAMWORK_INSTEAD_TARGETS_RE = re.compile(
    r"^(?:teamwork \d+ \([^)]*\)\n)?"
    r"(?P<lead_verb>[a-z]+) (?P<base>target[^.\n,]*?)(?=[.,]|\s+and\b)[^.\n]*\.\s*"
    r"if this spell was cast using teamwork, instead (?P=lead_verb) "
    r"(?P<teamwork>target[^.\n,]*?)(?=[.,]|\s+and\b)",
    re.IGNORECASE,
)


def teamwork_instead_target_text(text: str) -> tuple[str, str] | None:
    """The unpaid and teamwork-paid "choose ..." sentences of a spell whose
    Teamwork cost changes which targets it chooses
    (`_TEAMWORK_INSTEAD_TARGETS_RE`), each written as its own sentence for
    `machines.targeting.profile_for_text`, or `None`."""
    match = _TEAMWORK_INSTEAD_TARGETS_RE.search(text.strip())
    if match is None:
        return None
    return f"choose {match.group('base')}.", f"choose {match.group('teamwork')}."


def teamwork_payment_refusal(
    game: Game | None,
    caster: str,
    threshold: int,
    creatures: Sequence[CardState],
) -> str | None:
    """Why `creatures` cannot pay a `Teamwork <threshold>` cost right now, or
    `None` if they can (CR 118.3, CR 601.2b).

    Shared between `Casting.pay_teamwork` (which raises this as a
    `ValueError`) and any future caller that only wants the question
    answered, the same `why_not`-style split every other cost in
    `machines/cost.py` already keeps.
    """
    from ..models.zone import Zone

    if not creatures:
        return "teamwork is paid with at least one creature or not at all (CR 118.8b)"
    seen: set[object] = set()
    for creature in creatures:
        if creature.id in seen:
            return f"{creature.name} cannot pay teamwork's cost twice (CR 109.1)"
        seen.add(creature.id)
        if creature.zone is not Zone.BATTLEFIELD:
            return f"{creature.name} is not on the battlefield, so it cannot pay teamwork's cost"
        if creature.controller is not None and creature.controller != caster:
            return f"{caster} does not control {creature.name}"
        if creature.tapped:
            return f"{creature.name} is already tapped, so it cannot pay teamwork's cost"
        from ..models.card import Type

        is_creature = True
        if game is not None:
            try:
                is_creature = game.characteristics_of(creature).is_creature
            except KeyError:
                is_creature = Type.CREATURE in creature.types
        else:
            is_creature = Type.CREATURE in creature.types
        if not is_creature:
            return f"{creature.name} is not a creature, so it cannot pay teamwork's cost"
    total = total_power_of(game, creatures)
    if total < threshold:
        return (
            f"teamwork needs total power {threshold} or more, {total} offered "
            f"(Teamwork {threshold})"
        )
    return None
