import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from ...ids import new_id
from ...models.card import Card, Color, Supertype, Type
from ...models.card_state import CardState, Counter, ExileMarker
from ...models.token import TokenDefinition, is_token
from ...models.zone import Zone
from ...snapshot import EngineModel
from ..casting import PlayAction
from ..damage_modification import (
    DamageCantBePreventedReplacement,
    DamageModifierReplacement,
    DamageRedirectReplacement,
    PreventDamageByReplacement,
    TurnDamageGroup,
)
from ..decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ...models.game import Game
    from ...models.player import Player
    from ..layers import ComputedBoard


# --------------------------------------------------------------------------
# Kinds
# --------------------------------------------------------------------------


class ReplacementKind(StrEnum):
    """Which template a sentence matched. `UNPARSED` means none of them did."""

    #: CR 614.1a - "If [event] would [happen], [replacement] instead."
    IF_WOULD_INSTEAD = "if_would_instead"
    #: CR 614.1a - "[replacement] instead of [event]" / "Instead of [event], [replacement]".
    INSTEAD_OF = "instead_of"
    #: CR 614.1a shape - "[replacement] rather than [event]". Not every sentence
    #: of this shape is a CR 614 replacement effect; see `RATHER_THAN` notes.
    RATHER_THAN = "rather_than"
    #: CR 614.1b, 614.10 - "Skip [something]".
    SKIP = "skip"
    #: CR 614.1d - "[This permanent] enters tapped." Verified in this session:
    #: CR 614.1d is "Continuous effects that read '[This permanent] enters . . .'
    #: or '[Objects] enter [the battlefield] . . .' are replacement effects",
    #: which is the bare form. CR 614.1c is the *other* three shapes -
    #: "[This permanent] enters with . . . ," "As [this permanent] enters . . . ,"
    #: and "[This permanent] enters as . . ." - so it is `ENTERS_WITH`,
    #: `AS_ENTERS` and `ENTERS_AS_COPY`'s rule, not this one. This line cited
    #: 614.1c until that was looked up; the wrong number is recorded here the
    #: same way the parser docstring records the CR 113.3 correction.
    ENTERS_TAPPED = "enters_tapped"
    #: CR 614.1d - "[Objects] enter [the battlefield] untapped." A general
    #: effect watching a *class* of permanent, not the printing permanent's own
    #: CR 614.12 self-modification - Spelunking's "Lands you control enter
    #: untapped" is the pool's only printing, overriding whatever tapped state
    #: another effect (a search's own "tapped", a shockland's own "enters
    #: tapped") would otherwise have given the entering land.
    ENTERS_UNTAPPED = "enters_untapped"
    #: CR 614.1c - "[This permanent] enters with [counters] on it."
    ENTERS_WITH = "enters_with"
    #: CR 614.1c, 616.1c - "... enter as a copy of ...".
    ENTERS_AS_COPY = "enters_as_copy"
    #: CR 614.1c - "As [this permanent] enters, ...".
    AS_ENTERS = "as_enters"
    #: CR 614.1e - "As [this permanent] is turned face up, ...".
    AS_TURNED_FACE_UP = "as_turned_face_up"
    #: CR 614.1d's bare form, Reality Fracture's own addition: "[This
    #: creature] enters prepared" (CR 722.3a - "Some spells and abilities
    #: cause a permanent with a prepare spell to become prepared or state
    #: that a permanent enters prepared."). Verified this session: CR 722.3a
    #: is the rule that names this exact phrasing.
    ENTERS_PREPARED = "enters_prepared"
    #: CR 615.1a - "Prevent the next N damage that would be dealt to X this turn."
    PREVENT_NEXT = "prevent_next"
    #: CR 615.1a - "Prevent all [combat] damage that would be dealt ...".
    PREVENT_ALL = "prevent_all"
    #: CR 615.8 - "The next time [source] would deal damage ..., prevent that damage."
    PREVENT_NEXT_TIME = "prevent_next_time"
    #: CR 615.1a - "If [event] would [happen], prevent ...".
    PREVENT_IF_WOULD = "prevent_if_would"
    #: Cue word present, no template matched. Read `text`, do not trust the rest.
    UNPARSED = "unparsed"


#: The kinds that are prevention effects (CR 615) rather than plain replacement
#: effects (CR 614). Note CR 615.1 makes prevention a species of continuous
#: effect alongside replacement, so these are returned from the same call.
PREVENTION_KINDS = frozenset(
    {
        ReplacementKind.PREVENT_NEXT,
        ReplacementKind.PREVENT_ALL,
        ReplacementKind.PREVENT_NEXT_TIME,
        ReplacementKind.PREVENT_IF_WOULD,
    }
)

#: The kinds that modify how a permanent enters the battlefield (CR 614.12).
ENTERS_KINDS = frozenset(
    {
        ReplacementKind.ENTERS_TAPPED,
        ReplacementKind.ENTERS_UNTAPPED,
        ReplacementKind.ENTERS_WITH,
        ReplacementKind.ENTERS_AS_COPY,
        ReplacementKind.AS_ENTERS,
        ReplacementKind.ENTERS_PREPARED,
    }
)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


class CopyException(EngineModel):
    """CR 707.9b's modifications to a copy, read off an "except ..." tail.

    CR 707.9b: "Some copy effects modify a characteristic as part of the
    copying process. The final set of values for that characteristic becomes
    part of the copiable values of the copy." So these are not effects layered
    on top of the copy - they are part of what layer 1a writes (CR 613.2a,
    CR 613.2c: "After all rules and effects in layer 1 have been applied, the
    object's characteristics are its copiable values").

    Superior Spider-Man prints all three at once: "except his name is Superior
    Spider-Man and he's a 4/4 Spider Human Hero in addition to his other
    types" - a name, a base power and toughness, and subtypes *added* rather
    than replacing (CR 205.1b's retaining form, spelled out by "in addition to
    his other types").
    """

    model_config = ConfigDict(frozen=True)

    #: The name the copy has instead of the copied object's (CR 707.9b).
    name: str | None = None
    #: The copy's power and toughness, both or neither.
    power: int | None = None
    toughness: int | None = None
    #: Card types gained on top of the copied ones (CR 205.1b).
    added_types: tuple[Type, ...] = ()
    #: Subtypes gained on top of the copied ones (CR 205.1b, CR 205.3).
    added_subtypes: tuple[str, ...] = ()
    #: Abilities the copy gains as part of the copying process (CR 707.9a:
    #: "This ability becomes part of the copiable values for the copy, along
    #: with any other abilities that were copied."), one ability line each -
    #: a keyword capitalised the way a printed keyword line is ("Flying",
    #: Mockingbird's "it has flying"), or a quoted ability's own text with the
    #: quotes removed (Phantasmal Image's "it has "When this creature becomes
    #: the target of a spell or ability, sacrifice it.""). Lines, because
    #: `BecomeACopy.abilities` is ability text one line per ability, which is
    #: what every reader of the computed board already parses.
    added_abilities: tuple[str, ...] = ()
    #: Supertypes gained on top of the copied ones - Moritte of the Frost's
    #: "it's legendary and snow in addition to its other types" (CR 707.9b,
    #: CR 205.1b's retaining form).
    added_supertypes: tuple[Supertype, ...] = ()
    #: Colors gained on top of the copied ones - Lazotep Convert's own
    #: "it's a 4/4 black Zombie in addition to its other colors and types"
    #: (CR 707.9b, CR 105.3's own "in addition" retaining form for color).
    added_colors: tuple[Color, ...] = ()
    #: CR 707.9f's gate: "Some exceptions to the copying process apply only if
    #: the copy is or has certain characteristics" - Moritte's "if it's a
    #: creature, ...". Judged on the copy as it would be without the gated
    #: part (every other exception included). `None` when nothing is gated.
    if_type: Type | None = None
    #: The abilities gained only when `if_type` holds (CR 707.9a/707.9f).
    if_type_abilities: tuple[str, ...] = ()
    #: "it enters with two additional +1/+1 counters on it" - CR 707.9e's
    #: exception that is an additional effect rather than a characteristic,
    #: `(kind, amount)` pairs, placed as the copy enters, only when
    #: `if_type` holds (or always, with no gate).
    enters_with_counters: tuple[tuple[str, int], ...] = ()


