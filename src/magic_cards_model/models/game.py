"""A single game: the players, the shared zones, and where the turn is."""

import re
from collections.abc import Callable
from enum import StrEnum
from random import Random
from uuid import UUID

from pydantic import BaseModel, Field

from ..machines import combat as combat_rules
from ..machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    CostKind,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
)
from ..machines.combat import (
    Attack,
    CombatMachine,
    EvasionNotice,
    Keyword,
    UndefinedPowerNotice,
    has_keyword,
)
from ..machines.cost import (
    CostComponent,
    CostModifierKind,
    CostModifierNotice,
    CostPayment,
    TotalCost,
    cost_component_for_phrase,
    cost_modifier_effect,
    discard_cost,
    increase,
    looks_like_unparsed_cost_modifier,
    loyalty_cost,
    pay_life_cost,
    sacrifice_cost,
    tap_cost,
)
from ..machines.decisions import (
    NOT_ANSWERED,
    CardSplit,
    Decision,
    DecisionKind,
    DecisionScript,
    ask_attackers,
    ask_blockers,
    default_answer,
    legal_options,
)
from ..machines.delayed import DelayedTrigger, DelayedTriggers, return_subject_to_hand
from ..machines.effects import (
    AnaphoricClauseNotice,
    ConditionalClauseNotice,
    DelayedClauseNotice,
    ImprintNotice,
    ModeNotice,
    activated_effect_for,
    effect_for,
    trigger_effect_for,
)
from ..machines.keywords import (
    aura_state_based_actions,
    equipment_state_based_actions,
    is_indestructible,
    keyword_effect_for,
)
from ..machines.layers import (
    Characteristics,
    ComputedBoard,
    ContinuousEffects,
    LayerContext,
    additional_land_plays,
)
from ..machines.priority import PriorityMachine, PriorityOutcome
from ..machines.replacement import EventKind, ReplaceableEvent, apply_replacements
from ..machines.targeting import (
    TargetingProfile,
    profile_for_modes,
    profile_for_text,
    targeting_profile,
)
from ..machines.triggers import (
    AbilityOnStack,
    GameEvent,
    InterveningIfNotice,
    TargetingNotice,
    TargetingNoticeKind,
    activated_abilities_of,
    apnap_order,
    intervening_if_holds,
    tapped_for_mana_event,
    triggers_for,
)
from ..machines.turn import MAIN_PHASES, NO_PRIORITY, TURN_ORDER, Step, TurnMachine
from .card import Card, Color, Supertype, Type
from .card_state import CardState, ExileMarker, TargetRef, planeswalkers_with_zero_loyalty
from .mana import ManaCost
from .player import Player
from .token import move_refused, tokens_that_cease_to_exist
from .zone import Zone

#: Anything a spell can point at and then affect (CR 115.1).
Targetable = CardState | Player

#: What the stack holds. A spell is the card itself (CR 112.1); an ability is a
#: separate object with no card behind it (CR 405.1, 113.1c).
StackObject = CardState | AbilityOnStack

#: CR 702.16a: "Protection is a static ability, written 'Protection from
#: [quality]'." CR 702.16g makes "protection from A and from B" two abilities,
#: so the qualities are split apart rather than kept as one phrase.
_PROTECTION = re.compile(r"protection from ([^.;\n]+)", re.IGNORECASE)

#: A cost sentence that names the permanent its ability is printed on -
#: "Exert this land", "Sacrifice this creature". CR 602.1a: an activated
#: ability's source is the object it is printed on, so "this" is that object and
#: only the caller building the cost knows which it is.
_SELF_REFERENCE = re.compile(r"\bthis\b", re.IGNORECASE)

#: CR 601.2f cost reduction of the shape Emrakul, the Promised End prints.
#: Narrow on purpose: the amount, and the thing being counted, are both read
#: back out and anything else is left alone rather than guessed at.
_COSTS_LESS_PER_CARD_TYPE = re.compile(
    r"costs \{(\d+)\} less to cast for each card type among cards in your graveyard",
    re.IGNORECASE,
)


def _qualities_from_text(text: str | None) -> list[str]:
    """Every "protection from [quality]" this text carries, in order (CR 702.16a,
    CR 702.16g). Shared by `protection_qualities`, which reads a printing's own
    oracle text, and `Game._effective_protection_qualities`, which reads the
    same phrase off a *granted* ability line (`machines/layers.py`'s indefinite
    keyword-and-protection grant, Akroma's Memorial) the same way.
    """
    qualities: list[str] = []
    for match in _PROTECTION.finditer(text or ""):
        for part in match.group(1).split(" and from "):
            quality = part.strip().rstrip(",").strip()
            if quality and quality not in qualities:
                qualities.append(quality)
    return qualities


def protection_qualities(card: Card) -> list[str]:
    """Every quality this printing has protection from, in printed order (CR 702.16a).

    Read straight off the oracle text, which is how every other keyword in this
    engine is read: Scryfall's `keywords` field says only "Protection", never
    from what. CR 702.16g's "protection from [A] and from [B]" is two separate
    protection abilities, so the phrase is split on "and from".

    This is the printing's own protection only. A permanent can also have
    protection *granted* to it by another static ability (Akroma's Memorial's
    "creatures you control have ... protection from black and from red") -
    `Game._effective_protection_qualities` is the one that reads both.
    """
    return _qualities_from_text(card.oracle_text)


#: CR 605.1a's fourth criterion, read off the printed text: a word that means a
#: card is moving to or from a library. "Draw" draws from one, "mill" puts
#: library cards into the graveyard, "search" takes cards out of one, "surveil"
#: moves the top card of one, and the bare word "library" is in the list so a
#: phrasing this list does not name is still caught rather than guessed at.
_LIBRARY_MOVEMENT = re.compile(r"\b(draw|mill|search|surveil|library)\b", re.IGNORECASE)


def moves_a_library_card(ability: ActivatedAbility) -> bool:
    """Whether the ability's printed cost or effect moves a card to or from a
    library (CR 605.1a's fourth criterion).

    CR 605.1a: an activated ability is not a mana ability if "its cost and
    effect don't move any card to or from a library" fails - a mill- or
    draw-for-mana ability resolves as an ordinary activated ability, on the
    stack and counterable. The rule also says "Do not take into account
    replacement effects that may apply, other than self-replacement effects,
    when evaluating these criteria", and this does exactly that: the criteria
    are evaluated on the printed text and nothing else - no replacement is
    consulted, so there is no self-replacement to make an exception for.

    The check is honest about being a heuristic over the printed line: the
    words above are the ones the oracle text of a card-moving ability prints.
    A printing that *mentions* the library without moving a card - "reveal the
    top card of your library" moves nothing - would be classified as not a
    mana ability; no known printing of that shape is also an `Add` ability,
    which is what `ability.mana` gates this check behind.
    """
    return _LIBRARY_MOVEMENT.search(ability.raw) is not None


#: CR 105.1: "There are five colors in the Magic game: white, blue, black, red,
#: and green." Colorless is not a sixth - CR 105.2c: "A colorless object has no
#: color" - so it is not a key here, and a source is matched against the colors
#: it has rather than against the ones it lacks.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


#: CR 602.5d's timing restriction, in both templates WOTC prints it in:
#: "Activate only as a sorcery" and the older "Activate only any time you could
#: cast a sorcery". CR 307.5 makes them the same restriction.
_SORCERY_TIMING = re.compile(
    r"activate (?:this ability )?only (?:as a sorcery|any time you could cast a sorcery)",
    re.IGNORECASE,
)

#: Mox Opal's Metalcraft: "Activate only if you control three or more
#: artifacts." Number words rather than digits, matching how these two
#: restrictions are actually printed in the pool.
_ACTIVATE_ONLY_IF_CONTROL = re.compile(
    r"activate only if you control (?P<count>\w+) or more (?P<quality>\w+)s?",
    re.IGNORECASE,
)
#: Fanatic of Rhonas's Ferocious: "Activate only if you control a creature
#: with power 4 or greater."
_ACTIVATE_ONLY_IF_POWER = re.compile(
    r"activate only if you control a creature with power (?P<power>\d+) or greater",
    re.IGNORECASE,
)
_CONDITION_COUNT_WORDS: dict[str, int] = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def _card_type_named(quality: str) -> Type | None:
    """The card type a protection quality names, or None if it names something else.

    CR 205.2a lists the card types; a protection quality states them in the
    plural ("protection from instants"), so the trailing "s" comes off before
    the lookup.
    """
    word = quality.strip().lower().removesuffix("s")
    try:
        return Type(word)
    except ValueError:
        return None


class CastRecord(BaseModel):
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
    face: str | None = None
    """The name of the face being cast, for a card with more than one (CR 715.3)."""
    modes: list[int] = Field(default_factory=list)
    """The chosen modes, as their 1-based position on the card (CR 700.2)."""
    mode_targets: list[list[TargetRef]] = Field(default_factory=list)
    """Each chosen mode's own targets (CR 700.2f), aligned by position with
    `modes` - `mode_targets[i]` is what mode `modes[i]` targets."""
    x_value: int = 0
    """The value announced for X (CR 107.3a), which a mode's target count may use."""
    mana_spent: dict[Color, int] = Field(default_factory=dict)
    """How much mana of each colour was spent paying the total cost (CR 601.2h),
    taken from `machines/cost.ManaPayment.spend`. Colourless mana spent on a
    `{C}` symbol or on generic is `Color.COLORLESS`, same as everywhere else in
    this engine. Empty means either no mana was spent, or the spell was cast
    without going through `Casting` at all - the two are indistinguishable here,
    which is why `any_mana_spent` is the question to ask rather than truthiness
    of the dict alone when that distinction matters."""
    kicked: int = 0
    """How many times a kicker cost was paid (CR 702.33d), copied from
    `Casting.kicked`."""

    def mana_of_color_spent(self, color: Color) -> int:
        """How much mana of this colour was spent paying the total cost (CR 601.2h)."""
        return self.mana_spent.get(color, 0)

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


class PreventionShield(BaseModel):
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
    source_quality: str | None = None
    """CR 615.9 / CR 609.7b: only damage from a source with this property.

    "When the source would deal damage, the shield rechecks the source's
    properties. If the properties no longer match, the damage isn't prevented or
    replaced and the shield isn't used up." Rechecking is why the quality is
    stored as a word and matched against the source at damage time rather than
    resolved to a set of objects when the shield was made."""

    combat_only: bool = False
    """CR 510.2: "prevent all *combat* damage"."""

    amount: int = 0
    """What is left of a CR 615.7 shield. Meaningless for the other two kinds."""

    until_end_of_turn: bool = True
    """CR 514.2 ends it in the cleanup step, alongside the marked damage."""

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


