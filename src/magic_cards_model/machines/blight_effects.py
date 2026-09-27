"""CR 701.68's Blight, read as an ordinary resolving *effect* rather than as a
cost.

`machines/cost.py`'s `_PHRASE_BLIGHT` already reads "Blight N" printed as a
cost component - Sting-Slinger's "{1}{R}, {T}, Blight 1: ...", Requiting
Hex's "you may blight 1" additional cost. That machinery is untouched here.
This module is the other half: the keyword appearing inside a triggered or
activated ability's own *effect* text, or a spell's - "Whenever this
creature attacks, blight 1." (forced), "you may blight N. If you
do/don't, `<effect>`." (CR 118.12's optional action), "you may blight N.
When you do, `<effect>`." (CR 603.12's reflexive twin), "each opponent
blights N"/"target opponent blights N" (someone else performs CR 701.68a),
and the "blighted creature" (CR 701.68c) reference Grub, Notorious Auntie's
own attack trigger needs.

CR 701.68a: "To 'blight N' means to put N -1/-1 counters on a creature you
control." CR 701.68b: "If a player is given the choice to blight but is
unable to put N -1/-1 counters on a creature they control (usually because
they control no creatures), they can't choose to blight." CR 701.68c: "Some
spells and abilities that instruct a player to blight refer to the 'blighted
creature.' This phrase refers to the object that the player who was
instructed to blight chose to put -1/-1 counters on when blighting." Every
CR number in this module was read with `mise run rules:find` in the session
that wrote it.

## The general optional-action shape (CR 118.12)

`_parse_may_action_then_branch_clause` is the one reader for "you may
`<action>`. If you [do|don't], `<consequence>`." - built generically (the
action and the consequence are each read through `parse_mixed_effect`,
exactly the way `_parse_may_then_if_you_do_layer_clause` in `effects.py`
already reads its own "you may `<action>`. If you do, `<layer
consequence>`." for a *continuous*-effect consequence) rather than one
regex per printed sentence, because that is the only way one reader closes
every position blight prints in this shape: Blighted Blackthorn's "you may
blight 2. If you do, you draw a card and lose 1 life.", Boggart Mischief's
and Sourbread Auntie's "you may blight `<n>`. If you do, create two 1/1 ...
tokens.", Dream Seizer's "you may blight 1. If you do, each opponent
discards a card.", Scuzzback Scrounger's "... If you do, create a Treasure
token.", Gutsplitter Gang's "you may blight 2. If you don't, you lose 3
life.", and Chaos Spewer's "you may pay `{2}`. If you don't, blight 2." -
the *action* being something other than blight, for once, with blight as
the else branch. `Mardu Woe-Reaper`'s "you may exile target creature card
from a graveyard. If you do, you gain 1 life." (Modern/Pioneer-legal,
outside this pool, outside `code/magic-cards-model-api/decks`) is
`tests/scenarios/test_blight_positions.py`'s proof this reader is the
general shape and not blight's own private one: no blight in sight.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models.card import Color, Type
from ..models.card_state import CardState, Counter
from ..models.mana import ManaCost
from ..models.player import Player
from ..models.token import token_copy_of
from ..models.zone import Zone
from ..numbers import parse_count
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import ReflexiveConsequence
from .layers import ContinuousEffect, Duration, Layer, grant_ability, only_this_incarnation
from .triggers import AbilityOnStack

if TYPE_CHECKING:
    from ..models.game import Game, StackObject
    from .effects import AbilityEffect, Effect

# --------------------------------------------------------------------------
# CR 701.68a/701.68b/701.68c: the primitive itself
# --------------------------------------------------------------------------


def _creatures_controlled_by(game: Game, username: str) -> list[CardState]:
    """Every creature `username` controls (CR 613.5's computed types, so a
    land earthbend animated into a creature counts - the same read
    `computed_permanents` gives `machines/cost.py`'s own "a creature you
    control" requirement for blight-as-a-cost)."""
    from .effects import computed_permanents

    return computed_permanents(
        game,
        (state for state in game.battlefield if state.controller == username),
        lambda characteristics: Type.CREATURE in characteristics.types,
    )


def blight(
    game: Game,
    player: Player,
    count: int,
    *,
    source_name: str,
    source_id: str | None,
) -> CardState | None:
    """CR 701.68a: put `count` -1/-1 counters on a creature `player`
    controls, chosen by `player` as the action happens. CR 701.68b: a
    `player` who controls no creature cannot choose to blight - this simply
    puts no counters anywhere and returns `None`, the same "nothing to put
    it on" outcome any other "on a creature you control" instruction has
    with an empty board.

    Returns the object CR 701.68c calls "the blighted creature" - the one
    `player` actually put counters on - or `None` when nothing was blighted
    (a non-positive count, or no creature to choose). Always asks
    `DecisionKind.CHOOSE_CARDS`, even with a single candidate, the same way
    `machines/cost.py`'s own blight-as-a-cost payment always asks (see
    `tests/scenarios/test_blight_counts.py`) - a single answer is still an
    answer, not a shortcut this module takes on the player's behalf.
    """
    if count <= 0:
        return None
    candidates = _creatures_controlled_by(game, player.username)
    if not candidates:
        return None
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"choose a creature you control to blight {count} (CR 701.68a)",
            source=source_name,
            amount=1,
            exact=True,
            cards=tuple(candidate.id for candidate in candidates),
            source_id=source_id,
        )
    )
    assert isinstance(answer, tuple)
    if not answer:
        return None
    chosen = next(candidate for candidate in candidates if candidate.id == answer[0])
    game.add_counters(chosen, Counter.MINUS_ONE, count)
    return chosen


