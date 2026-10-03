"""The behavioural pool sweep: every handled trigger fires, every handled
activation resolves - executed through the real engine, not parsed.

`support.card_support` (and `scripts/sweep_pool.py` on top of it) is a
*static* verdict: "a dispatcher returned an effect for this text". It said
`handled` for Devourer of Destiny's cast trigger on the day that trigger
vanished in production (engine b4316b8, fixed by 838d1b0), because the
dispatcher did return an effect - the trigger just never reached the stack.
This module is the execution-based guard that would have caught it.

For every card in the fixture pool that exists in Modern, Pioneer or Standard
(`support.in_target_formats`), and for every triggered or activated clause
`card_support` classifies `handled`:

- **Triggers.** A real board is built from real printings (no mocks, no
  hand-written card data), the ability's trigger event is raised through the
  engine's own path - the event is read off the engine's own parsed
  `TriggeredAbility.event` (or `_unread_trigger_events` for a condition the
  parser leaves `event=None`), never off a card name - and the test asserts
  the ability reaches the stack (CR 603.3), or resolves on the spot for a
  triggered mana ability (CR 605.4a), and that resolving it changes the game
  state or asks a question (CR 608.2d) - never a silent no-op, and never a
  notice (the engine failing closed on the clause).
- **Activations.** The ability is activated once on the same stock board,
  through `Game.begin_activating`/`activate_ability` (or `off_zone_activation`
  for an ability that functions from a hand, graveyard or exile), and the
  same "resolution did something" check runs.

How an event is raised is chosen by event kind only, and each kind tries a
short list of real actions (put the source onto the battlefield, cast it,
destroy it, attack with it, play whole turns with it in play, ...), each on
a fresh board, until one puts the ability on the stack. Each list runs three
times over: on the plain stock board ("quiet"), after an eventful turn that
satisfies the common "if you [did X] this turn" conditions ("busy"), and
with the opponent's non-land permanents gone ("lonely"). A target the stock
board cannot offer is supplied from the pool by the engine's own
`TargetRequirement.rejects` (`_target_material`). Where an event kind still
cannot be raised generically it is listed in `TRIGGER_KIND_SKIPS` with its
reason - one per kind, never per card - and the module teardown prints the
executed/skipped count for every kind.

The stock opposing board is chosen to catch the Devourer class of defect:
every coloured permanent the opponent controls *mentions* a targeting
protection in a statement without having one (Kaito, Bane of Nightmares on
its non-controller's turn, Fleecemane Lion while not monstrous), and every
artifact is a hexproof granter or remover (Shadowspear, Dragonfire Blade),
while the controller's own permanents are colourless. A misread that makes a
mention count as the keyword leaves a "permanent that's one or more colors"
trigger with no legal target, and CR 603.3d removes it - which fails here.
This generalises the cast-trigger guard 838d1b0 added to every trigger event.

Every executed case is also compared with its golden,
`tests/golden/<card-slug>/<triggered|activated>-<n>.json` - the board, the
recipe, the ability on the stack and the normalised delta its resolution
made (see `tests/golden/__init__.py`); `mise run golden:update` rewrites
them after an intended change.

Rules verified this session with `mise run rules:find`: CR 603.2 (a trigger
event matching makes the ability trigger), CR 603.3 (it goes on the stack the
next time a player would receive priority), CR 603.3d (no legal target for a
required target removes it), CR 603.4 (an intervening "if" is checked when
the event occurs), CR 605.4a (a triggered mana ability resolves
immediately), CR 608.2d (choices made during resolution), CR 602.2 (the
activation process), CR 702.11b (hexproof).
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import re
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple
from uuid import NAMESPACE_OID, uuid5

import pytest

from magic_cards_model.data.subtypes import canonical_subtype
from magic_cards_model.ids import install_id_allocator, reset_id_allocator
from magic_cards_model.machines import Step, conditions
from magic_cards_model.machines.abilities import (
    ActivatedAbility,
    StaticAbility,
    TriggeredAbility,
    TriggerEvent,
    has_mana_ability,
    keyword_abilities,
    parse_abilities,
    self_reference_names,
)
from magic_cards_model.machines.casting import (
    MarkedExile,
    keyword_cast_options,
    kicker_costs,
    optional_additional_costs,
)
from magic_cards_model.machines.conditions import board as board_conditions
from magic_cards_model.machines.conditions import cast_record as cast_record_conditions
from magic_cards_model.machines.conditions.player import _QUANTITY, _SUBJECT, _quantity_test
from magic_cards_model.machines.cost import ComponentKind, cost_component_for_phrase
from magic_cards_model.machines.counter_effects import singular_subtype
from magic_cards_model.machines.decisions import Decision, DecisionKind, ScriptedAnswer
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.machines.enlist import eligible_enlist_creatures
from magic_cards_model.machines.keywords import (
    craft_abilities,
    craft_activation,
    crew_activation,
    crew_number,
    cycling_activation,
    off_zone_abilities,
    off_zone_activation,
)
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    Duration,
    Layer,
    only_this_incarnation,
    set_controller,
)
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.machines.special_actions import locked_doors
from magic_cards_model.machines.speed import effective_speed, increase_speed
from magic_cards_model.machines.targeting import (
    CombatState,
    ControllerRestriction,
    TargetRequirement,
    profile_for_text,
)
from magic_cards_model.machines.teamwork import teamwork_ability
from magic_cards_model.machines.triggers import (
    AbilityOnStack,
    _required_cast_origin_zone,
    _singular_subtype,
    _unread_trigger_events,
    triggered_abilities_of,
    zones_ability_functions_in,
)
from magic_cards_model.models import Card, CardState, Color, Type, Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.card import Layout
from magic_cards_model.models.card_state import Choice, ChoiceKind, TargetRef
from magic_cards_model.models.game import (
    _STEP_NAMES,
    builtin_condition_readable,
    colored_symbol_count,
    read_activation_instructions,
    symbol_threshold_exile_cost,
)
from magic_cards_model.models.token import PREDEFINED, create_predefined_tokens, token_copy_of
from magic_cards_model.numbers import parse_count, parse_ordinal
from magic_cards_model.support import _probe_cards, card_support, in_target_formats
from tests import golden
from tests.cards import card_state, pool
from tests.scenarios.harness import PlayedScenario, ResolutionEffect, Scenario, mana_from

# ---------------------------------------------------------------------------
# The stock board.
# ---------------------------------------------------------------------------

ALICE = "alice"
BOB = "bob"

_BASICS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]
#: Enough mana of every colour (three of each, for {G}{G}{G} and "three or
#: more other Plains"), and colourless - kept no larger, because every
#: permanent is recomputed by the layer system (CR 613) on every check.
_LANDS = _BASICS * 3 + ["Wastes"] * 2
#: The opponent casts only one-mana spells.
_BOB_LANDS = [*_BASICS, "Wastes"]
#: The controller's own non-land permanents are colourless on purpose - see
#: the module docstring: a coloured one would give a "permanent that's one or
#: more colors" trigger a target the Devourer misread never touched.
_ALICE_PERMANENTS = ["Memnite", "Icehide Golem", "Bonesplitter", "Icy Manipulator"]
#: Every coloured permanent mentions a targeting protection it does not have
#: right now; every artifact grants or removes hexproof on something else.
_BOB_PERMANENTS = [
    "Kaito, Bane of Nightmares",
    "Fleecemane Lion",
    "Icehide Golem",
    "Shadowspear",
    "Dragonfire Blade",
]
_LIBRARY = ["Forest", "Grizzly Bears", "Island", "Lightning Bolt", "Swamp", "Opt"] * 5
_HAND = ["Forest", "Grizzly Bears", "Lightning Bolt", "Opt"]
#: Eight permanent cards, for "N or more permanent cards in your graveyard"
#: (the descend 4 / descend 8 ability words, CR 207.2c).
_GRAVEYARD = [
    "Grizzly Bears",
    "Lightning Bolt",
    "Forest",
    "Bonesplitter",
    "Opt",
    "Memnite",
    "Island",
    "Llanowar Elves",
    "Swamp",
    "Serra Angel",
]

#: Spells cast to raise "whenever you cast a ..." for another spell: real
#: printings spanning card type, colour, mana value, supertype and
#: targeting. Stock material, like the board - never chosen per card.
_PROBE_SPELLS = [
    "Opt",
    "Lightning Bolt",
    "Memnite",
    "Grizzly Bears",
    "Giant Growth",
    "Duress",
    "Bonesplitter",
    "Thoughtseize",
    "Llanowar Elves",
    "Serra Angel",
    "Kaito, Bane of Nightmares",
    "Devourer of Destiny",
]
#: Creatures to put onto the battlefield, kill or attack with when a
#: condition names "a creature" without a type the probe finder can use.
#: The {X} spell cast for "a spell with {X} in its mana cost", and its X.
_X_PROBE = "Endless One"
_X_PROBE_VALUE = 2
_PROBE_CREATURES = ["Memnite", "Grizzly Bears", "Llanowar Elves", "Serra Angel"]
#: Noncreature permanents, for a condition that names "noncreature
#: permanents": an Equipment and an enchantment.
_PROBE_NONCREATURES = ["Bonesplitter", "Intangible Virtue"]
#: Stock tools: an activated ability that targets (CR 115.1c), and a card
#: with an adventure to cast a spell from exile with (CR 715.4).
_TARGETING_TOOL = "Icy Manipulator"
#: The stock tool is an artifact; a "target ... ability ... from a creature
#: source" (Echo, Perceptive Prodigy, CR 113.7) needs a creature's ability on
#: the stack instead - Mogg Fanatic's sacrifice ability, which no summoning
#: sickness stops (CR 602.5a names only {T}/{Q} costs).
_CREATURE_TARGETING_TOOL = "Mogg Fanatic"
_ADVENTURER = "Bonecrusher Giant"
#: Stock probes for a condition on how the cast spell was paid for
#: (`machines/conditions/cast_record.py`): a kicker spell cast kicked (CR
#: 702.33d), a creature spell paid with mana from creatures, and an affinity
#: spell the stock artifacts make cheaper than its mana value (CR 702.41a).
_KICKER_PROBE = "Skizzik"
_MANA_CREATURE = "Llanowar Elves"
_CREATURE_MANA_PROBE = "Serra Angel"
_DISCOUNTED_PROBE = "Frogmite"


# ---------------------------------------------------------------------------
# Variants and per-case staging, read by `_board`.
# ---------------------------------------------------------------------------

QUIET, BUSY, LONELY, WAR = "quiet", "busy", "lonely", "war"
#: Every variant, in the order a case tries them.
VARIANTS = (QUIET, BUSY, LONELY, WAR)


class Material(NamedTuple):
    """A real printing (or a predefined token, CR 111.10) a case needs on the
    board: in `owner`'s `zone`, tapped, or put onto the battlefield this turn
    (`entered`) rather than staged there."""

    name: str
    owner: str
    zone: Zone
    tapped: bool = False
    entered: bool = False
    #: A counter kind put on it once staged, for "target creature with a
    #: stun counter on it" (CR 122.1).
    counter: str | None = None


@dataclass
class _Staging:
    """What every board of the case being run gets on top of the stock one."""

    variant: str = QUIET
    case: Case | None = None
    material: tuple[Material, ...] = ()
    #: The last board `_board` built, in the scenario harness's own words -
    #: the golden's `board`.
    board: dict[str, Any] | None = None
    #: Set by `staged_board`: stop the case at the board its event is
    #: raised on (or its ability activated on) and hand that board back.
    halt: bool = False
    #: How a trigger case answers its own optional ("up to") target (CR
    #: 115.6): "some" takes the first legal target, "none" declines - the
    #: engine's own default, and the second golden of such a case.
    optional_targets: str = "some"
    #: Whether "some" actually answered an optional target this attempt.
    optional_chosen: bool = False


_STAGING = _Staging()


@dataclass
class _OneOptionalTarget(ScriptedAnswer):
    """Answers the case card's own optional-target question (`target_minimum`
    0, CR 115.6) with the first legal target offered, so the recorded
    resolution acts on something; a mandatory question keeps the engine's
    default. Scripted, not mocked: the value is one of the targets `Game.ask`
    itself offered and still validates."""

    card: str = ""

    def matches(self, decision: Decision) -> bool:
        if decision.kind is not DecisionKind.CHOOSE_TARGETS:
            return False
        if decision.target_minimum > 0 or not decision.targets:
            return False
        if decision.source is None or not _same_card(decision.source, self.card):
            return False
        self.value = tuple(decision.targets[:1])
        _STAGING.optional_chosen = True
        return True


@dataclass
class _SomeOfAnyNumberExiled(ScriptedAnswer):
    """`_OneOptionalTarget`'s sibling for the untargeted "exile any number of
    <permanents>" choice (CR 107.1c - zero is a legal answer, and the
    engine's own default): the case card's own non-exact `CHOOSE_CARDS`
    question whose prompt is that exile is answered with the first card
    offered, so the recorded resolution exiles something and its delayed
    return is armed. Keyed by the prompt's shape, never by card; declined is
    the second golden, as for an optional target."""

    card: str = ""

    def matches(self, decision: Decision) -> bool:
        if decision.kind is not DecisionKind.CHOOSE_CARDS or decision.exact:
            return False
        if not decision.cards or not decision.prompt.lower().startswith("exile any number of"):
            return False
        if decision.source is None or not _same_card(decision.source, self.card):
            return False
        self.value = tuple(decision.cards[:1])
        _STAGING.optional_chosen = True
        return True


class _Halt(Exception):  # noqa: N818 - control flow, not an error
    """`staged_board`'s stop: the fully staged board of a recorded recipe."""

    def __init__(self, scenario: PlayedScenario) -> None:
        super().__init__("staged")
        self.scenario = scenario


def _halt_here(scenario: PlayedScenario) -> None:
    if _STAGING.halt:
        raise _Halt(scenario)


def _board(
    *,
    hand: tuple[str, ...] = (),
    battlefield: tuple[str, ...] = (),
    graveyard: tuple[str, ...] = (),
    bob_hand: tuple[str, ...] = (),
    bob_battlefield: tuple[str, ...] = (),
    active: str = ALICE,
    step: Step | None = Step.PRECOMBAT_MAIN,
    busy: bool = True,
    before: Callable[[PlayedScenario], Any] | None = None,
) -> PlayedScenario:
    """The stock board plus this attempt's own cards, at `step` of
    `active`'s turn (`None` leaves it in the untap step, before anything).

    The current variant and the case's target material are applied here, so
    every attempt gets them without asking: a busy variant adds a rich board
    and plays an eventful turn first (unless `busy=False`, for an attempt
    that plays the turn itself), a lonely one clears the opponent's
    non-land permanents. `before` stages the source on the built board
    before anything is played."""
    variant = _STAGING.variant
    extra: dict[str, dict[str, list[str]]] = {
        ALICE: {"battlefield": [], "graveyard": [], "hand": []},
        BOB: {"battlefield": [], "graveyard": [], "hand": []},
    }
    tapped_material: list[tuple[str, str]] = []
    tokens: list[tuple[str, str]] = []
    entering: list[tuple[str, str]] = []
    countered: list[tuple[str, str, str]] = []
    for name, owner, zone, tapped, entered, counter in _STAGING.material:
        if zone is Zone.STACK:
            # Cast from the owner's hand by `_stack_material` once the board
            # is built - so it has to be in that hand first.
            extra[owner]["hand"].append(name)
            continue
        if name in PREDEFINED:
            tokens.append((name, owner))
            continue
        if entered:
            extra[owner]["hand"].append(name)
            entering.append((name, owner))
            continue
        extra[owner][zone.value].append(name)
        if tapped:
            tapped_material.append((name, owner))
        if counter is not None and zone is Zone.BATTLEFIELD:
            countered.append((name, owner, counter))
    if variant == BUSY:
        # An enchantment, a 4-power creature, five more Mountains and three
        # snow lands, for "if you control an enchantment", "while you control
        # a creature with power 4 or greater", "five other Mountains" and
        # "four or more snow permanents".
        extra[ALICE]["battlefield"] += (
            ["Intangible Virtue", "Serra Angel"] + ["Mountain"] * 5 + ["Snow-Covered Forest"] * 3
        )
        extra[ALICE]["hand"] += ["Giant Growth", "Memnite", "Opt"]
    if variant == WAR:
        extra[ALICE]["battlefield"] += ["Grizzly Bears"] * 3
        extra[BOB]["battlefield"] += ["Grizzly Bears"] * 3
    bob_permanents = [] if variant == LONELY else list(_BOB_PERMANENTS)
    seats = {
        ALICE: {
            "library": list(_LIBRARY),
            "hand": list(_HAND) + list(hand) + extra[ALICE]["hand"],
            "battlefield": list(_LANDS)
            + list(_ALICE_PERMANENTS)
            + list(battlefield)
            + extra[ALICE]["battlefield"],
            "graveyard": list(_GRAVEYARD) + list(graveyard) + extra[ALICE]["graveyard"],
        },
        BOB: {
            "library": list(_LIBRARY),
            "hand": list(_HAND) + list(bob_hand) + extra[BOB]["hand"],
            "battlefield": list(_BOB_LANDS)
            + bob_permanents
            + list(bob_battlefield)
            + extra[BOB]["battlefield"],
            "graveyard": list(_GRAVEYARD) + extra[BOB]["graveyard"],
        },
    }
    order = [ALICE, BOB] if active == ALICE else [BOB, ALICE]
    _STAGING.board = {
        "variant": variant,
        "order": order,
        "players": seats,
        "tokens": [list(pair) for pair in tokens],
        "tapped": [list(pair) for pair in tapped_material],
        "entering": [list(pair) for pair in entering],
        "step": step.value if step is not None else None,
        "busy_turn": variant == BUSY
        and busy
        and step in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN),
        "war_turn": variant == WAR and busy and step is Step.PRECOMBAT_MAIN and active == ALICE,
    }
    if countered:
        # Only when there is one, so every board recorded before it stays
        # byte-identical.
        _STAGING.board["counters"] = [list(entry) for entry in countered]
    return build_recorded(_STAGING.board, _STAGING.case, before)


def build_recorded(
    board: dict[str, Any],
    case: Case | None,
    before: Callable[[PlayedScenario], Any] | None = None,
) -> PlayedScenario:
    """Build a board from its record (`_board`'s, and a golden's `board`):
    the seats, the predefined tokens, the step, the tapped and entering
    material, and the busy or war turn played before the case's event.
    `before` stages the source on the built board before anything is
    played."""
    order, seats, tokens = board["order"], board["players"], board["tokens"]
    scenario = Scenario()
    for username in order:
        scenario.player(username, **seats[username])
    # Every id the board mints, and every shuffle after it (`Game.game_uid`),
    # is pinned by the case, the variant and the board's own contents, so
    # the same attempt builds the same game on every run - what makes its
    # golden stable - while two different boards never share an id (a cost
    # requirement's `source_id` read on one board must not name a card on
    # another).
    contents = json.dumps([order, seats, tokens], sort_keys=True)
    case_id = case.id if case else ""
    seed = f"behavioural-sweep:{case_id}:{board['variant']}:{contents}"
    minted = itertools.count()
    token = install_id_allocator(lambda: uuid5(NAMESPACE_OID, f"{seed}:{next(minted)}"))
    try:
        played = scenario.build()
        played.game.game_uid = uuid5(NAMESPACE_OID, seed)
        for name, owner in tokens:
            create_predefined_tokens(played.game, name, owner)
    finally:
        reset_id_allocator(token)
    if case is not None and case.kind != "activated" and _STAGING.optional_targets == "some":
        played.game.decisions.add(
            _OneOptionalTarget(
                kind=DecisionKind.CHOOSE_TARGETS, value=(), uses=None, card=case.card
            )
        )
        played.game.decisions.add(
            _SomeOfAnyNumberExiled(
                kind=DecisionKind.CHOOSE_CARDS, value=(), uses=None, card=case.card
            )
        )
    if before is not None:
        before(played)
    step = Step(board["step"]) if board["step"] is not None else None
    if step is not None:
        played.start_at(step)
    # Tapped after the untap step `start_at` runs (CR 502.3), or it would be
    # untapped again before anything asked about it.
    for name, owner in board["tapped"]:
        _last(played, name, Zone.BATTLEFIELD, owner).tapped = True
    for name, owner, kind in board.get("counters", []):
        played.game.add_counters(_last(played, name, Zone.BATTLEFIELD, owner), kind, 1)
    if step is not None:
        for name, owner in board["entering"]:
            state = _last(played, name, Zone.HAND, owner)
            played.game.put_onto_battlefield(state, owner)
        saved, _STAGING.case = _STAGING.case, case
        try:
            if board["busy_turn"]:
                _busy_turn(played)
            if board["war_turn"]:
                _war_turn(played)
        finally:
            _STAGING.case = saved
    return played


def _busy_turn(scenario: PlayedScenario) -> None:
    """An eventful turn so far, for the "if you [did X] this turn" family of
    conditions (CR 603.4): three instants cast, two creature spells, life
    gained, two cards drawn, a permanent sacrificed (revolt), a permanent card
    discarded (descend), and an opponent's blue spell - each stopping early
    if the case's own ability already triggered off it."""
    case = _STAGING.case
    game = scenario.game

    def done() -> bool:
        return case is not None and _drive(scenario, case, None) is not None

    steps: list[Callable[[], Any]] = [
        lambda: _cast(scenario, "Opt"),
        lambda: _cast(scenario, "Lightning Bolt"),
        lambda: _cast(scenario, "Giant Growth"),
        lambda: _cast(scenario, "Grizzly Bears"),
        lambda: _cast(scenario, "Memnite"),
        lambda: game.gain_life(ALICE, 1),
        lambda: game.draw_cards(ALICE, 2),
        lambda: game.sacrifice(_first(scenario, "Memnite", ALICE)),
        lambda: game.discard_cards(ALICE, [_last(scenario, "Forest", Zone.HAND, ALICE)]),
        lambda: _opponent_casts(scenario, "Opt"),
    ]
    for step in steps:
        try:
            step()
        except (_Unavailable, ValueError, AssertionError):
            continue
        if done():
            return
        while game.stack:
            game.resolve_top()
            if done():
                return


def _war_turn(scenario: PlayedScenario) -> None:
    """A bloody turn so far, for the "attacked with N or more creatures this
    turn" and "N or more creatures died this turn" conditions (CR 602.5b,
    CR 603.4): every creature the controller can attack with attacks
    (CR 508.1), combat damage is dealt, then creatures other than the case's
    own card are destroyed until five have died (CR 700.4) - ending in the
    postcombat main phase."""
    case = _STAGING.case
    game = scenario.game
    own = case.card if case is not None else ""
    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    game.sync_priority_with_step()
    attackers = [
        p
        for p in game.permanents_controlled_by(ALICE)
        if Type.CREATURE in p.types and not _named(p, own) and scenario.can_attack(p)
    ]
    try:
        if attackers:
            scenario.attack_with(*attackers)
            _settle(scenario)
            while game.stack:
                game.resolve_top()
            scenario.no_blocks()
            scenario.combat_damage()
            _settle(scenario)
            while game.stack:
                game.resolve_top()
    except (ValueError, AssertionError):
        pass
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    game.sync_priority_with_step()
    victims = [
        p
        for p in [*game.permanents_controlled_by(BOB), *game.permanents_controlled_by(ALICE)]
        if Type.CREATURE in p.types and not _named(p, own)
    ]
    for victim in victims:
        if game.creatures_died_this_turn >= 5:
            break
        game.destroy(victim)
    _settle(scenario)
    while game.stack:
        game.resolve_top()


def _first(scenario: PlayedScenario, name: str, username: str) -> CardState:
    for state in scenario.game.permanents_controlled_by(username):
        if _named(state, name):
            return state
    raise _Unavailable(f"{username} controls no {name}")


def _named(state: CardState, name: str) -> bool:
    """`name` is a printing's full name; a double-faced permanent on the
    battlefield answers to the face that is up (CR 712.8f), so the front
    face's name has to match too."""
    faces = {name, *name.split(" // ")}
    # A Room permanent answers only to its unlocked doors' names, and to
    # none while fully locked (CR 709.5) - its printing's name still finds it.
    return state.name in faces or state.name.split(" //")[0] in faces or state.card.name == name


def _last(scenario: PlayedScenario, name: str, zone: Zone, username: str) -> CardState:
    """The copy of `name` this attempt added: the last one in `zone`, so a
    stock copy of the same card (a probe Memnite beside the stock one) is
    never picked by mistake."""
    if zone in scenario.game.shared_zones:
        found = [
            state
            for state in scenario.game.shared_zones[zone]
            if isinstance(state, CardState)
            and getattr(state, "controller_or_owner", None) == username
            and _named(state, name)
        ]
    else:
        found = [
            state for state in scenario.game.player(username).cards_in(zone) if _named(state, name)
        ]
    if not found:
        raise _Unavailable(f"{name} is not in {username}'s {zone.value}")
    return found[-1]


# ---------------------------------------------------------------------------
# Cases.
# ---------------------------------------------------------------------------


@cache
def _format_pool() -> tuple[Card, ...]:
    """Every distinct printing in the fixture pool that exists in Modern,
    Pioneer or Standard - the owner rule's scope."""
    seen: set[str] = set()
    cards: list[Card] = []
    for card in pool().values():
        if card.name in seen or not in_target_formats(card):
            continue
        seen.add(card.name)
        cards.append(card)
    return tuple(sorted(cards, key=lambda card: card.name))


def _event_kind(ability: TriggeredAbility) -> str:
    """The event this trigger watches, as the engine itself reads it."""
    if ability.event is not None:
        return ability.event.value
    unread = _unread_trigger_events(ability.condition)
    if unread:
        return "+".join(sorted(event.value for event in unread))
    return "state"


@dataclass(frozen=True)
class Case:
    card: str
    text: str
    kind: str
    number: int

    @property
    def id(self) -> str:
        return f"{self.card} #{self.number} [{self.kind}]"

    @property
    def printing(self) -> Card:
        return pool()[self.card]


def _handled(card: Card, kind: str) -> list[str]:
    return [
        clause.text
        for clause in card_support(card).clauses
        if clause.kind == kind and clause.status == "handled"
    ]


