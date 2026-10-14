"""CR 607.2a's linked pair, read off the *return* half: "Return a creature
card exiled with this land to the battlefield under your control. Return
each other card exiled with this land to its owner's hand." (Northampton
Farm).

The exile half of the pair needs no code here at all. `{1}, {T}: Exile
target creature you own.` already reads as an ordinary targeted exile
through `machines/effects.py`'s own dispatch, and `models/game.py`'s
`link_cards_exiled_during` (`machines/effects.link_cards_exiled_during`,
called from `Game._resolve_ability` after *every* ability resolves) already
marks whatever that ability exiled with `ExileMarker.LINKED` the moment it
notices the same printed object also carries an ability that reads "the
exiled cards" or "exiled with [this object]" (`_LINKED_EXILE_READER_RE`,
`machines/effects._source_reads_its_exiled_cards`) - which this land's own
second ability's printed text does, verbatim. So by the time either sentence
below ever resolves, every card the first ability sent to exile is already
sitting there linked to this land's id and `zone_change_stamp`
(`AbilityOnStack.source_stamp`, captured before the "Sacrifice this land"
cost could move it - CR 400.7), exactly the way Skyclave Apparition's own
enters-the-battlefield exile is already linked by the time its
leaves-the-battlefield half reads it back
(`machines/effects._EXILED_CARD_OWNER_CREATES_X_TOKEN_RE`).

What is new here is the *return* shape: nothing in the pool before this had
one ability return **one specific characteristic** of what a sibling ability
exiled (only "a creature card") while a **second** ability swept up
everything else left over. `Game.cards_exiled_with` (CR 607.2a/607.3) already
answers "what is exiled with this object", so both sentences below are read
off it directly - the first filtering to creature cards and taking one, the
second reading whatever is left once the first has already moved its own
pick out of exile. Two clauses in *printed* order, run in that order
(CR 608.2c): the second's "each other" needs the first's move to have already
happened so what remains truly is "other".

Read generically off the shape, not the card: `<permanent-type>` is any of
CR 205.2a's card types (a land here; a future artifact, creature, or
enchantment naming itself the identical way reads the same code path).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game
    from .effects import AbilityEffect
    from .triggers import AbilityOnStack

#: CR 205.2a's card types, as the self-referential "this `<type>`" pronoun
#: this shape's printed pair both use to name their own source - never a
#: subtype, since every printing in the pool naming itself this way (a land)
#: does so by card type. Widened per new printing rather than pinned to
#: "land" alone, the same "target the mechanic" reasoning
#: `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE` already documents for its own
#: type alternation in `machines/effects.py`.
_LINKED_EXILE_PERMANENT_TYPE = (
    r"(?:permanent|land|artifact|creature|planeswalker|enchantment|battle)"
)

#: "Return [a|each] creature card exiled with this `<type>` to the
#: battlefield[ tapped] under (your|its owner's) control[ tapped]." - the
#: "which characteristic" half of the pair. "a" (CR 108.2, singular - exactly
#: one) is Northampton Farm's own quantifier; Endless Sands (Modern-legal
#: proof printing, no second "sweep up the rest" sentence at all) prints
#: "each" instead, returning every creature card the land's exile pile holds
#: rather than only the first - the identical CR 607.2a/607.3 read, plural.
#: `tapped` is read on either side of the control clause so a future printing
#: naming either word order still matches, the same reasoning
#: `_RETURN_TO_BATTLEFIELD_RE` already gives its own optional groups in
#: `machines/effects.py`.
_RETURN_LINKED_CREATURE_RE = re.compile(
    rf"^return (?P<quantifier>a|each) creature card"
    rf"s?"
    rf" exiled with this {_LINKED_EXILE_PERMANENT_TYPE} to the "
    r"battlefield(?P<tapped1> tapped)? under (?P<control>your|its owner'?s) control"
    r"(?P<tapped2> tapped)?\.?$",
    re.IGNORECASE,
)

#: "Return each other card exiled with this `<type>` to its owner's hand." -
#: the sweep-up half.
_RETURN_OTHER_LINKED_CARDS_TO_HAND_RE = re.compile(
    rf"^return each other card exiled with this {_LINKED_EXILE_PERMANENT_TYPE} to its "
    r"owner'?s hand\.?$",
    re.IGNORECASE,
)


def _linked_cards(game: Game, ability: AbilityOnStack) -> list[CardState]:
    """Every card still exiled with `ability`'s own source incarnation
    (CR 607.2a/607.3), in `Game.exile`'s own order.

    `ability.source_stamp` is the source's `zone_change_stamp` as of
    activation, captured before "Sacrifice this land" (or any other cost)
    could move it - CR 400.7's own incarnation guard, so a card an *earlier*
    printing of this land exiled (impossible for a land that has never left
    the battlefield before, but not for a permanent that has) is not read
    back as this activation's own pile.
    """
    if ability.source_id is None:
        return []
    return game.cards_exiled_with(ability.source_id, ability.source_stamp)


def parse_return_linked_creature_clause(clause: str) -> AbilityEffect | None:
    """`_RETURN_LINKED_CREATURE_RE`'s shape, or `None`.

    "A creature card" (CR 108.2, singular, no target) means exactly one -
    the first creature card this land's own exile pile holds, in the shared
    exile zone's insertion order (`Game.cards_exiled_with`'s own docstring:
    nothing in the pool needs a different order). Endless Sands' own "each
    creature card" instead returns every one the pile holds. Nothing to
    return is simply nothing to return (CR 608.2c never runs half an
    instruction, but there is no second half here to skip).
    """
    match = _RETURN_LINKED_CREATURE_RE.fullmatch(collapsed(clause.strip()))
    if match is None:
        return None
    tapped = match.group("tapped1") is not None or match.group("tapped2") is not None
    owners_control = match.group("control").lower() != "your"
    every_one = match.group("quantifier").lower() == "each"

    def effect(game: Game, ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        creature_cards = [
            card
            for card in _linked_cards(game, ability)
            if card.zone is Zone.EXILE and Type.CREATURE in card.types
        ]
        if not creature_cards:
            return
        chosen = creature_cards if every_one else creature_cards[:1]
        with game.entering_together():  # CR 603.6a: one arrival, together
            for card in chosen:
                new_controller = (
                    (card.owner or controller.username) if owners_control else controller.username
                )
                game.put_onto_battlefield(card, new_controller, tapped=tapped)

    return effect


def parse_return_other_linked_cards_to_hand_clause(clause: str) -> AbilityEffect | None:
    """`_RETURN_OTHER_LINKED_CARDS_TO_HAND_RE`'s shape, or `None`.

    "Each other card" is read at *this* clause's own resolution time
    (CR 608.2c: the two sentences run in the order printed), so whichever
    card the first sentence already moved off exile (or a token this same
    move refused to bring back, `is_token`/CR 111.7's own "ceases to exist"
    having already taken it out of the exile zone by then) is not "other"
    at all any more - it is simply gone from `Game.cards_exiled_with`'s own
    live scan, with no extra bookkeeping needed to exclude it by id.
    """
    if _RETURN_OTHER_LINKED_CARDS_TO_HAND_RE.fullmatch(collapsed(clause.strip())) is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        remaining = [card for card in _linked_cards(game, ability) if card.zone is Zone.EXILE]
        if not remaining:
            return
        with game.returning_together():  # CR 603.2c: one event, several cards
            for card in remaining:
                game.return_to_hand(card)

    return effect


#: "Return all cards exiled with `<self>` to their owner's hand and you lose
#: that much life." - Asmodeus the Archfiend's {B}. `<self>` is CR 201.5's
#: printed short name of the source (never validated against it: the pile is
#: the resolving ability's own, `_linked_cards`); "that much" is the number
#: of cards that actually reached a hand.
_RETURN_ALL_LINKED_TO_HAND_LOSE_LIFE_RE = re.compile(
    r"^return all cards exiled with (?:this \w+|[a-z][\w'-]*) to their owner'?s hand "
    r"and you lose that much life\.?$",
    re.IGNORECASE,
)


def parse_return_all_linked_to_hand_lose_life_clause(clause: str) -> AbilityEffect | None:
    """`_RETURN_ALL_LINKED_TO_HAND_LOSE_LIFE_RE`'s shape, or `None`."""
    if _RETURN_ALL_LINKED_TO_HAND_LOSE_LIFE_RE.fullmatch(collapsed(clause.strip())) is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        pile = [card for card in _linked_cards(game, ability) if card.zone is Zone.EXILE]
        with game.returning_together():  # CR 603.2c: one event, several cards
            for card in pile:
                game.return_to_hand(card)
        returned = sum(1 for card in pile if card.zone is Zone.HAND)
        if returned:
            game.lose_life(ability.controller, returned)

    return effect


