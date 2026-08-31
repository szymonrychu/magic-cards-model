"""Casting a spell, as a state machine (CR 601.2).

The rules cast a spell in a fixed order, and the whole thing is one action: if
any part of it cannot be completed legally, the game rewinds to before it began
(CR 601.6, 733.1).

    PROPOSED -> MODES -> TARGETS -> COST_DETERMINED -> PAYING -> CAST
         \\____________________________________________________/
                            cancel, rewinding everything

MODES is where the choices that change what the spell costs are made: the mode,
whether an alternative cost is being paid, and whether any optional additional
cost is being paid (CR 601.2b). TARGETS is CR 601.2c, and legality is checked
there rather than left to resolution.

Paying is delegated to `CostPayment`, so the mana side of casting is one
machine and the announcement side is another.
"""

from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models.card import Card, Layout, Type
from ..models.card_state import CardState, Counter, ExileAnnotation, ExileMarker, TargetRef
from ..models.mana import ManaCost, ManaSpend
from ..models.zone import Zone
from .abilities import KeywordAbility, TriggerEvent, keyword_abilities
from .casting_restrictions import (
    has_sorcery_speed_flash_grant,
    restricted_from_noncreature_casting,
    sorcery_speed_restriction_source,
)
from .cost import (
    CostPayment,
    CostStep,
    TotalCost,
    alternative_cost_offers,
    apply_modifications,
    total_cost_for_phrase,
)
from .keywords import (
    FACE_DOWN_CAST_COST,
    enchant_restrictions,
    face_down_characteristics,
    why_cannot_enchant,
)
from .layers import ContinuousEffect, Layer, grant_ability, only_this_incarnation
from .modes import ModalProfile, Mode, modal_profile, substitute_x
from .targeting import (
    TargetingProfile,
    profile_for_modes,
    profile_for_modes_with_owners,
    profile_for_text,
    targeting_profile,
)
from .triggers import GameEvent
from .turn import Step


class CastTiming(StrEnum):
    """When a keyword lets a card be cast.

    `ANY` means the card's own timing rules apply and this keyword adds nothing.
    `SORCERY` is the sentence plot prints, "Plot only as a sorcery": the
    caster's own main phase, with the stack empty (CR 702.170a, CR 117.1c).
    """

    ANY = "any"
    SORCERY = "sorcery"


class KeywordCastOption(BaseModel):
    """One way a keyword lets a card be cast (CR 601.3).

    "A player can begin to cast a spell only if a rule or effect allows that
    player to cast it and no rule or effect prohibits that player from casting
    it." Every keyword here is such an effect: it names a zone the card may be
    cast from and what has to be paid instead of the printed mana cost.

    The three pieces are deliberately separate, because the rules keep them
    separate:

    - **the zone**, which is what makes flashback (CR 702.34a) more than a
      discount - it is permission to cast from the graveyard at all;
    - **the cost**, which is an alternative cost under CR 118.9 when the keyword
      names one, and *nothing at all* when the keyword says "without paying its
      mana cost" - CR 107.3b treats those as two different things, so
      `pays_mana_cost` and `cost` are both recorded;
    - **the marker**, for the keywords that only work on a card sitting in a
      particular pile of exile (CR 406.4).
    """

    keyword: str
    """The canonical keyword, as Scryfall spells it."""
    rule: str
    """The CR number this option is read from, for the error message."""
    zone: Zone
    """Where the card has to be for this option to apply."""
    cost: TotalCost | None = None
    """What is paid instead of the mana cost. None with `pays_mana_cost` false
    means nothing at all is paid."""
    pays_mana_cost: bool = True
    """False when the keyword replaces the printed mana cost (CR 118.9)."""
    timing: CastTiming = CastTiming.ANY
    marker: ExileMarker | None = None
    """The exile pile the card must be in (CR 406.4)."""
    later_turn: bool = False
    """True when the card may only be cast on a turn after the one it was
    exiled on - plot (CR 702.170d), foretell, and warp all say so."""
    understood: bool = True
    """False when the keyword's printed cost could not be read into something
    payable. The option is still reported, so a sweep can see the gap."""

    def why_not(self, spell: CardState, caster: str, game: Any = None) -> str | None:
        """Why this option cannot be used right now, or None if it can.

        CR 601.3 is the rule: permission first, everything else after.
        """
        if not self.understood:
            return f"{spell.name}'s {self.keyword} cost could not be read, so it cannot be paid"
        if spell.zone is not self.zone:
            return (
                f"{self.keyword} casts {spell.name} from the {self.zone.value}, "
                f"but it is in the {spell.zone.value} ({self.rule})"
            )

        if self.marker is not None:
            annotation = spell.exile_annotation
            if annotation is None or annotation.marker is not self.marker:
                return (
                    f"{spell.name} is not {self.marker.value} in exile, so it cannot be "
                    f"cast with {self.keyword} ({self.rule})"
                )
            if annotation.owner is not None and annotation.owner != caster:
                return f"{spell.name} was {self.marker.value} by {annotation.owner}, not {caster}"
            now = _turn_number(game)
            if (
                self.later_turn
                and now is not None
                and annotation.turn_exiled is not None
                and now <= annotation.turn_exiled
            ):
                return (
                    f"{spell.name} became {self.marker.value} this turn; it can only be "
                    f"cast on a later turn ({self.rule})"
                )

        if (
            self.timing is CastTiming.SORCERY
            and game is not None
            and not game.can_cast_sorcery(caster)
        ):
            return (
                f"{self.keyword} can only be used as a sorcery: {caster}'s main phase, "
                f"with the stack empty ({self.rule})"
            )
        return None


def _turn_number(game: Any) -> int | None:
    turn = getattr(game, "turn", None)
    return None if turn is None else int(turn.turn_number)


def _option_from_keyword(ability: KeywordAbility) -> KeywordCastOption | None:
    """Build the cast option one keyword ability hands out, or None if it hands out none.

    Every rule quoted here was looked up this session; the keywords that let a
    card be cast are not interchangeable and are not guessable.
    """
    canonical = ability.canonical.lower()
    printed = ability.cost

    if canonical == "evoke":
        # CR 702.74a: evoke is a static ability that functions in any zone from
        # which the card can be cast, plus a triggered ability on the
        # battlefield. The static half is an alternative cost paid instead of
        # the mana cost, cast from hand like any other creature spell.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.74a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical == "flashback":
        # CR 702.34a: two static abilities, one functioning in the graveyard.
        # The graveyard half is what makes this permission and not a discount.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.34a",
            zone=Zone.GRAVEYARD,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical == "plot":
        # CR 702.170d: "A plotted card's owner may cast it from exile without
        # paying its mana cost during their main phase while the stack is empty
        # during any turn after the turn in which it became plotted." Nothing
        # is paid, which is not the same as an alternative cost (CR 107.3b).
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.170d",
            zone=Zone.EXILE,
            cost=None,
            pays_mana_cost=False,
            timing=CastTiming.SORCERY,
            marker=ExileMarker.PLOTTED,
            later_turn=True,
        )

    if canonical == "foretell":
        # CR 702.143a: the foretell *cost* is what a foretold card is cast for,
        # and the {2} paid to exile it is a separate special action (CR 116.2h).
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.143a",
            zone=Zone.EXILE,
            cost=cost,
            pays_mana_cost=False,
            marker=ExileMarker.FORETOLD,
            later_turn=True,
            understood=cost is not None,
        )

    if canonical == "madness":
        # CR 702.35a's *second* ability: "When this card is exiled this way, its
        # owner may cast it by paying [cost] rather than paying its mana cost."
        # The card is in its own pile of exile (CR 406.4) because the *first*
        # ability put it there, replacing the discard. CR 702.35b: "Casting a
        # spell using its madness ability follows the rules for paying
        # alternative costs in rules 601.2b and 601.2f-h."
        #
        # No `later_turn`: unlike plot, foretell and warp, madness is cast off
        # the triggered ability that just resolved, so it is cast on the same
        # turn or not at all.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.35a",
            zone=Zone.EXILE,
            cost=cost,
            pays_mana_cost=False,
            marker=ExileMarker.MADNESS,
            understood=cost is not None,
        )

    if canonical == "dash":
        # CR 702.109a: "Dash [cost]" means "You may cast this card by paying
        # [cost] rather than its mana cost", plus a delayed trigger that returns
        # the permanent at the beginning of the next end step and a static
        # ability granting haste while the dash cost was paid. This is the first
        # of the three; the other two are in `docs/engine-coverage.md`.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.109a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical in ("morph", "megamorph", "disguise"):
        # CR 702.37a: "'Morph [cost]' means "You may cast this card as a 2/2
        # face-down creature with no text, no name, no subtypes, and no mana
        # cost **by paying {3}** rather than paying its mana cost."" The printed
        # cost is *not* what casting it face down costs - it is what CR 702.37e's
        # special action pays to turn the permanent face up later. Charging the
        # printed cost here would be the obvious and wrong reading.
        #
        # CR 702.37a also makes morph "a static ability that functions in any
        # zone from which you could play the card it's on", which for every
        # printing in this pool is the hand.
        rule = "CR 702.168a" if canonical == "disguise" else "CR 702.37a"
        return KeywordCastOption(
            keyword=ability.canonical,
            rule=rule,
            zone=Zone.HAND,
            cost=TotalCost.of(ManaCost.parse(FACE_DOWN_CAST_COST)),
            pays_mana_cost=False,
        )

    if canonical == "warp":
        # CR 702.185a: warp is two static abilities that function while the card
        # is on the stack, one of which may create a delayed triggered ability.
        # The first is the alternative cost from hand; the delayed trigger is
        # what exiles the permanent and makes it a warped card (CR 702.185b).
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.185a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    return None


#: The second option warp hands out: a warped card in exile may be cast later,
#: for its own mana cost (CR 702.185b).
def _warp_from_exile(ability: KeywordAbility) -> KeywordCastOption:
    return KeywordCastOption(
        keyword=ability.canonical,
        rule="CR 702.185b",
        zone=Zone.EXILE,
        cost=None,
        pays_mana_cost=True,
        marker=ExileMarker.WARPED,
        later_turn=True,
    )


def keyword_cast_options(card: Card) -> list[KeywordCastOption]:
    """Every way this card's own text lets it be cast, in printed order (CR 601.3).

    Mostly that is keywords, but CR 715.3d hands out the same kind of permission
    to an adventurer card without a keyword to its name, so it is here too.

    A card with none of them returns an empty list, which is the ordinary case:
    it is cast from hand for its mana cost and needs no permission.
    """
    options: list[KeywordCastOption] = []
    for ability in keyword_abilities(card):
        option = _option_from_keyword(ability)
        if option is None:
            continue
        options.append(option)
        if option.keyword.lower() == "warp":
            options.append(_warp_from_exile(ability))

    if adventure_face(card) is not None:
        # CR 715.3d: "Instead of putting a spell that was cast as an Adventure
        # into its owner's graveyard as it resolves, its controller exiles it.
        # For as long as that card remains exiled, that player may play it."
        # Played normally, so its own mana cost and its own timing rules apply.
        options.append(
            KeywordCastOption(
                keyword="Adventure",
                rule="CR 715.3d",
                zone=Zone.EXILE,
                pays_mana_cost=True,
                marker=ExileMarker.ADVENTURED,
            )
        )
    return options


def castable_from(card: Card, zone: Zone) -> list[KeywordCastOption]:
    """The keyword options that cast this card out of one zone."""
    return [option for option in keyword_cast_options(card) if option.zone is zone]


