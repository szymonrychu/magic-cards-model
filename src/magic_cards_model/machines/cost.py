"""Paying a cost, as a state machine.

Follows the shape of CR 601.2f-h: work out the total cost, activate mana
abilities to fill the pool, then pay. Tapping a permanent for mana is both the
cost of the mana ability and the thing that fills the pool, so it lives here.

    PENDING -> TAPPING -> POOLED -> PAID
                 \\_______________/
       (mana already floating skips the tapping)

A cost is not only mana. CR 601.2f calls the whole thing the *total cost*, and
it is a composite: a mana part plus any number of non-mana components -
sacrificing a permanent, discarding a card, paying life, exiling a card,
tapping a permanent. `TotalCost` is that composite and `CostComponent` is one
non-mana piece of it.

The payment's mana pool opens as a copy of the payer's floating mana: CR 202.1a
has the cost spent "from their mana pool", and CR 106.4 lets mana already
floating there pay "immediately", so it is usable without activating anything.
The mana abilities the payment activates along the way (CR 601.2g) add into
that copy. When the payment succeeds, whatever it did not spend is written back
into the player's pool (CR 106.4a); when it is cancelled, the copy is thrown
away, so the player's pre-existing floating mana is untouched while the payment's
own activations die with the copy and their sources are untapped.

Any state before PAID can be cancelled, which untaps everything tapped for
mana, discards the mana the payment's own activations produced, and undoes
every component already paid. That is CR 733.1: an action that cannot be
completed legally is reversed in full and any payments already made are
cancelled.
"""

import re
from collections import Counter as _MultiSet
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from itertools import combinations, combinations_with_replacement, product
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import ConfigDict, Field, PrivateAttr

from magic_cards_model.phrases import with_indefinite_article

from ..data.subtypes import canonical_subtype
from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import CardState, ChoiceKind, Counter, CounterKind
from ..models.mana import (
    NO_SPEND_EFFECT,
    NOT_RETAINED,
    UNRESTRICTED,
    ManaCost,
    ManaPayment,
    ManaPool,
    ManaRestriction,
    ManaSpend,
    ManaSpendEffect,
    ManaSymbol,
    PaymentOption,
    SpendClause,
    SpendPurpose,
    SymbolKind,
    _assign_sources,
    _Bucket,
    _candidate_options,
    _demand_list,
)
from ..models.zone import Zone
from ..numbers import (
    QuantitySource,
    VariableX,
    count_pattern,
    parse_amount,
    parse_count,
    parse_quantity,
)
from ..snapshot import EngineModel, announce_mutation, mutation_landed
from .abilities import (
    ActivatedAbility,
    CostKind,
    ManaAbility,
    TriggerEvent,
    granted_mana_abilities,
    intrinsic_land_ability,
    parse_abilities,
    parse_mana_abilities,
    parse_triggered_mana,
)
from .combat import Keyword, has_keyword
from .triggers import (
    GameEvent,
    abilities_triggered_by,
    activated_abilities_from_lines,
    activated_abilities_of,
    added_ability_lines,
    granted_activated_abilities_of,
    is_ability,
    mana_added_event,
    rewritten_ability_lines,
    tapped_for_mana_event,
    triggered_abilities_on,
    triggered_mana_count,
    triggered_mana_recipient,
)


@dataclass(frozen=True)
class _SpendContext:
    """The read-only slice of a `CostPayment` that surveying the board for
    mana actually needs: which game to read the battlefield from, who is
    paying, and what the mana is for (CR 106.6's restriction is judged against
    `spend`).

    `_mana_context`, `_mana_narrowings`, `_auto_tap_candidates`,
    `_activation_refused`, and `_among_colors` all take one of these - a
    `CostPayment` satisfies it structurally (it carries the same three
    attributes), so a real payment still being built can be passed straight
    through while `auto_tap` executes. `could_pay_mana_cost` passes one of
    *these* instead: a pure affordability query has nothing to pay with and
    must build no `CostPayment` at all, because `CostPayment.for_total` seeds
    its pool through `_seed_payer_pool`, which calls `_register_pool` and
    publishes that pool into `game.open_payment_pools[payer]` - a write a
    read-only predicate must never make, whether or not anything ever reads it
    back out.
    """

    game: Any = None
    payer: str | None = None
    spend: "ManaSpend | None" = None


def can_tap_for_mana(source: CardState, game: Any = None) -> bool:
    """Whether this permanent's `{T}` ability may be activated (CR 302.6, 602.5a).

    Only creatures are held back, and haste turns the restriction off
    (CR 702.10c). `Game.can_activate_tap_ability` is the authority when there
    is a game; without one the same question is answered off the permanent
    itself, since summoning sickness is a flag on `CardState` and haste is
    printed on the card.
    """
    if game is not None:
        return bool(game.can_activate_tap_ability(source))
    if not source.is_creature:
        return True
    return not source.summoning_sick or has_keyword(source, Keyword.HASTE)


def why_payer_cannot_use(source: CardState, payer: str | None, game: Any = None) -> str | None:
    """Why `payer` may not spend `source` on a cost of theirs, or None.

    CR 602.2: "Only an object's controller ... can activate its activated
    ability", and CR 605.3 sends a mana ability through the same rule. So a
    mana source pays only for its controller. CR 723.5a is the one twist: a
    player controlling another player makes that player's choices, but the
    payment is still the controlled player's and "can use only that player's
    resources", so the controller's own permanents are refused too - and the
    refusal names that rule, since it is the one the seat is running into.

    `payer` None (a payment with nobody named) and a source with no
    controller at all are not judged: there is nobody to compare.
    """
    if payer is None:
        return None
    controller = source.controller
    if game is not None and source.zone is Zone.BATTLEFIELD and controller is not None:
        controller = game.controller_of(source).username
    if controller is None or controller == payer:
        return None
    if (
        game is not None
        and getattr(game, "turn", None) is not None
        and game.is_controlling_player(controller, payer)
    ):
        return (
            f"{source.name} is {controller}'s, and {controller} is deciding for "
            f"{payer}: the controller of another player can use only that "
            f"player's resources to pay their costs (CR 723.5a)"
        )
    return (
        f"{payer} does not control {source.name} ({controller} does), so {payer} "
        "cannot activate its mana ability: only an object's controller can "
        "activate its activated abilities (CR 602.2, CR 605.3)"
    )


def is_snow_source(source: CardState, game: Any = None) -> bool:
    """Whether mana from this permanent is snow mana (CR 106.3, 205.4g).

    With a `game` and the source on the battlefield, read off the computed
    board (CR 613.5) rather than the printed type line, the same optional-
    `game` shape `is_indestructible` and `has_keyword` already use for their
    own layer 6/4 questions - CR 613.1d's layer 4 is where a supertype-
    changing effect would land. Without one, or off the battlefield, the
    printed supertype is the only answer there is.

    Latent rather than live today: nothing in `machines/effects.py`'s
    registry grants or removes the snow supertype, so every board in the
    current pool computes the same answer either way - this only stops being
    a silent trap the day a card that does is added. Threaded through only
    the live auto-tap path (`_bucket_map`, `_best_flow_plan`, `tap_for_mana`);
    `_solve_colours`, reachable only from `_solve_auto_tap_brute_force`'s
    property-test oracle, is left reading the printed type - it builds no
    `CostPayment` and has no board to compute against without one.
    """
    if game is not None and source.zone is Zone.BATTLEFIELD:
        try:
            return Supertype.SNOW in game.characteristics_of(source).supertypes
        except (AttributeError, KeyError):
            pass
    return Supertype.SNOW in source.supertypes


# --------------------------------------------------------------------------
# CR 602.5: an activation's own restriction, asked on the payment path
# --------------------------------------------------------------------------
#
# CR 602.5, looked up this session: "A player can't begin to activate an
# ability that's prohibited from being activated." Tapping a permanent for
# mana *is* activating its mana ability (CR 605.3a), so every restriction
# `Game.why_cannot_activate` enforces on a deliberate activation binds this
# path too - and CR 602.5b keeps the restriction attached to the object even
# when its controller changes.
#
# This was a split brain: `why_cannot_activate` refused Mox Opal's metalcraft
# ability ("Activate only if you control three or more artifacts") correctly,
# while `auto_tap` and `tap_for_mana` never asked, so the payment path the API
# and the UI take tapped it with one artifact on the battlefield. The board
# state that came out was wrong, not missing, which is why no test caught it.


def _activations_of(source: CardState, game: Any = None) -> list[ActivatedAbility]:
    """`Game.activated_abilities(source)`'s own list, rebuilt from the same
    functions in the same order - printed abilities of the up face first
    (CR 712.8d/712.8e/712.8f), then `CardState.granted_ability_texts`'s.

    Rebuilt rather than asked of the game because a `CostPayment` may have no
    game behind it, and because an index into this list is what
    `Game.why_cannot_activate` takes: same order, same index.

    **CR 613.5 / CR 707.2**, and the whole reason `game` is a parameter: when a
    continuous effect has rewritten this permanent's computed ability text away
    from the printed card - a layer 1 copy effect is the only shape in the pool
    that does - the *computed* abilities are the ones it has, and the printed
    card is not consulted at all (CR 613.5: "all resulting changes to an
    object's characteristics are instantaneous"; CR 707.2: "the copy acquires
    the copiable values of the original object's characteristics"). A Forest
    that has become a copy of Sol Ring is tapped for `{C}{C}` and cannot be
    tapped for `{G}`.

    `Game.activated_abilities` already reads it this way, so before this
    parameter existed the two paths disagreed: activating the copy's ability
    directly was right, and spending the same permanent on a cost silently
    offered its printed one. Without a game there is no layer engine to ask and
    the printed reading is all there is, which is the answer this had before.
    """
    granted = granted_activated_abilities_of(source.granted_ability_texts)
    if game is not None:
        rewritten = rewritten_ability_lines(game, source)
        if rewritten is not None:
            # The grants are appended here too, for the reason
            # `Game.activated_abilities` spells out: a rewrite replaces the
            # printed text, while an ability granted by something that already
            # resolved is its own continuous effect (CR 611.2) applied in
            # layer 6 (CR 613.1f), after both the layer 1 copy effects and the
            # layer 4 type changes that can cause a rewrite. Keeping the two
            # paths identical is the whole point of this helper - a Blood
            # Mooned Urza's Saga must be spendable on a cost for the same
            # {C} its own chapter I granted, not only for the Mountain's {R}.
            base = activated_abilities_from_lines(rewritten, source.card, source.up_face_name)
            already = {ability.raw for ability in base}
            return base + [ability for ability in granted if ability.raw not in already]
    base = activated_abilities_of(source.card, source.up_face_name) + granted
    if game is None:
        return base
    # The additive half, kept identical to `Game.activated_abilities`: a basic
    # land type granted in layer 4 brings its intrinsic mana ability with it
    # (CR 305.6), and a land that gained one has to be spendable on a cost for
    # it, not merely show it on the computed board.
    added = activated_abilities_from_lines(
        added_ability_lines(game, source), source.card, source.up_face_name
    )
    seen = {ability.raw for ability in base}
    return base + [ability for ability in added if ability.raw not in seen]


def tappable_mana_activations(
    source: CardState, game: Any = None
) -> list[tuple[int, ActivatedAbility]]:
    """Every mana ability of `source` whose whole cost is a bare `{T}`, each
    with the index `Game.activated_abilities`/`Game.why_cannot_activate` know
    it by.

    The index matters as much as the ability: an activation restriction is
    read off *one* ability's printed instructions, and the only way to ask
    `why_cannot_activate` about it is by its position in `_activations_of`'s
    list.

    The `{T}`-only filter is `free_tap_mana_abilities`'s own, for the same
    CR 118.3c reason: a cost beyond the tap is a cost only the player may
    choose to pay.

    `game` is `_activations_of`'s own CR 613.5 parameter: passed, a permanent
    that has become a copy of something offers the *copy's* `{T}` ability here.
    """
    return [
        (index, ability)
        for index, ability in enumerate(_activations_of(source, game))
        if ability.mana is not None and [piece.kind for piece in ability.costs] == [CostKind.TAP]
    ]


def life_paid_mana_activations(
    source: CardState, game: Any = None
) -> list[tuple[int, ActivatedAbility, int]]:
    """Every mana ability of `source` whose cost is `{T}` plus paying a fixed
    amount of life ("{T}, Pay 1 life: Add {U} or {R}."), each with the index
    `Game.activated_abilities` knows it by and the life it costs.

    These are what `tappable_mana_activations` leaves out on CR 118.3c's
    ground: the player may activate one (CR 605.3a), the engine may not do it
    for them. Nothing that pays for anything on a player's behalf reads this.
    It exists for a what-if answer about what the player could pay
    (`mana_candidate_scan(..., include_life_paid=True)`). Any other extra
    cost (a sacrifice, a mana payment, a discard) is not here.
    """
    found: list[tuple[int, ActivatedAbility, int]] = []
    for index, ability in enumerate(_activations_of(source, game)):
        if ability.mana is None:
            continue
        kinds = [piece.kind for piece in ability.costs]
        if kinds.count(CostKind.TAP) != 1 or len(kinds) < 2:
            continue
        amounts = [
            _PHRASE_PAY_LIFE.match(piece.text.strip().rstrip("."))
            for piece in ability.costs
            if piece.kind is not CostKind.TAP
        ]
        if any(amount is None for amount in amounts):
            continue
        life = sum(int(amount.group("amount")) for amount in amounts if amount is not None)
        found.append((index, ability, life))
    return found


def _activation_refused(
    payment: "CostPayment | _SpendContext", source: CardState, index: int
) -> str | None:
    """Why CR 602.5 forbids activating `source`'s ability number `index` right
    now, or None - `Game.why_cannot_activate`'s answer, asked from the payment.

    Without a game there is no board to judge a restriction against, and
    without a controller there is nobody whose board it would be, so both fall
    through to None: this is the *same* answer those cases have always had
    here, not a new permission.
    """
    game = payment.game
    if game is None:
        return None
    controller = source.controller or payment.payer
    if controller is None:
        return None
    return game.why_cannot_activate(source, index, controller)


# --------------------------------------------------------------------------
# CR 106.5: "of any color among [permanents] you control"
# --------------------------------------------------------------------------
#
# CR 106.5, looked up this session: "If an ability would produce one or more
# mana of an undefined type, it produces no mana instead." Its own example is
# Meteor Crater, and Mox Amber prints the same shape - "{T}: Add one mana of
# any color among legendary creatures and planeswalkers you control." With no
# such permanent there is no colour to be chosen among, the type is undefined,
# and the ability adds nothing at all. `machines/abilities.py` reads the line
# as a plain any-colour ability and drops the qualifier, so the whole WUBRG
# option set survived to here and an empty board made a Black Lotus of it.
#
# The narrowing is applied where the mana is actually produced - the two
# entries into the pool, `auto_tap` and `tap_for_mana` - rather than at parse
# time, because the answer is a board state and changes between one tap and
# the next. CR 605.2 is why this narrows rather than deletes: "A mana ability
# remains a mana ability even if the game state doesn't allow it to produce
# mana", so the ability is still there and still `{T}`-activatable; it just
# has no legal type to add.

#: `color among legendary creatures and planeswalkers you control` (Mox
#: Amber). The quality is left as words for `_among_colors` to read, since
#: the same sentence is printed with other qualities on cards outside this
#: pool. Anchored on the word directly before "among" being "color" - not a
#: bare search anywhere in the effect - because "among ... you control" is
#: not always this survey: Loot, the Nexus's "one mana of that color for
#: each different power among creatures you control" also contains the
#: phrase, modifying the *count* rather than which colors are legal, and a
#: bare search wrongly refused its own unrelated color as undefined by
#: CR 106.5's restriction, which is not what that sentence is about at all.
_ANY_COLOR_AMONG = re.compile(r"\bcolor among (?P<quality>[a-z ,]+?) you control\b", re.IGNORECASE)


def _among_colors(
    effect: str, payment: "CostPayment | _SpendContext", source: CardState
) -> frozenset[Color] | None:
    """The colours an "of any color among [quality] you control" clause leaves
    defined right now, or None when the effect prints no such clause at all.

    None and the empty set are different answers and the caller must not
    conflate them: None is "this ability's type was never restricted by a
    board state", the empty set is CR 106.5's undefined type, which produces
    no mana.

    A supertype anywhere in the quality applies to the whole list, so "legendary
    creatures and planeswalkers" is read as legendary creatures plus legendary
    planeswalkers (CR 205.4a lists the five supertypes; CR 306.3 makes every
    planeswalker legendary in any case, so the pool cannot tell the two
    readings apart). Colours come from `CardState.colors`, which already knows
    which face is up (CR 712.8d) and that a face-down permanent is colorless
    (CR 708.2).

    A quality naming no card type at all is unreadable, and returns None -
    the ability is left alone rather than silenced, the same fail-open choice
    `Game._activation_condition_holds` makes for an "Activate only if" it
    cannot parse: refusing every activation on a sentence this cannot read
    would be a louder wrong answer than the narrow gap it replaces.
    """
    return among_colors(effect, payment.game, source.controller or payment.payer)


def among_colors(effect: str, game: Any, controller: str | None) -> frozenset[Color] | None:
    """`_among_colors` without a `CostPayment` to reach the game through.

    The survey needs exactly two things - a game to read the battlefield from
    and the controller whose permanents "you control" means - and the payment
    path happens to be one way to hold both. `Game.activate_ability`'s CR 605.3b
    mana fast path holds them directly and never builds a `CostPayment` at all,
    so the reading lives here and `_among_colors` is the payment-path adapter.
    Without this, the same Mox Amber produced nothing when tapped through a
    payment and one mana of any colour when activated directly.
    """
    match = _ANY_COLOR_AMONG.search(effect)
    if match is None:
        return None
    if game is None or controller is None:
        return None

    supertypes: list[Supertype] = []
    types: list[Type] = []
    for raw_word in match.group("quality").replace(",", " ").split():
        word = raw_word.lower().removesuffix("s")
        if word in _QUALITY_CONNECTORS:
            continue
        try:
            supertypes.append(Supertype(word))
            continue
        except ValueError:
            pass
        try:
            types.append(Type(word))
        except ValueError:
            return None
    if not types:
        return None

    # CR 613.5: the survey is of what each permanent *is* right now, not of
    # its printed type line - Mox Amber's "legendary creatures and
    # planeswalkers you control" has to see a Vehicle crewed into an artifact
    # creature (CR 613.1d, layer 4) the moment it is one, the same way it
    # would see an ordinary creature. `permanents_controlled_by` only ever
    # returns battlefield permanents, so every entry is on `board`; one
    # `computed_board()` is hoisted for the whole survey rather than recomputed
    # once per permanent.
    board = game.computed_board()
    colors: set[Color] = set()
    for state in game.permanents_controlled_by(controller):
        chars = board.of(state)
        if not any(type_ in chars.types for type_ in types):
            continue
        if not all(supertype in chars.supertypes for supertype in supertypes):
            continue
        colors.update(color for color in chars.colors if color is not Color.COLORLESS)
    return frozenset(colors)


def _activation_behind(
    activations: Sequence[ActivatedAbility], ability: ManaAbility
) -> tuple[int, ActivatedAbility] | None:
    """The activated ability in `activations` that `ability` was read off,
    with the index `Game.why_cannot_activate` knows it by, or None when it
    came from somewhere with no printed ability behind it.

    `ManaAbility` is what the payment path carries around, and it holds only
    what the ability *adds* - not the instructions that restrict it, nor the
    effect sentence that qualifies it. Matching it back to its
    `ActivatedAbility` is what lets `tap_for_mana` ask CR 602.5 and CR 106.5
    the same questions `_auto_tap_candidates` asks, on the path where the
    player named the source themselves.
    """
    for index, activation in enumerate(activations):
        if activation.mana == ability:
            return index, activation
    return None


def _narrow_to_defined_colors(
    options: list[list[Color]], any_color: bool, allowed: frozenset[Color] | None
) -> tuple[list[list[Color]], bool]:
    """`options`/`any_color` with every choice CR 106.5 leaves undefined
    dropped, so what remains is what this ability can actually add.

    `allowed` is `_among_colors`'s answer: None leaves the ability untouched.
    An option is kept only if every colour in it is defined - an ability that
    adds two mana of a chosen colour cannot half-add one.
    """
    if allowed is None:
        return options, any_color
    kept = [option for option in options if all(color in allowed for color in option)]
    return kept, any_color and len(kept) == len(options)


# --------------------------------------------------------------------------
# Auto-tapping: solving *which* sources to tap and *which* colour a choice
# source makes, so a player is not forced to hand-pick every dual and
# shockland on every cast (CR 601.2g, CR 118.3c).
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Reading a CR 106.6 spend restriction off a mana ability's effect text
# --------------------------------------------------------------------------
#
# CR 106.6, looked up this session: "Some spells or abilities that produce mana
# restrict how that mana can be spent, have an additional effect that affects
# the spell or ability that mana is spent on, or create a delayed triggered
# ability..." The restriction half is what this reads; the "additional effect"
# half (Cavern of Souls's and Delighted Halfling's "and that spell can't be
# countered", Arena of Glory's haste grant) is a separate clause of the same
# sentence and remains unmodelled - see `docs/engine-coverage.md`.
#
# Eight printings in the card pool carry one, and between them they are the
# whole of the grammar below:
#
#   Shang-Chi, Master of Kung Fu
#     "Spend this mana only to activate abilities of creature sources."
#   Sunken Citadel
#     "Spend this mana only to activate abilities of land sources."
#   Eldrazi Temple
#     "Spend this mana only to cast colorless Eldrazi spells or activate
#      abilities of colorless Eldrazi."
#   Cavern of Souls
#     "Spend this mana only to cast a creature spell of the chosen type, and
#      that spell can't be countered."
#   Delighted Halfling
#     "Spend this mana only to cast a legendary spell, and that spell can't be
#      countered."
#   Tablet of Discovery
#     "Spend this mana only to cast instant and sorcery spells."
#   Fíli and Kíli, Joyous
#     "Spend this mana only to cast Dwarf, Equipment, and Saga spells."
#   Interdimensional Web Watch
#     "Spend this mana only to cast spells from exile."
#
# The last three are the two shapes this grammar grew for, and both are read
# generally rather than per card:
#
#   * A **type list**, joined with "and", "or" or "and/or" and optionally
#     comma-separated, is one clause offering several qualifying types - not
#     several clauses. CR 205.2b, looked up this session: "Some objects have
#     more than one card type... Such objects satisfy the criteria for any
#     effect that applies to any of their card types." No spell is both an
#     instant and a sorcery, so "instant and sorcery spells" can only mean
#     either, and reading it as two alternatives would say the same thing
#     twice while claiming the sentence had two halves it does not have.
#   * A **zone tail**, "from <zone>", narrows the clause to one of CR 400.1's
#     zones: "There are normally seven zones: library, hand, battlefield,
#     graveyard, stack, exile, and command." CR 601.2a moves the card to the
#     stack as the first step of the announcement, so the zone a clause is
#     checked against is the one the cast *started* in and has to be carried
#     from before that move - `ManaSpend.casting`'s `zone` argument.
#
# A zone phrase that names an owner ("from your graveyard") is deliberately
# **not** read: `ManaSpend` carries the origin zone and not whose it was, so
# reading it would produce a restriction quietly wider than the card. It falls
# through to the fail-closed branch below like any other unread sentence.
#
# Anything else that opens "Spend this mana only" and does not fit the grammar
# below produces a restriction with **no** clauses, which permits nothing at
# all (`ManaRestriction.allows`). That is the fail-closed direction on purpose:
# mana that looks spendable and is not is worse than mana that refuses.

_SPEND_RESTRICTION = re.compile(r"Spend this mana only to (?P<what>[^.]+)\.")
#: Anything that talks about restricting this mana, whether or not the grammar
#: below could read it - the signal a caller uses to fail closed rather than
#: silently treat the sentence as absent.
_SPEND_RESTRICTION_SIGNAL = re.compile(r"[Ss]pend this mana only")
#: "cast a creature spell of the chosen type", "cast colorless Eldrazi spells",
#: "cast instant and sorcery spells", "cast spells from exile". `quality` is
#: lazy so the shortest reading wins - "cast spells from exile" leaves it empty
#: and puts "exile" in `zone` rather than swallowing the tail.
#: "pay cumulative upkeep costs" (Snowfall) - CR 702.24a's cost as the thing
#: the mana may pay.
_SPEND_CUMULATIVE_UPKEEP_CLAUSE = re.compile(r"^pay cumulative upkeep costs?$", re.IGNORECASE)
_SPEND_CAST_CLAUSE = re.compile(
    r"^cast (?P<quality>.*?) ?spells?"
    r"(?P<chosen> of the chosen type)?"
    r"(?: from (?P<zone>.+))?$",
    re.IGNORECASE,
)
#: "activate abilities of creature sources", "activate abilities of colorless
#: Eldrazi". The trailing "sources" is WOTC's own word for "the object the
#: ability is on" and narrows nothing further.
#: The "of <quality>" qualifier is optional - Boommobile's own "Spend this
#: mana only to activate abilities." (no qualifier at all, so CR 106.6's
#: restriction is "an activated ability", full stop) is the same bare shape
#: `_SPEND_CAST_CLAUSE`'s own `(?P<quality>.*?)` already reads for "cast
#: spells" with nothing narrowing it. `_spend_clause` already turns an empty
#: quality into a `SpendClause` with every qualifier set empty - unrestricted
#: within its purpose - so no other change is needed to read it correctly.
_SPEND_ACTIVATE_CLAUSE = re.compile(
    r"^activate abilities(?: of (?P<quality>.+?)(?: sources)?)?$", re.IGNORECASE
)
#: A rider joined onto the restriction sentence with ", and" - the
#: can't-be-countered half of Cavern of Souls and Delighted Halfling.
#:
#: It is **not** an unambiguous marker, and cutting on it unconditionally is a
#: bug: Fíli and Kíli, Joyous prints "cast Dwarf, Equipment, and Saga spells",
#: where the same three characters are the Oxford comma of a type list and
#: cutting there loses the last type. So the whole phrase is read first and
#: this cut is only tried when that fails - which is exactly when a rider is
#: present, because a rider ends the sentence on a verb ("can't be countered")
#: and no clause pattern below can end there.
_SPEND_RIDER = ", and "

_SUPERTYPE_WORDS = {supertype.value: supertype for supertype in Supertype}
#: The words that join a printed list of qualifying types into one clause.
#: MTG templates the same list three ways - "instant and sorcery spells"
#: (Tablet of Discovery), "a Knight or Equipment spell" (Tournament Grounds),
#: "Aura and/or Equipment spells" (Codsworth, Handy Helper, in the pool; also
#: Cormela, Glamour Thief's "instant and/or sorcery spells") - and all three
#: mean the same thing, so all three are joiners rather than one being
#: privileged. Commas are already stripped off each word.
_TYPE_LIST_JOINERS = {"and", "or", "and/or"}
#: The same three words in their other role: joining two whole **clauses**
#: rather than two qualities inside one. "cast Elf spells and activate
#: abilities of Elf sources" (Woodland Weavemaster), "cast colorless Eldrazi
#: spells or activate abilities of colorless Eldrazi" (Eldrazi Temple) - the
#: printed word does not say which of the two roles it is in, so this split is
#: only ever tried on a phrase the grammar has already failed to read as a
#: single clause. See `_spend_clauses`.
_SPEND_CLAUSE_SPLIT = re.compile(r" and/or | and | or ")
#: CR 400.1's zones, by the word a card prints for each. The sideboard is not
#: one ("Cards in a player's sideboard are outside the game", CR 400.11a) and
#: is left out so a "from the sideboard" sentence fails closed.
_SPEND_ZONE_WORDS = {zone.value: zone for zone in Zone if zone is not Zone.SIDEBOARD}


def _spend_zone(phrase: str) -> Zone | None:
    """The CR 400.1 zone a "from ..." tail names, or None if it names none.

    An article is dropped; anything else - a possessive ("your graveyard"), a
    quality ("anywhere other than your hand"), a second word of any kind -
    returns None and so fails the clause. `ManaSpend` carries which zone a
    spell was cast from and not whose it was, so a phrase that narrows by
    owner is one this engine cannot check and must not silently widen.
    """
    words = phrase.strip().rstrip(".").lower().split()
    if words and words[0] in {"a", "an", "the"}:
        words = words[1:]
    if words == ["command", "zone"]:
        words = ["command"]
    if len(words) != 1:
        return None
    return _SPEND_ZONE_WORDS.get(words[0])


