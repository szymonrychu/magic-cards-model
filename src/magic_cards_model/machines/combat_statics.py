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
from collections.abc import Callable  # noqa: F401
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
    from .block_statics import ring_bearer_must_be_blocked

    board = game.computed_board()
    found: list[Attack] = []
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if not isinstance(attacker, CardState):
            continue
        chars = board.of(attacker)
        if any(
            _must_be_blocked_match(line, attacker.name)
            or ring_bearer_must_be_blocked(game, attacker, line)
            for line in chars.abilities
        ):
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

_HAS_A_COUNTER_ON_IT_RE = re.compile(
    r"^an? (?P<kind>[+\-\d/]+ )?counters? on (?:it|them)$", re.IGNORECASE
)


@dataclass(frozen=True)
class _GroupBlockedByAtMostOne:
    """One parsed group "can't be blocked by more than one creature" grant
    (CR 509.1b), ready to judge one candidate attacker against it."""

    sentence: str
    #: A disjunction of (card type, subtype) alternatives - `None`/`None`
    #: means "no filter at all" (the bare "each creature you control" shape).
    quality: "list[tuple[Type | None, str | None]] | None" = None
    has_counter: bool = False
    #: The counter's kind ("+1/+1"), or None for "a counter" of any kind.
    counter_kind: str | None = None
    power_operator: str | None = None
    power_bound: int | None = None

    def matches(self, game: "Game", candidate: CardState) -> bool:
        characteristics = game.characteristics_of(candidate)
        if self.has_counter and not any(
            count > 0 and (self.counter_kind is None or str(kind) == self.counter_kind)
            for kind, count in characteristics.counters.items()
        ):
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
    if counter := _HAS_A_COUNTER_ON_IT_RE.fullmatch(text):
        return _GroupBlockedByAtMostOne(
            sentence=text, has_counter=True, counter_kind=(counter["kind"] or "").strip() or None
        )
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


# -- EP-01 R1 T4: dispatchers combat.py calls (additive hooks) ---------------


# -- "can't be blocked except by ...", "can't be blocked by ...", "can't block"
#    stated by the attacker, an attachment or a group (CR 509.1b) ------------

#: A predicate over (game, candidate creature).
_Matcher = "Callable[[Game, CardState], bool]"

_SENTENCE_SPLIT_RE = re.compile(r",?\s+and/or\s+|,\s*(?:or\s+|and\s+)?|\s+or\s+", re.IGNORECASE)
_EXCEPT_BY_RE = re.compile(
    r"^(?P<subject>.+?) can't be blocked except by (?P<desc>.+?)\.?$", re.IGNORECASE
)
_BLOCKED_BY_RE = re.compile(
    r"^(?P<subject>.+?) can't be blocked by (?P<desc>.+?)\.?$", re.IGNORECASE
)
_POWER_LESS_CANT_BLOCK_RE = re.compile(
    r"^creatures with power (?P<cmp>less|greater) than (?P<bound>.+?) can't block "
    r"(?P<object>it|this creature|creatures you control)\.?$",
    re.IGNORECASE,
)
_GROUP_CANT_BLOCK_RE = re.compile(r"^(?P<group>.+?) can't block\.?$", re.IGNORECASE)
#: "Creatures with flying can't block creatures you control." (Bower Passage),
#: "Cowards can't block Warriors." (Kargan Intimidator): a blocker group and an
#: attacker group (CR 509.1b).
_GROUP_CANT_BLOCK_OBJECT_RE = re.compile(
    r"^(?P<group>.+?) can't block (?P<object>(?!it\b|this creature\b).+?)\.?$", re.IGNORECASE
)
#: "Creatures you control with +1/+1 counters on them can't be blocked."
#: (Herald of Secret Streams): an unconditional evasion grant to a group.
_PLAIN_CANT_BE_BLOCKED_RE = re.compile(r"^(?P<subject>.+?) can't be blocked\.?$", re.IGNORECASE)
#: "~ can't be blocked unless all creatures defending player controls block
#: it." (Tromokratis): a fact about the whole declaration.
_UNLESS_ALL_BLOCK_RE = re.compile(
    r"^(?P<subject>.+?) can't be blocked unless all creatures defending player controls "
    r"block (?:it|this creature)\.?$",
    re.IGNORECASE,
)
#: "Your opponents can't block with creatures with even mana values." (Void
#: Winnower): a block ban on the blockers' controller's side.
_OPPONENTS_CANT_BLOCK_WITH_RE = re.compile(
    r"^your opponents can't block with (?P<desc>.+?)\.?$", re.IGNORECASE
)
_THREE_OR_MORE_RE = re.compile(r"^(?P<count>\w+) or more creatures$", re.IGNORECASE)