def _trigger_ability(card: Card, text: str) -> TriggeredAbility:
    for ability in triggered_abilities_of(card):
        if ability.text == text:
            return ability
    # A CR 603.8 state trigger ("When there are four or more page counters
    # on this artifact") is swept by `state_triggers_for`, not listed by
    # `triggered_abilities_of`, which answers for event triggers only.
    for ability in parse_abilities(card):
        if isinstance(ability, TriggeredAbility) and ability.text == text:
            return ability
    raise AssertionError(f"{card.name}: no triggered ability reads {text!r}")


@cache
def trigger_cases() -> tuple[Case, ...]:
    cases = []
    for card in _format_pool():
        for number, text in enumerate(_handled(card, "triggered")):
            kind = _event_kind(_trigger_ability(card, text))
            cases.append(Case(card.name, text, kind, number))
    return tuple(cases)


@cache
def activation_cases() -> tuple[Case, ...]:
    cases = []
    for card in _format_pool():
        for number, text in enumerate(_handled(card, "activated")):
            cases.append(Case(card.name, text, "activated", number))
    return tuple(cases)


# ---------------------------------------------------------------------------
# Finding the ability once the event has happened.
# ---------------------------------------------------------------------------


class _Unavailable(Exception):
    """This attempt's setup could not be made on the stock board - the next
    attempt is tried. Never a verdict on the ability itself."""


def _same_card(source_name: str, card: str) -> bool:
    """A source is named by the face that is up (CR 712.8e), so any face's
    name is this card's."""
    names = {card, *card.split(" // ")}
    return source_name in names or source_name.split(" //")[0] in names


def _settle(scenario: PlayedScenario) -> None:
    """CR 704.3 then CR 603.3: what the event caused, as the next priority
    would see it."""
    game = scenario.game
    if game.is_over:
        return
    game.check_state_based_actions()
    game.put_triggers_on_stack()


def _ours(scenario: PlayedScenario, case: Case, source_id: Any) -> AbilityOnStack | None:
    """The stack object this case's ability became, if it is there."""
    for item in scenario.game.stack:
        if not isinstance(item, AbilityOnStack) or item.ability.text != case.text:
            continue
        if source_id is not None and item.source_id != source_id:
            continue
        if _same_card(item.source_name, case.card):
            return item
    return None


def _drive(
    scenario: PlayedScenario,
    case: Case,
    source_id: Any,
    *,
    advance: bool = False,
    limit: int = 80,
) -> AbilityOnStack | None:
    """Look for the ability on the stack, resolving whatever else the event
    put there first; with `advance`, keep playing the turn forward (and the
    next ones, `limit` steps at most) until it shows up."""
    for _ in range(limit):
        _settle(scenario)
        found = _ours(scenario, case, source_id)
        if found is not None:
            return found
        if scenario.game.is_over:
            return None
        if scenario.game.stack:
            scenario.game.resolve_top()
            continue
        if not advance:
            return None
        scenario.advance()
    return None


# ---------------------------------------------------------------------------
# Targets: for the casts and activations the harness makes, and material for
# a target restriction the stock board cannot satisfy.
# ---------------------------------------------------------------------------


def _pick(scenario: PlayedScenario, slots: Any, prefer: Any = None, *, text: str = "") -> list[Any]:
    """The first legal candidates of each target slot (CR 601.2c) - `prefer`
    first when it is one - at least one per slot even for an "up to"
    requirement, so the resolution has something to act on, never the same
    object twice."""
    chosen: list[Any] = []
    taken: set[Any] = set()
    anchor: str | None = None
    for slot in slots:
        wanted = max(1, slot.minimum)
        if slot.maximum is not None:
            wanted = min(wanted, slot.maximum)
        options: list[Any] = [c for c in slot.candidates if c not in taken]
        options += [p for p in slot.player_candidates if p not in taken]
        if anchor is not None and _PRIOR_TARGET_PLAYER_PHRASE in text and slot.candidates:
            # Searing Blaze's dependent target (CR 601.2c): only a creature
            # the player just chosen (or that planeswalker's controller)
            # controls is a legal pairing.
            options = [
                option
                for option in options
                if not isinstance(option, str)
                and scenario.game.controller_of(scenario.game.find_by_id(option)).username == anchor
            ]
        if prefer in options:
            options.remove(prefer)
            options.insert(0, prefer)
        for option in options[:wanted]:
            taken.add(option)
            picked = option if isinstance(option, str) else scenario.game.find_by_id(option)
            chosen.append(picked)
            if isinstance(picked, str):
                anchor = picked
            elif picked is not None:
                anchor = scenario.game.controller_of(picked).username
    return [c for c in chosen if c is not None]


_PRIOR_TARGET_PLAYER_PHRASE = "that player or that planeswalker's controller controls"


def _action_for(
    scenario: PlayedScenario, username: str, kind: ActionKind, card_id: Any, **match: Any
) -> Any:
    for action in legal_actions(scenario.game, username):
        if action.kind is not kind or action.card_id != card_id:
            continue
        if all(getattr(action, field) == value for field, value in match.items()):
            return action
    return None


def _cast(
    scenario: PlayedScenario,
    name: str,
    username: str = ALICE,
    *,
    prefer: Any = None,
    keyword: str | None = None,
    kicked: bool = False,
    paying_with: str | None = None,
    from_zone: Zone = Zone.HAND,
    x_value: int | None = None,
    announce: Callable[[Any], Any] | None = None,
) -> CardState:
    """Cast `name` (CR 601.2) for its mana cost - face down with `keyword`
    (morph, CR 702.37c), kicked with `kicked` (CR 702.33a) - naming the
    first legal targets, and paying automatically, or with lands of the
    `paying_with` basic type first."""
    spell = _last(scenario, name, from_zone, username)
    action = _action_for(scenario, username, ActionKind.CAST, spell.id, alternative_cost=None)
    if keyword is None and from_zone is not Zone.HAND and action is not None:
        # The permission that lets it be cast from there (CR 715.3d's
        # Adventure, CR 702.34a's flashback) is announced as a keyword.
        keyword = action.keyword
    targets = (
        _pick(scenario, action.target_slots, prefer, text=spell.card.oracle_text or "")
        if action is not None
        else []
    )
    try:
        casting = scenario.cast(spell.name, username, from_zone=from_zone, targets=targets or None)
        if announce is not None:
            # CR 601.2b: the caller's own announcement of an optional or
            # alternative cost, with the objects it names.
            announce(casting)
        elif keyword is not None:
            casting.use_keyword(keyword)
        if kicked:
            # CR 702.33b: "Kicker [A] and/or [B]" is two kicker costs - kick
            # with every one, so each linked "kicked with its [A] kicker"
            # (CR 702.33f) and "kicked twice" is true.
            costs = kicker_costs(spell.card)
            if len(costs) > 1:
                for cost in costs:
                    casting.pay_kicker(1, which=cost)
            else:
                casting.pay_kicker(1)
        if x_value is not None:
            # CR 107.3a: the X announced for an {X} spell.
            casting.determine_cost(x_value=x_value)
        payment = casting.begin_paying()
        permanents = scenario.game.permanents_controlled_by(username)
        if paying_with is None:
            payment.auto_tap(permanents)
        else:
            # Tap the named basic type first, then colourless, for exactly
            # the spell's mana value - "if {U}{U} was spent" (CR 601.2h).
            lands = [p for p in permanents if p.card.is_land and not p.tapped]
            ordered = [p for p in lands if p.name == paying_with]
            ordered += [p for p in lands if p.name == "Wastes"]
            ordered += [p for p in lands if p not in ordered]
            for land in ordered[: int(spell.card.cmc)]:
                payment.tap_for_mana(land, mana_from(land))
        payment.pay()
        return scenario.put_on_stack(casting)
    except (ValueError, AssertionError) as error:
        raise _Unavailable(f"casting {name}: {error}") from error


def _opponent_casts(scenario: PlayedScenario, name: str, *, prefer: Any = None) -> CardState:
    """The non-active player casts an instant (CR 117.1a) once the active
    player has passed priority to them (CR 117.3d)."""
    active = scenario.game.active_player.username
    other = BOB if active == ALICE else ALICE
    if scenario.priority_holder == active:
        scenario.pass_priority(active)
    return _cast(scenario, name, other, prefer=prefer)


def _objects(scenario: PlayedScenario) -> list[Any]:
    game = scenario.game
    found: list[Any] = []
    for zone_cards in game.shared_zones.values():
        found += [s for s in zone_cards if isinstance(s, CardState)]
    for player in game.players:
        for zone_cards in player.zones.values():
            found += list(zone_cards)
    found += [item for item in game.stack if isinstance(item, AbilityOnStack)]
    found += list(game.players)
    return found


def _satisfied(scenario: PlayedScenario, requirement: TargetRequirement) -> bool:
    return any(
        requirement.rejects(candidate, ALICE, scenario.game, None) is None
        for candidate in _objects(scenario)
    )


def _quick_fit(card: Card, requirement: TargetRequirement) -> bool:
    """A cheap pre-filter on the printed characteristics a requirement
    names, before the engine's own `rejects` is asked on a real board."""
    types = set(card.types)
    if requirement.card_types and not requirement.card_types & types:
        return False
    if requirement.excluded_card_types & types:
        return False
    subtypes = {subtype.lower() for subtype in card.subtypes}
    if (
        requirement.required_subtypes
        and not {subtype.lower() for subtype in requirement.required_subtypes} & subtypes
    ):
        return False
    if requirement.required_colors and not requirement.required_colors & set(card.colors or ()):
        return False
    if requirement.color_count == "colorless" and card.colors:
        return False
    return not requirement.excluded_colors & set(card.colors or ())


_PERMANENT_TYPES = {
    Type.ARTIFACT,
    Type.CREATURE,
    Type.ENCHANTMENT,
    Type.LAND,
    Type.PLANESWALKER,
    Type.BATTLE,
}


@cache
def _target_material(text: str) -> tuple[Material, ...]:
    """Real printings to add to the board so each target requirement of
    `text` has a legal candidate, found by the engine's own
    `TargetRequirement.rejects` - empty when the stock board already has one
    for every requirement (so the Devourer board is never diluted)."""
    profile = profile_for_text(text)
    if not profile.understood or not profile.requirements:
        return ()
    saved = _STAGING.variant, _STAGING.material
    _STAGING.variant, _STAGING.material = QUIET, ()
    try:
        stock = _board()
        material: list[Material] = []
        for requirement in profile.requirements:
            if _satisfied(stock, requirement):
                continue
            if Type.CREATURE in requirement.ability_source_types:
                material.append(Material(_CREATURE_TARGETING_TOOL, ALICE, Zone.BATTLEFIELD))
                continue
            if Zone.STACK in requirement.zones:
                # "target spell an opponent controls" (Hope-Ender Coatl's own
                # cast trigger) needs the probe staged under, and cast by,
                # the opponent - the identical `ControllerRestriction` map
                # `_find_material` already uses for a battlefield/graveyard
                # requirement, not always Alice: a probe Alice herself
                # controls is never a legal target for "an opponent
                # controls", and would find no legal target at all
                # (CR 603.3d) rather than the wrong owner being merely a
                # worse choice.
                owner = {
                    ControllerRestriction.YOU: ALICE,
                    ControllerRestriction.OPPONENT: BOB,
                    ControllerRestriction.NOT_YOU: BOB,
                }.get(requirement.controller, ALICE)
                material.append(Material(_stack_probe(requirement, owner), owner, Zone.STACK))
                continue
            found = _find_material(requirement)
            if found is not None:
                material.append(found)
        return tuple(material)
    finally:
        _STAGING.variant, _STAGING.material = saved


def _stack_probe(requirement: TargetRequirement, owner: str = ALICE) -> str:
    """The first stock probe spell that, cast on the stock board under
    `owner`, is a legal target for a "target ... spell" requirement
    (CR 115.1) - "target artifact spell you control", "target instant or
    sorcery spell with a single target", "target spell an opponent
    controls" - judged by the engine's own `rejects`; Opt when none is.

    `owner` matches `_target_material`'s own choice for the real staged
    material: verifying the probe under the wrong controller would reject
    every candidate for a controller-restricted requirement regardless of
    its card-type fit, and always fall back to the plain "Opt" default
    rather than a probe that actually matches the requirement's own
    qualifier.
    """
    for name in _PROBE_SPELLS:
        saved = _STAGING.material
        _STAGING.material = (Material(name, owner, Zone.STACK),)
        try:
            scenario = _board()
        finally:
            _STAGING.material = saved
        try:
            spell = _cast(scenario, name, owner)
        except _Unavailable:
            continue
        if requirement.rejects(spell, ALICE, scenario.game, None) is None:
            return name
    return "Opt"


#: The permanent a player is given more of, for "an opponent controls more
#: [type] than you" (CR 603.4): a real printing of that type.
_MORE_OF = {Type.LAND: "Plains", Type.CREATURE: "Grizzly Bears", Type.ARTIFACT: "Memnite"}


@cache
def _precondition_material(condition: str) -> tuple[Material, ...]:
    """Real printings that make an intervening "if an opponent controls more
    [lands/creatures/artifacts] than you" (CR 603.4) true on the stock board:
    the opponent gets one more of that type than the controller has, counted
    on the stock board by the engine itself. "N or more card types among
    [permanents you control and/or] cards in your graveyard" (delirium,
    Happily Ever After) gets one graveyard card of each type the stock board
    lacks (CR 300.1). A compound is staged one conjunct at a time."""
    if len(parts := _conjuncts(condition)) > 1:
        return tuple(item for part in parts for item in _precondition_material(part))
    types_among = re.fullmatch(
        r"there (?:is|are) (?P<count>\w+) or more card types among "
        r"(?P<permanents>permanents you control and/or )?cards in your graveyard",
        _clause(condition),
    )
    if types_among is not None:
        return _card_types_material(
            types_among.group("count"), types_among.group("permanents") is not None
        )
    subtype_card = re.search(
        r"there(?:'s| is) an? (?P<subtype>[\w-]+) card in your graveyard", condition.lower()
    )
    if subtype_card is not None:
        found = _subtype_printing(subtype_card.group("subtype"))
        return (Material(found, ALICE, Zone.GRAVEYARD),) if found else ()
    # "the number of other Caves you control plus the number of Cave cards in
    # your graveyard is three or greater" (Cavernous Maw, CR 602.5b): that
    # many cards of the subtype in the graveyard alone meet it.
    subtype_sum = re.search(
        r"the number of other [\w-]+ you control plus the number of (?P<subtype>[\w-]+) "
        r"cards in your graveyard is (?P<count>\w+) or greater",
        condition.lower(),
    )
    if subtype_sum is not None:
        found = _subtype_printing(subtype_sum.group("subtype"))
        needed = parse_count(subtype_sum.group("count")) or 0
        return tuple(Material(found, ALICE, Zone.GRAVEYARD) for _ in range(needed)) if found else ()
    match = re.search(r"an opponent controls more (\w+) than you", condition.lower())
    if match is None:
        return ()
    wanted = next(
        (kind for kind in _MORE_OF if match.group(1).rstrip("s") == kind.value.lower()), None
    )
    if wanted is None:
        return ()
    saved = _STAGING.variant, _STAGING.material
    _STAGING.variant, _STAGING.material = QUIET, ()
    try:
        game = _board().game
        counts = {
            username: sum(wanted in p.types for p in game.permanents_controlled_by(username))
            for username in (ALICE, BOB)
        }
    finally:
        _STAGING.variant, _STAGING.material = saved
    more = counts[ALICE] + 1 - counts[BOB]
    return tuple(Material(_MORE_OF[wanted], BOB, Zone.BATTLEFIELD) for _ in range(max(0, more)))


def _subtype_printing(wanted_subtype: str) -> str | None:
    """The first single-faced pool printing with that subtype."""
    return next(
        (
            card.name
            for card in _format_pool()
            if not card.card_faces
            and wanted_subtype in (subtype.lower() for subtype in card.subtypes)
        ),
        None,
    )


@cache
def _card_types_material(count: str, with_permanents: bool) -> tuple[Material, ...]:
    """`_precondition_material`'s card-types case: single-typed graveyard
    printings of each card type the stock board is missing, until `count`."""
    needed = parse_count(count)
    if needed is None:
        return ()
    saved = _STAGING.variant, _STAGING.material
    _STAGING.variant, _STAGING.material = QUIET, ()
    try:
        game = _board().game
        have = {t for state in game.player(ALICE).graveyard for t in state.types}
        if with_permanents:
            have |= {
                t
                for state in game.permanents_controlled_by(ALICE)
                for t in game.characteristics_of(state).types
            }
    finally:
        _STAGING.variant, _STAGING.material = saved
    material: list[Material] = []
    for card in _format_pool():
        if len(have) >= needed:
            break
        types = set(card.types)
        if card.card_faces or len(types) != 1 or types <= have:
            continue
        have |= types
        material.append(Material(card.name, ALICE, Zone.GRAVEYARD))
    return tuple(material)


def _find_material(requirement: TargetRequirement) -> Material | None:
    owners = {
        ControllerRestriction.YOU: [ALICE],
        ControllerRestriction.OPPONENT: [BOB],
        ControllerRestriction.NOT_YOU: [BOB],
    }.get(requirement.controller, [BOB, ALICE])
    zones = [z for z in (Zone.BATTLEFIELD, Zone.GRAVEYARD) if z in requirement.zones]
    tapped = bool(requirement.must_be_tapped)
    entered = requirement.must_have_entered_this_turn
    if requirement.must_be_token and Zone.BATTLEFIELD in zones:
        # "target token you control": a predefined token (CR 111.10) - the
        # pool holds printed cards only.
        for token in PREDEFINED:
            for owner in owners:
                candidate = Material(token, owner, Zone.BATTLEFIELD)
                saved = _STAGING.material
                _STAGING.material = (candidate,)
                try:
                    scenario = _board()
                finally:
                    _STAGING.material = saved
                staged = next(
                    p
                    for p in scenario.game.permanents_controlled_by(owner)
                    if p.token and p.name.startswith(token)
                )
                if requirement.rejects(staged, ALICE, scenario.game, None) is None:
                    return candidate
    tried = 0
    for card in _format_pool():
        if card.card_faces or not _quick_fit(card, requirement):
            continue
        for zone in zones:
            if zone is Zone.BATTLEFIELD and not set(card.types) & _PERMANENT_TYPES:
                continue
            for owner in owners if zone is Zone.BATTLEFIELD else [ALICE]:
                tried += 1
                if tried > 40:
                    return None
                candidate = Material(
                    card.name, owner, zone, tapped, entered, requirement.required_counter_kind
                )
                saved = _STAGING.material
                _STAGING.material = (candidate,)
                try:
                    scenario = _board()
                finally:
                    _STAGING.material = saved
                try:
                    staged = _last(scenario, card.name, zone, owner)
                except _Unavailable:
                    continue
                if requirement.rejects(staged, ALICE, scenario.game, None) is None:
                    return candidate
    return None


# ---------------------------------------------------------------------------
# Board conditions: "you control N <quality>" and "N colors among permanents
# you control" (`machines/conditions/board.py`), made true on the board a
# case runs on - judged by the engine's own reader and its own quality test,
# never by reading the words here.
# ---------------------------------------------------------------------------


def _clause(condition: str) -> str:
    return " ".join(condition.strip().rstrip(".").split()).lower()


@cache
def _conjuncts(condition: str) -> tuple[str, ...]:
    """A compound "A and B" / serial "A, B, and C" condition (Happily Ever
    After) as the conjuncts the engine's own compound reader splits it into,
    so each is staged on its own; a clause some single reader claims whole,
    or any other shape, is its own only conjunct."""
    text = _clause(condition)
    if not text or conditions._claiming(text) is not None or builtin_condition_readable(text):
        return (condition,)
    for joiner, left, right in conditions._binary_splits(text):
        if joiner == "and" and conditions.claims(left) and conditions.claims(right):
            return _conjuncts(left) + _conjuncts(right)
    return (condition,)


@cache
def _board_clause(condition: str) -> tuple[str, Any, Any] | None:
    """`("control", test, amount)` for a "you control <amount> <quality>"
    clause and `("colors", test, None)` for "there are N colors among
    <quality> you control" - `test` the engine's own per-permanent quality
    test (`board.quality`), `amount` its own count test - or None for any
    other clause."""
    text = _clause(condition)
    for reader in board_conditions.READERS:
        match = reader.pattern.fullmatch(text)
        if match is None:
            continue
        if reader.read is board_conditions._controls and match.group("who") == "you":
            core, _grouping = board_conditions._split_quality(match.group("quality"))
            test = board_conditions.quality(core)
            amount = board_conditions._amount_test(match.group("amount"))
            if test is None or amount is None:
                return None
            return ("control", test, amount)
        if reader.read is board_conditions._colors_among:
            test = board_conditions.quality(match.group("quality"))
            return ("colors", test, None) if test is not None else None
    return None


def _board_holds(game: Any, source: CardState | None, condition: str) -> bool:
    context = conditions.ConditionContext(game=game, controller=ALICE, source=source)
    return conditions.read_condition(context, condition) is True


def _passes(game: Any, source: CardState | None, test: Any, state: CardState) -> bool:
    context = conditions.ConditionContext(game=game, controller=ALICE, source=source)
    try:
        return bool(test(context, state, game.characteristics_of(state)))
    except Exception:  # noqa: BLE001 - a candidate the test cannot read is no candidate
        return False


def _board_threshold(scenario: PlayedScenario, source: CardState | None, condition: str) -> None:
    """A "you control <amount> <quality>" condition (CR 603.4, CR 602.5b)
    the board does not meet yet is made true on it, each step judged by the
    engine: a +1/+1 counter on each of the controller's other creatures the
    counter makes pass the quality ("a creature with a +1/+1 counter on it",
    "an attacking modified creature", CR 700.9); then the controller's
    permanents that pass it exiled one at a time ("no artifacts", "exactly
    one creature", "no other creatures"); then the opponent's permanents
    that pass it gained control of (layer 2, CR 613.1b - "permanents you
    don't own"), each stopping as soon as the condition holds."""
    if len(parts := _conjuncts(condition or "")) > 1:
        for part in parts:
            _board_threshold(scenario, source, part)
        return
    found = _board_clause(condition or "")
    if found is None or found[0] != "control":
        return
    _kind, test, amount = found
    game = scenario.game
    if _board_holds(game, source, condition):
        return
    own = _STAGING.case.card if _STAGING.case is not None else ""

    def others(username: str) -> list[CardState]:
        return [
            permanent
            for permanent in game.permanents_controlled_by(username)
            if permanent is not source and not _named(permanent, own)
        ]

    for permanent in others(ALICE):
        if Type.CREATURE not in game.characteristics_of(permanent).types:
            continue
        if _passes(game, source, test, permanent):
            continue
        permanent.add_counters("+1/+1", 1)
        if not _passes(game, source, test, permanent):
            permanent.remove_counters("+1/+1", 1)
            continue
        if _board_holds(game, source, condition):
            return
    passing = [p for p in others(ALICE) if _passes(game, source, test, p)]
    if any(amount(count) for count in range(len(passing))):
        # Fewer is what the amount asks for ("no", "exactly one").
        for permanent in passing:
            game.exile_cards([permanent])
            if _board_holds(game, source, condition):
                return
    store = game.continuous_effects
    for permanent in others(BOB):
        if permanent.card.is_land or not _passes(game, source, test, permanent):
            continue
        store.add(
            ContinuousEffect(
                description=f"behavioural sweep: {ALICE} gains control of {permanent.name}",
                layer=Layer.CONTROL,
                timestamp=store.tick(),
                duration=Duration.INDEFINITE,
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=set_controller(ALICE),
            ),
            game,
        )
        if _passes(game, source, test, permanent) and _board_holds(game, source, condition):
            return


@cache
def _board_candidates() -> tuple[str, ...]:
    """Nonlegendary single-faced permanent printings of the pool, for a
    quality the stock board has too few of."""
    return tuple(
        card.name
        for card in _format_pool()
        if not card.card_faces
        and set(card.types) & _PERMANENT_TYPES
        and "Legendary" not in (card.type_line or "")
        and not card.is_land
    )


@cache
def _board_material(card_name: str, condition: str) -> tuple[Material, ...]:
    """Real printings (or predefined tokens, CR 111.10) that, added to the
    controller's side of the stock board, make a board condition true there
    after `_board_threshold` - the fewest copies of the first candidate the
    engine's own quality test accepts, confirmed by the engine's own reader
    on a built board. For "N colors among permanents you control" (CR
    105.2), one permanent of each missing color. A compound is staged one
    conjunct at a time (`_conjuncts`)."""
    if len(parts := _conjuncts(condition or "")) > 1:
        return tuple(item for part in parts for item in _board_material(card_name, part))
    found = _board_clause(condition or "")
    if found is None:
        return ()
    kind, test, _amount = found
    saved = _STAGING.variant, _STAGING.material
    _STAGING.variant = QUIET

    def confirmed(material: tuple[Material, ...]) -> bool:
        _STAGING.material = material
        scenario = _board(battlefield=(card_name,))
        source = _last(scenario, card_name, Zone.BATTLEFIELD, ALICE)
        _board_threshold(scenario, source, condition)
        return _board_holds(scenario.game, source, condition)

    try:
        if confirmed(()):
            return ()
        _STAGING.material = ()
        stock = _board(battlefield=(card_name,))
        game = stock.game
        source = _last(stock, card_name, Zone.BATTLEFIELD, ALICE)
        if kind == "colors":
            have: set[Color] = set()
            for permanent in game.permanents_controlled_by(ALICE):
                if _passes(game, source, test, permanent):
                    have |= set(game.characteristics_of(permanent).colors)
            material: list[Material] = []
            for color in Color:
                if color in have or color is Color.COLORLESS:
                    continue
                name = next(
                    (
                        name
                        for name in _board_candidates()
                        if list(pool()[name].colors or ()) == [color]
                        and _passes(game, source, test, card_state(name))
                    ),
                    None,
                )
                if name is not None:
                    material.append(Material(name, ALICE, Zone.BATTLEFIELD))
            return tuple(material) if material and confirmed(tuple(material)) else ()
        passing = [
            name for name in _board_candidates() if _passes(game, source, test, card_state(name))
        ]
        names = passing[:6]
        if " with different " in _clause(condition):
            # "N or more Demons with different names" (CR 201.2b): one copy
            # each of distinct printings, grown until the engine's own
            # grouped count holds.
            for count in range(1, min(len(passing), 10) + 1):
                material = tuple(
                    Material(name, ALICE, Zone.BATTLEFIELD) for name in passing[:count]
                )
                try:
                    if confirmed(material):
                        return material
                except (_Unavailable, ValueError, KeyError):
                    break
        for name in [*names, *PREDEFINED]:
            for copies in (1, 2, 3):
                material = tuple(Material(name, ALICE, Zone.BATTLEFIELD) for _ in range(copies))
                try:
                    if confirmed(material):
                        return material
                except (_Unavailable, ValueError, KeyError):
                    break
        return ()
    finally:
        _STAGING.variant, _STAGING.material = saved