def _spend_clause(
    phrase: str,
    purpose: SpendPurpose,
    chosen_type: str | None,
    zone: Zone | None = None,
) -> SpendClause | None:
    """Turn one quality phrase into a `SpendClause`, or None if unreadable.

    The vocabulary is deliberately closed: an article, a list joiner,
    "colorless", a printed supertype, a printed card type, or a capitalised
    noun read as a subtype (CR 205.3 subtypes are always capitalised on a type
    line, which is what tells "Eldrazi" apart from "colorless"). A word outside
    it fails the whole clause rather than being dropped, because a dropped word
    is a restriction that is quietly broader than the card.

    A card type or a subtype is read through the **plural** it is printed with
    here, because rules text names the objects and a type line names the card:
    "activate abilities of Elementals" is about the same subtype "Creature -
    Elemental Shaman" prints, and "abilities of artifacts" the same card type
    (CR 205.3b, looked up this session). Card types are a closed enum and lose
    a trailing "s"; subtypes go through `canonical_subtype`, which resolves the
    printed word against every subtype WOTC has printed rather than guessing at
    English morphology, and resolves nothing at all for a word it cannot place
    - which fails the clause, like any other unread word.

    Whether several qualities out of one phrase are **alternatives** or all
    required is decided by the joining word, not by which field they land in -
    see `SpendClause.joined`. A joined list is alternatives ("instant and
    sorcery spells", "instant, sorcery, Demon, and Spirit spells"), because no
    object is every item of such a list at once; juxtaposition is a single
    description that must hold whole ("Dragon creature spells", "colorless
    Eldrazi spells"). A phrase that does both at once is refused: no printing
    templates one, and choosing a reading for it would be a guess in a place
    where being wrong permits the wrong spells.
    """
    types: set[Type] = set()
    excluded_types: set[Type] = set()
    subtypes: set[str] = set()
    supertypes: set[Supertype] = set()
    colorless = False
    #: Whether a joiner or a comma stood between each pair of adjacent
    #: qualities. One consistent answer is the clause's reading; both answers
    #: in one phrase is the mixed shape above, and fails closed.
    separations: set[bool] = set()
    qualities = 0
    separator_pending = False

    for word in phrase.split():
        stripped = word.strip(",")
        lowered = stripped.lower()
        if lowered in {"a", "an", "the"}:
            continue
        if lowered in _TYPE_LIST_JOINERS:
            separator_pending = True
            continue

        if lowered == "colorless":
            colorless = True
        elif lowered.startswith("non") and lowered.removeprefix("non").removesuffix("s") in (
            _TYPE_WORDS
        ):
            # CR 109.2's negation of a printed card type - Chandra, Chill of
            # Compliance's own "a noncreature spell", the same "non<type>"
            # idiom `machines/effects.py`'s own `_nonland_or_typed_card_
            # matcher` already reads for a search/reveal quality.
            excluded_types.add(_TYPE_WORDS[lowered.removeprefix("non").removesuffix("s")])
        elif lowered in _SUPERTYPE_WORDS:
            supertypes.add(_SUPERTYPE_WORDS[lowered])
        elif lowered.removesuffix("s") in _TYPE_WORDS:
            types.add(_TYPE_WORDS[lowered.removesuffix("s")])
        elif stripped[:1].isupper():
            subtype = canonical_subtype(stripped)
            if subtype is None:
                return None
            subtypes.add(subtype)
        else:
            return None

        if qualities:
            separations.add(separator_pending)
        qualities += 1
        separator_pending = word.endswith(",")

    if len(separations) > 1:
        return None
    joined = separations == {True}
    if joined and colorless:
        # "colorless" is a colour and not a type, so it narrows the clause
        # rather than offering another way to satisfy it - which is the one
        # thing a joined list cannot express. No printing joins it; the day one
        # does, this refuses rather than reading it either way.
        return None

    if chosen_type is not None:
        subtypes.add(chosen_type.lower())

    return SpendClause(
        purpose=purpose,
        types=frozenset(types),
        excluded_types=frozenset(excluded_types),
        subtypes=frozenset(subtypes),
        supertypes=frozenset(supertypes),
        joined=joined,
        colorless=colorless,
        zone=zone,
    )


def _chosen_creature_type(source: CardState | None) -> str | None:
    """The creature type recorded on `source` by an "as this enters, choose a
    creature type" replacement effect (CR 614.12a) - Cavern of Souls's.

    None when nothing was recorded, which makes the clause that needs it
    unreadable and so fails the restriction closed.
    """
    choice = getattr(source, "choice", None) if source is not None else None
    if choice is None or choice.kind is not ChoiceKind.CREATURE_TYPE:
        return None
    return choice.value or None


def spend_restriction(effect: str, source: CardState | None = None) -> ManaRestriction | None:
    """The CR 106.6 restriction this mana ability's effect text puts on the
    mana it produces, or None if it puts none on.

    `source` is the permanent whose ability this is, needed only for "the
    chosen type" (CR 614.12a's answer lives on the object that was asked).

    A sentence that opens "Spend this mana only" and cannot be read returns a
    restriction with no clauses - present, quoting the card, and permitting
    nothing - rather than None. The two are not the same thing and the caller
    must not conflate them: None means "this mana is free to spend", an
    unread restriction means "this engine cannot show the restriction was
    honoured, so it refuses".

    `source` itself is not memoisable - it is a mutable `CardState` - but
    everything the parse actually reads out of it is the one string
    `_chosen_creature_type` returns, so that is what is memoised on
    (`_spend_restriction_cached`), not `source`. `auto_tap`'s search calls this
    once per candidate per combination tried; caching it is one of the two
    cheap wins this module makes ahead of replacing the search itself.
    """
    return _spend_restriction_cached(effect, _chosen_creature_type(source))


@cache
def _spend_restriction_cached(effect: str, chosen_type: str | None) -> ManaRestriction | None:
    """`spend_restriction`'s memo. `effect` and the chosen creature type
    (already resolved out of `source`) are the whole of what the parse below
    depends on, so caching on that pair is exact - no `CardState` identity
    needed, and no risk of two different sources colliding on one answer that
    was never about identity in the first place.
    """
    match = _SPEND_RESTRICTION.search(effect)
    if match is None:
        if _SPEND_RESTRICTION_SIGNAL.search(effect):
            return ManaRestriction(text=effect.strip())
        return None

    text = match.group(0)
    what = match.group("what").strip()

    clauses = _spend_clauses(what, chosen_type)
    if clauses is None and _SPEND_RIDER in what:
        clauses = _spend_clauses(what.partition(_SPEND_RIDER)[0].strip(), chosen_type)
    if clauses is None:
        return ManaRestriction(text=text)
    return ManaRestriction(text=text, clauses=tuple(clauses))


def _spend_clauses(what: str, chosen_type: str | None) -> list[SpendClause] | None:
    """Every clause the "only to ..." phrase permits, or None if any of it is
    unreadable.

    The whole phrase is offered to the grammar first and only split if that
    fails. Order matters both ways: "cast a Knight or Equipment spell" is one
    clause whose type list happens to be joined with "or", and would be torn
    into two unreadable halves by splitting first; Eldrazi Temple's "cast
    colorless Eldrazi spells or activate abilities of colorless Eldrazi" is
    genuinely two clauses and fails the whole-phrase read (neither clause
    pattern matches a phrase that starts "cast" and ends "Eldrazi"), so it
    reaches the split.

    All three joining words split, because all three are printed in this role:
    "or" (Eldrazi Temple, Smokebraider), "and" (Woodland Weavemaster's "cast
    Elf spells and activate abilities of Elf sources", Smoky Lounge's "cast
    Room spells and unlock doors") and "and/or". Splitting on one of them and
    not the others left a real printing reading as nothing at all - a
    restriction with no clauses, which permits nothing - while the identical
    sentence with "or" in it worked.
    """
    whole = _one_spend_clause(what, chosen_type)
    if whole is not None:
        return [whole]

    alternatives = _SPEND_CLAUSE_SPLIT.split(what)
    if len(alternatives) == 1:
        return None
    clauses: list[SpendClause] = []
    for alternative in alternatives:
        clause = _one_spend_clause(alternative.strip(), chosen_type)
        if clause is None:
            return None
        clauses.append(clause)
    return clauses


def _one_spend_clause(phrase: str, chosen_type: str | None) -> SpendClause | None:
    """One "cast ..." or "activate abilities of ..." phrase as a clause, or
    None when this grammar cannot read it."""
    cast = _SPEND_CAST_CLAUSE.match(phrase)
    if cast is not None:
        chosen = chosen_type if cast.group("chosen") else None
        if cast.group("chosen") and chosen is None:
            return None
        zone = None
        if cast.group("zone") is not None:
            zone = _spend_zone(cast.group("zone"))
            if zone is None:
                return None
        return _spend_clause(cast.group("quality"), SpendPurpose.CAST_SPELL, chosen, zone)

    activate = _SPEND_ACTIVATE_CLAUSE.match(phrase)
    if activate is not None:
        return _spend_clause(activate.group("quality") or "", SpendPurpose.ACTIVATE_ABILITY, None)
    if _SPEND_CUMULATIVE_UPKEEP_CLAUSE.match(phrase):
        # CR 702.24a's cost, not a spell or an ability: no quality to read.
        return SpendClause(purpose=SpendPurpose.PAY_CUMULATIVE_UPKEEP)
    return None


def free_tap_mana_abilities(
    card: Card, face: str | None = None
) -> list[tuple[ManaAbility, ManaRestriction | None]]:
    """Every mana ability this card may be tapped for **on the player's
    behalf**, in printed order, each paired with the CR 106.6 restriction its
    mana would carry (None if it carries none).

    Only an ability whose entire activation cost is a bare `{T}` qualifies.
    CR 601.2g lets a player activate mana abilities before paying a cost, and
    CR 118.3c makes doing so optional, but nothing there lets an *engine*
    spend a cost the player never agreed to - so a mana ability with anything
    else in its cost is skipped here even though `parse_mana_abilities` still
    reports it: an additional cost (Sunbaked Canyon's 1 life, Tinder Farm's
    sacrifice, Arena of Glory's `{R}` and exert) is a real cost only the player
    may choose to pay.

    A **restricted** ability is no longer skipped. It was, before the pool
    could carry a restriction - there was no way to check one later, so the
    only safe move was never to produce that mana automatically. Now the
    restriction travels with the mana and `auto_tap` can ask whether it permits
    the cost being paid, so a restricted source is offered exactly when its own
    text allows it and withheld otherwise.

    `face` narrows the result to one face's own abilities (CR 712.8d/712.8e/
    712.8f), the same convention `parse_mana_abilities`/`activated_abilities_of`
    use - pass `CardState.up_face_name`, never the bare `card`, whenever a
    real permanent is behind this call. Witch Enchanter sitting on the
    battlefield front face up must never offer Witch-Blessed Meadow's
    `{T}: Add {W}.` just because it is printed on the card's other half.
    `None` filters nothing, which keeps every single-faced card working as
    before.
    """
    found: list[tuple[ManaAbility, ManaRestriction | None]] = []
    for ability in parse_abilities(card):
        if not isinstance(ability, ActivatedAbility) or ability.mana is None:
            continue
        if face is not None and ability.face != face:
            continue
        if [piece.kind for piece in ability.costs] != [CostKind.TAP]:
            continue
        found.append((ability.mana, spend_restriction(ability.effect)))
    if found:
        return found
    intrinsic = intrinsic_land_ability(card, face)
    if intrinsic is not None and intrinsic.mana is not None:
        return [(intrinsic.mana, None)]
    return []


def free_tap_mana_ability(card: Card, face: str | None = None) -> ManaAbility | None:
    """The one mana ability this card may be tapped for on the player's behalf
    with **no** CR 106.6 restriction attached, or None if it has none.

    Kept for callers that have no cost in hand to judge a restriction against
    and so cannot safely be offered restricted mana. `auto_tap` uses
    `free_tap_mana_abilities` instead, which offers restricted abilities too
    and checks each restriction against what is actually being paid for.

    `face` is the same up-face filter `free_tap_mana_abilities` takes.
    """
    for ability, restriction in free_tap_mana_abilities(card, face):
        if restriction is None:
            return ability
    intrinsic = intrinsic_land_ability(card, face)
    return intrinsic.mana if intrinsic is not None and intrinsic.mana is not None else None


def _flexibility(options: list[list[Color]], any_color: bool) -> int:
    """How much of a real choice this ability is, least flexible first.

    Used only to order which sources an equally-small automatic assignment
    prefers to spend: a fixed source (a basic, a colourless rock) before a
    dual or shockland, and a dual before an any-colour source - so a flexible
    source is the one left untapped for whatever the player does next.

    Takes `options`/`any_color` already resolved against the board
    (`ManaAbility.effective`), not the ability's own unconditional shape, so a
    Tron piece is ranked on what it can actually make right now rather than
    its printed-alone `{T}: Add {C}.` line.
    """
    if any_color:
        return 2
    if len(options) > 1:
        return 1
    return 0


def _mana_context(
    payment: "CostPayment | _SpendContext", source: CardState
) -> tuple[frozenset[str], frozenset[str], bool]:
    """The board state `source`'s mana ability needs to resolve a CR 605.1a
    conditional "add X instead" clause right now: the land types its
    controller controls (Urza's Tower), the counters on `source` itself
    (Gemstone Caverns), and whether a card is exiled with it (Ugin's
    Labyrinth).

    Tapping a source changes nothing about who controls what, what counters
    are on a permanent, or what is exiled with it, so this is safe to compute
    once per candidate before any combination of sources is tried, rather than
    recomputed per combination - `Game._controlled_land_types` only reads
    control, not tapped status, and neither `source.counters` nor the exile
    zone is affected by tapping anything.
    """
    own_counters = frozenset(source.counters.counts)
    if payment.game is None:
        return frozenset(), own_counters, False
    has_imprinted_card = payment.game.card_imprinted_on(source.id) is not None
    controller = source.controller or payment.payer
    if controller is None:
        return frozenset(), own_counters, has_imprinted_card
    return payment.game._controlled_land_types(controller), own_counters, has_imprinted_card


def _mana_narrowings(
    payment: "CostPayment | _SpendContext", source: CardState, ability: ManaAbility
) -> dict:
    """The two board-derived narrowings `ManaAbility.effective` takes as
    keyword arguments, for a source being tapped through a payment.

    - **`could_produce_colors`** (CR 106.7) - the real survey, run over the
      permanents themselves rather than left to
      `colors_land_types_could_produce`'s land-type fallback. Reflecting Pool
      beside an Ancient Tomb taps for `{C}` because the Tomb's own printed
      ability says so, which no subtype set could ever report; Exotic Orchard,
      which has no fallback at all, becomes a mana source for the first time.
    - **`chosen_color`** (CR 614.12a) - the colour recorded on this permanent
      as it entered, for Utopia Sprawl's and Sunken Citadel's "the chosen
      color".

    `Game.colors_could_produce` carries its own recursion guard, so a Pool
    surveying a Pool terminates.
    """
    game = payment.game
    could_produce_colors = None
    if ability.could_produce is not None and game is not None:
        survey = getattr(game, "_could_produce_survey", None)
        if survey is not None:
            could_produce_colors = survey(ability.could_produce, source.controller or payment.payer)
    chosen_color = None
    choice = source.choice
    if choice is not None and choice.kind is ChoiceKind.COLOR:
        chosen_color = Color(choice.value)
    return {"could_produce_colors": could_produce_colors, "chosen_color": chosen_color}


#: One thing `auto_tap` may tap: the permanent, what its chosen ability would
#: add right now, and the CR 106.6 restriction that mana would carry.
_Candidate = tuple[CardState, list[list[Color]], ManaRestriction | None]


#: CR 105.1's five colours - what "one mana of any color" may be.
_FIVE_COLORS: tuple[Color, ...] = tuple(Color(letter) for letter in "WUBRG")


def mana_trigger_sources(game: Any) -> list[CardState]:
    """The permanents with a triggered mana ability (CR 605.1b) - a triggered
    ability whose effect adds mana - that a tap for mana might set off.

    Usually none, which is what keeps `triggered_mana_bonus` free on an
    ordinary board: the conditions are only read for these.
    """
    if game is None:
        return []
    return [
        permanent
        for permanent in game.battlefield
        if any(
            parse_triggered_mana(ability.effect) is not None
            for ability in triggered_abilities_on(game, permanent)
        )
    ]


def _triggered_mana_alternatives(
    shape: Any,
    trigger_source: CardState,
    tapped: CardState,
    produces: Sequence[Color],
    times: int,
    game: Any,
) -> list[list[Color]]:
    """What one triggered mana ability would add, one list per choice, its
    "for each" count already taken (`times`)."""
    colors = shape.colors
    if shape.snow_colors is not None and is_snow_source(tapped, game):
        colors = shape.snow_colors
    if colors:
        return [list(colors) * times]
    if shape.chosen_color:
        choice = trigger_source.choice
        if choice is None or choice.kind is not ChoiceKind.COLOR:
            return []
        try:
            return [[Color(choice.value)] * times]
        except ValueError:
            return []
    if shape.any_color:
        return [
            list(combo)
            for combo in combinations_with_replacement(_FIVE_COLORS, shape.any_color * times)
        ]
    if shape.produced_type:
        return [
            list(combo) for combo in combinations_with_replacement(dict.fromkeys(produces), times)
        ]
    return []


def triggered_mana_bonus(
    context: "CostPayment | _SpendContext",
    source: CardState,
    produces: Sequence[Color],
    trigger_sources: list[CardState] | None = None,
) -> list[list[Color]]:
    """Every way the triggered mana abilities that tapping `source` for
    `produces` sets off would add mana to the payer's pool - one alternative
    per choice of colour, `[[]]` when nothing would.

    CR 605.4a resolves a triggered mana ability "immediately after the mana
    ability that triggered it", and CR 601.2g has mana abilities activated
    before the cost is paid, so by CR 601.2h that mana is in the pool the cost
    is paid from: a cost only it can cover is payable (battle 7, B7-03).
    Nothing triggers here - `abilities_triggered_by` reads each condition
    against the events the tap would raise (CR 106.12a's tap, and the adding).
    """
    game = context.game
    if game is None or context.payer is None or source.zone is not Zone.BATTLEFIELD:
        return [[]]
    if trigger_sources is None:
        trigger_sources = mana_trigger_sources(game)
    if not trigger_sources:
        return [[]]
    alternatives: list[list[Color]] = [[]]
    events = (
        tapped_for_mana_event(source, game, mana_added=produces),
        mana_added_event(source, game, mana_added=produces),
    )
    for event in events:
        for trigger_source, ability, controller in abilities_triggered_by(
            game, event, trigger_sources
        ):
            shape = parse_triggered_mana(ability.effect)
            if shape is None or shape.restriction is not None:
                # CR 106.6: restricted mana is spend-dependent, and this scan
                # is hoisted independent of the spend; the only printing,
                # Snowfall's, pays cumulative upkeep, which no payment here is.
                continue
            if triggered_mana_recipient(shape.recipient, controller, event) != context.payer:
                continue
            times = (
                triggered_mana_count(game, shape.count, controller, source=trigger_source)
                if shape.count is not None
                else 1
            )
            if times <= 0:
                continue
            adds = _triggered_mana_alternatives(
                shape, trigger_source, source, produces, times, game
            )
            if shape.optional:
                # CR 608.2d: "may add" - a plan may take it or leave it.
                adds = [[], *adds]
            if adds:
                alternatives = [done + more for done in alternatives for more in adds]
    unique: dict[tuple[Color, ...], list[Color]] = {}
    for alternative in alternatives:
        unique.setdefault(tuple(sorted(alternative)), alternative)
    return list(unique.values())


def _with_triggered_mana(
    context: "CostPayment | _SpendContext",
    source: CardState,
    options: list[list[Color]],
    trigger_sources: list[CardState],
) -> list[list[Color]]:
    """Each of `options` followed by the mana its tap's triggered mana
    abilities add - the ability's own mana first, so `tap_for_mana` can tell
    the two apart again (`_activated_mana_ability_with_triggers`)."""
    expanded: dict[tuple[Color, ...], list[Color]] = {}
    for option in options:
        for bonus in triggered_mana_bonus(context, source, option, trigger_sources):
            combined = [*option, *bonus]
            expanded.setdefault(tuple(combined), combined)
    return list(expanded.values())


def _auto_tap_candidates(
    payment: "CostPayment | _SpendContext", sources: Iterable[CardState]
) -> list[_Candidate]:
    """Every source `auto_tap` may consider, paired with what it would
    actually add right now (conditional clauses resolved against the board -
    see `_mana_context`) and with the restriction that mana would carry, least
    flexible first.

    A source with both a restricted and an unrestricted `{T}`-only ability -
    Eldrazi Temple, Cavern of Souls, Delighted Halfling all print exactly that
    pair - appears twice, once per ability, so the solver can reach for the
    restricted one when this payment is something the restriction permits and
    fall back to the plain one when it is not. A restricted ability whose
    restriction does not permit `payment.spend` is dropped here rather than
    tried and rejected later, so it is never tapped for mana that could not be
    spent (CR 118.3c: activating a mana ability is never mandatory, so
    declining is always available).

    Two more things are asked of each ability before it is offered, both of
    them the ability's own and neither of them visible to the solver
    downstream:

    - **CR 602.5** - an ability prohibited from being activated is dropped
      (`_activation_refused`), so Mox Opal is not offered without metalcraft.
    - **CR 106.5** - a choice of colour the board leaves undefined is dropped
      (`_narrow_to_defined_colors`), and an ability left with no option at all
      is not a mana source at present, so Mox Amber is not offered with no
      legendary creature or planeswalker to name a colour among.
    """
    scanned = _scan_mana_candidates(payment, sources)
    return _filter_candidate_scan(scanned, payment.spend)


#: `_scan_mana_candidates`'s own row: a candidate plus the `any_color` flag
#: `_flexibility` needs to order it and the index `Game.activated_abilities`
#: knows the ability by, before CR 106.6's restriction is judged against any
#: particular `ManaSpend`.
#:
#: The index is carried for reporting, never for solving - `_filter_candidate_
#: scan` drops it again on the way into `_Candidate`, so nothing in the solver
#: sees it. `mana_ability_index` reads it back off a scan a caller already
#: hoisted, which is how a `TapPlan` entry says *which* ability makes its mana
#: without a second board survey per entry.
_ScannedCandidate = tuple[CardState, list[list[Color]], ManaRestriction | None, bool, int]


def _scan_mana_candidates(
    payment: "CostPayment | _SpendContext",
    sources: Iterable[CardState],
    *,
    include_life_paid: bool = False,
) -> list[_ScannedCandidate]:
    """The board-reading half of `_auto_tap_candidates`, with CR 106.6's
    restriction recorded but not yet judged against any particular spend.

    Every check this makes - `can_tap_for_mana`, CR 602.5's
    `_activation_refused`, `ability.effective`'s board survey - reads the
    battlefield and the payer, never `payment.spend`; only the one line this
    used to end on (`restriction.allows(payment.spend)`) is spend-dependent,
    and it is deliberately left for `_filter_candidate_scan` to apply
    afterwards. That split is what makes this list reusable: within one
    `legal_actions` enumeration the battlefield does not change from one
    action's cost to the next, so this expensive scan - `Game.computed_board`/
    `characteristics_of` underneath `can_tap_for_mana`/`_activation_refused`,
    the dominant cost `memory/flow-based-auto-tap-source-grouping.md`
    measured at ~80ms per call - runs once via `mana_candidate_scan` and every
    per-action `could_pay_mana_cost` call reuses it, paying only the cheap
    restriction filter each time.

    Sorting happens here rather than after filtering: the sort key
    (`_flexibility`, whether a restriction is present at all) never reads
    `payment.spend`, so sorting before or after dropping the entries a given
    spend disallows yields the same relative order for what remains - one
    scan, one sort, safe to filter as many times as there are spends to ask
    about.

    `include_life_paid` adds `life_paid_mana_activations`' rows, sorted after
    every free row so a plan reaches for life last, and - among those rows -
    by the life each one costs, ascending, so a plan that does reach for life
    reaches for the cheapest source rather than whichever one this scan found
    first. It is off everywhere the engine pays on a player's behalf
    (CR 118.3c).
    """
    candidates: list[_ScannedCandidate] = []
    paying_life: set[tuple[Any, int]] = set()
    life_cost: dict[tuple[Any, int], int] = {}
    trigger_sources = mana_trigger_sources(payment.game) if payment.payer is not None else []
    for source in sources:
        if source.zone is not Zone.BATTLEFIELD or source.tapped:
            continue
        if why_payer_cannot_use(source, payment.payer, payment.game) is not None:
            continue
        if not can_tap_for_mana(source, payment.game):
            continue
        land_types, own_counters, has_imprinted_card = _mana_context(payment, source)
        activations = tappable_mana_activations(source, payment.game)
        if include_life_paid:
            life_paid = life_paid_mana_activations(source, payment.game)
            paying_life.update((source.id, index) for index, _ability, _life in life_paid)
            life_cost.update({(source.id, index): life for index, _ability, life in life_paid})
            activations += [(index, activation) for index, activation, _life in life_paid]
        for index, activation in activations:
            ability = activation.mana
            if ability is None:
                continue
            if _activation_refused(payment, source, index) is not None:
                continue
            printed = spend_restriction(activation.effect)
            restriction = spend_restriction(printed.text, source) if printed is not None else None
            options, any_color = ability.effective(
                land_types,
                own_counters,
                has_imprinted_card,
                **_mana_narrowings(payment, source, ability),
            )
            options, any_color = _narrow_to_defined_colors(
                options, any_color, _among_colors(activation.effect, payment, source)
            )
            if not options:
                continue
            if trigger_sources:
                options = _with_triggered_mana(payment, source, options, trigger_sources)
            candidates.append((source, options, restriction, any_color, index))
    # A restricted ability first among a source's own abilities, so the mana
    # that can do less is the mana spent - the same preference `ManaPool._buckets`
    # applies inside the pool, applied here to which ability is activated.
    #
    # Free sources sort first (`paying_life`); among life-paid ones, the
    # cheaper life cost sorts first (`life_cost`, 0 for every free row) so a
    # plan reaching for life at all reaches for the smallest amount, not just
    # the first one this scan happened to find.
    candidates.sort(
        key=lambda item: (
            (item[0].id, item[4]) in paying_life,
            life_cost.get((item[0].id, item[4]), 0),
            _flexibility(item[1], item[3]),
            item[2] is None,
        )
    )
    return candidates


def _filter_candidate_scan(
    scanned: list[_ScannedCandidate], spend: "ManaSpend | None"
) -> list[_Candidate]:
    """`_scan_mana_candidates`'s rows narrowed to the ones CR 106.6 permits
    `spend` to draw on, in the `_Candidate` shape `_group_by_source` takes.

    The cheap half of what `_auto_tap_candidates` used to do in one pass -
    `mana_candidate_scan`/`_scan_mana_candidates` is the half that costs
    anything.
    """
    return [
        (source, options, restriction)
        for source, options, restriction, _any, _index in scanned
        if restriction is None or restriction.allows(spend)
    ]


def mana_candidate_scan(
    sources: Iterable[CardState],
    *,
    game: Any = None,
    payer: str | None = None,
    include_life_paid: bool = False,
) -> list[_ScannedCandidate]:
    """The public entry point for hoisting `_scan_mana_candidates` out of a
    loop over several costs - `legal_actions` calls this exactly once per
    enumeration and passes the result to every `could_pay_mana_cost` call it
    makes for that player, as `candidate_scan`.

    Built with no `spend` at all: as `_scan_mana_candidates` documents, the
    scan itself never reads `payment.spend`, so one scan serves every action's
    own spend purpose - `could_pay_mana_cost` applies `_filter_candidate_scan`
    with its own `spend` against the same rows.
    """
    return _scan_mana_candidates(
        _SpendContext(game=game, payer=payer, spend=None),
        sources,
        include_life_paid=include_life_paid,
    )


def _withheld_mana_sources(
    payment: "CostPayment", sources: Iterable[CardState]
) -> list[tuple[CardState, ActivatedAbility]]:
    """Every source among `sources` that `auto_tap` never considered because
    every mana ability it has costs more than a bare `{T}` - the land, or
    creature, that a refusal ought to name rather than leave the player to
    find by trial and error.

    CR 118.3c: activating a mana ability is never mandatory, even to pay a
    cost that is otherwise due, so `free_tap_mana_abilities` will not spend a
    life payment, a sacrifice, a discard, or any other cost the player did not
    choose - Nurturing Peatland's `{T}, Pay 1 life: Add {B} or {G}` is
    withheld exactly this way. This walks the same eligibility filters
    `_auto_tap_candidates` applies (on the battlefield, untapped, controlled
    by the payer, legal to tap for mana right now) before checking abilities,
    so a tapped land or one with no relevant ability at all is never named as
    though it had been passed over.

    A source with at least one bare-`{T}` mana ability is not withheld even if
    it also prints a costlier one (Tinder Farm's free `{T}: Add {G}` sits
    alongside a sacrifice ability) - `auto_tap` already had a free option to
    reach for, so that source is not what stood between the player and a
    legal payment.
    """
    withheld: list[tuple[CardState, ActivatedAbility]] = []
    for source in sources:
        if source.zone is not Zone.BATTLEFIELD or source.tapped:
            continue
        if why_payer_cannot_use(source, payment.payer, payment.game) is not None:
            continue
        if not can_tap_for_mana(source, payment.game):
            continue
        if tappable_mana_activations(source, payment.game):
            continue
        for ability in _activations_of(source, payment.game):
            if ability.mana is None:
                continue
            if [piece.kind for piece in ability.costs] == [CostKind.TAP]:
                continue
            withheld.append((source, ability))
    return withheld


def _unpayable_cost_message(payment: "CostPayment", sources: Iterable[CardState]) -> str:
    """The message `auto_tap` raises when no combination pays `payment.cost`.

    Names every source `_withheld_mana_sources` found so the refusal reads as
    "here is the source that could have helped and the cost it needed" rather
    than "the cost cannot be paid" - which is true only of automatic payment,
    not of the cost itself, and read the first time as an engine bug (see the
    module-level notes on `auto_tap` for the CR 118.3c reasoning). When no
    source was withheld, the plain cost-only message is kept so a genuinely
    unpayable cost - two Forests asked for {R}{W} - is never made to sound as
    though some source was passed over when none was.
    """
    base = f"no combination of the available mana sources can pay {payment.mana_owed}"
    withheld = _withheld_mana_sources(payment, sources)
    if not withheld:
        return base
    named = "; ".join(
        f"{source.name} was not auto-tapped because its only mana ability "
        f"costs more than {{T}} ({ability.cost}: {ability.effect}) - "
        "activate it manually to include it"
        for source, ability in withheld
    )
    return f"{base}: {named}"


def _solve_colours(
    combo: Sequence[_Candidate],
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    cost: ManaCost,
    life_available: int,
    spend: ManaSpend | None = None,
    base_restricted: list[Any] | None = None,
) -> list[tuple[CardState, list[Color]]] | None:
    """The first colour assignment for this exact set of sources that pays
    `cost`, or None if none of them do.

    Only the *set* of sources is fixed by the caller; this tries every colour
    a choice source in it could make - `combo`'s options are already resolved
    against the board by `_auto_tap_candidates` (`ManaAbility.effective`), so
    a Tron piece here is tried at what it actually produces right now, not
    its unconditional `{T}: Add {C}.` alone - until the resulting pool can
    pay the cost (`ManaPool.can_pay`, which already knows generic, hybrid,
    Phyrexian, and snow symbols), or exhausts them.

    The trial pool is seeded with the payment's existing restricted mana as
    well as its plain floating mana, and each source's own CR 106.6 restriction
    is carried onto what it adds, so "can this combination pay?" is asked of a
    pool that already knows which of its mana may legally be spent on `spend`.
    """
    option_lists = [options for _source, options, _restriction in combo]
    for chosen in product(*option_lists):
        trial = ManaPool(
            floating=dict(base_floating),
            snow=dict(base_snow),
            restricted=[entry.model_copy(deep=True) for entry in base_restricted or []],
        )
        for (source, _options, restriction), colors in zip(combo, chosen, strict=True):
            trial.add_all(colors, snow=is_snow_source(source), restriction=restriction)
        if trial.can_pay(cost, life_available=life_available, spend=spend):
            return [
                (source, list(colors))
                for (source, _options, _restriction), colors in zip(combo, chosen, strict=True)
            ]
    return None