def _is_aura_attached(game: "Game", creature: CardState) -> bool:
    """Whether `creature` is enchanted (an Aura is attached to it)."""
    board = game.computed_board()
    return any(
        permanent.attached_to == creature.id and "Aura" in board.of(permanent).subtypes
        for permanent in game.battlefield
    )


def _single_description(text: str):
    """One creature description beyond `combat._parse_creature_description`'s
    closed grammar, as a predicate, or None."""
    from .combat import _parse_creature_description, canonical_subtype, is_token

    word = text.strip().lower()
    if word in {"creature tokens", "tokens"}:
        return lambda game, candidate: is_token(candidate)
    if word == "creatures that don't have a name":
        return lambda game, candidate: not game.characteristics_of(candidate).name.strip()
    if word in {"legendary creatures", "legendary creature"}:
        return lambda game, candidate: any(
            str(value).lower() == "legendary"
            for value in game.characteristics_of(candidate).supertypes
        )
    if word in {"creatures with even mana values", "creatures with odd mana values"}:
        parity = 0 if " even " in f" {word} " else 1
        return lambda game, candidate: int(candidate.mana_value) % 2 == parity
    if word == "enchanted creatures":
        return lambda game, candidate: _is_aura_attached(game, candidate)
    if word == "enchantment creatures":
        return lambda game, candidate: Type.ENCHANTMENT in game.characteristics_of(candidate).types
    parsed = _parse_creature_description(text)
    if parsed is not None:
        return parsed.matches
    singular = re.sub(r"(es|s)$", "", word) if word.endswith("ses") else word.rstrip("s")
    for candidate_name in (word, word[:-1], singular):
        if canonical_subtype(candidate_name) is not None and " " not in word.strip():
            subtype = canonical_subtype(candidate_name).lower()
            return lambda game, candidate, subtype=subtype: (
                subtype in {value.lower() for value in game.characteristics_of(candidate).subtypes}
            )
    parts = word.removesuffix("s").split()
    if len(parts) > 1 and all(
        canonical_subtype(part) is not None or part == "scion" for part in parts
    ):
        return lambda game, candidate: (
            set(parts) <= {value.lower() for value in game.characteristics_of(candidate).subtypes}
        )
    return None


def parse_blocker_description(description: str):
    """A creature description as a predicate: a disjunction of the
    descriptions joined by "or"/"and/or"/commas, "creatures with flying or
    reach" sharing its "creatures with" lead, or None when any side is not
    read."""
    text = description.strip().rstrip(".")
    whole = _single_description(text)
    if whole is not None:
        return whole
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if len(parts) < 2:
        return None
    lead = ""
    matchers = []
    for part in parts:
        candidate = part
        if lead and "creature" not in part.lower() and not part.lower().startswith("power"):
            candidate = lead + part
        matcher = _single_description(candidate)
        if matcher is None:
            return None
        if part.lower().startswith("creatures with "):
            lead = "creatures with "
        matchers.append(matcher)
    return lambda game, candidate: any(matcher(game, candidate) for matcher in matchers)