def _may_blight(
    game: Game,
    player: Player,
    count: int,
    *,
    source_name: str,
    source_id: str | None,
) -> CardState | None:
    """CR 118.12's "may blight N" - CR 701.68b's own choice, offered only
    when `player` actually has a creature to put counters on
    (`Decision.affirmative_is_legal`), then `blight` itself. Returns the
    blighted creature, or `None` when the player declined or could not
    blight at all."""
    candidates = _creatures_controlled_by(game, player.username)
    decision = Decision(
        kind=DecisionKind.MAY,
        player=player.username,
        prompt=f"blight {count} (CR 701.68a)",
        source=source_name,
        affirmative_is_legal=bool(candidates),
        source_id=source_id,
    )
    if not game.ask(decision):
        return None
    return blight(game, player, count, source_name=source_name, source_id=source_id)


# --------------------------------------------------------------------------
# Forced "blight N." - Shadow Urchin's own attack trigger
# --------------------------------------------------------------------------

_BARE_BLIGHT_RE = re.compile(r"^blight (?P<n>\d+)\.?$", re.IGNORECASE)


def parse_bare_blight_ability_clause(text: str) -> AbilityEffect | None:
    """ "Blight N." on its own, with no "you may" (Shadow Urchin: "Whenever
    this creature attacks, blight 1.") - a mandatory CR 701.68a action, not
    CR 118.12's optional one."""
    match = _BARE_BLIGHT_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        blight(
            game,
            controller,
            count,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


def parse_bare_blight_spell_clause(text: str) -> Effect | None:
    """The spell-side twin of `parse_bare_blight_ability_clause`, for a bare
    "Blight N." sentence printed on a spell rather than an ability - the
    tail `_parse_then_if_not_main_phase_clause` reads for Dose of Dawnglow's
    "Then if it isn't your main phase, blight 2." reaches this through its
    own recursive `parse_mixed_effect_for_spell` call on that sentence
    alone."""
    match = _BARE_BLIGHT_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: Game, spell: StackObject) -> None:
        controller = game.controller_of(spell)
        blight(
            game,
            controller,
            count,
            source_name=spell.name if isinstance(spell, CardState) else spell.source_name,
            source_id=source_id_of(spell),
        )

    return effect


# --------------------------------------------------------------------------
# Someone else blights - "each opponent blights N" / "target opponent
# blights N"
# --------------------------------------------------------------------------

_EACH_OPPONENT_BLIGHTS_RE = re.compile(r"^each opponent blights (?P<n>\d+)\.?$", re.IGNORECASE)
_TARGET_OPPONENT_BLIGHTS_RE = re.compile(r"^target opponent blights (?P<n>\d+)\.?$", re.IGNORECASE)


def parse_each_opponent_blights_clause(text: str) -> AbilityEffect | None:
    """ "Each opponent blights N" (High Perfect Morcant's own Elf-tribal ETB
    trigger) - CR 701.68a/b performed by each opponent in turn, none of them
    targeted (CR 601.2c has nothing to announce here)."""
    match = _EACH_OPPONENT_BLIGHTS_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from .effects import _opponents

        controller = game.controller_of(ability)
        for opponent in _opponents(game, controller.username):
            blight(
                game,
                opponent,
                count,
                source_name=ability.source_name,
                source_id=source_id_of(ability),
            )

    return effect


