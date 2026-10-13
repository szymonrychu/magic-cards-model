import re
from random import Random
from typing import TYPE_CHECKING, Any

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import canonical_subtype
from ...models.card import Type
from ...models.card_state import (
    CardState,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    parse_count,
    parse_quantity,
    quantity_pattern,
)
from ..abilities import (
    TriggerEvent,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    ANAPHORIC_TIMING_STEPS,
    DelayedBlinkReturnWithRider,
    DelayedTrigger,
    ReturnEachExiledToBattlefieldUnderOwner,
    ReturnRiderCounter,
    ReturnSubjectFromGraveyardWithCounters,
    ReturnSubjectToBattlefieldUnderOwner,
    StaticPrisonReturn,
    anaphoric_delayed_trigger,
    parse_anaphoric_delayed_clause,
    return_subject_to_hand,
)
from ..layers import (
    CLOSED_SUBTYPE_LISTS,
    ContinuousEffect,
    Duration,
    Layer,
    SetTypesAndSubtypes,
    Sublayer,
    _only,
    add_subtype,
    grant_ability,
    lose_all_abilities,
    only_this_incarnation,
    set_power_toughness,
    split_and_validate_keywords,
)
from ..targeting import (
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
    from ..layers import Modification
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from ._common import AbilityEffect, Effect, TargetedClause, _CreatureRider

#: The rider of a return from the graveyard that makes the card a creature it
#: may not have been - "3/3 Robot artifact creature with flying" (Brilliance
#: Unleashed), "1/1 Spirit creature with flying in addition to its other
#: types" (Abuelo's Awakening). Case-sensitive on the subtypes, the way Oracle
#: capitalises a subtype.
_RETURN_CREATURE_RIDER_RE = re.compile(
    r"^(?P<power>\d+)/(?P<toughness>\d+) (?P<subtypes>[A-Z][a-z]+(?: [A-Z][a-z]+)*) "
    r"(?P<types>(?:(?:artifact|enchantment) )*)creature"
    r"(?: with (?P<keywords>[a-z][a-z ,]*?))?(?P<in_addition> in addition to its other types)?$"
)

#: Brilliance Unleashed's second mode: "Choose target artifact card in your
#: graveyard. Return it to the battlefield if it's an artifact creature card.
#: Otherwise, return it to the battlefield and it's a 3/3 Robot artifact
#: creature with flying." - the rider applies only on the "otherwise" branch.
_CHOOSE_RETURN_OTHERWISE_CREATURE_RE = re.compile(
    r"^choose (?P<phrase>target [^.]+? card) in your graveyard\.\s*"
    r"return it to the battlefield if it'?s an? (?P<kind>[a-z ]+?) card\.\s*"
    r"otherwise, return it to the battlefield and it'?s an? (?P<rider>[^.]+?)\.?$",
    re.IGNORECASE,
)

#: Abuelo's Awakening: "Return target artifact or non-Aura enchantment card
#: from your graveyard to the battlefield with X additional +1/+1 counters on
#: it. It's a 1/1 Spirit creature with flying in addition to its other
#: types." - X already substituted (CR 107.3a).
_RETURN_THEN_ITS_A_CREATURE_RE = re.compile(
    r"^return (?P<phrase>target [^.]+? card) from your graveyard to the battlefield"
    rf"(?: with (?P<counters>{COUNT}) additional \+1/\+1 counters? on it)?\.\s*"
    r"it'?s an? (?P<rider>[^.]+?)\.?$",
    re.IGNORECASE,
)


def _read_creature_rider(text: str) -> _CreatureRider | None:
    match = _RETURN_CREATURE_RIDER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    types: list[Type] = []
    for word in match.group("types").split():
        card_type = _singular_card_type(word)
        if card_type is None:
            return None
        types.append(card_type)
    keywords: list[str] = []
    if match.group("keywords"):
        validated = split_and_validate_keywords(match.group("keywords"))
        if validated is None:
            return None
        keywords = validated
    return _CreatureRider(
        int(match.group("power")),
        int(match.group("toughness")),
        tuple(match.group("subtypes").split()),
        tuple(types),
        tuple(keywords),
        match.group("in_addition") is not None,
    )


def _return_as_creature(
    game: "Game",
    stack_object: "StackObject",
    card: CardState,
    rider: _CreatureRider | None,
    *,
    counters: int = 0,
) -> None:
    """Put `card` onto the battlefield under the resolving object's
    controller, then - as part of the same event (`Game.entering_together`)
    - make it the rider's creature: layer 4 (CR 613.1d) for the types,
    layer 6 (CR 613.1f) for the keywords, sublayer 7b (CR 613.4b) for the P/T,
    each with no duration (CR 611.2a) and keyed to this object (CR 400.7).

    CR 205.1b decides the types: "in addition to its other types" keeps
    everything; "`<creature type>` artifact creature" keeps every prior card
    type and subtype other than creature types (so the creature types are
    replaced); a bare "`<creature type>` creature" is CR 205.1a's
    replacement of the card types too."""
    from ..layers import AddSubtype, AddType, Modification, SetCreatureTypes

    controller = game.controller_of(stack_object).username
    source_name = stack_object.name
    with game.entering_together():
        game.put_onto_battlefield(card, controller)
        if card.zone is not Zone.BATTLEFIELD:
            return
        if counters:
            game.add_counters(card, "+1/+1", counters, putter=controller)
        if rider is None:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        selector = only_this_incarnation(card, card.zone_change_stamp)
        type_changes: list[Modification] = []
        if rider.in_addition:
            type_changes.extend(AddType(card_type=t) for t in (*rider.types, Type.CREATURE))
            type_changes.extend(AddSubtype(subtype=subtype) for subtype in rider.subtypes)
        elif rider.types:
            type_changes.extend(AddType(card_type=t) for t in (*rider.types, Type.CREATURE))
            type_changes.append(SetCreatureTypes(subtypes=rider.subtypes))
        else:
            type_changes.append(
                SetTypesAndSubtypes(types=(Type.CREATURE,), subtypes=rider.subtypes)
            )
        effects = [
            ContinuousEffect(
                description=f"{source_name}: {card.name} is a creature ({modification.kind})",
                layer=Layer.TYPE,
                timestamp=timestamp,
                selector=selector,
                modification=modification,
            )
            for modification in type_changes
        ]
        effects.extend(
            ContinuousEffect(
                description=f"{source_name}: {card.name} has {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in rider.keywords
        )
        effects.append(
            ContinuousEffect(
                description=f"{source_name}: {card.name} is {rider.power}/{rider.toughness}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.SET,
                timestamp=timestamp,
                selector=selector,
                modification=set_power_toughness(rider.power, rider.toughness),
            )
        )
        for built in effects:
            store.add(built, game)


@ABILITY_TEXT.rung("s14")
@SPELL_TEXT.rung("s14")
def _parse_return_as_creature_clause(text: str) -> TargetedClause | None:
    """Brilliance Unleashed's mode (`_CHOOSE_RETURN_OTHERWISE_CREATURE_RE`)
    or Abuelo's Awakening (`_RETURN_THEN_ITS_A_CREATURE_RE`), on a spell or
    an ability, or `None`. CR 608.2b: a target that has left the graveyard
    is illegal, and nothing is returned."""
    flat = " ".join(text.strip().split())
    otherwise = _CHOOSE_RETURN_OTHERWISE_CREATURE_RE.fullmatch(flat)
    then = None if otherwise else _RETURN_THEN_ITS_A_CREATURE_RE.fullmatch(flat)
    match = otherwise or then
    if match is None:
        return None
    if not _targets_understood(
        f"{match.group('phrase')} from your graveyard", battlefield_only=False
    ):
        return None
    rider = _read_creature_rider(match.group("rider"))
    if rider is None:
        return None
    exempt: tuple[Type, ...] = ()
    if otherwise is not None:
        kinds = [_singular_card_type(word) for word in otherwise.group("kind").split()]
        if not kinds or any(kind is None for kind in kinds):
            return None
        exempt = tuple(kind for kind in kinds if kind is not None)
    counters = 0
    if then is not None and then.group("counters") is not None:
        read = parse_count(then.group("counters"))
        if read is None:
            return None
        counters = read

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            already = bool(exempt) and set(exempt) <= set(target.card.types)
            _return_as_creature(
                game, stack_object, target, None if already else rider, counters=counters
            )

    return effect


#: "Return this creature to its owner's hand and create N <token descriptor>
#: token(s)[ with <tail>]." - Thopter Assembly's whole upkeep trigger, read as
#: one CR 608.2c instruction: the return, then the token creation, in printed
#: order. The token count and its own P/T, color and subtypes are read
#: through `numbers.COUNT` and `_parse_generic_token_descriptor` rather than
#: pinned to Thopter Assembly's own "five"/"1/1 colorless Thopter artifact",
#: so a future card sharing this exact self-return-and-create template with a
#: different token reads for free. The card's own name is not matched
#: literally - "this creature"/"this permanent" is CR 201.5's own shortened
#: self-reference - so nothing here is keyed to Thopter Assembly at all.
_RETURN_SELF_THEN_CREATE_TOKENS_RE = re.compile(
    r"^return this (?:creature|permanent|artifact) to its owner['’]s hand"
    r"(?:,)?\s+and\s+(?P<token_clause>create .+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s16")
def _parse_return_self_then_create_tokens_clause(text: str) -> AbilityEffect | None:
    """`_RETURN_SELF_THEN_CREATE_TOKENS_RE`'s shape - Thopter Assembly's whole
    upkeep trigger (CR 401's return, CR 111.9's token creation).

    **The intervening *if* - "if you control no Thopters other than this
    creature" (CR 603.4) - is still not modelled**, so the trigger always goes
    on the stack and this always runs, which is wrong the turn after the first
    (the new Thopters plus this one both count). Left as a documented gap,
    not attempted here - unchanged by this parser replacing the row.
    """
    match = _RETURN_SELF_THEN_CREATE_TOKENS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    token_effect = _parse_token_clause(match.group("token_clause"), for_spell=False)
    if token_effect is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.return_to_hand(source)
        token_effect(game, ability)

    return effect


#: "Return this creature to its owner's hand." - Bramble Familiar's own
#: "{1}{G}, {T}, Discard a card: ..." ability, and every other ability that
#: bounces the permanent it is printed on (CR 201.5: "this creature" is that
#: object).
_RETURN_SELF_TO_OWNERS_HAND_RE = re.compile(
    r"^return this (?:creature|permanent|artifact|enchantment|land|planeswalker|aura"
    r"|equipment|fortification|vehicle) to its owner'?s hand\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_return_self_to_owners_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_SELF_TO_OWNERS_HAND_RE`'s shape, on an ability (a spell has
    no "this creature" on the battlefield to return). The permanent must
    still be the object the ability came from: one that left the battlefield
    and came back is a new object (CR 400.7) and stays where it is, as does
    one already gone (CR 113.7a leaves the ability nothing to move)."""
    if for_spell or _RETURN_SELF_TO_OWNERS_HAND_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if (
            stack_object.source_stamp is not None
            and source.zone_change_stamp != stack_object.source_stamp
        ):
            return
        game.return_to_hand(source)

    return effect


#: A bare "shuffle" left over once `split_effect_clauses` has cut across the
#: "then" inside a search's own "..., then shuffle." - CR 608.2c's clause
#: split has no notion that this particular "then" is the tail of the
#: sentence before it (CR 701.24a) rather than a separate instruction, the
#: same way it does not know "scry 2, then draw a card" (Preordain) *is* two
#: real instructions. `_rejoin_search_clauses` tells the two apart the only
#: way available here: a bare "shuffle" clause is reattached to whatever
#: clause precedes it if and only if that clause is itself a search. Named
#: distinctly from `_parse_each_player_step`'s own `_BARE_SHUFFLES_RE`
#: further down - a different clause, read in a different context - after
#: the two collided under the same name and the second silently shadowed
#: the first at module load.
_BARE_SHUFFLE_RE = re.compile(r"shuffle", re.IGNORECASE)
_MENTIONS_SEARCH_RE = re.compile(r"\bsearch(?:es)?\b", re.IGNORECASE)
#: A split-off "put that card on top" left over once `_CLAUSE_SEPARATOR`'s
#: bare " and " has cut across "..., reveal it, then shuffle and put that
#: card on top." (Old Thrush's own ETB) the identical way it cuts across the
#: bare "then" `_BARE_SHUFFLE_RE` already reattaches above - the same one CR
#: 608.2c instruction (CR 701.24a's shuffle, followed by where the found
#: card goes), not two. `_parse_search_reveal_shuffle_top_clause`'s own
#: whole-text special case in `_parse_mixed_clauses` already reads this
#: shape when the *entire* effect is nothing else - Old Thrush's version has
#: a life-gain sentence in front of it, so that whole-text check never even
#: runs and the clause split is the only place left to put the two halves
#: back together.
_BARE_PUT_ON_TOP_RE = re.compile(
    r"put (?:it|that card|them|those cards) on top(?: of (?:your|their) library)?",
    re.IGNORECASE,
)

#: Prismatic Undercurrents' own shape: "Search your library for up to X basic
#: land cards, where X is `<expr>`. Reveal those cards, put them into your
#: hand, then shuffle." - CR 608.2c's own instruction printed as two
#: sentences instead of `_SEARCH_AND_PUT_RE`'s usual one comma-joined run
#: (Changeling Wayfinder's "..., reveal it, put it into your hand, then
#: shuffle." all in the same sentence as the search). Rejoined here into that
#: same comma-joined shape, the same reattachment `_BARE_SHUFFLE_RE`/`_BARE_
#: PUT_ON_TOP_RE` already do for a "then"-split tail, so `_SEARCH_AND_PUT_RE`
#: reads it unchanged either way.
_REVEAL_PUT_SEARCH_CONTINUATION_RE = re.compile(
    r"^reveal (?:it|them|that card|those cards), put (?:it|them|that card|those cards) "
    r"(?:into your hand|into your graveyard|onto the battlefield(?: tapped)?)"
    r"(?:, then shuffle)?$",
    re.IGNORECASE,
)


def _rejoin_search_clauses(clauses: list[str]) -> list[str]:
    """Reattach a split-off "shuffle" (or "shuffle and put ... on top") to
    the search clause it belongs to.

    "Its controller may search their library for a basic land card, put it
    onto the battlefield, then shuffle." splits into three raw clauses -
    "destroy target land", "Its controller may search ... battlefield", and
    "shuffle" - because `_CLAUSE_SEPARATOR` treats every "then" alike. Only the
    last two are one CR 608.2c instruction; put back together, the merged
    clause is exactly what `_SEARCH_AND_PUT_RE` (with its own trailing "then
    shuffle" optional) expects to read as one clause among several.
    """
    merged: list[str] = []
    for clause in clauses:
        if (
            merged
            and _BARE_SHUFFLE_RE.fullmatch(clause.strip())
            and _MENTIONS_SEARCH_RE.search(merged[-1])
        ):
            merged[-1] = f"{merged[-1]}, then {clause.strip()}"
        elif (
            merged
            and _BARE_PUT_ON_TOP_RE.fullmatch(clause.strip())
            and _MENTIONS_SEARCH_RE.search(merged[-1])
            and re.search(r"shuffle$", merged[-1].strip(), re.IGNORECASE)
        ):
            merged[-1] = f"{merged[-1]} and {clause.strip()}"
        elif (
            merged
            and _REVEAL_PUT_SEARCH_CONTINUATION_RE.fullmatch(clause.strip())
            and _MENTIONS_SEARCH_RE.search(merged[-1])
        ):
            # Prismatic Undercurrents' own shape - see `_REVEAL_PUT_SEARCH_
            # CONTINUATION_RE`'s own docstring.
            merged[-1] = f"{merged[-1]}, {clause.strip()[0].lower()}{clause.strip()[1:]}"
        else:
            merged.append(clause)
    return merged


def _clause_targets(game: "Game", stack_object: "StackObject", phrase: str | None) -> list[Any]:
    """The targets still legal on resolution (CR 608.2b) that `phrase` - one
    clause's own "target ..." words - was announced for (CR 601.2c).

    A spell or ability that targets for other clauses too (Morgue Burst's
    "any target" next to its "target creature card from your graveyard")
    carries every one of them on the one stack object; each target records
    the requirement it filled (`TargetRef.slot`), and `_clause_slots` finds
    this clause's requirements among those, so the other clause's targets
    are never touched. Without a phrase, or one the targeting reader cannot
    read, every legal target is the clause's - which is all of them when it
    is the only one.
    """
    own = profile_for_text(phrase) if phrase else None
    if (
        own is None
        or not own.understood
        or not own.requirements
        or len(game._stack_object_profile(stack_object).requirements) < 2
    ):
        return list(game.resolve_targets(stack_object))
    slots = _clause_slots(game, stack_object, own)
    found: list[Any] = []
    for ref, slot in zip(stack_object.targets, slots, strict=True):
        if slot is None:
            continue
        thing = game.legal_target(stack_object, ref)
        if thing is not None:
            found.append(thing)
    return found


def return_clause_targets_to_hand(phrase: str | None = None) -> AbilityEffect:
    """`return_ability_targets_to_hand` for the clause whose target words are
    `phrase`: only the targets announced for that clause go to hand."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for target in _clause_targets(game, stack_object, phrase):
                if isinstance(target, CardState):
                    game.return_to_hand(target)

    return effect


def return_ability_targets_to_hand(game: "Game", stack_object: "StackObject") -> None:
    """Return each card or permanent this still legally targets to its
    owner's hand - every target the object has, for a clause that is its
    only targeting one (`return_clause_targets_to_hand` takes only a named
    clause's own).

    Not battlefield-only, for the same reason `exile_ability_targets` is not:
    "return" carries no CR-numbered keyword-action definition (CR 701's own
    list has no "Return" entry, unlike destroy, exile, or tap/untap), so
    nothing in the rules restricts its origin zone, and Raise Dead's
    "target creature card in your graveyard" is exactly this shape.
    `game.resolve_targets` already rechecks each target against the printed
    restriction's own zones (CR 608.2b), and `Game.return_to_hand` is
    zone-agnostic (see its docstring).
    """
    return_clause_targets_to_hand()(game, stack_object)


def return_ability_targets_to_battlefield(game: "Game", stack_object: "StackObject") -> None:
    """Return each target this still legally targets onto the battlefield,
    under the resolving spell or ability's own controller.

    The battlefield twin of `return_ability_targets_to_hand` immediately
    above, for the same reason: "return" has no CR-numbered keyword-action
    definition to name an origin zone with, and `game.resolve_targets` has
    already rechecked each target against the printed restriction's own
    zones (CR 608.2b), so a card that has already
    left the graveyard by the time this runs was already filtered out.
    CR 110.2a: "If an effect instructs a player to put an object onto the
    battlefield, that object enters the battlefield under that player's
    control unless the effect states otherwise" - none of the five cards this
    reads (Unearth, Renegade Rallier, Tameshi, Aftermath Analyst) states
    otherwise, so it is always the resolving object's own controller, the
    same read `_parse_mass_return_from_graveyard_to_battlefield_clause` and
    Greasefang's own reanimation effect already make.
    """
    controller = game.controller_of(stack_object)
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState):
            game.put_onto_battlefield(target, controller.username)


#: "When this land enters, return a land you control to its owner's hand."
#: (Gruul Turf, Simic Growth Chamber, and every other "Karoo"-cycle bounce
#: land - the shape generalises past this batch's two prints) or "return two
#: lands you control" (Khalni Gem) or "return up to two lands you control"
#: (Kazandu Stomper) - one printed quantity, not always "a". CR 608.2d: no
#: "target" is named, so the controller picks which land(s) they control,
#: including this one, as the ability resolves.
#: Widened (EP01-R2-T6) past lands to any mass qualifier
#: (`_parse_mass_type_qualifier`): Trusted Advisor's upkeep "return a blue
#: creature you control to its owner's hand".
_RETURN_A_LAND_YOU_CONTROL_RE = re.compile(
    rf"^(?P<may>you may )?return {quantity_pattern('n')} (?P<quality>[a-z ,-]+?) you control to "
    r"(?:its|their) owner'?s hand\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_optional_return_a_land_you_control_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """The "you may return a land you control to its owner's hand" clause that
    follows another instruction (Kefnet the Mindful's "Draw a card, then you
    may return a land ..."): `_parse_return_a_land_you_control_clause`'s shape
    with the printed "you may"."""
    if for_spell or not text.lstrip().lower().startswith("you may return "):
        return None
    return _parse_return_a_land_you_control_clause(text)


@ABILITY_TEXT.rung("s28")
def _parse_return_a_land_you_control_clause(text: str) -> AbilityEffect | None:
    """`_RETURN_A_LAND_YOU_CONTROL_RE`'s shape - a Karoo-cycle bounce land's
    own ETB trigger, or Khalni Gem's own printed-N one.

    CR 608.2d's controller-chosen "N land(s) you control" is `DecisionKind.
    CHOOSE_CARDS` over `game.permanents_controlled_by(controller)` filtered to
    `Type.LAND`, the same `MAY` + `CHOOSE_CARDS` shape `_parse_imprint_clause`
    already uses for a hand card - here there is no `MAY` half for the plain
    "return N", because the instruction is mandatory; "up to N" is `Decision.
    exact=False`, the "up to that many, or as many as possible" shape used
    throughout this wave for the same reason `search_library` reads it that
    way. A source that is not itself a land can genuinely control fewer lands
    than the printed count (Khalni Gem, cast off two lands, has none of its
    own to offer); the singular case's own candidate set was never empty only
    because the land resolving the trigger always counts as one of its own
    controller's lands (CR 110.5) - that guarantee does not extend to N > 1,
    so this caps the choice at whatever is actually there rather than asking
    for more than exists.
    """
    match = _RETURN_A_LAND_YOU_CONTROL_RE.fullmatch(text.strip())
    if match is None:
        return None
    quantity = parse_quantity(match.group("n"))
    quality = match.group("quality").strip()
    type_matches = _parse_mass_type_qualifier(quality)
    if quantity is None or type_matches is None:
        return None
    # "you may return a land you control" (Kefnet the Mindful): the controller
    # may choose none (CR 608.2d), so the choice is "up to" the printed count.
    optional = match.group("may") is not None
    exact = quantity.exact and not optional

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        candidates = computed_permanents(
            game, game.permanents_controlled_by(controller), type_matches
        )
        if not candidates:
            return
        limit = (
            len(candidates) if quantity.amount is None else min(quantity.amount, len(candidates))
        )
        if limit == 0:
            return
        source_name = ability.source_name
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"return {'a' if limit == 1 else limit} {quality} you control "
                "to its owner's hand",
                source=source_name,
                amount=limit,
                cards=tuple(state.id for state in candidates),
                exact=exact,
                default_cards=() if optional else tuple(state.id for state in candidates[:limit]),
                source_id=source_id_of(ability),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in candidates}
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for card_id in chosen_ids:
                game.return_to_hand(by_id[card_id])

    return effect


def _two_battlefield_targets_understood(phrase: str, *, up_to_one: bool) -> bool:
    """Exactly two single-permanent `TargetRequirement`s in `phrase`, each one
    `_targets_understood` would accept on its own. `up_to_one` also admits
    CR 115.6's "up to one target" (minimum zero) on either of them."""
    if _TRAILING_DURATION_RE.search(phrase):
        return False
    profile = profile_for_text(phrase)
    if not profile.understood or len(profile.requirements) != 2:
        return False
    minimums = (0, 1) if up_to_one else (1,)
    for requirement in profile.requirements:
        if _UNENFORCED_CONDITIONAL_RE.search(requirement.phrase) and (
            requirement.comparison_attribute is None
        ):
            return False
        if requirement.zones != frozenset({Zone.BATTLEFIELD}):
            return False
        if requirement.allows_players or requirement.unbounded:
            return False
        if requirement.minimum not in minimums or requirement.maximum != 1:
            return False
    return True


def _watch_for_departure_and_return_exiled_card(
    game: "Game",
    source: CardState,
    exiled: CardState,
    controller: str,
    *,
    return_zone: Zone = Zone.BATTLEFIELD,
) -> None:
    """Create the delayed triggered ability CR 610.2 describes: whenever
    `source` (the exiling enchantment) leaves the battlefield, by any of the
    three routes a permanent actually leaves it in this engine, return
    `exiled` to `return_zone` (CR 610.3's "previous zone" - the battlefield
    under its owner's control, CR 610.3c's default, for every caller that
    always exiles a permanent; a card the caller instead took from a
    player's hand, such as Cloak and Dagger, Entwined's own "or the chosen
    creature", passes `Zone.HAND` so the card comes back to the zone it
    actually left).

    Three sibling `DelayedTrigger`s, not one - CR 603.7a's ability watches
    for one event ("leaves the battlefield") that this engine represents as
    three distinct `TriggerEvent`s (`DIES` covers both destruction and
    sacrifice, CR 700.4/701.21a's own graveyard-arrival event for either
    verb; `LEAVES_BATTLEFIELD_TO_EXILE` and `LEAVES_BATTLEFIELD_TO_HAND`
    cover the other two), the same one-ability-many-events shape earthbend's
    "dies or is put into exile" already uses for two events.
    """
    exile_stamp = exiled.zone_change_stamp
    effect = StaticPrisonReturn(
        exiled_id=exiled.id, expected_stamp=exile_stamp, return_zone=return_zone
    )
    destination = (
        "hand" if return_zone is Zone.HAND else "the battlefield under its owner's control"
    )
    text = f"When {source.name} leaves the battlefield, return {exiled.name} to {destination}."
    siblings: list[DelayedTrigger] = []
    for event in (
        TriggerEvent.DIES,
        TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
        TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
    ):
        siblings.append(
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=text,
                    event=event,
                    controller=controller,
                    source_id=source.id,
                    source_name=source.name,
                    subject_id=source.id,
                    effect=effect,
                )
            )
        )
    for trigger in siblings:
        trigger.sibling_ids = tuple(other.id for other in siblings if other is not trigger)


def _return_ability_targets_to_battlefield_with_counter(
    tapped: bool, counter_kind: str | None = None, counter_amount: int = 0
) -> TargetedClause:
    """`return_ability_targets_to_battlefield`'s own tapped rider, with an
    optional counter on top - Generous Revival's own "with an additional
    `<n>` `<kind>` counter(s) on it" when `counter_kind` is given, and Primal
    Witchstalker's own bare "to the battlefield tapped" (no counter at all)
    when it is not. Built once per match rather than read off a stored regex
    group at resolution time.
    """
    kind = _counter_kind(counter_kind) if counter_kind else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState):
                continue
            permanent = game.put_onto_battlefield(target, controller.username, tapped=tapped)
            if kind is not None and permanent.zone is Zone.BATTLEFIELD:
                game.add_counters(permanent, kind, counter_amount)

    return effect


#: "Return a creature card from your graveyard to the battlefield with a
#: finality counter on it." (Scavenger's Talent) - no target: the player
#: chooses among their own graveyard's matching cards as the effect resolves
#: (CR 608.2d). An optional "tapped" and an optional "with N `<kind>`
#: counter(s) on it/them" ride along.
#: "another" stands in for `{COUNT}`'s own "a"/"an" here - CR 400.7's "an
#: other" object, not a real quantity word `parse_count` reads - so Rise of
#: the Witch-king's own no-target "you may return another permanent card
#: from your graveyard to the battlefield" is one instance of this same
#: templated CR 608.2d choice, not a different shape.
_RETURN_CARDS_FROM_YOUR_GRAVEYARD_RE = re.compile(
    rf"^(?P<may>you may )?return (?P<n>{COUNT}|another) (?P<quality>[a-z ,]+?) cards? "
    r"from your graveyard to the battlefield"
    r"(?P<tapped> tapped)?"
    rf"(?: with (?P<counter_n>{COUNT}) (?P<counter>[a-z0-9+/-]+) counters? on (?:it|them))?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_return_cards_from_your_graveyard_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_CARDS_FROM_YOUR_GRAVEYARD_RE`'s shape.

    CR 609.3: a graveyard holding fewer matching cards than the count returns
    what it has. The counters are placed as each permanent arrives, the way
    Neoform's "with an additional +1/+1 counter on it" already is, so a
    finality counter (CR 122.1h) is on it from then on.

    An optional leading "you may" is CR 608.2d's own choice, asked with
    `affirmative_is_legal` set to whether the graveyard actually holds a
    matching card right now - the same "no impossible option" shape
    `_parse_conditional_sacrifice_clause`'s own "you may sacrifice" already
    asks - rather than a bare CHOOSE_CARDS question with zero as a silent
    "no".
    """
    match = _RETURN_CARDS_FROM_YOUR_GRAVEYARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = 1 if match.group("n").lower() == "another" else parse_count(match.group("n"))
    if count is None or count < 1:
        return None
    matches = _quality_matcher(match.group("quality"))
    counter_kind = match.group("counter")
    counter_amount = parse_count(match.group("counter_n")) if counter_kind else 0
    if counter_kind and not counter_amount:
        return None
    tapped = match.group("tapped") is not None
    may = match.group("may") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        candidates = [state for state in player.cards_in(Zone.GRAVEYARD) if matches(state)]
        wanted = min(count, len(candidates))
        if wanted <= 0:
            return
        if may:
            decision = game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt=(
                        "return a card from your graveyard to the battlefield"
                        if wanted == 1
                        else f"return {wanted} cards from your graveyard to the battlefield"
                    ),
                    source=source,
                    affirmative_is_legal=True,
                    source_id=source_id_of(stack_object),
                )
            )
            if not decision:
                return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose {wanted} card(s) to return from your graveyard to the battlefield",
                source=source,
                amount=wanted,
                cards=tuple(state.id for state in candidates),
                source_id=source_id_of(stack_object),
            )
        )
        by_id = {state.id: state for state in candidates}
        for card_id in chosen_ids:
            permanent = game.put_onto_battlefield(by_id[card_id], player.username, tapped=tapped)
            if counter_kind and permanent.zone is Zone.BATTLEFIELD:
                game.add_counters(permanent, counter_kind.lower(), counter_amount or 0)

    return effect


#: "Return a `<quality>` card at random from your graveyard to the
#: battlefield." - Tomb Tyrant's own activated ability effect. Its own cost
#: (sacrifice a creature) and its own "Activate only during your turn and
#: only if there are at least three Zombie creature cards in your graveyard"
#: restriction are a separate workstream's; only this bare effect sentence
#: reaches this reader.
#:
#: "At random" carries no single dedicated CR paragraph of its own the way a
#: random discard does (CR 701.9b) - CR 608.2c simply has the resolving
#: ability follow this printed instruction, and "random" is read the plain,
#: unbiased way `_discard_at_random` already reads the identical adjective
#: on a different zone action: a `Random` seeded off `Game.shuffle_seed`/
#: `Game.shuffles_performed` rather than a bare `Random()`, so a scenario
#: asserting on which card came back stays deterministic, and the counter is
#: advanced afterward so the next random draw anywhere in the game is not
#: the same roll played twice.
#:
#: `quality` reuses `_quality_matcher` unchanged - any type/subtype phrase,
#: not only "Zombie creature" - so a card printing "Return a Spirit creature
#: card at random from your graveyard to the battlefield" reads for free.
#: CR 609.3: a graveyard with no matching card returns nothing.
#: The destination is the battlefield or the hand (Haunted Fengraf's "Return a
#: creature card at random from your graveyard to your hand."), and the quality
#: may be absent (The Deck of Many Things' "Return a card at random ...").
_RETURN_A_CARD_AT_RANDOM_FROM_GRAVEYARD_RE = re.compile(
    r"^return an? (?:(?P<quality>[a-z ,]+?) )?cards? at random from your graveyard to "
    r"(?P<destination>the battlefield|your hand)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_return_a_card_at_random_from_graveyard_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_A_CARD_AT_RANDOM_FROM_GRAVEYARD_RE`'s shape; see the banner
    above."""
    match = _RETURN_A_CARD_AT_RANDOM_FROM_GRAVEYARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quality = match.group("quality")
    matches = _quality_matcher(quality) if quality else (lambda _state: True)
    to_hand = match.group("destination").lower() == "your hand"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        candidates = [state for state in player.cards_in(Zone.GRAVEYARD) if matches(state)]
        if not candidates:
            return
        rng = Random(  # noqa: S311
            f"{game.shuffle_seed}:{game.shuffles_performed}:return-at-random"
        )
        chosen = rng.choice(candidates)
        game.shuffles_performed += 1
        if to_hand:
            player.move(chosen, Zone.HAND)
        else:
            game.put_onto_battlefield(chosen, player.username)

    return effect


def _matches_subtype_on_battlefield(game: "Game", referent: CardState, quality: str) -> bool:
    """Whether `referent`'s computed subtypes (CR 613.5) include `quality`
    (an article-stripped noun phrase - "Dwarf", "Human Soldier") - the same
    generic word-by-word subtype check `machines/keywords.equip_quality_
    refusal` already reads an "Equip [quality]" ability's own quality with,
    narrowed here to the single subtype-list shape this rider's own "if it's
    a `<subtype>`" ever prints (CR 205.3's card subtypes, `canonical_subtype`).
    """
    if referent.zone is not Zone.BATTLEFIELD:
        return False
    subtypes = {subtype.lower() for subtype in game.characteristics_of(referent).subtypes}
    words = quality.strip().lower().split()
    if not words:
        return False
    return all((canonical_subtype(word) or word) in subtypes for word in words)


#: Ugin's Labyrinth's third ability: "{T}: Return the exiled card to its
#: owner's hand." "The exiled card" is a definite reference to whichever card
#: `_parse_imprint_clause` linked to this permanent, not a target - CR 601.2c
#: never has this ability's activation choose one. Watcher for Tomorrow's
#: "When this creature leaves the battlefield, put the exiled card into its
#: owner's hand." is the same CR 607.2a linked reference worded "put ... into",
#: pointing back at hideaway's own exile.
_RETURN_IMPRINTED_RE = re.compile(
    r"^(?:return the exiled card to|put the exiled card into) (?:its|their) owner's hand$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_return_imprinted_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """The other half of the imprint shape: giving the linked card back.

    Found by `Game.card_imprinted_on` rather than kept as a pointer of its
    own, so it survives however the card got there. CR 608.2b's "the effect
    does as much as possible" covers the two ways there is nothing to
    return - no card was ever exiled, or the link has gone stale (see
    `ExileAnnotation.linked_permanent_id`'s own docstring) - both leave this a
    no-op rather than an error.
    """
    if not _RETURN_IMPRINTED_RE.fullmatch(clause.strip().rstrip(".")):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_id, _ = _permanent_id_and_name(stack_object, for_spell=for_spell)
        card = game.card_imprinted_on(source_id)
        if card is None:
            return
        owner_name = card.owner or game.controller_of(stack_object).username
        game.exile.remove(card)
        game.player(owner_name).add(card, Zone.HAND)

    return effect


#: "For each opponent, return up to one target `<X>` that player controls to
#: its owner's hand." - `_FOR_EACH_OPPONENT_DESTROY_RE`'s own bounce twin.
#: The Theorist, Jace Beleren's own `-2`, and the real, off-set printing
#: Enigma Thief's identical ETB trigger.
_FOR_EACH_OPPONENT_RETURN_TO_HAND_RE = re.compile(
    r"^for each opponent, return up to one target (?P<desc>.+?) that player controls "
    r"to its owner'?s hand\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_for_each_opponent_return_to_hand_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_FOR_EACH_OPPONENT_RETURN_TO_HAND_RE`'s shape - see the banner above."""
    match = _FOR_EACH_OPPONENT_RETURN_TO_HAND_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                    game.return_to_hand(target)

    return effect


#: Ilharg, the Raze-Boar's attack trigger, read whole: "you may put a creature
#: card from your hand onto the battlefield tapped and attacking. Return that
#: creature to your hand at the beginning of the next end step."
#:
#: Whole rather than per-clause because `split_effect_clauses` cuts on a bare
#: " and ", which slices "tapped and attacking" into "tapped" / "attacking" -
#: two fragments no parser can read back together, and CR 608.2c has no notion
#: of running half an instruction, so the whole ability would fail closed.
#:
#: CR 508.4 is what the second half of the first sentence means: "If a creature
#: is put onto the battlefield attacking, its controller chooses which defending
#: player, planeswalker a defending player controls, or battle a defending
#: player protects it's attacking as it enters the battlefield." CR 508.4a and
#: CR 506.3c are the two refusals - a defending player who has left the game,
#: or a permanent no longer on the battlefield - and both are honoured by the
#: CR 508.4 primitive this calls rather than re-checked here.
_PUT_CREATURE_FROM_HAND_ATTACKING_RE = re.compile(
    r"^you may put an? (?P<group>[a-z]+) card from your hand onto the battlefield "
    r"tapped and attacking\.\s*"
    r"(?P<delayed>return that [a-z]+ to your hand at the beginning of the next end step)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_put_creature_from_hand_attacking_then_return(text: str) -> AbilityEffect | None:
    """`_PUT_CREATURE_FROM_HAND_ATTACKING_RE`'s shape - Ilharg's attack trigger.

    Three things in printed order (CR 608.2c):

    1. CR 608.2d's plain "you may", then a `CHOOSE_CARDS` question over the
       cards in hand of the printed group - "creature card" here, read by the
       same `_parse_card_group_qualifier` every other group-reading clause in
       this file uses, so a group this file cannot read fails the whole
       ability closed rather than putting the wrong card down.
    2. `Game.put_onto_battlefield` tapped, and then CR 508.4's own placement
       into combat. The creature Ilharg is already attacking sets the
       defending player: CR 508.4 hands the choice to the permanent's
       controller, and the only defender this engine can read off the board is
       the one the controller's own attack already named.
    3. CR 603.7a's delayed triggered ability for the second sentence, built by
       `anaphoric_delayed_trigger` off the printed clause - "that creature" is
       a pronoun for whatever step 2 actually produced, which is exactly the
       shape that primitive exists for. CR 603.7c is why it is created about
       *that* object and checks it is still there when it resolves.

    The delayed trigger is created only if a creature actually arrived: a
    declined "you may", an empty hand, or a card the move refused leaves
    nothing for "that creature" to name, and CR 101.3 ignores an instruction
    that is impossible to perform.
    """
    match = _PUT_CREATURE_FROM_HAND_ATTACKING_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    matches_group = _parse_card_group_qualifier(match.group("group"))
    if matches_group is None:
        return None
    delayed_clause = match.group("delayed")
    if parse_anaphoric_delayed_clause(delayed_clause) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ...models.token import _put_onto_the_battlefield_attacking

        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        candidates = [state for state in controller.hand if matches_group(state)]
        if not candidates:
            return
        if not game.may(
            controller,
            "put a creature card from your hand onto the battlefield tapped and attacking",
            source=source_name,
            source_id=source_id_of(ability),
        ):
            return
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt="choose a creature card to put onto the battlefield attacking",
            source=source_name,
            amount=1,
            cards=tuple(state.id for state in reversed(candidates)),
            source_id=source_id_of(ability),
        )
        chosen_ids = game.ask(decision)
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id[chosen_ids[0]]
        # Attacking before the enters event is raised (CR 508.4, CR 603.6a).
        with game.entering_together():
            permanent = game.put_onto_battlefield(chosen, controller.username, tapped=True)
            if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
                return
            defender = _defender_of_controllers_attack(game, controller.username)
            if defender is not None:
                # CR 508.4, via `models/token.py`'s own primitive: it is
                # annotated for a `TokenState` because the token half was
                # written first, but everything it reads - `is_creature`,
                # `controller`, `id` - is `CardState`'s, and CR 508.4 draws no
                # distinction between a token and a card put onto the
                # battlefield attacking.
                _put_onto_the_battlefield_attacking(game, permanent, defender)  # type: ignore[arg-type]
        trigger = anaphoric_delayed_trigger(
            delayed_clause,
            subject=permanent,
            controller=controller.username,
            source_id=source_id,
            source_name=source_name,
        )
        if trigger is not None:
            game.create_delayed_trigger(trigger)

    return effect


#: "return that card/it/that creature/that permanent to the battlefield under
#: its/their owner's control" - the blink idiom (Phelia, Blizzard Strix, Angel
#: of Condemnation, Astral Drift all print it verbatim).
_RETURN_TO_BATTLEFIELD_OWNER_RE = re.compile(
    r"^(?:if you do, )?return (?:it|that card|that creature|that permanent|them"
    r"|those (?:cards|creatures|permanents)) to the battlefield "
    # ecl-T8: Morningtide's Light's own "... tapped under their owners'
    # control" - the identical optional "tapped" rider several other
    # zone-return shapes in this module already carry.
    r"(?P<tapped>tapped )?under (?:its|their) owners?'?s? control$",
    re.IGNORECASE,
)


#: "if it entered under your control, put N +1/+1 counter(s) on <recipient>" -
#: Phelia's own rider, generalised: `<recipient>` is read and checked against
#: the *resolving* source's own name at run time (its short form, "Phelia",
#: included), never hardcoded, so this reads any card printing the same shape
#: rather than being one more name-keyed table row.
_RETURN_RIDER_COUNTER_RE = re.compile(
    r"^if it entered under your control, "
    r"put (?P<n>a|one|two|three|four|five) \+1/\+1 counters? on (?P<who>.+)$",
    re.IGNORECASE,
)


def _parse_return_rider_clause(clause: str) -> ReturnRiderCounter | None:
    """Phelia's third sentence: "If it entered under your control, put a
    +1/+1 counter on Phelia." Conditional on the delayed return itself (not on
    anything true when the outer ability resolved), so it has to run as part
    of the delayed trigger's own resolution, not the attack trigger's - see
    `ReturnRiderCounter.__call__` in `machines/delayed.py`.
    """
    match = _RETURN_RIDER_COUNTER_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    who = match.group("who").strip().lower()
    return ReturnRiderCounter(amount=amount, who=who)


#: "the beginning of that player's next end step" / "of its owner's next end
#: step" - the exiled card's owner's own end step (CR 603.7).
_OWNERS_NEXT_END_STEP_RE = re.compile(
    r"the beginning of (?:that player's|its owner's) next end step", re.IGNORECASE
)


def _parse_delayed_blink_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Exile up to one other target nonland permanent. At the beginning of
    the next end step, return that card to the battlefield under its owner's
    control[. If it entered under your control, put a +1/+1 counter on
    <recipient>.]" as one combined instruction (CR 608.2c) - two or three
    consecutive clauses starting at `index`, or `None` if `index` is not the
    start of this shape.

    The linkage: clause two's "that card" is CR 400.7's anaphora back to
    whatever clause one's own exile just moved, discovered only as clause one
    actually runs - so the combined effect below exiles the target itself
    (not `exile_ability_targets`, which has nowhere to hand the result back
    to) and closes over the exiled `CardState` when it builds the
    `DelayedTrigger`, the same way `_parse_anaphoric_clause_pair` closes over
    its own first clause's target.
    """
    # "you may exile target ... If you do, return that card ..." (Sentinel of
    # the Pearl Trident): CR 608.2d's optional exile, and "If you do" is the
    # delayed return's own condition - nothing exiled, nothing returned.
    first = clauses[index].strip()
    optional = first.lower().startswith("you may ")
    if optional:
        first = first[len("you may ") :]
    exile_match = _EXILE_TARGET_RE.fullmatch(first)
    if exile_match is None:
        return None
    if not _targets_understood(
        exile_match.group("phrase"), count_agnostic=True, battlefield_only=False
    ):
        return None
    if index + 1 >= len(clauses):
        return None
    # CR 603.7: "at the beginning of that player's next end step" (The Eternal
    # Wanderer's +1: the exiled card's owner) waits for the next end step of
    # that player's own turn - read as the plain next end step plus an
    # `only_when_active` gate on the owner, below.
    owners_end_step = _OWNERS_NEXT_END_STEP_RE.search(clauses[index + 1]) is not None
    timing = _parse_delayed_timing_clause(
        _OWNERS_NEXT_END_STEP_RE.sub("the beginning of the next end step", clauses[index + 1])
    )
    if timing is None:
        return None
    step, verb = timing
    return_match = _RETURN_TO_BATTLEFIELD_OWNER_RE.fullmatch(verb)
    if return_match is None:
        return None
    tapped = return_match.group("tapped") is not None
    if optional and not verb.lower().startswith("if you do, "):
        return None

    consumed = 2
    rider: ReturnRiderCounter | None = None
    if index + 2 < len(clauses):
        maybe_rider = _parse_return_rider_clause(clauses[index + 2])
        if maybe_rider is not None:
            rider = maybe_rider
            consumed = 3

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = stack_object.id if for_spell else stack_object.source_id  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            # CR 115.6: "up to one" chose zero, or CR 608.2b left nothing
            # legal - nothing to exile, so nothing to delay either.
            return
        if optional and not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=controller,
                prompt=f"exile {', '.join(target.name for target in targets)}",
                source=source_name,
                source_id=source_id_of(stack_object),
                affirmative_is_legal=True,
            )
        ):
            return
        exiled_cards: list[CardState] = []
        for target in targets:
            game.exile_permanent(target)
            # CR 111.8 refused a token that already left the battlefield once -
            # no delayed return for something that never left.
            if target.zone is Zone.EXILE:
                exiled_cards.append(target)
        if not exiled_cards:
            return

        if len(exiled_cards) > 1 and rider is None:
            # "Return those cards ..." (Elrond, Moon-Reader; Eerie Interlude):
            # one delayed ability returning every card it exiled together.
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clauses[index + 1],
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    effect=ReturnEachExiledToBattlefieldUnderOwner(
                        subjects=tuple(
                            (card_state.id, card_state.zone_change_stamp)
                            for card_state in exiled_cards
                        ),
                        tapped=tapped,
                    ),
                )
            )
            return
        blink_effect = (
            ReturnSubjectToBattlefieldUnderOwner(tapped=tapped)
            if rider is None
            else DelayedBlinkReturnWithRider(rider=rider)
        )
        for target in exiled_cards:
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clauses[index + 1],
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    subject_id=target.id,
                    only_when_active=target.owner if owners_end_step else None,
                    expected_zone=Zone.EXILE,
                    expected_stamp=target.zone_change_stamp,
                    effect=blink_effect,
                )
            )

    return consumed, effect


#: "Return target creature card [with mana value N or X] from your graveyard
#: to the battlefield." - Postmortem Lunge's own reanimation clause, read
#: generically off the shape (not off the card's name): any card printing
#: this exact template gets the same treatment. A bare "X" is accepted here
#: (unlike `_extract_comparison`'s own unbound-X refusal) because this clause
#: never reads the number itself - the actual mana-value *legality* of the
#: target is enforced entirely by `machines/targeting.py`'s `TargetRequirement.
#: comparison_value`, fed by `Casting.targeting`'s own X substitution
#: (CR 107.3a) once the caster announces X, which happens independently of
#: this parser matching at all. Matching on the very first, unsubstituted
#: pass also sidesteps `_unreadable_delayed_clause`'s own fallback: without
#: this, `effect_for`'s first pass would read nothing here, fall through to
#: that notice for the still-unmatched "exile it at the beginning of the next
#: end step" clause, and return the notice before X substitution ever ran
#: (its own docstring's "only if that first pass reads nothing" only helps a
#: caller whose *first* pass reads `None`, not one that reads a competing
#: notice instead).
#:
#: The qualifier slot before "creature card" is deliberately open - "legendary"
#: (Goryo's Vengeance), "nonlegendary", "artifact", "multicolored" - rather
#: than a list this file would have to keep growing. It is safe to be open
#: because the phrase is then handed to `_targets_understood`, which refuses
#: any restriction `machines/targeting.py` cannot actually enforce; a qualifier
#: nobody can read fails the whole parse rather than quietly reanimating
#: something the card never named. CR 205.4a is the supertype the commonest
#: qualifier names ("the supertypes are basic, legendary, ongoing, snow, and
#: world").
_RETURN_CREATURE_CARD_FROM_GRAVEYARD_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?P<phrase>target (?:[a-z]+ )*creature card"
    r"(?: with mana value (?:\d+|x))? from your graveyard) to the battlefield$",
    re.IGNORECASE,
)

#: Clause two of the same instruction. "It" is Postmortem Lunge's pronoun and
#: "that creature" is Goryo's Vengeance's; both are CR 400.7 anaphora for
#: whatever clause one's own return just put onto the battlefield, so they are
#: one shape and not two. The demonstrative agrees with a creature by
#: construction here - clause one returned a creature card - so there is
#: nothing further to check.
_GAINS_HASTE_ANAPHOR_RE = re.compile(
    r"^(?:it|that creature|that card|that permanent) gains haste$", re.IGNORECASE
)


def _parse_delayed_reanimate_haste_exile_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Return target [qualifier] creature card [with mana value N] from your
    graveyard to the battlefield. It gains haste. <anaphoric delayed clause>."
    as one CR 608.2c instruction - three consecutive clauses starting at
    `index`, or `None` if `index` is not the start of this shape.

    Two printings, one shape. Postmortem Lunge reads "target creature card
    with mana value X ... It gains haste. Exile it at the beginning of the
    next end step."; Goryo's Vengeance reads "target legendary creature card
    ... That creature gains haste. Exile it at the beginning of the next end
    step." The supertype qualifier and the demonstrative pronoun are the only
    differences, and each one used to fail the parse - which, because an
    ability resolves whole or fails closed here, took the reanimation in
    clause one down with it and left the whole archetype inert.

    The linkage is CR 400.7 anaphora twice over, the same reasoning
    `_parse_delayed_blink_clauses` already documents for its own "that card":
    the pronoun in clause two and the pronoun in clause three both mean
    whatever clause one's own return just put onto the battlefield, discovered
    only as clause one actually runs - so this closes over the entered
    `CardState` rather than resolving either later sentence's target of its
    own.

    Clause three is not read here at all: it is handed to
    `machines/delayed.py`'s `parse_anaphoric_delayed_clause` /
    `anaphoric_delayed_trigger`, which own that shape (CR 603.7a creates the
    delayed ability, CR 603.7c is why the subject's zone and stamp are
    captured now rather than re-checked later). That is what makes "Sacrifice
    that token", "Destroy it" and the return-to-hand variants free here rather
    than one more literal string comparison each.

    Haste is granted with `Duration.INDEFINITE` (CR 611.2a's default: "if no
    duration is stated, it lasts indefinitely") scoped to `only_this_
    incarnation` - the object is about to be exiled by the delayed trigger
    anyway, but a response that saves it from that exile should not also
    strip the haste a literal reading of the card never granted with a time
    limit.
    """
    return_match = _RETURN_CREATURE_CARD_FROM_GRAVEYARD_TO_BATTLEFIELD_RE.fullmatch(
        clauses[index].strip().rstrip(".")
    )
    if return_match is None:
        return None
    if not _targets_understood(return_match.group("phrase"), battlefield_only=False):
        return None
    if index + 2 >= len(clauses):
        return None
    if _GAINS_HASTE_ANAPHOR_RE.fullmatch(clauses[index + 1].strip().rstrip(".")) is None:
        return None
    rider = clauses[index + 2]
    if parse_anaphoric_delayed_clause(rider) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = stack_object.id if for_spell else stack_object.source_id  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            entered = game.put_onto_battlefield(target, controller, tapped=False)
            if entered.zone is not Zone.BATTLEFIELD:
                continue  # a replacement effect sent it elsewhere (CR 614.6)
            store = continuous_effects(game)
            timestamp = store.tick()
            store.add(
                ContinuousEffect(
                    description=f"{source_name}: {entered.name} gains haste",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    selector=only_this_incarnation(entered, entered.zone_change_stamp),
                    modification=grant_ability("Haste"),
                )
            )
            trigger = anaphoric_delayed_trigger(
                rider,
                subject=entered,
                controller=controller,
                source_id=source_id,
                source_name=source_name,
            )
            if trigger is None:
                continue  # the pronoun does not agree; fail closed (CR 603.7a)
            game.create_delayed_trigger(trigger)

    return 3, effect


#: "Return that card to its owner's hand." - Ares, God of War's own
#: "Whenever an attacking creature you control dies, ..." "That card" is
#: CR 400.7/607.1 anaphora onto the DIES event's own subject
#: (`GameEvent.subject_id` keeps the same id across the battlefield-to-
#: graveyard move, per `Game.put_into_graveyard`'s own emit; only the
#: `zone_change_stamp` is fresh, rechecked here the same way every other
#: "that card" reader in this file already does).
_RETURN_THAT_CARD_TO_OWNERS_HAND_RE = re.compile(
    r"^return that card to its owner'?s hand\.?$", re.IGNORECASE
)


def _parse_return_that_card_to_owners_hand_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_RETURN_THAT_CARD_TO_OWNERS_HAND_RE`'s shape, or `None`.

    Ability-only: `event.subject_id`/`.zone_change_stamp` are a triggered
    ability's own event attributes.
    """
    if for_spell:
        return None
    if _RETURN_THAT_CARD_TO_OWNERS_HAND_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object) or stack_object.event is None:
            return
        event = stack_object.event
        if event.subject_id is None:
            return
        card = game.find_by_id(event.subject_id)
        if not isinstance(card, CardState) or card.zone is not Zone.GRAVEYARD:
            return
        if (
            event.zone_change_stamp is not None
            and card.zone_change_stamp != event.zone_change_stamp
        ):
            return
        game.return_to_hand(card)

    return effect


def _reposition_in_owners_library(game: "Game", card: CardState, *, depth: int) -> None:
    """After `Game.put_cards_into_library` has just put `card` on the very
    top of its own owner's library, slide it down to `depth` (CR 609.3's "as
    much as it can" when the library does not hold that many other cards) -
    the same list-surgery `_parse_dead_object_to_library_clause` reuses for
    its own self-referential ordinal placement. The rest of the library
    keeps its own order (CR 401.2)."""
    if card.owner is None:
        return
    library = game.player(card.owner).library
    if card in library:
        library.remove(card)
        library.insert(min(depth, len(library)), card)


#: Karai, Future of the Foot's own combat-damage trigger: "return target
#: creature card from your graveyard to your hand. If her sneak cost was
#: paid this turn, instead return that card to the battlefield." CR 614.1a's
#: "instead" replaces the base instruction's *destination* only - the target
#: itself is the ability's own already-chosen one (CR 601.2c has no bearing
#: on an ability, but CR 603.3c fixes a triggered ability's targets the
#: identical way, once, as it is put on the stack), so "that card" (CR
#: 400.7's anaphora) is read here as the same object `game.resolve_targets`
#: already gives the base branch, never as a second, separately-elided
#: target `_anaphoric_target_substitution`'s text-only rewrite would have to
#: reconstruct - which is why this is its own reader rather than a case of
#: `_parse_condition_instead_clause_for_ability` below: that function's own
#: alternative half is read as an independent instruction with its own
#: targeting, and "return that card" names no target phrase at all for it to
#: elide onto. `quality` generalises past "creature card" to whatever card
#: type(s) a future printing of this same rider names, read the identical
#: way every other "target `<quality>` card" clause in this file is
#: (`_targets_understood`, `battlefield_only=False` - CR 701.13a puts no
#: floor-only restriction on "return", `_targets_understood`'s own docstring
#: on this exact point).
_RETURN_TARGET_CARD_THEN_INSTEAD_BATTLEFIELD_IF_COST_PAID_RE = re.compile(
    r"^return target (?P<quality>.+? cards?) from your graveyard to your hand\.\s*"
    r"if (?P<condition>[^,]+), instead return that card to the battlefield\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_return_target_card_then_instead_battlefield_if_cost_paid_clause(
    text: str,
) -> AbilityEffect | None:
    """`_RETURN_TARGET_CARD_THEN_INSTEAD_BATTLEFIELD_IF_COST_PAID_RE`'s shape.

    Ability-only: `Game.condition_holds`'s own `source` argument is a live
    battlefield permanent's `ConditionContext.source`, which only a
    resolving ability - never a spell - carries the same way the whole
    `_keyword_cost_paid`/"paid this turn" family already requires.
    """
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _RETURN_TARGET_CARD_THEN_INSTEAD_BATTLEFIELD_IF_COST_PAID_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(
        f"target {match.group('quality')} from your graveyard", battlefield_only=False
    ):
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return  # CR 608.2b/115.6: no (legal) target chosen; nothing to move.
        target = targets[0]
        controller = game.controller_of(ability).username
        source = ability.source(game)
        held = game.condition_holds(controller, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=whole
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        if held:
            game.put_onto_battlefield(target, controller)
        else:
            game.return_to_hand(target)

    return effect


#: "Return this card from your graveyard to your hand." - World Breaker's
#: whole graveyard-only ability (CR 113.6m, `machines/abilities.py`'s
#: `zone`/`zone_rule` reads that half of it already). A self-reference, not a
#: target: CR 115.1's "target" always names a chosen object, and this
#: sentence names the very permanent whose ability is resolving instead, the
#: same self-reference `_parse_destroy_each_clause`'s "Destroy each ..." and
#: `machines/keywords`'s `discard_cost`/`sacrifice_cost` self-fill already
#: read off "this card"/"this permanent". Zones beyond graveyard-to-hand are
#: read too, generalized off the words rather than pinned to this one card -
#: CR 400.7's zone-change vocabulary is the same whichever two zones a future
#: card names this way.
_RETURN_THIS_CARD_RE = re.compile(
    r"^return this (?:card|permanent) from (?:your|its owner's) "
    r"(?P<from_zone>graveyard|hand|exile|library|battlefield) "
    r"to (?:your|its owner's) (?P<to_zone>hand|graveyard|battlefield|exile|library)\.?$",
    re.IGNORECASE,
)

#: The zone names `_RETURN_THIS_CARD_RE` reads map straight onto `Zone`.
_ZONE_BY_NAME: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "battlefield": Zone.BATTLEFIELD,
    "exile": Zone.EXILE,
    "library": Zone.LIBRARY,
}


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_self_return_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Return this card from your `<zone>` to your `<zone>`." - a plain
    zone change of the ability's own source, read off the clause's own words
    (CR 400.7a: putting a card into hand from anywhere but the stack or
    battlefield is a new object with no memory of what it was).

    CR 113.7a: the ability resolves independently of its source, so a source
    that can no longer be found (already moved again, or gone) or one that
    has already left the zone the clause names does nothing rather than
    raising - the same "the target left" shape CR 608.2b already gives a
    targeted effect, applied here to a plain self-reference instead.
    """
    match = _RETURN_THIS_CARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    from_zone = _ZONE_BY_NAME[match.group("from_zone").lower()]
    to_zone = _ZONE_BY_NAME[match.group("to_zone").lower()]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        if source is None or source.zone is not from_zone:
            return
        owner = game.find_owner(source) or game.player(
            source.controller_or_owner or game.active_player.username
        )
        # CR 400.1: the battlefield and exile are shared, so a move into
        # either of them is the game's, not the owner's - `Player.move` would
        # build a per-player pile of it. `_ZONE_BY_NAME` can name both, so
        # both are routed to the doors that own them rather than left to
        # whichever printing reaches this clause first.
        if to_zone is Zone.BATTLEFIELD:
            game.put_onto_battlefield(source, owner.username)
        elif to_zone is Zone.EXILE:
            game.exile_permanent(source)
        elif from_zone is Zone.BATTLEFIELD and to_zone is Zone.HAND:
            game.return_to_hand(source)
        elif from_zone.is_shared:
            game._take_out_of_every_zone(source)  # noqa: SLF001
            owner.add(source, to_zone)
        else:
            owner.move(source, to_zone)

    return effect


#: "return it to its owner's hand" (Rancor's own dies trigger) - CR 603.10a's
#: look-back "it", naming the ability's own source, the same self-reference
#: `_EXILE_IT_RE` reads for a different destination.
_RETURN_IT_TO_OWNERS_HAND_RE = re.compile(r"^return it to its owner'?s hand$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_return_dead_self_to_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Return it to its owner's hand." - Rancor's own dies trigger, moving
    the ability's own source (CR 603.10a's look-back "it") from wherever it
    now sits (almost always the graveyard, per CR 700.4 - an Aura's own dies
    trigger fires the same way a creature's does, CR 700.4 naming "a
    permanent", not only a creature) to its owner's hand (CR 108.3, CR 401).
    `_dead_self_found` is the same fail-soft/CR 400.7e lookup
    `_parse_exile_dead_self_clause` shares with this reader - see that
    helper's own docstring.

    Ability-only (`for_spell=False`): nothing in the pool prints this on a
    spell, and `AbilityOnStack.source`/`.event` are what finds the departed
    object.
    """
    if for_spell:
        return None
    if not _RETURN_IT_TO_OWNERS_HAND_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = _dead_self_found(game, ability)
        if source is None:
            return
        game.return_to_hand(source)

    return effect


#: "Return it to the battlefield with one fewer `<kind>` counter on it at the
#: beginning of the next end step." - Nine-Lives Familiar's dies trigger. "It"
#: is the object that died (CR 603.10a's look-back), found in the graveyard by
#: `_dead_self_found`'s CR 400.7e lookup. The "fewer" is worked out now, from
#: the counters it had as it last existed on the battlefield
#: (`CardState.last_known_counters`, CR 122.2 having ended the live ones), and
#: frozen into the delayed return (CR 603.7a), which puts it back with that
#: many (none when the subtraction reaches zero) when the step arrives. A fixed
#: "with N `<kind>` counters on it" is the same shape without the subtraction.
_RETURN_DEAD_SELF_WITH_COUNTERS_AT_STEP_RE = re.compile(
    rf"^return (?:it|this card|that card) to the battlefield(?P<tapped> tapped)? with "
    rf"(?:(?P<fewer>{COUNT}) fewer|(?P<fixed>{COUNT}|an?)) (?P<kind>[a-z0-9+/-]+) counters? "
    rf"on it at (?P<timing>{'|'.join(map(re.escape, ANAPHORIC_TIMING_STEPS))})\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_return_dead_self_with_counters_at_step_clause(text: str) -> AbilityEffect | None:
    """`_RETURN_DEAD_SELF_WITH_COUNTERS_AT_STEP_RE`'s shape (CR 603.7, 122.6)."""
    if " with " not in text:
        return None
    match = _RETURN_DEAD_SELF_WITH_COUNTERS_AT_STEP_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    fewer = parse_count(match.group("fewer")) if match.group("fewer") else None
    fixed = parse_count(match.group("fixed")) if match.group("fixed") else None
    if fewer is None and fixed is None:
        return None
    kind = str(match.group("kind").lower())
    step = ANAPHORIC_TIMING_STEPS[match.group("timing").lower()]
    tapped = match.group("tapped") is not None
    clause = text.strip().rstrip(".")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        card = _dead_self_found(game, ability)
        if card is None or card.zone is not Zone.GRAVEYARD:
            return
        amount = fixed if fixed is not None else card.last_known_counters[kind] - (fewer or 0)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=clause,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=card.id,
                expected_zone=Zone.GRAVEYARD,
                expected_stamp=card.zone_change_stamp,
                effect=ReturnSubjectFromGraveyardWithCounters(
                    counters=((kind, max(amount, 0)),), tapped=tapped
                ),
            )
        )

    return effect


#: "return it to your hand" / "return that card to your hand" (Enduring
#: Renewal's graveyard trigger) - the triggering event's card, found in the
#: graveyard it just arrived in (CR 400.7e), into the ability controller's own
#: hand. The trigger's condition already limits it to cards that player owns.
_RETURN_DEAD_IT_TO_YOUR_HAND_RE = re.compile(
    r"^return (?:it|that (?:creature )?card) to your hand$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_return_dead_card_to_your_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_DEAD_IT_TO_YOUR_HAND_RE`'s shape. Ability-only: the card is the
    triggering event's, found by `_dead_self_found`'s CR 400.7e lookup."""
    if for_spell or not _RETURN_DEAD_IT_TO_YOUR_HAND_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        card_state = _dead_self_found(game, ability)
        if card_state is not None and card_state.zone is Zone.GRAVEYARD:
            game.player(ability.controller).move(card_state, Zone.HAND)

    return effect


# --------------------------------------------------------------------------
# Secrets of Strixhaven prepare faces and their triggers (CR 722)
# --------------------------------------------------------------------------
#
# Each reader here targets a template, never a card: the prepare faces that
# exposed them (Reanimate, Secret Rendezvous, Echocasting Symposium's own
# paradigm body, Emeritus of Truce's and Emeritus of Ideation's triggers)
# are only the first printings of each shape - see
# `tests/scenarios/test_prepare_spell_faces.py`,
# `test_becomes_prepared_triggers.py` and `test_paradigm_token_copy.py` for
# the second printing each one is proven on.

#: "Put target `<card>` from a graveyard onto the battlefield under your
#: control." (Reanimate, Beacon of Unrest, Vat Emergence) - and its "return
#: ... to the battlefield under your control" twin. CR 110.2a: "If an effect
#: instructs a player to put an object onto the battlefield, that object
#: enters the battlefield under that player's control unless the effect
#: states otherwise" - "under your control" states exactly that default, so
#: this is `return_ability_targets_to_battlefield`'s own executor, read off a
#: phrase that may name *any* graveyard (`machines/targeting.py` already
#: reads "from a graveyard" as a graveyard-zone target with no owner filter).
_PUT_FROM_GRAVEYARD_ONTO_BATTLEFIELD_RE = re.compile(
    r"^(?:put (?P<phrase>(?:up to \w+ )?target .+? from (?:a|your|an opponent'?s) graveyard) "
    r"onto the battlefield(?: under your control)?"
    r"|return (?P<return_phrase>(?:up to \w+ )?target .+? from (?:a|an opponent'?s) graveyard) "
    r"to the battlefield under your control)\.?$",
    re.IGNORECASE,
)


def _parse_put_from_graveyard_onto_battlefield_clause(clause: str) -> TargetedClause | None:
    """`_PUT_FROM_GRAVEYARD_ONTO_BATTLEFIELD_RE`'s shape, or `None`."""
    match = _PUT_FROM_GRAVEYARD_ONTO_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    phrase = match.group("phrase") or match.group("return_phrase")
    if not _targets_understood(phrase, count_agnostic=True, battlefield_only=False):
        return None
    return return_ability_targets_to_battlefield


#: "return each other `<qualifier>` that entered [the battlefield ]this turn
#: to its owner's hand." - Renet, Temporal Apprentice's own enters-the-
#: battlefield trigger (TMT). One clause, no "and" to trip the splitter, but
#: nothing in `_parse_targeted_clause`'s chain reads a *mass*, untargeted
#: "entered this turn" subject (only `machines/targeting.py`'s
#: `must_have_entered_this_turn` restricts a chosen *target* this way), so
#: this is a new mass-subject reader rather than a clause-pair merge.
_RETURN_EACH_OTHER_ENTERED_THIS_TURN_TO_HAND_RE = re.compile(
    r"^return each other (?P<qualifier>.+?) that entered (?:the battlefield )?this turn "
    r"to (?:its|their) owners?'?s? hand\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s37", for_spell=False)
def _parse_mass_return_entered_this_turn_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_RETURN_EACH_OTHER_ENTERED_THIS_TURN_TO_HAND_RE`'s shape, or `None`.

    `<qualifier>` ("nonland permanent") is read by `_parse_mass_type_
    qualifier`, the same CR 205.2a type-list reader `_parse_mass_destroy_
    predicate` already shares for a mass destruction's own subject. "Entered
    this turn" is `CardState.turn_entered` (stamped once, in `Game.
    enter_the_battlefield`) compared against the *current* turn number
    (`Game.turn.turns_taken`) - the identical reading `machines/targeting.py`
    already gives the same phrase for a *targeted* restriction, applied here
    to every matching permanent at once rather than to one chosen target.
    "Each other" excludes only the resolving ability's own source by id -
    "nonland permanent" already excludes lands on its own, and a permanent
    that is neither is simply not in the candidate set to begin with.

    Ability-only: nothing in the pool prints this on a spell, and a
    resolving spell has no `source_id` of its own to exclude by (`for_spell`
    kept only so this fits the shared `TargetedClause`/whole-text call
    convention every other reader in this module uses).
    """
    if for_spell:
        return None
    match = _RETURN_EACH_OTHER_ENTERED_THIS_TURN_TO_HAND_RE.fullmatch(
        " ".join(text.strip().split())
    )
    if match is None:
        return None
    type_matches = _parse_mass_type_qualifier(match.group("qualifier"))
    if type_matches is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        turn_number = game.turn.turns_taken if game.turn is not None else None
        if turn_number is None:
            return
        source_id = ability.source_id
        targets = [
            permanent
            for permanent in list(game.battlefield)
            if permanent.id != source_id
            and permanent.turn_entered == turn_number
            and type_matches(game.characteristics_of(permanent))
        ]
        if not targets:
            return
        with game.returning_together():  # CR 603.2c: one event, several cards
            for permanent in targets:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.return_to_hand(permanent)

    return effect


#: "Return target creature card and all other cards with the same name as
#: that card from your graveyard to the battlefield tapped." - Rat King,
#: Verminister's own activated ability (TMT). `split_effect_clauses`'s bare
#: "and" cuts this into `['Return target creature card', 'all other cards
#: with the same name as that card from your graveyard to the battlefield
#: tapped']` - the second fragment has no verb of its own - so it is read
#: whole here instead.
#:
#: The destination is read rather than pinned to "the battlefield": Echoing
#: Return (Modern-legal proof printing, a sorcery rather than an activated
#: ability) prints the identical "and all other cards with the same name as
#: that card from your graveyard" middle but returns "to your hand" instead -
#: the same CR 201.2a grouping, a different destination CR 608.2c names.
_RETURN_TARGET_AND_SAME_NAME_FROM_GRAVEYARD_RE = re.compile(
    r"^return (?P<phrase>target .+?) and all other cards with the same name as that card "
    r"from your graveyard to (?:the battlefield(?P<tapped> tapped)?|your hand)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s37", for_spell=False)
@SPELL_TEXT.rung("s5", for_spell=True)
def _parse_return_target_and_same_name_from_graveyard_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_TARGET_AND_SAME_NAME_FROM_GRAVEYARD_RE`'s shape, or `None`.

    The regex's own `phrase` group is only the target description ("target
    creature card"); `from your graveyard` is reattached before it reaches
    `_targets_understood`, because `machines/targeting.profile_for_text`
    reads the origin zone off that phrase, not off anything downstream of it
    (a bare "target creature card" alone is `not understood` - no zone at
    all - since nothing says where to look).

    CR 201.2a: "Two or more objects have the same name if they have at least
    one name in common" - read here as an exact `CardState.name` match
    against every *other* card presently sitting in the same player's
    graveyard as the chosen target, the same "read the live object's own
    name" comparison the rest of this module already uses wherever a card
    describes itself (`target.name` printed into decision prompts
    throughout). Every card in the resulting group moves together
    (CR 603.6a/603.2c: one instruction, one event), so a static ability any
    of them grants the others on the way onto the battlefield already sees
    the whole group; to hand, `returning_together` is the identical batching
    for CR 603.2c's own "return" wording.
    """
    match = _RETURN_TARGET_AND_SAME_NAME_FROM_GRAVEYARD_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if not _targets_understood(
        f"{match.group('phrase')} from your graveyard", battlefield_only=False
    ):
        return None
    tapped = match.group("tapped") is not None
    to_battlefield = "to your hand" not in " ".join(text.strip().split()).lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD
        ]
        if not targets:
            return
        target = targets[0]
        name = target.name
        group = [target] + [
            card
            for card in list(controller.graveyard)
            if card.id != target.id and card.zone is Zone.GRAVEYARD and card.name == name
        ]
        if to_battlefield:
            with game.entering_together():  # CR 603.6a: one arrival, together
                for card_state in group:
                    if card_state.zone is Zone.GRAVEYARD:
                        game.put_onto_battlefield(card_state, controller.username, tapped=tapped)
        else:
            with game.returning_together():  # CR 603.2c: one event, several cards
                for card_state in group:
                    if card_state.zone is Zone.GRAVEYARD:
                        game.return_to_hand(card_state)

    return effect


def _bring_in_from_outside_the_game_or_exile(
    game: "Game",
    ability: AbilityOnStack,
    quality: Type,
    exile_quality: Type,
) -> None:
    """Perform the ability `_parse_outside_the_game_fetch` read (CR 608.2d).

    The candidates are computed twice over, in the two places the sentence
    names, and both are filtered by CR 108.3's **owner** - not the controller.
    Exile is a shared zone, so an opponent's card sitting face up in it is
    visible, choosable-looking, and not this player's to take.

    A `DecisionKind.CHOOSE_CARDS` question puts the choice to the ability's
    controller. That kind is deliberately reused rather than grown into a new
    one - its own docstring in `machines/decisions.py` says so: "any 'choose N
    of these cards' question (a search turning up more hits than needed,
    choosing among revealed cards) is the same question with a different prompt
    and a different source zone". The candidate ids therefore travel in the
    same `Decision.cards` field a scry's do, and are subject to the same
    per-player hidden-information filtering on the way out; the one card the
    player ends up revealing is recorded publicly on `Game.reveals`, and
    nothing else about the sideboard ever becomes public.

    With nothing legal to choose, the ability resolves having done nothing:
    CR 608.2d's "The player can't choose an option that's illegal or
    impossible", and there is no "if you can't, ..." clause to fall through to.
    """
    controller = game.player(ability.controller)

    def is_wanted(state: CardState, card_type: Type) -> bool:
        return card_type in state.types

    outside = controller.owned_outside_the_game(lambda state: is_wanted(state, quality))
    in_exile = game.face_up_cards_in_exile(
        owner=controller.username, matches=lambda state: is_wanted(state, exile_quality)
    )
    candidates = outside + in_exile
    if not candidates:
        return

    # CR 608.2d's plain "you may": the whole instruction is optional.
    if not game.may(
        controller,
        f"reveal {with_indefinite_article(f'{quality.value} card')} you own from outside the game, "
        f"or choose a "
        f"face-up one you own in exile",
        source=ability.source_name,
        source_id=source_id_of(ability),
    ):
        return

    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt=(
                f"choose {with_indefinite_article(f'{quality.value} card')} "
                "you own to put into your hand"
            ),
            source=ability.source_name,
            source_id=source_id_of(ability),
            amount=1,
            cards=tuple(state.id for state in candidates),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in candidates}
    for card_id in chosen_ids:
        chosen = by_id[card_id]
        if chosen.zone.is_outside_the_game:
            # CR 701.20a: the reveal is what makes taking it from a group
            # nobody may look at public information, and CR 701.20b leaves the
            # card where it is - so it is revealed first, then brought in.
            _reveal_and_bring_into_hand(game, controller, chosen, ability.source_name)
        else:
            # Already face up in exile (CR 406.3), so nothing to reveal.
            game.return_to_hand(chosen)


# --------------------------------------------------------------------------
# Returning a card from a graveyard to the battlefield (CR 110.2a)
# --------------------------------------------------------------------------
#
# Every shape here is "put onto the battlefield" rather than "cast", so
# CR 110.2a applies and no "when you cast" ability ever fires
# (`Game.put_onto_battlefield`'s own docstring). CR 400.7: the card that
# arrives is a new object, which is why nothing about the card's earlier life
# on the battlefield is carried back with it.

#: "Return this card from your graveyard to the battlefield[ tapped][ with N
#: `<kind>` counter(s) on `<pronoun>`]." - Cauldron Familiar's and Arclight
#: Phoenix's own bare shape, Grim Repriser's and Proctor of Potential's own
#: "with a finality counter on it" (CR 122.1h), and Gallia, Tragic Host's own
#: "tapped with a +1/+1 counter on her" - the source's own gendered pronoun
#: (CR 201.5), read the same closed set `_OBJECT_ANAPHOR`'s own "it|him|her"
#: alternatives already are, not a second copy of that vocabulary.
#: "Return target creature card from your graveyard to the battlefield
#: tapped and attacking[ with a `<kind>` counter on it]." - Grim Reaper,
#: Lethal Legionnaire's own reflexive "when you do" consequence (CR 508.4c:
#: with no attacked player/planeswalker named, the reanimated creature
#: attacks whoever/whatever the resolving ability's own source is currently
#: attacking).
_RETURN_TARGET_FROM_GRAVEYARD_TAPPED_AND_ATTACKING_RE = re.compile(
    r"^return target creature card from your graveyard to the battlefield "
    r"tapped and attacking"
    r"(?: with an? (?P<counter>[a-z0-9+/-]+) counter on it)?\.?$",
    re.IGNORECASE,
)


def _parse_return_target_from_graveyard_tapped_and_attacking_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_TARGET_FROM_GRAVEYARD_TAPPED_AND_ATTACKING_RE`'s shape, or
    `None`.

    Ability-only: `game.combat.attack_by` reads the resolving ability's own
    source, which only an `AbilityOnStack` has (CR 113.7a).
    """
    if for_spell:
        return None
    match = _RETURN_TARGET_FROM_GRAVEYARD_TAPPED_AND_ATTACKING_RE.fullmatch(clause.strip())
    if match is None:
        return None
    counter_kind = match.group("counter")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        source = ability.source(game)
        if source is None:
            return
        current_attack = game.combat.attack_by(source.id)
        if current_attack is None:
            return
        for target in game.resolve_card_targets(ability):
            if target.zone is not Zone.GRAVEYARD:
                continue
            controller = game.controller_of(ability).username
            permanent = game.put_onto_battlefield(target, controller, tapped=True)
            if permanent.zone is not Zone.BATTLEFIELD:
                continue
            if counter_kind:
                game.add_counters(permanent, counter_kind.lower(), 1)
            from ...models.token import _put_onto_the_battlefield_attacking

            _put_onto_the_battlefield_attacking(game, permanent, current_attack.defender)

    return effect


_RETURN_SELF_FROM_GRAVEYARD_TO_BATTLEFIELD_RE = re.compile(
    r"^return this card from your graveyard to the battlefield"
    r"(?P<tapped> tapped)?"
    rf"(?: with (?P<counter_n>{COUNT}) (?P<counter>[a-z0-9+/-]+) counters? "
    r"on (?:it|him|her|them))?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_return_self_from_graveyard_to_battlefield_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_SELF_FROM_GRAVEYARD_TO_BATTLEFIELD_RE`'s shape - Cauldron
    Familiar's "Sacrifice a Food:" ability and Arclight Phoenix's own combat
    trigger.

    "This card" is CR 700.7's self-reference - the object the ability is
    printed on, found by id wherever it is now (CR 113.7a). The return only
    happens if that object really is still in a graveyard: an ability whose
    card has already moved on resolves and does nothing, which is CR 608.2's
    ordinary "the object is gone" case rather than an error.

    Never a spell's own shape - an instant or sorcery saying this about
    itself does not exist - so `for_spell` refuses outright rather than
    reaching for a `CardState` that would be the spell on the stack.
    """
    if for_spell:
        return None
    match = _RETURN_SELF_FROM_GRAVEYARD_TO_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    tapped = bool(match.group("tapped"))
    counter_kind = match.group("counter")
    counter_amount = parse_count(match.group("counter_n")) if counter_kind else 0
    if counter_kind and not counter_amount:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        permanent = game.put_onto_battlefield(
            source, game.controller_of(stack_object).username, tapped=tapped
        )
        if counter_kind and permanent.zone is Zone.BATTLEFIELD:
            game.add_counters(permanent, counter_kind.lower(), counter_amount or 0)

    return effect


#: "Return this card from your graveyard to the battlefield attached to
#: target creature you control[ with power `<n>` or less]. Activate only as
#: a sorcery." - Eagle's Rescue's own graveyard-zone activated ability
#: (CR 113.6m), a twin of `_RETURN_SELF_FROM_GRAVEYARD_TO_BATTLEFIELD_RE`
#: with CR 701.3a's attach in place of that shape's own optional "tapped"/
#: counters tail. "Activate only as a sorcery" is stripped by `effect_for`'s
#: own `_CAST_TIMING_RESTRICTION_RE` before this ever sees it, the same way
#: it already is for every other timing-restricted ability.
_RETURN_SELF_FROM_GRAVEYARD_ATTACHED_RE = re.compile(
    r"^return this card from your graveyard to the battlefield attached to "
    r"target creature(?P<you_control> you control)?"
    r"(?P<power_bound> with power (?P<power>\d+) or less)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_return_self_from_graveyard_to_battlefield_attached_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_SELF_FROM_GRAVEYARD_ATTACHED_RE`'s shape - see the banner
    above. The target is announced and re-checked exactly as every other
    targeted ability's is (CR 601.2c/CR 608.2b); the card only returns, and
    only attaches, if it is still in a graveyard and the target is still
    legal once the ability resolves.
    """
    if for_spell:
        return None
    match = _RETURN_SELF_FROM_GRAVEYARD_ATTACHED_RE.fullmatch(clause.strip())
    if match is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        target = next(
            (t for t in game.resolve_targets(stack_object) if isinstance(t, CardState)), None
        )
        if target is None:
            return
        permanent = game.put_onto_battlefield(source, game.controller_of(stack_object).username)
        if permanent.zone is Zone.BATTLEFIELD:
            attach_permanent(game, permanent, target)

    return effect


#: "return it to the battlefield[ tapped][ and][ transformed] under its
#: owner's/your control[ with `<n>` `<kind>` counters on it]." - the Ojer
#: cycle's own death trigger (Ojer Taq, Deepest Foundation: "When Ojer Taq
#: dies, return it to the battlefield tapped and transformed under its
#: owner's control.") and its sibling Ojer Pakpatiq, Deepest Epoch, which adds
#: the trailing counters clause the first does not print ("... with three
#: time counters on it."). Read generally rather than pinned to either
#: printing: any future card sharing the sentence, whichever amount and kind
#: of counter it names, reaches this the same way.
#:
#: "It" is CR 400.7's own anaphor for the object the ability is printed on -
#: by the time a "dies" trigger resolves, that object is a new one wherever
#: it landed (almost always a graveyard), found by id the same way
#: `_parse_return_self_from_graveyard_to_battlefield_clause` finds "this
#: card". CR 701.27a/CR 712.14a: "transformed" describes how the permanent
#: *enters*, so the return goes through `Game.put_onto_battlefield
#: (transformed=True)` rather than transforming it afterwards.
_RETURN_SELF_TO_BATTLEFIELD_TRANSFORM_RE = re.compile(
    r"^return it to the battlefield"
    r"(?P<tapped> tapped)?"
    r"(?: and)?"
    r"(?P<transformed> transformed)?"
    r" under (?P<control>its owner'?s|your) control"
    rf"(?: with (?P<amount>{COUNT}) (?P<kind>[+/\w-]+) counters? on it)?"
    r"\.?$",
    re.IGNORECASE,
)


#: "return it to the battlefield under its owner's control. It's an
#: enchantment. (It's not a creature.)" - the Enduring cycle's death trigger
#: (Enduring Innocence, Enduring Curiosity): the source returns with its card
#: types *set* to the named list. The reminder parenthesis is tolerated
#: whether or not the oracle stripper already removed it.
#:
#: Widened for a plural subject and no explicit control clause - Tom, Bert,
#: and William's own "return them to the battlefield. They're an artifact.
#: (They're no longer a creature.)": a legendary creature that is three
#: named characters at once (CR 201.5's own printed-name self-reference
#: already carries the plural verb "die" on the condition side; the effect
#: keeps the same plurality) prints "them"/"they're" instead of "it"/"it's",
#: and prints no "under ... control" clause at all - CR 110.2a's own default
#: ("that object enters the battlefield under that player's control unless
#: the effect states otherwise") is exactly the `under_owner=False` branch
#: already below, read for a card that never states otherwise rather than
#: one more control phrase to match. The reminder text differs too ("no
#: longer a creature" rather than "not a creature") for the identical reason
#: the main sentence's pronoun does; both are read as loose, optional
#: reminder text either way.
_CARD_TYPE_WORD = r"(?:artifact|battle|creature|enchantment|land|planeswalker)"
_RETURN_SELF_AS_TYPE_RE = re.compile(
    r"^return (?:it|them) to the battlefield(?P<tapped> tapped)?"
    r"(?: under (?P<control>its owner'?s|your) control)?\.\s*"
    rf"(?:it'?s|they'?re) an? (?P<types>{_CARD_TYPE_WORD}(?:(?:,| and|, and) {_CARD_TYPE_WORD})*)\."
    r"(?:\s*\((?:it'?s not|they'?re no longer) an? [a-z]+\.\))?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s23")
def _parse_return_self_as_type_clause(text: str) -> AbilityEffect | None:
    """`_RETURN_SELF_AS_TYPE_RE`'s shape.

    CR 205.1a: "Some effects set an object's card type. In most such cases,
    the new card type(s) replaces any existing card types" - and a subtype
    correlated only with a removed card type goes with it, so Enduring
    Innocence comes back an enchantment with neither Sheep nor Glimmer. The
    type is part of the return itself, so the layer 4 effect (CR 613.1d) is
    in place before the enters event is announced: `Game.entering_together`
    defers that announcement until the effect exists, and a "whenever a
    creature enters" ability never sees a creature arrive.

    The return only happens if the card is still in the graveyard it died
    into (CR 400.7: exiled in response it is a new object), the same gate
    `_parse_return_self_to_battlefield_transformed_clause` uses. The returned
    permanent is a new object (CR 400.7), so the selector is keyed on the
    incarnation it arrives as, and the effect lasts until it leaves (CR
    611.2a: no duration stated).
    """
    match = _RETURN_SELF_AS_TYPE_RE.fullmatch(text.strip())
    if match is None:
        return None
    types = tuple(Type(word) for word in re.findall(_CARD_TYPE_WORD, match.group("types").lower()))
    tapped = match.group("tapped") is not None
    control = match.group("control")
    # CR 110.2a: no printed control clause at all defaults to the resolving
    # ability's own controller - the identical `under_owner=False` reading
    # "your control" already gets, since neither ever names the owner.
    under_owner = control is not None and control.lower().startswith("its")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        controller = (source.owner or ability.controller) if under_owner else ability.controller
        with game.entering_together():
            returned = game.put_onto_battlefield(source, controller, tapped=tapped)
            if returned.zone is not Zone.BATTLEFIELD:
                return
            kept = tuple(
                subtype
                for subtype in returned.subtypes
                if any(subtype in CLOSED_SUBTYPE_LISTS.get(kind, ()) for kind in types)
            )
            game.continuous_effects.add(
                ContinuousEffect(
                    description=f"{returned.name}: it's {with_indefinite_article(types[0].value)}",
                    layer=Layer.TYPE,
                    timestamp=game.continuous_effects.tick(),
                    duration=Duration.INDEFINITE,
                    selector=only_this_incarnation(returned, returned.zone_change_stamp),
                    modification=SetTypesAndSubtypes(types=types, subtypes=kept),
                )
            )

    return effect


@ABILITY_TEXT.rung("s24")
def _parse_return_self_transformed_attached_clause(text: str) -> AbilityEffect | None:
    """ "return <it|this card> to the battlefield transformed under your
    control[ attached to <target>]." - Accursed Witch, Radiant Grace, Skin
    Invasion, Vengeful Strangler. Read by `machines/return_transformed_
    attached.parse_return_self_transformed_clause`."""
    from ..return_transformed_attached import parse_return_self_transformed_clause

    return parse_return_self_transformed_clause(text)


@ABILITY_TEXT.rung("s24")
def _parse_return_subject_then_self_transformed_clause(text: str) -> AbilityEffect | None:
    """ "return it to the battlefield under your control, then return this
    card to the battlefield transformed under your control." - Journey to
    Eternity. Read by `machines/return_transformed_attached.
    parse_return_subject_then_self_transformed_clause`."""
    from ..return_transformed_attached import (
        parse_return_subject_then_self_transformed_clause,
    )

    return parse_return_subject_then_self_transformed_clause(text)


@ABILITY_TEXT.rung("s24", for_spell=False)
@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_return_self_to_battlefield_transformed_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_SELF_TO_BATTLEFIELD_TRANSFORM_RE`'s shape.

    Never a spell's own shape: "return it to the battlefield ... under its
    owner's control" with no preceding exile or destroy names nothing for a
    resolving instant or sorcery to act on - this is always a triggered or
    activated ability reading its own source back.

    The return only happens if the card genuinely is still wherever it went
    (CR 608.2's ordinary "the object is gone" case) - gated the same way the
    "this card" sibling above is, on the object still sitting in a graveyard,
    since every printing of this sentence is a death trigger.
    """
    if for_spell:
        return None
    match = _RETURN_SELF_TO_BATTLEFIELD_TRANSFORM_RE.fullmatch(clause.strip())
    if match is None:
        return None
    tapped = match.group("tapped") is not None
    transformed = match.group("transformed") is not None
    under_owner = match.group("control").lower().startswith("its")
    counter_kind = _counter_kind(match.group("kind")) if match.group("kind") else None
    counter_amount = parse_count(match.group("amount")) if match.group("amount") else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        controller = (
            source.owner or game.controller_of(stack_object).username
            if under_owner
            else game.controller_of(stack_object).username
        )
        returned = game.put_onto_battlefield(
            source, controller, tapped=tapped, transformed=transformed
        )
        if returned.zone is Zone.BATTLEFIELD and counter_kind is not None and counter_amount:
            game.add_counters(returned, counter_kind, counter_amount)

    return effect


#: "return that card to the battlefield[ tapped] under `<its owner's|your>`
#: control[ with `<n>` `<kind>` counters on it]." - Ferocity of the Hunt's
#: own "When enchanted creature dies, return that card to the battlefield
#: tapped under its owner's control.", and Unhallowed Pact's real, off-set
#: "When enchanted creature dies, return that card to the battlefield under
#: your control." "That card" is CR 400.7's anaphor for the *triggering
#: event's own subject* - the creature that just died - not the ability's
#: own source (`ability.source_id` names the Aura itself, a different
#: object): the sibling regex just above reads "it" as the ability's own
#: source (Ojer Taq's own death trigger, self-referential), but an Aura's
#: "enchanted creature dies" trigger fires on a *different* permanent's
#: death, so this reads `AbilityOnStack.event.subject_id` instead - the same
#: field `event_subject_power` already reads for a dying creature's power.
_RETURN_EVENT_SUBJECT_TO_BATTLEFIELD_RE = re.compile(
    r"^return that card to the battlefield"
    r"(?P<tapped> tapped)?"
    r" under (?P<control>its owner'?s|your) control"
    rf"(?: with (?P<amount>{COUNT}) (?P<kind>[+/\w-]+) counters? on it)?"
    r"\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_return_event_subject_to_battlefield_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_EVENT_SUBJECT_TO_BATTLEFIELD_RE`'s shape - see its own
    docstring for why this reads the triggering event's subject rather than
    the ability's own source.

    Never a spell's own shape (no resolving instant or sorcery has a
    triggering event to read "that card" off of), and the return only
    happens if the dead permanent is genuinely still sitting in a graveyard
    (CR 608.2's ordinary "the object is gone" case) - the same recheck every
    sibling in this section already applies.
    """
    if for_spell:
        return None
    match = _RETURN_EVENT_SUBJECT_TO_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    tapped = match.group("tapped") is not None
    under_owner = match.group("control").lower().startswith("its")
    counter_kind = _counter_kind(match.group("kind")) if match.group("kind") else None
    counter_amount = parse_count(match.group("amount")) if match.group("amount") else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        event = stack_object.event
        if event is None or event.subject_id is None:
            return
        card = game.find_by_id(event.subject_id)
        if card is None or card.zone is not Zone.GRAVEYARD:
            return
        controller = (
            (card.owner or game.controller_of(stack_object).username)
            if under_owner
            else game.controller_of(stack_object).username
        )
        returned = game.put_onto_battlefield(card, controller, tapped=tapped)
        if returned.zone is Zone.BATTLEFIELD and counter_kind is not None and counter_amount:
            game.add_counters(returned, counter_kind, counter_amount)

    return effect


#: "Return all <description> from your graveyard to the battlefield[ tapped]."
#: - Raise the Past, and Aftermath Analyst's own "Return all land cards from
#: your graveyard to the battlefield tapped." CR 608.2f: the whole group
#: moves as one action, so the candidate set is snapshotted before any of
#: them arrives.
_MASS_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_RE = re.compile(
    r"^return all (?P<rest>.+?) from your graveyard to the battlefield(?P<tapped> tapped)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_mass_return_from_graveyard_to_battlefield_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_MASS_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_RE`'s shape - Raise the
    Past's whole spell, and Aftermath Analyst's "... to the battlefield
    tapped." sacrifice ability.

    "Your graveyard" is the resolving object's controller's, and every card
    arrives under that same player's control (CR 110.2a names who controls a
    permanent an effect puts onto the battlefield; with nobody else named it
    is the spell or ability's own controller). Snapshotted first (CR 608.2f),
    so a trigger caused by an early return cannot change what the rest of the
    group still is. The trailing "tapped" is CR 110.5b's own instruction on how
    the permanent enters, threaded straight through to
    `Game.put_onto_battlefield`'s `tapped=` - the same parameter Aftermath
    Analyst's own ETB mill trigger has nothing to do with.
    """
    match = _MASS_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    predicate = _parse_card_group_qualifier(match.group("rest"))
    if predicate is None:
        return None
    tapped = match.group("tapped") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        chosen = [state for state in list(controller.graveyard) if predicate(state)]
        for state in chosen:
            if state.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(state, controller.username, tapped=tapped)

    return effect


#: "Return all <description> from your graveyard to your hand." - Wrenn and
#: Seven's own -8, "Return all permanent cards from your graveyard to your
#: hand." The hand-bound twin of `_MASS_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_
#: RE` right above - same subject, same source zone, a different
#: destination and (CR 400.7's plain "new object") no "tapped" of its own to
#: read, since a card in a hand has no such status (CR 110.5d).
_MASS_RETURN_FROM_GRAVEYARD_TO_HAND_RE = re.compile(
    r"^return all (?P<rest>.+?) from your graveyard to your hand\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_mass_return_from_graveyard_to_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_MASS_RETURN_FROM_GRAVEYARD_TO_HAND_RE`'s shape - Wrenn and Seven's
    -8, its own "permanent cards" quality read the same way `_parse_card_
    group_qualifier`'s "permanent"/"permanents" branch already reads it for
    the battlefield-bound family (CR 110.4a's own fifteen-type-minus-
    instant-and-sorcery group).

    Snapshotted before any card moves (CR 608.2f, the same reasoning
    `_parse_mass_return_from_graveyard_to_battlefield_clause` documents),
    and moved through `Game.return_to_hand` - the same primitive Raise
    Dead's own single-target return already uses.
    """
    match = _MASS_RETURN_FROM_GRAVEYARD_TO_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    predicate = _parse_card_group_qualifier(match.group("rest"))
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        chosen = [state for state in list(controller.graveyard) if predicate(state)]
        for state in chosen:
            if state.zone is Zone.GRAVEYARD:
                game.return_to_hand(state)

    return effect


#: "Each player returns all <description> from their graveyard to their hand."
#: (Empty the Catacombs; Underworld Cerberus' dies trigger after its "exile it
#: and") - `_MASS_RETURN_FROM_GRAVEYARD_TO_HAND_RE`'s subject widened from
#: "you" to every player: each player's own graveyard goes to that same
#: player's hand (CR 404.1 / CR 108.3 - a graveyard card's owner is the player
#: whose graveyard it is in).
_EACH_PLAYER_RETURNS_FROM_GRAVEYARD_TO_HAND_RE = re.compile(
    r"^each player returns all (?P<rest>.+?) from their graveyard to their hand\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_each_player_returns_from_graveyard_to_hand_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_RETURNS_FROM_GRAVEYARD_TO_HAND_RE`'s shape.

    The group is chosen in every graveyard before anything moves (CR 608.2f's
    snapshot, as `_parse_mass_return_from_graveyard_to_hand_clause` does) and
    each card goes through `Game.return_to_hand`, the same zone move the
    controller-only reader makes.
    """
    match = _EACH_PLAYER_RETURNS_FROM_GRAVEYARD_TO_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    predicate = _parse_card_group_qualifier(match.group("rest"))
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        chosen = [
            state
            for player in game.players_in_game
            for state in list(player.graveyard)
            if predicate(state)
        ]
        for state in chosen:
            if state.zone is Zone.GRAVEYARD:
                game.return_to_hand(state)

    return effect


#: "Return all <description> to their owners' hands." - Sunderflock's own
#: enters trigger. `_RETURN_TARGET_RE`'s verb with no target at all: every
#: permanent on the battlefield matching the description.
_MASS_RETURN_TO_HAND_RE = re.compile(
    r"^return all (?P<rest>.+?) to their owners'? hands\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_mass_return_to_hand_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_MASS_RETURN_TO_HAND_RE`'s shape - Sunderflock's "return all
    non-Elemental creatures to their owners' hands."

    The group is read off the *computed* board (`Game.computed_board`) for its types and
    subtypes, the same correction `_parse_mass_type_qualifier` already makes
    for a mass destruction: a permanent that became a creature, or gained a
    creature type, only through a continuous effect is one of "all creatures"
    and one of "all Elementals" too. `Game.return_to_hand` is the same zone
    move (CR 400.6, CR 400.7) every other return in this file makes, and
    CR 608.2f snapshots the group before any of it moves.
    """
    match = _MASS_RETURN_TO_HAND_RE.fullmatch(clause.strip())
    if match is None:
        return None
    text = match.group("rest").strip()
    excluded_subtype: str | None = None
    negated = _NON_SUBTYPE_PREFIX_RE.fullmatch(text)
    if negated is not None:
        excluded_subtype = negated.group("subtype").lower()
        text = negated.group("rest").strip()
    type_matches = _parse_mass_type_qualifier(text)
    if type_matches is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        board = game.computed_board()
        chosen: list[CardState] = []
        for permanent in list(game.battlefield):
            chars = board.of(permanent)
            if not type_matches(chars):
                continue
            if excluded_subtype is not None and excluded_subtype in {
                subtype.lower() for subtype in chars.subtypes
            }:
                continue
            chosen.append(permanent)
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for permanent in chosen:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.return_to_hand(permanent)

    return effect


# --------------------------------------------------------------------------
# "Return target X to its owner's hand. If you controlled that permanent,
# draw a card." (Boomerang Basics)
# --------------------------------------------------------------------------
#
# One CR 608.2c instruction in two sentences: "that permanent" is anaphoric
# (CR 700.7) for whatever the first sentence returned, and the question the
# second asks - who controlled it - can only be answered *before* the return
# happens, because the moment it reaches a hand it is a new object with no
# controller at all (CR 400.7, CR 108.4: "A card doesn't have a controller
# unless that card represents a permanent or spell").

_RETURN_TARGET_THEN_CONDITIONAL_DRAW_RE = re.compile(
    r"^return (?P<phrase>.*target.+?) to its owner'?s hand\.\s*"
    r"if you controlled that permanent, draw a card\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s21")
def _parse_return_target_then_conditional_draw(text: str) -> Effect | None:
    """`_RETURN_TARGET_THEN_CONDITIONAL_DRAW_RE`'s shape - Boomerang Basics.

    The controller check is made against the target as it still stands on the
    battlefield, for the reason the section banner above gives, and the draw
    happens after the return, in printed order (CR 608.2c). A spell whose
    target is gone by resolution (CR 608.2b) returns nothing and draws
    nothing - there is no "that permanent" left to have controlled.
    """
    match = _RETURN_TARGET_THEN_CONDITIONAL_DRAW_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        targets = [
            target for target in game.resolve_targets(spell) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        controlled_it = target.controller == controller.username
        game.return_to_hand(target)
        if controlled_it:
            game.draw_cards(controller.username, 1)

    return effect


# --------------------------------------------------------------------------
# Greasefang, Okiba Boss: reanimate a target, grant it a keyword, and set up
# the delayed return (CR 603.7)
# --------------------------------------------------------------------------
#
# "Return target Vehicle card from your graveyard to the battlefield. It
# gains haste. Return it to its owner's hand at the beginning of your next
# end step."
#
# All three sentences are one CR 608.2c instruction: the second and third
# both say "it", anaphoric (CR 700.7) for the card the first returned, and
# neither can be read on its own by any clause parser in this file. The
# keyword grant is a layer 6 continuous effect (CR 613.1f) with no stated
# duration, so CR 611.2a leaves it indefinite - it lasts as long as the
# permanent does, which is until the delayed trigger takes it away.

_RETURN_TARGET_FROM_GRAVEYARD_GAINS_THEN_BOUNCE_RE = re.compile(
    r"^return (?P<phrase>target .+? from your graveyard) to the battlefield\.\s*"
    r"it gains (?P<keyword>[a-z][a-z ]*?)\.\s*"
    r"return it to its owner'?s hand at the beginning of your next end step\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s32")
def _parse_return_target_from_graveyard_gains_then_bounce(text: str) -> AbilityEffect | None:
    """`_RETURN_TARGET_FROM_GRAVEYARD_GAINS_THEN_BOUNCE_RE`'s shape -
    Greasefang, Okiba Boss's own combat trigger.

    The delayed ability is CR 603.7a's, created as this resolves and fired at
    the beginning of *this player's* next end step - `DelayedTrigger.
    only_when_active` is what makes it "your" end step rather than the next
    one of any turn, the same field Emrakul's own extra turn uses. CR 603.7c
    is why the trigger records the returned card's zone and zone-change stamp:
    a permanent that has already left the battlefield by then is a different
    object and the ability does nothing to it.
    """
    match = _RETURN_TARGET_FROM_GRAVEYARD_GAINS_THEN_BOUNCE_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False, battlefield_only=False):
        return None
    keyword = match.group("keyword").strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        controller = game.controller_of(ability)
        put = game.put_onto_battlefield(target, controller.username)
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{ability.source_name}: {put.name} gains {keyword}",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.INDEFINITE,
                selector=_only(put.id),
                modification=grant_ability(keyword.title()),
            )
        )
        game.create_delayed_trigger(
            DelayedTrigger(
                text=("Return it to its owner's hand at the beginning of your next end step."),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=controller.username,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=put.id,
                only_when_active=controller.username,
                expected_zone=Zone.BATTLEFIELD,
                expected_stamp=put.zone_change_stamp,
                effect=return_subject_to_hand,
            )
        )

    return effect


#: "Return up to `<n>` `<group>` cards with total mana value `<total>` or
#: less from your graveyard to the battlefield." - Lively Dirge's own Spree
#: mode (CR 702.172a). The identical two-bound shape `_LOOK_TOP_N_PUT_
#: TOTAL_MV_ONTO_BATTLEFIELD_RE` already reads for a library look - "up to
#: N" cards whose mana values (CR 202.3) sum to at most a printed total, a
#: resolution-time choice (CR 608.2d) rather than a cast-time target - fed
#: from the graveyard instead: `_parse_card_group_qualifier` is the same
#: card-type-group reader either shares.
_RETURN_UP_TO_N_TOTAL_MV_FROM_GRAVEYARD_TO_BATTLEFIELD_RE = re.compile(
    rf"^return up to (?P<take>{COUNT}) (?P<group>[a-z]+) cards with total mana value "
    r"(?P<total>\d+) or less from your graveyard to the battlefield\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s22")
def _parse_return_up_to_n_total_mv_from_graveyard_to_battlefield(text: str) -> Effect | None:
    """`_RETURN_UP_TO_N_TOTAL_MV_FROM_GRAVEYARD_TO_BATTLEFIELD_RE`'s shape,
    or `None`. Both bounds are the choosing player's own to respect, refused
    rather than silently trimmed - the identical CR 608.2d discipline
    `_parse_look_top_n_put_total_mv_onto_battlefield` already keeps for its
    own pair of the same two bounds.
    """
    match = _RETURN_UP_TO_N_TOTAL_MV_FROM_GRAVEYARD_TO_BATTLEFIELD_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    take = parse_count(match.group("take"))
    if take is None:
        return None
    predicate = _parse_card_group_qualifier(match.group("group"))
    if predicate is None:
        return None
    total_bound = int(match.group("total"))

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        candidates = [state for state in controller.graveyard if predicate(state)]
        taken: list[CardState] = []
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"return up to {take} cards with total mana value {total_bound} "
                        "or less from your graveyard to the battlefield"
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
                    f"{spell.name} returns up to {take} cards from the graveyard, not {len(taken)}"
                )
            total = sum(state.card.cmc or 0 for state in taken)
            if total > total_bound:
                raise ValueError(
                    f"{spell.name} allows total mana value {total_bound} or less, not {total:g}"
                )
        for state in taken:
            game.put_onto_battlefield(state, controller.username)

    return effect


#: "Return `<it|him|her|them>` to the battlefield[ tapped] under `<its owner's|
#: your>` control[ with `<n>` `<kind>` counter(s) on `<it>`]. `<It|She|That
#: creature>` `<rider>`." - Hellcat, Undying Vigilante's "... with a +1/+1
#: counter on her. She loses all abilities and gains haste." and Thunderbolts
#: Conspiracy's "... with a finality counter on it. That creature is a Hero in
#: addition to its other types." Read whole: the rider's subject is the
#: object the return just made (CR 400.7), which only this reader knows.
#:
#: "It" is the triggering event's subject when the event names one (the
#: Villain that died, not the Conspiracy), else the ability's own source.
_RETURN_WITH_RIDER_RE = re.compile(
    r"^return (?:it|him|her|them|that card|that creature) to the battlefield(?P<tapped> tapped)?"
    r" under (?P<control>(?:its|his|her|their) owners?'?s?|your) control"
    rf"(?: with (?P<amount>{COUNT}) (?P<kind>[+/\w-]+) counters? on (?:it|him|her|them))?\.\s*"
    r"(?:it|he|she|they|that creature) (?P<rider>.+?)\.?$",
    re.IGNORECASE,
)

#: One rider predicate: "loses all abilities", "gains <keywords>", or "is
#: a[n] <creature types> in addition to its other types" (CR 205.1b).
_RETURN_RIDER_PREDICATE_RE = re.compile(
    r"^(?:(?P<loses>loses all abilities)"
    r"|gains (?P<keywords>[a-z][a-z ,]*?)"
    r"|is an? (?P<types>[A-Za-z][A-Za-z' -]*?) in addition to its other types)$",
    re.IGNORECASE,
)


def _return_rider_modifications(rider: str) -> "list[tuple[str, Layer, Modification]] | None":
    """Each predicate of a return rider as its layer and modification (CR
    613.1d/e/f), in printed order - or `None` for one this reader cannot
    read (the whole ability then fails closed)."""
    from ..layers import _creature_type_words, _split_and_validate_keywords

    parts: list[tuple[str, Layer, Modification]] = []
    for predicate in re.split(r"\s+and\s+(?=loses|gains|is\b)", rider.strip()):
        match = _RETURN_RIDER_PREDICATE_RE.fullmatch(predicate.strip())
        if match is None:
            return None
        if match.group("loses"):
            parts.append(("loses all abilities", Layer.ABILITY, lose_all_abilities))
            continue
        if match.group("keywords") is not None:
            keywords = _split_and_validate_keywords(match.group("keywords"))
            if keywords is None:
                return None
            parts.extend((f"gains {kw}", Layer.ABILITY, grant_ability(kw)) for kw in keywords)
            continue
        subtypes = _creature_type_words(match.group("types"))
        if subtypes is None:
            return None
        parts.extend((f"is a {subtype}", Layer.TYPE, add_subtype(subtype)) for subtype in subtypes)
    return parts


def _parse_return_with_rider_clause(effect_text: str) -> AbilityEffect | None:
    """`_RETURN_WITH_RIDER_RE`'s shape. The return happens only while the card
    is still in the graveyard it went to (CR 608.2's ordinary "the object is
    gone"); the rider's effects are indefinite (CR 611.2a: no duration
    stated) and follow only the object the return made (CR 400.7)."""
    match = _RETURN_WITH_RIDER_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    parts = _return_rider_modifications(match.group("rider"))
    if not parts:
        return None
    tapped = match.group("tapped") is not None
    under_owner = not match.group("control").lower().startswith("your")
    counter_kind = _counter_kind(match.group("kind")) if match.group("kind") else None
    counter_amount = parse_count(match.group("amount")) if match.group("amount") else None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        referent_id = (
            event.subject_id
            if event is not None and event.subject_id is not None
            else ability.source_id
        )
        card = game.find_by_id(referent_id) if referent_id is not None else None
        if card is None or card.zone is not Zone.GRAVEYARD:
            return
        controller = (card.owner or ability.controller) if under_owner else ability.controller
        returned = game.put_onto_battlefield(card, controller, tapped=tapped)
        if returned.zone is not Zone.BATTLEFIELD:
            return
        if counter_kind is not None and counter_amount:
            game.add_counters(returned, counter_kind, counter_amount)
        store = continuous_effects(game)
        timestamp = store.tick()
        for what, layer, modification in parts:
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {returned.name} {what}",
                    layer=layer,
                    timestamp=timestamp,
                    selector=only_this_incarnation(returned, returned.zone_change_stamp),
                    modification=modification,
                ),
                game,
            )

    return effect


#: "Return this card from your graveyard to the battlefield with a finality
#: counter on him. Then you may attach an Equipment you control to him."
#: (Winter Soldier, Icy Assassin) - the graveyard return the plain sentence
#: already reads (CR 122.1h's finality counter; Balustrade Wurm's "... on
#: it."), then CR 608.2d's optional choice of an Equipment its controller
#: controls, attached (CR 701.3a) to the card as the permanent it became.
_RETURN_SELF_THEN_MAY_ATTACH_EQUIPMENT_RE = re.compile(
    r"^(?P<returning>return this card from your graveyard to the battlefield[^.]*)\. "
    r"then you may attach an equipment you control to (?:it|him|her)\.?$",
    re.IGNORECASE,
)


def _parse_return_self_then_may_attach_equipment(text: str) -> AbilityEffect | None:
    """`_RETURN_SELF_THEN_MAY_ATTACH_EQUIPMENT_RE`'s shape, or `None`."""
    match = _RETURN_SELF_THEN_MAY_ATTACH_EQUIPMENT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    returning_text = re.sub(
        r"\bon (?:him|her)\b", "on it", match.group("returning"), flags=re.IGNORECASE
    )
    returning = parse_mixed_effect(f"{returning_text}.")
    if returning is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        returning(game, ability)
        returned = ability.source(game)
        if returned is not None and returned.zone is Zone.BATTLEFIELD:
            _may_attach_equipment_to(game, returned, ability)

    return effect


# --------------------------------------------------------------------------
# "Choose <target cards in graveyards>. [<payment>.] Put them onto the
# battlefield under your control."
# --------------------------------------------------------------------------
#
# Command the Dreadhorde: "Choose any number of target creature and/or
# planeswalker cards in graveyards. Command the Dreadhorde deals damage to
# you equal to the total mana value of those cards. Put them onto the
# battlefield under your control." Grim Return: "Choose target creature card
# in a graveyard that was put there from the battlefield this turn. Put that
# card onto the battlefield under your control." The opener only names the
# targets (CR 115.1a; the "put there from the battlefield this turn"
# restriction is `TargetRequirement.put_there_from_battlefield_this_turn`'s);
# "those cards" / "them" / "that card" are the ones still legal as the spell
# resolves (CR 608.2b - one that left its graveyard is neither paid for nor
# returned). The optional payment is the spell dealing damage to its
# controller equal to the total mana value of the chosen cards (CR 202.3).
_CHOSEN_GRAVEYARD_CARDS_ONTO_BATTLEFIELD_RE = re.compile(
    r"^choose (?P<phrase>[^.]*\btarget\b[^.]*\bcards? in (?:a )?graveyards?"
    r"(?: that (?:was|were) put there from the battlefield this turn)?)\.\s+"
    r"(?:(?P<payment>[^.]+? deals damage to you) equal to "
    r"the total mana value of those cards\.\s+)?"
    r"put (?:them|that card) onto the battlefield under your control\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s21")
def _parse_return_chosen_graveyard_cards_spell_text(text: str) -> Effect | None:
    """`_CHOSEN_GRAVEYARD_CARDS_ONTO_BATTLEFIELD_RE`'s shape; see the banner."""
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _CHOSEN_GRAVEYARD_CARDS_ONTO_BATTLEFIELD_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    pays_damage = match.group("payment") is not None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        chosen = [card for card in game.resolve_card_targets(spell) if card.zone is Zone.GRAVEYARD]
        if not chosen:
            return
        if pays_damage:
            total = int(sum(card.mana_value for card in chosen))
            if total > 0:
                game.deal_damage(controller, total, source=spell)
        for card in chosen:
            if card.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(card, controller.username)

    return effect


from ._common import (  # noqa: E402
    _EXILE_TARGET_RE,
    _NON_SUBTYPE_PREFIX_RE,
    _TRAILING_DURATION_RE,
    _UNENFORCED_CONDITIONAL_RE,
    ConditionalClauseNotice,
    _effect_condition_is_readable,
    _parse_card_group_qualifier,
    _parse_delayed_timing_clause,
    _parse_mass_type_qualifier,
    _permanent_id_and_name,
    _quality_matcher,
    _targets_understood,
    computed_permanents,
)
from .continuous import (  # noqa: E402
    _defender_of_controllers_attack,
    _for_each_opponent_target_phrase,
    _may_attach_equipment_to,
    attach_permanent,
    continuous_effects,
)
from .counters import _counter_kind  # noqa: E402
from .damage import _clause_slots  # noqa: E402
from .dispatch import parse_mixed_effect  # noqa: E402
from .library import _dead_self_found, _reveal_and_bring_into_hand  # noqa: E402
from .text import _singular_card_type, _strip_non_effect_preamble  # noqa: E402
from .tokens import _parse_token_clause  # noqa: E402


@MIXED_CLAUSE.rung("s1", for_spell=FORWARD)
def _parse_return_put_from_hand_or_graveyard_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "you may put a <quality> card from your hand or graveyard onto the
    battlefield" - `machines/if_you_do_chains.parse_put_from_hand_or_graveyard`."""
    if "hand or graveyard onto the battlefield" not in clause.lower():
        return None
    from ..if_you_do_chains import parse_put_from_hand_or_graveyard

    return parse_put_from_hand_or_graveyard(clause)
