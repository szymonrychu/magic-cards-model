"""This-turn effects on spells a player has yet to cast, recorded on `Game`.

Two printed shapes, both one-shot effects of a resolving spell or ability
that reach forward to later casts (CR 611.2a's "continuous effect from a
resolving spell or ability"):

- "The next `<quality>` spell you cast this turn can be cast without paying
  its mana cost." (World War Hulk's chapter I) - CR 118.9's alternative cost
  of nothing, offered to the first spell of that quality its controller casts
  this turn, and used up by that spell whether or not it was taken
  (`NextSpellFreeCastGrant`).
- "`<Quality>` spells you cast this turn cost {N} less to cast." (Armor Wars'
  chapter II, Ballad of the Black Flag's chapter IV) - CR 601.2f's cost
  reduction for every such spell its controller casts this turn
  (`SpellCostReductionGrant`); "The next `<quality>` spell you cast this turn
  costs {N} less to cast." (Kaza, Roil Chaser) is the same grant used up by the
  first such spell (`SpellCostReductionGrant.once`).
- "The next `<quality>` spell you cast this turn has `<keyword>`." (Don &
  Raph, Hard Science's affinity for artifacts, Archway of Innovation's
  improvise) - a cost keyword the next such spell has while its total cost is
  determined (CR 601.2f), used up as that spell becomes cast (CR 601.2i)
  (`NextSpellKeywordGrant`).

`spell_has_quality` reads the quality phrase off the spell: its colour words
(CR 105.1) are one disjunction applying to the whole phrase ("red or green
creature" is a creature that is red or green), and the rest goes through the
search-quality reader every other "`<quality>` card" phrase uses
(`machines/effects._quality_matcher`, which knows CR 700.6's historic). A
phrase `spell_quality_is_readable` refuses is never recorded.
"""

import re
from typing import TYPE_CHECKING

from pydantic import ConfigDict

from ..snapshot import EngineModel

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.card_state import CardState

_COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}


def _comma_list_as_or(quality: str) -> str:
    """ "Artifact, instant, and sorcery" is one disjunction of spell kinds (a
    spell is never two of them at once, so "and" lists what is covered):
    "artifact or instant or sorcery"."""
    if "," not in quality:
        return quality
    return re.sub(r",?\s+(?:and|or)\s+|,\s*", " or ", quality.strip(), flags=re.IGNORECASE)


def _split_colors(quality: str) -> tuple[set[str], str]:
    """The colour letters a quality phrase names, and the rest of it with the
    colours and the "or"/"and" between them taken out."""
    words = _comma_list_as_or(quality).strip().lower().split()
    colors = {_COLOR_WORDS[word.strip(",")] for word in words if word.strip(",") in _COLOR_WORDS}
    if not colors:
        return colors, " ".join(words)
    rest = [word for word in words if word.strip(",") not in _COLOR_WORDS]
    while rest and rest[0] in ("or", "and"):
        rest.pop(0)
    return colors, " ".join(rest)


def spell_quality_is_readable(quality: str) -> bool:
    """Whether every word of `quality` is one `spell_has_quality` reads."""
    from .effects import _search_quality_is_readable

    colors, rest = _split_colors(quality)
    return (bool(colors) and not rest) or (bool(rest) and _search_quality_is_readable(rest))


def spell_has_quality(spell: "CardState", quality: str) -> bool:
    """Whether `spell` is a "`<quality>` spell" - see this module's docstring."""
    from .effects import _quality_matcher

    colors, rest = _split_colors(quality)
    if colors and not any(color.value in colors for color in spell.colors):
        return False
    return not rest or _quality_matcher(rest)(spell)


class NextSpellFreeCastGrant(EngineModel):
    """ "The next `<quality>` spell you cast this turn can be cast without
    paying its mana cost." - offered by `Casting.alternative_costs` and
    `Game.alternative_costs_for` as CR 118.9's "nothing", and removed by
    `Game` as the next such spell becomes cast (CR 601.2i)."""

    model_config = ConfigDict(frozen=True)

    controller: str
    source_name: str
    quality: str
    turn: int
    """`TurnMachine.turns_taken` when it was created - "this turn"."""


class SpellCostReductionGrant(EngineModel):
    """ "`<Quality>` spells you cast this turn cost {N} less to cast." - read by
    `Game`'s CR 601.2f cost reductions for its controller's spells."""

    model_config = ConfigDict(frozen=True)

    controller: str
    source_name: str
    quality: str
    amount: int
    turn: int
    """`TurnMachine.turns_taken` when it was created - "this turn"."""
    once: bool = False
    """"The next `<quality>` spell you cast this turn costs {N} less" (Kaza, Roil
    Chaser): used up by the first such spell cast (CR 601.2i) instead of applying to
    every one."""


#: The keywords "the next `<quality>` spell you cast this turn has `<keyword>`"
#: is read for, each with the rule of the machine that executes it - both
#: act while the total cost is determined (CR 601.2f), before the spell
#: becomes cast and uses the grant up, so nothing is left for a keyword that
#: acts later (storm and cascade trigger on the cast itself).
NEXT_SPELL_KEYWORDS: dict[str, str] = {
    "affinity": "CR 702.41a",
    "improvise": "CR 702.126a",
}


class NextSpellKeywordGrant(EngineModel):
    """ "The next `<quality>` spell you cast this turn has `<keyword>`." -
    read by `machines/spell_grants.granted_spell_keyword_lines` (affinity)
    and `Game.has_granted_improvise` (improvise) for its controller's next
    such spell, and removed by `Game` as that spell becomes cast (CR 601.2i).
    Two of them for the same spell each apply (Don & Raph's own ruling:
    "Those abilities are cumulative")."""

    model_config = ConfigDict(frozen=True)

    controller: str
    source_name: str
    quality: str
    """The printed quality phrase, `""` for "the next spell"."""
    keyword: str
    """Lower case - a key of `NEXT_SPELL_KEYWORDS`."""
    line: str
    """The keyword written out as a card prints it ("Affinity for artifacts")."""
    turn: int
    """`TurnMachine.turns_taken` when it was created - "this turn"."""


def next_spell_keyword_grants_for(
    game: object, spell: "CardState", caster: str
) -> "list[NextSpellKeywordGrant]":
    """The live grants `spell`, which `caster` is casting, answers for: this
    turn's, `caster`'s own, and of a quality `spell` has. Nothing is live for
    a spell that has already become cast - its grant was used up then."""
    turn = getattr(game, "turn", None)
    if turn is None:
        return []
    return [
        grant
        for grant in getattr(game, "next_spell_keyword_grants", [])
        if grant.controller == caster
        and grant.turn == turn.turns_taken
        and (not grant.quality or spell_has_quality(spell, grant.quality))
    ]


def used_up_cost_reductions_for(
    game: object, spell: "CardState", caster: str
) -> "list[SpellCostReductionGrant]":
    """The one-shot ("the next `<quality>` spell") cost reductions `spell`, which
    `caster` is casting, answers for - used up by it as it becomes cast (CR 601.2i)."""
    turn = getattr(game, "turn", None)
    if turn is None:
        return []
    return [
        grant
        for grant in getattr(game, "spell_cost_reduction_grants", [])
        if grant.once
        and grant.controller == caster
        and grant.turn == turn.turns_taken
        and spell_has_quality(spell, grant.quality)
    ]