class ReplacementEffect(EngineModel):
    """One replacement or prevention effect read off a card.

    Most fields are per-kind and stay `None` when the kind does not carry them.
    `kind`, `raw`, and `text` are always populated, so an `UNPARSED` result is
    still usable - it says "this sentence is about replacement and I could not
    read it", which is the honest answer.
    """

    kind: ReplacementKind
    #: The whole ability paragraph as printed, reminder text included.
    raw: str
    #: The one sentence this effect was parsed from, reminder text removed.
    text: str
    #: Reminder text found in the paragraph, joined, or None. Never parsed.
    reminder: str | None = None
    #: Face name for a multifaced card, None for a single-faced one.
    face: str | None = None

    #: True when this sentence is the *effect* of a triggered ability rather
    #: than a static ability's own continuous effect (CR 603.1 vs CR 604.2).
    #:
    #: Brine Elemental's "When this creature is turned face up, each opponent
    #: skips their next untap step" is the only shape read this way, and the
    #: flag is what keeps reading it from being a lie: the skip does not exist
    #: while the permanent sits on the battlefield, it comes into being when
    #: the trigger resolves. `parsed_card_replacements` therefore never
    #: compiles a `from_trigger` effect into a `CardReplacement`, so nothing
    #: `applicable_effects` gathers off the battlefield can come from one.
    #: Reporting the shape and refusing to perform it is the honest answer;
    #: performing it as a static ability would be a wrong board state.
    from_trigger: bool = False

    #: The event being replaced or prevented, as templated.
    event: str | None = None
    #: What happens in its place.
    replacement: str | None = None
    #: What enters, is turned face up, or is skipped - the subject of the clause.
    subject: str | None = None
    #: A leading or trailing condition: "unless you control a basic land",
    #: "you don't".
    condition: str | None = None

    #: True when the effect is worded as a choice ("you may", "You may have").
    optional: bool = False
    #: "The first time [you would ...] each turn, ..." (Mirrormind Crown,
    #: Moonlit Meditation) - the effect only ever looks at the first such
    #: event of each turn, whether or not it replaced it.
    first_time_each_turn: bool = False
    #: True when the effect only concerns the object it is printed on, rather
    #: than being a general effect watching every object. CR 614.12 draws this
    #: line for effects that modify how a permanent enters: they "may come from
    #: the permanent itself if they affect only that permanent". Mox Diamond's
    #: "If this artifact would enter" is one; Gather Specimens' "If a creature
    #: would enter the battlefield under an opponent's control" is not.
    #:
    #: This is NOT CR 614.15's "self-replacement effect", which is a different
    #: thing: an effect of a resolving spell replacing part of its own effect.
    self_replacement: bool = False

    #: How many: counters entered with, damage prevented. None when absent or
    #: variable.
    amount: int | None = None
    #: True when the amount is X or otherwise not a fixed number.
    variable_amount: bool = False
    #: The kind of counter, as printed: "+1/+1", "shield", "charge".
    counter_kind: str | None = None
    #: How many, when the card states it as an expression rather than a number
    #: or an X - Ulamog, the Defiler's "equal to the greatest mana value among
    #: cards in exile". Kept as the printed phrase; `_self_enters_modifiers`
    #: evaluates it against the game as the permanent enters, and refuses the
    #: whole effect if it recognises no resolver for the phrase.
    amount_expression: str | None = None
    #: What the permanent enters as a copy of.
    copy_of: str | None = None
    #: CR 707.9b's "except ..." tail, already read into the values it overrides:
    #: "except his name is Superior Spider-Man and he's a 4/4 Spider Human Hero
    #: in addition to his other types". CR 707.9b: "Some copy effects modify a
    #: characteristic as part of the copying process. The final set of values
    #: for that characteristic becomes part of the copiable values of the copy."
    #: `None` when the clause has no exception at all - never when there was
    #: one this parser could not read; that case is `copy_exception_unparsed`
    #: instead, so the two `None`-shaped facts ("nothing was printed" and
    #: "something was printed and I could not read it") stay distinguishable
    #: downstream instead of collapsing into the same default.
    copy_exception: CopyException | None = None
    #: The raw "except ..." text, set only when the clause existed and
    #: `_parse_copy_exception` could not read it. CR 707.9b treats the copy and
    #: its exception as one atomic computation of copiable values ("The final
    #: set of values ... becomes part of the copiable values of the copy"), so
    #: a caller that cannot compute the exception must not silently apply the
    #: copy without it either - that would be running half the instruction,
    #: which CR 608.2c has no notion of. `_enters_as_copy` reads this field to
    #: fail closed *loudly*: a notice, and the "enter as a copy" replacement
    #: skipped, rather than the copy silently missing whatever the "except"
    #: tail was supposed to change. Exclusive with `copy_exception` being set:
    #: at most one of the two is non-`None`.
    copy_exception_unparsed: str | None = None
    #: The "When you do, ..." sentence printed immediately after this one, as
    #: printed. CR 603.12: "A resolving spell or ability may allow or instruct
    #: a player to take an action and create a triggered ability that triggers
    #: 'when [a player] [does or doesn't]' take that action" - Superior
    #: Spider-Man's "When you do, exile that card." is linked to the "you may
    #: have ... enter as a copy" choice above it and happens only if that
    #: choice was taken. Held here rather than parsed as its own effect
    #: because a reflexive ability has no independent existence: without the
    #: action it reflects, it is never created at all.
    linked_trigger: str | None = None
    #: True when the permanent also enters tapped alongside another `enters`
    #: clause, as on Vesuva.
    tapped: bool = False
    #: True when prevention is limited to combat damage.
    combat_only: bool = False
    #: Who or what the damage would be dealt to, as printed.
    damage_target: str | None = None
    #: The multiplier on an `ENTERS_WITH` "[`<multiplier>`] that many
    #: `<counter_kind>` counters" clause, when the count is carried from a
    #: sibling `AS_ENTERS` "[you may ]sacrifice any number of `<description>`"
    #: choice rather than CR 107.3m's X - 1 for a bare "that many" (Shimatsu
    #: the Bloodcloaked), 2 for "twice that many" (Devouring Hellion), and so
    #: on through `numbers.parse_multiplier`. `None` when the clause carries
    #: no such count at all - including CR 107.3m's own "X" shape, which is a
    #: different channel entirely and stays on `variable_amount` alone.
    that_many_multiplier: int | None = None

    @property
    def is_prevention(self) -> bool:
        """True for CR 615 prevention effects."""
        return self.kind in PREVENTION_KINDS

    @property
    def modifies_entering(self) -> bool:
        """True for CR 614.12 effects that change how a permanent enters."""
        return self.kind in ENTERS_KINDS

    @property
    def parsed(self) -> bool:
        return self.kind is not ReplacementKind.UNPARSED


# --------------------------------------------------------------------------
# Convenience
# --------------------------------------------------------------------------


def effects_of_kind(card: Card, *kinds: ReplacementKind) -> list[ReplacementEffect]:
    """Just the effects of the given kinds, in printed order."""
    wanted = set(kinds)
    return [effect for effect in parse_replacement_effects(card) if effect.kind in wanted]


def prevention_effects(card: Card) -> list[ReplacementEffect]:
    """Just the CR 615 prevention effects."""
    return [effect for effect in parse_replacement_effects(card) if effect.is_prevention]


def unparsed_effects(card: Card) -> list[ReplacementEffect]:
    """Sentences that read like replacement effects and could not be parsed."""
    return [effect for effect in parse_replacement_effects(card) if not effect.parsed]


# ==========================================================================
# Applying them
# ==========================================================================
#
# CR 614.1: "replacement effects apply continuously as events happen - they
# aren't locked in ahead of time. Such effects watch for a particular event
# that would happen and completely or partially replace that event."
#
# CR 614.6: "If an event is replaced, it never happens. A modified event occurs
# instead, which may in turn trigger abilities." That is the shape of everything
# below: `Game` builds a `ReplaceableEvent` describing what *would* happen, runs
# it through `apply_replacements`, and then carries out whatever the event says
# afterwards. Nothing is undone, because the original never happened.
#
# CR 616.1 orders competing effects: "If two or more replacement and/or
# prevention effects are attempting to modify the way an event affects an object
# or player, the affected object's controller (or its owner if it has no
# controller) or the affected player chooses one to apply." CR 616.1f then
# repeats the process "taking into account only replacement or prevention
# effects that would now be applicable", and CR 614.5 stops any one effect
# applying twice: "a replacement effect doesn't invoke itself repeatedly; it
# gets only one opportunity to affect an event or any modified events that may
# replace that event."


class EventKind(StrEnum):
    """The events this engine can put through the replacement machinery."""

    #: A permanent is about to enter the battlefield (CR 614.1c, 614.1d, 614.12).
    ENTERS_BATTLEFIELD = "enters_battlefield"
    #: An object is about to move zones (CR 400.6, 400.7). Only moves *to* a
    #: graveyard are raised so far, since that is where the pool's cards watch.
    ZONE_CHANGE = "zone_change"
    #: Damage is about to be dealt to a permanent or a player (CR 119.3, 615.1).
    DAMAGE = "damage"
    #: A permanent is about to be destroyed (CR 701.8a).
    #:
    #: Deliberately narrower than the graveyard move it usually becomes.
    #: CR 701.8b: "The only ways a permanent can be destroyed are as a result
    #: of an effect that uses the word 'destroy' or as a result of the
    #: state-based actions that check for lethal damage (see rule 704.5g) or
    #: damage from a source with deathtouch (see rule 704.5h). If a permanent
    #: is put into its owner's graveyard for any other reason, it hasn't been
    #: 'destroyed.'" So sacrificing, bouncing, the legend rule and CR 704.5f's
    #: toughness of 0 or less raise no `DESTROY` - they are `ZONE_CHANGE`s,
    #: and a destruction-replacement must not save a permanent from them.
    #: CR 704.5f says so in as many words: "Regeneration can't replace this
    #: event."
    #:
    #: This is what CR 614.8's regeneration and umbra armor replace, so the
    #: event is raised *before* the move and carries `replaced` rather than
    #: an amount: there is nothing to reduce, only something to call off.
    DESTROY = "destroy"
    #: A player is about to draw one card (CR 121.1, 121.6, 614.11).
    DRAW = "draw"
    #: A player is about to gain life (CR 119.3).
    GAIN_LIFE = "gain_life"
    #: A player is about to lose life (CR 119.3) - "you lose N life", a life
    #: payment (CR 118.3b), an exchange's losing half (CR 701.12c), or the
    #: life loss combat or noncombat damage to a player becomes (CR 119.2):
    #: `Game.deal_damage_to_player` always ends by calling `Game.lose_life`,
    #: so this is raised for damage too, *after* `EventKind.DAMAGE`'s own
    #: replacements have already had their say - a card watching "if your
    #: life total would be reduced to 0 or less" (Enduring Angel) sees the
    #: final amount either way arrived at, damage-scoped floor effects
    #: (Elderscale Wurm, Angel of Grace) included.
    LOSE_LIFE = "lose_life"
    #: Counters are about to be put on a permanent (CR 122.1, 122.6).
    ADD_COUNTERS = "add_counters"
    #: One or more tokens are about to be created (CR 111.1, 701.7a, 701.7b).
    #:
    #: Raised *before* anything is put onto the battlefield, which is the whole
    #: point of the event: CR 701.7b says "if a replacement effect applies to a
    #: token being created, that effect applies before considering any continuous
    #: effects that will modify the characteristics of that token", and it draws
    #: the line against the second sentence of the same rule - a replacement
    #: effect that applies to a token *entering the battlefield* applies after
    #: them, and is an `ENTERS_BATTLEFIELD` event like any other permanent's.
    #:
    #: `player` is the player who would create them (CR 111.2: "the player who
    #: creates a token is its owner"), and `amount` is how many.
    CREATE_TOKENS = "create_tokens"
    #: A player is about to lose the game (CR 104.3b/c/d's state-based losses
    #: for 0 or less life, an empty-library draw and ten-plus poison, and CR
    #: 104.3e's "an effect may state that a player loses the game"). Raised
    #: by `Game._apply_lose_the_game_replacements` ahead of `Game._lose_the_
    #: game` at both call sites, so a printed "if you would lose the game,
    #: instead ..." replacement (Exquisite Archangel, Lich's Mirror) gets CR
    #: 616.1's first refusal before the loss actually happens. `player` is
    #: who would lose; there is no `amount` to modify, only `replaced` to set
    #: (see `happens` below) - the same shape `DESTROY` already uses for a
    #: yes/no event with nothing to scale.
    LOSE_THE_GAME = "lose_the_game"


