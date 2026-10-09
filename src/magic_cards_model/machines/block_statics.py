"""Block-count, block-only and lure statics (EP-01 round 1, T3).

Five static shapes, each a declaration rule about *how many* and *which*
creatures block, read off every battlefield permanent's computed abilities
(CR 613.5):

- **"`<subject>` can block only `<creatures>`"** (CR 509.1b): a restriction.
  Brazen Borrower's "This creature can block only creatures with flying.",
  Stratus Walk's "Enchanted creature can block only creatures with flying.",
  Dense Canopy's "Creatures with flying can block only creatures with
  flying."
- **"`<subject>` can block an additional creature each combat"**, "an
  additional `<n>` creatures", "any number of creatures", "for each Equipment
  attached to `<it>`" (CR 509.1a): a blocker chooses one attacker to block by
  default, and each of these raises that bound. Subjects: the creature itself
  (Foriysian Interceptor), "equipped creature" (Echo Circlet), "each
  creature you control [with a +1/+1 counter on it]" (High Ground, Brave the
  Sands, Cenn's Tactician).
- **"All creatures able to block `<subject>` do so."** (CR 509.1c): a lure -
  one requirement per creature able to block the lure creature. Subjects: the
  creature itself (Breaker of Armies), "enchanted creature" (Lure),
  "equipped creature" (Nemesis Mask), or either of two (Noble Quarry).
- **"`<subject>` must be blocked by exactly `<n>` creature(s) if able"**
  (CR 509.1c): Nacatl War-Pride.
- **"As long as `<name>` is your Ring-bearer, it must be blocked if able."**
  (CR 509.1c, CR 701.54e): Frodo Baggins - `combat_statics` reads the
  unconditional "must be blocked if able"; this is its conditional twin.

Every CR number here was looked up with `mise run rules:find <n>`: 509.1a
(the defending player chooses which creatures block, and for each one
creature to block), 509.1b (restrictions), 509.1c (requirements; the maximum
number obeyed without disobeying any restriction), 510.1d (a blocker that
blocks two or more creatures divides its combat damage as its controller
chooses), 701.54e's Ring-bearer designation is `Game.ring_bearer_of`'s.

`reads_block_static_line` is the audit's way in: the line is credited
handled only when one of the parsers below - the very ones the enforcement
functions call - reads it.
"""

import functools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from ..models.card_state import CardState
from ..numbers import parse_count
from .abilities import layer_readable_sentences

if TYPE_CHECKING:
    from ..models.game import Game
    from .combat import Attack


# -- parsing -----------------------------------------------------------------

_EXTRA_RE = re.compile(
    r"^(?P<subject>.+?) can block (?:any number of creatures"
    r"|an additional (?:creature|(?P<count>[a-z0-9-]+) creatures)(?: each combat)?"
    r"(?P<equipment> for each equipment attached to (?:this creature|it|[a-z ',-]+))?)\.?$",
    re.IGNORECASE,
)
_ONLY_RE = re.compile(r"^(?P<subject>.+?) can block only (?P<description>.+?)\.?$", re.IGNORECASE)
_LURE_RE = re.compile(
    r"^all creatures able to block (?P<subjects>.+?)(?: this turn)? do so\.?$", re.IGNORECASE
)
_EXACT_RE = re.compile(
    r"^(?P<subject>.+?) must be blocked by exactly (?P<count>[a-z0-9-]+) creatures?"
    r"(?: if able)?\.?$",
    re.IGNORECASE,
)
_RING_RE = re.compile(
    r"^as long as (?P<name>.+?) is your ring-bearer, (?:it|this creature) "
    r"must be blocked if able\.?$",
    re.IGNORECASE,
)
#: A lure's, restriction's or grant's subject that names *other* creatures
#: relative to the permanent carrying the line.
_ATTACHED_SUBJECTS = frozenset({"equipped creature", "enchanted creature"})
_EACH_YOU_CONTROL_RE = re.compile(
    r"^(?:each creature|creatures) you control(?: with (?P<description>.+))?$", re.IGNORECASE
)
_PLUS_ONE_COUNTER_RE = re.compile(r"^an? (?P<kind>[+-]\d+/[+-]\d+) counter on it$", re.IGNORECASE)
_ANY_COUNTER_RE = re.compile(r"^an? counters? on (?:it|them)$", re.IGNORECASE)


