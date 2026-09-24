"""`Action`: a serializable call spec for one legal move.

The library owes two guarantees. "Decode any game state" is `Game` itself,
which round-trips through `model_dump_json`. This is the other one: enumerate
what a player *could* do at a given point, in a shape that can sit in an
append-only training log next to whatever the seat actually did, so "what was
taken" and "what else was legal" are directly comparable - the same type,
built the same way, from the same enumeration.

That comparability is why `Action` holds **ids only, never a `CardState`,
`Player`, or `Card`**. Two defects already shipped from getting this wrong in
this codebase (`memory/keyword-activation-round-trip-identity.md`):
`CostPayment.tapped_for_mana` was briefly `list[CardState]` and a dump/decode
round trip silently turned one physical permanent into two unrelated copies,
each mutated independently; `_equip_effect`/`_crew_effect` read a captured
`KeywordActivation.card` after exactly that kind of decode and acted on the
stale copy. A log row is read back long after the `Game` that produced it is
gone - there is no live object for an id to be "the same as" any more, only a
`UUID` a reader re-resolves through whatever `Game` they have on hand. Even
`CostComponent.cards: list[CardState]` (`machines/cost.py`), a live payment
object that never crosses a JSON boundary on its own account, is one reason
`Action.cost` below is a string rather than the engine's own `TotalCost` -
embedding it would smuggle exactly the same live `CardState` references into
what is supposed to be a plain record.
"""

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict, model_serializer

from ..snapshot import EngineModel
from .card import Color
from .zone import Zone


class ActionKind(StrEnum):
    """What kind of call spec this is - one entry point per engine action a
    seat (or `legal_actions`) can name."""

    CAST = "cast"
    """CR 601: cast a spell, for its printed mana cost or for one alternative
    cost - one `Action` per cast option (`Action.alternative_cost` names
    which, `None` for the printed mana cost). `Action.splice_options` names
    CR 702.47's splice pool for this same cast option, not a further cast
    option of its own - see its own docstring."""
    PLAY_LAND = "play_land"
    """CR 305.1, and CR 712.12 for an MDFC's land face (`Action.land_face`)."""
    TURN_FACE_UP = "turn_face_up"
    """CR 702.37e's special action."""
    SUSPEND = "suspend"
    """CR 116.2f."""
    COMPANION = "companion"
    """CR 116.2g: pay `{3}` to put a chosen companion into hand from outside
    the game, once per game."""
    FORETELL = "foretell"
    """CR 116.2h."""
    PLOT = "plot"
    """CR 116.2k."""
    DREDGE = "dredge"
    """CR 702.52a-b: replace a draw with a mill, off a graveyard card."""
    ACTIVATE = "activate"
    """CR 602.2: activate a printed or granted ability of a permanent the
    player controls on the battlefield - `Action.ability_index` names which."""
    ACTIVATE_MANA = "activate_mana"
    """The same CR 602.2 activation, split out for a mana ability
    specifically (CR 605), including one `auto_tap` withholds from a player
    unasked (`cost.py::_withheld_mana_sources`) because it costs more than a
    bare `{T}` - Nurturing Peatland's 1 life is a real, standalone action a
    seat can learn to take, not only a fallback `auto_tap` reaches for."""
    ACTIVATE_OFF_ZONE = "activate_off_zone"
    """CR 113.6j/113.6m: an activated ability that functions from a zone
    other than the battlefield - cycling (CR 702.29), a channel-style ability,
    Greater Gargadon's own suspended-exile ability."""
    DECLARE_ATTACKER = "declare_attacker"
    """CR 508.1: one creature attacking one defender - a single pair, not the
    whole declaration, so a seat can learn which pairs are legal rather than
    only whether attacking is legal at all."""
    DECLARE_BLOCKER = "declare_blocker"
    """CR 509.1: one blocker assigned to one attacker."""
    PASS_PRIORITY = "pass_priority"
    """CR 117.3d. Always legal whenever a player holds priority, and never
    listed by the API probe this replaces - an agent that never sees "pass"
    cannot learn when to pass."""
    CONCEDE = "concede"
    """CR 104.3a. Always legal."""
    ANSWER_DECISION = "answer_decision"
    """Not a CR-numbered action of its own - the answer to whichever
    `Decision` (`machines/decisions.py`) is currently pending, keyed by
    `Decision.kind`'s own rule (`rule_for_kind`). When a decision is pending,
    the legal actions **are** its legal answers and nothing else; see
    `legal_actions`'s own docstring for why that is not a gap the way the
    API's `{}` used to be."""