@dataclass
class ReplaceableEvent:
    """One event on its way to happening, as replacement effects see it.

    Mutable on purpose: applying a replacement effect *is* editing this object.
    CR 614.6 says the original event never happens and a modified one happens in
    its place, so there is only ever one event here - the current version of it.

    `Game` reads the fields back after `apply_replacements` returns and does what
    they now say.
    """

    kind: EventKind

    #: The object the event affects, when it is an object.
    card: CardState | None = None
    #: The player the event affects, when it is a player.
    player: "Player | None" = None
    #: Where the object is going, for a zone change or an entering permanent.
    destination: Zone | None = None
    #: Where it is coming from, as CR 400.6 asks.
    origin: Zone | None = None

    #: How much: damage, life, cards drawn, counters placed.
    amount: int = 0
    #: The counter kind being placed, for `ADD_COUNTERS`.
    counter_kind: str | None = None
    #: The player putting the counters, for `ADD_COUNTERS` - the controller
    #: of the resolving spell or ability (CR 608.2c), or the entering
    #: object's controller when nothing specifies one (CR 122.6a). What an
    #: active-voice "If you would put ... counters" reads.
    putter: str | None = None
    #: Counters the entering permanent will arrive with (CR 614.1c), summed by
    #: kind. `Game` places them after the permanent is on the battlefield, which
    #: raises its own `ADD_COUNTERS` event - CR 616.1g's "event contained within
    #: the first event", and what lets Doubling Season see them (CR 122.6).
    counters: dict[str, int] = field(default_factory=dict)
    #: Counters a player other than the entering object's controller puts on
    #: it as it enters, as `(kind, putter, amount)` - CR 702.104a's tribute,
    #: where "that player may put an additional N +1/+1 counters on it". Kept
    #: apart from `counters` only for the putter (CR 122.6a), which the
    #: counter history records and "if tribute wasn't paid" (CR 702.104b)
    #: reads back.
    counters_put_by: list[tuple[str, str, int]] = field(default_factory=list)
    #: Loyalty counters compleated takes back off a planeswalker's own CR
    #: 306.5b/CR 614.1c entering count (CR 702.150a), summed if more than one
    #: instance of the ability somehow applied. Deliberately not folded into
    #: `counters` above: every other entry there is an amount *placed on top
    #: of* an entering-with-nothing baseline (CR 614.1c's ordinary "enters
    #: with N counters" shape, which `counters` predates this field to serve),
    #: while compleated's own text is "that many ... minus two for each" -
    #: subtractive from whatever the permanent's *printed* loyalty (CR
    #: 306.5b) already put there, which `counters` never carries in the first
    #: place. Kept separate rather than let a negative slip into `counters`
    #: itself, which would also (wrongly) put it in reach of a doubling
    #: effect that watches counters *placed* (CR 122.6) - compleated removes
    #: counters that would otherwise have been placed; it does not itself
    #: place any. `Game.enter_the_battlefield` applies it, clamped to what
    #: CR 306.5b actually put there, after `counters` above.
    loyalty_reduction: int = 0
    #: A spell's own "The damage can't be prevented." (CR 615.12) for this one
    #: damage event - `Game.damage_cant_be_prevented` reads it first.
    unpreventable: bool = False
    #: Whether the permanent arrives tapped (CR 614.1c).
    tapped: bool = False
    #: Whether the permanent arrives with the prepared designation (CR 722.3a).
    prepared: bool = False
    #: The creature an as-enters choice made the entering Equipment arrive
    #: attached to (Grifter's Blade, CR 614.12a: "it enters attached to that
    #: creature"), attached by `Game.enter_the_battlefield` as it arrives.
    attach_to: CardState | None = None
    #: Whether the permanent arrives transformed, back face up (CR 712.14a,
    #: CR 702.145b): CR 614.12 judges its enters replacements on the face it
    #: would have on the battlefield.
    transformed: bool = False
    #: CR 702.136a's riot, declined: "If you don't [have this permanent enter
    #: with an additional +1/+1 counter], it gains haste." No duration is
    #: printed, so `Game.enter_the_battlefield` grants it indefinitely
    #: (CR 611.2a's default) once the permanent is on the battlefield, scoped
    #: to this exact incarnation the way dash and unearth's own haste grants
    #: already are (CR 400.7) - a later re-entry is a new object and is asked
    #: again rather than inheriting this flag.
    grants_haste: bool = False
    #: The copiable values an "enter as a copy" replacement already gave the
    #: entering permanent (CR 614.1c, CR 707.2), as (name, ability lines) -
    #: `None` until one applies. CR 614.12: which enters-replacements apply is
    #: decided from "the characteristics of the permanent as it would exist on
    #: the battlefield, taking into account replacement effects that have
    #: already modified how it enters", so once the copy is chosen the copied
    #: object's own "enters with"/"as ... enters"/"enters tapped" abilities
    #: are the ones read, not the entering card's printed ones.
    entering_as_copy: tuple[str, tuple[str, ...]] | None = None

    #: For `CREATE_TOKENS`: the permanent a replacement effect made the tokens
    #: copies of instead (Mirrormind Crown's "create that many tokens that are
    #: copies of equipped creature", CR 614.1a, CR 707.2). `None` leaves the
    #: tokens whatever the creating effect said they were.
    copy_of: CardState | None = None

    #: The object dealing the damage (CR 120.1, CR 120.7). `None` when the
    #: caller did not say - CR 609.7b, CR 615.8 and CR 702.16e all ask about the
    #: source's properties, and an anonymous source has none to check, so they
    #: simply do not apply rather than applying to everything.
    source: CardState | None = None

    #: True when the permanent got here by resolving as a spell. Containment
    #: Priest asks (CR 601.2 defines what casting is).
    was_cast: bool = True
    #: The exile pile (CR 406.4) a replacement that sends the card to exile
    #: also puts it in - CR 715.3d's adventured pile, whose "that player may
    #: play it" is read off this marker afterwards. `Game.put_into_graveyard`
    #: annotates the card once it has actually arrived in exile.
    exile_marker: ExileMarker | None = None
    #: The permanent a replacement exiled the card "with" (CR 607.1): set when
    #: the replacement's source also prints an ability referring to cards
    #: "exiled with" itself, so that ability finds the card. `Game.put_into_
    #: graveyard` writes the CR 607.2a link once the card is in exile.
    exile_link: CardState | None = None
    #: Counters the card arrives in exile with (CR 122.1) - Goliath
    #: Daydreamer's "exile that card with a dream counter on it ... as it
    #: resolves" (`machines/resolving_exile.py`). `Game.put_into_graveyard`
    #: places them once the card is in exile.
    exile_counters: dict[str, int] = field(default_factory=dict)
    #: An "If you do, ..." rider to run once the card is in exile (Feather,
    #: the Redeemed's "return it to your hand at the beginning of the next
    #: end step"), and whose it is.
    exile_rider: str | None = None
    exile_rider_controller: str | None = None
    #: True while combat damage is being dealt (CR 510.2).
    combat: bool = False
    #: True for the draw an active player takes as the draw step's turn-based
    #: action (CR 504.1, 703.4d). Alhammarret's Archive excepts exactly that one.
    draw_step_draw: bool = False
    #: True only for a spell's own successful CR 608 resolution reaching the
    #: graveyard - not a countered spell (CR 701.6, which never resolves at
    #: all) and not a fizzled one (CR 608.2b: "it doesn't resolve"), both of
    #: which move a card off the stack through this same `ZONE_CHANGE` event.
    #: CR 702.88a's rebound reads "instead of putting it into your graveyard
    #: **as it resolves**" - narrower than flashback's "any time it would
    #: leave the stack" (CR 702.34a), which is why flashback's own entry in
    #: `_stack_replacements` does not gate on this at all and rebound's does.
    resolving: bool = False

    #: False when the effect causing this `DESTROY` printed "can't be
    #: regenerated" (Wrath of God's "Destroy all creatures. They can't be
    #: regenerated.").
    #:
    #: CR 701.19c states the prohibition in exactly these terms: "Effects that
    #: say that a permanent can't be regenerated don't preclude such abilities
    #: from being activated or such spells from being cast; rather, they cause
    #: regeneration shields to **not be applied**." So it belongs on the
    #: destruction event, not on the permanent - a shield the sweeper ignored
    #: is still standing afterwards for the next destruction this turn, which
    #: a flag stamped on the creature would silently have spent.
    #:
    #: This is CR 608.2c's own worked example of a rider modifying its
    #: antecedent rather than running after it: "In some cases, later text on
    #: the card may modify the meaning of earlier text (for example, 'Destroy
    #: target creature. It can't be regenerated' ...)".
    regeneration_allowed: bool = True

    #: Under whose control the tokens being created would enter, for
    #: `CREATE_TOKENS` - `None` is `player`'s own (CR 111.2: "The token enters
    #: the battlefield under that player's control"). Kept apart from `player`
    #: because a replacement can change who controls them without changing who
    #: creates (and so owns) them - Crafty Cutpurse's "each token that would be
    #: created under an opponent's control this turn is created under your
    #: control instead" (`EnterUnderYourControl`).
    controller: str | None = None

    #: What the tokens being created are, for `CREATE_TOKENS` (CR 111.3).
    #:
    #: Without it the event says only *how many*, which is enough for Doubling
    #: Season ("twice that many of **those** tokens") and not enough for
    #: anything that asks what kind - Stridehangar Automaton watches for
    #: "artifact tokens" specifically, and cannot tell one from a Saproling
    #: without this. `None` for a token *copy*, whose characteristics come from
    #: a printed card rather than a definition (CR 707.2); `card` carries the
    #: original in that case, and is the thing to read instead.
    definition: TokenDefinition | None = None
    #: Tokens a replacement effect added to a `CREATE_TOKENS` event that are
    #: *not* more of `definition` - Stridehangar Automaton's "those tokens plus
    #: an additional 1/1 ... Thopter ... are created instead".
    #:
    #: Kept apart from `amount` because CR 614.6's modified event really is one
    #: creation of two different kinds of token, not two creations: they are
    #: created by draining this list inside the same `create_tokens` call, with
    #: no second `CREATE_TOKENS` event raised for them. Raising one would let
    #: the same permanent's effect apply again to its own addition, which
    #: CR 614.5 forbids ("it gets only one opportunity to affect an event or
    #: any modified events that may replace that event") and which would not
    #: terminate.
    extra: list[TokenDefinition] = field(default_factory=list)

    #: A `DESTROY` that a replacement effect called off (CR 614.8, CR 701.8c).
    #: The destruction simply does not happen; the permanent stays where it is.
    replaced: bool = False

    #: The keys of the effects that have already applied (CR 614.5).
    applied: set[str] = field(default_factory=set)
    #: A human-readable trace of what applied, in order. Scenario tests assert
    #: on outcomes, not on this - it exists so a failure says *why*.
    history: list[str] = field(default_factory=list)

    @property
    def creating_controller(self) -> str | None:
        """Under whose control the tokens of a `CREATE_TOKENS` event would enter."""
        if self.controller is not None:
            return self.controller
        return self.player.username if self.player is not None else None

    @property
    def happens(self) -> bool:
        """False when the event was replaced with nothing at all.

        Damage prevented down to zero (CR 615.1a) and a draw replaced by
        something else both land here.
        """
        if self.kind in (EventKind.DAMAGE, EventKind.LOSE_LIFE):
            return self.amount > 0
        if self.kind in (EventKind.DESTROY, EventKind.LOSE_THE_GAME):
            return not self.replaced
        return True

    def chooser(self, game: "Game") -> str | None:
        """Who orders the applicable effects (CR 616.1).

        "The affected object's controller (or its owner if it has no controller)
        or the affected player." An object on the stack or the battlefield has a
        controller (CR 109.4); anywhere else, fall back to the owner.
        """
        if self.player is not None:
            return self.player.username
        if self.card is None:
            return None
        if self.card.controller:
            return self.card.controller
        owner = game.find_owner(self.card)
        return owner.username if owner is not None else None


#: A test for whether one printed effect applies to an event, and what it does.
#: The source is `None` for an effect with no permanent behind it - a prevention
#: shield created by a spell that has long since resolved (CR 615.1, 615.4).
Applies = Callable[["Game", CardState, ReplaceableEvent], bool]
Apply = Callable[["Game", CardState | None, ReplaceableEvent], None]


@dataclass(frozen=True)
class CardReplacement:
    """One replacement or prevention effect a named card generates."""

    #: Which sentence on the card this is, for the trace and for the CR 614.5 key.
    label: str
    applies: Applies
    apply: Apply
    #: A prevention effect (CR 615.1a) rather than a replacement one - what
    #: CR 615.12's "can't be prevented" turns into a no-op.
    prevention: bool = False


