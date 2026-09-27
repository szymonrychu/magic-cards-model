"""New combat restrictions and requirements this task closes (round 271-tmt,
T5): CR 508.1c/509.1b's self power-threshold restriction, CR 509.1c's "must
be blocked if able" requirement, and CR 509.1b's "can't be blocked by more
than one creature" stated about a *group* rather than about the source itself.

A separate module rather than more of `machines/combat.py` because the plan
for this round names it as a new subsystem; every function here is called
from `combat.py`'s own `attack_refusal`/`block_refusal`/`declaration_
refusal`/`declare_blockers`/`required_block_declaration` through a lazy
import (this module imports *from* `combat.py` at module scope - `Attack`,
`CardState` self-reference helpers, `Keyword` - so the reverse import has to
be deferred to call time, the same convention `combat.py` already uses for
`machines/effects.py`).

Every CR number here was looked up with `mise run rules:find <n>` in this
session:

- **CR 508.1c** / **CR 509.1b**: "The active/defending player checks each
  creature they control to see whether it's affected by any restrictions
  (effects that say a creature can't attack/block, or that it can't
  attack/block unless some condition is met)."
- **CR 509.1c**: "The defending player checks each creature they control to
  see whether it's affected by any requirements (effects that say a creature
  must block, or that it must block if some condition is met). If the number
  of requirements that are being obeyed is fewer than the maximum possible
  number ... the declaration of blockers is illegal." "Must be blocked if
  able" (Raphael, Ninja Destroyer; Gaea's Protector) is the mirror-image
  wording of this same rule: Gaea's Protector's own Wizards ruling ("Only one
  creature is required to block Gaea's Protector ... If there's a cost
  associated with blocking Gaea's Protector, the defending player isn't
  forced to pay that cost, so it doesn't have to be blocked in that case
  either") is exactly CR 509.1c's own requirement-maximisation and unpaid-cost
  exemption, read from the attacker's side instead of a blocker's.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from ..models.card import Type
from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game
    from .combat import Attack


# -- CR 508.1c / 509.1b: a self power-threshold restriction ------------------

#: Technodrome: "This creature can't attack or block unless its power is 6 or
#: greater." `card_search` (Scryfall) found no second Modern/Pioneer/
#: Standard-legal printing of this exact self power-threshold shape as of
#: this session (see `MEMORY.md`), so both directions ("or less" as well as
#: "or greater") and every action ("attack", "block", or "attack or block")
#: are read generally rather than pinned to Technodrome's own "or greater"/
#: "attack or block" combination - the same generality every other reader in
#: this pool is held to even where only one printing proves it.
_SELF_CANT_UNLESS_OWN_POWER_RE = re.compile(
    r"^(?:(?P<subject>.+?) )?can't (?P<what>attack or block|attack|block) unless "
    r"(?:its|his|her|their) power is (?P<power>\d+) or (?P<direction>less|greater)\.?$",
    re.IGNORECASE,
)


def _own_power_threshold_match(line: str, name: str) -> "re.Match[str] | None":
    match = _SELF_CANT_UNLESS_OWN_POWER_RE.fullmatch(line.strip())
    if match is None:
        return None
    from .combat import _self_reference_names

    subject = (match.group("subject") or "").strip().lower()
    accepted = {"", "this creature", "this permanent"}
    accepted.update(candidate.lower() for candidate in _self_reference_names(name))
    return match if subject in accepted else None


def is_power_threshold_restriction_line(line: str, name: str) -> bool:
    """Whether a static line is `_SELF_CANT_UNLESS_OWN_POWER_RE`'s shape,
    self-referential to a creature named `name` - what `support.py` counts
    handled."""
    return _own_power_threshold_match(line, name) is not None


def power_threshold_restriction_refusal(
    game: "Game", creature: CardState, action: str
) -> str | None:
    """Why this creature's own "can't `action` unless its power is N or
    (greater|less)" stops it now, or None (CR 508.1c for "attack", CR 509.1b
    for "block"). Read off its computed abilities (CR 613.5) and the computed
    power (CR 613.5, CR 613.4c) at the moment asked, the same way `combat.
    self_card_count_restriction_refusal` reads its own "unless there are N or
    more cards" sibling."""
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for line in game.characteristics_of(creature).abilities:
        match = _own_power_threshold_match(line, creature.name)
        if match is None:
            continue
        if action not in match["what"].lower().split(" or "):
            continue
        threshold = int(match["power"])
        power = game.power_of(creature)
        if power is None:
            continue
        greater = match["direction"].lower() == "greater"
        obeyed = power >= threshold if greater else power <= threshold
        if not obeyed:
            return (
                f'{creature.name} can\'t {action}: "{line.strip()}" - its power is {power} ({rule})'
            )
    return None