class Affordability(StrEnum):
    """Whether an action's cost could be paid right now - reported
    *alongside* legality, never used to decide it. CR 118.6: "Attempting to
    cast a spell, activate an ability, or take a special action that has an
    unpayable cost is a legal action." Casting with no red mana in play is
    still casting; this is what tells the difference between "legal and
    payable" and "legal and not"."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"
    """The cost cannot be judged without more information this enumeration
    does not have yet - a modal spell before a mode is chosen, an X spell
    before X is announced. See `Action.modes`/`Action.x_range`."""


class TargetSlot(EngineModel):
    """One targeting requirement of a cast or an activation (CR 601.2c, and
    CR 602.2b for an activation): its phrase, how many targets it takes, and
    which objects and players it could legally name right now.

    The candidates are ids and usernames only, like `decision_candidates`/
    `decision_player_candidates`, and come from the same predicate the
    announcement checks with (`TargetRequirement.rejects`), so a candidate
    list cannot disagree with what announcing that target would accept. They
    are a snapshot of this moment, not a promise: CR 608.2b rechecks on
    resolution."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    minimum: int
    maximum: int | None
    """`None` for "any number of" (CR 107.1c)."""
    candidates: tuple[UUID, ...] = ()
    """Every object (a card in a public zone, or a spell or ability on the
    stack) this requirement could name right now."""
    player_candidates: tuple[str, ...] = ()
    """Every player (CR 115.1: targets are objects and/or players) this
    requirement could name right now."""


class SpliceOption(EngineModel):
    """One card in `player`'s hand that could be revealed to splice its text
    onto this `CAST` action's spell (CR 702.47a), before any is chosen.

    Unlike `spell_face`/`alternative_cost`, this is not one of a family of
    mutually exclusive ways to cast the same card - CR 702.47b lets more
    than one splice card apply to the same spell at once ("If you're
    splicing more than one card onto a spell, reveal them all at once"), so
    a `CAST` action carries the whole eligible pool here, the same
    "parameter space, not an enumeration" treatment `Action.modes` already
    gives a modal spell's bullets. Choosing one (or several) happens on the
    in-flight `Casting.splice(name)`, not here."""

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    cost: str
    """This card's own splice cost (CR 702.47a's `[cost]`), as `str(TotalCost)`
    - an *additional* cost on top of whatever `Action.cost` already names,
    the same way `Action.cost` never folds in `Action.modes`'/`x_range`'s own
    unresolved cost variance either."""


