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
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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


class TargetSlot(BaseModel):
    """One targeting requirement's shape, without naming its candidates -
    `legal_targets` (`Game.legal_targets`) is where the actual candidate
    objects for one specific requirement are enumerated; this is the summary
    that says how many requirements there are and how many targets each
    wants, so a caller can tell "this action targets" from "this action does
    not" without a second round trip."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    minimum: int
    maximum: int | None
    """`None` for "any number of" (CR 107.1c)."""


class SpliceOption(BaseModel):
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


class Action(BaseModel):
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
    `ACTIVATE`/`ACTIVATE_MANA` only."""
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
    """The determined total cost (`str(TotalCost)`), in the engine's own
    words - never the `TotalCost` object itself, which can hold live
    `CardState` references (`CostComponent.cards`) that must not leak into a
    serializable record. `None` when nothing is paid at all (CR 107.3b)."""
    mana_cost: str | None = None
    """Just the mana portion of `cost`, as `ManaCost.parse` can read it back -
    kept separate so a reader does not have to parse `cost`'s prose to check
    affordability itself."""
    affordable: Affordability = Affordability.UNKNOWN
    unaffordable_reason: str | None = None
    """The engine's own refusal, in its own words - never a synthesized
    message. This is the load-bearing field: a boolean says an action failed,
    this says why, and that difference is the reason this project exists."""

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
    `MULLIGAN`, `OPENING_HAND_ACTION`, and the two combat declarations'
    "declare nobody"), or one of `Decision.options` for `CHOOSE_A_QUALITY`/
    `CHOOSE_A_MODE`."""
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
