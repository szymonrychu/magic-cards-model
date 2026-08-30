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

from pydantic import BaseModel, ConfigDict, Field

from ..models.card import Card, Type
from ..models.card_state import CardState, ExileAnnotation, ExileMarker, TargetRef
from ..models.mana import ManaCost
from ..models.zone import Zone
from .abilities import KeywordAbility, TriggerEvent, keyword_abilities
from .cost import CostPayment, CostStep, TotalCost, apply_modifications, total_cost_for_phrase
from .keywords import (
    FACE_DOWN_CAST_COST,
    enchant_restrictions,
    face_down_characteristics,
    why_cannot_enchant,
)
from .modes import ModalProfile, Mode, modal_profile
from .targeting import (
    TargetingProfile,
    profile_for_modes,
    profile_for_modes_with_owners,
    targeting_profile,
)
from .triggers import GameEvent


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


def why_cannot_cast_from(spell: CardState, caster: str, zone: Zone, game: Any = None) -> str | None:
    """CR 601.3: why this card cannot be cast from where it is, or None.

    A card in hand needs no permission - that is where the rules cast from by
    default (CR 302.1, 601.3). Anywhere else, some keyword has to allow it, and
    the option's own conditions have to hold.
    """
    if zone is Zone.HAND:
        return None
    options = castable_from(spell.card, zone)
    if not options:
        return f"nothing allows {caster} to cast {spell.name} from the {zone.value} (CR 601.3)"
    reasons = [option.why_not(spell, caster, game) for option in options]
    if any(reason is None for reason in reasons):
        return None
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
    """
    if game is None:
        return None
    if Type.INSTANT in spell.card.types:
        return None  # CR 304.1
    if has_flash(spell.card):
        return None  # CR 702.8a
    if game.can_cast_sorcery(caster):
        return None
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
        """
        if self.modal is None or not self.chosen_mode_numbers:
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
        if not any(keyword.lower() == "hexproof" for keyword in target.card.keywords):
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

        self.payment = CostPayment.for_total(
            self.total_cost.assign_payer(self.caster), game=self.game, payer=self.caster
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

    def cast(self) -> CardState:
        """Finish casting: the cost is paid and the spell is on the stack."""
        if self.payment is None or self.payment.step is not CostStep.PAID:
            raise ValueError("cannot finish casting before the cost is paid")
        self._refuse_unless_modes_satisfied()
        self._refuse_if_x_changed_since_targets()

        self._advance_to(CastingStep.CAST)
        self._turn_face_down_if_cast_that_way()
        self.spell.move_to(Zone.STACK)
        # The spell carries its targets with it, so resolution knows what it hits.
        self.spell.targets = list(self.targets)
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

    Two of them are modelled: plot (CR 116.2k, CR 702.170b) and foretell
    (CR 116.2h, CR 702.143b). Both pay a cost, move a card from hand to exile,
    and leave it in a named pile that a later `Casting` reads.

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
        self.taken = True
        return self.card

    def cancel(self) -> None:
        """Rewind the cost, leaving the card where it was (CR 733.1)."""
        if self.payment is not None:
            self.payment.rewind()


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