#: One entry of the plan `_solve_auto_tap` returns: the source to tap, what
#: colour(s) to make it add, and the CR 106.6 restriction that mana carries -
#: everything `auto_tap` needs to call `tap_for_mana` and nothing it needs to
#: work out again.
#:
#: Public, because `plan_mana_payment` returns one: the solve used to be run
#: twice for every enumerated action and its answer thrown away both times
#: (once by `could_pay_mana_cost`, which reduced it to a bool, and again by
#: `auto_tap` when the action was actually taken). It is the same object in
#: both places now, and `machines/legal_actions` reports it on
#: `Action.pays_with` rather than discarding it.
#:
#: An empty list is a real answer and is not `None`: the cost is already
#: covered by floating mana, so no source needs tapping at all.
TapPlan = list[tuple[CardState, list[Color], ManaRestriction | None]]


def _solve_auto_tap_brute_force(
    context: "CostPayment | _SpendContext",
    sources: Iterable[CardState],
    *,
    owed: ManaCost,
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    base_restricted: list[Any],
    life_available: int,
) -> TapPlan | None:
    """Find a legal tapping-and-colour plan for `owed` out of `sources`, or
    None if none exists, by brute-force enumeration of which sources to tap.

    **Kept only as the flow solver's test-only reference oracle** (see
    `_solve_auto_tap_flow`, which is what `_solve_auto_tap` actually calls
    now) - `tests/scenarios/test_auto_tap_flow_property.py` generates random
    boards and costs and asserts the two agree on every one, because this one
    is slow but has been right for a long time and the flow solver is new.
    Nothing in production calls this any more: enumerating
    `combinations(candidates, size)` and then, for each combination, every
    colour a choice source in it could make, is exponential in the number of
    untapped sources, and a real board with a dozen or so duals/shocks/any-
    colour rocks already pushes a `{5}{B}{B}` question into multiple seconds.

    Prefers the fewest sources, and among equally-small choices prefers
    spending the least flexible ones first - see `_auto_tap_candidates` and
    `_flexibility`.

    An empty plan (`[]`, not `None`) means `owed` is already covered by
    `base_floating`/`base_snow`/`base_restricted` alone.
    """
    already_paid = ManaPool(
        floating=dict(base_floating),
        snow=dict(base_snow),
        restricted=[entry.model_copy(deep=True) for entry in base_restricted],
    )
    if already_paid.can_pay(owed, life_available=life_available, spend=context.spend):
        return []

    sources = list(sources)
    candidates = _auto_tap_candidates(context, sources)
    max_size = min(len(candidates), max(1, owed.converted))

    for size in range(1, max_size + 1):
        for combo in combinations(candidates, size):
            if len({id(source) for source, _o, _r in combo}) != len(combo):
                # A source with both a restricted and an unrestricted ability
                # appears once per ability; it still has only one `{T}` to
                # spend (CR 118.3: a permanent already tapped cannot pay a
                # cost that taps it), so a combination naming it twice is not
                # a legal plan.
                continue
            plan = _solve_colours(
                combo,
                base_floating,
                base_snow,
                owed,
                life_available,
                context.spend,
                base_restricted,
            )
            if plan is not None:
                chosen = {id(source): restriction for source, _o, restriction in combo}
                return [(source, colors, chosen[id(source)]) for source, colors in plan]
    return None


# --------------------------------------------------------------------------
# The flow solver
# --------------------------------------------------------------------------
#
# The exponential in `_solve_auto_tap_brute_force` is entirely in *which
# sources to tap* - the mana-pool layer underneath it, `ManaPool.can_pay` ->
# `payment_for` -> `_settle` -> `_assign`, is already a max-flow bipartite
# b-matching over `source -> demand -> allowed buckets -> sink` and costs
# fractions of a millisecond. The dominant case - N untapped permanents, each
# adding one mana from a set of colours it could choose, against a fixed set
# of demands - is exactly the shape `_assign` already solves, so
# `models.mana._assign_sources` extends that same network by the one layer
# `_assign_sources`'s own docstring describes: `demand -> bucket -> permanent
# -> sink`, with the new permanent -> sink cut (`capacity[permanent]`) the
# thing that keeps a choice a choice.
#
# What that extra cut cannot express is a permanent whose *choice* is between
# alternatives of more than one mana each - Shang-Chi's `{T}: Add two mana of
# any one color.` A capacity-2 node with five colour edges would let two units
# of flow leave by two different edges, which is two colours from one
# activation and not a choice of one; see `_assign_sources`'s own docstring
# for the mechanics. Those permanents (`_is_exotic`, below) are branched over
# explicitly instead, the same way `_solve_auto_tap_brute_force` always did,
# but only over *them* - on every board seen in this pool that is zero or one
# permanents, never the whole battlefield.


#: One ability's own alternative a permanent could produce if tapped for it -
#: the colours it would add and the CR 106.6 restriction that mana would
#: carry. `_auto_tap_candidates` already reads this off the board per
#: (source, ability) pair; `_group_by_source` below folds a permanent's
#: several abilities back together, since CR 118.3 gives it only one `{T}` to
#: spend on at most one of them.
_Alternative = tuple[list[Color], ManaRestriction | None]


def _group_by_source(
    candidates: list[_Candidate],
) -> list[tuple[CardState, list[_Alternative]]]:
    """`_auto_tap_candidates`'s one-entry-per-(source, ability) list, folded
    back to one entry per physical permanent.

    Eldrazi Temple's free `{T}: Add {C}.` and its restricted `{T}: Add
    {C}{C}.` arrive as two separate candidate tuples, because a CR 106.6
    restriction is judged per ability. A permanent can supply at most one of
    its abilities' worth of mana (CR 118.3: one `{T}` to spend), which is a
    fact about the *permanent* that the flow network has to see up front -
    `_is_exotic` and `_bucket_map` both read it off the grouped shape below,
    not off the flat one.

    Order is preserved from `candidates`, which `_auto_tap_candidates` has
    already sorted least-flexible-first - the order every provider node is
    inserted in, and so the order the flow solver prefers when several
    permanents could equally do.
    """
    order: list[int] = []
    grouped: dict[int, tuple[CardState, list[_Alternative]]] = {}
    for source, options, restriction in candidates:
        key = id(source)
        if key not in grouped:
            grouped[key] = (source, [])
            order.append(key)
        grouped[key][1].extend((option, restriction) for option in options)
    return [grouped[key] for key in order]


def _is_exotic(alternatives: list[_Alternative]) -> bool:
    """True when a permanent's alternatives cannot be laid into the flow
    network as ordinary edges - see the module-level notes above and
    `_assign_sources`'s own docstring for exactly what it can and cannot
    express.

    Safe whenever there is only one alternative at all, however much mana and
    however many colours it is (a Tron piece boosted to `{C}{C}{C}` has
    nothing to choose between), and safe whenever every alternative on offer
    is a single mana of a single colour (an ordinary dual, or Cavern of
    Souls's free `{C}` beside its restricted any-colour choice) - a capacity-1
    provider node already forces "at most one of these", which is CR 118.3's
    one-`{T}` rule for free.

    Unsafe exactly when a permanent offers a genuine choice **and** at least
    one option of that choice is more than one mana - Shang-Chi's is the only
    card in this pool shaped that way.
    """
    return len(alternatives) > 1 and any(len(option) > 1 for option, _restriction in alternatives)


def _slot_for(restriction: ManaRestriction | None, registry: list[ManaRestriction]) -> int:
    """`registry`'s index for `restriction`, recording it on first sight.

    `ManaPool._entry_for`'s own by-value matching, reused here so a permanent
    carrying a restriction already floating in the payer's pool lands in the
    very same bucket as that floating mana, rather than a second one the
    demand solver would have to be told to treat as identical.
    """
    if restriction is None:
        return UNRESTRICTED
    for index, seen in enumerate(registry):
        if seen == restriction:
            return index
    registry.append(restriction)
    return len(registry) - 1


def _bucket_map(
    source: CardState,
    alternatives: list[_Alternative],
    registry: list[ManaRestriction],
    game: Any = None,
) -> tuple[dict[_Bucket, int], int]:
    """The buckets one permanent could fill, and its own total capacity - the
    two things `_assign_sources` needs per provider.

    Only ever called on a permanent `_is_exotic` has cleared, or on one
    exotic alternative `_best_flow_plan` has already committed to, so every
    remaining choice is between single mana of single colours - safe to
    spread across one edge per colour, because the provider's own capacity (1
    for a real choice between abilities, or the fixed total of the one
    alternative when there is no choice at all) is what stops more than one
    of them being spent at once.
    """
    snow = is_snow_source(source, game)
    if len(alternatives) <= 1:
        option, restriction = alternatives[0] if alternatives else ([], None)
        slot = _slot_for(restriction, registry)
        counts = _MultiSet(option)
        buckets = {
            (color, snow, slot, NO_SPEND_EFFECT, NOT_RETAINED): amount
            for color, amount in counts.items()
        }
        return buckets, sum(counts.values())

    buckets = {}
    for option, restriction in alternatives:
        slot = _slot_for(restriction, registry)
        buckets[(option[0], snow, slot, NO_SPEND_EFFECT, NOT_RETAINED)] = 1
    return buckets, 1


def _chosen_alternative(
    alternatives: list[_Alternative],
    used: dict[_Bucket, int],
    snow: bool,
    registry: list[ManaRestriction],
) -> tuple[list[Color], ManaRestriction | None]:
    """Which of a tapped permanent's alternatives the flow solution actually
    used, read back from the buckets it put flow into.

    A permanent with only one alternative has nothing to read back - it *is*
    that alternative, whatever fraction of it the flow chose to spend,
    because tapping it produces the whole thing at once (CR 605.3b) and the
    rest just floats unspent (CR 106.4a). A permanent with more than one only
    ever has flow in the bucket its chosen alternative feeds, because its own
    capacity-1 cut in `_assign_sources` allows nothing else.

    `registry` must be the very same registry (or a later state of it)
    `_bucket_map` used to assign this permanent's own bucket slots - it is
    shared and mutated in place across every source `_best_flow_plan`
    considers for one flow-network build, seeded from `pool_registry` so a
    restriction already floating in the payer's pool keeps its slot. Passing
    a fresh, empty registry here instead - as this function used to - makes
    `_slot_for` renumber every restriction from 0 relative to this call
    alone, which only happens to match `used`'s real keys when nothing else
    (no other source, no floating restricted mana) registered a restriction
    first. When something did, the slot this recomputes is wrong, `used` has
    nothing at that key, and the source is silently dropped from the plan
    even though the flow solution actually spent it.
    """
    if len(alternatives) <= 1:
        if not alternatives:
            return [], None
        option, restriction = alternatives[0]
        return list(option), restriction
    for option, restriction in alternatives:
        slot = _slot_for(restriction, registry)
        if used.get((option[0], snow, slot, NO_SPEND_EFFECT, NOT_RETAINED), 0) > 0:
            return list(option), restriction
    return [], None


def _best_flow_plan(
    options: Sequence[PaymentOption],
    simple: list[tuple[CardState, list[_Alternative]]],
    exotic: list[tuple[CardState, list[_Alternative]]],
    pool_buckets: dict[_Bucket, int],
    pool_registry: list[ManaRestriction],
    game: Any = None,
) -> TapPlan | None:
    """The smallest tapping plan that settles `options` (one already-resolved
    reading of `ManaCost`'s payable-in-multiple-ways symbols) out of `simple`
    and `exotic` on top of `pool_buckets`, or None if none exists.

    `exotic` permanents are branched over explicitly - "not used" or "used for
    this one alternative", `product`ed across however many there are, which on
    every board in this pool is zero or one - and for each combination the
    rest (`pool_buckets` plus every `simple` permanent plus whichever `exotic`
    ones this combination commits to) is handed to `_assign_sources` as one
    flow problem. `None` is always the first choice tried for every exotic
    permanent, so a board that needs none of them settles in a single flow
    call and never explores a combination that would tap one unnecessarily -
    and ties are broken by whichever combination was found first, favouring
    that same all-`None` reading.
    """
    best: TapPlan | None = None
    best_size: int | None = None
    exotic_choices = [[None, *alternatives] for _source, alternatives in exotic]
    for choice_combo in product(*exotic_choices):
        registry = list(pool_registry)
        sources_map: dict[Hashable, dict[_Bucket, int]] = {
            ("pool", bucket): {bucket: amount} for bucket, amount in pool_buckets.items()
        }
        capacity_map: dict[Hashable, int] = dict.fromkeys(sources_map, 0)
        for key, amounts in sources_map.items():
            capacity_map[key] = sum(amounts.values())

        considered: list[tuple[CardState, list[_Alternative]]] = []
        for source, chosen in zip(exotic, choice_combo, strict=True):
            if chosen is None:
                continue
            buckets, capacity = _bucket_map(source[0], [chosen], registry, game)
            sources_map[id(source[0])] = buckets
            capacity_map[id(source[0])] = capacity
            considered.append((source[0], [chosen]))
        for source, alternatives in simple:
            buckets, capacity = _bucket_map(source, alternatives, registry, game)
            if not buckets:
                continue
            sources_map[id(source)] = buckets
            capacity_map[id(source)] = capacity
            considered.append((source, alternatives))

        # Restricted-before-unrestricted, non-snow-before-snow are the actual
        # preference (see `ManaPool._buckets`'s own reasoning, mirrored here);
        # `bucket[0].value`/`bucket[2]`/`bucket[3]` are pure tie-breakers with
        # no preference of their own, but they still have to be there. `_Bucket`
        # is `(Color, bool, int, int)`, and iterating a `set` of them walks it
        # in hash order - `Color` is a `StrEnum`, so that hash is
        # `PYTHONHASHSEED`-salted per CPython process. Without a total key,
        # every pair of unrestricted non-snow buckets of different colours ties
        # at `(True, False)` and the sort leaves that hash order showing
        # through, so which colour (and therefore which land) the flow below
        # prefers when several would do could vary by process even on an
        # identical board - the same class of bug `serialization.SortedSet`
        # fixes for a dumped `set` field, here in a live sort instead.
        all_buckets = sorted(
            {bucket for buckets in sources_map.values() for bucket in buckets},
            key=lambda bucket: (
                bucket[2] == UNRESTRICTED,
                bucket[4] != NOT_RETAINED,
                bucket[1],
                bucket[0].value,
                bucket[2],
                bucket[3],
            ),
        )
        demands = _demand_list(options, all_buckets)
        result = _assign_sources(demands, sources_map, capacity_map)
        if result is None:
            continue

        plan: TapPlan = []
        for source, alternatives in considered:
            used = result.get(id(source))
            if not used:
                continue
            colors, restriction = _chosen_alternative(
                alternatives, used, is_snow_source(source, game), registry
            )
            if colors:
                plan.append((source, colors, restriction))

        if best is None or len(plan) < best_size:  # type: ignore[operator]
            best, best_size = plan, len(plan)
    return best


def _solve_auto_tap_flow(
    context: "CostPayment | _SpendContext",
    sources: Iterable[CardState],
    *,
    owed: ManaCost,
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    base_restricted: list[Any],
    life_available: int,
    candidate_scan: list[_ScannedCandidate] | None = None,
) -> TapPlan | None:
    """The pure half of `auto_tap`: find a legal tapping-and-colour plan for
    `owed` out of `sources`, or None if none exists. Mutates nothing - no
    permanent is tapped, no pool is written to, and `context` may be a
    throwaway `_SpendContext` rather than a real `CostPayment`.

    `auto_tap` is `context._solve_auto_tap(...)` (below) followed by executing
    the plan this returns through `tap_for_mana`; `could_pay_mana_cost` is
    this and nothing else. Splitting the search out this way is what
    guarantees the two can never disagree, the same argument
    `TargetRequirement.rejects` already makes for `affordances.candidates`
    (magic-cards-model-api): the predicate and the action that acts on the
    predicate's answer share one implementation, so there is no second copy of
    the logic to drift out of sync with the first.

    This is the flow-based solver (see the module notes above
    `_group_by_source`); `_solve_auto_tap_brute_force` is kept only as its
    test-only reference oracle.

    An empty plan (`[]`, not `None`) means `owed` is already covered by
    `base_floating`/`base_snow`/`base_restricted` alone - `CostPayment.
    shortfall`'s own check, folded in here so both callers get it for free
    rather than needing their own copy of "is anything left to tap at all".

    `candidate_scan` is `mana_candidate_scan`'s output, hoisted by a caller
    that is about to ask this question many times over the same battlefield -
    `Game.legal_actions` is the one that exists today. Passed, the expensive
    per-source board scan (`_scan_mana_candidates`) is skipped entirely and
    only the cheap CR 106.6 filter (`_filter_candidate_scan`) runs against
    `context.spend`; omitted (`None`), the scan runs fresh exactly as before.

    `candidate_scan` is filtered down to `sources` first, rather than trusted
    outright: a caller that hoisted the scan over a wider battlefield than
    the `sources` it passes here (a narrower "these permanents only" question
    asked mid-enumeration) would otherwise get the wider scan's answer
    silently substituted for the narrower one it actually asked, which can
    turn a real `False` into a wrong `True`. `Game.legal_actions`'s own usage
    never triggers this - it always hoists the scan over the same
    `game.battlefield` it then passes as `sources` - but `could_pay_mana_cost`
    is a public entry point and nothing enforces that pairing for every future
    caller, so the filter is applied unconditionally rather than trusted by
    convention.
    """
    pool = ManaPool(
        floating=dict(base_floating),
        snow=dict(base_snow),
        restricted=[entry.model_copy(deep=True) for entry in base_restricted],
    )
    if pool.can_pay(owed, life_available=life_available, spend=context.spend):
        return []

    if candidate_scan is not None:
        source_ids = {source.id for source in sources}
        scanned = [entry for entry in candidate_scan if entry[0].id in source_ids]
    else:
        scanned = _scan_mana_candidates(context, sources)
    grouped = _group_by_source(_filter_candidate_scan(scanned, context.spend))
    simple = [
        (source, alternatives) for source, alternatives in grouped if not _is_exotic(alternatives)
    ]
    exotic = [
        (source, alternatives) for source, alternatives in grouped if _is_exotic(alternatives)
    ]
    pool_registry = [entry.restriction for entry in base_restricted]
    pool_buckets = pool._spendable_buckets(context.spend)

    for options in _candidate_options(owed, None):
        life = sum(option.life for option in options)
        if life > life_available:
            continue
        plan = _best_flow_plan(options, simple, exotic, pool_buckets, pool_registry, context.game)
        if plan is not None:
            return plan
    return None


def _solve_auto_tap(
    context: "CostPayment | _SpendContext",
    sources: Iterable[CardState],
    *,
    owed: ManaCost,
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    base_restricted: list[Any],
    life_available: int,
    candidate_scan: list[_ScannedCandidate] | None = None,
) -> TapPlan | None:
    """`auto_tap`/`could_pay_mana_cost`'s actual entry point - see
    `_solve_auto_tap_flow`, which this calls directly. Kept as its own name so
    every existing caller and docstring cross-reference stays correct without
    having to say "flow" - the brute-force predecessor is now
    `_solve_auto_tap_brute_force`, reachable only from the property test that
    checks the two still agree.
    """
    return _solve_auto_tap_flow(
        context,
        sources,
        owed=owed,
        base_floating=base_floating,
        base_snow=base_snow,
        base_restricted=base_restricted,
        life_available=life_available,
        candidate_scan=candidate_scan,
    )


def plan_mana_payment(
    cost: ManaCost,
    sources: Iterable[CardState],
    *,
    game: Any = None,
    payer: str | None = None,
    spend: "ManaSpend | None" = None,
    candidate_scan: list[_ScannedCandidate] | None = None,
) -> TapPlan | None:
    """*How* `cost` would be paid right now from `sources` plus whatever mana
    `payer` already has floating - which permanents get tapped, what colour
    each is made to add, and the CR 106.6 restriction that mana carries - or
    `None` if it could not be paid at all.

    This is the whole of what `could_pay_mana_cost` (below) does; the
    predicate is now literally `plan_mana_payment(...) is not None`, so there
    is exactly one implementation of "can this be paid" left and no second
    copy to drift. The same argument `_solve_auto_tap_flow`'s own docstring
    makes for splitting the search out of `auto_tap`, made once more one
    level up: the plan, the predicate, and the tapping `auto_tap` actually
    performs are all the same answer.

    **Purely informational.** Nothing about this asks a caller to name mana
    sources, and nothing consumes it on the way in - `auto_tap` still solves
    its own plan from every source offered and still stops as soon as the
    pool can pay (CR 118.3c). What it answers is a question a seat otherwise
    has to cast the spell to learn: *which* of its sources this cost eats.
    "This Bolt takes the Cavern of Souls I was holding" is a strategic fact
    about the board; "how do I pay for a Bolt" never was.

    An empty plan (`[]`) is a real, payable answer - `payer`'s floating mana
    already covers `cost` and no source needs tapping (see `TapPlan`).

    Deliberately builds no `CostPayment`. `CostPayment.for_total` is the only
    thing that ever should - it seeds its pool through `_seed_payer_pool`,
    which calls `_register_pool` and publishes the working pool into
    `game.open_payment_pools[payer]`. That write belongs to a payment that is
    actually about to happen; a read-only query must never make it, dead pool
    or not. This reads the payer's floating mana directly instead, through a
    throwaway `_SpendContext` that carries only `game`, `payer`, and `spend`.

    `game`/`payer` are both optional, the same way `CostPayment` allows a
    gameless payment for a unit test: omitted, this asks only whether `cost`
    is payable from `sources` alone, with no floating mana and no life to
    spend on a Phyrexian symbol.

    `candidate_scan` is `mana_candidate_scan(sources, game=game, payer=payer)`,
    computed once by a caller asking this question repeatedly over the same
    battlefield (`Game.legal_actions`) and passed to every call so the
    expensive board scan behind it runs exactly once per enumeration rather
    than once per candidate action - see `_solve_auto_tap_flow`.
    """
    context = _SpendContext(game=game, payer=payer, spend=spend)
    floating: dict[Color, int] = {}
    snow: dict[Color, int] = {}
    restricted: list[Any] = []
    life_available = 0
    if game is not None and payer is not None:
        try:
            player = game.player(payer)
        except (KeyError, ValueError, AttributeError):
            player = None
        if player is not None:
            pool = player.mana_pool
            floating = dict(pool.floating)
            snow = dict(pool.snow)
            restricted = [entry.model_copy(deep=True) for entry in pool.restricted]
            try:
                # CR 119.4b: "Players can always pay 0 life" - a total already
                # below zero (a mana ability's damage mid-payment) leaves 0 to
                # spend, never a negative budget that refuses a 0-life option.
                life_available = max(int(player.life), 0)
            except (TypeError, ValueError):
                life_available = 0
    return _solve_auto_tap(
        context,
        sources,
        owed=cost,
        base_floating=floating,
        base_snow=snow,
        base_restricted=restricted,
        life_available=life_available,
        candidate_scan=candidate_scan,
    )


def could_pay_mana_cost(
    cost: ManaCost,
    sources: Iterable[CardState],
    *,
    game: Any = None,
    payer: str | None = None,
    spend: "ManaSpend | None" = None,
    candidate_scan: list[_ScannedCandidate] | None = None,
) -> bool:
    """Whether `cost` could be paid right now from `sources` plus whatever
    mana `payer` already has floating - the public engine entry point for
    "could this cost be paid from this player's currently available
    resources", without paying anything.

    This is what legal-action enumeration calls, potentially many times per
    priority window, with its answers recorded in an append-only training
    log. It is `plan_mana_payment(...) is not None` and nothing else, so the
    predicate, the plan reported alongside the action, and the tapping
    `auto_tap` performs when the action is taken can never disagree - see
    `plan_mana_payment` for every argument, all of which are forwarded
    unchanged.

    A caller that wants the plan rather than the verdict should call
    `plan_mana_payment` directly rather than call this and then solve again.
    """
    return (
        plan_mana_payment(
            cost,
            sources,
            game=game,
            payer=payer,
            spend=spend,
            candidate_scan=candidate_scan,
        )
        is not None
    )


class CostStep(StrEnum):
    PENDING = "pending"
    TAPPING = "tapping"
    POOLED = "pooled"
    PAID = "paid"
    CANCELLED = "cancelled"


_ALLOWED: dict[CostStep, frozenset[CostStep]] = {
    CostStep.PENDING: frozenset({CostStep.TAPPING, CostStep.POOLED, CostStep.CANCELLED}),
    CostStep.TAPPING: frozenset({CostStep.TAPPING, CostStep.POOLED, CostStep.CANCELLED}),
    CostStep.POOLED: frozenset({CostStep.TAPPING, CostStep.PAID, CostStep.CANCELLED}),
    CostStep.PAID: frozenset(),
    CostStep.CANCELLED: frozenset(),
}


# --------------------------------------------------------------------------
# The non-mana half of a cost
# --------------------------------------------------------------------------


class ComponentKind(StrEnum):
    """The non-mana things a cost can ask for."""

    TAP = "tap"
    SACRIFICE = "sacrifice"
    DISCARD = "discard"
    EXILE = "exile"
    PAY_LIFE = "pay_life"
    REMOVE_COUNTERS = "remove_counters"
    #: "Put a -1/-1 counter on this creature:" (Devoted Druid), the templated
    #: twin of `REMOVE_COUNTERS` (CR 118.3, 122.1, 122.6). Unlike a loyalty
    #: cost's counters, which live on the ability's own source by definition
    #: (CR 606.4), this kind carries an explicit `counter_kind` because a
    #: printed cost can put on any named kind (Devoted Druid's -1/-1, a
    #: hypothetical +1/+1 or keyword counter).
    PLACE_COUNTERS = "place_counters"
    #: CR 606.4: "The cost to activate a loyalty ability of a permanent is to
    #: put on or remove from that permanent a certain number of loyalty
    #: counters, as shown by the loyalty symbol in the ability's cost." The
    #: amount is signed: positive puts counters on, negative removes them, and
    #: zero puts zero - `[0]` is a real cost whose payment is no event
    #: (CR 107.7). Not in `_OBJECT_KINDS`: the counters go on the ability's own
    #: source, so there is nothing to choose.
    LOYALTY = "loyalty"
    #: CR 701.43a, "to exert a permanent, you choose to have it not untap during
    #: your next untap step". Arena of Glory prints it inside an activation cost,
    #: `{R}, {T}, Exert this land:`.
    EXERT = "exert"
    #: CR 701.17a, "for a player to mill a number of cards, that player puts
    #: that many cards from the top of their library into their graveyard".
    #: Millikin prints it inside an activation cost, `{T}, Mill a card:`. Not
    #: in `_OBJECT_KINDS`: nothing is chosen, the cards are whichever ones are
    #: on top, so the count lives in `amount` the way paying life does.
    MILL = "mill"
    #: CR 107.6, "The untap symbol is {Q}. The untap symbol in an activation
    #: cost means 'Untap this permanent.'" The twin of `TAP`, and refused for
    #: the mirrored reason: "a permanent that's already untapped can't be
    #: untapped again to pay the cost". Umbral Mantle's granted `{3}, {Q}:` is
    #: the pool's printing.
    UNTAP = "untap"
    #: CR 701.59a, "to 'collect evidence N' means to exile any number of cards
    #: from your graveyard with total mana value N or greater." Detective's
    #: Phoenix prints it inside a bestow cost, `Bestow-{R}, Collect evidence
    #: 6.`. Not in `_OBJECT_KINDS`: "any number of cards" fixes no count at
    #: all, only the total mana value in `amount`, so the cards chosen are
    #: checked against that threshold rather than against a `required` count.
    COLLECT_EVIDENCE = "collect_evidence"
    #: CR 702.49a's own cost clause: "Return an unblocked attacking creature
    #: you control to its owner's hand." Ninjutsu's own cost, not shared with
    #: any other keyword this pool prints - `_why_not_return_to_hand` checks
    #: "unblocked attacking", the one restriction no existing object cost
    #: (SACRIFICE, DISCARD, EXILE) reads.
    RETURN_TO_HAND = "return_to_hand"
    #: CR 701.20a's reveal, as a cost (CR 118.1): "Reveal X white cards from
    #: your hand" (Martyr of Sands), "reveal a creature card from your hand"
    #: (Living Destiny's additional cost). Nothing moves (CR 701.20b); paying
    #: records the reveal on the game, and `variable_count` marks CR 107.3a's
    #: X, where `required` is the number the payer chose to reveal.
    REVEAL = "reveal"
    #: CR 701.4a's own keyword action, "to behold a [quality]": "Reveal a
    #: [quality] card from your hand or choose a [quality] permanent you
    #: control on the battlefield." Two zones satisfy one component - the
    #: chosen card is a `REVEAL` if it came from hand (CR 701.20a-b: shown,
    #: nothing moves) and untouched if it came from the battlefield (CR
    #: 701.4b: it is simply noted, not tapped, sacrificed, or exiled).
    BEHOLD = "behold"


_OBJECT_KINDS = frozenset(
    {
        ComponentKind.TAP,
        ComponentKind.UNTAP,
        ComponentKind.SACRIFICE,
        ComponentKind.DISCARD,
        ComponentKind.EXILE,
        ComponentKind.REMOVE_COUNTERS,
        ComponentKind.PLACE_COUNTERS,
        ComponentKind.EXERT,
        ComponentKind.RETURN_TO_HAND,
        ComponentKind.REVEAL,
        ComponentKind.BEHOLD,
    }
)