# --------------------------------------------------------------------------
# A permission handed out by a resolving effect (CR 601.3, CR 701.18b)
# --------------------------------------------------------------------------


class PlayAction(StrEnum):
    """What an effect's permission actually allows.

    CR 601.1a: "Some effects still refer to 'playing' a card. 'Playing a card'
    means playing that card as a land or casting that card as a spell,
    whichever is appropriate." CR 701.18b says the same thing as a keyword
    action, and CR 701.5b: "To cast a card is to cast it as a spell."

    So the two are **not** interchangeable, which is why they are two values
    rather than one flag: `PLAY` covers CR 701.18a's land drop as well as a
    cast, and `CAST` covers only the cast. Ugin, Eye of the Storms' −11 and
    Ragavan, Nimble Pilferer's combat-damage trigger both print *cast*;
    CR 715.3d's Adventure and CR 702.170's plot-adjacent wordings print
    *play*, and a land found under one of those consumes the land drop
    (CR 305.2a) while a card cast under the other never can.
    """

    CAST = "cast"
    PLAY = "play"


class PlayPermission(BaseModel):
    """CR 601.3's "a rule or effect allows that player to [play] it", handed
    out by a resolving effect to **one specific card**, for a bounded time.

    "A player can begin to cast a spell only if a rule or effect allows that
    player to cast it and no rule or effect prohibits that player from casting
    it." `KeywordCastOption` above is the *static* half of that rule - a grant
    read off a card's own printed keyword, true of every copy of that printing
    forever. This is the other half: a grant a resolving ability creates, that
    names particular objects and then stops.

    Four things the rules keep separate, kept separate here:

    - **which object**, by `card_id` *and* `zone_change_stamp`. CR 400.7: "an
      object that moves from one zone to another becomes a new object", so a
      card that leaves exile and comes back is not the card the permission was
      granted to, and the stamp is what says so. This is also why the
      permission is not a blanket "cards in exile are castable": it names
      instances, so an opponent's card exiled by something else is untouched.
    - **which player**, by `player`. Not the owner: Ragavan exiles the top card
      of the *damaged player's* library, and CR 108.3 leaves that card owned by
      that player while the Ragavan controller is the one permitted to cast it.
    - **cast or play**, by `action` - see `PlayAction`.
    - **what is paid**, by `pays_mana_cost`. False is CR 118.9's "without
      paying its mana cost", which CR 107.3b keeps distinct from an
      alternative cost of some other shape.

    Nothing here loosens timing. CR 117.1a still decides *when* the spell may
    be cast and CR 305.1 still decides when a land may be played, so a sorcery
    under this permission is still a sorcery.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    zone_change_stamp: UUID
    """CR 400.7's identity check: the value `CardState.zone_change_stamp` held
    when the permission was granted. A new stamp means a new object."""
    player: str
    """Who may play it - CR 108.3's owner is a different question."""
    zone: Zone = Zone.EXILE
    action: PlayAction = PlayAction.CAST
    pays_mana_cost: bool = True
    """False is CR 118.9's "without paying its mana cost"."""
    source_name: str = ""
    """The card whose ability handed this out, for the error message."""
    rule: str = "CR 601.3"
    until_end_of_turn: bool = True
    """CR 514.2: "all 'until end of turn' and 'this turn' effects end" in the
    cleanup step. `Game.cleanup_step` drops these there."""
    granted_turns_taken: int | None = None
    """`TurnMachine.turns_taken` when it was granted, so the permission can
    tell "this turn" from "a later turn" even in a game driven step by step
    without ever reaching a cleanup step. CR 500.7's extra turn is why this is
    `turns_taken` and not the turn number or the active seat."""
    expires_end_of_next_turn: bool = False
    """"Until the end of your next turn" (Wrenn's Resolve, Reckless Impulse) -
    a longer sibling of the plain `until_end_of_turn` above: the grant
    survives the granting turn's own cleanup, survives every turn in between
    that is not `player`'s, and only actually drops at the cleanup of the
    *next* turn `player` is active for. When this is set, `until_end_of_turn`
    is left `False` so `Game.cleanup_step`'s ordinary CR 514.2 sweep leaves
    the permission alone; `Game.begin_turn_for` and `Game.cleanup_step` drop
    it themselves, keyed off `owner_next_turn_started` below, rather than off
    a precomputed `turns_taken` target - CR 500.7's extra turns and
    multiplayer's uneven rotation both mean "two turns from now" is not a
    fixed number of turns, but "the next time it is `player`'s turn" is
    always answerable by watching whose turn is beginning.
    `PlayPermission.expired` never reports this kind expired on its own
    (list membership is what removes it); this is why `expired` below simply
    returns `False` for it rather than trying to recompute the same answer
    two ways."""
    owner_next_turn_started: bool = False
    """Set by `Game.begin_turn_for` the moment `player`'s own next turn
    begins (CR 500.7-safe: watches for `player` becoming active again, not a
    turn count) - `Game.cleanup_step` drops the permission once this is set
    and `player` is active again at a *later* cleanup step, i.e. that same
    turn's own cleanup. Meaningless unless `expires_end_of_next_turn` is."""
    immediate: bool = False
    """Whether this grant is CR 117.2e's "instructed by a resolving ability"
    shape rather than an explicit "until end of turn" duration printed on a
    card.

    CR 117.1's own preamble: "**Unless a spell or ability is instructing a
    player to take an action**, which player can take actions at any given
    time is determined by a system of priority." CR 117.2e: "Resolving spells
    and abilities may instruct players to make choices or take actions...
    Even if a player is doing so, no player has priority while a spell or
    ability is resolving." Suspend's third ability (CR 702.62a) is exactly
    that shape - "you may play it... If you don't, it remains exiled" is the
    ability's own resolution instructing the cast, not a standing grant that
    survives into the ordinary priority system afterward, unlike Ugin, Eye of
    the Storms' "−11" and Ragavan, Nimble Pilferer's trigger, which both print
    the words "**Until end of turn**" and so *do* hand out a permission good
    for the rest of the priority-driven turn (CR 514.2 is what ends those).
    An `immediate` grant is good only for the step it was granted in
    (`granted_step`) - once the game has moved on to another step, whatever
    priority the instructing ability's own resolution briefly stood in for
    has already passed, and CR 702.62a's own "if you don't, it remains
    exiled" has already taken effect."""
    granted_step: Step | None = None
    """The `TurnMachine.step` `immediate` is scoped to - meaningless unless
    `immediate` is set."""
    bottom_if_unused: bool = False
    """Whether `Game.cleanup_step` must sweep this card to the bottom of its
    owner's library, rather than just dropping the permission, if it is still
    sitting unclaimed in `zone` the moment this permission expires.

    Cascade (CR 702.85a) is the one grant this is true for, and the reason is
    textual, not a house rule: Ugin, Eye of the Storms' "−11" and Ragavan,
    Nimble Pilferer's trigger both print "**Until end of turn**, you may cast
    [it]" - an explicit standing permission whose own rule never says what
    happens to a card nobody got around to casting, so CR 514.2 dropping the
    permission and leaving the card wherever it sits is the whole of what
    those rules require. Suspend's own third ability (CR 702.62a) is the same
    shape again - no "until end of turn", and its own sentence names the
    resting state itself: "if you don't, it remains exiled." Cascade's single
    sentence is the one exception: "Put the exiled cards on the bottom in a
    random order" is not a fallback for a *declined* hit only, it is what CR
    702.85a's own resolution does with *every* card that "weren't cast" -
    the accepted-but-never-actually-cast case included. Nothing else in this
    engine can finish that cast synchronously inside `cascade`'s own
    resolution (a live seat's actual `Casting.use_permission()` call is a
    separate, later step - see `machines/keywords.cascade`), so this flag is
    what keeps CR 702.85a's own "exiled forever" outcome from becoming a
    legal resting state for cascade the way it legitimately is for Ugin,
    Ragavan, and Suspend."""

    def names(self, card: CardState) -> bool:
        """Whether this permission is about that exact object (CR 400.7)."""
        return card.id == self.card_id and card.zone_change_stamp == self.zone_change_stamp

    def expired(self, game: Any = None) -> bool:
        """CR 514.2: whether the turn it was granted on is over, or - for an
        `immediate` grant - whether CR 117.2e's own resolution-instructed
        window (scoped to `granted_step`) has already closed."""
        turn = getattr(game, "turn", None)
        if self.immediate and self.granted_step is not None:
            if turn is None:
                return False
            return turn.step is not self.granted_step
        if self.expires_end_of_next_turn:
            # Never expired by this lazy check - removal is entirely
            # `Game.begin_turn_for`/`Game.cleanup_step`'s job, per
            # `expires_end_of_next_turn`'s own docstring.
            return False
        if not self.until_end_of_turn or self.granted_turns_taken is None:
            return False
        if turn is None:
            return False
        return int(turn.turns_taken) != self.granted_turns_taken

    def why_not(
        self,
        card: CardState,
        player: str,
        game: Any = None,
        *,
        action: PlayAction = PlayAction.CAST,
    ) -> str | None:
        """Why this permission does not allow that player that action, or None.

        Mirrors `KeywordCastOption.why_not`: CR 601.3's permission first,
        everything else after. Timing is deliberately **not** asked here - a
        permission to play is not a permission to ignore CR 117.1a - and is
        left to `why_cannot_cast_now` and `Game.why_cannot_play_land`.
        """
        if not self.names(card):
            return f"{self.source_name}'s permission is not about this copy of {card.name}"
        if self.player != player:
            return (
                f"{self.source_name} let {self.player} {self.action.value} {card.name}, "
                f"not {player} ({self.rule})"
            )
        if card.zone is not self.zone:
            return (
                f"{self.source_name} let {self.player} {self.action.value} {card.name} from "
                f"the {self.zone.value}, but it is in the {card.zone.value} ({self.rule})"
            )
        if self.expired(game):
            if self.immediate:
                return (
                    f"{self.source_name}'s permission to {self.action.value} {card.name} was "
                    f"CR 117.2e's own resolution-instructed window, not a standing grant, and "
                    f"the game has since moved past the step it was granted in"
                )
            return (
                f"{self.source_name}'s permission to {self.action.value} {card.name} lasted "
                f"until end of turn and that turn is over (CR 514.2)"
            )
        if action is PlayAction.PLAY and self.action is PlayAction.CAST:
            # CR 701.5b's "cast it as a spell" is narrower than CR 701.18b's
            # "play that card as a land or cast that card as a spell": a
            # permission that says *cast* never reaches the land drop.
            return (
                f"{self.source_name} let {self.player} cast {card.name}, which is not "
                f"permission to play it as a land (CR 601.1a, CR 701.18b)"
            )
        return None


def play_permissions_on(game: Any, card: CardState) -> list[PlayPermission]:
    """Every permission recorded against that exact object (CR 400.7)."""
    if game is None:
        return []
    return [
        permission for permission in getattr(game, "play_permissions", []) if permission.names(card)
    ]


def usable_play_permission(
    game: Any,
    card: CardState,
    player: str,
    action: PlayAction = PlayAction.CAST,
) -> PlayPermission | None:
    """The first permission that lets `player` take `action` with `card`, or None."""
    for permission in play_permissions_on(game, card):
        if permission.why_not(card, player, game, action=action) is None:
            return permission
    return None


