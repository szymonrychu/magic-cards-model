import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import ConfigDict

from ...models.card import Card, Type
from ...models.card_state import CardState, ExileMarker
from ...models.mana import ManaCost
from ...models.zone import Zone
from ...phrases import with_indefinite_article
from ...snapshot import EngineModel
from ..abilities import (
    KeywordAbility,
    keyword_abilities,
)
from ..cost import (
    ComponentKind,
    CostComponent,
    TotalCost,
    additional_cost_phrases,
    alternative_cost_phrase_of_line,
    cost_component_for_phrase,
    per_object_exile_reduction_of_sentence,
    per_object_sacrifice_reduction_of_sentence,
    return_to_hand_cost,
    total_cost_for_phrase,
    why_not_unblocked,
)
from ..keywords import (
    FACE_DOWN_CAST_COST,
    printed_casualty_numbers,
    printed_conspire_count,
)
from ..modes import substitute_x
from ..targeting import (
    profile_for_text,
)


class CastTiming(StrEnum):
    """When a keyword lets a card be cast.

    `ANY` means the card's own timing rules apply and this keyword adds nothing.
    `SORCERY` is the sentence plot prints, "Plot only as a sorcery": the
    caster's own main phase, with the stack empty (CR 702.170a, CR 117.1c).
    """

    ANY = "any"
    SORCERY = "sorcery"
    #: CR 702.190a's sneak: "Any time you could cast an instant during your
    #: declare blockers step" - the caster's own turn, `Step.DECLARE_BLOCKERS`,
    #: with priority, stack empty or not (CR 117.1a's instant half). Unlike
    #: `ANY`, this is a *window*: it both opens that step to a card whose own
    #: type would not allow it (a sorcery, a creature without flash) and shuts
    #: every other moment to this option.
    OWN_DECLARE_BLOCKERS = "own_declare_blockers"
    #: The spell's own timing, exactly as if it were cast from the hand (CR
    #: 117.1a): a permission that only opens another zone - "You may cast
    #: creature spells from the top of your library." - changes where a spell
    #: is cast from and never when. `KeywordCastOption.why_not` asks
    #: `why_cannot_cast_now` of the card as a hand card, so flash (CR 702.8a)
    #: and every flash grant still count.
    OWN = "own"