class AdditionalCostOption(EngineModel):
    """One optional additional cost this `CAST` action's spell may be cast
    with (CR 601.2b, CR 118.8b) - Sowing Mycospawn's `Kicker {1}{C}`,
    Everflowing Chalice's `Multikicker {2}`, Gigadrowse's `Replicate {U}`.

    CR 601.2b: "If the spell has alternative or additional costs that will
    be paid as it's being cast such as buyback or kicker costs ..., the
    player announces their intentions to pay any or all of those costs".
    CR 118.8b: "Some additional costs are optional."

    Like `SpliceOption`, and unlike `spell_face`/`alternative_cost`, this is
    not a family of mutually exclusive `Action`s: CR 118.8a lets any number
    of additional costs apply to one cast, so the row carries the whole
    space a seat may announce from and the announcement itself is made on
    the cast (`Game.cast(kicker=..., offspring=..., ...)`).

    It is deliberately *not* folded into `Action.cost`. CR 118.8d: "Additional
    costs don't change a spell's mana cost, only what its controller has to
    pay to cast it" - and nobody has announced this one yet, so adding it to
    the displayed cost would claim a choice that has not been made, exactly
    the reason an unannounced `{X}` is left alone there too.
    """

    model_config = ConfigDict(frozen=True)

    keyword: str | None
    """The keyword printing it, lower-case (`kicker`, `multikicker`,
    `replicate`, `offspring`, `gift`, `blight`), or `None` for a cost printed
    as an "As an additional cost to cast this spell, you may ..." sentence
    with no keyword on it."""
    cost: str
    """The cost exactly as printed: `{1}{C}`, `a Food`, `you may blight 1`."""
    rule: str
    """The CR rule that defines this cost - CR 702.33a for kicker, CR 702.33c
    for multikicker, and so on."""
    repeatable: bool = False
    """CR 702.33c's multikicker and CR 702.56a's replicate may be announced
    "any number of times"; plain kicker (CR 702.33a) and offspring may not."""
    understood: bool = True
    """`False` is the loud "this engine cannot charge this cost" case, the
    same shape `restriction_understood` already uses for CR 106.6: the option
    is printed and optional, so a seat is told it exists rather than shown
    nothing, and told in the same breath that announcing it is not available
    here. Failing closed out loud, never a silent omission."""


class ManaPlanEntry(EngineModel):
    """One tap in the plan `Action.pays_with` carries: which permanent, which
    of its mana abilities, what that adds, and CR 106.6's restriction on the
    mana if it has one.

    `Action.pays_with`'s own docstring has why this exists at all. What it is
    *not* is a set of instructions: nothing reads one of these back in, and no
    entry point takes one. It is a report of what the engine has already
    decided it would do, so a seat can spend its thinking on the consequence
    ("that is the land I wanted for the counterspell") rather than on the
    mechanics of paying, which the engine does for it either way.

    An id and a name together, unlike everywhere else in this module where an
    id travels alone: this rides on an enumeration a seat reads in one pass to
    decide what to do, and re-resolving a dozen uuids against the board to
    find out that one of them is a Cavern of Souls is exactly the round trip
    the enumeration exists to avoid. The id remains the identity - the name is
    a label, and never what a caller matches on.
    """

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    """The permanent that gets tapped."""
    name: str
    """That permanent's name, so the plan reads without a second lookup."""
    ability_index: int | None
    """Which of `Game.activated_abilities(card_id)`'s entries produces this
    mana - the same index `Game.activate_ability` takes, and the difference
    between Cavern of Souls's free `{C}` (index 0) and its restricted mana of
    any colour (index 1). `None` only for an intrinsic ability with no
    enumerable activated ability behind it."""
    adds: str
    """The mana this tap adds, as bare colour letters in the order the ability
    produces them - `"R"`, `"W"`, `"RR"`, `"C"`. Not `ManaCost`'s braced
    notation: this is what a source *makes*, not a cost, and the two read
    differently on purpose."""
    restriction: str | None = None
    """CR 106.6's "Spend this mana only to ..." sentence, verbatim off the
    card, when this ability's mana carries one - the engine will enforce
    exactly this. Absent from the serialized entry entirely when there is
    none: a plan rides on every affordable action in an enumeration, so a
    null here is pure weight on every unrestricted land in the game."""

    @model_serializer(mode="wrap")
    def _drop_absent_restriction(self, handler: Any) -> dict[str, Any]:
        """Serialize without a `restriction` key when there is no restriction.

        Decoding is untouched - the field defaults to `None`, so a dumped
        entry still round-trips back to an equal object.
        """
        dumped = handler(self)
        if dumped.get("restriction") is None:
            dumped.pop("restriction", None)
        return dumped


