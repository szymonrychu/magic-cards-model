from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple
from uuid import UUID

from pydantic import ConfigDict, Field

from ...machines.layers import (
    Characteristics,
    Condition,
)
from ...machines.turn import (
    Step,
)
from ...serialization import SortedFrozenSet
from ...snapshot import EngineModel
from ..card import (
    Color,
    Supertype,
    Type,
)
from ..card_state import (
    CardState,
    ExileAnnotation,
    TargetRef,
)
from ..zone import Zone

if TYPE_CHECKING:
    from . import Game


@dataclass(frozen=True)
class ActivationInstructions:
    """Every CR 602.1b activation instruction an ability prints, read.

    `who` is whose activation the ability admits: `"controller"` (CR 602.2's
    default - "Only an object's controller ... can activate its activated
    ability unless the object specifically says otherwise"), `"opponents"`
    (the controller's opponents only) or `"any"`. `sorcery` is CR 602.5d's
    timing, `per_turn` CR 602.5b's per-turn count (with the words that set it
    in `per_turn_text`), `once` the never-reset "Activate only once", `windows`
    the "during ..." phrases, `conditions` the "only if ..." conditions, and
    `unread` every instruction this reads no meaning from - refused, never
    allowed unchecked."""

    who: str = "controller"
    sorcery: bool = False
    per_turn: int | None = None
    per_turn_text: str | None = None
    once: bool = False
    windows: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    unread: tuple[str, ...] = ()


class ActivationProhibition(EngineModel):
    """One "activated abilities of ... can't be activated" static, read (CR 602.5).

    `qualities` are the card types the sentence names its subjects by - Karn,
    the Great Creator's "artifacts", Clarion Conqueror's "artifacts, creatures,
    and planeswalkers" - or empty for "permanents", which names them all.
    """

    model_config = ConfigDict(frozen=True)

    qualities: tuple[Type, ...] = ()
    opponents_only: bool = False
    """True for Karn's "your opponents control", false for the symmetric
    printings (Collector Ouphe, Clarion Conqueror) that catch their own
    controller's permanents too."""
    mana_abilities_exempt: bool = False
    """CR 605.1a's mana abilities, spared by the "unless they're mana
    abilities" tail some printings carry and Karn does not."""


class Reveal(EngineModel):
    """One card shown to all players (CR 701.20a), or to one (CR 701.20e).

    "To reveal a card, show that card to all players for a brief time." That is
    the whole of what revealing does to the game state, plus CR 701.20b's
    "Revealing a card doesn't cause it to leave the zone it's in" - so this is a
    *record*, not a move: the card stays exactly where it was and this says that
    everyone got to see it.

    It exists because revealing is the one way information leaves a hidden
    group of cards without the cards moving. Karn, the Great Creator's `−2`
    reveals **one** artifact card from a sideboard that nobody may otherwise
    look at (CR 400.11c), and an engine that answered "what is public now?" by
    handing over the sideboard would be leaking fourteen cards the reveal never
    showed. One entry per card actually revealed is the whole public fact.

    Frozen, and named by id as well as by name, because CR 701.20c allows the
    same card to be revealed more than once and each showing is its own event.

    **A look is the same record with viewers.** CR 701.20e: "Looking at a
    card follows the same rules as revealing a card, except that the card is
    shown only to the specified player." So `Game.look` appends one of these
    too, with `viewers` naming that player, and `Game.known_to` reads both
    kinds through the same checks.

    **What a record knows, and for how long, is data.** `zone_change_stamp`
    is the card's `CardState.zone_change_stamp` when it was shown, because
    CR 400.7 makes a card that changed zones "a new object with no memory of,
    or relation to, its previous existence" even though this engine keeps its
    `id`. `library_epoch` is the owner's `Player.library_epoch` when the card
    was shown from a library, because CR 701.20d ends a library reveal the
    moment the library is "shuffled or otherwise reordered". Both are compared
    live by `Game.known_to`; nothing here is a callable.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    card_name: str
    revealed_by: str
    """The player who showed it - the one CR 701.20a's effect instructed."""
    zone: Zone
    """Where the card was while it was revealed (CR 701.20b: it did not move).
    `Zone.SIDEBOARD` means it was outside the game (CR 400.11a)."""
    source: str | None = None
    """The card whose text asked for the reveal, by name."""
    viewers: list[str] | None = None
    """Who was shown the card. `None` is every player (CR 701.20a's reveal);
    a list is a look (CR 701.20e) and names the players who looked."""
    zone_change_stamp: UUID | None = None
    """The card's `CardState.zone_change_stamp` when it was shown (CR 400.7).
    `None` is a record of a shape `Game.known_to` does not recognise, and it
    is never returned."""
    turn: int | None = None
    """`TurnMachine.turns_taken` when it was shown, `0` before the first turn."""
    library_epoch: int | None = None
    """The owner's `Player.library_epoch` when the card was shown from a
    library (CR 701.20d), and `None` for a card shown from any other zone.
    Never rewritten: a put that leaves the card's order untouched is recorded
    as a `LibraryOrderKept` row instead."""


class KnownCarry(EngineModel):
    """A library record carried into its owner's hand by the move itself.

    **A knowledge policy, not a Comprehensive Rules rule** - the project
    owner's decision. CR 400.7 makes the card in hand a new object, and
    CR 402.3's "A player can't look at the cards in another player's hand"
    says nothing about a player who watched a known card go there. A player
    who saw the top card of a library and then saw its owner draw it
    (CR 121.1: "putting the top card of their library into their hand") knows
    what that card in hand is, so a record still live at the moment of a move
    straight from the owner's library to the owner's hand is copied here with
    the card's *new* stamp. It ends the way every record ends: the card's
    next zone change mints another stamp.

    The same policy covers a card that moves from a public zone (CR 400.2:
    graveyard, battlefield, stack, exile face up) into its owner's hand: every
    player saw its face there, so the move is recorded for every player.

    Written by `Game.carry_knowledge_into_hand` and
    `Game.carry_public_knowledge_into_hand`, read by `Game.known_to`.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    card_name: str
    owner: str
    viewers: list[str] | None = None
    """The carried record's own viewers - a look stays the looker's."""
    zone_change_stamp: UUID
    """The card's stamp as it arrived in the hand."""
    source: str | None = None
    turn: int
    """When the carried record was made, not when the card moved."""