def parse_target_opponent_blights_clause(text: str) -> AbilityEffect | None:
    """ "Target opponent blights N" (Champion of the Weird's own activated
    ability: "Pay 1 life, Blight 2: Target opponent blights 2. Activate only
    as a sorcery." - the cost half is already `machines/cost.py`'s "Pay N
    life" plus its own blight-as-a-cost reading; this is only the effect)."""
    from .effects import _targets_understood

    match = _TARGET_OPPONENT_BLIGHTS_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood("target opponent", allow_player_targets=True):
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if isinstance(target, Player):
                opponent = target
            elif isinstance(target, str):
                opponent = game.player(target)
            else:
                continue
            blight(
                game,
                opponent,
                count,
                source_name=ability.source_name,
                source_id=source_id_of(ability),
            )

    return effect


# --------------------------------------------------------------------------
# CR 118.12: "you may `<action>`. If you [do|don't], `<consequence>`."
# --------------------------------------------------------------------------

_MAY_ACTION_THEN_BRANCH_RE = re.compile(
    r"^you may (?P<action>.+?)\.\s*if you (?P<branch>do not|don'?t|do),\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)
_MAY_BLIGHT_ACTION_RE = re.compile(r"^blight (?P<n>\d+)$", re.IGNORECASE)
_PAY_MANA_ACTION_RE = re.compile(r"^pay (?P<mana>(?:\{[^}]+\})+)$", re.IGNORECASE)


def _as_capitalized_sentence(text: str) -> str:
    """`text` as one capitalized sentence with a single closing period - the
    same normalisation `effects._as_capitalized_sentence` gives a clause
    read out of a larger sentence before handing it back to
    `parse_mixed_effect`."""
    stripped = text.strip().rstrip(".")
    return stripped[:1].upper() + stripped[1:] + "."


def _action_runner(action_text: str) -> object | None:
    """CR 118.12's "[Do something]" half, read three ways in turn: "blight
    N" (this module's own primitive, gated by CR 701.68b's own legality
    check), "pay `<mana>`" (delegated whole to `Game.may_pay_mana_cost`,
    which already asks and pays in one call), or anything
    `parse_mixed_effect` reads, asked as a plain CR 608.2d "you may" first
    since that generic reader has no legality check of its own to offer
    (the same choice `effects._parse_may_then_if_you_do_layer_clause`
    already makes for its own generic action half). `None` when none of the
    three read `action_text` at all - the whole ability then stays unread
    rather than running an action CR 608.2d never actually offered.

    Returns a `(game, ability) -> bool` callable: whether the action was
    actually carried out, which is what "if you do"/"if you don't" tests.
    """
    from .effects import parse_mixed_effect

    stripped = action_text.strip().rstrip(".")

    blight_match = _MAY_BLIGHT_ACTION_RE.fullmatch(stripped)
    if blight_match is not None:
        count = parse_count(blight_match.group("n"))
        if count is None:
            return None

        def run_blight(game: Game, ability: AbilityOnStack) -> bool:
            controller = game.controller_of(ability)
            blighted = _may_blight(
                game,
                controller,
                count,
                source_name=ability.source_name,
                source_id=source_id_of(ability),
            )
            return blighted is not None

        return run_blight

    pay_match = _PAY_MANA_ACTION_RE.fullmatch(stripped)
    if pay_match is not None:
        cost = ManaCost.try_parse(pay_match.group("mana"))
        if cost is None:
            return None

        def run_pay(game: Game, ability: AbilityOnStack) -> bool:
            controller = game.controller_of(ability)
            return game.may_pay_mana_cost(
                controller,
                cost,
                source=ability.source_name,
                source_id=source_id_of(ability),
            )

        return run_pay

    generic = parse_mixed_effect(_as_capitalized_sentence(stripped))
    if generic is None:
        return None

    def run_generic(game: Game, ability: AbilityOnStack) -> bool:
        controller = game.controller_of(ability)
        if not game.may(
            controller,
            stripped,
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return False
        generic(game, ability)
        return True

    return run_generic


def parse_may_action_then_branch_clause(text: str) -> AbilityEffect | None:
    """`_MAY_ACTION_THEN_BRANCH_RE`'s shape - see the module docstring's own
    "general optional-action shape" section."""
    from .effects import _strip_non_effect_preamble, parse_mixed_effect

    match = _MAY_ACTION_THEN_BRANCH_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    runner = _action_runner(match.group("action"))
    if runner is None:
        return None
    positive_branch = match.group("branch").lower() == "do"
    consequence = parse_mixed_effect(_as_capitalized_sentence(match.group("consequence")))
    if consequence is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        did = runner(game, ability)
        if did == positive_branch:
            consequence(game, ability)

    return effect


# --------------------------------------------------------------------------
# CR 603.12: "you may blight N. When you do, `<consequence>`." - Warren
# Torchmaster's own combat trigger
# --------------------------------------------------------------------------

_MAY_BLIGHT_THEN_REFLEXIVE_RE = re.compile(
    r"^you may blight (?P<n>\d+)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_may_blight_then_reflexive_clause(text: str) -> AbilityEffect | None:
    """Warren Torchmaster: "you may blight 1. When you do, target creature
    gains haste until end of turn." CR 603.12: the consequence is a *second*
    triggered ability, announcing its own target once it goes on the stack -
    never the parent ability's own target, the same way
    `effects._parse_reflexive_sacrifice_clause` already reads its own "you
    may sacrifice ... When you do, ..." shape.
    """
    from .effects import _strip_non_effect_preamble, reflexive_consequence_effect

    match = _MAY_BLIGHT_THEN_REFLEXIVE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    consequence_text = match.group("consequence").strip()
    # Read once, up front, so an unreadable consequence fails the whole
    # ability closed before the blight happens (the same guard
    # `_parse_reflexive_sacrifice_clause` already applies).
    if reflexive_consequence_effect(_as_capitalized_sentence(consequence_text)) is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        blighted = _may_blight(
            game,
            controller,
            count,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
        )
        if blighted is None:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


# --------------------------------------------------------------------------
# CR 701.68c: "the blighted creature" - Grub, Notorious Auntie's own attack
# trigger
# --------------------------------------------------------------------------

_MAY_BLIGHT_THEN_COPY_BLIGHTED_CREATURE_RE = re.compile(
    r"^you may blight (?P<n>\d+)\.\s*if you do, create an? tapped and attacking token "
    r"that'?s a copy of the blighted creature(?:, except (?P<except>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_may_blight_then_copy_blighted_creature_clause(text: str) -> AbilityEffect | None:
    """Grub, Notorious Auntie: "Whenever Grub attacks, you may blight 1. If
    you do, create a tapped and attacking token that's a copy of the
    blighted creature, except it has 'At the beginning of the end step,
    sacrifice this token.'" CR 701.68c's "blighted creature" is the object
    `blight` itself just chose and returned - reused here as `token_copy_
    of`'s original, the same "except" reader (`effects._read_token_copy_
    except`) every other token-copy-with-exceptions clause in this pool
    already shares (sos-T7's `_EXILE_CARD_THEN_TOKEN_COPY_RE` and its own
    siblings), and CR 508.4's "put onto the battlefield already attacking"
    reused whole from `models.token._put_onto_the_battlefield_attacking` and
    `effects._defender_of_controllers_attack`.
    """
    from ..models.token import _put_onto_the_battlefield_attacking
    from .effects import _defender_of_controllers_attack, _read_token_copy_except

    match = _MAY_BLIGHT_THEN_COPY_BLIGHTED_CREATURE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    exception = _read_token_copy_except(match.group("except"))
    if exception is None:
        return None
    added_abilities, power, toughness, added_creature_type = exception

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        blighted = _may_blight(
            game,
            controller,
            count,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
        )
        if blighted is None:
            return
        created = token_copy_of(
            game,
            blighted,
            controller.username,
            added_abilities=added_abilities,
            power=power,
            toughness=toughness,
            added_creature_type=added_creature_type,
            tapped=True,
        )
        defender = _defender_of_controllers_attack(game, controller.username)
        for token in created:
            if token.zone is Zone.BATTLEFIELD:
                _put_onto_the_battlefield_attacking(game, token, defender)

    return effect


# --------------------------------------------------------------------------
# Sygg, Wanderwine Wisdom // Sygg, Wanderbrine Shield's own two DFC triggers
# --------------------------------------------------------------------------

_TARGET_GAINS_QUOTED_TRIGGER_UNTIL_EOT_RE = re.compile(
    r'^(?P<phrase>target .+?) gains ["“](?P<ability>.+)["”] until end of turn\.?$',
    re.IGNORECASE | re.DOTALL,
)


def parse_target_gains_quoted_ability_until_eot_clause(text: str) -> AbilityEffect | None:
    """Sygg, Wanderwine Wisdom: "target creature gains 'Whenever this
    creature deals combat damage to a player or planeswalker, draw a card'
    until end of turn." The granted-quoted-ability channel is
    `machines/layers.grant_ability` plus a hand-built `ContinuousEffect`,
    the same escape hatch `effects._parse_self_gains_quoted_ability_until_
    eot_clause` and `effects._parse_it_gains_quoted_ability_clause` already
    use for their own self-referential "gains '`<ability>`'" shapes -
    `LAYER_EFFECTS` has no row for a quoted ability at all. This is their
    *targeted* twin: nothing about granting a quoted ability is special to
    the source granting it to itself.
    """
    from .effects import _targets_understood, continuous_effects

    match = _TARGET_GAINS_QUOTED_TRIGGER_UNTIL_EOT_RE.fullmatch(text.strip())
    if match is None:
        return None
    granted_text = match.group("ability").strip()
    if not granted_text:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f'{ability.source_name}: {target.name} gains "{granted_text}" until end of turn'
                ),
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=grant_ability(granted_text),
            ),
            game,
        )

    return effect


_PROTECTION_FROM_EACH_COLOR_RE = re.compile(
    r"^(?P<phrase>target .+?) gains protection from each color until your next turn\.?$",
    re.IGNORECASE,
)


def parse_protection_from_each_color_until_your_next_turn_clause(
    text: str,
) -> AbilityEffect | None:
    """Sygg, Wanderbrine Shield: "target creature you control gains
    protection from each color until your next turn." CR 702.16h: "shorthand
    for 'protection from [quality A],' 'protection from [quality B],' and so
    on for each possible quality the listed characteristic could have; it
    behaves as multiple separate protection abilities" - granted as one
    "Protection from `<color>` and from `<color>` ..." line, CR 702.16g's own
    join word repeated across every CR 105.1 color, which is what `Game.
    _qualities_from_text` (via `_PROTECTION`, `models/game.py`) already reads
    a "protection from `<A>` and from `<B>`" grant apart into as many
    qualities as it names - the same reading Akroma's Memorial's own two-
    quality "protection from black and from red" grant already relies on.
    A bare comma join would not do: `_PROTECTION`'s own regex stops only at a
    period, so a comma-joined line reads back as a single, meaningless
    quality string instead of five real ones.
    """
    from .effects import _COLOR_NAME, _targets_understood, continuous_effects

    match = _PROTECTION_FROM_EACH_COLOR_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None
    granted_text = "Protection from " + " and from ".join(
        _COLOR_NAME[color]
        for color in (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)
    )

    def effect(game: Game, ability: AbilityOnStack) -> None:
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        controller = game.controller_of(ability).username
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{ability.source_name}: {target.name} has protection from each color",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_YOUR_NEXT_TURN,
                until_next_turn_of=controller,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=grant_ability(granted_text),
            ),
            game,
        )

    return effect