def _stack_material(scenario: PlayedScenario) -> None:
    """A spell for a "target spell" requirement to aim at (CR 115.1)."""
    for name, owner, zone, *_ in _STAGING.material:
        if zone is Zone.STACK:
            with contextlib.suppress(_Unavailable):
                _cast(scenario, name, owner)


# ---------------------------------------------------------------------------
# Staging the source.
# ---------------------------------------------------------------------------

Attempt = Callable[[], tuple[PlayedScenario, Any]]


def _is(card: Card, card_type: Type) -> bool:
    return card_type in card.types


def _enchant_restriction(card: Card) -> str | None:
    for keyword in keyword_abilities(card):
        if keyword.canonical.lower() == "enchant":
            return (keyword.parameter or "").lower()
    return None


def _attach(scenario: PlayedScenario, source: CardState) -> None:
    """Stage an Aura on something it can enchant, as a board would have it:
    an unattached Aura is put into its owner's graveyard by CR 704.5m before
    anything else could happen."""
    restriction = _enchant_restriction(source.card)
    if restriction is None:
        return
    if "player" in restriction or "opponent" in restriction:
        source.attachment = TargetRef.to_player(scenario.game.player(BOB))
        return
    wanted = next((word for word in _BASICS if word.lower() in restriction), None)
    for permanent in scenario.game.permanents_controlled_by(ALICE):
        if permanent is source:
            continue
        if wanted is not None and permanent.name != wanted:
            continue
        if "land" in restriction and not permanent.card.is_land:
            continue
        if "creature" in restriction and Type.CREATURE not in permanent.types:
            continue
        if "artifact" in restriction and Type.ARTIFACT not in permanent.types:
            continue
        source.attachment = TargetRef.to_card(permanent)
        return


def _back_face(card: Card, ability: Any) -> bool:
    """Whether the ability is printed on a transforming card's back face
    (CR 712.2), so the source has to be staged transformed (CR 712.8e)."""
    faces = card.card_faces or []
    # A modal double-faced card whose front face transforms into its back
    # (Tony Stark's "Transform Tony Stark", Bruce Banner's) is staged the
    # same way (CR 701.27a turns the back face up).
    transforms = card.layout is Layout.TRANSFORM or (
        card.layout is Layout.MODAL_DFC
        and bool(faces)
        and re.search(r"\btransform\b", faces[0].oracle_text or "", re.IGNORECASE) is not None
    )
    return transforms and len(faces) > 1 and ability is not None and ability.face == faces[1].name


def _prime(scenario: PlayedScenario, source: CardState, ability: Any) -> CardState:
    """The source as the ability needs it: attached if an Aura, on the face
    the ability is printed on, at the Class level the ability unlocks at
    (CR 716.2a)."""
    if _back_face(source.card, ability):
        source.transformed = True
    face = getattr(ability, "face", None)
    faces = source.card.card_faces or []
    if (
        source.zone is Zone.BATTLEFIELD
        and source.card.layout is Layout.MODAL_DFC
        and not source.transformed
        and len(faces) > 1
        and face == faces[1].name
    ):
        # A modal permanent back face (The Prismatic Bridge) is up only when
        # it was cast as that face (CR 712.11b, CR 712.13) - staged the way
        # `move_to` records that resolution.
        source.land_face_played = face
    if (
        source.zone is Zone.BATTLEFIELD
        and face
        and face not in source.unlocked_doors
        and any(door.name == face for door in locked_doors(source))
    ):
        # A Room's door has its rules text only while unlocked (CR 709.5) -
        # staged with the designation (CR 709.5c), the way a Case is staged
        # solved below.
        source.unlocked_doors = (*source.unlocked_doors, face)
    level = getattr(ability, "class_level", None)
    if level is not None:
        source.class_level = level
    _attach(scenario, source)
    if getattr(ability, "ability_word", None) == "∞":
        # An Infinity ability functions only while its source is harnessed
        # (The Mind Stone, The Soul Stone) - staged harnessed.
        scenario.game.harness(source)
    if (getattr(ability, "ability_word", None) or "").lower() == "solved":
        # A "Solved -" ability works only once its Case is solved (CR 702.169c,
        # 702.169d) - staged solved, the designation CR 719.3b describes.
        source.solved = True
    if (getattr(ability, "ability_word", None) or "").lower() == "max speed":
        # "Max speed - [Ability]" exists only while its controller's speed is
        # 4 (CR 702.178a, 702.179e) - the controller's speed is increased to
        # it (CR 702.179c).
        player = scenario.game.player(source.controller)
        increase_speed(player, by=4 - effective_speed(player))
    _counter_threshold(scenario, source, getattr(ability, "intervening_if", None))
    _history_threshold(scenario, source, getattr(ability, "intervening_if", None))
    _target_damage_history(scenario, source, getattr(ability, "text", None))
    _board_threshold(scenario, source, getattr(ability, "intervening_if", None) or "")
    _player_state_threshold(scenario, getattr(ability, "intervening_if", None))
    _object_state_threshold(scenario, source, getattr(ability, "intervening_if", None))
    _chosen_parity(source, getattr(ability, "condition", None))
    _equip_for_condition(scenario, source, ability)
    _enter_for_condition(scenario, ability)
    return source


def _target_damage_history(scenario: PlayedScenario, source: CardState, text: str | None) -> None:
    """A target restriction or object filter reading "was dealt [combat]
    damage [by [N or more] <quality>] this turn" (Admiral Beckett Brass, Hope
    of Ghirapur, Steel Hellkite - CR 120.2a/120.2b) is satisfied on the stock
    board by playing the damage it asks about: opponent Bob is dealt damage
    by enough sources, each with the words of the "by" phrase (a color, a
    supertype, a card type, a subtype) or, for a self-reference, by the
    ability's own source - the records `Game.deal_damage` would have made."""
    from magic_cards_model.machines.conditions.history import (
        _DEALT_DAMAGE_TAIL_RE,
        _THIS_SELF_RE,
        _source_quality,
    )
    from magic_cards_model.models.card import Supertype
    from magic_cards_model.models.game import _COLOR_WORDS, DamageDealt

    lowered = (text or "").lower().replace(source.name.lower(), "this creature")
    found = _DEALT_DAMAGE_TAIL_RE.search(lowered)
    # Only the target phrase's own subject ("target player who", "a player
    # who", "whose controller") - an intervening "if" naming the damage is
    # `_damage_history`'s, staged by its own attempt.
    if found is None or not re.search(
        r"(?:player who|whose controller|^controller) $", lowered[: found.start()]
    ):
        return
    by_phrase = (found.group("by") or "").strip()
    sources = parse_count(found.group("by_count")) if found.group("by_count") else 1
    amount = parse_count(found.group("count")) if found.group("count") else 1
    self_reference = bool(by_phrase) and _THIS_SELF_RE.fullmatch(by_phrase) is not None
    if by_phrase and not self_reference and _source_quality(by_phrase) is None:
        return
    colors, supertypes, types, subtypes = [], [], [], []
    for word in by_phrase.replace(",", " ").split() if not self_reference else []:
        singular = word.removesuffix("s")
        if word in _COLOR_WORDS:
            colors.append(_COLOR_WORDS[word])
        elif (
            supertype := next((each for each in Supertype if each.value == word), None)
        ) is not None:
            supertypes.append(supertype)
        elif (
            card_type := next((each for each in Type if each.value == singular), None)
        ) is not None:
            types.append(card_type)
        elif (subtype := canonical_subtype(word)) is not None:
            subtypes.append(subtype)
    for index in range(sources):
        scenario.game.damage_dealt_this_turn.append(
            DamageDealt(
                source_id=source.id if self_reference else uuid5(NAMESPACE_OID, f"dealt-{index}"),
                source_controller=ALICE,
                source_types=tuple(types) or (Type.CREATURE,),
                source_subtypes=tuple(subtypes),
                source_supertypes=tuple(supertypes),
                source_colors=tuple(colors),
                recipient_player=BOB,
                amount=amount,
                combat="noncombat" not in (found.group("kind") or ""),
            )
        )


def _history_threshold(scenario: PlayedScenario, source: CardState, condition: str | None) -> None:
    """A this-turn (or last-turn) condition the stock board has not met yet is
    made true on it, read off the condition's own words - by playing the
    history it asks about through the engine (life gained or lost, CR 119.3;
    damage dealt, CR 120.1; a card leaving a graveyard or put into exile, CR
    603.10a/400.7; a permanent bounced, sacrificed or put into a graveyard
    from the battlefield, CR 701.21a/700.4; tokens entering; counters put, CR
    122.6; energy paid, CR 107.14; an Equipment attached), or, for what the
    turn before this one held, by staging last turn's own ledger the way the
    board itself is staged. For an intervening "if" (CR 603.4) and an
    "Activate only if" (CR 602.5b) alike."""
    lowered = (condition or "").lower()
    if not lowered:
        return
    game = scenario.game
    count = _history_count(lowered)
    if "an opponent lost life this turn" in lowered:
        game.lose_life(BOB, 1)
    if removed := re.search(r"an? (\S+) counter was removed from a permanent you", lowered):
        # "an oil counter was removed from a permanent you controlled this
        # turn": the source takes one and gives it up (CR 122.1).
        kind = removed.group(1)
        game.add_counters(source, kind, 1)
        source.remove_counters(kind, 1)
    if "left your graveyard this turn" in lowered:
        graveyard = [card for card in game.player(ALICE).graveyard if card is not source]
        if graveyard:
            game.exile_cards([graveyard[-1]])
    if "no creatures are on the battlefield" in lowered:
        # EC3's board reader (CR 613.5): every creature on the stock board
        # but the source is exiled, so the count is zero.
        creatures = [
            permanent
            for permanent in game.battlefield
            if permanent is not source and game.characteristics_of(permanent).is_creature
        ]
        if creatures:
            game.exile_cards(creatures)
    _life_history(scenario, lowered, count)
    _damage_history(scenario, source, lowered, count)
    _zone_history(scenario, source, lowered, count)
    _action_history(scenario, source, lowered, count)


_COLOR_OF = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def count_word(word: str) -> int:
    return int(word) if word.isdigit() else parse_count(word, article=False) or 1


def _history_count(lowered: str) -> int:
    """The "N" of an "N or more" in the condition, 1 without one."""
    match = re.search(r"\b(\w+) or more\b", lowered)
    if match is None:
        return 1
    word = match.group(1)
    return int(word) if word.isdigit() else parse_count(word, article=False) or 1


def _other_permanent(scenario: PlayedScenario, source: CardState, card_type: Type | None):
    for permanent in scenario.game.permanents_controlled_by(ALICE):
        if permanent is source or permanent.card.is_land:
            continue
        if card_type is None or card_type in permanent.types:
            return permanent
    return None


def _life_history(scenario: PlayedScenario, lowered: str, count: int) -> None:
    game = scenario.game
    whose = BOB if re.search(r"\ban opponent\b", lowered) else ALICE
    if re.search(r"\b(?:you|an opponent|a player) lost (?:\w+ or more )?life last turn", lowered):
        from magic_cards_model.machines.conditions.history import LIFE_LOST

        game.turn_counts_last_turn.setdefault(LIFE_LOST, {})[whose] = count
        return
    if re.search(r"\bgained(?: (?:and|or) lost)? (?:\w+ or more )?life this turn", lowered):
        game.gain_life(ALICE, count)
    if re.search(r"\b(?:and|or) lost life this turn", lowered) or re.search(
        r"\b(?:you|a player) lost (?:\w+ or more )?life this turn", lowered
    ):
        game.lose_life(ALICE, count)
    elif re.search(r"\ban opponent lost \w+ or more life this turn", lowered):
        game.lose_life(BOB, count)


def _damage_history(scenario: PlayedScenario, source: CardState, lowered: str, count: int) -> None:
    game = scenario.game
    if "this creature dealt damage to an opponent this turn" in lowered:
        game.deal_damage(game.player(BOB), 1, source=source)
    if re.search(r"\byou were dealt \w+ or more damage this turn", lowered):
        game.deal_damage(game.player(ALICE), count)
    if re.search(r"\ban opponent (?:was|has been) dealt damage this turn", lowered):
        game.deal_damage(game.player(BOB), 1)
    if re.search(r"damage was dealt to (?:it|this creature) this turn", lowered):
        game.deal_damage(source, count)
    if "was dealt excess damage this turn" in lowered:
        victim = next(
            (each for each in game.permanents_controlled_by(BOB) if Type.CREATURE in each.types),
            None,
        )
        if victim is not None:
            toughness = game.characteristics_of(victim).toughness or 0
            game.deal_damage(victim, toughness + 1)
    if re.search(r"paid or lost (\w+) or more \{e\}", lowered):
        game.add_player_counters(ALICE, "energy", count)
        game.may_pay_energy(ALICE, count)
    if lowered.startswith("equipped creature") and source.attached_to is None:
        wearer = _other_permanent(scenario, source, Type.CREATURE)
        if wearer is not None:
            source.attach_to(wearer)


def _zone_history(scenario: PlayedScenario, source: CardState, lowered: str, count: int) -> None:
    game = scenario.game
    if "put into your hand from the battlefield this turn" in lowered:
        bounced = _other_permanent(scenario, source, None)
        if bounced is not None:
            game.return_to_hand(bounced)
    if "put into exile this turn" in lowered:
        graveyard = [card for card in game.player(ALICE).graveyard if card is not source]
        if graveyard:
            game.exile_cards([graveyard[-1]])
    graveyard_from_battlefield = re.search(
        r"an? (?P<types>[a-z ]+?) was put into (?:a|your) graveyard from the battlefield", lowered
    )
    if graveyard_from_battlefield is not None:
        for word in re.split(r" or ", graveyard_from_battlefield.group("types")):
            card_type = next((each for each in Type if each.value == word.strip()), None)
            victim = _other_permanent(scenario, source, card_type)
            if victim is not None:
                game.destroy(victim)
                break
    entered = re.search(
        r"(?:\w+ or more |an? |another )(?P<quality>[a-z -]+?) entered the battlefield "
        r"under your control this turn",
        lowered,
    )
    if entered is not None and not re.search(r"\b(?:creature|land)s?\b", entered.group("quality")):
        # Artifacts, nonland permanents, permanents: Treasures entering.
        create_predefined_tokens(game, "Treasure", ALICE, count)
    if entered is not None and "face-down" in entered.group("quality"):
        from magic_cards_model.machines.effects import manifest

        top = game.player(ALICE).library[0]
        manifest(game, ALICE, top)
    if "that player had another land enter" in lowered:
        lands = [card for card in game.player(BOB).hand if card.card.is_land]
        if lands:
            game.put_onto_battlefield(lands[0], BOB)
    had = re.search(r"you had an? (?P<list>[a-z ]+?) enter the battlefield", lowered)
    if had is not None:
        wanted = [word.strip() for word in had.group("list").split(" or ")]
        entering = next(
            (
                printing
                for printing in pool().values()
                if printing.is_creature
                and any(word.capitalize() in printing.subtypes for word in wanted)
                and in_target_formats(printing)
            ),
            None,
        )
        if entering is not None:
            arriving = card_state(entering.name)
            game.player(ALICE).add(arriving, Zone.HAND)
            game.put_onto_battlefield(arriving, ALICE)


def _action_history(scenario: PlayedScenario, source: CardState, lowered: str, count: int) -> None:
    game = scenario.game
    sacrificed = re.search(r"sacrificed (?:\w+ or more |an? )(?P<what>\w+?)s? this turn", lowered)
    if sacrificed is not None:
        what = sacrificed.group("what").capitalize()
        token = what if what in PREDEFINED else "Clue"
        for each in create_predefined_tokens(game, token, ALICE, count):
            game.sacrifice(each)
    if re.search(r"counter was put on a permanent under your control this turn", lowered) or (
        "you put a counter on this creature this turn" in lowered
    ):
        game.add_counters(source, "+1/+1", 1)
    if "you put a counter on a creature this turn" in lowered:
        creature = _other_permanent(scenario, source, Type.CREATURE)
        if creature is not None:
            game.add_counters(creature, "+1/+1", 1, putter=ALICE)
    if "committed a crime this turn" in lowered:
        from magic_cards_model.machines.conditions.history import record_crime

        record_crime(game, ALICE, [TargetRef.to_player(BOB)])
    mana_value = re.search(r"cast a spell with mana value (\w+) or greater this turn", lowered)
    if mana_value is not None:
        # The history the sweep has no casting driver for, staged as last
        # turn's is: a real printing of that mana value, cast this turn.
        big = next(
            printing
            for printing in pool().values()
            if printing.cmc >= count_word(mana_value.group(1)) and not printing.is_land
        )
        game.spells_cast_this_turn.setdefault(ALICE, []).append(card_state(big.name, Zone.STACK))
    dealt = re.search(
        r"an opponent was dealt combat damage by an? (?P<quality>[a-z ]+?) this turn", lowered
    ) or re.search(
        r"(?P<color>white|blue|black|red|green) sources you controlled dealt (\w+) or more "
        r"noncombat damage this turn",
        lowered,
    )
    if dealt is not None:
        from magic_cards_model.models.card import Supertype
        from magic_cards_model.models.game import DamageDealt

        color = dealt.groupdict().get("color")
        game.damage_dealt_this_turn.append(
            DamageDealt(
                source_controller=ALICE,
                source_types=(Type.CREATURE,),
                source_supertypes=(Supertype.LEGENDARY,) if color is None else (),
                source_colors=(_COLOR_OF[color],) if color is not None else (),
                recipient_player=BOB,
                amount=count,
                combat=color is None,
            )
        )
    if "from anywhere other than your hand" in lowered:
        from magic_cards_model.machines.conditions.history import PLAYED_NOT_FROM_HAND

        game.record_turn_fact(PLAYED_NOT_FROM_HAND, ALICE)


#: `machines/conditions/player.py`'s own grammar, read here to stage a
#: player-state condition true on the stock board.
_HAND_CONDITION = re.compile(
    rf"(?P<who>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) cards? in "
    r"(?:(?:your|their) )?hand"
)
_LIBRARY_CONDITION = re.compile(
    rf"(?P<who>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) cards? in "
    r"(?:(?:your|their) )?library"
)
_LIFE_CONDITION = re.compile(
    rf"(?P<who>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) life(?! (?:more|less|fewer))"
)
_POISON_CONDITION = re.compile(
    rf"(?P<who>{_SUBJECT}) (?:has|have) (?P<quantity>{_QUANTITY}) poison counters?"
)


def _players_named(who: str) -> list[str]:
    """The seats a staged player-state condition is about: "you" is the
    controller, "each player" both, every other subject the opponent (the
    player whose upkeep it is, the defending player)."""
    if who == "you":
        return [ALICE]
    if who == "each player":
        return [ALICE, BOB]
    return [BOB]


def _hand_of_size(scenario: PlayedScenario, username: str, size: int) -> None:
    game = scenario.game
    hand = list(game.player(username).hand)
    if len(hand) > size:
        game.put_cards_into_library(hand[size:], to_bottom=True)
    elif len(hand) < size:
        game.draw_cards(username, size - len(hand))


def _library_of_size(scenario: PlayedScenario, username: str, test: Callable[[int], bool]) -> None:
    """A library grown (basic lands put on its bottom) or exiled
    from down to the nearest size a library-count condition allows - Battle
    of Wits' "200 or more cards in your library"."""
    game = scenario.game
    library = game.player(username).library
    size = len(library)
    if test(size):
        return
    wanted = min((n for n in range(301) if test(n)), key=lambda n: abs(n - size), default=None)
    if wanted is None:
        return
    if wanted < size:
        game.exile_cards(library[wanted:])
        return
    for _ in range(wanted - size):
        state = card_state("Forest", controller=username, owner=username)
        state.bind_to_game(game)
        library.append(state)
    game.player(username).note_library_changed()


def _player_state_threshold(scenario: PlayedScenario, condition: str | None) -> None:
    """A hand, life or poison condition (CR 402.1, 103.4, 122.1f) the stock
    board does not meet is made true on it, read off the condition's own
    words with the reader's own count grammar: a hand trimmed or drawn up to
    the nearest size it allows (a hand that already fits is left alone), a
    life total moved to the nearest one it allows, poison counters given,
    one more card or life than the player it is compared with. For an
    intervening "if" (CR 603.4) and an "Activate only if" (CR 602.5b)
    alike."""
    lowered = (condition or "").lower()
    if not lowered:
        return
    game = scenario.game
    for match in _HAND_CONDITION.finditer(lowered):
        test = _quantity_test(match.group("quantity"))
        if test is None:
            continue
        for username in _players_named(match.group("who")):
            held = len(game.player(username).hand)
            sizes = [n for n in range(12) if test(n)]
            if sizes:
                _hand_of_size(scenario, username, min(sizes, key=lambda n: (abs(n - held), n)))
    for match in _LIBRARY_CONDITION.finditer(lowered):
        test = _quantity_test(match.group("quantity"))
        if test is None:
            continue
        for username in _players_named(match.group("who")):
            _library_of_size(scenario, username, test)
    comparison = re.search(
        rf"(?P<who>{_SUBJECT}) (?:has|have) more cards in hand than "
        rf"(?P<other>{_SUBJECT}|each other player)",
        lowered,
    )
    if comparison is not None:
        ahead = ALICE if comparison.group("who") in ("you", "a player") else BOB
        behind = BOB if ahead == ALICE else ALICE
        _hand_of_size(scenario, ahead, len(game.player(behind).hand) + 1)
    for match in _LIFE_CONDITION.finditer(lowered):
        test = _quantity_test(match.group("quantity"))
        if test is None:
            continue
        for username in _players_named(match.group("who")):
            life = game.player(username).life
            wanted = min((n for n in range(1, 61) if test(n)), key=lambda n: abs(n - life))
            if wanted < life:
                game.lose_life(username, life - wanted)
            elif wanted > life:
                game.gain_life(username, wanted - life)
    below = re.search(
        r"life total is less than (?:(?P<number>\d+)|your starting life total)", lowered
    )
    if below is not None:
        player = game.player(ALICE)
        bar = int(below.group("number")) if below.group("number") else player.starting_life
        if player.life >= bar:
            game.lose_life(ALICE, player.life - bar + 1)
    above = re.search(r"at least (\d+) life more than your starting life total", lowered)
    if above is not None:
        player = game.player(ALICE)
        missing = player.starting_life + int(above.group(1)) - player.life
        if missing > 0:
            game.gain_life(ALICE, missing)
    if re.search(r"\byou own (?:a|one or more) cards? in exile\b", lowered):
        # CR 406.1: a card of the player's own library put into exile.
        library = game.player(ALICE).library
        if library and not any(card.owner == ALICE for card in game.exile):
            game.exile_cards([library[-1]])
    if re.search(r"you have (?:more life than an opponent|the most life)", lowered):
        game.lose_life(BOB, 1)
    if re.search(rf"(?:{_SUBJECT}) (?:is|are) poisoned", lowered):
        game.add_player_counters(BOB, "poison", 1)
    for match in _POISON_CONDITION.finditer(lowered):
        test = _quantity_test(match.group("quantity"))
        wanted = next((n for n in range(11) if test(n)), None) if test else None
        if wanted:
            for username in _players_named(match.group("who")):
                game.add_player_counters(username, "poison", wanted)


#: The party a "you have a full party" condition is staged with (CR 700.8c):
#: a pool Cleric, Rogue, Warrior and Wizard.
_PARTY = ("Infernal Vessel", "Blackbloom Rogue", "Squad Commander", "Eccentric Apprentice")
#: The source's own state a condition names, read off its words:
#: "if it's saddled", "if this creature is renowned", "... monstrous",
#: "... suspected" (CR 702.171b, 702.112b, 701.37b, 701.60b).
_SELF_DESIGNATION = re.compile(
    r"\b(?:it's|it is|this creature is|this permanent is) (?P<designation>saddled|renowned"
    r"|monstrous|suspected)\b",
    re.IGNORECASE,
)
#: "it has/had a +1/+1 counter on it", "there are N or more <kind> counters on
#: this <type>", "this creature has a +1/+1 counter on it" - counters on the
#: source itself (CR 122.1), put there as the board is staged.
_SELF_COUNTERS = re.compile(
    r"(?:\b(?:it|this \w+) (?:has|had) (?:(?P<count>a|an|one|two|three|four|five|\d+)"
    r"(?: or more)? )?(?:(?P<kind>\S+) )?counters? on it"
    r"|there (?:is|are) (?P<count2>\w+) or more (?P<kind2>\S+) counters? on this \w+)",
    re.IGNORECASE,
)
#: "this creature's power is N or greater", "its power was N or greater".
_SELF_POWER = re.compile(
    r"\b(?:this creature's|its) power (?:is|was) (?P<n>\d+) or greater", re.IGNORECASE
)