# -- CR 509.1c: "must be blocked if able" ------------------------------------

#: Raphael, Ninja Destroyer: "Raphael must be blocked if able." Gaea's
#: Protector: "This creature must be blocked if able." - the attacker's own
#: requirement (CR 509.1c), the mirror wording of `combat._BLOCKS_NAMED_EACH_
#: COMBAT_RE`'s "This creature blocks `<attacker>` each combat if able." -
#: that reader states a *blocker's* requirement to block one named attacker;
#: this one states that *some* blocker (any one is enough - Gaea's Protector's
#: own ruling) must block this attacker.
_MUST_BE_BLOCKED_RE = re.compile(
    r"^(?:(?P<subject>.+?) )?must be blocked if able\.?$", re.IGNORECASE
)


def _must_be_blocked_match(line: str, name: str) -> "re.Match[str] | None":
    match = _MUST_BE_BLOCKED_RE.fullmatch(line.strip())
    if match is None:
        return None
    from .combat import _self_reference_names

    subject = (match.group("subject") or "").strip().lower()
    accepted = {"", "this creature", "this permanent"}
    accepted.update(candidate.lower() for candidate in _self_reference_names(name))
    return match if subject in accepted else None


def is_must_be_blocked_line(line: str, name: str) -> bool:
    """Whether a static line is `_MUST_BE_BLOCKED_RE`'s shape, self-referential
    to a creature named `name` - what `support.py` counts handled."""
    return _must_be_blocked_match(line, name) is not None


def _must_be_blocked_attackers(game: "Game") -> list["Attack"]:
    """Every attack this combat whose attacker carries "must be blocked if
    able" on the computed board right now (CR 613.5)."""
    board = game.computed_board()
    found: list[Attack] = []
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if not isinstance(attacker, CardState):
            continue
        chars = board.of(attacker)
        if any(_must_be_blocked_match(line, attacker.name) for line in chars.abilities):
            found.append(attack)
    return found


def unobeyed_must_be_blocked_requirement(
    game: "Game", declared: "dict[UUID, list[CardState]]"
) -> str | None:
    """Why the block declaration `declared` (attacker id to its blockers)
    leaves a "must be blocked if able" attacker unblocked when some legal
    blocker could have blocked it, or None (CR 509.1c).

    CR 509.1c's own unpaid-cost exemption ("If a creature can't block unless
    a player pays a cost, that player is not required to pay that cost") has
    no cost-to-block reader in this pool to exempt (`combat.declaration_
    refusal`'s own docstring notes the identical gap for `unobeyed_block_
    requirement`), so every legal blocker counts. Any single legal blocker is
    enough - Gaea's Protector's own ruling: "Only one creature is required to
    block ... Other creatures may also block it ... or not block at all."
    """
    from .combat import block_refusal, declaration_refusal

    for attack in _must_be_blocked_attackers(game):
        if declared.get(attack.attacker_id):
            continue  # already has at least one blocker - the requirement is met
        attacker = game.find_by_id(attack.attacker_id)
        if not isinstance(attacker, CardState):
            continue
        defender_username = _defending_username(game, attack)
        if defender_username is None:
            continue
        for candidate in game.permanents_controlled_by(defender_username):
            if block_refusal(game, candidate, attack) is not None:
                continue
            trial = {attacker_id: list(blockers) for attacker_id, blockers in declared.items()}
            trial.setdefault(attack.attacker_id, []).append(candidate)
            if declaration_refusal(game, trial) is not None:
                continue
            return (
                f"{attacker.name} must be blocked if able, and {candidate.name} "
                f"could legally block it (CR 509.1c)"
            )
    return None