class CardRequirement(EngineModel):
    """What a cost demands of the cards chosen to pay it.

    CR 118.3 is the rule this serves: a player cannot pay a cost without the
    resources to pay it fully, and "a black card from your hand" is not paid by
    a red one. Every field is a disjunction and an empty field asks for nothing,
    so a bare `CardRequirement()` matches any card.
    """

    colors: list[Color] = Field(default_factory=list)
    """The card must be at least one of these colours."""
    types: list[Type] = Field(default_factory=list)
    """The card must have at least one of these card types."""
    subtypes: list[str] = Field(default_factory=list)
    """The card must have at least one of these subtypes, as printed."""
    supertypes: list[Supertype] = Field(default_factory=list)
    """The card must have **all** of these supertypes (CR 205.4a: "The
    supertypes are basic, legendary, ongoing, snow, and world"). Unlike the
    other three fields this is a conjunction, because a supertype in a cost
    phrase qualifies the noun after it - "a legendary card" is one demand, not
    a choice between several."""
    same_name_as: "CardRequirement | None" = None
    """Key to the Side-Door's "with the same name as a legendary permanent you
    control": the chosen card must share its name (CR 201.2a) with a permanent
    the payer controls that meets *this* requirement."""
    mana_value: int | None = None
    """Disrupting Shoal's "a blue card with mana value X from your hand": the
    chosen card's mana value (CR 202.3) must be exactly this.

    An exact number, not a ceiling - the printed phrase this reads is "with
    mana value N", and the X-keyed printing is the same sentence with
    CR 107.3a's announced X already substituted in. A "N or less" phrase is a
    different demand and is deliberately not read as this one."""
    description: str = ""
    """The phrase this was read from, for the message when it is not met."""
    excludes_source: bool = False
    """Gallia, Tragic Host's own "exile *another* creature card from your
    graveyard" - CR 601.2c calls this reading "another"/"other" already,
    `machines/targeting.py`'s own `TargetRequirement.excludes_source` is the
    identical concept on the targeting side, not a second name for a
    different one. `source_id` is what this checks against; set together,
    by `Game.activation_cost`, which is the one place that already knows
    which permanent this cost is being paid to activate."""
    source_id: UUID | None = None
    """The permanent `excludes_source` excludes, filled in by `Game.
    activation_cost` rather than by the reader that builds this
    `CardRequirement` - the reader never sees a live board, only the
    printed phrase."""

    @property
    def is_empty(self) -> bool:
        return not (
            self.colors
            or self.types
            or self.subtypes
            or self.supertypes
            or self.same_name_as
            or self.mana_value is not None
        )

    def why_not(self, card: CardState, game: Any = None, payer: str | None = None) -> str | None:
        """Why this card cannot pay, or None if it can.

        `game` and `payer` are needed only by `same_name_as`, which asks about
        the board rather than about the card alone. Without either there is no
        board to ask, and that half is skipped - a `CostPayment` with no game
        behind it cannot check any board-dependent requirement, the same
        limitation `_among_colors` documents on the mana side.

        The colour/type/subtype/mana-value checks below used to read
        `card.card` - the raw printing - unconditionally. That is CR 613.1's
        *starting point*, "the values of the characteristics printed on that
        card", never CR 613.5's "the application of continuous effects ... is
        continually and automatically performed": a card on the battlefield
        (`sacrifice a creature`, `tap an untapped creature you control`,
        CR 118.8a's additional costs) has to answer for what it *is*, and an
        animated land by earthbend (CR 701.66a) is a creature (CR 613.1d,
        layer 4; CR 205.1b's "in addition to its other types") that
        `card.card.types` would say is only ever a land. With a `game` and the
        card on the battlefield, `game.characteristics_of` is that answer.
        Off the battlefield there is no layer system to ask (CR 613.5 is about
        objects on the battlefield), so `CardState`'s own properties are read
        instead of the raw printing: they already resolve which face is up
        (CR 712.8d) the way `card.card`'s front face alone does not.
        """
        if self.excludes_source and self.source_id is not None and card.id == self.source_id:
            return f"{self.description or 'this cost'} excludes the ability's own source"
        if game is not None and card.zone is Zone.BATTLEFIELD:
            try:
                characteristics = game.characteristics_of(card)
            except (AttributeError, KeyError):
                characteristics = None
        else:
            characteristics = None
        if characteristics is not None:
            colors = set(characteristics.colors)
            supertypes = set(characteristics.supertypes)
            types = set(characteristics.types)
            subtypes = {subtype.lower() for subtype in characteristics.subtypes}
            mana_value = characteristics.mana_value
        else:
            colors = set(card.colors)
            supertypes = set(card.supertypes)
            types = set(card.types)
            subtypes = {subtype.lower() for subtype in card.subtypes}
            mana_value = card.mana_value

        if self.colors and not colors & set(self.colors):
            wanted = "/".join(color.value for color in self.colors)
            return f"{card.name} is not {wanted}"
        if self.supertypes and not set(self.supertypes) <= supertypes:
            wanted = " ".join(supertype.value for supertype in self.supertypes)
            return f"{card.name} is not {wanted}"
        if self.types and not types & set(self.types):
            wanted = "/".join(type_.value for type_ in self.types)
            return f"{card.name} is not {with_indefinite_article(wanted)}"
        if self.subtypes and not subtypes & self._wanted_subtypes():
            return f"{card.name} is not {with_indefinite_article('/'.join(self.subtypes))}"
        if self.mana_value is not None and mana_value != self.mana_value:
            # CR 202.3: the mana value is read off the object, not off the
            # printed front face - computed when there is a board to compute
            # it against, `CardState.mana_value`'s own up-face read otherwise.
            return (
                f"{card.name} has mana value {mana_value:g}, not the "
                f"{self.mana_value} this cost asks for"
            )
        if self.same_name_as is not None and game is not None and payer is not None:
            # CR 201.2a: "Two or more objects have the same name if they have
            # at least one name in common." Compared on `CardState.name`, which
            # is the name of the face that is up (CR 712.8d), rather than on
            # the printed front face.
            match = any(
                state.name == card.name and self.same_name_as.why_not(state) is None
                for state in game.permanents_controlled_by(payer)
            )
            if not match:
                return (
                    f"{payer} controls no {self.same_name_as.description or 'permanent'} "
                    f"named {card.name}"
                )
        return None

    def _wanted_subtypes(self) -> set[str]:
        """The subtypes this accepts, lowercased, plural forms included.

        A cost phrase names its subtype the way the sentence needs it, and
        Fireblast's "Sacrifice two Mountains" is plural while CR 205.3 prints
        the subtype itself as `Mountain`. Both spellings are accepted rather
        than the plural being stripped off the requirement, because CR 205.3i's
        own list of land types includes `Plains` and `Locus` - both genuinely
        end in *s*, and blind singularising would break them.
        """
        wanted = set()
        for subtype in self.subtypes:
            lowered = subtype.lower()
            wanted.add(lowered)
            if lowered.endswith("s"):
                wanted.add(lowered[:-1])
        return wanted


