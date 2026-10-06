import re
from collections.abc import Callable
from random import Random
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...models.card import Color, Type
from ...models.card_state import (
    CardState,
    ChoiceKind,
    Counter,
    ExileAnnotation,
    ExileMarker,
    FaceDownCharacteristics,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.token import (
    TokenDefinition,
    create_tokens,
    is_token,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    ORDINAL,
    QuantitySource,
    count_pattern,
    parse_count,
    parse_ordinal,
    parse_quantity,
    quantity_pattern,
)
from .. import combat as combat_rules
from ..casting import (
    PlayAction,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    ReflexiveWhenYouDoConsequence,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._common import _OWNER_PUTS_IT_INTO_LIBRARY_TAIL, AbilityEffect, Effect, TargetedClause

#: "Scry N." - the default half of Forsaken Crossroads' own paragraph, read
#: with the same `_SCRY_RE` `parse_clause_effect` already uses for a plain
#: "scry N" clause elsewhere, so a future card sharing this shape but a
#: different N still reads.
_SCRY_N_ONLY_RE = re.compile(rf"^scry (?P<n>{COUNT})$", re.IGNORECASE)
#: "If you weren't the starting player, you may untap `<name>` instead."
#: (Forsaken Crossroads) - CR 103.8's starting player, and CR 608.2d's "you
#: may" over what the previous clause would otherwise do.
_IF_NOT_STARTING_PLAYER_MAY_UNTAP_INSTEAD_RE = re.compile(
    r"^if you weren'?t the starting player, you may untap (?P<name>[^.]+) instead$",
    re.IGNORECASE,
)


def _parse_scry_or_untap_if_not_starting_player_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Forsaken Crossroads' whole trigger: "Scry 1. If you weren't the
    starting player, you may untap Forsaken Crossroads instead." Read as one
    CR 608.2c instruction, not two independent ones: "instead" makes the
    second sentence's "you may untap" a substitute for the first sentence's
    scry, not an addition to it, so whether the scry happens at all depends
    on the answer to a question the first clause alone never asks.

    CR 103.8: "The starting player takes their first turn" - `TurnMachine.
    starting_player` is `players[0]`, fixed for the whole game. A player who
    was not dealt that seat (CR 103.4's "on the draw") is who this offers the
    substitution to; the starting player never sees the choice at all and
    simply scries.

    Ability-only (`for_spell=False`): nothing in the pool prints this shape
    on a spell, and `AbilityOnStack.source` is what finds the land to untap.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    scry_match = _SCRY_N_ONLY_RE.fullmatch(clauses[index].strip())
    if scry_match is None:
        return None
    count = parse_count(scry_match.group("n"))
    if count is None:
        return None
    untap_match = _IF_NOT_STARTING_PLAYER_MAY_UNTAP_INSTEAD_RE.fullmatch(clauses[index + 1].strip())
    if untap_match is None:
        return None
    named = untap_match.group("name").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability)
        source = ability.source(game)
        eligible = (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and named.lower() in (source.name or "").lower()
            and controller.username != game.turn.starting_player
        )
        if eligible:
            assert source is not None
            decision = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller.username,
                    prompt=f"untap {source.name} instead of scrying",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    affirmative_is_legal=True,
                )
            )
            if decision:
                # CR 701.43b's exert never applies to an effect's own untap,
                # only to the untap step itself - `Player.untap` is the one
                # normal turn-based-action caller that leaves `exert_applies`
                # at its default `True`.
                source.untap(exert_applies=False)
                return
        game.scry(controller, count, source=ability.source_name, source_id=source_id_of(ability))

    return 2, effect


# --------------------------------------------------------------------------
# Looking at the top of your library (CR 701.22, CR 701.25)
# --------------------------------------------------------------------------


def scry(count: int) -> Effect:
    """ "Scry N" (CR 701.22a).

    "To 'scry N' means to look at the top N cards of your library, then put any
    number of them on the bottom of your library in any order and the rest on top
    of your library in any order."

    A decision, and `Game.scry` is what puts it to the player (CR 608.2d). Its
    default is to keep everything on top, which is a real answer - "any number"
    includes none - rather than a refusal to answer.

    CR 701.22b is why `Game.scry` is called even for 0: "If a player is
    instructed to scry 0, no scry event occurs", and the only way a scenario can
    tell "scried 0" from "did not scry" is that no question was asked. That
    distinction is `Game.scry`'s to make, not this function's.
    """

    def effect(game: "Game", spell: CardState) -> None:
        game.scry(
            game.controller_of(spell), count, source=spell.name, source_id=source_id_of(spell)
        )

    return effect


def puts_graveyard_on_bottom_of_library(game: "Game", stack_object: "StackObject") -> None:
    """Endurance: "up to one target player puts all the cards from their
    graveyard on the bottom of their library in a random order."

    CR 115.6: "up to one target" may legally choose zero, in which case
    `game.resolve_targets` returns nothing and this does nothing - a real
    answer to "nobody was chosen," not a fizzle. When a player was chosen and
    is still in the game (CR 608.2b), every card in *their* graveyard (CR
    404.1) moves to the bottom of *their* library (CR 401.2: a library stays
    face-down and in whatever order it is put) - own graveyard included, an
    empty one just as legal a target as a full one, the same as
    `exile_target_players_graveyard`.

    "In a random order" is not CR 701.24's shuffle - that verb is reserved for
    "shuffle" itself (CR 701.24a), and this text never says it - so no shuffle
    trigger fires here, the same distinction `machines/keywords.cascade`
    already draws for "put the exiled cards on the bottom in a random order."
    The randomisation reuses `Game.shuffle_library`'s own reproducible seed
    (`shuffle_seed` plus a running counter) rather than a bare, unseeded
    `Random()`, so a scenario asserting on the resulting library order stays
    deterministic.
    """
    for target in game.resolve_targets(stack_object):
        if not isinstance(target, Player):
            continue
        cards = list(target.graveyard)
        if not cards:
            continue
        rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:graveyard-bottom")  # noqa: S311
        rng.shuffle(cards)
        for card_state in cards:
            target.move(card_state, Zone.LIBRARY)
        game.shuffles_performed += 1


#: "Look at the top N cards of your library. Exile one of them face down
#: and put the rest on the bottom of your library in a random order." -
#: `machines/keywords._hideaway_ability`'s own expansion of "Hideaway N"
#: (CR 702.75a), read here off that generated text with no per-card row -
#: any future card printing hideaway is covered the same way.
_HIDEAWAY_LOOK_EXILE_ONE_RE = re.compile(
    r"^look at the top (?P<n>\d+) cards of your library\. "
    r"exile one of them face down and put the rest on the bottom of your "
    r"library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_hideaway_clause(text: str) -> AbilityEffect | None:
    """`_HIDEAWAY_LOOK_EXILE_ONE_RE`'s shape (CR 702.75a).

    The exiled card is tagged `ExileMarker.HIDEAWAY`, linked back to this
    permanent's own id (`ExileAnnotation.linked_permanent_id`), so a later
    ability printed on the same card (Fight Rigging's own beginning-of-combat
    trigger) can find it again by source rather than by name. Left face down
    (`CardState.face_up = False`, CR 406.3) with no `FaceDownCharacteristics`
    of its own - hideaway is not morph, and nothing in this pool casts a
    hidden-away card face down the way CR 708 lets a morphed one be.
    """
    match = _HIDEAWAY_LOOK_EXILE_ONE_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        looked = list(player.library[:n])
        if not looked:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a card to exile face down",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(state.id for state in looked),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in looked}
        chosen = by_id[chosen_ids[0]]
        rest = [state for state in looked if state is not chosen]

        player.cards_in(Zone.LIBRARY).remove(chosen)
        chosen.move_to(Zone.EXILE)
        chosen.face_up = False
        chosen.exile_annotation = ExileAnnotation(
            marker=ExileMarker.HIDEAWAY, owner=chosen.owner, linked_permanent_id=ability.source_id
        )
        game.exile.append(chosen)

        rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:hideaway")  # noqa: S311
        rng.shuffle(rest)
        for state in rest:
            player.move(state, Zone.LIBRARY)
        if rest:
            game.shuffles_performed += 1

    return effect


#: "Put a +1/+1 counter on target creature you control. Then if you control
#: a creature with power 7 or greater, you may play the exiled card without
#: paying its mana cost." - Fight Rigging's own beginning-of-combat trigger,
#: read as one CR 608.2c instruction: the counter always happens, and only
#: then is the board rechecked (CR 608.2c's "then" orders the two parts, and
#: CR 608.2b/608.2c evaluates a mid-effect condition against the game state
#: as it exists at that point in resolution - after the counter was placed,
#: not before) for whether the free-cast permission is on offer at all. The
#: counter count and the power threshold are read through `numbers.COUNT`
#: rather than pinned to Fight Rigging's own "a" and "7", so a future hideaway
#: permanent printing a different count of either reads for free.
_HIDEAWAY_COUNTER_THEN_CONDITIONAL_FREE_CAST_RE = re.compile(
    rf"^put {count_pattern('n')} \+1/\+1 counters? on target creature you control\. "
    rf"then if you control a creature with power {count_pattern('threshold', article=False)} "
    r"or greater, "
    r"you may play the exiled card without paying its mana cost\.?$",
    re.IGNORECASE,
)


def _parse_hideaway_counter_then_conditional_free_cast_clause(text: str) -> AbilityEffect | None:
    """`_HIDEAWAY_COUNTER_THEN_CONDITIONAL_FREE_CAST_RE`'s shape - Fight
    Rigging's whole beginning-of-combat trigger (CR 122.1a's counter;
    CR 601.3's permission to play a specific card, granted here rather than
    with `Game.grant_play_permission` because the text names no duration -
    the permission exists only as this ability itself resolves).

    "The exiled card" is CR 400.7 anaphora back to hideaway's own exile
    (`ExileMarker.HIDEAWAY`, `ExileAnnotation.linked_permanent_id` pointing
    at this same source) - the *only* card this permanent could mean, since
    it is the one card hideaway ever hid.
    """
    match = _HIDEAWAY_COUNTER_THEN_CONDITIONAL_FREE_CAST_RE.fullmatch(text.strip())
    if match is None:
        return None
    counters = parse_count(match.group("n"))
    threshold = parse_count(match.group("threshold"), article=False)
    if counters is None or threshold is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, Counter.PLUS_ONE, counters)

        board = game.computed_board()
        controls_big_creature = any(
            Type.CREATURE in board.of(permanent).types
            and (board.of(permanent).power or 0) >= threshold
            for permanent in game.permanents_controlled_by(ability.controller)
        )
        if not controls_big_creature:
            return

        hidden = next(
            (
                card
                for card in game.exile
                if card.exile_annotation is not None
                and card.exile_annotation.marker == ExileMarker.HIDEAWAY
                and card.exile_annotation.linked_permanent_id == ability.source_id
            ),
            None,
        )
        if hidden is None:
            return
        game.may_cast_during_resolution(
            hidden,
            ability.controller,
            prompt="play the exiled card without paying its mana cost",
            source=ability.source_name,
            source_id=source_id_of(ability),
            source_name=ability.source_name,
            rule="CR 608.2g",
            play=True,
        )

    return effect


def _put_rest_on_bottom(
    game: "Game",
    player: Player,
    rest: list[CardState],
    *,
    randomised: bool,
    source: str,
    source_id: str | None,
) -> None:
    """ "Put the rest on the bottom of your library in any order / in a random
    order" for the cards `Game.look_at_top_and_split` handed back.

    "In any order" is CR 401.4's free arrangement, asked of the owner. "In a
    random order" is nobody's arrangement and not CR 701.24a's shuffle (the
    verb is not printed, so nothing keyed off a shuffle may fire) - seeded
    off `Game.shuffle_seed` and `shuffles_performed` the way every other
    "in a random order" reader in this file is, so a replay reproduces it.
    """
    if not rest:
        return
    if randomised:
        rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:rest-{len(rest)}-bottom")  # noqa: S311
        rest = list(rest)
        rng.shuffle(rest)
        game.shuffles_performed += 1
    else:
        rest = game.ask_library_bottom_order(player, rest, source=source, source_id=source_id)
    for state in rest:
        player.library.append(state)
    # CR 701.20d for the cards put back; CR 401.2 keeps the cards above them
    # in their order.
    player.note_library_changed(placed=rest)


def _mill(game: "Game", player: Player, count: int) -> list[CardState]:
    """CR 701.17a, routed through `Game.put_into_graveyard` the way
    `Game.surveil` moves its own graveyard-bound cards - so a replacement
    effect watching a card enter a graveyard (Rest in Peace) still gets its
    say (CR 614.1a).

    Returns the cards actually milled (fewer than `count` at an empty
    library, CR 701.17a's own "as many of those cards as possible") - Grist,
    the Hunger Tide's `+1` and Tyvar, Jubilant Brawler's `-2` both act on
    *which* cards this specific mill moved, not the graveyard generally.
    """
    milled = list(player.library[:count])
    for card in milled:
        game.put_into_graveyard(card)
    game.record_count(len(milled))
    return milled


#: A mana/tap symbol run (or a bare word cost like "Sacrifice this
#: creature") followed by a colon - CR 602.1's own activated-ability
#: template ("[Cost]: [Effect]") - or a triggered ability's own leading
#: condition (CR 603.1's "When", "Whenever", or "At"). A spell's own
#: resolution text (CR 608.3) never legitimately opens a sentence either
#: way; either is only ever seen here because `effect_text` is actually a
#: *permanent's* whole raw printed text (CR 608.3a: a permanent spell has no
#: resolution to run in the first place) with a different, already
#: separately-read ability's own line embedded in it.
_EMBEDDED_ABILITY_LINE_RE = re.compile(
    r"(?:\{[^{}]*\}(?:,\s*\{[^{}]*\})*\s*:|^(?:when|whenever|at)\b)", re.IGNORECASE
)


def _looks_like_embedded_ability_line(sentence: str) -> bool:
    """Whether `sentence` reads like a different permanent ability's own
    line (`_EMBEDDED_ABILITY_LINE_RE`) rather than a genuine fragment of a
    spell's own resolution text - `_compose_layer_effect_with_remainder`'s
    guard against Ingris Stingerquill's own permanent-spell false positive
    (Kraul Harpooner's twin, one step further: there the *whole* text failed
    to parse into anything at all; here a genuine layer sentence from the
    activated ability sitting beside the spell's own printed lines is
    genuinely readable, just not this spell's).
    """
    return bool(_EMBEDDED_ABILITY_LINE_RE.search(sentence))


#: Mosswort Bridge: "You may play the exiled card without paying its mana
#: cost if creatures you control have total power 10 or greater." Not a
#: target - "the exiled card" is CR 607.1's within-one-permanent anaphora for
#: whatever `machines/keywords.py`'s own `_hideaway_effect` linked to this
#: land with `ExileMarker.IMPRINTED`, the same definite reference Ugin's
#: Labyrinth's "Return the exiled card to its owner's hand" already reads.
_HIDEAWAY_PLAY_RE = re.compile(
    r"^you may play the exiled card without paying its mana cost if creatures you control "
    r"have total power (?P<threshold>\d+) or greater\.?$",
    re.IGNORECASE,
)


def _parse_hideaway_play_clause(text: str) -> AbilityEffect | None:
    """`_HIDEAWAY_PLAY_RE`'s shape.

    CR 608.2d: "the player can't choose an option that's illegal or
    impossible" - so, like `_parse_reflexive_sacrifice_clause`'s own
    "you may" shapes, the permission is only ever granted once the printed
    condition already holds; there is nothing to grant otherwise, rather than
    a permission that would refuse to be used. Total power is read off the
    printed characteristic (`CardState.power`), the same simplification
    `Game._activation_condition_holds`'s own "Activate only if you control a
    creature with power N or greater" already makes, not the layer-computed
    board - `docs/engine-coverage.md` records this as an activated ability's
    own intervening condition rather than a layer-6 shape.
    """
    match = _HIDEAWAY_PLAY_RE.fullmatch(text.strip())
    if match is None:
        return None
    threshold = int(match.group("threshold"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        controller = game.controller_of(ability)
        # CR 613.5 twice over: which permanents are creatures is layer 4's
        # answer (an animated land is one), and each one's power is layer 7's
        # (an anthem or a characteristic-defining ability counts). One board
        # for both, so the sum is taken against a single consistent state.
        board = game.computed_board()
        total_power = sum(
            board.of(state).numeric_power
            for state in game.permanents_controlled_by(controller.username)
            if board.of(state).is_creature
        )
        if total_power < threshold:
            return
        card = game.card_imprinted_on(source.id)
        if card is None:
            return
        # "You may play the exiled card" is carried out while this ability
        # resolves (CR 608.2g), not a permission used later.
        game.may_cast_during_resolution(
            card,
            controller.username,
            prompt="play the exiled card without paying its mana cost",
            source=source.name,
            source_id=source_id_of(ability),
            source_name=source.name,
            rule="CR 608.2g",
            play=True,
        )

    return effect


#: The Master of Lake-town's own "Whenever a player loses life, that player
#: mills that many cards." - CR 701.17a's mill, both "that player" and "that
#: many" reading CR 607.1's anaphora onto the very trigger event (the player
#: who lost life, and how much), never the ability's own controller/a printed
#: number - so this is its own clause, not `_MILL_RE`'s ordinary "(you )
#: mill(s) N cards" shape, whose `player` argument is always whoever the
#: calling context hands it rather than the event's own subject.
_THAT_PLAYER_MILLS_THAT_MANY_RE = re.compile(
    r"^that player mills that many cards?\.?$", re.IGNORECASE
)


def _parse_that_player_mills_that_many_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_THAT_PLAYER_MILLS_THAT_MANY_RE`'s shape, or `None`."""
    if for_spell:
        return None
    if _THAT_PLAYER_MILLS_THAT_MANY_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object) or stack_object.event is None:
            return
        username = stack_object.event.player
        if username is None:
            return
        count = _that_many_or_notice(
            game,
            clause,
            source_id=stack_object.source_id,
            source_name=stack_object.source_name,
            stack_object=stack_object,
        )
        if count is None or count <= 0:
            return
        _mill(game, game.player(username), count)

    return effect


def put_ability_targets_on_bottom_of_owners_library(
    game: "Game", stack_object: "StackObject"
) -> None:
    """`_PUT_TARGET_FROM_GRAVEYARD_BOTTOM_OF_LIBRARY_RE`'s effect."""
    targets = [
        target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
    ]
    if targets:
        game.put_cards_into_library(targets, to_bottom=True)


def put_ability_targets_on_top_of_owners_library(game: "Game", stack_object: "StackObject") -> None:
    """`_PUT_TARGET_FROM_GRAVEYARD_TOP_OF_LIBRARY_RE`'s effect - reused as-is
    for `_PUT_TARGET_PERMANENT_TOP_OF_OWNERS_LIBRARY_RE`'s battlefield twin
    below: `Game.put_cards_into_library` is already zone-agnostic (it raises
    CR 603.6c's own battlefield-departure event itself when a target leaves
    the battlefield on the way), so nothing here needs to change for a
    target coming off the battlefield rather than out of a graveyard."""
    targets = [
        target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
    ]
    if targets:
        game.put_cards_into_library(targets, to_bottom=False)


#: Valakut Awakening: "Put any number of cards from your hand on the bottom
#: of your library, then draw that many cards plus one." A linked quantity
#: (CR 608.2c): the draw count is not printed, it is whatever "that many" -
#: the number actually put on the bottom - turns out to be, plus one, so the
#: two halves cannot be two independent clauses.
_BOTTOM_HAND_THEN_DRAW_PLUS_ONE_RE = re.compile(
    r"^put any number of cards from your hand on the bottom of your library, "
    r"then draw that many cards plus one\.?$",
    re.IGNORECASE,
)


def _parse_bottom_hand_then_draw_plus_one_clause(text: str) -> Effect | None:
    """Valakut Awakening - see `_BOTTOM_HAND_THEN_DRAW_PLUS_ONE_RE`.

    CR 107.1c: "any number" runs zero upward, so the caster's own `CHOOSE_
    CARDS` answer (`exact=False`) may bottom nothing at all, in which case the
    spell still draws its own "plus one" card. Which cards go is CR 608.2d's
    plain choice, offered in hand order the way `discard_two_draw_two_
    create_token`'s own `CHOOSE_CARDS` question already is; putting one on the
    bottom is `Player.move`, the same call `puts_graveyard_on_bottom_of_
    library` makes for Endurance, with no shuffle (CR 701.24a's shuffle verb
    is never printed here) and no randomised order (unlike Endurance's "in a
    random order", this text names none, so the caster's own choice order is
    what lands on the bottom).
    """
    whole = _strip_non_effect_preamble(text).strip()
    if _BOTTOM_HAND_THEN_DRAW_PLUS_ONE_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        hand = list(controller.hand)
        if hand:
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="put any number of cards from your hand on the bottom of your library",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=len(hand),
                cards=tuple(state.id for state in hand),
                exact=False,
            )
            chosen_ids = game.ask(decision)
        else:
            chosen_ids = ()
        by_id = {state.id: state for state in hand}
        bottomed = [by_id[card_id] for card_id in chosen_ids]
        for state in bottomed:
            controller.move(state, Zone.LIBRARY)
        game.draw_cards(controller.username, len(bottomed) + 1)

    return effect


#: Turntimber Symbiosis: "Look at the top seven cards of your library. You may
#: put a creature card from among them onto the battlefield. If that card has
#: mana value 3 or less, it enters with three additional +1/+1 counters on
#: it. Put the rest on the bottom of your library in a random order."
_LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_BONUS_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards? of your library\. "
    r"you may put a creature card from among them onto the battlefield\. "
    r"if that card has mana value (?P<threshold>\d+) or less, it enters with "
    rf"(?P<bonus>{COUNT}) additional \+1/\+1 counters? on it\. "
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_look_top_n_may_battlefield_creature_bonus_clause(text: str) -> Effect | None:
    """Turntimber Symbiosis - see `_LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_
    BONUS_RE`. An impulsive-look shape close to
    `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`'s "reveal
    the top four ... may put a permanent card into your hand ... put the rest
    into your graveyard" (CR 608.2d's plain "you may", `CHOOSE_CARDS` for
    *which* card among several candidates), but the destination for the kept
    card is the battlefield, not the hand, and the destination for the rest is
    the bottom of the library in a random order (CR 701.24a's shuffle verb is
    never printed here, so `Game.shuffle_library` is not called - the same
    non-shuffle randomisation `puts_graveyard_on_bottom_of_library` already
    uses for Endurance) rather than the graveyard.

    Put onto the battlefield through `Game.put_onto_battlefield` (CR 110.2a:
    no casting, so no "when you cast" trigger fires), then, only for the kept
    card and only if its own mana value is at or under the printed threshold,
    `Game.add_counters(put, Counter.PLUS_ONE, bonus)` (CR 122.1a, and CR 122.6
    for the event that route raises and a bare `CardState.add_counters` does
    not).
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_BONUS_RE.fullmatch(whole)
    if match is None:
        return None
    n = parse_count(match.group("n"))
    threshold = int(match.group("threshold"))
    bonus = parse_count(match.group("bonus"))
    if n is None or bonus is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        looked = list(controller.library[:n])
        creatures = [state for state in looked if state.is_creature]
        chosen: CardState | None = None
        if creatures and game.may(
            controller.username,
            "put a creature card onto the battlefield",
            source=spell.name,
            source_id=source_id_of(spell),
        ):
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a creature card to put onto the battlefield",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=1,
                cards=tuple(state.id for state in reversed(creatures)),
            )
            chosen_ids = game.ask(decision)
            by_id = {state.id: state for state in creatures}
            chosen = by_id[chosen_ids[0]]
        rest = [state for state in looked if state is not chosen]
        if chosen is not None:
            put = game.put_onto_battlefield(chosen, controller.username)
            if put.mana_value <= threshold:
                # `Game.add_counters`, for CR 122.6's event - see
                # `_parse_counter_on_additional_cost_card_clause`. One call for
                # the whole `bonus`, because CR 603.2c makes the instruction a
                # single occurrence however many counters it places.
                game.add_counters(put, Counter.PLUS_ONE, bonus)
        if rest:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{n}-bottom")  # noqa: S311
            rng.shuffle(rest)
            for state in rest:
                controller.move(state, Zone.LIBRARY)
            game.shuffles_performed += 1

    return effect


#: Earth's Mightiest Heroes: "Reveal the top eight cards of your library. You
#: may put a creature card from among them onto the battlefield. If this
#: spell was cast using teamwork, put any number of creature cards from
#: among them onto the battlefield instead. Put the rest into your
#: graveyard." - `_LOOK_TOP_N_MAY_BATTLEFIELD_CREATURE_BONUS_RE`'s own
#: shape (reveal instead of look, graveyard instead of library-bottom for
#: the rest), widened with `machines/teamwork.py`'s own CR 118.8b "if this
#: spell was cast using teamwork" branch: an unconditional single optional
#: pick (CR 608.2d) that becomes an unconditional CR 107.1c "any number"
#: pick once the condition holds, read generically through `condition_is_
#: readable`/`Game.condition_holds`, the same as every other printed
#: condition, not pinned to Teamwork alone.
_REVEAL_TOP_N_MAY_BATTLEFIELD_CREATURE_TEAMWORK_RE = re.compile(
    rf"^reveal the top (?P<n>{COUNT}) cards? of your library\. "
    r"you may put a creature card from among them onto the battlefield\. "
    r"if (?P<condition>[^,]+), put any number of creature cards from among them "
    r"onto the battlefield instead\. "
    r"put the rest into your graveyard\.?$",
    re.IGNORECASE,
)


def _parse_reveal_top_n_may_battlefield_creature_teamwork_clause(text: str) -> Effect | None:
    """`_REVEAL_TOP_N_MAY_BATTLEFIELD_CREATURE_TEAMWORK_RE`'s shape - see
    above. CR 701.20a: every one of the revealed cards is recorded through
    `Game.reveal` while still in the library, before any of them move.
    Whichever revealed creatures are not put onto the battlefield go to the
    graveyard (CR 608.2c's own "the rest", read off what is still left of
    `revealed` once the put-onto-battlefield half has run, not only the
    creatures - Reality Smasher's own "put the rest into your graveyard"
    twin already reads "the rest" as every card the earlier pick did not
    take, creature or not)."""

    whole = _strip_non_effect_preamble(text).strip()
    match = _REVEAL_TOP_N_MAY_BATTLEFIELD_CREATURE_TEAMWORK_RE.fullmatch(whole)
    if match is None:
        return None
    n = parse_count(match.group("n"))
    if n is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        revealed = list(controller.library[:n])
        for state in revealed:
            game.reveal(state, source=spell.name)
        creatures = [state for state in revealed if state.is_creature]
        held = game.condition_holds(controller.username, condition_text, spell)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=spell.id, source_name=spell.card.name, text=whole
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        chosen: list[CardState] = []
        if creatures and held:
            # CR 107.1c: "any number" is zero to every candidate, no
            # separate "may" gate in front of it.
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="put any number of creature cards from among them onto the battlefield",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=len(creatures),
                    exact=False,
                    cards=tuple(state.id for state in creatures),
                )
            )
            by_id = {state.id: state for state in creatures}
            chosen = [by_id[card_id] for card_id in chosen_ids]
        elif creatures and game.may(
            controller,
            "put a creature card from among them onto the battlefield",
            source=spell.name,
            source_id=source_id_of(spell),
            cards=creatures,
        ):
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="choose a creature card to put onto the battlefield",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=1,
                    exact=True,
                    cards=tuple(state.id for state in creatures),
                    default_cards=(creatures[0].id,),
                )
            )
            by_id = {state.id: state for state in creatures}
            chosen = [by_id[chosen_ids[0]]]
        chosen_ids_set = {state.id for state in chosen}
        for state in chosen:
            game.put_onto_battlefield(state, controller.username)
        for state in revealed:
            if state.id not in chosen_ids_set:
                game.put_into_graveyard(state)

    return effect


#: Goblin Charbelcher: "Reveal cards from the top of your library until you
#: reveal a land card. This artifact deals damage equal to the number of
#: nonland cards revealed this way to any target. If the revealed land card
#: was a Mountain, this artifact deals double that damage instead. Put the
#: revealed cards on the bottom of your library in any order."
#:
#: An open-ended reveal - the count is not printed anywhere, it is however
#: many cards it took to hit a land - feeding a targeted damage amount, with a
#: conditional doubling read off the card that stopped the reveal. One
#: CR 608.2c instruction across four sentences, none of which can be run
#: without the others.
_REVEAL_UNTIL_LAND_DAMAGE_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal a land card\. "
    r"this (?P<noun>\w+) deals damage equal to the number of nonland cards "
    r"revealed this way to any target\. "
    r"if the revealed land card was a (?P<doubler>[A-Za-z]+), this (?P=noun) deals "
    r"double that damage instead\. "
    r"put the revealed cards on the bottom of your library in any order\.?$",
    re.IGNORECASE,
)