def _attacker_subject(subject: str, source: CardState):
    """A predicate over attackers for a block-restriction sentence's subject
    (the source itself, what it enchants/equips, or a group its controller
    controls), or None."""
    from .combat import _parse_creature_description, _self_reference_alternatives

    text = subject.strip().lower()
    if text in {name.lower() for name in _self_reference_alternatives(source)} | _OBJECT_NOUNS:
        return lambda game, attacker: attacker.id == source.id
    if text in {"enchanted creature", "equipped creature"}:
        return lambda game, attacker: source.attached_to == attacker.id
    group = re.fullmatch(
        r"(?:each )?(?P<what>.+?) you control(?: with (?P<q>.+))?", subject.strip(), re.IGNORECASE
    )
    if group is None:
        return None
    what = group["what"].strip().lower()
    qualifier = group["q"]
    kind = None
    if what not in {"creature", "creatures"}:
        kind = parse_blocker_description(group["what"])
        if kind is None:
            return None
    extra = None
    if qualifier is not None:
        counter = _HAS_COUNTER_RE.fullmatch(qualifier.strip())
        if counter is not None:
            counter_name = (counter["kind"] or "").strip().lower()

            def extra(game, attacker, counter_name=counter_name):
                counters = game.characteristics_of(attacker).counters
                if counter_name:
                    return any(
                        count > 0 and str(key).lower() == counter_name
                        for key, count in counters.items()
                    )
                return any(count > 0 for count in counters.values())

        else:
            parsed = _parse_creature_description("creatures with " + qualifier.strip())
            if parsed is None:
                return None
            extra = parsed.matches

    def predicate(game, attacker):
        if game.controller_of(attacker).username != game.controller_of(source).username:
            return False
        if kind is not None and not kind(game, attacker):
            return False
        return extra is None or extra(game, attacker)

    return predicate


#: "This Vehicle can't be blocked by ..." - the permanent naming itself by type.
_OBJECT_NOUNS = frozenset(
    {"this vehicle", "this permanent", "this artifact", "this creature", "this land"}
)

_HAS_COUNTER_RE = re.compile(
    r"^(?:an? )?(?P<kind>[+\-\d/]+ )?counters? on (?:it|them)$", re.IGNORECASE
)


def _block_sentences(game: "Game"):
    """(source, sentence) for every static sentence on the computed board."""
    from .layers import layer_readable_sentences

    board = game.computed_board()
    for source in game.battlefield:
        for ability in board.of(source).abilities:
            lowered = ability.lower()
            if "can't be blocked" not in lowered and "can't block" not in lowered:
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                yield source, sentence.strip()


def block_evasion_refusal(game: "Game", blocker: CardState, attacker: CardState) -> str | None:
    """Why a "can't be blocked except by/by ..." or "can't block" static
    (printed, attached or group, CR 509.1b) refuses this blocker, or None."""
    for source, sentence in _block_sentences(game):
        if match := _EXCEPT_BY_RE.fullmatch(sentence):
            if _THREE_OR_MORE_RE.fullmatch(match["desc"].strip()):
                continue
            applies = _attacker_subject(match["subject"], source)
            matcher = parse_blocker_description(match["desc"])
            if applies is None or matcher is None or not applies(game, attacker):
                continue
            if not matcher(game, blocker):
                return (
                    f"{attacker.name} can't be blocked except by {match['desc'].strip()}, "
                    f'and {blocker.name} is not one: {source.name} says "{sentence}" (CR 509.1b)'
                )
        elif match := _BLOCKED_BY_RE.fullmatch(sentence):
            applies = _attacker_subject(match["subject"], source)
            matcher = parse_blocker_description(match["desc"])
            if applies is None or matcher is None or not applies(game, attacker):
                continue
            if matcher(game, blocker):
                return (
                    f"{attacker.name} can't be blocked by {match['desc'].strip()}, and "
                    f'{blocker.name} is one: {source.name} says "{sentence}" (CR 509.1b)'
                )
        elif match := _POWER_LESS_CANT_BLOCK_RE.fullmatch(sentence):
            refusal = _power_less_cant_block(game, source, blocker, attacker, match, sentence)
            if refusal is not None:
                return refusal
        elif match := _GROUP_CANT_BLOCK_RE.fullmatch(sentence):
            refusal = _group_cant_block(game, source, blocker, match, sentence)
            if refusal is not None:
                return refusal
        elif match := _OPPONENTS_CANT_BLOCK_WITH_RE.fullmatch(sentence):
            matcher = parse_blocker_description(match["desc"])
            if (
                matcher is not None
                and game.controller_of(blocker).username != game.controller_of(source).username
                and matcher(game, blocker)
            ):
                return f'{blocker.name} can\'t block: {source.name} says "{sentence}" (CR 509.1b)'
        elif (match := _GROUP_CANT_BLOCK_OBJECT_RE.fullmatch(sentence)) and (
            refusal := _group_cant_block_object(game, source, blocker, attacker, match, sentence)
        ):
            return refusal
        elif match := _PLAIN_CANT_BE_BLOCKED_RE.fullmatch(sentence):
            applies = _attacker_subject(match["subject"], source)
            if applies is not None and applies(game, attacker):
                return (
                    f"{attacker.name} can't be blocked: {source.name} says "
                    f'"{sentence}" (CR 509.1b)'
                )
    return None