class KeywordCastOption(EngineModel):
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
    normal_face_only: bool = False
    """True when the permission covers the card's normal characteristics and
    never an alternative face named on top of it - CR 715.3d's adventured
    exile: "It can't be cast as an Adventure this way". A cast claiming this
    option with a face named is refused (`Casting._refuse_unless_allowed_
    from_its_zone`), and `legal_actions` offers it no face row at all."""
    face_only: str | None = None
    """The one split half this option may cast, when it covers a single half
    rather than the whole card - CR 702.127a's aftermath: "You may cast this
    half of this split card from your graveyard". A cast claiming the option
    with another half named, or none, is refused (`Casting._refuse_unless_
    allowed_from_its_zone`), and `legal_actions` offers no row for the other
    half under it."""
    later_turn: bool = False
    """True when the card may only be cast on a turn after the one it was
    exiled on - plot (CR 702.170d), foretell, and warp all say so."""
    discarded_this_turn: bool = False
    """True when the keyword only applies to a card its controller *discarded*
    this turn - mayhem's own "As long as you discarded this card this turn"
    (CR 702.187b), and nothing else in this pool.

    Not a count. `Game.cards_discarded_this_turn` records how many cards each
    player has discarded, which answers Hollow One's cost reduction and cannot
    answer this: the question here is whether *this card* was one of them, and
    who discarded it. `CardState.discarded_by`/`discarded_on_turn` are that
    record, written by `machines/keywords.discard`, and `why_not` reads both."""
    returns_unblocked_creature: bool = False
    """True when the cost includes "returning an unblocked creature you
    control to its owner's hand" (CR 702.190a's sneak). The option is then
    unavailable while the caster controls no unblocked creature (CR 509.1h),
    and `cost` carries a `ComponentKind.RETURN_TO_HAND` component the caster
    fills with the creature chosen (CR 601.2b's `choosing`)."""
    returns_tapped_creature: bool = False
    """True when the cost includes "returning a tapped creature you control to
    its owner's hand" (CR 702.188a's web-slinging): unavailable while the
    caster controls no tapped creature, and the chosen creature is checked
    as it is chosen (CR 601.2b)."""
    prowl: bool = False
    """True for CR 702.76a's prowl: the alternative cost is available only "if
    a player was dealt combat damage this turn by a source that, at the time
    it dealt that damage, was under your control and had any of this spell's
    creature types". `why_not` asks `Game.prowl_condition_holds`, which reads
    `Game.combat_damage_to_players_this_turn` - the record captured as the
    damage was dealt, so a source that has since died or changed still counts
    as it was."""
    spectacle: bool = False
    """True for CR 702.137a's spectacle: the alternative cost is available
    only "if an opponent lost life this turn", checked by
    `Game.spectacle_condition_holds` against `Player.life_lost_this_turn`
    (CR 119.2/118.3b/701.12c's gross per-turn loss) rather than a new
    per-turn record of its own."""
    surge: bool = False
    """True for CR 702.117a's surge: the alternative cost is available only
    "if you or one of your teammates has cast another spell this turn",
    checked by `why_not` against `Game.spells_cast_this_turn` - another
    spell, so the one being cast never counts itself."""
    understood: bool = True
    """False when the keyword's printed cost could not be read into something
    payable. The option is still reported, so a sweep can see the gap."""
    granted_line: str | None = None
    """The keyword line this option came from when it was *granted* rather
    than printed (CR 610.5) - `"Evoke {4}"` for Ashling, the Limitless's
    "Elemental permanent spells you cast from your hand gain evoke {4} as you
    cast them." `None` for a keyword read off the card's own printing, which
    needs no line recorded because the printing already says it.

    CR 400.7b is what this is for: "effects from static abilities that grant an
    ability to a permanent spell that functions on the battlefield continue to
    apply to the permanent that spell becomes", and CR 611.3d adds that such an
    ability "lasts indefinitely unless some other duration is stated". A
    keyword that is *two* abilities - evoke is, by CR 702.74a - therefore keeps
    its battlefield half after the grantor is gone, and the only way for that
    to be true of the object rather than of the grantor is for the object to
    carry the line. `Casting._use_keyword` stamps it onto
    `CardState.granted_ability_texts`, where
    `machines/triggers.granted_triggered_abilities_of` reads it back."""
    exile_instead_of_graveyard: bool = False
    """The grant's own "If a spell cast this way would be put into a/your
    graveyard, exile it instead." (CR 614.1a) - Kess, Dissident Mage's and
    The Great Work's rider. `Casting.cast()` copies it onto
    `CastRecord.exile_instead_of_graveyard`, the same record a
    `PlayPermission`'s identical rider already reaches."""
    emerge_quality: str | None = None
    """CR 702.119a/b: the quality of the permanent the emerge cost sacrifices
    - "creature" for plain emerge, the printed [quality] for "Emerge from
    [quality]" - and so the mark that the total cost is then reduced by that
    permanent's mana value (`Casting._use_keyword`). None for every other
    keyword."""
    once_per_turn_key: str | None = None
    """Set for "Once during each of your turns, you may cast ... from your
    graveyard" (Rivaz of the Claw, Gisa and Geralf, Kess, Dissident Mage):
    the granting permanent as that object (`"<id>:<zone change stamp>"`,
    CR 400.7), which `Game.once_per_turn_cast_permissions_used` records the
    moment a spell is cast under it, so the same permanent grants no second
    one that turn - while a new object, or a second such permanent, grants
    its own."""
    additional_cost: TotalCost | None = None
    """An additional cost the permission itself charges on top of the spell's
    other costs (CR 601.2f) - Noctis, Prince of Lucis's "by paying 3 life in
    addition to paying their other costs". Added by `Casting._use_keyword`
    through `add_additional_cost` when the option is claimed."""
    enters_with_counters: tuple[str, ...] = ()
    """One counter kind per counter the spell's permanent enters with because
    it was cast under this permission - "If you cast a spell this way, that
    creature enters with a finality counter on it." (Leonardo, Sewer Samurai;
    Noctis, Prince of Lucis), "... enters with an additional +1/+1 counter on
    it" (Mikey & Don, Party Planners). CR 614.1c makes it a replacement effect
    on the entering permanent; `Casting.cast()` copies it onto
    `CastRecord.enters_with_counters`, which `machines/replacement.py`'s
    `_cast_permission_rider_modifiers` reads as the permanent enters."""

    def why_not(
        self,
        spell: CardState,
        caster: str,
        game: Any = None,
        origin: Zone | None = None,
        *,
        cost_paid: bool = False,
    ) -> str | None:
        """Why this option cannot be used right now, or None if it can.

        `cost_paid` is CR 601.2h already behind the cast: a requirement that is
        only about being able to pay the cost - an unblocked creature to
        return for sneak (CR 702.190a), a tapped one for web-slinging - was
        met by paying it, and the creature returned is no longer there to be
        found, so it is not asked again.

        CR 601.3 is the rule: permission first, everything else after.

        `origin` is the zone the cast is coming *from*, which is not always
        the zone the card is in: CR 601.2a moves the card to the stack as the
        first step of proposing the cast, so a `Casting` mid-announcement asks
        about the zone it announced from rather than about where the card is
        sitting now. Left out, the card's own zone is the answer, which is
        what every caller outside an announcement wants.
        """
        where = origin if origin is not None else spell.zone
        if not self.understood:
            return f"{spell.name}'s {self.keyword} cost could not be read, so it cannot be paid"
        if where is not self.zone:
            return (
                f"{self.keyword} casts {spell.name} from the {self.zone.value}, "
                f"but it is in the {where.value} ({self.rule})"
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

        if self.discarded_this_turn:
            # CR 702.187b's "as long as **you** discarded **this card** this
            # turn" - both halves, off the card's own discard record rather
            # than off `Game.cards_discarded_this_turn`, which counts a
            # player's discards and can say neither which card nor, for the
            # count alone, that this one was among them.
            now = _turn_number(game)
            if spell.discarded_by != caster:
                return (
                    f"{caster} did not discard {spell.name}, so it cannot be cast "
                    f"with {self.keyword} ({self.rule})"
                )
            if now is not None and spell.discarded_on_turn != now:
                return (
                    f"{spell.name} was not discarded this turn, so it cannot be cast "
                    f"with {self.keyword} ({self.rule})"
                )

        if self.prowl and game is not None and not game.prowl_condition_holds(caster, spell):
            return (
                f"no player was dealt combat damage this turn by a source {caster} "
                f"controlled that shared a creature type with {spell.name}, so it cannot "
                f"be cast for its {self.keyword} cost ({self.rule})"
            )
        if (
            self.returns_tapped_creature
            and not cost_paid
            and game is not None
            and not any(
                permanent.tapped and game.characteristics_of(permanent).is_creature
                for permanent in game.permanents_controlled_by(caster)
            )
        ):
            return (
                f"{caster} controls no tapped creature to return to its owner's hand, so "
                f"{spell.name} cannot be cast with {self.keyword} ({self.rule})"
            )
        if (
            self.surge
            and game is not None
            and not any(cast.id != spell.id for cast in game.spells_cast_this_turn.get(caster, []))
        ):
            return (
                f"{caster} has not cast another spell this turn, so {spell.name} cannot be "
                f"cast for its {self.keyword} cost ({self.rule})"
            )
        if self.spectacle and game is not None and not game.spectacle_condition_holds(caster):
            return (
                f"no opponent of {caster} has lost life this turn, so {spell.name} cannot "
                f"be cast for its {self.keyword} cost ({self.rule})"
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
        if self.timing is CastTiming.OWN_DECLARE_BLOCKERS and game is not None:
            refusal = _why_not_in_own_declare_blockers_step(game, caster, self)
            if refusal is not None:
                return refusal
        if self.timing is CastTiming.OWN and game is not None:
            refusal = why_cannot_cast_now(
                spell.model_copy(update={"zone": Zone.HAND}), caster, game
            )
            if refusal is not None:
                return refusal
        if (
            self.returns_unblocked_creature
            and not cost_paid
            and game is not None
            and not any(
                why_not_unblocked(game, permanent) is None
                for permanent in game.permanents_controlled_by(caster)
            )
        ):
            return (
                f"{caster} controls no unblocked creature to return to its owner's hand, "
                f"so {spell.name} cannot be cast with {self.keyword} ({self.rule}, "
                f"CR 509.1h)"
            )
        return None


def _describe_keyword_cost(option: KeywordCastOption) -> str:
    """What `option` charges, in words, for `_unclaimed_zone_permission_message`."""
    if option.cost is not None:
        return str(option.cost)
    return "its mana cost" if option.pays_mana_cost else "nothing"


def _turn_number(game: Any) -> int | None:
    turn = getattr(game, "turn", None)
    return None if turn is None else int(turn.turn_number)


#: CR 702.119b's "Emerge from [quality] [cost]", as `KeywordAbility.parameter`
#: carries it once the parser finds no bare cost after the keyword.
_EMERGE_FROM = re.compile(r"from (?P<quality>[a-z][a-z -]*?) (?P<cost>(?:\{[^}]+\})+)", re.I)


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

    if canonical == "emerge":
        # CR 702.119a: "'Emerge [cost]' means 'You may cast this spell by
        # paying [cost] and sacrificing a creature rather than paying its mana
        # cost' and 'If you chose to pay this spell's emerge cost, its total
        # cost is reduced by an amount of generic mana equal to the sacrificed
        # creature's mana value.'" CR 702.119b's "Emerge from [quality]
        # [cost]" sacrifices a [quality] permanent instead. The sacrifice is
        # one more component of the alternative cost (chosen at CR 601.2b per
        # CR 702.119c, paid at CR 601.2h); the reduction is applied once the
        # permanent is chosen (`Casting._use_keyword`).
        mana, quality = printed, "creature"
        if mana is None and ability.parameter:
            variant = _EMERGE_FROM.fullmatch(ability.parameter.strip())
            if variant is not None:
                mana, quality = variant.group("cost"), variant.group("quality").lower()
        cost = (
            total_cost_for_phrase(f"{mana}, Sacrifice {with_indefinite_article(quality)}")
            if mana
            else None
        )
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.119b" if quality != "creature" else "CR 702.119a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            emerge_quality=quality,
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

    if canonical == "escape":
        # CR 702.138a: "Escape represents a static ability that functions
        # while the card with escape is in a player's graveyard. 'Escape
        # [cost]' means 'You may cast this card from your graveyard by paying
        # [cost] rather than paying its mana cost.'" Structurally flashback
        # (CR 702.34a) with a different rule number - the graveyard half is
        # what makes this permission, not the discount - and unlike flashback
        # or mayhem, escape carries no "only as a sorcery" restriction of its
        # own: whatever timing the card's own type would normally allow
        # applies (`why_cannot_cast_now` reads that off the card as always).
        # `total_cost_for_phrase` already reads the "exile N **other** cards
        # from your graveyard" additional-cost half of the printed cost
        # (`machines/cost.py`'s `_QUALITY_CONNECTORS`), so nothing escape-
        # specific is needed here beyond the zone and the rule number.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.138a",
            zone=Zone.GRAVEYARD,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical == "harmonize":
        # CR 702.180a: "Harmonize represents three static abilities: one that
        # functions while the card is in a player's graveyard and two that
        # function while the spell with harmonize is on the stack." The
        # graveyard permission (this option) is structurally flashback's own
        # shape - an alternative cost cast from the graveyard, exiled instead
        # of put anywhere else (see `machines/replacement.py`'s check, widened
        # alongside flashback's own). The other two - the tap-a-creature
        # discount (CR 702.180b) and the exile itself (CR 702.180a's third
        # clause) - are `Casting.pay_harmonize` and the same replacement-effect
        # check, not this option.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.180a",
            zone=Zone.GRAVEYARD,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical == "mayhem":
        # CR 702.187a: "Mayhem is a static ability that functions while the card
        # with mayhem is in a player's graveyard." CR 702.187b: "'Mayhem
        # [cost]' means 'As long as you discarded this card this turn, you may
        # cast it from your graveyard by paying [cost] rather than paying its
        # mana cost.'"
        #
        # Structurally flashback (CR 702.34a) - the graveyard half is the
        # permission, and the cost replaces the mana cost - with the one clause
        # flashback does not have: "as long as you discarded this card this
        # turn". That is `discarded_this_turn` below, and it is a fact about a
        # *specific card*, not about how many cards a player has discarded -
        # `CardState.discarded_by`/`discarded_on_turn` is where the discard
        # itself records it (see `KeywordCastOption.discarded_this_turn`).
        #
        # CR 702.187c's costless form - "'Mayhem' without a cost means 'You may
        # play this card from your graveyard if you discarded it this turn'" -
        # is deliberately not folded in here: it says *play*, which reaches
        # lands and is a different permission from an alternative cost, and no
        # printing in this pool has it. A bare `Mayhem` line therefore reads as
        # not understood rather than as a free cast.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.187b",
            zone=Zone.GRAVEYARD,
            cost=cost,
            pays_mana_cost=False,
            discarded_this_turn=True,
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

    if canonical == "bestow":
        # CR 702.103a: "Bestow represents a static ability that functions in any
        # zone from which you could play the card it's on. 'Bestow [cost]'
        # means 'As you cast this spell, you may choose to cast it bestowed. If
        # you do, ... pay [cost] rather than its mana cost.'" So it is an
        # alternative cost (CR 118.9) that also changes what the spell *is*:
        # CR 702.103b, "as a spell cast bestowed is put onto the stack, it
        # becomes an Aura enchantment and gains enchant creature", which is
        # `CardState.bestowed` and not this option's business.
        #
        # The zone is the hand, the only zone "from which you could play the
        # card" for a creature card by default; a printing whose own text opens
        # another one says so itself (CR 604.6) and is read by
        # `_printed_zone_permissions` below, not here.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.103a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical == "impending":
        # CR 702.176a: "'Impending N-[cost]' means 'You may choose to pay
        # [cost] rather than pay this spell's mana cost,'" - the first of its
        # four abilities, "a static ability that functions while the spell with
        # impending is on the stack", and an alternative cost (CR 118.9) cast
        # like evoke's. The rule names no zone, so the zone is the one a card
        # is cast from by default, the hand - the same reading bestow's option
        # above makes. The other three abilities are the entering time counters
        # (`machines/replacement._impending_entering_counters`), the layer 4
        # "it's not a creature" (`machines/layers._impending_not_a_creature`)
        # and the end step trigger (`machines/keywords._impending_ability`).
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.176a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            understood=cost is not None,
        )

    if canonical == "prowl":
        # CR 702.76a: "'Prowl [cost]' means 'You may pay [cost] rather than
        # pay this spell's mana cost if a player was dealt combat damage this
        # turn by a source that, at the time it dealt that damage, was under
        # your control and had any of this spell's creature types.'" An
        # alternative cost (CR 118.9) with no zone of its own, so the hand -
        # the zone a card is cast from by default - the same reading evoke's
        # option makes. The condition is `why_not`'s, off `prowl`.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.76a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            prowl=True,
            understood=cost is not None,
        )

    if canonical == "sneak":
        # CR 702.190a: "'Sneak [cost]' means 'Any time you could cast an
        # instant during your declare blockers step, you may cast this spell
        # by paying [cost] and returning an unblocked creature you control to
        # its owner's hand rather than paying this spell's mana cost.'" An
        # alternative cost (CR 118.9) from the hand, the zone a card is cast
        # from by default, whose return half is the same
        # `ComponentKind.RETURN_TO_HAND` ninjutsu pays (CR 702.49a). Its
        # timing is its own window, for every card type alike. CR 702.190b's
        # tapped-and-attacking half is `Game`'s, on resolution.
        mana = total_cost_for_phrase(printed) if printed else None
        cost = (
            TotalCost(
                mana=mana.mana,
                components=[
                    *mana.components,
                    return_to_hand_cost(
                        required=1,
                        description="Return an unblocked creature you control to its owner's hand",
                    ),
                ],
            )
            if mana is not None
            else None
        )
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.190a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            timing=CastTiming.OWN_DECLARE_BLOCKERS,
            returns_unblocked_creature=True,
            understood=cost is not None,
        )

    if canonical == "spectacle":
        # CR 702.137a: "Spectacle is a static ability that functions on the
        # stack. 'Spectacle [cost]' means 'You may pay [cost] rather than pay
        # this spell's mana cost if an opponent lost life this turn.'" An
        # alternative cost (CR 118.9) with no zone of its own, so the hand -
        # the zone a card is cast from by default, the same reading prowl's
        # and evoke's options make. "Casting a spell for its spectacle cost
        # follows the rules for paying alternative costs in rules 601.2b and
        # 601.2f-h" (CR 702.137a), which is exactly what `spectacle=True`
        # routes through `why_not` to `Game.spectacle_condition_holds`.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.137a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            spectacle=True,
            understood=cost is not None,
        )

    if canonical == "surge":
        # CR 702.117a: "Surge is a static ability that functions while the
        # spell with surge is on the stack. 'Surge [cost]' means 'You may pay
        # [cost] rather than pay this spell's mana cost as you cast this spell
        # if you or one of your teammates has cast another spell this turn.'"
        # An alternative cost (CR 118.9) from the hand, the zone a card is
        # cast from by default - the same reading spectacle's option makes -
        # with its condition `why_not`'s, off `surge`.
        cost = total_cost_for_phrase(printed) if printed else None
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.117a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            surge=True,
            understood=cost is not None,
        )

    if canonical == "web-slinging":
        # CR 702.188a: "'Web-slinging [cost]' means 'You may cast this spell
        # by paying [cost] and returning a tapped creature you control to its
        # owner's hand rather than paying its mana cost.'" An alternative cost
        # (CR 118.9) from the hand, whose return half is sneak's and
        # ninjutsu's `ComponentKind.RETURN_TO_HAND` with a "tapped creature"
        # requirement instead of combat's unblocked attacker.
        from ..cost import CardRequirement

        mana = total_cost_for_phrase(printed) if printed else None
        cost = None
        if mana is not None:
            returning = return_to_hand_cost(
                required=1,
                description="Return a tapped creature you control to its owner's hand",
            )
            returning.requirement = CardRequirement(
                types=[Type.CREATURE], description="tapped creature"
            )
            cost = TotalCost(mana=mana.mana, components=[*mana.components, returning])
        return KeywordCastOption(
            keyword=ability.canonical,
            rule="CR 702.188a",
            zone=Zone.HAND,
            cost=cost,
            pays_mana_cost=False,
            returns_tapped_creature=True,
            understood=cost is not None,
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
#: for its own mana cost. The permission is CR 702.185a's own last sentence -
#: "Its owner may cast this card after the current turn has ended for as long
#: as it remains exiled" - while CR 702.185b only defines what a warped card is.
def _warp_from_exile(ability: KeywordAbility) -> KeywordCastOption:
    return KeywordCastOption(
        keyword=ability.canonical,
        rule="CR 702.185a",
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
    options.extend(_printed_zone_permissions(card, options))
    options.extend(_printed_self_zone_cast_with_additional_cost(card))

    aftermath = aftermath_cast_option(card)
    if aftermath is not None:
        # CR 702.127a: the aftermath half, from the graveyard (`machines/
        # aftermath.py`).
        options.append(aftermath)

    if adventure_face(card) is not None:
        # CR 715.3d: "Instead of putting a spell that was cast as an Adventure
        # into its owner's graveyard as it resolves, its controller exiles it.
        # For as long as that card remains exiled, that player may play it."
        # Played normally, so its own mana cost and its own timing rules apply.
        # "It can't be cast as an Adventure this way" - the creature face only.
        options.append(
            KeywordCastOption(
                keyword="Adventure",
                rule="CR 715.3d",
                zone=Zone.EXILE,
                pays_mana_cost=True,
                marker=ExileMarker.ADVENTURED,
                normal_face_only=True,
            )
        )
    return options


def marker_cast_options(spell: CardState) -> list[KeywordCastOption]:
    """The cast options a card has because of the *pile of exile it is in*
    (CR 406.4), rather than because of anything printed on it.

    Every option in `keyword_cast_options` is read off a printed CR 702 keyword
    line, so a permission handed out by a CR 701 keyword *action* - which
    prints nothing on the object it moves - can never come from there.
    Airbend is that shape.

    CR 701.65a: "Certain spells and abilities instruct a player to airbend one
    or more permanents and/or spells. To do so, that player exiles those
    objects. For each card exiled this way, for as long as it remains exiled,
    its owner may cast it for {2} rather than its mana cost."

    Three things follow, and each is a field below:

    - **{2} rather than its mana cost** is an alternative cost (CR 118.9), so
      `pays_mana_cost` is false and `cost` is the flat `{2}`, whatever the card
      itself costs.
    - **for as long as it remains exiled** is the marker, and nothing more.
      There is no "on a later turn" here the way plot (CR 702.170d) and
      foretell (CR 702.143a) have one, so no `later_turn` - an airbent card may
      be recast the moment its owner has priority.
    - **its owner** is `ExileAnnotation.owner`, which `why_not` already
      enforces. It matters more here than for any other marker: the player who
      airbent the object is usually not its owner, and the episode this is
      modelled from turns on exactly that.

    CR 701.65a says "for each **card** exiled this way", which is why a token
    airbent this way gets nothing: it is not a card, and CR 111.7/CR 704.5d
    have it cease to exist before anybody could ask.
    """
    annotation = spell.exile_annotation
    if annotation is None or annotation.marker is not ExileMarker.AIRBENT:
        return []
    return [
        KeywordCastOption(
            keyword="Airbend",
            rule="CR 701.65a",
            zone=Zone.EXILE,
            cost=TotalCost.of(ManaCost.parse("{2}")),
            pays_mana_cost=False,
            marker=ExileMarker.AIRBENT,
        )
    ]


#: CR 702.33b: "The phrase 'Kicker [cost 1] and/or [cost 2]' means the same
#: thing as 'Kicker [cost 1], kicker [cost 2].'"
_KICKER_AND_OR = re.compile(r"\s+and/or\s+", re.IGNORECASE)


def kicker_costs(card: Card) -> list[str]:
    """Every kicker cost `card` prints, each as printed, in printed order -
    CR 702.33b's "and/or" line is two of them, and CR 702.33f names them
    "[A]" and "[B]" in this order. Multikicker has its one cost."""
    costs: list[str] = []
    for ability in keyword_abilities(card):
        if ability.canonical.lower() not in ("kicker", "multikicker"):
            continue
        printed = ability.cost or ability.parameter or ""
        costs.extend(part.strip() for part in _KICKER_AND_OR.split(printed) if part.strip())
    return costs


#: Each keyword of `ADDITIONAL_COST_KEYWORDS` that prints its own cost on its
#: own line, with the rule that defines it and whether CR 601.2b's
#: announcement may name it more than once. Blight is absent because CR
#: 701.68a is printed inside the card's "As an additional cost ..." sentence
#: rather than as a keyword line (`_BLIGHT_PHRASE`), and so is read below off
#: `additional_cost_phrases` with every other printed optional cost.
#:
#: Repeatable is the keyword's own rule, never a guess: CR 702.33a's kicker
#: is "You may pay an additional [cost] as you cast this spell", CR 702.33c's
#: multikicker and CR 702.56a's replicate both add "any number of times".
_OPTIONAL_COST_KEYWORDS: tuple[tuple[str, str, bool], ...] = (
    ("kicker", "CR 702.33a", False),
    ("multikicker", "CR 702.33c", True),
    ("replicate", "CR 702.56a", True),
    ("offspring", "CR 702.175a", False),
    ("gift", "CR 702.174a", False),
)


class OptionalAdditionalCost(EngineModel):
    """One optional additional cost a spell's controller may announce as they
    cast it (CR 601.2b, CR 118.8b).

    CR 601.2b: "If the spell has alternative or additional costs that will be
    paid as it's being cast such as buyback or kicker costs ..., the player
    announces their intentions to pay any or all of those costs". CR 118.8b:
    "Some additional costs are optional."

    This is the **mechanic**, not a keyword: kicker, multikicker, replicate,
    offspring and gift each print theirs as a keyword line, and CR 701.68a's
    blight and March of Otherworldly Light's pitch each print theirs inside
    the card's own "As an additional cost to cast this spell, you may ..."
    sentence. Both readings land here, so a caller enumerating what a seat
    may announce asks one question rather than one per keyword.

    Carried across to `models.action.AdditionalCostOption` by
    `legal_actions`, the same way `SpliceCandidate` is carried to
    `SpliceOption` - strings only on the far side, never a live `Card`.
    """

    model_config = ConfigDict(frozen=True)

    keyword: str | None
    """The canonical keyword, lower-case, or `None` for a cost printed as a
    sentence rather than as a keyword line."""
    cost: str
    """The cost exactly as printed - `{1}{C}`, `a Food`, `you may blight 1`."""
    rule: str
    repeatable: bool = False
    """CR 702.33c / CR 702.56a's "any number of times"."""
    understood: bool = True
    """False when the cost is printed and optional but nothing here can
    charge it, so a seat is told the option exists and told this engine
    cannot take it, rather than being quietly shown nothing (CR 118.8b).
    Buyback and bargain are not read as additional costs at all and so never
    reach this; what does are the "you may ..." sentences
    `additional_cost_phrases` returns that `Casting` has no `pay_*` for."""


#: The name a seat announces the life half of a "pay N life or pay {M}"
#: additional cost by (CR 601.2b). Not a keyword ability - the sentence prints
#: none - but the handle `OptionalAdditionalCost.keyword` carries, so the
#: option is never a keyword-less entry a seat has no way to name back.
PAY_LIFE_KEYWORD = "pay life"


def casualty_cost_phrase(number: int) -> str:
    """CR 702.153a's cost, spelled out: "sacrifice a creature with power N or
    greater"."""
    return f"Sacrifice a creature with power {number} or greater"


def casualty_cost_option(number: int) -> OptionalAdditionalCost:
    """One casualty instance as an optional additional cost (CR 702.153a,
    CR 118.8b) - `Casting.pay_casualty` pays it."""
    return OptionalAdditionalCost(
        keyword="casualty", cost=casualty_cost_phrase(number), rule="CR 702.153a"
    )


def conspire_cost_option() -> OptionalAdditionalCost:
    """One conspire instance as an optional additional cost (CR 702.78a,
    CR 118.8b) - `Casting.pay_conspire` pays it."""
    return OptionalAdditionalCost(keyword="conspire", cost=CONSPIRE_COST, rule="CR 702.78a")


def optional_additional_costs(card: Card) -> list[OptionalAdditionalCost]:
    """Every optional additional cost `card` prints for CR 601.2b's
    announcement, keyword lines and "you may ..." sentences alike.

    The single place that question is answered: `legal_actions` reads it to
    tell a seat the option exists at all, and `Game._announce_optional_costs`
    reads it to offer the same options to a cast the engine is making on a
    player's behalf (CR 608.2g). Two enumerations would be free to drift, and
    the reported defect was exactly one surface knowing about kicker while
    the other did not.
    """
    found: list[OptionalAdditionalCost] = []
    for keyword, rule, repeatable in _OPTIONAL_COST_KEYWORDS:
        ability = _keyword(card, keyword)
        if ability is None:
            continue
        if keyword == "kicker":
            # CR 702.33b: one option per kicker cost, each announced on its own.
            found.extend(
                OptionalAdditionalCost(keyword=keyword, cost=cost, rule=rule)
                for cost in kicker_costs(card)
            )
            continue
        # CR 702.174a's gift has no resource behind it - "you may choose an
        # opponent" - so what it prints after the keyword is the promise
        # ("a Food"), read off `parameter`, not a cost off `cost`.
        printed = ability.cost or ability.parameter
        if not printed:
            continue
        found.append(
            OptionalAdditionalCost(keyword=keyword, cost=printed, rule=rule, repeatable=repeatable)
        )
    if _keyword(card, "bargain") is not None:
        found.append(
            OptionalAdditionalCost(keyword="bargain", cost=BARGAIN_COST, rule="CR 702.166a")
        )
    found.extend(casualty_cost_option(number) for number in printed_casualty_numbers(card))
    found.extend(conspire_cost_option() for _ in range(printed_conspire_count(card)))
    for phrase in additional_cost_phrases(card):
        if _OPTIONAL_ADDITIONAL_COST.match(phrase) is None:
            continue
        blight = _BLIGHT_PHRASE.match(phrase)
        if blight is not None:
            found.append(OptionalAdditionalCost(keyword="blight", cost=phrase, rule="CR 701.68a"))
        elif _OPTIONAL_COLLECT_EVIDENCE.match(phrase) is not None:
            found.append(
                OptionalAdditionalCost(keyword="collect evidence", cost=phrase, rule="CR 701.59a")
            )
        elif _OPTIONAL_REVEAL.match(phrase) is not None:
            found.append(OptionalAdditionalCost(keyword="reveal", cost=phrase, rule="CR 701.20a"))
        elif _OPTIONAL_BEHOLD_CHOSEN_TYPE.match(phrase) is not None:
            # Charged by `Casting.behold_chosen_type_for_cost` (the type named
            # and the creatures beheld, CR 701.4a).
            found.append(OptionalAdditionalCost(keyword="behold", cost=phrase, rule="CR 701.4a"))
        elif _OPTIONAL_BEHOLD.match(phrase) is not None:
            # Charged by `Casting.behold_for_cost` - a plain, fixed quality
            # (Dispelling Exhale's "a Dragon"), unlike the chosen-type shape
            # just above.
            found.append(OptionalAdditionalCost(keyword="behold", cost=phrase, rule="CR 701.4a"))
        elif _OPTIONAL_SACRIFICE_ANY_NUMBER.match(phrase) is not None:
            # Charged by `Casting.sacrifice_for_cost_reduction` (CR 118.7a,
            # CR 118.8b).
            found.append(
                OptionalAdditionalCost(
                    keyword="sacrifice any number", cost=phrase, rule="CR 118.8b"
                )
            )
        elif _OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND.match(phrase) is not None:
            # Charged by `Casting.exile_for_cost_reduction` (CR 118.7a,
            # CR 118.8b).
            found.append(
                OptionalAdditionalCost(keyword="exile any number", cost=phrase, rule="CR 118.8b")
            )
        else:
            found.append(
                OptionalAdditionalCost(
                    keyword=None, cost=phrase, rule="CR 118.8b", understood=False
                )
            )
    printed = additional_cost_phrases(card)
    for index, _ in life_or_mana_additional_costs(card):
        # Not optional as a whole - one half or the other is paid - but which
        # half is CR 601.2b's announcement, and a life half has no object to
        # nominate, so a seat is told the choice exists here, under
        # `PAY_LIFE_KEYWORD` so it has a name to send back, and makes it with
        # `Game.cast(pay_life_for_additional_cost=True)`.
        found.append(
            OptionalAdditionalCost(keyword=PAY_LIFE_KEYWORD, cost=printed[index], rule="CR 601.2b")
        )
    return found


#: Mindbreak Trap's shape of CR 118.9 offer: the same "rather than pay this
#: spell's mana cost" sentence, with a condition on the game's own history
#: printed ahead of it. `machines/cost.py`'s `_ALTERNATIVE` is anchored at
#: "You may" and its `_ALTERNATIVE_IF_NOT_YOUR_TURN` reads the one *timing*
#: condition (Force of Negation), so neither sees this one - the condition
#: here is a question about what has already happened this turn, which only a
#: machine holding the game can answer, which is why it is read here rather
#: than there.
_CONDITIONAL_ALTERNATIVE = re.compile(
    r"^If (?P<condition>[^,.]+), you may (?P<what>[^.]+?) rather than pay "
    r"this spell's mana cost\.",
    re.MULTILINE,
)


#: A cost phrase that is nothing but mana, with or without the verb in front of
#: it: Mindbreak Trap prints "pay {0}", and CR 118.5 makes that a real cost
#: ("Some costs are represented by {0} ... Even though such a cost requires no
#: resources, it's not automatically paid").
_PAY_ONLY_MANA = re.compile(r"^(?:pay\s+)?(?P<mana>(?:\{[^{}]+\}\s*)+)$", re.IGNORECASE)


class ConditionalAlternativeCostOffer(EngineModel):
    """One CR 118.9 offer whose sentence prints a condition ahead of it."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    """What would be paid, in the card's own words."""
    condition: str
    """The clause between "If" and the comma, as printed."""


def conditional_alternative_cost_offers(text: str) -> list[ConditionalAlternativeCostOffer]:
    """Every conditional CR 118.9 offer in this text (CR 604.6).

    Force of Negation's "If it's not your turn, ..." is deliberately skipped:
    `machines/cost.py::alternative_cost_offers` already reads that one, and
    reporting it twice would offer the same cost as two separate options,
    which CR 118.9a's "only one alternative cost" makes a lie.
    """
    offers: list[ConditionalAlternativeCostOffer] = []
    for match in _CONDITIONAL_ALTERNATIVE.finditer(text or ""):
        condition = match.group("condition").strip()
        if condition.lower() == "it's not your turn":
            continue
        offers.append(
            ConditionalAlternativeCostOffer(phrase=match.group("what").strip(), condition=condition)
        )
    return offers


def _printed_alternative_total_cost(phrase: str, payer: str | None) -> TotalCost | None:
    """The `TotalCost` a printed CR 118.9 phrase asks for, or None if unread.

    `machines/cost.py::total_cost_for_phrase` reads the component shapes
    ("exile a blue card from your hand"), but its mana branch wants the phrase
    to be *only* mana symbols, so the verb Mindbreak Trap prints in front of
    its own - "pay {0}" - is not one it can read. The verb is stripped here
    and the rest handed to `ManaCost.parse`; everything else is still
    `total_cost_for_phrase`'s job, including its None for a phrase nobody
    parsed.
    """
    mana_only = _PAY_ONLY_MANA.match(phrase.strip().rstrip("."))
    if mana_only is not None:
        mana = ManaCost.try_parse(mana_only.group("mana").strip())
        if mana is not None:
            return TotalCost.of(mana)
    return total_cost_for_phrase(phrase, payer=payer)


class AlternativeCostSource(StrEnum):
    """Where a CR 118.9 alternative cost came from.

    CR 118.9's own sentence names two origins - "a cost listed in a spell's
    text, or applied to it from another effect" - and this engine already had
    three separate announcement paths for them, so the enum is what lets one
    listing describe all of them without flattening the difference.
    """

    PRINTED = "printed"
    """The spell's own text, functioning from the zone it is cast from
    (CR 604.6): Force of Will's and Force of Negation's pitch sentence."""
    KEYWORD = "keyword"
    """A keyword ability that replaces the mana cost - evoke, dash - reported
    by `keyword_cast_options` with `pays_mana_cost` false."""
    PERMISSION = "permission"
    """A `PlayPermission` a resolving effect handed out "without paying its
    mana cost" (CR 601.3): cascade's hit, Ugin's exiled card."""
    STATIC = "static"
    """Another permanent's static ability applying the cost (CR 604.2):
    Omniscience."""


class AlternativeCostOption(EngineModel):
    """One CR 118.9 alternative cost a spell could be announced under, and
    whether it can be announced right now.

    This exists so a seat driving the engine can *find* an alternative cost
    rather than having to know in advance that a particular card prints one.
    Everything unavailable is still listed, carrying `unavailable` - a seat
    that is shown only the legal options cannot tell "this card has no pitch
    cost" from "it has one and it is not your turn" (CR 118.9b makes the
    difference: an option that exists is one the player may decline, and an
    option that does not exist is not a choice at all).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: int
    """Position in `Casting.alternative_costs`, and what
    `use_alternative_cost` takes."""
    source: AlternativeCostSource
    rule: str
    """The CR number this option is read from."""
    source_name: str = ""
    """The card offering it - the spell itself for `PRINTED`, the permanent
    for `STATIC`, the granting card for `PERMISSION`."""
    keyword: str | None = None
    """The keyword, for `KEYWORD` options only."""
    description: str
    """What would be paid, in the card's own words. "nothing" is CR 107.3b's
    "without paying its mana cost", which is not a cost of {0} (CR 118.5)."""
    cost: TotalCost | None = None
    """The payable cost, or None when nothing at all is paid."""
    requires: int = 0
    """How many objects `use_alternative_cost(choosing=...)` must supply."""
    unavailable: str | None = None
    """Why it cannot be announced right now, or None if it can."""
    once_per_turn_key: str | None = None
    """For a once-each-turn `STATIC` grant, the granting permanent's key -
    recorded as used when the spell becomes cast (CR 601.2i)."""

    @property
    def available(self) -> bool:
        return self.unavailable is None


#: CR 118.8b: "Some additional costs are optional." An optional one is printed
#: as a "you may ..." inside the additional-cost sentence - March of
#: Otherworldly Light's "you may exile any number of white cards from your
#: hand", Requiting Hex's "you may blight 1" - and declining it is a legal
#: announcement (CR 601.2b), so it is skipped rather than charged or refused.
_OPTIONAL_ADDITIONAL_COST = re.compile(r"^you may\b", re.IGNORECASE)

#: CR 601.2b's general "[cost] or pay [mana]" additional-cost shape - Silence
#: the Echo's "sacrifice a creature or planeswalker or pay {3}", Bayou
#: Groff's "sacrifice a creature or pay {3}", Countersculpt's "behold a Jace
#: or pay {1}". Blight's own copy of the same tail (`_BLIGHT_PHRASE`) is
#: tried first and this is only reached for a phrase that is not blight, so
#: the two never disagree about a blight sentence.
_OR_PAY_TAIL = re.compile(r"^(?P<primary>.+?) or pay (?P<mana>(?:\{[^{}]+\})+)$", re.IGNORECASE)
#: The same choice with the mana written first - Deadly Precision's "pay {4} or
#: sacrifice an artifact or creature".
_PAY_FIRST_OR = re.compile(r"^pay (?P<mana>(?:\{[^{}]+\})+) or (?P<primary>.+)$", re.IGNORECASE)
#: The same choice with a life payment as the fallback instead of mana -
#: Bitter Triumph's "discard a card or pay 3 life".
_OR_PAY_LIFE_TAIL = re.compile(r"^(?P<primary>.+?),? or (?P<mana>pay \d+ life)$", re.IGNORECASE)


def or_additional_cost_halves(phrase: str) -> tuple[str, str] | None:
    """CR 601.2b's "[cost] or [cost]" additional-cost sentence as its two halves
    `(primary, default)`, or `None` when it is not one.

    `default` is the half paid when the caster nominates nothing for the
    other: the mana of "[cost] or pay [mana]" and "pay [mana] or [cost]", or
    the life of "[cost] or pay N life". `primary` is the other half, the one
    `Casting._additional_cost_primary_alternatives` infers from nominated
    objects (or, for a life payment, from an explicit announcement).
    """
    for pattern in (_OR_PAY_TAIL, _PAY_FIRST_OR, _OR_PAY_LIFE_TAIL):
        match = pattern.match(phrase)
        if match is not None:
            return match.group("primary"), match.group("mana")
    return None


def _primary_alternatives_of(primary: str) -> list[str]:
    """The comma-separated alternatives inside an or-cost's `primary` half -
    Dusk Mangler's "sacrifice a creature, discard a card, or pay 4 life" has
    the two, in printed order. A half with no comma is the one alternative
    (a bare " or " is part of a single cost's own noun, "an artifact or
    creature")."""
    return [part.strip() for part in primary.split(",") if part.strip()]


def or_additional_cost_alternatives(phrase: str) -> list[str] | None:
    """Every way to pay a CR 601.2b "[cost] or [cost]" additional-cost
    sentence, in printed order with the default (mana or life) half last, or
    `None` when `phrase` is not one."""
    halves = or_additional_cost_halves(phrase)
    if halves is None:
        return None
    return [*_primary_alternatives_of(halves[0]), halves[1]]


def life_or_mana_additional_costs(card: Card) -> list[tuple[int, CostComponent]]:
    """CR 601.2b's "pay N life or pay {M}" additional-cost sentences
    (Redirect Lightning's "pay 5 life or pay {2}") - each one's position among
    `additional_cost_phrases` (the index `Casting.paying_life_for_additional_
    cost` takes) and its life half as an unpaid `CostComponent`.

    Read with the same `_OR_PAY_TAIL` every other "[cost] or pay [mana]"
    sentence goes through, keeping only those whose non-mana half is a life
    payment: that half has no object to nominate, so it is the one the caster
    has to *announce* rather than imply by choosing objects.
    """
    found: list[tuple[int, CostComponent]] = []
    for index, printed in enumerate(additional_cost_phrases(card)):
        if _BLIGHT_PHRASE.match(printed) is not None:
            continue
        halves = or_additional_cost_halves(printed)
        if halves is None or not halves[1].startswith("{"):
            continue
        component = cost_component_for_phrase(halves[0])
        if component is not None and component.kind is ComponentKind.PAY_LIFE:
            found.append((index, component))
    return found


def mandatory_additional_costs(
    spell: CardState,
    caster: str,
    x_value: int | None,
    *,
    blighted: bool = False,
    primary_alternatives: Mapping[int, int] | None = None,
    face: str | None = None,
) -> list[TotalCost]:
    """The spell's own printed "As an additional cost to cast this spell, ..."
    sentences as fresh, unfilled `TotalCost`s (CR 118.8a, 601.2f), X
    substituted first (CR 107.3a) and every optional one left out (CR 118.8b).

    The one reading both `Casting._printed_additional_costs` (which then fills
    the chosen objects in) and `legal_actions` (which counts whether they
    exist) use, so the two cannot disagree about what the cost is. A
    mandatory sentence that cannot be read raises, because CR 118.3 does not
    let the spell be cast without paying it.

    `primary_alternatives` maps which of CR 601.2b's "[cost] or pay [mana]"
    sentences (by position among `additional_cost_phrases`) are being paid
    with their non-default half to which of that half's comma-separated
    alternatives (usually the one, 0); every other one defaults to the mana half, the
    same default blight's own copy of this shape already uses when
    `blighted` is left false - a caller judging affordability with no
    objects chosen yet (`legal_actions`) always gets a single, cheap-to-
    compute answer rather than a set of alternatives to choose between.

    `face` is CR 715.3a's/CR 709.3a's chosen face (Adventure, split): a
    spell cast as one carries its additional cost, if any, on that face's own
    text rather than on `spell.card.oracle_text`, which a split/Adventure/
    modal-DFC printing leaves null - My Precious // Allure of Power's "As an
    additional cost to cast this spell, sacrifice a creature." is Allure of
    Power's own sentence, read only once that face is the one being cast.
    """
    built: list[TotalCost] = []
    for index, printed in enumerate(additional_cost_phrases(spell.card, face=face)):
        phrase = substitute_x(printed, x_value)
        if _OPTIONAL_ADDITIONAL_COST.match(phrase):
            continue
        blight = _BLIGHT_PHRASE.match(printed)
        if blight is not None and blighted:
            # `Casting.pay_blight` already added the blight, with its creature.
            continue
        if blight is not None and blight.group("instead"):
            # CR 601.2b: "blight 2 or pay {1}" not blighted is the mana.
            phrase = blight.group("instead")
        elif blight is None:
            halves = or_additional_cost_halves(phrase)
            if halves is not None:
                if index in (primary_alternatives or {}):
                    parts = _primary_alternatives_of(halves[0])
                    phrase = parts[(primary_alternatives or {})[index]]
                else:
                    phrase = halves[1]
        cost = total_cost_for_phrase(phrase, caster)
        if cost is None:
            raise ValueError(
                f"{spell.name}'s additional cost {phrase!r} could not be read, "
                f"so it cannot be paid (CR 118.3, 601.2f)"
            )
        for component in cost.components:
            if component.kind is ComponentKind.BEHOLD and component.exile_after:
                # CR 607.2q: the permanent this spell becomes keeps `spell`'s
                # own id across the stack-to-battlefield zone change
                # (`CardState.move_to`'s docstring), so linking against it
                # now already names the object whichever printed "return the
                # exiled card ..." ability on the resolved permanent will
                # look up later - the same link `objects_as_costs.delve`
                # fixes onto a delving spell's own cast cost.
                component.link_to_permanent_id = spell.id
        built.append(cost)
    return built


#: CR 207.2's reminder text, dropped from a spliced card's rules text the same
#: way `machines/abilities.py` drops it from an ability line.
_SPLICE_REMINDER_RE = re.compile(r"\([^()]*\)")

#: "Splice onto instant or sorcery {2}{U}" - the quality and the cost, as
#: CR 702.47a templates them: "Splice onto [quality] [cost]".
_SPLICE_PARAMETER_RE = re.compile(
    r"^onto (?P<quality>.+?)\s+(?P<cost>(?:\{[^}]+\})+)$", re.IGNORECASE
)


def _splice_parameter(ability: KeywordAbility) -> tuple[str | None, str | None]:
    """CR 702.47a's `[quality]` and `[cost]`, off the printed parameter.

    Returns `(None, None)` for a parameter this cannot read, which
    `Casting._splice` turns into a refusal rather than a free splice.
    """
    parameter = (ability.parameter or ability.cost or "").strip()
    match = _SPLICE_PARAMETER_RE.fullmatch(parameter)
    if match is None or ManaCost.try_parse(match.group("cost")) is None:
        return None, None
    return match.group("quality").strip().lower(), match.group("cost")


def _matches_splice_quality(spell: CardState, quality: str) -> bool:
    """Whether `spell` is the "[quality] spell" a splice ability names.

    Every printed splice ability in this pool says "onto Arcane" or "onto
    instant or sorcery", so the quality is read as card types and subtypes -
    each word of the quality, minus the "or"s, matched against the spell's own
    types (CR 205.2a) and subtypes (CR 205.3). All of them must match nothing;
    any one of them matching is enough, because the quality is a disjunction.
    """
    words = [word for word in quality.replace(",", " ").split() if word.lower() != "or"]
    if not words:
        return False
    have = {card_type.value.lower() for card_type in spell.types}
    have |= {subtype.lower() for subtype in spell.subtypes}
    return any(word.lower() in have for word in words)


def _spliced_rules_text(card: Card) -> str:
    """The rules text a spliced card adds to a spell (CR 702.47c, CR 612.10).

    The card's own paragraphs, minus its splice line and minus CR 207.2's
    reminder text. The splice ability itself is a static ability that
    functions only in a player's hand (CR 702.47a), so it does nothing
    whatever on the spell that carries it; leaving it in would only hand
    `machines/effects.py` a clause it cannot read, which fails the *whole*
    spell closed - the opposite of what CR 702.47c asks for.
    """
    lines = []
    for line in (card.oracle_text or "").split("\n"):
        stripped = _SPLICE_REMINDER_RE.sub("", line).strip()
        if not stripped or stripped.lower().startswith("splice onto"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _keyword(card: Card, keyword: str) -> KeywordAbility | None:
    for ability in keyword_abilities(card):
        if ability.canonical.lower() == keyword.lower():
            return ability
    return None


class SpliceCandidate(EngineModel):
    """One card in a hand that could be revealed to splice onto `spell`
    right now (CR 702.47a) - `splice_candidates`'s own return shape, read
    by `legal_actions` to build `Action.splice_options` without ever
    opening a `Casting` of its own (`legal_actions`'s module docstring: no
    in-flight announcement state lives here). `card` is a live `CardState`
    on purpose, the same as `KeywordCastOption`/`GrantedCastOption` above -
    this type never crosses a JSON boundary; `legal_actions` reads `card.id`
    into the id-only `models.action.SpliceOption` before an `Action` is
    ever built.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    card: CardState
    cost: TotalCost
    rule: str = "CR 702.47a"


def splice_candidates(game: Any, spell: CardState, player: str) -> list[SpliceCandidate]:
    """CR 702.47a: every card in `player`'s hand whose splice ability could
    be revealed onto `spell` right now, before any is actually chosen.

    Mirrors the refusals `CastingStep._splice` enforces once a card is
    named, minus the ones that only make sense for an in-flight `Casting`
    that has already chosen some (CR 702.47b's "already spliced onto this
    spell" is about a *second* reveal of the same card on the *same* cast,
    which cannot have happened yet here) - `spell` can never splice onto
    itself, since revealing it from hand and casting it are the same event
    happening to the same object, not two.
    """
    candidates: list[SpliceCandidate] = []
    for card in game.player(player).hand:
        if card.id == spell.id:
            continue
        ability = _keyword(card.card, "Splice")
        if ability is None:
            continue
        quality, cost = _splice_parameter(ability)
        if quality is None or cost is None:
            continue
        if not _matches_splice_quality(spell, quality):
            continue
        text = _spliced_rules_text(card.card)
        if not text:
            continue
        profile = profile_for_text(text)
        if profile.understood and profile.requirements:
            # CR 702.47b: refused fail-closed, the identical read `Casting.
            # _splice` gives this same sentence.
            continue
        candidates.append(SpliceCandidate(card=card, cost=TotalCost.of(cost)))
    return candidates


#: One whole "As an additional cost to cast this spell, <cost>." line.
_ADDITIONAL_COST_LINE = re.compile(
    r"^as an additional cost to cast this spell, (?P<what>[^.]+)\.?$", re.IGNORECASE
)


def reads_mandatory_additional_cost_line(text: str) -> bool:
    """Whether one printed line is a mandatory CR 118.8a additional cost
    `mandatory_additional_costs` reads (`total_cost_for_phrase`) and so
    charges on every cast - `support.py`'s credit for it on a permanent
    card. An optional one, blight, or a "[cost] or pay [mana]" choice is
    left to the readers that already answer for those."""
    match = _ADDITIONAL_COST_LINE.match(text.strip())
    if match is None:
        return False
    phrase = match.group("what")
    if (
        _OPTIONAL_ADDITIONAL_COST.match(phrase)
        or _BLIGHT_PHRASE.match(phrase)
        or or_additional_cost_halves(phrase) is not None
    ):
        return False
    return total_cost_for_phrase(phrase) is not None


def reads_or_pay_additional_cost_line(text: str) -> bool:
    """Whether one printed line is a "[cost] or pay [mana]" (or "pay [mana] or
    [cost]", or "[cost] or pay N life") additional cost whose two halves
    `mandatory_additional_costs` can both charge (the default half unless the
    caster picks the other) - `support.py`'s
    credit for it on a permanent card (Bayou Groff, Titania, Rugged
    Rumbler)."""
    match = _ADDITIONAL_COST_LINE.match(text.strip())
    if match is None:
        return False
    phrase = match.group("what")
    if _OPTIONAL_ADDITIONAL_COST.match(phrase) or _BLIGHT_PHRASE.match(phrase):
        return False
    halves = or_additional_cost_halves(phrase)
    return (
        halves is not None
        and total_cost_for_phrase(halves[0]) is not None
        and total_cost_for_phrase(halves[1]) is not None
    )


def reads_printed_alternative_cost_line(text: str) -> bool:
    """Whether one printed line is wholly an unconditional CR 118.9 "You may
    <cost> rather than pay this spell's mana cost." whose cost
    `Casting.alternative_costs` can read (`_printed_alternative_total_cost`)
    and so offers on a cast - `support.py`'s credit for it on a permanent
    card (Salvage Titan)."""
    phrase = alternative_cost_phrase_of_line(text)
    return phrase is not None and _printed_alternative_total_cost(phrase, payer=None) is not None


#: "As an additional cost to cast this spell, you may sacrifice any number of
#: <quality>. This spell costs <amount> less to cast for each <noun>
#: sacrificed this way." - one printed line, two sentences.
_OPTIONAL_SACRIFICE_REDUCTION_LINE = re.compile(
    r"^as an additional cost to cast this spell, (?P<what>[^.]+)\.\s+(?P<reduction>[^.]+\.)$",
    re.IGNORECASE,
)


def reads_optional_sacrifice_reduction_line(text: str) -> bool:
    """Whether one printed line is wholly a CR 118.8b optional "you may
    sacrifice any number of <quality>" additional cost with its linked
    per-object reduction that `Casting.sacrifice_for_cost_reduction` pays
    and applies - `support.py`'s credit for it on a permanent card
    (Rottenmouth Viper). CR 118.7a: the reduction applied there is generic
    only, so a coloured amount is left unread."""
    match = _OPTIONAL_SACRIFICE_REDUCTION_LINE.match(text.strip())
    if match is None:
        return False
    sacrifice = _OPTIONAL_SACRIFICE_ANY_NUMBER.match(match.group("what"))
    if sacrifice is None or cost_component_for_phrase(sacrifice.group("cost"), None) is None:
        return False
    amount = per_object_sacrifice_reduction_of_sentence(match.group("reduction"))
    return amount is not None and amount == ManaCost(generic=amount.generic)


def reads_optional_exile_reduction_line(text: str) -> bool:
    """`reads_optional_sacrifice_reduction_line`'s exile twin: whether one
    printed line is wholly a CR 118.8b optional "you may exile any number of
    <quality> cards from your hand" additional cost with its linked
    per-card generic reduction that `Casting.exile_for_cost_reduction` pays
    and applies - March of Wretched Sorrow, March of Otherworldly Light."""
    match = _OPTIONAL_SACRIFICE_REDUCTION_LINE.match(text.strip())
    if match is None:
        return False
    exile = _OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND.match(match.group("what"))
    if exile is None or cost_component_for_phrase(exile.group("cost"), None) is None:
        return False
    amount = per_object_exile_reduction_of_sentence(match.group("reduction"))
    return amount is not None and amount == ManaCost(generic=amount.generic)


from ..aftermath import aftermath_cast_option  # noqa: E402
from ._common import (  # noqa: E402
    _BLIGHT_PHRASE,
    _OPTIONAL_BEHOLD,
    _OPTIONAL_BEHOLD_CHOSEN_TYPE,
    _OPTIONAL_COLLECT_EVIDENCE,
    _OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND,
    _OPTIONAL_REVEAL,
    _OPTIONAL_SACRIFICE_ANY_NUMBER,
    BARGAIN_COST,
    CONSPIRE_COST,
)
from .casting import _why_not_in_own_declare_blockers_step, why_cannot_cast_now  # noqa: E402
from .permissions import (  # noqa: E402
    _printed_self_zone_cast_with_additional_cost,
    _printed_zone_permissions,
    adventure_face,
)