class Action(EngineModel):
    """The arguments one engine entry point takes - a serializable call spec.

    Built so "what a seat took" and "what else was legal at that moment" are
    the same type, directly comparable, and replayable from a log row long
    after the `Game` that produced it is gone. Every reference to something in
    the game is an id (`card_id`, `decision_candidates`, `attacker_id`) rather
    than a live object - see the module docstring for why that is load-bearing
    rather than a style preference.
    """

    model_config = ConfigDict(frozen=True)

    kind: ActionKind
    player: str
    rule: str
    """The verified CR number this action is taken under (or, for
    `ANSWER_DECISION`, `rule_for_kind(decision.kind)` - the engine's own
    citation for that question)."""

    card_id: UUID | None = None
    from_zone: Zone | None = None
    ability_index: int | None = None
    """Which of `Game.activated_abilities(source)`'s entries this activates -
    `ACTIVATE`/`ACTIVATE_MANA` only. `None` on an equip row (`keyword="Equip"`),
    which is a keyword ability with no entry there; it is taken with
    `keywords.equip_activation`."""
    keyword: str | None = None
    """The keyword this cast option or activation reads from - `Evoke`,
    `Flashback`, `Cycling` - or `None` for a plain mana-cost cast or a
    printed activated ability with no keyword name of its own."""
    alternative_cost: str | None = None
    """Which CR 118.9 alternative cost this `CAST` action pays under (the
    option's own keyword, or a short label for a printed pitch phrase), or
    `None` for the card's ordinary printed mana cost. Force of Negation for
    `{1}{U}{U}` and Force of Negation pitched are two `Action`s that differ
    only in this field and `cost`."""
    land_face: str | None = None
    """Which face of an MDFC is being played as a land (CR 712.12), or `None`
    for an ordinary land or a card's normal front face."""
    spell_face: str | None = None
    """Which face this `CAST` announces (CR 709.3's split-card choice,
    CR 715.3's Adventure), or `None` for the card's plain front face. A split
    card's two halves print one combined `mana_cost` (`{1}{R} // {W}`) that
    parses to their *summed* value, not what casting either half alone
    costs, so `Wear // Tear` is two `CAST` actions, one per half, each
    carrying its own face's `cost`/`mana_cost` here; an Adventure card is
    the creature's own plain cast (`None`) plus one more for the Adventure
    half."""

    cost: str | None = None
    """The determined total cost (CR 601.2f, `str(TotalCost)`), in the
    engine's own words - never the `TotalCost` object itself, which can hold
    live `CardState` references (`CostComponent.cards`) that must not leak
    into a serializable record. `None` when there is no cost at all - a land
    drop, passing priority.

    The rule here read CR 107.3b until 2026-09-10, cited from memory by an
    earlier pass and looked up (`mise run rules:find`) by a later one: 107.3b
    is "the only legal choice for X is 0" when a spell with {X} is cast
    without paying its mana cost, which is a different subject entirely.
    CR 601.2f is the sentence that defines a total cost."""
    mana_cost: str | None = None
    """Just the mana portion of `cost`, as `ManaCost.parse` can read it back -
    kept separate so a reader does not have to parse `cost`'s prose to check
    affordability itself."""
    affordable: Affordability = Affordability.UNKNOWN
    unaffordable_reason: str | None = None
    """The engine's own refusal, in its own words - never a synthesized
    message. This is the load-bearing field: a boolean says an action failed,
    this says why, and that difference is the reason this project exists."""
    pays_with: tuple[ManaPlanEntry, ...] = ()
    """Which permanents this action's mana cost would tap, and for what -
    `machines/cost.plan_mana_payment`'s answer, the plan `auto_tap` would
    execute if the action were taken.

    Present only on an action that owes mana (`mana_cost` is not `None`) and
    that the engine has said is payable (`affordable` is `YES`); empty
    everywhere else, including on a payable cost the payer's floating mana
    already covers, where the honest answer is that nothing gets tapped.

    Purely informational, and deliberately so. Nothing asks a seat to name
    mana sources - `auto_tap` chooses, offers every untapped source, and stops
    as soon as the pool can pay (CR 118.3c). What this answers is the question
    the seat cannot otherwise ask without casting the spell: *which* of its
    sources this particular cost eats. "This Bolt takes the Cavern of Souls I
    was holding for the counterspell" is a strategic fact about the board that
    a bare `affordable=yes` hides."""

    target_slots: tuple[TargetSlot, ...] = ()
    """One entry per targeting requirement this action would announce, in
    order. Candidates are not repeated here - see `Game.legal_targets`."""
    modes: tuple[str, ...] = ()
    """A modal action's printed mode texts (CR 700.2), offered as the
    parameter space they are rather than enumerated combination by
    combination - a caller chooses a subset from this list rather than being
    handed one `Action` per legal combination."""
    x_range: tuple[int, int | None] | None = None
    """`(minimum, maximum)` for an action whose cost or effect names an X
    (CR 107.3a) or an amount to pay (`PAY_ENERGY_AMOUNT`/`PAY_LIFE_AMOUNT`'s
    answers) - a parameter space, not an enumeration, the same treatment
    `modes` gets and for the same reason: naming every integer in range would
    make an unbounded X spell an unbounded number of `Action`s. `maximum` is
    `None` for a genuinely open-ended X (nothing caps how much mana could be
    spent on it), never for "not applicable" - `None` for the whole field is
    what says that."""
    splice_options: tuple[SpliceOption, ...] = ()
    """`CAST` only: CR 702.47a's splice, every card in `player`'s hand that
    could be revealed onto this spell right now - see `SpliceOption`'s own
    docstring for why this is a pool a caller chooses zero, one, or several
    from (`Casting.splice(name)`, once for each) rather than a family of
    `Action`s the way `spell_face`/`alternative_cost` are. Empty for the
    overwhelming majority of casts, which have no card in hand whose splice
    ability names this spell's own type or subtype (CR 702.47a's
    "[quality]")."""
    additional_cost_options: tuple[AdditionalCostOption, ...] = ()
    """`CAST` only: CR 601.2b's optional additional costs printed on this
    spell, which a seat announces as it casts. Empty for a spell that prints
    none - see `AdditionalCostOption`."""
    color_options: tuple[Color, ...] = ()
    """`ACTIVATE_MANA` only: every colour `Game.activate_ability`'s own
    `color=` would accept for this mana ability right now (CR 605.1a),
    computed by `Game.mana_color_options` - a dual land's two colours, or
    an "any color" source's five. Empty when the ability makes no real
    choice at all (one printed colour, or the choice has already been
    narrowed to nothing, CR 106.5), in which case `color=None` is what a
    caller passes through to `activate_ability`. The same parameter-space
    treatment `modes`/`x_range` already give a choice this module does not
    enumerate combination by combination - without this field, an
    `ACTIVATE_MANA` action reported `affordable=YES` for a choice-offering
    ability with no way for a caller to actually complete the call
    `Game.activate_ability` demands (`this ability offers [...]; pass the
    colour chosen`), which made the action unusable despite being reported
    legal and affordable."""
    color_choice_count: int = 0
    """`ACTIVATE_MANA` only: how many colours a caller names from
    `color_options`, one per mana whose colour is chosen separately -
    computed by `Game.mana_color_choice_count`. 0 whenever `color_options`
    is empty (the ability offers no choice, so `color=None`), 1 for nearly
    every ability that does offer one, and the mana count for "Add N mana in
    any combination of colors" (Interdimensional Web Watch), where each of
    the N mana takes its own colour and `Game.activate_ability` accepts a
    sequence of that many.

    The rest of the parameter space `color_options` alone cannot express:
    that pool is flat, so a two-colour choice among five reads exactly like
    a one-colour choice among five, and a caller driving the engine through
    `legal_actions` could only ever produce the five monochrome combinations
    - `{W}{U}`, which the printing plainly makes, was unreachable. Note that
    it counts *colours named*, not mana added: Shang-Chi, Master of Kung
    Fu's "two mana of any one color" adds two mana and takes one colour,
    because its own words lock both mana to it (CR 106.1b's colour is still
    each mana's own type; only this card's wording ties them together)."""
    produces: str | None = None
    """`ACTIVATE_MANA` only: what this mana ability's printed text **says**
    it adds, as printed - `"{C}{C}"`, `"one mana of any color"`, `"an amount
    of mana of that color equal to your devotion to that color"`. Two mana
    abilities on one permanent were otherwise byte-identical rows apart from
    `ability_index` (Eldrazi Temple prints `{T}: Add {C}.` and `{T}: Add
    {C}{C}. Spend this mana only ...`), so a seat holding the list could not
    tell which one it was choosing.

    **Deliberately not board-resolved**, and that is the promise this field
    makes: it is what the ability *says* it makes, never what the board would
    yield right now. Nykthos, Shrine to Nyx's amount is CR 700.5's devotion to
    a colour that has not been chosen yet, and Mox Amber's CR 106.5 narrowing
    ("of any color among legendary creatures and planeswalkers you control")
    is applied against the board at activation - neither is knowable before a
    colour is named. An `Action` is a snapshot a caller caches and acts on
    later, so a number that has since gone wrong is worse than no number at
    all. Counting and colour resolution stay where they already are, in
    `Game.activate_ability`; `color_options` above is the only choice this
    row enumerates. `None` when the ability's effect prints no readable
    "Add ..." phrase at all."""
    restriction: str | None = None
    """`ACTIVATE_MANA` only: CR 106.6's "Spend this mana only to ..." sentence
    as printed, verbatim, so a refusal downstream can quote the card rather
    than a parser's reading of it. Read with `machines/cost.spend_restriction`
    - the same call a real activation makes - off this ability's own effect
    text and this permanent (which "the chosen type" needs, CR 614.12a
    records the answer on the object that was asked).

    `None` when the ability prints no such sentence, which is the
    overwhelming majority; `None` here never means "restricted, but we could
    not read it" - that case carries the sentence and sets
    `restriction_understood` to False."""
    restriction_understood: bool | None = None
    """`ACTIVATE_MANA` only, and only alongside a `restriction`: whether this
    engine read that sentence into anything it can actually check
    (`models/mana.ManaRestriction.understood`).

    `False` is the loud case and the reason this field exists: the sentence
    is present, the mana will be produced and announced (CR 106.4a), and this
    engine will let it be spent on **nothing at all**, because an unread
    CR 106.6 restriction fails closed rather than towards permitting. A seat
    that cannot see this spends a turn discovering four unusable mana by
    experiment. `True` means the restriction is checkable and ordinary
    payment will honour it; `None` exactly when `restriction` is `None`, so
    there is nothing to have understood."""

    decision_candidates: tuple[UUID, ...] = ()
    """`ANSWER_DECISION` only, for a kind whose answer names a subset of
    `Decision.cards`/`Decision.targets` (`CHOOSE_CARDS`, `CHOOSE_TARGETS`,
    `SCRY`, `SURVEIL`, `ORDER_TRIGGERS`) - the candidate pool, offered as a
    parameter space rather than one `Action` per legal subset or permutation,
    which would be combinatorially unusable for exactly the reason `modes`
    already is. Card candidates only - see `decision_player_candidates` for
    `CHOOSE_TARGETS`'s other kind of legal answer."""
    decision_player_candidates: tuple[str, ...] = ()
    """`ANSWER_DECISION`/`CHOOSE_TARGETS` only: the usernames among
    `Decision.targets` (CR 115.1: "The targets are object(s) and/or
    player(s)"), which `decision_candidates` above cannot name at all - a
    `TargetRef` for a player carries a `username` and no `card_id`. Without
    this, an "any target"/"target player" question's enumerated answer
    silently dropped every legal player candidate from its own pool."""
    decision_option: str | None = None
    """`ANSWER_DECISION` only, for a kind whose legal answers are few enough
    to enumerate outright: `"true"`/`"false"` for every boolean-shaped kind
    (`MAY`, `PAY_LIFE`, `PAY_ENERGY`, `PAY_MANA`, `PUT_ON_TOP_OR_BOTTOM`,
    `CHOOSE_PILE`, `MULLIGAN`, `OPENING_HAND_ACTION`, and the two combat
    declarations' "declare nobody"), or one of `Decision.options` for
    `CHOOSE_A_QUALITY`/`CHOOSE_A_MODE`."""
    decision_seq: int | None = None
    """`PendingDecision.seq` - which question this answers. `Game` itself
    never carries a pending decision (it is raised as a `DecisionPending`
    exception and held by whichever caller catches it - the api's own
    mailbox, `magic_cards_model_api.decisions.PendingDecision`, is one such
    holder), so `legal_actions` cannot discover one on its own; a caller that
    already knows a decision is outstanding passes it in and this field says
    which one a given `Action` answers."""

    defender: str | None = None
    """`DECLARE_ATTACKER` only: the username, or the `UUID` (as a string) of
    a planeswalker or battle, being attacked."""
    attacker_id: UUID | None = None
    """`DECLARE_BLOCKER` only: which attack this assigns a blocker to."""


