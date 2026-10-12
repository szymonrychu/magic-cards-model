"""The optional cost to attack "You may exert [this creature] as it attacks."
and its linked "When you do, ..." triggered ability (CR 701.43d, CR 508.1g,
CR 607.2h).

CR 508.1g: the active player chooses, as the attackers are declared, which
optional costs they will pay. Exerting is that cost (CR 701.43a: the creature
doesn't untap during its controller's next untap step), and the sentence after
it in the same paragraph is a reflexive trigger linked to the choice
(CR 603.12): it exists only when the creature was exerted this way, goes on the
stack with the attack triggers, and is read by the same reflexive reader every
other "When you do" ability uses. The choice is a plain "you may" question
(`DecisionKind.MAY`), asked once per attacker that prints the line.
"""

import re
from functools import cache
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

_EXERT_AS_IT_ATTACKS_RE = re.compile(
    r"^(?P<once>if this creature hasn't been exerted this turn, )?"
    r"you may exert [^.]+? as it attacks\.(?: when you do, (?P<effect>[^.]+\.?))?$",
    re.IGNORECASE,
)


@cache
def _exert_as_it_attacks(line: str) -> tuple[bool, str | None, bool]:
    match = _EXERT_AS_IT_ATTACKS_RE.fullmatch(" ".join(line.split()))
    if match is None:
        return False, None, False
    return True, match.group("effect"), match.group("once") is not None


def exert_as_it_attacks_effect(line: str) -> tuple[bool, str | None]:
    """Whether `line` is the optional exert cost, and the effect text of its
    linked "When you do" trigger (None when the paragraph prints none)."""
    printed, effect, _once = _exert_as_it_attacks(line)
    return printed, effect


def exert_only_once_each_turn(line: str) -> bool:
    """Whether the exert line is gated on "If this creature hasn't been
    exerted this turn" (Combat Celebrant) - read off `Game.exerted_this_turn`."""
    return _exert_as_it_attacks(line)[2]


def reads_exert_as_it_attacks_line(line: str) -> bool:
    """Whether the whole paragraph is performed: the cost, and a linked effect
    the reflexive reader understands (or none)."""
    from .effects import reflexive_consequence_effect

    printed, effect = exert_as_it_attacks_effect(strip_reminder(line))
    if not printed:
        return False
    # The performer (`ReflexiveWhenYouDoConsequence`) is handed the effect as
    # printed, full stop included, so that is the text judged here.
    return effect is None or reflexive_consequence_effect(effect) is not None


def strip_reminder(line: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", line).strip()


def offer_exert_as_it_attacks(game: "Game", creature: CardState) -> None:
    """Ask the attacking player whether to exert `creature` (CR 508.1g) for
    each such line it prints, and queue the linked trigger when they do."""
    from .delayed import ReflexiveWhenYouDoConsequence
    from .exert_triggers import exert_permanent

    for line in game.characteristics_of(creature).abilities:
        printed, effect = exert_as_it_attacks_effect(strip_reminder(line))
        if not printed:
            continue
        if exert_only_once_each_turn(strip_reminder(line)) and (
            creature.id in game.exerted_this_turn
        ):
            continue
        controller = game.controller_of(creature).username
        chose = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=controller,
                prompt=f"exert {creature.name} as it attacks (CR 701.43d)",
                source=creature.name,
                source_id=source_id_of(creature),
            )
        )
        if not chose:
            continue
        exert_permanent(game, creature)
        if effect:
            game.create_reflexive_trigger(
                text=f"When you do, {effect}",
                controller=controller,
                source_id=creature.id,
                source_name=creature.name,
                callback=ReflexiveWhenYouDoConsequence(),
            )