def _parse_reveal_until_land_damage_clause(text: str) -> AbilityEffect | None:
    """`_REVEAL_UNTIL_LAND_DAMAGE_RE`'s shape - see above.

    CR 701.20a's reveal moves nothing; the cards stay on top of the library
    until the last sentence puts them on the bottom. Each card is recorded
    through `Game.reveal` as it is shown, and putting them on the bottom ends
    those records (CR 701.20d). A library with no land in
    it at all reveals the whole library and stops - "until" has no more cards
    to look at - and the damage is then the number of nonland cards seen,
    which is the entire library.

    The doubling is a property of *this* damage event, not a second one: the
    card says "deals double that damage instead", so one CR 120.1 damage event
    of twice the size happens, not two events. That matters to anything
    watching for damage, and to CR 615's prevention shields, which see one
    amount rather than two.

    The reveal happens before the damage, so a card that stopped the reveal is
    on the bottom of the library by the time state-based actions run - which
    is why the whole sequence is one effect and the "put the revealed cards on
    the bottom" sentence cannot be split off into a clause of its own.
    """
    match = _REVEAL_UNTIL_LAND_DAMAGE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    doubler = match.group("doubler").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        revealed: list[CardState] = []
        stopper: CardState | None = None
        for state in list(controller.library):
            game.reveal(state, source=ability.source_name)
            revealed.append(state)
            if Type.LAND in state.types:
                stopper = state
                break
        nonland = sum(1 for state in revealed if Type.LAND not in state.types)
        amount = nonland
        # CR 305.6's basic land types are subtypes, so "was a Mountain" is a
        # subtype question about the card that stopped the reveal.
        if stopper is not None and any(
            subtype.lower() == doubler for subtype in stopper.card.subtypes
        ):
            amount *= 2

        source = ability.source_or_last_known(game)
        for target in game.resolve_targets(ability):
            game.deal_damage(target, amount, source=source)

        # "In any order" is the controller's own arrangement (CR 401.4), not a
        # randomisation, so it is asked; unscripted, the revealed order stays.
        for state in game.ask_library_bottom_order(
            controller, revealed, source=ability.source_name, source_id=source_id_of(ability)
        ):
            controller.move(state, Zone.LIBRARY)

    return effect


def _reveal_until_n_of_kind(
    game: "Game",
    controller: Player,
    predicate: Callable[[CardState], bool],
    count: int,
    *,
    source: str,
) -> tuple[list[CardState], list[CardState]]:
    """Reveal cards from the top of `controller`'s library (CR 701.15a) until
    `count` of them satisfy `predicate`, or the library runs out - the
    "reveal ... until you reveal X `<kind>` cards" shape `_REVEAL_UNTIL_KIND_
    RE` already reads for a fixed "a `<kind>` card" (one), generalised to a
    resolution-time count (Aurora Awakener's and Sanar's own X).

    Returns `(matches, remainder)`: the up-to-`count` cards satisfying
    `predicate`, in the order revealed, and every other card revealed along
    the way, in the order revealed. `count <= 0` reveals nothing at all - CR
    107.1b already floors an `amount_expression` result at zero, and CR
    608.2c gives "until you reveal zero `<kind>` cards" no cards to look for.
    """
    revealed: list[CardState] = []
    matches: list[CardState] = []
    if count > 0:
        for state in list(controller.library):
            game.reveal(state, source=source)
            revealed.append(state)
            if predicate(state):
                matches.append(state)
                if len(matches) >= count:
                    break
    remainder = [state for state in revealed if state not in matches]
    return matches, remainder


def _shuffle_remainder_to_bottom(
    game: "Game", controller: Player, remainder: list["CardState"]
) -> None:
    """ "[Put] the rest on the bottom of your library in a random order" -
    `_PUT_REVEALED_CARD_REST_RANDOM_RE`'s own instruction, shared by every
    reveal-until reader in this family: the same reproducible-seed
    convention `_merge_reveal_until_kind_then_put_clauses` already uses."""
    still_in_library = [state for state in remainder if state.zone is Zone.LIBRARY]
    if not still_in_library:
        return
    rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-until-n")  # noqa: S311
    rng.shuffle(still_in_library)
    game.shuffles_performed += 1
    for state in still_in_library:
        controller.move(state, Zone.LIBRARY)


#: Aurora Awakener: "reveal cards from the top of your library until you
#: reveal X `<kind>` cards, where X is `<expr>`. Put any number of those
#: `<kind>` cards onto the battlefield, then put the rest of the revealed
#: cards on the bottom of your library in a random order." The variable-X
#: sibling of `_REVEAL_UNTIL_KIND_RE`'s own fixed "a `<kind>` card", with CR
#: 608.2d's own "any number" choice among the X found (`_LOOK_TOP_N_PUT_
#: KIND_BATTLEFIELD_RE`'s identical `DecisionKind.CHOOSE_CARDS` shape)
#: standing in for that reader's own single mandatory placement.
_REVEAL_UNTIL_X_KIND_PUT_ANY_ONTO_BATTLEFIELD_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal x "
    r"(?P<kind>[a-z]+) cards, where x is (?P<expr>.+?)\.\s*"
    r"put any number of those (?P=kind) cards onto the battlefield, then put "
    r"the rest of the revealed cards on the bottom of your library in a "
    r"random order\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_reveal_until_x_kind_put_any_onto_battlefield_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_REVEAL_UNTIL_X_KIND_PUT_ANY_ONTO_BATTLEFIELD_RE`'s shape, or `None`."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _REVEAL_UNTIL_X_KIND_PUT_ANY_ONTO_BATTLEFIELD_RE.fullmatch(whole)
    if match is None:
        return None
    kind_word = match.group("kind").lower()
    predicate = _SELECT_FROM_TOP_KINDS.get(kind_word)
    if predicate is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        source = ability.source(game)
        amount = reader(game, ability.controller, source, ability.x_value)
        matches, remainder = _reveal_until_n_of_kind(
            game, controller, predicate, amount, source=ability.source_name
        )
        if matches:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"put any number of the revealed {kind_word} cards onto the battlefield",
                    source=ability.source_name,
                    source_id=ability.source_id,
                    amount=len(matches),
                    exact=False,
                    cards=tuple(state.id for state in matches),
                    card_labels=tuple(state.name for state in matches),
                )
            )
            by_id = {state.id: state for state in matches}
            kept_ids = set()
            for card_id in chosen_ids:
                state = by_id.get(card_id)
                if state is not None:
                    game.put_onto_battlefield(state, controller.username)
                    kept_ids.add(card_id)
            remainder += [state for state in matches if state.id not in kept_ids]
        _shuffle_remainder_to_bottom(game, controller, remainder)

    return effect


#: Sanar, Innovative First-Year: "Vivid — At the beginning of your first main
#: phase, reveal cards from the top of your library until you reveal X
#: nonland cards, where X is `<expr>`. For each of those colors, you may
#: exile a card of that color from among the revealed cards. Then shuffle.
#: You may cast the exiled cards this turn." CR 505.1a's own name for the
#: precombat main phase. "For each of those colors" (CR 105.1) is every
#: distinct color among the X nonland cards found (CR 105.2c: a colorless
#: card contributes no color, so it can never be exiled this way and is
#: never a color this loop offers), one optional exile per color, each a
#: separate CR 608.2d choice among only the revealed cards of that color -
#: two revealed cards can share a color, and only one of them can answer
#: for it, the reason this is "for each color" and not "for each card".
#: "Then shuffle" (CR 701.24a's real shuffle) puts whatever the reveal did
#: not exile - every revealed card not chosen - back into the library, mixed;
#: nothing here is put on the bottom in any order, unlike Aurora Awakener's
#: own tail. The exiled cards get CR 400.11a's own "may be cast this turn"
#: permission, read the identical way `machines/casting.py` already grants
#: it for every other "exile ... you may cast [it/them] this turn" shape -
#: linked here rather than duplicated, through `link_exile_for_casting`.
_REVEAL_UNTIL_X_NONLAND_EXILE_PER_COLOR_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal x "
    r"nonland cards, where x is (?P<expr>.+?)\.\s*"
    r"for each of those colou?rs, you may exile a card of that colou?r from "
    r"among the revealed cards\.\s*then shuffle\.\s*"
    r"you may cast the exiled cards this turn\.?$",
    re.IGNORECASE | re.DOTALL,
)

_NONLAND_PREDICATE: Callable[[CardState], bool] = lambda state: Type.LAND not in state.types  # noqa: E731


def _parse_reveal_until_x_nonland_exile_per_color_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_REVEAL_UNTIL_X_NONLAND_EXILE_PER_COLOR_RE`'s shape, or `None`."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _REVEAL_UNTIL_X_NONLAND_EXILE_PER_COLOR_RE.fullmatch(whole)
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        source = ability.source(game)
        amount = reader(game, ability.controller, source, ability.x_value)
        matches, _remainder = _reveal_until_n_of_kind(
            game, controller, _NONLAND_PREDICATE, amount, source=ability.source_name
        )
        colors_found: list[Color] = sorted(
            {
                color
                for state in matches
                for color in state.card.colors
                if color is not Color.COLORLESS
            },
            key=lambda color: color.value,
        )
        exiled: list[CardState] = []
        available = list(matches)
        for color in colors_found:
            candidates = [state for state in available if color in state.card.colors]
            if not candidates:
                continue
            chosen_id = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"exile a revealed {color.value} card",
                    source=ability.source_name,
                    source_id=ability.source_id,
                    amount=1,
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                    card_labels=tuple(state.name for state in candidates),
                )
            )
            assert isinstance(chosen_id, tuple)
            if not chosen_id:
                continue
            by_id = {state.id: state for state in candidates}
            state = by_id.get(chosen_id[0])
            if state is None or state.zone is not Zone.LIBRARY:
                continue
            # CR 400.1's one shared exile zone (`game.exile_cards`, not a
            # bare `move`), the identical mover `_exile_cast_spell_or_none`'s
            # own dig-and-imprint loop already uses.
            game.exile_cards([state])
            exiled.append(state)
            available = [each for each in available if each.id != state.id]
        game.shuffle_library(controller.username)
        for state in exiled:
            # CR 601.3: "you may cast the exiled cards this turn" - the same
            # primitive Ragavan's own "you may cast that card" grants.
            game.grant_play_permission(
                state,
                controller.username,
                action=PlayAction.CAST,
                source_name=ability.source_name,
                zone=Zone.EXILE,
                until_end_of_turn=True,
            )

    return effect

    return effect


#: Atraxa, Grand Unifier's enters trigger: "reveal the top ten cards of your
#: library. For each card type, you may put a card of that type from among the
#: revealed cards into your hand. Put the rest on the bottom of your library
#: in a random order."
#:
#: One CR 608.2c instruction in three sentences, and the middle one is the
#: whole card: a *loop over card types* (CR 205.2a / CR 300.1), not a fixed
#: number of picks. Nothing else in the pool prints that shape, which is why
#: it needs its own reader rather than a wider quantity on an existing one.
_REVEAL_TOP_N_ONE_PER_CARD_TYPE_RE = re.compile(
    rf"^reveal the top (?P<n>{COUNT}) cards? of your library\. "
    r"for each card type, you may put a card of that type from among the "
    r"revealed cards into your hand\. "
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_reveal_top_n_one_per_card_type_clause(text: str) -> AbilityEffect | None:
    """`_REVEAL_TOP_N_ONE_PER_CARD_TYPE_RE`'s shape - see above.

    CR 701.20a's reveal moves nothing; each revealed card is recorded through
    `Game.reveal`, and what matters beyond that is which of them end up in
    hand and which go to the bottom (where CR 701.20d ends their records).

    **The loop is over the card types actually present among the revealed
    cards**, not over CR 300.1's full list. That is the same set of
    opportunities - a type nobody revealed offers no card to choose - and it
    avoids hard-coding a list of types the rules keep adding to. A card with
    two types (an artifact creature) is a candidate for either, and is taken
    off the table for the rest of the loop once it has been chosen: it is no
    longer "from among the revealed cards", so the artifact pick and the
    creature pick cannot both be the same card.

    Each pick is CR 608.2d's own "you may", asked once per type and only when
    that type still has a candidate left, so a player is never asked a
    question with no legal affirmative answer.

    The leftovers go to the bottom "in a random order", which is deliberately
    *not* CR 701.24a's shuffle - that verb is never printed here - so no
    shuffle happens and nothing watching for one fires. The randomisation
    reuses `Game.shuffle_library`'s reproducible seed, the same convention
    `puts_graveyard_on_bottom_of_library` already keeps.
    """
    match = _REVEAL_TOP_N_ONE_PER_CARD_TYPE_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = parse_count(match.group("n"))
    if n is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        revealed = list(controller.library[:n])
        if not revealed:
            return
        for state in revealed:
            game.reveal(state, source=ability.source_name)
        remaining = list(revealed)
        kept: list[CardState] = []
        # A stable order over the types present, so the questions are asked
        # the same way twice. CR 205.2a's own printed order is what `Type`
        # already enumerates.
        present = [
            card_type for card_type in Type if any(card_type in state.types for state in revealed)
        ]
        for card_type in present:
            candidates = [state for state in remaining if card_type in state.types]
            if not candidates:
                continue
            if not game.may(
                controller.username,
                f"put {with_indefinite_article(f'{card_type.value} card')} "
                f"from among the revealed cards into your hand",
                source=ability.source_name,
                source_id=source_id_of(ability),
            ):
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"choose {with_indefinite_article(f'{card_type.value} card')} "
                        "to put into your hand"
                    ),
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            chosen = by_id[chosen_ids[0]]
            remaining.remove(chosen)
            kept.append(chosen)

        for state in kept:
            controller.move(state, Zone.HAND)
        if remaining:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-{n}-bottom")  # noqa: S311
            rng.shuffle(remaining)
            for state in remaining:
                controller.move(state, Zone.LIBRARY)
            game.shuffles_performed += 1

    return effect


#: Getaway Barrel's own "put into a graveyard from the battlefield" trigger
#: (CR 700.4's own "dies" wording, spelled out rather than the shorthand):
#: "reveal the top thirteen cards of your library. Put a random creature card
#: from among them onto the battlefield. Put the rest on the bottom of your
#: library in a random order." The identical "reveal the top N, then decide
#: what to do with them, then bottom the rest in a random order" template
#: `_REVEAL_TOP_N_ONE_PER_CARD_TYPE_RE` already reads above, only with no
#: choice at all in the middle sentence - the printed "a random" means the
#: pick is made by chance, not by either player (`Random`, the same
#: reproducible-seed convention every other library randomisation in this
#: module keeps).
_REVEAL_TOP_N_PUT_RANDOM_KIND_RE = re.compile(
    rf"^reveal the top (?P<n>{COUNT}) cards? of your library\. "
    r"put a random (?P<kind>[a-z]+) card from among (?:them|the revealed cards) "
    r"onto the battlefield\. "
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_reveal_top_n_put_random_kind_clause(text: str) -> AbilityEffect | None:
    """`_REVEAL_TOP_N_PUT_RANDOM_KIND_RE`'s shape - see above.

    CR 701.20a's reveal moves nothing, so every one of the `n` cards is still
    in the library, in order, when the random pick and the bottoming both
    run - reading `controller.library[:n]` once, up front, the same way
    `_parse_reveal_top_n_one_per_card_type_clause` does.
    """
    match = _REVEAL_TOP_N_PUT_RANDOM_KIND_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    n = parse_count(match.group("n"))
    if n is None:
        return None
    predicate = _SELECT_FROM_TOP_KINDS.get(match.group("kind").lower())
    if predicate is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        revealed = list(controller.library[:n])
        if not revealed:
            return
        for state in revealed:
            game.reveal(state, source=ability.source_name)
        candidates = [state for state in revealed if predicate(state)]
        chosen: CardState | None = None
        if candidates:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-{n}-random-kind"
            )
            chosen = rng.choice(candidates)
            game.shuffles_performed += 1
            game.put_onto_battlefield(chosen, controller.username)
        remainder = [
            state for state in revealed if state is not chosen and state.zone is Zone.LIBRARY
        ]
        if remainder:
            rng2 = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-{n}-random-kind-rest"
            )
            rng2.shuffle(remainder)
            game.shuffles_performed += 1
            for state in remainder:
                controller.move(state, Zone.LIBRARY)

    return effect


#: ecl-T8: Grub's Command's own mode: "Target player mills five cards, then
#: puts each Goblin card milled this way into their hand." - the *same*
#: player both mills and receives (unlike `_MILL_THEN_MAY_TAKE_FROM_MILLED_
#: RE`'s family, always the resolving spell's own controller on the
#: receiving end), no "you may" at all (CR 608.2d: no choice - every
#: qualifying card among the milled ones goes), and "each" rather than "all"
#: for that same unconditional CR 608.2d shape.
_TARGET_PLAYER_MILLS_THEN_PUTS_MILLED_INTO_OWN_HAND_RE = re.compile(
    rf"^target player mills? (?P<n>{COUNT}) cards?, then puts? "
    r"(?:each|all) (?P<quality>[a-z]+(?: or [a-z]+)?) cards? milled this way "
    r"into (?:their|its) hand\.?$",
    re.IGNORECASE,
)


def _parse_target_player_mills_then_puts_milled_into_own_hand_clause(text: str) -> Effect | None:
    """`_TARGET_PLAYER_MILLS_THEN_PUTS_MILLED_INTO_OWN_HAND_RE`'s shape."""
    match = _TARGET_PLAYER_MILLS_THEN_PUTS_MILLED_INTO_OWN_HAND_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    quality_matches = _quality_matcher(match.group("quality"))

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            if not isinstance(target, Player):
                continue
            milled = _mill(game, target, count)
            for state in milled:
                if state.zone is Zone.GRAVEYARD and quality_matches(state):
                    target.move(state, Zone.HAND)

    return effect


#: Tyvar, Jubilant Brawler's `-2`, read whole: "Mill three cards, then you may
#: return a creature card with mana value 2 or less from your graveyard to
#: the battlefield." - a resolution-time choice among candidates (CR 608.2d),
#: not a "target" at all, the same shape `_bring_in_from_outside_the_game_or_
#: exile`'s `DecisionKind.CHOOSE_CARDS` already reads for Karn's `-2`.
_MILL_THEN_MAY_RETURN_CREATURE_RE = re.compile(
    rf"^mill (?P<n>{COUNT}) cards?, then you may return a creature card "
    r"with mana value (?P<max_mv>\d+) or less from your graveyard "
    r"to the battlefield\.?$",
    re.IGNORECASE,
)


def _parse_mill_then_may_return_creature_clause(text: str) -> AbilityEffect | None:
    """`_MILL_THEN_MAY_RETURN_CREATURE_RE`'s shape - Tyvar, Jubilant
    Brawler's `-2`.

    The candidate pool is read *after* the mill, so a creature this same
    resolution just put into the graveyard is itself eligible - CR 400.2's
    graveyard has no "just arrived" exception, and the sentence names no
    other timing. `Game.may` is asked only once a legal candidate actually
    exists (CR 608.2d), matching `_bring_in_from_outside_the_game_or_exile`'s
    own guard.
    """
    match = _MILL_THEN_MAY_RETURN_CREATURE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    ceiling = int(match.group("max_mv"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        _mill(game, player, count)
        candidates = [
            state
            for state in player.cards_in(Zone.GRAVEYARD)
            if Type.CREATURE in state.types and (state.card.cmc or 0) <= ceiling
        ]
        if not candidates:
            return
        if not game.may(
            player,
            f"return a creature card with mana value {ceiling} or less from your "
            f"graveyard to the battlefield",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a creature card to return to the battlefield",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = by_id[chosen_ids[0]]
        game.put_onto_battlefield(chosen, player.username)

    return effect


_SELECT_FROM_TOP_RE = re.compile(
    # CR 207.2c/207.2d: an ability word or a flavor word ("Look Around —" on
    # Scout the City's first mode) is italic flavour with no rules meaning, so
    # it is stepped over rather than read.
    r"^(?:[a-z][a-z '-]* — )?"
    rf"(?:mill (?P<mill_n>{COUNT}) cards?"
    rf"|look at the top (?P<look_n>{COUNT}) cards? of your library)\.\s*"
    # Cartographer's Survey/Deploy the Gatewatch print "put up to two ..."
    # with no "you may" at all - CR 608.2d's optionality already lives in
    # "up to"/"any number of" themselves. A bare fixed count ("a"/"an"/"one")
    # has no such built-in optionality, so it still needs the "you may" that
    # every printing pairing it with this shape carries.
    rf"(?P<may>you may )?put {quantity_pattern('n')} "
    # Either one positive kind word, or a run of CR 205.2a negations -
    # Fallaji Archaeologist's "a noncreature, nonland card", where the comma
    # is a conjunction (a card that is neither), the same De Morgan reading
    # `_quality_matcher` already documents for Narset, Parter of Veils.
    r"(?:(?P<kind>permanent|land|creature|artifact|enchantment|instant|sorcery|"
    r"planeswalker) |(?P<negated>non[a-z]+(?:, ?non[a-z]+)*) )?"
    # "from among them" and "from among the cards milled this way" name the
    # same set - the cards this clause's own first sentence just saw.
    r"cards? from among (?:them|the cards milled this way) "
    r"(?P<dest>into your hand|onto the battlefield tapped|onto the battlefield"
    r"|into your graveyard)\.\s*"
    r"(?:(?P<decline_counter>if you don't, put a \+1/\+1 counter on this creature\.\s*)"
    # Planar Genesis: "If you don't, put a card from among them into your
    # hand." - a second, mandatory take from the same seen cards.
    r"|if you don't, put (?:a|an|one) "
    r"(?:(?P<decline_kind>permanent|land|creature|artifact|enchantment|instant|sorcery|"
    r"planeswalker) )?card from among them "
    r"(?P<decline_dest>into your hand|onto the battlefield tapped|onto the battlefield"
    r"|into your graveyard)\.\s*)?"
    rf"(?:you gain (?P<life>{COUNT}) life\.\s*)?"
    r"(?:put the rest (?P<rest>on the bottom of your library in a random order"
    r"|on the bottom of your library in any order"
    r"|on the bottom of your library"
    r"|into your graveyard)\.\s*)?$",
    re.IGNORECASE,
)


def _select_from_top_runner(
    text: str,
) -> Callable[["Game", Player, str, CardState | None, str | None], None] | None:
    """Compile `_SELECT_FROM_TOP_RE`'s shape into one runner both the spell
    side and the ability side can call.

    The runner takes the controller, the asking card's name (for the decision
    prompts), and the source permanent if there is one - the last only so that
    "If you don't, put a +1/+1 counter on this creature" has something to put a
    counter on.
    """
    match = _SELECT_FROM_TOP_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    milling = match.group("mill_n") is not None
    count = parse_count(match.group("mill_n") if milling else match.group("look_n"))
    quantity = parse_quantity(match.group("n"))
    if quantity is None or quantity.source not in (QuantitySource.FIXED, QuantitySource.ANY_NUMBER):
        return None
    # A bare fixed count ("put a land card ...") with no printed "you may" is
    # CR 608.2d's *mandatory* form, which this family does not model - every
    # printing of that shape pairs it with "you may". "up to N"/"any number
    # of" carry their own optionality (CR 107.1c) and need no such prefix.
    if quantity.exact and match.group("may") is None:
        return None
    kind_word = (match.group("kind") or "").lower()
    negated = (match.group("negated") or "").lower()
    if negated:
        excluded: list[Type] = []
        for word in negated.split(","):
            card_type = _singular_card_type(word.strip().removeprefix("non"))
            if card_type is None:
                return None
            excluded.append(card_type)

        def predicate(state: CardState, excluded: tuple[Type, ...] = tuple(excluded)) -> bool:
            return not any(card_type in state.types for card_type in excluded)

        kind_word = negated
    else:
        found = _SELECT_FROM_TOP_KINDS.get(kind_word)
        if found is None:
            return None
        predicate = found
    destination = match.group("dest").lower()
    counter_when_declined = match.group("decline_counter") is not None
    decline_dest = (match.group("decline_dest") or "").lower()
    decline_kind_word = (match.group("decline_kind") or "").lower()
    decline_predicate = _SELECT_FROM_TOP_KINDS[decline_kind_word]
    decline_noun = f"{decline_kind_word} card" if decline_kind_word else "card"
    life = parse_count(match.group("life")) if match.group("life") else 0
    rest = (match.group("rest") or "").lower()
    noun = f"{kind_word} card" if kind_word else "card"
    plural_noun = f"{kind_word} cards" if kind_word else "cards"
    if quantity.source is QuantitySource.ANY_NUMBER:
        take_noun = f"any number of {plural_noun}"
    elif quantity.exact and quantity.amount == 1:
        take_noun = with_indefinite_article(noun)
    else:
        take_noun = f"up to {quantity.amount} {plural_noun}"

    def put(game: "Game", player: Player, chosen: CardState, where: str) -> None:
        if where == "into your hand":
            player.move(chosen, Zone.HAND)
        elif where == "into your graveyard":
            game.put_into_graveyard(chosen)
        else:
            # CR 110.4a's permanent card, put onto the battlefield without
            # being cast (no spell, so no cast trigger); "tapped" is a
            # property of how it enters, not a later action. A land put this
            # way is not a land played (CR 305.4).
            game.put_onto_battlefield(chosen, player.username, tapped=where.endswith("tapped"))

    def run(
        game: "Game",
        player: Player,
        source_name: str,
        source: CardState | None,
        source_id: str | None,
    ) -> None:
        # Milling moves the cards (CR 701.17a); looking changes no zone at all -
        # they stay where CR 401.2 keeps them, on top of the library, until
        # this effect moves one of them.
        seen = _mill(game, player, count) if milling else list(player.library[:count])

        # A milled card whose graveyard trip was replaced (Rest in Peace) is
        # not in the graveyard and so was never milled - CR 701.17a's mill is
        # a move *into the graveyard*, and there is nothing "among them" to
        # take. The look arm's own guard is the mirror image: a card is only a
        # candidate while it is still in the library.
        home = Zone.GRAVEYARD if milling else Zone.LIBRARY
        candidates = [state for state in seen if state.zone is home and predicate(state)]

        chosen: list[CardState] = []
        if candidates:
            if quantity.exact:
                # "you may put a/an/one <kind> card": a single optional
                # pick, gated behind the CR 608.2d "may" before naming
                # candidates - unchanged from before this family read any
                # other quantifier.
                if game.may(
                    player,
                    f"put {take_noun} from among them {destination}",
                    source=source_name,
                    source_id=source_id,
                ):
                    chosen_ids = game.ask(
                        Decision(
                            kind=DecisionKind.CHOOSE_CARDS,
                            player=player.username,
                            prompt=f"choose {take_noun} to put {destination}",
                            source=source_name,
                            amount=1,
                            cards=tuple(candidate.id for candidate in candidates),
                            source_id=source_id,
                        )
                    )
                    assert isinstance(chosen_ids, tuple)
                    by_id = {candidate.id: candidate for candidate in candidates}
                    chosen = [by_id[chosen_ids[0]]]
            else:
                # "up to N"/"any number of": CR 107.1c - zero to the
                # ceiling is one question, with no separate "may" gate.
                ceiling = (
                    len(candidates)
                    if quantity.amount is None
                    else min(quantity.amount, len(candidates))
                )
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"put {take_noun} from among them {destination}",
                        source=source_name,
                        amount=ceiling,
                        exact=False,
                        cards=tuple(candidate.id for candidate in candidates),
                        source_id=source_id,
                    )
                )
                assert isinstance(chosen_ids, tuple)
                by_id = {candidate.id: candidate for candidate in candidates}
                chosen = [by_id[card_id] for card_id in chosen_ids]

        for state in chosen:
            if state.zone is home:
                put(game, player, state, destination)

        # "If you don't, put a card from among them ..." is not a "you may":
        # when the first take was declined or had no candidate, one of the
        # seen cards still qualifying is chosen and moved (CR 608.2d).
        if not chosen and decline_dest:
            fallback = [state for state in seen if state.zone is home and decline_predicate(state)]
            if fallback:
                fallback_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"choose {with_indefinite_article(decline_noun)} to put "
                        f"{decline_dest}",
                        source=source_name,
                        amount=1,
                        cards=tuple(candidate.id for candidate in fallback),
                        default_cards=(fallback[0].id,),
                        source_id=source_id,
                    )
                )
                assert isinstance(fallback_ids, tuple)
                chosen = [next(state for state in fallback if state.id == fallback_ids[0])]
                put(game, player, chosen[0], decline_dest)

        # "If you don't" covers both branches that leave the follow-up untaken:
        # declining the may, and having no legal candidate to choose at all
        # (CR 608.2d only offers a choice that exists).
        if (
            not chosen
            and counter_when_declined
            and source is not None
            and source.zone is Zone.BATTLEFIELD
        ):
            game.add_counters(source, Counter.PLUS_ONE, 1)

        if life:
            game.gain_life(player.username, life)

        if rest and not milling:
            # Only the look arm has a "rest": the mill arm already moved every
            # card it saw into the graveyard.
            remainder = [
                state for state in seen if state not in chosen and state.zone is Zone.LIBRARY
            ]
            if rest == "into your graveyard":
                for state in remainder:
                    game.put_into_graveyard(state)
            elif remainder:
                if "random order" in rest:
                    rng = Random(  # noqa: S311
                        f"{game.shuffle_seed}:{game.shuffles_performed}:select-from-top"
                    )
                    rng.shuffle(remainder)
                    game.shuffles_performed += 1
                else:
                    # CR 401.4 lets the owner arrange cards put on the bottom
                    # together, whether or not "in any order" is printed.
                    remainder = game.ask_library_bottom_order(
                        player, remainder, source=source_name, source_id=source_id
                    )
                for state in remainder:
                    player.move(state, Zone.LIBRARY)

    return run


def _parse_select_from_top_clause(text: str) -> AbilityEffect | None:
    """The family above, on a triggered or activated ability (CR 603.3a,
    CR 602.2a): the controller is the ability's, and "this creature" is the
    permanent the ability is printed on."""
    run = _select_from_top_runner(text)
    if run is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        run(
            game,
            game.player(ability.controller),
            ability.source_name,
            ability.source(game),
            source_id_of(ability),
        )

    return effect


def _parse_select_from_top_spell_clause(text: str) -> Effect | None:
    """The same family on a spell or a spell's mode (CR 608.2c) - Scout the
    City's "Look Around". A spell is not on the battlefield, so the
    "+1/+1 counter on this creature" tail has no subject and no printing in
    the pool pairs the two; the runner is handed `None` and skips it."""
    run = _select_from_top_runner(text)
    if run is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        run(game, game.controller_of(spell), spell.name, None, source_id_of(spell))

    return effect


