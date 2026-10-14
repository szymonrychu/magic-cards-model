"""Losing unspent mana, and the static abilities that replace it.

CR 106.4 (looked up this session): "Each player's mana pool empties at the
end of each step and phase, and the player is said to lose this mana." CR
500.5 makes that emptying a turn-based action as each step and phase ends.

Two printed static shapes replace that loss (CR 614.1a: "Effects that use
the word 'instead' are replacement effects"), read here off the permanent's
own computed ability lines (CR 613.1f - a permanent that lost its abilities
replaces nothing), never off a card name:

- "If you would lose unspent mana, that mana becomes <colour> instead."
  (Omnath, Locus of All: black; Kruphix, God of Horizons and Horizon Stone:
  colorless; Ozai, the Phoenix King: red.) The mana is not lost; it stays,
  as that colour. The printings' rulings: any restriction or rider the mana
  carried "remain[s] associated with that mana" (`ManaPool.empty`).
- "You don't lose unspent [<colour>] mana as steps and phases end." /
  "Players don't lose unspent mana as steps and phases end." (Leyline Tyrant,
  Ashling, Flame Dancer, Electro, Omnath, Locus of Mana, Fangorn, Upwelling.)
  That mana is simply not lost.

CR 616.1: "If two or more replacement and/or prevention effects are
attempting to modify the way an event affects an object or player, the
affected object's controller (or its owner if it has no controller) or the
affected player chooses one to apply". CR 616.1f then repeats the choice
over the effects that still apply - so with Omnath, Locus of Mana and
Omnath, Locus of All both out, applying Locus of Mana first keeps the green
as green and leaves Locus of All only the rest to turn black, while applying
Locus of All first turns everything black and leaves Locus of Mana nothing
to keep. CR 614.5: each
effect gets one opportunity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card import Color
from .decisions import Decision, DecisionKind

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from ..models.mana import ManaPool

_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
    "colorless": Color.COLORLESS,
}
_COLOR_WORD = r"white|blue|black|red|green|colorless"

#: "If you would lose unspent mana, that mana becomes <colour> instead."
_BECOMES_RE = re.compile(
    rf"^if you would lose unspent mana, that mana becomes (?P<color>{_COLOR_WORD}) instead\.?$",
    re.IGNORECASE,
)

#: "You don't lose unspent [<colour>] mana as steps and phases end." and
#: Upwelling's "Players don't lose ..." (every player's mana).
_DONT_LOSE_RE = re.compile(
    rf"^(?P<who>you|players) don['’]t lose unspent (?:(?P<color>{_COLOR_WORD}) )?mana "
    r"as steps and phases end\.?$",
    re.IGNORECASE,
)

_EVERY_TYPE = frozenset(Color)

#: "Until end of turn, you don't lose unspent [<colour>] mana as steps and
#: phases end." (The Last Agni Kai) - the same replacement as `_DONT_LOSE_RE`
#: for the rest of the turn, made by a resolving spell or ability instead of a
#: permanent. CR 611.2a: a continuous effect from a resolving spell lasts as
#: long as it states; CR 611.2c: it is not locked in to the mana already in the
#: pool, so mana added later this turn is kept too. CR 514.2 ends it in the
#: cleanup step (`Game.cleanup_step`), before that step's own emptying.
_UNTIL_END_OF_TURN_DONT_LOSE_RE = re.compile(
    rf"^until end of turn, you don['’]t lose unspent (?:(?P<color>{_COLOR_WORD}) )?mana "
    r"as steps and phases end\.?$",
    re.IGNORECASE,
)

#: A recorded turn-scoped keep effect is a `CastingRuleEffect` whose `kind` is
#: this prefix plus the colour word it keeps, or `:all` for every type of mana.
KEEP_UNSPENT_MANA_RULE = "keep_unspent_mana"


def read_until_end_of_turn_dont_lose_unspent_mana(text: str) -> str | None:
    """The `CastingRuleEffect.kind` that records the turn-scoped sentence
    `_UNTIL_END_OF_TURN_DONT_LOSE_RE` reads (`KEEP_UNSPENT_MANA_RULE:<colour or
    all>`), or `None` when `text` is not that sentence."""
    match = _UNTIL_END_OF_TURN_DONT_LOSE_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    color = match.group("color")
    return f"{KEEP_UNSPENT_MANA_RULE}:{color.lower() if color else 'all'}"


@dataclass(frozen=True)
class ManaLossReplacement:
    """One static ability replacing a player's loss of unspent mana.

    `keep` is the mana it keeps as it is (every type for "unspent mana",
    one colour for "unspent red mana"), `becomes` the colour the mana it
    replaces becomes instead. Exactly one of the two is set. `source` is the
    permanent whose static ability this is, or `None` for a turn-scoped
    effect a spell recorded (`KEEP_UNSPENT_MANA_RULE`), whose source is gone."""

    source: CardState | None
    name: str
    keep: frozenset[Color] | None = None
    becomes: Color | None = None


def reads_unspent_mana_line(text: str) -> bool:
    """Whether `text` is one of the static lines this module performs -
    `support.py`'s credit."""
    line = collapsed(text.strip())
    return bool(_BECOMES_RE.match(line) or _DONT_LOSE_RE.match(line))