class LibraryOrderKept(EngineModel):
    """One library card, as one object, kept its place through one library put.

    CR 701.20d ends a library reveal only for "revealed cards that are
    reordered", and CR 401.2 keeps a library one ordered pile: a card put onto
    the bottom goes below every card already there, and a scry or surveil
    reorders only the cards it looked at. So when such a put moves its owner's
    `Player.library_epoch` to `epoch`, each other card with a live library
    record gets one of these, and `Game.known_to` reads a record made at an
    earlier epoch as still true when every epoch since has one for that card
    and stamp (CR 400.7). `Reveal` itself is never rewritten: its
    `library_epoch` stays the order the card was shown in.

    Written by `Game.keep_untouched_library_records`.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    zone_change_stamp: UUID
    """The card's stamp when the put happened - a later object is not this one."""
    epoch: int
    """The owner's `Player.library_epoch` the put moved the library to."""


class KnownCard(EngineModel):
    """One hidden card a player knows, as `Game.known_to` answers it.

    Ids only, never a live `CardState`, the same convention `models/action.py`
    keeps. `index_from_top` is computed live for a card known in a library
    (CR 401.2 keeps the library one ordered pile) and is `None` everywhere
    else; `carried` says the knowledge came through `KnownCarry`.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    card_name: str
    owner: str
    zone: Zone
    index_from_top: int | None
    source: str | None
    turn: int
    carried: bool


class UntapStepRule(NamedTuple):
    """What one player's untap step would do, before any of it is done.

    `Game.untap_step_rule`'s answer: `skipped` is CR 614.10's verdict for the
    whole step, and `permanents` are the permanents CR 502.3 would untap (the
    ones already untapped included - untapping them changes nothing, and
    leaving them out would make the list disagree with the batch the step
    actually hands to `Player.untap_all`). A skipped step untaps nothing, so
    `permanents` is empty whenever `skipped` is true.
    """

    skipped: bool
    permanents: list[CardState]


class CastRecord(EngineModel):
    """What was announced while a spell was being cast (CR 601.2b, 601.2c).

    A `CardState` on the stack is the card and its targets and nothing else, so
    the choices made during announcement have nowhere to live on it. They matter
    after announcement is over:

    - `keyword` - CR 702.34a's flashback exile and CR 702.185a's warp trigger
      both apply only "if the [flashback/warp] cost was paid".
    - `face` - CR 715.3d exiles a spell "that was cast as an Adventure".
    - `modes` - CR 700.2c makes which targets a modal spell has depend on which
      modes were chosen, which CR 608.2b then rechecks on resolution.
    - `mode_targets` - CR 700.2f: a modal spell may have "different targeting
      requirements for each mode", so each chosen mode keeps its own slice of
      what was targeted rather than sharing one flat list.
    - `mana_spent` - CR 601.2h is where the total cost's mana is actually spent;
      Vexing Bauble's "if no mana was spent to cast it" and Wistfulness's "if
      {G}{G} was spent to cast it" both read this after the fact
      (`machines/triggers.intervening_if_holds`).
    - `kicked` - CR 702.33d: a spell is "kicked" once its controller declares
      the intention to pay a kicker cost, which the linked ability's "if it
      was kicked" (CR 702.33a) checks afterwards.

    Written by `Game.note_cast`, which `machines/casting.py` calls as the spell
    goes on the stack.
    """

    keyword: str | None = None
    """The keyword the spell was cast with, as printed: `Flashback`, `Warp`."""
    exile_instead_of_graveyard: bool = False
    """Cast under a `PlayPermission` whose own "If that spell would be put
    into a graveyard, exile it instead." rider was printed alongside its
    grant (Dire Fleet Daredevil, Nita, Forum Conciliator) - the same CR 604.5
    "static ability applies while a spell is on the stack" shape flashback's
    own second half already reaches through `keyword`, folded straight onto
    this record instead of a second `keyword` value because the grant here
    names no keyword at all. Read by `machines/replacement._stack_
    replacements`."""
    keyword_cost_paid: bool = False
    """Whether the cost that keyword names was paid (`Casting.keyword_cost_paid`).

    CR 702.185a: a warped card cast from exile later is cast with the same
    keyword option but for its mana cost, and "If this spell's warp cost was
    paid" is false for it."""
    origin_zone: Zone = Zone.HAND
    """Where the spell was cast **from** (CR 601.2a), copied from `Casting.
    origin_zone` as the spell goes on the stack. CR 702.88a's rebound applies
    "if this spell was cast from your hand" - a card cast from the graveyard
    (Flashback), from exile (Rebound's own recast), or anywhere else never
    triggers it a second time, which is exactly what would build an infinite
    exile-and-recast loop if this were read off anything but the announcement
    itself.

    For a copy's own record (`is_copy=True`), this is always `Zone.STACK`,
    never the bare default above: CR 707.10 - "a copy of a spell isn't cast" -
    so a copy was not cast from anywhere, and `Zone.STACK` is neither `HAND`
    nor `GRAVEYARD` nor any other zone a "cast from <zone>" clause names,
    which is what makes every *positive* such read already correct for a copy
    with no clause-by-clause change. `is_copy` itself is the field a
    negation-shaped read ("wasn't cast from your hand") checks explicitly -
    see `is_copy`'s own docstring."""
    is_copy: bool = False
    """Whether this record describes a copy rather than a cast spell (CR
    707.10: "a copy of a spell isn't cast"). Written by `Game.copy_spell`,
    never by `Game.note_cast` - a copy's record is never the product of an
    announcement.

    Every "was this spell cast" and "cast from <zone>" reader in this engine
    is answered correctly for a copy by `origin_zone` alone (see its own
    docstring): a copy's `origin_zone` is always `Zone.STACK`, which no
    "cast from <zone>" clause ever names. This field exists for the one
    shape that default cannot answer on its own - a *negation* ("this spell
    wasn't cast from your hand", Twinned Vision) - where a reader checks
    `is_copy` explicitly alongside the zone comparison, rather than leaning
    on `Zone.STACK` happening to not equal `Zone.HAND` either. A copy is
    still "also a spell" (CR 112.1a) for everything else - targeting,
    resolution, the stack - only casting itself is excluded."""
    face: str | None = None
    """The name of the face being cast, for a card with more than one (CR 715.3)."""
    exile_annotation: "ExileAnnotation | None" = None
    """The exile pile the card was cast out of, captured before CR 601.2a's
    move to the stack cleared it.

    `CardState.move_to` nulls `exile_annotation` for any non-exile
    destination, so by the time a spell is on the stack the pile it came from
    is gone - and CR 702.143a's foretell asks afterwards, needing
    `turn_exiled` to count "the number of turns you've begun since it was
    foretold". Captured at announcement by `Casting.announced_exile_annotation`
    for the same reason `origin_zone` is."""
    modes: list[int] = Field(default_factory=list)
    """The chosen modes, as their 1-based position on the card (CR 700.2)."""
    mode_targets: list[list[TargetRef]] = Field(default_factory=list)
    """Each chosen mode's own targets (CR 700.2f), aligned by position with
    `modes` - `mode_targets[i]` is what mode `modes[i]` targets."""
    x_value: int = 0
    """The value announced for X (CR 107.3a), which a mode's target count may use."""
    spend_effects: tuple[str, ...] = ()
    """CR 106.6's additional-effect sentences carried by the mana that paid
    this spell's cost, verbatim.

    Filled at CR 601.2h from `ManaPayment.spend_effects_spent`, so it names
    only the effects of mana that was *actually spent* on this spell - the
    Arena's other red left floating tags nothing. Read once, as the spell
    resolves, by `Game._apply_mana_spend_effects`.
    """

    mana_spent: dict[Color, int] = Field(default_factory=dict)
    """How much mana of each colour was spent paying the total cost (CR 601.2h),
    taken from `machines/cost.ManaPayment.spend`. Colourless mana spent on a
    `{C}` symbol or on generic is `Color.COLORLESS`, same as everywhere else in
    this engine. Empty means either no mana was spent, or the spell was cast
    without going through `Casting` at all - the two are indistinguishable here,
    which is why `any_mana_spent` is the question to ask rather than truthiness
    of the dict alone when that distinction matters."""
    treasure_mana_spent: int = 0
    """How much of `mana_spent` came from a Treasure (CR 106.3's source of
    mana), from `ManaPayment.treasure_spent` - "if mana from a Treasure was
    spent to cast it" (`machines/triggers.intervening_if_holds`)."""
    cast_step: Step | None = None
    """The step the spell was cast in (CR 601.2i), and `cast_during_turn_of`
    whose turn it was - "if you cast it during your main phase" (CR 505.1,
    `machines/conditions/timing.py`) asks about the cast, not about now.
    `None` for a copy, which was never cast (CR 707.10)."""
    cast_during_turn_of: str | None = None
    kicked: int = 0
    """How many times a kicker cost was paid (CR 702.33d), copied from
    `Casting.kicked`."""
    replicated: int = 0
    """How many times a replicate cost was paid (CR 702.56a), copied from
    `Casting.replicated` - what `machines/keywords._replicate_effect` copies
    the spell for and `machines/triggers.intervening_if_holds`'s "a
    replicate cost was paid for it" clause reads."""
    casualty_paid: int = 0
    """How many of the spell's casualty costs were paid (CR 702.153a/b),
    copied from `Casting.casualty_paid` - one casualty trigger per payment
    (`machines/spell_grants.granted_triggered_abilities_for`), each gated by
    `machines/triggers.intervening_if_holds`'s "a casualty cost was paid for
    it" clause."""
    conspire_paid: int = 0
    """How many of the spell's conspire costs were paid (CR 702.78a), copied
    from `Casting.conspire_paid` - one conspire trigger per payment
    (`machines/spell_grants.granted_triggered_abilities_for`), each gated by
    `machines/triggers.intervening_if_holds`'s "its conspire cost was paid"
    clause."""
    offspring_paid: bool = False
    """Whether this spell's offspring cost was paid (CR 702.175a), copied
    from `Casting.offspring_paid`. Bool rather than a count: CR 702.175b's
    "multiple instances of offspring" each get their own linked ability and
    their own payment, which is not a pool printing yet - see
    `docs/engine-coverage.md`."""
    blight_paid: bool = False
    """Whether this spell's blight cost was paid (CR 701.68a), copied from
    `Casting.blight_paid`. Requiting Hex's own linked "if this spell's
    additional cost was paid, you gain 2 life" reads this generically -
    `optional_additional_cost_paid` below is the field that clause's own
    reader actually asks, so a future card whose optional additional cost is
    something other than blight is not left unreadable."""
    cast_using_teamwork: bool = False
    """Whether this spell's Teamwork cost was paid (`machines/teamwork.py`),
    copied from `Casting.teamwork_paid`. Read by `_CONDITION_CAST_USING_
    TEAMWORK` (`Game.condition_holds`) and by `machines/triggers.
    intervening_if_holds`'s own "if this spell was cast using teamwork"
    branch, the same two doors `kicked` is read through above."""
    phyrexian_life_symbols_paid: int = 0
    """How many Phyrexian mana symbols of this spell's total cost were paid
    with life rather than mana (CR 107.4f), read off the settled payment by
    `machines/cost.CostPayment.phyrexian_life_symbols_paid`.

    CR 702.150a's compleated is the one reader: "If this permanent would
    enter with one or more loyalty counters on it and the player who cast it
    chose to pay life for any part of its cost represented by Phyrexian mana
    symbols, it instead enters the battlefield with that many loyalty
    counters minus two for each of those mana symbols." `machines/
    replacement._compleated_modifier` reads this field off the cast record
    while the permanent is still on its way in (CR 614.12), the same moment
    `_sunburst_modifier` reads `mana_spent` for CR 702.44b's distinct-colors
    count.

    Not copied by `Game.copy_spell` (CR 707.10 - "a copy of a spell isn't
    cast", so no mana or life was ever spent casting it), the same exclusion
    `mana_spent`/`spend_effects` already document above: a copy's own record
    simply never mentions this field, which leaves it at its default of 0 and
    is exactly right - a copy of a compleated planeswalker enters at its full
    printed loyalty regardless of how the original was paid for."""

    @property
    def optional_additional_cost_paid(self) -> bool:
        """Whether *any* of this spell's own optional additional costs were
        paid - CR 118.8b's "you may ..." kind, kicker/offspring/blight alike.

        The generic reader for a card's own "if this spell's additional cost
        was paid" clause (`machines/effects._parse_if_additional_cost_paid_
        clause`) asks this rather than any one keyword's flag, because the
        clause names no keyword itself - only one card in the pool has more
        than one such cost to begin with, and CR 607's "linked ability"
        shape assumes exactly one antecedent per card.
        """
        return (
            self.kicked > 0
            or self.offspring_paid
            or self.blight_paid
            or self.cast_using_teamwork
            or self.behold_chosen_type_paid
        )

    gift_promised: bool = False
    """Whether this spell's gift was promised (CR 702.174k), copied from
    `Casting.gift_promised`."""
    gift_chosen_player: str | None = None
    """The opponent chosen when the gift was promised (CR 702.174a), copied
    from `Casting.gift_chosen_player`."""

    behold_chosen_type_paid: bool = False
    """Whether this spell's own optional "you may choose a creature type and
    behold two creatures of that type" additional cost was paid (CR 118.8b,
    701.4a) - Celestial Reunion's, copied from `Casting.behold_chosen_type_
    paid`. Folded into `optional_additional_cost_paid` below the same way
    `blight_paid` already is, since Celestial Reunion's own resolution text
    reads the generic "if this spell's additional cost was paid" phrasing
    (CR 607.2i), not a name of its own."""
    chosen_creature_type: str | None = None
    """The creature type named paying `behold_chosen_type_paid` (CR 607.2d's
    "choose a [value]"/"the chosen [value]" link), lowercased. `None` when
    the cost was not paid, or the spell prints no such choice at all - this
    is a *spell's* own one-off announcement, kept on `CastRecord` rather
    than on `CardState.choice` (`ChoiceKind.CREATURE_TYPE`) because CR
    614.12a's field is for a *permanent* replacement choice made "as [it]
    enters"; a sorcery that resolves and heads straight to the graveyard has
    no permanent incarnation to carry that choice on at all."""

    additional_cost_cards: list[UUID] = Field(default_factory=list)
    """Every card consumed paying one of `Casting.additional_costs`'
    components - Fling's "sacrifice a creature" (CR 118.8a), read here by
    whatever the resolving spell's own text says about it ("deals damage
    equal to the sacrificed creature's power"). Recorded by object identity
    rather than by a snapshotted value because different cards ask different
    questions of the same consumed card (a creature's power here, a
    discarded card's own characteristics elsewhere) - the caller looks the
    id up with `Game.find_by_id`, which still finds it wherever paying the
    cost moved it (a sacrifice to the graveyard, an exile cost to exile)."""

    additional_cost_mana_values: list[float] = Field(default_factory=list)
    """`additional_cost_cards`' mana values, aligned by position and taken as
    the record is written (CR 601.2h, the costs just paid) - CR 608.2h's last
    known information for Eldritch Evolution's "the sacrificed creature's
    mana value". An id alone is not enough for this one question: a
    sacrificed token ceases to exist (CR 111.7, CR 704.5d) before the spell
    resolves, leaving `Game.find_by_id` nothing to find, and a copy's mana
    value on the battlefield (CR 707.2) is not its card's. Read through
    `Game.last_known_mana_value`, the same number either way."""

    additional_cost_kinds: list[str] = Field(default_factory=list)
    """`additional_cost_cards`' `ComponentKind` values ("tap", "sacrifice",
    "discard", ...), aligned by position - which verb paid each one. A
    resolving spell's "the number of creatures tapped this way" (Burn at the
    Stake), "the sacrificed creatures" (Soulblast) or "the discarded cards"
    (Nahiri's Wrath) counts only the cards its own verb paid (CR 118.8,
    CR 601.2h), never every card any additional cost touched."""

    additional_cost_powers: list[int] = Field(default_factory=list)
    """`additional_cost_cards`' powers, aligned by position and taken as the
    record is written - CR 608.2h's last known information for "the total
    power of the sacrificed creatures" (Soulblast, Corpse Cobble). Like
    `additional_cost_mana_values` this is a snapshot, not an id lookup: a
    sacrificed token ceases to exist (CR 704.5d) before the spell resolves.
    A card with no power (a discarded instant, a `*` it cannot compute off
    the battlefield) reads 0 (CR 107.2)."""

    enters_with_counters: list[str] = Field(default_factory=list)
    """One counter kind per counter the permanent this spell becomes enters
    with because of how it was cast - a cast permission's own rider, "If you
    cast a spell this way, that creature enters with a finality counter on
    it." (Leonardo, Sewer Samurai; `KeywordCastOption.enters_with_counters`).
    CR 614.1c makes it a replacement effect on the entering permanent,
    applied by `machines/replacement._cast_permission_rider_modifiers`. Not
    copied by `Game.copy_spell`: CR 707.10's copy was not cast this way."""

    sneak_defender: TargetRef | None = None
    """The player, planeswalker or battle the creature returned to pay this
    spell's sneak cost was attacking (CR 702.190b), copied from `Casting.
    returned_creature_defender`. `None` unless the sneak cost was paid. The
    creature is out of combat by the time the spell resolves (CR 506.4), so
    this is the only place that answer survives to CR 702.190b's "It will be
    attacking the same player, planeswalker, or battle"."""

    card_id: UUID | None = None
    """The `CardState.id` of the card this record describes, so every record
    for a card can be forgotten at once (`Game.forget_cast_record`) after the
    object has moved on and its stamp no longer matches the key."""

    kicker_costs_paid: list[str] = Field(default_factory=list)
    """Which of the spell's kicker costs were paid, each as printed ("{2}{U}"),
    in announcement order (CR 702.33b: "Kicker [cost 1] and/or [cost 2]" is
    two kicker costs) - CR 702.33f's "if it was kicked with its [A] kicker"
    asks which, `kicked` only how many times. Copied from `Casting.
    kicker_costs_paid`."""
    bargained: bool = False
    """Whether the spell's bargain cost was paid (CR 702.166b: it "has been
    'bargained'"), copied from `Casting.bargained`."""
    evidence_collected: bool = False
    """Whether evidence was collected as an optional additional cost (CR
    701.59c's linked "if evidence was collected"), copied from `Casting.
    evidence_collected`."""
    revealed_for_cost: bool = False
    """Whether a card was revealed from hand for an optional "you may reveal a
    <quality> card from your hand" additional cost (CR 118.8b) - Orator of
    Ojutai's "if you revealed a Dragon card", copied from `Casting.
    revealed_for_cost`."""
    beheld_for_cost: bool = False
    """Whether a plain "you may behold a <quality>" additional cost (CR
    118.8b, CR 701.4a) was paid - Dispelling Exhale's "if a Dragon was
    beheld" (CR 701.4b), copied from `Casting.beheld_for_cost`."""
    controlled_subtypes_as_cast: tuple[str, ...] = ()
    """Every subtype among the permanents the caster controlled as the spell
    became cast (CR 601.2i), lowercased - "or controlled a Dragon as you cast
    this spell". Empty for a copy, which was never cast (CR 707.10)."""
    controlled_modified_creature_as_cast: bool = False
    """Whether the caster controlled a modified creature (CR 700.9) as the
    spell became cast (CR 601.2i) - Flame Discharge's "If you controlled a
    modified creature as you cast this spell". Fixed at casting, so a counter
    put on or taken off afterwards changes nothing. False for a copy (CR
    707.10)."""
    creature_mana_spent: int = 0
    """How much of `mana_spent` came from creatures (CR 106.3), from
    `ManaPayment.creature_spent` - "three or more mana from creatures was
    spent to cast it"."""
    snow_mana_spent: dict[Color, int] = Field(default_factory=dict)
    """How much of `mana_spent` came from snow sources, by colour (CR 107.4h's
    {S}), from `ManaPayment.snow_spent` - "{S} of any of that spell's colors
    was spent to cast it"."""

    def mana_of_color_spent(self, color: Color) -> int:
        """How much mana of this colour was spent paying the total cost (CR 601.2h)."""
        return self.mana_spent.get(color, 0)

    @property
    def total_mana_spent(self) -> int:
        """CR 601.2h: how much mana in all was spent paying the total cost -
        not the mana value (CR 202.3), which a reduction or life paid for a
        Phyrexian symbol does not change."""
        return sum(self.mana_spent.values())

    @property
    def any_mana_spent(self) -> bool:
        """CR 601.2h: whether any mana at all was spent paying the total cost."""
        return sum(self.mana_spent.values()) > 0