# --------------------------------------------------------------------------
# ecl-T8: "Look at the top X cards ..., where X is <expr>. [You may ]put any
# number of <quality> cards from among them onto the battlefield[ tapped],
# then shuffle." (CR 401.2's look, CR 701.7a's put)
# --------------------------------------------------------------------------
#
# Ajani, Outland Chaperone's `-8`: "Look at the top X cards of your library,
# where X is your life total. You may put any number of nonland permanent
# cards with mana value 3 or less from among them onto the battlefield. Then
# shuffle." and Famished Worldsire's own ETB trigger (Modern/Pioneer/
# Standard-legal, verified with `resolve_cards`): "look at the top X cards of
# your library, where X is this creature's power. Put any number of land
# cards from among them onto the battlefield tapped, then shuffle." - the
# same shape with a different X (`amount_expression`, widened above for "your
# life total"), a different quality (`_quality_matcher`, widened above for
# the "nonland " prefix) and an optional mana-value ceiling, and an optional
# "tapped". "Any number of" is CR 107.1c's own built-in optionality, so
# neither printing needs a separate "you may" gate the way a bare fixed count
# would - `_select_from_top_runner`'s own ANY_NUMBER branch is the same
# reading, just for a different destination and a variable X count that
# family's own `COUNT`-only `look_n`/`mill_n` groups cannot express.
_LOOK_TOP_X_PUT_PERMANENTS_RE = re.compile(
    r"^look at the top x cards of your library, where x is (?P<expr>.+?)\.\s*"
    r"(?:you may )?put any number of (?P<quality>[a-z]+(?: [a-z]+)*?) cards?"
    r"(?: with mana value (?P<mv>\d+) or less)?"
    r" from among them onto the battlefield(?P<tapped> tapped)?"
    r"[,.]\s*then shuffle\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_look_top_x_put_permanents_clause(text: str) -> AbilityEffect | None:
    """`_LOOK_TOP_X_PUT_PERMANENTS_RE`'s shape - see the banner above.

    The candidate pool is "them" - the cards this same instruction just
    looked at, still sitting on top of the library (CR 401.2: looking moves
    nothing) - not the whole library, so a card put onto the battlefield from
    lower in the deck is never offered. Read fresh at resolution (CR 608.2h):
    `X` is evaluated once here, off the current life total or the source's
    current power, never a value fixed when the ability was put on the stack.
    """
    match = _LOOK_TOP_X_PUT_PERMANENTS_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).strip().split())
    )
    if match is None:
        return None
    amount_reader = amount_expression(match.group("expr"))
    if amount_reader is None:
        return None
    quality_matches = _quality_matcher(match.group("quality"))
    mv_ceiling = int(match.group("mv")) if match.group("mv") else None
    tapped = match.group("tapped") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        source = ability.source(game)
        count = amount_reader(game, controller.username, source, 0)
        if count <= 0:
            return
        seen = list(controller.library[:count])
        candidates = [
            state
            for state in seen
            if quality_matches(state)
            and (mv_ceiling is None or (state.card.cmc or 0) <= mv_ceiling)
        ]
        chosen: list[CardState] = []
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="put any number of them onto the battlefield",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=len(candidates),
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            chosen = [state for card_id in chosen_ids if (state := by_id.get(card_id)) is not None]
        for state in chosen:
            if state.zone is Zone.LIBRARY:
                game.put_onto_battlefield(state, controller.username, tapped=tapped)
        # "Then shuffle." (CR 701.24a) happens regardless of what, if
        # anything, was put onto the battlefield.
        game.shuffle_library(controller.username)

    return effect


# --------------------------------------------------------------------------
# ecl-T8: "Mill N cards, then [you may ]put a[n] <quality> card [from among
# them|from your graveyard] on top of your library." (CR 701.17a's mill)
# --------------------------------------------------------------------------
#
# Lluwen, Imperfect Naturalist's ETB trigger: "mill four cards, then you may
# put a creature or land card from among the milled cards on top of your
# library." and Sequestered Stash's own activated ability (Pioneer/Modern-
# legal, verified with `resolve_cards`): "Mill five cards. Then you may put
# an artifact card from your graveyard on top of your library." - the same
# "mill, then optionally return one card to the top" shape
# `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`'s own family reads for a hand/
# battlefield destination, widened here for "on top of your library" instead,
# with two different candidate pools: "from among the milled cards"/"from
# among them" is only the cards this instruction's own mill just moved, while
# "from your graveyard" is the whole graveyard (Sequestered Stash's own
# wording), the identical pool distinction `_MILL_THEN_MAY_RETURN_CREATURE_RE`
# ("from your graveyard") draws against the "from among ..." family.
_MILL_THEN_MAY_PUT_ON_TOP_RE = re.compile(
    rf"^mill (?P<n>{COUNT}) cards?[.,]\s*then (?:you may )?put "
    r"(?:a|an) (?P<quality>[a-z]+(?: or [a-z]+)?) card "
    r"(?P<pool>from among (?:them|the milled cards)|from your graveyard) "
    r"on top of your library\.?$",
    re.IGNORECASE,
)


def _parse_mill_then_may_put_on_top_clause(text: str) -> AbilityEffect | None:
    """`_MILL_THEN_MAY_PUT_ON_TOP_RE`'s shape - see the banner above.

    CR 608.2d: with no candidate, nothing is asked; `Game.may` gates the
    optional pick the same way every other "you may put/return" family in
    this module does. `library.insert(0, ...)` plus `note_library_changed`
    is the established "put on top" idiom (`machines/effects.py`'s own
    `_explore` and `Game.put_cards_into_library`'s "not to_bottom" branch both
    do exactly this) - `Player.move` alone appends to the *bottom* (CR 401.2).
    """
    match = _MILL_THEN_MAY_PUT_ON_TOP_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    quality_matches = _quality_matcher(match.group("quality"))
    from_graveyard = match.group("pool").lower() == "from your graveyard"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        milled = _mill(game, controller, count)
        if from_graveyard:
            candidates = [state for state in controller.graveyard if quality_matches(state)]
        else:
            candidates = [
                state for state in milled if state.zone is Zone.GRAVEYARD and quality_matches(state)
            ]
        if not candidates:
            return
        if not game.may(
            controller,
            "put a card on top of your library",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a card to put on top of your library",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(state.id for state in candidates),
            )
        )
        by_id = {state.id: state for state in candidates}
        chosen = next((by_id[card_id] for card_id in chosen_ids if card_id in by_id), None)
        if chosen is None or chosen.zone is not Zone.GRAVEYARD:
            return
        controller.move(chosen, Zone.LIBRARY)
        controller.library.remove(chosen)
        controller.library.insert(0, chosen)
        controller.note_library_changed()

    return effect


#: "Look at/Reveal the top card of your library. If it's a <kind> card, [you
#: may ]put it/that card/the card <somewhere>. Otherwise, put it/that card/the
#: card <somewhere else>." (or the "If you don't put the card onto the
#: battlefield, put it <somewhere else>." else-arm) - Fecund Greenshell's own
#: "look at ... you may ... Otherwise, ..." is the narrowest member; Coiling
#: Oracle reveals instead of looking and the put is mandatory (no "you may");
#: Risen Reef looks and offers the "you may", but phrases its else-arm as an
#: anaphoric "If you don't put the card onto the battlefield" rather than a
#: bare "Otherwise"; Skyward Eye Prophets prints the identical mandatory
#: shape as Coiling Oracle on a `{T}:` activated ability instead of an enters
#: trigger. None of them choose among several candidates, so there is nothing
#: to `CHOOSE_CARDS` between - the branch is decided by the one card that
#: turns up.
#:
#: The two else-arm spellings are not interchangeable trivia: "Otherwise" is
#: the *card* failing the condition, so a declined "you may" leaves the card
#: exactly where CR 401.2/701.20b keep it, on top of the library (Fecund
#: Greenshell) - while Risen Reef's anaphoric "If you don't put the card onto
#: the battlefield, put it ..." is CR 118.12's own "[Do something]. If you
#: don't, [do something else]", so *declining* the "you may" runs that
#: else-arm immediately instead of leaving the card be. `decline_runs_else`
#: tells the two apart.
#:
#: CR 701.20a vs CR 701.20e is a real visibility split, not a wording choice:
#: "reveal" shows the card to every player, "look at" shows it only to the
#: ability's controller. `verb` picks which of `Game.reveal`/`Game.look` the
#: effect below calls.
#:
#: The kind may be a disjunction ("If it's a creature or planeswalker card" -
#: Ajani, Sleeper Agent's `+1`), met by a card of any one of the named types,
#: and the "Otherwise" arm may itself be optional ("Otherwise, you may put it
#: on the bottom of your library" - Ajani; "... you may put it into your
#: graveyard" - Nylea, Keen-Eyed's `{2}{G}`): `else_may` asks, and a decline
#: leaves the card on top of the library (CR 701.20a: revealing a card does
#: not move it). The else-arm may be absent altogether - Summon: Esper
#: Maduin's chapter I and Llanowar Empath's "If it's a creature card, put it
#: into your hand." - and then a card failing the condition simply stays on
#: top, for the same reason.
_LOOK_TOP_CARD_KIND = (
    r"(?:permanent|land|creature|artifact|enchantment|instant|sorcery|planeswalker)"
)
_LOOK_TOP_CARD_CONDITIONAL_RE = re.compile(
    r"^(?P<verb>look at|reveal) the top card of your library\. "
    rf"if it's an? (?P<kind>{_LOOK_TOP_CARD_KIND}(?: or {_LOOK_TOP_CARD_KIND})*)"
    r" card, (?P<may>you may )?put it "
    r"(?P<dest>onto the battlefield tapped|onto the battlefield|into your hand"
    r"|into your graveyard)(?:\.|$)"
    r"(?:\s*(?:otherwise, (?P<else_may>you may )?put (?:it|that card|the card)"
    r"|(?P<decline_runs_else>if you don't put the card onto the battlefield, put it)) "
    r"(?P<other>into your hand|into your graveyard|on the bottom of your library)\.?)?$",
    re.IGNORECASE,
)


#: Matter Reshaper's "reveal the top card of your library. You may put that
#: card onto the battlefield if it's a permanent card with mana value 3 or
#: less. Otherwise, put that card into your hand." - the same instruction as
#: `_LOOK_TOP_CARD_CONDITIONAL_RE` with the condition trailing the "you may"
#: instead of leading it, and an optional CR 202.3 mana value bound on the
#: kind. "Otherwise" here covers a declined "you may" as well as a card
#: failing the condition (the printing's own ruling: "If you don't put the
#: card onto the battlefield for any reason, you put the card into your
#: hand."), so it reads as `decline_runs_else`.
_LOOK_TOP_CARD_MAY_PUT_IF_RE = re.compile(
    r"^(?P<verb>look at|reveal) the top card of your library\. "
    r"(?P<may>you may )put (?:it|that card) "
    r"(?P<dest>onto the battlefield tapped|onto the battlefield) "
    rf"if it's an? (?P<kind>{_LOOK_TOP_CARD_KIND}(?: or {_LOOK_TOP_CARD_KIND})*) card"
    r"(?: with mana value (?P<mv>\d+) or (?P<cmp>less|greater))?\. "
    r"(?:otherwise|if you don't), put (?:it|that card|the card) "
    r"(?P<other>into your hand|into your graveyard|on the bottom of your library)\.?$",
    re.IGNORECASE,
)


#: "Reveal the top card of your library. If it's an `<quality>` card,
#: `<effect>`." - Iron Lad, Diverging Destiny's own `{T}` ability. A simpler
#: sibling of `_LOOK_TOP_CARD_CONDITIONAL_RE`/`_LOOK_TOP_CARD_MAY_PUT_IF_RE`
#: just above: no "put"/"otherwise" branch at all, an arbitrary trailing
#: effect instead (CR 101.3/609.3: the card stays on top either way, so
#: there is no move to make when the condition fails - "if it's a Hero
#: card" is the whole instruction).
#:
#: Widened to an optional leading "Scry `<n>`, then " (CR 701.22a) - Invasion
#: of Pyrulea's own "Scry 3, then reveal the top card of your library. If
#: it's a land or double-faced card, draw a card." and Track Down's real,
#: Modern/Pioneer-legal "Scry 3, then reveal the top card of your library.
#: If it's a creature or land card, draw a card." One CR 608.2c instruction
#: chain, read whole rather than split on the internal ", then "/". " the
#: way every other `parse_mixed_effect` clause would be - the second
#: sentence's own period (between "library." and "If it's") would otherwise
#: cut the reveal away from its own conditional, so this stays a whole-text
#: reader ahead of the ordinary splitter, exactly like its unscried sibling.
_REVEAL_TOP_CARD_IF_QUALITY_RE = re.compile(
    r"^(?:scry (?P<scry>\d+), then )?reveal the top card of your library\. if it's an? "
    r"(?P<quality>[\w' ,-]+?) card, (?P<effect>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_reveal_top_card_if_quality_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_REVEAL_TOP_CARD_IF_QUALITY_RE`'s shape, or `None`.

    The reveal is CR 701.20a's public action off the resolving spell's or
    ability's own controller's library either way - Iron Lad, Diverging
    Destiny prints the ability shape, and Track Down (Scry 3, then reveal
    the top card of your library. If it's a creature or land card, draw a
    card.) the identical template as an ordinary sorcery.
    """
    match = _REVEAL_TOP_CARD_IF_QUALITY_RE.fullmatch(text.strip())
    if match is None:
        return None
    scry_count = int(match.group("scry")) if match.group("scry") is not None else 0
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)
    consequence = _parse_mixed_clause(
        match.group("effect").strip().rstrip("."), for_spell=for_spell
    )
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        controller = game.controller_of(stack_object)
        if scry_count:
            game.scry(controller, scry_count, source=source_name, source_id=source_id)
        if not controller.library:
            return
        top = controller.library[0]
        game.reveal(top, source=source_name)
        if matches(top):
            consequence(game, stack_object)

    return effect


def _aura_host_for_entry(
    game: "Game", aura: CardState, controller: str, source_name: str, source_id: str | None
) -> "CardState | Player | None | bool":
    """CR 303.4f: an Aura entering the battlefield other than by resolving as
    an Aura spell enchants whatever its controller chooses as it enters,
    among the objects or players its enchant ability allows (CR 702.5a,
    `machines/keywords.why_cannot_enchant`). `True` for a card that is not an
    Aura (nothing to choose), `None` when nothing legal exists - the Aura
    then cannot enter at all - and otherwise the chosen host."""
    from ..keywords import why_cannot_enchant

    if "Aura" not in aura.subtypes:
        return True
    cards = [
        permanent
        for permanent in game.battlefield
        if permanent.id != aura.id and why_cannot_enchant(aura, permanent, controller, game) is None
    ]
    players = [
        player
        for player in game.players
        if why_cannot_enchant(aura, player, controller, game) is None
    ]
    if cards:
        if len(cards) == 1:
            return cards[0]
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose what {aura.name} will enchant",
                source=source_name,
                amount=1,
                cards=tuple(permanent.id for permanent in cards),
                source_id=source_id,
            )
        )
        assert isinstance(chosen, tuple)
        return next(permanent for permanent in cards if permanent.id == chosen[0])
    if players:
        if len(players) == 1:
            return players[0]
        picked = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_PLAYERS,
                player=controller,
                prompt=f"choose which player {aura.name} will enchant",
                source=source_name,
                amount=1,
                players=tuple(player.username for player in players),
                source_id=source_id,
            )
        )
        assert isinstance(picked, tuple)
        return next(player for player in players if player.username == picked[0])
    return None


#: "Look at the top card of your library. You may reveal that card[ if
#: <condition>][ and put it into your hand]. If you do, <effect>[ and put it
#: into your hand].[ If you don't reveal it, put it into your hand.]" - the
#: reveal is the choice, and the "if you do" effect reads the revealed card
#: back through "its" (CR 608.2c's anaphora onto the card this same
#: instruction showed). Omnath, Locus of All's first-main-phase trigger
#: gates the reveal on "it has three or more colored mana symbols in its mana
#: cost", adds "three mana in any combination of its colors" and puts the
#: card into hand either way; Sorin the Mirthless's `+1` has no condition,
#: puts the card into hand as part of the reveal, and "if you do, you lose
#: life equal to its mana value" - declined, the card stays on top (CR
#: 701.20b: looking moves nothing).
_LOOK_TOP_MAY_REVEAL_RE = re.compile(
    r"^look at the top card of your library\. you may reveal (?:that card|it)"
    r"(?: if (?P<condition>[^.]+?))?(?P<put_with_reveal> and put it into your hand)?\. "
    r"if you do, (?P<consequence>[^.]+?)(?P<put_after> and put it into your hand)?\."
    r"(?P<else_put> if you don't reveal it, put it into your hand\.?)?$",
    re.IGNORECASE,
)

#: CR 107.4c/107.4e/107.4f: a colored mana symbol is one with a color in it
#: - a hybrid ({R/G}), a monocolored hybrid ({2/W}) and a Phyrexian ({G/P})
#: symbol each count once (Omnath, Locus of All's own ruling counts
#: {R/G}{G}{G/W} as three).
_COLORED_SYMBOLS_CONDITION_RE = re.compile(
    rf"^it has (?P<n>{COUNT}) or more colored mana symbols in its mana cost$", re.IGNORECASE
)
_IT_IS_A_QUALITY_CONDITION_RE = re.compile(r"^it's an? (?P<quality>.+?) card$", re.IGNORECASE)
_ADD_ANY_COMBINATION_OF_ITS_COLORS_RE = re.compile(
    rf"^add (?P<n>{COUNT}) mana in any combination of its colors$", re.IGNORECASE
)
_LOSE_LIFE_EQUAL_TO_ITS_MANA_VALUE_RE = re.compile(
    r"^you lose life equal to its mana value$", re.IGNORECASE
)


def _look_top_reveal_condition(text: str) -> Callable[[CardState], bool] | None:
    """The "if <condition>" gate on the reveal, read against the looked-at card."""
    if match := _COLORED_SYMBOLS_CONDITION_RE.fullmatch(text.strip()):
        threshold = parse_count(match.group("n"))
        if threshold is None:
            return None
        return lambda state: colored_mana_symbols(state) >= threshold
    if match := _IT_IS_A_QUALITY_CONDITION_RE.fullmatch(text.strip()):
        quality = match.group("quality")
        if not _search_quality_is_readable(quality):
            return None
        return _quality_matcher(quality)
    return None


_RevealedCardEffect = Callable[["Game", AbilityOnStack, CardState], None]


def _look_top_reveal_consequence(text: str) -> _RevealedCardEffect | None:
    """The "if you do" effect, given the revealed card its "its" names."""
    if match := _ADD_ANY_COMBINATION_OF_ITS_COLORS_RE.fullmatch(text.strip()):
        count = parse_count(match.group("n"))
        if count is None:
            return None

        def add_its_colors(game: "Game", ability: AbilityOnStack, revealed: CardState) -> None:
            # CR 105.2: the revealed card's own colors; a colorless card
            # offers no color, and CR 609.3 adds nothing.
            palette = tuple(color for color in revealed.colors if color is not Color.COLORLESS)
            if palette:
                _add_mana_in_any_combination(game, ability, count, palette)

        return add_its_colors
    if _LOSE_LIFE_EQUAL_TO_ITS_MANA_VALUE_RE.fullmatch(text.strip()):

        def lose_its_mana_value(game: "Game", ability: AbilityOnStack, revealed: CardState) -> None:
            # CR 202.3: the card's mana value, read as it was revealed.
            game.lose_life(ability.controller, int(revealed.mana_value))

        return lose_its_mana_value
    if re.search(r"\b(?:it|its|that card)\b", text, re.IGNORECASE):
        return None
    plain = _parse_mixed_clause(text.strip(), for_spell=False)
    if plain is None:
        return None
    return lambda game, ability, _revealed: plain(game, ability)


def _parse_look_top_may_reveal_clause(text: str) -> AbilityEffect | None:
    """`_LOOK_TOP_MAY_REVEAL_RE`'s shape - see the banner above.

    An empty library has no top card (CR 609.3: nothing happens). The look
    (CR 701.20e) shows the card to its controller only; the reveal, when
    taken, shows it to everyone (CR 701.20a). A card that fails the condition
    cannot be revealed, so no question is asked about it at all."""
    match = _LOOK_TOP_MAY_REVEAL_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).strip().split())
    )
    if match is None:
        return None
    condition = (
        _look_top_reveal_condition(match.group("condition"))
        if match.group("condition") is not None
        else (lambda _state: True)
    )
    if condition is None:
        return None
    consequence = _look_top_reveal_consequence(match.group("consequence"))
    if consequence is None:
        return None
    put_with_reveal = match.group("put_with_reveal") is not None
    put_after = match.group("put_after") is not None
    else_put = match.group("else_put") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        if not player.library:
            return
        top = player.library[0]
        game.look(top, ability.controller, source=ability.source_name)
        revealed = condition(top) and game.may(
            player,
            f"reveal {top.name}",
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
        if revealed:
            game.reveal(top, source=ability.source_name)
            if put_with_reveal and top.zone is Zone.LIBRARY:
                player.move(top, Zone.HAND)
            consequence(game, ability, top)
            if put_after and top.zone is Zone.LIBRARY:
                player.move(top, Zone.HAND)
        elif else_put and top.zone is Zone.LIBRARY:
            player.move(top, Zone.HAND)

    return effect


#: One instruction ahead of the look/reveal - Llanowar Empath's "scry 2, then
#: reveal the top card of your library. If it's a creature card, put it into
#: your hand." CR 608.2c: the instructions are followed in the order written,
#: so the scry settles which card is on top before it is revealed.
_LEAD_THEN_LOOK_TOP_CARD_RE = re.compile(
    r"^(?P<lead>[^.,]+?)(?:, then |\.\s+)"
    r"(?P<rest>(?:look at|reveal) the top card of your library\..+)$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_look_top_card_conditional_clause(text: str) -> AbilityEffect | None:
    """`_LOOK_TOP_CARD_CONDITIONAL_RE`'s shape - Fecund Greenshell's own
    enters trigger, and Coiling Oracle's, Risen Reef's, and Skyward Eye
    Prophets's, all verified with `resolve_cards` - and
    `_LOOK_TOP_CARD_MAY_PUT_IF_RE`'s (Matter Reshaper).

    An empty library means there is no top card to look at or reveal, so
    every branch is impossible and the whole instruction is ignored (CR
    609.3's "does only as much as possible", CR 101.3's ignored impossible
    part) - no `Game.look`/`Game.reveal` call either, since CR 701.20 has
    nothing to show.

    An Aura bound for the battlefield enchants what its controller chooses
    as it enters (CR 303.4f, `_aura_host_for_entry`); with nothing legal to
    enchant it cannot be put there, and the instruction's other arm takes it.
    """
    stripped = _strip_non_effect_preamble(text).strip()
    led = _LEAD_THEN_LOOK_TOP_CARD_RE.fullmatch(stripped)
    if led is not None:
        lead = parse_mixed_effect(led.group("lead").strip())
        rest = _parse_look_top_card_conditional_clause(led.group("rest"))
        if lead is None or rest is None:
            return None

        def led_effect(game: "Game", ability: AbilityOnStack) -> None:
            lead(game, ability)
            rest(game, ability)

        return led_effect
    match = _LOOK_TOP_CARD_CONDITIONAL_RE.fullmatch(stripped)
    trailing = match is None
    if match is None:
        match = _LOOK_TOP_CARD_MAY_PUT_IF_RE.fullmatch(stripped)
    if match is None:
        return None
    kinds = [
        _SELECT_FROM_TOP_KINDS.get(word.strip())
        for word in match.group("kind").lower().split(" or ")
    ]
    if any(kind is None for kind in kinds):
        return None
    bound = int(match.group("mv")) if trailing and match.group("mv") else None
    at_most = trailing and (match.group("cmp") or "").lower() == "less"

    def predicate(state: CardState) -> bool:
        if not any(kind(state) for kind in kinds if kind is not None):
            return False
        if bound is None:
            return True
        # CR 202.3: the card's own mana value, read in the library.
        return state.mana_value <= bound if at_most else state.mana_value >= bound

    reveals_to_all = match.group("verb").lower() == "reveal"
    optional = match.group("may") is not None
    else_optional = not trailing and match.group("else_may") is not None
    decline_runs_else = trailing or match.group("decline_runs_else") is not None
    destination = match.group("dest").lower()
    otherwise = (match.group("other") or "").lower()
    noun = f"{match.group('kind').lower()} card"

    def move(
        game: "Game", player: Player, state: CardState, where: str, ability: AbilityOnStack
    ) -> bool:
        if where == "into your hand":
            player.move(state, Zone.HAND)
        elif where == "into your graveyard":
            game.put_into_graveyard(state)
        elif where == "on the bottom of your library":
            player.move(state, Zone.LIBRARY)
        else:
            host = _aura_host_for_entry(
                game, state, player.username, ability.source_name, source_id_of(ability)
            )
            if host is None:
                return False
            game.put_onto_battlefield(state, player.username, tapped=where.endswith("tapped"))
            if host is not True and state.zone is Zone.BATTLEFIELD:
                state.attach_to(host)
        return True

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        if not player.library:
            return
        top = player.library[0]
        # CR 701.20a/701.20e: showing the card is not a zone change, and it
        # still happens even down the "otherwise" branch - the card was
        # looked at or revealed before its type was ever checked.
        if reveals_to_all:
            game.reveal(top, source=ability.source_name)
        else:
            game.look(top, ability.controller, source=ability.source_name)
        if predicate(top):
            if optional:
                if game.may(
                    player,
                    f"put {with_indefinite_article(noun)} {destination}",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                ) and move(game, player, top, destination, ability):
                    return
                # CR 118.12: only the anaphoric "If you don't put the card
                # onto the battlefield" else-arm (Risen Reef) fires on a
                # decline. A bare "Otherwise" (Fecund Greenshell) is the
                # *card* failing the condition, not the player's choice, so
                # declining leaves it exactly where CR 401.2/701.20b already
                # keep it - on top of the library, untouched.
                if not decline_runs_else:
                    return
            elif move(game, player, top, destination, ability):
                return
        if not otherwise:
            return  # CR 701.20a: no else-arm - the card stays on top.
        if else_optional and not game.may(
            player,
            f"put {top.name} {otherwise}",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        move(game, player, top, otherwise, ability)

    return effect


#: Nashi, Searcher in the Dark's whole combat-damage trigger, once
#: `machines/abilities.py` has split the "Whenever Nashi deals combat damage to
#: a player," condition off: "you mill that many cards. You may put any number
#: of legendary and/or enchantment cards from among them into your hand. If you
#: put no cards into your hand this way, put a +1/+1 counter on Nashi."
#:
#: Three sentences, one paragraph, read whole because each depends on the one
#: before it and none of them can name its own subject:
#:
#: - "that many" is the damage the trigger event carries (`GameEvent.amount`),
#:   not a printed number.
#: - "from among them" is CR 400.7 anaphora back to the cards the *first*
#:   sentence actually milled - which is the whole point of DDR#833: a
#:   replacement effect that exiles them on the way to the graveyard (Leyline
#:   of the Void) leaves nothing among them to choose, so the question is never
#:   put at all (CR 608.2d: a player "can't choose an option that's illegal or
#:   impossible", and with no candidates there is no option).
#: - "no cards ... this way" is the count the *second* sentence moved, so the
#:   counter is decided by what happened, not by anything readable up front.
#:
#: `Game.put_into_graveyard` is where the replacement gets its say, and `_mill`
#: routes through it (CR 701.17a: "that player puts that many cards from the
#: top of their library into their graveyard"; CR 701.17b caps the count at the
#: library's size - "If instructed to do so, they mill as many as possible").
_MILL_THAT_MANY_THEN_TAKE_FROM_AMONG_THEM_RE = re.compile(
    r"^you mill that many cards\.\s*"
    r"you may put any number of (?P<quality>.+?) cards from among them into your hand\.\s*"
    r"if you put no cards into your hand this way, "
    rf"put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1) counters? on (?P<name>[^.]+)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_mill_that_many_then_take_from_among_them(text: str) -> AbilityEffect | None:
    """`_MILL_THAT_MANY_THEN_TAKE_FROM_AMONG_THEM_RE`'s shape - see it for what
    each sentence points back at.

    "Any number" is CR 107.1c ("that player may choose any positive number or
    zero"), so taking none is a real answer and the third sentence's counter is
    what it leads to.
    """
    match = _MILL_THAT_MANY_THEN_TAKE_FROM_AMONG_THEM_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    quality = match.group("quality").replace(" and/or ", " or ")
    matches = _quality_matcher(quality)
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        # "that many" through the shared count channel (`that_many`): the
        # damage the trigger event carried.
        count = that_many(game, ability)
        if count is None or count <= 0:
            return
        player = game.controller_of(ability)
        milled = _mill(game, player, count)
        # CR 400.7: only the cards this mill moved, and only those still in
        # the graveyard - a card the Leyline exiled on the way is not "among
        # them" any more, which is DDR#833's ruling.
        candidates = [state for state in milled if state.zone is Zone.GRAVEYARD and matches(state)]
        taken: tuple = ()
        if candidates:
            taken = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"put any number of {quality} cards into your hand",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    # CR 107.1c's "any number of": `amount` is the ceiling and
                    # any count from zero up to it is a legal answer, which is
                    # exactly what `exact=False` means.
                    amount=len(candidates),
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            for card_id in taken:
                state = by_id.get(card_id)
                if state is not None:
                    player.move(state, Zone.HAND)
        if taken:
            return
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.add_counters(source, kind, amount)

    return effect


#: "look at the top N cards of your library. You may put one of those cards
#: back on top of your library. Exile the rest." (Devourer of Destiny's
#: first-upkeep rider) and "... Put the rest into your graveyard." (Sage of
#: Days, Gurmag Nightwatch) - CR 608.2d's "you may" pick of at most one card
#: kept on top, and the remainder sent to the zone the last sentence names.
_LOOK_TOP_KEEP_ONE_ON_TOP_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards of your library\.\s*"
    r"you may put one of (?:them|those cards) back on top of your library\.\s*"
    r"(?:(?P<exile>exile the rest)|put the rest into your graveyard)\.?$",
    re.IGNORECASE,
)


def _parse_look_top_keep_one_on_top_clause(text: str) -> AbilityEffect | None:
    """`_LOOK_TOP_KEEP_ONE_ON_TOP_RE`'s shape, through `Game.look_at_top_and_
    split`: the "moved" half is the card kept on top (at most one - the card
    says "one"), so an unscripted player, whose default answer moves nothing,
    sends all of them away, which is what declining a "you may" does.

    The rest go to the one shared exile zone through `Game.exile_cards`
    (CR 400.1, CR 701.13a), or each to its owner's graveyard through
    `Game.put_into_graveyard`."""
    match = _LOOK_TOP_KEEP_ONE_ON_TOP_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"), article=False)
    if count is None:
        return None
    exiles = match.group("exile") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        kept, rest = game.look_at_top_and_split(
            player,
            count,
            source=ability.source_name,
            source_id=source_id_of(ability),
            prompt=f"look at the top {match.group('n')} cards; you may put one back on top",
            moved_label="top of your library",
            kept_label="exiled" if exiles else "into your graveyard",
            moved_amount=1,
        )
        if exiles:
            game.exile_cards(rest)
        else:
            for state in rest:
                game.put_into_graveyard(state)
        for index, state in enumerate(kept):
            player.library.insert(index, state)
        if kept:
            player.note_library_changed()  # CR 701.20d

    return effect


#: Geometer's Arthropod's whole cast-trigger effect: "look at the top X cards
#: of your library. Put one of them into your hand and the rest on the
#: bottom of your library in a random order." X here is never the ability's
#: own announced X (CR 107.3a - a triggered ability announces none) - it is
#: the *triggering* spell's own announced X (CR 202.3e), read off that
#: spell's `CastRecord.x_value` (`AbilityOnStack.event`'s own subject), the
#: cast-trigger restriction "a spell with {X} in its mana cost" is what
#: watched for in the first place (`machines/triggers.
#: _CAST_SPELL_MANA_COST_SYMBOL_RE`).
_CAST_TRIGGER_LOOK_TOP_X_TAKE_ONE_RE = re.compile(
    r"^look at the top x cards of your library\.\s*"
    r"put one of them into your hand and the rest on the bottom of your library "
    r"in a random order\.?$",
    re.IGNORECASE,
)


def _parse_cast_trigger_look_top_x_take_one_clause(effect_text: str) -> AbilityEffect | None:
    """`_CAST_TRIGGER_LOOK_TOP_X_TAKE_ONE_RE`'s shape - see the banner above.

    CR 701.20e's "look at", then a mandatory choice of one (CR 608.2d has no
    "may" printed here, unlike `_parse_look_top_lands_take_to_hand`'s own
    kicker-gated count), and the rest bottomed in a random order
    (`_bottom_in_random_order`, not a shuffle - CR 701.24a's word is never
    printed). X at 0 or less (no cast-trigger event, or the triggering spell
    somehow announced none) looks at nothing, the same as any other "top N"
    reader would for N=0.
    """
    match = _CAST_TRIGGER_LOOK_TOP_X_TAKE_ONE_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        x = _cast_trigger_x_value(game, ability) or 0
        if x <= 0:
            return
        controller = game.controller_of(ability)
        looked = list(controller.library[:x])
        if not looked:
            return
        for state in looked:
            game.look(state, controller.username, source=ability.source_name)
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="put one of the cards looked at into your hand",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(state.id for state in looked),
            )
        )
        by_id = {state.id: state for state in looked}
        taken = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        for state in taken:
            controller.move(state, Zone.HAND)
        _bottom_in_random_order(game, controller, [state for state in looked if state not in taken])

    return effect


