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
from collections.abc import Iterable, Sequence
from enum import StrEnum
from itertools import combinations, product
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import CardState, ChoiceKind, Counter, CounterKind
from ..models.mana import (
    ManaCost,
    ManaPayment,
    ManaPool,
    ManaRestriction,
    ManaSpend,
    ManaSymbol,
    PaymentOption,
    SpendClause,
    SpendPurpose,
    SymbolKind,
)
from ..models.zone import Zone
from .abilities import (
    ActivatedAbility,
    CostKind,
    ManaAbility,
    TriggerEvent,
    granted_mana_abilities,
    intrinsic_land_ability,
    parse_abilities,
    parse_mana_abilities,
)
from .combat import Keyword, has_keyword
from .triggers import (
    GameEvent,
    activated_abilities_of,
    granted_activated_abilities_of,
    is_ability,
    tapped_for_mana_event,
)


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


def is_snow_source(source: CardState) -> bool:
    """Whether mana from this permanent is snow mana (CR 106.3, 205.4g).

    Read off the printed type line, since nothing in this engine grants or
    removes a supertype yet.
    """
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


def _activations_of(source: CardState) -> list[ActivatedAbility]:
    """`Game.activated_abilities(source)`'s own list, rebuilt from the same two
    functions in the same order - printed abilities of the up face first
    (CR 712.8d/712.8e/712.8f), then `CardState.granted_ability_texts`'s.

    Rebuilt rather than asked of the game because a `CostPayment` may have no
    game behind it, and because an index into this list is what
    `Game.why_cannot_activate` takes: same order, same index.
    """
    return activated_abilities_of(
        source.card, source.up_face_name
    ) + granted_activated_abilities_of(source.granted_ability_texts)