@dataclass(frozen=True)
class ApplicableEffect:
    """One effect that could apply to the event in front of it right now."""

    #: Unique per (source permanent, printed effect). CR 614.5 keys off this, so
    #: two copies of Rest in Peace are two effects and one of them is two.
    key: str
    source: CardState | None
    label: str
    apply: Apply
    #: Who the effect belongs to when there is no source permanent to ask.
    #: A prevention shield (CR 615.1) outlives the object that made it, so the
    #: controller is recorded when the shield is created and carried here.
    controller_username: str | None = None

    #: CR 616.1c: "If any of the replacement and/or prevention effects would
    #: cause an object to become a copy of another object as it enters the
    #: battlefield, one of them must be chosen." True for exactly those, which
    #: is what `order_effects` puts first - the choice is forced, not free.
    copy_as_it_enters: bool = False

    #: CR 616.1b: "If any of the replacement and/or prevention effects would
    #: modify under whose control an object would enter the battlefield, one of
    #: them must be chosen." True for exactly those (`EnterUnderYourControl`),
    #: which `order_effects` puts ahead of even a copy effect.
    controls_entry: bool = False

    #: A prevention effect (CR 615.1a). CR 615.12: against damage that can't
    #: be prevented it still applies, but prevents nothing.
    prevention: bool = False

    @property
    def controller(self) -> str:
        if self.source is not None:
            return self.source.controller or ""
        return self.controller_username or ""

    @property
    def name(self) -> str:
        """What to call this in the event trace."""
        return self.source.name if self.source is not None else "the game"


def leaves_the_battlefield_not_to_exile(event: ReplaceableEvent) -> bool:
    """A permanent about to leave the battlefield for somewhere other than
    exile - the event "exile it instead of putting it anywhere else" replaces
    (an exile-bound move has nothing left to replace, CR 614.1a)."""
    return (
        event.kind is EventKind.ZONE_CHANGE
        and event.origin is Zone.BATTLEFIELD
        and event.destination is not None
        and event.destination is not Zone.EXILE
    )


def _leave_exile_line_replacements(lines: Iterable[str]) -> list[CardReplacement]:
    """Every such line among a permanent's computed abilities (CR 613.1f), so
    a layer 6 removal of it takes the replacement away with it."""
    found: list[CardReplacement] = []
    for line in lines:
        if not is_leave_exile_line(line):
            continue

        def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                leaves_the_battlefield_not_to_exile(event)
                and event.card is not None
                and event.card.id == source.id
            )

        found.append(CardReplacement(label=line.strip(), applies=applies, apply=_exile_instead))
    return found


