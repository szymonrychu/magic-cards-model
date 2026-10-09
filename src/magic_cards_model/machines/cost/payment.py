import re
from collections import Counter as _MultiSet
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from itertools import combinations, combinations_with_replacement, product
from typing import Any, NamedTuple
from uuid import UUID

from pydantic import ConfigDict, Field, PrivateAttr

from ...data.subtypes import canonical_subtype
from ...models.card import Card, Color, Supertype, Type
from ...models.card_state import (
    CardState,
    ChoiceKind,
)
from ...models.mana import (
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
from ...models.zone import Zone
from ...numbers import (
    count_pattern,
    parse_count,
)
from ...snapshot import EngineModel, announce_mutation, mutation_landed
from ..abilities import (
    ActivatedAbility,
    CostKind,
    ManaAbility,
    granted_mana_abilities,
    intrinsic_land_ability,
    one_named_color,
    parse_abilities,
    parse_mana_abilities,
    parse_triggered_mana,
    resolve_mana_count_expression,
)
from ..combat import Keyword, has_keyword
from ..triggers import (
    abilities_triggered_by,
    activated_abilities_from_lines,
    activated_abilities_of,
    added_ability_lines,
    granted_activated_abilities_of,
    is_ability,
    mana_ability_activated_event,
    mana_added_event,
    rewritten_ability_lines,
    tapped_for_mana_event,
    triggered_abilities_on,
    triggered_mana_count,
    triggered_mana_recipient,
)
from .components import CostComponent, CostStep, CostSubstitution, TotalCost


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


def is_creature_source(source: CardState, game: Any = None) -> bool:
    """Whether mana from this permanent is mana from a creature (CR 106.3) -
    read off the computed board where it still is (an animated land is one,
    CR 613.5), else off what it last was."""
    if game is not None and source.zone is Zone.BATTLEFIELD:
        try:
            return game.characteristics_of(source).is_creature
        except (AttributeError, KeyError):
            pass
    return Type.CREATURE in source.types


def is_treasure_source(source: CardState, game: Any = None) -> bool:
    """Whether mana from this permanent is mana from a Treasure (CR 106.3:
    the source of mana is the source of the ability that produced it) -
    read off the computed board where it still is, else off what it last was
    (a Treasure's own mana ability sacrifices it as a cost, CR 111.10a)."""
    if game is not None and source.zone is Zone.BATTLEFIELD:
        try:
            return "Treasure" in game.characteristics_of(source).subtypes
        except (AttributeError, KeyError):
            pass
    return "Treasure" in source.subtypes


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
#: "gain a Class level" (Sorcerer Class) - CR 716.2a: a Class gains a level
#: only by activating its "[Cost]: Level N" bar, so this is an activation
#: clause narrowed to level bars.
_SPEND_CLASS_LEVEL_CLAUSE = re.compile(r"^gain an? Class level$", re.IGNORECASE)
#: A trailing "with mana value N or greater" / "with {X} in its/their mana
#: cost(s)" narrows the spell by CR 202.3's mana value or its printed cost
#: (Helga, Skittish Seer).
_SPEND_CAST_CLAUSE = re.compile(
    r"^cast (?P<quality>.*?) ?spells?"
    r"(?P<chosen> of the chosen type)?"
    r"(?: with mana value (?P<min_mv>\d+) or greater"
    r"|(?P<x_cost> with \{X\} in (?:its|their) mana costs?))?"
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
#: The singular "activate an ability of a Villain source" (Villainous
#: Hideout, Cargo Ship, Ixalli's Lorekeeper) is the same restriction worded
#: for one ability at a time (CR 106.6).
#: The trailing "of the chosen type" is `_SPEND_CAST_CLAUSE`'s own `chosen`
#: group on the activation side - Eclipsed Realms' "activate an ability of a
#: source of the chosen type" (CR 106.6, the answer read off CR 614.12a's
#: choice on the source exactly as the cast half reads it).
_SPEND_ACTIVATE_CLAUSE = re.compile(
    r"^activate (?:abilities|an ability)"
    r"(?: of (?P<quality>.+?)(?: sources?)?(?P<chosen> of the chosen type)?)?$",
    re.IGNORECASE,
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
#: "or" before "greater"/"less" is a mana value comparison, never a joiner.
_SPEND_CLAUSE_SPLIT = re.compile(r" and/or | and | or (?!greater\b|less\b)")
#: A joiner followed by a repeated "to" ("cast an instant or sorcery spell or
#: to gain a Class level") can only join two whole clauses - a quality list
#: never repeats the infinitive - so this boundary is cut before the generic
#: split, which would also tear "instant or sorcery" apart.
_SPEND_INFINITIVE_SPLIT = re.compile(r" (?:and/or|and|or) (?=to )")
#: The verb a split "only to ..." phrase opens with, lent to a following
#: phrase that elides it.
_SPEND_VERB = re.compile(r"^(?:cast|activate|pay|unlock) ", re.IGNORECASE)
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

    infinitives = _SPEND_INFINITIVE_SPLIT.split(what)
    if len(infinitives) > 1:
        clauses: list[SpendClause] = []
        for infinitive in infinitives:
            read = _spend_clauses(infinitive.strip().removeprefix("to "), chosen_type)
            if read is None:
                return None
            clauses.extend(read)
        return clauses

    alternatives = _SPEND_CLAUSE_SPLIT.split(what)
    if len(alternatives) == 1:
        return None
    clauses = []
    verb: str | None = None
    for alternative in alternatives:
        # "cast a Villain spell or to activate ...": the second phrase repeats
        # the infinitive's "to", which the first one's "only to" already said.
        phrase = alternative.strip().removeprefix("to ")
        printed = _SPEND_VERB.match(phrase)
        if printed is not None:
            verb = printed.group(0).strip()
        elif verb is not None:
            # Maelstrom of the Spirit Dragon's "cast a Dragon spell or an
            # Omen spell": the second phrase's verb is the first one's.
            phrase = f"{verb} {phrase}"
        clause = _one_spend_clause(phrase, chosen_type)
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
        clause = _spend_clause(cast.group("quality"), SpendPurpose.CAST_SPELL, chosen, zone)
        if clause is None:
            return None
        if cast.group("min_mv") is not None:
            clause = clause.model_copy(update={"min_mana_value": int(cast.group("min_mv"))})
        if cast.group("x_cost") is not None:
            clause = clause.model_copy(update={"requires_x_in_cost": True})
        return clause

    activate = _SPEND_ACTIVATE_CLAUSE.match(phrase)
    if activate is not None:
        chosen = chosen_type if activate.group("chosen") else None
        if activate.group("chosen") and chosen is None:
            return None
        return _spend_clause(activate.group("quality") or "", SpendPurpose.ACTIVATE_ABILITY, chosen)
    if _SPEND_CLASS_LEVEL_CLAUSE.match(phrase):
        return SpendClause(purpose=SpendPurpose.ACTIVATE_ABILITY, class_level=True)
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


def mana_ability_count(
    game: Any,
    permanent: CardState,
    mana: ManaAbility,
    color: "Color | Sequence[Color] | str | None" = None,
    controller: str | None = None,
    *,
    x_value: int | None = None,
    sacrificed_ids: Sequence[UUID] = (),
) -> int | None:
    """How many mana `mana` adds if it resolves now, where the board decides
    it, else `None` (a printed amount, which `ManaAbility.resolve` already
    knows).

    CR 700.5's devotion to the colour `color` names (Nykthos), or the "where
    X is ..." / "for each ..." / "equal to ..." count (`resolve_mana_count_
    expression`) - with `x_value` the X announced for a "Remove any number of
    counters" cost (CR 107.3a) and `sacrificed_ids` what the activation cost
    sacrificed. This is the one reading `Game.activate_ability` resolves with,
    and the one a caller naming a source's mana before it is tapped should ask
    (CR 605.3b).
    """
    controller = controller or game.controller_of(permanent).username
    if mana.amount_from_devotion:
        from ..effects import devotion_to

        devotion_color = one_named_color(color)
        if devotion_color is None:
            return None
        return devotion_to(game, controller, devotion_color)
    expression = mana.any_color_count_expression or mana.for_each_expression
    if expression is None:
        return None
    return resolve_mana_count_expression(
        game, controller, permanent, expression, x_value, sacrificed_ids
    )


def mana_ability_most(
    game: Any, permanent: CardState, index: int = 0, controller: str | None = None
) -> int | None:
    """The most `mana_ability_count` could be for this ability if it were
    activated now, over the choices its own cost leaves open - every counter
    a "Remove any number of `<kind>` counters" cost could remove (CR 107.3a's
    announced X, bounded by the counters there), each permanent its sacrifice
    cost could take (CR 118.3). `None` where the board decides no count (a
    printed amount, or devotion with no colour named). For a caller
    describing a source before paying with it; the activation itself counts
    what was actually paid.
    """
    mana = game.activated_abilities(permanent)[index].mana
    if mana is None:
        return None
    controller = controller or game.controller_of(permanent).username
    cost = game.activation_cost(permanent, index, controller)
    x_value: int | None = None
    sacrifices: list[CardState] = []
    for component in cost.components:
        if component.kind is ComponentKind.REMOVE_COUNTERS and component.variable_count:
            x_value = permanent.counter_count(component.counter_kind)
        elif component.kind is ComponentKind.SACRIFICE:
            sacrifices = list(game._cost_candidates(component, controller) or [])
    if not sacrifices:
        return mana_ability_count(game, permanent, mana, None, controller, x_value=x_value)
    counts = [
        mana_ability_count(
            game, permanent, mana, None, controller, x_value=x_value, sacrificed_ids=(state.id,)
        )
        for state in sacrifices
    ]
    known = [count for count in counts if count is not None]
    return max(known) if known else None


def counted_mana_options(
    game: Any,
    payer: str | None,
    source: CardState,
    ability: ManaAbility,
    options: list[list[Color]],
) -> tuple[list[list[Color]], int | None]:
    """`options` scaled to the amount `ability` would really add if it
    resolved now (CR 605.3b), and that amount - `None` for a printed one.

    `ManaAbility.effective` answers *what* an ability makes; a count the board
    decides - "Add {C} for each charge counter on this artifact"
    (`for_each_expression`), "X mana of any one color, where X is ..."
    (`any_color_count_expression`), CR 700.5's devotion
    (`amount_from_devotion`) - is left at its one-mana placeholder there, and
    a payment plan built on the placeholder over- or under-taps. This is the
    same count `Game.activate_ability` passes to `ManaAbility.resolve`, read
    through the same `resolve_mana_count_expression` / `devotion_to`, so what
    a plan counts on is what the tap adds. A count of zero leaves no option at
    all: CR 605.2 keeps it a mana ability, but it is no mana source now.
    """
    expression = ability.for_each_expression or ability.any_color_count_expression
    if game is None or (expression is None and not ability.amount_from_devotion):
        return options, None
    controller = source.controller or payer
    if controller is None:
        return options, None
    if ability.amount_from_devotion:
        from ..effects import devotion_to

        counted = []
        for option in options:
            if not option:
                continue
            amount = devotion_to(game, controller, option[0])
            if amount > 0:
                counted.append([option[0]] * amount)
        return counted, None
    assert expression is not None
    # `x_value` stays unset: a plan pays no "Remove any number of counters"
    # cost, and only bare-`{T}` abilities are planned at all.
    amount = resolve_mana_count_expression(game, controller, source, expression)
    if amount <= 0:
        return [], 0
    if ability.for_each_expression is not None:
        return [list(option) * amount for option in options], amount
    return [[option[0]] * amount for option in options if option], amount


def _mixed_options(options: list[list[Color]]) -> list[list[Color]]:
    """A mixed ability's `options` (`[[c] * n for c in palette]`, already
    narrowed and counted) as the one `MixedProduction` they stand for. One
    mana is already a plain choice of colour, and nothing to mix."""
    if not options or len(options[0]) <= 1:
        return options
    palette = list(dict.fromkeys(option[0] for option in options if option))
    return [MixedProduction(palette, len(options[0]))]


def _spelled_out(options: list[list[Color]]) -> list[list[Color]]:
    """`options` with every `MixedProduction` expanded to its splits."""
    spelled: list[list[Color]] = []
    for option in options:
        if isinstance(option, MixedProduction):
            spelled.extend(option.splits())
        else:
            spelled.append(option)
    return spelled


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


def _mana_production_effects(game: Any) -> list[Any]:
    """`machines.replacement.mana_production_effects`, or nothing without a
    game. Imported late: `machines/replacement.py` imports `machines/casting.py`,
    which imports this module."""
    if game is None:
        return []
    from ..replacement import mana_production_effects

    return mana_production_effects(game)


def _replace_production(
    context: "CostPayment | _SpendContext",
    source: CardState,
    produced: Sequence[Color],
    effects: list[Any],
) -> list[Color]:
    """What tapping `source` for `produced` really adds (CR 106.12b) - see
    `machines.replacement.replace_mana_production`."""
    from ..replacement import replace_mana_production

    return replace_mana_production(
        context.game,
        source,
        produced,
        tapper=context.payer or source.controller,
        effects=effects,
    )


def _replaced_options(
    context: "CostPayment | _SpendContext",
    source: CardState,
    options: list[list[Color]],
    effects: list[Any],
) -> list[list[Color]]:
    """Each production in `options`, replaced, with duplicates dropped - a
    choice of "two mana of any one color" is one {C} five times over under
    Damping Sphere."""
    replaced: list[list[Color]] = []
    for option in options:
        production = _replace_production(context, source, option, effects)
        if sorted(production) not in (sorted(seen) for seen in replaced):
            replaced.append(production)
    return replaced


def _unreplaced_production(
    context: "CostPayment | _SpendContext",
    source: CardState,
    wanted: Sequence[Color],
    effects: list[Any],
) -> list[Color] | None:
    """The production one of `source`'s `{T}` mana abilities offers that CR
    106.12b's replacements turn into `wanted`, or `None`. Any mana a
    triggered mana ability adds after the ability's own (CR 605.4a) is kept
    as the tail, the way `_with_triggered_mana` appended it."""
    game = context.game
    land_types, own_counters, has_imprinted_card = _mana_context(context, source)
    productions: list[list[Color]] = []
    for _index, activation in tappable_mana_activations(source, game):
        ability = activation.mana
        if ability is None:
            continue
        options, any_color = ability.effective(
            land_types,
            own_counters,
            has_imprinted_card,
            **_mana_narrowings(context, source, ability),
        )
        options, _any = _narrow_to_defined_colors(
            options, any_color, _among_colors(activation.effect, context, source)
        )
        options, _amount = counted_mana_options(game, context.payer, source, ability, options)
        if ability.any_color_mixed:
            # Every split of a mixture is a production it offers.
            options = _spelled_out(_mixed_options(options))
        productions.extend(options)
    wanted = list(wanted)
    for cut in range(len(wanted), 0, -1):
        own, extra = sorted(wanted[:cut]), wanted[cut:]
        for production in productions:
            if sorted(_replace_production(context, source, production, effects)) == own:
                return list(production) + extra
    return None


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
    # CR 106.12b: what a source is planned for is what it really produces,
    # after any mana-production replacement - Damping Sphere's Ancient Tomb
    # is one mana to this solver, Nyxbloom Ancient's Forest three.
    production_effects = _mana_production_effects(payment.game)
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
            options, _amount = counted_mana_options(
                payment.game, payment.payer, source, ability, options
            )
            if not options:
                continue
            if ability.any_color_mixed:
                # "N mana in any combination of <colours>": one mixed
                # alternative, not N of a single colour (CR 106.1a).
                options = _mixed_options(options)
                any_color = True
            if production_effects or trigger_sources:
                # What a replacement or a triggered mana ability does depends
                # on the production itself, so each split is asked separately.
                options = _spelled_out(options)
            if production_effects:
                options = _replaced_options(payment, source, options, production_effects)
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
    base = (
        f"no combination of the available mana sources can pay {payment.mana_owed}"
        f"{payment.x_restriction_note()}"
    )
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


def _plan_life_loss(
    context: "CostPayment | _SpendContext",
    plan: Sequence[tuple[CardState, list[Color], ManaRestriction | None]],
) -> int:
    """The life `plan`'s own mana abilities take from their controller as
    they resolve - CR 405.6c's immediate side effect, Ancient Tomb's "This
    land deals 2 damage to you." or a "You lose 1 life." rider.

    CR 601.2g activates those abilities before CR 601.2h pays the total
    cost, so a Phyrexian symbol paid with life (CR 119.4: only with at least
    that much life) is paid out of what is left afterwards. Each entry is
    matched back to the ability `tap_for_mana` would activate for it - the
    first, in printed order, carrying the same CR 106.6 restriction and able
    to make those colours. A life-gain rider is not counted: this is only
    ever asked to rule a plan *out*, and leaving a gain uncounted can only
    make that answer more cautious, never let an unpayable plan through.
    """
    return sum(
        _entry_life_loss(context, source, colors, restriction)
        for source, colors, restriction in plan
    )


def _entry_life_loss(
    context: "CostPayment | _SpendContext",
    source: CardState,
    colors: Sequence[Color],
    restriction: ManaRestriction | None,
) -> int:
    """The life one plan entry's mana ability takes (`_plan_life_loss`'s
    per-entry half): 0 unless the ability `tap_for_mana` would activate for
    these colours carries a damage or life-loss rider."""
    wanted_text = restriction.text if restriction is not None else None
    matches = [
        (index, options)
        for scanned_source, options, scanned_restriction, _any, index in (
            _scan_mana_candidates(context, [source])
        )
        if scanned_source is source
        and (scanned_restriction.text if scanned_restriction is not None else None) == wanted_text
    ]
    chosen = sorted(colors)
    index = next(
        (
            index
            for index, options in sorted(matches, key=lambda item: item[0])
            if any(sorted(option) == chosen for option in options)
        ),
        min((index for index, _options in matches), default=None),
    )
    if index is None:
        return 0
    activation = dict(tappable_mana_activations(source, context.game)).get(index)
    rider = activation.mana.rider if activation is not None and activation.mana else None
    if rider is not None and rider.kind in ("damage_to_controller", "lose_life"):
        return rider.amount
    return 0


def _prefer_painless_mana(
    context: "CostPayment | _SpendContext",
    plan: "TapPlan",
    *,
    owed: ManaCost,
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    base_restricted: list[Any],
    life_available: int,
) -> "TapPlan":
    """Swap a plan entry that takes damage or life (a painland's coloured
    ability, CR 405.6c) for a rider-free ability of the same source with the
    same CR 106.6 restriction when the plan still pays - Llanowar Wastes
    pays a generic {1} with `{T}: Add {C}.`, not by hurting its controller."""
    plan = list(plan)
    for position, (source, colors, restriction) in enumerate(plan):
        if not _entry_life_loss(context, source, colors, restriction):
            continue
        wanted_text = restriction.text if restriction is not None else None
        for scanned_source, options, scanned_restriction, _any, _index in _scan_mana_candidates(
            context, [source]
        ):
            scanned_text = scanned_restriction.text if scanned_restriction is not None else None
            if scanned_source is not source or scanned_text != wanted_text:
                continue
            swapped = False
            for option in options:
                if _entry_life_loss(context, source, option, restriction):
                    continue
                trial_plan = (
                    plan[:position] + [(source, list(option), restriction)] + plan[position + 1 :]
                )
                trial = ManaPool(
                    floating=dict(base_floating),
                    snow=dict(base_snow),
                    restricted=[entry.model_copy(deep=True) for entry in base_restricted],
                )
                for each, each_colors, each_restriction in trial_plan:
                    trial.add_all(
                        each_colors, snow=is_snow_source(each), restriction=each_restriction
                    )
                if trial.can_pay(owed, life_available=life_available, spend=context.spend):
                    plan = trial_plan
                    swapped = True
                    break
            if swapped:
                break
    return plan


def _solve_colours(
    combo: Sequence[_Candidate],
    base_floating: dict[Color, int],
    base_snow: dict[Color, int],
    cost: ManaCost,
    life_available: int,
    spend: ManaSpend | None = None,
    base_restricted: list[Any] | None = None,
    life_loss: Callable[[list[tuple[CardState, list[Color], ManaRestriction | None]]], int]
    | None = None,
) -> list[tuple[CardState, list[Color]]] | None:
    """The first colour assignment for this exact set of sources that pays
    `cost`, or None if none of them do.

    `life_loss`, when given, is `_plan_life_loss` for this assignment: an
    assignment whose own mana abilities' damage leaves too little life for
    the Phyrexian symbols it pays with life (CR 601.2g-h, CR 119.4) does not
    pay, and the next colour choice is tried instead.

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
            if life_loss is not None:
                assignment = [
                    (source, list(colors), restriction)
                    for (source, _options, restriction), colors in zip(combo, chosen, strict=True)
                ]
                lost = life_loss(assignment)
                if lost and not trial.can_pay(
                    cost, life_available=max(life_available - lost, 0), spend=spend
                ):
                    continue
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
    candidates = [
        (source, _spelled_out(options), restriction)
        for source, options, restriction in _auto_tap_candidates(context, sources)
    ]
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
                life_loss=lambda assignment: _plan_life_loss(context, assignment),
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
    if any(isinstance(option, MixedProduction) for option, _restriction in alternatives):
        # A mixture is expressible as edges (`_bucket_map`), but it is still
        # branched over: tapping it makes all N mana at once, so a plan that
        # commits it is offered its whole capacity first (committed sources
        # are inserted ahead of the rest) and never taps a land beside it for
        # mana it would have floated anyway.
        return True
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
    if len(alternatives) == 1 and isinstance(alternatives[0][0], MixedProduction):
        # N mana, each its own colour: capacity N, any colour of the palette
        # for every one of them.
        mixture, restriction = alternatives[0]
        slot = _slot_for(restriction, registry)
        count = len(mixture)
        return {
            (color, snow, slot, NO_SPEND_EFFECT, NOT_RETAINED): count for color in mixture.palette
        }, count
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
        if isinstance(option, MixedProduction):
            spent: dict[Color, int] = {}
            for bucket, amount in used.items():
                spent[bucket[0]] = spent.get(bucket[0], 0) + amount
            return option.split_from(spent), restriction
        return list(option), restriction
    for option, restriction in alternatives:
        slot = _slot_for(restriction, registry)
        if used.get((option[0], snow, slot, NO_SPEND_EFFECT, NOT_RETAINED), 0) > 0:
            return list(option), restriction
    return [], None


def _exotic_choice_combos(
    options: Sequence[PaymentOption],
    exotic: list[tuple[CardState, list[_Alternative]]],
    game: Any = None,
) -> Iterable[tuple[_Alternative | None, ...]]:
    """Every "not used / used for this alternative" reading of `exotic`, in
    `product` order (all-`None` first), minus three kinds of redundant reading.

    A group-granted multi-mana ability ("Lands you control have "{T}: Add two
    mana of any one color ..."", Resonating Lute) makes every land exotic at
    once, and the plain product over them is exponential in the number of
    lands. So:

    1. Alternatives of one source that make the same amount of one colour
       nobody in `options` asks for, under the same restriction, can only
       ever pay generic mana, so they are interchangeable - the first one is
       kept.
    2. Exotic sources with identical (so pruned) alternatives and the same
       snow status are interchangeable, and one assignment per multiset of
       choices is kept (a non-decreasing choice index across the group, which
       for a group of one is exactly the old order).
    3. A reading that commits more exotic sources than `options` has mana to
       pay is never generated - each committed source that contributes pays
       at least one mana, and one that contributes nothing is left out of the
       plan anyway, so such a reading can never produce a plan the smaller
       readings do not.

    With no two identical exotic sources and nothing to prune, this yields
    exactly `product(*[[None, *alternatives] ...])` in the same order.
    """
    owed = sum(option.generic + (1 if option.color is not None else 0) for option in options)
    wanted = {option.color for option in options if option.color is not None}
    groups: list[tuple[list[_Alternative], list[int]]] = []
    for position, (source, alternatives) in enumerate(exotic):
        pruned: list[_Alternative] = []
        for option, restriction in alternatives:
            colors = set(option)
            if (
                not isinstance(option, MixedProduction)
                and len(colors) == 1
                and not colors & wanted
                and any(
                    not isinstance(kept, MixedProduction)
                    and len(kept) == len(option)
                    and kept_restriction == restriction
                    and len(set(kept)) == 1
                    and not set(kept) & wanted
                    for kept, kept_restriction in pruned
                )
            ):
                continue
            pruned.append((option, restriction))
        snow = is_snow_source(source, game)
        for group_alternatives, members in groups:
            first = exotic[members[0]][0]
            if group_alternatives == pruned and is_snow_source(first, game) == snow:
                members.append(position)
                break
        else:
            groups.append((pruned, [position]))

    def group_picks(size: int, choices: int, budget: int) -> Iterable[tuple[int, ...]]:
        """Non-decreasing index tuples (0 = unused) with at most `budget`
        non-zero entries, in `combinations_with_replacement` order."""
        for picks in combinations_with_replacement(range(choices + 1), size):
            if size - picks.count(0) <= budget:
                yield picks

    def walk(
        index: int, budget: int, combo: list[_Alternative | None]
    ) -> Iterable[tuple[_Alternative | None, ...]]:
        if index == len(groups):
            yield tuple(combo)
            return
        alternatives, members = groups[index]
        if budget == 0:
            yield from walk(index + 1, 0, combo)
            return
        for picks in group_picks(len(members), len(alternatives), budget):
            used = 0
            for position, pick in zip(members, picks, strict=True):
                combo[position] = alternatives[pick - 1] if pick else None
                used += 1 if pick else 0
            yield from walk(index + 1, budget - used, combo)
        for position in members:
            combo[position] = None

    yield from walk(0, owed, [None] * len(exotic))


def _best_flow_plan(
    options: Sequence[PaymentOption],
    simple: list[tuple[CardState, list[_Alternative]]],
    exotic: list[tuple[CardState, list[_Alternative]]],
    pool_buckets: dict[_Bucket, int],
    pool_registry: list[ManaRestriction],
    game: Any = None,
    *,
    any_color: bool = False,
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
    for choice_combo in _exotic_choice_combos(options, exotic, game):
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
        demands = _demand_list(options, all_buckets, any_color=any_color)
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
    sources = list(sources)
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
        plan = _best_flow_plan(
            options,
            simple,
            exotic,
            pool_buckets,
            pool_registry,
            context.game,
            any_color=context.spend is not None and context.spend.any_color,
        )
        if plan is not None:
            if life and life > life_available - _plan_life_loss(context, plan):
                # CR 601.2g-h: this plan's own mana abilities deal damage
                # (Ancient Tomb) before the Phyrexian life is paid, leaving
                # too little of it (CR 119.4). The flow network has no notion
                # of life at all, so a plan that avoids those sources is
                # searched for by the exhaustive solver instead - a rare
                # branch (life-paid Phyrexian *and* a self-damaging source
                # in the chosen plan), so its cost is only paid here.
                return _solve_auto_tap_brute_force(
                    context,
                    sources,
                    owed=owed,
                    base_floating=base_floating,
                    base_snow=base_snow,
                    base_restricted=base_restricted,
                    life_available=life_available,
                )
            return _prefer_painless_mana(
                context,
                plan,
                owed=owed,
                base_floating=base_floating,
                base_snow=base_snow,
                base_restricted=base_restricted,
                life_available=life_available,
            )
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


#: K'rrik, Son of Yawgmoth: "For each {B} in a cost, you may pay 2 life rather
#: than pay that mana." - the controller's every {B} is payable as a Phyrexian
#: {B/P} would be (CR 107.4f), a way of paying, not a change to the cost.
_BLACK_MANA_AS_LIFE_RE = re.compile(
    r"^for each \{B\} in a cost, you may pay 2 life rather than pay that mana\.?$", re.IGNORECASE
)


def treats_black_mana_as_life(game: Any, payer: str | None) -> bool:
    """Whether `payer` controls a permanent whose static ability reads
    `_BLACK_MANA_AS_LIFE_RE`."""
    if game is None or payer is None:
        return False
    board = game.computed_board()
    return any(
        _BLACK_MANA_AS_LIFE_RE.match(line.strip())
        for permanent in game.permanents_controlled_by(payer)
        for line in board.of(permanent).abilities
    )


def reads_black_mana_as_life_line(text: str) -> bool:
    """What `support.py` asks before crediting the line."""
    return _BLACK_MANA_AS_LIFE_RE.match(text.strip()) is not None


def payable_with_black_as_life(cost: ManaCost, game: Any, payer: str | None) -> ManaCost:
    """`cost` with each plain {B} read as {B/P} when `payer`'s permanents say
    so (K'rrik), else `cost` itself."""
    black = Color.BLACK
    if not any(
        symbol.kind is SymbolKind.COLORED and symbol.colors == (black,) for symbol in cost.symbols
    ) or not treats_black_mana_as_life(game, payer):
        return cost
    return ManaCost(
        symbols=tuple(
            ManaSymbol(kind=SymbolKind.PHYREXIAN, colors=(black,))
            if symbol.kind is SymbolKind.COLORED and symbol.colors == (black,)
            else symbol
            for symbol in cost.symbols
        )
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
    cost = payable_with_black_as_life(cost, game, payer)
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


_ALLOWED: dict[CostStep, frozenset[CostStep]] = {
    CostStep.PENDING: frozenset({CostStep.TAPPING, CostStep.POOLED, CostStep.CANCELLED}),
    CostStep.TAPPING: frozenset({CostStep.TAPPING, CostStep.POOLED, CostStep.CANCELLED}),
    CostStep.POOLED: frozenset({CostStep.TAPPING, CostStep.PAID, CostStep.CANCELLED}),
    CostStep.PAID: frozenset(),
    CostStep.CANCELLED: frozenset(),
}


#: "Pay `<count>` `{symbol}`" - a spelled-out (or digit) count naming how many
#: of one repeatable mana symbol to pay: Emrakul, the World Anew's own
#: "Madness—Pay six {C}." (CR 107.4c's `{C}`, one colorless mana). Read by the
#: count and the symbol, never by which symbol it is or which card prints it,
#: so a spelled-out cost of any repeatable mana symbol reads exactly as that
#: many bare copies of the symbol printed in a row already do -
#: `ManaCost.try_parse` is still what says whether the symbol itself is mana
#: at all, so CR 107.14's energy symbol `{E}` (not a mana symbol - it is its
#: own thing, paid by removing an energy counter, a resource this engine does
#: not yet model) is refused here exactly as a bare "`{E}`{E}{E}`" already is,
#: rather than silently treated as three mana.
_PHRASE_PAY_REPEATED_SYMBOL = re.compile(
    rf"^pay {count_pattern('count', article=False)} (?P<symbol>\{{[^{{}}]+\}})$",
    re.IGNORECASE,
)


def pay_repeated_symbol_mana_cost(phrase: str) -> ManaCost | None:
    """`_PHRASE_PAY_REPEATED_SYMBOL`'s shape, or `None`.

    Kept apart from `cost_component_for_phrase` for the same reason
    `waterbend_mana_cost` is: this is mana, and a `CostComponent` has nowhere
    to carry mana - `TotalCost` is what does, which is why `total_cost_for_
    phrase` is where this is folded in. No other printing in this pool uses
    this shape - Emrakul, the World Anew's own Madness cost is the only one -
    so nothing else here changes behaviour; a future card spelling out any
    other mana symbol's count reads the same way this one does.
    """
    match = _PHRASE_PAY_REPEATED_SYMBOL.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    count = parse_count(match.group("count"), article=False)
    if count is None or count < 1:
        return None
    return ManaCost.try_parse(match.group("symbol") * count)


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
        for option in counted_mana_options(
            game, None, source, activation.mana, activation.mana.effective()[0]
        )[0]
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
        if behind is not None and [piece.kind for piece in behind[1].costs] != [CostKind.TAP]:
            # A tap is all this path pays (CR 602.2b): an ability whose cost
            # is more than `{T}` - Cabal Stronghold's `{3}, {T}` - is the
            # player's to activate with its whole cost (CR 605.3a), never
            # one a bare tap may stand in for.
            refusals.append(
                f'its "{behind[1].cost}" ability costs more than {{T}}; activate it to pay that'
            )
            continue
        if behind is not None:
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
        options, amount = counted_mana_options(game, context.payer, source, ability, options)
        if ability.offers(list(produces), options, any_color, amount=amount):
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


def _activation_moves_library_card(ability: Any) -> bool:
    """CR 605.1a's library criterion, asked of `models/game.py`'s own reader."""
    from ...models.game import moves_a_library_card

    return moves_a_library_card(ability)


def _activation_bookkeeping_restore(
    game: Any, key: str, activations_before: int | None, exhausted_before: set[str]
) -> None:
    """Put `Game.activations[key]` and `Game.exhausted` back as they were
    before an activation that is being reversed (CR 733.1)."""
    if activations_before is None:
        game.activations.pop(key, None)
    else:
        game.activations[key] = activations_before
    game.exhausted.intersection_update(exhausted_before)


def _mana_pool_overwrite(target: ManaPool, contents: ManaPool) -> None:
    """Give `target` exactly `contents`' mana, tags included, without
    aliasing either pool to the other."""
    copied = _copy_pool(contents)
    target.floating = copied.floating
    target.snow = copied.snow
    target.treasure = copied.treasure
    target.creature = copied.creature
    target.restricted = copied.restricted
    target.spend_effects = copied.spend_effects
    target.retained = copied.retained


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
        treasure=dict(pool.treasure),
        creature=dict(pool.creature),
        restricted=[entry.model_copy(deep=True) for entry in pool.restricted],
        spend_effects=[tagged.model_copy(deep=True) for tagged in pool.spend_effects],
        retained=[entry.model_copy(deep=True) for entry in pool.retained],
    )


def _x_share_in_colors(cost: ManaCost, x_mana: int, colors: Sequence[Color]) -> ManaCost:
    """`cost` with `x_mana` of its generic mana (X's share, "Spend only
    <colour> mana on X.") written as symbols only `colors` can pay: one colour
    is `{B}` per mana, two are `{B/R}` (CR 107.4e - each mana chosen on its
    own). A share larger than the generic mana left after reductions is cut
    to it (CR 601.2f: cost reductions take generic first)."""
    share = min(x_mana, cost.generic)
    if share <= 0 or not colors:
        return cost
    restricted = (
        ManaSymbol(kind=SymbolKind.COLORED, colors=(colors[0],))
        if len(colors) == 1
        else ManaSymbol(kind=SymbolKind.HYBRID, colors=tuple(colors))
    )
    symbols: list[ManaSymbol] = []
    left = cost.generic - share
    for symbol in cost.symbols:
        if symbol.kind is SymbolKind.GENERIC:
            continue
        symbols.append(symbol)
    if left:
        symbols.insert(0, ManaSymbol(kind=SymbolKind.GENERIC, amount=left))
    symbols.extend([restricted] * share)
    return ManaCost(symbols=tuple(symbols))


class CostPayment(EngineModel):
    """Paying one total cost, from tapping sources through to the leftover mana."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cost: ManaCost
    components: list[CostComponent] = Field(default_factory=list)
    game: Any = Field(default=None, exclude=True, repr=False)
    payer: str | None = None
    pool: ManaPool = Field(default_factory=ManaPool)
    step: CostStep = CostStep.PENDING
    paying_for: str | None = None
    """What this is the total cost of: `"spell"` while a spell is being cast
    (CR 601.2h), `"ability"` while an ability is being activated (CR 602.2b),
    None for any other payment. Every event paying it raises carries this
    (`GameEvent.during_cost_of`), which is what a trigger event's own "while
    casting a spell with emerge" / "while you're activating a craft ability"
    qualifier reads (CR 603.2)."""
    paying_for_keyword: str | None = None
    """The keyword the spell is cast with or the ability expands, lowercased
    (CR 702.119a's emerge, CR 702.167a's craft), when there is one."""
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

    x_only_colors: tuple[Color, ...] = ()
    x_mana: int = 0
    x_restriction_text: str = ""
    """"Spend only <colour> mana on X." (Consume Spirit, Crypt Rats): the colours
    allowed to pay `x_mana` of the cost's generic mana - X's share of it (CR
    107.3a, 601.2f). `mana_owed` writes that share as coloured symbols, so the
    pool is asked for exactly the mana the sentence allows and the cost itself
    (mana value, what was paid) stays the real total cost. Set by
    `restrict_x_mana`; empty for every other payment."""

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

    _nested: list[tuple["CostPayment", UUID, str, int | None, frozenset[str]]] = PrivateAttr(
        default_factory=list
    )
    """The mana abilities `activate_mana_ability` activated during this
    payment, oldest first, for CR 733.1's reversal (`_undo_nested_activations`):
    each activation's own paid payment, its source's id, its
    `Game.activations` key and that key's count and `Game.exhausted` as they
    stood before. Like `_tapped_sources` it holds live objects and does not
    survive a dump/decode round trip; a payment is never persisted
    mid-activation."""

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
            cost=payable_with_black_as_life(total.mana, game, payer),
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
        owed = (
            cost_less(self.cost, [entry.option for entry in self.substitutions])
            if self.substitutions
            else self.cost
        )
        return _x_share_in_colors(owed, self.x_mana, self.x_only_colors)

    def restrict_x_from_text(self, text: str, x_count: int, x_value: int) -> None:
        """Apply the "Spend only <colour> mana on X." sentence `text` prints, if
        it prints one: `x_count * x_value` of the cost's generic mana (X's
        share, CR 107.3a) may only be paid with mana of those colours. Nothing
        happens when X is 0, when the sentence is absent, or when this payment
        may spend mana as though it were any type (CR 609.4b), which makes
        every mana the colour asked for."""
        colors = x_spend_colours(text)
        share = x_count * x_value
        if not colors or share <= 0 or (self.spend is not None and self.spend.any_color):
            return
        sentence = SPEND_ONLY_ON_X_RE.search(text)
        assert sentence is not None
        self.x_only_colors = colors
        self.x_mana = share
        self.x_restriction_text = sentence.group(0).strip()

    def x_restriction_note(self) -> str:
        """The refusal's own explanation when X is restricted, or ""."""
        if not self.x_only_colors or not self.x_mana:
            return ""
        for_what = self.spend.name if self.spend is not None and self.spend.name else "this cost"
        return (
            f": {self.x_restriction_text} - {self.x_mana} of the mana for {for_what} pays X "
            "and only that colour may (CR 107.3a, 601.2h)"
        )

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
    def phyrexian_life_symbols_paid(self) -> int:
        """How many Phyrexian mana symbols of this cost were paid with life
        rather than mana (CR 107.4f), read off the settled payment.

        `ManaPayment.options` lines up one-to-one with `ManaCost.symbols`
        (`ManaPool.payment_for`) - each entry is which resource actually paid
        that symbol, and `PaymentOption.life` is set only for the "or 2 life"
        half of a Phyrexian symbol (never for `pay_life_cost`'s own unrelated
        additional-cost life, which is a separate `CostComponent` and never
        touches `options` at all). Counting entries rather than dividing
        `life_paid` by `PHYREXIAN_LIFE` is deliberate: it stays correct symbol
        by symbol even if a future printing ever priced one differently from
        another, where a single pooled total could not be split back apart.

        `None` before the payment is settled (`mana_payment` is only set once
        `pay()` has actually run, in `_pay_impl`) reads as 0 - "nothing paid
        yet" is not "nothing paid with life", but it is exactly what CR
        702.150a's compleated needs to see for a payment nobody has finished.
        """
        if self.mana_payment is None:
            return 0
        return sum(1 for option in self.mana_payment.options if option.life)

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
        if self.spend is not None and self.spend.treasure_only and not is_treasure_source(
            source, self.game
        ):
            raise ValueError(
                f"{source.name} is not a Treasure, and only mana produced by Treasures "
                "may be spent to cast this spell this way (CR 106.6)"
            )
        activated, refusals, produces, triggered_colors = _activated_mana_ability_with_triggers(
            self, source, produces, restriction
        )
        production_effects = _mana_production_effects(self.game)
        if activated is None and production_effects:
            # A plan from the auto-tap solver names the *replaced* production
            # (CR 106.12b) - one {C} for Ancient Tomb under Damping Sphere -
            # which no ability of the source prints; find the production the
            # ability makes that is replaced into it.
            unreplaced = _unreplaced_production(self, source, produces, production_effects)
            if unreplaced is not None:
                activated, refusals, produces, triggered_colors = (
                    _activated_mana_ability_with_triggers(self, source, unreplaced, restriction)
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
        if self.game is not None:
            # Tapping for mana is tapping (CR 106.12, CR 701.26a): the source
            # became tapped, whatever else its ability goes on to do.
            self.game.emit_became_tapped(source)
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
        if production_effects and self.game is not None:
            # CR 106.12b: the production event is modified as the ability
            # resolves; what reaches the pool (and what "tapped for mana"
            # triggers see, CR 106.12a) is the replaced mana.
            produces = _replace_production(self, source, produces, production_effects)
        self.pool.add_all(
            produces,
            snow=is_snow_source(source, self.game),
            restriction=restriction,
            spend_effect=spend_effect,
            treasure=is_treasure_source(source, self.game),
            creature=is_creature_source(source, self.game),
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
                # CR 605.3a: the mana ability was activated, too.
                *self.game.emit(mana_ability_activated_event(source, self.game)),
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

    def activate_mana_ability(
        self,
        source: CardState,
        index: int,
        *,
        color: Color | Sequence[Color] | None = None,
        x_value: int = 0,
    ) -> ManaPool:
        """Activate `source`'s mana ability number `index` in the middle of
        this payment, whatever its cost, and put its mana into the pool.

        CR 605.3a: a player may activate a mana ability "whenever they are
        casting a spell or activating an ability that requires a mana
        payment"; CR 605.3 has it follow CR 602.2's activation rules, so its
        own cost is paid in full - Vivi Ornitier's `{0}`, Rakdos Signet's
        `{1}, {T}`, Lotus Petal's `{T}, Sacrifice this artifact`. `tap_for_mana`
        is the bare-`{T}` case of this (CR 106.12) and stays the path for it.

        The activation runs through the game's own `begin_activating` /
        `activate_ability`, so every refusal is the engine's own: an ability
        that is not a mana ability (CR 605.1a), one prohibited right now ("only
        once each turn", CR 602.5b), a colour the ability does not offer, a
        cost that cannot be paid. A mana cost on the ability is paid out of
        the mana already in this payment's pool (CR 601.2g: that pool *is* the
        player's mana pool while the payment is open) - name the sources that
        pay for it first. A refusal leaves the payment exactly as it was.

        `color` is the choice the ability offers (`Game.activate_ability`'s own
        argument), `x_value` an X its cost announces (CR 107.3a).

        CR 733.1: rewinding or cancelling this payment undoes the activation
        too - its cost is unpaid, its bookkeeping ("once each turn") taken
        back, and its mana dies with the payment's pool.
        """
        self._require_open()
        game = self.game
        if game is None or self.payer is None:
            raise ValueError("a mana ability can only be activated in a payment inside a game")
        abilities = game.activated_abilities(source)
        if not 0 <= index < len(abilities):
            raise ValueError(
                f"{source.name} has no ability {index}: it has {len(abilities)} activated "
                f"{'ability' if len(abilities) == 1 else 'abilities'}"
            )
        ability = abilities[index]
        if (
            ability.mana is None
            or ability.loyalty is not None
            or _activation_moves_library_card(ability)
        ):
            raise ValueError(
                f"{source.name}'s ability {index} ({ability.text}) is not a mana ability "
                "(CR 605.1a), so it cannot be activated while paying a cost (CR 605.3a)"
            )
        player = game.player(self.payer)
        own_pool = _copy_pool(player.mana_pool)
        key = game._activation_key(source, index)  # noqa: SLF001
        activations_before = game.activations.get(key)
        exhausted_before = set(game.exhausted)
        waiting = {id(pending) for pending in game.pending_triggers}
        # The working pool becomes the player's pool for the activation, so
        # its cost spends the mana this payment already has and its mana
        # lands beside it; the player's own pool is put back afterwards.
        _mana_pool_overwrite(player.mana_pool, self.pool)
        inner: CostPayment | None = None
        game._holding_mana_triggers = True  # noqa: SLF001
        try:
            inner = game.begin_activating(source, index, self.payer, x_value=x_value)
            if inner.shortfall:
                raise ValueError(
                    f"{source.name}'s mana ability costs {inner.cost}, and the mana already "
                    f"in the pool cannot pay it - activate the sources that pay for it first "
                    "(CR 605.3a, CR 601.2g)"
                )
            inner.pay()
            game.activate_ability(source, index, self.payer, color=color, x_value=x_value)
        except ValueError:
            if inner is not None:
                inner.rewind()
            _activation_bookkeeping_restore(game, key, activations_before, exhausted_before)
            _mana_pool_overwrite(player.mana_pool, own_pool)
            self._register_pool()
            raise
        finally:
            game._holding_mana_triggers = False  # noqa: SLF001
        self._transition(CostStep.TAPPING)
        _mana_pool_overwrite(self.pool, player.mana_pool)
        _mana_pool_overwrite(player.mana_pool, own_pool)
        self._register_pool()
        assert inner is not None
        self._nested.append(
            (inner, source.id, key, activations_before, frozenset(exhausted_before))
        )
        self.triggers_caused.extend(
            pending.id for pending in game.pending_triggers if id(pending) not in waiting
        )
        return self.pool

    @property
    def mana_abilities_activated(self) -> list[UUID]:
        """The sources whose mana abilities `activate_mana_ability` activated
        during this payment, oldest first - the any-cost twin of
        `tapped_for_mana`, for a caller reporting what paid."""
        return [source_id for _payment, source_id, *_rest in self._nested]

    def _undo_nested_activations(self) -> None:
        """CR 733.1: reverse every `activate_mana_ability` this payment made,
        newest first - each activation's own payment is rewound (its cost
        given back) and its bookkeeping restored. The player's pool is left
        as it was; the caller restores it from its own snapshot."""
        if not self._nested or self.game is None or self.payer is None:
            self._nested = []
            return
        player = self.game.player(self.payer)
        own_pool = _copy_pool(player.mana_pool)
        for inner, _source_id, key, activations_before, exhausted_before in reversed(self._nested):
            inner.rewind()
            _activation_bookkeeping_restore(
                self.game, key, activations_before, set(exhausted_before)
            )
        _mana_pool_overwrite(player.mana_pool, own_pool)
        self._nested = []

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
            raise ValueError(
                f"pool {self.pool.floating} cannot pay {owed}"
                f"{self._blocked()}{self.x_restriction_note()}"
            )
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
            with (
                self.game._id_allocator_scope(),
                self.game.paying_cost_of(self.paying_for, self.paying_for_keyword, self.payer),
            ):
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
        pool.treasure = dict(self.pool.treasure)
        pool.creature = dict(self.pool.creature)
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
        pool.treasure = dict(self._preexisting.treasure)
        pool.creature = dict(self._preexisting.creature)
        pool.restricted = [entry.model_copy(deep=True) for entry in self._preexisting.restricted]
        pool.retained = [entry.model_copy(deep=True) for entry in self._preexisting.retained]

    def _undo_everything(self) -> None:
        self._undo_nested_activations()
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


from ..modes import SPEND_ONLY_ON_X_RE  # noqa: E402
from ._common import _PHRASE_PAY_LIFE, _QUALITY_CONNECTORS, _TYPE_WORDS  # noqa: E402
from .components import ComponentKind, MixedProduction, cost_less, pay_life_cost  # noqa: E402
from .text import x_spend_colours  # noqa: E402