def tappable_mana_activations(source: CardState) -> list[tuple[int, ActivatedAbility]]:
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
    """
    return [
        (index, ability)
        for index, ability in enumerate(_activations_of(source))
        if ability.mana is not None and [piece.kind for piece in ability.costs] == [CostKind.TAP]
    ]


def _activation_refused(payment: "CostPayment", source: CardState, index: int) -> str | None:
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

#: `among legendary creatures and planeswalkers you control` (Mox Amber). The
#: quality is left as words for `_among_colors` to read, since the same
#: sentence is printed with other qualities on cards outside this pool.
_ANY_COLOR_AMONG = re.compile(r"\bamong (?P<quality>[a-z ,]+?) you control\b", re.IGNORECASE)


def _among_colors(
    effect: str, payment: "CostPayment", source: CardState
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
    match = _ANY_COLOR_AMONG.search(effect)
    if match is None:
        return None
    game = payment.game
    controller = source.controller or payment.payer
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

    colors: set[Color] = set()
    for state in game.permanents_controlled_by(controller):
        if not any(type_ in state.types for type_ in types):
            continue
        if not all(supertype in state.supertypes for supertype in supertypes):
            continue
        colors.update(color for color in state.colors if color is not Color.COLORLESS)
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
# Four printings in `tests/fixtures/cards/` carry one:
#
#   Shang-Chi, Master of Kung Fu
#     "Spend this mana only to activate abilities of creature sources."
#   Eldrazi Temple
#     "Spend this mana only to cast colorless Eldrazi spells or activate
#      abilities of colorless Eldrazi."
#   Cavern of Souls
#     "Spend this mana only to cast a creature spell of the chosen type, and
#      that spell can't be countered."
#   Delighted Halfling
#     "Spend this mana only to cast a legendary spell, and that spell can't be
#      countered."
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
#: "cast a creature spell of the chosen type", "cast colorless Eldrazi spells".
_SPEND_CAST_CLAUSE = re.compile(
    r"^cast (?P<quality>.*?) ?spells?(?P<chosen> of the chosen type)?$", re.IGNORECASE
)
#: "activate abilities of creature sources", "activate abilities of colorless
#: Eldrazi". The trailing "sources" is WOTC's own word for "the object the
#: ability is on" and narrows nothing further.
_SPEND_ACTIVATE_CLAUSE = re.compile(
    r"^activate abilities of (?P<quality>.+?)(?: sources)?$", re.IGNORECASE
)
#: A rider joined onto the restriction sentence with ", and" - the
#: can't-be-countered half of Cavern of Souls and Delighted Halfling. No
#: printing joins two *alternatives* that way (they use "or"), so everything
#: from the first ", and" onwards is a different clause of the ability and not
#: part of what the mana may pay for.
_SPEND_RIDER = ", and "

_SUPERTYPE_WORDS = {supertype.value: supertype for supertype in Supertype}
_TYPE_WORDS = {type_.value: type_ for type_ in Type}


def _spend_clause(
    phrase: str, purpose: SpendPurpose, chosen_type: str | None
) -> SpendClause | None:
    """Turn one quality phrase into a `SpendClause`, or None if unreadable.

    The vocabulary is deliberately closed: an article, "colorless", a printed
    supertype, a printed card type, or a capitalised noun read as a subtype
    (CR 205.3 subtypes are always capitalised on a type line, which is what
    tells "Eldrazi" apart from "colorless"). A word outside it fails the whole
    clause rather than being dropped, because a dropped word is a restriction
    that is quietly broader than the card.
    """
    types: set[Type] = set()
    subtypes: set[str] = set()
    supertypes: set[Supertype] = set()
    colorless = False

    for word in phrase.split():
        stripped = word.strip(",")
        lowered = stripped.lower()
        if lowered in {"a", "an", "the"}:
            continue
        if lowered == "colorless":
            colorless = True
        elif lowered in _SUPERTYPE_WORDS:
            supertypes.add(_SUPERTYPE_WORDS[lowered])
        elif lowered.rstrip("s") in _TYPE_WORDS:
            types.add(_TYPE_WORDS[lowered.rstrip("s")])
        elif stripped[:1].isupper():
            subtypes.add(lowered)
        else:
            return None

    if chosen_type is not None:
        subtypes.add(chosen_type.lower())

    return SpendClause(
        purpose=purpose,
        types=frozenset(types),
        subtypes=frozenset(subtypes),
        supertypes=frozenset(supertypes),
        colorless=colorless,
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
    """
    match = _SPEND_RESTRICTION.search(effect)
    if match is None:
        if _SPEND_RESTRICTION_SIGNAL.search(effect):
            return ManaRestriction(text=effect.strip())
        return None

    text = match.group(0)
    what = match.group("what").partition(_SPEND_RIDER)[0].strip()

    clauses: list[SpendClause] = []
    for alternative in what.split(" or "):
        phrase = alternative.strip()
        cast = _SPEND_CAST_CLAUSE.match(phrase)
        activate = _SPEND_ACTIVATE_CLAUSE.match(phrase)
        if cast is not None:
            chosen = _chosen_creature_type(source) if cast.group("chosen") else None
            if cast.group("chosen") and chosen is None:
                return ManaRestriction(text=text)
            clause = _spend_clause(cast.group("quality"), SpendPurpose.CAST_SPELL, chosen)
        elif activate is not None:
            clause = _spend_clause(activate.group("quality"), SpendPurpose.ACTIVATE_ABILITY, None)
        else:
            return ManaRestriction(text=text)
        if clause is None:
            return ManaRestriction(text=text)
        clauses.append(clause)

    return ManaRestriction(text=text, clauses=tuple(clauses))


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
    payment: "CostPayment", source: CardState
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


#: One thing `auto_tap` may tap: the permanent, what its chosen ability would
#: add right now, and the CR 106.6 restriction that mana would carry.
_Candidate = tuple[CardState, list[list[Color]], ManaRestriction | None]