def _object_state_threshold(
    scenario: PlayedScenario, source: CardState, condition: str | None
) -> None:
    """An object-state or designation condition the stock board does not
    meet is made true on it, read off the condition's own words (never a
    card's name): the source's own designation, counters or power; the
    city's blessing (CR 702.131c); a full party (CR 700.8c); a completed
    dungeon (CR 309.7); first strike (a keyword counter, CR 122.1b). For an
    intervening "if" (CR 603.4) and an "Activate only if" (CR 602.5b)."""
    lowered = (condition or "").lower()
    if not lowered:
        return
    game = scenario.game
    if (designation := _SELF_DESIGNATION.search(lowered)) is not None and " not " not in lowered:
        setattr(source, designation.group("designation"), True)
    if (
        (counters := _SELF_COUNTERS.search(lowered)) is not None
        and "no " not in lowered
        and "n't" not in lowered
    ):
        # A bare "it had counters on it" names no kind: +1/+1, like "counters".
        kind = counters.group("kind") or counters.group("kind2") or "counters"
        raw = counters.group("count") or counters.group("count2") or "1"
        count = int(raw) if raw.isdigit() else parse_count(raw) or 1
        game.add_counters(source, "+1/+1" if kind == "counters" else kind, count)
    if (power := _SELF_POWER.search(lowered)) is not None:
        missing = int(power.group("n")) - (game.characteristics_of(source).power or 0)
        if missing > 0:
            game.add_counters(source, "+1/+1", missing)
    if "you have the city's blessing" in lowered:
        game.player(ALICE).has_citys_blessing = True
    if "you have a full party" in lowered:
        for name in _PARTY:
            state = card_state(name, Zone.BATTLEFIELD, controller=ALICE, owner=ALICE)
            state.bind_to_game(game)
            game.battlefield.append(state)
    if "it has first strike" in lowered and "n't" not in lowered:
        game.add_counters(source, "first strike", 1)
    if "you've completed a dungeon" in lowered:
        from magic_cards_model.machines.dungeon import dungeon_printings

        completed = card_state(
            dungeon_printings()[0].name, Zone.SIDEBOARD, controller=ALICE, owner=ALICE
        )
        completed.dungeon_completions = 1
        game.player(ALICE).sideboard.append(completed)


def _activation_step(ability: ActivatedAbility) -> Step:
    """The step an "Activate only during ..." instruction (CR 602.1b) allows
    the activation in: the named step ("during your upkeep", "during the end
    of combat step"), the beginning of combat for "during combat", the
    precombat main phase otherwise.

    CR 702.57b's own forecast timing - "only during the upkeep step of the
    card's owner" - is never printed as one of those instructions
    (`ActivatedAbility.forecast` is set off the keyword itself, not off
    `instructions`), so it is read here the same generic way, off the
    ability's own timing field rather than any one card's name."""
    if ability.forecast:
        return Step.UPKEEP
    for window in read_activation_instructions(ability.instructions).windows:
        lowered = window.lower()
        for name, step in sorted(_STEP_NAMES.items(), key=lambda item: -len(item[0])):
            if lowered.endswith(f"{name} step") or lowered.endswith(f"your {name}"):
                return step
        if lowered.endswith("combat"):
            return Step.BEGINNING_OF_COMBAT
    return Step.PRECOMBAT_MAIN


def _chosen_parity(source: CardState, condition: str | None) -> None:
    """A trigger reading "mana value of the chosen quality" off its own
    "As this enters, choose odd or even" (CR 614.12a) has an answer on the
    staged source, which skipped entering: odd, which the stock probes
    (Opt, Lightning Bolt) fit."""
    if source.choice is not None or not condition or "chosen quality" not in condition.lower():
        return
    if re.search(r"\bchoose odd or even\b", source.card.oracle_text or "", re.IGNORECASE):
        source.choice = Choice(kind=ChoiceKind.ODD_OR_EVEN, value="odd")


def _counter_threshold(scenario: PlayedScenario, source: CardState, condition: str | None) -> None:
    """An intervening "if this [permanent] has N or more [kind] counters on
    it" (CR 603.4) is met on the board the source is staged on: the counters
    are put on it, read off the condition's own words."""
    if not condition:
        return
    match = re.search(
        r"(?:this \w+|~) has (?P<count>[\w,]+) or more (?P<kind>\S+) counters on it",
        condition.lower(),
    )
    if match is None:
        return
    raw = match.group("count").replace(",", "")
    count = int(raw) if raw.isdigit() else parse_count(raw, article=False)
    if count:
        scenario.game.add_counters(source, match.group("kind"), count)


def _staged(scenario: PlayedScenario, name: str, username: str = ALICE) -> CardState:
    return _last(scenario, name, Zone.BATTLEFIELD, username)


def _source(scenario: PlayedScenario, case: Case, ability: Any) -> CardState:
    return _prime(scenario, _staged(scenario, case.card), ability)


def _functions_from_graveyard(card: Card, ability: TriggeredAbility) -> bool:
    zones = zones_ability_functions_in(ability, card_state(card.name))
    return Zone.BATTLEFIELD not in zones and Zone.GRAVEYARD in zones


def _home(case: Case, ability: TriggeredAbility, **extra: Any) -> tuple[PlayedScenario, Any]:
    """A board with the source where its ability functions (CR 113.6): the
    battlefield, or the graveyard for "return this card from your
    graveyard" abilities."""
    card = case.printing
    if _functions_from_graveyard(card, ability):
        scenario = _board(
            graveyard=(card.name, *extra.pop("graveyard", ())),
            before=lambda played: _history_threshold(
                played, _last(played, card.name, Zone.GRAVEYARD, ALICE), ability.intervening_if
            ),
            **extra,
        )
        return scenario, _last(scenario, card.name, Zone.GRAVEYARD, ALICE).id
    battlefield = (
        card.name,
        *extra.pop("battlefield", ()),
        *_named_partners(ability),
        *_equipment_partner(ability),
    )
    staged: list[CardState] = []
    scenario = _board(
        battlefield=battlefield,
        before=lambda played: staged.append(_source(played, case, ability)),
        **extra,
    )
    _stack_material(scenario)
    return scenario, staged[0].id


#: An intervening "if he's equipped" / "if this creature is equipped" (CR
#: 603.4, CR 301.5a - Whiplash, Vengeful Engineer; Avacynian Missionaries):
#: the source is staged with a real Equipment attached to it.
_EQUIPPED_SELF_CONDITION = re.compile(
    r"\b(?:it's|he's|she's|this (?:creature|permanent) is) (?:enchanted or )?equipped\b",
    re.IGNORECASE,
)
_STAGED_EQUIPMENT = "Bonesplitter"


def _equipment_partner(ability: Any) -> tuple[str, ...]:
    """The Equipment a board stages beside a source whose intervening "if"
    asks that it be equipped."""
    if _EQUIPPED_SELF_CONDITION.search(getattr(ability, "intervening_if", None) or ""):
        return (_STAGED_EQUIPMENT,)
    return ()


#: An intervening "if a(n) `<type>` entered the battlefield under your
#: control this turn" (Iron Man, Master of Machines; Avengers Assemble!'s
#: "or a Hero entered ...", CR 603.4): a real permanent of that type or
#: subtype is put onto the battlefield as the board is staged, so the turn's
#: own record of it is there when the trigger checks.
_TYPED_ENTERED_CONDITION = re.compile(
    r"\ban? (?P<quality>[A-Za-z]+) entered the battlefield under your control this turn\b",
    re.IGNORECASE,
)


def _enter_for_condition(scenario: PlayedScenario, ability: Any) -> None:
    """Put a pool permanent matching a typed "entered this turn" condition
    onto the battlefield under the source's controller."""
    match = _TYPED_ENTERED_CONDITION.search(getattr(ability, "intervening_if", None) or "")
    if match is None:
        return
    quality = match.group("quality").lower()
    wanted_type = next((kind for kind in Type if kind.value == quality), None)
    for printing in _format_pool():
        if printing.card_faces or not set(printing.types) & _PERMANENT_TYPES:
            continue
        if wanted_type is not None:
            if wanted_type not in printing.types:
                continue
        elif quality.removesuffix("s") not in {sub.lower() for sub in printing.subtypes}:
            continue
        if "enters" in (printing.oracle_text or "").lower():
            continue  # no entering trigger of its own to crowd the stack
        state = card_state(printing.name)
        scenario.game.player(ALICE).add(state, Zone.HAND)
        try:
            scenario.game.put_onto_battlefield(state, ALICE)
        except ValueError:
            continue
        return


def _equip_for_condition(scenario: PlayedScenario, source: CardState, ability: Any) -> None:
    """Attach the staged Equipment to the source (CR 301.5a)."""
    if not _equipment_partner(ability):
        return
    for permanent in scenario.game.permanents_controlled_by(ALICE):
        if permanent.name == _STAGED_EQUIPMENT and permanent.attached_to is None:
            permanent.attachment = TargetRef.to_card(source)
            return


def _named_partners(ability: TriggeredAbility) -> tuple[str, ...]:
    """A card a condition names outright ("a creature named Midnight
    Scavengers", CR 201.2), read off the text, so it is on the board too."""
    text = f"{ability.condition} {ability.intervening_if or ''}"
    found = re.findall(r"named ([A-Z][\w' -]*?)(?=[,.]|$)", text)
    return tuple(name for name in found if name in pool())


def _plural_subtypes(condition: str) -> list[str]:
    found = []
    for word in re.findall(r"\b([A-Z][a-z]+s)\b", condition):
        singular = _singular_subtype(word)
        if singular is not None:
            found.append(singular)
    return found


def _probes(case: Case, ability: TriggeredAbility, *, entering: bool) -> list[str]:
    """Real printings to stand in for the "other" object a condition names:
    the engine's own probe finder (`support._probe_cards`, the one
    `card_support` proves reachability with), a creature of a plural subtype
    the condition names ("one or more Allies"), then the stock probe
    creatures."""
    found = _probe_cards(case.printing, ability.condition, entering=entering) or []
    names = [card.name for card in found if card.name in pool()]
    if "noncreature" in ability.condition.lower():
        # "one or more noncreature permanents": the stock noncreature ones.
        names += [name for name in _PROBE_NONCREATURES if name not in names]
    for subtype in _plural_subtypes(ability.condition):
        for card in _format_pool():
            lowered = {s.lower() for s in card.subtypes}
            if subtype.lower() in lowered and _is(card, Type.CREATURE) and not card.card_faces:
                names.append(card.name)
                break
    for name in _PROBE_CREATURES:
        if name not in names:
            names.append(name)
    # A subtype the condition names in a form with no plural "s" ("one or
    # more nontoken Merfolk you control", CR 205.3m) - tried last, so every
    # case the probes above already drive keeps the probe it had.
    for word in re.findall(r"\b([A-Z][a-z]+)\b", ability.condition):
        subtype = _singular_subtype(word)
        if subtype is None:
            continue
        for card in _format_pool():
            lowered = {s.lower() for s in card.subtypes}
            if (
                subtype.lower() in lowered
                and _is(card, Type.CREATURE)
                and not card.card_faces
                and card.name not in names
            ):
                names.append(card.name)
                break
    return names


# ---------------------------------------------------------------------------
# Raising a trigger event. An attempt builds its own fresh board, performs
# one real action and returns `(scenario, source_id)` - `source_id` pins the
# source when a twin of the card may be on the board, otherwise `None`.
# ---------------------------------------------------------------------------


_BASIC_OF = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}


def _extra_lands_for(card: Card) -> tuple[str, ...]:
    """Basics beyond the stock board's three of each, so a spell with more
    coloured pips than that (Doomsday Excruciator's six {B}) can be cast
    for its mana cost (CR 601.2g-h)."""
    pips = re.findall(r"\{([WUBRG])\}", card.mana_cost or "")
    stock = _LANDS.count("Plains")
    return tuple(
        basic
        for colour, basic in _BASIC_OF.items()
        for _ in range(max(0, pips.count(colour) - stock))
    )


