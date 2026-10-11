"""What a creature counts for when it pays a crew, saddle or station cost.

CR 702.122a / CR 702.171a count the "total power" of the tapped creatures; a
static ability can change what one creature counts for:

- "This creature saddles Mounts and crews Vehicles as though its power were 2
  greater." (Cloudspire Captain, Deathless Pilot, Dynamite Diver) and the
  crew-only "This creature crews Vehicles as though its power were 2 greater."
  (Hotshot Mechanic): the creature's power plus N.
- "This creature crews Vehicles using its toughness rather than its power."
  (Giant Ox, Interface Ace's saddle-and-crew form): its toughness instead.
- "Each creature you control with toughness greater than its power stations
  permanents using its toughness rather than its power." (Tapestry Warden): a
  group grant for CR 702.184a's station cost.

Read live off the computed abilities (CR 613.5), so a creature that lost its
abilities counts for its plain power.
"""

import re
from functools import cache
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from .objects_as_costs import power_of

if TYPE_CHECKING:
    from ..models.game import Game

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_VERBS = r"(?P<verbs>saddles mounts and crews vehicles|crews vehicles|saddles mounts)"
_NUMBER = rf"(?P<n>\d+|{'|'.join(_WORDS)})"
_BONUS_RE = re.compile(
    rf"^(?:this [a-z]+|~) {_VERBS} as though its power were {_NUMBER} greater\.?$",
    re.IGNORECASE,
)
_TOUGHNESS_RE = re.compile(
    rf"^(?:this [a-z]+|~) {_VERBS} using its toughness rather than its power\.?$",
    re.IGNORECASE,
)
_STATION_RE = re.compile(
    r"^each creature you control with toughness greater than its power stations "
    r"permanents using its toughness rather than its power\.?$",
    re.IGNORECASE,
)


@cache
def _read(line: str) -> tuple[frozenset[str], int, bool] | None:
    """The kinds ("crew", "saddle") a self line applies to, its power bonus and
    whether it swaps in toughness - or None for any other line."""
    text = " ".join(line.split())
    if "though its power were" not in text.lower() and "using its toughness" not in text.lower():
        return None
    bonus = _BONUS_RE.match(text)
    swap = _TOUGHNESS_RE.match(text)
    match = bonus or swap
    if match is None:
        return None
    verbs = match["verbs"].lower()
    kinds = frozenset(k for k, word in (("crew", "crews"), ("saddle", "saddles")) if word in verbs)
    if bonus is None:
        return kinds, 0, True
    n = bonus["n"].lower()
    return kinds, int(n) if n.isdigit() else _WORDS[n], False


def reads_crew_saddle_line(text: str) -> bool:
    """Whether `text` is a contribution line `contribution`/`station_amount` perform."""
    text = " ".join(text.split())
    return _read(text) is not None or _STATION_RE.match(text) is not None


def _abilities(game: "Game", creature: CardState) -> tuple[str, ...]:
    try:
        return tuple(game.characteristics_of(creature).abilities)
    except KeyError:
        return tuple((creature.oracle_text or "").splitlines())


def _toughness_of(game: "Game", creature: CardState) -> int:
    try:
        return game.characteristics_of(creature).numeric_toughness
    except (KeyError, AttributeError):
        return creature.toughness or 0


def contribution(game: "Game", creature: CardState, kind: str) -> int:
    """What `creature` counts for when tapped to pay a crew or saddle cost."""
    bonus, swapped = 0, False
    for line in _abilities(game, creature):
        read = _read(line)
        if read is None or kind not in read[0]:
            continue
        bonus += read[1]
        swapped = swapped or read[2]
    base = _toughness_of(game, creature) if swapped else power_of(creature, game)
    return base + bonus


def total_contribution(game: "Game", creatures: list[CardState], kind: str) -> int:
    return sum(contribution(game, creature, kind) for creature in creatures)


def station_amount(game: "Game", tapped: CardState) -> int:
    """How many charge counters tapping `tapped` to station puts on a
    permanent (CR 702.184a): its power, or its toughness when a permanent its
    controller controls says so and the toughness is greater."""
    power = power_of(tapped, game)
    toughness = _toughness_of(game, tapped)
    if toughness <= power:
        return power
    controller = game.controller_of(tapped).username
    for permanent in game.permanents_controlled_by(controller):
        if any(_STATION_RE.match(" ".join(line.split())) for line in _abilities(game, permanent)):
            return toughness
    return power