def _auto_tap_candidates(payment: "CostPayment", sources: Iterable[CardState]) -> list[_Candidate]:
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
    candidates: list[tuple[CardState, list[list[Color]], ManaRestriction | None, bool]] = []
    for source in sources:
        if source.zone is not Zone.BATTLEFIELD or source.tapped:
            continue
        if payment.payer is not None and source.controller not in (None, payment.payer):
            continue
        if not can_tap_for_mana(source, payment.game):
            continue
        land_types, own_counters, has_imprinted_card = _mana_context(payment, source)
        for index, activation in tappable_mana_activations(source):
            ability = activation.mana
            if ability is None:
                continue
            if _activation_refused(payment, source, index) is not None:
                continue
            printed = spend_restriction(activation.effect)
            restriction = spend_restriction(printed.text, source) if printed is not None else None
            if restriction is not None and not restriction.allows(payment.spend):
                continue
            options, any_color = ability.effective(land_types, own_counters, has_imprinted_card)
            options, any_color = _narrow_to_defined_colors(
                options, any_color, _among_colors(activation.effect, payment, source)
            )
            if not options:
                continue
            candidates.append((source, options, restriction, any_color))
    # A restricted ability first among a source's own abilities, so the mana
    # that can do less is the mana spent - the same preference `ManaPool._buckets`
    # applies inside the pool, applied here to which ability is activated.
    candidates.sort(key=lambda item: (_flexibility(item[1], item[3]), item[2] is None))
    return [(source, options, restriction) for source, options, restriction, _any in candidates]


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
        if payment.payer is not None and source.controller not in (None, payment.payer):
            continue
        if not can_tap_for_mana(source, payment.game):
            continue
        if free_tap_mana_abilities(source.card, source.up_face_name):
            continue
        up_face_name = source.up_face_name
        for ability in parse_abilities(source.card):
            if not isinstance(ability, ActivatedAbility) or ability.mana is None:
                continue
            if up_face_name is not None and ability.face != up_face_name:
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


_OBJECT_KINDS = frozenset(
    {
        ComponentKind.TAP,
        ComponentKind.SACRIFICE,
        ComponentKind.DISCARD,
        ComponentKind.EXILE,
        ComponentKind.REMOVE_COUNTERS,
        ComponentKind.PLACE_COUNTERS,
        ComponentKind.EXERT,
    }
)


class CardRequirement(BaseModel):
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
    description: str = ""
    """The phrase this was read from, for the message when it is not met."""

    @property
    def is_empty(self) -> bool:
        return not (
            self.colors or self.types or self.subtypes or self.supertypes or self.same_name_as
        )

    def why_not(self, card: CardState, game: Any = None, payer: str | None = None) -> str | None:
        """Why this card cannot pay, or None if it can.

        `game` and `payer` are needed only by `same_name_as`, which asks about
        the board rather than about the card alone. Without either there is no
        board to ask, and that half is skipped - a `CostPayment` with no game
        behind it cannot check any board-dependent requirement, the same
        limitation `_among_colors` documents on the mana side.
        """
        printed = card.card
        if self.colors and not set(printed.colors or []) & set(self.colors):
            wanted = "/".join(color.value for color in self.colors)
            return f"{card.name} is not {wanted}"
        if self.supertypes and not set(self.supertypes) <= set(printed.supertypes):
            wanted = " ".join(supertype.value for supertype in self.supertypes)
            return f"{card.name} is not {wanted}"
        if self.types and not set(printed.types) & set(self.types):
            wanted = "/".join(type_.value for type_ in self.types)
            return f"{card.name} is not a {wanted}"
        if self.subtypes:
            printed_subtypes = {subtype.lower() for subtype in printed.subtypes}
            if not printed_subtypes & self._wanted_subtypes():
                return f"{card.name} is not a {'/'.join(self.subtypes)}"
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