# --------------------------------------------------------------------------
# Dose of Dawnglow: "`<head>`. Then if it isn't your main phase, `<tail>`."
# --------------------------------------------------------------------------

_HEAD_THEN_IF_NOT_MAIN_PHASE_RE = re.compile(
    r"^(?P<head>.+?)\.\s*then if it (?:isn'?t|is not) your main phase,\s*(?P<tail>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_then_if_not_main_phase_clause(text: str, *, for_spell: bool) -> object | None:
    """Dose of Dawnglow: "Return target creature card from your graveyard to
    the battlefield. Then if it isn't your main phase, blight 2." CR 608.2c's
    plain sequence (`<head>`, then `<tail>`) with CR 608.2a's intervening
    *if* gating only the tail - read generically over whatever `<head>`/
    `<tail>` are through `parse_mixed_effect`/`parse_mixed_effect_for_spell`,
    so the mechanic this closes is "sequenced by CR 505.1a's own main-phase
    check", not "blight" - the tail is exactly as unconstrained as the head.
    CR 505.1: "Only the first main phase of the turn is a precombat main
    phase" - checked against `TurnMachine.step`/`.active_player` the same way
    `TurnMachine.can_cast_sorcery` already reads "your main phase".
    """
    from .effects import (
        _strip_non_effect_preamble,
        parse_mixed_effect,
        parse_mixed_effect_for_spell,
    )
    from .turn import MAIN_PHASES

    match = _HEAD_THEN_IF_NOT_MAIN_PHASE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    reader = parse_mixed_effect_for_spell if for_spell else parse_mixed_effect
    head = reader(_as_capitalized_sentence(match.group("head")))
    if head is None:
        return None
    tail = reader(_as_capitalized_sentence(match.group("tail")))
    if tail is None:
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        head(game, stack_object)
        controller = game.controller_of(stack_object)
        turn = game.turn
        in_main_phase = (
            turn is not None
            and turn.step in MAIN_PHASES
            and turn.active_player == controller.username
        )
        if in_main_phase:
            return
        tail(game, stack_object)

    return effect
