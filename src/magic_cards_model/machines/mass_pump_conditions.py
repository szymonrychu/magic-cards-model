"""Condition-gated riders after a mass pump or grant, and "the same is true for".

A mass pump ("Creatures you control get +1/+1 until end of turn.") is often
followed by sentences that only apply when something is true, all about "those
creatures" - the group the first sentence fixed (CR 611.2c):

- Break of Day (fateful hour): "If you have 5 or less life, those creatures
  gain indestructible until end of turn."
- Heroic Charge (kicker, CR 702.33d): "If this spell was kicked, those
  creatures also gain trample until end of turn."
- Kytheon's Tactics (spell mastery): "... two or more instant and/or sorcery
  cards in your graveyard, those creatures also gain vigilance ..."
- Unbreakable Formation (addendum): "If you cast this spell during your main
  phase, put a +1/+1 counter on each of those creatures and they gain
  vigilance until end of turn."
- Zealous Display: "If it's not your turn, untap those creatures." (CR 701.26)
- Golden Demise (CR 702.131 city's blessing): "If you have the city's
  blessing, instead only creatures your opponents control get -2/-2 until end
  of turn." (CR 614.1a: "instead" replaces the first sentence's effect.)

Each condition is answered by `Game.condition_holds`, with the trigger's own
ability and event threaded through for a triggered ability (CR 603.2), so an
anaphor like Guul Draz Overseer's "that land" finds the land that entered.
A condition nobody claims leaves the whole thing unread, as it always did.

The second family is Bleeding Effect, Concerted Effort and Odric, Lunarch
Marshal: "Creatures you control gain <kw> until end of turn if a creature
(card in your graveyard | you control) has <kw>. The same is true for <list>."
Per CR 608.2c every keyword is its own instruction, checked against the board
as the ability resolves *before* any of them is granted, so a keyword this
very ability gives out never feeds another check. "Landwalk" and "protection"
are families, not keywords (CR 702.14, CR 702.16): the creatures'
own instances are copied (swampwalk, protection from black), never a generic
one.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from .triggers import AbilityOnStack

#: What a rider needs to run: the game, the source (the spell or the
#: ability's permanent), its controller, and the resolving ability (None for a
#: spell).
RiderEffect = Callable[["Game", "CardState", str, "AbilityOnStack | None"], None]
#: Runs one mass-pump template against the board; returns the group it found.
RunPump = Callable[..., "list[CardState]"]

_ABILITY_WORD_RE = re.compile(r"^[A-Z][A-Za-z' ]+ — ")
_SUBJECT_RE = re.compile(r"^(?P<subject>.+?) (?:get|gain) ", re.IGNORECASE)

_GRANT_RE = re.compile(
    r"^if (?P<cond>.+?), those creatures (?:also )?gain (?P<kws>.+?) until end of turn$",
    re.IGNORECASE,
)
_COUNTERS_RE = re.compile(
    r"^if (?P<cond>.+?), put (?P<n>an?|\w+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? "
    r"on each of those creatures(?: and they gain (?P<kws>.+?) until end of turn)?$",
    re.IGNORECASE,
)
_UNTAP_RE = re.compile(r"^if (?P<cond>.+?), untap those creatures$", re.IGNORECASE)
_INSTEAD_ONLY_RE = re.compile(
    r"^if (?P<cond>.+?), instead only (?P<rest>creatures (?:you|your opponents) control "
    r"(?:get|gain) .+)$",
    re.IGNORECASE,
)


def _normalized(sentence: str) -> str:
    return _ABILITY_WORD_RE.sub("", sentence.strip()).rstrip(".").strip()


def _parseable(template: str) -> bool:
    """Whether `machines/layers.py` reads `template` as a pump or grant."""
    from .effects import _mass_pump_parseable, _substitute_mass_pump_magnitude
    from .layers import parsed_layer_effects

    probe = _substitute_mass_pump_magnitude(template, 1)
    return parsed_layer_effects(_mass_pump_parseable(probe)) is not None


def rider_effect(
    template: str, remainder: str, magnitude_expr: object, run_pump: RunPump
) -> RiderEffect | None:
    """The whole mass pump `template` followed by gated riders in `remainder`,
    or None when `remainder` is not made only of the shapes above (the caller's
    other readers, and ultimately its fail-closed notice, then keep it)."""
    subject_match = _SUBJECT_RE.match(template)
    if not remainder or subject_match is None:
        return None

    from . import conditions
    from .effects import (
        LayerRemainderNotice,
        _counter_kind,
        _plain_resolution_sentences,
        parse_count,
    )

    subject = subject_match.group("subject")
    instead: list[tuple[str, str]] = []
    additive: list[tuple] = []
    for sentence in _plain_resolution_sentences(remainder):
        text = _normalized(sentence)
        if (match := _INSTEAD_ONLY_RE.match(text)) is not None:
            if magnitude_expr is not None:
                return None
            replacement = match.group("rest")
            replacement = replacement[0].upper() + replacement[1:] + " until end of turn."
            if "until end of turn" in match.group("rest").lower():
                replacement = replacement.removesuffix(" until end of turn.") + "."
            if not _parseable(replacement):
                return None
            instead.append((match.group("cond"), replacement))
        elif (match := _GRANT_RE.match(text)) is not None:
            grant = f"{subject} gain {match.group('kws')} until end of turn."
            if not _parseable(grant):
                return None
            additive.append(("grant", match.group("cond"), grant))
        elif (match := _COUNTERS_RE.match(text)) is not None:
            amount = parse_count(match.group("n"))
            if amount is None:
                return None
            grant = (
                f"{subject} gain {match.group('kws')} until end of turn."
                if match.group("kws")
                else None
            )
            if grant is not None and not _parseable(grant):
                return None
            additive.append(
                ("counters", match.group("cond"), amount, _counter_kind(match.group("kind")), grant)
            )
        elif (match := _UNTAP_RE.match(text)) is not None:
            additive.append(("untap", match.group("cond")))
        else:
            return None
    conditions_used = [cond for cond, _ in instead] + [step[1] for step in additive]
    if not conditions_used or not all(conditions.claims(cond) for cond in conditions_used):
        return None

    def run(
        game: "Game", source: "CardState", controller: str, ability: "AbilityOnStack | None"
    ) -> None:
        def holds(condition: str) -> bool:
            if ability is None:
                answer = game.condition_holds(controller, condition, source)
            else:
                answer = game.condition_holds(
                    controller,
                    condition,
                    source,
                    ability=ability.ability,
                    event=ability.event,
                    source_stamp=ability.source_stamp,
                )
            if answer is None:
                game.layer_remainder_notices.append(
                    LayerRemainderNotice(
                        source_id=source.id, source_name=source.name, text=condition
                    )
                )
            return bool(answer)

        chosen = template
        for condition, replacement in instead:
            if holds(condition):
                chosen = replacement
        group = run_pump(game, source, controller, chosen, magnitude_expr)
        for step in additive:
            if not holds(step[1]):
                continue
            if step[0] == "grant":
                run_pump(game, source, controller, step[2], None)
            elif step[0] == "counters":
                _kind, _cond, amount, counter_kind, grant = step
                for target in group:
                    if target.zone.name == "BATTLEFIELD":
                        game.add_counters(target, counter_kind, amount)
                if grant is not None:
                    run_pump(game, source, controller, grant, None)
            else:
                for target in group:
                    if target.zone.name == "BATTLEFIELD":
                        target.untap()

    return run


# -- "The same is true for <list>" ------------------------------------------------

_SAME_IS_TRUE_RE = re.compile(
    r"^creatures you control gain (?P<first>[a-z ]+?) until end of turn "
    r"if (?P<where>a creature card in your graveyard|a creature you control) has (?P=first)\."
    r"\s+the same is true for (?P<rest>[a-z ,]+?)\.?$",
    re.IGNORECASE,
)

#: Keyword families whose instances differ (CR 702.14, CR 702.16).
_FAMILIES = ("landwalk", "protection")


def _keyword_list(first: str, rest: str) -> list[str] | None:
    names = [first.strip().lower()]
    for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", rest.strip().lower()):
        if part.strip():
            names.append(part.strip())
    from .layers import KNOWN_KEYWORDS

    if any(name not in KNOWN_KEYWORDS and name not in _FAMILIES for name in names):
        return None
    return names


def same_is_true_effect(effect_text: str) -> Callable[["Game", "AbilityOnStack"], None] | None:
    """The ability effect for the "same is true for" family, or None."""
    match = _SAME_IS_TRUE_RE.match(collapsed(effect_text))
    if match is None:
        return None

    from .effects import _run_mass_pump

    names = _keyword_list(match.group("first"), match.group("rest"))
    if names is None:
        return None
    in_graveyard = "graveyard" in match.group("where")

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        source = ability.source(game)
        if source is None:
            return
        controller = ability.controller
        granted = _instances_to_grant(game, controller, in_graveyard, names)
        for instance in granted:
            _run_mass_pump(
                game,
                source,
                controller,
                f"Creatures you control gain {instance} until end of turn.",
                None,
            )

    return effect


def _instances_to_grant(
    game: "Game", controller: str, in_graveyard: bool, names: list[str]
) -> list[str]:
    """Every keyword instance some creature has, read before anything is
    granted: a plain keyword once, each landwalk and protection present once."""
    from ..models.game import protection_qualities
    from .combat import LANDWALK_TYPES, has_keyword
    from .layers import creatures_controlled_by

    if in_graveyard:
        holders = [card for card in game.player(controller).graveyard if card.is_creature]
    else:
        board = game.computed_board()
        selector = creatures_controlled_by(controller)
        holders = [p for p in game.battlefield if selector(board.of(p), board.characteristics)]

    def protections(holder: "CardState") -> list[str]:
        if in_graveyard:
            return protection_qualities(holder.card)
        return game._effective_protection_qualities(holder)

    granted: list[str] = []
    for name in names:
        if name == "landwalk":
            found = [
                keyword.value
                for keyword in LANDWALK_TYPES
                if any(has_keyword(holder, keyword, game) for holder in holders)
            ]
        elif name == "protection":
            found = []
            for holder in holders:
                for quality in protections(holder):
                    instance = f"protection from {quality}"
                    if instance not in found:
                        found.append(instance)
        else:
            found = [name] if any(has_keyword(holder, name, game) for holder in holders) else []
        granted.extend(instance for instance in found if instance not in granted)
    return granted


__all__ = ["rider_effect", "same_is_true_effect"]