def why_cannot_cast_from(spell: CardState, caster: str, zone: Zone, game: Any = None) -> str | None:
    """CR 601.3: why this card cannot be cast from where it is, or None.

    A card in hand needs no permission - that is where the rules cast from by
    default (CR 302.1, 601.3). Anywhere else, some keyword has to allow it, or
    some effect has to have handed out a `PlayPermission`, and that grant's own
    conditions have to hold.
    """
    if zone is Zone.HAND:
        return None
    if usable_play_permission(game, spell, caster) is not None:
        return None
    options = castable_from(spell.card, zone)
    reasons = [option.why_not(spell, caster, game) for option in options]
    if any(reason is None for reason in reasons):
        return None
    granted = play_permissions_on(game, spell)
    if granted:
        # A permission was handed out for this object and does not apply - say
        # why it does not (expired, wrong player, cast-not-play) rather than
        # the generic "nothing allows this", which would be a lie.
        return granted[0].why_not(spell, caster, game)
    if not options:
        return f"nothing allows {caster} to cast {spell.name} from the {zone.value} (CR 601.3)"
    return next(reason for reason in reasons if reason is not None)


# --------------------------------------------------------------------------
# When a card may be cast (CR 117.1a, CR 702.8a)
# --------------------------------------------------------------------------

#: Keywords that change *when* a card may be cast rather than from where.
#: `scripts/sweep_pool.py` reads this to tell an executed timing keyword from an
#: ignored one.
TIMING_KEYWORDS = frozenset({"flash"})

#: Keywords that change whether a permanent may be *chosen* as a target
#: (CR 601.2c). `Casting.choose_targets` refuses the announcement for these.
TARGET_LEGALITY_KEYWORDS = frozenset({"hexproof"})

#: Keywords that are an optional additional cost on a spell being cast
#: (CR 118.8a). `Casting.pay_kicker` charges these.
ADDITIONAL_COST_KEYWORDS = frozenset({"kicker", "multikicker"})


def has_flash(card: Card) -> bool:
    """Whether this printing has flash (CR 702.8a).

    "Flash is a static ability that functions in any zone from which you could
    play the card it's on. 'Flash' means "You may play this card any time you
    could cast an instant.""

    Read off the printing's own Scryfall `keywords`, like every other keyword in
    this engine - nothing grants or removes it, because there are no layers for
    keywords.
    """
    return any(keyword.lower() == "flash" for keyword in card.keywords)


def why_cannot_cast_now(spell: CardState, caster: str, game: Any = None) -> str | None:
    """Why the timing rules refuse this cast right now, or None (CR 117.1a).

    CR 117.1a is the whole rule in two sentences: "A player may cast an instant
    spell any time they have priority. A player may cast a noninstant spell
    during their main phase any time they have priority and the stack is empty."
    The per-type rules say the same thing card type by card type - CR 304.1 for
    instants, CR 307.1 for sorceries, CR 302.1 for creatures, CR 301.1 for
    artifacts, CR 306.1 for planeswalkers, CR 310.1 for battles - and CR 505.6a
    restates that the main phase is the only phase the noninstants go in.

    Flash is the exception that makes the rule worth enforcing (CR 702.8a):
    with it, a creature is cast on the sorcery-speed rule's *other* side.

    Answered against the game because it is a question about the turn: without
    one there is nothing to ask, and the answer is None.

    **Teferi, Time Raveler's two halves, checked in the right order.** His
    static, "Each opponent can cast spells only any time they could cast a
    sorcery," removes *every* instant-speed exception - CR 304.1's instant
    permission and CR 702.8a's flash both - for an opponent, so it is read
    before either of them, but only once sorcery-speed timing has already
    failed: a restricted opponent whose own main phase it is, with an empty
    stack, needs no exception at all (CR 611.1 does not add a *second*
    restriction on top of ordinary permission). His +1, "Until your next
    turn, you may cast sorcery spells as though they had flash," is the
    opposite direction and touches only its own controller: a sorcery this
    caster could not otherwise cast at instant speed is let through the same
    way `has_flash` already lets an instant-speed creature through.

    **An `immediate` `PlayPermission` (CR 702.62a's suspend, the third
    ability) skips this whole rule rather than answering it.** CR 117.1's own
    preamble: "**Unless a spell or ability is instructing a player to take an
    action**, which player can take actions at any given time is determined
    by a system of priority." CR 117.2e: "Resolving spells and abilities may
    instruct players to make choices or take actions... Even if a player is
    doing so, no player has priority while a spell or ability is resolving."
    A card cast under a live `immediate` grant is being cast *as* the
    resolving ability's own instruction, not through the priority system
    CR 117.1a governs - which is why a suspended sorcery can be cast during
    an upkeep step that is never anyone's main phase. This does not apply to
    Ugin, Eye of the Storms' or Ragavan, Nimble Pilferer's grants: both print
    "**Until end of turn**, you may cast", an explicit standing permission
    used through the ordinary priority system afterward, where CR 117.1a
    still applies in full - see `PlayPermission.immediate`'s own docstring.
    """
    if game is None:
        return None
    permission = usable_play_permission(game, spell, caster)
    if permission is not None and permission.immediate:
        return None
    if game.can_cast_sorcery(caster):
        return None
    restricting_source = sorcery_speed_restriction_source(game, caster)
    if restricting_source is not None:
        return (
            f"{restricting_source} restricts {caster} to casting spells only any time "
            f"they could cast a sorcery, and it is not (CR 117.1a, CR 611.1)"
        )
    if Type.INSTANT in spell.card.types:
        return None  # CR 304.1
    if has_flash(spell.card):
        return None  # CR 702.8a
    if Type.SORCERY in spell.card.types and has_sorcery_speed_flash_grant(game, caster):
        return None  # Teferi, Time Raveler's +1
    if spell.zone is not Zone.HAND and castable_from(spell.card, spell.zone):
        # A keyword is what allows this cast at all (CR 601.3), and each one
        # carries its own timing - plot's "only as a sorcery" (CR 702.170a),
        # flashback's "any time you could cast a sorcery" (CR 702.34a). Let
        # `KeywordCastOption.why_not` answer instead of guessing over it.
        return None
    return (
        f"{spell.name} is not an instant and has no flash, so {caster} can only cast it "
        f"during their own main phase with the stack empty (CR 117.1a, CR 702.8a)"
    )


def why_cannot_cast_restriction(spell: CardState, caster: str, game: Any = None) -> str | None:
    """CR 611.1: why a rules-modifying continuous effect refuses this cast
    outright, or None.

    Distinct from `why_cannot_cast_now`'s timing question: Ranger-Captain of
    Eos's "Your opponents can't cast noncreature spells this turn" is a flat
    prohibition that holds at any timing, so it is checked separately rather
    than folded into the sorcery-speed logic above.
    """
    if game is None:
        return None
    restriction = restricted_from_noncreature_casting(game, caster)
    if restriction is not None and Type.CREATURE not in spell.card.types:
        return (
            f"{restriction.source_name} says {caster} can't cast noncreature spells "
            f"this turn (CR 611.1)"
        )
    return None


class CastingStep(StrEnum):
    PROPOSED = "proposed"
    MODES = "modes"
    TARGETS = "targets"
    COST_DETERMINED = "cost_determined"
    PAYING = "paying"
    CAST = "cast"
    CANCELLED = "cancelled"


CASTING_ORDER: tuple[CastingStep, ...] = (
    CastingStep.PROPOSED,
    CastingStep.MODES,
    CastingStep.TARGETS,
    CastingStep.COST_DETERMINED,
    CastingStep.PAYING,
    CastingStep.CAST,
)