class ShieldKind(StrEnum):
    """The three shapes CR 615 gives a prevention effect from a resolved spell."""

    #: CR 615.7: "prevent the next N damage that would be dealt to ... this
    #: turn". Each 1 damage prevented reduces the shield by 1; at 0 the rest is
    #: dealt normally.
    AMOUNT = "amount"
    #: CR 615.8: "the next time [a source] would deal damage". Prevents one whole
    #: instance regardless of size, then stops applying.
    NEXT_INSTANCE = "next_instance"
    #: CR 615.1a with a duration: "prevent all combat damage that would be dealt
    #: this turn". Never used up; it expires instead.
    ALL = "all"


class ShieldSourceFilter(EngineModel):
    """Which sources a filtered fog covers: "by attacking creatures", "by
    nongreen creatures", "by creatures with no +1/+1 counters on them", "by
    creatures without trample", "by creatures with power 4 or less", "by
    creatures `<player>` controls", "by creatures other than target creature".

    Data, never a callable (a persisted shield must decode), and read against
    the source as it is when the damage would be dealt - CR 609.7b: "When the
    source would deal damage, the "shield" rechecks the source's properties.
    If the properties no longer match, the damage isn't prevented." A
    creature that grows past the power limit, or gets a counter, after the
    shield was made is no longer covered; one that arrives later is. A
    filter that names creatures (`creatures`, the default) matches a creature
    on the battlefield as the damage is dealt, or a source that has left the
    battlefield and was a creature as it last existed there (CR 608.2h, its
    last known information) - never a creature card that was not a
    permanent, and "attacking" is read the same way (`last_known_attacking`:
    CR 506.4 took it out of combat as it left); one that names sources ("by
    colorless sources", "that black sources and red sources would deal", "by
    sources you don't control") reads any source, on the battlefield or not.
    """

    attacking: bool = False
    excluded_colors: tuple[Color, ...] = ()
    """"nongreen": the source must have none of these colours."""
    without_counter: str | None = None
    """"with no +1/+1 counters on them": the counter kind it must not carry."""
    without_keyword: str | None = None
    """"without trample"."""
    max_power: int | None = None
    """"with power N or less"."""
    controller: str | None = None
    """"creatures target opponent controls": the player chosen as the
    spell resolved; control is still read as the damage is dealt."""
    opponents_of: str | None = None
    """"creatures your opponents control": an opponent of this player."""
    excluded_card_id: UUID | None = None
    excluded_stamp: UUID | None = None
    """"other than target creature": that one object (CR 400.7: a new
    object after a zone change is covered again)."""
    creatures: bool = True
    """The filter names creatures: the source must be a creature on the
    battlefield. False for a filter that names sources of any kind."""
    colors_any: tuple[Color, ...] = ()
    """"black sources and red sources", "black and/or red sources": the
    source must have at least one of these colours."""
    colorless: bool = False
    """"colorless sources" (CR 105.2c: a colorless object has no color)."""
    not_controlled_by: str | None = None
    """"sources you don't control": a source this player does not control."""

    def matches(self, game: "Game", source: CardState) -> bool:
        from ...machines.combat import source_had_keyword

        if source.zone is Zone.BATTLEFIELD:
            chars = game.characteristics_of(source)
            colors = set(chars.colors)
            types = set(chars.types)
            counters = chars.counters
            attacking = game.is_attacking(source)
        elif self.creatures and not source.last_left_the_battlefield:
            return False  # a creature card never was a creature (CR 109.2)
        else:
            # CR 608.2h / 113.7a: a source gone from the battlefield is read
            # off its last known information - a Walking Ballista that
            # removed its last counter was a creature as it last existed.
            colors = set(
                source.last_known_colors if source.last_known_colors is not None else source.colors
            )
            types = set(
                source.last_known_types if source.last_known_types is not None else source.types
            )
            counters = source.last_known_counters
            attacking = source.last_known_attacking
        if self.creatures and Type.CREATURE not in types:
            return False
        if self.colors_any and not set(self.colors_any) & colors:
            return False
        if self.colorless and colors:
            return False
        if self.not_controlled_by is not None and (
            game.controller_of(source).username == self.not_controlled_by
        ):
            return False
        if not self.creatures:
            return True
        if self.attacking and not attacking:
            return False
        if set(self.excluded_colors) & colors:
            return False
        if self.without_counter is not None and counters.get(self.without_counter, 0) > 0:
            return False
        if self.without_keyword is not None and source_had_keyword(
            source, self.without_keyword, game
        ):
            return False
        if self.max_power is not None and (game.power_of(source) or 0) > self.max_power:
            return False
        controller = game.controller_of(source).username
        if self.controller is not None and controller != self.controller:
            return False
        if self.opponents_of is not None and controller == self.opponents_of:
            return False
        return not (
            self.excluded_card_id is not None
            and source.id == self.excluded_card_id
            and source.zone_change_stamp == self.excluded_stamp
        )


