"""Cast triggers that copy the spell cast and hand spells keywords (ECL).

Two printed shapes, both the effect of a CAST_SPELL trigger whose "it" /
"that spell" is CR 607.1-style anaphora back to the spell the event names:

- **"[You may] copy it. [If you do, those spells gain `<keywords>`.] [You
  may choose new targets for the copy.]"** - Spinerock Tyrant's whole
  trigger. CR 707.10: the copy is put onto the stack and isn't cast; CR
  707.10c: its controller may choose new targets. "Those spells" are the
  original and its copy; "If you do" gates the keyword grant on the copy
  having been made (CR 608.2c).
- **"That spell gains `<keywords>`."** - Judith, Carnage Connoisseur's first
  mode ("That spell gains deathtouch and lifelink."). CR 113.10: an effect
  can grant an ability to an object; a keyword a spell gains is carried on
  its `CardState.granted_ability_texts`, which `machines/combat.has_keyword`
  reads for an object on the stack - so a spell with wither deals damage to
  a creature as -1/-1 counters (CR 702.80a), one with deathtouch destroys
  what it damaged (CR 702.2b) and one with lifelink gains its controller that
  much life (CR 702.15b).
"""

import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from .decisions import source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

#: A keyword list a spell can gain - bare keywords the damage machinery
#: reads off a source (`machines/combat.Keyword`).
_SPELL_GAINABLE_KEYWORDS = frozenset(
    {"wither", "deathtouch", "lifelink", "infect", "trample", "first strike", "double strike"}
)

_COPY_IT_RE = re.compile(
    r"^(?P<may>you may )?copy (?:it|that spell)\."
    r"(?:\s*if you do, those spells gain (?P<keywords>[a-z ,]+?)\.)?"
    r"(?P<new_targets>\s*you may choose new targets for the copy\.?)?$",
    re.IGNORECASE,
)
_THAT_SPELL_GAINS_RE = re.compile(r"^that spell gains (?P<keywords>[a-z ,]+?)\.?$", re.IGNORECASE)


def _keywords(phrase: str) -> tuple[str, ...] | None:
    """ "wither" / "deathtouch and lifelink" as capitalised keyword lines, or
    None when any item is not a keyword a spell source is read for."""
    items = [item.strip().lower() for item in re.split(r",\s*(?:and\s+)?|\s+and\s+", phrase)]
    if not items or any(item not in _SPELL_GAINABLE_KEYWORDS for item in items):
        return None
    return tuple(item.capitalize() for item in items)


def grant_spell_keywords(spell: CardState | None, keywords: tuple[str, ...]) -> None:
    """Give a spell on the stack keyword lines (CR 113.10); a spell that has
    left the stack gains nothing."""
    if spell is None or spell.zone is not Zone.STACK:
        return
    for keyword in keywords:
        if keyword not in spell.granted_ability_texts:
            spell.granted_ability_texts = (*spell.granted_ability_texts, keyword)


def _event_spell(game: "Game", ability: Any) -> CardState | None:
    event = getattr(ability, "event", None)
    if event is None or event.subject_id is None:
        return None
    spell = game.find_by_id(event.subject_id)
    return spell if isinstance(spell, CardState) else None


def parse_copy_it_those_spells_gain_clause(text: str) -> Any:
    """`_COPY_IT_RE`'s shape, when it carries the "those spells gain" rider
    or a leading "you may" - the bare "copy that spell" is
    `machines/effects._COPY_THAT_SPELL_RE`'s."""
    match = _COPY_IT_RE.fullmatch(" ".join(text.split()))
    if match is None or (match.group("keywords") is None and match.group("may") is None):
        return None
    keywords: tuple[str, ...] = ()
    if match.group("keywords") is not None:
        read = _keywords(match.group("keywords"))
        if read is None:
            return None
        keywords = read
    optional = match.group("may") is not None
    offer_new_targets = match.group("new_targets") is not None

    def effect(game: "Game", ability: Any) -> None:
        spell = _event_spell(game, ability)
        if spell is None:
            return
        source_id = source_id_of(ability)
        if optional and not game.may(
            ability.controller,
            f"copy {spell.name}?",
            source=ability.source_name,
            source_id=source_id,
        ):
            return
        copy = game.copy_spell_as_last_known(spell, controller=ability.controller)
        if copy is None:
            return
        grant_spell_keywords(spell, keywords)
        grant_spell_keywords(copy, keywords)
        if offer_new_targets:
            game.offer_new_targets_for_copy(
                copy, ability.controller, source_name=ability.source_name, source_id=source_id
            )

    return effect


def parse_that_spell_gains_clause(text: str) -> Any:
    """`_THAT_SPELL_GAINS_RE`'s shape."""
    match = _THAT_SPELL_GAINS_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    keywords = _keywords(match.group("keywords"))
    if keywords is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        grant_spell_keywords(_event_spell(game, ability), keywords)

    return effect


#: "Copy it if you control a[n] `<qualityA>`, then copy it if you control a[n]
#: `<qualityB>`. You may choose new targets for the copies." - Banish into
#: Fable's own cast trigger: two *independent* conditional copies, each
#: checked against the board as the trigger resolves (CR 611.2c's "now",
#: read through the same `game.permanents_controlled_by`/`machines.
#: targeting.permanent_description` pairing `machines/effects.py`'s own
#: mass-control-change readers already use for "all `<description>` target
#: player controls") rather than one shared condition repeated twice. Either,
#: both, or neither copy may be made; CR 707.10's copy is put on the stack
#: for each condition that held, and CR 707.10c's new-targets offer covers
#: every copy actually made, not one apiece.
_COPY_IT_IF_CONTROL_TWICE_RE = re.compile(
    r"^copy it if you control an? (?P<qualityA>[a-z]+), "
    r"then copy it if you control an? (?P<qualityB>[a-z]+)\.\s*"
    r"you may choose new targets for the cop(?:y|ies)\.?$",
    re.IGNORECASE,
)


def parse_copy_it_if_control_twice_clause(text: str) -> Any:
    """`_COPY_IT_IF_CONTROL_TWICE_RE`'s shape - see the banner above."""
    from .targeting import permanent_description

    match = _COPY_IT_IF_CONTROL_TWICE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    requirement_a = permanent_description(match.group("qualityA"))
    if requirement_a is None:
        return None
    requirement_b = permanent_description(match.group("qualityB"))
    if requirement_b is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        spell = _event_spell(game, ability)
        if spell is None:
            return
        controller = ability.controller
        source_id = source_id_of(ability)
        for requirement in (requirement_a, requirement_b):
            controls_one = any(
                requirement.rejects(permanent, controller, game) is None
                for permanent in game.permanents_controlled_by(controller)
            )
            if not controls_one:
                continue
            copy = game.copy_spell_as_last_known(spell, controller=controller)
            if copy is None:
                continue
            game.offer_new_targets_for_copy(
                copy, controller, source_name=ability.source_name, source_id=source_id
            )

    return effect


def cast_copy_ability_effect(effect_text: str) -> Any:
    """This module's ability readers, or None."""
    for reader in (
        parse_copy_it_those_spells_gain_clause,
        parse_that_spell_gains_clause,
        parse_copy_it_if_control_twice_clause,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None