class CostComponent(BaseModel):
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

    _undo: list[tuple[CardState, dict[str, Any]]] = PrivateAttr(default_factory=list)

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
        }
        return checks[self.kind](game)

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
                # `Game.exile_permanent` already handles every zone
                # generically - battlefield departure events, token refusal
                # (CR 111.8), combat clean-up - so this delegates outright
                # rather than special-casing one more zone by hand.
                game.exile_permanent(card)
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
            for card in self.cards:
                self._remember_counters(card)
                if self.amount > 0:
                    card.counters.add(Counter.LOYALTY, self.amount)
                elif self.amount < 0:
                    card.counters.remove(Counter.LOYALTY, -self.amount)

        self.paid = True

    def unpay(self, game: Any) -> None:
        """Put back exactly what paying took, in reverse order (CR 733.1)."""
        if not self.paid:
            return

        if self.kind is ComponentKind.PAY_LIFE:
            if self.amount:
                game.player(self.payer).gain_life(self.amount)
        elif self.kind is ComponentKind.EXERT:
            # Exerting moves nothing either, and CR 701.43b lets it be exerted
            # more than once, so the rewind is simply putting the flag back.
            for card, _ in reversed(self._undo):
                card.exerted = False
        elif self.kind is ComponentKind.TAP:
            # Tapping moves nothing, so untapping is the whole rewind.
            for card, _ in reversed(self._undo):
                card.untap(exert_applies=False)
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
                card.counters = snapshot["counters"]
        else:
            for card, snapshot in reversed(self._undo):
                self._return(game, card, snapshot)

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


def tap_cost(*cards: CardState, payer: str | None = None, description: str = "") -> CostComponent:
    """Tap permanents as a cost. Already-tapped permanents cannot pay (CR 118.3)."""
    return CostComponent(
        kind=ComponentKind.TAP,
        cards=list(cards),
        required=len(cards),
        payer=payer,
        description=description,
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


class TotalCost(BaseModel):
    """What casting a spell actually costs: a mana part and everything else.

    CR 601.2f calls this the total cost. It is what an alternative cost
    replaces and what an additional cost is added to.
    """

    mana: ManaCost = Field(default_factory=ManaCost)
    components: list[CostComponent] = Field(default_factory=list)

    @classmethod
    def of(cls, mana: "ManaCost | str | None" = None, *components: CostComponent) -> "TotalCost":
        parsed = ManaCost.parse(mana) if isinstance(mana, str) else (mana or ManaCost())
        return cls(mana=parsed, components=list(components))

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


class CostModifierEffect(BaseModel):
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
_PER_SPELL_COST_INCREASE = re.compile(
    r"Each spell a player casts costs \{(?P<amount>\d+)\} more to cast for each "
    r"other spell that player has cast this turn\."
)
_SPELL_COST_FLOOR = re.compile(
    r"(?P<condition>As long as this \w+ is untapped, )?"
    r"[Ee]ach spell that would cost less than (?P<threshold>\w+) mana to cast "
    r"costs (?P<total>\w+) mana to cast\."
)

#: The Medallion cycle's own template - one color, one flat amount.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
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
        threshold = _count(match.group("threshold"))
        total = _count(match.group("total"))
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


class CostModifierNotice(BaseModel):
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


class AlternativeCostOffer(BaseModel):
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
_STATIC_FREE_CAST = re.compile(
    r"^You may cast (?P<what>[\w' -]*?spells?) from your (?P<zone>hand|graveyard) "
    r"without paying (?:its|their) mana costs?\.$",
    re.IGNORECASE,
)


class StaticFreeCastGrant(BaseModel):
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
    return StaticFreeCastGrant(zone=zone, type_word=qualifier or None)


# --------------------------------------------------------------------------
# Reading a printed cost phrase into something payable
# --------------------------------------------------------------------------

_COUNT_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
    "colorless": Color.COLORLESS,
}