def _exile_adventured_instead(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """CR 715.3d: "its controller exiles it. For as long as that card remains
    exiled, that player may play it" - exiled into the adventured pile."""
    event.destination = Zone.EXILE
    event.exile_marker = ExileMarker.ADVENTURED


def _shuffle_into_library_instead(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "Shuffle <name> into its owner's library" - the card goes to its
    owner's library instead of a graveyard. `Game.put_into_graveyard` reads
    this destination and does the actual move-and-shuffle (CR 701.24a/c).
    """
    event.destination = Zone.LIBRARY


#: "Shuffle <card's own name> into its owner's library." (Green Sun's Zenith).
#: Deliberately not one of `_parse_oracle_text`'s generic "instead" shapes:
#: this sentence never says "instead", it is CR 304.2/307.2's own final
#: graveyard step being pre-empted by an earlier one-shot effect that already
#: moved the object - the same reason flashback/rebound/adventure below are
#: hand-read here rather than through the generic replacement-effect parser.
_SELF_SHUFFLE_INTO_LIBRARY_RE = re.compile(
    r"shuffle (?P<name>.+?) into its owner'?s library", re.IGNORECASE
)


class DamageLifeFloorReplacement(EngineModel):
    """The created (until-end-of-turn) form of the static shape above -
    Angel of Grace's own "When this creature enters, until end of turn,
    damage that would reduce your life total to less than 1 reduces it to 1
    instead." No leading "as long as" condition on the created form: it is
    simply on or off for the stated duration."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["damage_life_floor"] = "damage_life_floor"
    floor: int

    def applies(self, game: "Game", controller: str, event: "ReplaceableEvent") -> bool:
        return (
            event.kind is EventKind.DAMAGE
            and event.player is not None
            and event.player.username == controller
            and event.amount > 0
            and event.player.life - event.amount < self.floor
        )

    def apply(self, game: "Game", controller: str, event: "ReplaceableEvent") -> None:
        if event.player is None:
            return
        event.amount = max(event.player.life - self.floor, 0)


def replacements_of_state(
    game: "Game", permanent: CardState, board: "ComputedBoard | None" = None
) -> list[CardReplacement]:
    """Like `replacements_of`, but reads a *live permanent's* level-gated
    text (CR 716.2a) rather than its printed card wholesale, and its computed
    ability list (CR 613.5, CR 613.1f) rather than its printed keywords.

    A Class needs the level gate: `CardState.class_ability_text` is exactly
    `oracle_text` for anything else, so this is a safe, behaviour-preserving
    substitute for `replacements_of(permanent.card)` at every battlefield
    scan - Artist's Talent's own level 3 must not double as a level 1's
    damage-plus-2, before the Class has actually reached level 3.

    Every permanent needs the computed ability list: `_keyword_replacements`
    would otherwise grant umbra armor's replacement off `Card.keywords` alone,
    missing a layer-6 removal of it.

    `board`, when the caller already has one (`applicable_effects`'s own
    battlefield sweep), is reused rather than asking `game.characteristics_of`
    again - `Game.computed_board` recomputes the whole battlefield on every
    call, so a caller looping over it must hoist one board rather than pay for
    N of them.
    """
    explicit = REPLACEMENTS.get(permanent.card.name)
    if explicit is not None:
        return explicit
    card = permanent.card
    chars = (board or game.computed_board()).of(permanent)
    found: list[CardReplacement] = (
        _keyword_replacements(card, computed_abilities=chars.abilities)
        + _cant_enter_replacements(card)
        # CR 613.1f: read off the computed ability list, so a layer-6 removal
        # takes the doubling away with the rest of the permanent's text.
        + _double_all_damage_replacements(_rules_lines("\n".join(chars.abilities)))
        + _leave_exile_line_replacements(chars.abilities)
        + _damage_life_floor_replacements(_rules_lines("\n".join(chars.abilities)))
    )
    if "Class" not in chars.subtypes:
        # CR 712.8d/712.8e/712.8f: a double-faced permanent has only the
        # characteristics of the face that's up, and CR 109.3 counts a
        # replacement effect among them - the same face filter `_self_enters_
        # modifiers` already applies for a permanent's *own* CR 614.12 entry
        # effects. Enduring Angel's own "if your life total would be reduced
        # to 0 or less, instead transform ..." is on its front face only;
        # without this, `parse_replacement_effects(card)` reads the whole
        # multi-face printing and the effect kept applying even once the
        # permanent had transformed to Angelic Enforcer, which prints no
        # such thing. `up_face_name` is `None` for an ordinary single-faced
        # card, which keeps every line exactly as before for one.
        up_face_name = permanent.up_face_name
        for effect in parse_replacement_effects(card):
            if up_face_name is not None and effect.face not in (None, up_face_name):
                continue
            compiled = _compile(effect)
            if compiled is not None:
                found.append(compiled)
        return found
    names = _names_of(card)
    for effect in _parse_oracle_text(permanent.class_ability_text, face=None, names=names):
        compiled = _compile(effect)
        if compiled is not None:
            found.append(compiled)
    return found


class ManaProductionReplacement(EngineModel):
    """One mana-production replacement (CR 106.12b), read off its sentence.

    `types` `None` is "a permanent"; otherwise the tapped permanent must have
    one of them (computed, CR 613.1d - an animated land is still a land).
    `basic` is "a basic land" (CR 205.4a's supertype). `at_least` is "for two
    or more mana". `colorless_instead` replaces type and amount with a single
    {C}; otherwise `multiplier` repeats each mana produced that many times.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["mana_production"] = "mana_production"
    you_tap: bool = False
    types: tuple[Type, ...] | None = None
    basic: bool = False
    at_least: int = 1
    colorless_instead: bool = False
    multiplier: int = 1

    def applies(
        self,
        game: "Game",
        controller: str | None,
        source: CardState,
        tapper: str | None,
        produced: list[Color],
    ) -> bool:
        if not produced or len(produced) < self.at_least:
            return False
        if self.you_tap and (tapper is None or tapper != controller):
            return False
        if self.types is None and not self.basic:
            return True
        if source.zone is Zone.BATTLEFIELD:
            chars = game.characteristics_of(source)
            types, supertypes = chars.types, chars.supertypes
        else:
            types, supertypes = tuple(source.types), tuple(source.card.supertypes)
        if self.basic and Supertype.BASIC not in supertypes:
            return False
        return self.types is None or any(wanted in types for wanted in self.types)

    def apply(self, produced: list[Color]) -> list[Color]:
        if self.colorless_instead:
            return [Color.COLORLESS]
        return [color for color in produced for _ in range(self.multiplier)]


class UnwiredChoiceNotice(EngineModel):
    """A card's own sentence reads back "the chosen color/card name/creature
    type" (CR 614.12a's choice, once made), but this wave only performs two
    shapes that add mana - `machines/effects.py`'s "adds an additional ..."
    clause, and `machines/abilities.ManaAbility`'s own "{T}: Add ... mana of
    the chosen color" printed ability (Room of Refuge, Sunken Citadel).
    Recorded instead of the card silently doing nothing, the same shape
    `AnaphoricClauseNotice`/`ConditionalClauseNotice`/`LayerNotice` already
    use elsewhere in this codebase for a clause this read but did not
    perform.

    The "as this enters, choose ..." cards that land here (Pithing Needle's
    and Disruptor Flute's activation line has since been wired - see
    `_WIRED_CHOSEN_NAME_PROHIBITION_HINT_RE` - and is kept below only as the
    history of why it once did):

    - **Runed Halo** - "You have protection from the chosen card name." is a
      layer 6 static ability (CR 613.1f) granted to a *player*, not a
      permanent; nothing in `machines/layers.py` grants protection to a
      player at all yet (its whole static-ability sweep is permanent-only).
    - **Pithing Needle** / **Disruptor Flute** (wired now, no longer here) -
      "Activated abilities of sources with the chosen name can't be
      activated unless they're mana abilities." is enforced by
      `Game.activation_prohibition` (CR 602.5). Disruptor Flute's *other* line, "Spells with the
      chosen name cost {3} more to cast.", is no longer here: CR 601.2f's
      cost-increase step reads it as `CostModifierKind.NAMED_INCREASE` and
      `Game.static_cost_modifiers_for` compares the chosen name against the
      spell being cast, so only the activation line of that card still lands
      on this list.
    - **Cavern of Souls** - "Spend this mana only to cast a creature spell of
      the chosen type, and that spell can't be countered." restricts what a
      floating mana symbol may pay for and grants an uncounterable quality to
      whatever it paid for; `models/mana.ManaPool` tracks color and snow-ness
      only, nothing that could carry a spend restriction.

    **Voice of All** is the fourth color-choosing card and is not listed
    here: "This creature has protection from *the chosen color*" already
    matches `machines/layers.py`'s generic `_LOOKS_LIKE_LAYER_EFFECT_RE`
    (subject "this creature" + "has") and fails `_parse_layer_sentence` (no
    shape reads a literal "the chosen color" as a quality), so
    `effects_for` already records a `LayerNotice` for it with no new code -
    proof the generic fail-closed net catches a permanent-targeted grant on
    its own; only the player-targeted and cost/restriction shapes needed a
    notice built here.

    None of the four attempted consumers listed above is wired - CR
    614.12a's choice itself is (`CardState.choice`), and the two payoffs
    performed end to end are the "adds an additional" mana clause (Utopia
    Sprawl, Leyline of Abundance, Badgermole Cub) and the printed "{T}: Add
    ... mana of the chosen color" ability (Room of Refuge, Sunken Citadel).
    """

    source_id: UUID
    source_name: str
    text: str


class UnreadableCopyExceptionNotice(EngineModel):
    """A card's "enter as a copy of X, except ..." tail exists but this parser
    could not read it - recorded instead of the copy silently applying no
    exception at all, the same shape `UnwiredChoiceNotice`/`LayerNotice`/
    `AnaphoricClauseNotice` already use elsewhere in this module for a clause
    that was read but could not be performed.

    CR 707.9b makes the copy and its exception one computation: "The final set
    of values for that characteristic becomes part of the copiable values of
    the copy." An unreadable exception therefore means the *whole* copiable
    result is unknown, not that the exception happens to be empty - applying
    the plain copy anyway would be running half of CR 608.2c's single
    instruction, silently. `_enters_as_copy` records this and skips the entire
    "enter as a copy" replacement rather than guessing: the permanent enters
    as itself.

    This is what closes a real defect found live this session: Echoing Deeps
    - "You may have this land enter tapped as a copy of any land card in a
    graveyard, except it's a Cave in addition to its other types" - has no
    power/toughness in its exception, which the parser required before this
    fix, so `copy_exception` silently defaulted to no modification at all and
    the land entered as a plain copy with no Cave type. Echoing Deeps' own
    tail is genuinely readable (see `_COPY_EXCEPT_PT_AND_TYPES`) and no longer
    reaches this notice; Mockingbird's "... and it has flying" still does,
    since granting an ability is not a shape this module parses yet.
    """

    source_id: UUID
    source_name: str
    text: str


def _leaving_the_stack(event: ReplaceableEvent) -> bool:
    return event.kind is EventKind.ZONE_CHANGE and event.origin is Zone.STACK


def _stack_replacements(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """A spell's own replacement effects for leaving the stack (CR 604.5).

    Two keywords put a static ability on the *spell*, and CR 604.5 - "some
    static abilities apply while a spell is on the stack" - is what lets it
    function there. Flashback says so itself, in as many words: CR 702.34a calls
    it "another [static ability] that functions while the card is on the stack".
    Both replace where the
    card goes when it stops being a spell, so neither can be read off the
    battlefield the way `REPLACEMENTS` entries are - the object generating the
    effect is the object being moved.

    - **CR 702.34a** - "Flashback [cost]" means, in part, "If the flashback cost
      was paid, exile this card instead of putting it anywhere else any time it
      would leave the stack." *Any* time, so this catches a countered or
      fizzled flashback spell as well as a resolved one.
    - **CR 715.3d** - "Instead of putting a spell that was cast as an Adventure
      into its owner's graveyard as it resolves, its controller exiles it. For
      as long as that card remains exiled, that player may play it."

    Whether the cost was paid or the Adventure face was chosen is a fact about
    the announcement, which the `CardState` does not carry; `Game.cast_records`
    does (CR 601.2b).
    """
    card = event.card
    if card is None or not _leaving_the_stack(event):
        return []

    found: list[ApplicableEffect] = []
    from ..resolving_exile import apply_resolving_exile, resolving_exile_of

    if (
        event.resolving
        and event.destination is Zone.GRAVEYARD
        and resolving_exile_of(card) is not None
    ):
        # CR 614.1a: a cast trigger's "exile that card [with a <kind>
        # counter on it] instead of putting it into your graveyard as it
        # resolves" (Goliath Daydreamer, Feather, the Redeemed, Lilah,
        # Undefeated Slickshot) - recorded on the spell by the trigger.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:resolving_exile",
                source=card,
                label="exiled instead of put into the graveyard as it resolves",
                apply=lambda game, source, event: apply_resolving_exile(game, event.card, event),
            )
        )
    record = game.cast_record(card)

    if record.keyword is not None and record.keyword.lower() == "flashback":
        found.append(
            ApplicableEffect(
                key=f"{card.id}:flashback",
                source=card,
                label="if the flashback cost was paid, exile this card instead (CR 702.34a)",
                apply=_exile_instead,
            )
        )
    from ..casting import CAST_PERMISSION, exiles_spells_cast_this_way

    if (
        record.keyword == CAST_PERMISSION
        and event.destination is Zone.GRAVEYARD
        and card.controller is not None
        and exiles_spells_cast_this_way(game, card.controller)
    ):
        # Jaya Ballard's emblem: "If a spell cast this way would be put into
        # your graveyard, exile it instead." - a replacement (CR 614.1a) on a
        # spell recorded as cast under that emblem's own permission.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:cast-permission",
                source=card,
                label="a spell cast this way is exiled instead of put into the graveyard",
                apply=_exile_instead,
            )
        )
    if record.exile_instead_of_graveyard:
        # Dire Fleet Daredevil's/Nita, Forum Conciliator's own rider on the
        # "exile target ... you may cast it ..." grant (CR 604.5) - the same
        # unconditional "any time it would leave the stack" shape flashback's
        # own second static already gets, just recorded through a plain
        # boolean instead of `record.keyword` since the grant names no
        # keyword at all.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:exile_instead_of_graveyard",
                source=card,
                label="if that spell would be put into a graveyard, exile it instead",
                apply=_exile_instead,
            )
        )
    if record.keyword is not None and record.keyword.lower() == "harmonize":
        # CR 702.180a's third static ability: "If the harmonize cost was
        # paid, exile this card instead of putting it anywhere else any
        # time it would leave the stack." Structurally identical to
        # flashback's own clause just above - a second `record.keyword`
        # value reaching the same `_exile_instead`, not a new mechanism.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:harmonize",
                source=card,
                label="if the harmonize cost was paid, exile this card instead (CR 702.180a)",
                apply=_exile_instead,
            )
        )
    from ..aftermath import exiles_on_leaving_the_stack

    if exiles_on_leaving_the_stack(card, record.origin_zone, record.face):
        # CR 702.127a's third static ability: "If this spell was cast from a
        # graveyard, exile it instead of putting it anywhere else any time it
        # would leave the stack." - resolved or countered alike.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:aftermath",
                source=card,
                label="aftermath: cast from a graveyard, exile it instead (CR 702.127a)",
                apply=_exile_instead,
            )
        )
    from ..keywords import has_rebound_now  # imported here: casting imports this module's siblings

    if has_rebound_now(card) and record.origin_zone is Zone.HAND and event.resolving:
        # CR 702.88a: "If this spell was cast from your hand, instead of
        # putting it into your graveyard as it resolves, exile it." A spell
        # cast from anywhere else - most pointedly from exile by its own
        # previous rebound recast - never triggers this a second time, which
        # is what stops an infinite exile-and-recast loop; `record.origin_zone`
        # is `Casting.origin_zone` as the spell was actually announced, not a
        # fact about the card's printed text.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:rebound",
                source=card,
                label="cast from hand with rebound: exile this card instead (CR 702.88a)",
                apply=_exile_instead,
            )
        )
    from ..keywords import has_paradigm  # imported here: casting imports this module's siblings

    if has_paradigm(card.card) and event.resolving:
        # CR 702.192a: Paradigm "represents two spell abilities ... 'Exile
        # this spell.'" Unlike rebound's "if cast from your hand", this half
        # is unconditional - every resolution of a Paradigm spell is exiled
        # instead of going to the graveyard, whether it is the original cast
        # or a later free-cast copy created by `models/game.py`'s own
        # `_create_paradigm_delayed_trigger`/`ParadigmCopyAndCast`.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:paradigm",
                source=card,
                label="Paradigm: exile this spell instead (CR 702.192a)",
                apply=_exile_instead,
            )
        )
    from ..casting import adventure_face  # imported here: casting imports this module's siblings

    adventure = adventure_face(card.card)
    cast_as_adventure = adventure is not None and record.face == adventure.name
    if cast_as_adventure and event.destination is Zone.GRAVEYARD:
        found.append(
            ApplicableEffect(
                key=f"{card.id}:adventure",
                source=card,
                label="a spell cast as an Adventure is exiled instead (CR 715.3d)",
                apply=_exile_adventured_instead,
            )
        )
    if event.resolving and event.destination is Zone.GRAVEYARD:
        # CR 304.2/307.2: "the actions stated in its rules text are followed.
        # Then it's put into its owner's graveyard" - a spell whose own text
        # already shuffled itself into the library during that first part
        # never reaches the second, the same "instead of graveyard, elsewhere"
        # shape as rebound just above, gated the same way on `event.resolving`
        # (CR 701.6a: a countered spell "doesn't resolve and none of its
        # effects occur", so this must never fire for one - the whole reason
        # this reads `event.resolving` rather than "leaving the stack" the way
        # flashback's *any*-exit exile does).
        match = _SELF_SHUFFLE_INTO_LIBRARY_RE.search(card.oracle_text)
        if match is not None and _refers_to_self(match.group("name"), _names_of(card.card)):
            found.append(
                ApplicableEffect(
                    key=f"{card.id}:self_shuffle",
                    source=card,
                    label=(
                        "shuffled into its owner's library instead, as it "
                        "resolves (CR 304.2/307.2, 701.24c)"
                    ),
                    apply=_shuffle_into_library_instead,
                )
            )
    return found


def _protection_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """Protection preventing damage from a source with the stated quality.

    CR 702.16e: "Any damage that would be dealt by sources that have the stated
    quality to a permanent or player with protection is prevented." Protection
    is a static ability (CR 702.16a) of the *damaged* object rather than of a
    third permanent watching, so it cannot be a `REPLACEMENTS` entry - it belongs
    to whatever is being damaged, and the target of the event is where to look.

    `Game.protection_from_damage` does the reading, because the quality matcher
    and the protection parser both live there.
    """
    reason = game.protection_from_damage(event)
    if reason is None or event.card is None:
        return []
    return [
        ApplicableEffect(
            key=f"{event.card.id}:protection",
            source=event.card,
            label=reason,
            apply=_prevent_all,
        )
    ]


def _shield_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """The prevention shields waiting on this damage event (CR 615.1, 615.7-615.9).

    CR 615.1 puts prevention effects in the same machinery as replacement
    effects - "Like replacement effects (see rule 614), prevention effects apply
    continuously as events happen" - and CR 616.1 orders the two kinds together,
    which is why they are gathered here rather than applied separately in
    `Game.deal_damage`.

    A shield has no source permanent: CR 615.4 has it created before the damage
    and CR 615.3 has it last "until [it is] used up or [its] duration has
    expired", both of which can outlive whatever made it.
    """
    if event.kind is not EventKind.DAMAGE:
        return []

    def applier(shield: object) -> Apply:
        def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
            game.apply_prevention_shield(shield, event)

        return apply

    return [
        ApplicableEffect(
            key=f"shield:{index}",
            source=None,
            label=shield.label,
            apply=applier(shield),
            controller_username=shield.controller,
        )
        for index, shield in enumerate(game.prevention_shields)
        if game.shield_applies(shield, event)
    ]


#: The ability line a "can't be regenerated this turn" effect grants the
#: creature it names (CR 701.19c); `_regeneration_effects` reads it off the
#: computed characteristics, so it ends with the effect's duration.
CANT_BE_REGENERATED_LINE = "This creature can't be regenerated."


def _cant_be_regenerated(game: "Game", permanent: CardState) -> bool:
    return CANT_BE_REGENERATED_LINE in game.characteristics_of(permanent).abilities


def _regeneration_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """The regeneration shields waiting on this destruction (CR 701.19a).

    CR 701.19a: "If the effect of a resolving spell or ability regenerates a
    permanent, it creates a replacement effect that protects the permanent the
    next time it would be destroyed this turn. In this case, 'Regenerate
    [permanent]' means 'The next time [permanent] would be destroyed this
    turn, instead remove all damage marked on it and its controller taps it.
    If it's an attacking or blocking creature, remove it from combat.'"

    Gathered here rather than checked inside `Game.destroy` so that CR 616.1's
    ordering applies to it exactly as it does to umbra armor and to the
    prevention shields just above - two destruction-replacements on one
    permanent is a choice the rules give somebody, not a fixed precedence this
    function gets to invent.

    Like a prevention shield (and unlike umbra armor) it has no source
    permanent: CR 701.19a's effect outlives whatever created it, right up to
    the end of the turn. `controller_username` is the permanent's own
    controller, since CR 701.19a names them as the player who taps it.

    `event.regeneration_allowed` is CR 701.19c's prohibition - see that field.
    """
    if event.kind is not EventKind.DESTROY or event.replaced:
        return []
    if not event.regeneration_allowed:
        return []
    permanent = event.card
    if permanent is None or permanent.regeneration_shields <= 0:
        return []
    if _cant_be_regenerated(game, permanent):
        return []  # CR 701.19c: the shield is not applied (and not used up)

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        card = event.card
        if card is None:
            return
        card.regeneration_shields -= 1
        card.damage = 0
        game.tap_permanent(card)
        game.combat.remove(card.id)  # CR 506.4
        event.replaced = True

    return [
        ApplicableEffect(
            key=f"regeneration:{permanent.id}",
            source=None,
            label="regeneration shield: tap it and remove it from combat instead (CR 701.19a)",
            apply=apply,
            controller_username=game.controller_of(permanent).username,
        )
    ]


# --------------------------------------------------------------------------
# Replacement effects a resolving spell or ability leaves behind
# --------------------------------------------------------------------------
#
# "Until end of turn, if target player would draw a card, instead that player
# skips that draw and you draw a card." (Plagiarize), "{4}{W}: Until end of
# turn, if you would put one or more +1/+1 counters on a creature you
# control, put that many plus one +1/+1 counters on it instead." (Prairie
# Dog), "If a creature would enter the battlefield under an opponent's control
# this turn, it enters under your control instead." (Gather Specimens).
#
# CR 614.1a makes each a replacement effect; CR 611.2a gives it the duration
# it states, independent of the object that made it - so unlike every static
# replacement above there is no permanent to ask while it lasts, and it is
# stored on `Game.created_replacements` as a `CreatedReplacement` until CR
# 514.2's cleanup step ends it. What it does is data - one of the `kind`-
# tagged shapes below - so a game carrying one round-trips through
# `Game.model_dump` and applies identically after decode.
#
# Each shape is read by one reader shared with the printed static form of the
# same sentence: `DrawSkipReplacement` is Notion Thief's static line too,
# `CounterAmountReplacement` is Hardened Scales' (`_compile_counter_doubler`
# wraps the same spec). The static form's "you" is its permanent's
# controller; the created form's is the player who controlled the creating
# spell or ability as it resolved.


class DrawSkipReplacement(EngineModel):
    """ "If `<player>` would draw a card[ except the first one they draw in
    each of their draw steps], [instead ]that player skips that draw[ and you
    draw a card][ instead]."

    CR 614.6: "If an event is replaced, it never happens. A modified event
    occurs instead" - "that player skips that draw and you draw a card" is the
    same draw, now yours, so `apply` hands the event itself to the replacing
    player rather than raising a fresh draw. That is what CR 614.5 needs: the
    modified draw is one this effect has already had its opportunity at, so
    Plagiarize on yourself does not loop (ruling 2004-10-04), and two players'
    Plagiarizes on each other hand the draw back (ruling 2007-07-15), the same
    shape Notion Thief's own two-Thieves ruling (2018-03-16) describes.

    `affected` is who "would draw": `"player"` is one named player
    (`affected_player` - Plagiarize's "target player", fixed at resolution),
    `"opponent"`/`"you"` are read against the effect's controller, `"any"` is
    "a player". `you_draw` false is Possessed Portal's bare "skips that draw".
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["draw_skip"] = "draw_skip"
    affected: Literal["player", "opponent", "you", "any"]
    affected_player: str | None = None
    except_first_draw_step_draw: bool = False
    you_draw: bool = True

    def applies(self, game: "Game", controller: str, event: "ReplaceableEvent") -> bool:
        if event.kind is not EventKind.DRAW or event.player is None or event.amount <= 0:
            return False
        if self.except_first_draw_step_draw and event.draw_step_draw:
            return False
        drawer = event.player.username
        if self.affected == "player":
            return drawer == self.affected_player
        if self.affected == "opponent":
            return drawer != controller
        if self.affected == "you":
            return drawer == controller
        return True

    def apply(self, game: "Game", controller: str, event: "ReplaceableEvent") -> None:
        if not self.you_draw:
            event.amount = 0
            return
        event.player = game.player(controller)
        event.draw_step_draw = False


class CounterAmountReplacement(EngineModel):
    """ "If one or more `<kind>` counters would be put on `<a subject>`
    [you control], `<N times | that many plus/minus N>` ... instead" and the
    active-voice "If you would put one or more `<kind>` counters on `<a
    subject>` [you control], put that many plus N ... instead" (Prairie Dog).

    CR 122.6: counters an object is given as it enters count as counters put
    on it, so both routes reach `EventKind.ADD_COUNTERS`. `you_put` is the
    active voice's "you would put": the event's `putter` must be the
    effect's controller, so an opponent's effect putting counters on your
    creature is left alone. `types` `None` is "a permanent"; `counter_kind`
    `None` is any kind. CR 107.1b floors the result at zero.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["counter_amount"] = "counter_amount"
    counter_kind: str | None = None
    types: tuple[Type, ...] | None = None
    you_control: bool = False
    you_put: bool = False
    #: "If an opponent would put ..." (Vorinclex, Monstrous Raider): the
    #: event's putter (CR 122.6a) is some player other than the controller.
    opponent_puts: bool = False
    #: "... on a permanent or player": a player getting counters is the
    #: event too (CR 122.6, `Game.add_player_counters`).
    players: bool = False
    multiplier: int = 1
    addend: int = 0
    #: "half that many ..., rounded down/up" - divided after multiplying,
    #: rounded as printed (CR 107.1a).
    divisor: int = 1
    round_up: bool = False

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        if event.kind is not EventKind.ADD_COUNTERS or event.amount <= 0:
            return False
        if self.you_put and event.putter != controller:
            return False
        if self.opponent_puts and (event.putter is None or event.putter == controller):
            return False
        card = event.card
        if card is None:
            return self.players and event.player is not None and self.counter_kind is None
        if self.you_control and card.controller != controller:
            return False
        if self.counter_kind is not None and (
            (event.counter_kind or "").strip().lower() != self.counter_kind
        ):
            return False
        if self.types is None:
            return True
        card_types = (
            game.characteristics_of(card).types if card.zone is Zone.BATTLEFIELD else card.types
        )
        return any(wanted in card_types for wanted in self.types)

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        scaled = event.amount * self.multiplier + self.addend
        if self.divisor > 1:
            scaled = -(-scaled // self.divisor) if self.round_up else scaled // self.divisor
        event.amount = max(scaled, 0)


class EnterUnderYourControl(EngineModel):
    """ "If a creature would enter the battlefield under an opponent's control
    this turn, it enters under your control instead." (Gather Specimens) and
    "each token that would be created under an opponent's control this turn is
    created under your control instead." (Crafty Cutpurse).

    Two events, because CR 701.7b makes a token *being created* and a token
    *entering the battlefield* two: `on_creation` watches `CREATE_TOKENS` and
    moves `ReplaceableEvent.controller` (the owner stays the creator, CR
    111.2), otherwise `ENTERS_BATTLEFIELD` and the entering object's own
    controller. CR 616.1b puts either ahead of every other replacement on the
    same event (`ApplicableEffect.controls_entry`) - Crafty Cutpurse's ruling
    (2018-01-19) that an opponent's Anointed Procession then doubles nothing,
    Gather Specimens' (2008-10-01) that it applies before "enters with".

    `types` is what "a creature" names, read off the object as it would exist
    on the battlefield (CR 614.12); `tokens_only` is "each token".
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["enter_under_your_control"] = "enter_under_your_control"
    on_creation: bool = False
    types: tuple[Type, ...] = ()
    tokens_only: bool = False

    def applies(self, game: "Game", controller: str, event: "ReplaceableEvent") -> bool:
        if self.on_creation:
            if event.kind is not EventKind.CREATE_TOKENS or event.amount <= 0:
                return False
            would_be = event.creating_controller
            if would_be is None or would_be == controller:
                return False
            if not self.types:
                return True
            if event.definition is not None:
                return any(wanted in event.definition.types for wanted in self.types)
            return event.card is not None and any(
                wanted in event.card.types for wanted in self.types
            )
        card = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or card is None:
            return False
        if not card.controller or card.controller == controller:
            return False
        if self.tokens_only and not is_token(card):
            return False
        return not self.types or any(wanted in card.types for wanted in self.types)

    def apply(self, game: "Game", controller: str, event: "ReplaceableEvent") -> None:
        if self.on_creation:
            event.controller = controller
        elif event.card is not None:
            event.card.controller = controller


class EnterUncastExile(EngineModel):
    """ "If a [nontoken] creature would enter and it wasn't cast, exile it
    instead." - Containment Priest's static line, Mistcaller's and Hallowed
    Moonlight's "Until end of turn, ..." created form (CR 614.1a).

    "Wasn't cast" is `ReplaceableEvent.was_cast` (CR 601.2 defines casting).
    "Nontoken" excludes tokens (CR 111.1) - a token exiled this way would only
    cease to exist, and the printing that says "nontoken" deliberately does
    not do that; the one that does not say it (Hallowed Moonlight) does.
    `types` is read off the entering object as it would exist on the
    battlefield (CR 614.12). No "you" anywhere: every player's creatures.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["enter_uncast_exile"] = "enter_uncast_exile"
    types: tuple[Type, ...] = (Type.CREATURE,)
    nontoken: bool = True

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        card = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or event.was_cast or card is None:
            return False
        if self.nontoken and is_token(card):
            return False
        return any(wanted in card.types for wanted in self.types)

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        event.destination = Zone.EXILE


class LeaveBattlefieldExile(EngineModel):
    """ "If it would leave the battlefield, exile it instead of putting it
    anywhere else." - the rider a resolving ability gives the one permanent it
    just returned (Whip of Erebos; CR 702.84a spells the same sentence out for
    unearth). CR 614.1a makes it a replacement effect.

    Bound to one object: `stamp` is its `zone_change_stamp` when the rider was
    created, so a permanent that left and came back is a new object the rider
    no longer names (CR 400.7). No duration is printed, so it lasts as long as
    that object stays on the battlefield (CR 611.2a); the source ability
    leaving changes nothing, which is why this is a stored record and not
    read off a permanent.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["leave_battlefield_exile"] = "leave_battlefield_exile"
    object_id: UUID
    stamp: UUID

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        card = event.card
        return (
            leaves_the_battlefield_not_to_exile(event)
            and card is not None
            and card.id == self.object_id
            and card.zone_change_stamp == self.stamp
        )

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        event.destination = Zone.EXILE


def exile_instead_of_leaving(
    game: "Game",
    permanent: CardState,
    *,
    controller: str,
    source_id: UUID | None,
    source_name: str,
) -> None:
    """Give `permanent`, as the object it is now, CR 702.84a's "If it would
    leave the battlefield, exile it instead of putting it anywhere else."
    Stored on `Game.created_replacements` with no end of turn, because it
    lasts as long as the object does (CR 611.2a)."""
    game.created_replacements.append(
        CreatedReplacement(
            spec=LeaveBattlefieldExile(object_id=permanent.id, stamp=permanent.zone_change_stamp),
            label="if it would leave the battlefield, exile it instead",
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            until_end_of_turn=False,
        )
    )


class DieToExileReplacement(EngineModel):
    """ "If a creature [an opponent controls] would die this turn, exile it
    instead." - a resolving spell's own turn-long replacement (CR 614.1a,
    CR 611.2a). CR 700.4: "dies" is put into a graveyard from the
    battlefield, so the event is that zone change of an object that is a
    creature on the battlefield as it would leave.

    CR 611.2c: it changes no characteristics, so it is not locked to the
    creatures present when it began - a creature entering, or coming under
    an opponent's control, later this turn is caught too (Malicious Eclipse's
    and Cry of the Carnarium's rulings). `whose` is read against the dying
    creature's controller (CR 108.4) at the moment it would die.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["die_to_exile"] = "die_to_exile"
    #: `None` every creature; "opponent" one an opponent of the effect's
    #: controller controls; "you" one the effect's controller controls.
    whose: Literal["opponent", "you"] | None = None
    nontoken: bool = False

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        if not _to_graveyard(event) or event.origin is not Zone.BATTLEFIELD:
            return False
        card = event.card
        if card is None or Type.CREATURE not in game.characteristics_of(card).types:
            return False
        if self.nontoken and is_token(card):
            return False
        if self.whose == "opponent":
            return _is_opponent(game, card.controller, controller)
        if self.whose == "you":
            return card.controller == controller
        return True

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        event.destination = Zone.EXILE


class GainNoLifeReplacement(EngineModel):
    """ "If that player [or that planeswalker's controller] would gain life
    this turn, that player gains no life instead." (Flames of the Blood Hand)
    - a resolving spell's own turn-long replacement (CR 614.1a, CR 611.2a),
    on the one player it named as it resolved. CR 119.10: it is a life-gain
    event that would happen which is replaced, so a gain of 0 never reaches
    it; the gain becomes none, and with it CR 603.2g's trigger never fires.
    Unlike CR 119.7's "can't gain life", it is a replacement: CR 616.1 orders
    it with the player's other life-gain replacements."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["gain_no_life"] = "gain_no_life"
    player: str

    def applies(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> bool:
        return (
            event.kind is EventKind.GAIN_LIFE
            and event.amount > 0
            and event.player is not None
            and event.player.username == self.player
        )

    def apply(self, game: "Game", controller: str | None, event: "ReplaceableEvent") -> None:
        event.amount = 0


#: What a `CreatedReplacement` does - a `kind`-tagged union, refused at decode
#: for an unknown tag rather than silently doing nothing.
CreatedReplacementSpec = Annotated[
    DrawSkipReplacement
    | CounterAmountReplacement
    | EnterUnderYourControl
    | EnterUncastExile
    | LeaveBattlefieldExile
    | DamageLifeFloorReplacement
    | DieToExileReplacement
    | GainNoLifeReplacement
    | DamageModifierReplacement
    | PreventDamageByReplacement
    | DamageCantBePreventedReplacement
    | DamageRedirectReplacement
    | TurnDamageGroup,
    Field(discriminator="kind"),
]


class CreatedReplacement(EngineModel):
    """One replacement effect a resolved spell or ability left on the game
    (CR 614.1a, CR 611.2a). `controller` is CR 109.5's "you": whoever
    controlled the creating spell or ability as it resolved - the source
    itself may be long gone. Ended by `Game.cleanup_step` (CR 514.2)."""

    id: UUID = Field(default_factory=new_id)
    spec: CreatedReplacementSpec
    label: str
    controller: str
    source_id: UUID | None = None
    source_name: str
    until_end_of_turn: bool = True


def _created_replacement_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """Every `Game.created_replacements` record that applies to this event.
    Sourceless like a prevention shield (CR 615.1): the controller recorded at
    creation is who CR 616.1 treats as the effect's controller."""
    found: list[ApplicableEffect] = []
    for record in game.created_replacements:
        # A `TurnDamageGroup` is several effects of one spell (CR 608.2c),
        # each applying on its own and keyed apart (CR 614.5).
        parts = (
            list(enumerate(record.spec.parts))
            if isinstance(record.spec, TurnDamageGroup)
            else [(None, record.spec)]
        )
        for index, spec in parts:
            if not spec.applies(game, record.controller, event):
                continue

            def apply(
                game: "Game",
                source: CardState | None,
                event: ReplaceableEvent,
                record: CreatedReplacement = record,
                spec: object = spec,
            ) -> None:
                spec.apply(game, record.controller, event)  # type: ignore[attr-defined]

            found.append(
                ApplicableEffect(
                    key=f"created:{record.id}" + ("" if index is None else f":{index}"),
                    source=None,
                    label=record.label,
                    apply=apply,
                    controller_username=record.controller,
                    controls_entry=isinstance(spec, EnterUnderYourControl),
                    prevention=bool(getattr(spec, "prevention", False)),
                )
            )
    return found


class DrawReplacementKind(StrEnum):
    """The shapes a `NextTimeDrawReplacement` can take. One variant today,
    the same open-ended enum pattern `ShieldKind` already gives CR 615.8's
    "next time [a source] would deal damage" shield - a new variant is a
    schema bump, not a new stored type, the next time this pool needs one."""

    #: "Instead [player] exiles the top card of their library[. They may
    #: play it this turn.]" - Urabrask, Heretic Praetor's own second
    #: trigger.
    EXILE_TOP_CARD = "exile_top_card"


class NextTimeDrawReplacement(EngineModel):
    """One player's *next* draw this turn, replaced with something else
    (CR 614.1a's "the next time ... would ..., instead ..." shape), rather
    than every draw for a duration the way `DrawSkipReplacement` reads Plagiarize's
    "until end of turn, if ... would draw ..., instead ...".

    Urabrask, Heretic Praetor prints the only one in this pool: "At the
    beginning of each opponent's upkeep, the next time they would draw a
    card this turn, instead they exile the top card of their library. They
    may play it this turn." The trigger's own resolution installs this
    record; nothing else happens when it resolves - the same division
    `Game.create_prevention_shield` already draws for CR 615.8 ("creating the
    shield *is* the effect").

    Stored on `Game.next_time_draw_replacements` for the same reason
    `Game.prevention_shields` and `Game.created_replacements` are stored rather
    than closed over: the ability that created it is off the stack by the
    time a future draw event checks for it, and CR 514.2's cleanup step needs
    an unused one to expire with every other "this turn" effect.
    """

    kind: DrawReplacementKind
    label: str
    """What the effect says, for the event trace."""

    controller: str
    """Who created it - `ApplicableEffect` needs a controller for CR 616.1's
    ordering, and the ability that made this may be off the stack by the time
    it fires."""

    affected: str
    """The player whose draw is replaced - Urabrask's own "they"."""

    grants_play_permission: bool = False
    """"They may play it this turn." - CR 601.3, via `Game.
    grant_play_permission`, the same primitive Ragavan, Nimble Pilferer and
    Emry, Lurker of the Loch already use."""

    action: PlayAction = PlayAction.PLAY
    """CR 601.1a's "play"/"cast" distinction, read off the printed permission
    sentence - only meaningful when `grants_play_permission` is set."""

    pays_mana_cost: bool = True
    """CR 118.9: whether the permission includes "without paying its mana
    cost" - only meaningful when `grants_play_permission` is set."""

    spent: bool = False
    """CR 614.5: applied at most once. Consumed on the very next draw event
    for `affected`, however that draw happens."""

    until_end_of_turn: bool = True
    """CR 514.2 ends an unused one in the cleanup step, alongside every other
    "this turn" effect."""


def _finality_counter_effects(event: ReplaceableEvent) -> list[ApplicableEffect]:
    """A finality counter's replacement effect (CR 122.1h): "One or more
    finality counters on a permanent create a single replacement effect that
    stops the permanent from going to the graveyard. That effect is 'If this
    permanent would be put into a graveyard from the battlefield, exile it
    instead.'"

    Gathered here rather than checked inside `Game.put_into_graveyard` so CR
    616.1 orders it against every other graveyard replacement (Rest in Peace)
    the way it orders any two. One effect however many counters there are,
    keyed by the permanent, so CR 614.5 applies it once. Like a regeneration
    shield it has no source permanent to ask, so its controller is the
    permanent's own.
    """
    if event.kind is not EventKind.ZONE_CHANGE or event.destination is not Zone.GRAVEYARD:
        return []
    if event.origin is not Zone.BATTLEFIELD:
        return []
    permanent = event.card
    if permanent is None or permanent.counter_count(Counter.FINALITY) <= 0:
        return []
    return [
        ApplicableEffect(
            key=f"finality:{permanent.id}",
            source=None,
            label="finality counter: exile it instead (CR 122.1h)",
            apply=_exile_instead_of_graveyard,
            controller_username=permanent.controller,
        )
    ]


def _exile_instead_of_graveyard(
    game: "Game", source: CardState | None, event: ReplaceableEvent
) -> None:
    event.destination = Zone.EXILE


def _die_to_exile_this_turn_effects(
    game: "Game", event: ReplaceableEvent
) -> list[ApplicableEffect]:
    """Essence Burn's own rider (CR 614.1a): "If that permanent would die this
    turn, exile it instead" - one specific permanent, named by a resolved
    spell that is long gone by the time the replacement ever fires, so the
    marker is kept on `Game.die_to_exile_this_turn` the same way `Game.draw_
    redirections` keeps Plagiarize's own sourceless redirection alive.
    """
    if event.kind is not EventKind.ZONE_CHANGE or event.destination is not Zone.GRAVEYARD:
        return []
    if event.origin is not Zone.BATTLEFIELD:
        return []
    permanent = event.card
    if permanent is None or permanent.id not in game.die_to_exile_this_turn:
        return []
    return [
        ApplicableEffect(
            key=f"die_to_exile_this_turn:{permanent.id}",
            source=None,
            label="if it would die this turn, exile it instead",
            apply=_exile_instead_of_graveyard,
            controller_username=permanent.controller,
        )
    ]


def _next_time_draw_replacement_effects(
    game: "Game", event: ReplaceableEvent
) -> list[ApplicableEffect]:
    """The unspent "next time [player] would draw a card this turn, instead
    ..." replacements waiting on this draw event (CR 614.1a, CR 614.5).

    Sourceless, like `_created_replacement_effects`: the ability that installed
    one may be off the stack, and CR 614.6 does not care. Unlike a
    `DrawSkipReplacement`, this fires at most once - `replacement.spent` is set
    inside `apply` rather than the record being removed from `Game.
    next_time_draw_replacements`, so a player ordering several replaceable
    effects on the same draw (CR 616.1) still sees a consistent list while
    they choose, and the spent record is what CR 514.2's cleanup step (and
    every later draw this turn) then skips.
    """
    if event.kind is not EventKind.DRAW or event.player is None:
        return []

    def applier(replacement: NextTimeDrawReplacement) -> Apply:
        def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
            replacement.spent = True
            # "instead they exile the top card of their library" - the
            # event's own draw is replaced down to nothing (CR 603.2g), and a
            # *different* zone change happens in its place.
            event.amount = 0
            player = game.player(replacement.affected)
            if not player.library:
                return
            if replacement.kind is DrawReplacementKind.EXILE_TOP_CARD:
                card = game.exile_permanent(player.library[0])
                if replacement.grants_play_permission:
                    # "They may play it this turn." (CR 601.3), the same
                    # primitive Ragavan, Nimble Pilferer's own "you may cast
                    # that card" already grants.
                    game.grant_play_permission(
                        card,
                        replacement.affected,
                        action=replacement.action,
                        pays_mana_cost=replacement.pays_mana_cost,
                        source_name=replacement.label,
                        rule="CR 601.3",
                        zone=card.zone,
                    )

        return apply

    return [
        ApplicableEffect(
            key=f"next-time-draw-replacement:{index}",
            source=None,
            label=replacement.label,
            apply=applier(replacement),
            controller_username=replacement.controller,
        )
        for index, replacement in enumerate(game.next_time_draw_replacements)
        if not replacement.spent
        and replacement.affected == event.player.username
        and event.amount > 0
    ]


def _prevents_nothing(apply: Apply) -> Apply:
    """CR 615.12: a prevention effect applied to damage that can't be
    prevented - "Those effects won't prevent any damage, but any additional
    effects they have will take place" (The Mindskinner's mill still
    happens). The amount is put back after the effect runs."""

    def unpreventable(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        amount = event.amount
        apply(game, source, event)
        event.amount = amount

    return unpreventable


def applicable_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """Every effect that would modify this event as it stands (CR 614.1, 616.1).

    Sources are the permanents on the battlefield - CR 604.2 makes a static
    ability's continuous effect active while the permanent is there - plus, for
    a permanent entering the battlefield, the entering object's own CR 614.12
    effects, which are read while it is still on its way in, plus the two kinds
    of prevention effect that have no watching permanent behind them: the
    damaged object's own protection (CR 702.16e) and the shields a resolved
    spell left behind (CR 615.1).
    """
    found: list[ApplicableEffect] = []

    # CR 615.12: against damage that can't be prevented, prevention effects
    # prevent nothing - protection (CR 702.16e) and a shield have no other
    # effect to take place, and "existing damage prevention shields won't be
    # reduced", so neither is offered at all.
    unpreventable = game.damage_cant_be_prevented(event) is not None
    if not unpreventable:
        found.extend(_protection_effects(game, event))
        found.extend(_shield_effects(game, event))
    found.extend(_regeneration_effects(game, event))
    found.extend(_finality_counter_effects(event))
    found.extend(_die_to_exile_this_turn_effects(game, event))
    found.extend(_created_replacement_effects(game, event))
    found.extend(_next_time_draw_replacement_effects(game, event))

    if event.kind is EventKind.ENTERS_BATTLEFIELD and event.card is not None:
        entering = event.card
        for suffix, apply, label, copy_as_it_enters in _self_enters_modifiers(
            game,
            entering,
            entering_as_copy=event.entering_as_copy,
            entering_transformed=event.transformed,
        ):
            found.append(
                ApplicableEffect(
                    key=f"{entering.id}:{suffix}",
                    source=entering,
                    label=label,
                    apply=apply,
                    copy_as_it_enters=copy_as_it_enters,
                )
            )
        found.extend(_impending_entering_counters(game, event))
        found.extend(_bloodthirst_entering_counters(game, event))
        found.extend(_vanishing_entering_counters(game, event))
        found.extend(_group_entering_counters(game, event))

    found.extend(_stack_replacements(game, event))

    # One board, hoisted out of the loop below: `computed_board()` recomputes
    # the whole battlefield on every call (CR 613.5), and `replacements_of_
    # state` now asks it once per permanent for its computed abilities.
    board = game.computed_board()
    for permanent in list(game.battlefield):
        for index, printed in enumerate(replacements_of_state(game, permanent, board)):
            if printed.applies(game, permanent, event):
                apply = printed.apply
                if printed.prevention and unpreventable:
                    apply = _prevents_nothing(apply)
                found.append(
                    ApplicableEffect(
                        key=f"{permanent.id}:{index}",
                        source=permanent,
                        label=printed.label,
                        apply=apply,
                        prevention=printed.prevention,
                    )
                )

    return [effect for effect in found if effect.key not in event.applied]


def order_effects(
    game: "Game", event: ReplaceableEvent, candidates: Iterable[ApplicableEffect]
) -> list[ApplicableEffect]:
    """Put the applicable effects in the order they will be applied (CR 616.1).

    The rules hand the choice to the affected object's controller, one effect at
    a time; `choose_effect` puts that question. This is the order it offers the
    options in, and the order an unscripted player takes: the effects that
    player controls come first, then everybody else's, each group in
    battlefield order.

    CR 616.1a-d's forced choices are checked first even so, because they are not
    a matter of preference: a self-replacement effect (CR 614.15) must be chosen
    before anything else, then a control-changing one (CR 616.1b), then a
    copy-as-it-enters one (CR 616.1c). The second and third are effects this
    engine performs - Gather Specimens' and Crafty Cutpurse's "enters/is created
    under your control instead" (`EnterUnderYourControl`), Clone's "enters as a
    copy of" - and are sorted ahead of everything else here, in that order. The
    first is still a hook with nothing to hang on it.
    """
    ordered = list(candidates)
    chooser = event.chooser(game)
    ordered.sort(
        key=lambda effect: (*_forced_tier(effect), 0 if effect.controller == chooser else 1)
    )
    return ordered


def _forced_tier(effect: ApplicableEffect) -> tuple[int, int]:
    """CR 616.1b, then 616.1c: the tiers a free choice (CR 616.1e) comes after."""
    return (0 if effect.controls_entry else 1, 0 if effect.copy_as_it_enters else 1)


def choose_effect(
    game: "Game", event: ReplaceableEvent, candidates: Iterable[ApplicableEffect]
) -> ApplicableEffect:
    """The one effect to apply next, chosen by the affected player (CR 616.1).

    "The affected object's controller (or its owner if it has no controller)
    or the affected player chooses one to apply." CR 616.1a-c narrow the
    choice to the forced tier first; within whatever tier is left, the chooser
    is asked through `Game.ask` - a "choose one" among named options, the
    question `CHOOSE_A_MODE` already puts, rather than a new kind every client
    would have to learn. The prompt carries CR 616.1 so a seat can tell it
    from a modal spell's.

    Nothing is asked when there is no choice: one effect in the tier, no
    affected player, or every option being the same printed effect under the
    same controller (two Solphims - either order is the same order). CR 616.1f
    repeats the process after each application, and `apply_replacements`
    calls this again each time, so the second of two effects is never asked
    about.
    """
    ordered = order_effects(game, event, candidates)
    tier = [effect for effect in ordered if _forced_tier(effect) == _forced_tier(ordered[0])]
    chooser = event.chooser(game)
    distinct = {(effect.name, effect.label, effect.controller) for effect in tier}
    if len(tier) < 2 or chooser is None or len(distinct) < 2:
        return ordered[0]
    if all(
        effect.source is not None
        and effect.source is event.card
        and not effect.copy_as_it_enters
        and not effect.controls_entry
        for effect in tier
    ):
        # The entering permanent's own CR 614.12 modifiers ("enters tapped",
        # "as it enters, choose a color") each change a different aspect of
        # the one object, so every order gives the same permanent - no choice
        # worth asking, the same reasoning as two identical effects above.
        return ordered[0]
    options = _effect_options(tier)
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_A_MODE,
            player=chooser,
            prompt=(
                "choose which replacement or prevention effect applies first (CR 616.1): "
                + "; ".join(
                    f"{option} - {effect.label}"
                    for option, effect in zip(options, tier, strict=True)
                )
            ),
            options=options,
            # The object the event affects - no one effect's source asks a
            # CR 616.1 order question; `None` for an event on a player.
            source_id=source_id_of(event.card),
        )
    )
    return tier[options.index(answer)] if answer in options else tier[0]


def _effect_options(tier: list[ApplicableEffect]) -> tuple[str, ...]:
    """One distinct name per effect: the source's name where that alone tells
    them apart, else "name: label", numbered only if even that repeats."""
    names = [effect.name for effect in tier]
    options = [
        name if names.count(name) == 1 else f"{name}: {effect.label}"
        for name, effect in zip(names, tier, strict=True)
    ]
    seen: dict[str, int] = {}
    for index, option in enumerate(options):
        if options.count(option) > 1:
            seen[option] = seen.get(option, 0) + 1
            options[index] = f"{option} ({seen[option]})"
    return tuple(options)


def apply_replacements(game: "Game", event: ReplaceableEvent) -> ReplaceableEvent:
    """Run an event through every replacement effect that applies (CR 616.1).

    One effect is applied at a time; the list is then rebuilt against the
    *modified* event, so an effect that no longer applies does nothing
    (CR 614.7) and one that only now applies gets its turn (CR 616.2). Each
    effect is remembered in `event.applied` so it cannot apply twice (CR 614.5),
    which is also what makes the loop terminate.
    """
    while True:
        candidates = applicable_effects(game, event)
        if not candidates:
            return event
        chosen = choose_effect(game, event, candidates)
        event.applied.add(chosen.key)
        event.history.append(f"{chosen.name}: {chosen.label}")
        chosen.apply(game, chosen.source, event)


from .enters import (  # noqa: E402
    _bloodthirst_entering_counters,
    _cant_enter_replacements,
    _group_entering_counters,
    _impending_entering_counters,
    _refers_to_self,
    _self_enters_modifiers,
    _vanishing_entering_counters,
)
from .parse import (  # noqa: E402
    REPLACEMENTS,
    _compile,
    _damage_life_floor_replacements,
    _double_all_damage_replacements,
    _exile_instead,
    _is_opponent,
    _keyword_replacements,
    _names_of,
    _parse_oracle_text,
    _prevent_all,
    _rules_lines,
    _to_graveyard,
    is_leave_exile_line,
    parse_replacement_effects,
)