def _computed_lines(game: Game, permanent: CardState) -> tuple[str, ...]:
    try:
        return tuple(game.characteristics_of(permanent).abilities)
    except KeyError:
        return tuple((permanent.oracle_text or "").splitlines())


def mana_loss_replacements(game: Game, username: str) -> list[ManaLossReplacement]:
    """Every static on the battlefield that would replace `username` losing
    unspent mana right now (CR 604.2: only while its source is there)."""
    found: list[ManaLossReplacement] = []
    for permanent in game.battlefield:
        controller = game.controller_of(permanent).username
        for line in _computed_lines(game, permanent):
            text = collapsed(line.strip())
            becomes = _BECOMES_RE.match(text)
            if becomes is not None:
                if controller == username:
                    found.append(
                        ManaLossReplacement(
                            source=permanent,
                            name=permanent.name,
                            becomes=_COLOR_WORDS[becomes.group("color").lower()],
                        )
                    )
                continue
            keeps = _DONT_LOSE_RE.match(text)
            if keeps is None:
                continue
            if keeps.group("who").lower() == "you" and controller != username:
                continue
            color = keeps.group("color")
            found.append(
                ManaLossReplacement(
                    source=permanent,
                    name=permanent.name,
                    keep=frozenset({_COLOR_WORDS[color.lower()]}) if color else _EVERY_TYPE,
                )
            )
    for effect in game.casting_rule_effects:
        prefix, _, scope = effect.kind.partition(":")
        if prefix != KEEP_UNSPENT_MANA_RULE or effect.controller != username:
            continue
        found.append(
            ManaLossReplacement(
                source=None,
                name=effect.source_name,
                keep=_EVERY_TYPE if scope == "all" else frozenset({_COLOR_WORDS[scope]}),
            )
        )
    return found


def _would_lose(pool: ManaPool, expiring: frozenset[object]) -> dict[Color, int]:
    """The mana in `pool` that this emptying would lose, before any
    replacement: everything but retained mana whose own scope has not ended."""
    survived: dict[Color, int] = {}
    for entry in pool.retained:
        if entry.until in expiring:
            continue
        for color, amount in entry.amounts.items():
            survived[color] = survived.get(color, 0) + amount
    return {
        color: amount - survived.get(color, 0)
        for color, amount in pool.floating.items()
        if amount - survived.get(color, 0) > 0
    }


def settle_mana_loss(
    game: Game, username: str, pool: ManaPool, expiring: frozenset[object]
) -> tuple[frozenset[Color], Color | None]:
    """What replaces `username` losing the unspent mana in `pool` at this
    boundary: the colours kept as they are, and the colour whatever is still
    lost becomes instead (or `None`: it is lost).

    CR 616.1/616.1f: while more than one effect still applies, the affected
    player chooses which applies next, asked through `Game.ask` as a "choose
    one" - the same question `replacement.choose_effect` puts for every other
    CR 616.1 order."""
    lost = set(_would_lose(pool, expiring))
    if not lost:
        return frozenset(), None
    effects = mana_loss_replacements(game, username)
    kept: set[Color] = set()
    applied: set[int] = set()
    while True:
        remaining = lost - kept
        candidates = [
            (index, effect)
            for index, effect in enumerate(effects)
            if index not in applied
            and remaining
            and (effect.becomes is not None or bool(effect.keep and effect.keep & remaining))
        ]
        if not candidates:
            return frozenset(kept), None
        distinct = {(effect.name, effect.keep, effect.becomes) for _index, effect in candidates}
        index, chosen = candidates[0]
        if len(distinct) > 1:
            options: list[str] = []
            for _index, effect in candidates:
                option = effect.name
                suffix = 2
                while option in options:
                    option = f"{effect.name} ({suffix})"
                    suffix += 1
                options.append(option)
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_MODE,
                    player=username,
                    prompt=(
                        "choose which replacement effect applies first to the unspent "
                        "mana you would lose (CR 616.1): "
                        + "; ".join(
                            f"{option} - "
                            + (
                                f"that mana becomes {effect.becomes.name.lower()} instead"
                                if effect.becomes is not None
                                else "you don't lose it"
                            )
                            for option, (_index, effect) in zip(options, candidates, strict=True)
                        )
                    ),
                    options=tuple(options),
                    # The event is a player's loss of mana, not anything one
                    # object asks - the same `None` `replacement.choose_effect`
                    # passes for a CR 616.1 order over an event on a player.
                    source_id=None,
                )
            )
            if answer in options:
                index, chosen = candidates[options.index(answer)]
        applied.add(index)
        if chosen.becomes is not None:
            return frozenset(kept), chosen.becomes
        kept |= chosen.keep or frozenset()