#: "Reveal the top X cards of your library[, where X is <expr>]. You may put
#: a[n] `<quality>` permanent card with mana value X or less from among them
#: onto the battlefield. [Then shuffle the rest into your library.|Put the
#: rest on the bottom of your library in a random order.]" - Genesis Hydra's
#: own cast trigger (X is CR 107.3a's announced value on the spell itself,
#: `_cast_trigger_x_value`) and Hatchery Spider's Undergrowth twin (X is CR
#: 107.3c's self-defined "the number of creature cards in your graveyard",
#: read the same `amount_expression` way `_LOOK_TOP_X_PUT_PERMANENTS_RE`
#: already reads a self-defined X for its own "look at"/"any number of"
#: cousin of this shape). CR 701.20a's "reveal" is never CR 701.20e's "look
#: at" here - every card in this family shows the top cards to both players,
#: not just the searcher - so a real `Game.reveal` call is made for each,
#: even though nothing else about the mechanic differs from a "look" cousin.
_CAST_TRIGGER_REVEAL_TOP_X_PUT_ONE_PERMANENT_RE = re.compile(
    r"^reveal the top x cards of your library(?:, where x is (?P<expr>.+?))?\.\s*"
    r"you may put an? (?P<quality>[a-z]+(?: [a-z]+)*?) permanent card with mana value x or less "
    r"from among them onto the battlefield\.\s*"
    r"(?P<tail>then shuffle the rest into your library"
    r"|put the rest on the bottom of your library in a random order)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_cast_trigger_reveal_top_x_put_one_permanent_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_CAST_TRIGGER_REVEAL_TOP_X_PUT_ONE_PERMANENT_RE`'s shape - see the
    banner above.

    CR 608.2d's "may put a[n] `<quality>` permanent card": at most one card,
    never `_LOOK_TOP_X_PUT_PERMANENTS_RE`'s "any number of" - the established
    `Game.may` + mandatory-single-pick idiom `_parse_mill_then_may_put_on_
    top_clause` already uses for exactly this "you may put A card" phrasing.
    X at 0 or less (CR 107.3a's caster announced none, CR 107.3c's
    expression evaluates to nothing, or there is no cast-trigger event at
    all) reveals nothing, the same as any other "top N" reader at N=0 - but
    "then shuffle the rest into your library" still runs even then (Genesis
    Hydra's own Oracle ruling: the library is shuffled even when the rest is
    zero cards - CR 701.24d, "shuffle a set of objects into a library ...
    even if there are no objects in that set"), so this never skips straight
    past the tail the way the sibling "put the rest on the bottom" branch
    harmlessly could.
    """
    whole = " ".join(_strip_non_effect_preamble(effect_text).strip().split())
    match = _CAST_TRIGGER_REVEAL_TOP_X_PUT_ONE_PERMANENT_RE.fullmatch(whole)
    if match is None:
        return None
    quality_matches = _quality_matcher(match.group("quality"))
    expr = match.group("expr")
    amount_reader = amount_expression(expr) if expr else None
    if expr is not None and amount_reader is None:
        return None
    shuffle_tail = match.group("tail").lower().startswith("then shuffle")
    quality_word = match.group("quality")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        if amount_reader is not None:
            x = amount_reader(game, ability.controller, ability.source(game), 0)
        else:
            x = _cast_trigger_x_value(game, ability) or 0
        x = max(x, 0)
        revealed = list(controller.library[:x]) if x > 0 else []
        for state in revealed:
            game.reveal(state, source=ability.source_name)
        candidates = [
            state for state in revealed if quality_matches(state) and state.mana_value <= x
        ]
        chosen: CardState | None = None
        if candidates and game.may(
            controller,
            f"put a {quality_word} permanent card with mana value {x} or less onto the battlefield",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="put a card onto the battlefield",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            chosen = next((by_id[card_id] for card_id in chosen_ids if card_id in by_id), None)
        if chosen is not None and chosen.zone is Zone.LIBRARY:
            game.put_onto_battlefield(chosen, controller.username)
        rest = [state for state in revealed if state is not chosen and state.zone is Zone.LIBRARY]
        if shuffle_tail:
            # Oracle ruling (Genesis Hydra): the library is still shuffled
            # even when X is 0 or the library was already empty, so "the
            # rest" is zero cards - CR 701.24d's shuffle-of-an-empty-set
            # still counts, not gated on there being anything to reveal first.
            game.shuffle_library(controller.username)
        else:
            _bottom_in_random_order(game, controller, rest)

    return effect


#: "Reveal cards from the top of your library until you reveal X creature
#: cards. Put all creature cards revealed this way into your graveyard, then
#: put the rest on the bottom of your library in a random order." - Old
#: Stickfingers's own cast trigger. X is CR 107.3a's announced value on the
#: spell that triggered this (`_cast_trigger_x_value`), never the ability's
#: own (a triggered ability announces no X of its own). The "reveal until N
#: of a kind" mechanics (`_reveal_until_n_of_kind`) and "bottom the rest in a
#: random order" tail (`_bottom_in_random_order`) are the same primitives
#: `_merge_reveal_until_n_kind_put_onto_battlefield_clauses`'s family already
#: built for a fixed literal count; only X's source (a cast trigger's own
#: announced value, not a literal digit) and the destination (every match
#: goes to the graveyard, mandatorily, rather than a `CHOOSE_CARDS`-optional
#: battlefield placement) differ.
_CAST_TRIGGER_REVEAL_UNTIL_X_KIND_TO_GRAVEYARD_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal x (?P<kind>[a-z]+) cards\.\s*"
    r"put all (?P=kind) cards revealed this way into your graveyard,?\s*"
    r"then put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_cast_trigger_reveal_until_x_kind_to_graveyard_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_CAST_TRIGGER_REVEAL_UNTIL_X_KIND_TO_GRAVEYARD_RE`'s shape - see the
    banner above. X at 0 or less looks at nothing (CR 608.2c); a library
    with fewer than X of the named kind reveals the whole thing (CR 608.2c's
    own "looks at all of them" when an effect wants more cards than remain).
    """
    whole = " ".join(_strip_non_effect_preamble(effect_text).strip().split())
    match = _CAST_TRIGGER_REVEAL_UNTIL_X_KIND_TO_GRAVEYARD_RE.fullmatch(whole)
    if match is None:
        return None
    predicate = _SELECT_FROM_TOP_KINDS.get(match.group("kind").lower())
    if predicate is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        x = _cast_trigger_x_value(game, ability) or 0
        matches, remainder = _reveal_until_n_of_kind(
            game, controller, predicate, x, source=ability.source_name
        )
        for state in matches:
            game.put_into_graveyard(state)
        _bottom_in_random_order(game, controller, remainder)

    return effect


#: "Put each/all <qualifier> on the bottom of their owners' libraries." -
#: Terminus's whole sentence, the library twin of `_EXILE_EACH_RE` sharing its
#: qualifier grammar (`_parse_mass_destroy_predicate`): CR 205.2a's card types
#: read the same whichever zone the sweep sends the permanents to.
_PUT_EACH_ON_BOTTOM_RE = re.compile(
    r"^put (?:each|all) (?P<rest>.+?) on the bottom of their owners' libraries\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_put_each_on_bottom_clause(sentence: str) -> TargetedClause | None:
    """ "Put each/all <qualifier> on the bottom of their owners' libraries."

    One instruction, applied to a candidate set snapshotted before anything
    moves (CR 608.2f, the same snapshot `_exile_matching` takes). Each card
    goes into its own owner's library (CR 401.1, `Game.put_cards_into_
    library`), and CR 401.4 - "If an effect puts two or more cards in a
    specific position in a library at the same time, the owner of those
    cards may arrange them in any order" - is asked of each owner, for that
    owner's cards, through `Game.ask_library_bottom_order`, in APNAP order
    (CR 101.4). A token put there ceases to exist as a state-based action
    (CR 704.5d).
    """
    match = _PUT_EACH_ON_BOTTOM_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("rest"))
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        candidates = [
            permanent for permanent in list(game.battlefield) if predicate(game, permanent, source)
        ]
        by_owner: dict[str, list[CardState]] = {}
        for permanent in candidates:
            by_owner.setdefault(permanent.owner or permanent.controller or "", []).append(permanent)
        ordered: list[CardState] = []
        for player in _players_in_apnap_order(game):
            owned = by_owner.get(player.username, [])
            ordered.extend(
                game.ask_library_bottom_order(
                    player,
                    owned,
                    source=getattr(source, "name", None),
                    source_id=source_id_of(source) if source is not None else None,
                )
            )
        game.put_cards_into_library(ordered, to_bottom=True)

    return effect


# --------------------------------------------------------------------------
# Venture into the dungeon (CR 701.49)
# --------------------------------------------------------------------------

#: "venture into the dungeon" (CR 701.49a-c) and "venture into <quality>" (CR
#: 701.49d) - the resolving object's controller ventures (CR 109.5).
_VENTURE_RE = re.compile(
    r"^(?:you )?venture into (?:the dungeon|(?P<quality>[A-Z][A-Za-z' -]+?))\.?$", re.IGNORECASE
)


def _parse_venture_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Venture into the dungeon." (Veteran Dungeoneer, Dungeon Map, Bar the
    Gate) - `machines/dungeon.venture` for the resolving object's controller."""
    match = _VENTURE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quality = match.group("quality")

    def venture_effect(game: "Game", stack_object: "StackObject") -> None:
        from ..dungeon import venture

        player = game.controller_of(stack_object).username
        venture(
            game,
            player,
            source_name=stack_object.name,
            source_id=source_id_of(stack_object),
            quality=quality,
        )

    return venture_effect


#: "look at the top card of target player's/your/their library" - Mishra's
#: Bauble's first clause, ahead of its own delayed-trigger second clause -
#: or "look at the top N cards", Orcish Spy's "Look at the top three cards
#: of target player's library". CR 701.20e: "looking at a card follows the
#: same rules as revealing a card, except that the card is shown only to the
#: specified player" - so it moves nothing, and is recorded through
#: `Game.look` for `Game.known_to`, once per card.
_LOOK_AT_TOP_CARD_RE = re.compile(
    rf"^look at the top (?:card|(?P<n>{COUNT}) cards?) of "
    r"(?:target player's|your|their) library$",
    re.IGNORECASE,
)


def _parse_look_at_top_card_clause(
    clause: str,
) -> Callable[["Game", "StackObject"], None] | None:
    """`_LOOK_AT_TOP_CARD_RE`'s shape, or `None`."""
    match = _LOOK_AT_TOP_CARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = 1 if match.group("n") is None else parse_count(match.group("n"))
    if count is None:
        return None

    def look_at_top_card(game: "Game", stack_object: "StackObject") -> None:
        """The controller looks at the top `count` cards of each targeted
        player's library (CR 701.20e), or of their own for the untargeted
        "your library" wording.

        `Game.look` records each of the `count` cards with the controller as
        the only viewer. A target that is gone by resolution is refused the
        ordinary way (CR 608.2b), and CR 609.3 gives a shorter library
        whatever it has.
        """
        viewer = game.controller_of(stack_object)
        source = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        if stack_object.targets:
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
        else:
            players = [viewer]
        for player in players:
            for card in player.library[:count]:
                game.look(card, viewer.username, source=source)

    return look_at_top_card


def _look_at_target_hand(game: "Game", stack_object: "StackObject") -> None:
    """The controller looks at every card in each targeted player's hand
    (CR 701.20e), recorded through `Game.look` with the controller as the only
    viewer - the target learns nothing (CR 402.3). A target that is gone by
    resolution is refused the ordinary way (CR 608.2b)."""
    viewer = game.controller_of(stack_object)
    source = (
        stack_object.source_name if isinstance(stack_object, AbilityOnStack) else stack_object.name
    )
    for target in game.resolve_targets(stack_object):
        if isinstance(target, Player):
            for state in list(target.hand):
                game.look(state, viewer.username, source=source)


#: "Look at target opponent's hand. You may exile a nonland card from it.
#: For as long as that card remains exiled, its owner may play it. A spell
#: cast this way costs {2} more to cast." - Elite Spellbinder's own template
#: (real, Modern/Pioneer-legal), printed verbatim on Invasion of Gobakhan's
#: ETB with "this Siege" the only difference in source. CR 701.20e's private
#: look (`_look_at_target_hand`'s own reader, widened here to "opponent" as
#: well as "player"), then CR 608.2d's optional single exile scoped to a
#: stated quality, then `machines.casting.PlayPermission` (CR 601.3) handed
#: to the exiled card's *owner* - never the ability's own controller, CR
#: 108.3's ordinary distinction - with no turn-bounded duration at all
#: (`PermissionDuration.WHILE_EXILED`'s own reasoning: CR 400.7 ends it the
#: moment the card leaves exile) and, when printed, `PlayPermission.
#: cost_increase` (CR 601.2f) riding on that same grant.
_LOOK_HAND_MAY_EXILE_OWNER_MAY_PLAY_RE = re.compile(
    r"^look at target (?:opponent|player)'?s hand\.\s*"
    r"you may exile an? (?P<quality>[a-z]+) card from it\.\s*"
    r"for as long as that card remains exiled, its owner may play it\."
    r"(?:\s*a spell cast this way costs (?P<increase>(?:\{[^}]+\})+) more to cast\.)?$",
    re.IGNORECASE,
)


def _parse_look_hand_may_exile_owner_may_play_clause(text: str) -> AbilityEffect | None:
    """`_LOOK_HAND_MAY_EXILE_OWNER_MAY_PLAY_RE`'s shape, or `None`.

    Ability-only: the source is always a permanent's own printed trigger in
    the pool (Elite Spellbinder's ETB, Invasion of Gobakhan's), never a
    spell's.
    """
    match = _LOOK_HAND_MAY_EXILE_OWNER_MAY_PLAY_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    quality = match.group("quality").strip()
    if not _search_quality_is_readable(quality):
        return None
    matches_quality = _quality_matcher(quality)
    increase = ManaCost.parse(match.group("increase")) if match.group("increase") else None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_name = ability.source_name
        source_id = source_id_of(ability)
        opponent = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if opponent is None:
            return
        for state in list(opponent.hand):
            game.look(state, controller.username, source=source_name)
        candidates = [state for state in opponent.hand if matches_quality(state)]
        if not candidates:
            return
        if not game.may(
            controller,
            f"exile {with_indefinite_article(quality)} card from {opponent.username}'s hand",
            source=source_name,
            source_id=source_id,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=(
                    f"exile {with_indefinite_article(quality)} card from {opponent.username}'s hand"
                ),
                source=source_name,
                source_id=source_id,
                amount=1,
                cards=tuple(state.id for state in candidates),
                card_labels=tuple(state.name for state in candidates),
                exact=False,
            )
        )
        assert isinstance(chosen_ids, tuple)
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id[chosen_ids[0]]
        exiled = game.exile_permanent(chosen)
        if exiled.zone is not Zone.EXILE:
            return
        game.grant_play_permission(
            exiled,
            exiled.owner,
            action=PlayAction.CAST,
            source_name=source_name,
            rule="CR 601.3",
            zone=Zone.EXILE,
            until_end_of_turn=False,
            cost_increase=increase,
        )

    return effect


#: CR 701.57a: "'Discover N' means '...'" - a bare keyword action, the same
#: shape as investigate/amass above, printed only with a plain digit in the
#: pool ("discover 5", Trumpeting Carnosaur; "discover 3", Geological
#: Appraiser and Zoetic Glyph). "Discover X" or "where X is ..." shapes are
#: not read - fail closed rather than guess a value.
_DISCOVER_RE = re.compile(r"^discover (?P<n>\d+)$", re.IGNORECASE)


def _parse_discover_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Discover N." - `_DISCOVER_RE`'s shape, as one clause among however
    many the card prints around it.

    Discover targets nothing (CR 701.57a names no target) and, like amass and
    investigate above, reads only the stack object's controller and name for
    the prompt, so the same clause works identically whether it is printed on
    a triggered ability (Trumpeting Carnosaur's bare enters-the-battlefield
    trigger, Zoetic Glyph's leaves-the-battlefield one), an activated
    ability, or a spell - the intervening *if* in front of Geological
    Appraiser's own "if you cast it, discover 3" is read separately, by
    `machines/triggers.intervening_if_holds`, before this clause is ever
    reached, so it needs no special handling here.

    The real machinery is `machines.keywords.discover` - cascade's own
    exile-until/free-cast/random-bottom process, parameterised by `N` instead
    of a spell's own mana value.
    """
    match = _DISCOVER_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    n = int(match.group("n"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..keywords import discover

        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        discover(
            game,
            controller,
            n,
            source_name=source,
            source_id=source_id_of(stack_object),
        )

    return effect


#: CR 701.48a: "'Learn' means 'You may discard a card. If you do, draw a
#: card. If you didn't discard a card, you may reveal a Lesson card you own
#: from outside the game and put it into your hand.'" A bare keyword action,
#: read off the printed line rather than by card name - Divide by Zero's
#: capitalised, sentence-final "Learn." and Eyetwitch's lowercase, mid-clause
#: "learn" ("When this creature dies, learn.") are the same word in two
#: printed shapes, both matched here.
_LEARN_RE = re.compile(r"^learn$", re.IGNORECASE)


def learn(game: "Game", player: Player, source: str, *, source_id: str | None) -> None:
    """CR 701.48a, both halves.

    The discard is offered first; a player who discards draws and is done. A
    player who did not discard - declined, or had no card to discard - may
    then reveal a Lesson card (CR 205.3k's spell type) they own from outside
    the game (CR 400.11a, CR 108.3b) and put it into their hand. The reveal
    and the move are `_reveal_and_bring_into_hand`, the same tail Karn, the
    Great Creator's -2 and the Burning Wish family use, so the Lesson stays
    known to every player in that hand until it changes zones again.
    """
    if (
        player.hand
        and game.may(player, "discard a card, then draw a card", source=source, source_id=source_id)
        and _discard_cards(game, player, 1, source, source_id=source_id)
    ):
        game.draw_cards(player, 1)
        return
    lessons = player.owned_outside_the_game(_is_lesson)
    if not lessons or not game.may(
        player,
        "reveal a Lesson card you own from outside the game and put it into your hand",
        source=source,
        source_id=source_id,
    ):
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt="choose a Lesson card you own from outside the game",
            source=source,
            source_id=source_id,
            amount=1,
            cards=tuple(state.id for state in lessons),
            card_labels=tuple(state.name for state in lessons),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in lessons}
    for card_id in chosen_ids:
        _reveal_and_bring_into_hand(game, player, by_id[card_id], source)


def _is_lesson(state: CardState) -> bool:
    """CR 205.3k: Lesson is one of the spell types instants and sorceries share."""
    return any(subtype.lower() == "lesson" for subtype in state.subtypes)


def _parse_learn_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Learn." - `_LEARN_RE`'s shape, as one clause among however many the
    card prints around it.

    Learn targets nothing and names no object of its own (CR 701.48a), so -
    like amass and investigate above - the same clause works for a spell or
    an ability alike, reading only the stack object's controller.
    """
    if _LEARN_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        learn(game, game.controller_of(stack_object), source, source_id=source_id_of(stack_object))

    return effect


#: CR 701.40a: "To manifest a card, turn it face down. It becomes a 2/2
#: face-down creature card with no text, no name, no subtypes, and no mana
#: cost. Put that card onto the battlefield face down." "Manifest the top
#: card of your library." (Mastery of the Unseen, Arashin War Beast) is the
#: shape read here; CR 701.62a's "manifest dread" below reuses this function
#: rather than re-implementing CR 701.40a a second time.
_MANIFEST_TOP_CARD_RE = re.compile(
    rf"^manifest the top (?:card|{count_pattern('n')} cards) of your library$", re.IGNORECASE
)


def manifest(game: "Game", controller: str, card_state: CardState) -> CardState:
    """CR 701.40a: turn `card_state` face down and put it onto the battlefield.

    CR 708.2a's default 2/2 vanilla is what `FaceDownCharacteristics()`'s own
    empty constructor already is - the same shape `machines/casting.py` gives
    a morph or disguise spell cast face down, reused rather than duplicated.
    Turning it face down before the zone change (not after) is deliberate,
    mirroring `Casting._apply_face_down`'s own ordering: `CardState.move_to`
    does not touch `face_down_characteristics`, so setting it first is what
    keeps a caller from ever observing the card face up on the battlefield,
    even for one line.

    `card_state.manifested` is stamped `True` here - "that permanent is a
    manifested permanent for as long as it remains face down" - which is what
    lets `machines/keywords.why_cannot_turn_up_manifested`/`.manifest_turn_up_
    cost` tell this face-down object apart from a face-down morph or disguise
    spell that happens to share the identical empty characteristics, and offer
    CR 701.40b's own turn-up procedure (pay the card's mana cost) instead of
    (or, for a card that also has morph or disguise, alongside) CR 702.37e's/
    CR 702.168d's.
    """
    card_state.turn_face_down(FaceDownCharacteristics())
    card_state.manifested = True
    return game.put_onto_battlefield(card_state, controller)


def _parse_manifest_top_card_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Manifest the top card of your library." or "Manifest the top N
    cards of your library." (Ethereal Ambush) - `_MANIFEST_TOP_CARD_RE`'s
    shape, as one clause among however many the card prints around it.

    N manifests, one card at a time, top card first - CR 701.40a says nothing
    about looking before manifesting (unlike CR 701.62a's "manifest dread"
    just below, which looks at two and manifests one), so this is simply
    `manifest` run N times, exiling nothing and asking no question. A
    library with fewer than N cards left manifests what it can rather than
    raising, the same "even if some or all of those actions were impossible"
    reading `amass`'s own docstring argues for CR 701.47b.
    """
    match = _MANIFEST_TOP_CARD_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    n = parse_count(match.group("n")) if match.group("n") else 1

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        for _ in range(n):
            if not player.library:
                break
            top = player.library[0]
            player.zones[Zone.LIBRARY].remove(top)
            manifest(game, player.username, top)

    return effect


#: CR 701.62a: "'Manifest dread' means 'Look at the top two cards of your
#: library. Manifest one of them, then put the cards you looked at that were
#: not manifested this way into your graveyard.'" A bare keyword action, the
#: same shape as investigate/learn/amass above.
_MANIFEST_DREAD_RE = re.compile(r"^manifest dread$", re.IGNORECASE)


def manifest_dread(game: "Game", controller: str, source: str, *, source_id: str | None) -> None:
    """CR 701.62a, in full: look at the top two, manifest a choice among
    them, mill the rest.

    The choice among two candidates is CR 608.2d's - only asked when there
    really are two, the same shape
    `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`'s own "which
    permanent to keep" question already takes - and CR 701.62b's own "even
    if some or all of those actions were impossible" is why a library with
    zero or one card left still manifests what it can rather than raising.
    """
    player = game.player(controller)
    top_two = list(player.library[:2])
    if not top_two:
        return
    if len(top_two) == 1:
        chosen = top_two[0]
    else:
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt="choose a card to manifest",
                source=source,
                amount=1,
                cards=tuple(state.id for state in top_two),
                source_id=source_id,
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in top_two}
        chosen = by_id[chosen_ids[0]]
    for state in top_two:
        player.zones[Zone.LIBRARY].remove(state)
    manifest(game, controller, chosen)
    for state in top_two:
        if state is not chosen:
            game.put_into_graveyard(state)


def _parse_manifest_dread_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Manifest dread." - `_MANIFEST_DREAD_RE`'s shape.

    Names no object of its own (CR 701.62a), so - like amass, investigate and
    learn above - the same clause works for a spell or an ability alike.
    """
    if _MANIFEST_DREAD_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        manifest_dread(
            game,
            game.controller_of(stack_object).username,
            source,
            source_id=source_id_of(stack_object),
        )

    return effect


#: "Up to two target players each manifest two cards from their hands. For
#: each card manifested this way, you draw a card." - Kozilek, the Broken
#: Reality's own cast trigger. CR 701.40a's manifest names no zone of its
#: own - "manifest the top card of your library" above and CR 701.62a's
#: "manifest dread" both happen to manifest from the library, but the keyword
#: action itself is just "turn it face down [and] put that card onto the
#: battlefield face down", so this reader generalises `manifest` to a card
#: taken from a player's *hand* instead - the identical primitive, a
#: different origin zone. Each target player is the one who chooses which of
#: their own cards to manifest (CR 601.2d/701.9b's default: the affected
#: player's own choice, not the caster's), the same "choose N cards from your
#: own hand" question `_parse_reveal_n_cards_then_choose_discard_whole_text`
#: already asks for a reveal. "For each card manifested this way" is CR
#: 608.2c's running count of what the first sentence actually did (`record_
#: count`'s own convention elsewhere in this file), read across both target
#: players together, not per player - a target player short of two cards in
#: hand manifests as many as they have (CR 609.3) and simply contributes
#: fewer to that shared count.
_MANIFEST_FROM_HAND_THEN_DRAW_RE = re.compile(
    rf"^(?P<phrase>(?:up to )?{COUNT} target players) each manifest "
    rf"(?P<count>{COUNT}) cards? from their hands?\.\s*"
    r"for each card manifested this way, you draw a card\.?$",
    re.IGNORECASE,
)


def _parse_manifest_from_hand_then_draw_clause(effect_text: str) -> AbilityEffect | None:
    """`_MANIFEST_FROM_HAND_THEN_DRAW_RE`'s shape - see the banner above."""
    match = _MANIFEST_FROM_HAND_THEN_DRAW_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    if not _targets_understood(
        match.group("phrase"), allow_player_targets=True, count_agnostic=True
    ):
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        players = [target for target in game.resolve_targets(ability) if isinstance(target, Player)]
        if not players:
            return
        controller = game.controller_of(ability)
        manifested = 0
        for player in players:
            hand = list(player.hand)
            take = min(count, len(hand))
            if take <= 0:
                continue
            if take < len(hand):
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"choose {take} card(s) from your hand to manifest",
                        source=ability.source_name,
                        source_id=source_id_of(ability),
                        amount=take,
                        exact=True,
                        cards=tuple(card.id for card in hand),
                    )
                )
                assert isinstance(chosen_ids, tuple)
                by_id = {card.id: card for card in hand}
                chosen = [by_id[card_id] for card_id in chosen_ids]
            else:
                chosen = hand
            for card in chosen:
                player.zones[Zone.HAND].remove(card)
                manifest(game, player.username, card)
                manifested += 1
        if manifested > 0:
            game.draw_cards(controller.username, manifested)

    return effect