@dataclass(frozen=True)
class BlockStatic:
    """One parsed block-count, block-only, lure or exact-blockers sentence."""

    kind: str
    """"extra", "only", "lure", "exact" or "ring"."""
    sentence: str
    subjects: tuple[str, ...]
    """Raw lowercase subject phrases ("this creature", "enchanted creature",
    "each creature you control with a +1/+1 counter on it", ...)."""
    amount: int | None = None
    """"extra": how many more attackers (`None`: any number); "exact": N."""
    per_equipment: bool = False
    description: str | None = None
    """"only": what the blocker may block, e.g. "creatures with flying"."""


def _count_word(word: str | None) -> int | None:
    return 1 if word is None else parse_count(word, article=False)


@functools.lru_cache(maxsize=4096)
def parse_block_static(sentence: str) -> BlockStatic | None:
    """`sentence` as one of the shapes in the module docstring, or None."""
    text = " ".join(sentence.split())
    lowered = text.lower()
    if " can block " in lowered:
        if match := _EXTRA_RE.fullmatch(text):
            if "any number" in lowered:
                amount = None
            else:
                amount = _count_word(match.group("count"))
                if amount is None:
                    return None
            return BlockStatic(
                kind="extra",
                sentence=text,
                subjects=(match.group("subject").strip().lower(),),
                amount=amount,
                per_equipment=match.group("equipment") is not None,
            )
        if match := _ONLY_RE.fullmatch(text):
            from .combat import _parse_creature_description

            description = match.group("description").strip()
            if _parse_creature_description(description) is None:
                return None
            return BlockStatic(
                kind="only",
                sentence=text,
                subjects=(match.group("subject").strip().lower(),),
                description=description,
            )
        return None
    if lowered.startswith("all creatures able to block "):
        if match := _LURE_RE.fullmatch(text):
            subjects = tuple(
                part.strip().lower()
                for part in re.split(r"\s+or\s+", match.group("subjects"), flags=re.IGNORECASE)
            )
            return BlockStatic(kind="lure", sentence=text, subjects=subjects)
        return None
    if " must be blocked by exactly " in lowered:
        if match := _EXACT_RE.fullmatch(text):
            amount = parse_count(match.group("count"), article=False)
            if amount is None or amount < 1:
                return None
            return BlockStatic(
                kind="exact",
                sentence=text,
                subjects=(match.group("subject").strip().lower(),),
                amount=amount,
            )
        return None
    if lowered.startswith("as long as ") and "ring-bearer" in lowered:
        match = _RING_RE.fullmatch(text)
        if match is not None:
            return BlockStatic(
                kind="ring", sentence=text, subjects=(match.group("name").strip().lower(),)
            )
    return None


def _self_names(name: str) -> frozenset[str]:
    from .combat import _self_reference_names

    return frozenset({"this permanent", *(n.lower() for n in _self_reference_names(name))})


def _subject_is_wellformed(subject: str, name: str, *, group: bool, attached: bool) -> bool:
    if subject in _self_names(name):
        return True
    if attached and subject in _ATTACHED_SUBJECTS:
        return True
    if group:
        match = _EACH_YOU_CONTROL_RE.fullmatch(subject)
        if match is not None:
            description = match.group("description")
            return description is None or _counter_matcher(description) is not None
        from .combat import _parse_creature_description

        return _parse_creature_description(subject) is not None
    return False


def reads_block_static_line(text: str, name: str) -> bool:
    """Whether one static line (or mode bullet) of a card named `name` is a
    shape the enforcement code below reads in full - the static audit's
    credit for it. The subject has to be one the enforcement resolves: the
    permanent itself, "equipped"/"enchanted creature", or (for the count and
    restriction shapes) a group."""
    lowered = text.lower()
    if "block" not in lowered:
        return False
    sentences = [s.strip() for s in layer_readable_sentences(text)] or [text.strip()]
    return all(_sentence_is_read(sentence, name) for sentence in sentences if sentence)