class ReflectedDamage(EngineModel):
    """CR 615.5's "If damage is prevented this way, `<spell>` deals that much
    damage to any target." (Refraction Trap, Divine Deflection): who deals it
    and to what. The target was chosen as the spell was cast (CR 601.2c) and
    is held as the object it was on resolution - a permanent that has since
    changed zones is a new object (CR 400.7) and is dealt nothing."""

    source_id: UUID
    target_card_id: UUID | None = None
    target_stamp: UUID | None = None
    target_player: str | None = None
    optional: bool = False
    """"you may have `<spell>` deal that much damage" (Channel Harm): the
    shield's controller chooses each time, as the damage is prevented (CR
    608.2d, CR 615.5)."""


class PreventionShield(EngineModel):
    """One prevention effect waiting for a damage event (CR 615.1).

    "Like replacement effects (see rule 614), prevention effects apply
    continuously as events happen - they aren't locked in ahead of time. Such
    effects watch for a damage event that would happen and completely or
    partially prevent the damage that would be dealt. They act like 'shields'
    around whatever they're affecting."

    CR 615.4 is why this is a stored object rather than something computed when
    the damage lands: "Prevention effects must exist before the appropriate
    damage event occurs - they can't 'go back in time'". A shield created after
    the damage was dealt does nothing, and one created before it applies even
    though its source has left the battlefield.

    CR 615.3: "Such effects last until they're used up or their duration has
    expired." Both endings are here - `used_up` and `until_end_of_turn`.
    """

    kind: ShieldKind
    label: str
    """What the shield says, for the event trace."""

    controller: str
    """Who created it. CR 616.1 hands the ordering choice to the *affected*
    player, not to this one, but `ApplicableEffect` still needs a controller and
    the shield's source permanent may be long gone."""

    card_id: UUID | None = None
    """The shielded permanent, or None if the shield protects a player."""
    player: str | None = None
    """The shielded player, or None if the shield protects a permanent."""

    source_id: UUID | None = None
    """CR 615.8: only damage from this specific source is prevented."""
    source_stamp: UUID | None = None
    """The `zone_change_stamp` of the `source_id` object the shield was made
    for, when it was made for one particular object - Old Fat Spider Can't See
    Me's "damage that would be dealt by up to one target creature". CR 400.7:
    that creature leaving and returning is a new object the shield never
    named, so damage from it is not prevented. `None` for a shield keyed to
    a source id alone (the older CR 615.8 shapes)."""
    lasts_while: Condition | None = None
    """CR 611.2b's "for as long as ..." duration on a prevention effect - Old
    Fat Spider's "for as long as this Saga remains on the battlefield". The
    shield applies only while it holds; `until_end_of_turn` is False for
    such a shield."""
    source_quality: str | None = None
    """CR 615.9 / CR 609.7b: only damage from a source with this property.

    "When the source would deal damage, the shield rechecks the source's
    properties. If the properties no longer match, the damage isn't prevented or
    replaced and the shield isn't used up." Rechecking is why the quality is
    stored as a word and matched against the source at damage time rather than
    resolved to a set of objects when the shield was made."""

    excluded_source_subtypes: SortedFrozenSet[str] = frozenset()
    """CR 609.7b's recheck, stated as an exclusion instead of a match.

    Moonmist's "Prevent all combat damage that would be dealt this turn **by
    creatures other than Werewolves and Wolves**" names the sources it does
    *not* cover, which `source_quality` cannot say: that field is one quality
    the source must have, and it reads card types and colours, never subtypes.

    Stored as words and rechecked at damage time for the same reason
    `source_quality` is - CR 609.7b: "When the source would deal damage, the
    'shield' rechecks the source's properties. If the properties no longer
    match, the damage isn't prevented." A creature that becomes a Werewolf
    after the shield was made is excluded when the damage lands, and a
    creature that arrives later is covered without the shield having to know
    about it. Resolving this to a set of objects at resolution would fail
    open on both counts.
    """

    source_filter: ShieldSourceFilter | None = None
    """The filtered fog's "by `<sources>`" (CR 609.7b, rechecked as the
    damage would be dealt). An anonymous source never matches a filter."""

    players_only: bool = False
    """"damage that would be dealt to players": every player, no permanent."""

    and_permanents_of: str | None = None
    """"to you and/or permanents you control": this player, and any permanent
    this player controls as the damage would be dealt. Used with `player`
    left None."""

    recipient_types: tuple[Type, ...] = ()
    """"to creatures", "to artifact creatures", "to you and creatures you
    control": a damaged permanent must have every one of these card types as
    the damage would be dealt. No player is covered unless `and_permanents_of`
    names them."""

    recipient_controller: str | None = None
    """"to creatures you control": a damaged permanent must be controlled by
    this player as the damage would be dealt; no player is covered."""

    reflects: ReflectedDamage | None = None
    """CR 615.5's "deals that much damage to any target" rider."""

    combat_only: bool = False
    """CR 510.2: "prevent all *combat* damage"."""

    amount: int = 0
    """What is left of a CR 615.7 shield. Meaningless for the other two kinds."""

    until_end_of_turn: bool = True
    """CR 514.2 ends it in the cleanup step, alongside the marked damage."""

    until_next_turn_of: str | None = None
    """CR 611.2a's "until your next turn" duration - Morningtide's Light's
    own "Until your next turn, prevent all damage that would be dealt to
    you." A shield with this set is created with `until_end_of_turn=False`
    (cleanup never touches it) and is instead removed by `Game.
    begin_turn_for` the moment this named player's own next turn begins -
    the identical hook `machines/layers.py`'s own `Duration.
    UNTIL_YOUR_NEXT_TURN`/`until_next_turn_of` already ends a continuous
    effect through."""

    used_up: bool = False
    """CR 615.7's shield reduced to 0, or CR 615.8's instance spent.

    CR 609.7b: "If for any reason the shield prevents no damage or replaces no
    damage, the shield isn't used up" - so this is set from what was actually
    prevented, never from having been consulted.
    """

    prevented: int = 0
    """How much damage this shield has actually prevented, in total (CR 615.5).

    "Some prevention effects also include an additional effect, which may refer
    to the amount of damage that was prevented. The prevention takes place at the
    time the original event would have happened; the rest of the effect takes
    place immediately afterward."

    A shield that was consulted and prevented nothing leaves this at 0, which is
    the same fact CR 609.7b makes `used_up` record. It accumulates rather than
    being overwritten, because a CR 615.7 amount shield can prevent damage from
    several events before it is spent and "the damage prevented this way" means
    all of it.
    """

    gains_life_when_prevented: bool = False
    """CR 615.5's additional effect, in the one shape the engine has.

    Awe Strike's "You gain life equal to the damage prevented this way" is a
    rider on the prevention rather than part of the resolving spell's effect: the
    amount does not exist until the damage event that never happened would have
    happened, so nothing can be gained when the spell resolves. `Game.apply_prevention_shield`
    performs it "immediately afterward", which is where CR 615.5 puts it.

    A flag rather than a callback because CR 615.5's riders are a small, printed
    set and this is the only one in the pool. A second shape - Nature's Blessing,
    a rider that draws - would be a second field or a proper hook; this is not
    the general mechanism and does not pretend to be.
    """

    @property
    def spent(self) -> bool:
        return self.used_up or (self.kind is ShieldKind.AMOUNT and self.amount <= 0)