#: "defending player reveals the top card of their library. If it's a land
#: card, that player puts it into their hand." - Goblin Guide's own attack
#: trigger. Read whole (CR 608.2c: one instruction, not two independent
#: ones - the second sentence's "that player" is CR 400.7 anaphora back to
#: the "defending player" the first sentence just resolved, so this has to
#: stay one function the way `delver_upkeep`'s reveal-then-maybe-transform
#: does, rather than being split into two clauses the way an ordinary
#: "reveal ..., then ..." pair would be). "Defending player" is read exactly
#: as `_parse_defending_player_exiles_top_n_clause` reads it, off
#: `ability.event.defender` (CR 508.1a) through `machines.combat.
#: defending_player` - **the withheld or granted party is the player
#: Goblin Guide is attacking, never Goblin Guide's own controller**, which
#: is the specific "wrong player" bug this shape exists to catch.
_DEFENDING_PLAYER_REVEALS_TOP_CONDITIONAL_LAND_RE = re.compile(
    r"^defending player reveals the top card of their library\.\s*"
    r"if it'?s a land card, that player puts it into their hand\.?$",
    re.IGNORECASE,
)


def _parse_defending_player_reveals_top_conditional_land_clause(
    text: str,
) -> AbilityEffect | None:
    """`_DEFENDING_PLAYER_REVEALS_TOP_CONDITIONAL_LAND_RE`'s shape - Goblin
    Guide's whole attack trigger (CR 701.20a's reveal, CR 205.2a's land type
    check, CR 401 for the library-to-hand move).
    """
    if _DEFENDING_PLAYER_REVEALS_TOP_CONDITIONAL_LAND_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.defender is None:
            return
        username = combat_rules.defending_player(game, event.defender)
        if username is None:
            return
        player = game.player(username)
        if not player.library:
            return
        top = player.library[0]
        game.reveal(top, source=ability.source_name)
        if Type.LAND in top.card.types:
            player.move(top, Zone.HAND)

    return effect


# --------------------------------------------------------------------------
# Wave W1: a non-owner choosing from a revealed hand (CR 701.20a, CR 701.9b),
# "target player discards N cards" (CR 701.9a), and Formidable Speaker's
# "you may discard a card. If you do, ..." (CR 118.12's discard cousin) -
# Thoughtseize, Go Blank, and Formidable Speaker. Duskwatch Recruiter's
# "look at the top three ..." activated ability sits in its own block further
# down, next to `Game.look_at_top_and_split`, the primitive it and it alone
# needs here.
#
# Verified this session with `knowledge_search(q="...", type="rules")`:
#
#   CR 701.20a - "To reveal a card, show that card to all players for a brief
#   time."
#   CR 701.9a - "To discard a card, move it from its owner's hand to that
#   player's graveyard."
#   CR 701.9b - "By default, effects that cause a player to discard a card
#   allow the affected player to choose which card to discard. Some effects,
#   however, require a random discard or allow another player to choose
#   which card is discarded" - Thoughtseize's own "You choose a nonland card
#   from it" is exactly that override, read by naming `Decision.player` as
#   the resolving spell's controller rather than the revealing player.
# --------------------------------------------------------------------------

#: "target player reveals their hand" (Thoughtseize) / "target opponent
#: reveals their hand" (Grief, Thought-Knot Seer) - the same CR 701.20a
#: reveal, aimed at whichever player word the card prints; the actual target
#: restriction (a plain player, or specifically an opponent) is still
#: enforced by `machines/targeting.py` through `_targets_understood` below,
#: not by this regex.
#: "Target player reveals a number of cards from their hand equal to
#: `<expr>`. You choose one of them. That player discards that card." -
#: Klaw, Sonic Subjugator's own "Sonic Attack" ETB. Unlike `_REVEAL_HAND_RE`
#: (the whole hand), this reveals only *some* cards - CR 701.20's general
#: reveal action names no chooser of its own, so, as with any other reveal
#: of "a number of" cards rather than the whole hand or a search's own
#: found set, the choice of *which* cards to reveal belongs to the hand's
#: owner (CR 608.2d has nothing to say here; this is CR 701.20a's plain
#: instruction, not a "may").
_REVEAL_N_CARDS_FROM_HAND_THEN_CHOOSE_DISCARD_RE = re.compile(
    r"^target player reveals a number of cards from their hand equal to "
    r"(?P<expr>.+?)\.\s*you choose one of them\.\s*"
    r"that player discards that card\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_reveal_n_cards_then_choose_discard_whole_text(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_REVEAL_N_CARDS_FROM_HAND_THEN_CHOOSE_DISCARD_RE`'s shape, read
    whole - three sentences that all name the same target player and the
    same revealed set, none readable alone.

    Ability-only: `resolve_targets` names a player only for a resolving
    ability/permanent's own targets here (no printing in the pool has a
    spell do this).
    """
    if for_spell:
        return None
    match = _REVEAL_N_CARDS_FROM_HAND_THEN_CHOOSE_DISCARD_RE.fullmatch(text.strip())
    if match is None:
        return None
    magnitude = amount_expression(match.group("expr"))
    if magnitude is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        target_player = next(
            (t for t in game.resolve_targets(ability) if isinstance(t, Player)), None
        )
        if target_player is None:
            return
        controller = game.controller_of(ability)
        source = ability.source(game)
        count = magnitude(game, controller.username, source, ability.x_value)
        count = min(max(count, 0), len(target_player.hand))
        if count <= 0:
            return
        revealed_ids = target_player.hand
        if count < len(target_player.hand):
            chosen = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=target_player.username,
                    prompt=f"choose {count} cards from your hand to reveal",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=count,
                    exact=True,
                    cards=tuple(card.id for card in target_player.hand),
                )
            )
            assert isinstance(chosen, tuple)
            by_id = {card.id: card for card in target_player.hand}
            revealed_ids = [by_id[card_id] for card_id in chosen]
        for card in revealed_ids:
            game.reveal(card, source=ability.source_name)
        chosen_one = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose one of the revealed cards",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(card.id for card in revealed_ids),
            )
        )
        assert isinstance(chosen_one, tuple)
        by_revealed_id = {card.id: card for card in revealed_ids}
        game.discard_cards(target_player.username, [by_revealed_id[chosen_one[0]]])

    return effect


#: "put two cards from your hand on top of your library in any order"
#: (Brainstorm), and its bottom-of-library twin. CR 121.1's draw is a move
#: *out* of the library; this is the move back in, and CR 603.2c is the reason
#: it has to be one instruction rather than N: "an ability triggers only once
#: each time its trigger event occurs", and "whenever one or more cards are put
#: into a library from anywhere" (Wan Shi Tong, All-Knowing) is one event with a
#: count. `Game.put_cards_into_library` is where that single event is emitted.
#:
#: "in any order" is CR 608.2d's choice, made by the same player and the same
#: `CHOOSE_CARDS` question that picks *which* cards: the answer is an ordered
#: list, and the first card named ends up nearest the top.
_PUT_CARDS_FROM_HAND_INTO_LIBRARY_RE = re.compile(
    rf"^put (?P<count>{COUNT}) cards? from your hand "
    r"on (?:(?P<top>top)|the (?P<bottom>bottom)) of your library"
    r"(?: in any order)?\.?$",
    re.IGNORECASE,
)


def _parse_put_cards_from_hand_into_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_PUT_CARDS_FROM_HAND_INTO_LIBRARY_RE`'s shape - Brainstorm's second half.

    The cards are the controller's own choice (CR 608.2d: "the player
    announces their choice of an appropriate object ... as the spell or
    ability resolves"), asked as one `CHOOSE_CARDS` question over the whole
    hand. A hand short of the count moves as many as it has - CR 609.3's
    "does as much as it can" - rather than refusing the whole instruction.

    The move itself goes through `Game.put_cards_into_library`, which is what
    makes the two cards one CR 603.2c event instead of two.
    """
    match = _PUT_CARDS_FROM_HAND_INTO_LIBRARY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = parse_count(match.group("count"))
    to_bottom = match.group("bottom") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        hand = list(player.hand)
        amount = min(count, len(hand))
        if amount <= 0:
            return
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=(
                f"choose {amount} card(s) from your hand to put on "
                f"{'the bottom' if to_bottom else 'top'} of your library"
            ),
            source=source,
            amount=amount,
            cards=tuple(state.id for state in reversed(hand)),
            source_id=source_id_of(stack_object),
        )
        chosen_ids = game.ask(decision)
        by_id = {state.id: state for state in hand}
        game.put_cards_into_library([by_id[card_id] for card_id in chosen_ids], to_bottom=to_bottom)

    return effect


#: "The owner of `<target>` puts it ..." - Deem Inferior, Sudden Setback,
#: Plan for All Outcomes, Moonsnare Prototype. CR 108.3's owner, read off the
#: target itself, deliberately never the resolving spell/ability's controller
#: nor the target's own controller (`test_a_stolen_permanents_owner_is_asked_
#: not_its_new_controller` is exactly the case where those two diverge).
_OWNER_OF_TARGET_PUTS_INTO_LIBRARY_RE = re.compile(
    rf"^the owner of (?P<phrase>.+?) {_OWNER_PUTS_IT_INTO_LIBRARY_TAIL}", re.IGNORECASE
)

#: "`<target>`'s owner puts it ..." - Misleading Motes, Wan Shi Tong - the
#: same CR 108.3 owner, in the possessive rather than "the owner of".
_TARGET_POSSESSIVE_OWNER_PUTS_INTO_LIBRARY_RE = re.compile(
    rf"^(?P<phrase>.+?)'s owner {_OWNER_PUTS_IT_INTO_LIBRARY_TAIL}", re.IGNORECASE
)


def _owner_puts_it_into_library_destination_depth(match: re.Match[str]) -> int | None:
    """The 0-based index `_OWNER_PUTS_IT_INTO_LIBRARY_TAIL`'s own `<ordinal>`
    names, or `None` for the bare "top or bottom of `<library>`" shape, whose
    own top answer is the literal top rather than a printed depth."""
    ordinal_text = match.group("ordinal")
    if ordinal_text is None:
        return None
    ordinal = parse_ordinal(ordinal_text)
    if ordinal is None or ordinal < 1:
        return None
    return ordinal - 1


def _put_spell_in_library(
    game: "Game", spell: CardState, *, top: bool, depth: int | None = None
) -> None:
    """Move a spell off the stack straight into its owner's library (CR
    401.2), instead of letting it resolve.

    Deliberately not `Game.counter`: Subtlety's own ruling (and CR 701.6a's
    own text) is that this spell was never countered - it is simply removed
    from the stack and placed in a library, so `TriggerEvent.SPELL_IS_
    COUNTERED` must never fire for it and it must never pass through
    `Game.put_into_graveyard`. The bookkeeping `counter` otherwise shares
    (removing it from `game.stack`, dropping its now-stale `CastRecord`) is
    still needed here for the same reason `counter` needs it: a `CastRecord`
    surviving past this point would misread a later intervening *if* as
    "nothing was spent" instead of correctly finding no record at all
    (`machines/triggers._cast_record_for_clause`).

    `depth` is Wan Shi Tong's/Deem Inferior's own printed ordinal (Aether
    Gust's/Subtlety's/Sudden Setback's bare top-or-bottom shape leaves it
    `None`) - only meaningful on the top side; the bottom answer ignores it.
    """
    if spell not in game.stack:
        return
    game.stack.remove(spell)
    if spell.owner is None:
        game.forget_cast_record(spell)
        return
    # One CR 401.1 instruction, so the move raises the library event and is
    # known to every player, who saw the spell on the stack (CR 400.2).
    game.put_cards_into_library([spell], to_bottom=not top)
    # Forgotten after the move, so `last_known_spell` keeps it (CR 608.2h).
    game.forget_cast_record(spell)
    if top and depth:
        _reposition_in_owners_library(game, spell, depth=depth)


def _owner_puts_it_into_library_effect(*, for_spell: bool, depth: int | None) -> TargetedClause:
    """The shared effect body for every "owner puts it into a library"
    subject form: CR 608.2d's own choice, asked of the target's own owner
    (CR 108.3) - never the resolving spell/ability's controller, and never
    the target's own controller when the two differ - then dispatched by the
    *target's own zone* at the moment of resolution, not by which sentence
    named it: `_put_spell_in_library` off the stack (which also forgets the
    stale `CastRecord`, CR 400.7/608.2b), `Game.put_cards_into_library`
    everywhere else. `depth` is `None` for the bare top-or-bottom destination,
    or the printed ordinal's 0-based index for the other one.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.owner is None:
                continue
            top = game.ask(
                Decision(
                    kind=DecisionKind.PUT_ON_TOP_OR_BOTTOM,
                    player=target.owner,
                    prompt=f"put {target.name} on the top or bottom of {target.owner}'s library",
                    source=source,
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(top, bool)
            if target.zone is Zone.STACK:
                _put_spell_in_library(game, target, top=top, depth=depth)
                continue
            game.put_cards_into_library([target], to_bottom=not top)
            if top and depth:
                _reposition_in_owners_library(game, target, depth=depth)

    return effect


def _parse_owner_puts_it_into_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "The owner of `<target>` puts it ..." or "`<target>`'s owner puts it
    ..." - `_OWNER_OF_TARGET_PUTS_INTO_LIBRARY_RE`'s and `_TARGET_POSSESSIVE_
    OWNER_PUTS_INTO_LIBRARY_RE`'s shapes, either destination. Works for a
    spell target and an ability target alike (`for_spell` only ever picks
    which of the two names the resolving object in a prompt)."""
    stripped = clause.strip()
    match = _OWNER_OF_TARGET_PUTS_INTO_LIBRARY_RE.fullmatch(stripped)
    if match is None:
        match = _TARGET_POSSESSIVE_OWNER_PUTS_INTO_LIBRARY_RE.fullmatch(stripped)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    depth = _owner_puts_it_into_library_destination_depth(match)
    return _owner_puts_it_into_library_effect(for_spell=for_spell, depth=depth)


#: "Target opponent reveals their hand. You choose from it a `<qualityA>`
#: card with mana value `<mvA>` or less and a `<qualityB>` card with mana
#: value `<mvB>` or greater. That player discards those cards." - Distended
#: Mindbender's own cast trigger: two *independent* picks, each with its own
#: mana-value bound, rather than `_CHOOSE_CARD_FROM_REVEALED_RE`'s one shared
#: bound repeated N times. Not fitted to this card's own sentence: Perilous
#: Iteration's "Seek a card with mana value 2 or less and a card with mana
#: value 3 or greater." (a Seek, a different verb entirely) proves the
#: "`<quality>` with mana value X or less and a card with mana value Y or
#: greater" phrase-pair is itself a shared MTG template, not one author's
#: wording - this reader targets that shared template's *choose-from-a-
#: revealed-hand* verb, the one Distended Mindbender actually prints.
#:
#: Read against the *whole*, unsplit text, like `_parse_manifest_from_hand_
#: then_draw_clause` just above: `_prepare_effect_clauses`'s bare-"and" split
#: cuts "... or less and a card ..." into two fragments before any per-clause
#: or per-clause-run merge ever sees them together (the identical trap
#: `_parse_pump_and_becomes_chosen_color_clause`'s own docstring already
#: documents for a "power and toughness" type list), so this cannot be a
#: `_merge_*_clauses` entry the way `_merge_reveal_hand_choose_discard_
#: clauses` is.
_REVEAL_HAND_CHOOSE_TWO_BOUNDED_CARDS_THEN_DISCARD_RE = re.compile(
    r"^target opponent reveals their hand\.\s*"
    r"you choose from it an? (?:(?P<qualityA>[a-z]+) )?card with mana value (?P<mvA>\d+) "
    r"or (?P<cmpA>less|greater) and an? (?:(?P<qualityB>[a-z]+) )?card with mana value "
    r"(?P<mvB>\d+) or (?P<cmpB>less|greater)\.\s*"
    r"that player discards those cards\.?$",
    re.IGNORECASE,
)


def _parse_reveal_hand_choose_two_bounded_cards_then_discard_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_REVEAL_HAND_CHOOSE_TWO_BOUNDED_CARDS_THEN_DISCARD_RE`'s shape - see
    the banner above.

    CR 608.2d: each of the two picks is asked and made independently, and a
    bracket with no qualifying card left is CR 608.2d's own "impossible
    option" - skipped rather than asked, exactly as `_merge_reveal_hand_
    choose_discard_clauses` already treats an unsatisfiable single bound.
    A card already taken for the first pick is never offered for the second,
    even on a hypothetical printing whose two brackets could overlap - CR
    608.2d's "the player announces their choice of an appropriate object"
    reads each instruction as choosing a *fresh* one.
    """
    match = _REVEAL_HAND_CHOOSE_TWO_BOUNDED_CARDS_THEN_DISCARD_RE.fullmatch(
        " ".join(effect_text.split())
    )
    if match is None:
        return None
    if not _targets_understood("target opponent", allow_player_targets=True):
        return None
    matches_a = _bounded_revealed_card_matcher(
        match.group("qualityA"),
        int(match.group("mvA")),
        at_least=match.group("cmpA").lower() == "greater",
    )
    if matches_a is None:
        return None
    matches_b = _bounded_revealed_card_matcher(
        match.group("qualityB"),
        int(match.group("mvB")),
        at_least=match.group("cmpB").lower() == "greater",
    )
    if matches_b is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        revealer = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if revealer is None:
            return
        source = ability.source_name
        for state in list(revealer.hand):
            game.reveal(state, source=source)
        controller = game.controller_of(ability)
        chosen: list[CardState] = []
        for matcher in (matches_a, matches_b):
            candidates = [
                state for state in revealer.hand if state not in chosen and matcher(state)
            ]
            if not candidates:
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose a card from {revealer.username}'s revealed hand",
                    source=source,
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                    source_id=source_id_of(ability),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in candidates}
            chosen.append(by_id[chosen_ids[0]])
        if chosen:
            game.discard_cards(revealer.username, chosen, source=source)

    return effect


#: "Target player shuffles." (Lantern of Insight) - CR 701.20a's shuffle,
#: aimed at a chosen player rather than the controller's own library the way
#: a trailing "then shuffle" after a search already reads it
#: (`_BARE_SHUFFLE_RE`). Same sentence shape as `_TARGET_PLAYER_DRAWS_RE`,
#: CR 701.20a's verb in place of CR 121.1's.
_TARGET_PLAYER_SHUFFLES_RE = re.compile(
    r"^target player shuffles(?: their library)?\.?$", re.IGNORECASE
)


def _parse_target_player_shuffles_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TARGET_PLAYER_SHUFFLES_RE`'s shape, or `None` if this is not it."""
    if _TARGET_PLAYER_SHUFFLES_RE.fullmatch(clause.strip()) is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                game.shuffle_library(target)

    return effect


#: Riddles in the Dark's own shape: "Look at the top four cards of your
#: library and separate them into a face-down pile and a face-up pile. An
#: opponent chooses one of the piles. Put that pile into your hand and the
#: other into your graveyard." CR 700.3's identical pile primitive the
#: Liliana of the Veil family above already models, over the top of a
#: library instead of a battlefield, with a fixed hand/graveyard consequence
#: in place of a named verb, and the *resolving spell's own controller*
#: doing the dividing (there is no "target player" here to divide for) while
#: an opponent picks. "Face-down"/"face-up" is what actually happens to each
#: card as it is sorted: a face-up card is revealed (CR 701.20a) to every
#: player, including the opponent about to choose, and a face-down one stays
#: unrevealed - the division is a real information split, not flavour text.
_LOOK_TOP_SEPARATE_FACE_DOWN_FACE_UP_PILES_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards? of your library and separate them into "
    r"a face-down pile and a face-up pile\. "
    # "the piles" (Riddles in the Dark) and "those piles" (Curator of
    # Destinies) are the same CR 607.1 anaphora back to the two piles the
    # first sentence just made - two printed pronouns for one referent.
    r"an opponent chooses one of (?:the|those) piles\. "
    r"put that pile into your hand and the other into your graveyard\.?$",
    re.IGNORECASE,
)


def _parse_look_top_separate_face_down_face_up_piles_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_LOOK_TOP_SEPARATE_FACE_DOWN_FACE_UP_PILES_RE`'s shape, or `None`."""
    match = _LOOK_TOP_SEPARATE_FACE_DOWN_FACE_UP_PILES_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = parse_count(match.group("n"))
    if n is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        looked = list(controller.library[:n])
        if not looked:
            return
        # Step 1 (CR 700.3a/700.3d): the resolving spell or ability's own
        # controller separates every looked-at card into exactly one of the
        # two piles - named here as the face-up pile, the complement among
        # `looked` is the face-down pile.
        face_up_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="separate them into a face-down pile and a face-up pile - "
                "choose the face-up pile",
                source=source,
                amount=len(looked),
                cards=tuple(state.id for state in looked),
                source_id=source_id,
                exact=False,
            )
        )
        face_up_id_set = set(face_up_ids)
        face_up = [state for state in looked if state.id in face_up_id_set]
        face_down = [state for state in looked if state.id not in face_up_id_set]
        for state in face_up:
            game.reveal(state, source=source)
        # Step 2: an opponent picks a whole pile.
        opponent = _choose_an_opponent(game, controller, source, source_id)
        if opponent is None:
            chosen, other = face_down, face_up
        else:
            wants_face_up = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_PILE,
                    player=opponent.username,
                    prompt="choose a pile",
                    source=source,
                    cards=tuple(state.id for state in face_up),
                    source_id=source_id,
                )
            )
            assert isinstance(wants_face_up, bool)
            chosen = face_up if wants_face_up else face_down
            other = face_down if wants_face_up else face_up
        for state in chosen:
            if state.zone is Zone.LIBRARY:
                controller.move(state, Zone.HAND)
        for state in other:
            if state.zone is Zone.LIBRARY:
                game.put_into_graveyard(state)

    return effect


#: "you may put a `<kind>` card[, a `<kind>` card,] and/or a `<kind>` card from
#: among them into your hand" - Kiora, Master of the Depths' -2. Not
#: `_MAY_PUT_A_CARD_FROM_AMONG_THEM_INTO_HAND_RE`'s one pick of "a creature or
#: land card": one optional pick *per named kind*, from the same revealed
#: cards.
_MAY_PUT_ONE_OF_EACH_KIND_FROM_AMONG_THEM_INTO_HAND_RE = re.compile(
    r"^you may put (?P<kinds>an? [^,]+? card(?:, an? [^,]+? card)*,? and/or an? .+? card) "
    r"from among them into your hand$",
    re.IGNORECASE,
)
_ONE_OF_EACH_KIND_SEPARATOR_RE = re.compile(r",? and/or |, ", re.IGNORECASE)


def _reveal_take_one_of_each_kind(clause: str, count: int) -> tuple[int, TargetedClause] | None:
    """`_MAY_PUT_ONE_OF_EACH_KIND_FROM_AMONG_THEM_INTO_HAND_RE` inside
    `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`' run.

    Each named kind is its own CR 608.2d "you may", asked only while a
    revealed card of that kind is still on the table, so no question has no
    legal answer. A card of two named kinds (Dryad Arbor, a creature land)
    is one card: once taken for one pick it is no longer "from among them"
    for the next. Every card is revealed first (CR 701.20a); the rest go to
    the graveyard.
    """
    match = _MAY_PUT_ONE_OF_EACH_KIND_FROM_AMONG_THEM_INTO_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    kinds: list[tuple[str, Callable[[CardState], bool]]] = []
    for part in _ONE_OF_EACH_KIND_SEPARATOR_RE.split(match.group("kinds")):
        kind_match = re.fullmatch(r"an? (?P<quality>.+?) card", part.strip(), re.IGNORECASE)
        if kind_match is None:
            return None
        quality = kind_match.group("quality")
        if not _search_quality_is_readable(quality):
            return None
        kinds.append((with_indefinite_article(f"{quality} card"), _quality_matcher(quality)))
    if len(kinds) < 2:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        revealed = list(player.library[:count])
        for state in revealed:
            game.reveal(state, source=source)
        remaining = list(revealed)
        taken: list[CardState] = []
        for noun, matches in kinds:
            candidates = [state for state in remaining if matches(state)]
            if not candidates or not game.may(
                player,
                f"put {noun} from among them into your hand",
                source=source,
                source_id=source_id,
                cards=candidates,
            ):
                continue
            chosen = _choose_one_card(
                game,
                player,
                candidates,
                prompt=f"choose {noun} to put into your hand",
                source=source,
                source_id=source_id,
            )
            remaining.remove(chosen)
            taken.append(chosen)
        for state in taken:
            player.move(state, Zone.HAND)
        for state in remaining:
            game.put_into_graveyard(state)

    return 3, effect


#: Flow State's whole shape: `_merge_look_top_split_hand_graveyard_clauses`'s
#: own "look at the top N, put M into hand, the rest elsewhere" instruction,
#: followed by a second sentence naming a printed condition that changes only
#: how many go to hand - "If there is an instant card and a sorcery card in
#: your graveyard, instead put two of them into your hand and the rest on
#: the bottom of your library in any order."
#:
#: Read whole (`re.DOTALL`), ahead of the per-clause dispatcher, for two
#: reasons neither `_merge_look_top_split_hand_graveyard_clauses` nor the
#: general CR 614.1a "instead" framework (`_parse_condition_instead_clause`)
#: fits: `split_effect_clauses`'s own "and" cut fragments the condition's own
#: internal "an instant card **and** a sorcery card" into pieces no clause
#: parser reads on its own; and the alternative sentence's "of them" refers
#: to the very cards the *base* sentence looked at, not a second,
#: independently expressible branch the way `_parse_condition_instead_clause`
#: already reads elsewhere (Colossal Growth's own kicked alternative is a
#: whole standalone pump, not a changed count over a shared earlier step) -
#: so this shares one `Game.look_at_top_and_split` call and only the amount
#: moved to hand differs, decided at resolution (CR 608.2c fixes an
#: "instead" amount when the ability resolves, not when it is written).
_LOOK_TOP_SPLIT_CONDITIONAL_INSTEAD_RE = re.compile(
    rf"^look at the top (?P<count>{COUNT}) cards? of your library\.\s*"
    rf"put (?P<hand_n>{COUNT})(?: of (?:them|those cards))? into your hand and "
    r"the rest (?P<destination>into your graveyard|on the bottom of your library"
    r"(?: in (?:(?P<random>a random)|any) order)?)\.\s*"
    rf"if (?P<condition>.+?), instead put (?P<instead_n>{COUNT})"
    r"(?: of (?:them|those cards))? into your hand and the rest "
    r"(?P<destination2>into your graveyard|on the bottom of your library"
    r"(?: in (?:(?P<random2>a random)|any) order)?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_look_top_split_conditional_instead_clause(effect_text: str) -> Effect | None:
    """`_LOOK_TOP_SPLIT_CONDITIONAL_INSTEAD_RE`'s shape, or `None`.

    `condition_is_readable` gates the parse the same way `_parse_condition_
    instead_clause` gates its own condition - a card whose condition this
    engine cannot read is left unread entirely (CR 608.2c), never treated as
    permanently false. `Game.condition_holds` answering `None` at
    resolution despite the shape parsing (an inner count or quality word it
    does not know) is recorded as a `ConditionalClauseNotice`, the same
    fail-closed record `_parse_condition_instead_clause` already leaves for
    its own unreadable-at-resolution case, rather than silently false.
    """
    whole = " ".join(effect_text.split())
    match = _LOOK_TOP_SPLIT_CONDITIONAL_INSTEAD_RE.fullmatch(whole)
    if match is None:
        return None
    if match.group("destination").lower() != match.group("destination2").lower():
        # CR 608.2c: an "instead" here only ever changes the amount, never
        # the destination too - a card that changed both would need its own
        # reader rather than a guessed merge of the two.
        return None
    count = parse_count(match.group("count"))
    hand_count = parse_count(match.group("hand_n"))
    instead_count = parse_count(match.group("instead_n"))
    if count is None or hand_count is None or instead_count is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    to_bottom = match.group("destination").lower().startswith("on the bottom")
    randomised = match.group("random") is not None
    rest_label = "bottom of your library" if to_bottom else "your graveyard"

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        source = spell.card.name
        source_id = source_id_of(spell)
        held = game.condition_holds(controller.username, condition_text, spell)
        if held is None:
            notice = ConditionalClauseNotice(source_id=spell.id, source_name=source, text=whole)
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        amount = instead_count if held else hand_count
        prompt = f"put {amount} into your hand, the rest to {rest_label}"
        moved, rest = game.look_at_top_and_split(
            controller,
            count,
            source=source,
            prompt=prompt,
            moved_label="your hand",
            kept_label=rest_label,
            rest_in_random_order=randomised,
            source_id=source_id,
            moved_amount=amount,
            moved_exact=True,
        )
        required = min(amount, len(moved) + len(rest))
        if len(moved) != required:
            raise ValueError(
                f"{source}: exactly {required} of the {len(moved) + len(rest)} looked at must "
                f"go to hand, the rest to {rest_label} (CR 608.2d)"
            )
        for state in moved:
            controller.add(state, Zone.HAND)
        if to_bottom and randomised and rest:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom"
            )
            rng.shuffle(rest)
            game.shuffles_performed += 1
        elif to_bottom and rest:
            # CR 401.4: "in any order" is the player's own arrangement.
            rest = game.ask_library_bottom_order(
                controller, rest, source=source, source_id=source_id
            )
        if to_bottom:
            controller.library.extend(rest)
            if rest:
                controller.note_library_changed(placed=rest)
        else:
            for state in rest:
                controller.add(state, Zone.GRAVEYARD)
                game._record_graveyard_arrival(  # noqa: SLF001
                    state, origin_zone=Zone.LIBRARY, permanent_types=None
                )

    return effect


def _dead_self_object_id(ability: "AbilityOnStack") -> UUID | None:
    """The id a dead-self clause's "it" names: `ability.event.subject_id`
    when there is a triggering event to read (CR 603.10a's look-back),
    falling back to the ability's own `source_id` when there is none (a
    plain activated ability, CR 113.7a). For a `TriggerEvent.DIES` ability
    the two already agree - `Game.put_into_graveyard`'s own `triggers_for`
    call sets `source_id` to the very card the dies event names - so this
    only actually matters for the no-event fallback."""
    event = ability.event
    return (event.subject_id if event is not None else None) or ability.source_id


def _dead_self_found(game: "Game", ability: "AbilityOnStack") -> CardState | None:
    """The object a dead-self clause's "it" still names, or `None` if CR
    113.7a/CR 400.7e no longer let this ability find it.

    With a triggering event (every dies trigger in this family):
    `GameEvent.zone_change_stamp` is the exact CR 400.7 incarnation the dies
    event's own move minted in the graveyard. CR 400.7e: a look-back ability
    "can find the new object that it became in the zone it moved to when the
    ability triggered, if that zone is a public zone" - the graveyard, and
    only that graveyard incarnation, not wherever the card has gone since.
    So this refuses unless the live object (by id) is *still* sitting in the
    graveyard carrying that same stamp - exiled from the graveyard in
    response (a real pool graveyard-hate printing, Tormod's Crypt among
    them), returned to the battlefield, or even shuffled back into the same
    graveyard as a fresh CR 400.7 object of its own, are all "not found" the
    same way, and CR 608.2c never runs half an instruction for the clauses
    that read this.

    With no triggering event (a plain activated ability, Borborygmos and
    Fblthp's own `{1}{U}`, which fires *from* the battlefield and is still
    sitting there, untriggered by any zone change, when this runs): the old,
    looser check this family always had before the subsume - found by id,
    full stop, whatever zone that turns out to be. Gating this branch on
    "not on the battlefield" is the exile-it/return-it siblings' own dies-
    trigger gate (CR 113.7a's fail-soft for a source that has since gone
    back to the battlefield), and it does not apply here: this branch is
    reached only by a source that started on the battlefield and is
    expected to still be there.
    """
    object_id = _dead_self_object_id(ability)
    if object_id is None:
        return None
    found = game.find_by_id(object_id)
    if not isinstance(found, CardState):
        return None
    event = ability.event
    if event is None:
        return found
    if event.subject_id is None:
        # An event about no object - a step beginning (Cactuar's "At the
        # beginning of your end step, if this creature didn't enter the
        # battlefield this turn, return it to its owner's hand"): "it" is the
        # source itself, and only while it is still the object that
        # triggered (CR 400.7) on the battlefield.
        if found.zone is not Zone.BATTLEFIELD:
            return None
        if ability.source_stamp is not None and found.zone_change_stamp != ability.source_stamp:
            return None
        return found
    stamp = event.zone_change_stamp
    if stamp is None and found.zone is Zone.BATTLEFIELD:
        # An event that moved nothing (Shatterskull Charger's "At the
        # beginning of your end step, ... return it to its owner's hand"):
        # "it" is the source still on the battlefield - the same object the
        # ability came from (CR 113.7a, CR 400.7), or nothing.
        if ability.source_stamp is None or found.zone_change_stamp == ability.source_stamp:
            return found
        return None
    if stamp is None or found.zone is not Zone.GRAVEYARD or found.zone_change_stamp != stamp:
        return None
    return found


#: "put it (on the (top|bottom) of|into) its owner's library[ <ordinal> from
#: the top]" / "shuffle it into its owner's library" - Murderous Rider's own
#: dies trigger ("put it on the bottom of its owner's library"), Dark
#: Revenant's ("...on top..."), and Cavalier of Gales's ("shuffle it into
#: its owner's library") - the dead-self family's own library placement,
#: alongside `_EXILE_IT_RE`'s exile and `_RETURN_IT_TO_OWNERS_HAND_RE`'s
#: hand.
#:
#: Subsumes `_PUT_SELF_INTO_LIBRARY_NTH_FROM_TOP_RE`'s old "this
#: `<permanent|creature|card>`" self-reference (Borborygmos and Fblthp,
#: Bookwurm, Screaming Swarm) rather than keeping a second regex for the
#: same "put/shuffle this object into a library" mechanic - "it" and "this
#: `<noun>`" name the same CR 201.5/CR 607.1 self-reference, just
#: normalised differently depending on whether `_self_normalized_effect_
#: text` already turned a permanent's own printed name into "this
#: permanent" or the card prints the pronoun itself.
_DEAD_OBJECT_TO_LIBRARY_RE = re.compile(
    r"^(?:you may )?"
    r"(?:"
    r"put (?:it|this (?:permanent|creature|card|artifact))(?: from your graveyard)? "
    r"on (?:the )?(?P<side>top|bottom) of (?:its owner'?s|your) library"
    r"|"
    rf"put (?:it|this (?:permanent|creature|card|artifact))(?: from your graveyard)? "
    rf"into (?:its owner'?s|your) library (?P<ordinal>{ORDINAL}) from the top"
    r"|"
    r"shuffle (?:it|this (?:permanent|creature|card|artifact))(?: from your graveyard)? "
    r"into (?:its owner'?s|your) library"
    r")\.?$",
    re.IGNORECASE,
)