def _sentence_is_read(sentence: str, name: str) -> bool:
    parsed = parse_block_static(sentence)
    if parsed is None:
        return False
    if parsed.kind == "ring":
        return parsed.subjects[0] in _self_names(name)
    group = parsed.kind in ("extra", "only")
    attached = parsed.kind != "ring"
    return all(
        _subject_is_wellformed(subject, name, group=group, attached=attached)
        for subject in parsed.subjects
    )


# -- who a sentence applies to -----------------------------------------------


def _counter_matcher(description: str):
    """A predicate on a creature's counters for "a +1/+1 counter on it" (a
    named kind) or "a counter on it" (any kind), or None."""
    text = description.strip()
    if _ANY_COUNTER_RE.fullmatch(text):
        return lambda counters: any(count > 0 for count in counters.values())
    match = _PLUS_ONE_COUNTER_RE.fullmatch(text)
    if match is not None:
        kind = match.group("kind")
        return lambda counters: counters.get(kind, 0) > 0
    return None


def _applies_to(
    game: "Game", source: CardState, subject: str, candidate: CardState, *, board
) -> bool:
    """Whether a sentence on permanent `source` with this `subject` is about
    `candidate`."""
    if subject in _self_names(source.name):
        return source.id == candidate.id
    if subject in _ATTACHED_SUBJECTS:
        return source.attached_to == candidate.id
    each = _EACH_YOU_CONTROL_RE.fullmatch(subject)
    if each is not None:
        if board.of(candidate).controller != board.of(source).controller:
            return False
        if not board.of(candidate).is_creature:
            return False
        description = each.group("description")
        if description is None:
            return True
        counter_test = _counter_matcher(description)
        return counter_test is not None and counter_test(board.of(candidate).counters)
    from .combat import _parse_creature_description

    matcher = _parse_creature_description(subject)
    return matcher is not None and matcher.matches(game, candidate)


def _statics_on_board(game: "Game", kinds: tuple[str, ...], gate: str, board):
    """Every (source, BlockStatic) of these kinds across the battlefield's
    computed abilities. `gate` is a cheap lowercase substring test that skips
    lines which cannot carry the shape."""
    found: list[tuple[CardState, BlockStatic]] = []
    for source in game.battlefield:
        for ability in board.of(source).abilities:
            if gate not in ability.lower():
                continue
            for sentence in layer_readable_sentences(ability):
                parsed = parse_block_static(sentence)
                if parsed is not None and parsed.kind in kinds:
                    found.append((source, parsed))
    return found


# -- CR 509.1b: "can block only ..." -------------------------------------------


def block_only_refusal(game: "Game", blocker: CardState, attacker: CardState) -> str | None:
    """Why a "can block only `<creatures>`" sentence (self, enchanted, or a
    group) stops `blocker` blocking `attacker`, or None (CR 509.1b)."""
    board = game.computed_board()
    from .combat import _parse_creature_description

    for source, parsed in _statics_on_board(game, ("only",), "can block only", board):
        if not any(
            _applies_to(game, source, subject, blocker, board=board) for subject in parsed.subjects
        ):
            continue
        assert parsed.description is not None
        matcher = _parse_creature_description(parsed.description)
        if matcher is not None and not matcher.matches(game, attacker):
            return (
                f"{blocker.name} can block only {parsed.description}, and {attacker.name} is "
                f'not one: {source.name} says "{parsed.sentence}" (CR 509.1b)'
            )
    return None


# -- CR 509.1a: how many attackers one blocker may block --------------------------


def _equipment_attached_to(game: "Game", creature: CardState, board) -> int:
    return sum(
        1
        for permanent in game.battlefield
        if permanent.attached_to == creature.id and "Equipment" in board.of(permanent).subtypes
    )


def blocks_allowed(game: "Game", blocker: CardState) -> int | None:
    """How many attackers `blocker` may block in one declaration (CR 509.1a):
    one, plus every "can block an additional creature" that applies to it;
    `None` for "any number of creatures"."""
    board = game.computed_board()
    allowed = 1
    for source, parsed in _statics_on_board(game, ("extra",), "can block", board):
        if not any(
            _applies_to(game, source, subject, blocker, board=board) for subject in parsed.subjects
        ):
            continue
        if parsed.amount is None:
            return None
        extra = parsed.amount
        if parsed.per_equipment:
            extra *= _equipment_attached_to(game, blocker, board)
        allowed += extra
    return allowed


