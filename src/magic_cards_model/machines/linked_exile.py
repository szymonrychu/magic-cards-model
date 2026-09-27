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
from typing import TYPE_CHECKING

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
    match = _RETURN_LINKED_CREATURE_RE.fullmatch(" ".join(clause.strip().split()))
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
    if _RETURN_OTHER_LINKED_CARDS_TO_HAND_RE.fullmatch(" ".join(clause.strip().split())) is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        remaining = [card for card in _linked_cards(game, ability) if card.zone is Zone.EXILE]
        if not remaining:
            return
        with game.returning_together():  # CR 603.2c: one event, several cards
            for card in remaining:
                game.return_to_hand(card)

    return effect