class CostComponent(EngineModel):
    """One non-mana piece of a cost, with the objects chosen to pay it.

    The choice of *which* permanent to sacrifice is made while announcing the
    spell (CR 601.2b) and the sacrifice itself happens when the total cost is
    paid (CR 601.2h), so a component carries its chosen objects from the moment
    it is built and only acts on them at payment time.

    CR 118.3: a player cannot pay a cost without the resources to pay it fully,
    and `why_not` is where that is decided - before anything has been spent.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: ComponentKind
    payer: str | None = None
    amount: int = 0
    """Life to pay, or counters to place/remove."""

    counter_kind: str = Counter.PLUS_ONE.value
    """Which kind of counter `PLACE_COUNTERS`/`REMOVE_COUNTERS` acts on - a
    named `Counter` or any string a card invents (CR 122.1). Unused by every
    other component kind."""

    required: int = 0
    """How many objects this component needs chosen. Zero for paying life."""

    cards: list[CardState] = Field(default_factory=list)
    """The objects chosen to pay this component, held by reference rather than
    by id. Kept as `CardState` rather than `list[UUID]` (unlike `CostPayment.
    tapped_for_mana`) because `why_not`/`pay` read a dozen of this object's own
    fields (`.zone`, `.tapped`, `.controller`, `.counters`, `.mana_value`,
    `.name`) throughout this class, several of them from call sites that pass
    no `game` at all (a unit test paying a bare component); reducing this to
    ids would mean every one of those reads needs a `game` to resolve through,
    which does not exist everywhere this class is used. `unpay` is the one
    place that both mutates through a captured reference *and* can run after a
    dump/decode round trip (a payment resumed from `AbilityOnStack.
    keyword_activation.payment`/`.unless_payment`), so that is where the
    re-resolve lives instead - see its own docstring's `_live` helper."""
    description: str = ""
    paid: bool = False

    requirement: CardRequirement | None = None
    """What the chosen cards have to be, when the cost says (CR 118.3)."""

    pay_mana_cost_of_chosen: bool = False
    """`ComponentKind.EXILE` only: Back from the Brink's own "... and pay its
    mana cost" shape (CR 118.9's "rather than pay [an alternative cost]" is
    not this - this is the *whole* cost, not an alternative to a printed
    one). The mana amount depends on which card is chosen, which is not
    known until the card is, so this only flags that the amount still needs
    adding once it is - `Game.activation_cost` is what reads the flag and
    folds `ManaCost.parse(card.mana_cost)` into the activation's mana cost
    for each chosen card, since a bare `CostComponent` has nowhere else to
    carry a mana requirement of its own."""

    zone: Zone = Zone.HAND
    """Where an `ComponentKind.EXILE` card must presently be (CR 406.2).

    Nothing in CR 406 ties exiling to the hand - a card can be exiled "from
    your graveyard" (Seasoned Pyromancer), "from your hand" (Force of Will), or
    from wherever it already is (a self-referential "Exile this card"). Only
    `EXILE` reads this; `DISCARD` is hand-only by definition (CR 701.9a: "To
    discard a card, move it from its owner's hand to that player's graveyard")
    and stays hardcoded.
    """

    variable_count: bool = False
    """The printed count is CR 107.3a's X or "one or more", so the number is
    whatever the payer announced or chose rather than one the text fixes. For
    `ComponentKind.REVEAL` ("Reveal X white cards from your hand") that is
    `required`, the number of cards they chose to reveal; for
    `ComponentKind.PAY_LIFE` ("Pay X life") and `REMOVE_COUNTERS` ("Remove X
    +1/+1 counters") it is `amount`; for the other object kinds it is
    `required`, which the reader leaves at the fewest that pays - 0 for X, 1
    for "one or more" - until `announce_count` fixes it."""

    source: str | None = None
    """The card whose cost this is, by name - the `Reveal.source` a paid
    `ComponentKind.REVEAL` records (CR 701.20a)."""

    _undo: list[tuple[CardState, dict[str, Any]]] = PrivateAttr(default_factory=list)
    """What `pay` changed, so `unpay` can put it back (CR 733.1). A
    `PrivateAttr`, so - unlike every `Field` above it - it does not survive a
    dump/decode round trip at all: a decoded `CostComponent` with `paid=True`
    always comes back with `_undo == []`. `unpay` refuses loudly rather than
    silently restoring nothing when that state was needed and is gone; see its
    own docstring."""

    _reveals_recorded: list[Any] = PrivateAttr(default_factory=list)
    """The `Reveal` records a paid `ComponentKind.REVEAL` wrote, so `unpay` can
    take exactly those back (CR 733.1). Private for the same reason `_undo` is."""

    def __str__(self) -> str:
        if self.description:
            return self.description
        if self.kind is ComponentKind.PAY_LIFE:
            return f"pay {self.amount} life"
        return f"{self.kind.value} {', '.join(card.name for card in self.cards) or self.required}"

    # -- legality ---------------------------------------------------------

    def why_not(self, game: Any) -> str | None:
        """Why this component cannot be paid, or None if it can (CR 118.3)."""
        if self.kind in _OBJECT_KINDS and len(self.cards) != self.required:
            return (
                f"{self.kind.value} needs {self.required} card(s) chosen, {len(self.cards)} given"
            )

        if self.requirement is not None:
            for card in self.cards:
                mismatch = self.requirement.why_not(card, game, self.payer)
                if mismatch is not None:
                    return mismatch

        checks = {
            ComponentKind.TAP: self._why_not_tap,
            ComponentKind.SACRIFICE: self._why_not_sacrifice,
            ComponentKind.DISCARD: lambda _: self._why_not_in_zone(Zone.HAND),
            ComponentKind.EXILE: lambda _: self._why_not_in_zone(self.zone),
            ComponentKind.PAY_LIFE: self._why_not_life,
            ComponentKind.REMOVE_COUNTERS: self._why_not_remove_counters,
            ComponentKind.PLACE_COUNTERS: self._why_not_place_counters,
            ComponentKind.LOYALTY: self._why_not_loyalty,
            ComponentKind.EXERT: self._why_not_exert,
            ComponentKind.MILL: self._why_not_mill,
            ComponentKind.UNTAP: self._why_not_untap,
            ComponentKind.COLLECT_EVIDENCE: self._why_not_collect_evidence,
            ComponentKind.RETURN_TO_HAND: self._why_not_return_to_hand,
            ComponentKind.REVEAL: self._why_not_reveal,
            ComponentKind.BEHOLD: self._why_not_behold,
        }
        return checks[self.kind](game)

    def _why_not_behold(self, _game: Any) -> str | None:
        """CR 701.4a: "Reveal a [quality] card from your hand or choose a
        [quality] permanent you control on the battlefield." Each chosen
        object has to be in one of those two places - owned in hand, or
        controlled on the battlefield - the same ownership/control check
        `_why_not_reveal`/`_why_not_controlled` already make for each half."""
        seen: set[UUID] = set()
        for card in self.cards:
            if card.id in seen:
                return (
                    f"{card.name} is named more than once, but one object is beheld only "
                    "once to pay a cost (CR 109.1, CR 118.3)"
                )
            seen.add(card.id)
            if card.zone is Zone.HAND:
                if self.payer is not None and card.owner is not None and card.owner != self.payer:
                    return f"{card.name} is not in {self.payer}'s hand"
            elif card.zone is Zone.BATTLEFIELD:
                if (
                    self.payer is not None
                    and card.controller is not None
                    and card.controller != self.payer
                ):
                    return f"{self.payer} does not control {card.name}"
            else:
                return (
                    f"{card.name} is neither in {self.payer or 'the payer'}'s hand nor a "
                    "permanent they control, so it cannot be beheld (CR 701.4a)"
                )
        return None

    def _why_not_reveal(self, _game: Any) -> str | None:
        """CR 118.3 for a reveal cost: every card named has to be in the
        payer's own hand ("from your hand"), and a card is one object
        (CR 109.1) - naming it twice reveals one card, not two."""
        seen: set[UUID] = set()
        for card in self.cards:
            if card.id in seen:
                return (
                    f"{card.name} is named more than once, but one card is revealed only "
                    "once to pay a cost (CR 109.1, CR 118.3)"
                )
            seen.add(card.id)
        in_hand = self._why_not_in_zone(Zone.HAND)
        if in_hand is not None:
            return in_hand
        if self.payer is not None:
            for card in self.cards:
                if card.owner is not None and card.owner != self.payer:
                    return f"{card.name} is not in {self.payer}'s hand"
        return None

    def _why_not_untap(self, _game: Any) -> str | None:
        """CR 107.6: "A permanent that's already untapped can't be untapped
        again to pay the cost" - the exact mirror of CR 107.5's already-tapped
        refusal, and CR 701.26b says the same from the other side ("Only tapped
        permanents can be untapped").

        CR 602.5a's summoning-sickness half - "a creature's activated ability
        with the tap symbol ({T}) or the untap symbol ({Q}) in its activation
        cost can't be activated unless the creature has been under its
        controller's control since their most recent turn began" - is a
        restriction on *activating*, not on paying, and lives where the
        `{T}` half of the same sentence already does (`can_tap_for_mana`,
        `Game.activate_ability`), not here.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be untapped"
            if not card.tapped:
                return f"{card.name} is already untapped, so it cannot be untapped to pay a cost"
        return self._why_not_controlled()

    def _why_not_collect_evidence(self, game: Any) -> str | None:
        """CR 701.59a-b: enough total mana value has to be there to exile.

        CR 701.59a fixes what the cost asks for - "exile any number of cards
        from your graveyard with total mana value N or greater" - and CR 701.59b
        is the "if unable" case: "if a player is given the choice to collect
        evidence but is unable to exile cards with total mana value N or greater
        from their graveyard ... they can't choose to do so." Choosing to pay a
        cost is such a choice, so a graveyard that cannot reach N refuses the
        payment outright rather than exiling what it can (CR 118.3).

        Cards already chosen are checked against the same threshold; an
        unchosen component is checked against the whole graveyard, because
        `pay` is what picks in that case.
        """
        if self.amount <= 0:
            # CR 118.5: a cost of nothing is paid by acknowledging it, and
            # "total mana value 0 or greater" is met by exiling nothing.
            return None
        if self.cards:
            for card in self.cards:
                if card.zone is not Zone.GRAVEYARD:
                    return f"{card.name} is in the {card.zone.value}, not the graveyard"
            controlled = self._why_not_controlled()
            if controlled is not None:
                return controlled
            total = sum(card.mana_value for card in self.cards)
            if total < self.amount:
                return (
                    f"the cards chosen have total mana value {total:g}, not the "
                    f"{self.amount} collect evidence {self.amount} asks for (CR 701.59a)"
                )
            return None
        if game is None or self.payer is None:
            return "collecting evidence needs a game and a player whose graveyard to exile from"
        graveyard = game.player(self.payer).cards_in(Zone.GRAVEYARD)
        available = sum(card.mana_value for card in graveyard)
        if available < self.amount:
            return (
                f"{self.payer}'s graveyard holds total mana value {available:g}, not the "
                f"{self.amount} collect evidence {self.amount} asks for (CR 701.59b)"
            )
        return None

    def _why_not_return_to_hand(self, game: Any) -> str | None:
        """CR 702.49a's "Return an unblocked attacking creature you control
        to its owner's hand" - Ninjutsu's own cost restriction.

        CR 509.1h/CR 506.4a are what "unblocked" means: an attacking
        creature with no blocker assigned to it, checked against the live
        `Combat` rather than the card's own printed text, since nothing
        prints "unblocked" on a card.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it is not attacking"
            controlled = self._why_not_controlled()
            if controlled is not None:
                return controlled
            if game is None:
                return "returning an attacking creature needs a game to check combat"
            attack = game.combat.attack_by(card.id) if game.combat is not None else None
            if attack is None:
                return f"{card.name} is not attacking, so it cannot pay this cost (CR 702.49a)"
            if attack.blockers:
                return f"{card.name} is blocked, so it cannot pay this cost (CR 702.49a)"
        return None

    def _evidence_to_exile(self, game: Any) -> list[CardState]:
        """Which graveyard cards this collect-evidence cost exiles.

        CR 701.59a's "any number of cards" is a choice, and nothing in the
        engine makes it, so the cards are taken highest mana value first -
        the fewest cards that reach the threshold. A component whose cards
        were chosen already keeps them.
        """
        if self.cards:
            return list(self.cards)
        graveyard = sorted(
            game.player(self.payer).cards_in(Zone.GRAVEYARD),
            key=lambda card: card.mana_value,
            reverse=True,
        )
        chosen: list[CardState] = []
        total = 0.0
        for card in graveyard:
            if total >= self.amount:
                break
            chosen.append(card)
            total += card.mana_value
        return chosen

    def _why_not_mill(self, game: Any) -> str | None:
        """CR 701.17b: a player can't mill more cards than their library holds,
        and "if given the choice to do so, they can't choose to take that
        action" - choosing to pay a cost is such a choice, so a short library
        refuses the payment outright rather than milling fewer (CR 118.3)."""
        if self.amount < 0:
            return "a cost cannot ask for a negative number of cards to be milled"
        if self.amount == 0:
            return None
        if game is None or self.payer is None:
            return "milling as a cost needs a game and a player to mill"
        library = game.player(self.payer).cards_in(Zone.LIBRARY)
        if len(library) < self.amount:
            return (
                f"{self.payer} cannot mill {self.amount} card(s) from a library of "
                f"{len(library)} (CR 701.17b)"
            )
        return None

    def _why_not_remove_counters(self, _game: Any) -> str | None:
        """CR 118.3: the counters removed by a cost have to be there already.

        Same principle CR 118.3 states for a tapped permanent and CR 606.6
        states for a loyalty ability's negative cost - "a permanent that's
        already tapped can't [pay a cost that taps it]" generalises to any
        resource a cost spends, counters included, and the whole cost is
        checked before anything is spent.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so its counters cannot be removed"
            if not card.can_remove_counters(self.counter_kind, self.amount):
                have = card.counter_count(self.counter_kind)
                return (
                    f"{card.name} has {have} {self.counter_kind} counter(s), not the "
                    f"{self.amount} its cost removes (CR 118.3)"
                )
        return self._why_not_controlled()

    def _why_not_place_counters(self, _game: Any) -> str | None:
        """Putting a counter on as a cost needs only a permanent to put it on.

        CR 122.6: "putting counters on an object" refers to it while it's on
        the battlefield, so a permanent that has already left has nothing to
        put a counter on. Unlike removing counters, there is no further
        resource requirement (CR 118.3) - a cost that puts a counter on is
        always payable once the permanent exists to receive it.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so a counter cannot be put on it"
        return self._why_not_controlled()

    def _why_not_loyalty(self, _game: Any) -> str | None:
        """CR 606.4 and 606.6: the counters go on or come off the source itself.

        CR 606.6: "A loyalty ability with a negative loyalty cost, taking into
        account any additional costs, can't be activated unless the permanent
        has at least that many loyalty counters on it." The counters must be
        there right now, because CR 118.3 has the whole cost checked before
        anything is spent.
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so its loyalty cost cannot be paid"
            if self.amount < 0 and card.counters[Counter.LOYALTY] < -self.amount:
                return (
                    f"{card.name} has {card.counters[Counter.LOYALTY]} loyalty, not the "
                    f"{-self.amount} its cost removes (CR 606.6)"
                )
        return None

    def _why_not_exert(self, _game: Any) -> str | None:
        """CR 701.43b-c: only a permanent, and being tapped is no obstacle.

        "A permanent can be exerted even if it's not tapped or has already been
        exerted in a turn", so the only thing that can refuse this is CR 701.43c:
        "An object that isn't on the battlefield can't be exerted."
        """
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be exerted"
        return self._why_not_controlled()

    def _why_not_tap(self, _game: Any) -> str | None:
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not on the battlefield, so it cannot be tapped"
            if card.tapped:
                return f"{card.name} is already tapped, so it cannot be tapped to pay a cost"
        return self._why_not_controlled()

    def _why_not_sacrifice(self, _game: Any) -> str | None:
        for card in self.cards:
            if card.zone is not Zone.BATTLEFIELD:
                return f"{card.name} is not a permanent, so it cannot be sacrificed"
        return self._why_not_controlled()

    def _why_not_controlled(self) -> str | None:
        """CR 701.21a: you can only sacrifice something you control."""
        if self.payer is None:
            return None
        for card in self.cards:
            if card.controller is not None and card.controller != self.payer:
                return f"{self.payer} does not control {card.name}"
        return None

    def _why_not_in_zone(self, zone: Zone) -> str | None:
        for card in self.cards:
            if card.zone is not zone:
                return f"{card.name} is in the {card.zone.value}, not the {zone.value}"
        return None

    def _why_not_life(self, game: Any) -> str | None:
        """CR 119.4: life can only be paid down to zero, and 0 is always payable."""
        if self.amount < 0:
            return "a cost cannot ask for a negative amount of life"
        if self.amount == 0:
            return None
        if game is None or self.payer is None:
            return "paying life needs a game and a player to pay it"
        life = game.player(self.payer).life
        if life < self.amount:
            return f"{self.payer} cannot pay {self.amount} life from a life total of {life}"
        return None

    # -- paying and rewinding ---------------------------------------------

    def pay(self, game: Any) -> None:
        reason = self.why_not(game)
        if reason is not None:
            raise ValueError(reason)
        if self.paid:
            raise ValueError(f"{self} has already been paid")

        if self.kind is ComponentKind.EXERT:
            for card in self.cards:
                self._remember(card)
                card.exerted = True  # CR 701.43a
        elif self.kind is ComponentKind.TAP:
            for card in self.cards:
                self._remember(card)
                card.tap()  # CR 701.26a: only untapped permanents can be tapped
                if game is not None:
                    # Tapping the permanent is the event (CR 701.26a); a unit
                    # test paying a component without a game emits nothing.
                    game.emit(
                        GameEvent(
                            event=TriggerEvent.BECOMES_TAPPED,
                            subject_id=card.id,
                            subject_name=card.name,
                            subject_controller=card.controller,
                            subject_card=card.card,
                            player=card.controller,
                        )
                    )
        elif self.kind is ComponentKind.SACRIFICE:
            for card in self.cards:
                self._remember(card)
                # A sacrifice cost is a sacrifice (CR 702.48b: "you sacrifice
                # that permanent as you pay the total cost"), and sacrificing
                # is CR 701.21a's move to the graveyard, not a destruction -
                # CR 701.8b destroys only from "destroy" effects or SBAs, and
                # an indestructible permanent is sacrificed all the same.
                game.sacrifice(card)
        elif self.kind is ComponentKind.DISCARD:
            # CR 701.9a's discard, through `Game.discard_cards` rather than
            # straight to the graveyard: madness (CR 702.35a) replaces where a
            # discarded card lands, and CR 603.2c's "whenever you discard one
            # or more cards" (Captain Howler, Sea Scourge) has to see every
            # card this one cost discarded as a single batch, cost-paid
            # discards included.
            for card in self.cards:
                self._remember(card)
            if self.cards:
                game.discard_cards(self.payer, list(self.cards), source=None)
        elif self.kind is ComponentKind.EXILE:
            for card in self.cards:
                self._remember(card)
            if self.cards:
                # `Game.exile_cards`, not `exile_permanent` per card: one cost
                # is one instruction, and CR 603.2c says "an ability triggers
                # only once each time its trigger event occurs. However, it can
                # trigger repeatedly if one event contains multiple
                # occurrences." A delve payment (CR 702.66a: "For each generic
                # mana in this spell's total cost, you may exile a card from
                # your graveyard rather than pay that mana") that exiles five
                # cards is one occurrence of "one or more cards leave your
                # graveyard", so Hardened Academic triggers once with a count
                # of five, not five times. Exiling card by card raised five
                # events and triggered it five times.
                #
                # CR 406.2: exile moves an object "from whatever zone it's
                # currently in" - not only a per-player zone the way the old
                # `game.player(self.payer).cards_in(card.zone).remove(card)`
                # assumed. Every exile-as-a-cost example before The Stone
                # Brain (Force of Will's hand, Seasoned Pyromancer's
                # graveyard) happened to be one of `self.payer`'s own
                # zones, so that assumption went untested until a cost
                # exiling a permanent straight off the shared battlefield
                # (`zone=Zone.BATTLEFIELD`) tried to remove it from a list
                # that was never holding it and raised `ValueError:
                # list.remove(x): x not in list` - Abstergo Entertainment's
                # own "Exile Abstergo Entertainment" cost hits the same gap.
                # `Game.exile_cards` already handles every zone generically -
                # battlefield departure events, token refusal (CR 111.8),
                # combat clean-up - so this delegates outright rather than
                # special-casing one more zone by hand.
                game.exile_cards(list(self.cards))
        elif self.kind is ComponentKind.REVEAL:
            # CR 701.20a: showing the cards is the whole payment, and CR
            # 701.20b keeps them where they are. The record is what
            # `Game.known_to` reads, and it ends when the card leaves the hand
            # (CR 400.7). A component paid with no game has nobody to show.
            for card in self.cards:
                self._remember(card)
                if game is not None:
                    before = len(game.reveals)
                    game.reveal(card, source=self.source)
                    self._reveals_recorded.extend(game.reveals[before:])
        elif self.kind is ComponentKind.BEHOLD:
            # CR 701.4a's two halves: a hand card is revealed exactly like
            # `REVEAL` (nothing moves, CR 701.20b); a battlefield permanent is
            # simply chosen (CR 701.4b) and nothing happens to it at all -
            # not tapped, not sacrificed, not exiled.
            for card in self.cards:
                self._remember(card)
                if game is not None and card.zone is Zone.HAND:
                    before = len(game.reveals)
                    game.reveal(card, source=self.source)
                    self._reveals_recorded.extend(game.reveals[before:])
        elif self.kind is ComponentKind.RETURN_TO_HAND:
            # CR 702.49a's own cost: the creature leaves combat as it leaves
            # the battlefield (the zone change is what ends its being an
            # attacker), through `Game.return_to_hand` rather than a bare
            # zone move so a leaves-the-battlefield trigger still sees it.
            for card in self.cards:
                self._remember(card)
                if game is not None:
                    game.return_to_hand(card)
        elif self.kind is ComponentKind.UNTAP:
            for card in self.cards:
                self._remember(card)
                # CR 107.6's "Untap this permanent", with `exert_applies=False`
                # because CR 701.43a delays one thing only - "it doesn't untap
                # during your next untap step" - and a cost is not that step.
                # The exert stays on for the step it was aimed at.
                card.untap(exert_applies=False)
        elif self.kind is ComponentKind.COLLECT_EVIDENCE and self.amount:
            # CR 701.59a's exile, through `Game.exile_cards` for the same
            # reason the `EXILE` branch above uses it: one cost is one
            # instruction, so a "one or more cards leave your graveyard"
            # trigger (CR 603.2c) sees a single batch however many cards the
            # threshold needed.
            chosen = self._evidence_to_exile(game)
            for card in chosen:
                self._remember(card)
            if chosen:
                game.exile_cards(list(chosen))
        elif self.kind is ComponentKind.MILL and self.amount:
            # CR 701.17a's move, routed through `Game.put_into_graveyard` so a
            # replacement effect watching a card enter a graveyard (Rest in
            # Peace) still gets its say - the same route `machines/effects._mill`
            # takes for a mill an *effect* performs.
            library = game.player(self.payer).cards_in(Zone.LIBRARY)
            for card in list(library[: self.amount]):
                self._remember(card)
                game.put_into_graveyard(card)
        elif self.kind is ComponentKind.PAY_LIFE and self.amount:
            game.player(self.payer).lose_life(self.amount)
        elif self.kind is ComponentKind.REMOVE_COUNTERS:
            # The counters come off at payment time (CR 601.2h/602.2b: the
            # cost is paid before the ability resolves), not when the
            # ability's effect resolves - Walking Ballista's damage and its
            # cost are two different things, and the counter is already gone
            # even if the ability is later countered on the stack.
            for card in self.cards:
                self._remember_counters(card)
                card.remove_counters(self.counter_kind, self.amount)
        elif self.kind is ComponentKind.PLACE_COUNTERS:
            # Same timing as above, the other direction (Devoted Druid): the
            # counter lands on the permanent as the cost is paid, so a
            # toughness drop from a -1/-1 counter is visible immediately,
            # before the ability that untapped it has even resolved.
            #
            # CR 614.16: "if an effect would put one or more counters on a
            # permanent" replacement effects (Vizier of Remedies) "apply if
            # the effect of a resolving spell or ability ... [does so], and
            # they also apply if another replacement or prevention effect
            # does so, even if the original event being modified wasn't
            # itself an effect" - that last clause is written for exactly
            # this case, a cost's own counter (CR 118.1: a cost is an action,
            # not an effect). CR 118.11 backs it from the cost side: "the
            # actions performed when paying a cost may be modified by
            # effects [and] the cost has still been paid" either way. So this
            # routes through `Game.add_counters` - the same replacement path
            # a resolving effect's counters already use - rather than
            # mutating the permanent directly. A unit test that pays a
            # component with no `game` has no replacement machinery to ask,
            # so it falls back to placing the counters unmodified.
            for card in self.cards:
                self._remember_counters(card)
                if game is not None:
                    game.add_counters(card, self.counter_kind, self.amount)
                else:
                    card.add_counters(self.counter_kind, self.amount)
        elif self.kind is ComponentKind.LOYALTY:
            # CR 606.4: the counter change *is* the cost, so it happens at
            # payment time - on activation, before the ability is on the stack
            # doing anything (CR 602.2). CR 107.7: `[+N]` puts N loyalty
            # counters on, `[−N]` removes N, and `[0]` puts zero, which is a
            # payment with no event at all.
            #
            # The plus half goes through `Game.add_counters`, the same door
            # `PLACE_COUNTERS` uses, so a loyalty counter put on as a cost
            # raises the counters-put event and can be replaced (CR 614.16,
            # CR 118.11) exactly like any other counter a cost places. A
            # component paid with no `game` behind it - a unit test - has
            # nothing to ask and mutates the permanent directly.
            for card in self.cards:
                self._remember_counters(card)
                if self.amount > 0:
                    if game is not None:
                        game.add_counters(card, Counter.LOYALTY, self.amount)
                    else:
                        card.counters.add(Counter.LOYALTY, self.amount)
                elif self.amount < 0:
                    card.counters.remove(Counter.LOYALTY, -self.amount)

        self.paid = True

    def unpay(self, game: Any) -> None:
        """Put back exactly what paying took, in reverse order (CR 733.1).

        Two hazards, both about what a decode leaves behind:

        - `self._undo` is a `PrivateAttr` (see its own docstring) and does not
          survive a dump/decode round trip at all. A paid component whose
          `_undo` came back empty cannot be rewound - not "rewound to no
          effect", genuinely cannot, because the prior state it needs is gone -
          so this refuses loudly rather than silently doing nothing, the same
          choice `CostPayment._restore_payer_pool` makes for `_preexisting`.
          `PAY_LIFE` is exempt: its rewind only ever reads `self.amount` and
          `self.payer`, both plain fields that do survive.
        - Even when `_undo` did survive (the ordinary, non-decoded case), the
          `CardState`s it captured are the ones `self.cards` already held, and
          those are real, live objects only until the *next* round trip -
          `self.cards: list[CardState]` is not `Any`/excluded and would decode
          to copies with the same id as, but not the same identity as, the
          battlefield object, the identical hazard `_equip_effect`/`_crew_
          effect` had for `activation.card`. `_live` below re-resolves each
          one through `game.find_by_id` before mutating it; `game` is `None`
          only for a component paid outside a `Game` (a unit test), where the
          captured object is the only real one there is.
        """
        if not self.paid:
            return
        if (
            not self._undo
            and self.kind is not ComponentKind.PAY_LIFE
            and (self.cards or self.amount)
        ):
            raise RuntimeError(
                f"{self} was paid but its undo history (CostComponent._undo) "
                "did not survive a dump/decode round trip, so there is "
                "nothing left to rewind it from"
            )

        def _live(card: CardState) -> CardState:
            if game is None:
                return card
            found = game.find_by_id(card.id)
            return found if isinstance(found, CardState) else card

        if self.kind is ComponentKind.PAY_LIFE:
            if self.amount:
                game.player(self.payer).gain_life(self.amount)
        elif self.kind is ComponentKind.REVEAL:
            # Revealing moved nothing (CR 701.20b), so neither does the
            # rewind; it takes back the records the payment wrote, so an
            # attempt rewound under CR 733.1 leaves nobody knowing the cards.
            if game is not None:
                for record in self._reveals_recorded:
                    if record in game.reveals:
                        game.reveals.remove(record)
            self._reveals_recorded = []
        elif self.kind is ComponentKind.BEHOLD:
            # Neither half moved anything (CR 701.4a/b), so the rewind is the
            # same as REVEAL's: only the reveal record a hand-half payment
            # wrote needs taking back.
            if game is not None:
                for record in self._reveals_recorded:
                    if record in game.reveals:
                        game.reveals.remove(record)
            self._reveals_recorded = []
        elif self.kind is ComponentKind.EXERT:
            # Exerting moves nothing either, and CR 701.43b lets it be exerted
            # more than once, so the rewind is simply putting the flag back.
            for card, _ in reversed(self._undo):
                _live(card).exerted = False
        elif self.kind is ComponentKind.TAP:
            # Tapping moves nothing, so untapping is the whole rewind.
            for card, _ in reversed(self._undo):
                _live(card).untap(exert_applies=False)
        elif self.kind is ComponentKind.UNTAP:
            # Untapping moves nothing either, so re-tapping is the whole
            # rewind - the mirror of `TAP`'s above.
            for card, _ in reversed(self._undo):
                _live(card).tap()
        elif self.kind is ComponentKind.MILL:
            # CR 733.1: the rewind has to put the cards back *on top*, in the
            # order they were milled in - `_return` appends, which would leave
            # them on the bottom of the library. Walking `self._undo` backwards
            # and inserting each at index 0 restores the original order.
            for card, snapshot in reversed(self._undo):
                live = _live(card)
                self._return(game, live, snapshot)
                library = game.player(self.payer).cards_in(Zone.LIBRARY)
                if library and library[-1] is live:
                    library.pop()
                library.insert(0, live)
        elif self.kind in (
            ComponentKind.LOYALTY,
            ComponentKind.REMOVE_COUNTERS,
            ComponentKind.PLACE_COUNTERS,
        ):
            # The counters were mutated in place, and the permanent never left
            # the battlefield, so the rewind puts the snapshotted `Counters`
            # model back wholesale. Not `_return`, which removes the card from
            # its zone list and re-appends it - reordering the battlefield for
            # a payment that moved nothing.
            for card, snapshot in reversed(self._undo):
                _live(card).counters = snapshot["counters"]
        else:
            for card, snapshot in reversed(self._undo):
                self._return(game, _live(card), snapshot)

        self._undo = []
        self.paid = False

    def _remember(self, card: CardState) -> None:
        """Snapshot everything about a card except which printing it is.

        Taken field by field rather than by name, so a rewind still restores
        state that other parts of the model add to `CardState` later.
        """
        snapshot = {
            name: getattr(card, name)
            for name in type(card).model_fields
            if name not in {"id", "card"}
        }
        self._undo.append((card, snapshot))

    def _remember_counters(self, card: CardState) -> None:
        """Snapshot a card's counters for the rewind of a counter-based cost
        (loyalty, `PLACE_COUNTERS`, `REMOVE_COUNTERS`).

        Not `_remember`: that snapshots every field *by reference*, and paying
        one of these costs mutates `counters` in place (CR 122.1e - a loyalty
        counter *is* the planeswalker's loyalty, and the same in-place
        `Counters.add`/`.remove` backs every other counter kind), so a
        by-reference snapshot would record the payment as if it had already
        happened and the rewind would rewind nothing. A deep copy of the
        `Counters` model is what unpay restores.
        """
        self._undo.append((card, {"counters": card.counters.model_copy(deep=True)}))

    def _return(self, game: Any, card: CardState, snapshot: dict[str, Any]) -> None:
        """Take the card out of wherever paying put it and restore its old state."""
        for zone_cards in game.shared_zones.values():
            if card in zone_cards:
                zone_cards.remove(card)
        for player in game.players:
            for zone_cards in player.zones.values():
                if card in zone_cards:
                    zone_cards.remove(card)

        for name, value in snapshot.items():
            setattr(card, name, value)

        zone = card.zone
        if zone.is_shared:
            game.shared_zones[zone].append(card)
        else:
            owner = card.controller or self.payer
            game.player(owner).cards_in(zone).append(card)
            if zone is Zone.LIBRARY:
                game.player(owner).note_library_changed()  # CR 701.20d


def tap_cost(*cards: CardState, payer: str | None = None, description: str = "") -> CostComponent:
    """Tap permanents as a cost. Already-tapped permanents cannot pay (CR 118.3)."""
    return CostComponent(
        kind=ComponentKind.TAP,
        cards=list(cards),
        required=len(cards),
        payer=payer,
        description=description,
    )


def untap_cost(*cards: CardState, payer: str | None = None, description: str = "") -> CostComponent:
    """Untap permanents as a cost (CR 107.6's `{Q}`).

    "The untap symbol in an activation cost means 'Untap this permanent.' A
    permanent that's already untapped can't be untapped again to pay the cost"
    - the exact mirror of `tap_cost`, refused by `_why_not_untap` for the
    mirrored reason (CR 118.3).

    Built empty by `cost_component_for_phrase`, because `{Q}` is a
    self-reference (CR 107.6's "this permanent") and only the caller knows
    which permanent that is - the same shape `exert_cost` uses for
    "Exert this land".
    """
    return CostComponent(
        kind=ComponentKind.UNTAP,
        cards=list(cards),
        required=len(cards) or 1,
        payer=payer,
        description=description,
    )


def collect_evidence_cost(
    amount: int, payer: str | None = None, description: str = ""
) -> CostComponent:
    """Collect evidence N as a cost (CR 701.59a).

    "To 'collect evidence N' means to exile any number of cards from your
    graveyard with total mana value N or greater." The N rides in `amount`,
    because "any number of cards" fixes no count - the threshold is the whole
    demand, and `_why_not_collect_evidence` is what checks it against
    CR 701.59b's "if unable ... they can't choose to do so".
    """
    return CostComponent(
        kind=ComponentKind.COLLECT_EVIDENCE,
        amount=amount,
        payer=payer,
        description=description,
        zone=Zone.GRAVEYARD,
    )


def sacrifice_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Sacrifice permanents as a cost (CR 701.21a).

    `required` says how many the cost asks for, so a cost with nothing to
    sacrifice can be built and then correctly refuse to be paid.
    """
    return CostComponent(
        kind=ComponentKind.SACRIFICE,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def exert_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Exert permanents as a cost (CR 701.43a).

    "To exert a permanent, you choose to have it not untap during your next
    untap step." Arena of Glory is the printing in this pool, and it exerts
    itself: `{R}, {T}, Exert this land: Add {R}{R}.`
    """
    return CostComponent(
        kind=ComponentKind.EXERT,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def discard_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Discard cards from hand as a cost."""
    return CostComponent(
        kind=ComponentKind.DISCARD,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def reveal_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    variable_count: bool = False,
) -> CostComponent:
    """Reveal cards from the payer's hand as a cost (CR 118.1, CR 701.20a).
    `CostComponent._why_not_reveal` is the check."""
    return CostComponent(
        kind=ComponentKind.REVEAL,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        variable_count=variable_count,
    )


def behold_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Behold a quality as a cost (CR 701.4a, CR 118.1): reveal a card from
    the payer's hand, or choose a permanent they control on the battlefield.
    `CostComponent._why_not_behold` is the check."""
    return CostComponent(
        kind=ComponentKind.BEHOLD,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def announce_reveal(
    component: CostComponent,
    revealing: Sequence[CardState] | None,
    x_value: int,
    source: str,
) -> CostComponent:
    """A reveal cost with the cards its payer named filled in (CR 601.2b).

    For a fixed count the count stands and the named cards must match it
    (`_why_not_reveal`, CR 118.3). For CR 107.3a's X the number revealed is
    the X announced: naming the cards fixes it, and an `x_value` announced as
    well has to agree. Nothing named leaves `required` at the announced
    `x_value` (0 when none was), which is a cost `legal_actions` can price and
    `Game.choose_cards_to_reveal` can ask about.
    """
    cards = list(revealing or [])
    required = component.required
    if component.variable_count:
        if revealing is not None:
            if x_value and x_value != len(cards):
                raise ValueError(
                    f"X was announced as {x_value}, but {len(cards)} card(s) were named to "
                    f"pay {component.description!r} (CR 107.3a)"
                )
            required = len(cards)
        else:
            required = x_value
    return component.model_copy(update={"cards": cards, "required": required, "source": source})


def announce_count(component: CostComponent, x_value: int, nominated: int) -> CostComponent:
    """A variable-count component with its number fixed as the cost is paid.

    CR 107.3a: an X in the cost is the `x_value` announced - life paid,
    counters removed, or objects chosen. "One or more" is every one of the
    `nominated` objects, and never fewer than one (CR 118.3 then refuses a
    choice of none). A fixed count, and a reveal (`announce_reveal`), come
    back unchanged.
    """
    if not component.variable_count or component.kind is ComponentKind.REVEAL:
        return component
    if component.kind in {
        ComponentKind.PAY_LIFE,
        ComponentKind.REMOVE_COUNTERS,
        ComponentKind.PLACE_COUNTERS,
    }:
        return component.model_copy(update={"amount": x_value})
    if component.required:
        return component.model_copy(update={"required": max(component.required, nominated)})
    return component.model_copy(update={"required": x_value})


def cost_announces_x(cost_text: str) -> bool:
    """Whether a printed cost has an X in it (CR 107.3a: "a mana cost,
    alternative cost, additional cost, and/or activation cost with an {X},
    [-X], or X in it") - `{X}` and Martyr of Sands's bare "Reveal X white
    cards" alike."""
    return re.search(r"\bX\b", cost_text or "") is not None


def return_to_hand_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
) -> CostComponent:
    """Return an unblocked attacking creature to its owner's hand as a cost
    (CR 702.49a's ninjutsu). `_why_not_return_to_hand` is the check."""
    return CostComponent(
        kind=ComponentKind.RETURN_TO_HAND,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
    )


def exile_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    zone: Zone = Zone.HAND,
) -> CostComponent:
    """Exile cards as a cost (CR 406.2).

    `zone` is where the card has to presently be - `Zone.HAND` for Force of
    Will's "exile a blue card from your hand", `Zone.GRAVEYARD` for Seasoned
    Pyromancer's "Exile this card from your graveyard". Nothing in CR 406 ties
    exiling to the hand; only the printed cost does, so the reader is what
    decides it, not this builder's default.
    """
    return CostComponent(
        kind=ComponentKind.EXILE,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        zone=zone,
    )


def exile_and_pay_mana_cost_cost(
    *cards: CardState,
    payer: str | None = None,
    required: int | None = None,
    description: str = "",
    zone: Zone = Zone.GRAVEYARD,
    requirement: CardRequirement | None = None,
) -> CostComponent:
    """Back from the Brink: "Exile a creature card from your graveyard and
    pay its mana cost" (CR 406.2, CR 118.9's shape of naming a card's own
    mana cost as a cost - Emerge and Delve's own "pay [a card's] mana cost"
    templates read the identical way, just not in this pool). The mana
    amount itself is not known here - only once a card is chosen - so
    `pay_mana_cost_of_chosen` flags it for `Game.activation_cost` to add.
    """
    return CostComponent(
        kind=ComponentKind.EXILE,
        cards=list(cards),
        required=len(cards) if required is None else required,
        payer=payer,
        description=description,
        zone=zone,
        requirement=requirement,
        pay_mana_cost_of_chosen=True,
    )


def mill_cost(amount: int, payer: str | None = None, description: str = "") -> CostComponent:
    """Mill cards as a cost (CR 701.17a).

    "For a player to mill a number of cards, that player puts that many cards
    from the top of their library into their graveyard." Nothing is chosen, so
    the count rides in `amount` exactly as paying life does.

    CR 701.17b is what makes a short library refuse the payment rather than
    mill fewer: "A player can't mill a number of cards greater than the number
    of cards in their library. **If given the choice to do so, they can't
    choose to take that action.**" Paying a cost is a choice, so CR 118.3's
    "a player can't pay a cost without the resources to pay it fully" and
    CR 701.17b agree - the second sentence's "if instructed to do so, they mill
    as many as possible" is for an *effect* that mills, never for a cost.
    """
    return CostComponent(
        kind=ComponentKind.MILL,
        amount=amount,
        payer=payer,
        description=description,
    )


def pay_life_cost(amount: int, payer: str | None = None, description: str = "") -> CostComponent:
    """Pay life as a cost (CR 118.3b, 119.4)."""
    return CostComponent(
        kind=ComponentKind.PAY_LIFE,
        amount=amount,
        payer=payer,
        description=description,
    )


def loyalty_cost(
    card: CardState, amount: int, payer: str | None = None, description: str = ""
) -> CostComponent:
    """A loyalty symbol as a cost (CR 606.4, CR 107.7).

    `amount` is signed: positive puts that many loyalty counters on the
    permanent, negative removes them, and zero puts zero - `[0]` is still a
    cost, paid by putting zero counters, which is no event at all. The
    permanent is the ability's own source (CR 606.4), so there is nothing to
    choose, and CR 606.6 gates a negative amount on the counters being there.
    """
    return CostComponent(
        kind=ComponentKind.LOYALTY,
        cards=[card],
        amount=amount,
        payer=payer,
        description=description,
    )


def remove_counters_cost(
    card: CardState | None,
    amount: int,
    counter_kind: CounterKind = Counter.PLUS_ONE,
    payer: str | None = None,
    description: str = "",
) -> CostComponent:
    """Remove counters from a permanent as a cost (CR 118.3, CR 122.1).

    Walking Ballista's "Remove a +1/+1 counter from this creature: It deals 1
    damage to any target" is the printing this reads (`cost_component_for_phrase`
    builds it from the sentence). Loyalty counters have their own component,
    `loyalty_cost`, where the counter change is the whole cost of a loyalty
    ability (CR 606.4) rather than a chosen amount of a chosen kind.

    `card` may be left `None` when the caller does not yet know which
    permanent this is - the self-referential "this creature" shape a printed
    cost sentence reads into, filled in by whoever resolves the self-reference
    (`Game.activation_cost`), the same way `exert_cost`/`exile_cost` do.
    """
    return CostComponent(
        kind=ComponentKind.REMOVE_COUNTERS,
        cards=[card] if card is not None else [],
        required=1,
        amount=amount,
        counter_kind=str(counter_kind),
        payer=payer,
        description=description,
    )


def place_counters_cost(
    card: CardState | None,
    amount: int,
    counter_kind: CounterKind = Counter.PLUS_ONE,
    payer: str | None = None,
    description: str = "",
) -> CostComponent:
    """Put counters on a permanent as a cost (CR 118.3, CR 122.1, CR 122.6).

    Devoted Druid's "Put a -1/-1 counter on this creature: Untap this
    creature." is the printing this reads. Unlike `remove_counters_cost`,
    nothing about the permanent's current counters can make this unpayable -
    only whether it is still there to receive one (`_why_not_place_counters`).

    `card` may be left `None` for the same self-referential reason
    `remove_counters_cost` allows it.
    """
    return CostComponent(
        kind=ComponentKind.PLACE_COUNTERS,
        cards=[card] if card is not None else [],
        required=1,
        amount=amount,
        counter_kind=str(counter_kind),
        payer=payer,
        description=description,
    )


# --------------------------------------------------------------------------
# The composite: mana plus components
# --------------------------------------------------------------------------


class TotalCost(EngineModel):
    """What casting a spell actually costs: a mana part and everything else.

    CR 601.2f calls this the total cost. It is what an alternative cost
    replaces and what an additional cost is added to.
    """

    mana: ManaCost = Field(default_factory=ManaCost)
    components: list[CostComponent] = Field(default_factory=list)

    waterbend_generic: int | None = None
    """CR 701.67b: when this total cost includes a waterbend cost, how much
    of `mana`'s generic is specifically the waterbend's own - the bound the
    alternate tap method (`machines/objects_as_costs.waterbend`) may not
    reach past, "even if the total cost ... includes other generic mana
    components." `None` for the ordinary case (no waterbend cost at all, or
    the whole of `mana`'s generic *is* the waterbend's own, which is every
    printing in the pool today - nothing prints a waterbend cost alongside
    another generic mana component in the same total cost yet). Set by
    `total_cost_for_phrase` when it folds in a `waterbend_mana_cost` piece,
    and carried onto the open `CostPayment` by `CostPayment.for_total`."""

    @classmethod
    def of(
        cls,
        mana: "ManaCost | str | None" = None,
        *components: CostComponent,
        waterbend_generic: int | None = None,
    ) -> "TotalCost":
        parsed = ManaCost.parse(mana) if isinstance(mana, str) else (mana or ManaCost())
        return cls(mana=parsed, components=list(components), waterbend_generic=waterbend_generic)

    @property
    def is_free(self) -> bool:
        """True if nothing at all has to be paid - not even {0} acknowledgement."""
        return self.mana.converted == 0 and not self.mana.x_count and not self.components

    def assign_payer(self, payer: str) -> "TotalCost":
        """Fill in who is paying on every component that did not say."""
        for component in self.components:
            if component.payer is None:
                component.payer = payer
        return self

    def __str__(self) -> str:
        parts = [str(self.mana)] if self.mana.converted or self.mana.x_count else []
        parts.extend(str(component) for component in self.components)
        return ", ".join(parts) or "{0}"


# --------------------------------------------------------------------------
# Cost increases and reductions (CR 601.2f, 118.7)
# --------------------------------------------------------------------------


def increase(cost: ManaCost, by: ManaCost) -> ManaCost:
    """Add a cost increase to a mana cost (CR 601.2f).

    Delegated to `ManaCost.plus`, which combines the two costs symbol for
    symbol. Rebuilding a total from generic and colour alone used to drop
    every hybrid, Phyrexian, and snow symbol, so Kitchen Finks with a kicker
    silently became `{1}` plus the kicker.
    """
    return cost.plus(by)


def reduce(cost: ManaCost, by: ManaCost) -> ManaCost:
    """Apply a cost reduction, following CR 118.7a-d, 118.7f-g.

    Delegated to `ManaCost.minus`, which is where those rules are worked out
    and where reducing *by* a hybrid symbol is refused (CR 118.7e).
    """
    return cost.minus(by)


def apply_modifications(
    base: ManaCost,
    increases: "list[ManaCost] | None" = None,
    reductions: "list[ManaCost] | None" = None,
    floor: int | None = None,
) -> ManaCost:
    """The mana part of a total cost, once increases and reductions are applied.

    CR 601.2f is where the total cost is worked out, and CR 118.9d confirms
    that additional costs, increases, and reductions all apply on top of an
    alternative cost. Increases are applied first here and reductions second;
    the rules text stating that order could not be retrieved in full from the
    rules search, so treat the ordering as this engine's choice rather than as
    a cited rule. It matters: reducing first and increasing after would let a
    reduction be undone by an increase that lands on top of it.

    What each reduction may touch *is* cited, in `ManaCost.minus`: CR 118.7a-d
    and 118.7f-g.

    `floor`, if given, is Trinisphere's shape - "each spell that would cost
    less than three mana to cast costs three mana to cast" - applied last, once
    every other increase and reduction has already run, because it reads
    "would cost", i.e. the cost as everything else has already left it. It is
    not a flat surcharge: only the shortfall against the floor is added, and
    always as generic mana, per Trinisphere's own reminder text ("a spell that
    would cost {1}{B} to cast costs {2}{B} to cast instead") - so a cost
    already at or above the floor is untouched, and one below it keeps its
    coloured pips and only gains enough generic to reach the floor.
    """
    total = base
    for extra in increases or []:
        total = increase(total, extra)
    for saving in reductions or []:
        total = reduce(total, saving)
    if floor is not None and total.converted < floor:
        total = increase(total, ManaCost.parse(f"{{{floor - total.converted}}}"))
    return total


# --------------------------------------------------------------------------
# Static cost-increase text on *other* permanents (CR 601.2f, 611.3)
# --------------------------------------------------------------------------
#
# Unlike `additional_cost_phrases`/`alternative_cost_phrases` below (a spell's
# own printed cost), these read a *different* permanent's static ability -
# Sphere of Resistance taxing every spell in the game, Trinisphere flooring
# them at three mana. Three shapes are recognised; anything else that mentions
# a cost increase is reported by `looks_like_unparsed_cost_modifier` so the
# caller can fail closed and record a notice instead of silently doing
# nothing, which is the exact defect this was written to fix (DDR#978).


class CostModifierKind(StrEnum):
    FLAT_INCREASE = "flat_increase"
    """"Spells cost {1} more to cast." / "Noncreature spells cost {1} more to
    cast." - Sphere of Resistance, Thorn of Amethyst, Lodestone Golem."""

    PER_SPELL_INCREASE = "per_spell_increase"
    """"Each spell a player casts costs {1} more to cast for each other spell
    that player has cast this turn." - Damping Sphere."""

    NAMED_INCREASE = "named_increase"
    """"Spells with the chosen name cost {3} more to cast." - Disruptor Flute.

    A flat increase like `FLAT_INCREASE`, but scoped by a CR 614.12a choice
    made as the source entered (`CardState.choice`, `ChoiceKind.CARD_NAME`)
    rather than by a card type, so the amount alone cannot say who it taxes:
    `Game.static_cost_modifiers_for` reads the chosen name off the permanent
    and compares it to the spell's own name."""

    FLOOR = "floor"
    """"Each spell that would cost less than [N] mana to cast costs [N] mana
    to cast." - Trinisphere."""

    COLOR_DECREASE = "color_decrease"
    """"`<Color>` spells you cast cost `{N}` less to cast." - the Medallion
    cycle (Ruby Medallion, etc.). "You cast" makes this controller-scoped,
    unlike the increase kinds above: `Game.static_cost_modifiers_for` only
    applies it when the permanent's controller is the one casting."""

    TYPE_DECREASE = "type_decrease"
    """"`<Type[ and Type]>` spells you cast cost `{N}` less to cast." (Ral,
    Monsoon Mage's front-face static, Goblin Electromancer) or its "Non-"
    qualified opposite, "`<Nontype>` spells you cast cost `{N}` less to
    cast." (Artist's Talent's level 2). Controller-scoped the same way as
    `COLOR_DECREASE`. Exactly one of `applies_to_types`/`excludes_type` is
    set, matching which of the two shapes was printed."""

    OPPONENT_TYPE_INCREASE = "opponent_type_increase"
    """"[<Qualifier> s]pells your opponents cast cost `{N}` more to cast." -
    Thalia, the Survivor's own "Noncreature spells your opponents cast cost
    {1} more to cast.", and the unqualified "Spells your opponents cast cost
    {1} more to cast." this same shape covers with `excludes_type` left
    `None`. `FLAT_INCREASE`'s own mirror, scoped the other way round from
    `COLOR_DECREASE`/`TYPE_DECREASE`: those apply only when the permanent's
    controller *is* the caster, this only when they are not
    (`Game.static_cost_modifiers_for`)."""


class CostModifierEffect(EngineModel):
    """One static cost-modifying ability, read off a permanent's oracle text."""

    model_config = ConfigDict(frozen=True)

    kind: CostModifierKind
    amount: int
    """The flat/per-spell surcharge, the floor's minimum mana value, or the
    decrease amount."""

    excludes_type: Type | None = None
    """`FLAT_INCREASE`/`TYPE_DECREASE`: the printed type the qualifier
    excludes - `Type.CREATURE` for "Noncreature spells", `Type.ARTIFACT` for
    "Nonartifact spells". `None` on `FLAT_INCREASE` means the increase is
    unconditional, like Sphere of Resistance's own "Spells cost {1} more to
    cast."."""

    requires_untapped: bool = False
    """`FLOOR` only: Trinisphere's "As long as this artifact is untapped,"
    condition (CR 611.3b keeps a static ability live only while its source
    carries it, and being tapped turns this one off)."""

    applies_to_color: Color | None = None
    """`COLOR_DECREASE` only: the one color named."""

    applies_to_types: tuple[Type, ...] | None = None
    """`TYPE_DECREASE` only, when the printed shape names type(s) positively
    ("Instant and sorcery spells...") rather than by exclusion - a spell
    needs only one of these types to qualify (CR 205.2a: a multi-type card is
    checked against all its types)."""


_QUALIFIER_EXCLUDES: dict[str, Type] = {
    "Noncreature": Type.CREATURE,
    "Nonartifact": Type.ARTIFACT,
    "Nonland": Type.LAND,
    "Noninstant": Type.INSTANT,
    "Nonsorcery": Type.SORCERY,
    "Nonenchantment": Type.ENCHANTMENT,
    "Nonplaneswalker": Type.PLANESWALKER,
}

_FLAT_COST_INCREASE = re.compile(
    r"(?:(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) )?[Ss]pells? cost \{(?P<amount>\d+)\} more to cast\."
)
#: Disruptor Flute's own tax, scoped by the card name it chose as it entered
#: (CR 614.12a) rather than by a card type. Matched ahead of
#: `_FLAT_COST_INCREASE` so the qualifier is never dropped: that pattern wants
#: "spells cost {N} more" contiguously and so cannot read this line at all,
#: which is precisely why the increase used to be recorded as an unparsed
#: notice and applied to nothing.
_NAMED_COST_INCREASE = re.compile(
    r"[Ss]pells with the chosen name cost \{(?P<amount>\d+)\} more to cast\."
)
#: Thalia, the Survivor's tax, and Grand Arbiter Augustin IV's own
#: unqualified "Spells your opponents cast cost {1} more to cast." - the
#: opponent-scoped mirror of `_FLAT_COST_INCREASE`. Matched ahead of it for
#: the same reason `_NAMED_COST_INCREASE` is: "spells ... your opponents
#: cast cost {N} more" is not contiguous "spells cost {N} more", so the
#: qualifier and the tax would otherwise be silently dropped rather than
#: read, the exact DDR#978 shape this permanent's own docstring names.
_OPPONENT_COST_INCREASE = re.compile(
    r"(?:(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) )?[Ss]pells your opponents cast cost "
    r"\{(?P<amount>\d+)\} more to cast\."
)
_PER_SPELL_COST_INCREASE = re.compile(
    r"Each spell a player casts costs \{(?P<amount>\d+)\} more to cast for each "
    r"other spell that player has cast this turn\."
)
_SPELL_COST_FLOOR = re.compile(
    r"(?P<condition>As long as this \w+ is untapped, )?"
    r"[Ee]ach spell that would cost less than (?P<threshold>\w+) mana to cast "
    r"costs (?P<total>\w+) mana to cast\."
)

#: The Medallion cycle's own template - one color, one flat amount. Reads
#: through the wider `_COLOR_WORDS` defined below (with "colorless"), which
#: this regex's own closed color alternation can never actually produce -
#: it exists once, past `_TYPE_WORDS`, so both this and `_requirement`'s
#: colorless-aware quality reading share one source of truth.
_COLOR_COST_DECREASE = re.compile(
    r"(?P<color>White|Blue|Black|Red|Green) spells you cast cost \{(?P<amount>\d+)\} "
    r"less to cast\.",
    re.IGNORECASE,
)

#: The exclusion-qualified shape - Artist's Talent's own level-2 "Noncreature
#: spells you cast cost {1} less to cast." - matched before the plain
#: inclusion shape below so its "Non..." prefix is not mistaken for the bare
#: type word inside it (though the two never actually collide: `\bcreature\b`
#: cannot match inside the single unbroken token "Noncreature").
_NONTYPE_COST_DECREASE = re.compile(
    r"(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) spells you cast cost \{(?P<amount>\d+)\} "
    r"less to cast\.",
)

#: The plain positive-inclusion shape - Ral, Monsoon Mage's own front-face
#: static "Instant and sorcery spells you cast cost {1} less to cast.",
#: Goblin Electromancer's identical wording. One or two type words, joined by
#: "and" the way the templating always prints a two-type qualifier.
_TYPE_WORDS: dict[str, Type] = {
    "creature": Type.CREATURE,
    "instant": Type.INSTANT,
    "sorcery": Type.SORCERY,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "planeswalker": Type.PLANESWALKER,
    "land": Type.LAND,
}
_TYPE_COST_DECREASE = re.compile(
    r"\b(?P<types>(?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker|Land)"
    r"(?: and (?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker|Land))?) "
    r"spells you cast cost \{(?P<amount>\d+)\} less to cast\.",
    re.IGNORECASE,
)

#: Anything that talks about a spell costing more, or a floor on what a spell
#: would cost, whether or not the shapes above could read it - Grand Arbiter
#: Augustin IV's "Spells your opponents cast cost {1} more to cast" mentions
#: an increase but is controller-relative, a shape none of the above parse.
_COST_MODIFIER_SIGNAL = re.compile(r"more to cast|would cost .* mana to cast")

#: The board-wide *decrease* signal, kept narrower and separate from
#: `_COST_MODIFIER_SIGNAL`: it is anchored on "spells you cast", the
#: Medallion/Electromancer grant's own grammatical subject, so it never fires
#: on a spell's *own* self-reduction sentence (Emrakul's "This spell costs
#: [N] less to cast for each card type...", already `Game.cost_reduction_for`'s
#: job, not this one) even after that spell resolves onto the battlefield and
#: its printed text is scanned here again.
_COST_DECREASE_SIGNAL = re.compile(r"spells you cast cost \{\d+\} less to cast", re.IGNORECASE)


def cost_modifier_effect(text: str) -> CostModifierEffect | None:
    """Read one static cost-modifying sentence off a permanent's oracle text.

    Returns `None` if nothing here matches a recognised shape - which is not
    the same as "this text has nothing to say about costs"; that distinction
    is `looks_like_unparsed_cost_modifier`'s job, kept separate so a numeral
    this engine cannot read (an out-of-range word, say) is reported rather
    than silently treated as "no effect here".
    """
    match = _NAMED_COST_INCREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.NAMED_INCREASE, amount=int(match.group("amount"))
        )
    match = _OPPONENT_COST_INCREASE.search(text)
    if match is not None:
        qualifier = match.group("qualifier")
        return CostModifierEffect(
            kind=CostModifierKind.OPPONENT_TYPE_INCREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES.get(qualifier) if qualifier else None,
        )
    match = _FLAT_COST_INCREASE.search(text)
    if match is not None:
        qualifier = match.group("qualifier")
        return CostModifierEffect(
            kind=CostModifierKind.FLAT_INCREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES.get(qualifier) if qualifier else None,
        )
    match = _PER_SPELL_COST_INCREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.PER_SPELL_INCREASE, amount=int(match.group("amount"))
        )
    match = _SPELL_COST_FLOOR.search(text)
    if match is not None:
        threshold = parse_count(match.group("threshold"))
        total = parse_count(match.group("total"))
        if threshold is None or total is None:
            return None
        return CostModifierEffect(
            kind=CostModifierKind.FLOOR,
            amount=total,
            requires_untapped=match.group("condition") is not None,
        )
    match = _COLOR_COST_DECREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.COLOR_DECREASE,
            amount=int(match.group("amount")),
            applies_to_color=_COLOR_WORDS[match.group("color").lower()],
        )
    match = _NONTYPE_COST_DECREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.TYPE_DECREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES[match.group("qualifier")],
        )
    match = _TYPE_COST_DECREASE.search(text)
    if match is not None:
        words = [word.strip().lower() for word in match.group("types").split(" and ")]
        types = tuple(_TYPE_WORDS[word] for word in words if word in _TYPE_WORDS)
        if types:
            return CostModifierEffect(
                kind=CostModifierKind.TYPE_DECREASE,
                amount=int(match.group("amount")),
                applies_to_types=types,
            )
    return None