def _parse_dead_object_to_library_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_DEAD_OBJECT_TO_LIBRARY_RE`'s shape.

    "It"/"this `<noun>`" is resolved by `_dead_self_found` exactly as
    `_parse_exile_dead_self_clause`'s own "it" is - see that helper's own
    docstring for the CR 400.7e look-back this is the actual fix for:
    Murderous Rider's own dies trigger, exiled from the graveyard in
    response by a real pool printing (Tormod's Crypt), no longer moves; the
    same recheck that already refuses a dies trigger's "exile it" once the
    card has moved on refuses this reader's "put it .../shuffle it ..." too.
    Borborygmos and Fblthp's own event-less `{1}{U}` keeps the old, looser
    "found by id, not on the battlefield" behaviour that reader always had -
    it fires *from* the battlefield, so gating it on "still in the
    graveyard" would refuse the very ability this clause has always run
    (`test_fra_s8b_self_into_library_nth_from_top.py`).

    CR 701.24c: "If an effect would cause a player to shuffle one or more
    specific objects into a library, that library is shuffled even if none
    of those objects are in the zone they're expected to be in." So the
    shuffle destination always shuffles the named object's owner's library -
    read off the live object by id alone, CR 108.3 ownership surviving every
    CR 400.7 reset regardless of whether `_dead_self_found` can still find
    *this* incarnation of it - moving the object in only when
    `_dead_self_found` says it is still there to move. The put-on-top,
    put-on-bottom and put-Nth-from-the-top destinations have no such rule:
    unfound there is simply refused, the same as the exile/hand siblings.

    A token (CR 111.7) already ceased to exist, or one this resolution
    catches still sitting in the graveyard, is excluded from both paths the
    same way - CR 111.8 lets a token that left the battlefield move to
    nowhere, including a library, so this reader is never the thing that
    moves one.
    """
    if for_spell:
        return None
    match = _DEAD_OBJECT_TO_LIBRARY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    is_optional = clause.strip().lower().startswith("you may")
    side = match.group("side")
    ordinal_word = match.group("ordinal")
    is_shuffle = side is None and ordinal_word is None
    to_bottom = side == "bottom"
    depth: int | None = None
    if ordinal_word is not None:
        ordinal = parse_ordinal(ordinal_word)
        if ordinal is None or ordinal < 1:
            return None
        depth = ordinal - 1

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        object_id = _dead_self_object_id(ability)
        if object_id is None:
            return
        raw = game.find_by_id(object_id)
        raw_state = raw if isinstance(raw, CardState) and not is_token(raw) else None
        found_state = _dead_self_found(game, ability)
        if found_state is not None and is_token(found_state):
            found_state = None
        if is_optional:
            controller = game.controller_of(ability)
            if not game.may(
                controller,
                clause.strip(),
                source=ability.source_name,
                source_id=source_id_of(ability),
            ):
                return
        if is_shuffle:
            owner_name = raw_state.owner if raw_state is not None else None
            if owner_name is None:
                return
            owner = game.player(owner_name)
            if found_state is not None:
                owner.add(found_state, Zone.LIBRARY)
            game.shuffle_library(owner)
            return
        if found_state is None or found_state.owner is None:
            return
        game.put_cards_into_library([found_state], to_bottom=to_bottom)
        if depth is not None and depth > 0:
            _reposition_in_owners_library(game, found_state, depth=depth)

    return effect


#: "its owner shuffles their graveyard into their library" - Emrakul, the
#: Aeons Torn's own dies-from-anywhere trigger (CR 603.10a). Distinct from
#: `_DEAD_OBJECT_TO_LIBRARY_RE`'s "shuffle it into its owner's library"
#: (Purity, Dread, Kozilek's own "Butcher of Truth" printing), which shuffles
#: only the dead object itself back in: this shuffles the *whole* graveyard
#: the object just joined, itself included, back into that same player's
#: library.
_OWNER_SHUFFLES_GRAVEYARD_INTO_LIBRARY_RE = re.compile(
    r"^its owner shuffles (?:their|his or her) graveyard into (?:their|his or her) library$",
    re.IGNORECASE,
)


def _parse_owner_shuffles_graveyard_into_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_OWNER_SHUFFLES_GRAVEYARD_INTO_LIBRARY_RE`'s shape - "its owner" is
    the dead self's own owner (CR 108.3), read off the object by id alone
    the same way `_parse_dead_object_to_library_clause`'s own shuffle branch
    does (CR 701.24c: the shuffle happens even once the object itself can no
    longer be found, since a card leaving its own graveyard in response,
    Tormod's Crypt among them, never stops that graveyard's *other* cards
    from being shuffled)."""
    if for_spell:
        return None
    if not _OWNER_SHUFFLES_GRAVEYARD_INTO_LIBRARY_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        object_id = _dead_self_object_id(ability)
        if object_id is None:
            return
        raw = game.find_by_id(object_id)
        owner_name = raw.owner if isinstance(raw, CardState) else None
        if owner_name is None:
            return
        owner = game.player(owner_name)
        for state in list(owner.graveyard):
            owner.add(state, Zone.LIBRARY)
        game.shuffle_library(owner)

    return effect


#: "Shuffle this creature and target `<description>` into their owners'
#: libraries." - Floodpits Drowner's own `{1}{U}, {T}` ability. The self
#: half is the same CR 201.5/CR 607.1 self-reference the dead-self family
#: above reads ("this `<noun>`"); the "and target ..." half is any targeting
#: phrase `_targets_understood` already reads (Serene Remembrance's own
#: "up to three target cards from a single graveyard" proves the same "self
#: plus target(s), each into its *own* owner's library" shape generalises
#: past a single target and past an activated ability into a sorcery).
#: The self half is either an ability's own normalised "this `<noun>`"/"it"
#: (CR 700.7), or - since a spell resolving keeps its own literal printed
#: name in this text, never normalised to "this spell"/"this sorcery" the
#: way an ability's self-reference is - a bare run of capitalised words
#: (Serene Remembrance's own "Shuffle Serene Remembrance and ..."), the same
#: fallback shape other self-referential readers in this module already use
#: for a spell's own name (see the identical alternation elsewhere in this
#: file).
_SHUFFLE_SELF_AND_TARGETS_INTO_OWNERS_LIBRARIES_RE = re.compile(
    r"^shuffle (?:this (?:creature|permanent|artifact|card)|it|"
    r"[A-Z][\w'-]*(?: [A-Z][\w'-]*)*) and "
    r"(?P<phrase>(?:up to (?:one|two|three|four|\d+) )?target [^.]+?) "
    r"into their owners'? libraries\.?$",
    re.IGNORECASE,
)


def _parse_shuffle_self_and_targets_into_owners_libraries_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SHUFFLE_SELF_AND_TARGETS_INTO_OWNERS_LIBRARIES_RE`'s shape.

    CR 701.24c: "If an effect would cause a player to shuffle one or more
    specific objects into a library, that library is shuffled even if none
    of those objects are in the zone they're expected to be in" - so each
    card named (self included) goes into its *own* owner's library, and
    every distinct owner's library touched is shuffled once, grouped so two
    cards owned by the same player are not shuffled into it twice.

    The self half: for an ability, `_dead_self_found`'s id-based lookup
    (CR 113.7a's fail-soft for an activated ability with no triggering
    event, exactly Borborygmos and Fblthp's own untriggered `{1}{U}` above),
    so a self already moved on by something else in response is simply not
    found rather than moved twice; for a spell (Serene Remembrance), the
    resolving `stack_object` itself - CR 701.24c's own "even if [it isn't]
    in the zone it's expected to be in" covers the stack, the spell's own
    current zone as it resolves. The target half is `game.
    resolve_card_targets`, the ordinary CR 608.2b illegal-target recheck,
    either way.
    """
    match = _SHUFFLE_SELF_AND_TARGETS_INTO_OWNERS_LIBRARIES_RE.fullmatch(
        " ".join(text.strip().split())
    )
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        moved: list[CardState] = []
        self_found = (
            stack_object
            if for_spell and isinstance(stack_object, CardState)
            else _dead_self_found(game, stack_object)
            if isinstance(stack_object, AbilityOnStack)
            else None
        )
        if self_found is not None and not is_token(self_found):
            moved.append(self_found)
        for target in game.resolve_card_targets(stack_object):
            if not is_token(target) and target not in moved:
                moved.append(target)
        moved = [card for card in moved if card.owner is not None]
        if not moved:
            return
        # `Game.put_cards_into_library` (not `Player.add` directly) is what
        # actually takes each card out of wherever it is now - the
        # battlefield included (`Game._take_out_of_every_zone`) - as well as
        # sorting them into their own owners' libraries (CR 108.3); the
        # position it leaves them at does not matter, since every library
        # touched is shuffled right after (CR 701.24c).
        game.put_cards_into_library(moved)
        for owner_name in dict.fromkeys(card.owner for card in moved):
            assert owner_name is not None
            game.shuffle_library(game.player(owner_name))

    return effect


def _source_escaped(game: "Game", source: CardState) -> bool:
    """CR 702.138b: "A spell or permanent 'escaped' if that spell or the spell
    that became that permanent as it resolved was cast from a graveyard with an
    escape ability." `CardState.cast_with_keyword` is set only as a cast spell
    becomes this exact permanent and cleared on every later move (CR 400.7), so
    a permanent that was never cast, or was cast for its mana cost, did not."""
    return (source.cast_with_keyword or "").lower() == "escape"


#: --- "Chooses a card name, then reveals the top card ... If that card has
#: the chosen name, ..." (CR 608.2c, CR 701.20a, CR 201.4, CR 201.1) -------
#:
#: The shared core Vexing Arcanix and Conundrum Sphinx both print: ask
#: someone to name a card, reveal a library's own top card, and branch on
#: whether the two names match. One shared function rather than two copies
#: of the same three steps, the same reason `_filtered_anthem_builder` is
#: shared by every subtype-list lord rather than reimplemented per card.


def _ask_name_reveal_top_and_branch(
    game: "Game",
    revealer: Player,
    *,
    chooser: Player,
    source: str,
    source_id: str | None,
    on_match: Callable[[CardState], None],
    on_miss: Callable[[CardState], None],
) -> None:
    """Ask `chooser` to name a card (CR 601.2c's own kind of resolution-time
    choice, not tied to any `CardState.choice`, since nothing here re-reads
    "the chosen name" later the way a static CR 614.1c "as this enters,
    choose..." grant does; CR 201.4 makes the chosen name a real card's,
    checked by `Game.ask` itself against `data.printing_pool`), reveal
    `revealer`'s own top library card (CR 701.20a), and run `on_match` when
    its printed name (CR 201.1) equals what was chosen or `on_miss`
    otherwise.

    An empty library has no top card to reveal, so nothing happens at all
    (CR 609.3, CR 101.3) - not even the naming question, which nothing could
    ever be compared against.
    """
    if not revealer.library:
        return
    name = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=chooser.username,
            prompt="choose a card name",
            source=source,
            source_id=source_id,
            quality=ChoiceKind.CARD_NAME.value,
        )
    )
    assert isinstance(name, str)
    top = revealer.library[0]
    game.reveal(top, source=source)
    if top.name == name:
        on_match(top)
    else:
        on_miss(top)


#: "Target player chooses a card name, then reveals the top card of their
#: library. If that card has the chosen name, that player puts it into
#: their hand. Otherwise, they put it into their graveyard and this artifact
#: deals 2 damage to them." - Vexing Arcanix's whole `{3}, {T}` effect, read
#: as one paragraph (CR 608.2c: one instruction, not several independent
#: clauses - "that card"/"the chosen name"/"they" are all CR 400.7/CR 607.1
#: anaphora back to what the first sentence just did).
#:
#: This used to fall through to `_parse_damage_that_player_clause` instead,
#: whose `_DAMAGE_THAT_PLAYER_RE` opens with a bare `.*` - it matched the
#: *tail* of this whole paragraph and reported the card `handled` while
#: silently discarding the naming choice, the reveal, and the hand branch
#: entirely. This reader is tried earlier in the dispatch chain so the
#: correct, whole-paragraph reading wins first.
#:
#: The trailing "and `<source>` deals N damage to `<them>`" is optional and
#: its subject/object phrasing is read the same subject-agnostic way
#: `_DAMAGE_THAT_PLAYER_RE` already reads a trailing damage rider, not
#: pinned to "this artifact"/"them" - Petra Sphinx's own identical template
#: with no damage rider at all (not in Modern/Pioneer/Standard, so not a
#: pool card) is what "optional" is for.
_TARGET_PLAYER_NAME_REVEAL_BRANCH_RE = re.compile(
    r"^target player chooses a card name, then reveals the top card of "
    r"their library\.\s*"
    r"if that card has the chosen name, that player puts it into their "
    r"hand\.\s*"
    r"otherwise, (?:they|that player) puts? it into their graveyard"
    rf"(?: and .+? deals (?P<n>{COUNT}) damage to (?:them|that player))?\.?$",
    re.IGNORECASE,
)


def _parse_target_player_name_reveal_branch_clause(text: str) -> AbilityEffect | None:
    """`_TARGET_PLAYER_NAME_REVEAL_BRANCH_RE`'s shape; see the banner above."""
    match = _TARGET_PLAYER_NAME_REVEAL_BRANCH_RE.fullmatch(text.strip())
    if match is None:
        return None
    damage = parse_count(match.group("n")) if match.group("n") is not None else 0

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        target_player = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if target_player is None:
            return

        def on_match(top: CardState) -> None:
            target_player.move(top, Zone.HAND)

        def on_miss(top: CardState) -> None:
            game.put_into_graveyard(top)
            if damage:
                game.deal_damage(target_player, damage, source=ability.source_or_last_known(game))

        _ask_name_reveal_top_and_branch(
            game,
            target_player,
            chooser=target_player,
            source=ability.source_name,
            source_id=source_id_of(ability),
            on_match=on_match,
            on_miss=on_miss,
        )

    return effect


#: "Each player chooses a card name. Then each player reveals the top card
#: of their library. If the card a player revealed has the name they chose,
#: that player puts it into their hand. If it doesn't, that player puts it
#: on the bottom of their library[./ into their graveyard.]" - Conundrum
#: Sphinx's own attack trigger (the "Whenever this creature attacks"
#: condition is a plain, already-read `TriggerEvent.ATTACKS`; only this
#: effect sentence reaches this reader). The identical `_ask_name_reveal_
#: top_and_branch` core as Vexing Arcanix's own reader, run once per player
#: instead of once for a single target - CR 101.4's APNAP order for the
#: naming choices (`_players_in_apnap_order`, already shared with every
#: other simultaneous-choice reader in this module), each player naming and
#: revealing only their own library, never another's (CR 400.7's "a player"
#: here is each player in turn, not a single target the way Vexing
#: Arcanix's "that player" is).
#:
#: The miss branch is read generically rather than pinned to Conundrum
#: Sphinx's own literal "puts it on the bottom of their library" - Vexing
#: Arcanix's identical shape prints "puts it into their graveyard" for the
#: same miss instead, so a card sharing this exact "each player" template
#: with that consequence reads for free, proved directly (`test_choose_
#: name_reveal_top_and_branch.py`'s own generalises-off-a-differently-
#: worded-variant test) - Conundrum Sphinx and Petra Sphinx are this
#: template's only two known printings and neither one uses it, but the
#: reader is not fitted to either one's exact sentence.
_EACH_PLAYER_NAME_REVEAL_BRANCH_RE = re.compile(
    r"^each player chooses a card name\.\s*"
    r"then each player reveals the top card of their library\.\s*"
    r"if the card a player revealed has the name they chose, that player "
    r"puts it into their hand\.\s*"
    r"if it doesn'?t, that player puts it (?P<miss>on the bottom of their "
    r"library|into their graveyard)\.?$",
    re.IGNORECASE,
)


def _parse_each_player_name_reveal_branch_clause(text: str) -> AbilityEffect | None:
    """`_EACH_PLAYER_NAME_REVEAL_BRANCH_RE`'s shape; see the banner above.

    CR 101.4's APNAP order governs the *naming*, and only the naming: "each
    player chooses a card name" is one simultaneous action every player
    takes in turn order before anyone's own library is shown (the identical
    reading `_players_in_apnap_order`'s other callers already give a
    simultaneous choice), so this asks every player for their name first,
    in a whole first pass, and only then reveals and branches for each of
    them in a second pass - never name-reveal-branch one player at a time,
    which would let a later player's own choice follow an earlier player's
    already-revealed card.
    """
    match = _EACH_PLAYER_NAME_REVEAL_BRANCH_RE.fullmatch(text.strip())
    if match is None:
        return None
    miss_to_graveyard = match.group("miss").lower().startswith("into their graveyard")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        players = [player for player in _players_in_apnap_order(game) if player.library]
        chosen_names: dict[str, str] = {}
        for player in players:
            name = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=player.username,
                    prompt="choose a card name",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    quality=ChoiceKind.CARD_NAME.value,
                )
            )
            assert isinstance(name, str)
            chosen_names[player.username] = name
        for player in players:
            top = player.library[0]
            game.reveal(top, source=ability.source_name)
            if top.name == chosen_names[player.username]:
                player.move(top, Zone.HAND)
            elif miss_to_graveyard:
                game.put_into_graveyard(top)
            else:
                player.move(top, Zone.LIBRARY)

    return effect


#: "Shuffle up to three target cards from your graveyard into your library."
#: (Tamiyo Meets the Story Circle III), "Shuffle up to five target cards ..."
#: (Wand of Vertebrae), "Shuffle any number of target cards ..." (Perpetual
#: Timepiece, The Bath Song III) - CR 701.24a's shuffle with the targeted
#: cards put in first.
_SHUFFLE_TARGET_CARDS_INTO_LIBRARY_RE = re.compile(
    r"^shuffle (?P<phrase>(?:up to [a-z0-9]+ |any number of |[a-z0-9]+ )?target cards? "
    r"from (?:your|a) graveyard) into (?:your|its owner'?s|their owners'?) library\.?$",
    re.IGNORECASE,
)