class Casting(BaseModel):
    """One spell on its way to the stack.

    Created with the card being cast. Walk it through the steps in order, then
    `cast()` to finish, or `cancel()` to rewind the whole announcement.

    `game` is optional. Without it the announcement still works and targets are
    still checked against whatever objects the caller passed in; with it, costs
    that move cards or change a life total can actually be paid.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    spell: CardState
    caster: str
    game: Any = Field(default=None, exclude=True, repr=False)
    step: CastingStep = CastingStep.PROPOSED
    origin_zone: Zone = Zone.HAND
    chosen_modes: list[str] = Field(default_factory=list)
    """The text of each mode announced, in the order it was announced."""
    chosen_mode_numbers: list[int] = Field(default_factory=list)
    """Those same modes as their 1-based position on the card (CR 700.2)."""
    entwined: bool = False
    """CR 702.42a: the entwine cost is being paid, so every mode was chosen."""
    targets: list[TargetRef] = Field(default_factory=list)
    division: list[int] | None = None
    """CR 601.2d's announced division, one share per entry of `targets` in
    order - set by `announce_division`, `None` until then (and `None` stays
    the answer for a spell that never calls it, so `machines/effects.py`'s
    divided-damage effect falls back to splitting as evenly as it goes, the
    behaviour every existing scenario that never announces a division already
    relies on)."""
    mode_target_slices: list[list[TargetRef]] = Field(default_factory=list)
    """CR 700.2f: `self.targets`, the same announcement, bucketed one list per
    chosen mode instance instead of flattened - set by `choose_targets`, and
    parallel to `chosen_mode_numbers` (a mode chosen twice, where the card
    allows it, gets two entries here, one per instance)."""
    x_value: int = 0
    x_value_at_targets: int | None = None
    """The value `x_value` held the moment `choose_targets` ran, or None if it
    has not run yet. `choose_modes` and `determine_cost` are two independent
    setters of `x_value` (CR 107.3a's X is fixed once for the whole spell, but
    nothing before this stopped a caller from calling only one of them) - a
    caller that announces targets under one X and then changes it before
    `cast()` would count a mode's "up to X target ..." against the X it had
    when targets were chosen, not the X the spell actually resolves with.
    `cast()` compares this against the final `x_value` and refuses loudly
    rather than let that mismatch through silently."""
    face: str | None = None
    """The name of the face being cast, for a card with more than one (CR 715.3)."""
    keyword_used: str | None = None
    """The keyword this spell is being cast with, if any (CR 601.2b).

    Set by `use_keyword`. Kept on the casting because several keywords have a
    second half that fires afterwards - evoke's sacrifice trigger (CR 702.74a),
    flashback's exile replacement (CR 702.34a), warp's delayed trigger
    (CR 702.185a) - and none of them can be applied without knowing the spell
    was cast that way.
    """
    permission_used: PlayPermission | None = None
    """The `PlayPermission` this spell is being cast under, if any (CR 601.3).

    Set by `use_permission`. Kept for the same reason `keyword_used` is: it is
    what `cast()` checks to know the CR 601.3 permission was actually claimed,
    rather than inferred after the fact from the zone the card happened to be
    in."""
    alternative_cost: TotalCost | None = None
    additional_costs: list[TotalCost] = Field(default_factory=list)
    cost_increases: list[ManaCost] = Field(default_factory=list)
    cost_reductions: list[ManaCost] = Field(default_factory=list)
    kicked: int = 0
    """How many times this spell's kicker cost was paid (CR 702.33d).

    "If a spell's controller declares the intention to pay any of that spell's
    kicker costs, that spell has been 'kicked.'" Kept as a count rather than a
    flag because CR 702.33c's multikicker may be paid any number of times.
    """
    payment: CostPayment | None = None

    def model_post_init(self, _context: object) -> None:
        """CR 601.3: the announcement is refused if the timing does not allow it.

        "A player can begin to cast a spell only if a rule or effect allows that
        player to cast it and no rule or effect prohibits that player from
        casting it." The timing rules of CR 117.1a are such a prohibition, so
        they are checked here rather than after the cost has been paid.
        """
        refusal = why_cannot_cast_now(self.spell, self.caster, self.game)
        if refusal is not None:
            raise ValueError(refusal)
        refusal = why_cannot_cast_restriction(self.spell, self.caster, self.game)
        if refusal is not None:
            raise ValueError(refusal)

    @property
    def is_settled(self) -> bool:
        return self.step in {CastingStep.CAST, CastingStep.CANCELLED}

    @property
    def base_cost(self) -> ManaCost:
        """The printed mana cost of the spell.

        CR 118.9c: an alternative cost does not change this. It only changes
        what the caster has to pay, which is `total_cost`.

        A split card prints both halves in one `mana_cost` string,
        `{2}{R} // {1}{R}`, so the face being cast decides which half applies.
        CR 715.3 puts that choice on the caster for an adventurer card and
        CR 715.3a evaluates only the chosen face's characteristics.

        A transform or modal DFC is different again: Scryfall leaves the
        top-level `mana_cost` blank for those and puts each face's own cost on
        `card_faces` instead, because CR 712.8a only grants the card "the
        characteristics of its front face" outside the battlefield or stack -
        there is no combined cost to fall back to the way a split card has
        one. No face is ever explicitly chosen for these (`Casting.cast_as_adventure`
        is Adventure-only, CR 715.3), so the front face is the only one this
        reaches for.
        """
        face = self.chosen_face
        if face is not None:
            return ManaCost.parse(face.mana_cost or "")
        printed = self.spell.card.mana_cost or ""
        if "//" in printed and self.spell.card.card_faces:
            return ManaCost.parse(self.spell.card.card_faces[0].mana_cost or "")
        if not printed and self.spell.card.card_faces:
            return ManaCost.parse(self.spell.card.card_faces[0].mana_cost or "")
        return ManaCost.parse(printed)

    @property
    def chosen_face(self) -> Any:
        """The `CardFace` being cast, when the caster named one (CR 715.3)."""
        if self.face is None:
            return None
        for face in self.spell.card.card_faces or []:
            if face.name == self.face:
                return face
        raise ValueError(f"{self.spell.name} has no face called {self.face}")

    def cast_as_adventure(self) -> CastingStep:
        """CR 715.3: cast the Adventure half of an adventurer card.

        CR 715.3b: "While on the stack as an Adventure, the spell has only its
        alternative characteristics." This engine records *which* face was
        chosen and charges that face's mana cost; nothing else about the card
        changes, because `Card` reports the front face everywhere else - see
        `docs/engine-coverage.md`.
        """
        face = adventure_face(self.spell.card)
        if face is None:
            raise ValueError(f"{self.spell.name} has no Adventure (CR 715.1)")
        self._enter_modes()
        self.face = face.name
        return self.step

    def cast_as_split_half(self, face_name: str) -> CastingStep:
        """CR 709.3: choose which half of a split card to cast.

        "A player chooses which half of a split card they are casting before
        putting it onto the stack." Unlike `cast_as_adventure`, there is no
        modal structure to enter first - CR 709 names no bulleted choice, just
        the one face. `self.face` already drives `base_cost`/`chosen_face`
        (shared with Adventure); what is new here is recording the choice onto
        `self.spell` itself once cast (see `cast`), which `CardState.up_face`
        then reads for the whole time the spell sits on the stack (CR 709.3b) -
        Adventure's own equivalent gap is a separate, still-open limitation
        (`docs/engine-coverage.md`).

        Fuse (CR 702.102) - casting *both* halves as one spell - is not
        offered here: this always names exactly one.
        """
        if self.spell.card.layout is not Layout.SPLIT:
            raise ValueError(f"{self.spell.name} is not a split card (CR 709)")
        for face in self.spell.card.card_faces or []:
            if face.name == face_name:
                self.face = face_name
                return self.step
        raise ValueError(f"{self.spell.name} has no half called {face_name}")

    @property
    def modal(self) -> ModalProfile | None:
        """This card's modal structure, or None if it is not modal (CR 700.2)."""
        return modal_profile(self.spell.card)

    @property
    def chosen_mode_objects(self) -> tuple[Mode, ...]:
        """The announced modes, resolved back to the card's own bullets."""
        modal = self.modal
        if modal is None:
            return ()
        return tuple(modal.mode(number) for number in self.chosen_mode_numbers)

    @property
    def targeting(self) -> TargetingProfile:
        """What this spell is allowed to target, read off its oracle text.

        For a modal spell this is the profile of the *chosen* modes (CR 700.2c),
        which is why it can only be asked once the modes are announced. Before
        that, and for a modal card whose modes were never announced, it is the
        card-wide profile, which says `understood=False`.

        A split card (CR 709) reads its *chosen* half's own text once
        `cast_as_split_half` has named one - `targeting_profile(card)` always
        reads the combined text (both halves) otherwise, which is CR 709.3b's
        wrong answer for a spell that has "only the characteristics of the
        half being cast". Scoped to `Layout.SPLIT` alone, the same boundary
        `CardState.face_played` draws, so Adventure's own still-open gap is
        untouched.

        A **non-modal** card whose own mana cost has `{X}` (Postmortem
        Lunge's own "target creature card with mana value X") reads its text
        with X already substituted (CR 107.3a: X is announced before targets,
        so it is always known here). `profile_for_modes` already does the
        equivalent substitution for a *modal* card's chosen mode text; this is
        the same idea for the plain, unmoded case, which had no substitution
        at all before - `targeting_profile(card)` takes only the card, never
        an X, so "mana value X" came back an unresolvable bare X forever, at
        both announcement and `Game.legal_target`'s CR 608.2b recheck.
        """
        if self.modal is None or not self.chosen_mode_numbers:
            if self.spell.card.layout is Layout.SPLIT and self.face is not None:
                face = self.chosen_face
                if face is not None:
                    return profile_for_text(face.oracle_text or "")
            if "{X}" in (self.spell.mana_cost or ""):
                return profile_for_text(substitute_x(self.spell.oracle_text, self.x_value))
            return targeting_profile(self.spell.card)
        return profile_for_modes(self.spell.card, self.chosen_mode_objects, self.x_value)

    # -- CR 601.2b: modes, alternative costs, additional costs -------------

    def choose_modes(
        self,
        modes: Sequence[int | str | Mode],
        x_value: int | None = None,
        entwined: bool = False,
    ) -> CastingStep:
        """CR 601.2b: announce the mode choice, before targets and before costs.

        CR 700.2a puts the choice here, as part of casting, and CR 700.2c makes
        it decide what the spell targets - so an announcement that is not legal
        has to be refused now: an unknown mode, a mode chosen twice where the
        card does not allow it (CR 700.2d), or the wrong number of modes.

        A mode may be named by its 1-based number, by its text, or by a `Mode`
        read off `self.modal`. A card that is not modal accepts only an empty
        list, since it has no modes to choose.

        `entwined` is CR 702.42a: "'Entwine [cost]' means "You may choose all
        modes of this spell instead of just the number specified. **If you do,
        you pay an additional [cost].**"" Both halves happen here - every mode is
        opened *and* the cost is charged as an additional cost (CR 118.8a), so
        an entwined spell cannot be announced without paying for it.

        `x_value` is the value the caster chose for X (CR 107.3a). It is
        accepted here because a mode can read "up to X target cards", and that
        cannot be counted at CR 601.2c without it. It is the same value
        `determine_cost` locks into the total cost.
        """
        self._enter_modes()
        modal = self.modal

        if modal is None:
            if modes:
                raise ValueError(f"{self.spell.name} is not a modal spell (CR 700.2)")
            self.chosen_modes = []
            self.chosen_mode_numbers = []
        elif not modal.understood:
            # The card is modal but its instruction could not be read. Record
            # what was asked for and check nothing, rather than reject a legal
            # choice on the strength of a failed parse.
            chosen = [modal.mode(spec) for spec in modes]
            self.chosen_modes = [mode.text for mode in chosen]
            self.chosen_mode_numbers = [mode.number for mode in chosen]
        else:
            chosen = list(modal.resolve(modes, entwined=entwined))
            self.chosen_modes = [mode.text for mode in chosen]
            self.chosen_mode_numbers = [mode.number for mode in chosen]

        if entwined and not self.entwined:
            self._charge_entwine(modal)
        self.entwined = entwined
        if x_value is not None:
            self.x_value = x_value
        return self.step

    def _charge_entwine(self, modal: ModalProfile | None) -> None:
        """CR 702.42a: "If you do, you pay an additional [cost]."

        An *additional* cost (CR 118.8a), so the printed mana cost is still paid
        on top of it - the difference from an alternative cost, and the reason
        an entwined Tooth and Nail costs {7}{G}{G} rather than {2}.
        """
        if modal is None or modal.entwine_cost is None:
            raise ValueError(f"{self.spell.name} has no entwine cost (CR 702.42a)")
        cost = total_cost_for_phrase(modal.entwine_cost, self.caster)
        if cost is None:
            raise ValueError(
                f"{self.spell.name}'s entwine cost {modal.entwine_cost!r} could not be "
                f"read, so it cannot be paid"
            )
        self.additional_costs.append(cost.assign_payer(self.caster))

    def choose_alternative_cost(self, cost: TotalCost | ManaCost | None) -> CastingStep:
        """CR 118.9: pay this instead of the spell's mana cost.

        Only one alternative cost may ever apply to a spell (CR 118.9a), so
        announcing a second one is an error rather than a second discount.
        Additional costs, increases, and reductions still apply on top of it
        (CR 118.9d).
        """
        if self.alternative_cost is not None:
            raise ValueError("only one alternative cost can be applied to a spell")
        self._enter_modes()
        total = cost if isinstance(cost, TotalCost) else TotalCost.of(cost)
        self.alternative_cost = total.assign_payer(self.caster)
        return self.step

    @property
    def cast_options(self) -> list[KeywordCastOption]:
        """The keyword options that would cast this spell out of its origin zone."""
        return castable_from(self.spell.card, self.origin_zone)

    def use_keyword(self, keyword: str, *, choosing: list[CardState] | None = None) -> CastingStep:
        """CR 601.2b: announce that this spell is being cast using a keyword.

        This is the announcement, not the payment: it settles which zone the
        spell is coming from and what replaces its mana cost, and leaves the
        paying to `determine_cost`/`begin_paying` like any other cost.

        `choosing` fills in the objects a keyword cost needs - the black card
        evoke exiles, the Mountain Lava Dart's flashback sacrifices - because
        CR 601.2b is where those are chosen and CR 601.2h is where they are
        spent. They are handed to the cost's components in order.

        Raises when the keyword is not printed on the card, when the spell is in
        the wrong zone for it, when the exile pile is wrong, or when the timing
        is (CR 601.3). A keyword whose printed cost this engine could not read
        also raises rather than being quietly charged nothing.
        """
        options = [
            option
            for option in keyword_cast_options(self.spell.card)
            if option.keyword.lower() == keyword.lower()
        ]
        if not options:
            raise ValueError(f"{self.spell.name} has no {keyword} ability that casts it")

        reasons = [option.why_not(self.spell, self.caster, self.game) for option in options]
        usable = [option for option, reason in zip(options, reasons, strict=True) if reason is None]
        if not usable:
            # A keyword can hand out more than one option - warp casts from hand
            # and from exile - so report the one that was actually being tried,
            # which is the option for the zone the card is in.
            for option, reason in zip(options, reasons, strict=True):
                if option.zone is self.spell.zone and reason is not None:
                    raise ValueError(reason)
            raise ValueError(next(reason for reason in reasons if reason is not None))

        option = usable[0]
        self._enter_modes()
        self.keyword_used = option.keyword

        if option.pays_mana_cost:
            # Warp's second half: the card is cast from exile for its own mana
            # cost, so there is no alternative cost to announce (CR 702.185b).
            return self.step

        cost = option.cost.model_copy(deep=True) if option.cost is not None else TotalCost()
        remaining = list(choosing or [])
        for component in cost.components:
            if component.required and not component.cards:
                component.cards = remaining[: component.required]
                remaining = remaining[component.required :]
        self.choose_alternative_cost(cost)
        return self.step

    def use_permission(self) -> CastingStep:
        """CR 601.2b: announce that this spell is being cast under a
        `PlayPermission` some effect handed out (CR 601.3).

        The twin of `use_keyword` for the dynamic half of CR 601.3: it settles
        that the permission is what allows this cast, and - when the permission
        says "without paying its mana cost" - announces the empty alternative
        cost that replaces the printed one (CR 118.9, CR 107.3b).

        Raises when no live permission covers this player, this object and this
        zone, carrying the permission's own reason: the wrong player, a card
        that has moved since (CR 400.7), a turn that has ended (CR 514.2), or a
        permission that says *play* against a card being cast.
        """
        permission = usable_play_permission(self.game, self.spell, self.caster)
        if permission is None:
            granted = play_permissions_on(self.game, self.spell)
            if granted:
                raise ValueError(granted[0].why_not(self.spell, self.caster, self.game))
            raise ValueError(
                f"nothing allows {self.caster} to cast {self.spell.name} from the "
                f"{self.spell.zone.value} (CR 601.3)"
            )
        self._enter_modes()
        self.permission_used = permission
        if not permission.pays_mana_cost:
            # CR 118.9's alternative cost, with nothing in it - "without paying
            # its mana cost" is not a discount on the printed cost (CR 118.9c),
            # it is a different thing paid in its place, and CR 107.3b keeps
            # "no cost at all" distinct from "some other cost".
            self.choose_alternative_cost(TotalCost())
        return self.step

    def use_pitch_cost(self, *, choosing: list[CardState] | None = None) -> CastingStep:
        """CR 118.9's alternative cost, read straight off the card's own
        printed text rather than a named keyword - Force of Will's "You may
        pay 1 life and exile a blue card from your hand rather than pay this
        spell's mana cost." `_option_from_keyword` never sees this: nothing
        here names a keyword ability the way Evoke or Flashback does.

        Mirrors `use_keyword`: which card(s) pay a component (the blue card
        exiled, here) is chosen now (CR 601.2b), and paying happens later
        through the ordinary `CostPayment` path once `begin_paying` opens.

        Raises when the card prints no such offer, when its printed cost
        could not be read, or - Force of Negation's and Force of Vigor's own
        gate - when it is only offered "if it's not your turn" and it is.
        """
        offers = alternative_cost_offers(self.spell.card)
        if not offers:
            raise ValueError(f"{self.spell.name} has no inline alternative cost to pay (CR 118.9)")
        offer = offers[0]
        if offer.requires_not_your_turn and not self._is_not_my_turn():
            raise ValueError(
                f"{self.spell.name}'s alternative cost can only be paid on an opponent's turn"
            )
        cost = total_cost_for_phrase(offer.phrase, payer=self.caster)
        if cost is None:
            raise ValueError(f"{self.spell.name}'s alternative cost could not be read")
        self._enter_modes()
        remaining = list(choosing or [])
        for component in cost.components:
            if component.required and not component.cards:
                component.cards = remaining[: component.required]
                remaining = remaining[component.required :]
        self.choose_alternative_cost(cost)
        return self.step

    def _is_not_my_turn(self) -> bool:
        """Force of Negation's and Force of Vigor's own condition: whoever is
        casting is not the active player right now."""
        turn = getattr(self.game, "turn", None)
        if turn is None:
            return False
        return turn.active_player != self.caster

    def pay_escalate(self, *, choosing: list[CardState] | None = None) -> CastingStep:
        """CR 702.120a: pay the escalate cost for each mode beyond the first.

        Escalate is an *additional* cost, not an alternative one (CR 118.8a), so
        the printed mana cost is still paid on top of it - the difference from
        evoke, and the reason the two are not interchangeable.

        Collective Brutality prints its cost after an em dash,
        `Escalate—Discard a card.`, so `choosing` names the cards discarded, one
        set per extra mode. The modes have to be announced first, since the
        number of them is what the cost is multiplied by.
        """
        modal = self.modal
        if modal is None or modal.escalate_cost is None:
            raise ValueError(f"{self.spell.name} has no escalate cost (CR 702.120a)")
        if not self.chosen_mode_numbers:
            raise ValueError(
                f"{self.spell.name}'s modes have to be announced before escalate can be "
                f"paid for them (CR 601.2b, CR 702.120a)"
            )

        remaining = list(choosing or [])
        for _ in range(len(self.chosen_mode_numbers) - 1):
            cost = total_cost_for_phrase(modal.escalate_cost, self.caster)
            if cost is None:
                raise ValueError(
                    f"{self.spell.name}'s escalate cost {modal.escalate_cost!r} could not "
                    f"be read, so it cannot be paid"
                )
            for component in cost.components:
                if component.required and not component.cards:
                    component.cards = remaining[: component.required]
                    remaining = remaining[component.required :]
            self.add_additional_cost(cost)
        return self.step

    def pay_kicker(self, times: int = 1, *, choosing: list[CardState] | None = None) -> CastingStep:
        """CR 702.33a: pay this spell's kicker cost as an additional cost.

        "Kicker is a static ability that functions while the spell with kicker
        is on the stack. 'Kicker [cost]' means "You may pay an additional [cost]
        as you cast this spell."" It is an *additional* cost (CR 118.8a), so the
        printed mana cost is still paid on top - the difference from evoke.

        CR 702.33d: paying it is what makes the spell "kicked", which is the
        condition the card's other, linked ability reads (CR 702.33e, CR 607.2i).
        `kicked` records it, because nothing else on the casting could tell a
        kicked Burst Lightning from an unkicked one.

        CR 702.33c's multikicker may be paid more than once; `times` is that.
        A card with plain kicker refuses a second payment rather than charging
        for it.
        """
        ability = _keyword(self.spell.card, "kicker") or _keyword(self.spell.card, "multikicker")
        if ability is None:
            raise ValueError(f"{self.spell.name} has no kicker ability (CR 702.33a)")
        if times < 1:
            raise ValueError("kicker is paid at least once or not at all")
        multi = ability.canonical.lower() == "multikicker"
        if not multi and (times > 1 or self.kicked):
            raise ValueError(
                f"{self.spell.name} has plain kicker, which can only be paid once "
                f"(CR 702.33a; multikicker is CR 702.33c)"
            )

        remaining = list(choosing or [])
        for _ in range(times):
            cost = total_cost_for_phrase(ability.cost or "", self.caster)
            if cost is None:
                raise ValueError(
                    f"{self.spell.name}'s kicker cost {ability.cost!r} could not be read, "
                    f"so it cannot be paid"
                )
            for component in cost.components:
                if component.required and not component.cards:
                    component.cards = remaining[: component.required]
                    remaining = remaining[component.required :]
            self.add_additional_cost(cost)
            self.kicked += 1
        return self.step

    def add_additional_cost(self, cost: TotalCost | ManaCost) -> CastingStep:
        """CR 118.8a: any number of additional costs may be applied to a spell.

        Kicker is the mana-only case; "as an additional cost to cast this
        spell, sacrifice a creature" is the other kind. Both land here.
        """
        self._enter_modes()
        total = cost if isinstance(cost, TotalCost) else TotalCost.of(cost)
        self.additional_costs.append(total.assign_payer(self.caster))
        return self.step

    def increase_cost(self, amount: ManaCost | str) -> CastingStep:
        """An effect that makes this spell cost more (CR 601.2f)."""
        self._enter_modes()
        self.cost_increases.append(_as_mana(amount))
        return self.step

    def reduce_cost(self, amount: ManaCost | str) -> CastingStep:
        """An effect that makes this spell cost less (CR 601.2f, 118.7)."""
        self._enter_modes()
        self.cost_reductions.append(_as_mana(amount))
        return self.step

    # -- CR 601.2c: targets ------------------------------------------------

    def choose_targets(self, targets: Iterable[Any]) -> CastingStep:
        """CR 601.2c: announce a legal object or player for each target.

        Each entry may be a `TargetRef`, a `CardState` or its id, or a player
        or their username; `TargetRef.coerce` reads which was meant.

        An illegal choice raises: a target of the wrong kind, in a zone the
        spell cannot reach, controlled by the wrong player, or more targets
        than the spell takes. Announcing *fewer* targets than the spell
        requires is not rejected, which is a known gap - existing scenarios
        cast a targeted spell with no target chosen to prove the effect finds
        nothing. `self.targeting.min_targets` says what would be required.

        A card whose text the target parser cannot read is not checked at all,
        because refusing a target the parser merely failed to understand would
        be worse than not checking.

        A modal spell has to have its modes announced first (CR 601.2b, and
        CR 700.2c: which targets it needs follows from which modes were
        chosen), so reaching this step without them is an error rather than an
        unchecked cast.
        """
        modal = self.modal
        if modal is not None and modal.understood and not self.chosen_mode_numbers:
            raise ValueError(
                f"{self.spell.name} is modal: its modes must be announced before its "
                f"targets (CR 601.2b, CR 700.2c)"
            )

        chosen = list(targets)
        # The game is handed over because some restrictions are not
        # characteristics (CR 109.3) and cannot be read off the permanent -
        # "target attacking creature" lives on `Game.combat` (CR 508.1k).
        self.targeting.check(chosen, self.caster, game=self.game)
        for target in chosen:
            refusal = self._hexproof_refusal(target)
            if refusal is not None:
                raise ValueError(refusal)
            refusal = self._enchant_refusal(target)
            if refusal is not None:
                raise ValueError(refusal)
        self._advance_to(CastingStep.TARGETS)
        self.targets = [TargetRef.coerce(target) for target in chosen]
        if self.modal is not None and self.modal.understood and self.chosen_mode_numbers:
            # Only a modal spell's target *count* can depend on X (CR 700.2c's
            # "up to X target ..."), so only here does a later change to X
            # actually invalidate what was just announced - a non-modal X
            # spell (Prismatic Ending's mana-value comparison, Fireball's
            # damage total) is untouched by this and keeps announcing targets
            # and determining its cost in either order, as before.
            self.x_value_at_targets = self.x_value
        self._slice_targets_by_mode(chosen)
        return self.step

    def _slice_targets_by_mode(self, chosen: list[Any]) -> None:
        """CR 700.2f: bucket `chosen` by which chosen mode instance each entry
        belongs to, into `self.mode_target_slices` - the structural piece
        resolution needs to dispatch each mode against only its own targets.

        A non-modal spell, or a modal spell whose modes were never announced
        or whose profile this parser could not read, gets no slices at all;
        `machines/effects.py`'s per-mode dispatch treats a missing slice as
        "no targets known for this mode instance" rather than an error.
        """
        modal = self.modal
        if modal is None or not modal.understood or not self.chosen_mode_numbers:
            self.mode_target_slices = []
            return
        profile, owners = profile_for_modes_with_owners(
            self.spell.card, self.chosen_mode_objects, self.x_value
        )
        if not profile.understood:
            self.mode_target_slices = []
            return
        assignment = profile.assign_to_owners(owners, chosen, self.caster, game=self.game)
        self.mode_target_slices = [
            [TargetRef.coerce(target) for target in assignment.get(index, [])]
            for index in range(len(self.chosen_mode_numbers))
        ]

    def announce_division(self, shares: Iterable[int]) -> None:
        """CR 601.2d: announce how a divided effect is split among the
        targets already chosen - Electrolyze's 2 damage as 1 and 1 (or all 2
        on one target), Shatterskull Smashing's X (or twice X) split however
        the caster likes.

        Targets must already be announced (`choose_targets`): `shares` is one
        entry per entry of `self.targets`, in that same order, and CR 115.7f
        then keeps this fixed if a target is later changed. For a variable
        (X) division, `self.x_value` must already reflect CR 107.3a's
        announced X - `determine_cost` sets that - since the total to divide
        is not known before then; the doubling condition, if the card has
        one, is applied here from `TargetingProfile.division.
        doubled_if_x_at_least`.

        A card whose text carries no division at all raises, the same way
        `choose_targets` refuses an illegal target rather than silently doing
        nothing.
        """
        profile = self.targeting
        if profile.division is None:
            raise ValueError(f"{self.spell.name} does not divide anything to announce (CR 601.2d)")
        resolved_shares = [int(share) for share in shares]
        amount = profile.division.amount
        if amount is None:
            amount = self.x_value
            threshold = profile.division.doubled_if_x_at_least
            if threshold is not None and self.x_value >= threshold:
                amount = 2 * self.x_value
        profile.check_division(resolved_shares, self.targets, amount=amount)
        self.division = resolved_shares

    def _enchant_refusal(self, target: Any) -> str | None:
        """Why enchant stops this Aura spell targeting that, or None (CR 702.5a).

        "The enchant ability restricts what an Aura spell can target and what an
        Aura can enchant." An Aura spell targets what it will enchant (CR 303.4b),
        so the restriction has to be applied at announcement, not discovered on
        resolution.

        Only an Aura is asked, because enchant is written on Auras.
        """
        if "Aura" not in self.spell.card.subtypes:
            return None
        if not enchant_restrictions(self.spell.card):
            return None
        return why_cannot_enchant(self.spell, target, self.caster, self.game)

    def _hexproof_refusal(self, target: Any) -> str | None:
        """Why hexproof stops this spell targeting that, or None (CR 702.11b).

        CR 702.11a: "Hexproof is a static ability." CR 702.11b: "'Hexproof' on a
        permanent means 'This permanent can't be the target of spells or
        abilities your opponents control.'" So it is about *who* is casting,
        not about what: the controller's own spells target it happily.

        CR 702.11d's "hexproof from [quality]" is not read - no card in the pool
        has it, and guessing a quality would be worse than not checking. Nor is
        hexproof on a player (CR 702.11c): `Player` has no text to read it off.

        A `Casting` without a game cannot say who controls the target, so
        nothing is checked there.
        """
        if self.game is None or not isinstance(target, CardState):
            return None
        if target.zone is not Zone.BATTLEFIELD:
            # CR 702.11b speaks of a permanent, and a permanent is on the
            # battlefield (CR 110.1).
            return None
        # `target.keywords` (not `target.card.keywords`): a face-down
        # permanent has no text (CR 702.37c) and CardState.keywords already
        # knows that, so the raw printed field would wrongly grant hexproof
        # to a face-down permanent whose printed side happens to have it.
        if not any(keyword.lower() == "hexproof" for keyword in target.keywords):
            return None
        if self.game.controller_of(target).username == self.caster:
            return None
        return (
            f"{target.name} has hexproof, so {self.caster} - an opponent of its "
            f"controller - cannot target it (CR 702.11b)"
        )

    # -- CR 601.2f-h: the total cost, and paying it ------------------------

    @property
    def total_cost(self) -> TotalCost:
        """The whole thing that has to be paid, X included (CR 601.2f).

        Built from the printed cost, or from the alternative cost if one was
        announced, with every additional cost added and every increase and
        reduction applied.

        When a game is attached, board-wide static cost increases (Sphere of
        Resistance's "Spells cost {1} more to cast", Trinisphere's floor) are
        folded in here too, via `Game.static_cost_modifiers_for` - this is the
        step every ordinary cast reaches (`begin_paying` -> `determine_cost` ->
        this property), so nothing extra has to be called for them to apply.
        That is unlike `cost_reduction_for`'s self-discount, which stays an
        opt-in `Game.determine_total_cost` call (see its own docstring) - a
        spell reducing its own cost from its own text is a different question
        from another permanent taxing every spell in the game, and only the
        latter is this fix's job.
        """
        base = self.alternative_cost.mana if self.alternative_cost else self.base_cost
        increases = [*self.cost_increases, *(extra.mana for extra in self.additional_costs)]
        floor: int | None = None
        if self.game is not None:
            board_increases, floor = self.game.static_cost_modifiers_for(self.spell, self.caster)
            increases = increases + board_increases
        mana = apply_modifications(
            base.with_x(self.x_value), increases, self.cost_reductions, floor=floor
        )

        components = list(self.alternative_cost.components) if self.alternative_cost else []
        for extra in self.additional_costs:
            components.extend(extra.components)
        return TotalCost(mana=mana, components=components)

    def determine_cost(
        self,
        x_value: int | None = None,
        additional: ManaCost | None = None,
        choices: list[int | None] | None = None,
    ) -> CostPayment:
        """CR 601.2f: lock in the total cost, X included, and open a payment.

        The total cost is locked here and does not change afterwards, even if
        something would alter it mid-payment (CR 601.8).

        An additional cost is combined with the printed one symbol for symbol
        by `ManaCost.plus`, so a hybrid, Phyrexian, or snow symbol survives it.

        `choices` pins how each symbol of the finished total cost is paid, one
        index into that symbol's options per symbol (CR 118.13a) - which half
        of a hybrid, or whether a Phyrexian symbol takes mana or life.

        Passing no `x_value` keeps whatever the caster already announced -
        `choose_modes` takes one, because a mode can read "up to X target
        cards" and CR 601.2c has to be able to count it. X is 0 if nobody ever
        said otherwise.
        """
        self._advance_to(CastingStep.COST_DETERMINED)
        if x_value is not None:
            self.x_value = x_value
        if additional is not None:
            self.additional_costs.append(TotalCost.of(additional).assign_payer(self.caster))
        self._refuse_unless_mana_cost_payable()

        self.payment = CostPayment.for_total(
            self.total_cost.assign_payer(self.caster),
            game=self.game,
            payer=self.caster,
            # CR 106.6: the payment has to know what it is paying for, or mana
            # carrying a spend restriction cannot be judged against it. This is
            # a *cast*, which is what tells Cavern of Souls's mana apart from
            # Shang-Chi's - the latter pays for no spell at all.
            spend=ManaSpend.casting(self.spell.card),
        )
        if choices is not None:
            self.payment.choose(choices)
        return self.payment

    def begin_paying(self, choices: list[int | None] | None = None) -> CostPayment:
        """CR 601.2g: mana abilities may be activated now, and only now.

        `choices` pins how each symbol is paid, as in `determine_cost`.
        """
        if self.payment is None:
            self.determine_cost(choices=choices)
        elif choices is not None:
            self.payment.choose(choices)
        self._advance_to(CastingStep.PAYING)
        assert self.payment is not None
        return self.payment

    def _refuse_unless_modes_satisfied(self) -> None:
        """CR 700.2a/601.2b: modes are chosen as part of casting, not optional.

        `choose_modes` already rejects an out-of-range, duplicate, or unknown
        choice the moment it is called (via `ModalProfile.resolve`) - but a
        caller can skip calling it altogether, leaving `chosen_mode_numbers`
        at its empty default. That is not a spell cast with no chosen modes;
        it is a spell whose announcement (CR 601.2b) was never completed, so
        CR 601.2e/601.6 make the whole cast illegal. This is the one place
        every casting path passes through on the way to the stack, so it is
        where that illegality is finally caught, however it was reached.

        A card that is modal but whose instruction this parser could not read
        (`modal.understood is False`) is deliberately left unchecked, per
        `ModalProfile`'s own contract of refusing to guess. Elder Gargaroth's
        modal *triggered* ability likewise never reaches here, because
        `self.modal` only reads a *spell's* modal profile off the card - the
        creature spell itself is not modal.
        """
        modal = self.modal
        if modal is None or not modal.understood:
            return
        minimum, maximum = modal.allowed_range(entwined=self.entwined)
        chosen = len(self.chosen_mode_numbers)
        if minimum <= chosen <= maximum:
            return
        listing = "; ".join(str(mode) for mode in modal.modes)
        requirement = f"exactly {minimum}" if minimum == maximum else f"{minimum} to {maximum}"
        raise ValueError(
            f"{self.spell.name} is modal (CR 700.2a, CR 601.2b) and requires "
            f"{requirement} mode(s) chosen, but {chosen} were chosen. Modes: {listing}"
        )

    def _refuse_if_x_changed_since_targets(self) -> None:
        """CR 107.3a/CR 107.3c: X is fixed once for the whole spell - it does
        not get to mean one thing when targets were counted and another when
        the spell resolves.

        `choose_modes(x_value=...)` and `determine_cost(x_value=...)` are two
        independent setters of `self.x_value`: nothing before this stopped a
        caller from announcing targets under one value and then changing X
        with the other setter before `cast()`. That mismatch used to be
        silent - a mode reading "up to X target cards" would be *counted*
        against the X in force when `choose_targets` ran, then *resolve*
        against whatever X ended up being, which can create more targets than
        were ever legally announced for it. Loud beats silent here: refuse the
        cast outright rather than let the two disagree.
        """
        if self.x_value_at_targets is None:
            return
        if self.x_value_at_targets == self.x_value:
            return
        raise ValueError(
            f"{self.spell.name}: X was {self.x_value_at_targets} when targets were "
            f"chosen but is now {self.x_value} (CR 107.3a). Announce X once, before "
            f"choosing targets - via choose_modes's own x_value, or determine_cost "
            f"before choose_targets - and do not change it afterward."
        )

    def _refuse_unless_mana_cost_payable(self) -> None:
        """CR 118.6: a card with no printed mana cost has an unpayable cost.

        "Some objects have no mana cost. This represents an unpayable cost."
        This is not the same thing as a printed {0}: CR 118.5a's "{0}" is a
        real, if empty, cost that "must still be cast the same way as one with
        a cost greater than zero", so it parses to one generic symbol worth
        zero (`ManaCost.parse("{0}").symbols` is non-empty). A card with no
        mana symbols at all - Living End's blank corner, `Card.mana_cost ==
        ""` with no `card_faces` to fall back to - parses to no symbols at
        all, and CR 118.6 says that cost cannot be paid, full stop.

        CR 118.6a is the escape hatch: "If an alternative cost is applied to
        an unpayable cost, including an effect that allows a player to cast a
        spell without paying its mana cost, ... the cost becomes payable."
        `self.alternative_cost` is set exactly when CR 118.9's alternative
        cost machinery ran - `use_keyword` (Suspend's own free cast, once its
        last time counter comes off), `use_permission` (Shardless Agent's
        cascade hit), or `use_pitch_cost` - so this only refuses the *plain*
        hardcast CR 601.2b never grants Living End on its own: no black
        source on the battlefield, no alternative cost, no announcement.
        """
        if self.alternative_cost is not None:
            return
        if self.base_cost.symbols:
            return
        raise ValueError(
            f"{self.spell.name} has no mana cost, which CR 118.6 makes an unpayable "
            f"cost - it cannot be cast this way. Some alternative or additional cost "
            f"permission (a keyword like Suspend, or a resolving effect's permission "
            f"to cast it without paying its mana cost) must apply instead (CR 118.6a)."
        )

    def _refuse_unless_allowed_from_its_zone(self) -> None:
        """CR 601.3: a spell cast from anywhere but the hand needs permission.

        "A player can begin to cast a spell only if a rule or effect allows
        that player to cast it and no rule or effect prohibits that player from
        casting it." The hand is where the rules cast from by default
        (CR 302.1, CR 601.3); every other zone needs a keyword's static grant
        or an effect's `PlayPermission`.

        Checked here rather than at announcement because `Casting` is driven
        step by step: a scenario legitimately constructs the machine for a card
        in the graveyard and *then* discovers, through `use_keyword`, that
        nothing allows it. This is the last point before the spell reaches the
        stack, and CR 601.6 rewinds the whole thing anyway, so refusing here
        refuses the same action - it just lets the earlier steps say their own,
        more specific "no" first.
        """
        if self.origin_zone is Zone.HAND:
            return
        refusal = why_cannot_cast_from(self.spell, self.caster, self.origin_zone, self.game)
        if refusal is not None:
            raise ValueError(refusal)

    def cast(self) -> CardState:
        """Finish casting: the cost is paid and the spell is on the stack."""
        if self.payment is None or self.payment.step is not CostStep.PAID:
            raise ValueError("cannot finish casting before the cost is paid")
        self._refuse_unless_modes_satisfied()
        self._refuse_if_x_changed_since_targets()
        self._refuse_unless_allowed_from_its_zone()

        self._advance_to(CastingStep.CAST)
        self._turn_face_down_if_cast_that_way()
        self.spell.move_to(Zone.STACK)
        # The spell carries its targets with it, so resolution knows what it hits.
        self.spell.targets = list(self.targets)
        # CR 601.2d: the announced division, if any, travels with the spell
        # the same way its targets do - `None` when `announce_division` was
        # never called, which `deal_divided_damage` reads as "fall back to
        # splitting the total as evenly as it goes" rather than an error.
        self.spell.division = list(self.division) if self.division is not None else None
        if self.face is not None and self.spell.card.layout is Layout.SPLIT:
            # CR 709.3b: "While on the stack, only the characteristics of the
            # half being cast exist." `CardState.face_played` is what
            # `up_face` reads for the whole time this spell sits on the
            # stack - see its own docstring for why this is scoped to split
            # cards and does not also cover Adventure's `self.face`.
            self.spell.face_played = self.face
        if self.game is not None:
            self._emit_becomes_target()
            # CR 601.2b announced the keyword, the face and the modes, and
            # CR 601.2h paid the cost, and the `CardState` that reaches the
            # stack carries none of it. Several rules ask afterwards:
            # flashback's "exile this card instead" (CR 702.34a), warp's
            # delayed trigger, which exists only if the warp cost was paid
            # (CR 702.185a), Adventure's exile on resolution (CR 715.3d), which
            # targets a modal spell has (CR 700.2c, rechecked by CR 608.2b),
            # what mana was spent to pay the total cost (CR 601.2h), and
            # whether a kicker cost was among the costs paid (CR 702.33d).
            # `Game.note_cast` is where every answer is kept.
            self.game.note_cast(
                self.spell,
                keyword=self.keyword_used,
                origin_zone=self.origin_zone,
                face=self.face,
                modes=list(self.chosen_mode_numbers),
                mode_targets=[list(slice_) for slice_ in self.mode_target_slices],
                x_value=self.x_value,
                mana_spent=(
                    dict(self.payment.mana_payment.spend)
                    if self.payment is not None and self.payment.mana_payment is not None
                    else {}
                ),
                kicked=self.kicked,
                additional_cost_cards=[
                    card.id
                    for extra in self.additional_costs
                    for component in extra.components
                    for card in component.cards
                ],
            )
        return self.spell

    def _turn_face_down_if_cast_that_way(self) -> None:
        """CR 708.4: a card cast face down is turned face down before it is cast.

        "Objects that are cast face down are turned face down before they are
        put onto the stack, so effects that care about the characteristics of a
        spell will see only the face-down spell's characteristics."

        Which characteristics those are is listed by the keyword that allowed it
        (CR 708.2): CR 702.37c for morph and megamorph, CR 702.168b for
        disguise.
        """
        if self.keyword_used is None:
            return
        if self.keyword_used.lower() not in ("morph", "megamorph", "disguise"):
            return
        characteristics = face_down_characteristics(self.spell.card)
        if characteristics is not None:
            self.spell.turn_face_down(characteristics)

    def _emit_becomes_target(self) -> None:
        """CR 702.21a: the objects this spell targeted have become targets.

        Ward is a *triggered* ability, so this is an event like any other and
        `Game.emit` works out what it fired. It is raised as the announcement
        finishes because that is when the targets are settled (CR 601.2c) and
        the spell exists on the stack for the trigger to counter (CR 601.2i);
        `Game.put_on_stack` then flushes it alongside the cast triggers, which
        is CR 603.3's "the next time a player would receive priority".

        Only permanents are asked: CR 702.21a says "whenever **this permanent**
        becomes the target", and an object that is not on the battlefield is not
        a permanent (CR 110.1).
        """
        for target in self.targets:
            if not target.is_card or target.card_id is None:
                continue
            targeted = self.game.find_by_id(target.card_id)
            if targeted is None or targeted.zone is not Zone.BATTLEFIELD:
                continue
            self.game.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_TARGET,
                    subject_id=targeted.id,
                    subject_name=targeted.name,
                    subject_controller=targeted.controller,
                    subject_card=targeted.card,
                    targeted_by=self.spell.id,
                    player=self.caster,
                )
            )

    def cancel(self) -> None:
        """Rewind the announcement, undoing every payment already made.

        CR 733.1: the entire action is reversed and any payments already made
        are cancelled. The spell goes back where it came from, since a spell
        that cannot be cast legally was never cast at all (CR 601.6).
        """
        if self.is_settled:
            raise ValueError(f"casting is already {self.step}")
        if self.payment is not None:
            self.payment.rewind()
        annotation = self.spell.exile_annotation
        self.spell.move_to(self.origin_zone)
        if self.origin_zone is Zone.EXILE:
            # It never left, so its pile is still its pile (CR 406.4).
            self.spell.exile_annotation = annotation
        self.step = CastingStep.CANCELLED

    def _enter_modes(self) -> None:
        """CR 601.2b happens once, before targets are chosen."""
        if self.is_settled:
            raise ValueError(f"casting is already {self.step}")
        if self.step is CastingStep.PROPOSED:
            self.step = CastingStep.MODES
        elif self.step is not CastingStep.MODES:
            raise ValueError(f"cannot go back to {CastingStep.MODES} from {self.step}")

    def _advance_to(self, target: CastingStep) -> None:
        """Steps run in order and none may be repeated or skipped backwards."""
        if self.is_settled:
            raise ValueError(f"casting is already {self.step}")
        if CASTING_ORDER.index(target) <= CASTING_ORDER.index(self.step):
            raise ValueError(f"cannot go back to {target} from {self.step}")
        self.step = target