_PHRASE_PAY_LIFE = re.compile(r"^pay (?P<amount>\d+) life$", re.IGNORECASE)
#: `Exile a black card from your hand` (Force of Will) and the self-referential
#: `Exile this card from your graveyard` (Seasoned Pyromancer). CR 406.2 never
#: restricts exiling to the hand, so the zone is read off the sentence rather
#: than assumed - `exile_cost`'s default is only ever a fallback for a
#: sentence that names none.
_PHRASE_EXILE = re.compile(
    r"^exile (?:this card|(?P<count>\w+) (?P<quality>[\w ]*?)cards?)"
    r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))?$",
    re.IGNORECASE,
)
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
    r"^exile (?:this card|(?P<count>\w+) (?P<quality>[\w ]*?)cards?)"
    r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))? and pay "
    r"(?:its|their) mana cost$",
    re.IGNORECASE,
)
#: `quality`'s character class allows a comma so a disjunctive list -
#: "Sacrifice an artifact, creature, or land" (Greater Gargadon) - matches as
#: one phrase rather than being split by `_split_cost_phrase`'s own comma cut;
#: `_requirement` is what turns the list into a `CardRequirement` disjunction.
_PHRASE_SACRIFICE = re.compile(r"^sacrifice (?P<count>\w+) (?P<quality>[\w ,]+)$", re.IGNORECASE)
#: `Discard a card`, `Discard a legendary card with the same name as a
#: legendary permanent you control` (Key to the Side-Door). The same-name tail
#: is a second demand on the *same* card - CR 201.2a's "at least one name in
#: common" against something the payer controls - not a second card to choose,
#: so it becomes a nested `CardRequirement` rather than another component.
_PHRASE_DISCARD = re.compile(
    r"^discard (?P<count>\w+) (?P<quality>[\w ]*?)cards?"
    r"(?: with the same name as (?:a|an) (?P<same_name>[\w ]+?) you control)?$",
    re.IGNORECASE,
)
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
    rf"^put (?P<count>\w+) (?P<kind>[\w+/−-]+) counters? on {_COUNTER_SELF_SUBJECT}$",
    re.IGNORECASE,
)
_PHRASE_REMOVE_COUNTERS = re.compile(
    rf"^remove (?P<count>\w+) (?P<kind>[\w+/−-]+) counters? from {_COUNTER_SELF_SUBJECT}$",
    re.IGNORECASE,
)


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


