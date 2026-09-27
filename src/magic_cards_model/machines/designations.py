"""Player designations a printed condition names - the one reader of their
wording, shared by every machine that gates on one.

A designation (CR 702.195b's enduring story) is "a marker that other rules and
effects can identify": a static ability prints "As long as you have an
enduring story, `<static>`" (CR 604.2, CR 611.3a - active only while the
condition holds), and a resolving effect prints "If you have an enduring
story, `<instruction>`" (CR 608.2c). The rest of the sentence is whatever the
machine that owns it already reads - `machines/layers.py` for a pump or a
grant, `machines/triggers.py` for a trigger multiplier (CR 603.2d),
`machines/combat.py` for an attack cost (CR 508.1h), `machines/keywords.py`
for an equip cost (CR 702.6a) - so this module only recognises the condition
and splits it off; it never decides what the rest means.

Kept import-free of the rest of the engine on purpose: every one of those
machines imports it, and they import each other.
"""

import re
from typing import Any

#: CR 702.195b's designation, as every storied card words the condition.
ENDURING_STORY = "you have an enduring story"

#: The conditions this module can answer, each to the `Player` field that
#: holds the designation.
_DESIGNATION_FIELDS: dict[str, str] = {ENDURING_STORY: "has_enduring_story"}

_CONDITION = "|".join(re.escape(condition) for condition in _DESIGNATION_FIELDS)

#: "As long as `<designation>`, `<rest>`" - a static ability's own gate
#: (CR 604.2: its effects are active only while the condition holds).
_AS_LONG_AS_RE = re.compile(
    rf"^as long as (?P<condition>{_CONDITION}), (?P<rest>.+)$", re.IGNORECASE | re.DOTALL
)

#: "`<rest>` unless `<designation>`" - the same gate printed the other way
#: round, true while the designation is *absent* (Bombur, Gentle Dreamer's
#: "Bombur doesn't untap during your untap step unless you have an enduring
#: story.").
_UNLESS_RE = re.compile(
    rf"^(?P<rest>.+?) unless (?P<condition>{_CONDITION})\.?$", re.IGNORECASE | re.DOTALL
)

#: "If `<designation>`, `<rest>`" - an instruction inside a resolving effect
#: (CR 608.2c), checked when that instruction is reached.
_IF_RE = re.compile(rf"^if (?P<condition>{_CONDITION}), (?P<rest>.+)$", re.IGNORECASE | re.DOTALL)


def designation_holds(condition: str, player: Any) -> bool:
    """Whether `player` has the designation `condition` names. A condition
    this module does not know is never true."""
    field = _DESIGNATION_FIELDS.get(condition.strip().lower())
    return field is not None and player is not None and bool(getattr(player, field, False))


def split_as_long_as(text: str) -> tuple[str, str] | None:
    """ "As long as you have an enduring story, creatures you control get
    +1/+1." -> `("you have an enduring story", "creatures you control get
    +1/+1.")`, or `None` when `text` opens with no designation gate."""
    match = _AS_LONG_AS_RE.match(text.strip())
    if match is None:
        return None
    return match["condition"].lower(), match["rest"].strip()


def split_unless(text: str) -> tuple[str, str] | None:
    """ "`<rest>` unless `<designation>`." -> `(condition, rest + ".")`, or
    `None`."""
    match = _UNLESS_RE.match(text.strip())
    if match is None:
        return None
    return match["condition"].lower(), match["rest"].strip() + "."


def split_if(text: str) -> tuple[str, str] | None:
    """ "If you have an enduring story, `<rest>`" -> `(condition, rest)`, or
    `None`."""
    match = _IF_RE.match(text.strip())
    if match is None:
        return None
    return match["condition"].lower(), match["rest"].strip()


#: CR 700.8: "A player's party consists of up to one Cleric creature that
#: player controls, up to one Rogue creature they control, up to one Warrior
#: creature they control, and up to one Wizard creature they control."
PARTY_ROLES: tuple[str, ...] = ("Cleric", "Rogue", "Warrior", "Wizard")


def party_size(game: Any, player: str) -> int:
    """How many creatures are in `player`'s party (CR 700.8a: "a number
    between zero and four"), read off the computed board (CR 613.5).

    CR 700.8b: a creature with more than one of the four types counts for
    only one of them, "counted in such a way to get the highest result" - a
    maximum matching of creatures to roles, found by augmenting paths (at
    most four roles, so this is tiny)."""
    candidates: list[set[str]] = []
    for permanent in game.permanents_controlled_by(player):
        chars = game.characteristics_of(permanent)
        if not chars.is_creature:
            continue
        roles = {role for role in PARTY_ROLES if role in chars.subtypes}
        if roles:
            candidates.append(roles)
    holder: dict[str, int] = {}

    def assign(index: int, seen: set[str]) -> bool:
        for role in candidates[index]:
            if role in seen:
                continue
            seen.add(role)
            if role not in holder or assign(holder[role], seen):
                holder[role] = index
                return True
        return False

    return sum(1 for index in range(len(candidates)) if assign(index, set()))


def has_full_party(game: Any, player: str) -> bool:
    """CR 700.8c: "A player has a full party if there are four creatures in
    that player's party." """
    return party_size(game, player) == len(PARTY_ROLES)


def solve_condition_of_line(line: str) -> str | None:
    """Placeholder until the Case reader lands below."""
    return None