class ObjectCostOffer(EngineModel):
    """One convoke/delve/improvise/crew offer for a card's cost, and the
    cards eligible to pay it right now - `Game.object_cost_offers`'s own
    answer, typed so a caller can read it without importing
    `machines/objects_as_costs.py`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rule: str
    number: int | None = None
    """Crew's own printed number (CR 702.122a); `None` for convoke, delve and
    improvise, which name no fixed total."""
    candidates: list[CardState] = Field(default_factory=list)


class GraveyardArrival(EngineModel):
    """One card's arrival at a graveyard this turn (CR 400.6's "put into a
    graveyard").

    A general record rather than another single-purpose counter: it is the
    same underlying fact - "a card was put into a graveyard, from where,
    belonging to whom, was it a permanent card" - that several different
    printed conditions each ask a narrower question of. Wan Shi Tong-style
    "cards put into a library" already gets its own per-event `GameEvent`
    (`ExtraTriggerEvent.PUT_INTO_LIBRARY`); a graveyard arrival gets no
    trigger event of its own in this pool, only intervening-*if*/activation
    questions about the turn as a whole, which is why this is a plain
    `Game`-level ledger rather than something `machines/triggers.py` matches.

    `Game.put_into_graveyard` is the main place a graveyard arrival passes
    through (CR 400.6, 614.1a's own docstring on that method), but not the
    only one: `machines/keywords.discard`/`.dredge` and the two
    `Game.enter_the_battlefield` branches where a replacement effect
    (CR 614.6) redirects an entering permanent's destination to a graveyard
    instead never call it, so each records its own arrival too - see
    `Game.descended`'s own docstring for why CR 700.11's "from anywhere"
    needs every one of them. `origin_zone` is the zone the card left
    (captured before the move, the same way `CastRecord.origin_zone` is), and
    `permanent_types` is the computed types the object had while it was still
    on the battlefield for a card that arrived that way (`None` for a card
    that reached the graveyard from anywhere else, since CR 613.5's computed
    board has nothing to compute for an object that was never a permanent).

    Cleared when a new turn begins, the same reset every other per-turn
    ledger on `Game` already gets.
    """

    player: str
    """The graveyard's owner (CR 111.4/400.3: a card's owner's graveyard is
    where it goes), read off `Game._owner_of` at the moment of arrival."""
    origin_zone: Zone
    is_permanent_card: bool = False
    """CR 110.4a's "permanent card" question - artifact, battle, creature,
    enchantment, land, or planeswalker - asked of the card's own *printed*
    types (`CardState.types`, front-face-safe) regardless of whether it was
    ever on the battlefield on this trip. Deliberately not answered by
    `permanent_types` below: that field is `None` for anything that skipped
    the battlefield (a discard, a mill, a countered permanent spell), and CR
    700.11's Descend counts exactly those too - "permanent cards put into a
    player's graveyard from anywhere this turn" has no battlefield
    requirement at all. `Game.cards_put_into_graveyard_this_turn`'s own
    `permanent_only` filter reads this field, not `permanent_types`."""
    permanent_types: tuple[Type, ...] | None = None
    """The computed card types (CR 613.5) the object had while still a
    permanent, for an arrival straight off the battlefield (CR 700.4's dies,
    a sacrifice, a destroy effect). `None` for a card that was never on the
    battlefield on this trip - a discard, a mill, a countered or resolved
    spell leaving the stack."""
    card_id: UUID | None = None
    """Which card arrived - what "all creature cards in your opponents'
    graveyards that were put there from the battlefield this turn" (Supper
    for Spiders, Faith's Reward) asks. The card's *latest* arrival this turn
    is the one that counts: a card that left the graveyard and came back is a
    new object (CR 400.7) whose own trip decides. `None` only on a ledger
    written before this field existed."""
    card_types: tuple[Type, ...] = ()
    """The card's own *printed* types (CR 613.5-free, front-face-safe - the
    same source `is_permanent_card` already reads off `card_state.types`),
    kept whole rather than reduced to one boolean. `is_permanent_card` only
    answers CR 110.4a's own six-type question; a template naming one type in
    particular - Raphael, Fiendish Savior's and Macabre Reconstruction's "a
    **creature** card was put into your graveyard from anywhere this turn" -
    needs the type itself, not a permanent/nonpermanent split, and needs it
    for an arrival that skipped the battlefield exactly the way
    `is_permanent_card` already does (a discard, a mill, a countered spell).
    `()` only on a ledger written before this field existed, which reads as
    "no printed types" - wrong for a real card, which is why every reader of
    this field is an *additional* gate alongside `is_permanent_card`/
    `permanent_types`, never the only one a card's identity depends on."""
    combat: int = 0
    """Which combat phase of the turn the card arrived during (the same
    `Game.turn_count("combat_phases", ...)` ordinal `TurnHistoryEntry.combat`
    uses, CR 506.1/500.8), or `0` for an arrival outside any combat phase -
    what "that wasn't put there this combat" (Storrev, Devkarin Lich) asks."""