class CostModifierNotice(EngineModel):
    """One permanent whose cost-modifying text could not be read (DDR#978).

    The same "unreadable is not the same as no effect" record `TargetingNotice`
    and `InterveningIfNotice` already keep in `machines/triggers.py`: a cost
    increase that silently fails to apply is indistinguishable from ordinary
    play - nobody is refused, nothing looks wrong - which is exactly how
    Trinisphere sat on a battlefield for several playtest turns doing nothing
    and nobody noticed. `Game.static_cost_modifiers_for` appends one of these
    instead of skipping the permanent quietly.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The permanent's own oracle text, for whoever reads the notice later."""


def looks_like_unparsed_cost_modifier(text: str) -> bool:
    """True if `text` reads like a cost-increase/floor effect this cannot
    turn into a `CostModifierEffect` - the fail-closed signal a caller records
    as a notice rather than silently skipping (the exact shape of DDR#978:
    a cost increase that fails to apply looks identical to ordinary play)."""
    if cost_modifier_effect(text) is not None:
        return False
    return bool(_COST_MODIFIER_SIGNAL.search(text)) or bool(_COST_DECREASE_SIGNAL.search(text))


# --------------------------------------------------------------------------
# Reading a card's own additional and alternative costs
# --------------------------------------------------------------------------

_ADDITIONAL = re.compile(
    r"^As an additional cost to cast this spell, (?P<what>[^.]+)\.", re.MULTILINE
)
_ALTERNATIVE = re.compile(
    r"^You may (?P<what>[^.]+?) rather than pay this spell's mana cost\.", re.MULTILINE
)
#: Force of Negation's and Force of Vigor's own cousin of `_ALTERNATIVE`: the
#: same CR 118.9 offer, gated on a plain "if it's not your turn" timing
#: condition printed ahead of it rather than offered unconditionally.
_ALTERNATIVE_IF_NOT_YOUR_TURN = re.compile(
    r"^If it's not your turn, you may (?P<what>[^.]+?) rather than pay this spell's mana cost\.",
    re.MULTILINE,
)


def additional_cost_phrases(card: Card) -> list[str]:
    """The "as an additional cost" sentences printed on the card (CR 118.8a)."""
    return [match.group("what") for match in _ADDITIONAL.finditer(card.oracle_text or "")]


def alternative_cost_phrases(card: Card) -> list[str]:
    """The "rather than pay this spell's mana cost" offers on the card (CR 118.9)."""
    return [match.group("what") for match in _ALTERNATIVE.finditer(card.oracle_text or "")]


class AlternativeCostOffer(EngineModel):
    """One CR 118.9 "rather than pay this spell's mana cost" offer, read off a
    spell's own printed text rather than off a named keyword - Force of
    Will's pitch cost is inline text, not a keyword the way Evoke or
    Flashback is, so `_option_from_keyword` never sees it.
    """

    model_config = ConfigDict(frozen=True)

    phrase: str
    requires_not_your_turn: bool = False
    """Force of Negation's and Force of Vigor's own gate: the offer only
    exists "if it's not your turn"."""


def alternative_cost_offers(card: Card) -> list[AlternativeCostOffer]:
    """Every inline CR 118.9 offer this card's own text prints - Force of
    Will's unconditional "You may pay 1 life and exile a blue card from your
    hand rather than pay this spell's mana cost." and Force of Negation's
    "If it's not your turn, you may exile a blue card from your hand rather
    than pay this spell's mana cost." alike.
    """
    offers = [
        AlternativeCostOffer(phrase=match.group("what"))
        for match in _ALTERNATIVE.finditer(card.oracle_text or "")
    ]
    offers.extend(
        AlternativeCostOffer(phrase=match.group("what"), requires_not_your_turn=True)
        for match in _ALTERNATIVE_IF_NOT_YOUR_TURN.finditer(card.oracle_text or "")
    )
    return offers


#: Omniscience: "You may cast spells from your hand without paying their mana
#: costs." CR 118.9's *other* half - "a cost listed in a spell's text, **or
#: applied to it from another effect**" - so this is read off a permanent on
#: the battlefield rather than off the spell being cast, and the spell it
#: applies to prints nothing about it at all.
#:
#: Omnipresence's own sibling narrows by mana value instead of by type:
#: "You may cast spells with mana value less than or equal to the number of
#: creatures you control from your hand without paying their mana costs." -
#: the optional clause between "spells" and "from your hand" reads either a
#: literal number ("mana value 3 or less", not printed on any pool card but
#: the same CR 107.3a-free shape) or a live count phrased "the number of
#: [quality] you control", read again at CR 601.2f by `mana_value_cap_for`.
_STATIC_FREE_CAST = re.compile(
    r"^You may cast (?P<what>[\w' -]*?spells?)"
    r"(?: with mana value (?:(?P<mv_number>\d+) or less"
    r"|less than or equal to (?P<mv_quality>.+?)))?"
    r" from your (?P<zone>hand|graveyard) "
    r"without paying (?:its|their) mana costs?\.$",
    re.IGNORECASE,
)

#: "the number of creatures you control" - `mana_value_cap_for`'s own reading
#: of `StaticFreeCastGrant.max_mana_value_quality`, sharing `_requirement`
#: with every other quality this module already counts (`_PHRASE_SACRIFICE`
#: and friends), rather than a new vocabulary just for this one card.
_THE_NUMBER_OF_YOU_CONTROL = re.compile(r"^the number of (?P<quality>.+?) you control$")


class StaticFreeCastGrant(EngineModel):
    """A permanent's static ability applying CR 118.9's alternative cost of
    *nothing at all* to spells its controller casts - Omniscience.

    Distinct from `AlternativeCostOffer` in where it is read from: that one is
    the spell's own CR 604.6 static ability, functioning from the zone it is
    cast from, and this one is CR 604.2's ordinary battlefield static ability
    reaching out at somebody else's spell. Distinct from `PlayPermission` in
    what it does: this grants no permission to cast anything that could not
    already be cast (the card is in hand, where it was always castable), only
    a different thing to pay (CR 118.9c).
    """

    model_config = ConfigDict(frozen=True)

    zone: Zone
    """Where the spell has to be cast from for the grant to apply."""
    type_word: str | None = None
    """The card type the grant is narrowed to, lowercased ("creature spells
    from your hand"), or None for every spell."""
    max_mana_value: int | None = None
    """A printed literal cap ("mana value 3 or less"), or None when the grant
    prints no fixed number - either no cap at all, or `max_mana_value_quality`'s
    live one. Exactly one of the two is ever set."""
    max_mana_value_quality: str | None = None
    """Omnipresence's own live cap, as the printed quality phrase ("the
    number of creatures you control") rather than a precomputed count - this
    is a live board read at CR 601.2f, not a fact fixed when the permanent
    entered, so nothing here may cache a number. `mana_value_cap_for` counts
    it against the board when the grant is actually checked."""


def static_free_cast_grant(text: str) -> StaticFreeCastGrant | None:
    """Read one static ability line into a `StaticFreeCastGrant`, or None.

    Fails closed: a line this cannot read returns None rather than a guess, so
    a spell is never quietly made free by text nobody parsed.
    """
    match = _STATIC_FREE_CAST.match(text.strip())
    if match is None:
        return None
    zone = _ZONE_WORDS.get(match.group("zone").lower())
    if zone is None:
        return None
    what = match.group("what").strip().lower()
    qualifier = re.sub(r"spells?$", "", what).strip()
    mv_number = match.group("mv_number")
    mv_quality = match.group("mv_quality")
    return StaticFreeCastGrant(
        zone=zone,
        type_word=qualifier or None,
        max_mana_value=int(mv_number) if mv_number is not None else None,
        max_mana_value_quality=mv_quality.strip() if mv_quality is not None else None,
    )


def mana_value_cap_for(
    grant: StaticFreeCastGrant, game: Any = None, controller: str | None = None
) -> int | None:
    """The live mana-value cap `grant` puts on what it makes free.

    `None` either when the grant carries no cap at all (an ordinary
    Omniscience-shaped grant, `grant.max_mana_value_quality` unset - the
    caller tells this apart from the case below by checking that field
    itself, a printed fact rather than a computed one) or when a printed
    quality this cannot read leaves a *live* cap unreadable - CR 118.3's
    "cannot use what was not read", not "nothing to cap", which is why the
    caller has to distinguish the two rather than treating both as free.
    """
    if grant.max_mana_value is not None:
        return grant.max_mana_value
    if grant.max_mana_value_quality is None:
        return None
    match = _THE_NUMBER_OF_YOU_CONTROL.fullmatch(grant.max_mana_value_quality.strip().lower())
    if match is None or game is None or controller is None:
        return None
    requirement = _requirement(match.group("quality"))
    if requirement is None:
        return None
    return sum(
        1
        for state in game.permanents_controlled_by(controller)
        if requirement.why_not(state, game, controller) is None
    )


# --------------------------------------------------------------------------
# Reading a printed cost phrase into something payable
# --------------------------------------------------------------------------

_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
    "colorless": Color.COLORLESS,
}

#: "Pay 2 life" and CR 107.3a's "Pay X life" (Krumar Initiate), whose amount is
#: the X announced as the cost is paid.
_PHRASE_PAY_LIFE = re.compile(rf"^pay {count_pattern('amount', x=True)} life$", re.IGNORECASE)
#: The count of an object cost: a number, CR 107.3a's X ("Exile X cards from
#: your graveyard", Necropolis Fiend), or "one or more" ("Sacrifice one or
#: more artifacts", Radiant Lotus). Read back with `_cost_count`.
_COST_COUNT = rf"(?P<count>one or more|{count_pattern(x=True)})"
#: `Exile a black card from your hand` (Force of Will) and the self-referential
#: `Exile this card from your graveyard` (Seasoned Pyromancer). CR 406.2 never
#: restricts exiling to the hand, so the zone is read off the sentence rather
#: than assumed - `exile_cost`'s default is only ever a fallback for a
#: sentence that names none.
#: The optional "with mana value N" tail Disrupting Shoal's pitch cost prints
#: ("exile a blue card with mana value X from your hand", CR 107.3a's X already
#: substituted). It sits between the noun and the zone, so it is spelled once
#: here and shared by every phrase that can carry it.
_MANA_VALUE_TAIL = r"(?: with mana value (?P<mana_value>\d+))?"
#: Gallia, Tragic Host's own "exile another creature card from your
#: graveyard" - CR 601.2c/113.6's "another"/"other" reads as a single
#: implicit "one", excluding the ability's own source (the same concept
#: `machines/targeting.py`'s own `TargetRequirement.excludes_source` already
#: names on the targeting side; `_requirement`'s caller below is what
#: actually marks `CardRequirement.excludes_source`, since `_requirement`
#: itself never sees which permanent this cost belongs to).
_PHRASE_EXILE = re.compile(
    rf"^exile (?:this card|(?:(?P<another>another)|{_COST_COUNT}) (?P<quality>[\w ]*?)cards?)"
    + _MANA_VALUE_TAIL
    + r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))?$",
    re.IGNORECASE,
)
#: CR 701.20a's reveal as a cost: "Reveal X white cards from your hand"
#: (Martyr of Sands, Martyr of Spores), "reveal a creature card from your
#: hand" (Living Destiny). The count is a number word or CR 107.3a's X, and
#: the quality is read by `_requirement` like every other object cost's. A
#: rider after "hand" - Illuminated Folio's "that share a color" - is not this
#: shape, so that phrase stays unread rather than paying for the wrong cards.
_PHRASE_REVEAL = re.compile(
    r"^reveal (?P<count>x|\w+) (?P<quality>[\w ,]*?)cards? from your hand$",
    re.IGNORECASE,
)
#: CR 701.4a's keyword action as a cost: "behold a Jace" (Countersculpt,
#: Theorist's Sanctum), "behold a Kithkin" (Kinsbaile Aspirant, off-set).
#: "Reveal a [quality] card from your hand or choose a [quality] permanent
#: you control on the battlefield" - one component, `ComponentKind.BEHOLD`,
#: since CR 701.4a is a single keyword action with two ways to satisfy it,
#: not two separate costs the way sacrifice-or-discard would be.
_PHRASE_BEHOLD = re.compile(r"^behold (?:a|an) (?P<quality>[\w' ]+)$", re.IGNORECASE)
_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "battlefield": Zone.BATTLEFIELD,
}
#: Back from the Brink: "Exile a creature card from your graveyard and pay
#: its mana cost". Ahead of `_PHRASE_EXILE`, whose own trailing zone group is
#: a strict subset of this one's start, so this is tried first rather than
#: matching the exile half and silently dropping "and pay its mana cost".
_PHRASE_EXILE_AND_PAY_MANA_COST = re.compile(
    rf"^exile (?:this card|{count_pattern('count')} (?P<quality>[\w ]*?)cards?)"
    r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))? and pay "
    r"(?:its|their) mana cost$",
    re.IGNORECASE,
)
#: `quality`'s character class allows a comma so a disjunctive list -
#: "Sacrifice an artifact, creature, or land" (Greater Gargadon) - matches as
#: one phrase rather than being split by `_split_cost_phrase`'s own comma cut;
#: `_requirement` is what turns the list into a `CardRequirement` disjunction.
_PHRASE_SACRIFICE = re.compile(rf"^sacrifice {_COST_COUNT} (?P<quality>[\w ,]+)$", re.IGNORECASE)
#: `Discard a card`, `Discard a legendary card with the same name as a
#: legendary permanent you control` (Key to the Side-Door). The same-name tail
#: is a second demand on the *same* card - CR 201.2a's "at least one name in
#: common" against something the payer controls - not a second card to choose,
#: so it becomes a nested `CardRequirement` rather than another component.
_PHRASE_DISCARD = re.compile(
    rf"^discard {_COST_COUNT} (?P<quality>[\w ]*?)cards?"
    r"(?: with the same name as (?:a|an) (?P<same_name>[\w ]+?) you control)?$",
    re.IGNORECASE,
)
#: `Tap an untapped creature you control` (Swallow Whole's printed additional
#: cost, CR 118.8a). Distinct from the `{T}` symbol, which CR 107.5 defines as
#: "Tap this permanent" and never needs a choice made: this sentence names a
#: *quality*, so the permanent tapped is chosen at announcement (CR 601.2b) and
#: tapped as the total cost is paid (CR 601.2h). "untapped" is optional in the
#: wording because CR 107.5's "a permanent that's already tapped can't be
#: tapped again to pay the cost" is true whether or not the sentence says so -
#: `CostComponent._why_not_tap` enforces it either way.
_PHRASE_TAP = re.compile(
    rf"^tap {_COST_COUNT} (?:untapped )?(?P<quality>[\w ,]+?) you control$", re.IGNORECASE
)
#: `Collect evidence 6` (Detective's Phoenix's `Bestow-{R}, Collect evidence
#: 6.`) - CR 701.59a's keyword action used as a cost. Nothing is named to
#: choose: "any number of cards ... with total mana value N or greater" is a
#: threshold, not a count, so this carries only N.
_PHRASE_COLLECT_EVIDENCE = re.compile(
    rf"^collect evidence {count_pattern('amount', article=False)}$", re.IGNORECASE
)
#: `{Q}`, CR 107.6's untap symbol, which "in an activation cost means 'Untap
#: this permanent.'" Umbral Mantle's granted `{3}, {Q}:` is the pool's
#: printing. Read here rather than left to `ManaCost.parse` because it is not
#: mana at all - it is an action, exactly as `{T}` is (CR 107.5).
_PHRASE_UNTAP_SYMBOL = re.compile(r"^\{Q\}$", re.IGNORECASE)
#: `Mill a card` (Millikin's `{T}, Mill a card: Add {C}.`) - CR 701.17a's
#: keyword action used as a cost. Nothing is chosen: the cards come off the top
#: of the payer's own library, so this carries a count and no requirement.
_PHRASE_MILL = re.compile(rf"^mill {count_pattern('count')} cards?$", re.IGNORECASE)
#: `Waterbend {3}` (Flexible Waterbender) - CR 701.67a: "'Waterbend [cost]'
#: means 'Pay [cost]. For each generic mana in that cost, you may tap an
#: untapped artifact or creature you control rather than pay that mana.'" The
#: cost half is plain mana and is read here; the tapping half is CR 701.67b's
#: alternate payment method, which - like convoke (CR 702.51b) - applies only
#: after the total cost is determined, and so lives on an already-open
#: `CostPayment` in `machines/objects_as_costs.waterbend`, not here.
_PHRASE_WATERBEND = re.compile(r"^waterbend (?P<cost>(?:\{[^{}]+\})+)$", re.IGNORECASE)


def waterbend_mana_cost(phrase: str) -> ManaCost | None:
    """The mana a `Waterbend [cost]` phrase asks for, or None if that is not
    what this phrase is (CR 701.67a).

    Separate from `cost_component_for_phrase` because a waterbend cost is
    *mana*, and a `CostComponent` has nowhere to carry mana - `TotalCost` is
    the shape that does, which is why `total_cost_for_phrase` is where this is
    folded in.
    """
    match = _PHRASE_WATERBEND.match(phrase.strip().rstrip("."))
    if match is None:
        return None
    return ManaCost.parse(match.group("cost"))


#: `Exert this land`, `Exert this creature` (CR 701.43a). Only the self-
#: referential form, which is the only one printed inside a cost.
_PHRASE_EXERT_SELF = re.compile(
    r"^exert this (?:land|creature|permanent|artifact|enchantment)$", re.IGNORECASE
)
#: "Put a -1/-1 counter on this creature" (Devoted Druid) and "Remove a +1/+1
#: counter from this creature" (Walking Ballista) - CR 118.3, 122.1, 122.6.
#: Only the self-referential "this <type>" shape is read; a cost that names a
#: chosen target ("Remove a counter from target permanent") would need target
#: resolution this builder does not have, so it is left unmatched and the
#: caller fails closed (see `cost_component_for_phrase`'s docstring).
_COUNTER_SELF_SUBJECT = r"this (?:creature|permanent|artifact|enchantment|planeswalker|land)"
_PHRASE_PLACE_COUNTERS = re.compile(
    rf"^put {count_pattern('count')} (?P<kind>[\w+/−-]+) counters? on {_COUNTER_SELF_SUBJECT}$",
    re.IGNORECASE,
)
_PHRASE_REMOVE_COUNTERS = re.compile(
    rf"^remove {_COST_COUNT} (?P<kind>[\w+/−-]+) counters? from {_COUNTER_SELF_SUBJECT}$",
    re.IGNORECASE,
)


#: CR 701.68a's "Blight N" as a cost - "{1}{R}, {T}, Blight 1" (Sting-Slinger),
#: "blight X" (Soul Immolation, X already substituted when announced): N -1/-1
#: counters on a creature the payer controls, chosen as the cost is paid.
_PHRASE_BLIGHT = re.compile(
    rf"^blight {count_pattern('count', x=True, article=False)}$", re.IGNORECASE
)


def _cost_count(word: str) -> tuple[int, bool] | None:
    """An object cost's count as (the fewest that pays it, whether the payer
    decides the number), or None when `word` is not a count.

    A printed number is exact. CR 107.3a's X is announced as the cost is paid
    and may be 0. "One or more" is every object the payer chooses, at least
    one. The chosen number is filled in by `announce_count`.
    """
    quantity = parse_quantity(word)
    if quantity is None:
        return None
    if quantity.source is QuantitySource.X:
        return 0, True
    if quantity.source is QuantitySource.ONE_OR_MORE:
        return 1, True
    if quantity.source is QuantitySource.FIXED and quantity.amount is not None:
        return quantity.amount, False
    return None


def _counter_kind_word(word: str) -> str:
    """Normalise a counter kind read out of a cost sentence.

    `+1/+1` and `-1/-1` are kept exactly as `Counter` spells them (accepting
    the U+2212 minus Scryfall sometimes prints, same as `_LOYALTY_SYMBOL`);
    any named kind - "oil", "fate", "charge" - is lower-cased so it matches
    however else the engine already stores it (Gemstone Caverns's "luck" is
    lower-cased the same way in `machines/abilities.py`).
    """
    if re.fullmatch(r"[+−-]1/[+−-]1", word):
        return word.replace("−", "-")
    return word.lower()


#: Connector words a comma-and-"or" (or "and") list of card types leaves
#: between its items - "an artifact, creature, or land" - that name nothing
#: themselves and are skipped rather than treated as an unread word.
#:
#: "other" joins them for the same reason: CR 201.4's self-exclusion word,
#: printed on a cost that names a count of cards rather than "this card"
#: itself - Escape's own template (CR 702.138a), "Exile five **other** cards
#: from your graveyard" (Cling to Dust, Uro, Titan of Nature's Wrath). It adds
#: no restriction on *which* cards may pay: by the time this cost is paid, the
#: escaping card itself is on the stack (CR 601.2a moved it there before
#: CR 601.2h ever pays anything), not sitting in the graveyard pile this
#: exiles from, so "other" is satisfied by the zone alone and the word is
#: correctly a no-op rather than an unread one.
_QUALITY_CONNECTORS = {"or", "and", "other"}


def _requirement(quality: str) -> CardRequirement | None:
    """Turn `black`, `creature`, `Mountain`, or `artifact, creature, or land`
    into what the cards must be.

    `CardRequirement.types` (like `.colors` and `.subtypes`) is already a
    disjunction - "at least one of these" - so a comma-and-"or" list of card
    types (Greater Gargadon's "Sacrifice an artifact, creature, or land") is
    the same shape as a single type, just with more words: each word is
    stripped of the punctuation the list leaves on it and matched the same
    way, and a bare connector ("or", "and") names nothing and is skipped
    rather than failing the whole phrase.

    Unrecognised wording returns None, which the caller reads as "this phrase
    was not understood" rather than as "anything will do" - a cost that silently
    accepts the wrong card is worse than one that refuses to be built.
    """
    words = [word for word in quality.strip().split() if word]
    if not words:
        return CardRequirement(description=quality.strip())

    colors: list[Color] = []
    types: list[Type] = []
    subtypes: list[str] = []
    supertypes: list[Supertype] = []
    for raw_word in words:
        word = raw_word.strip(",")
        if not word:
            continue
        lowered = word.lower().rstrip("s")
        if lowered in _QUALITY_CONNECTORS:
            continue
        if lowered == "permanent":
            # CR 110.1 makes everything on the battlefield a permanent
            # already, so "permanent"/"permanents" names no card type at all
            # - the same "no restriction" reading `_controlled_requirement`
            # already gives it on same-name comparisons, needed here too for
            # a sacrifice cost with no type demand (Ward - Sacrifice three
            # permanents, CR 702.21a) rather than one word away from a
            # subtype (Greater Gargadon's "artifact, creature, or land" is
            # the demand-bearing shape; bare "permanents" is not).
            continue
        if lowered in _COLOR_WORDS:
            colors.append(_COLOR_WORDS[lowered])
        elif lowered in {supertype.value for supertype in Supertype}:
            # CR 205.4a's five supertypes. "A legendary card" is as much a
            # demand on what may pay as "a black card" is, and was previously
            # unread, which built no requirement at all and let anything pay.
            supertypes.append(Supertype(lowered))
        elif lowered in {type_.value for type_ in Type}:
            types.append(Type(lowered))
        elif word[:1].isupper():
            # A capitalised noun in a cost phrase is a subtype: `Sacrifice a
            # Mountain`, `Sacrifice a Goblin`.
            subtypes.append(word)
        else:
            return None
    return CardRequirement(
        colors=colors,
        types=types,
        subtypes=subtypes,
        supertypes=supertypes,
        description=quality.strip(),
    )


def _controlled_requirement(quality: str) -> CardRequirement | None:
    """`_requirement` for the *other* side of a same-name comparison: what the
    permanent on the battlefield has to be.

    Only one word differs in practice, and it is the noun: "a legendary
    permanent you control" says nothing about card types, because CR 110.1
    makes every object on the battlefield a permanent already. So `permanent`
    is read as "no type demand at all" here, where on the paying side - "a
    permanent card" in a hand - it would be a real demand and is deliberately
    not accepted.
    """
    words = [word for word in quality.split() if word.lower().rstrip("s") != "permanent"]
    if not words:
        return CardRequirement(description=quality.strip())
    requirement = _requirement(" ".join(words))
    if requirement is None:
        return None
    requirement.description = quality.strip()
    return requirement