def _defending_username(game: "Game", attack: "Attack") -> str | None:
    from .combat import defending_player

    return defending_player(game, attack.defender)


def required_must_be_blocked_declaration(
    game: "Game", username: str, declared: "dict[UUID, list[CardState]]"
) -> list[tuple[UUID, UUID]]:
    """What `username`'s own creatures add to satisfy every "must be blocked
    if able" attacker they can (CR 509.1c), as `(blocker_id, attacker_id)`
    pairs - `combat.required_block_declaration`'s own default-answer helper,
    extended to this requirement the same way that function already handles
    a *blocker's* own "blocks `<attacker>` each combat if able.\""""
    from .combat import block_refusal, declaration_refusal

    pairs: list[tuple[UUID, UUID]] = []
    for attack in _must_be_blocked_attackers(game):
        if declared.get(attack.attacker_id):
            continue
        if _defending_username(game, attack) != username:
            continue
        for candidate in game.permanents_controlled_by(username):
            if any(candidate.id == blocker_id for blocker_id, _ in pairs):
                continue
            if block_refusal(game, candidate, attack) is not None:
                continue
            trial = {attacker_id: list(blockers) for attacker_id, blockers in declared.items()}
            for _blocker_id, attacker_id in pairs:
                trial.setdefault(attacker_id, [])
            trial.setdefault(attack.attacker_id, []).append(candidate)
            if declaration_refusal(game, trial) is None:
                declared.setdefault(attack.attacker_id, []).append(candidate)
                pairs.append((candidate.id, attack.attacker_id))
                break
    return pairs


# -- CR 509.1b: "can't be blocked by more than one creature", stated about a
#    group rather than about the source itself --------------------------------

#: Rocksteady, Crash Courser: "Boars you control can't be blocked by more
#: than one creature." - a type/subtype-list group, the same "`<Type(s)>` you
#: control" subject `combat._control_quality` already reads for CR 508.1c's
#: "can't attack unless you control `<quality>`".
_TYPE_GROUP_BLOCKED_BY_AT_MOST_ONE_RE = re.compile(
    r"^(?P<quality>[A-Za-z][A-Za-z' -]*?) you control can't be blocked by more than "
    r"one creature\.?$",
    re.IGNORECASE,
)

#: Michelangelo, Mutant BFF: "Each creature you control with a counter on it
#: can't be blocked by more than one creature." Proved general on Flopsie,
#: Bumi's Buddy's differently-worded "Each creature you control with power 4
#: or greater can't be blocked by more than one creature." (Modern/Pioneer/
#: Standard legal, not a listed card, not in any deck list) - the same
#: "with `<description>`" clause `combat._parse_creature_description` already
#: reads for a power comparison, widened here to also accept "a counter on
#: it" (CR 122.1), the identical "any counter, any kind" test
#: `layers.PermanentsControlledByWithCounters` already applies with no
#: `counter_kind` of its own.
_EACH_CREATURE_BLOCKED_BY_AT_MOST_ONE_RE = re.compile(
    r"^each creature you control(?: with (?P<description>.+?))? can't be blocked by "
    r"more than one creature\.?$",
    re.IGNORECASE,
)

_HAS_A_COUNTER_ON_IT_RE = re.compile(r"^an? counters? on (?:it|them)$", re.IGNORECASE)