def _attacker_object(phrase: str, source: CardState):
    """An attacker predicate for "creatures you control" and friends, or a bare
    creature description of any controller ("Warriors")."""
    applies = _attacker_subject(phrase, source)
    if applies is not None:
        return applies
    matcher = parse_blocker_description(phrase)
    return None if matcher is None else (lambda game, attacker: matcher(game, attacker))


def _group_cant_block_object(game, source, blocker, attacker, match, sentence) -> str | None:
    group = match["group"].strip()
    if (
        group.lower().startswith(("this ", "enchanted ", "equipped "))
        or group.lower() == "creatures"
    ):
        return None
    blockers = parse_blocker_description(group)
    attackers = _attacker_object(match["object"].strip(), source)
    if blockers is None or attackers is None or not blockers(game, blocker):
        return None
    if not attackers(game, attacker):
        return None
    return (
        f'{blocker.name} can\'t block {attacker.name}: {source.name} says "{sentence}" (CR 509.1b)'
    )


def _power_less_cant_block(game, source, blocker, attacker, match, sentence) -> str | None:
    from .effects import count_expression

    if match["object"].lower() == "creatures you control":
        if game.controller_of(attacker).username != game.controller_of(source).username:
            return None
    elif attacker.id != source.id:
        return None
    bound_text = match["bound"].strip()
    own = re.fullmatch(
        r"(?:this creature|it)'?s power|this creature's power|.+'s power", bound_text
    )
    if own is not None:
        bound = game.power_of(source)
    else:
        reader = count_expression(bound_text)
        if reader is None:
            return None
        bound = reader(game, game.controller_of(source).username or "")
    power = game.power_of(blocker)
    if bound is None or power is None:
        return None
    greater = match["cmp"].lower() == "greater"
    if (power <= bound) if greater else (power >= bound):
        return None
    return (
        f"{blocker.name} can't block {attacker.name}: its power {power} is "
        f'{"greater" if greater else "less"} than {bound} - {source.name} says "{sentence}" '
        "(CR 509.1b)"
    )


def _group_cant_block(game, source, blocker, match, sentence) -> str | None:
    group = match["group"].strip()
    if group.lower().startswith(("this ", "enchanted ", "equipped ")):
        return None
    if group.lower() == "creatures":
        return None
    matcher = parse_blocker_description(group)
    if matcher is None:
        return None
    if not matcher(game, blocker):
        return None
    return f'{blocker.name} can\'t block: {source.name} says "{sentence}" (CR 509.1b)'


