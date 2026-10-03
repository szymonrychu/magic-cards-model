"""Sentences that follow a mass pump or grant and refer back to its group.

A mass pump ("Creatures you control get +1/+1 until end of turn.") fixes its
group once, as it resolves (CR 611.2c). Two follow-up sentences are read here,
each against that fixed group or a fresh filtered one, in printed order
(CR 608.2c):

- "Untap them." / "Untap those creatures." / "Untap each creature you
  control." - the anaphora is exactly the group the pump affected (Rally to
  Battle, War Flare, Tenacity, Ready // Willing, Jeskai Ascendancy, Essence
  of Antiquity, ...). CR 701.26b.
- "<Kithkin|Warrior|White|Colorless> creatures you control (also) gain
  <keyword> until end of turn." - a second grant, on the creatures you control
  that match the filter at that moment (Gallant Fowlknight, Rush of Battle,
  Sanctified Charge, Swarm Surge). CR 205.3m, CR 105.2.

`machines/effects.py` calls `ability_effect` / `spell_effect` from its
mass-pump remainder path; a remainder with any other sentence returns `None`
so the ordinary remainder handling stays in charge.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..data.subtypes import canonical_subtype
from ..models.card import Color
from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game
    from .abilities import AbilityOnStack
    from .layers import Characteristics

#: "Untap them." / "Untap those creatures." / "Untap each creature you control."
_UNTAP_RE = re.compile(r"^untap (?:them|those creatures|each creature you control)$", re.IGNORECASE)
#: "Kithkin creatures you control also gain first strike until end of turn."
_SUBSET_GRANT_RE = re.compile(
    r"^(?P<filter>[a-z]+) creatures you control (?:also )?gain (?P<keywords>.+?) "
    r"until end of turn$",
    re.IGNORECASE,
)
_COLORS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}

Matches = Callable[["Characteristics"], bool]
#: One step: `None` untaps the pumped group; otherwise a grant sentence on the
#: creatures you control that satisfy the predicate.
FollowupStep = tuple[str, Matches] | None


def _filter(word: str) -> Matches | None:
    lowered = word.lower()
    if lowered == "colorless":
        return lambda chars: not chars.colors
    if lowered in _COLORS:
        color = _COLORS[lowered]
        return lambda chars: color in chars.colors
    subtype = canonical_subtype(word)
    if subtype is None:
        return None
    return lambda chars: subtype in {name.lower() for name in chars.subtypes}


def parse(remainder: str) -> list[FollowupStep] | None:
    """The follow-up steps `remainder` is made of, or `None` when any of its
    sentences is not one of the two shapes above."""
    steps: list[FollowupStep] = []
    for sentence in re.split(r"(?<=\.)\s+", remainder.strip()):
        text = sentence.strip().rstrip(".").strip()
        if not text:
            continue
        if _UNTAP_RE.fullmatch(text):
            steps.append(None)
            continue
        grant = _SUBSET_GRANT_RE.fullmatch(text)
        matches = _filter(grant.group("filter")) if grant else None
        if grant is None or matches is None:
            return None
        steps.append(
            (f"creatures you control gain {grant.group('keywords')} until end of turn.", matches)
        )
    return steps or None


def _run(
    steps: list[FollowupStep],
    game: "Game",
    source: CardState,
    controller: str,
    template: str,
    magnitude_expr: object,
) -> None:
    from .effects import _run_mass_pump

    group = _run_mass_pump(game, source, controller, template, magnitude_expr)  # type: ignore[arg-type]
    for step in steps:
        if step is None:
            for creature in group:
                if creature.zone is Zone.BATTLEFIELD and creature.tapped:
                    creature.untap(exert_applies=False)  # CR 701.26b
            continue
        sentence, matches = step
        board = game.computed_board()
        _run_mass_pump(
            game,
            source,
            controller,
            sentence,
            None,
            restrict=lambda creature, matches=matches, board=board: matches(board.of(creature)),
        )


def ability_effect(remainder: str, template: str, magnitude_expr: object):
    """The mass pump of an ability followed by `remainder`, or `None`."""
    steps = parse(remainder) if remainder else None
    if steps is None:
        return None

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = ability.source(game)
        if source is not None:
            _run(steps, game, source, ability.controller, template, magnitude_expr)

    return effect


def spell_effect(remainder: str, template: str, magnitude_expr: object):
    """The mass pump of a spell followed by `remainder`, or `None`."""
    steps = parse(remainder) if remainder else None
    if steps is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        _run(steps, game, spell, game.controller_of(spell).username, template, magnitude_expr)

    return effect
