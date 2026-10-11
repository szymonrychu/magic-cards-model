"""Plan enchantments' own sentence shapes (CR 205.3h names Plan an
enchantment type).

Every Plan printed so far (Marvel Super Heroes) is two triggered abilities:

- a counter-adding trigger ending "... and put a plan counter on this
  enchantment" - read by the ordinary clause parser, except Claim the
  Kingdom's "put a +1/+1 counter on target creature you control and a plan
  counter on this enchantment", where one "put" governs two objects
  (`parse_put_counters_on_two_objects`);
- "When the Nth plan counter is put on this enchantment, ..." - the condition
  is `machines/triggers.py`'s `_NTH_COUNTER_PUT_CONDITION` (CR 122.6 as a
  threshold), and the effect opens with "sacrifice it" joined to its payoff
  one of three ways:

  - "sacrifice it. When you do, <effect>" - CR 603.12's reflexive ability,
    created only once the sacrifice has happened
    (`parse_sacrifice_self_when_you_do`);
  - "sacrifice it, <effect>, and <effect>" - a series of instructions run in
    order, none of them conditional on the sacrifice (CR 608.2c,
    `parse_sacrifice_self_then_series`);
  - "sacrifice it and <effect>" - two instructions, which the ordinary
    clause splitter already reads.

None of these shapes names a card: each is read off the ability's own text,
and each accepts "this <noun>" as well as "it" for the self-sacrifice.
"""

import re
from typing import TYPE_CHECKING

from ..models.zone import Zone
from ..numbers import COUNT
from .triggers import AbilityOnStack

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game
    from .effects import AbilityEffect

#: "sacrifice it" / "sacrifice this enchantment" - the ability's own source.
_SACRIFICE_SELF = r"sacrifice (?:it|this [a-z]+)"

#: CR 603.12: "[Do something]. When you do, [effect]." with the mandatory
#: self-sacrifice as the action.
_SACRIFICE_SELF_WHEN_YOU_DO_RE = re.compile(
    rf"^(?P<action>{_SACRIFICE_SELF})\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "sacrifice it, draw a card, and put a +1/+1 counter on each creature you
#: control." - CR 608.2c's instructions in the order written, the first of
#: them the self-sacrifice.
_SACRIFICE_SELF_THEN_SERIES_RE = re.compile(
    rf"^(?P<action>{_SACRIFICE_SELF}),\s+(?P<rest>(?!when you do\b).+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "put a +1/+1 counter on target creature you control and a plan counter on
#: this enchantment." - one "put" (CR 122.1), two objects each getting its
#: own counters. The second object is always the ability's own source.
_PUT_COUNTERS_ON_TWO_OBJECTS_RE = re.compile(
    rf"^put (?P<first>(?:{COUNT}) \S+ counters? on (?!this )[^.]+?) and "
    rf"(?P<second>(?:{COUNT}) \S+ counters? on this [a-z]+)\.?$",
    re.IGNORECASE,
)


def parse_sacrifice_self_when_you_do(text: str) -> "AbilityEffect | None":
    """ "sacrifice it. When you do, `<consequence>`." (CR 603.12, CR 701.21a).

    The sacrifice is mandatory ("instruct", not "allow"), so no question is
    asked. The reflexive ability is created only if the source really was
    sacrificed: a source that already left the battlefield - or left and came
    back as a new object (CR 400.7) - is not sacrificed, and then nothing
    reflects. Its consequence is read now, so an unreadable one fails the
    whole ability closed rather than sacrificing for nothing, and again when
    it resolves (`delayed.ReflexiveConsequence`), choosing its own targets as
    it goes on the stack (CR 603.3d)."""
    match = _SACRIFICE_SELF_WHEN_YOU_DO_RE.fullmatch(text.strip())
    if match is None:
        return None

    from .delayed import ReflexiveConsequence
    from .effects import parse_mixed_effect, reflexive_consequence_effect

    sacrifice = parse_mixed_effect(match.group("action") + ".")
    consequence = match.group("consequence").strip() + "."
    if sacrifice is None or reflexive_consequence_effect(consequence) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        stamp = None if source is None else source.zone_change_stamp
        sacrifice(game, ability)
        if source is None or source.zone is Zone.BATTLEFIELD or source.zone_change_stamp == stamp:
            return  # CR 603.12: nothing was sacrificed, so nothing reflects.
        game.create_reflexive_trigger(
            text=consequence,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


def parse_sacrifice_self_then_series(text: str) -> "AbilityEffect | None":
    """ "sacrifice it, `<effect>`, and `<effect>`." - the sacrifice, then the
    rest in the order written (CR 608.2c). Nothing after it is conditional on
    the sacrifice, so a source already gone is simply not sacrificed and the
    rest still happens (CR 113.7a)."""
    match = _SACRIFICE_SELF_THEN_SERIES_RE.fullmatch(text.strip())
    if match is None:
        return None

    from .effects import parse_mixed_effect

    rest = re.sub(r",\s+and\s+", ". ", match.group("rest").strip())
    rest = re.sub(r",\s+", ". ", rest)
    sacrifice = parse_mixed_effect(match.group("action") + ".")
    remainder = parse_mixed_effect(rest + ".")
    if sacrifice is None or remainder is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        sacrifice(game, ability)
        remainder(game, ability)

    return effect


def parse_put_counters_on_two_objects(text: str) -> "AbilityEffect | None":
    """ "put `<counters>` on `<object>` and `<counters>` on this `<noun>`." -
    each half read as its own "put" instruction, in the order written."""
    match = _PUT_COUNTERS_ON_TWO_OBJECTS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None

    from .effects import parse_mixed_effect

    first = parse_mixed_effect(f"put {match.group('first')}.")
    second = parse_mixed_effect(f"put {match.group('second')}.")
    if first is None or second is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        first(game, ability)
        second(game, ability)

    return effect
