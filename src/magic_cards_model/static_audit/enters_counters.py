"""Audit of "[This] enters with <counters>" static lines (CR 614.1c, CR 614.12).

A line is credited only when the PRODUCTION entry, `_self_enters_modifiers`,
really performs every enters-replacement sentence the line parses into. The
production entry is asked on throwaway permanents staged the way a real game
could be - a spell cast and kicked with a full set of mana spent, a board where
the gate reads true, a turn where an opponent lost life and a creature died,
and the bare empty board an "unless" gate needs - never by re-deriving what the
sentence means here. A sentence whose gate the engine cannot read is skipped by
the production entry in every staging, so it is not credited.
"""

from functools import cache

from magic_cards_model.machines.replacement.enters import _self_enters_modifiers
from magic_cards_model.machines.replacement.model import ENTERS_KINDS, ReplacementKind
from magic_cards_model.machines.replacement.parse import (
    parse_replacement_effects,
    strip_reminder_text,
)
from magic_cards_model.models.card import Card, Color, Type
from magic_cards_model.models.card_state import CardState, Counter, Counters
from magic_cards_model.models.game import Game
from magic_cards_model.models.game.records import CastRecord
from magic_cards_model.models.player import Player
from magic_cards_model.models.zone import Zone


@cache
def _board_cards() -> tuple[Card, ...]:
    """Real printings that make the common board gates true: a power 4+
    creature, a mana value 4+ permanent, five lands."""
    from magic_cards_model.support import _cards_by_power_or_toughness, _cards_by_type

    big = _cards_by_power_or_toughness("power", "more", 4)[:1]
    lands = tuple(_cards_by_type().get(Type.LAND, ()))[:1] * 5
    return (*big, *lands)


def _stage(printing: Card, *, rich: bool, record: CastRecord | None) -> tuple[Game, CardState]:
    from magic_cards_model.support import _synthetic_permanent

    game = Game(
        players=[Player(username="sweep_you"), Player(username="sweep_opp")],
        schema_version=Game.CURRENT_SCHEMA_VERSION,
    )
    state = _synthetic_permanent(
        printing, controller="sweep_you", token=False, tapped=False, counter_kind=None
    )
    state.bind_to_game(game)
    if rich:
        opponent = game.players[1]
        for card in _board_cards():
            permanent = CardState(
                card=card,
                zone=Zone.BATTLEFIELD,
                controller="sweep_you",
                owner="sweep_you",
                counters=Counters({Counter.PLUS_ONE: 1})
                if Type.CREATURE in card.types
                else Counters(),
            )
            permanent.bind_to_game(game)
            game.battlefield.append(permanent)
        opponent.lose_life(1)
        game.record_turn_fact("attacked", "sweep_you")
        game.creatures_died_this_turn = 1
    if record is not None:
        game.cast_records[state.zone_change_stamp] = record
    return game, state


_ALL_MANA = {color: 3 for color in (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)}


def _stagings(printing: Card):
    """Each way of staging the entering permanent: nothing behind it (an
    "unless" gate, a plain line), a kicked cast with every colour spent from
    a rich board (raid, adamant, kicker, "cast it from your hand", "five or
    more untapped lands"), and an escape cast (CR 702.138b)."""
    cast = CastRecord(origin_zone=Zone.HAND, kicked=1, mana_spent=dict(_ALL_MANA), x_value=6)
    yield _stage(printing, rich=False, record=None)
    yield _stage(printing, rich=True, record=cast)
    yield _stage(
        printing,
        rich=True,
        record=CastRecord(origin_zone=Zone.GRAVEYARD, keyword="Escape", x_value=0),
    )
    yield _stage(printing, rich=True, record=CastRecord(origin_zone=Zone.GRAVEYARD, x_value=0))


def _line_effects(printing: Card, text: str):
    return [
        effect
        for effect in parse_replacement_effects(printing)
        if effect.kind in ENTERS_KINDS
        and effect.self_replacement
        and strip_reminder_text(effect.raw)[0].strip() == text.strip()
    ]


def _group_line_performed(printing: Card, text: str) -> bool:
    """A group line ("Each Dragon you control enters with an additional ...")
    is credited when the production reader (`_group_entering_counters`),
    asked with the printing staged as the source on the battlefield (or in the
    graveyard for its "as long as this creature is in your graveyard" form)
    and a real printing from the pool entering under the same controller,
    produces an effect for it that applies cleanly."""
    from magic_cards_model.machines.replacement.enters import (
        _group_entering_counters,
        group_enters_specs,
    )
    from magic_cards_model.machines.replacement.model import EventKind, ReplaceableEvent
    from magic_cards_model.support import _probe_pool

    specs = group_enters_specs([text])
    if not specs:
        return False
    for spec in specs:
        performed = False
        for candidate in _probe_pool().values():
            game, source = _stage(printing, rich=True, record=None)
            entering = CardState(
                card=candidate, zone=Zone.STACK, controller="sweep_you", owner="sweep_you"
            )
            entering.bind_to_game(game)
            if not spec["predicate"](source, entering):
                continue
            if spec["in_graveyard"]:
                source.zone = Zone.GRAVEYARD
                game.players[0].graveyard.append(source)
            else:
                game.battlefield.append(source)
            event = ReplaceableEvent(kind=EventKind.ENTERS_BATTLEFIELD, card=entering)
            try:
                effects = _group_entering_counters(game, event)
                for effect in effects:
                    effect.apply(game, effect.source, event)
            except Exception:
                return False
            performed = bool(effects)
            break
        if not performed:
            return False
    return True


def reads_static_line(
    printing: Card, text: str, *, card_name: str | None = None, legendary: bool = False
) -> bool:
    lowered = text.lower()
    if "counter" not in lowered or not ("enter" in lowered or "escape" in lowered):
        return False
    if "additional" in lowered and _group_line_performed(printing, text):
        return True
    effects = _line_effects(printing, text)
    if not effects or any(effect.kind is not ReplacementKind.ENTERS_WITH for effect in effects):
        return False
    pending = {effect.text.strip() for effect in effects}
    for game, state in _stagings(printing):
        try:
            labels = " ".join(
                label for _suffix, _apply, label, _copy in _self_enters_modifiers(game, state)
            )
        except Exception:
            continue
        pending = {sentence for sentence in pending if sentence not in labels}
        if not pending:
            return True
    return False