def _parse_shuffle_target_cards_into_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SHUFFLE_TARGET_CARDS_INTO_LIBRARY_RE`'s shape.

    Each target still in the graveyard it was chosen in (CR 608.2b) goes into
    its owner's library, and each library that received a card is shuffled
    (CR 701.24a). With no card moved - zero targets chosen (CR 115.6), or
    every one gone - the controller's own library is still shuffled, the
    instruction's own verb.
    """
    match = _SHUFFLE_TARGET_CARDS_INTO_LIBRARY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        moved = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD
        ]
        _shuffle_targets_into_owners_libraries(game, stack_object, moved)

    return effect


def _shuffle_targets_into_owners_libraries(
    game: "Game", stack_object: "StackObject", targets: list[CardState]
) -> None:
    """The shared CR 701.24a half of `_parse_shuffle_target_cards_into_
    library_clause` above and `_parse_shuffle_target_permanent_into_library_
    clause` below: each already-legality-filtered target goes into its
    owner's library, and each library that received one is shuffled. With
    no target moved - zero chosen (CR 115.6), or every one gone (CR 608.2b) -
    the controller's own library is still shuffled, the instruction's own
    verb."""
    owners: list[str] = []
    for target in targets:
        if target.owner not in owners:
            owners.append(target.owner)
        game.put_cards_into_library([target])
    for owner in owners or [game.controller_of(stack_object).username]:
        game.shuffle_library(owner)


#: "Shuffle target nonland permanent an opponent controls with mana value X
#: or less into its owner's library, where X is the number of creatures
#: tapped this way." (Invasion of New Phyrexia // Teferi Akosa of Zhalfir's
#: own `-3`) - CR 701.24a's shuffle again, this time on a targeted
#: *permanent* instead of `_SHUFFLE_TARGET_CARDS_INTO_LIBRARY_RE`'s targeted
#: graveyard card. The restriction itself ("an opponent controls", "with
#: mana value N or less") is `_targets_understood`'s ordinary business, the
#: same reader every other targeted clause in this file already goes
#: through, so a future "shuffle target artifact you control into its
#: owner's library" reads identically without a second parser.
_SHUFFLE_TARGET_PERMANENT_INTO_LIBRARY_RE = re.compile(
    r"^shuffle (?P<phrase>target .+?permanents?.+?) into "
    r"(?:its owner'?s|their owners'?) librar(?:y|ies)\.?$",
    re.IGNORECASE,
)


def _parse_shuffle_target_permanent_into_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SHUFFLE_TARGET_PERMANENT_INTO_LIBRARY_RE`'s shape; see the banner
    above."""
    match = _SHUFFLE_TARGET_PERMANENT_INTO_LIBRARY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        moved = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        _shuffle_targets_into_owners_libraries(game, stack_object, moved)

    return effect


def _reveal_and_bring_into_hand(
    game: "Game", controller: Player, card: CardState, source: str | None
) -> None:
    """Reveal a card its controller owns outside the game, then put it into
    that player's hand - the shared tail of Karn, the Great Creator's -2 and
    the Burning Wish family.

    CR 701.20a shows it to all players and CR 701.20b leaves it where it is,
    so the public record is made against the sideboard (CR 400.11a) first;
    CR 108.3b/400.11b's move into the hand then carries that record with the
    card (`Player.add`, `Game.carry_knowledge_into_hand`), so every player
    knows it in hand until it changes zones again.
    """
    game.reveal(card, source=source)
    controller.bring_into_the_game(card, Zone.HAND)


#: "You may reveal exactly two cards you own with different names from
#: outside the game. An opponent chooses one of them. You put that card into
#: your hand." - Extrapolate the Impossible's own whole effect. CR 608.2d's
#: own "you may" gates the whole instruction, not just the reveal; "with
#: different names" narrows the candidate pool the same way `_parse_search_
#: distinct_names_clause` already does for a library search, one
#: representative per name before any choice is offered, so the controller's
#: own CR 608.2d pick of exactly two can never name the same card twice. The
#: opponent's own choice (CR 608.2d again, made by whoever "an opponent"
#: names rather than by this spell's controller) is the one place in this
#: family the choosing player is not the ability's own controller.
_REVEAL_TWO_DIFFERENT_NAMES_OUTSIDE_THEN_OPPONENT_CHOOSES_RE = re.compile(
    r"^you may reveal exactly two cards you own with different names from "
    r"outside the game\.\s*an opponent chooses one of them\.\s*"
    r"you put that card into your hand\.?$",
    re.IGNORECASE,
)


def _parse_reveal_two_outside_opponent_chooses_clause(
    effect_text: str, *, for_spell: bool
) -> Effect | None:
    """`_REVEAL_TWO_DIFFERENT_NAMES_OUTSIDE_THEN_OPPONENT_CHOOSES_RE`'s
    shape, or `None`. Never an ability's own shape - nothing in the pool
    prints this off a permanent - so `for_spell` is checked rather than
    reached for a `CardState` that would be the wrong stack object.
    """
    if not for_spell:
        return None
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    if _REVEAL_TWO_DIFFERENT_NAMES_OUTSIDE_THEN_OPPONENT_CHOOSES_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        by_name: dict[str, CardState] = {}
        for state in controller.owned_outside_the_game():
            by_name.setdefault(state.name or "", state)
        candidates = list(by_name.values())
        if len(candidates) < 2:
            return
        if not game.may(
            controller,
            "reveal exactly two cards you own with different names from outside the game",
            source=spell.name,
            source_id=source_id_of(spell),
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose exactly two cards with different names to reveal",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=2,
                exact=True,
                cards=tuple(state.id for state in candidates),
                card_labels=tuple(state.name for state in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        if len(chosen_ids) < 2:
            return
        by_id = {state.id: state for state in candidates}
        revealed = [by_id[card_id] for card_id in chosen_ids]
        for state in revealed:
            game.reveal(state, source=spell.name)
        opponents = _opponents(game, controller.username)
        if not opponents:
            return
        # CR 102.2 for who "an opponent" is; a single-opponent game (the
        # only shape this engine plays) has exactly one to ask.
        chooser = opponents[0]
        picked_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=chooser.username,
                prompt=f"choose one of the two cards {controller.username} revealed",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=1,
                cards=tuple(state.id for state in revealed),
                card_labels=tuple(state.name for state in revealed),
            )
        )
        assert isinstance(picked_ids, tuple)
        if not picked_ids:
            return
        by_revealed_id = {state.id: state for state in revealed}
        chosen = by_revealed_id[picked_ids[0]]
        # Already revealed above (both cards were, together, as the
        # sentence's own first instruction) - only the move is left.
        controller.bring_into_the_game(chosen, Zone.HAND)

    return effect


#: The Burning Wish family: "You may reveal a <quality> card you own from
#: outside the game and put it into your hand[. Exile <this>.]" Burning Wish
#: (sorcery), Cunning Wish (instant), Living Wish (creature or land) and every
#: other printing of the template share it, and so do Granted (Fae of Wishes'
#: Adventure) and Vivien, Arkbow Ranger's −5 without the exile tail; the
#: quality is read by the same `_quality_matcher` a library search uses
#: (Glittering Wish's "multicolored" is CR 105.2b's color count), and a
#: quality it cannot read leaves the whole paragraph unread rather than
#: half-run.
_REVEAL_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE = re.compile(
    r"^you may reveal an? (?P<quality>.+?) card you own from outside the game "
    r"and put (?:it|that card) into your hand\.?(?:\s*exile (?P<name>[^.]+)\.?)?$",
    re.IGNORECASE,
)


#: Legion Angel's template: "You may reveal a card you own named <name> from
#: outside the game and put it into your hand." The Burning Wish family's
#: sentence with a name where the quality was.
_REVEAL_NAMED_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE = re.compile(
    r"^you may reveal a card you own named (?P<name>.+?) from outside the game "
    r"and put (?:it|that card) into your hand\.?$",
    re.IGNORECASE,
)


def _read_reveal_from_outside_the_game(
    effect_text: str,
) -> tuple[str, Callable[[CardState], bool], str | None] | None:
    """`(quality, matcher, exiled name or None)` for
    `_REVEAL_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE`, or `None` when the text is
    not that shape or its quality cannot be read."""
    match = _REVEAL_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        named_card = _REVEAL_NAMED_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE.fullmatch(
            " ".join(effect_text.split())
        )
        if named_card is None:
            return None
        # Legion Angel: "a card you own named <name>" - CR 201.2 names are
        # compared whole, ignoring case; the name is whatever the sentence
        # prints (this card's own, for the one printing that has the clause).
        wanted = named_card.group("name").strip().lower()
        return (
            f"named {named_card.group('name').strip()}",
            lambda state: (state.name or "").lower() == wanted,
            None,
        )
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    named = match.group("name")
    return quality, _quality_matcher(quality), named.strip() if named else None


def _reveal_a_quality_card_from_outside_the_game(
    game: "Game",
    controller: Player,
    quality: str,
    matches: Callable[[CardState], bool],
    source: str | None,
    source_id: object,
) -> None:
    """CR 400.11c lets the spell or ability reach outside the game at all,
    CR 108.3b limits it to cards its controller owns, and CR 608.2d makes the
    "you may" and the choice as it resolves - with no candidate there is
    nothing to choose. The reveal and the move are
    `_reveal_and_bring_into_hand`."""
    candidates = controller.owned_outside_the_game(matches)
    if not candidates or not game.may(
        controller,
        f"reveal {_outside_the_game_card_phrase(quality)} you own from outside the game "
        f"and put it into your hand",
        source=source,
        source_id=source_id,
    ):
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt=(
                f"choose {_outside_the_game_card_phrase(quality)} you own from outside the game"
            ),
            source=source,
            source_id=source_id,
            amount=1,
            cards=tuple(state.id for state in candidates),
            card_labels=tuple(state.name for state in candidates),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in candidates}
    for card_id in chosen_ids:
        _reveal_and_bring_into_hand(game, controller, by_id[card_id], source)


def _parse_reveal_from_outside_the_game_into_hand_clause(effect_text: str) -> Effect | None:
    """`_REVEAL_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE`'s shape on a spell, or
    `None`. "Exile <this>" is CR 201.5's reference to this very spell, done
    last as printed, whether or not a card was taken; a name that is not this
    spell's fails closed. Without the tail (Granted) the spell leaves the
    stack the ordinary way (CR 608.2n, CR 715.3d for an Adventure)."""
    read = _read_reveal_from_outside_the_game(effect_text)
    if read is None:
        return None
    quality, matches, named = read

    def effect(game: "Game", spell: CardState) -> None:
        if named is not None and named.lower() != (spell.name or "").lower():
            return
        _reveal_a_quality_card_from_outside_the_game(
            game, game.controller_of(spell), quality, matches, spell.name, source_id_of(spell)
        )
        if named is not None:
            game.exile_cards([spell])

    return effect


def _parse_card_group_alternatives(phrase: str) -> Callable[[CardState], bool] | None:
    """`_parse_card_group_qualifier` over an "A or B" list of descriptions -
    Overlord of the Balemurk's "a non-Avatar creature card or a planeswalker
    card". A card matching *either* description is a candidate; a half
    neither reads takes the whole list down with it (fail-closed)."""
    parts = [part.strip() for part in re.split(r"\s+or\s+", phrase.strip()) if part.strip()]
    predicates: list[Callable[[CardState], bool]] = []
    for part in parts:
        part = re.sub(r"^(?:an?|the)\s+", "", part, flags=re.IGNORECASE).strip()
        predicate = _parse_card_group_qualifier(part)
        if predicate is None:
            return None
        predicates.append(predicate)
    if not predicates:
        return None

    def matches(state: CardState) -> bool:
        return any(predicate(state) for predicate in predicates)

    return matches


#: "This creature's/artifact's/permanent's owner shuffles it/him/her/them
#: into their library." - Fblthp, Impossibly Lost's own "Fblthp's owner
#: shuffles him into their library." (CR 201.5's short-name self-reference,
#: already rewritten to "this permanent" ahead of every parser by `self_
#: normalized_effect_text`), and the real, off-set printing Cerulean
#: Sphinx's own "{U}: This creature's owner shuffles it into their
#: library." - printed directly as CR 700.7's own "this creature", never
#: rewritten at all since it names no card by name to begin with. The
#: self-referential twin of `_CHOOSE_TARGET_OWNER_SHUFFLES_IT_RE`'s
#: *targeted* "[Choose ]target `<X>`. Its owner shuffles it into their
#: library." - the ability's own source, not something it targets.
_SELF_OWNER_SHUFFLES_SELF_INTO_LIBRARY_RE = re.compile(
    r"^this (?:creature|artifact|enchantment|land|planeswalker|permanent|token)'?s "
    r"owner shuffles (?:it|him|her|them) into (?:their|his or her) library\.?$",
    re.IGNORECASE,
)


def _parse_self_owner_shuffles_self_into_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SELF_OWNER_SHUFFLES_SELF_INTO_LIBRARY_RE`'s shape - never a spell's
    own shape (an instant or sorcery card resolving and vanishing off the
    stack has no "owner shuffles it in" sentence printed on it anywhere in
    the pool; every printing of this sentence is a permanent's own triggered
    ability).

    Shuffled in, not placed, the same "position does not matter, the very
    next step randomises the whole library" (CR 701.20a) reading
    `_parse_choose_target_owner_shuffles_it_clause` already gives its own
    targeted twin.
    """
    if for_spell:
        return None
    if _SELF_OWNER_SHUFFLES_SELF_INTO_LIBRARY_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        source = stack_object.source(game)
        if source is None or source.zone not in (
            Zone.BATTLEFIELD,
            Zone.HAND,
            Zone.GRAVEYARD,
            Zone.EXILE,
        ):
            return  # CR 608.2b: no longer a legal object to move.
        owner = game.player(source.owner)
        game.put_cards_into_library([source])
        game.shuffle_library(owner)

    return effect


# --------------------------------------------------------------------------
# Recruit (CR 701.70a)
# --------------------------------------------------------------------------
#
# CR 701.70a: "'Recruit' means 'Draw a card, then discard a card. If you
# discarded a nonland card this way, create a 1/1 white Human Soldier
# creature token.'" Lake-town Lookout's whole dies trigger is the bare word.
#
# The token is built here rather than read off the keyword's reminder text,
# because the reminder text is not what defines it - CR 701.70a is - and the
# card prints the word alone on a line of its own. Everything else reuses the
# machinery the spelled-out sentence would have used anyway: `Game.draw_cards`
# and `_discard_cards` (CR 701.9b lets the discarding player choose which
# card), and `create_tokens` with the same `TokenDefinition` shape
# `_parse_generic_token_descriptor` would have produced from "1/1 white Human
# Soldier creature token".

#: Bare "recruit." (Lake-town Lookout, Bard's Company) as well as "you
#: recruit." (The Queen of Dale's own "an opponent casts their first
#: noncreature spell each turn, you recruit.") - the leading "you" is only
#: ever needed for clarity once a trigger's own condition already names a
#: different player ("an opponent") than the one who recruits, the same
#: reason "you" shows up on some triggered effects and not others across the
#: templating generally; the keyword action itself (CR 701.70a) is unchanged
#: either way.
_RECRUIT_RE = re.compile(r"^(?:you )?recruit\.?$", re.IGNORECASE)

#: CR 701.70a's own token, spelled out because the keyword's own definition
#: is what names it - there is no printed noun phrase on the card to read.
_RECRUIT_TOKEN = TokenDefinition(
    types=(Type.CREATURE,),
    subtypes=("Human", "Soldier"),
    colors=(Color.WHITE,),
    power=1,
    toughness=1,
)


def _parse_recruit_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_RECRUIT_RE`'s shape - CR 701.70a, spelled out.

    The token is conditional on what was actually discarded, so the discard's
    result is read back rather than assumed: `Player.discard` is what
    `_discard_cards` calls, and the cards it moved are the ones checked
    against CR 205.2a's land type. A draw that finds no card (an empty
    library) leaves nothing to discard and so creates no token either - the
    "if" simply does not hold; CR 104.3c's loss for drawing from an empty
    library is `Game.draw_cards`' own business, not this clause's.
    """
    if _RECRUIT_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        game.draw_cards(controller.username, 1)
        if not controller.hand:
            return
        discarded = _discard_cards(
            game, controller, 1, source_name, source_id=source_id_of(stack_object)
        )
        if any(Type.LAND not in state.card.types for state in discarded):
            create_tokens(game, _RECRUIT_TOKEN, controller.username, 1)

    return effect


# --------------------------------------------------------------------------
# Explore (CR 701.44a, CR 701.44b)
# --------------------------------------------------------------------------
#
# CR 701.44a: "Certain spells and abilities instruct a permanent to explore.
# To do so, that permanent's controller reveals the top card of their
# library. If a land card is revealed this way, that player puts that card
# into their hand. Otherwise, that player puts a +1/+1 counter on the
# exploring permanent, then puts the card back on top of their library or
# into their graveyard."
#
# CR 701.44b: "A permanent 'explores' after the process described in rule
# 701.44a is complete, even if some or all of those actions were impossible."
# - so an empty library still counts as having explored; there is simply
# nothing to reveal.
#
# The back-or-graveyard half is exactly `Game.look_at_top_and_split`'s own
# question over one card: which of the cards looked at move to the first
# group, and the caller decides where each group goes. Reusing it rather than
# `Game.surveil` is deliberate - surveil is CR 701.25a's own keyword action
# with its own name, and nothing here is a surveil.


def _explore(
    game: "Game",
    permanent: CardState,
    controller: Player,
    source_name: str,
    *,
    source_id: str | None,
) -> None:
    """One permanent explores (CR 701.44a), whatever the outcome.

    The reveal is CR 701.20a's own keyword action, done through
    `Game.reveal`. The +1/+1 counter is CR 122.1a's, added to the exploring
    permanent - which CR 701.44a names as the exploring one, not the source
    of the ability, though for every printing in the pool they are the same
    object.
    """
    library = controller.library
    if not library:
        return  # CR 701.44b: it explored anyway; there was nothing to reveal.
    top = library[0]
    game.reveal(top, source=source_name)
    if Type.LAND in top.card.types:
        controller.move(top, Zone.HAND)
        return
    if permanent.zone is Zone.BATTLEFIELD:
        game.add_counters(permanent, Counter.PLUS_ONE, 1)
    to_graveyard, back_on_top = game.look_at_top_and_split(
        controller,
        1,
        source=source_name,
        prompt="put the revealed card into your graveyard, or back on top",
        moved_label="your graveyard",
        kept_label="top of your library",
        source_id=source_id,
    )
    for state in to_graveyard:
        game.put_into_graveyard(state)
    for state in reversed(back_on_top):
        controller.library.insert(0, state)
    if back_on_top:
        controller.note_library_changed()  # CR 701.20d


def _explore_each_in_apnap_order(
    game: "Game",
    explorers: list[CardState],
    source_name: str,
    source_id: str | None,
    *,
    twice: bool,
) -> None:
    """One or more permanents explore, one at a time (CR 701.44d).

    CR 701.44d: "If multiple permanents are instructed to explore at the same
    time, the first player in APNAP order who controls (or, in the case of a
    permanent no longer on the battlefield, last controlled; see rule
    701.44c) one or more of those permanents chooses one of them and it
    explores. Then this process is repeated for each remaining instruction to
    explore." CR 101.4 is the APNAP order itself.

    Grouped by each permanent's own controller - live if it can still be
    found, or its last known controller (CR 701.44c) - rather than by the
    resolving ability's controller, so this reads correctly even for a
    permanent nobody currently controls. With zero or one explorer (every
    printed shape this parser currently reaches: a self-reference or a single
    target both name at most one permanent) the loop runs once with nothing
    to choose between, exactly CR 608.2d's "no impossible or trivial choice".
    """
    remaining = list(explorers)
    while remaining:
        by_controller: dict[str, list[CardState]] = {}
        for permanent in remaining:
            by_controller.setdefault(game.controller_of(permanent).username, []).append(permanent)
        chooser = next(
            player for player in _players_in_apnap_order(game) if player.username in by_controller
        )
        own = by_controller[chooser.username]
        if len(own) == 1:
            chosen = own[0]
        else:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=chooser.username,
                    prompt="choose a permanent to explore next",
                    source=source_name,
                    amount=1,
                    cards=tuple(permanent.id for permanent in own),
                    source_id=source_id,
                )
            )
            by_id = {permanent.id: permanent for permanent in own}
            chosen = by_id.get(chosen_ids[0], own[0]) if chosen_ids else own[0]
        remaining.remove(chosen)
        controller = game.controller_of(chosen)
        _explore(game, chosen, controller, source_name, source_id=source_id)
        if twice:
            _explore(game, chosen, controller, source_name, source_id=source_id)


#: The generic "<subject> explores[, then it explores again]." clause (CR
#: 701.44a-d), read off any triggered, activated, or spell text - Merfolk
#: Branchwalker's "it explores.", Legion Vanguard's "This creature
#: explores.", Miner's Guidewing's "target creature you control explores.",
#: Jadelight Ranger's "it explores, then it explores again.". `for_spell`
#: gates the self-referring subjects out: CR 701.44a instructs "a permanent"
#: to explore, and a resolving spell is not itself a permanent (CR 300.1) to
#: be that subject - only its targeted or "each ... you control" forms make
#: sense on a spell (Enter the Unknown, Over the Edge).
#:
#: A literal self-reference by the card's own printed name reaches this the
#: same way every other self-referring clause in this file does: normalized
#: to "this permanent" by `_self_normalized_effect_text` before the second,
#: fallback parse attempt - Amalia Benavides Aguirre's own "Amalia Benavides
#: Aguirre explores. Then destroy ..." keeps its dedicated whole-sentence
#: parser below instead (its second sentence is not part of this shape at
#: all), but shares this function's `source_or_last_known` fix for CR
#: 701.44c.
_EXPLORES_CLAUSE_RE = re.compile(
    r"^(?P<subject>this creature|this permanent|it|"
    r"target creature you control|each creature you control)\s+explores"
    r"(?P<again>,?\s*then it explores again)?\.?$",
    re.IGNORECASE,
)


def _parse_explores_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_EXPLORES_CLAUSE_RE`'s shape; see the banner above.

    - **CR 701.44a** - what exploring does, run by the shared `_explore`.
    - **CR 701.44b** - it explored even if every action was impossible (an
      empty library) - `_explore` itself returns immediately in that case,
      after nothing.
    - **CR 701.44c** - a permanent gone before this resolves still explores,
      by its last known information, and gets no counter (`_explore`'s own
      `permanent.zone is Zone.BATTLEFIELD` check reads false either for a
      live object that has moved off the battlefield, found by the same id
      wherever it now sits, or for a detached last-known-information
      snapshot, since both carry the zone they were last actually in).
    - **CR 701.44d** - multiple explorers from one instruction go one at a
      time, in APNAP order; `_explore_each_in_apnap_order` above.
    """
    match = _EXPLORES_CLAUSE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    subject = match.group("subject").lower()
    twice = match.group("again") is not None
    is_self = subject in ("this creature", "this permanent", "it")
    if is_self and for_spell:
        return None
    is_target = subject == "target creature you control"
    if is_target and not _targets_understood("target creature you control", count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        source_id = source_id_of(stack_object)
        if is_self:
            assert isinstance(stack_object, AbilityOnStack)
            source = stack_object.source_or_last_known(game)
            explorers = [source] if source is not None else []
        elif is_target:
            explorers = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ]
        else:  # "each creature you control"
            controller_username = game.controller_of(stack_object).username
            explorers = [
                permanent
                for permanent in list(game.battlefield)
                if game.controller_of(permanent).username == controller_username
                and game.characteristics_of(permanent).is_creature
            ]
        _explore_each_in_apnap_order(game, explorers, source_name, source_id, twice=twice)

    return effect


#: Amalia Benavides Aguirre's whole trigger: "<Name> explores. Then destroy
#: all other creatures if its power is exactly N." Read whole rather than
#: clause by clause, because the second sentence's "its" is anaphoric
#: (CR 700.7's "this [something]" read back onto the exploring permanent) and
#: because the *if* is checked after the explore, not before - the +1/+1
#: counter the explore may add is exactly what makes the power reach N.
_EXPLORES_THEN_CONDITIONAL_MASS_DESTROY_RE = re.compile(
    r"^(?P<name>.+?) explores\.\s*"
    r"then destroy all (?P<rest>.+?) if its power is exactly (?P<n>\d+)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_explores_then_conditional_mass_destroy(text: str) -> AbilityEffect | None:
    """`_EXPLORES_THEN_CONDITIONAL_MASS_DESTROY_RE`'s shape - Amalia
    Benavides Aguirre's own "whenever you gain life" trigger.

    "All other creatures" is every creature on the battlefield except the
    exploring permanent itself, read off the computed board
    (`Game.computed_board`) through the same `_parse_mass_type_qualifier`
    every other mass clause in this file uses, with the "other" stripped off
    and applied as an exclusion by id (CR 700.7 again).

    The power compared is the *computed* one (`Game.power_of`), which is what
    CR 613.4c's layer 7c leaves after the +1/+1 counter this same resolution
    may have just added (CR 122.1a). A permanent no longer on the battlefield
    has no power to compare and destroys nothing.
    """
    match = _EXPLORES_THEN_CONDITIONAL_MASS_DESTROY_RE.fullmatch(text.strip())
    if match is None:
        return None
    rest = match.group("rest").strip()
    others_only = rest.lower().startswith("other ")
    if others_only:
        rest = rest[len("other ") :].strip()
    type_matches = _parse_mass_type_qualifier(rest)
    if type_matches is None:
        return None
    threshold = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        # CR 701.44c: gone before this resolves, its last known information
        # still says which object explored - `source`, not `source_or_last_
        # known`, used to make Amalia stop exploring entirely the moment she
        # left the battlefield, which was simply wrong (see `_explore_each_
        # in_apnap_order`'s docstring, this shape's generic twin).
        source = ability.source_or_last_known(game)
        if source is None:
            return
        _explore(game, source, controller, ability.source_name, source_id=source_id_of(ability))
        power = game.power_of(source) if source.zone is Zone.BATTLEFIELD else None
        if power != threshold:
            return
        board = game.computed_board()
        doomed = [
            permanent
            for permanent in list(game.battlefield)
            if type_matches(board.of(permanent)) and not (others_only and permanent.id == source.id)
        ]
        for permanent in doomed:
            if permanent.zone is Zone.BATTLEFIELD:
                game.destroy(permanent)

    return effect


# --------------------------------------------------------------------------
# Exiling the top of your library and being allowed to play it
# --------------------------------------------------------------------------
#
# Tablet of Discovery: "mill a card. You may play that card this turn." - CR
# 601.3's "a rule or effect allows that player to cast it" granted over a
# card that is not in exile at all: the card is in the graveyard (CR
# 701.17a), which is the zone the permission has to name. Read whole: "that
# card" is anaphora for what the first sentence just moved, and neither
# sentence is readable alone. (Interdimensional Web Watch's exile-top form is
# `_parse_exile_then_play_permission_clauses`'s, with every other duration.)

_MILL_THEN_PLAY_THAT_CARD_RE = re.compile(
    rf"^mill (?P<n>{COUNT}) cards?\.\s*you may play (?:that|those) cards?\s+this turn\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_mill_then_play_that_card(text: str) -> AbilityEffect | None:
    """`_MILL_THEN_PLAY_THAT_CARD_RE`'s shape - Tablet of Discovery's own
    enters trigger.

    The permission names the *graveyard* (CR 701.17a is where the mill put
    the card), and it is a permission, not an instruction: "you may play"
    grants CR 601.3's allowance and never plays anything itself, so there is
    no CR 608.2d question asked here at all - the choice is made later, when
    the player would actually play it.
    """
    match = _MILL_THEN_PLAY_THAT_CARD_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        milled = _mill(game, controller, count)
        for state in milled:
            if state.zone is not Zone.GRAVEYARD:
                continue
            game.grant_play_permission(
                state,
                controller.username,
                action=PlayAction.PLAY,
                pays_mana_cost=True,
                source_name=ability.source_name,
                zone=Zone.GRAVEYARD,
                rule="CR 601.3",
            )

    return effect


# --------------------------------------------------------------------------
# "<player> mill(s) N cards, then [you] [may] return <description> from your
# graveyard to your hand."
# --------------------------------------------------------------------------
#
# The hand-destination twin of `_MILL_THEN_MAY_RETURN_CREATURE_RE` above,
# with the candidate description read by `_parse_card_group_alternatives`
# rather than hard-coded to a creature with a mana value bound. One reader
# for every form the sentence is printed in:
#
#   Overlord of the Balemurk  "mill four cards, then you may return a
#                             non-Avatar creature card or a planeswalker card
#                             from your graveyard to your hand" (optional)
#   Takenuma, Abandoned Mire  "Mill three cards, then return a creature or
#                             planeswalker card from your graveyard to your
#                             hand." (mandatory; a Channel ability)
#   Inspiration from Beyond   "... then return an instant or sorcery card ..."
#                             (mandatory; a spell)
#   Witherbloom Command       "Target player mills three cards, then you return
#                             a land card from your graveyard to your hand."
#                             (a mode; the mill is the *targeted* player's,
#                             the return is the controller's own)

_MILL_THEN_RETURN_TO_HAND_RE = re.compile(
    rf"^(?:(?P<subject>target player|you) )?mills? (?P<n>{COUNT}) cards?, "
    r"then (?:you )?(?P<may>may )?return (?P<group>.+?) "
    r"from your graveyard to your hand\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_mill_then_return_to_hand_clause(text: str) -> TargetedClause | None:
    """`_MILL_THEN_RETURN_TO_HAND_RE`'s shape, for a spell, a mode, or an
    activated or triggered ability alike - the effect reads only
    `Game.controller_of` and the stack object's own targets, both of which
    every stack object has.

    CR 608.2c: the instructions run in the order written, so the candidate
    pool is read *after* the mill, and a card this same resolution just put
    into the graveyard (CR 701.17a) is itself eligible - nothing in the
    sentence excludes it. The card is chosen as the effect is applied, never
    targeted (CR 608.2d), and only from the controller's own graveyard ("you
    return ... from your graveyard") even when a *target player* did the
    milling. With no candidate nothing is asked (CR 608.2d: no legal option
    to choose). A printed "may" asks `Game.may` first; without it one card is
    returned whenever one can be.

    "Target player" mills each still-legal target (CR 608.2b); an illegal one
    mills nothing, and the return - which never involved it - still happens.
    """
    match = _MILL_THEN_RETURN_TO_HAND_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    predicate = _parse_card_group_alternatives(match.group("group"))
    if predicate is None:
        return None
    targets_a_player = (match.group("subject") or "").lower() == "target player"
    optional = match.group("may") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        source_id = source_id_of(stack_object)
        if targets_a_player:
            for target in game.resolve_targets(stack_object):
                if isinstance(target, Player):
                    _mill(game, target, count)
        else:
            _mill(game, controller, count)
        candidates = [state for state in list(controller.graveyard) if predicate(state)]
        if not candidates:
            return
        if optional and not game.may(
            controller,
            "return a card from your graveyard to your hand",
            source=source_name,
            source_id=source_id,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a card to return to your hand",
                source=source_name,
                source_id=source_id,
                amount=1,
                cards=tuple(state.id for state in candidates),
            )
        )
        by_id = {state.id: state for state in candidates}
        for card_id in chosen_ids:
            state = by_id.get(card_id)
            if state is not None and state.zone is Zone.GRAVEYARD:
                controller.move(state, Zone.HAND)

    return effect


# --------------------------------------------------------------------------
# Rapid Rescue: mill, then choose from among *the milled cards*
# --------------------------------------------------------------------------
#
# "Mill two cards. You may put a permanent card from among the milled cards
# into your hand. You gain 2 life."
#
# "From among the milled cards" is a narrower pool than "from your graveyard"
# - anything already there is not a candidate - so the three sentences have
# to be read together: only the first sentence knows which cards those are
# (CR 700.7's anaphora again).

#: Rapid Rescue's fixed "a", Vorinclex // The Grand Evolution's chapter I
#: "up to two ... onto the battlefield": `QUANTITY` reads either. A bare
#: fixed count needs the printed "you may" for its CR 608.2d optionality,
#: exactly as `_SELECT_FROM_TOP_RE` requires it above; "up to N"/"any number
#: of" carry their own (CR 107.1c) and print no "you may" at all.
#:
#: Gyruda, Doom of Depths and Fetch Quest widen it: "each player mills four
#: cards" (every player's mill is one pool - CR 701.17a, once per player),
#: a "Then " in front of the put, a mandatory "put a ..." with no "you may"
#: (CR 608.2d: one must be chosen when any qualifies), an Oxford-comma list
#: ("a creature, enchantment, or land card"), a mana-value condition on the
#: description ("with an even mana value", `_PUT_DESCRIPTION_RE`), and "under
#: your control" (CR 110.2a: the controller of the resolving ability gets it,
#: whoever owns it).
_MILL_THEN_MAY_TAKE_FROM_MILLED_RE = re.compile(
    # "Mill two cards. You may put ..." (Rapid Rescue, its own full stop) and
    # "mill four cards, then put ..." (Cantankerous Keepers and its Silvan
    # Rally/Speak Secrets siblings, one comma-joined clause with no second
    # sentence) both close CR 608.2c's first instruction the same way - a
    # comma before "then" is not a different shape, only a different printed
    # separator for it.
    rf"^(?:(?P<each>each player mills)|mill) (?P<mill_n>{COUNT}) cards?(?:\.|,)\s*"
    # "put all `<quality>` cards ..." (Cantankerous Keepers) has no printed
    # count at all - CR 608.2d is not in play, there is no choice, every
    # qualifying card among the milled ones goes; `take_all` is read ahead of
    # `quantity_pattern` (whose own grammar has no "all") rather than folded
    # into it, so `QUANTITY`'s shared vocabulary used by every other
    # template stays exactly as it was.
    rf"(?:then\s+)?(?P<may>you may )?(?:put|return) "
    rf"(?:(?P<take_all>all)|{quantity_pattern('take_n')}) "
    # A single-word quality (Rapid Rescue's "a permanent card") or an
    # "and/or"/"and"/"or"/comma-joined list of them (Smuggler's Surprise's
    # own first Spree mode: "creature and/or land cards"; Glamdring, Foe-
    # hammer // Gleam of Death's own "instant and sorcery cards") - CR
    # 205.3's "and/or" reads as an inclusive or, the same list `_parse_card_
    # group_alternatives` already reads for `_parse_mill_that_many_then_
    # take_from_among_them`. A bare "and" between two card-type words in
    # this position is the identical inclusive reading, not a conjunction:
    # "instant and sorcery cards" means a card that is either type, the same
    # way `_quality_matcher`'s own comma/"or" list already reads "artifact,
    # creature, or land" - a card cannot itself be an instant *and* a
    # sorcery at once (CR 300.1), so "and" here is templating shorthand for
    # the same union `_parse_card_group_alternatives` builds for "or".
    r"(?P<group>[a-z]+(?:(?:,| (?:and/or|and|or)|, or) [a-z]+)*) cards?"
    r"(?P<condition> with an? (?:even|odd) mana value| with mana value \d+ or less)? "
    # "from among the milled cards" (Rapid Rescue) and "from among them"
    # (Cantankerous Keepers, Most Decrepit Old Bird // Speak Secrets,
    # Thranduil, Sindarin Liege // Silvan Rally) are the same anaphoric
    # reference (CR 400.7) to the cards this clause's own first sentence
    # just milled - two printed shapes for one referent, not two different
    # pools.
    # Vivien on the Hunt's own "put any number of creature cards milled this
    # way into your hand" carries no "from among" at all - "milled this way"
    # is its own complete CR 400.7 anaphor, read the same as the other two.
    # Cache Grab's own "from among the cards milled this way" (R0a-T7) fuses
    # the "from among" prefix with that participial phrasing rather than
    # either of the other two nouns.
    r"(?:from among (?:the milled cards|the cards milled this way|those cards|them)"
    r"|milled this way) "
    r"(?P<dest>into your hand|to your hand|onto the battlefield(?: under your control)?)"
    r"\.(?:\s*you gain (?P<life>\d+) life\.?)?"
    # Cache Grab's own rider: "If you control a Squirrel or returned a
    # Squirrel card to your hand this way, create a Food token." - a
    # resolution-time condition (CR 608.2c, checked once the mill and the
    # put/return above have already happened) on either half of the same
    # instruction: the controller's *current* board, or which subtype the
    # card just taken carried. Generalised on the subtype word (`\1` backref
    # ties the two halves to the same one, CR 205.3m's own creature types
    # never differing between them on one printed card) and on the
    # consequence, read the ordinary way through `parse_mixed_effect[_for_
    # spell]` rather than pinned to Cache Grab's own "create a Food token."
    rf"(?:\s*if you control an? (?P<subtype>[a-z]+) or returned an? (?P=subtype) card"
    rf"(?: to your hand)? this way, (?P<consequence>.+?)\.?)?$",
    re.IGNORECASE | re.DOTALL,
)


def _mill_then_may_take_from_milled_runner(
    text: str,
) -> Callable[["Game", Player, str, str | None], None] | None:
    """Compile `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`'s shape into one runner
    both the spell side (Rapid Rescue) and the ability side (Vorinclex //
    The Grand Evolution's own chapter I) call.

    The optional trailing life gain is part of this pattern rather than left
    to the ordinary player-clause path, because a whole-text parser has to
    consume the whole text: matching only the first two sentences would leave
    the third unread and the effect would fail closed on it (CR 608.2c has no
    half-run). CR 119.3 is what the gain does.
    """
    match = _MILL_THEN_MAY_TAKE_FROM_MILLED_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("mill_n"))
    if count is None:
        return None
    take_all = match.group("take_all") is not None
    if take_all:
        # CR 608.2d: "all" prints no count and no choice at all - every
        # qualifying card among the milled ones goes, never a `you may` or a
        # `CHOOSE_CARDS` question over how many.
        quantity = None
        mandatory = True
    else:
        quantity = parse_quantity(match.group("take_n"))
        if quantity is None or quantity.source not in (
            QuantitySource.FIXED,
            QuantitySource.ANY_NUMBER,
        ):
            return None
        mandatory = quantity.exact and match.group("may") is None
        if mandatory and quantity.amount != 1:
            return None
    group_text = re.sub(r",\s*(?:or\s+)?", " or ", match.group("group"), flags=re.IGNORECASE)
    # "and/or" first (its own inclusive-or wording), then a bare "and" left
    # over (Glamdring, Foe-hammer // Gleam of Death's own "instant and
    # sorcery") - both normalise to the "or" `_parse_card_group_alternatives`
    # already splits on, per this regex's own comment above on why "and" is
    # inclusive here.
    normalized_group = re.sub(r"\s+and(?:/or)?\s+", " or ", group_text, flags=re.IGNORECASE)
    group_predicate = _parse_card_group_qualifier(group_text) or _parse_card_group_alternatives(
        normalized_group
    )
    if group_predicate is None:
        return None
    printed_condition = (match.group("condition") or "").strip().lower()
    parity = re.search(r"\b(even|odd)\b", printed_condition)
    ceiling = re.search(r"mana value (\d+) or less", printed_condition)
    condition = _PutDescription(
        text=printed_condition,
        quality=lambda state: True,
        max_mv=int(ceiling.group(1)) if ceiling else None,
        x_bound=False,
        parity=parity.group(1) if parity else None,
    )

    def predicate(state: CardState) -> bool:
        return group_predicate(state) and condition.admits(state)

    each_player = match.group("each") is not None
    destination = match.group("dest").lower()
    if destination.startswith("onto the battlefield"):
        destination = "onto the battlefield"
    elif destination == "to your hand":
        # "return a card ... to your hand" (Midnight Tilling) means the same
        # move as "put a card ... into your hand" - only the verb differs.
        destination = "into your hand"
    life = int(match.group("life")) if match.group("life") else 0
    condition_subtype = match.group("subtype")
    consequence_text = (match.group("consequence") or "").strip()
    consequence_for_spell = (
        parse_mixed_effect_for_spell(consequence_text) if consequence_text else None
    )
    consequence_for_ability = parse_mixed_effect(consequence_text) if consequence_text else None
    if consequence_text and consequence_for_spell is None and consequence_for_ability is None:
        return None
    if take_all:
        take_noun = "all cards"
    elif quantity.source is QuantitySource.ANY_NUMBER:
        take_noun = "any number of cards"
    elif quantity.exact and quantity.amount == 1:
        take_noun = "a card"
    else:
        take_noun = f"up to {quantity.amount} cards"

    def run(
        game: "Game",
        controller: Player,
        source_name: str,
        source_id: str | None,
        stack_object: "StackObject | None" = None,
    ) -> None:
        milled = [
            state
            for player in (game.players_in_game if each_player else [controller])
            for state in _mill(game, player, count)
        ]
        candidates = [
            state for state in milled if state.zone is Zone.GRAVEYARD and predicate(state)
        ]
        chosen: list[CardState] = []
        if candidates and take_all:
            # No decision at all: CR 608.2d's "may"/"choose" machinery never
            # runs for a bare "all" - every qualifying card goes.
            chosen = candidates
        elif candidates and mandatory:
            # CR 608.2d: not optional - one qualifying card must be chosen,
            # and with only one there is nothing to ask.
            if len(candidates) == 1:
                chosen = candidates
            else:
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt=f"choose {take_noun} to put {destination}",
                        source=source_name,
                        source_id=source_id,
                        amount=1,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                by_id = {state.id: state for state in candidates}
                chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        elif candidates:
            if quantity.exact:
                # A single optional pick, CR 608.2d's "may" gate before
                # naming candidates - unchanged from before this family
                # read any other quantifier.
                if game.may(
                    controller,
                    f"put {take_noun} from among the milled cards {destination}",
                    source=source_name,
                    source_id=source_id,
                ):
                    chosen_ids = game.ask(
                        Decision(
                            kind=DecisionKind.CHOOSE_CARDS,
                            player=controller.username,
                            prompt=f"choose {take_noun} to put {destination}",
                            source=source_name,
                            source_id=source_id,
                            amount=1,
                            cards=tuple(state.id for state in candidates),
                        )
                    )
                    by_id = {state.id: state for state in candidates}
                    chosen = [
                        state for card_id in chosen_ids if (state := by_id.get(card_id)) is not None
                    ]
            else:
                # "up to N"/"any number of": CR 107.1c - zero to the
                # ceiling is one question, with no separate "may" gate.
                ceiling = (
                    len(candidates)
                    if quantity.amount is None
                    else min(quantity.amount, len(candidates))
                )
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt=f"put {take_noun} from among the milled cards {destination}",
                        source=source_name,
                        source_id=source_id,
                        amount=ceiling,
                        exact=False,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                by_id = {state.id: state for state in candidates}
                chosen = [
                    state for card_id in chosen_ids if (state := by_id.get(card_id)) is not None
                ]
        for state in chosen:
            if state.zone is not Zone.GRAVEYARD:
                continue
            if destination == "into your hand":
                controller.move(state, Zone.HAND)
            else:
                # CR 110.4a's permanent card, put onto the battlefield
                # without being cast (no spell, so no cast trigger).
                game.put_onto_battlefield(state, controller.username)
        if life:
            game.gain_life(controller, life)
        if condition_subtype and stack_object is not None:
            # Cache Grab's own rider (CR 608.2c, checked once the put/return
            # above has already happened): "you control a `<subtype>`" reads
            # the controller's current board; "returned a `<subtype>` card
            # to your hand this way" reads which of the cards this
            # resolution just moved to hand carried it - CR 400.7 already
            # keeps `chosen` as the same objects `controller.move` just
            # mutated in place, so `state.zone` is HAND by now.
            subtype_lower = condition_subtype.lower()
            controls_subtype = any(
                subtype_lower
                in {each.lower() for each in game.characteristics_of(permanent).subtypes}
                for permanent in game.permanents_controlled_by(controller.username)
            )
            returned_subtype = any(
                subtype_lower in {each.lower() for each in state.subtypes}
                for state in chosen
                if state.zone is Zone.HAND
            )
            if controls_subtype or returned_subtype:
                consequence = (
                    consequence_for_spell
                    if isinstance(stack_object, CardState)
                    else consequence_for_ability
                )
                if consequence is not None:
                    consequence(game, stack_object)

    return run


def _parse_mill_then_may_take_from_milled(text: str) -> Effect | None:
    """The runner above, on a spell (CR 608.3) - Rapid Rescue."""
    run = _mill_then_may_take_from_milled_runner(text)
    if run is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        run(game, game.controller_of(spell), spell.name, source_id_of(spell), spell)

    return effect


def _parse_mill_then_may_take_from_milled_ability(text: str) -> AbilityEffect | None:
    """The runner above, on a triggered or activated ability (CR 603.3a,
    CR 602.2a) - Vorinclex // The Grand Evolution's chapter I."""
    run = _mill_then_may_take_from_milled_runner(text)
    if run is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        run(
            game,
            game.player(ability.controller),
            ability.source_name,
            source_id_of(ability),
            ability,
        )

    return effect


#: "Mill `<n>` cards, then put all `<quality>` cards from among them into your
#: hand." (CR 701.13c's mill, CR 608.2c's "then") - Glamdring, Foe-hammer //
#: Gleam of Death's Adventure half. `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`'s own
#: `quantity_pattern` reads "up to `<n>`"/"any number of"/a bare number, never
#: the word "all" - this is the sibling shape for the unconditional,
#: everything-that-qualifies count `parse_quantity` has no `Quantity` for at
#: all, so it needs its own regex and its own (unconditional, no `Decision`)
#: runner rather than a new branch inside that one.
_MILL_THEN_PUT_ALL_FROM_MILLED_RE = re.compile(
    r"^mill (?P<mill_n>" + COUNT + r") cards?, then put all "
    r"(?P<group>[a-z]+(?:(?:,| (?:and/or|and|or)|, or) [a-z]+)*) cards? from among them "
    r"into your hand\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _mill_then_put_all_from_milled_runner(
    text: str,
) -> Callable[["Game", Player, str, str | None], None] | None:
    """`_MILL_THEN_PUT_ALL_FROM_MILLED_RE`'s shape, compiled once for both
    the spell and the ability side - the identical split
    `_mill_then_may_take_from_milled_runner` already draws."""
    match = _MILL_THEN_PUT_ALL_FROM_MILLED_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("mill_n"))
    if count is None:
        return None
    # CR 205.2a's card-type list always reads as a union - a card qualifying
    # under "instant and sorcery cards" needs only one of the two types, the
    # same non-intersective "and" `_parse_card_group_alternatives` already
    # reads for an "and/or" list - so every joining word (a comma, "and",
    # "and/or", or "or") is folded to "or" before that reader ever sees it.
    group_text = re.sub(
        r",\s*(?:and(?:/or)?\s+|or\s+)?|\s+and/or\s+|\s+and\s+",
        " or ",
        match.group("group"),
        flags=re.IGNORECASE,
    )
    group_predicate = _parse_card_group_qualifier(group_text) or _parse_card_group_alternatives(
        group_text
    )
    if group_predicate is None:
        return None

    def run(game: "Game", controller: Player, source_name: str, source_id: str | None) -> None:
        milled = _mill(game, controller, count)
        for state in milled:
            if state.zone is Zone.GRAVEYARD and group_predicate(state):
                controller.move(state, Zone.HAND)

    return run


