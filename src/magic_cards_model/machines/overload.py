"""Overload (CR 702.96): the overloaded side of a spell, read from its printed side.

CR 702.96a: casting for the overload cost changes the spell's text by replacing
every "target" with "each", and CR 702.96b: an overloaded spell requires no
targets. Two readers cover that, in order:

1. The changed text itself, for the shapes the engine has a mass reader for
   ("Destroy each artifact you don't control", "deals 4 damage to each creature
   you don't control"): `keywords.overload_text`, then `effect_for`.
2. Otherwise the *printed* side's own per-target reader, followed once for every
   object the target phrase describes - the meaning of "each" in a text whose only
   change is that word (CR 608.2f). A tap, a return, a counter, a pump, a
   "becomes", a "put a counter, then double" are all read once, by the reader
   that already understands the targeted sentence, and are never re-parsed here.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.card import Card
from ..models.card_state import CardState, TargetRef
from ..models.player import Player
from .keywords import overload_text

if TYPE_CHECKING:
    from ..models.game import Game


def _reads(effect: object) -> bool:
    from .effects.tokens import _is_notice_only

    return (
        effect is not None
        and not _is_notice_only(effect)
        and getattr(effect, "unparsed_remainder", None) is None
    )


def _mass_candidates(game: "Game", spell: CardState) -> list[Any]:
    """Every object the printed "target ..." phrase describes right now, in
    board order (CR 702.96a's "each"): the phrase is judged by the same
    `TargetRequirement.rejects` an announcement uses, but nothing here is a
    target (CR 702.96b), so hexproof, shroud and protection do not apply."""
    requirements = game._resolution_profile(spell).requirements
    caster = game.controller_of(spell).username
    return [
        thing
        for thing in game.targetable_objects()
        if thing is not spell
        and all(
            requirement.rejects(thing, caster, game, spell.id) is None
            for requirement in requirements
        )
    ]


def _ref(thing: Any) -> TargetRef:
    return TargetRef.to_player(thing) if isinstance(thing, Player) else TargetRef.to_card(thing)


def _once_for_each(printed: Callable[..., None]) -> Callable[["Game", CardState], None]:
    def effect(game: "Game", spell: CardState) -> None:
        # CR 608.2f: the objects are fixed before the first is acted on; one an
        # earlier step moved away (CR 400.7) is a new object and no longer "each".
        candidates = [
            (thing, getattr(thing, "zone", None)) for thing in _mass_candidates(game, spell)
        ]
        try:
            for thing, zone in candidates:
                if getattr(thing, "zone", None) is not zone:
                    continue
                spell.targets = [_ref(thing)]
                printed(game, spell)
        finally:
            spell.targets = []

    return effect


def overload_effect(card_name: str, printed_text: str, *, x_value: int | None = None):
    """The effect an overloaded `card_name` resolves with, or `None` when neither
    reader understands it. `printed_text` is the card's own (unchanged) text."""
    from .effects import effect_for

    changed = effect_for(card_name, overload_text(printed_text), x_value=x_value)
    if _reads(changed):
        return changed
    printed = effect_for(card_name, printed_text, x_value=x_value)
    if not _reads(printed):
        return None
    return _once_for_each(printed)


def overload_is_read(printing: Card) -> bool:
    """Whether the overloaded side of this printing resolves in full (the
    support oracle's question): a changed-text reader, or a printed per-target
    reader behind exactly one target phrase `_mass_candidates` can enumerate."""
    from .effects import effect_for
    from .targeting import targeting_profile

    text = printing.front_oracle_text or ""
    if _reads(effect_for(printing.name, overload_text(text), x_value=1)):
        return True
    if not _reads(effect_for(printing.name, text, x_value=1)):
        return False
    profile = targeting_profile(printing)
    return profile.understood and len(profile.requirements) == 1