# --------------------------------------------------------------------------
# R0a-T5: "exile all <group> until this <type> leaves the battlefield"
# (CR 610.3) and "Put each card exiled with this <type> into its owner's
# graveyard, then create <token> for each card put into a graveyard this way.
# Sacrifice this <type>." (CR 607.1)
# --------------------------------------------------------------------------

_GROUP_STAT_RE = re.compile(
    r"^(?P<base>.+?) with (?P<stat>mana value|power|toughness) (?P<n>\d+) or "
    r"(?P<cmp>less|greater)$",
    re.IGNORECASE,
)

#: "artifacts and creatures", "creatures", "artifacts your opponents
#: control" - one or two plural types joined by "and" (CR 608.2c reads "and"
#: here as the union of the two groups), with the damage grammar's own
#: controller qualifier.
_TWO_TYPES_RE = re.compile(r"^(?P<a>[a-z]+s) and (?P<b>[a-z]+s)(?P<rest>(?: .+)?)$", re.IGNORECASE)

_EXILE_ALL_UNTIL_LEAVES_RE = re.compile(
    rf"^exile all (?P<group>.+?) until this (?P<type>{_LINKED_EXILE_PERMANENT_TYPE}) leaves "
    r"the battlefield\.?$",
    re.IGNORECASE,
)