def multi_block_refusal(game: "Game", declared: "dict[UUID, list[CardState]]") -> str | None:
    """Why a blocker declared on more attackers than it may block, or on one
    attacker twice, makes the declaration illegal, or None (CR 509.1a)."""
    blocked: dict[UUID, list[tuple[CardState, UUID]]] = {}
    for attacker_id, blockers in declared.items():
        for blocker in blockers:
            blocked.setdefault(blocker.id, []).append((blocker, attacker_id))
    for entries in blocked.values():
        blocker = entries[0][0]
        attackers = [attacker_id for _, attacker_id in entries]
        if len(set(attackers)) != len(attackers):
            return f"{blocker.name} cannot block the same attacker twice (CR 509.1a)"
        if len(attackers) < 2:
            continue
        allowed = blocks_allowed(game, blocker)
        if allowed is not None and len(attackers) > allowed:
            if allowed == 1:
                return f"{blocker.name} cannot block more than one attacker (CR 509.1a)"
            return (
                f"{blocker.name} cannot block more than {allowed} attackers: "
                f"{len(attackers)} declared (CR 509.1a)"
            )
    return None


# -- CR 509.1c: lures, exact-blocker counts, conditional must-be-blocked ----------


def _defending_username(game: "Game", attack: "Attack") -> str | None:
    from .combat import defending_player

    return defending_player(game, attack.defender)


def _attacker_requirements(game: "Game", kinds: tuple[str, ...], gate: str):
    """`(attack, BlockStatic)` for every attack whose attacker is a subject of
    a sentence of these kinds."""
    board = game.computed_board()
    found: list[tuple[Attack, BlockStatic]] = []
    statics = _statics_on_board(game, kinds, gate, board)
    if not statics:
        return found
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if not isinstance(attacker, CardState):
            continue
        for source, parsed in statics:
            if any(
                _applies_to(game, source, subject, attacker, board=board)
                for subject in parsed.subjects
            ):
                found.append((attack, parsed))
                break
    return found


def lure_attacks(game: "Game") -> list["Attack"]:
    """The attacks whose attacker is the subject of an "All creatures able to
    block `<it>` do so." sentence right now (CR 509.1c)."""
    return [attack for attack, _ in _attacker_requirements(game, ("lure",), "able to block")]


def _blocks_by(declared: "dict[UUID, list[CardState]]") -> dict[UUID, set[UUID]]:
    blocks: dict[UUID, set[UUID]] = {}
    for attacker_id, blockers in declared.items():
        for blocker in blockers:
            blocks.setdefault(blocker.id, set()).add(attacker_id)
    return blocks


def _with_block(
    declared: "dict[UUID, list[CardState]]",
    blocker: CardState,
    attacker_id: UUID,
    release: UUID | None,
) -> "dict[UUID, list[CardState]]":
    trial = {
        attacked: [
            chosen for chosen in blockers if not (chosen.id == blocker.id and attacked == release)
        ]
        for attacked, blockers in declared.items()
    }
    trial.setdefault(attacker_id, []).append(blocker)
    return trial


def _extra_requirement_trial(
    game: "Game",
    declared: "dict[UUID, list[CardState]]",
    candidate: CardState,
    lure: "Attack",
    lure_ids: set[UUID],
    *,
    allow_move: bool = True,
) -> "dict[UUID, list[CardState]] | None":
    """`declared` with `candidate` additionally blocking `lure` - added when
    it may block one more attacker, else moved off a block that obeys no lure
    - or None when no legal declaration obeys one more requirement."""
    from .combat import declaration_refusal

    blocking = _blocks_by(declared).get(candidate.id, set())
    if lure.attacker_id in blocking:
        return None
    allowed = blocks_allowed(game, candidate)
    release: UUID | None = None
    if allowed is not None and len(blocking) >= allowed:
        movable = [attacker_id for attacker_id in blocking if attacker_id not in lure_ids]
        if not movable or not allow_move:
            return None
        release = movable[0]
    trial = _with_block(declared, candidate, lure.attacker_id, release)
    return trial if declaration_refusal(game, trial) is None else None