def _all_must_block_refusal(game, source, attacker, blockers, match, sentence) -> str | None:
    from .combat import defending_player

    applies = _attacker_subject(match["subject"], source)
    attack = game.combat.attack_by(attacker.id)
    if applies is None or attack is None or not applies(game, attacker):
        return None
    defender = defending_player(game, attack.defender)
    board = game.computed_board()
    blocking = {blocker.id for blocker in blockers}
    missing = [
        creature
        for creature in game.permanents_controlled_by(defender or "")
        if board.of(creature).is_creature and creature.id not in blocking
    ]
    if not missing:
        return None
    return (
        f"{attacker.name} can't be blocked unless all creatures {defender} controls block it, "
        f'and {missing[0].name} does not: {source.name} says "{sentence}" (CR 509.1b)'
    )


def block_evasion_declaration_refusal(game: "Game", declared) -> str | None:
    """ "can't be blocked except by three or more creatures" judged on the
    whole declaration (CR 509.1b, like menace in CR 702.111b)."""
    for attacker_id, blockers in declared.items():
        if not blockers:
            continue
        attacker = game.find_by_id(attacker_id)
        if attacker is None:
            continue
        for source, sentence in _block_sentences(game):
            if (every := _UNLESS_ALL_BLOCK_RE.fullmatch(sentence)) is not None:
                refusal = _all_must_block_refusal(game, source, attacker, blockers, every, sentence)
                if refusal is not None:
                    return refusal
                continue
            match = _EXCEPT_BY_RE.fullmatch(sentence)
            if match is None:
                continue
            count = _THREE_OR_MORE_RE.fullmatch(match["desc"].strip())
            if count is None:
                continue
            applies = _attacker_subject(match["subject"], source)
            if applies is None or not applies(game, attacker):
                continue
            from ..numbers import parse_count

            needed = parse_count(count["count"], article=True)
            if needed is not None and len(blockers) < needed:
                return (
                    f"{attacker.name} can't be blocked except by {match['desc'].strip()}, but "
                    f'only {len(blockers)} block it: {source.name} says "{sentence}" (CR 509.1b)'
                )
    return None


def reads_block_evasion_line(printing, text: str, *, card_name: str) -> bool:
    """Whether every sentence of this static line is a block restriction the
    functions above enforce - asked of the parsers themselves."""
    from .layers import layer_readable_sentences

    lowered = text.lower()
    if "can't be blocked" not in lowered and "can't block" not in lowered:
        return False
    sentences = [s.strip() for s in layer_readable_sentences(text, static_only=True)]
    return bool(sentences) and all(
        _reads_block_sentence(sentence, card_name) for sentence in sentences
    )


def _reads_block_sentence(sentence: str, card_name: str) -> bool:
    from ..numbers import parse_count

    if match := _EXCEPT_BY_RE.fullmatch(sentence):
        desc = match["desc"].strip()
        count = _THREE_OR_MORE_RE.fullmatch(desc)
        if count is not None:
            ok = parse_count(count["count"], article=True) is not None
        else:
            ok = parse_blocker_description(desc) is not None
        return ok and _subject_readable(match["subject"], card_name)
    if match := _BLOCKED_BY_RE.fullmatch(sentence):
        return parse_blocker_description(match["desc"]) is not None and _subject_readable(
            match["subject"], card_name
        )
    if match := _POWER_LESS_CANT_BLOCK_RE.fullmatch(sentence):
        from .effects import count_expression

        bound = match["bound"].strip()
        return bound.endswith("'s power") or count_expression(bound) is not None
    if match := _GROUP_CANT_BLOCK_RE.fullmatch(sentence):
        group = match["group"].strip()
        return (
            not group.lower().startswith(("this ", "enchanted ", "equipped "))
            and group.lower() != "creatures"
            and parse_blocker_description(group) is not None
        )
    if match := _OPPONENTS_CANT_BLOCK_WITH_RE.fullmatch(sentence):
        return parse_blocker_description(match["desc"]) is not None
    if match := _GROUP_CANT_BLOCK_OBJECT_RE.fullmatch(sentence):
        group = match["group"].strip()
        probe = _SubjectProbe(card_name)
        return (
            not group.lower().startswith(("this ", "enchanted ", "equipped "))
            and group.lower() != "creatures"
            and parse_blocker_description(group) is not None
            and (
                _attacker_subject(match["object"].strip(), probe) is not None
                or parse_blocker_description(match["object"].strip()) is not None
            )
        )
    if match := _PLAIN_CANT_BE_BLOCKED_RE.fullmatch(sentence):
        return _subject_readable(match["subject"], card_name)
    if match := _UNLESS_ALL_BLOCK_RE.fullmatch(sentence):
        return _subject_readable(match["subject"], card_name)
    return False