class CombatDamageToPlayer(EngineModel):
    """One source's combat damage actually dealt to a player this turn
    (CR 510.2), with what that source was *at the time it dealt that damage*.

    CR 702.76a's prowl asks exactly this: "if a player was dealt combat damage
    this turn by a source that, at the time it dealt that damage, was under
    your control and had any of this spell's creature types." Storing the
    source's id and looking it up later cannot answer that - the source may
    have died since, changed controller, or lost a type - so the controller
    and the computed creature types (CR 613.5, changeling's CR 702.73a
    included) are captured by `machines/combat._deal_combat_damage` as the
    damage is dealt, off damage actually dealt only (a prevented hit is not
    "dealt"). Cleared when a new turn begins."""

    player: str
    """The player who was dealt the damage."""
    source_id: UUID
    controller: str
    """The source's controller when it dealt the damage."""
    creature_types: tuple[str, ...] = ()
    """The source's computed creature types (CR 205.3m) when it dealt the
    damage."""


class CountersPutRecord(EngineModel):
    """One instruction's counters put on one permanent this turn (CR 122.6),
    with who put them (CR 122.6a) - what "you've put one or more +1/+1
    counters on `<it>` this turn" (Beast, Erudite Aerialist; Kid Loki) and
    "for each +1/+1 counter you've put on creatures under your control this
    turn" (Iridescent Hornbeetle) look back at. The counters themselves are
    no answer: one may have been removed, or annihilated (CR 704.5q), since.

    `controller` and `types` are the permanent's when the counters landed -
    "creatures under your control" is judged then, not now."""

    putter: str
    card_id: UUID
    kind: str
    amount: int
    controller: str | None = None
    types: tuple[Type, ...] = ()
    zone_change_stamp: UUID | None = None
    """Which incarnation of `card_id` (CR 400.7): a permanent that left the
    battlefield and came back is a new object the counters were never put
    on."""