class BlockedCast(EngineModel):
    """One `CAST` face CR 601.3 refuses right now on timing (CR 117.1a,
    `machines.casting.why_cannot_cast_now`) or a CR 611.1 rules-modifying
    prohibition (`machines.casting.why_cannot_cast_restriction`) - the same
    per-face refusal `machines.legal_actions._cast_actions` already computes
    and used to silently `continue` past, reported here instead.

    `legal_actions` (`machines.legal_actions.legal_actions`) itself never
    grows a row for one of these: CR 601.3 makes a refused cast an illegal
    one, and `legal_actions`'s own promise is "what was legal" (see its
    module docstring). `blocked_casts` (`machines.legal_actions.
    blocked_casts`) is the companion enumeration - walking the same hand and
    permission-granted zones `legal_actions` itself walks building `CAST`
    rows - so a seat can tell "there was nothing to cast" apart from "Ocelot
    Pride sat in hand the whole game, uncastable only because the stack was
    never empty".

    **Timing/prohibition only, on purpose.** A card that fails
    `why_cannot_cast_from` (no permission to cast from where it sits at all -
    CR 601.3's "a rule or effect allows... to cast it" half) is left out
    entirely, never reported here: `legal_actions` enumerates no `Action` for
    it either, this reports only the *other* half of CR 601.3 ("no rule or
    effect prohibits"), and a land (CR 305.1: never a spell) is never a
    candidate to begin with."""

    model_config = ConfigDict(frozen=True)

    card_id: UUID
    name: str
    zone: Zone
    spell_face: str | None = None
    """Which face was refused (CR 709.3a/715.3a's chosen half) - `None` for
    a card whose only cast option is its plain front-face cast, the same
    value `Action.spell_face` would carry for that face."""
    reason: str
    """The engine's own refusal, verbatim - whatever `why_cannot_cast_now` or
    `why_cannot_cast_restriction` returned, never re-worded or summarized."""
    rule: str
    """The CR number `reason` itself cites first (`"117.1a"`, `"611.1"`),
    read off the refusal string rather than re-derived from which check
    produced it - a reason that cites more than one rule (Teferi, Time
    Raveler's own combined sorcery-speed refusal names CR 117.1a before CR
    611.1) reports the one it leads with, matching what a reader of `reason`
    would call the rule for this refusal."""