def _as_mana(amount: ManaCost | str) -> ManaCost:
    return ManaCost.parse(amount) if isinstance(amount, str) else amount


# --------------------------------------------------------------------------
# Adventure (CR 715)
# --------------------------------------------------------------------------


def adventure_face(card: Card) -> Any:
    """The Adventure half of an adventurer card, or None (CR 715.1).

    CR 715.1: "Adventurer cards have a two-part card frame, with a smaller frame
    inset within their text box." The inset half is the one whose type line says
    Adventure.
    """
    for face in card.card_faces or []:
        if "adventure" in (face.type_line or "").lower():
            return face
    return None


# --------------------------------------------------------------------------
# Exiling a card now to cast it later (CR 116.2, CR 406.4)
# --------------------------------------------------------------------------


def annotate_exile(
    card: CardState, marker: ExileMarker, owner: str | None = None, game: Any = None
) -> CardState:
    """Record which pile of exile a card is in (CR 406.4).

    The turn number is taken from the game because every keyword that casts out
    of exile is gated on "a later turn" than the one the card arrived on -
    CR 702.170d says so for plot in as many words.
    """
    if card.zone is not Zone.EXILE:
        raise ValueError(f"{card.name} is in the {card.zone.value}, not in exile")
    card.exile_annotation = ExileAnnotation(
        marker=marker, owner=owner or card.controller, turn_exiled=_turn_number(game)
    )
    return card