def cost_component_for_phrase(phrase: str, payer: str | None = None) -> CostComponent | None:
    """Read one printed cost sentence into a payable `CostComponent`.

    This is what makes `Evoke—Exile a black card from your hand.` more than a
    string: CR 118.9 calls it an alternative cost, and an alternative cost has
    to be *paid*, which means knowing that it exiles one black card out of the
    caster's hand.

    Also reads "Put a -1/-1 counter on this creature" (Devoted Druid) and
    "Remove a +1/+1 counter from this creature" (Walking Ballista) - the
    templated counter-cost shapes CR 122.1/122.6 describe - but only the
    self-referential "this <type>" form; a phrase naming a chosen target
    ("Remove a counter from target permanent") is outside what this builder
    can resolve and returns None like any other unread shape.

    Returns None for a phrase it cannot read, so the caller can leave the
    keyword unexecuted rather than charge the wrong thing - `Game.activation_cost`
    turns that `None` into a raised refusal (CR 602.5) instead of silently
    skipping the cost, so an ability this cannot template is refused, never
    activated for free.
    """
    text = phrase.strip().rstrip(".")

    life = _PHRASE_PAY_LIFE.match(text)
    if life is not None:
        amount = parse_amount(life.group("amount"))
        if amount is None:
            return None
        if isinstance(amount, VariableX):
            # CR 118.3b: players can always pay 0 life, so 0 stands until the
            # X is announced (`Game.activation_cost`).
            return pay_life_cost(0, payer, description=text).model_copy(
                update={"variable_count": True}
            )
        return pay_life_cost(amount, payer, description=text)

    mill = _PHRASE_MILL.match(text)
    if mill is not None:
        count = parse_count(mill.group("count"))
        if count is None:
            return None
        return mill_cost(count, payer, description=text)

    evidence = _PHRASE_COLLECT_EVIDENCE.match(text)
    if evidence is not None:
        amount = parse_count(evidence.group("amount"), article=False)
        if amount is None:
            return None
        return collect_evidence_cost(amount, payer, description=text)

    if _PHRASE_UNTAP_SYMBOL.match(text):
        # CR 107.6's "Untap this permanent": the permanent is the one whose
        # ability this is, and only the caller knows which that is, so the
        # component is built empty and correctly refuses to be paid until the
        # card is filled in (CR 118.3) - same as `_PHRASE_EXERT_SELF` below.
        return untap_cost(payer=payer, description=text)

    if _PHRASE_EXERT_SELF.match(text):
        # The permanent exerted is the one whose ability this is, and only the
        # caller knows which that is, so the component is built empty and
        # correctly refuses to be paid until the card is filled in (CR 118.3).
        return exert_cost(payer=payer, required=1, description=text)

    place = _PHRASE_PLACE_COUNTERS.match(text)
    if place is not None:
        count = parse_count(place.group("count"))
        if count is None:
            return None
        kind = _counter_kind_word(place.group("kind"))
        return place_counters_cost(None, count, counter_kind=kind, payer=payer, description=text)

    remove_counters = _PHRASE_REMOVE_COUNTERS.match(text)
    if remove_counters is not None:
        read = _cost_count(remove_counters.group("count"))
        if read is None or (read[1] and read[0]):
            # "Remove one or more counters" has no announced number to remove.
            return None
        count, variable = read
        kind = _counter_kind_word(remove_counters.group("kind"))
        component = remove_counters_cost(
            None, count, counter_kind=kind, payer=payer, description=text
        )
        component.variable_count = variable
        return component

    blight = _PHRASE_BLIGHT.match(text)
    if blight is not None:
        amount = parse_amount(blight.group("count"))
        if amount is None:
            return None
        variable = isinstance(amount, VariableX)
        component = place_counters_cost(
            None,
            0 if variable else amount,
            counter_kind=_counter_kind_word("-1/-1"),
            payer=payer,
            description=text,
        )
        # CR 701.68a: "a creature you control" - the control half is
        # `_why_not_controlled`, the creature half this requirement.
        component.requirement = _requirement("creature")
        component.variable_count = variable
        return component

    reveal = _PHRASE_REVEAL.match(text)
    if reveal is not None:
        reveal_requirement = _requirement(reveal.group("quality"))
        if reveal_requirement is None:
            return None
        if reveal.group("count").lower() == "x":
            component = reveal_cost(payer=payer, required=0, description=text, variable_count=True)
        else:
            reveal_count = parse_count(reveal.group("count"))
            if reveal_count is None:
                return None
            component = reveal_cost(payer=payer, required=reveal_count, description=text)
        component.requirement = reveal_requirement
        return component

    behold = _PHRASE_BEHOLD.match(text)
    if behold is not None:
        behold_requirement = _requirement(behold.group("quality"))
        if behold_requirement is None:
            return None
        component = behold_cost(payer=payer, required=1, description=text)
        component.requirement = behold_requirement
        return component

    exile_and_pay = _PHRASE_EXILE_AND_PAY_MANA_COST.match(text)
    if exile_and_pay is not None:
        zone = _ZONE_WORDS.get((exile_and_pay.group("zone") or "graveyard").lower(), Zone.GRAVEYARD)
        count = parse_count(exile_and_pay.group("count"))
        requirement = _requirement(exile_and_pay.group("quality") or "")
        if count is None or requirement is None:
            return None
        return exile_and_pay_mana_cost_cost(
            payer=payer, required=count, description=text, zone=zone, requirement=requirement
        )

    exile = _PHRASE_EXILE.match(text)
    if exile is not None:
        zone = _ZONE_WORDS.get((exile.group("zone") or "hand").lower(), Zone.HAND)
        if exile.group("count") is None and exile.group("another") is None:
            # "Exile this card [from your graveyard]": CR 700.7's self-
            # reference, so there is nothing to choose - only the caller
            # knows which permanent this is, same as `_PHRASE_EXERT_SELF`.
            return exile_cost(payer=payer, required=1, description=text, zone=zone)
        if exile.group("another") is not None:
            # "Exile another <quality> card": CR 601.2c/113.6's "another" -
            # a plain, implicit one, excluding the ability's own source
            # (`Game.activation_cost` fills in which permanent that is).
            requirement = _requirement(exile.group("quality"))
            if requirement is None:
                return None
            requirement.excludes_source = True
            component = exile_cost(payer=payer, required=1, description=text, zone=zone)
            component.requirement = requirement
            return component
        read = _cost_count(exile.group("count"))
        requirement = _requirement(exile.group("quality"))
        if read is None or requirement is None:
            return None
        if exile.group("mana_value") is not None:
            requirement.mana_value = int(exile.group("mana_value"))
        component = exile_cost(payer=payer, required=read[0], description=text, zone=zone)
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    discard = _PHRASE_DISCARD.match(text)
    if discard is not None:
        read = _cost_count(discard.group("count"))
        requirement = _requirement(discard.group("quality"))
        if read is None or requirement is None:
            return None
        if discard.group("same_name") is not None:
            same_name = _controlled_requirement(discard.group("same_name"))
            if same_name is None:
                return None
            requirement.same_name_as = same_name
        component = discard_cost(payer=payer, required=read[0], description=text)
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    sacrifice = _PHRASE_SACRIFICE.match(text)
    if sacrifice is not None:
        read = _cost_count(sacrifice.group("count"))
        requirement = _requirement(sacrifice.group("quality"))
        if read is None or requirement is None:
            return None
        component = sacrifice_cost(payer=payer, required=read[0], description=text)
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    tap = _PHRASE_TAP.match(text)
    if tap is not None:
        read = _cost_count(tap.group("count"))
        requirement = _requirement(tap.group("quality"))
        if read is None or requirement is None:
            return None
        component = tap_cost(payer=payer, description=text)
        component.required = read[0]
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    return None


def total_cost_for_phrase(phrase: str, payer: str | None = None) -> TotalCost | None:
    """A whole printed cost, mana or otherwise, as a `TotalCost`.

    `Flashback {2}{R}` is mana; `Evoke—Exile a black card from your hand.` is a
    component; a comma-separated phrase can be both.

    `Waterbend {3}` is mana too, spelled with an action word in front of it
    (CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. ...'"). The permission
    that word carries - tapping an untapped artifact or creature for each
    generic mana - is CR 701.67b's alternate payment method and belongs to an
    open `CostPayment`, not to the total cost, exactly as CR 702.51b puts
    convoke after the cost is determined.
    """
    mana = ManaCost()
    components: list[CostComponent] = []
    waterbend_generic: int | None = None
    for part in _split_cost_phrase(phrase):
        if _ONLY_MANA.match(part) and not _ACTION_SYMBOL.match(part):
            mana = mana.plus(ManaCost.parse(part))
            continue
        waterbend = waterbend_mana_cost(part)
        if waterbend is not None:
            mana = mana.plus(waterbend)
            # CR 701.67b's own bound: only *this* piece's generic, not the
            # whole phrase's - a second, plain-mana piece in the same
            # comma-separated cost (none printed yet, but CR 602.1a allows
            # it) must not widen what the tap method may cover.
            waterbend_generic = (waterbend_generic or 0) + waterbend.generic
            continue
        component = cost_component_for_phrase(part, payer)
        if component is None:
            return None
        components.append(component)
    return TotalCost(mana=mana, components=components, waterbend_generic=waterbend_generic)


_ONLY_MANA = re.compile(r"^(?:\{[^{}]+\}|\s)+$")

#: The two brace-wrapped symbols that are *not* mana: CR 107.5's tap symbol
#: `{T}` and CR 107.6's untap symbol `{Q}`, each of which "in an activation
#: cost means" an action rather than a payment from the mana pool. They match
#: `_ONLY_MANA`'s shape and would otherwise be handed to `ManaCost.parse`,
#: which rightly refuses them - so `total_cost_for_phrase` checks this first
#: and lets `cost_component_for_phrase` read them as the actions they are.
_ACTION_SYMBOL = re.compile(r"^\s*\{[TQ]\}\s*$", re.IGNORECASE)


#: Splits a printed cost on its commas, or on a joining "and" with no comma at
#: all - "pay 1 life and exile a blue card from your hand" (Force of Will's
#: pitch cost) never has one. A run of mana symbols never contains the word
#: "and", so this never cuts one of those in half.
_COST_PHRASE_SEPARATOR = re.compile(r",\s*|\s+and\s+")


def _split_cost_phrase(phrase: str) -> list[str]:
    """Split a printed cost into its components, keeping mana symbols whole."""
    parts = _COST_PHRASE_SEPARATOR.split(phrase.strip().rstrip("."))
    return [part.strip() for part in parts if part.strip()]


# --------------------------------------------------------------------------
# The payment machine
# --------------------------------------------------------------------------


#: `tap_for_mana`'s default: work the restriction out from the card rather than
#: from the caller. Distinct from `None`, which is a caller positively saying
#: "this mana carries no restriction".
INFER_RESTRICTION: Any = object()


def restriction_for_production(
    source: CardState, produces: Sequence[Color], game: Any = None
) -> ManaRestriction | None:
    """The CR 106.6 restriction on mana a manual `tap_for_mana(source, produces)`
    just made, worked out from which of `source`'s `{T}`-only abilities could
    have produced exactly that.

    Every printing in this pool that carries a restriction prints an
    unrestricted ability beside it, and the two always differ in what they add:
    Eldrazi Temple's `{C}` against its `{C}{C}`, Cavern of Souls's and
    Delighted Halfling's `{C}` against their one mana of any colour. So
    matching on the actual production names one ability and there is nothing to
    guess at.

    When more than one ability could have produced it, the **unrestricted**
    reading wins. A caller on this path named the mana itself, and narrowing
    what it may pay for on a guess would refuse plays the rules allow - the
    opposite failure from letting restricted mana pay for anything, and the
    only one available here, since the caller has already been given the mana.
    A caller that knows which ability it activated passes the restriction
    explicitly and none of this runs.

    `game` is `_activations_of`'s CR 613.5 parameter again: the abilities asked
    are the permanent's *computed* ones, so a copy's restriction (or its lack of
    one) is the one read, never the printed card's.
    """
    wanted = sorted(produces)
    matches = [
        spend_restriction(activation.effect)
        for _index, activation in tappable_mana_activations(source, game)
        if activation.mana is not None
        for option in activation.mana.effective()[0]
        if sorted(option) == wanted
    ]
    if not matches or any(restriction is None for restriction in matches):
        return None
    return spend_restriction(matches[0].text, source)


class _ActivatedMana(NamedTuple):
    """Which of a permanent's mana abilities a `tap_for_mana` is activating.

    `index` is the position `Game.activated_abilities`/`Game.activate_ability`
    know that ability by, or `None` when the ability came from somewhere with
    no printed activated ability behind it (`_activation_behind`'s own miss -
    an intrinsic ability granted with a basic land type in layer 4, which
    nothing enumerates as an activation).
    """

    index: int | None
    ability: ManaAbility


def _activated_mana_ability(
    context: "CostPayment | _SpendContext",
    source: CardState,
    produces: Sequence[Color],
    restriction: Any = INFER_RESTRICTION,
) -> tuple[_ActivatedMana | None, list[str]]:
    """Which of `source`'s mana abilities a tap that adds `produces` counts as
    having activated, and the CR 602.5 refusals collected along the way.

    Pure: reads the computed board and nothing else, taps nothing, and takes a
    `_SpendContext` as happily as a live `CostPayment`. That is what lets the
    two callers share it - `_tap_for_mana_impl`, which then executes the tap,
    and `mana_ability_index`, which only wants to *report* which ability a
    planned tap would activate. Splitting it out is the same argument
    `_solve_auto_tap_flow` makes for splitting the search out of `auto_tap`:
    the reported ability and the activated one are one answer, so there is no
    second copy of the matching to disagree with the first.

    Both of CR 106.6's tags (the spend restriction and the additional-effect
    sentence) are read off the one ability this returns, so they can never
    come from two different abilities of the same permanent.

    `restriction` is `INFER_RESTRICTION` when the caller did not say which
    restriction the mana carries. Named, it outranks "the production happened
    to match" wherever the two could differ.

    Raises `ValueError` when `source` has no `{T}` mana ability at all on the
    face that is up - a fact about the permanent, identical for both callers.
    Returns `(None, refusals)` when it has one but none of them offers
    `produces`.
    """
    # Printed abilities plus `CardState.granted_ability_texts`'s own -
    # Urza's Saga chapter I's own "This Saga gains '{T}: Add {C}.'" is
    # what makes this second half necessary; see `granted_mana_
    # abilities`'s own docstring.
    game = context.game
    activations = _activations_of(source, game)
    rewritten = (rewritten_ability_lines(game, source) if game is not None else None) is not None
    if rewritten:
        # CR 613.5 / CR 707.2: the computed text is the only text this
        # permanent has, so the printed card is not consulted at all - the
        # `{T}` filter `parse_mana_abilities` applies is applied to the
        # copied lines instead. See `_activations_of`.
        abilities = [
            activation.mana
            for activation in activations
            if activation.mana is not None
            and any(piece.kind is CostKind.TAP for piece in activation.costs)
        ]
    else:
        # Plus the intrinsic mana ability that came with a basic land type
        # granted in layer 4 (CR 305.6, CR 613.1d) - Urborg's Swamp,
        # Yavimaya's Forest, Dryad's all five. Without it the type showed on
        # the computed board and the land still refused to be tapped for it.
        added = added_ability_lines(game, source) if game is not None else ()
        abilities = (
            parse_mana_abilities(source.card, source.up_face_name)
            + granted_mana_abilities(source.granted_ability_texts)
            + granted_mana_abilities(added)
        )
    if not abilities:
        raise ValueError(
            f"{source.name} has no {{T}} mana ability on the face that is up "
            "and cannot be tapped for mana"
        )
    land_types, own_counters, has_imprinted_card = _mana_context(context, source)
    refusals: list[str] = []
    # The ability this tap is treated as having activated - the first one
    # that offers `produces`, unless the caller named which restriction the
    # mana carries and a *later* one is the ability carrying it.
    activated: _ActivatedMana | None = None
    named_restriction = restriction is not INFER_RESTRICTION
    for ability in abilities:
        behind = _activation_behind(activations, ability)
        effect = behind[1].effect if behind is not None else ""
        if behind is not None and [piece.kind for piece in behind[1].costs] == [CostKind.TAP]:
            # CR 602.5, asked of the ability actually being activated: a
            # prohibited activation is refused however the source was
            # chosen. Only a bare-`{T}` ability is asked, because that is
            # the only shape this path claims to be activating in full -
            # anything with a further cost was never paid for here.
            refused = _activation_refused(context, source, behind[0])
            if refused is not None:
                refusals.append(refused)
                continue
        # `any_color` is carried through rather than dropped: it is what
        # tells "N mana in any combination of colors" apart from a choice
        # between printed options, and `ManaAbility.offers` needs it to
        # know that a genuine mixture - `{G}{W}` out of Smokebraider - is a
        # production the printing names. Enumerating the mixtures instead
        # would be `combinations_with_replacement` over five colours, which
        # is 126 entries at five mana and unbounded for a count the board
        # decides; see that method.
        offered, any_color = ability.effective(
            land_types,
            own_counters,
            has_imprinted_card,
            **_mana_narrowings(context, source, ability),
        )
        options, any_color = _narrow_to_defined_colors(
            offered, any_color, _among_colors(effect, context, source)
        )
        if ability.offers(list(produces), options, any_color):
            match = _ActivatedMana(behind[0] if behind is not None else None, ability)
            if activated is None:
                activated = match
            # A caller that named the restriction named the ability with
            # it. Every printing in this pool that has two mana abilities
            # has two *different* productions on them, so the first match
            # is already the named one and this never has a second
            # candidate to prefer - but "the caller told us" outranks "the
            # production happened to match" wherever the two could differ,
            # and reading one tag from the caller and the other from a
            # guess is how they would come to disagree.
            if not named_restriction or spend_restriction(effect, source) == restriction:
                activated = match
                break
    return activated, refusals


def _activated_mana_ability_with_triggers(
    context: "CostPayment | _SpendContext",
    source: CardState,
    produces: Sequence[Color],
    restriction: Any = INFER_RESTRICTION,
) -> tuple["_ActivatedMana | None", list[str], list[Color], list[Color]]:
    """`_activated_mana_ability`, also accepting a production that lists the
    mana the tap's triggered mana abilities add after the ability's own
    (CR 605.4a) - what a `TapPlan` entry reports and what a caller pinning a
    source may name. Returns `(activated, refusals, the ability's own mana,
    the triggered mana)`.
    """
    activated, refusals = _activated_mana_ability(context, source, produces, restriction)
    wanted = list(produces)
    if activated is not None or context.game is None or len(wanted) < 2:
        return activated, refusals, wanted, []
    trigger_sources = mana_trigger_sources(context.game)
    if not trigger_sources:
        return activated, refusals, wanted, []
    for cut in range(len(wanted) - 1, 0, -1):
        own, extra = wanted[:cut], wanted[cut:]
        candidate, _ = _activated_mana_ability(context, source, own, restriction)
        if candidate is None:
            continue
        bonuses = triggered_mana_bonus(context, source, own, trigger_sources)
        if sorted(extra) in (sorted(bonus) for bonus in bonuses):
            return candidate, refusals, own, extra
    return activated, refusals, wanted, []


def mana_ability_index(
    source: CardState,
    produces: Sequence[Color],
    restriction: ManaRestriction | None,
    *,
    game: Any = None,
    payer: str | None = None,
    candidate_scan: list[_ScannedCandidate] | None = None,
) -> int | None:
    """Which of `source`'s abilities `Game.activate_ability` would be told to
    use for one entry of a `TapPlan` - the index `Game.activated_abilities`
    knows it by (CR 605.1a), or `None` when nothing enumerable is behind it.

    This is the reporting half of `plan_mana_payment`: a plan entry says
    *which permanent* and *what it adds*, and this says *which of its
    abilities does that*, which is the difference between Cavern of Souls's
    free `{C}` (index 0) and its CR 106.6-restricted mana of any colour
    (index 1).

    `candidate_scan` is the fast path, and the one `machines/legal_actions`
    always takes: every plan entry was built out of exactly one of that scan's
    rows, so the row whose source, restriction and offered options match this
    entry *is* the ability the solver chose, read back for free. Without it -
    or on a miss, which a scan hoisted over a wider board than the plan was
    solved from could produce - the question is put to
    `_activated_mana_ability`, the same function `tap_for_mana` uses to decide
    which ability a tap activates. That survey costs a board read per entry,
    which is why the enumeration hands its scan down rather than paying it
    once per action.

    `None` rather than a raise when nothing matches: this is a report, and a
    plan entry that cannot be attributed to a printed ability is still a true
    statement about which permanent gets tapped and what it adds.
    """
    wanted = list(produces)
    if candidate_scan is not None:
        for scanned, options, scanned_restriction, _any, index in candidate_scan:
            if scanned.id == source.id and scanned_restriction == restriction and wanted in options:
                return index
    context = _SpendContext(game=game, payer=payer, spend=None)
    try:
        activated, _refusals, _own, _triggered = _activated_mana_ability_with_triggers(
            context, source, wanted, restriction
        )
    except ValueError:
        return None
    return activated.index if activated is not None else None


def _copy_pool(pool: ManaPool) -> ManaPool:
    """A detached copy of a pool, restrictions included (CR 106.6).

    A payment works on a copy so a cancellation throws away only what the
    payment itself produced; the copy has to carry the CR 106.6 tags too, or
    restricted mana the player already had would silently become spendable on
    anything the moment a payment opened. Both of CR 106.6's tags travel: the
    spend *effect* on the copy is what tells the settled `ManaPayment` which
    of the mana it spent carried an additional effect on the spell.
    """
    return ManaPool(
        floating=dict(pool.floating),
        snow=dict(pool.snow),
        restricted=[entry.model_copy(deep=True) for entry in pool.restricted],
        spend_effects=[tagged.model_copy(deep=True) for tagged in pool.spend_effects],
        retained=[entry.model_copy(deep=True) for entry in pool.retained],
    )


class CostSubstitution(EngineModel):
    """One object standing in for one mana symbol of a total cost.

    The shared shape behind convoke (CR 702.51a) and delve (CR 702.66a), and
    the reason they are one subsystem rather than two special cases: both are
    static abilities that function while the spell is on the stack, both apply
    only *after* the total cost has been determined (CR 702.51b, CR 702.66b),
    and both say the same thing about one symbol - "you may [do something to an
    object] **rather than pay that mana**".

    So a substitution is not mana, not a cost reduction, and not an alternative
    cost. It is a symbol of the already-determined cost that will be paid by
    `component` (a tap, an exile) instead of out of the pool. `option` is which
    symbol it covers - `PaymentOption(generic=1)` for a generic one, or
    `PaymentOption(color=...)` for a coloured one, which is exactly the split
    CR 702.51a draws between "for each colored mana in this spell's total cost"
    and its generic half.

    `component` is an ordinary `CostComponent`, so the tapping or exiling is
    paid by `CostPayment.pay` alongside every other component and is undone by
    `cancel`/`rewind` through the same CR 733.1 reversal. Nothing about
    substitution needs its own undo path.

    Who may be substituted, and what they may cover, is not decided here -
    `machines/objects_as_costs.py` holds the eligibility rules each keyword
    prints. This module only knows that a symbol can be paid by an object.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    keyword: str
    """What offered it - "convoke", "delve" - for the refusal messages."""

    rule: str
    """The CR number that keyword expands to, quoted in refusals."""

    card_id: UUID
    card_name: str
    """The id and name of the object paying this symbol, kept as plain data
    rather than the `CardState` itself - `component.cards` next door already
    holds the same object for the actual tap or exile, so a `card: CardState`
    field here was a second, redundant reference to it, dumping a whole extra
    copy of the same permanent on every serialization for no reader that
    needed more than its id and name (`__str__`'s message, and `entry.card.id`
    in `machines/objects_as_costs.py`'s own-object check)."""
    option: PaymentOption
    component: CostComponent

    def __str__(self) -> str:
        return f"{self.card_name} pays {self.option} ({self.keyword}, {self.rule})"


def cost_less(cost: ManaCost, options: Iterable[PaymentOption]) -> ManaCost:
    """`cost` with the symbols `options` cover taken out of it.

    Not `ManaCost.minus`, which is a cost *reduction* - this is the arithmetic
    of "that mana is not paid because an object paid it instead", and the
    difference matters for the messages and for what `converted` a caller sees.
    A generic option eats one point off a generic symbol (`{7}` becomes `{6}`,
    and disappears at zero); a coloured option removes one symbol of that
    colour.

    Symbols nothing covers are left exactly where they were, in printed order,
    so what remains still reads as a real cost.
    """
    generic = sum(option.generic for option in options)
    colored: dict[Color, int] = {}
    for option in options:
        if option.color is not None:
            colored[option.color] = colored.get(option.color, 0) + 1

    remaining: list[ManaSymbol] = []
    for symbol in cost.symbols:
        if symbol.kind is SymbolKind.GENERIC and generic:
            taken = min(generic, symbol.amount)
            generic -= taken
            if symbol.amount - taken:
                remaining.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=symbol.amount - taken))
            continue
        if symbol.kind is SymbolKind.COLORED and colored.get(symbol.colors[0], 0):
            colored[symbol.colors[0]] -= 1
            continue
        remaining.append(symbol)
    return ManaCost(symbols=tuple(remaining))