class DamageDealt(EngineModel):
    """One damage event this turn (CR 120.1: "An object that deals damage is
    the source of that damage"), with what its source was *as it dealt it*.

    "If a Giant, Wizard, or spell you controlled dealt damage to it this turn"
    (Aegar, the Freezing Flame) asks about the source's controller, types and
    whether it was a spell at that moment - none of which an id looked up
    later can answer once the source has died, resolved or changed hands, the
    same reason `CombatDamageToPlayer` captures prowl's facts. Recorded from
    every `TriggerEvent.DEALS_DAMAGE` event by `machines/conditions/history.
    record`; cleared when a new turn begins."""

    source_id: UUID | None = None
    source_controller: str | None = None
    source_types: tuple[Type, ...] = ()
    """The source's types as it dealt the damage (CR 613.5's computed ones
    for a permanent, the printed line for a spell)."""
    source_subtypes: tuple[str, ...] = ()
    source_was_spell: bool = False
    """Whether the source was a spell on the stack (CR 109.2b) as it dealt
    the damage."""
    recipient_id: UUID | None = None
    """The permanent dealt the damage, or `None` for a player."""
    recipient_player: str | None = None
    amount: int = 0
    combat: bool = False
    source_supertypes: tuple[Supertype, ...] = ()
    """The source's supertypes as it dealt the damage - "a legendary
    creature" (Blitzball)."""
    source_colors: tuple[Color, ...] = ()
    """The source's colors as it dealt the damage - "red sources you
    controlled" (Temple of Power)."""
    recipient_types: tuple[Type, ...] = ()
    """The permanent recipient's types as it was dealt the damage - "combat
    damage to a creature" (Thirsting Axe). Empty for a player."""
    recipient_controller: str | None = None
    """The permanent recipient's controller as it was dealt the damage - "a
    creature ... an opponent controlled" (Rith, Liberated Primeval)."""
    excess: int = 0
    """CR 120.10's excess damage this event dealt to a creature or
    planeswalker, worked out by `Game.deal_damage` from the recipient as it
    was before the damage."""