def _count(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return _COUNT_WORDS.get(word.lower())


#: Connector words a comma-and-"or" (or "and") list of card types leaves
#: between its items - "an artifact, creature, or land" - that name nothing
#: themselves and are skipped rather than treated as an unread word.
_QUALITY_CONNECTORS = {"or", "and"}


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
        return pay_life_cost(int(life.group("amount")), payer, description=text)

    if _PHRASE_EXERT_SELF.match(text):
        # The permanent exerted is the one whose ability this is, and only the
        # caller knows which that is, so the component is built empty and
        # correctly refuses to be paid until the card is filled in (CR 118.3).
        return exert_cost(payer=payer, required=1, description=text)

    place = _PHRASE_PLACE_COUNTERS.match(text)
    if place is not None:
        count = _count(place.group("count"))
        if count is None:
            return None
        kind = _counter_kind_word(place.group("kind"))
        return place_counters_cost(None, count, counter_kind=kind, payer=payer, description=text)

    remove_counters = _PHRASE_REMOVE_COUNTERS.match(text)
    if remove_counters is not None:
        count = _count(remove_counters.group("count"))
        if count is None:
            return None
        kind = _counter_kind_word(remove_counters.group("kind"))
        return remove_counters_cost(None, count, counter_kind=kind, payer=payer, description=text)

    exile_and_pay = _PHRASE_EXILE_AND_PAY_MANA_COST.match(text)
    if exile_and_pay is not None:
        zone = _ZONE_WORDS.get((exile_and_pay.group("zone") or "graveyard").lower(), Zone.GRAVEYARD)
        count = _count(exile_and_pay.group("count"))
        requirement = _requirement(exile_and_pay.group("quality") or "")
        if count is None or requirement is None:
            return None
        return exile_and_pay_mana_cost_cost(
            payer=payer, required=count, description=text, zone=zone, requirement=requirement
        )

    exile = _PHRASE_EXILE.match(text)
    if exile is not None:
        zone = _ZONE_WORDS.get((exile.group("zone") or "hand").lower(), Zone.HAND)
        if exile.group("count") is None:
            # "Exile this card [from your graveyard]": CR 700.7's self-
            # reference, so there is nothing to choose - only the caller
            # knows which permanent this is, same as `_PHRASE_EXERT_SELF`.
            return exile_cost(payer=payer, required=1, description=text, zone=zone)
        count = _count(exile.group("count"))
        requirement = _requirement(exile.group("quality"))
        if count is None or requirement is None:
            return None
        component = exile_cost(payer=payer, required=count, description=text, zone=zone)
        component.requirement = requirement
        return component

    discard = _PHRASE_DISCARD.match(text)
    if discard is not None:
        count = _count(discard.group("count"))
        requirement = _requirement(discard.group("quality"))
        if count is None or requirement is None:
            return None
        if discard.group("same_name") is not None:
            same_name = _controlled_requirement(discard.group("same_name"))
            if same_name is None:
                return None
            requirement.same_name_as = same_name
        component = discard_cost(payer=payer, required=count, description=text)
        component.requirement = requirement
        return component

    sacrifice = _PHRASE_SACRIFICE.match(text)
    if sacrifice is not None:
        count = _count(sacrifice.group("count"))
        requirement = _requirement(sacrifice.group("quality"))
        if count is None or requirement is None:
            return None
        component = sacrifice_cost(payer=payer, required=count, description=text)
        component.requirement = requirement
        return component

    return None


def total_cost_for_phrase(phrase: str, payer: str | None = None) -> TotalCost | None:
    """A whole printed cost, mana or otherwise, as a `TotalCost`.

    `Flashback {2}{R}` is mana; `Evoke—Exile a black card from your hand.` is a
    component; a comma-separated phrase can be both.
    """
    mana = ManaCost()
    components: list[CostComponent] = []
    for part in _split_cost_phrase(phrase):
        if _ONLY_MANA.match(part):
            mana = mana.plus(ManaCost.parse(part))
            continue
        component = cost_component_for_phrase(part, payer)
        if component is None:
            return None
        components.append(component)
    return TotalCost(mana=mana, components=components)


_ONLY_MANA = re.compile(r"^(?:\{[^{}]+\}|\s)+$")


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
    source: CardState, produces: Sequence[Color]
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
    """
    wanted = sorted(produces)
    matches = [
        restriction
        for ability, restriction in free_tap_mana_abilities(source.card, source.up_face_name)
        for option in ability.effective()[0]
        if sorted(option) == wanted
    ]
    if not matches or any(restriction is None for restriction in matches):
        return None
    return spend_restriction(matches[0].text, source)


def _copy_pool(pool: ManaPool) -> ManaPool:
    """A detached copy of a pool, restrictions included (CR 106.6).

    A payment works on a copy so a cancellation throws away only what the
    payment itself produced; the copy has to carry the CR 106.6 tags too, or
    restricted mana the player already had would silently become spendable on
    anything the moment a payment opened.
    """
    return ManaPool(
        floating=dict(pool.floating),
        snow=dict(pool.snow),
        restricted=[entry.model_copy(deep=True) for entry in pool.restricted],
    )


class CostSubstitution(BaseModel):
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

    card: CardState
    option: PaymentOption
    component: CostComponent

    def __str__(self) -> str:
        return f"{self.card.name} pays {self.option} ({self.keyword}, {self.rule})"


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


class CostPayment(BaseModel):
    """Paying one total cost, from tapping sources through to the leftover mana."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cost: ManaCost
    components: list[CostComponent] = Field(default_factory=list)
    game: Any = Field(default=None, exclude=True, repr=False)
    payer: str | None = None
    pool: ManaPool = Field(default_factory=ManaPool)
    step: CostStep = CostStep.PENDING
    tapped_for_mana: list[CardState] = Field(default_factory=list)
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

    choices: list[int | None] | None = None
    """CR 118.13a: one pinned option per symbol of `cost`, or None to leave the
    choice to the engine. Set it to insist that Dismember's `{B/P}` is paid
    with black mana rather than with life."""

    substitutions: list[CostSubstitution] = Field(default_factory=list)
    """Symbols of `cost` that an object is paying instead of the pool.

    Convoke's creatures (CR 702.51a) and delve's exiled cards (CR 702.66a) land
    here. `mana_owed` is `cost` with them taken out, and that - not `cost` - is
    what the pool is asked to cover."""

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

    _preexisting: ManaPool | None = PrivateAttr(default=None)
    """The payer's floating mana as it stood when the payment opened, so a
    rewind (CR 733.1) can put it back after `pay` spent part of it."""

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
        payment = cls(cost=total.mana, components=components, game=game, payer=payer, spend=spend)
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
            keyword=keyword, rule=rule, card=card, option=option, component=component
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
        the cost could not be paid.
        """
        if self.game is None or self.payer is None:
            return 0
        try:
            return int(self.game.player(self.payer).life)
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

        Mana from a snow permanent (CR 205.4g) is marked as such, because `{S}`
        can only be paid with mana produced by a snow source (CR 107.4h, 106.3).

        CR 106.12a: an ability that triggers "whenever a permanent is tapped
        for mana" triggers when this mana ability resolves and produces mana -
        emitted here, the only place the engine taps a permanent for mana.

        `source` is validated here, not trusted from the caller: this is the
        one place a caller with an explicit, hand-picked source list (a
        scenario's `pay_with`, a player choosing their own sources instead of
        `auto_tap`) reaches the pool, and `auto_tap` itself is not the only
        path in. CR 712.8d/712.8e/712.8f give a double-faced permanent only
        the characteristics of the face that's up, so `produces` must be
        something a `{T}`-including mana ability *of that face* could
        actually make right now (`parse_mana_abilities` already reads only
        the up face - see its own docstring); Witch Enchanter on the
        battlefield front face up (a creature, no mana ability at all) is
        refused here even if a caller asks for Witch-Blessed Meadow's `{T}:
        Add {W}.` by name.
        """
        self._require_open()
        if not can_tap_for_mana(source, self.game):
            raise ValueError(
                f"{source.name} has not been under {source.controller or 'its controller'}'s "
                "control since their most recent turn began, so its {T} ability "
                "cannot be activated"
            )
        # Printed abilities plus `CardState.granted_ability_texts`'s own -
        # Urza's Saga chapter I's own "This Saga gains '{T}: Add {C}.'" is
        # what makes this second half necessary; see `granted_mana_
        # abilities`'s own docstring.
        abilities = parse_mana_abilities(source.card, source.up_face_name) + granted_mana_abilities(
            source.granted_ability_texts
        )
        if not abilities:
            raise ValueError(
                f"{source.name} has no {{T}} mana ability on the face that is up "
                "and cannot be tapped for mana"
            )
        land_types, own_counters, has_imprinted_card = _mana_context(self, source)
        wanted = sorted(produces)
        refusals: list[str] = []
        payable = False
        activations = _activations_of(source)
        for ability in abilities:
            behind = _activation_behind(activations, ability)
            effect = behind[1].effect if behind is not None else ""
            if behind is not None and [piece.kind for piece in behind[1].costs] == [CostKind.TAP]:
                # CR 602.5, asked of the ability actually being activated: a
                # prohibited activation is refused however the source was
                # chosen. Only a bare-`{T}` ability is asked, because that is
                # the only shape this path claims to be activating in full -
                # anything with a further cost was never paid for here.
                refused = _activation_refused(self, source, behind[0])
                if refused is not None:
                    refusals.append(refused)
                    continue
            options, _any_color = _narrow_to_defined_colors(
                ability.effective(land_types, own_counters, has_imprinted_card)[0],
                False,
                _among_colors(effect, self, source),
            )
            if any(sorted(option) == wanted for option in options):
                payable = True
                break
        if not payable:
            made = "".join(f"{{{color.value}}}" for color in produces) or "no mana"
            if refusals:
                raise ValueError(
                    f"{source.name} cannot be tapped to add {made}: {'; '.join(refusals)}"
                )
            raise ValueError(f"{source.name} cannot be tapped to add {made}")
        self._transition(CostStep.TAPPING)

        source.tap()
        self.tapped_for_mana.append(source)
        if restriction is INFER_RESTRICTION:
            restriction = restriction_for_production(source, produces)
        self.pool.add_all(produces, snow=is_snow_source(source), restriction=restriction)
        if self.game is not None:
            triggered = self.game.emit(tapped_for_mana_event(source, self.game))
            self.triggers_caused.extend(ability.id for ability in triggered)
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
        """
        self._require_open()
        if not self.shortfall:
            return []

        sources = list(sources)
        candidates = _auto_tap_candidates(self, sources)
        base_floating = dict(self.pool.floating)
        base_snow = dict(self.pool.snow)
        base_restricted = [entry.model_copy(deep=True) for entry in self.pool.restricted]
        owed = self.mana_owed
        max_size = min(len(candidates), max(1, owed.converted))

        for size in range(1, max_size + 1):
            for combo in combinations(candidates, size):
                if len({id(source) for source, _o, _r in combo}) != len(combo):
                    # A source with both a restricted and an unrestricted
                    # ability appears once per ability; it still has only one
                    # `{T}` to spend (CR 118.3: a permanent already tapped
                    # cannot pay a cost that taps it), so a combination naming
                    # it twice is not a legal plan.
                    continue
                plan = _solve_colours(
                    combo,
                    base_floating,
                    base_snow,
                    owed,
                    self.life_available,
                    self.spend,
                    base_restricted,
                )
                if plan is not None:
                    chosen = {id(source): restriction for source, _o, restriction in combo}
                    for source, colors in plan:
                        self.tap_for_mana(source, colors, chosen[id(source)])
                    return [source for source, _ in plan]

        raise ValueError(_unpayable_cost_message(self, sources))

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
        """
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
        components = [*self.components, *([life] if life is not None else [])]
        if life is not None:
            owed = life.why_not(self.game)
            if owed is not None:
                raise ValueError(owed)

        # Pay first: a pool that falls short leaves the machine untouched, so the
        # caller can tap another source and try again.
        floating = dict(self.pool.floating)
        snow = dict(self.pool.snow)
        restricted = [entry.model_copy(deep=True) for entry in self.pool.restricted]
        self.pool.pay(self.mana_owed, payment=mana_payment)

        paid: list[CostComponent] = []
        try:
            for component in components:
                component.pay(self.game)
                paid.append(component)
        except Exception:
            for component in reversed(paid):
                component.unpay(self.game)
            self.pool.floating = floating
            self.pool.snow = snow
            self.pool.restricted = restricted
            raise

        if life is not None:
            self.components.append(life)
        self.mana_payment = mana_payment
        self._transition(CostStep.PAID)
        self._write_back_remainder()
        self.overflow = self.pool
        return self.overflow

    def cancel(self) -> None:
        """Rewind: undo every component paid, untap the mana sources, empty the pool.

        The payer's own floating mana needs no restoring here: the payment
        worked on a copy, so their pool was never touched (see
        `_seed_payer_pool`).
        """
        self._require_open()
        self._undo_everything()
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

    def _restore_payer_pool(self) -> None:
        """Put the payer's floating mana back the way it was before payment.

        The PAID half of CR 733.1's reversal: `pay` replaced the pool with the
        remainder, which spent whatever pre-existing mana the payment used, so
        undoing the whole action puts that mana back.
        """
        if self._preexisting is None or self.game is None or self.payer is None:
            return
        try:
            pool = self.game.player(self.payer).mana_pool
        except (KeyError, ValueError, AttributeError):
            return
        pool.floating = dict(self._preexisting.floating)
        pool.snow = dict(self._preexisting.snow)
        pool.restricted = [entry.model_copy(deep=True) for entry in self._preexisting.restricted]

    def _undo_everything(self) -> None:
        for component in reversed(self.components):
            component.unpay(self.game)
        for source in self.tapped_for_mana:
            source.untap()
        self.tapped_for_mana = []
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