class MarkedExile(BaseModel):
    """One of CR 116.2's exile-it-now, cast-it-later special actions.

    Three of them are modelled: plot (CR 116.2k, CR 702.170b), foretell
    (CR 116.2h, CR 702.143b), and suspend (CR 116.2f, CR 702.62a). All three
    pay a cost, move a card from hand to exile, and leave it in a named pile
    that a later `Casting` reads.

    CR 116.1: special actions do not use the stack, so nothing here touches it
    and nobody gets priority in the middle. The cost is still a cost, so it is
    paid through `CostPayment` and rewinds the same way (CR 733.1).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: CardState
    player: str
    marker: ExileMarker
    cost: TotalCost
    rule: str
    face_down: bool = False
    game: Any = Field(default=None, exclude=True, repr=False)
    payment: CostPayment | None = None
    taken: bool = False
    time_counters: int | None = None
    """Suspend only (CR 702.62a): the N of "Suspend N-[cost]", put on the card
    as `Counter.TIME` once it reaches exile. `None` for plot and foretell,
    which exile a card with no counters at all."""

    @classmethod
    def plot(cls, game: Any, card: CardState, player: str) -> "MarkedExile":
        """CR 116.2k: exile a card with plot from hand, paying its plot cost.

        CR 702.170a puts the timing on it - "Any time you have priority during
        your main phase while the stack is empty" - which is the same window as
        casting a sorcery, so `Game.can_cast_sorcery` answers it.
        """
        ability = _keyword(card.card, "plot")
        if ability is None:
            raise ValueError(f"{card.name} has no plot ability (CR 702.170a)")
        if game is not None and not game.can_cast_sorcery(player):
            raise ValueError(
                f"{player} can only plot during their own main phase with the stack "
                f"empty (CR 116.2k, CR 702.170a)"
            )
        cost = total_cost_for_phrase(ability.cost or "") or TotalCost()
        return cls(
            card=card,
            player=player,
            marker=ExileMarker.PLOTTED,
            cost=cost.assign_payer(player),
            rule="CR 116.2k",
            game=game,
        )

    @classmethod
    def foretell(cls, game: Any, card: CardState, player: str) -> "MarkedExile":
        """CR 116.2h: pay {2} and exile a card with foretell from hand, face down.

        The {2} is the special action's cost, not the card's foretell cost -
        that one is what the card is later cast for (CR 702.143a). Getting the
        two the wrong way round would make Lupine Harbingers cost {4}{G}{G} to
        put away and {2} to cast.

        CR 116.2h allows it "any time they have priority during their turn", so
        unlike plot it is not restricted to a main phase or an empty stack.
        """
        if _keyword(card.card, "foretell") is None:
            raise ValueError(f"{card.name} has no foretell ability (CR 702.143a)")
        if game is not None and game.turn is not None and game.turn.active_player != player:
            raise ValueError(f"{player} can only foretell during their own turn (CR 116.2h)")
        return cls(
            card=card,
            player=player,
            marker=ExileMarker.FORETOLD,
            cost=TotalCost.of(ManaCost.parse("{2}")).assign_payer(player),
            rule="CR 116.2h",
            face_down=True,
            game=game,
        )

    @classmethod
    def suspend(cls, game: Any, card: CardState, player: str) -> "MarkedExile":
        """CR 116.2f: exile a card with suspend from hand, paying its suspend cost.

        "'Suspend N-[cost]' means 'If you could begin to cast this card by
        putting it onto the stack from your hand, you may pay [cost] and
        exile it with N time counters on it. This action doesn't use the
        stack.'" (CR 702.62a). Unlike plot and foretell, the suspend cost
        *is* what is paid here - there is no separate cast-time cost the way
        foretell's {2} is distinct from its own printed cost, because CR
        702.62a's third ability later casts the card "without paying its mana
        cost" outright.

        CR 702.62c: "While determining if you could begin to cast a card with
        suspend, take into consideration any effects that would prohibit that
        card from being cast" - `why_cannot_cast_now`/`why_cannot_cast_
        restriction` are exactly that question (CR 117.1a's timing, CR
        611.1's flat prohibitions), and deliberately not CR 118.6's unpayable
        cost: CR 118.6 itself says "attempting to cast a spell ... that has
        an unpayable cost is a legal action" - only *paying* an unpayable
        cost is illegal - so Living End's blank mana cost does not block
        being suspended, which is the whole reason the special action exists
        for a card like it at all.
        """
        ability = _keyword(card.card, "suspend")
        if ability is None:
            raise ValueError(f"{card.name} has no suspend ability (CR 702.62a)")
        if card.zone is not Zone.HAND:
            raise ValueError(f"{card.name} is in the {card.zone.value}, not in hand (CR 116.2f)")
        refusal = why_cannot_cast_now(card, player, game) or why_cannot_cast_restriction(
            card, player, game
        )
        if refusal is not None:
            raise ValueError(
                f"{card.name} could not begin to be cast right now, so it cannot be "
                f"suspended: {refusal} (CR 116.2f, CR 702.62c)"
            )
        if ability.count is None:
            raise ValueError(f"{card.name}'s suspend count could not be read (CR 702.62a)")
        cost = total_cost_for_phrase(ability.cost or "") if ability.cost else TotalCost()
        if cost is None:
            raise ValueError(f"{card.name}'s suspend cost could not be read (CR 702.62a)")
        return cls(
            card=card,
            player=player,
            marker=ExileMarker.SUSPENDED,
            cost=cost.assign_payer(player),
            rule="CR 116.2f",
            game=game,
            time_counters=ability.count,
        )

    def begin_paying(self) -> CostPayment:
        """Open the payment for the special action's cost (CR 601.2h shape)."""
        if self.payment is None:
            self.payment = CostPayment.for_total(self.cost, game=self.game, payer=self.player)
        return self.payment

    def take(self) -> CardState:
        """Perform the action: the cost is paid, so the card goes to exile.

        CR 406.3: exiled cards are face up by default; foretell says face down,
        which is what `face_down` carries.
        """
        payment = self.begin_paying()
        if payment.step is not CostStep.PAID:
            raise ValueError("the special action's cost has not been paid yet")
        if self.taken:
            raise ValueError(f"{self.card.name} has already been exiled")

        owner = self.game.player(self.player)
        if self.card in owner.cards_in(self.card.zone):
            owner.cards_in(self.card.zone).remove(self.card)
        self.card.move_to(Zone.EXILE)
        self.game.exile.append(self.card)
        if self.face_down:
            self.card.turn_face_down()
        annotate_exile(self.card, self.marker, self.player, self.game)
        if self.time_counters is not None:
            # CR 702.62a: "... exile it with N time counters on it."
            self.game.add_counters(self.card, Counter.TIME, self.time_counters)
        self.taken = True
        return self.card

    def cancel(self) -> None:
        """Rewind the cost, leaving the card where it was (CR 733.1)."""
        if self.payment is not None:
            self.payment.rewind()


def remove_suspend_time_counter(game: Any, card: CardState) -> int:
    """CR 702.62a's second ability: "At the beginning of your upkeep, if this
    card is suspended, remove a time counter from it."

    CR 702.62b: "suspended" means "in the exile zone, has suspend, and has a
    time counter on it" - the intervening *if*. A card that fails any part of
    that (already cast, already left exile some other way, or already at
    zero counters) is left untouched and this returns its current count
    rather than raising, the same "the *if* was false, do nothing" shape
    `persist_return` already returns `None` for.

    Not driven automatically: like `exile_warped`'s delayed trigger, nothing
    in this engine's turn machine dispatches a per-card upkeep trigger (the
    CR 703.4 actions it does drive - untap, draw, discard, damage-wipe - are
    listed in `docs/scenario-tests.md`), so a scenario calls this once per
    upkeep it cares about, the same hand-driven shape combat's own
    declarations take.
    """
    if card.zone is not Zone.EXILE:
        return card.counter_count(Counter.TIME)
    annotation = card.exile_annotation
    if annotation is None or annotation.marker is not ExileMarker.SUSPENDED:
        return card.counter_count(Counter.TIME)
    if card.counter_count(Counter.TIME) <= 0:
        return 0
    card.remove_counters(Counter.TIME, 1)
    return card.counter_count(Counter.TIME)


def finish_suspend(game: Any, card: CardState) -> PlayPermission | None:
    """CR 702.62a's third ability: once the last time counter comes off a
    suspended card, its owner may cast it without paying its mana cost.

    "'When the last time counter is removed from this card, if it's exiled,
    you may play it without paying its mana cost if able. If you don't, it
    remains exiled.'" The intervening *if* ("if it's exiled") is read against
    the card's *current* zone, not the zone it was in when the last counter
    came off - CR 603.10's ordinary "check now" shape for a triggered
    ability's own condition.

    Returns the granted `PlayPermission` (CR 601.3's dynamic half - the same
    primitive Ugin, Eye of the Storms' -11 and Ragavan's trigger already use,
    via `Game.grant_play_permission`), or `None` when the *if* is false or
    the card still has a time counter on it (the ability has not actually
    triggered). The "may" itself is left to the caller: nobody here to ask
    (CR 608.2d) - the caller's choice **is** whether it ever calls
    `Casting.use_permission()` on the permission this hands back; never
    calling it is CR 702.62a's own "if you don't, it remains exiled."

    That fallback is what makes leaving the permission to expire on its own
    (`bottom_if_unused` left at its default `False`) correct here, rather
    than the gap it turned out to be for `machines.keywords.cascade`: CR
    702.62a's own sentence names "remains exiled" as the resting state for a
    suspended card nobody plays, so `Game.cleanup_step` dropping an unused
    permission and leaving the card exactly where it sits already matches the
    rule. Cascade's own sentence names no such fallback - "put the exiled
    cards... that weren't cast on the bottom" is the fallback, for every card
    that "weren't cast" - which is why only cascade's grant carries `bottom_
    if_unused=True`. See `PlayPermission.bottom_if_unused`'s own docstring.

    `immediate=True`: unlike Ugin's and Ragavan's grants, CR 702.62a's third
    ability never prints "until end of turn" - it is CR 117.2e's "resolving
    spells and abilities may instruct players to take actions... no player has
    priority while [it] is resolving" shape instead, so the "you may play it"
    is only good for as long as that instruction is still being carried out,
    not for the rest of the turn. See `PlayPermission.immediate`'s own
    docstring.
    """
    if card.zone is not Zone.EXILE:
        return None
    annotation = card.exile_annotation
    if annotation is None or annotation.marker is not ExileMarker.SUSPENDED:
        return None
    if card.counter_count(Counter.TIME) > 0:
        return None
    return game.grant_play_permission(
        card,
        annotation.owner or card.controller or game.active_player.username,
        action=PlayAction.CAST,
        pays_mana_cost=False,
        source_name=f"{card.name}'s suspend",
        rule="CR 702.62a",
        immediate=True,
    )


def grant_suspend_haste(game: Any, permanent: CardState) -> None:
    """The back half of CR 702.62a's third ability: "If you cast a creature
    spell this way, it gains haste until you lose control of the spell or the
    permanent it becomes."

    Applied the same way Postmortem Lunge's own no-duration-stated haste is
    (`machines/effects._parse_delayed_reanimate_haste_exile_clauses`):
    `Duration.INDEFINITE` (CR 611.2a's default when no duration is printed),
    scoped with `only_this_incarnation` to the exact object that just entered,
    so a later object with the same id (returned again some other way) does
    not inherit it. "Until you lose control" is not separately timed -
    losing control ordinarily also means a zone change (CR 400.7 makes the
    permanent that arrives under a new controller a new object), which
    `only_this_incarnation`'s stamp check already ends the effect for.

    Not driven automatically, for the same reason `remove_suspend_time_
    counter` is not: nothing here knows a resolving spell "was cast this way"
    except the caller who called `finish_suspend` and then
    `Casting.use_permission()` - a scenario calls this once the resolved
    spell's `CardState` reaches the battlefield, mirroring the hand-driven
    shape every other delayed or off-stack trigger in this engine already
    takes.
    """
    store = game.continuous_effects
    timestamp = store.tick()
    store.add(
        ContinuousEffect(
            description=f"{permanent.name}: suspend grants haste (CR 702.62a)",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
            modification=grant_ability("Haste"),
        )
    )


def exile_warped(game: Any, permanent: CardState) -> CardState:
    """Perform warp's delayed triggered ability by hand (CR 702.185a, CR 603.7).

    "Warp represents two static abilities that function while the card with warp
    is on the stack, one of which may create a delayed triggered ability." That
    delayed ability exiles the permanent at the beginning of the next end step,
    and CR 702.185b then calls it a warped card in exile.

    Delayed triggered abilities are not modelled (CR 603.7), so nothing fires
    this on its own. A scenario calls it, the way scenarios call the combat
    turn-based actions the turn machine does not perform.
    """
    game.exile_permanent(permanent)
    return annotate_exile(permanent, ExileMarker.WARPED, permanent.controller, game)


def exile_adventured(game: Any, spell: CardState, owner: str | None = None) -> CardState:
    """Perform CR 715.3d by hand: exile a resolved Adventure instead of binning it.

    "Instead of putting a spell that was cast as an Adventure into its owner's
    graveyard as it resolves, its controller exiles it. For as long as that card
    remains exiled, that player may play it."

    A replacement effect on resolution, and `Game.resolve_top` has no hook for
    one, so a scenario applies it itself.
    """
    player = game.player(owner or spell.controller)
    if spell in player.cards_in(spell.zone):
        player.cards_in(spell.zone).remove(spell)
    for cards in game.shared_zones.values():
        if spell in cards:
            cards.remove(spell)
    spell.move_to(Zone.EXILE)
    game.exile.append(spell)
    return annotate_exile(spell, ExileMarker.ADVENTURED, player.username, game)


def _keyword(card: Card, keyword: str) -> KeywordAbility | None:
    for ability in keyword_abilities(card):
        if ability.canonical.lower() == keyword.lower():
            return ability
    return None