def _group_predicate(group: str) -> Callable[[Game, CardState, str], bool] | None:
    """The mass group as a predicate on the computed board (CR 613.5), read at
    resolution (CR 611.2c's "determined when that effect begins")."""
    from .effects import _parse_damage_group_phrase

    text = group.strip()
    stat = _GROUP_STAT_RE.fullmatch(text)
    base_text = stat.group("base") if stat else text
    two = _TWO_TYPES_RE.fullmatch(base_text)
    if two is not None:
        rest = two.group("rest")
        first = _parse_damage_group_phrase(f"{two.group('a')}{rest}")
        second = _parse_damage_group_phrase(f"{two.group('b')}{rest}")
        if first is None or second is None:
            return None

        def base(game: Game, permanent: CardState, controller: str) -> bool:
            return first(game, permanent, controller) or second(game, permanent, controller)

    else:
        single = _parse_damage_group_phrase(base_text)
        if single is None:
            return None
        base = single
    if stat is None:
        return base
    which = stat.group("stat").lower()
    bound = int(stat.group("n"))
    at_least = stat.group("cmp").lower() == "greater"

    def predicate(game: Game, permanent: CardState, controller: str) -> bool:
        if not base(game, permanent, controller):
            return False
        computed = game.characteristics_of(permanent)
        if which == "mana value":
            value = permanent.mana_value
        elif which == "power":
            value = computed.numeric_power
        else:
            value = computed.numeric_toughness
        return value >= bound if at_least else value <= bound

    return predicate


def parse_exile_all_until_leaves_clause(clause: str) -> AbilityEffect | None:
    """`_EXILE_ALL_UNTIL_LEAVES_RE`'s effect: every permanent in the group is
    exiled, linked to the source (CR 607.1, so "cards exiled with this
    artifact" finds them), and watched for the source leaving (CR 610.3) -
    returning each under its owner's control (CR 610.3c). CR 610.3b: if the
    source already left before this resolves, nothing is exiled."""
    match = _EXILE_ALL_UNTIL_LEAVES_RE.fullmatch(collapsed(clause))
    if match is None:
        return None
    predicate = _group_predicate(match.group("group"))
    if predicate is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return  # CR 610.3b
        controller = ability.controller
        chosen = [
            permanent
            for permanent in list(game.battlefield)
            if permanent is not source and predicate(game, permanent, controller)
        ]
        exile_linked_until_leaves(game, source, chosen, controller)

    return effect


def exile_linked_until_leaves(
    game: Game, source: CardState, chosen: list[CardState], controller: str
) -> list[CardState]:
    """Exile `chosen` permanents linked to `source` (CR 607.1, so "cards exiled
    with this creature" finds them) and watch for `source` leaving (CR 610.3),
    returning each under its owner's control (CR 610.3c). Returns what really
    went to exile; a token does not (CR 111.8)."""
    from ..models.card_state import ExileAnnotation, ExileMarker
    from .effects import _watch_for_departure_and_return_exiled_card

    exiled_cards: list[CardState] = []
    for permanent in chosen:
        exiled = game.exile_permanent(permanent)
        if exiled.zone is not Zone.EXILE:
            continue  # CR 111.8: a token does not come back
        exiled.exile_annotation = ExileAnnotation(
            marker=ExileMarker.LINKED,
            owner=exiled.owner,
            turn_exiled=game.turn.turns_taken if game.turn is not None else None,
            linked_permanent_id=source.id,
            linked_permanent_stamp=source.zone_change_stamp,
        )
        _watch_for_departure_and_return_exiled_card(game, source, exiled, controller)
        exiled_cards.append(exiled)
    return exiled_cards