class CostPayment(EngineModel):
    """Paying one total cost, from tapping sources through to the leftover mana."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cost: ManaCost
    components: list[CostComponent] = Field(default_factory=list)
    game: Any = Field(default=None, exclude=True, repr=False)
    payer: str | None = None
    pool: ManaPool = Field(default_factory=ManaPool)
    step: CostStep = CostStep.PENDING
    tapped_for_mana: list[UUID] = Field(default_factory=list)
    """The ids of the sources this payment's own `tap_for_mana` calls tapped,
    matching `triggers_caused` below rather than holding the `CardState`s
    themselves. It used to be `list[CardState]`, which round-tripped as a full
    second copy of every tapped permanent (`Game.find_by_id`, `game.battlefield`
    and this list each dumping their own `CardState` with the same id) - and
    once `AbilityOnStack.keyword_activation`/`.unless_payment` could survive a
    round trip at all, `_undo_everything` untapping those decoded copies
    directly left the real battlefield sources tapped forever with no error,
    the identical shape `_equip_effect`/`_crew_effect` had for `activation.
    card`. `_undo_everything` re-resolves each id through `game.find_by_id`
    now; `_tapped_sources` below is the only place a live object is still kept,
    and only for the no-`game` path."""
    overflow: ManaPool | None = None

    triggers_caused: list[UUID] = Field(default_factory=list)
    """CR 106.12a triggers this payment's own `tap_for_mana` calls have queued
    on `Game.pending_triggers` (or, if a priority check already ran, pushed
    onto `Game.stack`) - Utopia Sprawl, Leyline of Abundance, Badgermole Cub,
    and anything else sharing that trigger shape.

    CR 733.1: "If a player takes an illegal action or starts to take an
    action but can't legally complete it, the entire action is reversed and
    any payments already made are canceled. No abilities trigger and no
    effects are applied due to any part of the illegal action." `cancel`/
    `rewind` already untap `tapped_for_mana` and empty the pool - this is the
    same reversal applied to what tapping those sources queued. Without it, a
    payment tried, found unpayable, and cancelled left its trigger behind:
    each retried combination queued one more, and every one of them still
    resolved once payment finally succeeded, multiplying the bonus mana by
    however many attempts were cancelled along the way."""

    components_before_mana: bool = False
    """CR 601.2h: "The player pays the total cost. First, they pay all costs
    that don't involve random elements or moving objects from the library to a
    public zone, **in any order**."

    The order is the payer's, and it is observable: Momentous Fall sacrificing
    Omnath, Locus of Mana ("gets +1/+1 for each unspent green mana you have")
    reads a 5/5 if the sacrifice is paid while the four green mana is still
    floating and a 1/1 if the mana is spent first (DDR#955). This flag is that
    choice. It defaults to False - mana first, the order this engine has always
    used - so nothing that does not ask for it changes.

    It does not reorder the *second* half of CR 601.2h. A mill component moves
    objects from a library to a public zone, so it is paid after everything
    else whichever way this flag is set.
    """

    choices: list[int | None] | None = None
    """CR 118.13a: one pinned option per symbol of `cost`, or None to leave the
    choice to the engine. Set it to insist that Dismember's `{B/P}` is paid
    with black mana rather than with life."""

    substitutions: list[CostSubstitution] = Field(default_factory=list)
    """Symbols of `cost` that an object is paying instead of the pool.

    Convoke's creatures (CR 702.51a) and delve's exiled cards (CR 702.66a) land
    here. `mana_owed` is `cost` with them taken out, and that - not `cost` - is
    what the pool is asked to cover."""

    waterbend_generic: int | None = None
    """`TotalCost.waterbend_generic`, carried over by `for_total` - CR
    701.67b's own bound on how much of `cost`'s generic the waterbend tap
    method (`machines/objects_as_costs.waterbend`) may cover, distinct from
    `cost`'s own generic total whenever the total cost also has other
    generic mana in it. `None` when this payment has no waterbend cost, or
    when nothing distinguishes the waterbend's own generic from the rest
    (every printing in the pool today) - `waterbend` then bounds itself by
    `cost` alone, exactly as convoke and delve already do."""

    mana_payment: ManaPayment | None = None
    """How the mana part was settled, once it has been (CR 118.13)."""

    spend: ManaSpend | None = None
    """What this cost belongs to - the spell being cast, or the source of the
    ability being activated - so mana carrying a CR 106.6 spend restriction can
    be judged against it.

    `None` says the caller could not name it, and that refuses restricted mana
    outright: the engine cannot show the restriction was honoured, so it does
    not spend the mana. A payment left unnamed is therefore payable exactly
    with the unrestricted mana available to it, which is what the engine did
    everywhere before restrictions existed."""

    _planning: bool = PrivateAttr(default=False)
    _preexisting: ManaPool | None = PrivateAttr(default=None)
    """The payer's floating mana as it stood when the payment opened, so a
    rewind (CR 733.1) can put it back after `pay` spent part of it.

    A `PrivateAttr`, so it does not survive a dump/decode round trip -
    `_restore_payer_pool` refuses loudly rather than silently restoring
    nothing when that matters (see its own docstring)."""

    _tapped_sources: dict[UUID, CardState] = PrivateAttr(default_factory=dict)
    """The live objects behind `tapped_for_mana`'s ids, for the one case that
    still needs them by reference: a `CostPayment` used with no `game` at all
    (a unit test tapping a bare `CardState` directly). `_undo_everything`
    resolves through `game.find_by_id` whenever there is a game; this is only
    the fallback for when there is none to ask. A `PrivateAttr` here is safe -
    unlike `_preexisting` and `CostComponent._undo` - because a payment with no
    `game` was never attached to one to be serialized as part of in the first
    place."""

    @classmethod
    def for_total(
        cls,
        total: TotalCost,
        game: Any = None,
        payer: str | None = None,
        spend: ManaSpend | None = None,
    ) -> "CostPayment":
        """Open a payment for a composite cost.

        `payer` is who is paying. It is what makes a Phyrexian symbol payable
        with life, since the life has to come from a real life total, and it
        falls back to whoever the components already name.

        `spend` is what the cost is for (CR 106.6), so restricted mana already
        floating in the payer's pool can be judged against it. Omitted, no
        restricted mana is spendable by this payment.

        The payment's pool opens as a copy of that player's floating mana, so
        mana already in their pool can pay this cost (see `_seed_payer_pool`).
        """
        components = list(total.components)
        if payer is None:
            payer = next((c.payer for c in components if c.payer is not None), None)
        payment = cls(
            cost=total.mana,
            components=components,
            game=game,
            payer=payer,
            spend=spend,
            waterbend_generic=total.waterbend_generic,
        )
        payment._seed_payer_pool()
        return payment

    @property
    def total_cost(self) -> TotalCost:
        return TotalCost(mana=self.cost, components=self.components)

    @property
    def mana_owed(self) -> ManaCost:
        """The part of `cost` the mana pool still has to cover.

        `cost` stays the total cost CR 601.2f determined - convoke and delve
        are explicitly *not* cost reductions (CR 702.51b, CR 702.66b), so
        anything asking what this spell cost gets the real number. What each
        substitution changes is only which resource pays one symbol, and that
        is this property.
        """
        if not self.substitutions:
            return self.cost
        return cost_less(self.cost, [entry.option for entry in self.substitutions])

    def substitute(
        self,
        *,
        keyword: str,
        rule: str,
        card: CardState,
        option: PaymentOption,
        component: CostComponent,
    ) -> CostSubstitution:
        """Pay one symbol of `cost` with an object rather than with mana.

        The general form of convoke (CR 702.51a) and delve (CR 702.66a). The
        caller has already decided that `card` is eligible and which symbol it
        covers; what is checked here is the arithmetic CR 702.51a and CR 702.66a
        both bound themselves by - "for each [colored|generic] mana **in this
        spell's total cost**". A symbol that is not there, or is already
        covered by an earlier substitution, cannot be paid a second time, so an
        offer beyond what the cost holds is refused rather than silently
        wasted.

        `component` joins `components`, so the tap or exile happens in
        CR 601.2h's payment step with everything else and is reversed with it
        (CR 733.1). Nothing is tapped or exiled at the moment this is called.
        """
        self._require_open()
        if self.choices is not None:
            # `choose` pins one option per symbol of the cost that is left to
            # pay; a substitution changes that list underneath it. Rather than
            # silently re-index someone's pinned hybrid choice, refuse.
            raise ValueError(
                "cannot substitute an object for a symbol after the payment's "
                "symbol choices have been pinned (CR 118.13a) - substitute first"
            )
        owed = self.mana_owed
        if cost_less(owed, [option]) == owed:
            for_what = self.spend.name if self.spend is not None else "this cost"
            raise ValueError(
                f"{card.name} cannot pay {option} for {for_what}: {owed or '{0}'} "
                f"has no {option} left to pay ({keyword}, {rule})"
            )
        entry = CostSubstitution(
            keyword=keyword,
            rule=rule,
            card_id=card.id,
            card_name=card.name,
            option=option,
            component=component,
        )
        self.substitutions.append(entry)
        self.components.append(component)
        return entry

    @property
    def is_settled(self) -> bool:
        return self.step in {CostStep.PAID, CostStep.CANCELLED}

    @property
    def life_available(self) -> int:
        """What the payer may put towards a Phyrexian symbol (CR 107.4f, 119.4).

        Their whole life total: CR 119.4 lets life be paid down to zero, and
        losing the game for it is a state-based action afterwards, not a reason
        the cost could not be paid. A total already below zero - a mana
        ability's CR 405.6c damage taken while this payment is open - is 0 to
        spend, not a negative budget: CR 119.4b, "Players can always pay 0
        life".
        """
        if self.game is None or self.payer is None:
            return 0
        try:
            return max(int(self.game.player(self.payer).life), 0)
        except (KeyError, ValueError, AttributeError):
            return 0

    @property
    def shortfall(self) -> bool:
        """True if the pool still cannot cover the mana part of the cost."""
        return not self.pool.can_pay(
            self.mana_owed, life_available=self.life_available, spend=self.spend
        )

    @property
    def unpayable(self) -> str | None:
        """Why the non-mana components cannot be paid, or None (CR 118.3)."""
        for component in self.components:
            reason = component.why_not(self.game)
            if reason is not None:
                return reason
        return None

    def choose(self, choices: list[int | None]) -> "CostPayment":
        """Pin how each symbol of the cost is paid (CR 118.13a)."""
        owed = self.mana_owed
        if len(choices) != len(owed.symbols):
            raise ValueError(f"expected {len(owed.symbols)} choices, got {len(choices)}")
        self.choices = list(choices)
        return self

    def tap_for_mana(
        self,
        source: CardState,
        produces: list[Color],
        restriction: ManaRestriction | None = INFER_RESTRICTION,
    ) -> ManaPool:
        """Tap a permanent for mana and put what it makes into the pool.

        `produces` is what this activation makes, so a dual land is called with
        the single colour chosen, not with everything it could make.

        `restriction` is the CR 106.6 tag the produced mana carries. Left at
        its default it is worked out from `produces` by
        `restriction_for_production`, so a caller that hand-picks its mana
        sources - a scenario tapping a Cavern of Souls for a colour, the
        harness's `pay_with` - gets the restriction enforced without having to
        know it exists. Passing it explicitly (`None` included) overrides that;
        `auto_tap` does, because it knows exactly which ability it chose.

        The tag goes onto the mana, not onto `source`: once the mana ability
        has resolved (CR 605.3b) the source has nothing more to do with it, and
        the mana keeps the restriction after the source has left the
        battlefield.

        A creature that has not been under its controller's control since their
        most recent turn began cannot be tapped for mana (CR 302.6, 602.5a)
        unless it has haste (CR 702.10c); see `can_tap_for_mana`.

        The ability's own restrictions are checked here too, because a
        hand-picked source is still an activation (CR 605.3a) and CR 602.5
        does not care who chose it: an ability prohibited from being activated
        - Mox Opal's metalcraft with two artifacts out - is refused, and so is
        a colour CR 106.5 leaves undefined, Mox Amber's "among legendary
        creatures and planeswalkers you control" with none of either. Both are
        the same questions `_auto_tap_candidates` asks on the automatic path;
        neither was asked on any path before.

        **CR 613.5 / CR 707.2**: which abilities `source` has is asked of the
        layer engine through `_activations_of`, not of the printed `Card`. A
        Forest that has become a copy of Sol Ring is tapped for `{C}{C}` here
        and refuses `{G}`, the same answer `Game.activated_abilities` gives when
        the copy's ability is activated directly.

        Mana from a snow permanent (CR 205.4g) is marked as such, because `{S}`
        can only be paid with mana produced by a snow source (CR 107.4h, 106.3).

        CR 106.12a: an ability that triggers "whenever a permanent is tapped
        for mana" triggers when this mana ability resolves and produces mana -
        emitted here, the only place the engine taps a permanent for mana.

        `source` is validated here, not trusted from the caller: this is the
        one place a caller with an explicit, hand-picked source list (a
        scenario's `pay_with`, a player choosing their own sources instead of
        `auto_tap`) reaches the pool, and `auto_tap` itself is not the only
        path in. That includes whose `source` is: only its controller may
        activate its mana ability (CR 602.2, CR 605.3), and a controlled
        player's cost is paid from their own board (CR 723.5a) - see
        `why_payer_cannot_use`, which the auto-tap candidate scans share.
        CR 712.8d/712.8e/712.8f give a double-faced permanent only
        the characteristics of the face that's up, so `produces` must be
        something a `{T}`-including mana ability *of that face* could
        actually make right now (`parse_mana_abilities` already reads only
        the up face - see its own docstring); Witch Enchanter on the
        battlefield front face up (a creature, no mana ability at all) is
        refused here even if a caller asks for Witch-Blessed Meadow's `{T}:
        Add {W}.` by name.

        Run under `Game._id_allocator_scope` whenever there is a game:
        `_tap_for_mana_impl`'s own `game.emit` below mints a fresh
        `AbilityOnStack` id for every "tapped for mana" trigger it finds -
        CR 106.12a. `pay()` already wraps its own `settle_mana`/`pool.pay`
        path, but this is a separate one: the api's `pay_with` calls this
        directly, once per hand-picked source, before `pay()` is ever
        reached, and `auto_tap` below calls it directly too.
        """
        if self.game is None:
            return self._tap_for_mana_impl(source, produces, restriction)
        with self.game._id_allocator_scope():
            return self._tap_for_mana_impl(source, produces, restriction)

    def _tap_for_mana_impl(
        self,
        source: CardState,
        produces: list[Color],
        restriction: ManaRestriction | None = INFER_RESTRICTION,
    ) -> ManaPool:
        """The rest of `tap_for_mana` - see its own docstring for why it is
        split out."""
        self._require_open()
        refusal = why_payer_cannot_use(source, self.payer, self.game)
        if refusal is not None:
            raise ValueError(refusal)
        if not can_tap_for_mana(source, self.game):
            raise ValueError(
                f"{source.name} has not been under {source.controller or 'its controller'}'s "
                "control since their most recent turn began, so its {T} ability "
                "cannot be activated"
            )
        # Which of `source`'s abilities this tap counts as having activated,
        # and the CR 602.5 refusals collected on the way - `_activated_mana_
        # ability`, shared with `mana_ability_index` so the ability a
        # `TapPlan` entry reports is the ability the tap actually activates.
        activated, refusals, produces, triggered_colors = _activated_mana_ability_with_triggers(
            self, source, produces, restriction
        )
        if activated is None:
            made = "".join(f"{{{color.value}}}" for color in produces) or "no mana"
            if refusals:
                raise ValueError(
                    f"{source.name} cannot be tapped to add {made}: {'; '.join(refusals)}"
                )
            raise ValueError(f"{source.name} cannot be tapped to add {made}")
        self._transition(CostStep.TAPPING)

        source.tap()
        self.tapped_for_mana.append(source.id)
        self._tapped_sources[source.id] = source
        if restriction is INFER_RESTRICTION:
            restriction = restriction_for_production(source, produces, self.game)
        # CR 106.6's additional-effect clause travels with the mana too, and it
        # is read off the **same** ability the restriction above belongs to.
        # `activated` is the ability this tap counts as having activated: the
        # one the caller named where it named one, and otherwise the one whose
        # production matched. Reading the restriction from the caller and this
        # sentence from whichever ability the production loop broke on is how
        # one tap would come to carry two abilities' worth of CR 106.6.
        #
        # Not exercisable end to end today, and deliberately not faked: it
        # takes a printing with two mana abilities that produce the *same*
        # mana and carry different CR 106.6 sentences, and no card in Magic
        # does that - every multi-ability printing in the pool (Eldrazi
        # Temple's `{C}` beside `{C}{C}`, Cavern of Souls's `{C}` beside one
        # mana of any colour) differs in what it adds. So this is a
        # correct-by-construction fix rather than a tested one, and the note
        # is here rather than in a commit message because the next reader
        # needs the reason the asymmetry was closed with no test beside it.
        spend_effect = (
            ManaSpendEffect(text=activated.ability.spend_effect)
            if activated.ability.spend_effect
            else None
        )
        self.pool.add_all(
            produces,
            snow=is_snow_source(source, self.game),
            restriction=restriction,
            spend_effect=spend_effect,
        )
        if self.game is not None:
            # CR 405.6c: the mana ability's other effect happens with the mana,
            # through the same funnel `Game.activate_ability` uses.
            self.game.apply_mana_ability_rider(
                activated.ability.rider, self.game.controller_of(source).username, source
            )
            waiting = {id(ability) for ability in self.game.pending_triggers}
            # CR 106.12a: this mana ability resolved and produced mana - and
            # an ability caused the payer to add it, which Caged Sun asks.
            set_off = [
                *self.game.emit(tapped_for_mana_event(source, self.game, mana_added=produces)),
                *self.game.emit(mana_added_event(source, self.game, mana_added=produces)),
            ]
            # CR 605.4a: the triggered mana abilities among them resolve now,
            # into this payment's pool (`Game.mana_pool_receiving`), with any
            # colour the caller already named for them; CR 733.1's rewind
            # empties that pool with the rest of the payment's mana.
            self.game.resolve_triggered_mana_abilities(
                set_off, color_hints=triggered_colors, planned=self._planning
            )
            self.triggers_caused.extend(
                ability.id for ability in self.game.pending_triggers if id(ability) not in waiting
            )
        return self.pool

    def auto_tap(self, sources: Iterable[CardState]) -> list[CardState]:
        """Solve which of `sources` to tap, and which colour each makes, to
        cover this payment's mana part - and do it.

        A dual land, a shockland, and an any-colour source all offer a choice
        of colour (CR 605.1a's mana abilities do not require the choice to be
        made until the ability resolves), but once the cost to pay is fixed,
        which colour makes it payable is deterministic bookkeeping in the
        overwhelming majority of cases, not a strategic decision - this finds
        a legal assignment the same way a player filling in a dual land's
        colour to make their spell work would, rather than making the player
        name it for every cast. CR 601.2g: mana abilities are activated
        before the cost is paid; CR 118.3c: activating any of them, or all of
        them, is never mandatory, so this stops as soon as the pool can pay
        and never taps more than that.

        What this will not choose on the player's behalf: a source with any
        cost beyond `{T}` (life, a sacrifice, an exert, more mana), filtered
        out before the search starts by `free_tap_mana_abilities`.

        A CR 106.6 restricted ability **is** offered now, but only when its
        restriction permits what this payment is for (`self.spend`) - a
        payment that cannot name what it is for gets none of them. So Eldrazi
        Temple's `{C}{C}` is auto-tapped for a colorless Eldrazi spell and
        withheld from a Mind Stone, and Shang-Chi's mana is offered to an
        activation of a creature's ability and to nothing else. When both a
        restricted and an unrestricted ability of the same source would serve,
        the restricted one is preferred, so the mana that can do less is the
        mana spent.

        Prefers the fewest sources, and among equally-small choices prefers
        spending the least flexible ones (a basic over a dual, a dual over an
        any-colour source) so a flexible source stays untapped - see
        `_flexibility`. Raises a `ValueError` naming the cost if no legal
        assignment of `sources` exists; nothing is tapped when that happens.
        When the reason is that a source was withheld by the `{T}`-only rule
        above, the message names that source and the cost it needed (see
        `_unpayable_cost_message`) rather than just reporting the cost as
        unpayable, which would read as a solver bug rather than as "activate
        that one yourself".

        Solving *which* sources and colours is `_solve_auto_tap` (pure,
        below); this is the thin remainder - execute the plan it finds, or
        raise if it found none. `could_pay_mana_cost` is the same solve with
        no execution at all, which is what makes the two unable to disagree.
        """
        self._require_open()
        sources = list(sources)
        plan = _solve_auto_tap(
            self,
            sources,
            owed=self.mana_owed,
            base_floating=dict(self.pool.floating),
            base_snow=dict(self.pool.snow),
            base_restricted=[entry.model_copy(deep=True) for entry in self.pool.restricted],
            life_available=self.life_available,
        )
        if plan is None:
            raise ValueError(_unpayable_cost_message(self, sources))
        # The plan answers the "may add" of each tap's triggered mana abilities
        # (CR 608.2d), the way it picks each colour: the mana it counted is
        # taken, and the mana it left out is declined, never asked mid-payment.
        self._planning = True
        try:
            for source, colors, restriction in plan:
                self.tap_for_mana(source, colors, restriction)
        finally:
            self._planning = False
        return [source for source, _colors, _restriction in plan]

    def add_mana(self, color: Color, amount: int = 1, snow: bool = False) -> ManaPool:
        """Add mana that came from somewhere other than tapping a permanent."""
        self._require_open()
        self.pool.add(color, amount, snow=snow)
        return self.pool

    def finish_tapping(self) -> CostStep:
        """Declare the pool filled and ready to pay from."""
        self._require_open()
        self._transition(CostStep.POOLED)
        return self.step

    def settle_mana(self) -> ManaPayment:
        """Work out how the mana part would be paid, or raise if it cannot.

        The search lives on `ManaPool`; this is where the payer's life total
        joins it, which is the only thing that makes a Phyrexian symbol payable
        with life through the engine (CR 107.4f).
        """
        owed = self.mana_owed
        payment = self.pool.payment_for(
            owed,
            life_available=self.life_available,
            choices=self.choices,
            spend=self.spend,
        )
        if payment is None:
            raise ValueError(f"pool {self.pool.floating} cannot pay {owed}{self._blocked()}")
        return payment

    def _blocked(self) -> str:
        """The CR 106.6 half of the message when a payment is refused.

        A pool that visibly holds enough mana and still cannot pay reads as a
        bug unless the refusal says which mana was off limits and why, quoting
        the card's own sentence.
        """
        offending = [
            entry.restriction
            for entry in self.pool.restricted
            if entry.total and not entry.restriction.allows(self.spend)
        ]
        if not offending:
            return ""
        quoted = "; ".join(sorted({restriction.text for restriction in offending}))
        for_what = self.spend.name if self.spend is not None else "this cost"
        return f": {quoted} (CR 106.6), and this pays for {for_what}"

    def pay(self) -> ManaPool:
        """Pay the whole total cost and return the mana still floating after.

        Everything is checked before anything is spent, so a cost that cannot
        be paid in full leaves the machine exactly as it was and the caller can
        tap another source or cancel outright (CR 118.3, 601.2h).

        Life owed for a Phyrexian symbol is paid as one more component of the
        total cost, so it leaves the life total through the same machinery as
        "pay 2 life" printed on a card, and rewinds with it (CR 733.1).

        That overflow does not vanish here. The remainder is written back into
        the payer's mana pool, where it stays until the current step or phase
        ends, and can pay for something else first (CR 106.4a).

        CR 601.2h gives the payer the order: "First, they pay all costs that
        don't involve random elements or moving objects from the library to a
        public zone, in any order. Then they pay all remaining costs in any
        order." `components_before_mana` is the first sentence's freedom - pay
        the sacrifice before the mana, or after - and the mill components are
        held back to the second sentence's pass regardless of it.

        Run under `Game._id_allocator_scope` whenever there is a game: a
        sacrifice, discard, exile, or mill component's own `pay(self.game)`
        below moves a real card (`CardState.move_to` mints a fresh
        `zone_change_stamp`), and this is called directly by a caller paying a
        cost - `Casting.cast()` and `Game.activate_ability` are downstream of
        the announcement, not upstream of this call, so their own allocator
        scopes do not cover it.
        """
        if self.game is not None:
            with self.game._id_allocator_scope():
                return self._pay_impl()
        return self._pay_impl()

    def _pay_impl(self) -> ManaPool:
        """The rest of `pay` - see its own docstring for why it is split out."""
        self._require_open()
        if self.step in {CostStep.PENDING, CostStep.TAPPING}:
            self.finish_tapping()

        unpayable = self.unpayable
        if unpayable is not None:
            raise ValueError(unpayable)

        mana_payment = self.settle_mana()
        life = (
            pay_life_cost(
                mana_payment.life_paid,
                self.payer,
                description=f"pay {mana_payment.life_paid} life for {self.mana_owed}",
            )
            if mana_payment.life_paid
            else None
        )
        self._merge_exile_components()
        components = [*self.components, *([life] if life is not None else [])]
        if life is not None:
            owed = life.why_not(self.game)
            if owed is not None:
                raise ValueError(owed)

        # A pool that falls short leaves the machine untouched, so the caller
        # can tap another source and try again.
        floating = dict(self.pool.floating)
        snow = dict(self.pool.snow)
        restricted = [entry.model_copy(deep=True) for entry in self.pool.restricted]
        retained = [entry.model_copy(deep=True) for entry in self.pool.retained]

        # CR 601.2h's two passes: everything else first, then the costs that
        # move objects from a library to a public zone (a mill cost).
        first_pass = [c for c in components if c.kind is not ComponentKind.MILL]
        second_pass = [c for c in components if c.kind is ComponentKind.MILL]

        paid: list[CostComponent] = []
        mana_spent = False
        try:
            if not self.components_before_mana:
                self.pool.pay(self.mana_owed, payment=mana_payment)
                mana_spent = True
            for component in first_pass:
                component.pay(self.game)
                paid.append(component)
            if self.components_before_mana:
                self.pool.pay(self.mana_owed, payment=mana_payment)
                mana_spent = True
            for component in second_pass:
                component.pay(self.game)
                paid.append(component)
        except Exception:
            for component in reversed(paid):
                component.unpay(self.game)
            if mana_spent:
                self.pool.floating = floating
                self.pool.snow = snow
                self.pool.restricted = restricted
                self.pool.retained = retained
            raise

        if life is not None:
            self.components.append(life)
        self.mana_payment = mana_payment
        self._transition(CostStep.PAID)
        self._write_back_remainder()
        self._unregister_pool()
        self.overflow = self.pool
        return self.overflow

    def _merge_exile_components(self) -> None:
        """Fold this payment's like exile components into one before paying.

        CR 603.2c: "An ability triggers only once each time its trigger event
        occurs. However, it can trigger repeatedly if one event contains
        multiple occurrences." Paying one cost is one instruction, so a delve
        payment (CR 702.66a) that exiles five cards out of a graveyard is one
        occurrence of "one or more cards leave your graveyard" - Hardened
        Academic triggers once with a count of five, not five times.

        The shape that made that hard is CR 702.66a's own "**for each** generic
        mana ... you may exile a card", which `machines/objects_as_costs.delve`
        honours by building one component per symbol. Five components exiling
        one card each are five calls to `Game.exile_cards` and five events, so
        they are merged here - at CR 601.2h, the moment the cost is actually
        paid - into one component holding all five cards, which makes one call.

        Only components that differ in nothing but their cards are merged: same
        zone, same payer, same requirement, same "pay its mana cost" flag. Two
        genuinely different exile costs on one spell stay two instructions. The
        merged component replaces its parts in `self.components`, so the
        rewind (CR 733.1) undoes exactly what was paid.
        """
        merged: list[CostComponent] = []
        by_key: dict[tuple[Any, ...], CostComponent] = {}
        for component in self.components:
            if component.kind is not ComponentKind.EXILE or component.paid:
                merged.append(component)
                continue
            key = (
                component.payer,
                component.zone,
                component.pay_mana_cost_of_chosen,
                None if component.requirement is None else component.requirement.model_dump_json(),
            )
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = component
                merged.append(component)
                continue
            existing.cards = [*existing.cards, *component.cards]
            existing.required += component.required
            existing.description = "; ".join(
                part for part in (existing.description, component.description) if part
            )
        self.components = merged

    def cancel(self) -> None:
        """Rewind: undo every component paid, untap the mana sources, empty the pool.

        The payer's own floating mana needs no restoring here: the payment
        worked on a copy, so their pool was never touched (see
        `_seed_payer_pool`).
        """
        self._require_open()
        self._undo_everything()
        self._unregister_pool()
        self._transition(CostStep.CANCELLED)

    def rewind(self) -> None:
        """Undo the payment even if it was already made in full.

        CR 601.6: if the casting turns out to be illegal after the proposal was
        completed, the game returns to the moment before it began, and CR 733.1
        cancels any payments already made. A finished payment is otherwise
        closed, so this is the one door out of PAID.

        From PAID the reversal is total: `pay` already replaced the payer's
        pool with the remainder, so the pre-existing floating mana the payment
        spent is put back (CR 733.1 reverses "any payments already made"). The
        mana the payment's own activations produced does not come back - those
        activations are undone, their sources untapped by `_undo_everything`,
        and their mana died with the copy.
        """
        if self.step is CostStep.CANCELLED:
            return
        if self.step is not CostStep.PAID:
            self.cancel()
            return

        self._undo_everything()
        self._restore_payer_pool()
        self._unregister_pool()
        self.overflow = None
        self.step = CostStep.CANCELLED

    def _seed_payer_pool(self) -> None:
        """Start the pool from the payer's floating mana, on a copy.

        CR 202.1a: "The mana cost of an object represents what a player must
        spend from their mana pool to cast that card", and CR 106.4 lets mana
        already floating there pay "immediately", so a payment opens on what
        its payer already has. It works on a copy so that a cancelled payment
        (CR 733.1) throws away only what the payment itself produced: the
        player's pre-existing floating mana never leaves their pool, while the
        mana abilities activated along the way (CR 601.2g) add into the copy
        and die with it when the payment is undone. `pay` writes the remainder
        back, and `rewind` restores this snapshot.
        """
        if self.game is None or self.payer is None:
            return
        try:
            floating = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        self.pool = _copy_pool(floating)
        self._preexisting = _copy_pool(floating)
        self._register_pool()

    def _register_pool(self) -> None:
        """Publish this payment's working pool as the payer's unspent mana.

        CR 106.4: mana produced and not spent is in the player's mana pool.
        The working copy above is where CR 601.2g's mana abilities actually
        put it, so for as long as this payment is open the copy - not the
        player's own `ManaPool` - is what "unspent mana you have" means. The
        only reader is `Game.unspent_mana_of`, for Omnath, Locus of Mana's
        continuous effect; nothing pays out of it.
        """
        pools = getattr(self.game, "open_payment_pools", None)
        if pools is not None and self.payer is not None:
            # An in-place edit of the game outside any command, read by the
            # layered board (Omnath): announced like one (`snapshot.py`).
            announce_mutation(self.game)
            pools[self.payer] = self.pool
            mutation_landed(self.game)

    def _unregister_pool(self) -> None:
        """Stop publishing: the payment is paid, cancelled or rewound, and the
        payer's own `ManaPool` is the answer again (`_write_back_remainder`
        and `_restore_payer_pool` have already put the right mana in it)."""
        pools = getattr(self.game, "open_payment_pools", None)
        if pools is not None and self.payer is not None:
            announce_mutation(self.game)
            pools.pop(self.payer, None)
            mutation_landed(self.game)

    def _write_back_remainder(self) -> None:
        """Leave what the payment did not spend floating in the payer's pool.

        CR 106.4a: "If any mana remains in a player's mana pool after mana is
        spent to pay a cost, that player announces what mana is still there" -
        the engine has no announcement to read, but the remainder belongs in
        the player's pool, where it stays until the step ends (CR 703.4q) and
        can pay for something else first (CR 106.4). The payment's pool is a
        working copy, so the player's pool is given the remainder's contents,
        never aliased to it.
        """
        if self.game is None or self.payer is None:
            return
        try:
            pool = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        pool.floating = dict(self.pool.floating)
        pool.snow = dict(self.pool.snow)
        pool.restricted = [entry.model_copy(deep=True) for entry in self.pool.restricted]
        pool.retained = [entry.model_copy(deep=True) for entry in self.pool.retained]

    def _restore_payer_pool(self) -> None:
        """Put the payer's floating mana back the way it was before payment.

        The PAID half of CR 733.1's reversal: `pay` replaced the pool with the
        remainder, which spent whatever pre-existing mana the payment used, so
        undoing the whole action puts that mana back.

        `game is None or payer is None` is a legitimate no-op: there was never
        a pool to restore into. `_preexisting is None` while `game` and
        `payer` are both set is a different thing entirely - in production a
        `CostPayment` only ever comes from `for_total`, which seeds
        `_preexisting` whenever it has a `game` and `payer` to seed it from, so
        reaching PAID with a `game`/`payer` but no `_preexisting` means the
        snapshot was there once and a dump/decode round trip dropped it
        (`_preexisting` is a `PrivateAttr`; see its own docstring). Restoring
        nothing and reporting success would leave a rewound payment's mana
        gone - the reviewer's exact repro - so this refuses loudly instead.
        """
        if self.game is None or self.payer is None:
            return
        if self._preexisting is None:
            raise RuntimeError(
                f"cannot rewind {self.payer}'s payment: its pre-payment mana "
                "pool snapshot (CostPayment._preexisting) did not survive a "
                "dump/decode round trip, so there is nothing to restore it "
                "from"
            )
        try:
            pool = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        pool.floating = dict(self._preexisting.floating)
        pool.snow = dict(self._preexisting.snow)
        pool.restricted = [entry.model_copy(deep=True) for entry in self._preexisting.restricted]
        pool.retained = [entry.model_copy(deep=True) for entry in self._preexisting.retained]

    def _undo_everything(self) -> None:
        for component in reversed(self.components):
            component.unpay(self.game)
        for source_id in self.tapped_for_mana:
            # Re-resolved through `game` rather than held by reference (see
            # `tapped_for_mana`'s own docstring): after a dump/decode round
            # trip the only object that answers to this id and is actually on
            # the battlefield is the one `game.find_by_id` finds.
            # `_tapped_sources` only carries a live object when there is no
            # `game` to ask at all (a unit test tapping a bare `CardState`).
            source = (
                self.game.find_by_id(source_id)
                if self.game is not None
                else self._tapped_sources.get(source_id)
            )
            if isinstance(source, CardState):
                source.untap()
        self.tapped_for_mana = []
        self._tapped_sources = {}
        self.pool.empty()
        self.mana_payment = None
        self._discard_triggers_caused()

    def _discard_triggers_caused(self) -> None:
        """CR 733.1: undo the CR 106.12a triggers this payment's own taps
        queued, the same reversal `_undo_everything`'s untapping already gives
        the sources themselves.

        Two places a queued trigger can still be waiting: `pending_triggers`,
        if nobody has received priority since the tap, or `stack`, if a
        `retain_priority`/`pass_priority` call already ran `put_triggers_on_
        stack` in between - a cancelled or rewound payment has to check both.
        """
        if self.game is None or not self.triggers_caused:
            return
        caused = frozenset(self.triggers_caused)
        self.game.pending_triggers = [
            ability for ability in self.game.pending_triggers if ability.id not in caused
        ]
        stack = self.game.stack
        stack[:] = [item for item in stack if not (is_ability(item) and item.id in caused)]
        self.triggers_caused = []

    def _require_open(self) -> None:
        if self.is_settled:
            raise ValueError(f"payment is already {self.step}")

    def _transition(self, target: CostStep) -> None:
        if target not in _ALLOWED[self.step]:
            raise ValueError(f"cannot go from {self.step} to {target}")
        self.step = target