def _able_candidates(game: "Game", attack: "Attack") -> list[CardState]:
    from .combat import block_refusal

    username = _defending_username(game, attack)
    if username is None:
        return []
    return [
        candidate
        for candidate in game.permanents_controlled_by(username)
        if block_refusal(game, candidate, attack) is None
    ]


def unobeyed_lure_requirement(
    game: "Game", declared: "dict[UUID, list[CardState]]", player: str | None = None
) -> str | None:
    """Why the block declaration `declared` obeys fewer lure requirements than
    it could, or None (CR 509.1c): a creature able to block a lure creature
    that is not blocking it - and could, without breaking any restriction -
    makes the declaration illegal. A tapped creature, a creature with "can't
    block" and a creature without flying or reach against a flyer are not
    able (`combat.block_refusal`) and so are excused; two lures each need
    every able creature, but one creature serves one of them unless it may
    block more (`blocks_allowed`)."""
    from .combat import declaration_refusal

    lures = lure_attacks(game)
    if not lures:
        return None
    lure_ids = {attack.attacker_id for attack in lures}
    for lure in lures:
        username = _defending_username(game, lure)
        if username is None or (player is not None and username != player):
            continue
        attacker = game.find_by_id(lure.attacker_id)
        able = [
            candidate
            for candidate in _able_candidates(game, lure)
            if candidate.id not in {b.id for b in declared.get(lure.attacker_id, [])}
        ]
        for candidate in able:
            if _extra_requirement_trial(game, declared, candidate, lure, lure_ids) is not None:
                return (
                    f"all creatures able to block {attacker.name} do so, and {candidate.name} "
                    f"could legally block it (CR 509.1c)"
                )
        # Several creatures that are only legal together (menace): one at a time
        # each trial fails, the whole set does not.
        if able and not declared.get(lure.attacker_id):
            trial = {attacked: list(blockers) for attacked, blockers in declared.items()}
            moved = False
            for candidate in able:
                if _blocks_by(trial).get(candidate.id) and (
                    blocks_allowed(game, candidate) is not None
                    and len(_blocks_by(trial)[candidate.id]) >= blocks_allowed(game, candidate)
                ):
                    continue
                trial.setdefault(lure.attacker_id, []).append(candidate)
                moved = True
            if moved and declaration_refusal(game, trial) is None:
                names = ", ".join(c.name for c in trial[lure.attacker_id])
                return (
                    f"all creatures able to block {attacker.name} do so, and {names} "
                    f"could legally block it together (CR 509.1c)"
                )
    return None


def required_lure_declaration(
    game: "Game", username: str, declared: "dict[UUID, list[CardState]]"
) -> list[tuple[UUID, UUID]]:
    """What `username`'s own creatures add to obey every lure they can
    (CR 509.1c) as `(blocker_id, attacker_id)` pairs - the unscripted
    default answer, `combat.required_block_declaration`'s helper for this
    requirement. `declared` is updated in place."""
    from .combat import declaration_refusal

    pairs: list[tuple[UUID, UUID]] = []
    lures = [lure for lure in lure_attacks(game) if _defending_username(game, lure) == username]
    lure_ids = {lure.attacker_id for lure in lures}
    for lure in lures:
        for candidate in _able_candidates(game, lure):
            trial = _extra_requirement_trial(
                game, declared, candidate, lure, lure_ids, allow_move=False
            )
            if trial is None:
                continue
            declared.clear()
            declared.update(trial)
            pairs.append((candidate.id, lure.attacker_id))
    if lures:
        # A menace lure needs its blockers together.
        for lure in lures:
            if declared.get(lure.attacker_id):
                continue
            trial = {attacked: list(blockers) for attacked, blockers in declared.items()}
            candidates = [
                c
                for c in _able_candidates(game, lure)
                if c.id not in {blocker for blocker, _ in pairs}
            ]
            trial.setdefault(lure.attacker_id, []).extend(candidates)
            if candidates and declaration_refusal(game, trial) is None:
                declared.clear()
                declared.update(trial)
                pairs.extend((c.id, lure.attacker_id) for c in candidates)
    return pairs