class TurnHistoryEntry(EngineModel):
    """One thing that happened this turn that a turn-history condition
    (`machines/conditions/history.py`) asks about afterwards and no narrower
    ledger keeps with the characteristics it needs: a permanent entering, a
    permanent going to a graveyard or a hand from the battlefield, a
    sacrifice, an attack, a crew.

    `characteristics` is the object as it was at that moment (CR 603.10a's
    look-back for a departure, the computed types of an entering or attacking
    permanent), so "a non-Skeleton creature died under your control" is read
    off what the creature was then, not what the card is now. Written by
    `machines/conditions/history.record` from the event that carries it;
    `Game.turn_history` is this turn's and `Game.turn_history_last_turn` the
    previous turn's, rolled where every other per-turn ledger is.
    """

    kind: str
    """What happened: "entered", "to_graveyard" (CR 700.4's put into a
    graveyard from the battlefield), "to_hand", "sacrificed", "attacked",
    "crewed", "left_battlefield" (any route off the battlefield, written by
    `Game._note_left_battlefield`)."""
    player: str | None = None
    """Whose it was: the controller of the permanent (entered, to_graveyard,
    to_hand, attacked), the player who sacrificed it (CR 701.21a) or crewed
    with it (CR 702.122b)."""
    owner: str | None = None
    """The owner of the card - whose graveyard or hand it went to (CR 108.3)."""
    object_id: UUID | None = None
    related_id: UUID | None = None
    """For "crewed", the Vehicle it crewed."""
    characteristics: Characteristics | None = None
    face_down: bool = False
    combat: int = 0
    """For "attacked", which combat phase of the turn (CR 500.8 can add more
    than one), counted by `Game.turn_count("combat_phases", ...)`."""
    cast_mana_spent: int | None = None
    """For "entered", how much mana was spent to cast the spell that became
    this permanent (CR 601.2h, read off its `CastRecord` through CR 400.7d as
    it entered), or None when it was not cast at all (put onto the
    battlefield, or a copy that was never cast). Fixed at the event, so CR
    603.4's recheck reads the same answer after the permanent has left -
    Satoru, the Infiltrator's "if none of them were cast or no mana was spent
    to cast them"."""


class SchemaVersionMismatch(RuntimeError):
    """A `Game` snapshot's `schema_version` does not match this build's
    `Game.CURRENT_SCHEMA_VERSION`, or the snapshot has no `schema_version` at
    all - T9 of the stateless-library plan. See `Game.schema_version`'s own
    docstring for the policy this enforces and why both cases refuse rather
    than fall back to a default.

    Raised from `Game._check_schema_version`, a `mode="before"` validator, so
    it surfaces on every construction path: `Game(...)`, `Game.model_validate
    (...)`/`model_validate_json(...)`, and `Game` decoded as an element of
    `Match.games`.

    Deliberately **not** a `ValueError` (unlike `DeckIllegal`, this package's
    usual convention for "a bad state discovered while building a model"):
    pydantic-core catches `ValueError`/`TypeError`/`AssertionError` raised
    inside a validator and rewraps it as a generic `pydantic.ValidationError`,
    which would bury this behind a string message indistinguishable from any
    other bad-input error. A future persistence/replay caller needs to catch
    a version mismatch *specifically* - refuse the load, log which versions
    disagreed, without also swallowing an unrelated malformed-data bug - so
    this subclasses `RuntimeError` instead, which pydantic-core does not
    intercept and lets propagate as-is, verified to do so even when the
    mismatched `Game` is nested inside a `Match.games` decode.
    """


class LoyaltyInstantSpeedPermission(EngineModel):
    """CR 606.3's own "any time you have priority and the stack is empty
    during a main phase of your turn" loosened to instant speed on any
    player's turn - "You may activate loyalty abilities of `<subject>` on
    any player's turn any time you could cast an instant."

    Three real shapes share this one record: Teferi, Master of Time's own
    self-reference ("... of Teferi ..."), permanent and scoped to himself
    (`self_source_id`); Teferi's Talent's and Teferi, Temporal Archmage's
    emblem ("... of planeswalkers you control ..."), permanent and
    unscoped; and Jace's Machinations' own "Until end of turn, you may
    activate loyalty abilities of Jace planeswalkers you control ...",
    scoped by subtype (`subtype="Jace"`) and bounded
    (`until_end_of_turn=True`). CR 606.3's *other* half - "only if no
    player has previously activated a loyalty ability of that permanent
    that turn" - is untouched: this loosens only the timing, never the
    once-per-turn-per-permanent rule.

    Nothing here checks priority itself, the same posture `why_cannot_
    activate`'s own docstring already takes for the ordinary CR 606.3
    timing: this engine has no notion of a priority possession that
    persists between moves, so a caller granted this permission is trusted
    to hold priority when it uses it.
    """

    model_config = ConfigDict(frozen=True)

    player: str
    """Whose "you"/"your" the printed grant means (CR 608.2h)."""
    subtype: str | None = None
    """A planeswalker subtype filter ("Jace"), or `None` for every
    planeswalker `player` controls."""
    self_source_id: UUID | None = None
    """Scoped to one specific planeswalker by id (Teferi, Master of Time's
    own self-reference) rather than by subtype or by "you control" at
    large. Takes priority over `subtype` when set."""
    until_end_of_turn: bool = False
    """`False` is a permanent grant (an emblem's own "always"); `True` is
    Jace's Machinations' own bounded one, dropped by `Game.cleanup_step`
    the same way `play_permissions`' own "until end of turn" entries are."""