def _self_entering(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    card = case.printing
    lowered = (ability.condition + " " + (ability.intervening_if or "")).lower()
    tapped_choices = [False, True] if "tapped" in lowered else [False]
    transformed = _back_face(card, ability)

    for tapped in tapped_choices:

        def put(tapped: bool = tapped) -> tuple[PlayedScenario, Any]:
            scenario = _board(hand=(card.name,))
            _stack_material(scenario)
            _board_threshold(scenario, None, ability.intervening_if or "")
            _player_state_threshold(scenario, ability.intervening_if)
            source = _last(scenario, card.name, Zone.HAND, ALICE)
            try:
                entered = scenario.game.put_onto_battlefield(
                    source, ALICE, tapped=tapped, transformed=transformed
                )
            except ValueError as error:
                raise _Unavailable(str(error)) from error
            _prime(scenario, entered, ability)
            return scenario, None

        yield put

    if "from your graveyard" in lowered:
        # "if it entered from your graveyard" (CR 603.4, CR 603.6a): the card
        # is put onto the battlefield from its owner's graveyard.

        def from_graveyard() -> tuple[PlayedScenario, Any]:
            scenario = _board(graveyard=(card.name,))
            source = _last(scenario, card.name, Zone.GRAVEYARD, ALICE)
            try:
                entered = scenario.game.put_onto_battlefield(source, ALICE, transformed=transformed)
            except ValueError as error:
                raise _Unavailable(str(error)) from error
            _prime(scenario, entered, ability)
            return scenario, None

        yield from_graveyard

    if card.is_land:

        def play() -> tuple[PlayedScenario, Any]:
            scenario = _board(hand=(card.name,))
            try:
                scenario.play_land(card.name, ALICE)
            except ValueError as error:
                raise _Unavailable(str(error)) from error
            return scenario, None

        yield play
        return

    kicker = any(k.canonical.lower() in ("kicker", "multikicker") for k in keyword_abilities(card))
    payers: list[str | None] = [None, *(_BASICS if "spent" in lowered else [])]
    for kicked in [False, True] if kicker else [False]:
        for paying_with in payers:

            def cast(kicked: bool = kicked, paying_with: str | None = paying_with):
                scenario = _board(hand=(card.name,), battlefield=_extra_lands_for(card))
                _stack_material(scenario)
                _board_threshold(scenario, None, ability.intervening_if or "")
                _player_state_threshold(scenario, ability.intervening_if)
                _cast(scenario, card.name, kicked=kicked, paying_with=paying_with)
                return scenario, None

            yield cast

    yield from _paid_cost_casts(case, ability)

    if "{X}" in (card.mana_cost or "") and re.search(r"\bX\b", ability.effect or ""):
        # CR 107.3m: an enters ability that refers to X reads the X its spell
        # was cast with - The Ruinous Wrecking Crew's "choose up to X" has no
        # mode to choose at the X = 0 the attempts above cast it for.

        def cast_with_x() -> tuple[PlayedScenario, Any]:
            scenario = _board(hand=(card.name,), battlefield=_extra_lands_for(card))
            _stack_material(scenario)
            _cast(scenario, card.name, x_value=1)
            return scenario, None

        yield cast_with_x

    nth = re.search(r"\bit was the (\w+) spell you cast this turn\b", lowered)
    if nth is not None:
        # "if it was the second spell you cast this turn" (Codespell Cleric):
        # that many spells before it are cast first (CR 601.2i), on a board
        # with no other turn played.
        before = (parse_ordinal(nth.group(1)) or 1) - 1

        def cast_after_others() -> tuple[PlayedScenario, Any]:
            scenario = _board(
                hand=(card.name, *(["Opt"] * before)),
                battlefield=_extra_lands_for(card),
                busy=False,
            )
            game = scenario.game
            for _ in range(before):
                _cast(scenario, "Opt")
                while game.stack:
                    game.resolve_top()
            _stack_material(scenario)
            _cast(scenario, card.name)
            return scenario, None

        yield cast_after_others

    if "mana from a treasure" in lowered:
        # "if mana from a Treasure was spent to cast it" (CR 106.3): a
        # Treasure's mana floats first, and the pool pays before the lands.

        def cast_with_treasure() -> tuple[PlayedScenario, Any]:
            scenario = _board(hand=(card.name,), battlefield=_extra_lands_for(card))
            _stack_material(scenario)
            _treasure_mana_for(scenario, card.name, ALICE)
            _cast(scenario, card.name)
            return scenario, None

        yield cast_with_treasure


# ---------------------------------------------------------------------------
# Paid-cost conditions (`machines/conditions/cast_record.py`): "if its surge
# cost was paid", "if it was bargained", "if evidence was collected" - the
# source is cast every way its own printed alternative and optional costs let
# it be (the engine's `keyword_cast_options`/`optional_additional_costs`),
# each staged by what the engine's own option says it needs.
# ---------------------------------------------------------------------------

#: The optional additional costs a paid-cost cast announces here, by the
#: engine's own keyword for each (`OptionalAdditionalCost.keyword`).
_PAID_OPTIONAL_COSTS = ("bargain", "collect evidence", "reveal")


def _claims_cast_record(condition: str) -> bool:
    text = _clause(condition)
    return any(reader.pattern.fullmatch(text) for reader in cast_record_conditions.READERS)


@cache
def _type_sharer(card_name: str) -> str | None:
    """A nonlegendary pool creature sharing a creature type with the card -
    the creature whose combat damage enables prowl (CR 702.76a)."""
    subtypes = {subtype.lower() for subtype in pool()[card_name].subtypes}
    return next(
        (
            name
            for name in _board_candidates()
            if name != card_name
            and _is(pool()[name], Type.CREATURE)
            and subtypes & {subtype.lower() for subtype in pool()[name].subtypes}
        ),
        None,
    )


@cache
def _revealable(phrase: str) -> tuple[str, ...]:
    """Pool cards of a subtype a "reveal a <Subtype> card" phrase names - read
    the way `_probes` reads a subtype named in a condition."""
    names: list[str] = []
    for word in re.findall(r"\b([A-Z][a-z]+)\b", phrase):
        subtype = _singular_subtype(word) or word
        names += [
            name
            for name in _board_candidates()
            if subtype.lower() in {s.lower() for s in pool()[name].subtypes}
        ][:2]
    return tuple(names)


def _deal_combat_damage_with(scenario: PlayedScenario, name: str) -> None:
    """`name` attacks the opponent unblocked and deals its combat damage (CR
    510.1), then the turn moves on to the postcombat main phase."""
    attacker = _first(scenario, name, ALICE)
    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    scenario.game.sync_priority_with_step()
    try:
        scenario.attack_with(attacker, defending=BOB)
        _settle(scenario)
        while scenario.game.stack:
            scenario.game.resolve_top()
        scenario.no_blocks()
        scenario.combat_damage()
    except (ValueError, AssertionError) as error:
        raise _Unavailable(f"combat: {error}") from error
    _settle(scenario)
    while scenario.game.stack:
        scenario.game.resolve_top()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.game.sync_priority_with_step()


def _paid_cost_casts(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    if not _claims_cast_record(ability.intervening_if or ""):
        return
    card = case.printing
    lands = _extra_lands_for(card)

    for option in keyword_cast_options(card):
        keyword = option.keyword

        def alternative(option: Any = option, keyword: str = keyword):
            sharer = _type_sharer(card.name) if option.prowl else None
            battlefield = (*lands, *((sharer,) if sharer else ()))
            step = Step.DECLARE_ATTACKERS if option.returns_unblocked_creature else None
            scenario = _board(
                hand=(card.name,),
                battlefield=battlefield,
                **({"step": step} if step else {}),
            )
            game = scenario.game
            if option.surge or option.spectacle:
                # CR 702.117a: another spell cast this turn; CR 702.137a: an
                # opponent lost life this turn - one Lightning Bolt does both.
                _cast(scenario, "Lightning Bolt", prefer=BOB)
                while game.stack:
                    game.resolve_top()
            if option.prowl:
                if sharer is None:
                    raise _Unavailable("no creature shares a type with it for prowl")
                _deal_combat_damage_with(scenario, sharer)
            choosing = None
            if option.returns_tapped_creature:
                # CR 702.188a: a tapped creature returned to its owner's hand.
                creature = _first(scenario, "Memnite", ALICE)
                game.tap_permanent(creature)
                choosing = [creature]
            if option.returns_unblocked_creature:
                # CR 702.190a: an unblocked attacker returned to its owner's hand.
                attacker = _first(scenario, "Memnite", ALICE)
                try:
                    scenario.attack_with(attacker, defending=BOB)
                    scenario.turn.advance_to(Step.DECLARE_BLOCKERS)
                    game.sync_priority_with_step()
                    scenario.no_blocks()
                    game.cast(
                        _last(scenario, card.name, Zone.HAND, ALICE),
                        ALICE,
                        keyword=keyword,
                        choosing=[attacker],
                        mana_sources=game.permanents_controlled_by(ALICE),
                    )
                except (ValueError, AssertionError) as error:
                    raise _Unavailable(f"{keyword}: {error}") from error
                return scenario, None
            zone = Zone.HAND
            if option.zone is Zone.EXILE:
                # CR 702.35a: madness exiles the card as it is discarded.
                spell = _last(scenario, card.name, Zone.HAND, ALICE)
                game.discard_cards(ALICE, [spell])
                zone = spell.zone
            _cast(
                scenario,
                card.name,
                keyword=keyword,
                from_zone=zone,
                announce=(lambda casting: casting.use_keyword(keyword, choosing=choosing))
                if choosing
                else None,
            )
            return scenario, None

        yield alternative

    for option in optional_additional_costs(card):
        if option.keyword not in _PAID_OPTIONAL_COSTS:
            continue

        def optional(option: Any = option) -> tuple[PlayedScenario, Any]:
            revealed = _revealable(option.cost) if option.keyword == "reveal" else ()
            scenario = _board(hand=(card.name, *revealed), battlefield=lands)
            game = scenario.game

            def announce(casting: Any) -> None:
                if option.keyword == "collect evidence":
                    casting.collect_evidence()
                    return
                if option.keyword == "bargain":
                    candidates = [
                        p for p in game.permanents_controlled_by(ALICE) if not p.card.is_land
                    ]
                    pay = casting.pay_bargain
                else:
                    candidates = [c for c in game.player(ALICE).hand if not _named(c, card.name)]
                    pay = casting.reveal_for_cost
                for candidate in candidates:
                    # The engine judges each: the first it accepts is paid.
                    with contextlib.suppress(ValueError):
                        pay(candidate)
                        return
                raise ValueError(f"nothing on the board pays {option.keyword}")

            _cast(scenario, card.name, announce=announce)
            return scenario, None

        yield optional

    def declined() -> tuple[PlayedScenario, Any]:
        # A cost an opponent chooses whether to pay as the source enters -
        # CR 702.104a's tribute - declined, for "if tribute wasn't paid" (CR
        # 702.104b): the opponent answers no to every "may".
        scenario = _board(hand=(card.name,))
        scenario.will_take_the_may(False, username=BOB, times=None)
        try:
            scenario.game.put_onto_battlefield(_last(scenario, card.name, Zone.HAND, ALICE), ALICE)
        except ValueError as error:
            raise _Unavailable(str(error)) from error
        return scenario, None

    yield declined


def _other_entering(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    lowered = ability.condition.lower()
    tapped_choices = [False, True] if "tapped" in lowered else [False]
    owners = [ALICE, BOB] if "opponent" in lowered or "a player" in lowered else [ALICE]
    if "from your graveyard" in (ability.intervening_if or "").lower():
        # "if it entered from your graveyard" (CR 603.4): the other object
        # enters from the controller's graveyard.
        for probe in _probes(case, ability, entering=True):

            def exhume(probe: str = probe) -> tuple[PlayedScenario, Any]:
                scenario, source_id = _home(case, ability, graveyard=(probe,))
                entering = _last(scenario, probe, Zone.GRAVEYARD, ALICE)
                if entering.id == source_id:
                    raise _Unavailable(f"{probe} is the source itself")
                try:
                    scenario.game.put_onto_battlefield(entering, ALICE)
                except ValueError as error:
                    raise _Unavailable(str(error)) from error
                return scenario, source_id

            yield exhume
    for probe in _probes(case, ability, entering=True):
        for owner in owners:
            for tapped in tapped_choices:

                def put(probe: str = probe, owner: str = owner, tapped: bool = tapped):
                    extra = {"hand": (probe,)} if owner == ALICE else {"bob_hand": (probe,)}
                    scenario, source_id = _home(case, ability, **extra)
                    entering = _last(scenario, probe, Zone.HAND, owner)
                    try:
                        scenario.game.put_onto_battlefield(entering, owner, tapped=tapped)
                    except ValueError as error:
                        raise _Unavailable(str(error)) from error
                    return scenario, source_id

                yield put

        if "token" in lowered:

            def token(probe: str = probe) -> tuple[PlayedScenario, Any]:
                scenario, source_id = _home(case, ability, battlefield=(probe,))
                token_copy_of(scenario.game, _staged(scenario, probe), ALICE)
                return scenario, source_id

            yield token


#: How each "leaves the battlefield" event is caused, in the engine's own
#: words: the method that performs the move is the one that emits the event.
_REMOVALS: dict[str, tuple[str, ...]] = {
    TriggerEvent.DIES.value: ("destroy", "sacrifice"),
    TriggerEvent.IS_SACRIFICED.value: ("sacrifice",),
    TriggerEvent.LEAVES_THE_BATTLEFIELD.value: ("exile_permanent", "destroy", "return_to_hand"),
    TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE.value: ("exile_permanent",),
    TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND.value: ("return_to_hand",),
}

_PREDEFINED_TOKEN_WORDS = ("food", "treasure", "clue", "powerstone")


def _leaving(case: Case, ability: TriggeredAbility, kind: str) -> Iterator[Attempt]:
    lowered = ability.condition.lower()
    removals = _REMOVALS[kind]

    for removal in removals:

        def itself(removal: str = removal) -> tuple[PlayedScenario, Any]:
            scenario = _board(battlefield=(case.card,))
            _stack_material(scenario)
            source = _source(scenario, case, ability)
            getattr(scenario.game, removal)(source)
            return scenario, None

        yield itself

    for word in _PREDEFINED_TOKEN_WORDS:
        if word in lowered:

            def predefined(word: str = word) -> tuple[PlayedScenario, Any]:
                scenario, source_id = _home(case, ability)
                (token,) = create_predefined_tokens(scenario.game, word.capitalize(), ALICE)
                getattr(scenario.game, removals[-1])(token)
                return scenario, source_id

            yield predefined

    owners = [ALICE, BOB] if "opponent" in lowered or "a creature dies" in lowered else [ALICE]
    for probe in _probes(case, ability, entering=False):
        for owner in owners:
            for removal in removals:
                for as_token in [False, True] if "token" in lowered else [False]:

                    def other(
                        probe: str = probe,
                        owner: str = owner,
                        removal: str = removal,
                        as_token: bool = as_token,
                    ) -> tuple[PlayedScenario, Any]:
                        extra = (
                            {"battlefield": (probe,)}
                            if owner == ALICE
                            else {"bob_battlefield": (probe,)}
                        )
                        scenario, source_id = _home(case, ability, **extra)
                        victim = _staged(scenario, probe, owner)
                        if as_token:
                            (victim,) = token_copy_of(scenario.game, victim, owner)
                        source = scenario.game.find_by_id(source_id)
                        if re.search(r"\b(enchanted|equipped)\b", lowered):
                            source.attachment = TargetRef.to_card(victim)
                        if "dealt damage by" in lowered:
                            scenario.game.deal_damage(victim, 1, source=source)
                        getattr(scenario.game, removal)(victim)
                        return scenario, source_id

                    yield other


def _combat_sides(ability: TriggeredAbility) -> list[str]:
    """Which side attacks for this condition: the source's controller, or
    its opponent ("attacks you", "blocks")."""
    lowered = ability.condition.lower()
    if re.search(r"attacks you\b", lowered):
        return [BOB]
    if "blocks" in lowered or "opponent" in lowered or "a creature attacks" in lowered:
        return [ALICE, BOB]
    return [ALICE]


def _crew(scenario: PlayedScenario, vehicle: CardState, only: tuple[str, ...] = ()) -> None:
    """Crew a Vehicle (CR 702.122a) with the controller's other creatures -
    only the ones named in `only`, when it names any."""
    controller = vehicle.controller
    crew = [
        p
        for p in scenario.game.permanents_controlled_by(controller)
        if Type.CREATURE in p.types
        and p is not vehicle
        and not p.tapped
        and (not only or p.name in only)
    ]
    try:
        activation = crew_activation(scenario.game, vehicle, crew, controller)
        activation.begin_paying()
        activation.payment.pay()
        activation.activate()
        activation.resolve()
    except (ValueError, AssertionError) as error:
        raise _Unavailable(f"crewing: {error}") from error


#: A real Equipment (CR 301.5) to stage on an "equipped creature" attacker.
_EQUIPMENT = "Bonesplitter"


def _is_equipment(card: Card) -> bool:
    return "Equipment" in card.subtypes


def _combat(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    card = case.printing
    lowered = ability.condition.lower()
    is_vehicle = crew_number(card) is not None
    # Pack tactics' "if you attacked with creatures with total power N or
    # greater this combat" (CR 207.2c): a 6-power partner attacks as well.
    # "another target attacking creature" (Eddytrail Hawk, Smelted Chargebug)
    # has no legal target unless a second creature attacks too (CR 603.3d),
    # so a vanilla partner attacks alongside.
    partners: tuple[str, ...] = (
        ("Craw Wurm",)
        if re.search(r"attacked with creatures with total power", ability.intervening_if or "")
        else ("Grizzly Bears",)
        if re.search(r"\banother target attacking creature\b", ability.effect or "", re.I)
        else ()
    )
    # "if you attacked with exactly N other creatures this combat" (Creepy
    # Puppeteer): N vanilla partners attack alongside the source.
    exactly = re.search(
        r"\battacked with exactly (\w+) other creatures?\b", (ability.intervening_if or "").lower()
    )
    if exactly is not None and not partners:
        partners = ("Grizzly Bears",) * (parse_count(exactly.group(1), article=False) or 1)
    # "if a Pirate and a Vehicle attacked this combat" (Fearless
    # Swashbuckler): each kind the source is not attacks alongside it - a
    # crewed Vehicle (CR 702.122a), or the simplest creature of that subtype.
    crewers: tuple[str, ...] = ()
    composition = re.search(
        r"\ban? (\w+) and an? (\w+) attacked this combat\b", (ability.intervening_if or "").lower()
    )
    if composition is not None and not partners:
        wanted: list[str] = []
        for word in composition.groups():
            if word.lower() in {subtype.lower() for subtype in card.subtypes}:
                continue
            if word == "vehicle":
                wanted.append(_VEHICLE)
                crewers = (_VEHICLE_CREW,)
                continue
            kin = _simplest_creature_of(word)
            if kin is None:
                break
            wanted.append(kin)
        else:
            partners = tuple(wanted)
    # "if an Assassin crewed it this turn" (Adrestia, CR 702.122c): the
    # Vehicle is crewed by the simplest creature of that subtype alone.
    crewed_by = re.search(
        r"\ban? (\w+) crewed (?:it|this vehicle) this turn\b",
        (ability.intervening_if or "").lower(),
    )
    crew_kin = _simplest_creature_of(crewed_by.group(1)) if crewed_by is not None else None
    # "Whenever an equipped creature you control attacks" on a non-Equipment
    # source (Swordsman, Sharp Scoundrel, CR 301.5a): a real Equipment is
    # staged and attached to the attacker.
    equipment: tuple[str, ...] = (
        (_EQUIPMENT,) if "an equipped creature" in lowered and not _is_equipment(card) else ()
    )
    # A transforming card whose ability is printed on a creature back face
    # (Hidetsugu Consumes All's Vessel of the All-Consuming) fights as that
    # face: `_source` stages it transformed (CR 712.8e).
    back_creature = _back_face(card, ability) and "Creature" in (
        (card.card_faces or [])[1].type_line or ""
    )
    for side in _combat_sides(ability):
        attackers: list[str | None] = []
        if side == ALICE and (_is(card, Type.CREATURE) or is_vehicle or back_creature):
            attackers.append(None)
        if not is_vehicle:
            attackers += [p for p in _probes(case, ability, entering=False) if p != card.name]
        for probe in attackers:

            def fight(probe: str | None = probe, side: str = side) -> tuple[Any, ...]:
                extra: tuple[str, ...] = (probe,) if probe is not None else ()
                if is_vehicle:
                    extra = (crew_kin or "Serra Angel",)
                if side == ALICE:
                    scenario = _board(
                        battlefield=(
                            case.card,
                            *extra,
                            *partners,
                            *crewers,
                            *equipment,
                            *_equipment_partner(ability),
                        ),
                        step=Step.DECLARE_ATTACKERS,
                    )
                else:
                    scenario = _board(
                        battlefield=(case.card,),
                        bob_battlefield=extra,
                        active=BOB,
                        step=Step.DECLARE_ATTACKERS,
                    )
                source = _source(scenario, case, ability)
                if is_vehicle and side == ALICE:
                    _crew(scenario, source, (crew_kin,) if crew_kin else ())
                attacker = source if probe is None else _staged(scenario, probe, side)
                if attacker is not source and "equipped" in lowered:
                    holder = _staged(scenario, _EQUIPMENT, ALICE) if equipment else source
                    holder.attachment = TargetRef.to_card(attacker)
                defender = BOB if side == ALICE else ALICE
                alongside = (
                    [_staged(scenario, partner, side) for partner in partners]
                    if side == ALICE
                    else []
                )
                for partner in alongside:
                    if crew_number(partner.card) is not None:
                        _crew(scenario, partner, crewers)
                try:
                    scenario.attack_with(attacker, *alongside, defending=defender)
                except (ValueError, AssertionError) as error:
                    raise _Unavailable(str(error)) from error
                return scenario, source, attacker, defender

            yield _combat_stages(case, fight, lowered)

    if re.search(
        r"\bthat creature entered (?:the battlefield )?this turn\b",
        (ability.intervening_if or "").lower(),
    ):
        # "Whenever a creature you control deals combat damage to a player, if
        # that creature entered this turn" (Samut, Vizier of Naktamun): a
        # hasty creature enters this turn, then attacks (CR 702.10b).

        def fresh_attacker() -> tuple[Any, ...]:
            scenario = _board(battlefield=(case.card,), hand=(_HASTY,), step=Step.DECLARE_ATTACKERS)
            source = _source(scenario, case, ability)
            try:
                fresh = scenario.game.put_onto_battlefield(
                    _last(scenario, _HASTY, Zone.HAND, ALICE), ALICE
                )
                scenario.attack_with(fresh, defending=BOB)
            except (ValueError, AssertionError) as error:
                raise _Unavailable(str(error)) from error
            return scenario, source, fresh, BOB

        yield _combat_stages(case, fresh_attacker, lowered)


#: A Vehicle with nothing but crew (CR 702.122a), and a creature that crews
#: it alone, for "a Vehicle attacked this combat".
_VEHICLE = "Consulate Dreadnought"
_VEHICLE_CREW = "Craw Wurm"
#: A vanilla creature with haste (CR 702.10b), for an attacker that entered
#: this turn.
_HASTY = "Raging Goblin"


def _simplest_creature_of(subtype_word: str) -> str | None:
    """The shortest-texted single-faced creature in the pool with this
    subtype, or None."""
    subtype = singular_subtype(subtype_word.capitalize()) or subtype_word.capitalize()
    candidates = sorted(
        (
            card
            for card in _format_pool()
            if Type.CREATURE in card.types
            and subtype.lower() in {word.lower() for word in card.subtypes}
            and not card.card_faces
        ),
        key=lambda card: (len(card.oracle_text or ""), card.name),
    )
    return candidates[0].name if candidates else None


def _combat_stages(case: Case, fight: Callable[[], tuple[Any, ...]], lowered: str) -> Attempt:
    """Declare the attack, then block (with the source when it is on the
    defending side, CR 509.1), then deal combat damage (CR 510) - checking
    for the ability after each."""

    def combat() -> tuple[PlayedScenario, Any]:
        scenario, source, attacker, defender = fight()
        if _drive(scenario, case, source.id) is not None:
            return scenario, source.id
        game = scenario.game
        blocker = None
        if "block" in lowered:
            if source is not attacker and source.controller == defender:
                if crew_number(source.card) is not None:
                    _crew(scenario, source)
                blocker = source
            else:
                blocker = next(
                    (
                        p
                        for p in game.permanents_controlled_by(defender)
                        if Type.CREATURE in p.types and not p.tapped
                    ),
                    None,
                )
        try:
            if blocker is not None:
                scenario.block(attacker, blocker)
            else:
                scenario.no_blocks()
        except (ValueError, AssertionError) as error:
            raise _Unavailable(str(error)) from error
        if _drive(scenario, case, source.id) is not None:
            return scenario, source.id
        scenario.combat_damage()
        return scenario, source.id

    return combat


def _turns(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Play whole turns - the source's controller's, then the opponent's,
    then the controller's again - with the source already in play: every
    "at the beginning of" step, every draw step, every untap step and every
    lore counter a Saga gets (CR 714.3c) happens on its own along the way."""
    card = case.printing

    def staged() -> tuple[PlayedScenario, Any]:
        step = Step.PRECOMBAT_MAIN if _STAGING.variant == BUSY else None
        scenario, source_id = _home(case, ability, step=step)
        source = scenario.game.find_by_id(source_id)
        if _STAGING.variant == BUSY:
            source.tapped = True
        for permanent in scenario.game.permanents_controlled_by(ALICE):
            if permanent.card.is_land:
                permanent.tapped = True  # something for the untap step to untap
                break
        return scenario, source_id

    yield staged

    if re.search(r"\battack|\bcombat damage\b", (ability.intervening_if or "").lower()):
        # "if this creature attacked this turn", "if Kytheon and at least two
        # other creatures attacked this combat", "if a player was dealt 6 or
        # more combat damage this turn": a combat is fought first - every
        # creature the controller can attack with attacks, unblocked, and
        # deals its damage (CR 508.1, CR 510) - then the turn plays on into
        # the end of combat and end steps.

        def fought() -> tuple[PlayedScenario, Any]:
            scenario, source_id = _home(case, ability, step=Step.PRECOMBAT_MAIN, busy=False)
            game = scenario.game
            source = game.find_by_id(source_id)
            if (
                source is not None
                and source.zone is Zone.BATTLEFIELD
                and crew_number(source.card) is not None
            ):
                # "if this Vehicle attacked or blocked this combat" (Daredevil
                # Dragster): a Vehicle attacks only once crewed (CR 702.122a).
                _crew(scenario, source)
            scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
            game.sync_priority_with_step()
            attackers = [
                permanent
                for permanent in game.permanents_controlled_by(ALICE)
                if game.characteristics_of(permanent).is_creature and scenario.can_attack(permanent)
            ]
            if not attackers:
                raise _Unavailable("nothing can attack")
            # Staged deep enough to survive the whole board attacking, so the
            # game goes on to the steps the ability waits for.
            game.player(BOB).life = 1000
            try:
                scenario.attack_with(*attackers)
                _settle(scenario)
                while game.stack:
                    game.resolve_top()
                scenario.no_blocks()
                scenario.combat_damage()
            except (ValueError, AssertionError) as error:
                raise _Unavailable(str(error)) from error
            return scenario, source_id

        yield fought

    if set(card.types) & _PERMANENT_TYPES:

        def entered() -> tuple[PlayedScenario, Any]:
            scenario = _board(hand=(card.name,))
            state = _last(scenario, card.name, Zone.HAND, ALICE)
            try:
                entered_state = scenario.game.put_onto_battlefield(
                    state, ALICE, transformed=_back_face(card, ability)
                )
            except ValueError as error:
                raise _Unavailable(str(error)) from error
            _prime(scenario, entered_state, ability)
            return scenario, None

        yield entered


def _casting(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    lowered = ability.condition.lower()
    if "this spell" in lowered:
        yield from _self_entering(case, ability)
        return

    if "from exile" in lowered or "other than your hand" in lowered:
        # Cast from exile - an Adventurer's creature half after its
        # Adventure (CR 715.4) - for "from exile" and "from anywhere other
        # than your hand".

        def adventure() -> tuple[PlayedScenario, Any]:
            scenario, source_id = _home(case, ability, hand=(_ADVENTURER,))
            casting = scenario.cast(_ADVENTURER, ALICE)
            casting.cast_as_adventure()
            casting.choose_targets([BOB])
            payment = casting.begin_paying()
            payment.auto_tap(scenario.game.permanents_controlled_by(ALICE))
            payment.pay()
            scenario.put_on_stack(casting)
            scenario.game.resolve_top()
            _cast(scenario, _ADVENTURER, from_zone=Zone.EXILE)
            return scenario, source_id

        yield adventure

    if _required_cast_origin_zone(lowered) is Zone.GRAVEYARD:
        # "Whenever you cast a <quality> spell from your graveyard" (Rivaz of
        # the Claw, Secrets of the Dead): a probe card that fits the named
        # quality is put in the graveyard and handed CR 601.3's permission
        # to be cast from there by the engine's own `grant_play_permission`,
        # then cast - the cast itself is the event.
        probes = [
            name
            for name in [*_probes(case, ability, entering=False), *_PROBE_SPELLS]
            if name in pool() and not pool()[name].is_land and not pool()[name].card_faces
        ]
        for probe in dict.fromkeys(probes):

            def graveyard_probe(probe: str = probe):
                scenario, source_id = _home(case, ability, graveyard=(probe,))
                spell = _last(scenario, probe, Zone.GRAVEYARD, ALICE)
                scenario.game.grant_play_permission(
                    spell, ALICE, zone=Zone.GRAVEYARD, source_name="behavioural sweep"
                )
                _cast(scenario, probe, ALICE, from_zone=Zone.GRAVEYARD)
                _drive(scenario, case, source_id)
                return scenario, source_id

            yield graveyard_probe
        return

    if "opponent" in lowered:
        casters = [BOB]
    elif "player" in lowered:
        casters = [ALICE, BOB]
    else:
        casters = [ALICE]
    during_your_turn = "during your turn" in lowered
    # "a spell that targets <this>" (Speedball, New Warrior): the probe names
    # the source as its target when it can.
    target_phrase = re.search(r"\bthat targets (.+)$", lowered)
    targets_self = target_phrase is not None and (
        target_phrase.group(1).startswith("this ")
        or target_phrase.group(1)
        in {name.lower() for name in self_reference_names(case.printing.name)}
    )
    # "if mana from a Treasure was spent to cast it" (CR 106.3): the caster
    # floats a Treasure's mana first, which the pool spends before any land.
    treasure_paid = "mana from a treasure" in (ability.intervening_if or "").lower()
    # The stock spells, then a spell of the quality the condition names ("a
    # Zombie spell" - Diregraf Colossus, which no stock spell is) from the
    # engine's own probe finder.
    fitted = [
        card.name
        for card in _probe_cards(case.printing, ability.condition, entering=False) or []
        if card.name in pool()
        and not pool()[card.name].is_land
        and not pool()[card.name].card_faces
    ]
    # "a spell with {X} in its mana cost" (CR 107.3): no stock spell prints
    # {X}, so a real {X} spell is cast too, with X announced (CR 107.3a).
    x_spell = "{x} in its mana cost" in lowered
    if x_spell:
        fitted.append(_X_PROBE)
    for caster in casters:
        for probe in dict.fromkeys([*_PROBE_SPELLS, *fitted]):

            def cast_probe(probe: str = probe, caster: str = caster):
                if caster == ALICE:
                    scenario, source_id = _home(case, ability, hand=(probe, probe))
                elif during_your_turn:
                    scenario, source_id = _home(case, ability, bob_hand=(probe,))
                else:
                    scenario, source_id = _home(case, ability, bob_hand=(probe,), active=BOB)
                for _ in range(2 if caster == ALICE else 1):
                    if treasure_paid:
                        _treasure_mana_for(scenario, probe, caster)
                    prefer = source_id if targets_self else None
                    if caster == scenario.game.active_player.username:
                        x_value = _X_PROBE_VALUE if x_spell and probe == _X_PROBE else None
                        _cast(scenario, probe, caster, prefer=prefer, x_value=x_value)
                    else:
                        _opponent_casts(scenario, probe, prefer=prefer)
                    if _drive(scenario, case, source_id) is not None:
                        break
                return scenario, source_id

            yield cast_probe

    if ALICE in casters and _claims_cast_record(ability.intervening_if or ""):
        yield from _paid_probes(case, ability)


def _paid_probes(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """A probe spell cast by the controller for a condition on how it was
    paid for: kicked, with mana from creatures first, or for less than its
    mana value."""

    def kicked_probe() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability, hand=(_KICKER_PROBE,))
        _cast(scenario, _KICKER_PROBE, kicked=True)
        return scenario, source_id

    yield kicked_probe

    def creature_mana_probe() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(
            case,
            ability,
            hand=(_CREATURE_MANA_PROBE,),
            battlefield=(_MANA_CREATURE,) * 5,
        )
        game = scenario.game
        casting = scenario.cast(_CREATURE_MANA_PROBE, ALICE)
        payment = casting.begin_paying()
        try:
            # CR 106.3: each creature's mana ability is the mana's source.
            for creature in [
                p for p in game.permanents_controlled_by(ALICE) if _named(p, _MANA_CREATURE)
            ]:
                payment.tap_for_mana(creature, mana_from(creature))
            payment.auto_tap(game.permanents_controlled_by(ALICE))
            payment.pay()
            scenario.put_on_stack(casting)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(f"casting {_CREATURE_MANA_PROBE}: {error}") from error
        return scenario, source_id

    yield creature_mana_probe

    def discounted_probe() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability, hand=(_DISCOUNTED_PROBE,))
        _cast(scenario, _DISCOUNTED_PROBE)
        return scenario, source_id

    yield discounted_probe


def _treasure_mana_for(scenario: PlayedScenario, probe: str, username: str) -> None:
    """Sacrifice a fresh Treasure for one mana of the probe's first colour."""
    (treasure,) = create_predefined_tokens(scenario.game, "Treasure", username)
    colors = pool()[probe].colors if probe in pool() else []
    scenario.game.activate_ability(treasure, 0, username, color=colors[0] if colors else Color.RED)


def _mana_sources(scenario: PlayedScenario, username: str) -> list[CardState]:
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if not permanent.tapped
        and any(
            ability.mana is not None
            for ability in scenario.game.activated_abilities(permanent)
            if isinstance(ability, ActivatedAbility)
        )
    ]


def _tapping_for_mana(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Tap one mana source of the relevant player through its own mana
    ability (CR 106.12). A triggered mana ability resolves right away
    (CR 605.4a), so it shows as extra mana rather than on the stack -
    `run_trigger_case` checks for both."""
    lowered = ability.condition.lower()
    tapper = BOB if "opponent" in lowered else ALICE
    # The stock boards' mana sources are all lands, so a trigger about a
    # nonland one (a creature, an artifact, "a nonland permanent") gets a
    # mana source of that type staged beside them.
    extra = tuple(
        name
        for name, types in (("Llanowar Elves", ("creature",)), ("Mind Stone", ("artifact",)))
        if "nonland" in lowered or any(t in lowered for t in types)
    )
    # "As this enters, choose a color" (Caged Sun, Utopia Sprawl) is only
    # chosen by really entering (CR 614.12), so the source is also tried
    # put onto the battlefield rather than staged there.
    for entered in (False, True):
        for wanted in [*extra, *_BASICS, "Wastes"]:
            yield _tap_one(case, ability, tapper, extra, wanted, entered)


def _tap_one(
    case: Case,
    ability: TriggeredAbility,
    tapper: str,
    extra: tuple[str, ...],
    wanted: str,
    entered: bool,
) -> Attempt:
    def tap() -> tuple[PlayedScenario, Any]:
        own = (case.card,) if not entered else ()
        if tapper == ALICE:
            scenario = _board(battlefield=(*own, *extra), hand=(case.card,), step=None)
        else:
            scenario = _board(
                battlefield=own,
                hand=(case.card,),
                bob_battlefield=extra,
                active=BOB,
                step=None,
            )
        if entered:
            state = _last(scenario, case.card, Zone.HAND, ALICE)
            source = _prime(scenario, scenario.game.put_onto_battlefield(state, ALICE), ability)
        else:
            source = _source(scenario, case, ability)
        scenario.start_at(Step.PRECOMBAT_MAIN)
        land = next(
            (s for s in _mana_sources(scenario, tapper) if s.name == wanted and s is not source),
            None,
        )
        if source.attachment is not None and source.attachment.card_id is not None:
            land = scenario.game.find_by_id(source.attachment.card_id)
        if land is None:
            raise _Unavailable(f"no untapped {wanted}")
        pool_before = scenario.game.player(tapper).mana_pool.total
        produced = land.card.produced_mana or []
        color = Color(produced[0]) if len(produced) > 1 else None
        try:
            scenario.activate(land, username=tapper, color=color)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(str(error)) from error
        scenario.mana_gained = scenario.game.player(tapper).mana_pool.total - pool_before
        return scenario, source.id

    return tap


def _about_the_source(case: Case, ability: TriggeredAbility, action: str) -> Iterator[Attempt]:
    """An event about the source itself that one engine method performs."""
    lowered = ability.condition.lower()

    def happen() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability)
        game = scenario.game
        source = game.find_by_id(source_id)
        if action == "dealt damage":
            game.deal_damage(source, 1, source=_staged(scenario, "Icehide Golem", BOB))
        elif action == "counters":
            nth = re.search(r"the ([a-z]+) (\S+) counter is put on", lowered)
            if nth is not None and parse_ordinal(nth.group(1)) is not None:
                # "When the fourth plan counter is put on this enchantment"
                # (CR 122.6 as a threshold): enough at once to reach it.
                game.add_counters(source, nth.group(2), parse_ordinal(nth.group(1)))
            else:
                match = re.search(r"(\+1/\+1|[a-z]+) counters?", lowered)
                game.add_counters(source, match.group(1) if match else "+1/+1", 1)
        elif action == "monstrous":
            game.become_monstrous(source, 1)
        elif action == "transform":
            source.transformed = False  # from the front face, into the back
            transform_permanent(game, source)
        elif action == "state":
            match = re.search(
                r"there are (?P<count>[\w,]+) or more (?P<kind>[a-z]+) counters", lowered
            )
            if match is None:
                raise _Unavailable("no counter threshold in the condition")
            raw = match.group("count").replace(",", "")
            count = int(raw) if raw.isdigit() else parse_count(raw, article=False)
            if count is None:
                raise _Unavailable(f"cannot read {raw!r}")
            game.add_counters(source, match.group("kind"), count)
        return scenario, source_id

    yield happen


def _counters_you_put(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """ "Whenever you put a[n]/one or more `<kind>` counter(s) on `<a
    description>`" (CR 122.6, CR 122.6a): the controller puts one on another
    creature they control - of the subtype the description names, when it
    names one (Invisible Woman, Sue Storm's "other Heroes"), a plain Grizzly
    Bears otherwise (Knight of Wundagore's "another creature", Stocking the
    Pantry's "a creature you control")."""
    match = re.search(
        r"\byou put (?:an?|one or more) (\+1/\+1|-1/-1|[a-z]+) counters? on (.+)$",
        ability.condition,
        re.IGNORECASE,
    ) or re.search(
        # The passive "one or more [<kind>] counters are put on another
        # permanent you control" / "a creature you control" (Botanical
        # Brawler, Stalwart Successor): no kind is any kind, a +1/+1 counter.
        r"^one or more (?:(\+1/\+1|-1/-1|[a-z]+) )?counters are put on"
        r" ((?:another|an?) [a-z ]+ you control)$",
        ability.condition,
        re.IGNORECASE,
    )
    if match is None:
        return
    kind = match.group(1) or "+1/+1"
    partner = "Grizzly Bears"
    for word in re.findall(r"\b[A-Z][a-z]+\b", match.group(2)):
        subtype = singular_subtype(word)
        if subtype is None:
            continue
        candidates = sorted(
            (
                card
                for card in _format_pool()
                if Type.CREATURE in card.types
                and subtype.lower() in {word.lower() for word in card.subtypes}
                # A multi-faced printing carries its text per face, so an
                # empty top-level text would rank it "simplest" - and it
                # enters under its face's name, not the card's.
                and not card.card_faces
            ),
            key=lambda card: (len(card.oracle_text or ""), card.name),
        )
        if not candidates:
            return
        partner = candidates[0].name
        break

    def put_on_another() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability, battlefield=(partner,))
        target = next(
            permanent
            for permanent in reversed(scenario.game.permanents_controlled_by(ALICE))
            if permanent.name == partner and permanent.id != source_id
        )
        scenario.game.add_counters(target, kind, 1, putter=ALICE)
        return scenario, source_id

    yield put_on_another


def _untapping(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Tap the source by attacking with it (CR 508.1f), then play on to the
    controller's next untap step (CR 502.3)."""

    def run() -> tuple[PlayedScenario, Any]:
        scenario = _board(battlefield=(case.card,), step=Step.DECLARE_ATTACKERS)
        source = _source(scenario, case, ability)
        try:
            scenario.attack_with(source, defending=BOB)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(str(error)) from error
        scenario.no_blocks()
        return scenario, source.id

    yield run


def _targeting(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Make something the target of a spell (a probe spell cast at it) or of
    an ability (the stock targeting tool activated at it), CR 115.1."""
    for probe in ("Giant Growth", "Lightning Bolt"):

        def spell(probe: str = probe) -> tuple[PlayedScenario, Any]:
            scenario, source_id = _home(case, ability, hand=(probe,))
            _cast(scenario, probe, prefer=source_id)
            return scenario, source_id

        yield spell

    if "an opponent controls" in ability.condition.lower():
        # "becomes the target of a spell an opponent controls" (Reality
        # Smasher, Frost Titan): the probe spell is cast by the opponent,
        # once the active player has passed priority (CR 117.3d).
        for probe in ("Giant Growth", "Lightning Bolt"):

            def opposing_spell(probe: str = probe) -> tuple[PlayedScenario, Any]:
                scenario, source_id = _home(case, ability, bob_hand=(probe,))
                if scenario.priority_holder == ALICE:
                    scenario.pass_priority(ALICE)
                _cast(scenario, probe, BOB, prefer=source_id)
                return scenario, source_id

            yield opposing_spell

    def tool() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability, battlefield=(_TARGETING_TOOL,))
        tool_state = _staged(scenario, _TARGETING_TOOL)
        action = _action_for(scenario, ALICE, ActionKind.ACTIVATE, tool_state.id, ability_index=0)
        if action is None:
            raise _Unavailable("the targeting tool cannot be activated")
        targets = _pick(scenario, action.target_slots, source_id)
        scenario.activate(tool_state, auto=True, targets=targets)
        return scenario, source_id

    yield tool


#: The keywords that let a card be cast face down and turned face up for a
#: cost: morph (CR 702.37), megamorph (CR 702.37b) and disguise (CR 702.168).
_FACE_DOWN_KEYWORDS = ("morph", "megamorph", "disguise")


def _levelling(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """A Class gains the level its "When this Class becomes level N" ability
    names (CR 716.2a): staged one level below it, then its own level-up
    ability (CR 716.2b) is activated and resolved."""
    level = getattr(ability, "class_level", None)
    if level is None:
        return

    def level_up() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability)
        game = scenario.game
        source = game.find_by_id(source_id)
        source.class_level = level - 1
        indexes = [
            index
            for index, activated in enumerate(game.activated_abilities(source))
            if isinstance(activated, ActivatedAbility) and activated.class_level_target == level
        ]
        if not indexes:
            raise _Unavailable(f"no ability levels the Class to {level}")
        activated = game.activated_abilities(source)[indexes[0]]
        on_stack = _activate(scenario, source, indexes[0], activated)
        if on_stack is not None:
            while game.stack and _ours(scenario, case, source_id) is None:
                game.resolve_top()
                _settle(scenario)
        return scenario, source_id

    yield level_up


def _morph_card() -> str | None:
    for card in _format_pool():
        if any(k.canonical.lower() == "morph" for k in keyword_abilities(card)):
            return card.name
    return None


def _turning_face_up(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Cast a card face down for its morph cost (CR 702.37c), then turn it
    face up (CR 702.37e) - the source itself, or the pool's first morph card
    for a condition about another permanent."""
    card = case.printing
    own_abilities = [
        k for k in keyword_abilities(card) if k.canonical.lower() in _FACE_DOWN_KEYWORDS
    ]
    own = [k.canonical for k in own_abilities]
    # The face-down cast's {3} may spend any stock basic, so a retry gives
    # every coloured pip of the face-up cost a basic of its own on top of the
    # stock board (Alley Assailant's "Disguise {4}{B}{B}").
    face_up_lands = tuple(
        _BASIC_OF[colour]
        for colour in re.findall(r"\{([WUBRG])\}", (own_abilities[0].cost or "") if own else "")
    )
    choices = ([(card.name, own[0])] if own else []) + [(_morph_card(), "Morph")]

    def turn_up(name: str, keyword: str, extra: tuple[str, ...]) -> tuple[PlayedScenario, Any]:
        if name == card.name:
            scenario, source_id = _board(hand=(name,), battlefield=extra), None
        else:
            scenario, source_id = _home(case, ability, hand=(name,))
        _cast(scenario, name, keyword=keyword)
        scenario.game.resolve_top()
        # A turned-face-up trigger that counters "target spell" (Kheru
        # Spellsnatcher) needs one on the stack to aim at (CR 115.1).
        _stack_material(scenario)
        face_down = next(p for p in scenario.game.permanents_controlled_by(ALICE) if not p.face_up)
        try:
            payment = scenario.game.begin_turning_face_up(face_down, ALICE)
            payment.auto_tap(_mana_sources(scenario, ALICE))
            payment.pay()
            scenario.game.turn_face_up(face_down, ALICE)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(f"turning face up: {error}") from error
        scenario.game.retain_priority(ALICE)
        return scenario, source_id

    for name, keyword in choices:
        if name is None:
            continue

        def run(name: str = name, keyword: str = keyword) -> tuple[PlayedScenario, Any]:
            return turn_up(name, keyword, ())

        yield run
        if name == card.name and face_up_lands:

            def run_with_face_up_lands(
                name: str = name, keyword: str = keyword, extra: tuple[str, ...] = face_up_lands
            ) -> tuple[PlayedScenario, Any]:
                return turn_up(name, keyword, extra)

            yield run_with_face_up_lands


def _bending(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Pay a waterbend cost (CR 701.67a) - the one bending event the engine
    raises - by activating a pool ability whose cost prints one."""
    tool = next(
        (
            card.name
            for card in _format_pool()
            for a in parse_abilities(card)
            if isinstance(a, ActivatedAbility) and "waterbend" in a.cost.lower()
        ),
        None,
    )
    if tool is None:
        return

    def run() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability, battlefield=(tool,))
        tool_state = _staged(scenario, tool)
        for index, activated in enumerate(scenario.game.activated_abilities(tool_state)):
            if "waterbend" not in activated.cost.lower():
                continue
            action = _action_for(
                scenario, ALICE, ActionKind.ACTIVATE, tool_state.id, ability_index=index
            )
            targets = _pick(scenario, action.target_slots) if action is not None else []
            scenario.activate(tool_state, index=index, auto=True, targets=targets or None)
            return scenario, source_id
        raise _Unavailable("no waterbend cost")

    yield run


def _player_event(case: Case, ability: TriggeredAbility, action: str) -> Iterator[Attempt]:
    """An event that happens to a player: drawing, gaining or losing life,
    discarding, getting energy, being dealt noncombat damage, scrying -
    up to three times, for "your second/third card each turn"."""
    lowered = ability.condition.lower()
    if action == "discard" and "this card" in lowered:
        # CR 113.6: "When you discard this card" functions from the hand the
        # card is discarded out of, so the source itself is what goes.
        yield _discarding_itself(case)
        return
    players = [BOB] if "opponent" in lowered else [ALICE, BOB]
    for player in players:

        def happen(player: str = player) -> tuple[PlayedScenario, Any]:
            scenario, source_id = _home(case, ability)
            game = scenario.game
            for _ in range(3):
                if action == "draw":
                    game.draw_cards(player, 1)
                elif action == "gain":
                    game.gain_life(player, 1)
                elif action == "lose":
                    game.lose_life(player, 1)
                elif action == "discard":
                    game.discard_cards(player, [game.player(player).hand[-1]])
                elif action == "energy":
                    game.add_player_counters(player, "energy", 1)
                elif action == "noncombat damage":
                    memnite = _first(scenario, "Memnite", ALICE)
                    game.deal_damage(game.player(player), 1, source=memnite)
                elif action == "scry":
                    game.scry(player, 1)
                elif action == "scry to the bottom":
                    scenario.scry_bottoming(game.player(player).library[0], username=player)
                    game.scry(player, 1)
                if _drive(scenario, case, source_id) is not None:
                    break
            return scenario, source_id

        yield happen


def _discarding_itself(case: Case) -> Attempt:
    def discard_it() -> tuple[PlayedScenario, Any]:
        scenario = _board(hand=(case.card,))
        _stack_material(scenario)
        source = _last(scenario, case.card, Zone.HAND, ALICE)
        scenario.game.discard_cards(ALICE, [source])
        return scenario, None

    return discard_it


def _cycling_card() -> str:
    """The first in-format pool card with cycling that is not a land - a card
    to cycle when the source watches someone else's (CR 702.29a)."""
    for card in _format_pool():
        if card.is_land or card.card_faces:
            continue
        if any(k.canonical.lower() == "cycling" for k in keyword_abilities(card)):
            return card.name
    raise _Unavailable("no cycling card in the pool")


def _cycle(scenario: PlayedScenario, card: CardState, player: str) -> None:
    """Activate `card`'s cycling from `player`'s hand and leave it on the
    stack (CR 702.29a, CR 602.2), paying automatically."""
    game = scenario.game
    try:
        activation = cycling_activation(game, card, player, 0)
        payment = activation.begin_paying()
        payment.auto_tap(game.permanents_controlled_by(player))
        payment.pay()
        activation.activate()
    except (ValueError, AssertionError) as error:
        raise _Unavailable(f"cycling {card.name}: {error}") from error


def _cycling(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """CR 702.29c: "When you cycle this card" - cycle the source from the
    hand; "you cycle a card"/"another card" - cycle some other card with the
    source in play, by whoever the condition names."""
    lowered = ability.condition.lower()
    if "this card" in lowered:

        def cycle_it() -> tuple[PlayedScenario, Any]:
            scenario = _board(hand=(case.card,))
            _stack_material(scenario)
            _cycle(scenario, _last(scenario, case.card, Zone.HAND, ALICE), ALICE)
            return scenario, None

        yield cycle_it
        return
    other = _cycling_card()
    players = [BOB] if "opponent" in lowered else [ALICE, BOB]
    for player in players:

        def cycle_other(player: str = player) -> tuple[PlayedScenario, Any]:
            hands = {"hand": (other,)} if player == ALICE else {"bob_hand": (other,)}
            scenario, source_id = _home(case, ability, **hands)
            _cycle(scenario, _last(scenario, other, Zone.HAND, player), player)
            return scenario, source_id

        yield cycle_other


def _activating(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """CR 602.2: a player activates an ability that is not a mana ability
    (CR 605.1a) - the first one that player's stock permanents can pay for,
    with priority passed to them first (CR 602.2, CR 117.1b) when it is the
    opponent."""
    lowered = ability.condition.lower()
    players = [BOB] if "opponent" in lowered else [ALICE, BOB]
    # CR 605.3a: a mana ability is activated too, so a condition without
    # "that isn't a mana ability" (Elrond, Moon-Reader) is met by one.
    mana_counts = "isn't a mana ability" not in lowered
    extra = _activation_probes(lowered)
    for player in players:

        def activate(player: str = player) -> tuple[PlayedScenario, Any]:
            battlefield = {"battlefield": extra} if player == ALICE else {"bob_battlefield": extra}
            scenario, source_id = _home(case, ability, **(battlefield if extra else {}))
            game = scenario.game
            if scenario.priority_holder != player:
                scenario.pass_priority(scenario.priority_holder)
            for state in _activation_order(game, player, lowered):
                if state.id == source_id or (has_mana_ability(state.card) and not mana_counts):
                    continue
                for index, _ in enumerate(game.activated_abilities(state)):
                    if game.why_cannot_activate(state, index, player) is not None:
                        continue
                    try:
                        scenario.activate(state, index=index, username=player, auto=True)
                    except (ValueError, AssertionError):
                        continue
                    return scenario, source_id
            raise _Unavailable(f"{player} has no ability to activate")

        yield activate


def _activation_order(game: Any, player: str, condition: str) -> list[CardState]:
    """The player's permanents, those the condition's own quality names first
    ("an ability of a creature", "of an Elemental") so the activation is one
    the trigger watches for."""
    match = re.search(r"an ability of an? ([a-z]+)\b", condition)
    permanents = list(game.permanents_controlled_by(player))
    if match is None or "isn't a mana ability" in condition:
        # The non-mana conditions keep the stock order their goldens pin.
        return permanents
    word = match.group(1)

    def named(state: CardState) -> bool:
        chars = game.characteristics_of(state)
        types = {kind.value for kind in chars.types}
        return word in types or word in {s.lower() for s in chars.subtypes}

    return sorted(permanents, key=lambda state: not named(state))


def _activation_probes(condition: str) -> tuple[str, ...]:
    """A pool creature of the subtype "an ability of an `<subtype>`" names
    (Ceaseless Searblades' "an Elemental", CR 205.3) with an activated
    ability, put on the board so there is one to activate."""
    match = re.search(r"an ability of an? ([a-z]+)\b", condition)
    if (
        match is not None
        and match.group(1) == "creature"
        and "isn't a mana ability" not in condition
    ):
        # A creature whose mana ability counts (CR 605.3a).
        return ("Llanowar Elves",)
    if match is None or match.group(1) in {
        "artifact",
        "creature",
        "land",
        "enchantment",
        "planeswalker",
        "permanent",
    }:
        return ()
    subtype = match.group(1)
    for card in _format_pool():
        if card.card_faces or subtype not in {s.lower() for s in card.subtypes}:
            continue
        if any(isinstance(a, ActivatedAbility) for a in parse_abilities(card)):
            return (card.name,)
    return ()


def _graveyard_leaving(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    for name in ["Lightning Bolt", "Grizzly Bears"]:

        def exile(name: str = name) -> tuple[PlayedScenario, Any]:
            scenario, source_id = _home(case, ability)
            scenario.game.exile_cards([_last(scenario, name, Zone.GRAVEYARD, ALICE)])
            return scenario, source_id

        yield exile


def _playing_exiled(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """Activate the source's own abilities, then play or cast what they
    exiled with permission (CR 601.2, CR 305.1) - "a card exiled with this"
    (CR 607.2a)."""

    def play_exiled() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability)
        game = scenario.game
        source = game.find_by_id(source_id)
        for index, _ in enumerate(game.activated_abilities(source)):
            if game.why_cannot_activate(source, index, ALICE) is not None:
                continue
            scenario.activate(source, index=index, auto=True)
            while game.stack:
                game.resolve_top()
            break
        for action in legal_actions(game, ALICE):
            if action.from_zone is not Zone.EXILE:
                continue
            exiled = game.find_by_id(action.card_id)
            if action.kind is ActionKind.PLAY_LAND:
                game.play_land(exiled, ALICE)
                return scenario, source_id
            if action.kind is ActionKind.CAST:
                _cast(scenario, exiled.name, from_zone=Zone.EXILE)
                return scenario, source_id
        raise _Unavailable("nothing exiled to play")

    yield play_exiled


def _teamwork_tapping(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """ "becomes tapped to pay a teamwork cost" (Agent Maria Hill): a Teamwork
    spell from the pool is cast with the source among the creatures tapped
    for its teamwork cost (`Casting.pay_teamwork`), every other untapped
    creature alice controls joining it to reach the printed power."""
    spells = sorted(
        (
            card
            for card in _format_pool()
            if not card.card_faces and teamwork_ability(card) is not None
        ),
        key=lambda card: (len(card.oracle_text or ""), card.name),
    )
    for spell in spells[:3]:

        def cast_with_teamwork(spell: str = spell.name) -> tuple[PlayedScenario, Any]:
            scenario, source_id = _home(case, ability, hand=(spell,))
            game = scenario.game
            source = game.find_by_id(source_id)
            crew = [source] + [
                p
                for p in game.permanents_controlled_by(ALICE)
                if p is not source and Type.CREATURE in p.types and not p.tapped
            ]
            card = _last(scenario, spell, Zone.HAND, ALICE)
            action = _action_for(scenario, ALICE, ActionKind.CAST, card.id, alternative_cost=None)
            targets = (
                _pick(scenario, action.target_slots, text=card.card.oracle_text or "")
                if action is not None
                else []
            )
            try:
                casting = scenario.cast(spell, ALICE)
                casting.pay_teamwork(crew)
                if targets:
                    casting.choose_targets(targets)
                payment = casting.begin_paying()
                payment.auto_tap(
                    [p for p in game.permanents_controlled_by(ALICE) if p.card.is_land]
                )
                payment.pay()
                scenario.put_on_stack(casting)
            except (ValueError, AssertionError) as error:
                raise _Unavailable(f"teamwork cast: {error}") from error
            _drive(scenario, case, source_id)
            return scenario, source_id

        yield cast_with_teamwork


#: A trigger event's own "while <doing something>" qualifier (CR 603.2), as
#: `machines/conditions/events.py` reads it: the keyword whose cast or
#: activation the event happened during.
_WHILE_CASTING = re.compile(r"^(?:you(?:'re| are) )?casting an? spell with (?P<keyword>[a-z-]+)$")
_WHILE_ACTIVATING = re.compile(
    r"^(?:you(?:'re| are) )?activating an? (?P<keyword>[a-z-]+) ability$"
)


@cache
def _keyword_casters(keyword: str) -> tuple[str, ...]:
    """In-format pool printings that can be cast from a hand with `keyword`
    (CR 601.2b's alternative cost), by name."""
    from magic_cards_model.machines.casting import keyword_cast_options

    found = [
        printing
        for printing in _format_pool()
        if any(
            option.keyword.lower() == keyword and option.understood and option.zone is Zone.HAND
            for option in keyword_cast_options(printing)
        )
    ]
    return tuple(sorted(p.name for p in found))


@cache
def _keyword_activators(keyword: str) -> tuple[str, ...]:
    """In-format pool printings with a `keyword` activated ability this sweep
    can build with objects chosen for its cost (craft's materials)."""
    return tuple(
        printing.name
        for printing in _format_pool()
        if keyword == "craft" and craft_abilities(printing)
    )


def _qualified(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """The event raised the way its qualifier says: the source sacrificed or
    exiled as a cost of a spell cast with the named keyword (emerge's
    sacrifice, CR 702.119a) or of an ability the keyword expands (craft's
    materials, CR 702.167a), or a scry's choice (CR 701.22a)."""
    qualifier = (ability.event_qualifier or "").lower()
    if qualifier == "scrying":
        yield from _player_event(case, ability, "scry to the bottom")
        return
    if match := _WHILE_CASTING.fullmatch(qualifier):
        for spell in _keyword_casters(match.group("keyword")):

            def cast_with(spell: str = spell, keyword: str = match.group("keyword")):
                scenario, source_id = _home(case, ability, hand=(spell,))
                game = scenario.game
                game.cast(
                    _last(scenario, spell, Zone.HAND, ALICE),
                    ALICE,
                    keyword=keyword,
                    choosing=[game.find_by_id(source_id)],
                    mana_sources=_mana_sources(scenario, ALICE),
                )
                return scenario, source_id

            yield cast_with
    if match := _WHILE_ACTIVATING.fullmatch(qualifier):
        for activator in _keyword_activators(match.group("keyword")):

            def activate_with(activator: str = activator):
                scenario, source_id = _home(case, ability, battlefield=(activator,))
                game = scenario.game
                crafter = _staged(scenario, activator)
                activation = craft_activation(game, crafter, ALICE, [game.find_by_id(source_id)])
                payment = activation.begin_paying()
                scenario.auto_pay(payment, username=ALICE)
                activation.activate()
                return scenario, source_id

            yield activate_with


def _committing_crime(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """CR 700.13: the controller commits a crime as they cast a spell that
    targets an opponent - a Lightning Bolt from the stock hand, at bob."""

    def crime() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability)
        _cast(scenario, "Lightning Bolt", prefer=BOB)
        return scenario, source_id

    yield crime


#: A real library search (CR 701.23a) any player can make: a fetchland.
_SEARCHER = "Wooded Foothills"


def _searching(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """A player searches their library (CR 701.23a) by activating a
    fetchland - the opponent for "an opponent searches", else either."""
    players = [BOB] if "opponent" in ability.condition.lower() else [ALICE, BOB]
    for player in players:

        def search(player: str = player) -> tuple[PlayedScenario, Any]:
            if player == ALICE:
                scenario, source_id = _home(case, ability, battlefield=(_SEARCHER,))
            else:
                scenario, source_id = _home(case, ability, bob_battlefield=(_SEARCHER,))
            fetch = _staged(scenario, _SEARCHER, player)
            if scenario.priority_holder != player:
                scenario.pass_priority(scenario.priority_holder)
            try:
                scenario.activate(fetch, username=player, sacrificing=[fetch], auto=True)
            except (ValueError, AssertionError) as error:
                raise _Unavailable(f"fetching: {error}") from error
            return scenario, source_id

        yield search


def _unlocking(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """ "When you unlock this door": the Room's half the ability is printed on
    is cast, so the permanent enters with that half unlocked (CR 709.5d),
    which is when the door-unlock trigger fires (CR 709.5h); then, on a Room
    already on the battlefield with neither door unlocked, that door's unlock
    cost is paid as the CR 709.5e special action."""
    face = getattr(ability, "face", None)
    if not face:
        return

    def unlock(face: str = face) -> tuple[PlayedScenario, Any]:
        scenario = _board(hand=(case.card,))
        _cast(scenario, case.card, announce=lambda casting: casting.cast_as_split_half(face))
        return scenario, None

    yield unlock

    def unlock_cost(face: str = face) -> tuple[PlayedScenario, Any]:
        scenario = _board(battlefield=(case.card,))
        game = scenario.game
        room = _last(scenario, case.card, Zone.BATTLEFIELD, ALICE)
        try:
            payment = game.begin_unlocking_door(ALICE, room, face)
            payment.auto_tap(game.permanents_controlled_by(ALICE))
            payment.pay()
            game.finish_unlocking_door(ALICE, room, face)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(f"unlocking {face}: {error}") from error
        return scenario, room.id

    yield unlock_cost


def _to_graveyard(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """ "When [this] is put into a graveyard from anywhere" (CR 603.6c): the
    source goes to the graveyard - destroyed from the battlefield, then
    discarded from the hand."""
    card = case.printing
    if set(card.types) & _PERMANENT_TYPES:

        def destroyed() -> tuple[PlayedScenario, Any]:
            scenario = _board(battlefield=(case.card,))
            source = _source(scenario, case, ability)
            scenario.game.destroy(source)
            return scenario, None

        yield destroyed

    def discarded() -> tuple[PlayedScenario, Any]:
        scenario = _board(hand=(case.card,))
        scenario.game.discard_cards(ALICE, [_last(scenario, case.card, Zone.HAND, ALICE)])
        return scenario, None

    yield discarded


def _enlisting(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """The source attacks and enlists another creature its controller could
    have attacked with (CR 702.154a)."""

    def enlist() -> tuple[PlayedScenario, Any]:
        scenario, source_id = _home(case, ability, step=Step.DECLARE_ATTACKERS)
        game = scenario.game
        source = game.find_by_id(source_id)
        eligible = eligible_enlist_creatures(game, source, set())
        if not eligible:
            raise _Unavailable("nothing to enlist")
        try:
            game.declare_attackers([(source, BOB)], enlist_choices={source.id: eligible[0]})
        except (ValueError, AssertionError) as error:
            raise _Unavailable(str(error)) from error
        return scenario, source_id

    yield enlist


def _animation_index(scenario: PlayedScenario, source: CardState) -> int | None:
    """The source's own activated ability that makes it a creature ("this
    land becomes a 2/3 ... creature"), read off the engine's parsed
    abilities, or None."""
    for index, activated in enumerate(scenario.game.activated_abilities(source)):
        effect = (activated.effect or "").lower()
        if re.search(r"\bbecomes? an? [^.]*\bcreature\b", effect):
            return index
    return None


def _animated_attack(case: Case, ability: TriggeredAbility) -> Iterator[Attempt]:
    """A noncreature permanent that makes itself a creature (a manland) is
    animated by its own ability, then attacks."""
    card = case.printing
    if _is(card, Type.CREATURE) or not set(card.types) & _PERMANENT_TYPES:
        return

    def animated() -> tuple[PlayedScenario, Any]:
        scenario = _board(battlefield=(case.card,), step=Step.PRECOMBAT_MAIN, busy=False)
        source = _source(scenario, case, ability)
        game = scenario.game
        index = _animation_index(scenario, source)
        if index is None:
            raise _Unavailable("no ability makes it a creature")
        try:
            scenario.activate(source, index=index, auto=True)
            while game.stack:
                game.resolve_top()
            scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
            game.sync_priority_with_step()
            scenario.attack_with(source, defending=BOB)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(str(error)) from error
        return scenario, source.id

    yield animated


def _attempts(case: Case) -> Iterator[Attempt]:
    ability = _trigger_ability(case.printing, case.text)
    if ability.event_qualifier:
        yield from _qualified(case, ability)
    kinds = case.kind.split("+")
    for kind in kinds:
        if kind == TriggerEvent.ENTERS_THE_BATTLEFIELD.value:
            yield from _self_entering(case, ability)
            yield from _other_entering(case, ability)
        elif kind in _REMOVALS:
            yield from _leaving(case, ability, kind)
        elif kind == "becomes_tapped" and "teamwork" in ability.condition.lower():
            yield from _teamwork_tapping(case, ability)
        elif kind in (
            "attacks",
            "attacks_unblocked",
            "blocks",
            "combat_damage_to_players",
            "becomes_tapped",
            # "one or more <description> become tapped" (CR 603.2c): the
            # attackers a declaration taps together (CR 508.1f).
            "permanents_tapped",
        ):
            yield from _combat(case, ability)
            if kind == "becomes_tapped":
                # CR 701.26a: a mana ability's {T} taps a permanent too - the
                # tap no attack declaration makes (CR 508.1f).
                yield from _tapping_for_mana(case, ability)
        elif kind == TriggerEvent.DEALS_DAMAGE.value:
            lowered = ability.condition.lower()
            if "is dealt damage" in lowered and "noncombat" not in lowered:
                yield from _about_the_source(case, ability, "dealt damage")
            elif "noncombat" in lowered:
                yield from _player_event(case, ability, "noncombat damage")
            else:
                yield from _combat(case, ability)
        elif kind == TriggerEvent.CAST_SPELL.value:
            if "plays_land" in kinds:
                yield from _playing_exiled(case, ability)
            yield from _casting(case, ability)
        elif kind in ("tapped_for_mana", "mana_added"):
            yield from _tapping_for_mana(case, ability)
        elif kind == "draws_a_card":
            yield from _player_event(case, ability, "draw")
        elif kind == "gains_life":
            yield from _player_event(case, ability, "gain")
        elif kind == "loses_life":
            yield from _player_event(case, ability, "lose")
        elif kind == "discards_a_card":
            yield from _player_event(case, ability, "discard")
        elif kind == "player_counters_put":
            yield from _player_event(case, ability, "energy")
        elif kind == "scry_or_surveil":
            yield from _player_event(case, ability, "scry")
        elif kind == "counters_put":
            yield from _about_the_source(case, ability, "counters")
            yield from _counters_you_put(case, ability)
        elif kind == "becomes_monstrous":
            yield from _about_the_source(case, ability, "monstrous")
        elif kind == "transforms":
            yield from _about_the_source(case, ability, "transform")
        elif kind == "state":
            yield from _about_the_source(case, ability, "state")
        elif kind in ("leaves_graveyard", "exiled_from_graveyard"):
            yield from _graveyard_leaving(case, ability)
        elif kind == "becomes_untapped":
            yield from _untapping(case, ability)
        elif kind == "becomes_target":
            yield from _targeting(case, ability)
        elif kind == "turned_face_up":
            yield from _turning_face_up(case, ability)
        elif kind == "class_becomes_level":
            yield from _levelling(case, ability)
        elif kind == "waterbends":
            yield from _bending(case, ability)
        elif kind == "cycled":
            yield from _cycling(case, ability)
        elif kind == "ability_activated":
            yield from _activating(case, ability)
    # Every kind also gets whole turns played with the source in play:
    # beginning-of-step, draw-step draws, untap steps and Saga chapters all
    # happen on their own there, and so does anything an attempt above
    # started (an attack that tapped the source untaps next turn).
    yield from _turns(case, ability)
    # Drivers added after the ones above run last, so every case that
    # already executes keeps its recorded attempt index (its golden recipe).
    for kind in kinds:
        if kind == "crime_committed":
            yield from _committing_crime(case, ability)
        elif kind == "searches_library":
            yield from _searching(case, ability)
        elif kind == "door_unlocked":
            yield from _unlocking(case, ability)
        elif kind == "put_into_graveyard":
            yield from _to_graveyard(case, ability)
        elif kind == "enlists":
            yield from _enlisting(case, ability)
        elif kind == "attacks":
            yield from _animated_attack(case, ability)


#: Attempts whose event happens later in the turn (or in the next ones), so
#: `_drive` keeps playing forward after them.
_ADVANCING = {"staged", "entered", "run", "fought"}


# ---------------------------------------------------------------------------
# Kinds the harness cannot raise generically - reviewed, one reason per event
# kind, never per card.
# ---------------------------------------------------------------------------

TRIGGER_KIND_SKIPS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Real engine gaps this sweep found that are larger than a local fix - left
# failing, `xfail(strict=True)`, for the silent-card campaign. `strict` makes
# a fix announce itself: the entry has to be removed the day the card works.
# Keyed by case id because each is a finding about one clause, not a harness
# limitation (those are `TRIGGER_KIND_SKIPS`, per event kind).
# ---------------------------------------------------------------------------

KNOWN_ENGINE_GAPS: dict[str, str] = {
    "Illuminated Folio #0 [activated]": (
        "cost 'Reveal two cards from your hand that share a color' cannot be built"
    ),
    "The Filigree Sylex #2 [activated]": (
        "cost 'Remove ten oil counters from among permanents you control and "
        "sacrifice The Filigree Sylex' cannot be built"
    ),
}


# ---------------------------------------------------------------------------
# Events and preconditions the sweep has no driver for yet - reviewed, keyed
# by event kind plus the precondition that kind's attempts cannot set up,
# never by card. Each is `xfail(strict=True)`: the day a driver lands
# the cases pass, the strict xpass fails, and the entry has to go. A new card
# matching an entry is covered by the same reason; a card that matches one
# and already executes shows up as that strict xpass instead of hiding here.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DriverGap:
    kind: str
    #: What has to happen that no attempt for `kind` can make happen.
    event: str
    #: Matched against the clause text; empty matches every clause of `kind`.
    precondition: str = ""
    #: A keyword the source must have (how it is turned face up, say).
    keyword: str | None = None

    def covers(self, case: Case) -> bool:
        if case.kind != self.kind:
            return False
        if self.keyword is not None and self.keyword not in case.printing.keywords:
            return False
        return re.search(self.precondition, case.text, re.IGNORECASE) is not None

    @property
    def reason(self) -> str:
        return f"sweep has no driver for {self.event} yet"


SWEEP_DRIVER_GAPS: tuple[DriverGap, ...] = (
    # EC6's object-state conditions about an object other than the source,
    # which the stock board cannot give the state the condition asks for.
    DriverGap(
        kind="dies",
        event="another creature dying with the counters, toughness or attachments asked for",
        precondition=r"^whenever (?:another|a) (?:nontoken )?creature(?: an opponent controls"
        r"| you control)? "
        r"dies, if (?:it had [^,]*counters?\b|its toughness was|it was enchanted|an aura)",
    ),
    DriverGap(
        kind="deals_damage",
        event="a creature of the controller's with a counter on it dealing combat damage",
        precondition=r"creature you control with an? (?:\+1/\+1 )?counter on it deals combat "
        r"damage",
    ),
    DriverGap(
        kind="leaves_the_battlefield",
        event="a creature of the controller's with a counter on it leaving the battlefield",
        precondition=r"creature you control with an? (?:\+1/\+1 )?counter on it leaves",
    ),
    DriverGap(
        kind="dies",
        event="a permanent with the counters the condition names dying",
        precondition=r"with (?:an?|one or more) (?:\S+ )?counters? on it dies",
    ),
    DriverGap(
        kind="ring_tempts_you",
        event="the Ring tempting you with a creature other than the source chosen",
        precondition=r"you chose a creature other than",
    ),
    DriverGap(
        kind="cast_spell+plays_land",
        event="a card exiled with the source sharing a type with what is played",
        precondition=r"shares a card type with the exiled card",
    ),
    DriverGap(
        kind="cast_spell",
        event="a spell cast while the named source is attacking",
        precondition=r"while .+ is attacking",
    ),
    DriverGap(
        kind="enters_the_battlefield",
        event="a creature entering from exile or cast from exile",
        precondition=r"entered from exile or was cast from exile",
    ),
    DriverGap(
        kind="enters_the_battlefield",
        event="the source cast from a graveyard",
        precondition=r"if it was cast from your graveyard",
    ),
    DriverGap(
        kind="enters_the_battlefield",
        event="another creature entering from a graveyard or cast from one",
        precondition=r"entered or were cast from a graveyard",
    ),
    DriverGap(
        kind="enters_the_battlefield",
        event="a token entering under an opponent's control",
        precondition=r"one or more tokens your opponents control enter",
    ),
    DriverGap(
        kind="activated",
        event="an activation in combat by the attacking source",
        precondition=r"activate only if this creature is attacking",
    ),
    DriverGap(
        kind="activated",
        event="the source made blue",
        precondition=r"activate only if this creature is blue",
    ),
    DriverGap(
        kind="beginning_of_step",
        event="a graveyard holding cards of five or more different mana values",
        precondition=r"if there are \w+ or more mana values among cards in your graveyard",
    ),
    # ecl integration: shapes the stock boards cannot set up.
    DriverGap(
        kind="attacks",
        event="a second attacking creature of the subtype the trigger targets",
        precondition=r"another target attacking [A-Z][a-z]+ you control",
    ),
    DriverGap(
        kind="enters_the_battlefield",
        event="a creature type chosen for the source as it entered (CR 614.12a)",
        precondition=r"of the chosen type enters",
    ),
)


def _driver_gap(case: Case) -> DriverGap | None:
    return next((gap for gap in SWEEP_DRIVER_GAPS if gap.covers(case)), None)


def _params(cases: tuple[Case, ...]) -> list[Any]:
    params = []
    for case in cases:
        reason = KNOWN_ENGINE_GAPS.get(case.id)
        if reason is None and (gap := _driver_gap(case)) is not None:
            reason = gap.reason
        marks = [pytest.mark.xfail(strict=True, reason=reason)] if reason else []
        params.append(pytest.param(case, id=case.id, marks=marks))
    return params


# ---------------------------------------------------------------------------
# The report.
# ---------------------------------------------------------------------------

_REPORT: dict[str, Counter[str]] = {"triggered": Counter(), "activated": Counter()}


def _reported(case: Case, outcome: str) -> str:
    if outcome == "executed":
        return outcome
    if case.id in KNOWN_ENGINE_GAPS:
        return "known engine gap (xfail)"
    if _driver_gap(case) is not None:
        return "no sweep driver yet (xfail)"
    return outcome


def _record(family: str, kind: str, outcome: str) -> None:
    _REPORT[family][f"{kind}: {outcome}"] += 1


@pytest.fixture(scope="module", autouse=True)
def _report_counts(request: pytest.FixtureRequest) -> Iterator[None]:
    """Print executed/skipped/failed per event kind when the module ends."""
    yield
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    for family, counts in _REPORT.items():
        if not counts:
            continue
        reporter.write_line(f"\nbehavioural sweep - {family}, per event kind:")
        for key in sorted(counts):
            reporter.write_line(f"  {key}: {counts[key]}")


# ---------------------------------------------------------------------------
# The trigger sweep.
# ---------------------------------------------------------------------------


def _resolve_ours(
    scenario: PlayedScenario, found: Any, labels: golden.Labels
) -> tuple[ResolutionEffect, dict[str, Any], dict[str, Any]]:
    """Resolve whatever went on the stack above the ability, then the
    ability itself, measuring what it did - as the sweep's verdict and as the
    golden's `action` and `delta`."""
    game = scenario.game
    while game.stack and game.stack[-1] is not found:
        game.resolve_top()
    with game.board_snapshot():
        before = golden.snapshot(game, labels)
        action = golden.action_view(game, labels, found)
    game.resolve_top()
    with game.board_snapshot():
        after = golden.snapshot(game, labels)
    effect = ResolutionEffect(before.dump, after.dump, after.asked - before.asked)
    return effect, action, golden.delta(game, labels, before, after)


def _source_notices(scenario: PlayedScenario, case: Case) -> list[str]:
    """Notices the engine raised about this card while the event played
    out - an unread intervening "if" (CR 603.4), cast condition or target
    restriction is the engine failing closed on the ability rather than
    performing it. CR 603.3d's plain "no legal target" is not one: it is
    reported with the attempt instead."""
    found = []
    for field in ("intervening_if_notices", "targeting_notices", "cast_condition_notices"):
        for notice in getattr(scenario.game, field):
            kind = getattr(notice, "kind", None)
            if kind is not None and kind.value == "no_legal_targets":
                continue
            if _same_card(notice.source_name, case.card):
                text = getattr(notice, "clause", None) or getattr(notice, "condition", None)
                found.append(f"{field}: {text or notice.text!r}")
    return found


def _wrongly_untargetable(
    scenario: PlayedScenario, case: Case, ability: TriggeredAbility, source_id: Any
) -> list[str]:
    """The objects the target restriction itself accepts although CR 603.3d
    removed the ability for having no legal target - on the controller's own
    turn, where nothing on the stock board has a targeting protection (the
    opponent's permanents only *mention* one; Kaito's own-turn hexproof is
    his controller's turn, not this one). A non-empty answer is a targeting
    protection read where there is none: the Devourer of Destiny defect."""
    game = scenario.game
    if not _no_target(scenario, case) or game.active_player.username != ALICE:
        return []
    if source_id is None:
        source_id = next(
            (s.id for s in [*game.stack, *game.battlefield] if _same_card(s.name, case.card)),
            None,
        )
    requirements = profile_for_text(ability.text).requirements
    found = []
    for candidate in _objects(scenario):
        if isinstance(candidate, AbilityOnStack) or getattr(candidate, "id", None) == source_id:
            continue
        if any(r.rejects(candidate, ALICE, game, source_id) is None for r in requirements):
            found.append(getattr(candidate, "name", None) or getattr(candidate, "username", "?"))
    return found


def _no_target(scenario: PlayedScenario, case: Case) -> bool:
    return any(
        notice.kind.value == "no_legal_targets" and _same_card(notice.source_name, case.card)
        for notice in scenario.game.targeting_notices
    )


class Outcome(NamedTuple):
    """A case's verdict, why, and - when it executed - its golden record."""

    status: str
    detail: str
    record: dict[str, Any] | None = None


def _params_of(attempt: Attempt) -> dict[str, Any]:
    """An attempt's own parameters - the defaults its closure was bound with
    (the probe card, its owner, the removal, ...) - for the golden recipe."""
    code = attempt.__code__
    names = code.co_varnames[: code.co_argcount]
    values = attempt.__defaults__ or ()
    bound = dict(zip(names[len(names) - len(values) :], values, strict=True))
    return {name: value if golden._scalar(value) else str(value) for name, value in bound.items()}


def _golden_record(
    case: Case, recipe: dict[str, Any], action: dict[str, Any], delta: dict[str, Any]
) -> dict[str, Any]:
    family = "activated" if case.kind == "activated" else "triggered"
    return {
        "format": golden.FORMAT,
        "card": case.card,
        "family": family,
        "number": case.number,
        "ability": case.text,
        "kind": case.kind,
        "board": _STAGING.board,
        "recipe": recipe,
        "action": action,
        "delta": delta,
    }


def run_trigger_case(case: Case, only: dict[str, Any] | None = None) -> Outcome:
    """`executed` (with its golden record) when the ability fired and did
    something, `failed` otherwise. `only` replays one recorded recipe."""
    ability = _trigger_ability(case.printing, case.text)
    tried: list[str] = []
    outcome: Outcome | None = None
    closed: str | None = None
    declined = only is not None and only.get("optional_targets") == "none"
    _STAGING.optional_targets = "none" if declined else "some"
    for variant in VARIANTS:
        if only is not None and variant != only["variant"]:
            continue
        _STAGING.variant, _STAGING.case = variant, case
        # Dash Hopes' own second, unrelated ability - "Counter target
        # spell." - needs a target to even be cast at all (CR 601.2c), a
        # requirement the trigger's own clause (`ability.text`, "any player
        # may pay 5 life. If a player does, counter Dash Hopes.") says
        # nothing about. A "when you cast this spell" trigger's own attempts
        # (`_self_entering`'s `cast`) genuinely cast the printing itself, so
        # every *static* ability's own targeting requirement needs a
        # candidate too - never an *activated* ability's (Kozilek, the Great
        # Distortion's own "Discard a card with mana value X: Counter target
        # spell with mana value X." is never part of casting Kozilek at all,
        # and staging its "target spell" a `Zone.STACK` probe would ask
        # `_stack_material` to put something on the stack before Kozilek is
        # even cast - breaking CR 117.1a's empty-stack requirement for the
        # sorcery-speed creature it actually is).
        static_text = " ".join(
            a.text for a in parse_abilities(case.printing) if isinstance(a, StaticAbility)
        )
        whole_card_material = (
            _target_material(static_text) if "this spell" in ability.condition.lower() else ()
        )
        _STAGING.material = (
            _target_material(ability.text)
            + _precondition_material(ability.intervening_if or "")
            + _board_material(case.card, ability.intervening_if or "")
            + whole_card_material
        )
        try:
            for index, attempt in enumerate(_attempts(case)):
                if only is not None and index != only["index"]:
                    continue
                recipe = {
                    "variant": variant,
                    "attempt": attempt.__name__,
                    "index": index,
                    "params": _params_of(attempt),
                }
                _STAGING.board = None
                _STAGING.optional_chosen = False
                try:
                    scenario, source_id = attempt()
                except (_Unavailable, ValueError) as unavailable:
                    tried.append(f"{variant} {attempt.__name__}: unavailable: {unavailable}")
                    continue
                _halt_here(scenario)
                advance = attempt.__name__ in _ADVANCING
                found = _drive(scenario, case, source_id, advance=advance)
                if found is None:
                    gained = getattr(scenario, "mana_gained", 0)
                    if gained > 1:
                        labels = golden.Labels(scenario.game)
                        with scenario.game.board_snapshot():
                            now = golden.snapshot(scenario.game, labels)
                        delta = {"mana_gained": gained, "players": now.players}
                        return Outcome(
                            "executed",
                            "triggered mana ability resolved on the spot",
                            _golden_record(
                                case, recipe, golden.action_view(scenario.game, labels, None), delta
                            ),
                        )
                    wrongly = _wrongly_untargetable(scenario, case, ability, source_id)
                    if wrongly:
                        return Outcome(
                            "failed",
                            f"{variant} {attempt.__name__}: removed for no legal target "
                            f"(CR 603.3d), yet the target restriction accepts {wrongly} - "
                            "a targeting protection read where there is none (CR 702.11b)",
                        )
                    notices = _source_notices(scenario, case)
                    if notices:
                        closed = (
                            f"{variant} {attempt.__name__}: failed closed: {sorted(set(notices))}"
                        )
                    why = "no legal target (CR 603.3d)" if _no_target(scenario, case) else ""
                    tried.append(f"{variant} {attempt.__name__}: never reached the stack {why}")
                    continue
                labels = golden.Labels(scenario.game)
                effect, action, delta = _resolve_ours(scenario, found, labels)
                if declined:
                    # The declined branch of an optional target (CR 115.6):
                    # recorded whatever it did, doing nothing included.
                    recipe["optional_targets"] = "none"
                    return Outcome(
                        "declined", repr(effect), _golden_record(case, recipe, action, delta)
                    )
                if _STAGING.optional_chosen:
                    recipe["optional_targets"] = "some"
                if effect.did_something:
                    return Outcome(
                        "executed", repr(effect), _golden_record(case, recipe, action, delta)
                    )
                outcome = Outcome("failed", f"{variant} {attempt.__name__}: resolved: {effect!r}")
        finally:
            _STAGING.variant, _STAGING.case, _STAGING.material = QUIET, None, ()
            _STAGING.optional_targets, _STAGING.optional_chosen = "some", False
    if outcome is not None:
        return outcome
    if closed is not None:
        return Outcome("failed", closed)
    return Outcome("failed", "the ability never reached the stack: " + "; ".join(tried[-8:]))


@pytest.mark.parametrize("case", _params(trigger_cases()))
def test_every_handled_trigger_fires_and_does_something(
    case: Case, request: pytest.FixtureRequest
) -> None:
    if case.kind in TRIGGER_KIND_SKIPS:
        _record("triggered", case.kind, "skipped")
        pytest.skip(TRIGGER_KIND_SKIPS[case.kind])
    outcome = run_trigger_case(case)
    _record("triggered", case.kind, _reported(case, outcome.status))
    assert outcome.status == "executed", f"{case.card}: {case.text!r} - {outcome.detail}"
    _check_golden(case, outcome.record, request)
    assert outcome.record is not None
    if outcome.record["recipe"].get("optional_targets") == "some":
        # The same recipe with the optional target declined (CR 115.6): its
        # own golden, so both branches of the choice are pinned.
        declined = run_trigger_case(
            case, only={**outcome.record["recipe"], "optional_targets": "none"}
        )
        assert declined.status == "declined", f"{case.id}: {declined.detail}"
        _check_golden(case, declined.record, request, declined=True)


# ---------------------------------------------------------------------------
# The activation sweep.
# ---------------------------------------------------------------------------

#: The `begin_activating`/`off_zone_activation` keyword each object-choosing
#: cost component is paid through (CR 601.2b, CR 602.2b).
_COST_KEYWORDS = {
    ComponentKind.SACRIFICE: "sacrificing",
    ComponentKind.DISCARD: "discarding",
    ComponentKind.EXILE: "exiling",
    ComponentKind.TAP: "tapping",
    ComponentKind.REVEAL: "revealing",
}


def _activated_ability(card: Card, text: str) -> ActivatedAbility:
    for ability in parse_abilities(card):
        if isinstance(ability, ActivatedAbility) and ability.text == text:
            return ability
    raise AssertionError(f"{card.name}: no activated ability reads {text!r}")


def _x_for(ability: ActivatedAbility) -> int:
    cost = ability.cost.lower()
    return 1 if "{x}" in cost or " x " in f" {cost} " or "remove any number of" in cost else 0


def _prepare(scenario: PlayedScenario, source: CardState, ability: ActivatedAbility) -> None:
    """What the cost or the restriction asks for that the stock board does
    not start with: energy (CR 107.14), counters to remove (CR 122.1),
    loyalty for a minus ability (CR 606.6), the level below a Class's bar
    (CR 716.2a), a card exiled with the source for a "card exiled with this"
    target (CR 607.2a), an ability on the stack to target (CR 115.1c), and a
    this-turn "Activate only if" condition (`_history_threshold`)."""
    game = scenario.game
    for condition in read_activation_instructions(ability.instructions).conditions:
        _counter_threshold(scenario, source, condition)
        _history_threshold(scenario, source, condition)
        _board_threshold(scenario, source, condition)
        _player_state_threshold(scenario, condition)
        _object_state_threshold(scenario, source, condition)
    cost = ability.cost.lower()
    if "{e}" in cost:
        game.add_player_counters(ALICE, "energy", 10)
    for match in re.finditer(
        r"remove (?:an?|one|two|three|x|\d+|any number of) (\S+) counters? from "
        r"(?:this|~|(?P<name>[^,:]+))",
        cost,
    ):
        named = match.group("name")
        # "from a creature you control": the source is one such permanent,
        # so its own counters can pay (CR 118.3).
        chosen = named is not None and re.match(r"an? .+ you control$", named.strip())
        if named is not None and not chosen and not source.name.lower().startswith(named.strip()):
            continue  # CR 201.5: a name in its own cost is the source itself
        game.add_counters(source, match.group(1), 5)
    if ability.loyalty is not None:
        minus = re.match(r"[−-](\d+)", ability.cost.strip())
        if minus is not None:
            game.add_counters(source, "loyalty", int(minus.group(1)))
    if ability.class_level_target is not None:
        source.class_level = ability.class_level_target - 1
    if (ability.ability_word or "").lower() == "boast":
        # CR 702.142a: "Activate only if this creature attacked this turn" -
        # the attack is staged as the historical fact it is, the same way the
        # level below a Class's bar is.
        game.attacked_this_turn.add(source.id)
    profile = profile_for_text(ability.effect)
    if any(r.exiled_with_source for r in profile.requirements):
        # The source's own linked exile (CR 607.2a) fills when a creature
        # dies with it in play - kill the opponent's.
        victims = [p for p in game.permanents_controlled_by(BOB) if Type.CREATURE in p.types]
        if victims:
            game.destroy(victims[0])
        _settle(scenario)
        while game.stack:
            game.resolve_top()
    if any(Type.CREATURE in r.ability_source_types for r in profile.requirements):
        fanatic = _first(scenario, _CREATURE_TARGETING_TOOL, ALICE)
        scenario.activate(fanatic, sacrificing=[fanatic], targets=[BOB])
    elif any(r.allows_abilities for r in profile.requirements):
        tool = _first(scenario, _TARGETING_TOOL, ALICE)
        action = _action_for(scenario, ALICE, ActionKind.ACTIVATE, tool.id, ability_index=0)
        if action is not None:
            scenario.activate(tool, auto=True, targets=_pick(scenario, action.target_slots))


def _cost_choices(
    scenario: PlayedScenario, source: CardState, index: int, x_value: int, *, off_zone: bool
) -> dict[str, list[CardState]]:
    """The objects each "sacrifice/discard/exile/tap [something]" cost piece
    is paid with (CR 601.2b): the first ones the cost's own `CardRequirement`
    accepts, never the source itself unless the cost names it, lands last."""
    game = scenario.game
    threshold = _symbol_threshold(game.activated_abilities(source)[index])
    if threshold is not None:
        # "Exile any number of <colour> cards from your graveyard with N or
        # more <colour> mana symbols ..." (CR 118.3): every card of that
        # colour in the graveyard, which is as many symbols as there are.
        quality, _color, _needed = threshold
        return {
            "exiling": [
                card for card in game.player(ALICE).graveyard if quality in card.card.colors
            ]
        }
    try:
        total = game.activation_cost(source, index, ALICE, x_value=x_value)
    except ValueError:
        return {}
    chosen: dict[str, list[CardState]] = {}
    taken: set[Any] = set()
    for component in total.components:
        keyword = _COST_KEYWORDS.get(component.kind)
        if keyword is None or component.cards or component.required <= 0:
            continue
        if component.kind in (ComponentKind.SACRIFICE, ComponentKind.TAP) or (
            component.zone is Zone.BATTLEFIELD
        ):
            pool = [
                p
                for p in game.permanents_controlled_by(ALICE)
                if component.kind is not ComponentKind.TAP or not p.tapped
            ]
        elif component.kind in (ComponentKind.DISCARD, ComponentKind.REVEAL):
            pool = list(game.player(ALICE).hand)
        else:
            pool = list(game.player(ALICE).cards_in(component.zone))
        # The source itself may pay a cost that names no "other" (four
        # Persistent Petitioners tapping themselves); never a sacrifice of it.
        own_ok = component.kind is ComponentKind.TAP and not getattr(
            component.requirement, "excludes_source", False
        )
        candidates = [
            c
            for c in pool
            if (c is not source or own_ok)
            and c.id not in taken
            and (
                component.requirement is None
                or component.requirement.why_not(c, game, ALICE) is None
            )
        ]
        candidates.sort(key=lambda c: c.card.is_land)
        picked = candidates[: component.required]
        taken.update(c.id for c in picked)
        chosen.setdefault(keyword, []).extend(picked)
    return chosen


def _cost_material(case: Case) -> tuple[Material, ...]:
    """Real printings - or predefined tokens (CR 111.10) - for a cost piece
    the stock board cannot pay ("Sacrifice a Food", "Tap four untapped
    Advisors you control"), found by the cost's own `CardRequirement`."""
    return _cost_material_for(case.card, case.text)


def _symbol_threshold(ability: ActivatedAbility) -> tuple[Any, Any, int] | None:
    """The parts of a symbol-threshold exile cost piece on this ability, if any
    (`models.game.symbol_threshold_exile_cost`)."""
    for piece in ability.costs:
        parts = symbol_threshold_exile_cost(piece.text)
        if parts is not None:
            return parts
    return None


def _symbol_threshold_material(threshold: tuple[Any, Any, int]) -> tuple[Material, ...]:
    """Graveyard cards of the cost's colour carrying at least its threshold of
    mana symbols between them, the richest printings in the pool first."""
    quality, color, needed = threshold
    ranked = sorted(
        (
            card
            for card in _format_pool()
            if not card.card_faces and quality in card.colors and not card.is_land
        ),
        key=lambda card: (-colored_symbol_count(card, color), card.name),
    )
    material: list[Material] = []
    total = 0
    for card in ranked:
        if total >= needed:
            break
        count = colored_symbol_count(card, color)
        if count <= 0:
            break
        material.append(Material(card.name, ALICE, Zone.GRAVEYARD))
        total += count
    return tuple(material) if total >= needed else ()


@cache
def _cost_material_for(card_name: str, text: str) -> tuple[Material, ...]:
    card = pool()[card_name]
    ability = _activated_ability(card, text)
    threshold = _symbol_threshold(ability)
    if threshold is not None:
        return _symbol_threshold_material(threshold)
    saved = _STAGING.variant, _STAGING.material
    _STAGING.variant, _STAGING.material = QUIET, _target_material(ability.effect)
    try:
        scenario, source, index = _activation_board(case_for(card_name, text), ability, False)
        if source is None or index is None:
            return ()
        game = scenario.game
        try:
            total = game.activation_cost(source, index, ALICE, x_value=_x_for(ability))
        except ValueError:
            return ()
        material: list[Material] = []
        choices = _cost_choices(scenario, source, index, _x_for(ability), off_zone=False)
        for component in total.components:
            keyword = _COST_KEYWORDS.get(component.kind)
            if keyword is None or component.cards or component.required <= 0:
                continue
            have = len(choices.get(keyword, []))
            if have >= component.required:
                continue
            requirement = component.requirement
            if requirement is not None and requirement.same_name_as is not None:
                # "a legendary card with the same name as a legendary
                # permanent you control": the pair, one in each place.
                pair = _same_name_pair(requirement)
                if pair is not None:
                    material += [
                        Material(pair, ALICE, Zone.BATTLEFIELD),
                        Material(pair, ALICE, Zone.HAND),
                    ]
                continue
            found = _cost_card(component)
            if found is not None:
                material += [found] * (component.required - have)
        return tuple(material)
    finally:
        _STAGING.variant, _STAGING.material = saved


def case_for(card_name: str, text: str) -> Case:
    return Case(card_name, text, "activated", 0)


def _same_name_pair(requirement: Any) -> str | None:
    """A permanent card that satisfies both halves of a "with the same name
    as a [quality] permanent you control" cost."""
    for card in _format_pool():
        if card.card_faces or not set(card.types) & _PERMANENT_TYPES:
            continue
        if set(requirement.supertypes) <= set(card.supertypes) and set(
            requirement.same_name_as.supertypes
        ) <= set(card.supertypes):
            return card.name
    return None


def _subtype_stems(subtypes: Any) -> set[str]:
    """Each printed subtype lowercased, as printed, without a plural "s"
    ("Sacrifice five Treasures"), and through the subtype pool's own plural
    index for an irregular plural ("Elves" for `Elf`)."""
    stems = {s.lower() for s in subtypes} | {s.lower().removesuffix("s") for s in subtypes}
    return stems | {c for c in (canonical_subtype(s) for s in subtypes) if c is not None}


def _cost_card(component: Any) -> Material | None:
    requirement = component.requirement
    if component.kind in (ComponentKind.DISCARD, ComponentKind.REVEAL):
        zone = Zone.HAND
    elif component.kind is ComponentKind.EXILE:
        zone = component.zone
    else:
        zone = Zone.BATTLEFIELD
    if requirement is not None and zone is Zone.BATTLEFIELD:
        for token in PREDEFINED:
            if token.lower() in _subtype_stems(requirement.subtypes):
                return Material(token, ALICE, Zone.BATTLEFIELD)
    tried = 0
    for card in _format_pool():
        if card.card_faces:
            continue
        if zone is Zone.BATTLEFIELD and not set(card.types) & _PERMANENT_TYPES:
            continue
        if requirement is not None:
            if requirement.types and not set(requirement.types) & set(card.types):
                continue
            # Printed plural ("Advisors") or singular - compare stems.
            wanted = {s.lower().rstrip("s") for s in requirement.subtypes} | {
                c for c in (canonical_subtype(s) for s in requirement.subtypes) if c is not None
            }
            have = {s.lower().rstrip("s") for s in card.subtypes} | {
                s.lower() for s in card.subtypes
            }
            if wanted and not wanted & have:
                continue
        tried += 1
        if tried > 12:
            return None
        scenario = _board(
            battlefield=(card.name,) if zone is Zone.BATTLEFIELD else (),
            hand=(card.name,) if zone is Zone.HAND else (),
            graveyard=(card.name,) if zone is Zone.GRAVEYARD else (),
        )
        state = _last(scenario, card.name, zone, ALICE)
        if requirement is None or requirement.why_not(state, scenario.game, ALICE) is None:
            return Material(card.name, ALICE, zone)
    return None


def _activation_board(
    case: Case, ability: ActivatedAbility, enters: bool, *, combat: bool = False
) -> tuple[PlayedScenario, CardState | None, int | None]:
    """A board with the source on the battlefield - staged, or put there
    this turn (`enters`: a planeswalker's loyalty, CR 306.5b) - and the index
    of the ability in `Game.activated_abilities` (CR 602.1)."""
    card = case.printing
    if combat and _needs_a_blocker(ability):
        # "target creature blocking or blocked by [this]" (CR 509.1g): the
        # source attacks and the opponent's first creature blocks it.
        scenario = _board(battlefield=(card.name,), step=Step.DECLARE_ATTACKERS)
        source = _source(scenario, case, ability)
        blocker = next(
            (p for p in scenario.game.permanents_controlled_by(BOB) if Type.CREATURE in p.types),
            None,
        )
        try:
            scenario.attack_with(source, defending=BOB)
            if blocker is None:
                raise _Unavailable("the opponent has no creature to block with")
            scenario.block(source, blocker)
        except (ValueError, AssertionError) as error:
            raise _Unavailable(f"combat: {error}") from error
    elif combat:
        # "target attacking or blocking creature" (CR 506.3): the
        # controller's own stock creature attacks, the source stays home -
        # and the combat moves on to the step an "Activate only during ..."
        # names (Desert's end of combat step), the attacker still attacking
        # until that step ends (CR 511.3).
        scenario = _board(battlefield=(card.name,), step=Step.DECLARE_ATTACKERS)
        scenario.attack_with(_first(scenario, "Memnite", ALICE), defending=BOB)
        scenario.no_blocks()
        window = _activation_step(ability)
        if window in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE, Step.END_OF_COMBAT):
            scenario.turn.advance_to(window)
            scenario.game.sync_priority_with_step()
        source = _source(scenario, case, ability)
    elif enters:
        scenario = _board(hand=(card.name,), step=_activation_step(ability))
        state = _last(scenario, card.name, Zone.HAND, ALICE)
        source = scenario.game.put_onto_battlefield(
            state, ALICE, transformed=_back_face(card, ability)
        )
        _prime(scenario, source, ability)
        _settle(scenario)
        while scenario.game.stack:
            scenario.game.resolve_top()
            _settle(scenario)
    else:
        scenario = _board(battlefield=(card.name,), step=_activation_step(ability))
        source = _source(scenario, case, ability)
    indexes = [
        i for i, a in enumerate(scenario.game.activated_abilities(source)) if a.text == case.text
    ]
    return scenario, source, indexes[0] if indexes else None


def _needs_a_blocker(ability: ActivatedAbility) -> bool:
    """Whether every combat-state target of the ability must be blocking
    (CR 509.1g) - only a declared block can supply one."""
    states = [r.combat_states for r in profile_for_text(ability.effect).requirements]
    return any(states) and all(CombatState.ATTACKING not in state for state in states if state)


def _activate(
    scenario: PlayedScenario, source: CardState, index: int, ability: ActivatedAbility
) -> Any:
    """Activate once (CR 602.2): announce with the first legal targets and
    the cost's chosen objects, pay mana with everything but the source, and
    put it on the stack."""
    game = scenario.game
    refusal = game.why_cannot_activate(source, index, ALICE)
    if refusal is not None:
        raise _Unavailable(f"refused: {refusal}")
    x_value = _x_for(ability)
    action = _action_for(scenario, ALICE, ActionKind.ACTIVATE, source.id, ability_index=index)
    targets = (
        _pick(scenario, action.target_slots, text=ability.effect) if action is not None else []
    )
    choices = _cost_choices(scenario, source, index, x_value, off_zone=False)
    sacrificing = choices.get("sacrificing")
    if sacrificing is None and re.search(r"sacrifice (this|~)", ability.cost.lower()):
        sacrificing = [source]
    try:
        payment = game.begin_activating(
            source,
            index,
            ALICE,
            sacrificing=sacrificing,
            discarding=choices.get("discarding"),
            exiling=choices.get("exiling"),
            revealing=choices.get("revealing"),
            tapping=choices.get("tapping"),
            x_value=x_value,
            targets=targets or None,
        )
        payment.auto_tap([p for p in game.permanents_controlled_by(ALICE) if p is not source])
        payment.pay()
        on_stack = game.activate_ability(
            source,
            index,
            ALICE,
            x_value=x_value,
            exiled_for_cost=(choices.get("exiling") or [None])[0],
            sacrificed_for_cost=sacrificing,
        )
        game.retain_priority(ALICE)
        return on_stack
    except (ValueError, AssertionError) as error:
        raise _Unavailable(f"activation refused: {error}") from error


def run_activation_case(case: Case, only: dict[str, Any] | None = None) -> Outcome:
    """`executed` (with its golden record) when one activation resolved and
    did something, `failed` otherwise. `only` replays one recorded recipe."""
    card = case.printing
    ability = _activated_ability(card, case.text)
    if ability.zone not in (None, Zone.BATTLEFIELD):
        return _run_off_zone(case, ability, only)
    tried: list[str] = []
    outcome: Outcome | None = None
    profile = profile_for_text(ability.effect)
    # "target creature ... that's attacking alone" (CR 506.5) needs combat
    # too: the one stock attacker is attacking alone.
    in_combat = any(
        r.combat_states or getattr(r, "must_be_attacking_alone", False)
        for r in profile.requirements
    ) or any(
        # "Activate only if you control an attacking ... creature" (CR 602.5b,
        # CR 508.1a): the stock attacker is attacking as it is activated.
        "attacking" in condition.lower()
        for condition in read_activation_instructions(ability.instructions).conditions
    )
    for variant in VARIANTS:
        if only is not None and variant != only["variant"]:
            continue
        _STAGING.variant, _STAGING.case = variant, case
        _STAGING.material = (
            _target_material(ability.effect)
            + _cost_material(case)
            + tuple(
                material
                for condition in read_activation_instructions(ability.instructions).conditions
                for material in (
                    _board_material(case.card, condition) + _precondition_material(condition)
                )
            )
        )
        try:
            for enters in [False, True]:
                if only is not None and enters != only["enters"]:
                    continue
                recipe = {"variant": variant, "enters": enters, "off_zone": False}
                _STAGING.board = None
                try:
                    scenario, source, index = _activation_board(
                        case, ability, enters, combat=in_combat and not enters
                    )
                except _Unavailable as unavailable:
                    tried.append(f"{variant}: {unavailable}")
                    continue
                if source is None or index is None:
                    tried.append(f"{variant}: the permanent does not list the ability")
                    continue
                _stack_material(scenario)
                _prepare(scenario, source, ability)
                _halt_here(scenario)
                game = scenario.game
                labels = golden.Labels(game)
                before = None
                if ability.mana is not None:
                    with game.board_snapshot():
                        before = golden.snapshot(game, labels)
                try:
                    on_stack = _activate(scenario, source, index, ability)
                except _Unavailable as unavailable:
                    tried.append(f"{variant}: {unavailable}")
                    continue
                _settle(scenario)
                if on_stack is None:
                    with game.board_snapshot():
                        after = golden.snapshot(game, labels)
                    delta = (
                        golden.delta(game, labels, before, after)
                        if before is not None
                        else {"players": after.players}
                    )
                    return Outcome(
                        "executed",
                        "resolved as a mana ability",
                        _golden_record(case, recipe, golden.action_view(game, labels, None), delta),
                    )
                effect, action, delta = _resolve_ours(scenario, on_stack, labels)
                if effect.did_something:
                    return Outcome(
                        "executed", repr(effect), _golden_record(case, recipe, action, delta)
                    )
                outcome = Outcome("failed", f"{variant}: resolved: {effect!r}")
        finally:
            _STAGING.variant, _STAGING.case, _STAGING.material = QUIET, None, ()
    if outcome is not None:
        return outcome
    return Outcome("failed", "; ".join(tried[-6:]))


def _off_zone_home(case: Case, ability: ActivatedAbility) -> tuple[PlayedScenario, CardState]:
    """The card where its ability functions (CR 113.6j, 113.6m): in hand, in
    the graveyard, or suspended in exile (CR 702.62a) for an ability that
    functions "only if this card is suspended"."""
    card = case.printing
    combat = any(r.combat_states for r in profile_for_text(ability.effect).requirements)
    where: dict[str, Any] = {"step": _activation_step(ability)}
    if combat:
        # "target attacking or blocking creature": during the opponent's
        # attack (CR 506.3), where such a creature exists.
        where = {"bob_battlefield": ("Memnite",), "active": BOB, "step": Step.DECLARE_ATTACKERS}
    if ability.zone is Zone.GRAVEYARD:
        scenario = _board(graveyard=(card.name,), **where)
        state = _last(scenario, card.name, Zone.GRAVEYARD, ALICE)
    else:
        scenario = _board(hand=(card.name,), **where)
        state = _last(scenario, card.name, Zone.HAND, ALICE)
    if combat:
        scenario.attack_with(_staged(scenario, "Memnite", BOB), defending=ALICE)
        scenario.no_blocks()
    if ability.zone is Zone.GRAVEYARD:
        return scenario, state
    if ability.zone is Zone.EXILE:
        action = MarkedExile.suspend(scenario.game, state, ALICE)
        payment = action.begin_paying()
        payment.auto_tap(scenario.game.permanents_controlled_by(ALICE))
        payment.pay()
        action.take()
        state = _last(scenario, card.name, Zone.EXILE, ALICE)
    return scenario, state


def _run_off_zone(
    case: Case, ability: ActivatedAbility, only: dict[str, Any] | None = None
) -> Outcome:
    """An ability that functions from a hand, a graveyard or exile,
    activated through `off_zone_activation` (the index space legal_actions'
    `ACTIVATE_OFF_ZONE` names)."""
    card = case.printing
    entries = [i for i, e in enumerate(off_zone_abilities(card)) if e.ability.text == case.text]
    if not entries:
        return Outcome("failed", "not listed among the off-zone abilities")
    index = entries[0]
    tried: list[str] = []
    for variant in (QUIET, BUSY):
        if only is not None and variant != only["variant"]:
            continue
        recipe = {"variant": variant, "enters": False, "off_zone": True}
        _STAGING.variant, _STAGING.case = variant, case
        _STAGING.material = _target_material(ability.effect) + _off_zone_cost_material(case)
        _STAGING.board = None
        try:
            scenario, state = _off_zone_home(case, ability)
            game = scenario.game
            _stack_material(scenario)
            _prepare(scenario, state, ability)
            _halt_here(scenario)
            action = _action_for(
                scenario, ALICE, ActionKind.ACTIVATE_OFF_ZONE, state.id, ability_index=index
            )
            targets = (
                _pick(scenario, action.target_slots, text=ability.effect)
                if action is not None
                else []
            )
            choices = _off_zone_choices(scenario, state, ability)
            labels = golden.Labels(game)
            try:
                activation = off_zone_activation(
                    game,
                    state,
                    ALICE,
                    index,
                    targets=targets or None,
                    sacrificing=choices.get("sacrificing"),
                    discarding=choices.get("discarding"),
                    exiling=choices.get("exiling"),
                )
                payment = activation.begin_paying()
                payment.auto_tap(game.permanents_controlled_by(ALICE))
                payment.pay()
                on_stack = activation.activate()
            except (ValueError, AssertionError) as error:
                tried.append(f"{variant}: activation refused: {error}")
                continue
            _settle(scenario)
            effect, action_record, delta = _resolve_ours(scenario, on_stack, labels)
            if effect.did_something:
                return Outcome(
                    "executed", repr(effect), _golden_record(case, recipe, action_record, delta)
                )
            tried.append(f"{variant}: resolved: {effect!r}")
        finally:
            _STAGING.variant, _STAGING.case, _STAGING.material = QUIET, None, ()
    return Outcome("failed", "; ".join(tried))


def _off_zone_pieces(ability: ActivatedAbility) -> list[tuple[str, Any]]:
    """The sacrifice/discard/exile pieces of an off-battlefield cost other than the
    card itself, as (keyword, `CostComponent`) - read by the engine's own
    `cost_component_for_phrase`."""
    pieces = []
    for part in ability.cost.split(","):
        phrase = part.strip()
        lowered = phrase.lower()
        for verb, keyword in (
            ("sacrifice", "sacrificing"),
            ("discard", "discarding"),
            ("exile", "exiling"),
        ):
            if lowered.startswith(verb) and not re.match(rf"{verb} (this|~)", lowered):
                pieces.append((keyword, cost_component_for_phrase(phrase)))
    return pieces


def _off_zone_choices(
    scenario: PlayedScenario, state: CardState, ability: ActivatedAbility
) -> dict[str, list[CardState]]:
    """The objects an off-battlefield sacrifice/discard/exile cost is paid
    with - as many as the cost counts ("Exile three artifact cards from your
    graveyard", CR 118.3) - accepted by the cost's own
    `CardRequirement.why_not`, lands last."""
    game = scenario.game
    chosen: dict[str, list[CardState]] = {}
    for keyword, component in _off_zone_pieces(ability):
        wanted = max(1, getattr(component, "required", 1) or 1)
        found = [
            candidate
            for candidate in sorted(_off_zone_pool(game, keyword, component), key=_land_last)
            if candidate is not state and _pays(component, candidate, game)
        ]
        if found:
            chosen[keyword] = found[:wanted]
    return chosen


def _land_last(candidate: CardState) -> bool:
    return candidate.card.is_land


def _off_zone_pool(game: Any, keyword: str, component: Any) -> list[CardState]:
    """Where an off-battlefield cost piece's objects come from."""
    if keyword == "sacrificing":
        return list(game.permanents_controlled_by(ALICE))
    if keyword == "exiling":
        return list(game.player(ALICE).cards_in(getattr(component, "zone", Zone.GRAVEYARD)))
    return list(game.player(ALICE).hand)


def _pays(component: Any, candidate: CardState, game: Any) -> bool:
    requirement = getattr(component, "requirement", None)
    return requirement is None or requirement.why_not(candidate, game, ALICE) is None


def _off_zone_cost_material(case: Case) -> tuple[Material, ...]:
    """A predefined token (CR 111.10) for an off-battlefield "Sacrifice a
    Food" cost the stock board cannot pay, and real printings for a counted
    cost the stock board holds too few of ("Exile three artifact cards from
    your graveyard", CR 118.3) - the shortfall judged by the cost's own
    `CardRequirement.why_not` on the stock board."""
    ability = _activated_ability(case.printing, case.text)
    material: list[Material] = []
    for keyword, component in _off_zone_pieces(ability):
        requirement = getattr(component, "requirement", None)
        if keyword == "sacrificing" and requirement is not None:
            tokens = [
                Material(token, ALICE, Zone.BATTLEFIELD)
                for token in PREDEFINED
                if token.lower() in _subtype_stems(requirement.subtypes)
            ]
            if tokens:
                material += tokens
                continue
        wanted = getattr(component, "required", 1) or 1
        if wanted <= 1:
            continue
        have = _off_zone_stock_count(case, keyword, component)
        found = _cost_card(component) if have < wanted else None
        if found is not None:
            material += [found] * (wanted - have)
    return tuple(material)


def _off_zone_stock_count(case: Case, keyword: str, component: Any) -> int:
    """How many objects on the stock board (the source aside) pay this cost
    piece."""
    saved = _STAGING.variant, _STAGING.material
    _STAGING.variant, _STAGING.material = QUIET, ()
    try:
        game = _board().game
    finally:
        _STAGING.variant, _STAGING.material = saved
    return sum(
        1
        for candidate in _off_zone_pool(game, keyword, component)
        if not _named(candidate, case.card) and _pays(component, candidate, game)
    )


@pytest.mark.parametrize("case", _params(activation_cases()))
def test_every_handled_activation_resolves_and_does_something(
    case: Case, request: pytest.FixtureRequest
) -> None:
    outcome = run_activation_case(case)
    _record("activated", "activated", _reported(case, outcome.status))
    assert outcome.status == "executed", f"{case.card}: {case.text!r} - {outcome.detail}"
    _check_golden(case, outcome.record, request)


# ---------------------------------------------------------------------------
# The goldens (`tests/golden/`): what each executed ability did, pinned.
# ---------------------------------------------------------------------------


def _updating(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("update_golden", default=False)) or (
        os.environ.get("GOLDEN_UPDATE") == "1"
    )


def _check_golden(
    case: Case,
    record: dict[str, Any] | None,
    request: pytest.FixtureRequest,
    *,
    declined: bool = False,
) -> None:
    """Compare the live record to the case's golden - or write it, under
    `--update-golden` / `mise run golden:update`. A mismatch fails this
    case's own test id with a unified diff."""
    assert record is not None, f"{case.id}: executed without a golden record"
    family = "activated" if case.kind == "activated" else "triggered"
    path = golden.golden_path(case.card, family, case.number, declined=declined)
    text = golden.dumps(record)
    if _updating(request):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
        return
    if not path.exists():
        pytest.fail(
            f"{case.id}: no golden at {path.relative_to(golden.GOLDEN_DIR.parent.parent)} - "
            "run `mise run golden:update` and review the new file in the commit"
        )
    recorded = json.loads(path.read_text())
    if recorded != json.loads(text):
        pytest.fail(
            f"{case.id}: behaviour differs from its golden "
            "(`mise run golden:update` regenerates it once the change is intended):\n"
            + golden.diff(recorded, record, str(path.relative_to(golden.GOLDEN_DIR)))
        )


def _expected_goldens() -> set[Path]:
    paths = set()
    for case in trigger_cases():
        if case.kind not in TRIGGER_KIND_SKIPS and case.id not in KNOWN_ENGINE_GAPS:
            paths.add(golden.golden_path(case.card, "triggered", case.number))
    for case in activation_cases():
        if case.id not in KNOWN_ENGINE_GAPS:
            paths.add(golden.golden_path(case.card, "activated", case.number))
    for path in list(paths):
        # A trigger whose golden took an optional target has a second,
        # declined golden beside it.
        if path.exists() and json.loads(path.read_text())["recipe"].get("optional_targets"):
            paths.add(path.with_name(path.stem + ".no-targets.json"))
    return paths


def test_every_golden_belongs_to_a_swept_case(request: pytest.FixtureRequest) -> None:
    """A golden whose case no longer exists (a card's handled clauses were
    renumbered, a card left the pool) is stale; the update removes it."""
    expected = _expected_goldens()
    stale = sorted(p for p in golden.GOLDEN_DIR.glob("*/*.json") if p not in expected)
    if _updating(request):
        for path in stale:
            path.unlink()
            with contextlib.suppress(OSError):
                path.parent.rmdir()
        return
    assert not stale, "stale goldens (run `mise run golden:update`): " + ", ".join(
        str(p.relative_to(golden.GOLDEN_DIR)) for p in stale
    )


def case_named(card: str, family: str, number: int) -> Case:
    """The swept case a golden was recorded for."""
    cases = activation_cases() if family == "activated" else trigger_cases()
    for case in cases:
        if case.card == card and case.number == number:
            return case
    raise KeyError(f"no {family} case #{number} for {card!r} in the sweep")


def staged_board(case: Case, recipe: dict[str, Any]) -> PlayedScenario:
    """The board one recorded recipe of `case` raises its event on (the
    loader's `Golden.build_board`): the recorded board built, then the
    recipe's own staging - the source primed (its face, Class level, Aura
    attachment, counters an intervening "if" asks for), the material a
    "target spell" aims at cast - stopping before the ability is activated
    or, for a trigger, where the recipe hands the board to the driver."""
    _STAGING.halt = True
    try:
        if case.kind == "activated":
            outcome = run_activation_case(case, only=recipe)
        else:
            outcome = run_trigger_case(case, only=recipe)
    except _Halt as halted:
        return halted.scenario
    finally:
        _STAGING.halt = False
    raise AssertionError(f"{case.id}: the recorded recipe no longer stages: {outcome.detail}")


def replay(case: Case, recipe: dict[str, Any]) -> dict[str, Any]:
    """Run one recorded recipe of `case` again and return its golden record
    (the loader's `Golden.replay`)."""
    if case.kind == "activated":
        outcome = run_activation_case(case, only=recipe)
    else:
        outcome = run_trigger_case(case, only=recipe)
    if outcome.record is None:
        raise AssertionError(f"{case.id}: the recorded recipe no longer executes: {outcome.detail}")
    return json.loads(golden.dumps(outcome.record))