def _parse_mill_then_put_all_from_milled(text: str) -> Effect | None:
    """The runner above, on a spell (CR 608.3) - Gleam of Death."""
    run = _mill_then_put_all_from_milled_runner(text)
    if run is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        run(game, game.controller_of(spell), spell.name, source_id_of(spell))

    return effect


def _parse_mill_then_put_all_from_milled_ability(text: str) -> AbilityEffect | None:
    """The runner above, on a triggered or activated ability."""
    run = _mill_then_put_all_from_milled_runner(text)
    if run is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        run(game, game.player(ability.controller), ability.source_name, source_id_of(ability))

    return effect


# --------------------------------------------------------------------------
# Looking at the top N and taking some of them (CR 701.20e)
# --------------------------------------------------------------------------
#
# Two spells, one shape: look at a number of cards off the top, put some of
# them somewhere, and bottom the rest in a random order. CR 701.20e is the
# "look at", and the randomisation is not a shuffle (CR 701.24a's word is
# never printed here) - the same non-shuffle bottoming
# `_parse_look_top_n_may_battlefield_creature_bonus_clause` already does.
#
# - Consult the Star Charts: "Look at the top X cards of your library, where
#   X is the number of lands you control. Put one of those cards into your
#   hand. If this spell was kicked, put two of those cards into your hand
#   instead. Put the rest on the bottom of your library in a random order."
# - Michelangelo's Technique: "Look at the top eight cards of your library.
#   Put up to two creature cards with total mana value 6 or less from among
#   them onto the battlefield and the rest on the bottom of your library in a
#   random order."


def _bottom_in_random_order(game: "Game", player: Player, cards: list[CardState]) -> None:
    """Put `cards` on the bottom of `player`'s library in a random order.

    Not a shuffle: CR 701.24a's verb is never printed on either card, and
    only the named cards are randomised, so `Game.shuffle_library` would be
    the wrong action as well as the wrong word. The seed is derived the same
    way `_parse_look_top_n_may_battlefield_creature_bonus_clause` derives its
    own, so a game replays identically.
    """
    if not cards:
        return
    rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:bottom-{len(cards)}")  # noqa: S311
    ordered = list(cards)
    rng.shuffle(ordered)
    for state in ordered:
        player.move(state, Zone.LIBRARY)
    game.shuffles_performed += 1


#: "Whenever you attack, look at the top `<n>` cards of your library. You may
#: cast a spell from among them with mana value less than or equal to the
#: greatest power among attacking creatures you control without paying its
#: mana cost. Put the rest on the bottom of your library in a random order."
#: - Cosmic Cube's own attack trigger. A third member of the "look at a
#: number of cards, act on some, bottom the rest in a random order" family
#: just above, with its own mv bound (CR 202.3) read off the board rather
#: than printed as a number, and CR 118.9's "without paying its mana cost"
#: (X counts as 0, CR 107.3b, matching `can_cast_during_resolution`'s own
#: `mana_value_below` reading of that rider).
_LOOK_TOP_CAST_LE_GREATEST_ATTACKING_POWER_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards of your library\.\s*"
    r"you may cast a spell from among them with mana value less than or equal to "
    r"the greatest power among attacking creatures you control without paying "
    r"its mana cost\.\s*"
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_look_top_cast_le_greatest_attacking_power_whole_text(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_LOOK_TOP_CAST_LE_GREATEST_ATTACKING_POWER_RE`'s shape, read whole:
    the mana-value bound is CR607.1 anaphora onto the board ("the greatest
    power among attacking creatures you control"), not a fixed printed
    number, so no earlier per-clause parser in the "look/bottom" family
    reads it.

    Ability-only: `game.combat` is asked for the controller's own current
    attackers, which only makes sense for a triggered ability (`Whenever you
    attack`) resolving during that same combat.
    """
    if for_spell:
        return None
    match = _LOOK_TOP_CAST_LE_GREATEST_ATTACKING_POWER_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = parse_count(match.group("n"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        controller = game.controller_of(ability)
        attackers = [
            state
            for aid in game.combat.attacker_ids
            if (state := game.find_by_id(aid)) is not None
            and state.controller == controller.username
        ]
        greatest = max((game.power_of(state) or 0 for state in attackers), default=0)
        looked_at = list(controller.library[: max(n, 0)])
        for state in looked_at:
            game.look(state, controller.username, source=ability.source_name)
        legal = [
            state
            for state in looked_at
            if not state.card.is_land
            and game.can_cast_during_resolution(
                state, controller.username, mana_value_below=greatest + 1
            )
        ]
        chosen: CardState | None = None
        if legal:
            taken = game.may(
                controller,
                f"cast a spell among the top {n} cards of your library with mana "
                f"value {greatest} or less, without paying its mana cost",
                source=ability.source_name,
                source_id=source_id_of(ability),
                cards=tuple(legal),
            )
            if taken:
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt="choose a spell to cast without paying its mana cost",
                        source=ability.source_name,
                        source_id=source_id_of(ability),
                        amount=1,
                        cards=tuple(state.id for state in legal),
                    )
                )
                assert isinstance(chosen_ids, tuple)
                chosen = next(state for state in legal if state.id == chosen_ids[0])
        if chosen is not None:
            game.cast_during_resolution(
                chosen, controller.username, source_name=ability.source_name, rule="CR 608.2g"
            )
        rest = [state for state in looked_at if chosen is None or state.id != chosen.id]
        _bottom_in_random_order(game, controller, rest)

    return effect


_LOOK_TOP_LANDS_TAKE_TO_HAND_RE = re.compile(
    r"^look at the top x cards of your library, where x is the number of lands you control\.\s*"
    rf"put (?P<n>{COUNT}) of those cards into your hand\.\s*"
    rf"if this spell was kicked, put (?P<kicked>{COUNT}) of those cards "
    r"into your hand instead\.\s*"
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_look_top_lands_take_to_hand(text: str) -> Effect | None:
    """`_LOOK_TOP_LANDS_TAKE_TO_HAND_RE`'s shape - Consult the Star Charts.

    X here is CR 107.3c's - "if ... the value of X is defined by the text of
    that spell or ability, then that's the value of X" - rather than
    CR 107.3a's kind announced alongside a cost, since the card defines it
    itself ("where X is the number of lands you control"). So it is counted at
    resolution off the computed board (`Game.computed_board`), the same way
    `count_expression`'s own "you control" phrases are.

    Whether the spell was kicked is read off `Game.cast_record`, which is
    where the announcement of CR 118.8b's optional additional cost was
    recorded; it is paid as the spell is cast, long before this runs.
    """
    match = _LOOK_TOP_LANDS_TAKE_TO_HAND_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    plain = parse_count(match.group("n"))
    kicked_count = parse_count(match.group("kicked"))
    if plain is None or kicked_count is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        board = game.computed_board()
        lands = sum(
            1
            for permanent in game.permanents_controlled_by(controller.username)
            if Type.LAND in board.of(permanent).types
        )
        looked = list(controller.library[:lands])
        if not looked:
            return
        wanted = kicked_count if game.cast_record(spell).kicked else plain
        wanted = min(wanted, len(looked))
        taken: list[CardState] = []
        if wanted:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"put {wanted} of the cards looked at into your hand",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=wanted,
                    cards=tuple(state.id for state in looked),
                )
            )
            by_id = {state.id: state for state in looked}
            taken = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        for state in taken:
            controller.move(state, Zone.HAND)
        _bottom_in_random_order(game, controller, [s for s in looked if s not in taken])

    return effect


_LOOK_TOP_N_PUT_TOTAL_MV_ONTO_BATTLEFIELD_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards of your library\.\s*"
    rf"put up to (?P<take>{COUNT}) (?P<group>[a-z]+) cards with total mana value "
    r"(?P<total>\d+) or less from among them onto the battlefield and the rest on the "
    r"bottom of your library in a random order\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_look_top_n_put_total_mv_onto_battlefield(text: str) -> Effect | None:
    """`_LOOK_TOP_N_PUT_TOTAL_MV_ONTO_BATTLEFIELD_RE`'s shape -
    Michelangelo's Technique.

    Two bounds at once, and both are the choosing player's to respect: at
    most `take` cards - "up to two" runs from zero upward, so choosing none
    is legal - whose mana values (CR 202.3) sum to at most `total`. An answer
    breaking either is refused rather than
    quietly trimmed - CR 608.2d makes an illegal choice not a choice, and
    silently correcting one would hide a caller's bug the way this file
    refuses to hide an unread clause.
    """
    match = _LOOK_TOP_N_PUT_TOTAL_MV_ONTO_BATTLEFIELD_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    look = parse_count(match.group("n"))
    take = parse_count(match.group("take"))
    if look is None or take is None:
        return None
    predicate = _parse_card_group_qualifier(match.group("group"))
    if predicate is None:
        return None
    total_bound = int(match.group("total"))

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        looked = list(controller.library[:look])
        if not looked:
            return
        candidates = [state for state in looked if predicate(state)]
        taken: list[CardState] = []
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"put up to {take} cards with total mana value {total_bound} "
                        "or less onto the battlefield"
                    ),
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=min(take, len(candidates)),
                    cards=tuple(state.id for state in candidates),
                    exact=False,
                )
            )
            by_id = {state.id: state for state in candidates}
            taken = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
            if len(taken) > take:
                raise ValueError(
                    f"{spell.name} puts up to {take} cards onto the battlefield, not {len(taken)}"
                )
            total = sum(state.card.cmc or 0 for state in taken)
            if total > total_bound:
                raise ValueError(
                    f"{spell.name} allows total mana value {total_bound} or less, not {total:g}"
                )
        for state in taken:
            game.put_onto_battlefield(state, controller.username)
        _bottom_in_random_order(game, controller, [s for s in looked if s not in taken])

    return effect


#: "Reveal any number of `<quality>` cards from your hand. When you do, this
#: Siege deals X plus `<n>` damage to any other target, where X is the
#: number of cards revealed this way. (X can be 0.)" - Invasion of Tarkir's
#: own ETB (Defiant Thundermaw). CR 603.12's reflexive trigger, the
#: `_SELF_COUNTER_THEN_RIDER_RE` shape just above with a reveal-and-count
#: instead of a counter as the antecedent action - the reminder text's own
#: "(X can be 0.)" is what says the reveal always "happens" (CR 701.20a) and
#: the reflexive always triggers, never gated on `game.may`/a real choice
#: to decline (revealing zero of a stated quality is still revealing that
#: many, CR 701.20e).
_REVEAL_ANY_NUMBER_THEN_X_PLUS_DAMAGE_RE = re.compile(
    r"^reveal any number of (?P<quality>.+?) cards from your hand\. when you do, "
    r"this siege deals x plus (?P<bonus>\d+) damage to any other target, "
    r"where x is the number of cards revealed this way\.?$",
    re.IGNORECASE,
)


def _parse_reveal_any_number_then_x_plus_damage_clause(text: str) -> AbilityEffect | None:
    """`_REVEAL_ANY_NUMBER_THEN_X_PLUS_DAMAGE_RE`'s shape, or `None`.

    Ability-only: "this Siege" (CR 310.12a's own subtype-named self-
    reference, CR 201.5c) is a permanent's own printed ability, never a
    spell's - `_source_relative_whole_text_ability_effect` is the only
    caller.
    """
    match = _REVEAL_ANY_NUMBER_THEN_X_PLUS_DAMAGE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    quality = match.group("quality").strip()
    if not _search_quality_is_readable(quality):
        return None
    matches_quality = _quality_matcher(quality)
    bonus = int(match.group("bonus"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_name = ability.source_name
        source_id = source_id_of(ability)
        candidates = [state for state in controller.hand if matches_quality(state)]
        chosen: list[CardState] = []
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"reveal any number of {quality} cards from your hand",
                    source=source_name,
                    source_id=source_id,
                    amount=len(candidates),
                    cards=tuple(state.id for state in candidates),
                    exact=False,
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in candidates}
            chosen = [by_id[card_id] for card_id in chosen_ids]
            for state in chosen:
                game.reveal(state, source=source_name)
        count = len(chosen)
        game.create_reflexive_trigger(
            text=f"When you do, this permanent deals {count + bonus} damage to any other target.",
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveWhenYouDoConsequence(),
        )

    return effect


def _put_card_from_hand_on_bottom_of_library(
    game: "Game", player: Player, source: str, source_id: str | None
) -> None:
    """`_PUT_CARD_FROM_HAND_ON_BOTTOM_OF_LIBRARY_RE`'s effect: the player's
    own CR 608.2d choice of which card, put on the bottom (CR 401.2) rather
    than shuffled in. An empty hand has nothing to choose and does nothing,
    the same floor every other hand-choice clause in this file applies.
    """
    hand = list(player.hand)
    if not hand:
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt="choose a card from your hand to put on the bottom of your library",
            source=source,
            source_id=source_id,
            amount=1,
            cards=tuple(state.id for state in hand),
        )
    )
    assert isinstance(chosen_ids, tuple)
    if not chosen_ids:
        return
    by_id = {state.id: state for state in hand}
    game.put_cards_into_library([by_id[chosen_ids[0]]], to_bottom=True)


#: "Whenever `<A & B>` attack, reveal cards from the top of your library
#: until you reveal a creature card. Put that card onto the battlefield
#: tapped and attacking and the rest on the bottom of your library in a
#: random order." - Raph & Mikey, Troublemakers' own attack trigger. Read
#: whole for the identical reason Ilharg, the Raze-Boar's own attack trigger
#: is (`_PUT_CREATURE_FROM_HAND_ATTACKING_RE`'s docstring): `split_effect_
#: clauses`'s bare-"and" cut slices "tapped and attacking" and "attacking and
#: the rest" into fragments no per-clause parser reads back together.
_REVEAL_UNTIL_CREATURE_THEN_ATTACKING_REST_RANDOM_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal a creature card\.\s*"
    r"put that card onto the battlefield tapped and attacking and the rest on the "
    r"bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_reveal_until_creature_then_attacking_rest_random_clause(
    text: str,
) -> AbilityEffect | None:
    """`_REVEAL_UNTIL_CREATURE_THEN_ATTACKING_REST_RANDOM_RE`'s shape.

    CR 701.20a's reveal moves nothing, so every card seen along the way is
    still on top of the library until it is dealt with below - the same
    `_parse_reveal_until_land_damage_clause`/`_merge_reveal_until_kind_then_
    put_clauses` convention. The stopping card goes onto the battlefield
    tapped and then into the ability's controller's own combat via CR 508.4
    (`_defender_of_controllers_attack`/`_put_onto_the_battlefield_attacking`,
    the same primitives Ilharg's own attack trigger already uses) - Raph &
    Mikey are themselves attacking when this resolves, so there is always a
    defender to name unless every attacker of theirs has since left combat.
    Everything else the reveal turned up goes to the bottom in a random order
    (CR 701.24a's shuffle is never the verb printed here, so nothing watching
    for one fires), using the same reproducible seed convention `_merge_
    reveal_until_kind_then_put_clauses` already shares with every other
    "in a random order" clause in this file.

    An empty library, or one with no creature card in it, reveals everything
    there is and stops - "until" has no more cards to look at - and the
    "put that card" half of the sentence is CR 101.3's impossible instruction
    to nothing at all.
    """
    if (
        _REVEAL_UNTIL_CREATURE_THEN_ATTACKING_REST_RANDOM_RE.fullmatch(" ".join(text.split()))
        is None
    ):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ...models.token import _put_onto_the_battlefield_attacking

        controller = game.controller_of(ability)
        source_name = ability.source_name
        revealed: list[CardState] = []
        stopper: CardState | None = None
        for state in list(controller.library):
            game.reveal(state, source=source_name)
            revealed.append(state)
            if Type.CREATURE in state.types:
                stopper = state
                break
        if stopper is not None:
            permanent = game.put_onto_battlefield(stopper, controller.username, tapped=True)
            if permanent is not None and permanent.zone is Zone.BATTLEFIELD:
                defender = _defender_of_controllers_attack(game, controller.username)
                if defender is not None:
                    _put_onto_the_battlefield_attacking(game, permanent, defender)  # type: ignore[arg-type]
        remainder = [
            state for state in revealed if state is not stopper and state.zone is Zone.LIBRARY
        ]
        if remainder:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-until-creature-attacking"
            )
            rng.shuffle(remainder)
            game.shuffles_performed += 1
            for state in remainder:
                controller.move(state, Zone.LIBRARY)

    return effect


from ._common import (  # noqa: E402
    _SELECT_FROM_TOP_KINDS,
    ConditionalClauseNotice,
    _effect_condition_is_readable,
    _opponents,
    _parse_card_group_qualifier,
    _parse_mass_type_qualifier,
    _players_in_apnap_order,
    _PutDescription,
    _quality_matcher,
    _targets_understood,
)
from .amounts import (  # noqa: E402
    _bounded_revealed_card_matcher,
    _cast_trigger_x_value,
    _that_many_or_notice,
    amount_expression,
    that_many,
)
from .continuous import _defender_of_controllers_attack  # noqa: E402
from .counters import _counter_kind  # noqa: E402
from .dispatch import (  # noqa: E402
    _parse_mixed_clause,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .draw_discard import _discard_cards  # noqa: E402
from .mana import _add_mana_in_any_combination, colored_mana_symbols  # noqa: E402
from .modal import _choose_an_opponent, _choose_one_card  # noqa: E402
from .removal import _parse_mass_destroy_predicate  # noqa: E402
from .returns import _reposition_in_owners_library  # noqa: E402
from .search import _outside_the_game_card_phrase, _search_quality_is_readable  # noqa: E402
from .text import _singular_card_type, _strip_non_effect_preamble  # noqa: E402