@dataclass(frozen=True)
class _GroupBlockedByAtMostOne:
    """One parsed group "can't be blocked by more than one creature" grant
    (CR 509.1b), ready to judge one candidate attacker against it."""

    sentence: str
    #: A disjunction of (card type, subtype) alternatives - `None`/`None`
    #: means "no filter at all" (the bare "each creature you control" shape).
    quality: "list[tuple[Type | None, str | None]] | None" = None
    has_counter: bool = False
    power_operator: str | None = None
    power_bound: int | None = None

    def matches(self, game: "Game", candidate: CardState) -> bool:
        characteristics = game.characteristics_of(candidate)
        if self.has_counter and not any(count > 0 for count in characteristics.counters.values()):
            return False
        if self.power_operator is not None:
            power = game.power_of(candidate)
            if power is None:
                return False
            bound = self.power_bound or 0
            if self.power_operator == "greater_or_equal" and power < bound:
                return False
            if self.power_operator == "less_or_equal" and power > bound:
                return False
        if self.quality is None:
            return True
        subtypes_lower = {subtype.lower() for subtype in characteristics.subtypes}
        return any(
            (card_type is None or card_type in characteristics.types)
            and (subtype is None or subtype in subtypes_lower)
            for card_type, subtype in self.quality
        )


def _parse_each_creature_description(description: str) -> "_GroupBlockedByAtMostOne | None":
    text = description.strip()
    if _HAS_A_COUNTER_ON_IT_RE.fullmatch(text):
        return _GroupBlockedByAtMostOne(sentence=text, has_counter=True)
    power = re.fullmatch(
        r"power (?P<number>\d+) or (?P<direction>less|greater)", text, re.IGNORECASE
    )
    if power is not None:
        greater = power.group("direction").lower() == "greater"
        operator = "greater_or_equal" if greater else "less_or_equal"
        return _GroupBlockedByAtMostOne(
            sentence=text, power_operator=operator, power_bound=int(power.group("number"))
        )
    return None


def _parse_group_blocked_by_at_most_one(sentence: str) -> "_GroupBlockedByAtMostOne | None":
    text = sentence.strip()
    if match := _TYPE_GROUP_BLOCKED_BY_AT_MOST_ONE_RE.fullmatch(text):
        from .combat import _control_quality

        quality = _control_quality(match.group("quality"))
        if quality is None:
            return None
        return _GroupBlockedByAtMostOne(sentence=text, quality=quality)
    if match := _EACH_CREATURE_BLOCKED_BY_AT_MOST_ONE_RE.fullmatch(text):
        description = match.group("description")
        if description is None:
            return _GroupBlockedByAtMostOne(sentence=text)
        return _parse_each_creature_description(description)
    return None


def is_group_blocked_by_at_most_one_line(line: str) -> bool:
    """Whether a static line is a *group* "can't be blocked by more than one
    creature" grant (CR 509.1b) that `group_blocked_by_at_most_one_refusal`
    reads - what `support.py` counts handled. The self-referential singular
    shape ("This creature can't be blocked by more than one creature.") is
    `combat.is_blocked_by_at_most_one_line`'s own, not this one - the two are
    disjoint: this only ever matches a subject naming a group ("`<Type>`s you
    control", "Each creature you control")."""
    return _parse_group_blocked_by_at_most_one(line) is not None


def group_blocked_by_at_most_one_refusal(
    game: "Game", attacker: CardState, blocker_count: int
) -> str | None:
    """Why a battlefield permanent's *group* "can't be blocked by more than
    one creature" restriction stops this many blockers on `attacker`, or None
    (CR 509.1b) - `combat.blocked_by_at_most_one_refusal`'s own group-subject
    sibling, read off every battlefield permanent's computed static lines the
    same way `combat.group_attack_restriction_refusal` reads a source that
    restricts creatures other than itself."""
    if blocker_count < 2:
        return None
    board = game.computed_board()
    for source in game.battlefield:
        source_characteristics = board.of(source)
        controller = source_characteristics.controller
        if controller != game.controller_of(attacker).username:
            continue
        for ability in source_characteristics.abilities:
            if "can't be blocked by more than one creature" not in ability.lower():
                continue
            restriction = _parse_group_blocked_by_at_most_one(ability)
            if restriction is None or not restriction.matches(game, attacker):
                continue
            return (
                f"{attacker.name} can't be blocked by more than one creature: "
                f'{source.name} says "{restriction.sentence}" (CR 509.1b)'
            )
    return None