def exact_blocker_requirements(game: "Game") -> list[tuple["Attack", int]]:
    """`(attack, N)` for every attack whose attacker "must be blocked by
    exactly N creature(s) if able" right now (CR 509.1c)."""
    return [
        (attack, parsed.amount)
        for attack, parsed in _attacker_requirements(game, ("exact",), "must be blocked by")
        if parsed.amount is not None
    ]


def _exact_trial(
    game: "Game", declared: "dict[UUID, list[CardState]]", attack: "Attack", wanted: int
) -> "dict[UUID, list[CardState]] | None":
    """A legal declaration in which exactly `wanted` creatures block `attack`,
    reached from `declared` by adding or dropping blockers on it, or None."""
    from .combat import declaration_refusal

    current = list(declared.get(attack.attacker_id, []))
    trial = {attacked: list(blockers) for attacked, blockers in declared.items()}
    if len(current) > wanted:
        trial[attack.attacker_id] = current[:wanted]
    else:
        blocking = _blocks_by(declared)
        for candidate in _able_candidates(game, attack):
            if len(trial[attack.attacker_id]) >= wanted:
                break
            if any(chosen.id == candidate.id for chosen in current):
                continue
            allowed = blocks_allowed(game, candidate)
            if allowed is not None and len(blocking.get(candidate.id, ())) >= allowed:
                continue
            trial[attack.attacker_id].append(candidate)
    if len(trial.get(attack.attacker_id, [])) != wanted:
        return None
    return trial if declaration_refusal(game, trial) is None else None


def unobeyed_exact_blockers(
    game: "Game", declared: "dict[UUID, list[CardState]]", player: str | None = None
) -> str | None:
    """Why `declared` leaves an attacker that "must be blocked by exactly N
    creatures if able" with some other number of blockers when a legal
    declaration gives it exactly N, or None (CR 509.1c)."""
    for attack, wanted in exact_blocker_requirements(game):
        username = _defending_username(game, attack)
        if username is None or (player is not None and username != player):
            continue
        have = len(declared.get(attack.attacker_id, []))
        if have == wanted:
            continue
        if _exact_trial(game, declared, attack, wanted) is None:
            continue
        attacker = game.find_by_id(attack.attacker_id)
        noun = "creature" if wanted == 1 else "creatures"
        return (
            f"{attacker.name} must be blocked by exactly {wanted} {noun} if able, and "
            f"{have} block it though a legal declaration has exactly {wanted} (CR 509.1c)"
        )
    return None


def required_exact_declaration(
    game: "Game", username: str, declared: "dict[UUID, list[CardState]]"
) -> list[tuple[UUID, UUID]]:
    """What `username`'s creatures add so every "must be blocked by exactly N
    creatures if able" attacker gets N blockers (the unscripted default,
    CR 509.1c); `declared` is updated in place."""
    pairs: list[tuple[UUID, UUID]] = []
    for attack, wanted in exact_blocker_requirements(game):
        if _defending_username(game, attack) != username:
            continue
        before = {blocker.id for blocker in declared.get(attack.attacker_id, [])}
        if len(before) == wanted:
            continue
        trial = _exact_trial(game, declared, attack, wanted)
        if trial is None:
            continue
        declared.clear()
        declared.update(trial)
        pairs.extend(
            (blocker.id, attack.attacker_id)
            for blocker in trial[attack.attacker_id]
            if blocker.id not in before
        )
    return pairs


def ring_bearer_must_be_blocked(game: "Game", attacker: CardState, line: str) -> bool:
    """Whether `line` is "As long as `<attacker>` is your Ring-bearer, it
    must be blocked if able." and `attacker` is its controller's Ring-bearer
    (CR 701.54e): the conditional twin of the unconditional requirement
    `combat_statics` reads."""
    if "ring-bearer" not in line.lower():
        return False
    parsed = parse_block_static(line)
    if (
        parsed is None
        or parsed.kind != "ring"
        or parsed.subjects[0] not in _self_names(attacker.name)
    ):
        return False
    return game.ring_bearer_of(game.controller_of(attacker).username) is attacker