def _subject_readable(subject: str, card_name: str) -> bool:
    from ..models.card_state import CardState as _CardState  # noqa: F401
    from .combat import _self_reference_names

    text = subject.strip().lower()
    if text in {name.lower() for name in _self_reference_names(card_name)} | _OBJECT_NOUNS:
        return True
    if text in {"enchanted creature", "equipped creature"}:
        return True
    # A group the attacker-subject parser reads: probe it against a dummy source.
    probe = _SubjectProbe(card_name)
    return _attacker_subject(subject, probe) is not None


class _SubjectProbe:
    """The minimum of a CardState `_attacker_subject` reads while parsing."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.id = None
        self.attached_to = None


def extra_attack_refusal(game: "Game", creature: CardState, defender) -> str | None:
    from . import (
        attached_restrictions,
        attack_block_costs,
        attacking_statics,
        group_attack_statics,
        opponent_attack_restrictions,
        static_cast_bans,
    )

    return (
        attached_restrictions.attached_attack_refusal(game, creature)
        or static_cast_bans.attack_ban_reason(game, creature)
        or attack_block_costs.return_cost_refusal(game, creature)
        or attacking_statics.self_attack_condition_refusal(game, creature, defender)
        or group_attack_statics.group_attack_refusal(game, creature, defender)
        or opponent_attack_restrictions.cant_attack_refusal(game, creature, defender)
    )


def extra_block_refusal(game: "Game", blocker: CardState, attacker: CardState) -> str | None:
    from . import attached_restrictions, attacking_statics, group_attack_statics

    return (
        block_evasion_refusal(game, blocker, attacker)
        or attached_restrictions.attached_block_refusal(game, blocker)
        or attacking_statics.self_block_condition_refusal(game, blocker, attacker)
        or group_attack_statics.group_block_refusal(game, blocker, attacker)
    )


def extra_declaration_refusal(game: "Game", declared) -> str | None:
    from . import attacking_statics, group_attack_statics

    return (
        block_evasion_declaration_refusal(game, declared)
        or attacking_statics.self_block_declaration_refusal(game, declared)
        or group_attack_statics.block_cap_refusal(game, declared)
    )


def extra_attack_declaration_refusal(game: "Game", attacks) -> str | None:
    from . import attack_block_costs, attacking_statics, group_attack_statics

    return (
        attacking_statics.self_attack_declaration_refusal(game, attacks)
        or group_attack_statics.attack_cap_refusal(game, attacks)
        or attack_block_costs.return_cost_declaration_refusal(game, attacks)
    )


def extra_attack_requirements(game: "Game", creature: CardState) -> list[bool]:
    from . import attached_restrictions, attacking_statics, group_attack_statics

    return [
        *attached_restrictions.attached_attack_requirements(game, creature),
        *attacking_statics.self_attack_requirements(game, creature),
        *group_attack_statics.group_attack_requirements(game, creature),
    ]


def extra_attack_costs(game: "Game", creature: CardState, defender) -> list:
    from . import attack_block_costs

    return attack_block_costs.attack_costs(game, creature, defender)


def extra_block_costs(game: "Game", blocker: CardState) -> list:
    from . import attack_block_costs

    return attack_block_costs.block_costs(game, blocker)