class Game(BaseModel):
    """One game of Magic, from the first untap step to somebody winning.

    Holds the four shared zones. The per-player zones - library, hand,
    graveyard, sideboard - belong to each `Player`.
    """

    players: list[Player] = Field(min_length=1)
    turn: TurnMachine | None = None
    shared_zones: dict[Zone, list[StackObject]] = Field(
        default_factory=lambda: {
            Zone.BATTLEFIELD: [],
            Zone.STACK: [],
            Zone.EXILE: [],
            Zone.COMMAND: [],
        }
    )
    priority: PriorityMachine | None = None
    combat: CombatMachine = Field(default_factory=CombatMachine)
    lands_played: dict[str, int] = Field(default_factory=dict)
    winner: str | None = None
    drawn: bool = False
    """Whether the game ended in a draw (CR 104.4a).

    "If all the players remaining in a game lose simultaneously, the game is a
    draw." `check_state_based_actions` sets this when every player still in the
    game would lose at the same state-based-action check: nobody wins (CR 104.2a
    needs a player still in the game) and `winner` stays None, but the game ends
    immediately all the same (CR 104.1), which is why `is_over` reads this too.
    CR 104.5 sends a player the game is a draw for out of the game, so the
    losers still leave and their objects go with them (CR 800.4a).

    Not the whole of CR 104.4: the mandatory-action loop draws (CR 104.4b) have
    no loop machinery behind them, and CR 104.4c's "an effect may state that the
    game is a draw" needs a registry effect to reach, which none has -
    `end_in_draw` is the staging entry for both. The teams variant (CR 104.4d)
    is outside the free-for-all defaults this model plays.
    """

    conceded: list[str] = Field(default_factory=list)
    losers: list[str] = Field(default_factory=list)
    fizzled: list[UUID] = Field(default_factory=list)
    """Spells that were removed from the stack without resolving (CR 608.2b)."""

    pending_triggers: list[AbilityOnStack] = Field(default_factory=list)
    """Abilities that have triggered but are not on the stack yet (CR 603.2, 603.3).

    "The ability doesn't do anything at this point" - it waits here until the
    next time a player would receive priority, which is what
    `put_triggers_on_stack` represents.
    """

    trigger_targets: dict[str, list[TargetRef]] = Field(default_factory=dict)
    """What a triggered ability will target, keyed by its source's card name.

    CR 603.3d: choosing a trigger's targets is part of putting it on the stack,
    and follows the same rules as CR 601.2c-d. There is no player here to ask,
    so a scenario says in advance what a given card's trigger aims at.
    """

    targeting_notices: list[TargetingNotice] = Field(default_factory=list)
    """One entry per triggered ability whose targets could not be worked out
    normally (`Game._ask_trigger_targets`) - either the restriction itself was
    unreadable, or it was read fine but nothing on the battlefield satisfies
    it right now. Both leave the ability on the stack with no targets
    (CR 603.3d's outcome is unchanged either way); this is only the record of
    which of the two happened, so a gap in the parser stays visible instead of
    looking identical to a legal "nothing to target"."""

    intervening_if_notices: list[InterveningIfNotice] = Field(default_factory=list)
    """One entry per triggered ability whose intervening *if* clause
    (CR 603.4) could not be evaluated. `intervening_if_holds` fails such a
    clause closed - the ability does not trigger - and records it here rather
    than leaving that indistinguishable from a clause that was read and found
    false."""

    mode_notices: list[ModeNotice] = Field(default_factory=list)
    """One entry per chosen mode of a resolving modal spell (CR 700.2a) whose
    text `resolve_modal_spell` could not read into an effect - the same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps, so a mode that silently does nothing is not indistinguishable
    from one that legitimately has nothing left to do."""

    cost_modifier_notices: list[CostModifierNotice] = Field(default_factory=list)
    """One entry per permanent whose static cost-modifying text
    (`static_cost_modifiers_for`) could not be read - Grand Arbiter Augustin
    IV's controller-relative "Spells your opponents cast cost {1} more to
    cast" is the example neither `cost_modifier_effect`'s shapes cover. A
    cost increase that silently fails to apply looks identical to ordinary
    play, which is the DDR#978 defect this is written against; recording it
    here keeps the gap visible instead."""

    anaphoric_clause_notices: list[AnaphoricClauseNotice] = Field(default_factory=list)
    """One entry per "<verb> target X. Its/that X's controller ..." effect
    whose anaphoric second sentence (CR 400.7) could not be read - Solitude's
    own defect: it used to exile a legally-targeted creature and gain no life
    at all, with nothing anywhere recording that the second sentence had gone
    unread. The same unreadable-is-not-the-same-as-no-effect record every
    other notice list here keeps."""

    imprint_notices: list[ImprintNotice] = Field(default_factory=list)
    """One entry per "you may exile a `<quality>` card ... from your hand"
    effect (CR 207.2c's "Imprint" ability word among them) whose stated
    quality could not be read - Ugin's Labyrinth's own defect: its imprint
    trigger used to resolve offering no decision at all, with nothing anywhere
    recording that a choice had gone unoffered. The same unreadable-is-not-
    the-same-as-no-effect record every other notice list here keeps."""

    conditional_clause_notices: list[ConditionalClauseNotice] = Field(default_factory=list)
    """One entry per "you may sacrifice `<restriction>`. If you do,
    `<consequence>`." effect (CR 118.12) whose restriction or consequence
    could not be read - Disciple of Freyalise's and Sanctum of Ugin's own
    defect before this list existed: both used to resolve offering no choice
    at all, with nothing anywhere recording that a choice had gone unoffered.
    The same unreadable-is-not-the-same-as-no-effect record every other
    notice list here keeps."""

    delayed_clause_notices: list[DelayedClauseNotice] = Field(default_factory=list)
    """One entry per delayed-trigger clause (CR 603.7) whose timing this wave
    recognised but whose antecedent or verb it still could not read - Phelia,
    Exuberant Shepherd's own defect before this list existed: its attack
    trigger exiled a legal target and never returned it, with nothing
    recording that the second and third sentences had gone unread. Postmortem
    Lunge and Nahiri, the Harbinger's -8 land here too: both name a delayed
    return, but off an antecedent (a variable-mana-value reanimation target, a
    search result) this wave does not yet capture."""

    evasion_notices: list[EvasionNotice] = Field(default_factory=list)
    """One entry per attacker whose own "can't be blocked" restriction text
    (CR 509.1a) `combat.block_refusal` could read as an attempt at the shape
    but not fully parse - a plain "can't be blocked" and "can't be blocked by
    creatures with power N or less" are the only two read; anything else
    fails closed here instead of a block silently going through unrestricted,
    the same unreadable-is-not-the-same-as-no-effect record every other
    notice list here keeps."""

    undefined_power_notices: list[UndefinedPowerNotice] = Field(default_factory=list)
    """One entry per creature `combat._power_of` was asked to assign combat
    damage for but could not compute a power for - a printed `*` with no
    characteristic-defining ability the engine reads. `power or 0` used to
    fold that into a real 0 rather than record the gap; now the creature
    assigns no combat damage for the step and this is why, the same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps."""

    spells_cast_this_turn: dict[str, list[CardState]] = Field(default_factory=dict)
    """Every spell each player has cast this turn, keyed by controller
    (CR 601.2a marks the casting event; `put_on_stack` records it here).
    Feeds Damping Sphere's per-spell cost increase and
    `_first_spell_this_turn_holds`'s "first [type] spell you've cast this
    turn" intervening *if* clauses. Cleared when a new turn begins."""

    life_gained_this_turn: set[str] = Field(default_factory=set)
    """Which players have gained life this turn (CR 119.9 treats any source
    of the gain the same way). `Player.gain_life` is the single place a life
    total actually goes up, so it is recorded there rather than only at
    `Game.gain_life`'s call site - a direct gain (an effect, a cost paid with
    life the other way) used to leave this unrecorded. Feeds Ocelot Pride's
    "you gained life this turn" intervening *if*. Cleared when a new turn
    begins."""

    activations: dict[str, int] = Field(default_factory=dict)
    """How often each ability has been activated this turn, keyed
    `"<permanent id>:<ability index>"`, for CR 602.5b restrictions such as
    "Activate only once each turn". Cleared when a new turn begins."""

    loyalty_activations: dict[str, int] = Field(default_factory=dict)
    """How often a loyalty ability of each permanent has been activated this
    turn, keyed by permanent id, for CR 606.3's once-per-turn rule - which is
    per permanent, not per ability: "but only if no player has previously
    activated a loyalty ability of that permanent that turn". Any of a
    planeswalker's loyalty abilities having been activated refuses the next
    one. Cleared when a new turn begins."""

    blocks_triggered: list[str] = Field(default_factory=list)
    """The blocker/attacker pairs that have already fired their block triggers
    this combat, so re-declaring the same block does not trigger twice."""

    continuous_effects: ContinuousEffects = Field(default_factory=ContinuousEffects)
    """Every continuous effect a resolving spell or ability has created (CR 611.2).

    A static ability's effect (CR 611.3b) is rebuilt from the battlefield every
    time and needs no storage. This kind outlives the object that made it, so
    the game has to write it down. `machines/layers.py` owns the store and the
    timestamps (CR 613.7a, 613.7b); this is where it lives.

    Two calls keep it honest, and both are in this file: `note` stamps each
    permanent as it enters (CR 613.7a), and `end_the_turn` ends the "until end
    of turn" effects in the cleanup step (CR 514.2).
    """

    delayed_triggers: DelayedTriggers = Field(default_factory=DelayedTriggers)
    """Delayed triggered abilities waiting for their event (CR 603.7).

    Not printed on any card, so `machines/triggers.py` cannot find them; they
    are created by a resolution and watch `Game.emit` for the event they were
    told to wait for. See `machines/delayed.py`.
    """

    cast_records: dict[UUID, "CastRecord"] = Field(default_factory=dict)
    """How each spell now on the stack was cast, keyed by its id (CR 601.2b).

    Several rules ask a question about *how* a spell was cast rather than about
    what it is: CR 702.34a exiles a card whose flashback cost was paid,
    CR 715.3d exiles a spell that was cast as an Adventure, CR 702.185a's warp
    creates its delayed trigger only "if this spell's warp cost was paid", and
    CR 700.2c makes a modal spell's targets depend on the modes announced.

    `Casting` knows all four and the `CardState` it puts on the stack carries
    none of them, so the answer is recorded here by `note_cast`.
    """

    decisions: DecisionScript = Field(default_factory=DecisionScript)
    """The answers a caller has queued for questions asked during resolution.

    CR 608.2d: "If an effect of a spell or ability offers any choices other than
    choices already made as part of casting the spell ... the player announces
    these while applying the effect." There is no player agent here and there is
    deliberately not going to be one, so a caller says in advance what it wants -
    which scry keeps what on top, whether the shockland's 2 life is paid - and
    `Game.ask` matches each answer to the question when it is asked.

    Unanswered questions fall through to `machines/decisions.default_answer`,
    whose table is written down in that module rather than improvised per card.
    """

    shuffle_seed: int = 0
    """The seed every shuffle in this game derives from (CR 701.24a).

    "To shuffle a library or a face-down pile of cards, randomize the cards
    within it so that no player knows their order." Randomize, not "make
    unpredictable to the program": a seeded shuffle satisfies the rule and keeps
    a scenario reproducible, which an unseeded one would not. The seed is mixed
    with `shuffles_performed` so the second shuffle of a game differs from the
    first, and a game replayed from the same seed shuffles identically.
    """

    shuffles_performed: int = 0
    """How many shuffles this game has done, counting up (CR 701.24e, 701.24f).

    Both rules turn on a shuffle having *happened* rather than on it having
    changed anything: a library of zero or one cards still shuffles, and two
    simultaneous shuffles are two shuffles. Nothing triggers on a shuffle yet,
    so this is the only record that one occurred.
    """

    prevention_shields: list["PreventionShield"] = Field(default_factory=list)
    """Prevention effects created by a resolving spell or ability (CR 615.1).

    Distinct from `machines/replacement.py`'s registry, which holds the
    prevention effects that are *static abilities* of permanents on the
    battlefield (CR 609.7c) and are rebuilt from the board every time. These
    outlive their source and have a duration, so the game writes them down -
    the same reason `continuous_effects` is a field.
    """

    _dealing_combat_damage: bool = False
    """True only while a combat damage step is running (CR 510.2).

    Damage reaches `deal_damage` as a target and a number, with nothing to say
    where it came from, so this is how a prevention effect limited to *combat*
    damage tells the two apart."""

    automatic_turn_based_actions: bool = True
    """Whether `advance` performs the step's turn-based actions itself (CR 703.3).

    On by default, because the rules say these happen automatically and a game
    that does not draw is not a game. Turning it off is for scenario tests that
    want to drive a single mechanic by hand without the engine acting around
    them - notably a board built with an empty library, whose owner would
    otherwise lose to CR 704.5b the moment `advance` reached the draw step.

    `Game.turn_based_actions` is always callable directly, and
    `Scenario.manual_turn_based_actions()` turns this off for one scenario.
    Note that `Scenario.start_at` walks the turn machine directly and never
    fires turn-based actions, whatever this is set to.
    """

    def model_post_init(self, _context: object) -> None:
        usernames = [player.username for player in self.players]
        for player in self.players:
            # CR 701.9a's discard has to be able to consult the game, because
            # CR 702.35a's madness replaces where the discarded card lands. A
            # `Player` on its own has nothing to ask; this is the back-reference
            # that lets `Player.discard` find the rules. Excluded from the
            # serialised model, so it cannot make the game state cyclic.
            player.game = self
        if self.turn is None:
            self.turn = TurnMachine(players=usernames)
        if self.priority is None:
            self.priority = PriorityMachine(players=usernames)

    @property
    def is_over(self) -> bool:
        """A game with a winner is over, and so is a drawn one (CR 104.1)."""
        return self.winner is not None or self.drawn

    @property
    def battlefield(self) -> list[CardState]:
        """The shared battlefield. Only cards ever live here, never abilities."""
        return self.shared_zones[Zone.BATTLEFIELD]  # type: ignore[return-value]

    @property
    def stack(self) -> list[StackObject]:
        """The stack, top last. Holds spells (cards) and abilities (CR 405.1)."""
        return self.shared_zones[Zone.STACK]

    @property
    def spells_on_stack(self) -> list[CardState]:
        """Just the spells: a card on the stack is a spell, an ability is not (CR 112.1)."""
        return [item for item in self.stack if isinstance(item, CardState)]

    @property
    def abilities_on_stack(self) -> list[AbilityOnStack]:
        return [item for item in self.stack if isinstance(item, AbilityOnStack)]

    @property
    def exile(self) -> list[CardState]:
        return self.shared_zones[Zone.EXILE]  # type: ignore[return-value]

    @property
    def stack_is_empty(self) -> bool:
        return not self.stack

    @property
    def active_player(self) -> Player:
        assert self.turn is not None
        return self.player(self.turn.active_player)

    def player(self, username: str) -> Player:
        for player in self.players:
            if player.username == username:
                return player
        raise KeyError(f"no player named {username}")

    @property
    def players_in_game(self) -> list[Player]:
        """Everyone who has not yet lost or conceded (CR 104.3a, 104.5)."""
        return [player for player in self.players if self.is_in_game(player.username)]

    def is_in_game(self, username: str) -> bool:
        """True while this player is still playing.

        A player who has conceded or lost leaves the game immediately, and is
        no longer something a spell can affect: a player who concedes leaves
        the game immediately (CR 104.3a), a player who loses leaves too
        (CR 104.5), and their objects leave with them (CR 800.4a).
        """
        return (
            any(player.username == username for player in self.players)
            and username not in self.conceded
            and username not in self.losers
        )

    def can_cast_sorcery(self, username: str) -> bool:
        assert self.turn is not None
        return self.turn.can_cast_sorcery(self.stack_is_empty, username)

    def permanents_controlled_by(self, username: str) -> list[CardState]:
        """Battlefield permanents this player controls.

        A permanent with no controller set counts as the active player's, so a
        one-player scenario does not have to label every card.
        """
        return [
            state
            for state in self.battlefield
            if state.controller == username or state.controller is None
        ]

    def _controlled_land_types(self, controller: str) -> frozenset[str]:
        """Land subtypes (CR 205.3i) this player controls, as single words.

        Feeds `ManaAbility.resolve`'s conditional "If you control an Urza's
        Mine and an Urza's Power-Plant, ..." clauses. CR 305.5: "Land
        subtypes are always a single word", which is why `Card.subtypes`
        already reads "Urza's Mine" as the two words "Urza's" and "Mine" -
        the same words `machines/abilities.py` reads off the condition's own
        printed sentence - so nothing further needs parsing here.
        """
        return frozenset(
            subtype
            for state in self.permanents_controlled_by(controller)
            if state.card.is_land
            for subtype in state.card.subtypes
        )

    def untap_step(self) -> None:
        """Untap everything the active player controls (CR 502.3).

        The turn has begun by now, so anything the active player already
        controls stops being summoning sick (CR 302.6).

        CR 502.3 untaps them "all simultaneously", but each permanent that
        untaps is its own event (CR 603.2c: an ability triggers each time its
        trigger event occurs), so "Whenever this creature becomes untapped"
        (CR 701.26b) fires once per tapped permanent, not once for the batch.
        A permanent that was already untapped is not untapped by this step -
        only tapped permanents can be untapped (CR 701.26b) - and so triggers
        nothing.
        """
        active = self.active_player
        self.begin_turn_for(active.username)
        controlled = self.permanents_controlled_by(active.username)
        tapped = [state for state in controlled if state.tapped]
        active.untap_all(controlled)
        for state in tapped:
            self.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_UNTAPPED,
                    subject_id=state.id,
                    subject_name=state.name,
                    subject_controller=state.controller,
                    subject_card=state.card,
                    player=state.controller,
                )
            )

    # -- turn-based actions (CR 703) ---------------------------------------

    def empty_mana_pools(self) -> None:
        """Empty every player's mana pool (CR 500.5, 703.4q).

        "As a step or phase ends ... any unspent mana left in a player's mana
        pool empties." A turn-based action: automatic, controlled by no player,
        and never on the stack. The player is said to lose this mana (CR 106.4).
        Replacement effects that keep mana from being lost this way (Horizon
        Stone and friends) are not modelled.
        """
        for player in self.players:
            player.mana_pool.empty()

    def turn_based_actions(self) -> None:
        """Perform the turn-based actions of the step that has just begun (CR 703.3).

        These happen automatically, are controlled by no player (CR 703.2), and
        do not use the stack (CR 703.1). CR 703.3 puts them before state-based
        actions and before anybody would receive priority, which is the order
        `advance` runs them in.

        What is implemented here, from the CR 703.4 list:

        - **CR 703.4c / 502.3** - the untap step untaps the active player's
          permanents.
        - **CR 703.4d / 504.1** - the draw step draws a card, unless this is the
          first turn of a two-player game and the active player played first
          (CR 103.8a).
        - **CR 703.4i / 508.1** - the declare attackers step asks the active
          player which creatures attack, and at whom (`declare_attackers_step`).
        - **CR 703.4j / 509.1** - the declare blockers step asks each defending
          player, in turn order (CR 802.4), which creatures block
          (`declare_blockers_step`).
        - **CR 703.4k / 510.1** - the combat damage step deals the assigned
          damage.
        - **CR 703.4n / 514.1** - the cleanup step discards down to maximum hand
          size.
        - **CR 703.4p / 514.2** - then removes all damage marked on permanents.
        - **CR 703.4q / 500.5** - as each step or phase ends, mana pools empty
          (`empty_mana_pools`, run at every boundary `advance` and `advance_to`
          cross; a step-end action, unlike the step-begin ones above).

        Everything else on the CR 703.4 list needs a mechanic this model does
        not have - see `docs/engine-coverage.md`.
        """
        assert self.turn is not None
        if not self.is_in_game(self.turn.active_player):
            # CR 800.4j: the turn runs to its end without an active player, so
            # there is nobody to untap, draw, attack, block, or discard.
            return
        step = self.turn.step
        if step is Step.UNTAP:
            self.untap_step()
        elif step is Step.DRAW:
            self.draw_step()
        elif step is Step.DECLARE_ATTACKERS:
            self.declare_attackers_step()
        elif step is Step.DECLARE_BLOCKERS:
            self.declare_blockers_step()
        elif step is Step.COMBAT_DAMAGE:
            self.combat_damage()
        elif step is Step.CLEANUP:
            self.cleanup_step()

    def declare_attackers_step(self) -> None:
        """The declare attackers step's turn-based action (CR 703.4i, 508.1).

        CR 508.1: "First, the active player declares attackers. This
        turn-based action doesn't use the stack." CR 508.1a: "The active player
        chooses which creatures that they control, if any, will attack." The
        question is put through `machines/decisions.py` like the mulligan
        declaration is, and an unscripted player declares nobody - "if any"
        makes that legal.

        The declaration is a single whole: `declare_attackers` refuses it if any
        creature in it may not attack, and puts the abilities that triggered on
        attackers being declared onto the stack once the whole attack is
        declared (CR 508.2b), before the priority round `advance` runs next (CR
        508.2: "Second, the active player gets priority").

        CR 508.8 then skips the rest of the combat phase when nobody was
        declared as attacking; `advance` handles that, so the step that began
        here always runs, and is the one combat step that never skips.
        """
        assert self.turn is not None
        attacks = ask_attackers(self.decisions, self.turn.active_player, prompt="declare attackers")
        if attacks:
            self.declare_attackers(attacks)

    def declare_blockers_step(self) -> None:
        """The declare blockers step's turn-based action (CR 703.4j, 509.1).

        CR 509.1: "First, the defending player declares blockers. This
        turn-based action doesn't use the stack." CR 509.1a: "The defending
        player chooses which creatures they control, if any, will block." With
        more than one of them, CR 802.4: "each defending player in APNAP order
        declares blockers as the declare blockers step begins". Every attack
        names its defender, so the question goes to each player defending
        against at least one attack, in `_turn_order_from_active` order - CR
        101.4's APNAP order, which starts at the active player and so visits
        the defenders in the order the rule names.

        The declarations are judged as one whole (CR 509.1's declaration rules
        - which is what lets menace work at all) once every answer is in, and
        `declare_blockers` puts the block triggers on the stack before the
        priority round `advance` runs next (CR 509.2a: "Any abilities that
        triggered on blockers being declared ... are put onto the stack before
        the active player gets priority").
        """
        attackers_by_defender: dict[str, list[UUID]] = {}
        for attack in self.combat.attacks:
            defender = combat_rules.defending_player(self, attack)
            attackers_by_defender.setdefault(defender, []).append(attack.attacker_id)

        blocks: list[tuple[CardState, CardState]] = []
        for username in self._turn_order_from_active():
            if username not in attackers_by_defender:
                continue
            blocks.extend(
                ask_blockers(
                    self.decisions,
                    username,
                    prompt="declare blockers",
                    attackers=tuple(attackers_by_defender[username]),
                )
            )
        if blocks:
            self.declare_blockers(blocks)

    def draw_step(self) -> list[CardState]:
        """The active player draws a card (CR 504.1, 703.4d).

        Drawing from a library that cannot supply the card is not an error: the
        player draws what is there and loses at the next state-based check
        (CR 104.3c, 704.5b).
        """
        assert self.turn is not None
        if self.turn.skips_draw():
            return []
        return self.draw_cards(self.active_player, 1)

    def cleanup_step(self) -> list[CardState]:
        """The cleanup step's two turn-based actions, in order (CR 514.1, 514.2).

        First the active player discards down to their maximum hand size
        (CR 703.4n). Then, as one simultaneous event (CR 703.4p), CR 514.2
        happens: "all damage marked on permanents (including phased-out
        permanents) is removed and all 'until end of turn' and 'this turn'
        effects end."

        Both halves are performed here, in that order, because they are one
        turn-based action rather than two - which is also why "until end of
        turn" outlasts the end step and only stops in cleanup.

        A prevention shield with a "this turn" duration ends in the same
        sentence: CR 615.3 gives a prevention effect a duration and CR 514.2
        ends every "this turn" effect here, so an unused shield stops existing
        rather than carrying into the next turn.
        """
        discarded = self.active_player.discard_to_maximum_hand_size()
        self.remove_all_damage()
        self.continuous_effects.end_the_turn()  # CR 514.2, the other half
        self.prevention_shields = [
            shield
            for shield in self.prevention_shields
            if not shield.spent and not shield.until_end_of_turn
        ]
        return discarded

    def remove_all_damage(self) -> None:
        """Wipe damage marked on every permanent (CR 514.2, 703.4p)."""
        for permanent in self.battlefield:
            permanent.damage = 0

    def begin_turn_for(self, username: str) -> None:
        """This player's turn has begun, so their permanents lose summoning sickness.

        "Continuously since their most recent turn began" (CR 302.6) is a
        one-way door per turn: everything they control right now has been here
        since the turn began, by definition.

        CR 800.4m: an "until [a player's] next turn" effect "will last until
        that turn would have begun" - the same moment, so any effect keyed to
        this player's next turn ends here too (Karn, the Great Creator's +1).
        """
        for permanent in self.permanents_controlled_by(username):
            permanent.summoning_sick = False
        self.continuous_effects.end_for_next_turn(username)

    def can_activate_tap_ability(self, permanent: CardState) -> bool:
        """Whether a `{T}` ability of this permanent may be activated (CR 302.6).

        Only creatures are affected: a land or an artifact taps the turn it
        arrives. Haste turns the restriction off (CR 702.10c).
        """
        if not permanent.is_creature:
            return True
        return not permanent.summoning_sick or has_keyword(permanent, Keyword.HASTE)

    def note_cast(
        self,
        spell: CardState,
        *,
        keyword: str | None = None,
        face: str | None = None,
        modes: list[int] | None = None,
        mode_targets: list[list[TargetRef]] | None = None,
        x_value: int = 0,
        mana_spent: dict[Color, int] | None = None,
        kicked: int = 0,
    ) -> "CastRecord":
        """Record how a spell was cast, for the rules that ask afterwards.

        CR 601.2b is where a caster announces an alternative cost, a face, and
        the modes; the `CardState` that reaches the stack carries none of that.
        Five rules need it later:

        - **CR 702.34a** - "If the flashback cost was paid, exile this card
          instead of putting it anywhere else any time it would leave the
          stack."
        - **CR 702.185a** - warp's delayed trigger exists only "if this spell's
          warp cost was paid".
        - **CR 715.3d** - "Instead of putting a spell that was cast as an
          Adventure into its owner's graveyard as it resolves, its controller
          exiles it."
        - **CR 700.2c** - which targets a modal spell has depends on the modes
          chosen, which CR 608.2b then rechecks.
        - **CR 700.2f** - "Modal spells ... may have different targeting
          requirements for each mode", so each mode keeps its own slice of
          what was targeted rather than one flat list shared by all of them.
        - **CR 601.2h / CR 702.33d** - what mana was spent paying the total
          cost, and whether a kicker cost was among the costs paid; both are
          read afterwards by `machines/triggers.intervening_if_holds`.

        `machines/casting.py` calls this as the spell goes on the stack. A spell
        cast without going through a `Casting` has no record and is treated as
        cast plainly, which is exactly right.
        """
        record = CastRecord(
            keyword=keyword,
            face=face,
            modes=list(modes or []),
            mode_targets=[list(slice_) for slice_ in mode_targets or []],
            x_value=x_value,
            mana_spent=dict(mana_spent or {}),
            kicked=kicked,
        )
        self.cast_records[spell.id] = record
        return record

    def cast_record(self, spell: StackObject) -> "CastRecord":
        """How this spell was cast, or an empty record if nobody said."""
        if isinstance(spell, CardState):
            found = self.cast_records.get(spell.id)
            if found is not None:
                return found
        return CastRecord()

    def was_cast_with(self, spell: StackObject, keyword: str) -> bool:
        """Whether this spell was cast using the named keyword (CR 601.2b)."""
        used = self.cast_record(spell).keyword
        return used is not None and used.lower() == keyword.lower()

    def put_on_stack(self, card_state: CardState, controller: str) -> CardState:
        """Put a spell onto the stack. The stack's last entry is its top.

        Refused for a token that has left the battlefield (CR 111.8). A token is
        not a card and can never be cast (CR 111.6), so this only ever matters
        for an effect that would move one onto the stack.
        """
        if move_refused(card_state, Zone.STACK) is not None:
            return card_state
        # Exile and the command zone are modelled as shared, not per-player
        # (`shared_zones`, not `owner.zones`) - a card foretold, plotted, or
        # exiled by an Adventure sits there, and was left behind (duplicated
        # onto the stack) when only the player's own zones were searched.
        self._take_out_of_every_zone(card_state)

        card_state.controller = controller
        card_state.move_to(Zone.STACK)
        if card_state not in self.stack:
            self.stack.append(card_state)
        self.spells_cast_this_turn.setdefault(controller, []).append(card_state)

        # CR 601.2a: the card is now a spell on the stack, so the casting event
        # has happened and anything watching for it triggers (CR 603.2).
        self.emit(
            GameEvent(
                event=TriggerEvent.CAST_SPELL,
                subject_id=card_state.id,
                subject_name=card_state.name,
                subject_controller=controller,
                subject_card=card_state.card,
                player=controller,
            )
        )
        # CR 117.3c gives priority straight back to the caster, so this is the
        # "next time a player would receive priority" of CR 603.3 - a cast
        # trigger goes on the stack above the spell that caused it.
        self.put_triggers_on_stack()
        return card_state

    def resolve_top(self) -> StackObject:
        """Resolve the top of the stack (CR 608).

        A spell's effect happens, then permanents land on the battlefield and
        everything else goes to its controller's graveyard. An ability resolves
        through `_resolve_ability` instead, because CR 608.2n removes it from the
        stack rather than putting it anywhere.

        An Aura is a permanent spell too, but CR 608.3c gives it one more step
        than "enters the battlefield": it enters *attached* to whatever it was
        targeting, so `_aura_attachment` re-resolves that target and
        `enter_the_battlefield` is asked to attach it in the same event, not
        afterwards - see both docstrings.

        State-based actions are checked afterwards and anything that triggered is
        put on the stack, since both happen before any player next receives
        priority (CR 704.3, 603.3).
        """
        if self.stack_is_empty:
            raise ValueError("the stack is empty")

        top = self.stack.pop()
        if isinstance(top, AbilityOnStack):
            return self._resolve_ability(top)

        spell = top
        if self.spell_fizzles(spell):
            # CR 608.2b: it does not resolve. None of its effects happen, not
            # even the untargeted ones, and it is put into its owner's
            # graveyard straight from the stack.
            self.fizzled.append(spell.id)
            self.put_into_graveyard(spell)
            # Same cleanup as the successful path below: nothing further on
            # this route will read what was announced for this spell, and
            # `machines/triggers._cast_record_for_clause` now fails an
            # intervening *if* closed rather than misreading a lingering
            # record as "nothing was spent" once it is gone.
            self.cast_records.pop(spell.id, None)
            self._before_priority()
            return spell

        # CR 712.8c/712.8f: a double-faced spell on the stack has only the
        # characteristics of the face that's up - `oracle_text` already reads
        # that face, but `spell.card.oracle_text` is the raw Scryfall field,
        # which Scryfall leaves null for `modal_dfc`/`transform` layouts (the
        # text lives on `card_faces` instead). Reading it directly here made
        # every modal-DFC spell side (Shatterskull Smashing, Valakut
        # Awakening, Sink into Stupor, Turntimber Symbiosis) resolve to
        # nothing, since `effect_text` came back empty.
        effect = effect_for(spell.name, spell.oracle_text)
        if effect is not None:
            effect(self, spell)

        if spell.is_permanent:
            # CR 608.3, 608.3a: a resolving permanent spell "becomes a permanent
            # and enters the battlefield under the control of the spell's
            # controller". It was cast, so Containment Priest does not catch it.
            if "Aura" in spell.subtypes:
                attachment = self._aura_attachment(spell)
                if attachment is None:
                    # Not fizzled (that was checked above), yet nothing to
                    # attach to - a shape `machines/targeting.py` cannot fully
                    # read for this Aura. CR 608.3c gives it nothing to enter
                    # attached to, and letting it land unattached would only
                    # have CR 704.5m destroy it a moment later - so it does not
                    # enter at all, the same fail-closed policy as the fizzle
                    # branch just above.
                    self.targeting_notices.append(
                        TargetingNotice(
                            kind=TargetingNoticeKind.NO_LEGAL_TARGET,
                            source_id=spell.id,
                            source_name=spell.name,
                            text=spell.oracle_text,
                        )
                    )
                    self.put_into_graveyard(spell)
                    self.cast_records.pop(spell.id, None)
                    self._before_priority()
                    return spell
            else:
                attachment = None
            self.enter_the_battlefield(
                spell,
                spell.controller or self.active_player.username,
                was_cast=True,
                attach_to=attachment,
            )
            self._create_resolution_delayed_triggers(spell)
        else:
            # CR 614.1: the move to the graveyard is an event like any other, so
            # it goes through the replacement effects. That is the hook
            # CR 702.34a's flashback exile and CR 715.3d's Adventure exile hang
            # off - both replace where the card goes as it leaves the stack.
            self.put_into_graveyard(spell)

        self.cast_records.pop(spell.id, None)
        self._before_priority()
        return spell

    def create_delayed_trigger(self, trigger: DelayedTrigger) -> DelayedTrigger:
        """Create a delayed triggered ability (CR 603.7, 603.7a).

        The way in for `machines/effects.py`: a resolving spell or ability that
        says something will happen later builds one of these instead of doing it
        now. CR 603.7a is emphatic that the moment matters - "a delayed
        triggered ability won't trigger until it has actually been created, even
        if its trigger event occurred just beforehand" - so this is called
        during the resolution, not before it.

        CR 603.7d/e make the controller the controller of the spell or ability
        that created it, taken as that spell or ability resolved. The caller
        fills that in, because only the caller knows which it was.
        """
        return self.delayed_triggers.create(trigger)

    def _create_resolution_delayed_triggers(self, spell: CardState) -> None:
        """Delayed triggered abilities a resolving permanent spell creates (CR 603.7a).

        CR 608.3g: "If the object that's resolving has a static ability that
        functions on the stack and creates a delayed triggered ability, that
        delayed triggered ability is created as that permanent is put onto the
        battlefield." So this runs *after* `enter_the_battlefield`, and the
        object the ability refers to is the permanent, not the spell.

        Two keywords need it. CR 702.185a: "Warp represents two static
        abilities that function while the card with warp is on the stack, one
        of which may create a delayed triggered ability. ... 'If this spell's
        warp cost was paid, exile the permanent this spell becomes at the
        beginning of the next end step.'" CR 702.109a's dash is the same
        shape with a different verb: "If this spell's dash cost was paid,
        return the permanent this spell becomes to its owner's hand at the
        beginning of the next end step."

        CR 603.7d/e give the ability the creating spell's source and its
        controller as it resolved, which is what is recorded here.
        """
        if self.was_cast_with(spell, "Warp"):
            self.delayed_triggers.create(
                DelayedTrigger(
                    text=(
                        "Exile the permanent this spell becomes at the "
                        "beginning of the next end step."
                    ),
                    effect="warp:exile",
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.END_STEP,
                    controller=spell.controller or self.active_player.username,
                    source_id=spell.id,
                    source_name=spell.name,
                    subject_id=spell.id,
                    expected_zone=Zone.BATTLEFIELD,  # CR 603.7c
                    expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                )
            )
        if self.was_cast_with(spell, "Dash"):
            self.delayed_triggers.create(
                DelayedTrigger(
                    text=(
                        "Return the permanent this spell becomes to its "
                        "owner's hand at the beginning of the next end step."
                    ),
                    controller=spell.controller or self.active_player.username,
                    source_id=spell.id,
                    source_name=spell.name,
                    subject_id=spell.id,
                    expected_zone=Zone.BATTLEFIELD,  # CR 603.7c
                    expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.END_STEP,
                    callback=return_subject_to_hand,
                )
            )

    def _resolve_ability(self, ability: AbilityOnStack) -> AbilityOnStack:
        """Resolve an ability that was on the stack (CR 608.2).

        Two things can stop the effect happening:

        - **CR 608.2b** - if every target it chose is now illegal, it does not
          resolve at all.
        - **CR 608.2a** - an intervening *if* clause (CR 603.4) is checked again
          here; if it is false "the ability is removed from the stack and does
          nothing".

        Either way **CR 608.2n** applies: "As the final part of an ability's
        resolution, the ability is removed from the stack and ceases to exist."
        An ability is not a card (CR 405.1), so it goes to no zone - not even a
        graveyard - and its source is irrelevant by now (CR 113.7a).
        """
        if self.spell_fizzles(ability):
            self.fizzled.append(ability.id)
        elif self._intervening_if_still_true(ability):
            delayed = self.delayed_triggers.trigger_for(ability)
            if delayed is not None:
                # CR 603.7: a delayed triggered ability's effect is not printed
                # anywhere, so it comes from `machines/delayed.py` rather than
                # from the registry keyed on the source card's text.
                run = self.delayed_triggers.effect_for(ability)
                if run is not None:
                    run(self, ability, delayed)
            else:
                effect = self._effect_of(ability)
                if effect is not None:
                    effect(self, ability)

        self.delayed_triggers.discard(ability)  # CR 608.2n: it ceases to exist
        self._before_priority()
        return ability

    def _effect_of(self, ability: AbilityOnStack) -> object | None:
        """The scripted effect of an ability, or None if nobody has written one.

        A **keyword** ability is asked about first. `machines/effects.py` is keyed
        by `(card name, event)` and `(card name, index)`, and a CR 702 keyword
        ability belongs to no card name - cycling is the same ability on every
        card that prints it, and so are equip, ward, prowess, cascade, persist and
        madness. `machines/keywords.keyword_effect_for` answers for both kinds:
        an activated one through the `KeywordActivation` that put it on the stack
        (CR 602.2), a triggered one through `TriggeredAbility.keyword`
        (CR 603.2). Returning None there means no keyword owns the ability and
        the card-name registries are the right place to look.

        Asked *here* rather than anywhere else, a keyword ability's effect goes
        through the ordinary CR 608.2 resolution path with everything that
        implies: CR 608.2b's target recheck, CR 608.2a's intervening *if*, and
        CR 608.2n's removal from the stack.
        """
        keyword = keyword_effect_for(ability)
        if keyword is not None:
            return keyword
        if isinstance(ability.ability, TriggeredAbility) and ability.ability.event is not None:
            return trigger_effect_for(
                ability.source_name, ability.ability.event, ability.ability.effect
            )
        if isinstance(ability.ability, ActivatedAbility):
            index = self._activated_index(ability)
            if index is not None:
                return activated_effect_for(ability.source_name, index, ability.ability.effect)
        return None

    def _activated_index(self, ability: AbilityOnStack) -> int | None:
        source = ability.source(self)
        card = source.card if source is not None else None
        if card is None:
            return None
        for index, printed in enumerate(activated_abilities_of(card)):
            if printed.text == ability.ability.text:
                return index
        return None

    def _intervening_if_still_true(self, ability: AbilityOnStack) -> bool:
        """CR 608.2a: recheck the intervening *if* as the ability resolves.

        A trigger whose source has left is checked as true, because the clause is
        usually about the source and there is nothing left to read it against -
        and CR 113.7a says the ability resolves regardless of what happened to
        its source.

        `ability.event` is threaded through here because a non-self-referential
        "it" - Vexing Bauble's "Whenever a player casts a spell, if no mana was
        spent to cast it" - means the *cast spell*, not Vexing Bauble. Without
        the event, `_cast_record_for_clause` falls back to `game.cast_record`
        of the ability's own source, which is the wrong object for exactly the
        clause shape this recheck exists to handle.
        """
        printed = ability.ability
        if not isinstance(printed, TriggeredAbility) or not printed.intervening_if:
            return True
        source = ability.source(self)
        if source is None:
            return True
        return intervening_if_holds(self, printed, source, ability.event)

    # -- events and triggered abilities (CR 603) ---------------------------

    def _enters_event(self, permanent: CardState) -> GameEvent:
        return GameEvent(
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
            subject_id=permanent.id,
            subject_name=permanent.name,
            subject_controller=permanent.controller,
            subject_card=permanent.card,
            player=permanent.controller,
        )

    def emit(self, event: GameEvent) -> list[AbilityOnStack]:
        """Something happened; work out what it triggered (CR 603.2).

        Nothing goes on the stack here. The abilities that triggered wait in
        `pending_triggers` until the next time a player would receive priority,
        which is CR 603.3 to the letter.

        Which objects are asked depends on the event. Normally it is everything
        on the battlefield. A cast trigger also asks the spells on the stack, so
        "When you cast this spell" can see itself. A dies trigger also asks the
        permanent that just left, because CR 603.10a has those triggers look
        back in time - and so do the other two events on that list, a permanent
        being sacrificed and a spell being countered (CR 603.10e), whose
        subjects have also moved by the time the trigger is worked out.
        """
        sources: list[CardState] = list(self.battlefield)
        if event.event is TriggerEvent.CAST_SPELL:
            sources = self.spells_on_stack + sources
        elif (
            event.event
            in (
                TriggerEvent.DIES,
                TriggerEvent.IS_SACRIFICED,
                TriggerEvent.SPELL_IS_COUNTERED,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
            )
            and event.subject_id is not None
        ):
            gone = self.find_by_id(event.subject_id)
            if isinstance(gone, CardState) and gone not in sources:
                sources = [*sources, gone]

        triggered = triggers_for(self, event, sources)
        # CR 603.7: a delayed triggered ability is not printed on any card, so
        # no source can be asked for it. It watches the event directly, and once
        # it has triggered it is an ordinary trigger in every other respect -
        # CR 603.3 puts it on the stack the next time a player would receive
        # priority, alongside these.
        triggered = triggered + self.delayed_triggers.fire(event)
        self.pending_triggers.extend(triggered)
        return triggered

    def put_triggers_on_stack(self) -> list[AbilityOnStack]:
        """Put everything that has triggered onto the stack (CR 603.3, 603.3b).

        CR 603.3b orders them: "each player, in APNAP order, puts each triggered
        ability they control on the stack in any order they choose". The active
        player goes first, so the active player's trigger sits *lowest* and
        resolves *last*. Within one player's abilities the order they triggered
        in is kept - the rules leave that choice to the player, and a fixed order
        is what makes a scenario reproducible.

        Targets are chosen here, not when the ability triggered (CR 603.3d).

        A `choose_trigger_targets` answer is consumed by this one batch and no
        other: it is thrown away once every waiting ability has had its turn,
        so a later, separate trigger sharing the same source name (a second
        cast of the same card, or an unrelated delayed trigger printed on the
        same card) is asked fresh rather than inheriting a stale answer.
        """
        if not self.pending_triggers:
            return []
        assert self.turn is not None

        waiting, self.pending_triggers = self.pending_triggers, []
        waiting = [item for item in waiting if self.is_in_game(item.controller)]  # CR 800.4d
        ordered = apnap_order(waiting, self._turn_order_from_active())
        for ability in ordered:
            ability.targets = list(self._targets_for_trigger(ability))
            self.stack.append(ability)
        for ability in ordered:
            self.trigger_targets.pop(ability.source_name, None)
            self.trigger_targets.pop(ability.source_name.split("//")[0].strip(), None)
        return ordered

    def _targets_for_trigger(self, ability: AbilityOnStack) -> list[TargetRef]:
        """What this triggered ability targets, as it goes on the stack (CR 603.3d).

        A scripted `choose_trigger_targets(card_name, ...)` answer wins outright
        - it is keyed by name rather than by ability instance on purpose, so
        two simultaneous triggers sharing a name (Ugin, Eye of the Storms'
        pair of "when you cast this spell" lines) both see it. Nothing
        scripted falls through to `_ask_trigger_targets`, which asks this
        ability *instance*, addressed to its own controller.
        """
        front = ability.source_name.split("//")[0].strip()
        if ability.source_name in self.trigger_targets:
            return self.trigger_targets[ability.source_name]
        if front in self.trigger_targets:
            return self.trigger_targets[front]
        return self._ask_trigger_targets(ability)

    def _ask_trigger_targets(self, ability: AbilityOnStack) -> list[TargetRef]:
        """Ask a triggered ability's own controller for its targets (CR 603.3d).

        "The remainder of the process for putting a triggered ability on the
        stack is identical to the process for casting a spell listed in rules
        601.2c-601.2d" - so this is CR 601.2c's target announcement, put to
        `ability.controller` through the ordinary `Game.ask` `CHOOSE_TARGETS`
        question, with the legal candidates worked out by
        `TargetRequirement.rejects` - the same checker `activate_ability` and
        `choose_trigger_targets` already use.

        Two things can leave this with no targets and something to say about
        why, recorded on `targeting_notices` rather than silently returned as
        if nothing were amiss (the DDR#978-shaped defect: an ability that
        does nothing looks identical to one with nothing to point at):

        - the restriction itself could not be read at all
          (`TargetingProfile.understood` is False) - `TargetingNoticeKind.UNPARSED`;
        - it was read fine, but nothing on the battlefield satisfies it right
          now - `TargetingNoticeKind.NO_LEGAL_TARGET`, a legal game state
          (CR 608.2d's own "nobody says otherwise" default), not a bug.

        An ability with no targeting requirement at all is not asked anything
        and gets no notice either - there is nothing to be silent about.
        """
        printed = ability.ability
        text = printed.text if isinstance(printed, TriggeredAbility) else ""
        profile = profile_for_text(text)
        if not profile.understood:
            self.targeting_notices.append(
                TargetingNotice(
                    kind=TargetingNoticeKind.UNPARSED,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=text,
                )
            )
            return []
        if not profile.requirements:
            return []

        candidates = self._legal_target_candidates(profile, ability.controller, ability.source_id)
        if not candidates:
            self.targeting_notices.append(
                TargetingNotice(
                    kind=TargetingNoticeKind.NO_LEGAL_TARGET,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=text,
                )
            )
            return []

        decision = Decision(
            kind=DecisionKind.CHOOSE_TARGETS,
            player=ability.controller,
            prompt=f"choose targets for {ability.source_name}",
            source=ability.source_name,
            targets=tuple(TargetRef.coerce(candidate) for candidate in candidates),
            target_maximum=profile.max_targets,
        )
        chosen = self.ask(decision)
        assert isinstance(chosen, (list, tuple))
        return list(chosen)

    def _legal_target_candidates(
        self, profile: TargetingProfile, controller: str, source_id: UUID | None
    ) -> list[Targetable]:
        """Every object or player `profile` could legally land on right now.

        Used only to tell CR 608.2d's "nothing satisfies the restriction"
        apart from "the restriction could not be read" - not a full
        target-choosing implementation, so every legal candidate is returned
        rather than just the first, letting the caller (a live decision, or
        this file's own notice check) pick among them.
        """
        seen: set[UUID] = set()
        candidates: list[Targetable] = []
        for zone_cards in self.shared_zones.values():
            for state in zone_cards:
                if isinstance(state, CardState) and state.id not in seen:
                    seen.add(state.id)
                    candidates.append(state)
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    if state.id not in seen:
                        seen.add(state.id)
                        candidates.append(state)
        if profile.requirements and any(r.allows_players for r in profile.requirements):
            candidates.extend(self.players)
        return [
            candidate
            for candidate in candidates
            if any(
                requirement.rejects(candidate, controller, self, source_id) is None
                for requirement in profile.requirements
            )
        ]

    def choose_trigger_targets(self, card_name: str, targets: list[object]) -> None:
        """Say what a card's triggered ability will target when it goes on the stack.

        CR 603.3d: choosing a trigger's targets is part of putting the ability
        on the stack and "follows the rules for announcing targets" - which is
        CR 601.2c, the same check a spell's targets get. So the choice is
        refused here rather than recorded and discovered to be illegal later:
        `machines/targeting.py` reads the ability's own text through
        `profile_for_text`, because `targeting_profile` answers for the *spell*
        and drops the lines belonging to an ability (CR 113.1c).

        A card with no readable targeting ability is not checked, the same way
        an unreadable spell is not - see `docs/engine-coverage.md`.
        """
        refusal = self.why_cannot_target_with_trigger(card_name, targets)
        if refusal is not None:
            raise ValueError(refusal)
        self.trigger_targets[card_name] = [TargetRef.coerce(target) for target in targets]

    def why_cannot_target_with_trigger(self, card_name: str, targets: list[object]) -> str | None:
        """Why this card's trigger could not target those, or None (CR 601.2c, 603.3d).

        The source is found by name among the objects that can carry a trigger -
        the battlefield and the stack - because `trigger_targets` is keyed by
        name and there is no ability object yet at the time a scenario says what
        it will aim at.

        A card may print more than one targeting trigger. The announcement names
        the card, not the ability, so the targets are legal if *any* of its
        triggers would accept them; the first reason is reported when none do.
        """
        source = self._trigger_source_named(card_name)
        if source is None:
            return None
        controller = self.controller_of(source).username

        # `parse_abilities` rather than `triggers_for`'s `triggered_abilities_of`,
        # which keeps only the six trigger conditions the matcher recognises. A
        # trigger the matcher cannot read still announces targets, and Guide of
        # Souls' "Whenever you attack" is exactly that case.
        printed = [
            ability
            for ability in parse_abilities(source.card)
            if isinstance(ability, TriggeredAbility)
        ]
        reasons: list[str] = []
        for ability in printed:
            profile = profile_for_text(ability.text)
            if not profile.understood or not profile.requirements:
                continue
            try:
                profile.check(list(targets), controller, self, source_id=source.id)
            except ValueError as refusal:
                reasons.append(str(refusal))
            else:
                return None
        return reasons[0] if reasons else None

    def _trigger_source_named(self, card_name: str) -> CardState | None:
        """The object a named card's trigger would come from, if it is here.

        CR 603.6a puts an enters-the-battlefield trigger's source on the
        battlefield; a cast trigger's source is the spell on the stack
        (CR 603.2g). Both are searched, front face first, matching how
        `_targets_for_trigger` reads the same key back out.
        """
        front = card_name.split("//")[0].strip()
        for state in [*self.battlefield, *self.spells_on_stack]:
            if state.name in (card_name, front) or state.name.split("//")[0].strip() == front:
                return state
        return None

    def _turn_order_from_active(self) -> list[str]:
        """Every player, starting with the active player (CR 101.4, APNAP order)."""
        assert self.turn is not None
        players = list(self.turn.players)
        start = self.turn.active_index % len(players)
        return [players[(start + offset) % len(players)] for offset in range(len(players))]

    def _check_state_based_actions_and_stack_triggers(self) -> list[CardState]:
        """CR 704.3, then CR 603.3: the pair that precedes every "would receive
        priority" moment, not only a fresh step.

        CR 704.3: "Whenever a player would get priority ... the game checks for
        any of the listed conditions for state-based actions ... then performs
        all applicable state-based actions simultaneously ... This process
        repeats". CR 117.3c is exactly such a moment for the player who just
        cast a spell or activated an ability - they receive priority right back
        - so `retain_priority` calls this too, not only a step change or a
        resolution. A land drop uses no stack and never hands priority
        anywhere (CR 116.2a), so nothing changes for the player who played it
        until they next pass, which `pass_priority` covers by calling this
        before `PriorityMachine` acts on the pass.
        """
        gone = self.check_state_based_actions()
        self.put_triggers_on_stack()
        return gone

    def _before_priority(self) -> None:
        """Everything that happens before a player would receive priority.

        CR 704.3 checks state-based actions first, then CR 603.3 puts anything
        that has triggered onto the stack, and only then does `PriorityMachine`
        hand priority out.
        """
        self._check_state_based_actions_and_stack_triggers()
        if self.priority is not None:
            self.priority.reset()

    def _take_out_of_every_zone(self, card_state: CardState) -> None:
        """Lift a card out of wherever it currently is, shared zones included."""
        for player in self.players:
            for zone_cards in player.zones.values():
                if card_state in zone_cards:
                    zone_cards.remove(card_state)
        for zone_cards in self.shared_zones.values():
            if card_state in zone_cards:
                zone_cards.remove(card_state)

    def enter_the_battlefield(
        self,
        card_state: CardState,
        controller: str,
        *,
        tapped: bool = False,
        was_cast: bool,
        attach_to: "Targetable | None" = None,
    ) -> CardState:
        """A permanent enters the battlefield, replacement effects first (CR 614.12).

        Every route onto the battlefield runs through here: a permanent spell
        resolving, a land being played, a card put there by an effect. CR 614.1c
        and 614.1d make "[this] enters tapped", "[this] enters with N counters",
        and "[objects] enter ..." replacement effects, and CR 614.12 says such an
        effect "may come from the permanent itself if [it affects] only that
        permanent" - so the entering card's own text is consulted while it is
        still on its way in, alongside every effect already on the battlefield.

        A replacement may send it somewhere else entirely (Containment Priest).
        CR 614.6: the entering event then never happens, so nothing enters, no
        enters-the-battlefield ability triggers (CR 603.6a), and the counters and
        the tapped state the modified event was carrying are dropped with it.

        `attach_to` is CR 608.3c's half of the same event: a resolving Aura
        spell "becomes a permanent and is put onto the battlefield under the
        control of the spell's controller attached to the player or object it
        was targeting" - attached as it enters, not mutated afterwards, which is
        why it is applied here rather than by the caller. That is also what
        keeps a Containment Priest redirect honest: if the replacement above
        sends the event to exile or a graveyard instead, `event.destination` is
        no longer `Zone.BATTLEFIELD` and this returns before `attach_to` is ever
        touched, so nothing is left attached to something that never arrived.
        `resolve_top` is the caller, and it is the only one that passes this -
        every other route onto the battlefield leaves it `None` and this is a
        no-op, exactly the old behaviour.

        CR 303.4d says an Aura can't enchant itself, and if it somehow does
        anyway, "the Aura is put into its owner's graveyard" rather than the
        engine raising out of the middle of a spell's resolution - targeting
        already keeps this from happening in practice (an Aura spell cannot
        legally target itself), but the fallback is here so a caller that
        manages to ask for it fails onto a real rule instead of a crash.

        Counters the permanent arrives with are placed after it is on the
        battlefield, through `add_counters`, because CR 122.6 counts them as
        counters being put on the object and effects such as Doubling Season
        watch for exactly that - CR 616.1g's second event inside the first.

        CR 111.8 refuses the whole thing for a token that has already been to the
        battlefield and left: "it remains in its current zone instead". Nothing
        enters, so no replacement effect is consulted and no enters trigger fires
        (CR 603.6a) - the event never happened at all.
        """
        if move_refused(card_state, Zone.BATTLEFIELD) is not None:
            return card_state

        event = ReplaceableEvent(
            kind=EventKind.ENTERS_BATTLEFIELD,
            card=card_state,
            origin=card_state.zone,
            destination=Zone.BATTLEFIELD,
            tapped=tapped,
            was_cast=was_cast,
        )
        card_state.controller = controller
        apply_replacements(self, event)

        if event.destination is not Zone.BATTLEFIELD:
            self._take_out_of_every_zone(card_state)
            if event.destination is Zone.EXILE:
                card_state.move_to(Zone.EXILE)
                self.exile.append(card_state)
            else:
                self._owner_of(card_state).add(card_state, event.destination or Zone.GRAVEYARD)
            return card_state

        if (
            attach_to is not None
            and isinstance(attach_to, CardState)
            and attach_to.id == card_state.id
        ):
            # CR 303.4d: an Aura can't enchant itself - see the docstring above.
            self._take_out_of_every_zone(card_state)
            self._owner_of(card_state).add(card_state, Zone.GRAVEYARD)
            return card_state

        self._take_out_of_every_zone(card_state)
        card_state.move_to(Zone.BATTLEFIELD)
        card_state.tapped = event.tapped
        self.battlefield.append(card_state)

        if attach_to is not None:
            card_state.attach_to(attach_to)  # CR 608.3c, 701.3a

        # CR 613.7a: "a continuous effect generated by a static ability has the
        # same timestamp as the object the static ability is on". Stamped as it
        # arrives, so a permanent that entered after a spell resolved is
        # correctly newer than that spell's effect (CR 613.7b).
        self.continuous_effects.note(self.battlefield)

        for kind, amount in event.counters.items():
            self.add_counters(card_state, kind, amount)

        self.emit(self._enters_event(card_state))
        return card_state

    def put_onto_battlefield(
        self, card_state: CardState, controller: str, *, tapped: bool = False
    ) -> CardState:
        """Put a card onto the battlefield without casting it (CR 110.2a).

        This is the Tooth and Nail path. CR 601.2 defines casting as taking a
        card "from where it is (usually the hand), put it on the stack, and pay
        its costs" - a card put straight onto the battlefield never does any of
        that, so no casting event occurs and CR 603.2's "an ability triggers only
        if its trigger event actually occurs" (CR 603.2g) means a "when you cast
        this spell" ability never fires. Enters-the-battlefield abilities do
        (CR 603.6a), because that event *did* happen.
        """
        return self.enter_the_battlefield(card_state, controller, tapped=tapped, was_cast=False)

    # -- decisions made during resolution (CR 608.2d) -------------------------

    def ask(self, decision: Decision) -> object:
        """Put one question to a player and get the answer back (CR 608.2d).

        "If an effect of a spell or ability offers any choices other than
        choices already made as part of casting the spell, activating the
        ability, or otherwise putting the spell or ability on the stack, the
        player announces these while applying the effect. The player can't
        choose an option that's illegal or impossible."

        That second sentence is enforced here and is the reason this is a method
        rather than a lookup: a scripted answer naming an illegal option is
        refused with the rule that makes it illegal, and an absent answer falls
        through to `default_answer`, which never returns one.

        A question whose only option is "no" - the shockland at 1 life, where
        CR 119.4 forbids the payment - has its answer forced rather than chosen.
        It is still recorded in `decisions.asked`, with
        `affirmative_is_legal` False, because "there was nothing to decide" is a
        fact a scenario may want to assert.

        A scripted answer always wins; only once none matches is a live
        `decisions.provider` (if one is set) consulted, and only once that
        also has nothing - `NOT_ANSWERED`, or no provider at all - does
        `default_answer` speak for the player.
        """
        self.decisions.asked.append(decision)
        allowed = legal_options(decision)
        found, value = self.decisions.take(decision)
        if not found and self.decisions.provider is not None:
            provided = self.decisions.provider.decide(decision)
            if provided is not NOT_ANSWERED:
                found, value = True, provided
        if not found:
            return default_answer(decision)

        if decision.kind in (DecisionKind.MAY, DecisionKind.PAY_LIFE):
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
            if value not in allowed:
                raise ValueError(
                    f"{decision.prompt}: that option is illegal, so CR 608.2d "
                    f"does not allow choosing it"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_CARDS:
            if not isinstance(value, tuple) or not all(isinstance(v, UUID) for v in value):
                raise ValueError(f"{decision.prompt}: needs a tuple of chosen card ids")
            offered = set(decision.cards)
            stray = [str(card_id) for card_id in value if card_id not in offered]
            if stray:
                raise ValueError(
                    f"{decision.prompt}: cannot choose a card that was not offered: "
                    f"{', '.join(stray)}"
                )
            if len(value) != decision.amount:
                raise ValueError(
                    f"{decision.prompt}: needs {decision.amount} card(s) chosen, {len(value)} given"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_TARGETS:
            if not isinstance(value, (tuple, list)):
                raise ValueError(f"{decision.prompt}: needs a tuple of targets")
            chosen = [TargetRef.coerce(target) for target in value]
            legal = set(decision.targets)
            stray = [str(ref) for ref in chosen if ref not in legal]
            if stray:
                raise ValueError(f"{decision.prompt}: not a legal target: {', '.join(stray)}")
            if decision.target_maximum is not None and len(chosen) > decision.target_maximum:
                raise ValueError(
                    f"{decision.prompt}: too many targets chosen, at most "
                    f"{decision.target_maximum} (CR 115.6)"
                )
            return chosen

        if not isinstance(value, CardSplit):
            raise ValueError(f"{decision.prompt}: needs a CardSplit answer")
        looked_at = set(decision.cards)
        stray = [str(card_id) for card_id in value.moved if card_id not in looked_at]
        if stray:
            raise ValueError(
                f"{decision.prompt}: cannot move a card that was not looked at "
                f"(CR 701.22a, CR 701.25a): {', '.join(stray)}"
            )
        return value

    def ask_cleanup_discard(self, player: Player, needed: int) -> list[CardState]:
        """Which cards a player discards to their maximum hand size (CR 514.1).

        CR 701.9b: "By default, effects that cause a player to discard a card
        allow the affected player to choose which card to discard" - the
        cleanup discard is such an effect, so this is a `CHOOSE_CARDS`
        question through `Game.ask`, the same CR 608.2d machinery every other
        discard-a-card choice in `machines/effects.py` uses.

        The hand is offered in hand order, so `default_answer`'s "back of the
        offered cards" lands on the actual back of the hand - the behaviour
        `Player.discard_to_maximum_hand_size` had before this question existed.
        """
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"discard {needed} card(s) to maximum hand size",
            amount=needed,
            cards=tuple(state.id for state in player.hand),
        )
        chosen_ids = self.ask(decision)
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in player.hand}
        return [by_id[card_id] for card_id in chosen_ids]

    def may(self, player: Player | str, prompt: str, *, source: str | None = None) -> bool:
        """A plain "you may" during resolution (CR 608.2d).

        Both branches are always legal, so this is the one question where the
        default - take it - is a genuine deviation rather than the only answer.
        """
        username = player if isinstance(player, str) else player.username
        answer = self.ask(
            Decision(kind=DecisionKind.MAY, player=username, prompt=prompt, source=source)
        )
        return bool(answer)

    def may_pay_life(self, player: Player | str, amount: int, *, source: str | None = None) -> bool:
        """ "You may pay N life", asked and then paid (CR 119.4, CR 608.2d).

        CR 119.4: "If a cost or effect allows a player to pay an amount of life
        greater than 0, the player may do so only if their life total is greater
        than or equal to the amount of the payment. If a player pays life, the
        payment is subtracted from their life total; in other words, the player
        loses that much life."

        So the affirmative is *illegal* below that life total, not merely a bad
        idea, and CR 608.2d then forbids choosing it - which is how a shockland
        fetched at 1 life enters tapped without anybody deciding anything.
        CR 119.4b: "Players can always pay 0 life", whatever the total.

        Returns whether the life was paid, and pays it.
        """
        if isinstance(player, str):
            player = self.player(player)
        payable = amount <= 0 or player.life >= amount
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_LIFE,
                player=player.username,
                prompt=f"pay {amount} life",
                source=source,
                amount=amount,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        if amount > 0:
            player.lose_life(amount)
        return True

    def _look_at_top(self, player: Player, count: int) -> list[CardState]:
        """The top `count` cards, or as many as there are (CR 701.22a, 701.25a)."""
        return list(player.library[: max(count, 0)])

    def _split_top(
        self,
        player: Player,
        looked_at: list[CardState],
        answer: CardSplit,
    ) -> tuple[list[CardState], list[CardState]]:
        """Work an answer out into (moved away, put back on top), in order.

        "The rest on top of your library in any order" (CR 701.22a, CR 701.25a):
        an order the answer may state and, if it does not, the order they were
        looked at in - which keeps a rigged library rigged when the scenario
        did not ask for anything else.
        """
        by_id = {state.id: state for state in looked_at}
        moved = [by_id[card_id] for card_id in answer.moved if card_id in by_id]
        moved_ids = {state.id for state in moved}
        rest = [state for state in looked_at if state.id not in moved_ids]
        if answer.top_order is not None:
            ranked = {card_id: index for index, card_id in enumerate(answer.top_order)}
            rest.sort(key=lambda state: ranked.get(state.id, len(ranked)))
        return moved, rest

    def scry(self, player: Player | str, count: int, *, source: str | None = None) -> CardSplit:
        """Scry N (CR 701.22a).

        "To 'scry N' means to look at the top N cards of your library, then put
        any number of them on the bottom of your library in any order and the
        rest on top of your library in any order."

        CR 701.22b: "If a player is instructed to scry 0, no scry event occurs."
        So scry 0 asks nothing and this returns an empty split without recording
        a question - which is the only way a scenario can tell the two apart.

        CR 701.22c orders a simultaneous multi-player scry in APNAP order; no
        card in the pool scries more than one player at a time, so that path is
        not exercised. CR 701.22d's "whenever a player scries" trigger has no
        event to emit yet - see `docs/engine-coverage.md`.
        """
        if isinstance(player, str):
            player = self.player(player)
        if count <= 0:
            return CardSplit()

        looked_at = self._look_at_top(player, count)
        answer = self.ask(
            Decision(
                kind=DecisionKind.SCRY,
                player=player.username,
                prompt=f"scry {count}",
                source=source,
                amount=count,
                cards=tuple(state.id for state in looked_at),
            )
        )
        assert isinstance(answer, CardSplit)
        to_bottom, on_top = self._split_top(player, looked_at, answer)
        library = player.library
        for state in looked_at:
            library.remove(state)
        for index, state in enumerate(on_top):
            library.insert(index, state)
        library.extend(to_bottom)
        return CardSplit(
            moved=tuple(state.id for state in to_bottom),
            top_order=tuple(state.id for state in on_top),
        )

    def surveil(self, player: Player | str, count: int, *, source: str | None = None) -> CardSplit:
        """Surveil N (CR 701.25a).

        "To 'surveil N' means to look at the top N cards of your library, then
        put any number of them into your graveyard and the rest on top of your
        library in any order."

        The same shape as a scry with a different destination, so it asks the
        same question - and CR 701.25c mirrors CR 701.22b exactly: surveil 0 is
        no surveil event at all.

        The cards go to the graveyard through `put_into_graveyard`, so a
        replacement effect watching that move (Rest in Peace, CR 614.1) gets its
        say - a surveil into a graveyard is a card being put into a graveyard.
        """
        if isinstance(player, str):
            player = self.player(player)
        if count <= 0:
            return CardSplit()

        looked_at = self._look_at_top(player, count)
        answer = self.ask(
            Decision(
                kind=DecisionKind.SURVEIL,
                player=player.username,
                prompt=f"surveil {count}",
                source=source,
                amount=count,
                cards=tuple(state.id for state in looked_at),
            )
        )
        assert isinstance(answer, CardSplit)
        to_graveyard, on_top = self._split_top(player, looked_at, answer)
        library = player.library
        for state in looked_at:
            library.remove(state)
        for index, state in enumerate(on_top):
            library.insert(index, state)
        for state in to_graveyard:
            self.put_into_graveyard(state)
        return CardSplit(
            moved=tuple(state.id for state in to_graveyard),
            top_order=tuple(state.id for state in on_top),
        )

    # -- shuffling and searching (CR 701.23, CR 701.24) -----------------------

    def shuffle_library(self, player: Player | str, *, keep: list[CardState] | None = None) -> None:
        """Randomize a player's library (CR 701.24a).

        "To shuffle a library or a face-down pile of cards, randomize the cards
        within it so that no player knows their order."

        CR 701.24b is the reason for `keep`: "Some effects cause a player to
        search a library for a card or cards, shuffle that library, then put
        some or all of the found cards into a different zone or in a certain
        position in that library. In such cases, the found cards aren't included
        in the shuffle, even though they remain in the library at that time.
        Rather, all the cards in that library except those are shuffled." The
        kept cards stay where they are, at the front, and everything else is
        randomized around them.

        The randomness is seeded from `shuffle_seed` and the shuffle count, so
        the shuffle is a real shuffle and the game is still reproducible - which
        CR 701.24a permits, since it asks only that no *player* know the order.

        CR 701.24c-e all say the same thing from different angles: the shuffle
        happens even when there is nothing to shuffle in. A library of zero or
        one cards is shuffled here too, and `shuffles_performed` counts it, so
        CR 701.24e's trigger has something to trigger on when triggers on
        shuffling exist.
        """
        if isinstance(player, str):
            player = self.player(player)
        held = list(keep or [])
        held_ids = {state.id for state in held}
        rest = [state for state in player.library if state.id not in held_ids]
        rng = Random(f"{self.shuffle_seed}:{self.shuffles_performed}")  # noqa: S311
        rng.shuffle(rest)
        player.zones[Zone.LIBRARY] = held + rest
        self.shuffles_performed += 1

    def search_library(
        self,
        player: Player | str,
        matches: Callable[[CardState], bool],
        *,
        count: int = 1,
        optional: bool = False,
        shuffle: bool = True,
        source: str | None = None,
    ) -> list[CardState]:
        """Search a library, take what was found out of it, then shuffle.

        CR 701.23a: "To search for a card in a zone, look at all cards in that
        zone (even if it's a hidden zone) and find a card that matches the given
        description." The whole library is visible to the searcher, which is why
        this takes a predicate over every card rather than looking only at the
        top.

        CR 701.23b is the rule that makes a search a *decision*: "If a player is
        searching a hidden zone for cards with a stated quality ... that player
        isn't required to find some or all of those cards even if they're
        present in that zone." A library is a hidden zone (CR 400.2 lists the
        public ones and the library is not among them), so failing to find is
        always legal. That is what `optional` asks about - and note it is not
        the same question as CR 701.23g's "you *may* search", which the caller
        asks with `Game.may` before calling this at all.

        CR 701.23d is the exception: "If a player is searching a hidden zone
        simply for a quantity of cards, such as 'a card' or 'three cards,' that
        player must find that many cards (or as many as possible ...)." A search
        with no stated quality passes `optional=False` and finds what is there.

        CR 701.23e: nothing is revealed unless the effect says so, so nothing is
        revealed here.

        The cards found are removed from the library and returned; the caller
        decides where they go. The shuffle then happens without them, per
        CR 701.24b - which is the same thing as shuffling before moving them,
        and avoids having to put them back first.
        """
        if isinstance(player, str):
            player = self.player(player)

        found: list[CardState] = []
        for state in list(player.library):
            if len(found) >= count:
                break
            if not matches(state):
                continue
            if optional and not self.may(
                player, f"find {state.card.name} while searching your library", source=source
            ):
                continue
            found.append(state)

        for state in found:
            player.library.remove(state)
        if shuffle:
            self.shuffle_library(player)
        return found

    # -- drawing, life, and counters, as replaceable events ------------------

    def draw_cards(self, player: Player | str, count: int = 1) -> list[CardState]:
        """Draw `count` cards one at a time, replacement effects included.

        CR 121.2: "Cards may only be drawn one at a time. If a player is
        instructed to draw multiple cards, that player performs that many
        individual card draws." Each of those individual draws is its own
        replaceable event (CR 121.6), so Alhammarret's Archive replacing one
        draw with two does not then replace the two it produced - CR 614.5 gives
        each effect one opportunity per event.

        CR 121.6a applies a draw replacement "even if no cards could be drawn
        because there are no cards in the affected player's library", which is
        why the replacement runs before the library is consulted. `draw_up_to`
        then records the failed draw for CR 704.5b.
        """
        if isinstance(player, str):
            player = self.player(player)

        drawn: list[CardState] = []
        for index in range(count):
            event = ReplaceableEvent(
                kind=EventKind.DRAW,
                player=player,
                amount=1,
                draw_step_draw=self._is_draw_step_draw(player) and index == 0,
            )
            apply_replacements(self, event)
            # CR 121.2: each card actually drawn is its own draw, so each is
            # its own trigger event - a replacement that turns one draw into
            # two still produces two events. A draw replaced down to nothing
            # never happened, so it triggers nothing (CR 603.2g).
            for card in player.draw_up_to(event.amount) if event.amount > 0 else []:
                drawn.append(card)
                self.emit(
                    GameEvent(
                        event=TriggerEvent.DRAWS_A_CARD,
                        subject_id=card.id,
                        subject_name=card.name,
                        subject_controller=player.username,
                        subject_card=card.card,
                        player=player.username,
                    )
                )
        return drawn

    def _is_draw_step_draw(self, player: Player) -> bool:
        """Whether this is the active player's draw-step draw (CR 504.1, 703.4d)."""
        assert self.turn is not None
        return self.turn.step is Step.DRAW and self.turn.active_player == player.username

    def gain_life(self, player: Player | str, amount: int) -> int:
        """A player gains life, replacement effects included (CR 119.3).

        "If an effect causes a player to gain life or lose life, that player's
        life total is adjusted accordingly" - and CR 614.1a lets an effect such
        as Alhammarret's Archive replace how much before it is.
        """
        if isinstance(player, str):
            player = self.player(player)
        if amount <= 0:
            return player.life

        event = ReplaceableEvent(kind=EventKind.GAIN_LIFE, player=player, amount=amount)
        apply_replacements(self, event)
        # CR 119.9: a trigger written "Whenever [a player] gains life" is
        # treated as written "Whenever a source causes [a player] to gain
        # life". One event per gain (CR 702.15e makes even simultaneous
        # lifelink sources separate gains), and only if life was actually
        # gained - a gain replaced to zero never happened (CR 603.2g).
        if event.amount > 0:
            player.gain_life(event.amount)
            self.emit(GameEvent(event=TriggerEvent.GAINS_LIFE, player=player.username))
        return player.life

    def add_counters(self, permanent: CardState, kind: str, amount: int = 1) -> int:
        """Put counters on a permanent, replacement effects included (CR 122.1).

        CR 122.6: "Some spells and abilities refer to counters being put on an
        object. This refers to putting counters on that object while it's on the
        battlefield and also to an object that's given counters as it enters the
        battlefield" - so both routes reach the same replaceable event, which is
        what lets Doubling Season double a Kalonian Hydra's four printed counters
        as it arrives.
        """
        if amount <= 0:
            return permanent.counter_count(kind)

        event = ReplaceableEvent(
            kind=EventKind.ADD_COUNTERS, card=permanent, counter_kind=kind, amount=amount
        )
        apply_replacements(self, event)
        if event.amount <= 0:
            return permanent.counter_count(kind)
        return permanent.add_counters(kind, event.amount)

    def return_to_hand(self, permanent: CardState) -> CardState:
        """Return a permanent to its owner's hand (CR 701.19a is "return").

        CR 111.8 refuses this for a token that has already left the battlefield,
        which is the rule that stops a Raise Dead or a flicker effect recurring a
        dead token: "If such a token would change zones, it remains in its
        current zone instead."
        """
        if move_refused(permanent, Zone.HAND) is not None:
            return permanent
        self._take_out_of_every_zone(permanent)
        self.combat.remove(permanent.id)  # CR 506.4
        self._owner_of(permanent).add(permanent, Zone.HAND)
        return permanent

    # -- targeting and effects --------------------------------------------

    def find_by_id(self, card_id: UUID) -> CardState | None:
        """Any card the game can see, by id: battlefield, stack, exile, or a player's zones."""
        for zone_cards in self.shared_zones.values():
            for state in zone_cards:
                if isinstance(state, CardState) and state.id == card_id:
                    return state
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    if state.id == card_id:
                        return state
        return None

    def find_ability_by_id(self, ability_id: UUID) -> AbilityOnStack | None:
        """An activated or triggered ability on the stack, by id (CR 113.1c, 405.1).

        Deliberately separate from `find_by_id`, which answers with a
        `CardState`. An ability is not a card - CR 405.1 puts it on the stack
        "without any card associated with it" - so it exists in exactly one
        place and nowhere else. CR 115.2 makes one a legal target ("Some spells
        and abilities can target abilities on the stack"), and CR 608.2b then
        looks it back up on resolution, which is what this is for.
        """
        for item in self.stack:
            if isinstance(item, AbilityOnStack) and item.id == ability_id:
                return item
        return None

    def resolve_target(self, target: TargetRef) -> "Targetable | AbilityOnStack | None":
        """What a target reference points at now, or None if it is gone.

        A card that has left the zone it was targeted in, and a player who has
        left the game, are both simply not there any more.

        An **ability** on the stack is looked up too (CR 115.2, 113.1c). It has
        no zone list to walk, so `find_by_id` cannot see it; without this a
        `TargetRef` naming one always resolved to nothing and CR 608.2b removed
        the spell or ability that had legally targeted it. Tishana's Tidebinder
        is the card that needs it.
        """
        if target.is_player:
            username = target.username
            if username is None or not self.is_in_game(username):
                return None
            return self.player(username)
        if target.card_id is None:
            return None
        found = self.find_by_id(target.card_id)
        if found is not None:
            return found
        return self.find_ability_by_id(target.card_id)

    def resolve_targets(self, spell: StackObject) -> list[Targetable]:
        """The spell's targets that are still legal on resolution (CR 608.2b).

        Cards and players both, in the order they were chosen. An illegal
        target is skipped and the rest of the spell still happens; it is only
        when *every* target is illegal that the spell does not resolve at all,
        which `resolve_top` checks with `spell_fizzles` before getting here.
        """
        return [
            thing
            for target in spell.targets
            if (thing := self.legal_target(spell, target)) is not None
        ]

    def legal_target(
        self, spell: StackObject, target: TargetRef
    ) -> "Targetable | AbilityOnStack | None":
        """What this target points at, if it is still a legal target (CR 608.2b).

        "A target that's no longer in the zone it was in when it was targeted is
        illegal. Other changes to the game state may cause a target to no longer
        be legal." So a target that has gone is illegal, and so is one the
        spell's own text would no longer accept - a creature that stopped being
        one, or a permanent that changed controller under a "you control" clause.

        Legality is judged by the same parser that checked it at announcement
        (`machines/targeting.py`), so a card whose text the parser cannot read
        is treated as still legal rather than made to fizzle on a guess.

        An **ability** on the stack is checked against its own printed text
        (`ability.ability.text`, the same source `activate_ability` and
        `_ask_trigger_targets` already read with `profile_for_text`) rather
        than a spell's `targeting_profile` - CR 113.1c's ability has no card
        text of its own to look up by name, but it carries its restriction
        right there on the object.
        """
        thing = self.resolve_target(target)
        if thing is None:
            return None

        source_card = self._source_card_of(spell)
        if source_card is not None and self.protection_refusal(thing, source_card) is not None:
            # CR 702.16b, checked again here because protection can be gained
            # after a spell was legally announced.
            return None

        if isinstance(spell, AbilityOnStack):
            profile = profile_for_text(spell.ability.text)
            if not profile.understood or not profile.requirements:
                return thing
            caster = spell.controller
            if any(
                requirement.rejects(thing, caster, self, spell.source_id) is None
                for requirement in profile.requirements
            ):
                return thing
            return None

        profile = self._resolution_profile(spell)
        if not profile.understood or not profile.requirements:
            return thing
        caster = spell.controller or self.active_player.username
        # The game is handed over because not every restriction is a
        # characteristic: CR 109.3 lists what a characteristic is and being in
        # combat is not among them. "Target attacking creature" is answered off
        # `Game.combat` (CR 508.1k, 509.1g), and CR 511.3 taking everything out
        # of combat is exactly the "other changes to the game state may cause a
        # target to no longer be legal" of CR 608.2b.
        if any(
            requirement.rejects(thing, caster, self) is None for requirement in profile.requirements
        ):
            return thing
        return None

    def _resolution_profile(self, spell: CardState) -> "TargetingProfile":
        """What this spell may legally be targeting now (CR 608.2b, 700.2c).

        For an ordinary spell that is simply the card's text. For a **modal**
        one it is not: `targeting_profile` reports `understood=False` for every
        modal card on purpose, because CR 700.2c makes the targets depend on the
        modes - "if a spell or ability targets one or more targets only if a
        particular mode is chosen for it, its controller will need to choose
        those targets only if they chose that mode. Otherwise, the spell or
        ability is treated as though it did not have those targets."

        So the modes announced during casting are read back off `cast_records`
        and `profile_for_modes` is asked instead. Without them the spell stays
        unchecked, which is the old behaviour and the honest one: a modal spell
        whose modes were never recorded cannot be judged.
        """
        record = self.cast_records.get(spell.id)
        if record is not None and record.modes:
            try:
                return profile_for_modes(spell.card, record.modes, record.x_value or None)
            except ValueError:
                # Not a modal card after all; fall through to its plain text.
                pass
        return targeting_profile(spell.card)

    # -- protection (CR 702.16) --------------------------------------------

    def _source_card_of(self, spell: StackObject) -> "Card | None":
        """The card a stack object's protection quality is judged against.

        For a spell that is the card itself; for an ability it is the card the
        ability came from, because CR 702.16b speaks of "abilities from a source
        with the stated quality" rather than of the ability's own type.
        """
        if isinstance(spell, CardState):
            return spell.card
        source = spell.source(self)
        return source.card if source is not None else None

    def protection_refusal(
        self, target: "Targetable | AbilityOnStack", source: "Card"
    ) -> str | None:
        """Why protection stops this source touching this target, or None (CR 702.16b).

        "A permanent or player with protection can't be targeted by spells with
        the stated quality and can't be targeted by abilities from a source with
        the stated quality."

        Only the card-type flavour of the quality is read, because CR 702.16a
        makes that a rule of its own: "If the quality is a card type, subtype, or
        supertype, the ability applies to sources that are permanents with that
        card type, subtype, or supertype and to any sources not on the
        battlefield that are of that card type, subtype, or supertype. This is an
        exception to rule 109.2." Emrakul's "protection from instants" is exactly
        that shape, and an instant is never on the battlefield, so both halves of
        the rule point at the same thing here.

        A quality this engine cannot read is not enforced - see
        `docs/engine-coverage.md`. Protection on a *player* is not modelled at
        all: no card in the pool grants it and `Player` has no text to read.
        """
        if not isinstance(target, CardState):
            return None
        for quality in self._effective_protection_qualities(target):
            card_type = _card_type_named(quality)
            if card_type is not None and card_type in source.types:
                return (
                    f"{target.name} has protection from {quality}, so {source.name} "
                    f"cannot target it (CR 702.16b)"
                )
        return None

    def _effective_protection_qualities(self, target: CardState) -> list[str]:
        """Every quality `target` has protection from right now: its own printed
        text plus anything granted to it by another static ability (CR 613.1f).

        Akroma's Memorial's "creatures you control have ... protection from
        black and from red" is layer 6, not the permanent's own printing, so
        `protection_qualities(target.card)` alone misses it - it only reads
        what `machines/layers.py` left in `Characteristics.abilities` as a
        "Protection from <quality>" line, the same way `combat.has_keyword`
        reads a granted keyword off the same list. A permanent not on the
        battlefield (a spell on the stack, say) has no computed board to ask,
        so only its own printed protection applies there.
        """
        qualities = list(protection_qualities(target.card))
        if target.zone is Zone.BATTLEFIELD:
            try:
                characteristics = self.characteristics_of(target)
            except KeyError:
                characteristics = None
            if characteristics is not None:
                for line in characteristics.abilities:
                    for quality in _qualities_from_text(line):
                        if quality not in qualities:
                            qualities.append(quality)
        return qualities

    def why_cannot_target(self, spell: StackObject, target: Targetable) -> str | None:
        """Why this stack object may not target that, as far as protection goes.

        CR 601.2c chooses targets and CR 608.2b rechecks them; this answers the
        protection half of both questions. `Casting.choose_targets` does not
        consult it yet - `machines/targeting.py` reads the *caster's* text and
        has nothing to say about the target's - so announcement is still
        unchecked and only `legal_target` enforces it. See
        `docs/engine-coverage.md`.
        """
        source = self._source_card_of(spell)
        if source is None:
            return None
        return self.protection_refusal(target, source)

    def spell_fizzles(self, spell: StackObject) -> bool:
        """Whether this spell would be removed from the stack unresolved (CR 608.2b).

        A spell that chose no targets never fizzles - "if the spell or ability
        specifies targets" is the whole condition. One that did fizzles only if
        every one of them is now illegal.
        """
        if not spell.targets:
            return False
        return all(self.legal_target(spell, target) is None for target in spell.targets)

    def _aura_attachment(self, spell: CardState) -> Targetable | None:
        """What a resolving Aura spell attaches to (CR 608.3c, 303.4a).

        An Aura spell's only target is what it will enchant, so once
        `resolve_top` has confirmed the spell did not fizzle (CR 608.2b), at
        least one target is still legal - and CR 702.5a's enchant ability gives
        it exactly one to begin with. This re-resolves it from the
        announcement through `resolve_targets` rather than trusting the id
        `spell.targets` recorded: the creature it named may have died and come
        back as a new object (CR 400.7), or the id may now belong to nothing at
        all, and attaching to a stale reference would just relocate this bug
        instead of fixing it.

        None means the parser could not read something about this Aura's
        targeting well enough to say - `resolve_top` fails closed on that
        rather than putting the Aura onto the battlefield unattached.
        """
        targets = self.resolve_targets(spell)
        return targets[0] if targets else None

    def resolve_card_targets(self, spell: StackObject) -> list[CardState]:
        """Just the card targets, for effects that cannot touch a player."""
        return [thing for thing in self.resolve_targets(spell) if isinstance(thing, CardState)]

    # -- damage and life ---------------------------------------------------

    def deal_damage(
        self, target: Targetable, amount: int, *, source: "CardState | None" = None
    ) -> int:
        """Deal damage to a permanent or a player, and say how much landed.

        Damage to a permanent is marked on it and waits for state-based
        actions; damage to a player causes that much life loss immediately.

        CR 120.1: "An object that deals damage is the source of that damage",
        and CR 120.7 says the source is simply "the object that dealt it". That
        object is `source`, and it is what makes three rules writable that were
        not before:

        - **CR 609.7b** - a prevention or replacement effect that watches for
          damage "from sources with certain properties" rechecks the source when
          the damage would be dealt.
        - **CR 615.8** - "the next time a specific source would deal damage".
        - **CR 702.16e** - "Any damage that would be dealt by sources that have
          the stated quality to a permanent or player with protection is
          prevented."

        It is optional because CR 120.2b's "the spell or ability will specify
        which object deals that damage" is a fact the caller holds, and not
        every caller passes it yet: `machines/combat.py` and
        `machines/effects.py` still call this with a target and a number, so
        their damage arrives anonymous and the three rules above do not fire for
        it. See `docs/engine-coverage.md`.

        Prevention and replacement effects get first refusal (CR 615.1, 616.1).
        CR 615.1a: "Effects that use the word 'prevent' are prevention effects.
        Prevention effects use 'prevent' to indicate what damage will not be
        dealt" - so a prevented event deals zero damage rather than dealing
        damage and undoing it.

        Returns the damage actually dealt, which is what CR 702.2b's deathtouch
        and CR 702.15b's lifelink both key off: zero damage is not damage dealt.
        """
        event = ReplaceableEvent(
            kind=EventKind.DAMAGE,
            card=None if isinstance(target, Player) else target,
            player=target if isinstance(target, Player) else None,
            amount=amount,
            combat=self._dealing_combat_damage,
            source=source,
        )
        apply_replacements(self, event)
        if not event.happens or event.amount <= 0:
            return 0

        if isinstance(target, Player):
            self.deal_damage_to_player(target, event.amount)
        else:
            target.mark_damage(event.amount)
        # CR 120.1: "An object that deals damage is the source of that
        # damage" - the subject is the source, and the player, when there is
        # one, is who the damage went to. A prevention or replacement that
        # stopped the damage entirely has stopped the event too (CR 603.2g).
        self.emit(
            GameEvent(
                event=TriggerEvent.DEALS_DAMAGE,
                subject_id=source.id if source is not None else None,
                subject_name=source.name if source is not None else None,
                subject_controller=source.controller if source is not None else None,
                subject_card=source.card if source is not None else None,
                player=target.username if isinstance(target, Player) else None,
                combat=event.combat,
            )
        )
        return event.amount

    # -- prevention effects with a duration (CR 615) --------------------------

    def create_prevention_shield(self, shield: PreventionShield) -> PreventionShield:
        """Record a prevention effect created by a resolving spell (CR 615.1, 615.4).

        CR 615.4: "Prevention effects must exist before the appropriate damage
        event occurs - they can't 'go back in time' and change something that's
        already happened." Creating the shield *is* the effect; nothing else
        happens when the spell resolves.

        CR 615.3: "There are no special restrictions on casting a spell or
        activating an ability that generates a prevention effect. Such effects
        last until they're used up or their duration has expired."
        """
        self.prevention_shields.append(shield)
        return shield

    def active_prevention_shields(self) -> list[PreventionShield]:
        """The shields that are neither used up nor expired (CR 615.3)."""
        return [shield for shield in self.prevention_shields if not shield.spent]

    def shield_applies(self, shield: PreventionShield, event: ReplaceableEvent) -> bool:
        """Whether this shield would prevent any of this damage (CR 615.7-615.9).

        CR 609.7b: "When the source would deal damage, the 'shield' rechecks the
        source's properties. If the properties no longer match, the damage isn't
        prevented or replaced." That recheck happens here, every time, against
        the source as it is now - not against the source as it was when the
        shield was made.

        A shield that names a source or a source quality never applies to
        anonymous damage: an unknown source is not a source that matches.
        """
        if shield.spent or event.kind is not EventKind.DAMAGE or event.amount <= 0:
            return False
        if shield.combat_only and not event.combat:
            return False
        if shield.card_id is not None and (event.card is None or event.card.id != shield.card_id):
            return False
        if shield.player is not None and (
            event.player is None or event.player.username != shield.player
        ):
            return False
        if shield.source_id is not None and (
            event.source is None or event.source.id != shield.source_id
        ):
            return False
        return not (
            shield.source_quality is not None
            and (
                event.source is None
                or not self.source_has_quality(event.source, shield.source_quality)
            )
        )

    def apply_prevention_shield(self, shield: PreventionShield, event: ReplaceableEvent) -> None:
        """Prevent what this shield prevents, and use it up if it prevented any.

        CR 615.7: "Each 1 damage that would be dealt to the 'shielded' permanent
        or player is prevented. Preventing 1 damage reduces the remaining shield
        by 1 ... Once the shield has been reduced to 0, any remaining damage is
        dealt normally."

        CR 615.8: a next-instance shield "prevents the next instance of damage
        from that source, regardless of how much damage that is."

        CR 609.7b's last sentence is the one that has to be honoured explicitly:
        "If for any reason the shield prevents no damage or replaces no damage,
        the shield isn't used up." So each branch sets `used_up` from what it
        actually prevented.

        CR 615.5 is the last step: "Some prevention effects also include an
        additional effect, which may refer to the amount of damage that was
        prevented. The prevention takes place at the time the original event would
        have happened; **the rest of the effect takes place immediately
        afterward**." `shield.prevented` is what such a rider reads, and it is
        recorded whether or not the shield carries one - a rider that is added
        later has the number waiting for it, and a scenario can assert on how much
        a shield ate without a card that says so.
        """
        prevented = 0
        if shield.kind is ShieldKind.AMOUNT:
            prevented = min(shield.amount, event.amount)
            shield.amount -= prevented
        else:
            prevented = event.amount
            if prevented > 0 and shield.kind is ShieldKind.NEXT_INSTANCE:
                shield.used_up = True
        event.amount -= prevented
        shield.prevented += prevented

        # CR 615.5's "immediately afterward". The life is gained now rather than
        # queued, because the prevention has already taken place - the damage
        # event in hand has had `amount` taken off it and cannot be undone
        # (CR 615.6: "if damage that would be dealt is prevented, it never
        # happens").
        if prevented > 0 and shield.gains_life_when_prevented:
            self.gain_life(shield.controller, prevented)

    def source_has_quality(self, source: CardState, quality: str) -> bool:
        """Whether a damage source has a named property (CR 609.7b, CR 702.16a).

        CR 702.16a: "This quality is usually a color (as in 'protection from
        black') but can be any characteristic value or information ... If the
        quality is a card type, subtype, or supertype, the ability applies to
        sources that are permanents with that card type, subtype, or supertype
        and to any sources not on the battlefield that are of that card type,
        subtype, or supertype. This is an exception to rule 109.2."

        Colours and card types are read; anything else returns False rather than
        being guessed at, and is listed in `docs/engine-coverage.md`.
        """
        wanted = quality.strip().lower()
        card_type = _card_type_named(wanted)
        if card_type is not None:
            return card_type in source.card.types
        color = _COLOR_WORDS.get(wanted)
        if color is not None:
            return color in (source.card.colors or [])
        return False

    def protection_from_damage(self, event: ReplaceableEvent) -> str | None:
        """Why protection prevents this damage, or None (CR 702.16e).

        "Any damage that would be dealt by sources that have the stated quality
        to a permanent or player with protection is prevented."

        Damage with no known source is never prevented here: CR 702.16e asks
        about the source's qualities, and an anonymous source has none to check.
        Protection on a *player* is not modelled - `Player` has no text - so
        only a permanent's protection is read.
        """
        if event.kind is not EventKind.DAMAGE or event.card is None or event.source is None:
            return None
        for quality in self._effective_protection_qualities(event.card):
            if self.source_has_quality(event.source, quality):
                return (
                    f"{event.card.name} has protection from {quality}, so damage from "
                    f"{event.source.name} is prevented (CR 702.16e)"
                )
        return None

    def deal_damage_to_player(self, player: Player | str, amount: int) -> int:
        """Damage dealt to a player causes that much life loss (CR 119.2, 120.3a).

        Losing the game is not part of dealing damage: a player at zero or
        less life loses the next time state-based actions are checked
        (CR 704.5a), which is what `check_state_based_actions` does.

        The life loss is its own event as well (CR 119.3), because a trigger
        watching "a player loses life" fires for loss by damage the same as
        any other loss. A player who loses none triggers nothing.
        """
        if amount < 0:
            raise ValueError("cannot deal negative damage")
        if isinstance(player, str):
            player = self.player(player)
        if amount == 0:
            return player.life
        lost = player.lose_life(amount)
        self.emit(GameEvent(event=TriggerEvent.LOSES_LIFE, player=player.username))
        return lost

    def counter(self, spell: StackObject) -> StackObject:
        """Counter a spell or an ability on the stack: it never resolves (CR 701.6).

        CR 113.9: an activated or triggered ability on the stack is not a spell,
        but it can still be countered by an effect that counters abilities. It
        goes nowhere when it is - there is no card behind it (CR 405.1) - while a
        countered spell is put into its owner's graveyard.

        Countering is a trigger event in its own right (CR 701.6a is the verb,
        CR 603.10e the look back in time), which is why the event is emitted
        after the spell has moved to its graveyard: the subject is found where
        it went, and the trigger reads it as it last existed on the stack.
        """
        if spell not in self.stack:
            raise ValueError(f"{spell.name} is not on the stack")
        self.stack.remove(spell)
        if isinstance(spell, CardState):
            self.put_into_graveyard(spell)
            # Same cleanup `resolve_top` does on every other way off the
            # stack: a countered spell will not be read again through the
            # normal fast-forward paths, and a `CastRecord` this module can no
            # longer answer for now fails an intervening *if* closed
            # (`machines/triggers._cast_record_for_clause`) instead of a
            # lingering record being misread as "nothing was spent".
            self.cast_records.pop(spell.id, None)
        self.emit(
            GameEvent(
                event=TriggerEvent.SPELL_IS_COUNTERED,
                subject_id=spell.id,
                subject_name=spell.name,
                subject_controller=spell.controller,
                subject_card=spell.card if isinstance(spell, CardState) else None,
                player=spell.controller,
            )
        )
        return spell

    def destroy(self, permanent: CardState) -> CardState:
        """Put a permanent into its controller's graveyard.

        CR 700.4: "dies" means "is put into a graveyard from the battlefield", so
        a permanent that was on the battlefield when this was called has died and
        anything watching for that triggers (CR 603.2). CR 603.10a lets the
        permanent itself be one of the things watching, even though it is in the
        graveyard by the time the trigger is worked out.

        The move is a zone change and goes through the replacement effects first
        (CR 614.1, 616.1). A Rest in Peace or a Kalitas that sends the card to
        exile instead means the card never reaches a graveyard, so by CR 700.4 it
        never died and no dies trigger fires (CR 614.6).

        CR 701.8a is what this call *is*: "To destroy a permanent, move it from
        the battlefield to its owner's graveyard." CR 702.12b then refuses it
        outright for a permanent with indestructible - "a permanent with
        indestructible can't be destroyed" - and the permanent stays where it is,
        undamaged in the bookkeeping sense: nothing is moved, nothing dies, no
        trigger fires.

        Note what this does **not** stop, because CR 701.8b draws the line: "The
        only ways a permanent can be destroyed are as a result of an effect that
        uses the word 'destroy' or as a result of the state-based actions that
        check for lethal damage (see rule 704.5g) or damage from a source with
        deathtouch (see rule 704.5h). If a permanent is put into its owner's
        graveyard for any other reason, it hasn't been 'destroyed.'" Sacrificing,
        exiling, bouncing, and CR 704.5f's toughness of 0 or less are not
        destruction and go through `put_into_graveyard` and friends directly.
        """
        if is_indestructible(permanent, self):
            return permanent  # CR 702.12b
        return self.put_into_graveyard(permanent)

    def sacrifice(self, permanent: CardState) -> CardState:
        """Sacrifice a permanent (CR 701.21a).

        "To sacrifice a permanent, its controller moves it from the battlefield
        directly to its owner's graveyard." A player can't sacrifice something
        that isn't a permanent, so anything not on the battlefield is refused.

        Two trigger events are true of one sacrifice, and both fire. The
        permanent is sacrificed - CR 603.10a names "abilities that trigger when
        a player sacrifices a permanent" among those that look back in time,
        and the event is emitted while the permanent is still on the
        battlefield, so its own trigger reads it as it last existed there. And
        the permanent dies - CR 700.4's "dies" means "is put into a graveyard
        from the battlefield", which is exactly where CR 701.21a sends it - so
        the graveyard move goes through `put_into_graveyard`, whose dies event
        fires on arrival. The two are distinct events about one move, which is
        why a Dragon Appeasement and a "when this creature dies" trigger both
        fire for the same sacrifice.
        """
        if permanent not in self.battlefield:
            raise ValueError(f"{permanent.name} is not a permanent on the battlefield")
        self.emit(
            GameEvent(
                event=TriggerEvent.IS_SACRIFICED,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_controller=permanent.controller,
                subject_card=permanent.card,
                player=permanent.controller,
            )
        )
        return self.put_into_graveyard(permanent)

    def put_into_graveyard(self, card_state: CardState) -> CardState:
        """Move a card to its owner's graveyard, replacement effects included.

        Every route to a graveyard runs through here: a destroyed permanent, a
        resolved instant, a countered spell, a spell that fizzled. Each is "a
        card would be put into a graveyard", which is the event Rest in Peace,
        Leyline of the Void, Necrodominance, and Sanctifier en-Vec all watch for
        (CR 400.6, 614.1a).

        A token's *first* trip here is allowed and is the whole of CR 111.7's
        parenthesis - "if a token changes zones, applicable triggered abilities
        will trigger before the token ceases to exist" - so a dying token really
        does reach a graveyard and really does fire its dies trigger (CR 700.4).
        A second trip is refused by CR 111.8.
        """
        if move_refused(card_state, Zone.GRAVEYARD) is not None:
            return card_state

        origin = card_state.zone
        was_on_battlefield = card_state in self.battlefield

        event = ReplaceableEvent(
            kind=EventKind.ZONE_CHANGE,
            card=card_state,
            origin=Zone.BATTLEFIELD if was_on_battlefield else origin,
            destination=Zone.GRAVEYARD,
        )
        apply_replacements(self, event)

        self._take_out_of_every_zone(card_state)
        self.combat.remove(card_state.id)  # CR 506.4

        if event.destination is Zone.GRAVEYARD:
            self._owner_of(card_state).add(card_state, Zone.GRAVEYARD)
        elif event.destination is Zone.EXILE:
            card_state.move_to(Zone.EXILE)
            self.exile.append(card_state)
        else:
            raise ValueError(f"a graveyard replacement sent {card_state.name} nowhere")

        # CR 700.4: it only died if it actually reached a graveyard from the
        # battlefield. Exiled instead, the dies event never happened (CR 614.6).
        if was_on_battlefield and event.destination is Zone.GRAVEYARD:
            self.emit(
                GameEvent(
                    event=TriggerEvent.DIES,
                    subject_id=card_state.id,
                    subject_name=card_state.name,
                    subject_controller=card_state.controller,
                    subject_card=card_state.card,
                    player=card_state.controller,
                )
            )
        return card_state

    def card_imprinted_on(self, permanent_id: UUID) -> CardState | None:
        """The card exiled *with* `permanent_id`, if any (`ExileMarker.IMPRINTED`).

        This is what "exiled with this land" means once it is read off the
        card's own printed text (`machines/effects.py`'s `_parse_imprint_
        clause`) rather than remembered from the plain-English sentence: a
        linear scan of the shared exile zone for the annotation `_parse_
        imprint_clause` left on the exiled card, matched by id rather than by
        object identity so it survives a round trip through persistence.
        Ugin's Labyrinth's own conditional mana ability (`ManaCondition.
        imprinted`) and its "Return the exiled card to its owner's hand"
        ability both call this rather than keeping their own pointer.
        """
        for card in self.exile:
            annotation = card.exile_annotation
            if (
                annotation is not None
                and annotation.marker is ExileMarker.IMPRINTED
                and annotation.linked_permanent_id == permanent_id
            ):
                return card
        return None

    def exile_permanent(self, permanent: CardState) -> CardState:
        """Move a permanent to the shared exile zone.

        Refused for a token that has already left the battlefield (CR 111.8).

        Emits `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE` when the move was
        actually from the battlefield - the "or is put into exile" half of
        CR 701.66a's earthbend, and the general battlefield-to-exile event
        `machines/triggers.py` never had before: `DIES` already exists for the
        battlefield-to-graveyard half of the same idea, but nothing watched
        this one, so a delayed trigger waiting for it had nothing to fire on.
        """
        if move_refused(permanent, Zone.EXILE) is not None:
            return permanent
        was_on_battlefield = permanent in self.battlefield
        self._take_out_of_every_zone(permanent)
        self.combat.remove(permanent.id)  # CR 506.4
        permanent.move_to(Zone.EXILE)
        self.exile.append(permanent)
        if was_on_battlefield:
            self.emit(
                GameEvent(
                    event=TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    player=permanent.controller,
                )
            )
        return permanent

    def check_state_based_actions(self) -> list[CardState]:
        """Apply state-based actions, returning whatever left the battlefield (CR 704).

        CR 704.3 performs every applicable action simultaneously as a single
        event, then checks again, repeating until none apply - which is why
        this loops rather than making one pass.

        What is checked, from the CR 704.5 list:

        - **CR 704.5a** - a player at 0 or less life loses the game.
        - **CR 704.5b** - a player who tried to draw from an empty library since
          the last check loses the game (CR 104.3c).
        - **CR 704.5c** - a player with ten or more poison counters loses.
        - **CR 704.5d** - "If a token is in a zone other than the battlefield, it
          ceases to exist." Not a zone change and not a death: the token is
          simply gone. CR 111.7's parenthesis is what makes the dying token's own
          trigger safe - it triggered while the token was still in the graveyard.
        - **CR 704.5f** - a creature with toughness 0 or less is put into its
          owner's graveyard.
        - **CR 704.5g** - a creature with lethal damage marked on it is destroyed.
        - **CR 704.5h** - "If a creature has toughness greater than 0, and it's
          been dealt damage by a source with deathtouch since the last time
          state-based actions were checked, that creature is destroyed." A
          separate rule from CR 704.5g, with a separate condition: one point of
          deathtouch damage is enough and the amount never enters into it.
        - **CR 704.5i** - "If a planeswalker has loyalty 0, it's put into its
          owner's graveyard." Loyalty is the number of loyalty counters on it
          (CR 306.5c, CR 122.1e), which a loyalty cost removes (CR 606.4) as
          often as it can take the walker to zero.
        - **CR 704.5j** - the legend rule.
        - **CR 704.5m** - "If an Aura is attached to an illegal object or player,
          or is not attached to an object or player, that Aura is put into its
          owner's graveyard." The opposite of CR 704.5n's Equipment, which stays
          on the battlefield. What counts as illegal is read off the Aura's own
          enchant ability by `machines/keywords.aura_state_based_actions`
          (CR 702.5a), so the announcement and the state-based action cannot
          disagree about the same sentence.
        - **CR 704.5n** - "If an Equipment or Fortification is attached to an
          illegal permanent or to a player, it becomes unattached from that
          permanent or player. It remains on the battlefield."
        - **CR 704.5z** - every Role but the newest on one permanent, controlled
          by one player, goes to its owner's graveyard.

        The rest of CR 704.5 needs a mechanic this model does not have: copies
        (704.5e) and battles (704.5v-704.5x). See `docs/engine-coverage.md`.

        Losing is one-way: a player who is gone stays gone even if something
        later adds life back.

        When a check would remove *every* player still in the game at once, the
        game is a draw (CR 104.4a): nobody is left to win (CR 104.2a needs a
        player still in the game), so `drawn` is set and the losers leave under
        CR 104.5 like any other loss. The check that finds the game already
        over does nothing - CR 104.1 ends the game immediately, and a state
        that arrives after the end never happens.
        """
        if self.is_over:
            return []
        gone: list[CardState] = []
        for _ in range(len(self.players) + len(self.battlefield) + 1):
            leaving = self._state_based_actions_once()
            gone.extend(leaving)
            losing = self._losing_players()
            if not leaving and not losing:
                break
            # CR 104.4a: "If all the players remaining in a game lose
            # simultaneously, the game is a draw." `_losing_players` is who one
            # check removes and `players_in_game` is who it found still in the
            # game, so equal sets mean nobody survives to win. A solo game has
            # no draw to hand out, matching `_check_for_a_winner`'s guard.
            remaining = {player.username for player in self.players_in_game}
            if len(self.players) > 1 and losing and set(losing) == remaining:
                self.drawn = True
            for username in losing:
                self._lose_the_game(username)
        self._check_for_a_winner()
        return gone

    # -- what the board actually is (CR 613.5) -----------------------------

    def computed_board(self) -> ComputedBoard:
        """Every permanent's characteristics with every continuous effect applied.

        CR 613.5: "The application of continuous effects as described by the
        layer system is continually and automatically performed by the game. All
        resulting changes to an object's characteristics are instantaneous."
        Recomputed on every call rather than cached, because that is what
        "continually" means: an anthem that left the battlefield a moment ago is
        already not applying.

        `CardState.power` and `.toughness` are the *printed* values plus counters
        (CR 122.1a) and know nothing about layers, so anything in this file that
        needs a real power or toughness asks here instead.

        A `LayerContext` of every graveyard goes with the battlefield, because a
        characteristic-defining ability can be printed on the card it affects
        while counting something the layer engine never sees on its own -
        Tarmogoyf's power (CR 604.3, CR 604.3a, CR 613.4a) counts card types
        "among cards in all graveyards" (CR 300.1), and Boneyard Wurm's counts
        creature cards in its own controller's graveyard only. Without this,
        every such CDA is built against an empty world and reads as if every
        graveyard were empty, whatever is actually in them.
        """
        self.continuous_effects.note(self.battlefield)
        context = LayerContext(
            graveyards=tuple(card for player in self.players_in_game for card in player.graveyard),
            graveyard_by_controller={
                player.username: tuple(player.graveyard) for player in self.players_in_game
            },
        )
        return self.continuous_effects.board(self.battlefield, context)

    def characteristics_of(self, permanent: CardState) -> Characteristics:
        """This permanent's characteristics right now, layers included (CR 613.5)."""
        return self.computed_board().of(permanent)

    def power_of(self, permanent: CardState) -> int | None:
        """This creature's power right now, layers included (CR 613.4, 613.5).

        `machines/combat.py` assigns combat damage equal to a creature's power
        (CR 510.1a) and reads `CardState.power` to get it, which is the printed
        value plus counters. This is the answer that counts an anthem, a
        characteristic-defining ability (CR 604.3, layer 7a), and a switch
        (CR 613.4d).
        """
        return self.characteristics_of(permanent).power

    def toughness_of(self, permanent: CardState) -> int | None:
        """This creature's toughness right now, layers included (CR 613.4, 613.5)."""
        return self.characteristics_of(permanent).toughness

    def _state_based_actions_once(self) -> list[CardState]:
        """One simultaneous round of the permanent-facing state-based actions.

        Toughness is the *computed* toughness (CR 613.5), not the printed value
        plus counters, because both rules are written about the creature as it
        is right now:

        - **CR 704.5f** - "If a creature has toughness 0 or less, it's put into
          its owner's graveyard. Regeneration can't replace this event."
        - **CR 704.5g** - "If a creature has toughness greater than 0, it has
          damage marked on it, and the total damage marked on it is greater than
          or equal to its toughness, that creature has been dealt lethal damage
          and is destroyed."

        That is what lets Elesh Norn's -2/-2 in layer 7c kill a 2/1, and what
        makes three damage on a Giant Spider lethal the moment layer 7d turns it
        into a 4/2. A creature whose computed toughness is not a number - which
        cannot happen once layer 7a has run, but can if the board is
        uncomputable - falls back to the printed value rather than being spared
        on a technicality.

        CR 704.5d runs first, against the board as the check found it: "If a
        token is in a zone other than the battlefield, it ceases to exist." A
        token that one of the actions below kills in *this* round was still on
        the battlefield when the conditions were checked, so it ceases to exist
        on the repeat check CR 704.3 guarantees, not in the same event.
        """
        gone_tokens = tokens_that_cease_to_exist(self)  # CR 704.5d, CR 111.7

        board = self.computed_board()
        leaving = [
            state
            for state in list(self.battlefield)
            # CR 704.5f before CR 704.5g: a 0-toughness creature is put into the
            # graveyard whatever damage it has, and regeneration cannot stop it.
            # `board.of(state).is_creature` rather than the printed
            # `state.is_creature` (CR 613.5): an animated artifact (Karn, the
            # Great Creator's +1) is a creature on the computed board only.
            if board.of(state).is_creature and self._dies_to_state_based_action(state, board)
        ]
        leaving += [state for state in self._legend_rule_losers() if state not in leaving]
        # CR 704.5m, read off the Aura's own enchant ability (CR 702.5a) by
        # `machines/keywords.py`, which owns the reader `Casting` uses for the
        # announcement half of the same sentence.
        leaving += [state for state in aura_state_based_actions(self) if state not in leaving]
        leaving += [state for state in self._roles_beyond_the_newest() if state not in leaving]
        # CR 704.5i: "If a planeswalker has loyalty 0, it's put into its owner's
        # graveyard." Loyalty is the counter count (CR 306.5c), which is what
        # `planeswalkers_with_zero_loyalty` reads.
        leaving += [
            state
            for state in planeswalkers_with_zero_loyalty(self.battlefield)
            if state not in leaving
        ]
        # `put_into_graveyard` rather than `destroy`, because CR 701.8b says only
        # CR 704.5g and CR 704.5h destroy: CR 704.5f, the legend rule (704.5j),
        # CR 704.5i, CR 704.5m and CR 704.5z all read "is put into its owner's
        # graveyard".
        # The two that *do* destroy have already had CR 702.12b applied to them
        # by `_dies_to_state_based_action`, so an indestructible permanent is not
        # in this list for either of them - and an indestructible 0/0 is, which
        # is the point of the distinction.
        for state in leaving:
            self.put_into_graveyard(state)

        # CR 704.5n, after the round that killed the host: an Equipment whose
        # creature has just left becomes unattached and *stays on the
        # battlefield*, so it is not part of `leaving`. CR 704.3 makes every
        # applicable action one simultaneous event and then checks again, which
        # is what the caller's loop does. It runs after CR 704.5m so that an Aura
        # is already off the battlefield by the time it looks: `equipment_state_based_actions`
        # does not check that what it is unattaching is an Equipment.
        equipment_state_based_actions(self)
        return leaving + gone_tokens

    def _roles_beyond_the_newest(self) -> list[CardState]:
        """The Roles CR 704.5z puts into their owners' graveyards.

        "If a permanent has more than one Role controlled by the same player
        attached to it, each of those Roles except the one with the most recent
        timestamp is put into its owner's graveyard." CR 303.7a states the same
        rule, and CR 303.7 is what makes Role a subtype of Aura at all.

        Two conditions in that sentence do the work, and both are easy to drop:
        the Roles must be on the **same permanent**, and they must be controlled
        by the **same player** - two players' Roles on one creature both stay.

        The timestamp is CR 613.7a's, the one the permanent got as it entered the
        battlefield, which `machines/layers.ContinuousEffects` already keeps in
        `entered`. `computed_board` is called immediately before this in
        `_state_based_actions_once`, and it stamps anything unseen, so every Role
        on the battlefield has one by the time this reads them.
        """
        stamps = self.continuous_effects.entered
        groups: dict[tuple[UUID, str], list[CardState]] = {}
        for permanent in self.battlefield:
            if "Role" not in permanent.card.subtypes or permanent.attached_to is None:
                continue
            groups.setdefault((permanent.attached_to, permanent.controller or ""), []).append(
                permanent
            )

        doomed: list[CardState] = []
        for roles in groups.values():
            if len(roles) < 2:
                continue
            roles.sort(key=lambda role: stamps.get(role.id, 0))
            doomed.extend(roles[:-1])  # every one but the most recent timestamp
        return doomed

    def _dies_to_state_based_action(self, state: CardState, board: ComputedBoard) -> bool:
        """CR 704.5f and CR 704.5g, judged against the computed toughness.

        CR 702.12b splits the two: "A permanent with indestructible can't be
        destroyed. Such permanents aren't destroyed by lethal damage, and **they
        ignore the state-based action that checks for lethal damage** (see rule
        704.5g)." CR 704.5h destroys as well, and a permanent that can't be
        destroyed is not destroyed by it either.

        **CR 704.5f keeps applying.** "If a creature has toughness 0 or less,
        it's put into its owner's graveyard" - put into, not destroyed, which
        CR 701.8b confirms is a different thing, and the rule's own
        "Regeneration can't replace this event" is the clue that it is not a
        destruction to be stopped. An indestructible 0/0 dies.
        """
        if is_indestructible(state, self):
            # Only 704.5f is left, and it is judged below on toughness alone.
            return self._toughness_is_zero_or_less(state, board)
        try:
            toughness = board.of(state).toughness
        except KeyError:
            toughness = state.toughness
        if toughness is None:
            # A printed `*` with no characteristic-defining ability the engine
            # can read. CR 208.5 would call that 0 and CR 704.5f would bin the
            # creature; that is a worse answer than leaving it alone, because
            # the gap is in the registry rather than on the board. Neither rule
            # is applied, and CR 704.5h still is.
            return state.dealt_deathtouch_damage
        if toughness <= 0:
            return True  # CR 704.5f
        # CR 704.5g's arithmetic, plus CR 704.5h's deathtouch, which needs none.
        return state.damage >= toughness or state.dealt_deathtouch_damage

    def _toughness_is_zero_or_less(self, state: CardState, board: ComputedBoard) -> bool:
        """CR 704.5f alone, against the computed toughness (CR 613.5).

        Split out because it is the only one of the three that reaches a
        permanent with indestructible: CR 704.5f puts a creature into its
        graveyard rather than destroying it, which CR 701.8b makes a different
        event, so CR 702.12b has nothing to say about it. A toughness that is not
        a number is not zero or less and is left alone, exactly as above.
        """
        try:
            toughness = board.of(state).toughness
        except KeyError:
            toughness = state.toughness
        return toughness is not None and toughness <= 0

    def _legend_rule_losers(self) -> list[CardState]:
        """The legendary permanents the legend rule puts into graveyards (CR 704.5j).

        "If two or more legendary permanents with the same name are controlled
        by the same player, that player chooses one of them, and the rest are
        put into their owners' graveyards." Nothing here asks the player, so the
        first copy on the battlefield is the one kept, which keeps a scenario
        that does not care about the choice reproducible.
        """
        kept: set[tuple[str, str]] = set()
        losers: list[CardState] = []
        for state in self.battlefield:
            if Supertype.LEGENDARY not in state.card.supertypes:
                continue
            key = (self.controller_of(state).username, state.name)
            if key in kept:
                losers.append(state)
            else:
                kept.add(key)
        return losers

    def _losing_players(self) -> list[str]:
        """Players a state-based action would remove right now.

        - **CR 704.5a** - 0 or less life.
        - **CR 704.5b** - tried to draw from an empty library since the last check.
        - **CR 704.5c** - "If a player has ten or more poison counters, that
          player loses the game." `Player.loses_to_poison` is the threshold; the
          Two-Headed Giant exception the rule names is not modelled.
        """
        return [
            player.username
            for player in self.players
            if self.is_in_game(player.username)
            and (
                player.life <= 0
                or player.tried_to_draw_from_empty_library
                or player.loses_to_poison
            )
        ]

    def _lose_the_game(self, username: str) -> None:
        """This player loses, and so leaves the game (CR 104.5)."""
        if username not in self.losers:
            self.losers.append(username)
        self._player_left(username)

    def _player_left(self, username: str) -> None:
        """Clean up after a player who is no longer in the game (CR 800.4).

        CR 800.4a: everything they own leaves the game, and CR 800.4j has the
        turn carry on without them. Ownership is not modelled separately from
        control, so this reads their objects off `controller`.
        """
        assert self.turn is not None
        for zone_cards in self.shared_zones.values():
            for state in list(zone_cards):
                if state.controller == username:
                    self.combat.remove(state.id)
                    zone_cards.remove(state)
        # CR 800.4d: a triggered ability that would be controlled by a player who
        # has left the game is never put on the stack.
        self.pending_triggers = [
            trigger for trigger in self.pending_triggers if trigger.controller != username
        ]
        self.turn.leave(username)
        if self.priority is not None:
            self.priority.leave(username)

    def _check_for_a_winner(self) -> None:
        """The last player left in a two-or-more player game wins (CR 104.2a).

        Runs after every state-based-action check and after every concession.
        When a draw has emptied the game - every player still in it lost at the
        same check, CR 104.4a - there is nobody left to win, `winner` stays
        None, and the draw recorded by `check_state_based_actions` says the
        game is over.
        """
        remaining = self.players_in_game
        if len(remaining) == 1 and len(self.players) > 1:
            self.winner = remaining[0].username

    # -- combat ------------------------------------------------------------

    def attack_target(self, defender: "Targetable | str") -> TargetRef:
        """Read an attack target out of a player, a username, or a permanent."""
        return TargetRef.coerce(defender)

    def can_attack(self, creature: CardState, defender: "Targetable | str") -> bool:
        """Whether this creature could be declared attacking that (CR 508.1a)."""
        return combat_rules.attack_refusal(self, creature, self.attack_target(defender)) is None

    def why_cannot_attack(self, creature: CardState, defender: "Targetable | str") -> str | None:
        """The reason a declaration would be refused, for a scenario to assert on."""
        return combat_rules.attack_refusal(self, creature, self.attack_target(defender))

    def declare_attacker(self, creature: CardState, defender: "Targetable | str") -> Attack:
        """Declare one attacker (CR 508.1). Taps it unless it has vigilance.

        The attack triggers whatever watches for it, but nothing goes on the
        stack here: CR 508.2b puts the abilities that triggered on attackers
        being declared onto the stack "before the active player gets priority",
        and no player receives priority between one declaration and the next.
        `declare_attackers` opens that window once the whole attack is declared.
        """
        attack = combat_rules.declare_attacker(self, creature, self.attack_target(defender))
        self.emit(
            GameEvent(
                event=TriggerEvent.ATTACKS,
                subject_id=creature.id,
                subject_name=creature.name,
                subject_controller=self.controller_of(creature).username,
                subject_card=creature.card,
                defender=attack.defender,
                player=self.controller_of(creature).username,
            )
        )
        return attack

    def declare_attackers(self, attacks: list[tuple[CardState, "Targetable | str"]]) -> None:
        """Declare a whole attack at once, in order (CR 508.1, 508.2b)."""
        for creature, defender in attacks:
            self.declare_attacker(creature, defender)
        if attacks:
            # CR 508.3d: "An ability that reads 'Whenever [a player] attacks,
            # . . .' triggers if one or more creatures that player controls
            # are declared as attackers" - once for the whole declaration,
            # not once per attacker, so this is its own subject-less event
            # alongside each creature's own ATTACKS event above.
            self.emit(GameEvent(event=TriggerEvent.ATTACKS, player=self.active_player.username))
        self.put_triggers_on_stack()

    def can_block(self, blocker: CardState, attacker: CardState) -> bool:
        """Whether this creature could block that attacker on its own (CR 509.1a).

        Restrictions that only make sense against the finished declaration -
        menace - are checked by `declare_blockers`, not here.
        """
        return self.why_cannot_block(blocker, attacker) is None

    def why_cannot_block(self, blocker: CardState, attacker: CardState) -> str | None:
        attack = self.combat.attack_by(attacker.id)
        if attack is None:
            return f"{attacker.name} is not attacking"
        return combat_rules.block_refusal(self, blocker, attack)

    def declare_blockers(self, blocks: list[tuple[CardState, CardState]]) -> None:
        """Declare the blocks for this combat as one legal declaration (CR 509.1).

        `blocks` is `(blocker, attacker)` pairs, in the order damage should be
        assigned through them (CR 510.1c).

        Once the declaration is legal, each blocking pair is an event: the
        blocker blocked and the attacker became blocked (CR 509.1a), and both
        halves are what an Ashmouth Hound reads. A pair only ever triggers once
        per combat, so re-declaring a block that was already declared does not
        fire it again.
        """
        combat_rules.declare_blockers(self, blocks)

        for attack in self.combat.attacks:
            attacker = self.find_by_id(attack.attacker_id)
            for blocker_id in attack.blockers:
                blocker = self.find_by_id(blocker_id)
                if attacker is None or blocker is None:
                    continue
                pair = f"{blocker_id}:{attack.attacker_id}"
                if pair in self.blocks_triggered:
                    continue
                self.blocks_triggered.append(pair)
                self.emit(
                    GameEvent(
                        event=TriggerEvent.BLOCKS,
                        subject_id=blocker.id,
                        subject_name=blocker.name,
                        subject_controller=self.controller_of(blocker).username,
                        subject_card=blocker.card,
                        related_id=attacker.id,
                        player=self.controller_of(blocker).username,
                    )
                )
        self.put_triggers_on_stack()

    def attacking_creatures(self) -> list[CardState]:
        found = (self.find_by_id(card_id) for card_id in self.combat.attacker_ids)
        return [state for state in found if state is not None]

    def blocking_creatures(self) -> list[CardState]:
        found = (self.find_by_id(card_id) for card_id in self.combat.blocker_ids)
        return [state for state in found if state is not None]

    def is_attacking(self, creature: CardState) -> bool:
        return self.combat.attack_by(creature.id) is not None

    def is_blocking(self, creature: CardState) -> bool:
        return self.combat.attack_blocked_by(creature.id) is not None

    def is_blocked(self, creature: CardState) -> bool:
        """A creature stays blocked even once its blockers are gone (CR 509.1h)."""
        attack = self.combat.attack_by(creature.id)
        return attack is not None and attack.blocked

    @property
    def needs_first_strike_damage_step(self) -> bool:
        """Whether combat takes two damage steps rather than one (CR 510.4)."""
        return combat_rules.needs_first_strike_step(self)

    def combat_damage_step(self) -> list[tuple[Targetable, int]]:
        """Run one combat damage step, returning what was assigned (CR 510).

        The flag marks every `deal_damage` inside the step as combat damage
        (CR 510.2), which is what a prevention effect limited to combat damage
        needs to know.
        """
        self._dealing_combat_damage = True
        try:
            return combat_rules.combat_damage_step(self)
        finally:
            self._dealing_combat_damage = False

    def combat_damage(self) -> list[tuple[Targetable, int]]:
        """Run every combat damage step this combat needs (CR 510.1, 510.4).

        One step normally; two when anything in combat has first strike or
        double strike, with state-based actions between them - which is what
        stops a creature killed by first strike from striking back.
        """
        assigned = self.combat_damage_step()
        if self.combat.first_strike_step_happened and self.combat.damage_steps_done < 2:
            assigned = assigned + self.combat_damage_step()
        return assigned

    def end_of_combat(self) -> None:
        """Everything is removed from combat as the step ends (CR 511.3)."""
        self.combat.clear()
        self.blocks_triggered = []

    # -- special actions ---------------------------------------------------

    def land_allowance(self, username: str) -> int:
        """The number of lands `username` can play this turn (CR 305.2, 305.2a).

        One by default - CR 305.2: "A player can normally play one land during
        their turn; however, continuous effects may increase this number." The
        increases come from static abilities of permanents the player controls,
        read through `machines.layers.ADDITIONAL_LAND_PLAYS`: CR 611.3d is the
        rule that lets a static ability allow playing a land at all, and since
        static ability text is not parsed (see `docs/engine-coverage.md`) the
        grants are a per-card registry like `LAYER_EFFECTS`.

        Azusa's printed "on each of your turns" adds no condition of its own
        here: `can_play_land` refuses anyone who is not the active player
        (CR 305.3), so the allowance is only ever consulted for a player on
        their own turn. And it reaches only its controller, because
        `permanents_controlled_by` is what feeds the read.

        CR 305.2a compares this number against `lands_played`, which counts
        "lands played as special actions and lands played during the resolution
        of spells and abilities". Every land play this engine has goes through
        `play_land`, so the one counter covers both halves of the
        parenthetical - and a land PUT onto the battlefield by an effect (a
        fetchland's find, CR 305.4) counts in neither number, because
        `put_onto_battlefield` never reaches `play_land`.
        """
        return 1 + additional_land_plays(self.permanents_controlled_by(username))

    def why_cannot_play_land(self, username: str) -> str | None:
        """Why `username` cannot play a land right now, or None (CR 305.1-305.3).

        The checks, in the order the rules number them:

        - **CR 305.1** - "A player who has priority may play a land card from
          their hand during a main phase of their turn when the stack is
          empty." Of that, the main phase and the empty stack are checked here.
          Priority is not, and that is a gap, not a reading: CR 116.2a times
          the special action to "any time they have priority and the stack is
          empty during a main phase of their turn", but the engine has no
          notion of a priority possession that persists between moves, so the
          caller is trusted to hold it the way the rules require.
        - **CR 305.3** - "A player can't play a land, for any reason, if it
          isn't their turn. Ignore any part of an effect that instructs a
          player to do so."
        - **CR 305.2b** - "A player can't play a land, for any reason, if the
          number of lands the player can play this turn is equal to or less
          than the number of lands they have already played this turn."
          CR 305.2a is the comparison: `land_allowance` against `lands_played`.
        """
        assert self.turn is not None
        if self.turn.step not in MAIN_PHASES:
            return (
                f"{username} cannot play a land outside a main phase of their turn "
                f"(CR 305.1); the turn is in {self.turn.step.value}"
            )
        if not self.stack_is_empty:
            return f"{username} cannot play a land while the stack is not empty (CR 305.1)"
        if username != self.turn.active_player:
            return (
                f"{username} cannot play a land, for any reason, if it isn't their turn "
                f"(CR 305.3); it is {self.turn.active_player}'s turn"
            )
        played = self.lands_played.get(username, 0)
        allowance = self.land_allowance(username)
        if played >= allowance:
            return (
                f"{username} cannot play a land: {played} of the {allowance} they may play "
                f"this turn already used (CR 305.2a, 305.2b)"
            )
        return None

    def can_play_land(self, username: str) -> bool:
        """Whether `username` may play a land right now (CR 305.1-305.3).

        Every reason it could refuse is spelled out in `why_cannot_play_land`,
        which carries the rule for each check; this is that answer as a bool.
        """
        return self.why_cannot_play_land(username) is None

    def play_land(self, land: CardState, username: str) -> CardState:
        """Play a land: a special action, so it uses no stack and no priority.

        Nobody gets a chance to respond, because nothing is ever put on the
        stack (CR 116.2a, 505.5b). Priority does not change hands.

        A modal double-faced card is not a land by `Card.is_land`, which only
        ever reads the front face (CR 712.8a) - Witch Enchanter // Witch-
        Blessed Meadow's front is a creature. `Card.land_face` is the mirror
        read for its back: CR 712.12 lets a player play an MDFC as a land by
        choosing "one of its faces that's a land" before it hits the
        battlefield, and CR 712.8f then gives the permanent only that face's
        characteristics for as long as it stays there. There is no separate
        "playing an MDFC's land face" special action in the rules - it is the
        same CR 305.1 land drop, so it is checked and counted exactly like any
        other land below.
        """
        land_face = land.card.land_face
        if not land.card.is_land and land_face is None:
            raise ValueError(f"{land.name} is not a land")
        refusal = self.why_cannot_play_land(username)
        if refusal is not None:
            raise ValueError(refusal)

        # CR 305.2a counts "lands played as special actions and lands played
        # during the resolution of spells and abilities", so any future effect
        # that plays a land during a resolution must come through here to be
        # counted. A land PUT onto the battlefield (CR 305.4) must not.
        self.lands_played[username] = self.lands_played.get(username, 0) + 1

        if not land.card.is_land and land_face is not None:
            land.land_face_played = land_face.name

        # Playing a land is not casting it (CR 116.2a, 305.1), so `was_cast` is
        # False. The land itself used no stack, but its enters-the-battlefield
        # ability is an ordinary triggered ability and does (CR 603.6a) - and
        # "this land enters tapped" is a replacement effect, not a trigger
        # (CR 614.1c), which `enter_the_battlefield` applies on the way in.
        # The player who played the land keeps priority, so this is the CR 603.3
        # window.
        self.enter_the_battlefield(land, username, was_cast=False)
        self.put_triggers_on_stack()
        return land

    # -- determining a spell's total cost (CR 601.2f) ----------------------

    def cost_reduction_for(self, spell: CardState, caster: str | None = None) -> ManaCost:
        """What this spell's own text takes off its cost right now (CR 601.2f).

        The reduction is *computed*, never stored: CR 601.2f is a step of casting
        that happens after modes and targets, and what it reads is the game state
        at that moment. Emrakul, the Promised End is the card that makes the
        difference visible - "This spell costs {1} less to cast for each card
        type among cards in your graveyard" is worth however many card types are
        in that graveyard when the cost is determined, not when the card was
        drawn or when announcement began.

        CR 205.2b: "Some objects have more than one card type (for example, an
        artifact creature). Such objects satisfy the criteria for any effect that
        applies to any of their card types" - so one artifact creature in the
        graveyard is two card types, not one.

        A card whose reduction sentence this does not recognise reduces nothing.
        """
        # Same DFC-family fix as `effect_for` above: a modal-DFC/transform
        # spell's reduction clause lives on `card_faces`, not the raw
        # top-level `oracle_text` field, so this has to read `oracle_text`
        # (which already falls back to the up face) rather than `card.oracle_text`.
        text = spell.oracle_text or ""
        match = _COSTS_LESS_PER_CARD_TYPE.search(text)
        if match is None:
            return ManaCost()

        owner = caster or spell.controller or self.active_player.username
        types = {
            card_type for card in self.player(owner).graveyard for card_type in card.card.types
        }
        amount = int(match.group(1)) * len(types)
        return ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()

    def static_cost_modifiers_for(
        self, spell: CardState, caster: str | None = None
    ) -> tuple[list[ManaCost], int | None]:
        """Board-wide static cost increases and the floor in play right now
        (CR 601.2f, 611.3).

        Unlike `cost_reduction_for`, which reads *this* spell's own text for a
        self-discount, this reads every *other* permanent's static ability for
        a tax or a floor on spells in general: Sphere of Resistance and Thorn
        of Amethyst's flat increases, Damping Sphere's per-spell-this-turn
        increase, Trinisphere's floor. `Casting.total_cost` folds this in for
        every ordinary cast, so nothing has to opt in the way
        `determine_total_cost` does for a self-reduction.

        A permanent whose text names a card-type qualifier ("Noncreature
        spells cost {1} more") only taxes a spell that lacks that type
        (CR 205.2b: a multi-type card is checked against all of them). A
        permanent whose ability requires being untapped (Trinisphere's own
        clause) is skipped while tapped (CR 611.3b: a static ability's effect
        applies only while its source carries it).

        Text that reads like a cost modifier but does not match one of
        `cost_modifier_effect`'s recognised shapes - Grand Arbiter Augustin
        IV's controller-relative "Spells your opponents cast cost {1} more to
        cast" - is neither applied nor silently skipped: a `CostModifierNotice`
        is appended to `cost_modifier_notices` instead (DDR#978 - an increase
        that fails to apply looks identical to ordinary play). Deduplicated by
        source, since this runs every time a cost is priced.
        """
        caster = caster or spell.controller or self.active_player.username
        increases: list[ManaCost] = []
        floor: int | None = None
        already_noticed = {notice.source_id for notice in self.cost_modifier_notices}

        for permanent in self.battlefield:
            # Same DFC-family fix as `effect_for`: `oracle_text` reads the up
            # face, `card.oracle_text` is null for a modal-DFC/transform
            # permanent and would silently skip its static ability.
            text = permanent.oracle_text or ""
            if not text:
                continue
            effect = cost_modifier_effect(text)
            if effect is None:
                if looks_like_unparsed_cost_modifier(text) and permanent.id not in already_noticed:
                    already_noticed.add(permanent.id)
                    self.cost_modifier_notices.append(
                        CostModifierNotice(
                            source_id=permanent.id, source_name=permanent.name, text=text
                        )
                    )
                continue

            if effect.kind is CostModifierKind.FLOOR:
                if effect.requires_untapped and permanent.tapped:
                    continue
                if floor is None or effect.amount > floor:
                    floor = effect.amount
            elif effect.kind is CostModifierKind.FLAT_INCREASE:
                if effect.excludes_type is not None and effect.excludes_type in spell.card.types:
                    continue
                increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
            elif effect.kind is CostModifierKind.PER_SPELL_INCREASE:
                prior = len(self.spells_cast_this_turn.get(caster, []))
                if prior:
                    increases.append(ManaCost.parse(f"{{{effect.amount * prior}}}"))

        return increases, floor

    def determine_total_cost(self, casting: object) -> CostPayment:
        """CR 601.2f: work out the reduction now, then lock the total cost in.

        "Once the total cost is determined, any effects that directly affect the
        total cost are applied. Then the resulting total cost becomes 'locked
        in.' If effects would change the total cost after this time, they have no
        effect." Which is why the reduction is applied *here* rather than when
        the `Casting` was created: a card put into the graveyard between
        announcement and this call still counts, and one put there afterwards
        does not.

        `Casting.determine_cost` does not consult the game for a self-reduction
        on its own, so a scenario that wants Emrakul's discount calls this
        instead of `casting.determine_cost()`. Routing it into
        `machines/casting.py` is the tidier home - see `docs/engine-coverage.md`.
        """
        reduction = self.cost_reduction_for(casting.spell, casting.caster)  # type: ignore[attr-defined]
        if reduction.symbols:
            # Appended straight onto the casting's reductions rather than through
            # `reduce_cost`, which belongs to CR 601.2b and refuses to run once
            # targets have been chosen. CR 601.2f is a later step than that.
            casting.cost_reductions.append(reduction)  # type: ignore[attr-defined]
        return casting.determine_cost()  # type: ignore[attr-defined]

    # -- activated abilities (CR 602) --------------------------------------

    def activated_abilities(self, permanent: CardState) -> list[ActivatedAbility]:
        """Every activated ability printed on this permanent, in printed order.

        CR 602.1: an activated ability is written `[Cost]: [Effect.]
        [Activation instructions (if any).]`. The index into this list is what
        `activate_ability` and `machines/effects.py` key on.
        """
        return activated_abilities_of(permanent.card)

    def why_cannot_activate(
        self, permanent: CardState, index: int = 0, controller: str | None = None
    ) -> str | None:
        """Why this ability may not be activated right now, or None (CR 602.5).

        "A player can't begin to activate an ability that's prohibited from being
        activated." What is checked:

        - the permanent is on the battlefield and the player controls it
          (CR 602.1a, 602.2: only an object's controller may activate its
          abilities);
        - **CR 602.5a / 302.6** - a creature that has not been controlled since
          its controller's most recent turn began cannot activate an ability with
          `{T}` or `{Q}` in its cost, unless it has haste (CR 702.10c);
        - **CR 602.5b** - "Activate only once each turn" and its siblings.
        - **CR 602.5d** - "Activated abilities that read 'Activate only as a
          sorcery' mean the player must follow the timing rules for casting a
          sorcery spell, though the ability isn't actually a sorcery. The player
          doesn't actually need to have a sorcery card that they could cast."
          CR 307.5 spells out what those timing rules are: "the player must have
          priority, it must be during the main phase of their turn, and the
          stack must be empty", which is `can_cast_sorcery`.
        - **CR 606.3** - a loyalty ability carries its own, stricter timing:
          "any time they have priority and the stack is empty during a main
          phase of their turn, but only if no player has previously activated a
          loyalty ability of that permanent that turn". Same timing machinery
          as CR 307.5, but the once-per-turn half is per permanent - activating
          one of a planeswalker's loyalty abilities refuses all the others
          until the next turn.
        - **CR 606.6** - "A loyalty ability with a negative loyalty cost, taking
          into account any additional costs, can't be activated unless the
          permanent has at least that many loyalty counters on it." The
          counters are what `CardState.loyalty` reads (CR 306.5c).

        CR 602.5e's "Activate only as an instant" is not checked, because
        CR 304.5 makes it "only that the player must have priority" - which is
        already true of every activation here.

        CR 113.6's "abilities of all other objects usually function only while
        that object is on the battlefield" is enforced as a flat rule, so an
        ability that functions from another zone is refused. Cycling is the pool's
        example and it goes through `machines/keywords.KeywordActivation`
        instead, which carries the zone its rule names - see
        `docs/engine-coverage.md`.
        """
        abilities = self.activated_abilities(permanent)
        if index >= len(abilities):
            return f"{permanent.name} has no activated ability number {index}"
        ability = abilities[index]
        controller = controller or self.controller_of(permanent).username

        if permanent.zone is not Zone.BATTLEFIELD:
            return f"{permanent.name} is in {permanent.zone.value}, not on the battlefield"
        if self.controller_of(permanent).username != controller:
            return f"{controller} does not control {permanent.name}"
        if not self._still_has_ability(permanent, ability):
            # CR 602.2: activating is putting *its* activated ability on the
            # stack, so the object has to still have it. CR 613.1f applies
            # ability-removing effects in layer 6, and CR 613.5 has the result
            # apply instantly - a permanent that lost all abilities has nothing
            # left to activate, however plainly the card is printed.
            return (
                f"{permanent.name} no longer has that ability: it was removed by a "
                "continuous effect in layer 6 (CR 613.1f)"
            )

        needs_tapping = any(piece.kind in {CostKind.TAP, CostKind.UNTAP} for piece in ability.costs)
        if needs_tapping and not self.can_activate_tap_ability(permanent):
            return (
                f"{permanent.name} has not been under {controller}'s control since their "
                "most recent turn began, so an ability with {T} in its cost cannot be activated"
            )

        if ability.loyalty is not None:
            # CR 606.3: "A player may activate a loyalty ability of a permanent
            # they control any time they have priority and the stack is empty
            # during a main phase of their turn, but only if no player has
            # previously activated a loyalty ability of that permanent that
            # turn." The timing half is CR 307.5's sorcery machinery; the
            # once-per-turn half is per permanent, so it is keyed by the
            # permanent alone, not by which ability was activated.
            if not self.can_cast_sorcery(controller):
                return (
                    f"{permanent.name}'s loyalty ability can only be activated during "
                    f"{controller}'s main phase, with the stack empty (CR 606.3)"
                )
            if self._loyalty_activation_count(permanent):
                return (
                    f"{permanent.name}'s loyalty abilities have already been activated "
                    "this turn (CR 606.3)"
                )
            removes = ability.loyalty.removes
            if removes and (permanent.loyalty or 0) < removes:
                # CR 606.6: the counters the negative cost removes have to be
                # on the planeswalker before the ability may be activated.
                return (
                    f"{permanent.name} has {permanent.loyalty} loyalty, not the {removes} "
                    f"its {ability.loyalty.printed} cost removes (CR 606.6)"
                )

        instructions = (ability.instructions or "").lower()
        if "once each turn" in instructions and self._activation_count(permanent, index):
            return f"{permanent.name}'s ability has already been activated this turn"
        if _SORCERY_TIMING.search(instructions) and not self.can_cast_sorcery(controller):
            return (
                f"{permanent.name}'s ability can only be activated as a sorcery: "
                f"{controller}'s main phase, with the stack empty "
                f"(CR 602.5d, CR 307.5)"
            )
        if "activate only if" in instructions and not self._activation_condition_holds(
            ability, controller
        ):
            return f"{permanent.name}'s activation restriction is not met (CR 602.5b)"
        return None

    def _activation_condition_holds(self, ability: ActivatedAbility, controller: str) -> bool:
        """Whether an "Activate only if [board state]" restriction is met (CR 602.5b).

        Two shapes are read, both of this pool's own examples: Mox Opal's
        Metalcraft ("you control three or more artifacts") and Fanatic of
        Rhonas's Ferocious ("you control a creature with power 4 or
        greater"). Anything else this cannot read is **not** blocked - an
        unparsed restriction refusing every activation would trade a narrow,
        documented gap (see `docs/engine-coverage.md`) for a much louder
        wrong one, on cards this restriction was never meant to touch.
        """
        instructions = ability.instructions or ""
        controlled = self.permanents_controlled_by(controller)

        match = _ACTIVATE_ONLY_IF_CONTROL.search(instructions)
        if match is not None:
            needed = _CONDITION_COUNT_WORDS.get(match.group("count").lower())
            card_type = _card_type_named(match.group("quality"))
            if needed is not None and card_type is not None:
                count = sum(1 for state in controlled if card_type in state.card.types)
                return count >= needed

        match = _ACTIVATE_ONLY_IF_POWER.search(instructions)
        if match is not None:
            threshold = int(match.group("power"))
            return any(
                state.is_creature and state.power is not None and state.power >= threshold
                for state in controlled
            )

        return True

    def _still_has_ability(self, permanent: CardState, ability: ActivatedAbility) -> bool:
        """Whether the computed board still shows this ability on the permanent.

        `Characteristics.abilities` is a tuple of ability *text*, one entry per
        oracle line, because nothing here parses a static ability into anything
        richer. Layer 6 removal empties it and a grant appends to it, so
        comparing the printed line against it answers CR 613.1f.

        A permanent the layer engine has never seen - not on the battlefield, or
        computed before it arrived - is not judged, so this can only ever take
        an ability away that an effect actually removed.
        """
        try:
            computed = self.characteristics_of(permanent)
        except KeyError:
            return True
        if not computed.abilities:
            # No ability lines at all is either a vanilla permanent or one that
            # lost everything. Only the second is interesting, and it is told
            # apart by the card having printed one in the first place.
            # `oracle_text` reads the up face; `card.oracle_text` is null for
            # a modal-DFC/transform permanent and would misreport it as
            # having lost every ability when it never had raw text to begin
            # with (same family as `effect_for` above).
            return not (permanent.oracle_text or "").strip()
        return any(ability.text in line or line in ability.text for line in computed.abilities)

    def _activation_key(self, permanent: CardState, index: int) -> str:
        return f"{permanent.id}:{index}"

    def _activation_count(self, permanent: CardState, index: int) -> int:
        return self.activations.get(self._activation_key(permanent, index), 0)

    def _loyalty_activation_count(self, permanent: CardState) -> int:
        """How often any loyalty ability of this permanent was activated this turn.

        CR 606.3's once-per-turn rule is about the permanent, not the ability -
        "but only if no player has previously activated a loyalty ability of
        that permanent that turn" - so this is keyed by the permanent alone.
        """
        return self.loyalty_activations.get(str(permanent.id), 0)

    def _choice_cost(
        self,
        text: str,
        permanent: CardState,
        pool: list[CardState],
        controller: str,
        builder: Callable[..., CostComponent],
    ) -> CostComponent:
        """One `[Sacrifice|Discard]` cost piece, self-reference and quality
        requirement both handled (CR 602.1a, CR 118.3).

        `cost_component_for_phrase` already reads the qualified shape -
        "Sacrifice a Goblin", "Discard two cards" - into a component carrying
        a `CardRequirement`, but always with `cards=[]`: it has no `pool` to
        choose from and no permanent to self-reference. This fills the gap
        either way: from `pool` (the caller's nomination) up to however many
        the cost asks for, or with `permanent` itself when nothing was
        nominated and the text names "this" card - the same self-reference
        `CostKind.OTHER`'s own fill-in below handles.

        Falls back to `builder` directly - no requirement, "sacrifice
        anything" - only when the phrase does not match the qualified shape
        at all (CR 602.1a - "Sacrifice this land"'s `count` position holds the
        word "this", not a number, so `cost_component_for_phrase` cannot read
        it as one).
        """
        component = cost_component_for_phrase(text, payer=controller)
        if component is None:
            if pool:
                chosen = [pool.pop(0)]
            elif _SELF_REFERENCE.search(text):
                chosen = [permanent]
            else:
                chosen = []
            return builder(*chosen, payer=controller, required=1, description=text)

        chosen = []
        while pool and len(chosen) < component.required:
            chosen.append(pool.pop(0))
        if not chosen and _SELF_REFERENCE.search(text):
            chosen = [permanent]
        return component.model_copy(update={"cards": chosen})

    def activation_cost(
        self,
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
    ) -> TotalCost:
        """The total cost of one activation (CR 602.1a, 601.2f).

        CR 602.1a: "the activation cost is everything before the colon". Each
        comma-separated piece was classified by `machines/abilities.py`; this
        turns those pieces into the `TotalCost` that `machines/cost.py` knows how
        to pay. A piece that asks for an object - sacrifice, discard - takes the
        next card from `sacrificing` or `discarding`; leaving it empty builds a
        cost that correctly refuses to be paid (CR 118.3) rather than one that
        cannot be built.
        """
        ability = self.activated_abilities(permanent)[index]
        controller = controller or self.controller_of(permanent).username
        sacrifices = list(sacrificing or [])
        discards = list(discarding or [])

        mana = ManaCost()
        components = []
        for piece in ability.costs:
            if piece.kind is CostKind.MANA:
                mana = increase(mana, ManaCost.parse(piece.text))
            elif piece.kind is CostKind.TAP:
                components.append(tap_cost(permanent, payer=controller, description=piece.text))
            elif piece.kind is CostKind.SACRIFICE:
                components.append(
                    self._choice_cost(piece.text, permanent, sacrifices, controller, sacrifice_cost)
                )
            elif piece.kind is CostKind.DISCARD:
                components.append(
                    self._choice_cost(piece.text, permanent, discards, controller, discard_cost)
                )
            elif piece.kind is CostKind.PAY_LIFE:
                digits = re.search(r"\d+", piece.text)
                components.append(
                    pay_life_cost(
                        int(digits.group()) if digits else 0,
                        controller,
                        description=piece.text,
                    )
                )
            elif piece.kind is CostKind.LOYALTY:
                # CR 606.4: the loyalty symbol is the whole cost, and the
                # counter change it asks for is the cost itself. A `−X` cost
                # has no amount anyone can pay until something can choose X
                # (CR 107.7: "a minus sign followed by a number or an X").
                amount = ability.loyalty.amount if ability.loyalty else None
                if amount is None:
                    raise ValueError(f"cannot build a cost for {piece.text!r}")
                components.append(
                    loyalty_cost(permanent, amount, payer=controller, description=piece.text)
                )
            else:
                # CostKind.OTHER: a printed cost sentence `machines/abilities.py`
                # could not classify into one of the shapes above. CR 118.3 makes
                # any of them payable in principle, and
                # `machines/cost.cost_component_for_phrase` is the reader that
                # turns the sentence into something payable - "Exert this land"
                # (CR 701.43a), "Exile a black card from your hand" (CR 118.9).
                component = cost_component_for_phrase(piece.text, payer=controller)
                if component is None:
                    raise ValueError(f"cannot build a cost for {piece.text!r}")
                if not component.cards and _SELF_REFERENCE.search(piece.text):
                    # "Exert **this** land": only the caller knows which
                    # permanent the ability is on, so the reader builds the
                    # component empty and it is filled in here (CR 602.1a - the
                    # ability's source is the object it is printed on).
                    component = component.model_copy(update={"cards": [permanent]})
                components.append(component)

        return TotalCost(mana=mana, components=components).assign_payer(controller)

    def begin_activating(
        self,
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
    ) -> CostPayment:
        """Announce an activation and open its payment (CR 602.2a, 602.2b).

        Raises if the ability is prohibited from being activated at all
        (CR 602.5), before anything has been spent.
        """
        refusal = self.why_cannot_activate(permanent, index, controller)
        if refusal is not None:
            raise ValueError(refusal)
        controller = controller or self.controller_of(permanent).username
        total = self.activation_cost(
            permanent, index, controller, sacrificing=sacrificing, discarding=discarding
        )
        return CostPayment.for_total(total, game=self, payer=controller)

    def activate_ability(
        self,
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        targets: list[object] | None = None,
        color: Color | None = None,
    ) -> AbilityOnStack | None:
        """Finish activating: put the ability on the stack (CR 602.2).

        "To activate an ability is to put it onto the stack and pay its costs, so
        that it will eventually resolve and have its effect." The cost is paid by
        the caller through `begin_activating`; this is the half that produces the
        object on the stack.

        **Mana abilities are the exception.** CR 605.1a: an activated ability is
        a mana ability if it meets all of the following criteria: it doesn't
        require a target, it could add mana to a player's mana pool when it
        resolves, it's not a loyalty ability, and its cost and effect don't move
        any card to or from a library. (The first three were the whole rule
        before the 2026-08-19 release added the library criterion.) The
        criteria are evaluated on the printed text - "Do not take into account
        replacement effects that may apply, other than self-replacement
        effects, when evaluating these criteria" - and the library criterion is
        `moves_a_library_card`. CR 605.3b: a mana ability "doesn't go on the
        stack, so it can't be targeted, countered, or otherwise responded to.
        Rather, it resolves immediately after it is activated" - so the mana
        goes into its controller's pool here and `None` comes back, meaning
        nothing was put on the stack.

        `color` is the colour picked for a mana ability offering a choice (a
        dual land, an "any color" source) - `ManaAbility.resolve` is what
        actually makes the choice and raises its own clear message when one
        is needed but missing, or when the one given is not on offer. It is
        not consulted at all for an ability with only one possible output.
        """
        ability = self.activated_abilities(permanent)[index]
        controller = controller or self.controller_of(permanent).username

        # CR 602.2b: "the remainder of the process for activating an ability is
        # identical to the process for casting a spell", so CR 601.2c applies -
        # the targets are announced and checked here, against the ability's own
        # text rather than the card's spell text (CR 113.1c).
        profile = profile_for_text(ability.text)
        if profile.understood and profile.requirements:
            profile.check(list(targets or []), controller, self)

        key = self._activation_key(permanent, index)
        self.activations[key] = self.activations.get(key, 0) + 1
        if ability.loyalty is not None:
            # CR 606.3's once-per-turn rule is per permanent: having activated
            # any loyalty ability of this planeswalker this turn, the next one
            # is refused until a new turn begins.
            self.loyalty_activations[str(permanent.id)] = (
                self.loyalty_activations.get(str(permanent.id), 0) + 1
            )

        if (
            ability.mana is not None
            and ability.loyalty is None
            and not targets
            and not moves_a_library_card(ability)
        ):
            # All four of CR 605.1a's criteria, and the loyalty one is now
            # checked rather than assumed: a `0: Add {C}{C}{C}.` cost is a
            # loyalty symbol (CR 606.2), which makes the ability a loyalty
            # ability, and a loyalty ability is not a mana ability - it goes
            # on the stack like any other activated ability (CR 602.2,
            # CR 113.3b). The other three: no target announced, an "Add"
            # effect, and nothing in the printed cost or effect moves a card
            # to or from a library. CR 605.3b: no stack at all; the mana lands
            # in the pool immediately.
            land_types = self._controlled_land_types(controller)
            own_counters = frozenset(permanent.counters.counts)
            has_imprinted_card = self.card_imprinted_on(permanent.id) is not None
            produced_mana = ability.mana.resolve(
                land_types, own_counters, color, has_imprinted_card
            )
            for produced in produced_mana:
                self.player(controller).mana_pool.add(produced)
            # CR 106.12: "to 'tap [a permanent] for mana' is to activate a mana
            # ability of that permanent that includes the {T} symbol in its
            # activation cost" - so only a `{T}: ...` ability counts, not
            # Skirk Prospector's sacrifice-only one. CR 106.12a is the event
            # Leyline of Abundance and Utopia Sprawl watch for, even though
            # CR 605.3b means this ability itself never touched the stack
            # (`tapped_for_mana_event`'s own docstring is the other half of
            # this: `CostPayment.tap_for_mana` emits the same event when a
            # source pays for a spell instead of being activated directly).
            if any(piece.kind is CostKind.TAP for piece in ability.costs):
                self.emit(tapped_for_mana_event(permanent))
            self.put_triggers_on_stack()
            return None

        on_stack = AbilityOnStack(
            kind=AbilityKind.ACTIVATED,
            ability=ability,
            source_id=permanent.id,
            source_name=permanent.name,
            controller=controller,
            targets=[TargetRef.coerce(target) for target in targets or []],
        )
        self.stack.append(on_stack)
        # CR 117.3c hands priority straight back, so anything that triggered
        # while the cost was paid goes on the stack now - above the ability.
        self.put_triggers_on_stack()
        return on_stack

    # -- priority ----------------------------------------------------------

    def pass_priority(self, username: str) -> PriorityOutcome:
        """Pass priority. If everyone passes, resolve the top of the stack.

        CR 117.4: "If all players pass in succession ... the spell or ability
        on top of the stack resolves or, if the stack is empty, the phase or
        step ends." CR 405.5: the next step or phase then begins - nobody has
        to move the game on; passing is saying "I am done for now". So on
        END_STEP the turn rolls forward here, with everything that boundary
        brings (CR 500.5's mana-pool emptying among them), and the next
        step's first priority round starts with its active player (CR 117.1).
        """
        assert self.priority is not None
        # CR 704.3, then CR 603.3: state-based actions, then anything that has
        # triggered goes on the stack, before the pass is acted on - the next
        # player (or nobody, if the stack resolves) is about to receive
        # priority. This is also the check a special action like playing a
        # land relies on: CR 116.2a hands out no priority of its own, so the
        # legend rule or any other state-based action it caused is caught here,
        # the next time anyone would receive priority.
        self._check_state_based_actions_and_stack_triggers()
        outcome = self.priority.pass_priority(username, self.stack_is_empty)
        if outcome is PriorityOutcome.RESOLVE_TOP:
            self.resolve_top()
        elif outcome is PriorityOutcome.END_STEP and not self.is_over:
            self.advance()
        return outcome

    def retain_priority(self, username: str) -> str:
        """The player who just cast or activated keeps priority (CR 117.3c).

        Keeping priority is still *receiving* it, so CR 704.3 applies here too:
        a cost paid to cast or activate (a sacrifice, most often, but also life
        paid down to 0) can leave two legendary permanents, a 0-toughness
        creature, or even take the activator themselves out of the game before
        their own ability ever resolves (CR 704.5a) - and that must be resolved
        before this player would act again rather than waiting for the next
        pass. If the check just removed `username`, CR 800.4j has already
        moved priority on to whoever is next seated, so there is nobody left
        to hand it back to.
        """
        assert self.priority is not None
        self._check_state_based_actions_and_stack_triggers()
        if not self.is_in_game(username):
            return self.priority.holder
        return self.priority.retain(username)

    # -- controlling another player (CR 723) -------------------------------

    def _sync_player_control(self) -> None:
        """Show the priority machine who is deciding for whom (CR 723.5).

        The effect itself lives on `TurnMachine`, because CR 723.1 scopes it to
        a whole turn. `PriorityMachine` only needs to know who may act.
        """
        assert self.turn is not None
        if self.priority is not None:
            self.priority.controlled_by = dict(self.turn.player_control)

    def gain_control_of_player(self, controller: str, controlled: str) -> None:
        """Gain control of another player during their next turn (CR 723.1).

        This is Emrakul, the Promised End's cast trigger and the only shape of
        the effect this engine models. CR 723.1: "This effect applies to the
        next turn that the affected player actually takes", so nothing changes
        now - the effect waits on `TurnMachine` until that turn begins, and
        CR 723.1b keeps it waiting through any skipped turn.

        A later effect on the same player replaces this one (CR 723.1a).
        """
        assert self.turn is not None
        self.player(controller)  # raises if unknown
        self.player(controlled)
        self.turn.gain_control_of_player(controller, controlled)
        self._sync_player_control()

    def controller_of_player(self, username: str) -> str:
        """Who is making this player's decisions (CR 723.5, 723.8, 723.9).

        Themselves, unless a player-controlling effect is in force this turn.
        """
        assert self.turn is not None
        return self.turn.controller_of_player(username)

    def is_controlling_player(self, controller: str, controlled: str) -> bool:
        """Whether `controller` is deciding for `controlled` right now (CR 723.1)."""
        return controller != controlled and self.controller_of_player(controlled) == controller

    def why_cannot_decide_for(self, decider: str, player: str) -> str | None:
        """Why `decider` may not make `player`'s choices, or None (CR 723.5).

        "While controlling another player, a player makes all choices and
        decisions the controlled player is allowed to make or is told to make by
        the rules or by any objects." Everyone decides for themselves by default
        (CR 723.9), and CR 723.8 leaves a controller's own choices theirs; the
        only thing refused here is a player reaching for somebody else's
        decisions without an effect that gives them.
        """
        actual = self.controller_of_player(player)
        if decider == actual:
            return None
        if actual != player:
            return f"{actual} is deciding for {player} this turn, not {decider} (CR 723.5)"
        return f"nothing gives {decider} control of {player} (CR 723.5)"

    def why_cannot_pay_with(self, controlled: str, source: CardState) -> str | None:
        """Why this permanent cannot pay a controlled player's cost (CR 723.5a).

        "The controller of another player can use only that player's resources
        (cards, mana, and so on) to pay costs for that player." So a controller
        making their victim cast a spell has to find the mana on the victim's
        own board; their own lands are not available for it.
        """
        owner = self.controller_of(source).username
        if owner == controlled:
            return None
        return f"{source.name} is {owner}'s, so it cannot pay a cost for {controlled} (CR 723.5a)"

    # -- extra turns (CR 500.7) --------------------------------------------

    def grant_extra_turn(self, username: str) -> None:
        """This player takes an extra turn after the current one (CR 500.7).

        The turns are added directly after the turn in progress; several of them
        are added one at a time and the most recently created is taken first.
        """
        assert self.turn is not None
        self.player(username)  # raises if unknown
        self.turn.grant_extra_turn(username)

    def controller_of(self, state: StackObject) -> Player:
        """Who controls this object. Unlabelled cards belong to the active player."""
        return self.player(state.controller) if state.controller else self.active_player

    def _owner_of(self, state: CardState) -> Player:
        """Whose private zones a card goes to when nobody names a player (CR 108.3).

        `CardState.owner` is the actual answer - set once when the card
        entered the game and never keyed to the zone it happens to sit in
        right now, unlike `find_owner`'s zone lookup (which cannot answer at
        all for a card already taken out of every zone on its way to a new
        one - milling from *bob's* library was landing in whoever the active
        player was, because by the time this ran the card had already left
        bob's zones). Only a card with no `owner` set at all - most of this
        engine's own test fixtures, which usually skip it - falls back to
        `controller_of`'s active-player default.
        """
        return self.player(state.owner) if state.owner else self.controller_of(state)

    def find_owner(self, state: CardState) -> Player | None:
        """Whose card this is, by the zone it is sitting in.

        Ownership is not modelled separately from control (see
        `docs/engine-coverage.md`), so this asks the only question the model can
        answer: which player's zones hold it. A card on the battlefield, the
        stack, or in exile is in a shared zone and has no owner to find that
        way, so its controller stands in.
        """
        for player in self.players:
            for zone_cards in player.zones.values():
                if state in zone_cards:
                    return player
        return self.player(state.controller) if state.controller else None

    def concede(self, username: str, by: str | None = None) -> None:
        """A player concedes and leaves the game immediately (CR 104.3a).

        Conceding is not a state-based action and does not wait for one: the
        player is gone at once, their objects go with them (CR 800.4a), and the
        last player standing wins (CR 104.2a).

        `by` is who is taking the action, and defaults to the player themselves.
        It exists for CR 723.6: "The controller of another player can't make
        that player concede. A player may concede the game at any time, even if
        they are controlled by another player." That is the one decision a
        player-controlling effect never reaches - CR 723.5 hands over every
        choice "the rules or any objects" call for, and conceding is neither.
        """
        self.player(username)  # raises if unknown
        if by is not None and by != username:
            raise ValueError(
                f"{by} cannot make {username} concede, even while controlling them (CR 723.6)"
            )
        if username not in self.conceded:
            self.conceded.append(username)
        self._player_left(username)
        self._check_for_a_winner()

    def end_with_winner(self, username: str) -> None:
        self.player(username)  # raises if unknown
        self.winner = username

    def end_in_draw(self) -> None:
        """End this game as a draw, with no winner (CR 104.4a).

        The state-based-action path sets `drawn` itself when one check removes
        every player still in the game; this is the entry for a draw that does
        not come from a check - the mandatory-action loops of CR 104.4b are not
        modelled, and CR 104.4c's "an effect may state that the game is a draw"
        has no registry effect behind it, so a scenario stages one here.

        CR 104.5 sends a player the game is a draw for out of the game, and the
        game is a draw for everyone still in it, so they all leave and their
        objects go with them (CR 800.4a).
        """
        if self.is_over:
            raise ValueError("the game is already over")
        self.drawn = True
        for username in [player.username for player in self.players_in_game]:
            self._lose_the_game(username)

    def advance(self, username: str | None = None) -> Step:
        """Move to the next step (CR 500.1), as `username`'s own decision.

        `username` defaults to whoever is actually authorized right now (the
        active player, or their CR 723.5 controller) so a caller that is not
        testing the refusal itself does not have to look that player up.

        In the order CR 703.3, CR 704.3 and CR 603.3 set out: the step begins and
        anything that triggers "at the beginning of" it triggers (CR 500.6), its
        turn-based actions happen, state-based actions are checked, everything
        that has triggered goes on the stack, and only then does a player receive
        priority. The turn-based actions are run only when
        `automatic_turn_based_actions` is on - see that field.

        Nothing is put on the stack in the untap or cleanup steps, where no
        player receives priority (CR 502.4, 514.3); those triggers wait for the
        next step. CR 514.3a's rule that a cleanup trigger *does* give players
        priority and repeats the step is not modelled.

        Two refusals, both raised before anything moves:

        - **CR 117.3a**: the active player is the one whose decision this is -
          or, under a CR 723.5 control effect, whoever is deciding for them.
          Anyone else is refused outright.
        - **CR 500.2 / CR 117.4 / CR 405.5**: a step or phase that grants
          priority (i.e. not one of `NO_PRIORITY`'s untap/cleanup exceptions,
          CR 500.3) ends only once the stack is empty and every player has
          passed in succession. A non-empty stack means that has not happened
          yet, so advancing past it here would strand whatever is waiting -
          the caller must pass priority and let it resolve instead.
        """
        assert self.turn is not None
        if self.is_over:
            raise ValueError("the game is over")

        decider = self.controller_of_player(self.turn.active_player)
        if username is None:
            username = decider
        if username != decider:
            raise ValueError(
                f"{username} may not advance the turn - only {decider} may, as "
                f"{self.turn.active_player}'s active-player decision (CR 117.3a, 723.5)"
            )
        if self.turn.step not in NO_PRIORITY and not self.stack_is_empty:
            raise ValueError(
                f"cannot advance past {self.turn.step} while the stack is "
                f"non-empty - pass priority instead (CR 500.2)"
            )

        previous_turns_taken = self.turn.turns_taken
        previous_step = self.turn.step
        step = self.turn.advance()

        if self.automatic_turn_based_actions and previous_step is Step.DECLARE_ATTACKERS:
            # CR 508.8: "If no creatures are declared as attackers or put onto
            # the battlefield attacking, skip the declare blockers and combat
            # damage steps." A skipped step is one that never happens (CR
            # 500.11: "to skip a step ... is to proceed past it as though it
            # didn't exist"), so it gets no beginning event, no turn-based
            # actions, no priority round, and nothing scheduled for it happens
            # (CR 614.10a). Walking the pointer past them here, before either
            # begins, does that.
            #
            # The condition is the declaration, not who is still in combat:
            # CR 508.8 keys off "declared as attackers or put onto the
            # battlefield attacking", so CR 506.4 removing an attacker after
            # the declaration does not un-skip the combat. Nothing in this
            # model puts a creature onto the battlefield attacking, so the
            # declaration flag is the whole of it. Only the automatic path
            # skips: a caller driving combat by hand may have declared its
            # attackers in whatever way it likes, and its steps must be there
            # when it steps into them.
            while step in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE) and (
                not self.combat.attacked_this_combat
            ):
                step = self.turn.advance()

        if previous_step is Step.END_OF_COMBAT:
            # CR 511.3: everything leaves combat as the end of combat step ends.
            self.end_of_combat()

        # CR 500.5: as the step that just ended ends, any unspent mana empties.
        # The pointer may have crossed several boundaries (the skip loop above,
        # or a cleanup that rolled into the next turn); nothing between them
        # can add mana, so one emptying covers every boundary crossed.
        self.empty_mana_pools()

        if self.turn.turns_taken != previous_turns_taken:
            # A new turn: land drops reset and the new active player gets
            # priority. `turns_taken` is the signal rather than the active seat
            # or the turn number, because an extra turn (CR 500.7) moves
            # neither: the same player can take two turns in a row.
            self.lands_played = {}
            self.activations = {}  # CR 602.5b restrictions are per turn
            self.loyalty_activations = {}  # CR 606.3's once-per-turn is per turn too
            self.spells_cast_this_turn = {}
            self.life_gained_this_turn = set()
            self.end_of_combat()
            self.begin_turn_for(self.turn.active_player)
            self._sync_player_control()  # CR 723.1

        # CR 500.6: "When a phase or step begins, any abilities that trigger 'at
        # the beginning of' that phase or step trigger."
        self.emit(
            GameEvent(
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                player=self.turn.active_player,
            )
        )

        if self.automatic_turn_based_actions:
            self.turn_based_actions()  # CR 703.3, before state-based actions
            self.check_state_based_actions()  # CR 704.3, before anyone has priority

        if step not in NO_PRIORITY:
            self.put_triggers_on_stack()  # CR 603.3, before anyone has priority

        if self.priority is not None:
            self.priority.reset(self.turn.active_index)
        return step

    def advance_to(self, step: Step) -> Step:
        """Move the turn marker forward through every boundary up to `step`.

        The full funnel is `advance`, which also performs what each *beginning*
        needs - beginning-of-step triggers, turn-based actions, state-based
        actions, priority. This one crosses boundaries only, and at each of
        them performs the step-end turn-based action CR 500.5 requires: mana
        pools empty as every crossed step ends. Raises if `step` has already
        passed this turn, exactly as `TurnMachine.advance_to` does.
        """
        assert self.turn is not None
        if TURN_ORDER.index(step) < TURN_ORDER.index(self.turn.step):
            raise ValueError(f"{step} already passed this turn, currently at {self.turn.step}")
        while self.turn.step is not step:
            self.turn.advance()
            self.empty_mana_pools()
        return self.turn.step