_PUT_LINKED_INTO_GRAVEYARD_THEN_TOKENS_RE = re.compile(
    rf"^put each card exiled with this (?P<type>{_LINKED_EXILE_PERMANENT_TYPE}) into its "
    r"owner'?s graveyard, then create an? (?P<desc>.+?) tokens? for each card put into a "
    r"graveyard this way\.(?: sacrifice this (?P<sac>"
    rf"{_LINKED_EXILE_PERMANENT_TYPE})\.)?$",
    re.IGNORECASE,
)


def parse_put_linked_into_graveyard_then_tokens_clause(clause: str) -> AbilityEffect | None:
    """`_PUT_LINKED_INTO_GRAVEYARD_THEN_TOKENS_RE`'s effect (CR 607.1's linked
    pile, CR 701.7a's tokens counted off what actually reached a graveyard -
    a replacement that exiled a card instead does not count - then the
    source is sacrificed, CR 701.21a)."""
    match = _PUT_LINKED_INTO_GRAVEYARD_THEN_TOKENS_RE.fullmatch(collapsed(clause))
    if match is None:
        return None

    from .effects import _parse_generic_token_descriptor

    definition = _parse_generic_token_descriptor(match.group("desc").split(), None)
    if definition is None:
        return None
    sacrifices = match.group("sac") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from ..models.token import create_tokens

        put = 0
        for card in _linked_cards(game, ability):
            landed = game.put_into_graveyard(card)
            if landed.zone is Zone.GRAVEYARD:
                put += 1
        if put:
            create_tokens(game, definition, ability.controller, put)
        if sacrifices:
            source = ability.source(game)
            if source is not None and source.zone is Zone.BATTLEFIELD:
                game.sacrifice(source)

    return effect


def put_linked_cards_into_graveyards(game: Game, ability: AbilityOnStack) -> int:
    """Put every card exiled with `ability`'s source (CR 607.1's linked pile,
    that incarnation of it - CR 400.7) into its owner's graveyard, and say how
    many got there: a replacement that sent one elsewhere does not count
    (Valakut Exploration's "put them into their owner's graveyard, then ...
    that much damage")."""
    put = 0
    for card in _linked_cards(game, ability):
        landed = game.put_into_graveyard(card)
        if landed.zone is Zone.GRAVEYARD:
            put += 1
    return put


#: "The exiled card's owner manifests dread." (Unidentified Hovership's
#: leaves-the-battlefield trigger, CR 603.6c). "The exiled card" is the pile
#: the same object's enters trigger exiled - linked by
#: `effects.link_cards_exiled_during` (CR 607.1, CR 607.2a) - and each player
#: who owns one or more of those cards manifests dread once (CR 701.62a;
#: CR 607.3's plural read). No card in the pile - "up to one" chose none, or
#: the enters trigger has not resolved yet - is nobody manifesting. The
#: exiled cards themselves stay where they are.
_EXILED_CARD_OWNER_MANIFESTS_DREAD_RE = re.compile(
    r"^the exiled (?:card's|cards') owners? (?:each )?manifests? dread\.?$", re.IGNORECASE
)


def parse_exiled_card_owner_manifests_dread_clause(text: str) -> AbilityEffect | None:
    """`_EXILED_CARD_OWNER_MANIFESTS_DREAD_RE`'s effect, or `None`."""
    match = _EXILED_CARD_OWNER_MANIFESTS_DREAD_RE.fullmatch(collapsed(text))
    if match is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from .decisions import source_id_of
        from .effects import manifest_dread

        if ability.source_id is None:
            return
        owners: list[str] = []
        for exiled in game.cards_imprinted_on(ability.source_id):
            owner = exiled.owner
            if owner is not None and owner not in owners:
                owners.append(owner)
        # CR 101.4: several owners act in APNAP order, active player first.
        seats = [player.username for player in game.players]
        active = seats.index(game.turn.active_player) if game.turn.active_player in seats else 0
        turn_order = seats[active:] + seats[:active]
        for owner in sorted(
            owners,
            key=lambda name: turn_order.index(name) if name in turn_order else len(turn_order),
        ):
            manifest_dread(game, owner, ability.source_name, source_id=source_id_of(ability))

    return effect
