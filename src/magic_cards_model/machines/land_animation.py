"""An animation whose retention clause is a sentence of its own.

"Untap target Mountain. It becomes a 4/4 red Elemental creature until end of
turn. It's still a land." (Koth of the Hammer), "Put X +1/+1 counters on
target land you control. That land becomes a 0/0 Elemental creature with
haste. It's still a land." (Waker of the Wilds), and the same shape on
Wakeroot Elemental, Tendril of the Mycotyrant, Titania, Gaea Incarnate and
Roaring Earth's Channel.

- **CR 205.1b** - "Some effects change an object's card type, subtype, and/or
  supertype but specify that it retains a prior card type, subtype, or
  supertype": "It's still a land." keeps the land type and every land subtype,
  so the animated Mountain is still a Mountain and still taps for mana
  (CR 305.6).
- **CR 611.2a** - with no duration the animation lasts for the rest of the
  game; "until end of turn" ends it at cleanup (CR 514.2).
- **CR 608.2c** - the instructions run in the order written: the untap and the
  counters come first, so a target 0/0 land has its counters before it is a
  creature that state-based actions could check (CR 704.5f).

The clause is folded onto the animation sentence in front of it by
`machines/layers._fold_retention_clauses`, and `machines/layers.py`'s
`_ANIMATION_RE` reads the pair. What this module adds is the resolution
closure that *carries that sentence*: `effects.create_continuous_effect_of_
ability` reads the ability's whole text at resolution, so a closure built on
it does not change when the retention clause is removed, which is exactly how
`support.ignored_rider` tells a clause nothing read. This closure registers
the folded animation sentence itself, so the clause is part of what the
ability performs and the support oracle can see it.

Cosmium Confluence's second mode names no target at all: "Put three +1/+1
counters on a Cave you control. It becomes a 0/0 Elemental creature with haste.
It's still a land." The Cave is chosen by the spell's controller as the mode
resolves (CR 608.2d), the counters go on first (CR 608.2c) and "It" is that
Cave. `choose_and_animate_mode` is that reader; a mode chosen more than once
(CR 700.2d) resolves each time and chooses again.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState, Counter
from ..models.zone import Zone
from ..numbers import parse_count
from .abilities import ActivatedAbility
from .cost import cost_announces_x
from .decisions import Decision, DecisionKind, source_id_of
from .layers import is_genuine_resolution_layer_sentence, is_retention_clause
from .modes import substitute_x
from .targeting import profile_for_text

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack

#: "Put three +1/+1 counters on a Cave you control. It becomes a 0/0 Elemental
#: creature with haste. It's still a land." - the counters, an untargeted
#: "a <type or subtype> you control", and the animation of "It".
_CHOOSE_AND_ANIMATE_RE = re.compile(
    r"^put (?P<count>\w+) \+1/\+1 counters? on an? (?P<quality>[A-Za-z]+) you control\.\s+"
    r"(?P<animation>It becomes an? .+\. It's still an? .+?)\.?$",
    re.IGNORECASE,
)


def retained_animation_sentence(sentences: Sequence[str]) -> str | None:
    """The one genuine layer sentence among `sentences` that ends in its folded
    "It's still a `<type>`." clause, or `None`.

    A sentence naming X is left to the path that substitutes it (Jolrael's
    "where X is the number of cards in your hand"): this closure registers the
    sentence as printed.
    """
    animations = [
        sentence
        for sentence in sentences
        if is_genuine_resolution_layer_sentence(sentence)
        and _ends_in_retention(sentence)
        and "X" not in sentence
    ]
    return animations[0] if len(animations) == 1 else None


def _ends_in_retention(sentence: str) -> bool:
    head, _, tail = sentence.rstrip().rpartition(". ")
    return bool(head) and is_retention_clause(tail)


def retained_animation_effect(animation: str) -> Callable[[Game, AbilityOnStack], None]:
    """Register `animation` (the folded sentence, retention clause included)
    for what the resolving ability targeted, or for its source when its text
    names no target (CR 611.2, CR 608.2b) - the same subject rule
    `effects.create_continuous_effect_of_ability` applies, with the sentence
    this closure carries as the registered text."""

    def animate(game: Game, ability: AbilityOnStack) -> None:
        from .effects import continuous_effects, layer_context_for

        source = ability.source(game)
        if source is None:
            return
        ability_text = (
            substitute_x(ability.ability.text, ability.x_value)
            if isinstance(ability.ability, ActivatedAbility)
            and cost_announces_x(ability.ability.cost)
            else ability.ability.text
        )
        profile = profile_for_text(ability_text)
        requires_target = profile.understood and bool(profile.requirements)
        # CR 113.7a: a targeted ability outlives its source.
        if not requires_target and source.zone is not Zone.BATTLEFIELD:
            return
        targets = game.resolve_card_targets(ability) if requires_target else [source]
        if not targets:
            return
        continuous_effects(game).create(
            source,
            targets=targets,
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=animation,
            game=game,
        )

    return animate


def choose_and_animate_mode(text: str) -> Callable[[Game, CardState], None] | None:
    """`_CHOOSE_AND_ANIMATE_RE`'s mode (Cosmium Confluence), or `None`.

    The effect lets the spell's controller choose one permanent they control
    with the stated card type or subtype (CR 608.2d; no choice is asked when
    only one qualifies, and nothing happens when none does), puts the counters
    (CR 122.1a), then registers the animation for it (CR 611.2). The animation
    sentence must itself be a layer sentence `machines/layers.py` reads.
    """
    match = _CHOOSE_AND_ANIMATE_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    count = parse_count(match.group("count"))
    animation = f"{match.group('animation')}."
    if count is None or not is_genuine_resolution_layer_sentence(animation):
        return None
    quality = match.group("quality").lower()

    def effect(game: Game, spell: CardState) -> None:
        from .effects import continuous_effects, layer_context_for

        controller = game.controller_of(spell)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if quality in _quality_words(game, permanent)
        ]
        if not candidates:
            return
        chosen = candidates[0]
        if len(candidates) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose a {match.group('quality')} you control",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=1,
                    exact=True,
                    cards=tuple(candidate.id for candidate in candidates),
                )
            )
            chosen = next(candidate for candidate in candidates if candidate.id in answer)
        game.add_counters(chosen, Counter.PLUS_ONE, count)
        continuous_effects(game).create(
            spell,
            targets=[chosen],
            context=layer_context_for(game, controller),
            ability_text=animation,
            game=game,
        )

    return effect


def _quality_words(game: Game, permanent: CardState) -> set[str]:
    """The lower-cased card types and subtypes `permanent` has right now."""
    characteristics = game.characteristics_of(permanent)
    return {str(word).lower() for word in (*characteristics.types, *characteristics.subtypes)}
