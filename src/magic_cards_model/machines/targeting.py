"""What a spell is allowed to target, read off its oracle text (CR 115).

CR 601.2c has the caster announce "an appropriate object or player for each
target the spell requires". Appropriate is decided by the spell's own text, so
working out legality means reading the WOTC targeting templates:

    "any target"                        creature, player, planeswalker, battle
    "target creature"                   a creature on the battlefield
    "target player" / "target opponent" a player
    "target player's hand"              the player, not the hand
    "target player or planeswalker"     either
    "target spell"                      an object on the stack
    "target activated or triggered ability"  an ability on the stack
    "target creature card ... graveyard" a card in a graveyard, not a permanent
    "... you control" / "... an opponent controls"   who must control it

An **adjective** in front of the noun narrows it further, and the ones that turn
up in the pool split three ways:

    "target tapped creature"            a characteristic of the game state
    "target attacking creature"         a creature in combat
    "target noncreature spell"          a type the object must *not* have
    "target token you control"          a permanent that is not a card

The negated ones are the plainest. The CR has no numbered rule for the "non-"
prefix; it simply uses it (CR 110.3's "nontoken permanent", CR 702.108a's
"noncreature spell"), and CR 109.2 decides what the description reaches: a
description carrying a card type and no zone means a permanent on the
battlefield, CR 109.2a's "card" plus a zone means a card there, and CR 109.2b's
"spell" means a spell on the stack. So "noncreature spell" is an object on the
stack whose types do not include creature (CR 300.1 lists the card types), and
"nonland permanent card ... from your graveyard" is a card in a graveyard whose
types do not include land.

"Token" is a different kind of adjective. CR 111.1: "a token is a marker used to
represent any permanent that isn't represented by a card", and CR 108.2b and
CR 111.6 both say a token is not a card. It is still a permanent with card types
(CR 205.2c), so "target token you control" asks for a permanent on the
battlefield - and `CardState` has no way to say a permanent is one, so that half
of the restriction is read and then fails open. See `docs/engine-coverage.md`.

"Attacking" and "blocking" are not characteristics at all - CR 109.3 lists what
is, and whether a permanent is in combat is not among them. A creature "becomes
an attacking creature ... until it's removed from combat or the combat phase
ends" (CR 508.1k), a blocking one likewise (CR 509.1g), and CR 506.4 says what
removes it. That state lives on `Game.combat`, not on the permanent, so
`rejects` and `check` take an optional `game` to read it from; without one the
restriction fails open like everything else the parser cannot settle. CR 608.2b
is what then makes it matter on resolution: "other changes to the game state may
cause a target to no longer be legal".

A "target" is not always exactly one thing, so every requirement carries a
range rather than a single count:

    "target creature"                   exactly one
    "up to two target creatures"        nought to two (CR 115.6)
    "one or two target creatures"       one or two - Abzan Charm
    "one or two targets"                the same, in CR 115.4's damage wording
    "any number of target players'..."  nought to no maximum (CR 107.1c)
    "up to X target cards"              nought to X, and X may not be known yet

Two of those come with a **division** attached: "2 damage divided as you choose
among one or two targets" (Electrolyze) and "distribute two +1/+1 counters
among one or two target creatures" (Abzan Charm). CR 601.2d makes the division
part of announcing the spell rather than part of resolving it, and each target
chosen has to receive at least one of whatever is divided - which is what
`TargetingProfile.check_division` enforces. CR 115.7f then keeps the division
fixed if the targets are ever changed.

This is a template parser, not a card-text engine. Anything it cannot read
leaves the profile `understood=False` and every check passes, because refusing
a target the parser merely failed to understand would be worse than not
checking at all.

A **modal** card has no single answer here. CR 700.2c: a spell that targets
only if a particular mode is chosen needs those targets only if that mode was
chosen, and CR 700.2f and CR 115.8 both say the modes may have different
targeting requirements. So `targeting_profile` refuses to answer for a modal
card - it returns `understood=False` - and `profile_for_modes` answers for a
chosen set of modes instead. `machines/modes.py` reads the modal structure.

An **ability** on the stack is a legal target when a card says so (CR 115.2:
only permanents, "unless a spell or ability (a) specifies that it can target an
object in another zone or a player, or (b) targets an object that can't exist on
the battlefield, such as a spell or ability on the stack"). CR 113.1c makes such
an ability an object, and CR 113.9 is what lets it be countered. Its targeting
requirement is printed inside the ability rather than in the card's spell text,
so `targeting_profile` never sees it - ask `profile_for_text` with the ability's
own text instead.

`machines/abilities.py` parses mana abilities off the same oracle text; the two
are deliberately separate parsers with separate jobs.
"""

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import ConfigDict

from magic_cards_model.phrases import with_indefinite_article

from ..data.subtypes import noncreature_subtype_card_type
from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import CardState, TargetRef
from ..models.zone import Zone
from ..numbers import parse_count
from ..serialization import SortedFrozenSet
from ..snapshot import EngineModel
from .abilities import AbilityKind, TriggeredAbility, keyword_abilities, parse_abilities
from .combat import has_keyword
from .converge import colors_of_mana_spent
from .keywords import keyword_triggered_abilities
from .layers import BASIC_LAND_TYPES, CLOSED_SUBTYPE_LISTS
from .modes import Mode, modal_profile, mode_rules_text

# --------------------------------------------------------------------------
# The shape of one target a spell requires
# --------------------------------------------------------------------------


class ControllerRestriction(StrEnum):
    """Who has to control the object being targeted."""

    ANY = "any"
    YOU = "you"
    OPPONENT = "opponent"
    NOT_YOU = "not_you"
    EVENT_PLAYER = "event_player"
    """"... that player controls" in a triggered ability whose trigger event
    names a player - Soul Seizer's "When this creature deals combat damage to
    a player, ... target creature that player controls." Who "that player" is
    is not printed text but the event (`GameEvent.player`), so the printed
    phrase alone reads this and `TargetingProfile.for_event_player` binds the
    actual player into `TargetRequirement.event_player` once an ability with
    that event exists. Unbound (no event to read, a scripted choice made
    before the trigger exists), it restricts nothing - the same fail-open
    posture every restriction here takes when the caller cannot supply what
    it needs."""

    DEFENDING_PLAYER = "defending_player"
    """"... target creature defending player controls" - CR 508.5: for an
    ability of an attacking creature (or one that refers to an attacking
    creature), the player that creature is attacking, or the controller or
    protector of the planeswalker or battle it attacks. Bound off the trigger
    event's own `GameEvent.defender` by `TargetingProfile.for_defending_
    player` into `TargetRequirement.event_player`; unbound, it restricts
    nothing, like `EVENT_PLAYER`."""

    PRIOR_TARGET_PLAYER = "prior_target_player"
    """"... target creature that player or that planeswalker's controller
    controls" after "target player or planeswalker" - Searing Blaze, Soul of
    Shandalar. The creature must be controlled by the player chosen for the
    requirement printed just before it, or by the chosen planeswalker's
    controller (CR 601.2c). One target alone cannot say, so `rejects`
    restricts nothing and `TargetingProfile.check` compares the pair."""


class RetargetScope(StrEnum):
    """How many of a stack object's targets a CR 115.7 effect may change.

    - `ALL`: "change the target(s)" (CR 115.7a) - every target changes to
      another legal target, or none of them does.
    - `ONE`: "change a target" (CR 115.7b) - exactly one of them.
    - `ANY`: "change any targets" (CR 115.7c) and "choose new targets"
      (CR 115.7d) - any number of them, each left alone at will.
    """

    ALL = "all"
    ONE = "one"
    ANY = "any"


class ComparisonAttribute(StrEnum):
    """What "with mana value N or less" is comparing (CR 202.3, CR 208.1, CR 208.2).

    `power_or_toughness` is Warping Wail's disjunction, "target creature with
    power or toughness 1 or less" - either characteristic being low enough
    satisfies it.
    """

    MANA_VALUE = "mana_value"
    POWER = "power"
    TOUGHNESS = "toughness"
    POWER_OR_TOUGHNESS = "power_or_toughness"


class ComparisonOperator(StrEnum):
    """ "or less", "or greater", a bare equality, or a strict "less/greater
    than" with no "or equal to" (CR 107.1a's ordinary numbers either way).

    Nahiri, the Unforgiving's own 0 ability - "Exile target creature or
    Equipment card with mana value **less than** Nahiri's loyalty ..." - prints
    a strict inequality, not "or less": a target whose mana value equals
    Nahiri's current loyalty is not legal. `LESS_OR_EQUAL`/`GREATER_OR_EQUAL`
    cannot express that (subtracting one from the bound would be wrong once
    the bound is a `ComparisonCount` rather than a printed number - `<` and
    `<=` are different relations, not the same relation shifted by one), so
    `LESS_THAN`/`GREATER_THAN` are their own operators rather than a special
    case of the "or equal" ones.
    """

    LESS_OR_EQUAL = "le"
    GREATER_OR_EQUAL = "ge"
    EQUAL = "eq"
    LESS_THAN = "lt"
    GREATER_THAN = "gt"


class ComparisonCount(StrEnum):
    """A comparison bound the card *computes* instead of printing a number.

    Drown in the Loch's "with mana value less than or equal to the number of
    cards in its controller's graveyard" states a real restriction on what may
    be targeted, but the number it compares against is not on the card - it is
    read off the game when the question is asked. CR 404.1 makes a graveyard "a
    player's discard pile" and CR 404.2 keeps it "a single face-up pile" every
    player may examine at any time, so the count is public information both at
    announcement (CR 601.2c) and at the CR 608.2b recheck, and it can move
    between the two.

    Only counts that are *knowable while targets are being announced* belong
    here. Prismatic Ending's "the number of colors of mana spent to cast this
    spell" deliberately does not: CR 601.2c announces targets and CR 601.2h
    pays the total cost afterwards, so at the moment the target is chosen there
    is no such number yet - that clause is a condition on what the spell does,
    not on what it may target, and `_COLORS_OF_MANA_SPENT_CONDITION` reads it
    out of the way rather than turning it into a restriction.
    """

    CONTROLLERS_GRAVEYARD_CARDS = "controllers_graveyard_cards"
    """"the number of cards in its controller's graveyard" - counted in the
    graveyard of the *target's* controller, which for a card with no
    controller at all is its owner instead (CR 108.4a, CR 109.4)."""

    SOURCE_LOYALTY = "source_loyalty"
    """"`<Name>`'s loyalty", where `<Name>` is a capitalized possessive read
    generically rather than compared against anything - CR 201.5: "text that
    refers to the object it's on by name means just that particular object,"
    the same self-reference `TargetRequirement.exiled_with_source` already
    reads for "exiled with `<name>`" (see its own docstring). Nahiri, the
    Unforgiving's 0 ability prints exactly this on its own activated ability,
    "... with mana value less than Nahiri's loyalty ..." - CR 306.5c: "The
    loyalty of a planeswalker on the battlefield is equal to the number of
    loyalty counters on it," which moves as the ability's own +1/0 abilities
    (and combat damage) add or remove counters, so it is counted fresh at
    every `rejects` call the same way `CONTROLLERS_GRAVEYARD_CARDS` is,
    never fixed once. Read off *any* capitalized name immediately before
    "'s loyalty" (`_COMPARISON_CLAUSE`'s own `source_loyalty` group), not
    literally against the card's own printed name: the parser has no reach
    into the card's identity at this point (`_CACHE` in `targeting_profile`
    keys purely on oracle text - see its own docstring), and a loyalty
    ability's only planeswalker with a meaningful, trackable "current
    loyalty" to compare against is the one the ability is printed on, so the
    self-reference is unambiguous by construction rather than by checking a
    name. Resolved in `TargetRequirement._counted_bound` off the requirement's
    own `source_id` (`Game.find_by_id`), never off `target` - it is the
    *ability's* loyalty, not the target's own."""

    SOURCE_COLORS_SPENT = "source_colors_spent"
    """Converge (CR 207.2c), the target-legality position: Sundering
    Archaic's own "Converge — When this creature enters, exile target
    nonland permanent an opponent controls with mana value less than or
    equal to the number of colors of mana spent to cast this creature."

    Unlike Prismatic Ending's own converge clause (whose count this class's
    own docstring explains is *not* a `ComparisonCount` at all, because
    CR 601.2c's target announcement happens before CR 601.2h pays the total
    cost), this one genuinely is knowable while a target is being chosen:
    the "target" here belongs to a *triggered* ability (CR 603.3d puts an
    ETB ability's targets on the stack with it, after the creature that
    triggered it has already resolved and finished being cast), so the
    creature's own `CastRecord.mana_spent` is already fixed by the time
    this restriction is ever asked. Resolved in `TargetRequirement.
    _counted_bound` off `source_id` - the entering creature the ability is
    on, via `Game.cast_record_of` (`machines/converge.colors_of_mana_
    spent`) - the identical "read off the source, not the target" shape
    `SOURCE_LOYALTY` just above already uses for Nahiri's own activated
    ability."""


class CombatState(StrEnum):
    """Being in combat, which is a game state rather than a characteristic.

    CR 109.3 lists an object's characteristics and this is not one of them, so
    it cannot be read off the card: CR 508.1k and CR 509.1g put a creature into
    these states when it is declared and CR 506.4 takes it back out again.
    """

    ATTACKING = "attacking"
    BLOCKING = "blocking"


#: "Any target" is creatures, players, planeswalkers, and battles (CR 115.4).
ANY_TARGET_TYPES = frozenset({Type.CREATURE, Type.PLANESWALKER, Type.BATTLE})


#: Restrictions one target cannot be judged against on its own - no
#: restriction at all, or `PRIOR_TARGET_PLAYER`'s pairing, which
#: `TargetingProfile.check` judges across the whole announcement.
_UNRESTRICTED_ALONE = frozenset(
    {ControllerRestriction.ANY, ControllerRestriction.PRIOR_TARGET_PLAYER}
)


class TargetRequirement(EngineModel):
    """One "target ..." the spell asks for, and what satisfies it."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    count: int = 1
    """The most targets this requirement takes. Ignored when `unbounded`."""
    owned_by_caster: bool = False
    """"target creature **you own**" (The Eagles Are Coming!) - CR 108.3's
    owner, a different question from who controls it: a creature the caster
    controls but an opponent owns is not one, and one the caster owns but an
    opponent has taken is."""
    minimum: int = 1
    """The fewest it takes. Zero for "up to N" (CR 115.6) and for "any number
    of" (CR 107.1c); one for "one or two target creatures"."""
    unbounded: bool = False
    """True for "any number of target ...", which has no maximum (CR 107.1c)."""
    variable_count: bool = False
    """True when the count is an X nobody has announced yet (CR 107.3, 107.3a).

    The count is then left wide open - `minimum` nought and `unbounded` - so the
    *kind* of each target is still checked while the number is not. CR 601.2b
    announces X before CR 601.2c announces the targets, so a real cast always
    knows it; this covers reading the card before either has happened.
    """

    card_types: SortedFrozenSet[Type] = frozenset()
    """Acceptable card types. Empty means any card type, as "target spell" does."""
    excluded_card_types: SortedFrozenSet[Type] = frozenset()
    """Card types the target must *not* have: the "non-" of "noncreature spell"."""
    required_supertypes: SortedFrozenSet[Supertype] = frozenset()
    """Supertypes the target must have: "basic" in "target basic land"."""
    excluded_supertypes: SortedFrozenSet[Supertype] = frozenset()
    """Supertypes the target must *not* have: the "non-" of "target nonbasic
    land" (CR 205.4c: "any land that doesn't have this supertype is a
    nonbasic land, even if it has a basic land type")."""
    required_colors: SortedFrozenSet[Color] = frozenset()
    """Which of the five colors would satisfy this (CR 105.1, 105.2b): "target
    black or red permanent" (Celestial Purge) is a disjunction - either color
    is enough, the same way `card_types` already is one for "target artifact
    or enchantment". Empty means color is not restricted at all - not "target
    colorless permanent", which this wave's cards never need and which would
    mean something different (CR 105.2c: no color, not any color)."""
    excluded_colors: SortedFrozenSet[Color] = frozenset()
    """Colors the target must *not* have: the "non-" of "target nonblack
    creature" (Cradle to Grave), read the identical way `excluded_card_types`/
    `excluded_supertypes` already read their own "non-" prefix. CR 105.2's "An
    object can be one or more of the five colors, or it can be no color at
    all" is what makes a colorless target satisfy this for free - it has none
    of the excluded color either, the same way it has none of a *required*
    one and so never satisfies `required_colors` on its own."""
    must_be_token: bool | None = None
    """True for "target token", False for "target nontoken ..." (CR 111.1)."""
    color_count: str | None = None
    """CR 105.2's color-*count* categories - "multicolored" (two or more of
    the five colors, CR 105.2b, Psychotic Fury), "monocolored" (exactly one,
    CR 105.2a), "colorless" (no color at all, CR 105.2c), or "colored" (one
    or more of the five colors, CR 105.2: "An object can be one or more of
    the five colors, or it can be no color at all" - the logical negation of
    "colorless", read off a trailing "that's one or more colors" clause
    rather than a leading adjective - Devourer of Destiny's and Ugin, Eye of
    the Storms' shared "target permanent that's one or more colors") - as
    opposed to `required_colors`' membership check for a *specific* named
    color, which cannot express any of the four (CR 105.4: "'Multicolored'
    is not a color. Neither is 'colorless.'", so `_COLOR_WORDS` correctly
    does not carry them). `None` means the phrase named no such category.

    Devourer of Destiny's "exile target permanent that's one or more colors"
    used to parse with no color restriction at all: `_read_phrase` read
    "permanent" as the noun and had nothing that recognised the trailing
    "that's one or more colors" clause, so it was silently dropped and a
    colorless permanent was accepted as a legal target - an over-broad,
    actively wrong targeting list (a live correctness bug found in a real
    game), worse than refusing the target outright. `_read_phrase` now reads
    that trailing clause via `_extract_color_presence` the same way it
    already reads a trailing comparison or "with `<keyword>`" clause."""
    historic: bool = False
    """True for "target historic ..." (Abstergo Entertainment). CR 700.6:
    "The term historic refers to an object that has the legendary supertype,
    the artifact card type, or the Saga subtype." A disjunction across three
    different characteristics - card type, supertype, *and* subtype at
    once - that `card_types`/`required_supertypes` alone cannot express
    together (each is itself only an OR within one axis), so this gets its
    own field and its own check, `_rejects_historic`, rather than trying to
    fold it into either."""
    combat_states: SortedFrozenSet[CombatState] = frozenset()
    """Which of attacking and blocking would satisfy this (CR 508.1k, 509.1g).

    Empty means the text asked for neither. More than one is a disjunction:
    "target attacking or blocking creature" takes either.
    """
    excluded_combat_states: SortedFrozenSet[CombatState] = frozenset()
    """Which of attacking and blocking this target must NOT be in (CR
    508.1k, 509.1g) - "another target **nonattacking** creature you
    control" (Spider-Man, To the Rescue's own ETB rider). The negation of
    `combat_states` just above, the same "non-" convention `excluded_types`/
    `excluded_supertypes`/`excluded_colors` already read for other
    adjectives."""
    must_be_attacking_alone: bool = False
    """"target creature you control that's attacking alone" (Crowd of True
    Believers). CR 506.5's own live "alone" state - true only while this
    creature is the whole of its own attacking party this combat - read the
    same way `combat_states` reads "attacking"/"blocking" off `Game.combat`,
    not a per-turn historical fact the way `must_have_attacked_this_turn`
    below is."""
    must_have_attacked_this_turn: bool = False
    """"target creature that attacked this turn" (Hexhaven Dueling Arena).
    Unlike `combat_states`' live "is this creature currently attacking",
    CR 508.1k's attacking status ends when combat does (CR 511.3, 514) -
    this is a per-turn historical fact instead, tracked on `Game.
    attacked_this_turn` (populated by `Game.declare_attackers`, cleared each
    new turn the same way `permanents_left_battlefield_this_turn` is)."""
    must_have_entered_this_turn: bool = False
    """"target creature that entered this turn" (Mabel, Valley Hero's
    trigger; Gallia, the Merrymaker's activated ability). The same kind of
    per-turn historical fact `must_have_attacked_this_turn` already is, but
    read off `CardState.turn_entered` (stamped once, the turn a permanent's
    current incarnation reached the battlefield) compared against `Game.
    turn.turn_number` rather than a dedicated per-turn set - every permanent
    already remembers its own arrival turn, so nothing new has to be tracked
    on `Game` the way `attacked_this_turn` is."""
    must_have_crewed_source_this_turn: bool = False
    """"target creature that crewed it this turn" (Turtle Van's own attack
    trigger) - CR 702.122b's "a creature crews a Vehicle when it's tapped to
    pay the cost to activate a Vehicle's crew ability", and "it" is this
    ability's own source Vehicle, not any Vehicle. A per-turn historical fact
    the same shape `must_have_attacked_this_turn`/`must_have_entered_this_
    turn` already are, but scoped to *this* target having crewed *this*
    source specifically - read off `Game.turn_history`'s own "crewed" entries
    (`related_id` is the Vehicle crewed, `object_id` the creature that
    crewed it), which `machines/conditions/history._record_crew`/`_bind_
    crew` already populate for every crew activation in the pool, so nothing
    new has to be tracked on `Game` for this either."""
    required_subtypes: SortedFrozenSet[str] = frozenset()
    """A bare CR 205.3m creature-type list used as the target noun itself -
    "target Vampire, Werewolf, or Zombie" (Slayer of the Wicked) - rather than
    "target creature" narrowed by a "with"/"you control" clause. Oracle
    templating elides the word "creature" here; `card_types` still carries
    `{Type.CREATURE}` for the ordinary type check, and this is the
    disjunction across which of the named types would satisfy it (any one is
    enough, the same "or" reading `card_types` already gives "target artifact
    or enchantment"). Lower-cased for a case-insensitive match against
    `CardState.subtypes`."""

    excluded_subtypes: SortedFrozenSet[str] = frozenset()
    """CR 205.3m creature types the target must *not* have: the "non-" of
    "target non-Human creature" (Fight as One's own second mode; CR 702.140a's
    mutate reminder text prints the identical phrase). Read the same "non-" of
    `excluded_card_types`/`excluded_supertypes`/`excluded_colors` already
    read for their own vocabularies, but the negated word keeps its hyphen
    ("non-Human", not "nonHuman") the way a *positive* hyphenated creature
    type does (Assembly-Worker) - Oracle's own templating difference between
    a card type/supertype/color prefix (fused: "noncreature", "nonbasic",
    "nonblack") and a creature-type prefix (hyphenated). Lower-cased the same
    way `required_subtypes` is."""

    allows_cards: bool = True
    allows_players: bool = False
    allows_abilities: bool = False
    """True for "target activated or triggered ability" (CR 115.2, CR 113.1c)."""
    ability_source_types: SortedFrozenSet[Type] = frozenset()
    """"target activated or triggered ability you control from a creature
    source" (Echo, Perceptive Prodigy; Scientist Supreme of A.I.M.'s
    "artifact source"; Weaver of Harmony's "enchantment source") - the card
    types the ability's source (CR 113.7) must have: its computed types while
    it is on the battlefield, its last known ones once it has left (CR
    113.7a). Empty means any source."""
    ability_kinds: SortedFrozenSet[AbilityKind] = frozenset()
    """Which of CR 113.3's categories an ability target must belong to, read
    off the phrase: `{TRIGGERED}` for Consign to Memory's "target triggered
    ability" (CR 113.3c), `{ACTIVATED}` for Rimewind Cryomancer's "target
    activated ability" (CR 113.3b), both for "activated or triggered". Empty
    means the phrase named no category, and any ability is accepted."""
    opponent_only: bool = False
    zones: SortedFrozenSet[Zone] = frozenset({Zone.BATTLEFIELD})
    controller: ControllerRestriction = ControllerRestriction.ANY
    event_player: str | None = None
    """`ControllerRestriction.EVENT_PLAYER` only: the player "that player"
    names, bound from the trigger's own event by
    `TargetingProfile.for_event_player`. `None` until then."""
    must_be_tapped: bool | None = None
    excludes_source: bool = False
    """True for "target *other* ..." / "*another* target ...": the permanent
    the ability or spell is on cannot be its own target. `knowledge_search`
    found no single numbered CR rule defining "another"/"other" this session;
    this is read off the plain-English word, the same way `must_be_tapped` is
    read off "tapped" rather than off a rule number."""
    or_any_spell: bool = False
    """True for a noun list, two items or more, where one of them is a bare
    "spell" reached across an "or" - Aang, Swift Savior's "airbend up to one
    other **target creature or spell**" (spell last) and Fatehold Charm's
    "Return **target spell or creature** to its owner's hand" (spell first)
    both read the identical way; only a bare, single-item "target spell"
    keeps `zones` narrowed to the stack instead.

    "Target creature spell" and "target creature or spell" are two different
    restrictions and the word "or" is the only thing telling them apart. The
    first is one noun ("spell") with one adjective ("creature"); the second is
    CR 115.1's target being satisfied by *either* item, and the items are of
    different kinds - one is a permanent on the battlefield, the other is
    CR 112.1's "A spell is a card on the stack", of no particular card type.

    `card_types` and `zones` cannot express that on their own: they are read as
    one conjunction, so unioning `Zone.STACK` in would let a permanent-typed
    restriction reach any spell on the stack only by also dropping the type
    check for battlefield permanents. This flag keeps the two apart instead -
    `_rejects_card` accepts anything on the stack outright when it is set, and
    everything else still goes through the ordinary permanent checks."""
    exiled_with_source: bool = False
    """True for "target ... card exiled with `<name>`" (The Darkness Crystal,
    Mosswort Bridge's own hideaway-play permission does not use this - it
    names no target at all). CR 201.5: an object's own printed name inside
    its own text always means itself, so this is set whenever a "card
    exiled with `<name>`" clause is read at all - the captured name is never
    compared against anything, since the only object it could possibly name
    is the one the ability is printed on (`source_id`). Enforced in
    `_rejects_card` against `CardState.exile_annotation` - the same
    `ExileMarker.IMPRINTED`/`linked_permanent_id` link `machines/effects.py`'s
    own imprint clauses (Ugin's Labyrinth) already write when a permanent
    exiles a card "with" itself."""

    comparison_attribute: ComparisonAttribute | None = None
    """"mana value"/"power"/"toughness" in "target creature with mana value 2
    or less" (Abrupt Decay), None when the phrase makes no such comparison."""
    comparison_operator: ComparisonOperator | None = None
    """How `comparison_value` bounds it - "or less", "or greater", or a bare
    equality ("target ... card with mana value X" - Tamiyo, Compleated Sage)."""
    comparison_value: int | None = None
    """The number to compare against, or `None` when it cannot be pinned down
    right now: an unbound X (CR 107.3 - not yet announced when this profile was
    built) or a count this parser cannot read at all (Prismatic Ending's "the
    number of colors of mana spent to cast this spell"). `rejects` refuses
    every target while this is `None` rather than skip the comparison, because
    an unevaluable restriction that quietly let everything through would be a
    wrong game state that looks right - worse than refusing a legal target."""
    comparison_count: ComparisonCount | None = None
    """Where to *compute* `comparison_value` from when the card names a count
    rather than printing a number - Drown in the Loch's "mana value less than
    or equal to the number of cards in its controller's graveyard".

    Evaluated fresh every time `rejects` is asked, at announcement (CR 601.2c)
    and again at the CR 608.2b recheck, exactly like `comparison_value_if_revolt`
    and for the same reason: the count can change in between (a fetchland
    cracked in response makes a spell Drown could not touch a legal target, and
    an exiled graveyard takes one away). `None` for every phrase that printed
    its own number.

    When this is set, `comparison_value` stays `None` on the requirement
    itself; `_rejects_comparison` resolves it and, if it cannot (no game, or a
    controller with no player object), fails closed the same way an unbound X
    does."""
    comparison_x_definition: str | None = None
    """The expression a trailing "where X is <expression>" gives an X bound -
    Spellstutter Sprite's "with mana value X or less, where X is the number of
    Faeries you control". CR 107.3c: X is then defined by the text, nobody
    chooses it, and "the value of X may change while that spell or ability is
    on the stack", so it is counted for the caster at every `rejects` call,
    at announcement and at the CR 608.2b recheck, never fixed here. An
    expression `machines/effects.count_expression` cannot read leaves the
    bound unresolved, which refuses every target (fail closed)."""
    comparison_value_if_revolt: int | None = None
    """Fatal Push's own "Revolt — ... mana value 4 or less instead if a
    permanent left the battlefield under your control this turn": the wider
    number to use in place of `comparison_value` when the caster's Revolt
    condition holds *right now* (an ability word, CR 207.2c - no further
    numbered rule for Revolt itself). Read directly off the card's printed
    Revolt paragraph by `_parse` alongside the base comparison, and evaluated
    fresh every time `rejects` is asked - at announcement (CR 601.2c) and
    again at resolution (CR 608.2b) - rather than fixed once, since whether a
    permanent left the battlefield this turn can change between the two."""

    required_target_count: int | None = None
    """"with a single target" in Bolt Bend's "target spell or ability with a
    single target" - CR 115.9a: "An object that looks for a '[spell or
    ability] with [a number of] targets' checks the number of times any
    object or player was chosen as the target of that spell or ability when
    it was put on the stack."

    A restriction on the *one* target this requirement asks for, not a second
    target of its own - which is exactly what the parser used to read it as,
    leaving Bolt Bend asking for two targets and castable at nothing at all.
    Enforced in `_rejects_card`/`_rejects_ability` by counting the targeted
    stack object's own `targets`; a target that carries no target list to
    count fails open, the same as every other restriction this parser cannot
    evaluate."""

    must_target_you: bool = False
    """"target spell ... that targets you[ or ...]" (Siren Stormtamer) - one
    disjunct of a "that targets `<description>`" clause on a "target spell"
    requirement: satisfied when one of the *candidate spell's own* targets is
    this requirement's own caster (CR 109.5's "you", read at `rejects`-time
    against whoever is asking). `must_target_types`/`must_target_you_control`
    are its sibling disjuncts; any one of the three that is set and satisfied
    is enough (CR 115.1's compound-noun "or" reading, applied here to a
    compound *description* rather than to a compound noun)."""
    must_target_types: SortedFrozenSet[Type] = frozenset()
    """Card types a "target spell that targets an `<type>`[ or `<type>`]
    [you control]" clause's own type list names - Fugitive Droid's "an
    artifact or creature you control." Checked against the candidate spell's
    own targets' computed types (CR 613.5), never against the spell itself.
    Empty means this gate is not printed at all."""
    must_target_you_control: bool = False
    """Whether `must_target_types`' own targets must be permanents this
    requirement's caster controls, as every real printing of this clause
    prints ("... you control") - CR 109.5's "you" read against the
    requirement's own caster, not the candidate spell's controller."""

    distinct_controllers: bool = False
    """"Choose two target creatures controlled by different players" (Run Away
    Together) - a restriction *across* this requirement's targets rather than
    on any one of them, so it cannot be answered by `rejects`, which only ever
    sees one target at a time. `TargetingProfile._why_not` enforces it while it
    fills this requirement's slots, next to CR 115.3's own across-targets rule
    ("the same target can't be chosen multiple times for any one instance of
    the word 'target'"), which lives there for the same reason.

    `knowledge_search` found no numbered CR rule for the phrase "controlled by
    different players" itself this session; it is read off the plain English,
    the way `excludes_source` reads "another". What it hangs on is CR 601.2c:
    the announcement has to be "an appropriate object or player for each
    target the spell requires", and two creatures one player controls are not
    an appropriate answer to a spell that asks for two players' creatures.

    Fails open for a target whose controller cannot be read (a bare `UUID` or
    a `TargetRef`), like every other restriction here that needs more than the
    caller supplied."""

    excludes_enchanted: bool = False
    """"target creature other than enchanted creature" (Secret Invasion) - the
    permanent the requirement's own source (an Aura) is attached to (CR
    303.4b) cannot be chosen. Read off the plain words; not the source itself
    (`excludes_source`), which is the Aura."""

    total_mana_value_at_most: int | None = None
    """"up to two target creatures with total mana value 6 or less" (The Super
    Hero Civil War's chapter I) - like `distinct_controllers`, a restriction
    *across* this requirement's targets: the sum of their mana values (CR
    202.3) may not exceed the bound. CR 601.2c: the announcement has to be
    "an appropriate object ... for each target the spell requires". Read
    ahead of the per-target comparison scan, which would otherwise take it
    for a bound on each target alone. Fails open for a target whose mana
    value cannot be read."""

    share_a_card_type: bool = False
    """"two target nonland permanents that share a card type" (Burglar's Plot,
    Shifting Loyalties) - like `distinct_controllers`, a restriction *across*
    this requirement's targets: every target chosen for it must have at least
    one card type (CR 205.2a) in common with the others. CR 601.2c: the
    announcement has to be "an appropriate object ... for each target the
    spell requires". Card types are the computed ones (CR 613.1d) for a
    permanent. Fails open for a target whose types cannot be read."""

    one_per_opponent: bool = False
    """"For each opponent, goad target creature that player controls."
    (Frenzied Gorespawn) - the mandatory twin of `_for_each_opponent_profile`'s
    "up to one". The text prints one "target" per opponent (CR 601.2c: "In
    some cases, the number of targets will be defined by the spell's text"),
    so each opponent who controls a legal choice must have one chosen; an
    opponent with none gets none, and CR 603.3d removes the ability only when
    no opponent has one. Enforced in `TargetingProfile.check` when a `game`
    is given, since which opponents have a legal choice is game state."""

    distinct_from_prior_requirement: bool = False
    """CR 115.3/115.4's paired "any target"/"any other target" idiom (Boulder
    Dash, Arc Trail: "deals 2 damage to any target and 1 damage to any other
    target") - a restriction *between* this requirement and the one printed
    immediately before it in the same `TargetingProfile.requirements`, so it
    cannot be answered by `rejects`, which only ever sees one requirement's
    own target at a time. `TargetingProfile._check_distinct_from_prior`
    enforces it once every target has been placed into a requirement's slot
    (`_fill_slots`), next to `_check_one_per_opponent`/
    `_check_prior_target_player`, the announcement's other across-requirement
    checks.

    Set only when this exact bare "any other target" shape follows a bare
    "any target" earlier in the same text (`_parse`'s own `_ANY_TARGET`/
    `_ANY_OTHER_TARGET` reading) - never for a solitary "any other target"
    with nothing before it to be distinct from. Iron Fist, Living Weapon; Red
    Hulk; and Screaming Nemesis each print exactly one "any other target" and
    nothing else in the same ability, and there the word "other" means
    something else entirely: "other than this ability's own source"
    (`excludes_source`, whose own docstring reads that word the plain-English
    way). The two meanings share a word but never a card - a card would need
    to both name an earlier plain "any target" and mean "excludes its own
    source" by the later "other" for them to conflict, and CR 115.4's own
    "any target"/"any other target" pairing is always about the two targets
    differing from *each other*, not about either one dodging the source."""

    required_keyword: str | None = None
    """"with flying" in "target creature you don't control with flying"
    (Kraul Harpooner) - a trailing keyword-ability clause, read off the same
    closed CR 702 evasion/combat vocabulary `machines/combat.py::Keyword`
    already speaks. Only a small, explicitly named set is read
    (`_WITH_KEYWORD_RE`) rather than any "with <word>" at all: an unrecognised
    "with" clause is left exactly as before this field existed - silently
    unenforced - so a card this narrow reader does not know about does not
    regress from "ignored" to "the whole targeting text refuses to parse"."""

    required_counter_kind: str | None = None
    """"with a +1/+1 counter on it" in "target creature with a +1/+1 counter
    on it" (Tomik, Orzhov Lawmage) - CR 122.1's counter kind (any single
    word or the two printed +N/-N shapes), read the same narrow way
    `required_keyword` reads a trailing "with <keyword>" clause
    (`_WITH_COUNTER_RE`): this used to be exactly the unenforced "with"
    clause `required_keyword`'s own docstring names as the reason its own
    vocabulary stays narrow, so a target with no counter on it at all was
    silently accepted as legal."""

    if_gift_promised: "TargetRequirement | None" = None
    """CR 702.174m: "If part of a spell's ability has its effect only if its
    gift was promised, and that part of the ability includes any targets, the
    spell's controller chooses those targets only if the gift was promised."

    Into the Flood Maw's own "Return target creature an opponent controls to
    its owner's hand. If the gift was promised, instead return target
    nonland permanent an opponent controls to its owner's hand." is not a
    second target of the spell's own - CR 601.2c: "a spell may require
    alternative targets only if an alternative or additional cost ... was
    chosen for it" - it is what this same slot asks for *instead*, once
    gift's cost was paid. `_parse` reads the "if the gift was promised,
    instead ..." clause into this field on the requirement it replaces,
    rather than either counting it as a second requirement (which is what
    used to make the spell demand two targets and be uncastable at anything,
    CR 601.2c) or discarding the clause outright, which would permanently
    hardcode the not-promised answer the day gift itself is implemented.
    `TargetingProfile.for_gift_promise` is what actually chooses between the
    two. Nothing calls it with `True` today: `machines/casting.py`'s
    `ADDITIONAL_COST_KEYWORDS` has no "gift" entry, so a spell's gift can
    never actually be promised yet (see `docs/engine-coverage.md`'s "Not
    modelled" table) - this field exists so the data is not lost the day it
    is."""

    alternatives: "tuple[TargetRequirement, ...]" = ()
    """Full independent requirements this one is OR'd with - Nissa's Defeat's
    own "target Forest, green enchantment, or green planeswalker": a
    compound noun list whose items do not all carry the same adjectives (a
    bare land subtype next to two color-qualified card types). `card_types`/
    `required_subtypes`/`required_colors` alone cannot express that: each is
    itself only a disjunction *within* one axis (CR 205.2a's card types, CR
    205.3's subtypes, CR 105.1's colors), so unioning "green" from the
    second and third items into one shared `required_colors` would wrongly
    demand it of the colorless Forest the first item names too - the same
    kind of cross-axis disjunction `historic`'s own docstring already
    describes for a different three-characteristic case, and the reason it
    gets its own field rather than trying to fold into the existing ones.

    A target satisfies the whole requirement when it satisfies the base
    fields on this object *or* any one alternative's own complete `rejects`
    check (`rejects` tries each in turn); every other field - `zones`,
    `controller`, `comparison_*`, and the rest of the shared context that
    is not itself part of the divergent noun list - is read only off this
    outer object, since English prints a trailing restriction like "you
    control" once, after the whole list, not once per item. Recursive the
    same way `if_gift_promised` already is; an alternative's own
    `alternatives` is always empty, so there is no deeper nesting and no
    risk of unbounded recursion."""

    @property
    def optional(self) -> bool:
        """True when none of these targets has to be chosen (CR 115.6)."""
        return self.minimum == 0

    @property
    def maximum(self) -> int | None:
        """The most targets this takes, or None when there is no maximum."""
        return None if self.unbounded else self.count

    def rejects(
        self, target: Any, caster: str, game: Any = None, source_id: UUID | None = None
    ) -> str | None:
        """Why this target is illegal for this requirement, or None if it is fine.

        A target the caller passed as a bare reference cannot be inspected, so
        only its kind is checked.

        `game` is optional because some restrictions are not on the permanent at
        all: whether a creature is attacking or blocking is game state rather
        than a characteristic (CR 109.3), and lives on `Game.combat`. Without a
        game those restrictions are not checked, the same way an unreadable
        phrase is not checked.

        `source_id` is the id of the permanent this requirement's own ability or
        spell is on - needed for `excludes_source` ("target *other* creature").
        Without it, that restriction is not checked, the same way any other
        restriction fails open when the caller cannot supply what it needs.

        `alternatives` (CR 115.1's single target satisfying any one of a
        mixed compound noun list's own independent shapes) is tried after
        the base fields fail: this object's own reading is the first, most
        specific candidate, and the alternatives are only extra chances,
        never a narrowing of it.
        """
        reason = self._rejects_without_alternatives(target, caster, game, source_id)
        if reason is None or not self.alternatives:
            return reason
        for alternative in self.alternatives:
            if alternative.rejects(target, caster, game, source_id) is None:
                return None
        return reason

    def _rejects_without_alternatives(
        self, target: Any, caster: str, game: Any = None, source_id: UUID | None = None
    ) -> str | None:
        if getattr(target, "is_ability", False):
            return self._rejects_ability(target, caster, game)
        if isinstance(target, CardState):
            return self._rejects_card(target, caster, game, source_id)
        if isinstance(target, TargetRef):
            if target.is_player:
                return self._rejects_player(str(target.username), caster)
            return None if self._allows_objects else f"{self.phrase} cannot target a card"
        if isinstance(target, UUID):
            return None if self._allows_objects else f"{self.phrase} cannot target a card"
        username = target if isinstance(target, str) else getattr(target, "username", None)
        if username is not None:
            return self._rejects_player(str(username), caster)
        return f"{target!r} is not something a spell can target"

    @property
    def _allows_objects(self) -> bool:
        """Whether anything that is not a player could satisfy this.

        A bare `TargetRef` or `UUID` names an object without saying which kind,
        so this is as far as it can be checked - fail open, as everywhere else.
        """
        return self.allows_cards or self.allows_abilities

    def _rejects_ability(self, target: Any, caster: str, game: Any = None) -> str | None:
        """CR 113.1c: an ability on the stack is an object, and can be targeted.

        CR 115.2 only lets a spell reach it when the spell says so, so a
        requirement that did not read "target ... ability" refuses it. Mana
        abilities never get here: they do not use the stack and "can't be
        targeted, countered, or otherwise responded to" (CR 605.3b, CR 605.4a).
        """
        if not self.allows_abilities:
            return f"{self.phrase} cannot target {target.name}, which is an ability on the stack"
        kind = getattr(target, "kind", None)
        if self.ability_kinds and kind not in self.ability_kinds:
            category = "an activated" if kind is AbilityKind.ACTIVATED else "a triggered"
            return f"{self.phrase} cannot target {target.name}, which is {category} ability"
        target_count = self._rejects_target_count(target)
        if target_count is not None:
            return target_count
        must_target = self._rejects_must_target(target, game, caster)
        if must_target is not None:
            return must_target
        if self.ability_source_types:
            source_types = _ability_source_types(target, game)
            if source_types is not None and not (source_types & self.ability_source_types):
                wanted = " or ".join(sorted(t.value for t in self.ability_source_types))
                return (
                    f"{self.phrase} needs an ability from {with_indefinite_article(wanted)} "
                    f"source, and {target.name}'s source is not one (CR 113.7)"
                )
        controller = getattr(target, "controller", None)
        if self.controller is ControllerRestriction.ANY or controller is None:
            return None
        if self.controller in (
            ControllerRestriction.EVENT_PLAYER,
            ControllerRestriction.DEFENDING_PLAYER,
        ):
            return self._rejects_event_player_control(target, controller)
        if self.controller is ControllerRestriction.YOU and controller != caster:
            return f"{self.phrase} needs an ability {caster} controls, and {target.name} is not"
        not_yours = {ControllerRestriction.OPPONENT, ControllerRestriction.NOT_YOU}
        if self.controller in not_yours and controller == caster:
            return f"{self.phrase} cannot target {target.name}, which {caster} controls"
        return None

    def _rejects_card(
        self, target: CardState, caster: str, game: Any = None, source_id: UUID | None = None
    ) -> str | None:
        if not self.allows_cards:
            if self.allows_abilities:
                return f"{self.phrase} can only target an ability, not {target.name}"
            return f"{self.phrase} can only target a player, not {target.name}"
        if self.excludes_source and source_id is not None and target.id == source_id:
            return f"{self.phrase} cannot target {target.name}, which this is on"
        if self.excludes_enchanted and game is not None and source_id is not None:
            source = game.find_by_id(source_id)
            if source is not None and getattr(source, "attached_to", None) == target.id:
                return f"{self.phrase} cannot target {target.name}, the enchanted creature"
        if self.owned_by_caster and target.owner is not None and target.owner != caster:
            return f"{self.phrase} needs one {caster} owns, and {target.name} is {target.owner}'s"
        # "... or spell" (CR 112.1: "A spell is a card on the stack"), the
        # second half of a two-kind noun list - see `or_any_spell`. The phrase
        # names no card type or zone for this half, so those two checks are
        # skipped for it - but a *shared* trailing clause ("target spell or
        # permanent **with mana value 1 or greater**", Divide by Zero;
        # "target spell or permanent **that's red or green**", Aether Gust)
        # binds both halves of the disjunction at once and is not part of
        # either noun's own type restriction, so a comparison or color check
        # still runs for a spell on the stack exactly as it does for a
        # permanent.
        #
        # A supertype/subtype restriction is different: Icy Reception's own
        # "target creature or **legendary** spell" reads "legendary" as the
        # *second* item's own leading adjective (`_read_adjectives`'
        # per-item loop), not a trailing clause about the whole compound -
        # but `required_supertypes`/`required_subtypes` hold one shared
        # value for the whole requirement with no record of which disjunct
        # it was read for, so by the time this runs there is no way to tell
        # "legendary spell" apart from a genuinely shared "target legendary
        # creature or spell" (a shape the pool does not print, but nothing
        # here could rule out either way). The safe direction is the one
        # that matches every printing actually seen: exempt the spell half,
        # exactly as it always was, rather than assume a per-item adjective
        # was meant to bind both.
        spell_on_stack = self.or_any_spell and target.zone is Zone.STACK
        if not spell_on_stack and target.zone not in self.zones:
            wanted = " or ".join(sorted(zone.value for zone in self.zones))
            return (
                f"{self.phrase} needs a target in the {wanted}, "
                f"but {target.name} is in the {target.zone.value}"
            )
        if self.exiled_with_source:
            annotation = target.exile_annotation
            # Any CR 607.2a/607.1 link to this permanent - imprint's,
            # hideaway's or a plain "exiled with" one.
            linked = (
                annotation is not None
                and source_id is not None
                and annotation.links_to(source_id, None)
            )
            if not linked:
                return (
                    f"{self.phrase} needs a card exiled with this permanent, "
                    f"and {target.name} is not one"
                )
        if not spell_on_stack and (self.card_types or self.excluded_card_types):
            current_types = set(self._current_types(target, game))
            if self.card_types and not (current_types & self.card_types):
                wanted = " or ".join(sorted(kind.value for kind in self.card_types))
                return (
                    f"{self.phrase} needs {with_indefinite_article(wanted)}, "
                    f"and {target.name} is not one"
                )
            if self.excluded_card_types and (current_types & self.excluded_card_types):
                unwanted = " or ".join(sorted(kind.value for kind in self.excluded_card_types))
                return (
                    f"{self.phrase} cannot target {with_indefinite_article(unwanted)}, "
                    f"and {target.name} is one"
                )
        if (
            not spell_on_stack
            and self.required_supertypes
            and not (set(self._current_supertypes(target, game)) & self.required_supertypes)
        ):
            wanted = " or ".join(sorted(kind.value for kind in self.required_supertypes))
            return (
                f"{self.phrase} needs {with_indefinite_article(wanted)} permanent, "
                f"and {target.name} is not one"
            )
        if (
            not spell_on_stack
            and self.excluded_supertypes
            and (set(self._current_supertypes(target, game)) & self.excluded_supertypes)
        ):
            unwanted = " or ".join(sorted(kind.value for kind in self.excluded_supertypes))
            return (
                f"{self.phrase} cannot target {with_indefinite_article(unwanted)} permanent, "
                f"and {target.name} is one"
            )
        if (
            not spell_on_stack
            and self.required_subtypes
            and not any(
                word.lower() in self.required_subtypes
                for word in self._current_subtypes(target, game)
            )
        ):
            wanted = " or ".join(sorted(self.required_subtypes))
            return (
                f"{self.phrase} needs {with_indefinite_article(wanted)}, "
                f"and {target.name} is not one"
            )
        if (
            not spell_on_stack
            and self.excluded_subtypes
            and any(
                word.lower() in self.excluded_subtypes
                for word in self._current_subtypes(target, game)
            )
        ):
            unwanted = " or ".join(sorted(self.excluded_subtypes))
            return (
                f"{self.phrase} cannot target {with_indefinite_article(unwanted)}, "
                f"and {target.name} is one"
            )
        if self.required_colors and not (
            set(self._current_colors(target, game)) & self.required_colors
        ):
            wanted = " or ".join(sorted(color.name.lower() for color in self.required_colors))
            return (
                f"{self.phrase} needs {with_indefinite_article(wanted)} permanent, "
                f"and {target.name} is not one"
            )
        if self.excluded_colors and (
            set(self._current_colors(target, game)) & self.excluded_colors
        ):
            unwanted = " or ".join(sorted(color.name.lower() for color in self.excluded_colors))
            return (
                f"{self.phrase} cannot target {with_indefinite_article(unwanted)} permanent, "
                f"and {target.name} is one"
            )
        if self.color_count is not None:
            count = len(set(self._current_colors(target, game)))
            satisfied = (
                (self.color_count == "multicolored" and count >= 2)
                or (self.color_count == "monocolored" and count == 1)
                or (self.color_count == "colorless" and count == 0)
                or (self.color_count == "colored" and count >= 1)
            )
            if not satisfied:
                return (
                    f"{self.phrase} needs {with_indefinite_article(self.color_count)} permanent, "
                    f"and {target.name} is not one"
                )
        historic = self._rejects_historic(target, game)
        if historic is not None:
            return historic
        if self.must_be_tapped is not None and target.tapped is not self.must_be_tapped:
            state = "tapped" if self.must_be_tapped else "untapped"
            return (
                f"{self.phrase} needs {with_indefinite_article(state)} permanent, "
                f"and {target.name} is not"
            )
        token = self._rejects_token(target)
        if token is not None:
            return token
        combat = self._rejects_combat_state(target, game)
        if combat is not None:
            return combat
        alone = self._rejects_attacking_alone(target, game)
        if alone is not None:
            return alone
        attacked = self._rejects_attacked_this_turn(target, game)
        if attacked is not None:
            return attacked
        entered = self._rejects_entered_this_turn(target, game)
        if entered is not None:
            return entered
        crewed = self._rejects_crewed_this_turn(target, game, source_id)
        if crewed is not None:
            return crewed
        comparison = self._rejects_comparison(target, game, caster, source_id)
        if comparison is not None:
            return comparison
        keyword = self._rejects_required_keyword(target, game)
        if keyword is not None:
            return keyword
        counter_kind = self._rejects_required_counter_kind(target)
        if counter_kind is not None:
            return counter_kind
        target_count = self._rejects_target_count(target)
        if target_count is not None:
            return target_count
        must_target = self._rejects_must_target(target, game, caster)
        if must_target is not None:
            return must_target
        return self._rejects_controller(target, caster)

    def _rejects_must_target(self, target: Any, game: Any, caster: str) -> str | None:
        """ "target spell that targets `<description>`" (Fugitive Droid's "an
        artifact or creature you control"; Siren Stormtamer's "you or a
        creature you control") - whether the *candidate spell's own* targets
        (CR 601.2c) satisfy at least one of `must_target_you`/`must_target_
        types` (with `must_target_you_control`). `game` is needed to read a
        targeted permanent's own computed types (CR 613.5); without one this
        fails open, the same as every other restriction this parser cannot
        evaluate without it.
        """
        if not (self.must_target_you or self.must_target_types):
            return None
        found_targets = getattr(target, "targets", None)
        if not found_targets:
            return (
                f"{self.phrase} needs a target that itself targets "
                f"{'you' if self.must_target_you else 'a matching object'}, and "
                f"{getattr(target, 'name', target)} has no targets"
            )
        for ref in found_targets:
            if self.must_target_you and getattr(ref, "is_player", False):
                if ref.username == caster:
                    return None
                continue
            if not self.must_target_types or getattr(ref, "is_player", False):
                continue
            card_id = getattr(ref, "card_id", None)
            if card_id is None or game is None:
                continue
            candidate = game.find_by_id(card_id)
            if not isinstance(candidate, CardState) or candidate.zone is not Zone.BATTLEFIELD:
                continue
            if self.must_target_you_control and game.controller_of(candidate).username != caster:
                continue
            characteristics = game.characteristics_of(candidate)
            if set(characteristics.types) & self.must_target_types:
                return None
        wanted_types = (
            with_indefinite_article(
                " or ".join(sorted(kind.value for kind in self.must_target_types))
            )
            if self.must_target_types
            else ""
        )
        return (
            f"{self.phrase} needs a target that itself targets "
            f"{'you or ' if self.must_target_you else ''}{wanted_types}"
            f", and {getattr(target, 'name', target)} does not"
        )

    def _rejects_target_count(self, target: Any) -> str | None:
        """CR 115.9a: how many targets the *targeted* object itself has.

        "The number of times any object or player was chosen as the target of
        that spell or ability when it was put on the stack" - so a spell that
        chose the same creature twice has two targets, which is why this
        counts the entries of the target list rather than the distinct objects
        in it (CR 115.9c's "targets only" is the distinct-object reading, and
        no card in the pool uses it here).

        Fails open for anything with no target list to count, the same way a
        combat-state or comparison restriction is skipped when the caller
        cannot supply what it needs.
        """
        if self.required_target_count is None:
            return None
        targets = getattr(target, "targets", None)
        if targets is None:
            return None
        if len(targets) == self.required_target_count:
            return None
        name = getattr(target, "name", target)
        return (
            f"{self.phrase} needs a single target, "
            f"and {name} was put on the stack with {len(targets)}"
        )

    def _rejects_historic(self, target: CardState, game: Any = None) -> str | None:
        """CR 700.6: legendary, artifact, or Saga.

        Was checked off `target.card` - doubly printed, since that bypasses
        both the layer system (CR 613.5) and `CardState`'s own up-face read
        (CR 712.8d), so a transformed or face-down permanent answered off its
        front face rather than what it actually is right now. Mishra's
        Factory's own "This land becomes a 2/2 Assembly-Worker artifact
        creature" is the real case: nothing in this engine's pool grants
        Legendary or Saga through a continuous effect yet, but Type.ARTIFACT
        through layer 4 is exactly what that ability does, and "historic"
        has to see it the moment it does.

        A card in a graveyard or library reaches no layer (CR 611.2c: layers
        only apply on the battlefield), so `_current_types`/`_current_
        supertypes`/`_current_subtypes` already fall back to `target.types`/
        `.supertypes`/`.subtypes` there - the same up-face-respecting read
        `target.card` never gave, just without a layer stack to run on top of.
        """
        if not self.historic:
            return None
        is_historic = (
            Supertype.LEGENDARY in self._current_supertypes(target, game)
            or Type.ARTIFACT in self._current_types(target, game)
            or "saga" in {subtype.lower() for subtype in self._current_subtypes(target, game)}
        )
        if is_historic:
            return None
        return f"{self.phrase} needs a historic card, and {target.name} is not one"

    def _rejects_required_keyword(self, target: CardState, game: Any = None) -> str | None:
        """CR 702: "with flying" and its like siblings (Kraul Harpooner).

        Without a game there is no computed board to read a granted keyword
        off, so this fails open the same way `_rejects_combat_state` does
        without one - a false rejection would be worse than an unchecked one.
        """
        if self.required_keyword is None or game is None:
            return None
        if not has_keyword(target, self.required_keyword, game):
            return (
                f"{self.phrase} needs an object with {self.required_keyword}, "
                f"and {target.name} is not"
            )
        return None

    def _rejects_required_counter_kind(self, target: Any) -> str | None:
        """CR 122.1: "with a `<kind>` counter on it" (Tomik, Orzhov Lawmage).

        Fails open for anything with no `counters` to read - a bare `UUID`
        or `TargetRef`, the same shape every other restriction here already
        falls back to when the caller supplied less than a real `CardState`.
        """
        if self.required_counter_kind is None:
            return None
        counters = getattr(target, "counters", None)
        if counters is None:
            return None
        if self.required_counter_kind in counters:
            return None
        return (
            f"{self.phrase} needs a permanent with a {self.required_counter_kind} counter "
            f"on it, and {target.name} has none"
        )

    def _rejects_token(self, target: CardState) -> str | None:
        """CR 111.1: a token is a permanent that no card represents.

        `CardState` is built around a `Card`, so it has nothing that says a
        permanent is a token - CR 108.2b and CR 111.6 both draw the line the
        model does not. The restriction is therefore read off the text and then
        fails open, and starts working the day `CardState` grows a `token` flag.
        """
        if self.must_be_token is None:
            return None
        is_token = getattr(target, "token", None)
        if is_token is None or is_token is self.must_be_token:
            return None
        wanted = "a token" if self.must_be_token else "a nontoken permanent"
        return f"{self.phrase} needs {wanted}, and {target.name} is not"

    def _rejects_combat_state(self, target: CardState, game: Any) -> str | None:
        """CR 508.1k, CR 509.1g: is this creature attacking, or blocking?

        Neither is a characteristic (CR 109.3), so the answer is on the game's
        combat rather than on the permanent. No game means no answer, and an
        unanswerable restriction is not enforced.
        """
        combat = getattr(game, "combat", None)
        if self.excluded_combat_states and combat is not None:
            is_attacking = combat.attack_by(target.id) is not None
            is_blocking = combat.attack_blocked_by(target.id) is not None
            if CombatState.ATTACKING in self.excluded_combat_states and is_attacking:
                return (
                    f"{self.phrase} needs a nonattacking creature, and {target.name} is attacking"
                )
            if CombatState.BLOCKING in self.excluded_combat_states and is_blocking:
                return f"{self.phrase} needs a nonblocking creature, and {target.name} is blocking"
        if not self.combat_states:
            return None
        if combat is None:
            return None
        if CombatState.ATTACKING in self.combat_states and combat.attack_by(target.id) is not None:
            return None
        blocking = CombatState.BLOCKING in self.combat_states
        if blocking and combat.attack_blocked_by(target.id) is not None:
            return None
        wanted = " or ".join(sorted(state.value for state in self.combat_states))
        return f"{self.phrase} needs a creature that is {wanted}, and {target.name} is not"

    def _rejects_attacking_alone(self, target: CardState, game: Any) -> str | None:
        """CR 506.5: is this creature attacking, and is it the *only* one
        attacking this combat - the same "alone" `machines/triggers.py`
        reads off `GameEvent.attacking_alone` for a trigger's own condition,
        asked here of a target's *current* state instead of a past event.
        No game, no combat to ask: fails open the same way `_rejects_
        combat_state` does."""
        if not self.must_be_attacking_alone:
            return None
        combat = getattr(game, "combat", None)
        if combat is None:
            return None
        if combat.attack_by(target.id) is not None and len(combat.attacker_ids) == 1:
            return None
        return f"{self.phrase} needs a creature attacking alone, and {target.name} is not"

    def _rejects_attacked_this_turn(self, target: CardState, game: Any) -> str | None:
        """ "target creature that attacked this turn" - a per-turn historical
        fact, not `combat_states`' live one. No game, no per-turn record to
        read: fails open the same way `_rejects_combat_state` does."""
        if not self.must_have_attacked_this_turn:
            return None
        attacked = getattr(game, "attacked_this_turn", None)
        if attacked is None:
            return None
        if target.id in attacked:
            return None
        return f"{self.phrase} needs a creature that attacked this turn, and {target.name} did not"

    def _rejects_entered_this_turn(self, target: Any, game: Any) -> str | None:
        """ "target creature that entered this turn" - read off `CardState.
        turn_entered` against the game's own current turn number, the "turn
        history on `Game`" this restriction is backed by. No game, no turn
        number yet (CR 103.5/103.6's pregame steps), or a bare reference with
        no `turn_entered` to read: fails open the same way every other
        restriction here does when it cannot be judged. A live battlefield
        `CardState` always carries a `turn_entered` (`CardState.turn_entered`'s
        own docstring: stamped once, at the one choke point every route onto
        the battlefield runs through), so `None` *there* is a determinate
        "did not" rather than an unknown to fail open over."""
        if not self.must_have_entered_this_turn:
            return None
        turn_number = getattr(getattr(game, "turn", None), "turn_number", None)
        if turn_number is None:
            return None
        missing = object()
        turn_entered = getattr(target, "turn_entered", missing)
        if turn_entered is missing:
            return None
        if turn_entered == turn_number:
            return None
        return f"{self.phrase} needs a creature that entered this turn, and {target.name} did not"

    def _rejects_crewed_this_turn(
        self, target: CardState, game: Any, source_id: UUID | None
    ) -> str | None:
        """ "target creature that crewed it this turn" - CR 702.122b, scoped
        to this ability's own source Vehicle (`source_id`) rather than any
        Vehicle. No game, or no source id to scope "it" to, fails open the
        same way `_rejects_attacked_this_turn` does with nothing to read."""
        if not self.must_have_crewed_source_this_turn:
            return None
        turn_history = getattr(game, "turn_history", None)
        if turn_history is None or source_id is None:
            return None
        crewed = any(
            entry.kind == "crewed"
            and entry.object_id == target.id
            and entry.related_id == source_id
            for entry in turn_history
        )
        if crewed:
            return None
        return f"{self.phrase} needs a creature that crewed it this turn, and {target.name} did not"

    def _current_types(self, target: CardState, game: Any) -> tuple[Type, ...]:
        """This target's card types right now, layers included (CR 613.5, 613.1d).

        The same reasoning `_rejects_comparison` already applies to power,
        toughness, and mana value: a type-changing continuous effect (layer 4,
        CR 613.1d) can make a noncreature permanent a legal "target creature"
        or an artifact stop being a legal "target nonartifact permanent",
        and CR 613.5 says the game judges that "continually" - Karn, the Great
        Creator's animated Trinisphere is exactly this case. Off the
        battlefield, or with no `game` to compute layers from, the printed
        types on `Card` are the only ones there are (layers only ever apply to
        permanents on the battlefield, CR 611.2c).
        """
        characteristics_of = getattr(game, "characteristics_of", None)
        if target.zone is Zone.BATTLEFIELD and characteristics_of is not None:
            return characteristics_of(target).types
        return target.types

    def _current_supertypes(self, target: CardState, game: Any) -> tuple[Supertype, ...]:
        """This target's supertypes right now, layers included (CR 613.5,
        613.1d) - the same `characteristics_of` reasoning `_current_types`
        already uses, for the supertype half of the same layer instead of the
        card-type half. No printed static ability in this engine's pool grants
        a supertype through a continuous effect yet, but the read has to be
        right the day one does, the same way `_current_types` was fixed ahead
        of a real disagreeing card existing for every one of its cases.
        """
        characteristics_of = getattr(game, "characteristics_of", None)
        if target.zone is Zone.BATTLEFIELD and characteristics_of is not None:
            return characteristics_of(target).supertypes
        return target.supertypes

    def _current_subtypes(self, target: CardState, game: Any) -> tuple[str, ...]:
        """This target's subtypes right now, layers included (CR 613.5,
        613.1d) - the same `characteristics_of` reasoning `_current_types`
        already uses, for the subtype half. Mishra's Factory's own "This land
        becomes a 2/2 Assembly-Worker artifact creature" is exactly this case:
        the printed card has no creature type at all, and "Target Assembly-
        Worker creature" (its own second ability) has to see the one the
        first ability's continuous effect just granted.
        """
        characteristics_of = getattr(game, "characteristics_of", None)
        if target.zone is Zone.BATTLEFIELD and characteristics_of is not None:
            return characteristics_of(target).subtypes
        return target.subtypes

    def _current_colors(self, target: CardState, game: Any) -> tuple[Color, ...]:
        """This target's colors right now (CR 105.1), layers included (CR
        613.1e's color-changing layer 5) - the same `characteristics_of`
        reasoning `_current_types` already uses for a type-changing layer 4
        effect, off the same computed board rather than the printed `Card`.
        """
        characteristics_of = getattr(game, "characteristics_of", None)
        if target.zone is Zone.BATTLEFIELD and characteristics_of is not None:
            return characteristics_of(target).colors
        return target.card.colors

    def _rejects_comparison(
        self,
        target: CardState,
        game: Any,
        caster: str | None = None,
        source_id: UUID | None = None,
    ) -> str | None:
        """ "with mana value N or less" and its power/toughness relatives.

        CR 613.5: "the application of continuous effects ... is continually
        ... performed by the game" - so a creature's *current* power, toughness,
        and mana value (CR 202.3) are what `machines/layers.py` computes with
        every static ability and effect applied, not the printed numbers on
        `CardState`. `Game.characteristics_of` is the same board every combat
        and state-based-action check already reads off of; asking it here
        rather than the `Card` is what makes a pumped or shrunk creature, or
        one whose mana value a copy effect changed, judged on what it is right
        now.

        Layers only ever apply to permanents on the battlefield (CR 611.2c's
        continuous effects, and every layer in CR 613, are about objects
        *there*) - `ComputedBoard.of` has nothing for a card sitting in a
        graveyard or hand, which is exactly where Tamiyo, Compleated Sage's
        own "target ... card with mana value X ... from your graveyard" points.
        For a target anywhere else, the printed values on `Card`/`CardState`
        are the only values there are, so those are read directly instead.

        Fails closed, never open: no `comparison_attribute` at all is the only
        way this returns None outright. An unbound comparison value, or no
        `game` to compute layers from for a battlefield permanent, refuses the
        target - the same choice every other unanswerable restriction in this
        file makes.

        `source_id` is the id of the permanent this requirement's own ability
        is on - `rejects`' own copy of it, threaded down here for
        `ComparisonCount.SOURCE_LOYALTY` ("Nahiri's loyalty"), which needs
        *that* permanent's current loyalty (CR 306.5c), never the target's.
        Without it that one count is unevaluable and refuses the target, the
        same as every other restriction this method cannot answer.
        """
        if self.comparison_attribute is None:
            return None
        label = self.comparison_attribute.value.replace("_", " ")
        comparison_value = self.comparison_value
        if comparison_value is None and self.comparison_count is not None:
            comparison_value = self._counted_bound(target, game, source_id)
        if comparison_value is None and self.comparison_x_definition is not None:
            comparison_value = self._defined_x(game, caster)
        if self.comparison_value_if_revolt is not None and caster is not None:
            revolt_active_for = getattr(game, "revolt_active_for", None)
            if revolt_active_for is not None and revolt_active_for(caster):
                comparison_value = self.comparison_value_if_revolt
        if comparison_value is None:
            return f"{self.phrase} compares {label} to a value this engine cannot resolve right now"
        characteristics_of = getattr(game, "characteristics_of", None)
        if target.zone is Zone.BATTLEFIELD:
            if characteristics_of is None:
                return f"{self.phrase} needs {target.name}'s current {label}, and no game was given"
            board_characteristics = characteristics_of(target)
            mana_value, power, toughness = (
                board_characteristics.mana_value,
                board_characteristics.power,
                board_characteristics.toughness,
            )
        else:
            # Off the battlefield, no layer applies, so the printed values are
            # the only ones there are to compare against (CR 613's layers are
            # all about permanents).
            mana_value, power, toughness = target.mana_value, target.power, target.toughness
        if self.comparison_attribute is ComparisonAttribute.MANA_VALUE:
            values: list[float] = [mana_value]
        elif self.comparison_attribute is ComparisonAttribute.POWER:
            values = [] if power is None else [power]
        elif self.comparison_attribute is ComparisonAttribute.TOUGHNESS:
            values = [] if toughness is None else [toughness]
        else:
            values = [value for value in (power, toughness) if value is not None]
        if not values:
            return (
                f"{self.phrase} needs {with_indefinite_article(label)}, and {target.name} has none"
            )
        if any(self._comparison_holds(value, comparison_value) for value in values):
            return None
        return (
            f"{self.phrase} needs {label} {self._comparison_words(comparison_value)}, "
            f"and {target.name} does not have it"
        )

    def _counted_bound(
        self, target: CardState, game: Any, source_id: UUID | None = None
    ) -> int | None:
        """The number a `comparison_count` names, right now, or None if it
        cannot be counted from what the caller supplied.

        Drown in the Loch's "the number of cards in its controller's graveyard"
        is the *target's* own count - "its controller" is CR 108.4a's, which
        sends the question to the owner instead only for a card that has no
        controller at all (CR 109.4: "only objects on the stack or on the
        battlefield have a controller"), what `controller_or_owner` already
        answers for a card sitting in a graveyard or hand.

        Nahiri, the Unforgiving's "Nahiri's loyalty" is a different shape:
        the count belongs to the *ability's source*, not the target, so it is
        read off `source_id` (`Game.find_by_id`) rather than off `target` at
        all - CR 306.5c: "The loyalty of a planeswalker on the battlefield is
        equal to the number of loyalty counters on it," `CardState.loyalty`'s
        own reading of that rule.

        None here means the restriction is unevaluable, and `_rejects_comparison`
        then refuses the target rather than waving it through - the same
        fail-closed choice it already makes for an unbound X.
        """
        if self.comparison_count is ComparisonCount.CONTROLLERS_GRAVEYARD_CARDS:
            controller = getattr(target, "controller_or_owner", None) or target.controller
            if controller is None:
                return None
            player_of = getattr(game, "player", None)
            if player_of is None:
                return None
            try:
                player = player_of(str(controller))
            except (KeyError, ValueError):
                return None
            graveyard = getattr(player, "graveyard", None)
            return None if graveyard is None else len(graveyard)
        if self.comparison_count is ComparisonCount.SOURCE_LOYALTY:
            if source_id is None:
                return None
            find_by_id = getattr(game, "find_by_id", None)
            if find_by_id is None:
                return None
            source = find_by_id(source_id)
            return None if source is None else source.loyalty
        if self.comparison_count is ComparisonCount.SOURCE_COLORS_SPENT:
            if source_id is None:
                return None
            find_by_id = getattr(game, "find_by_id", None)
            if find_by_id is None:
                return None
            source = find_by_id(source_id)
            return None if source is None else colors_of_mana_spent(game, source)
        return None

    def _defined_x(self, game: Any, caster: str | None) -> int | None:
        """`comparison_x_definition` counted for `caster` right now (CR 107.3c),
        or None when it cannot be: no caster, no game board to count on, or an
        expression `count_expression` does not read."""
        if caster is None or self.comparison_x_definition is None:
            return None
        if getattr(game, "computed_board", None) is None:
            return None
        # Imported here: `machines/effects.py` imports this module at load time.
        from .effects import count_expression

        reader = count_expression(self.comparison_x_definition)
        return None if reader is None else reader(game, caster)

    def _comparison_holds(self, value: float, comparison_value: int) -> bool:
        assert self.comparison_operator is not None
        if self.comparison_operator is ComparisonOperator.LESS_OR_EQUAL:
            return value <= comparison_value
        if self.comparison_operator is ComparisonOperator.GREATER_OR_EQUAL:
            return value >= comparison_value
        if self.comparison_operator is ComparisonOperator.LESS_THAN:
            return value < comparison_value
        if self.comparison_operator is ComparisonOperator.GREATER_THAN:
            return value > comparison_value
        return value == comparison_value

    def _comparison_words(self, comparison_value: int) -> str:
        if self.comparison_operator is ComparisonOperator.LESS_THAN:
            return f"less than {comparison_value}"
        if self.comparison_operator is ComparisonOperator.GREATER_THAN:
            return f"greater than {comparison_value}"
        suffix = {
            ComparisonOperator.LESS_OR_EQUAL: "or less",
            ComparisonOperator.GREATER_OR_EQUAL: "or greater",
            ComparisonOperator.EQUAL: "",
        }[self.comparison_operator]
        return f"{comparison_value} {suffix}".strip()

    def _rejects_controller(self, target: CardState, caster: str) -> str | None:
        # CR 108.4a: "If anything asks for the controller of a card that doesn't
        # have one (because it's not a permanent or spell), use its owner
        # instead." CR 109.4 is why a card in a graveyard has none, and
        # "target card in your graveyard" is the phrase that needs the fallback.
        controller = getattr(target, "controller_or_owner", target.controller)
        if self.controller in _UNRESTRICTED_ALONE or controller is None:
            return None
        if self.controller in (
            ControllerRestriction.EVENT_PLAYER,
            ControllerRestriction.DEFENDING_PLAYER,
        ):
            return self._rejects_event_player_control(target, controller)
        if self.controller is ControllerRestriction.YOU and controller != caster:
            return f"{self.phrase} needs a permanent {caster} controls, and {target.name} is not"
        not_yours = {ControllerRestriction.OPPONENT, ControllerRestriction.NOT_YOU}
        if self.controller in not_yours and controller == caster:
            return f"{self.phrase} cannot target {target.name}, which {caster} controls"
        return None

    def _rejects_event_player_control(self, target: Any, controller: str) -> str | None:
        """`ControllerRestriction.EVENT_PLAYER`: the target must be controlled
        by the player the trigger event named, once `event_player` is bound;
        unbound, nothing is restricted (see the enum member's docstring)."""
        if self.event_player is None or controller == self.event_player:
            return None
        return (
            f"{self.phrase} needs a permanent {self.event_player} controls, "
            f"and {target.name} is not"
        )

    def _rejects_player(self, username: str, caster: str) -> str | None:
        if not self.allows_players:
            return f"{self.phrase} cannot target the player {username}"
        if self.opponent_only and username == caster:
            return f"{self.phrase} cannot target {caster}, who is not an opponent"
        return None


#: `if_gift_promised`'s forward reference resolves once the class itself is
#: fully defined - explicit rather than relying on pydantic's implicit
#: first-use resolution, since a self-referencing field is exactly the case
#: where that can be deferred by surprise.
TargetRequirement.model_rebuild()


class Division(EngineModel):
    """An effect the caster splits among the targets (CR 601.2d).

    "If the spell requires the player to divide or distribute an effect (such as
    damage or counters) among one or more targets, the player announces the
    division. Each of these targets must receive at least one of whatever is
    being divided."

    Two consequences the rest of the engine has to respect. First, the division
    is announced with the spell, at CR 601.2d, not worked out on resolution -
    CR 608.2d only covers "choices other than choices already made as part of
    casting". Second, CR 115.7f: "the same distribution of the effect must be
    used" if the targets are ever changed, so a target that becomes illegal
    loses its share rather than handing it to anyone else.
    """

    model_config = ConfigDict(frozen=True)

    amount: int | None
    """How much there is to divide: Electrolyze's 2 damage. `None` for a
    variable amount printed as "X" (Shatterskull Smashing's "X damage divided
    as you choose among ..."), which CR 107.3a fixes only once the caster
    announces X - `check_division`'s `amount` parameter is how a caller
    supplies the resolved number for one of these."""
    what: str
    """What is being divided, as the card words it: "damage", "+1/+1 counters"."""
    doubled_if_x_at_least: int | None = None
    """Shatterskull Smashing's own second sentence: "If X is 6 or more, ...
    deals twice X damage divided as you choose among them instead." A second
    generalised condition alongside the plain X division above, not a second
    card-specific field - any future card phrasing the identical "if X is N or
    more, twice X ... instead" doubles the same way. `None` for every fixed
    or plain-X division that carries no such clause."""


class TargetingProfile(EngineModel):
    """Everything one card's text asks it to target."""

    model_config = ConfigDict(frozen=True)

    requirements: tuple[TargetRequirement, ...] = ()
    understood: bool = True
    """False when the text mentions a target the parser could not read."""
    division: Division | None = None
    """What the caster divides among these targets, if anything (CR 601.2d)."""
    source_card: Card | None = None
    """The card this profile was read off, when it was read off one at all.

    Every restriction above this line is read from the *caster's* text. CR
    702.16b is the one that is not: "a permanent or player with protection
    can't be targeted by spells with the stated quality" is printed on the
    **target**, and until this field existed nothing consulted it while targets
    were being announced - only `Game.legal_target`'s CR 608.2b recheck did, so
    a spell could be announced at a target it could never legally have chosen
    and then fizzle on resolution instead of the cast being refused outright
    (CR 601.2c).

    `None` for a profile built from bare text (`profile_for_text`, which reads
    a triggered or activated ability's own words and has no card behind them) -
    protection is then left to the resolution recheck exactly as before."""

    @property
    def max_targets(self) -> int | None:
        """The most targets that may be announced, or None if there is no most."""
        if any(requirement.unbounded for requirement in self.requirements):
            return None
        return sum(requirement.count for requirement in self.requirements)

    @property
    def min_targets(self) -> int:
        return sum(requirement.minimum for requirement in self.requirements)

    @property
    def targets_anything(self) -> bool:
        return bool(self.requirements)

    def for_event_player(self, player: str | None) -> "TargetingProfile":
        """Bind `ControllerRestriction.EVENT_PLAYER`'s "that player" to the
        player the trigger event named (`GameEvent.player`) - CR 603.3d
        chooses a trigger's targets as it is put on the stack, when that event
        is known, and CR 608.2b rechecks them against the same restriction.
        `player=None` (no event, or an event naming nobody) leaves the profile
        as read, restriction unbound."""
        if player is None or not any(
            requirement.controller is ControllerRestriction.EVENT_PLAYER
            for requirement in self.requirements
        ):
            return self
        return self.model_copy(
            update={
                "requirements": tuple(
                    requirement.model_copy(update={"event_player": player})
                    if requirement.controller is ControllerRestriction.EVENT_PLAYER
                    else requirement
                    for requirement in self.requirements
                )
            }
        )

    def for_defending_player(self, player: str | None) -> "TargetingProfile":
        """Bind `ControllerRestriction.DEFENDING_PLAYER` to the defending
        player CR 508.5 names - the twin of `for_event_player`, read off the
        attack the trigger event records. `None` leaves it unbound."""
        if player is None or not any(
            requirement.controller is ControllerRestriction.DEFENDING_PLAYER
            for requirement in self.requirements
        ):
            return self
        return self.model_copy(
            update={
                "requirements": tuple(
                    requirement.model_copy(update={"event_player": player})
                    if requirement.controller is ControllerRestriction.DEFENDING_PLAYER
                    else requirement
                    for requirement in self.requirements
                )
            }
        )

    def for_gift_promise(self, promised: bool) -> "TargetingProfile":
        """CR 601.2c/702.174m: which candidate set applies, once whether this
        spell's gift cost was paid (CR 702.174k) is known.

        Not promised - the only case reachable today, since
        `machines/casting.py`'s `ADDITIONAL_COST_KEYWORDS` has no "gift"
        entry and nothing can announce the intention to pay one - leaves
        every requirement exactly as `_parse` read it: CR 601.2c's "a spell
        may require alternative targets only if an alternative or additional
        cost ... was chosen for it", read the other way round. Promised swaps
        in each requirement's own `TargetRequirement.if_gift_promised`
        alternate where `_parse` read one off the card's own "If the gift
        was promised, instead ..." clause, and leaves any requirement
        without one untouched - a requirement elsewhere on the same card
        that names no gift-conditional replacement is not affected by the
        promise at all.
        """
        if not promised:
            return self
        return self.model_copy(
            update={
                "requirements": tuple(
                    requirement.if_gift_promised or requirement for requirement in self.requirements
                )
            }
        )

    def check(
        self,
        targets: list[Any],
        caster: str,
        game: Any = None,
        source_id: UUID | None = None,
        *,
        source: Any = None,
    ) -> None:
        """Raise if this set of targets could not legally be announced (CR 601.2c).

        A spell that requires targets cannot be cast with fewer than it needs -
        it is not an illegal spell that fizzles later, it is a cast that never
        happens. "Up to N" targets are optional and do not count towards the
        minimum (CR 115.6), and so does the nought of "any number of"
        (CR 107.1c).

        CR 115.3 is checked here too: "the same target can't be chosen multiple
        times for any one instance of the word 'target'". Two instances may
        share a target, so the check is per requirement rather than over the
        whole announcement.

        A division makes a further demand of its own (CR 601.2d): every target
        has to receive at least one of what is divided, so no more targets may
        be chosen than there is to go round.

        Pass `game` to have the combat restrictions checked as well - "target
        attacking creature" cannot be settled without it (CR 508.1k). Pass
        `source_id` to have `excludes_source` checked - "target *other*
        creature" cannot be settled without knowing what "this" is.

        CR 702.16b is checked first and separately, because it is the one
        restriction here that is printed on the *target* rather than on the
        spell: a protected target is refused whether or not this parser could
        read the spell's own targeting text. Shroud (CR 702.18a) and hexproof
        (CR 702.11) are printed on the target too, and are checked beside it.

        `source` is the object whose quality CR 702.11d's "hexproof from"
        judges - the spell itself for a cast (`Casting._check_targets`), or an
        ability's source; when it is not given, `source_id` is looked up.
        """
        for target in targets:
            # CR 702.26b: a phased-out permanent "is treated as though it
            # does not exist. It can't affect or be affected by anything else
            # in the game" - nothing can name it as a target.
            if getattr(target, "phased_out", False):
                raise ValueError(
                    f"{target.name} is phased out and is treated as though it does "
                    "not exist (CR 702.26b)"
                )
        self._check_protection(targets, game, caster)
        self._check_shroud(targets, game)
        self._check_hexproof(targets, caster, game, source, source_id)

        if not self.understood:
            return

        maximum = self.max_targets
        if maximum is not None and len(targets) > maximum:
            raise ValueError(
                f"too many targets: {len(targets)} chosen where the spell takes at most {maximum}"
            )

        if len(targets) < self.min_targets:
            raise ValueError(
                f"too few targets: {len(targets)} chosen where the spell requires "
                f"{self.min_targets}"
            )

        if (
            self.division is not None
            and self.division.amount is not None
            and len(targets) > self.division.amount
        ):
            raise ValueError(
                f"too many targets to divide {self.division.amount} {self.division.what} among: "
                f"each target must receive at least one (CR 601.2d)"
            )
        # A variable ("X") division's own amount is `None` here - CR 107.3a's
        # X is not yet a number to check against at announcement/target-
        # selection time - so this bound is skipped and left to
        # `check_division`'s own resolved-amount call once X is known.

        taken = self._fill_slots(targets, caster, game, source_id)
        self._check_one_per_opponent(targets, caster, game, source_id)
        self._check_prior_target_player(targets, caster, game, source_id)
        self._check_distinct_from_prior(taken)

    def prior_target_player(
        self,
        dependent: TargetRequirement,
        targets: Sequence[Any],
        caster: str,
        game: Any,
        source_id: UUID | None = None,
    ) -> str | None:
        """The player `dependent`'s `PRIOR_TARGET_PLAYER` names: the target
        chosen for the requirement printed just before it, if it is a player,
        or that permanent's controller (Searing Blaze's "that player or that
        planeswalker's controller"). `None` when no such target was chosen."""
        position = next(
            (index for index, found in enumerate(self.requirements) if found is dependent), None
        )
        if not position:
            return None
        anchor_requirement = self.requirements[position - 1]
        for target in targets:
            if anchor_requirement.rejects(target, caster, game, source_id) is not None:
                continue
            username = getattr(target, "username", None)
            if isinstance(target, str):
                return target
            if username is not None:
                return str(username)
            found = getattr(target, "controller_or_owner", None) or getattr(
                target, "controller", None
            )
            return None if found is None else str(found)
        return None

    def _check_prior_target_player(
        self, targets: list[Any], caster: str, game: Any, source_id: UUID | None
    ) -> None:
        """`ControllerRestriction.PRIOR_TARGET_PLAYER`, across the whole
        announcement (CR 601.2c)."""
        for requirement in self.requirements:
            if requirement.controller is not ControllerRestriction.PRIOR_TARGET_PLAYER:
                continue
            anchor = self.prior_target_player(requirement, targets, caster, game, source_id)
            if anchor is None:
                continue
            position = self.requirements.index(requirement)
            anchor_requirement = self.requirements[position - 1]
            for target in targets:
                if isinstance(target, str) or getattr(target, "username", None) is not None:
                    continue
                if anchor_requirement.rejects(target, caster, game, source_id) is None:
                    continue
                if requirement.rejects(target, caster, game, source_id) is not None:
                    continue
                found = getattr(target, "controller_or_owner", None) or getattr(
                    target, "controller", None
                )
                if found is not None and str(found) != anchor:
                    raise ValueError(
                        f"{requirement.phrase} needs a creature {anchor} controls, and "
                        f"{target.name} is not (CR 601.2c)"
                    )

    def _check_one_per_opponent(
        self, targets: list[Any], caster: str, game: Any, source_id: UUID | None
    ) -> None:
        """`TargetRequirement.one_per_opponent`: every opponent who controls
        a legal choice has one of the announced targets (CR 601.2c)."""
        battlefield = getattr(game, "battlefield", None)
        if battlefield is None:
            return
        chosen: set[str] = set()
        for target in targets:
            found = getattr(target, "controller_or_owner", None) or getattr(
                target, "controller", None
            )
            if found is not None:
                chosen.add(str(found))
        for requirement in self.requirements:
            if not requirement.one_per_opponent:
                continue
            owed = {
                str(permanent.controller_or_owner)
                for permanent in battlefield
                if requirement.rejects(permanent, caster, game, source_id) is None
            }
            missing = sorted(owed - chosen)
            if missing:
                raise ValueError(
                    f"{requirement.phrase} needs one target for each opponent, and "
                    f"{', '.join(missing)} controls a legal one no target was chosen "
                    f"from (CR 601.2c)"
                )

    def _check_distinct_from_prior(self, taken: dict[int, set[TargetRef]]) -> None:
        """`TargetRequirement.distinct_from_prior_requirement`: CR 115.3/
        115.4's paired "any target"/"any other target" idiom (Boulder Dash,
        Arc Trail) refuses an announcement that names the same object for
        both halves, rather than letting it through to resolve with both
        amounts stacked onto that one object.

        `taken` is `_fill_slots`'s own bookkeeping, already keyed by
        `id(requirement)` exactly the way this needs it - the requirement
        marked `distinct_from_prior_requirement` and the requirement printed
        immediately before it in `self.requirements` must not have been
        filled by the same `TargetRef`. A `TargetRef` a target could not be
        coerced to (see `_why_not`) is never recorded in `taken` at all, so
        this fails open for those exactly as every other cross-requirement
        check here does."""
        for position, requirement in enumerate(self.requirements):
            if not requirement.distinct_from_prior_requirement or position == 0:
                continue
            prior = self.requirements[position - 1]
            overlap = taken.get(id(requirement), set()) & taken.get(id(prior), set())
            if overlap:
                raise ValueError(
                    f"{requirement.phrase} needs a target other than the one chosen for "
                    f"{prior.phrase}, and the same object was named for both (CR 115.3, "
                    "CR 115.4)"
                )

    def _check_protection(self, targets: list[Any], game: Any, caster: str | None = None) -> None:
        """CR 702.16b, at announcement (CR 601.2c) rather than only at the
        CR 608.2b recheck.

        Asks the game the same question `Game.legal_target` already asks on
        resolution (`protection_refusal`), so the two can never disagree about
        what protection means - this file deliberately holds no protection
        vocabulary of its own. Needs both a `game` to read the target's
        *current* qualities from (Akroma's Memorial grants protection in
        layer 6, so it is not on the printed card) and a `source_card` to
        compare them against; without either, protection stays unchecked here
        and the resolution recheck is still the backstop.
        """
        if game is None or self.source_card is None:
            return
        refusal_of = getattr(game, "protection_refusal", None)
        if refusal_of is None:
            return
        for target in targets:
            # `source_controller`: CR 702.16k's protection from a player is
            # decided by who controls the spell or ability, not by any
            # quality printed on its source (Figure of Fable's Avatar).
            refusal = refusal_of(target, self.source_card, source_controller=caster)
            if refusal is not None:
                raise ValueError(refusal)

    def _check_shroud(self, targets: list[Any], game: Any) -> None:
        """CR 702.18a, at announcement (CR 601.2c) rather than only at the
        CR 608.2b recheck - `_check_protection`'s sibling, one call below it.

        Needs only a `game`, unlike `_check_protection`: shroud names no
        quality to compare a source against (CR 702.18a is unconditional -
        "can't be the target of spells or abilities", full stop), so there is
        nothing here a missing `source_card` would leave unchecked. This is
        also why one shared call covers both a spell's targets
        (`Casting.choose_targets`) and an activated or triggered ability's
        (`Game.activate_ability`, `Game.put_triggers_on_stack`, both of which
        already call `TargetingProfile.check`): shroud refuses the
        controller's own ability exactly as it refuses an opponent's spell,
        so there is no caster-specific case for a spell-only hook to carry.
        """
        if game is None:
            return
        refusal_of = getattr(game, "shroud_refusal", None)
        if refusal_of is None:
            return
        for target in targets:
            refusal = refusal_of(target)
            if refusal is not None:
                raise ValueError(refusal)

    def _check_hexproof(
        self,
        targets: list[Any],
        caster: str,
        game: Any,
        source: Any,
        source_id: UUID | None,
    ) -> None:
        """CR 702.11, at announcement - `_check_shroud`'s sibling, one call below it.

        Asks `Game.hexproof_refusal`, the one hexproof vocabulary shared with
        `Game.legal_target`'s CR 608.2b recheck and with the candidate lists a
        live `CHOOSE_TARGETS` question offers. Unlike shroud it needs the
        `caster` - CR 702.11b's "your opponents control" - and, for CR
        702.11d's "hexproof from [quality]", the object whose quality is
        judged: the spell, or the ability's source. That is `source` when the
        caller has it, else whatever `source_id` names; with neither, only
        plain hexproof is decided (a quality nothing can be compared against
        is not enforced, the same fail-open `_check_protection` takes).

        Being here is what reaches every path at once: a spell's targets
        (`Casting._check_targets`), an activated ability's
        (`Game._announce_activation_targets`, `off_battlefield_activation`,
        `equip_activation`) and a triggered ability's
        (`Game.why_cannot_target_with_trigger`).
        """
        if game is None:
            return
        refusal_of = getattr(game, "hexproof_refusal", None)
        if refusal_of is None:
            return
        if source is None and source_id is not None:
            source = game.find_by_id(source_id)
        for target in targets:
            refusal = refusal_of(target, caster, source)
            if refusal is not None:
                raise ValueError(refusal)

    def _fill_slots(
        self, targets: list[Any], caster: str, game: Any = None, source_id: UUID | None = None
    ) -> dict[int, set[TargetRef]]:
        """Match each chosen target to a requirement it satisfies (CR 601.2c).

        Returns `taken`, keyed by `id(requirement)` exactly as `_why_not`
        keys it - which `TargetRef`s ended up filling each requirement's own
        slots. `_check_distinct_from_prior` is the one caller that needs it
        after the fact; every other requirement-local check here already had
        it in scope while `_fill_slots` was still running."""
        slots = [
            requirement
            for requirement in self.requirements
            if not requirement.unbounded
            for _ in range(requirement.count)
        ]
        unbounded = [r for r in self.requirements if r.unbounded]
        taken: dict[int, set[TargetRef]] = {}
        controllers: dict[int, set[str]] = {}
        shared_types: dict[int, frozenset[Type]] = {}
        filled: dict[int, int] = {}
        totals: dict[int, float] = {}

        for target in targets:
            reasons: list[str] = []
            for index, slot in enumerate(slots):
                reason = self._why_not(
                    slot, target, caster, taken, game, source_id, controllers, shared_types, totals
                )
                if reason is None:
                    slots.pop(index)
                    filled[id(slot)] = filled.get(id(slot), 0) + 1
                    break
                reasons.append(reason)
            else:
                for requirement in unbounded:
                    reason = self._why_not(
                        requirement,
                        target,
                        caster,
                        taken,
                        game,
                        source_id,
                        controllers,
                        shared_types,
                        totals,
                    )
                    if reason is None:
                        filled[id(requirement)] = filled.get(id(requirement), 0) + 1
                        break
                    reasons.append(reason)
                else:
                    raise ValueError("illegal target: " + "; ".join(dict.fromkeys(reasons)))

        # CR 601.2c: the total can reach `min_targets` while one mandatory
        # "target ..." is left empty and an optional "up to one" beside it
        # takes the target instead - every requirement needs its own minimum.
        for requirement in self.requirements:
            if filled.get(id(requirement), 0) < requirement.minimum:
                raise ValueError(
                    f"too few targets for {requirement.phrase}: "
                    f"{filled.get(id(requirement), 0)} chosen where it requires "
                    f"{requirement.minimum} (CR 601.2c)"
                )
        return taken

    @staticmethod
    def _why_not(
        requirement: TargetRequirement,
        target: Any,
        caster: str,
        taken: dict[int, set[TargetRef]],
        game: Any = None,
        source_id: UUID | None = None,
        controllers: dict[int, set[str]] | None = None,
        shared_types: dict[int, frozenset[Type]] | None = None,
        totals: dict[int, float] | None = None,
    ) -> str | None:
        """Why this requirement cannot take this target, CR 115.3 included.

        `controllers` carries the controllers already chosen for each
        requirement, which is what "controlled by different players" needs and
        `rejects` cannot see: it judges one target at a time. Left `None` by a
        caller that is only re-matching an announcement `check` already
        accepted (`assign_to_owners`), where re-refusing it would be wrong.
        """
        reason = requirement.rejects(target, caster, game, source_id)
        if reason is not None:
            return reason
        controller: str | None = None
        if requirement.distinct_controllers and controllers is not None:
            found = getattr(target, "controller_or_owner", None) or getattr(
                target, "controller", None
            )
            controller = None if found is None else str(found)
            if controller is not None and controller in controllers.get(id(requirement), set()):
                return (
                    f"{requirement.phrase} needs targets controlled by different players, "
                    f"and {controller} already controls one of them (CR 601.2c)"
                )
        types: frozenset[Type] | None = None
        if requirement.share_a_card_type and shared_types is not None:
            types = _computed_card_types(target, game)
            common = shared_types.get(id(requirement))
            if types is not None and common is not None and not (common & types):
                return (
                    f"{requirement.phrase} need targets that share a card type, and "
                    f"{target} shares none with the others (CR 601.2c)"
                )
        mana_value: float | None = None
        if requirement.total_mana_value_at_most is not None and totals is not None:
            mana_value = _computed_mana_value(target, game)
            running = totals.get(id(requirement), 0)
            if (
                mana_value is not None
                and running + mana_value > requirement.total_mana_value_at_most
            ):
                return (
                    f"{requirement.phrase} need a total mana value of "
                    f"{requirement.total_mana_value_at_most} or less, and {target} would bring "
                    f"it to {running + mana_value:g} (CR 601.2c)"
                )
        try:
            reference = TargetRef.coerce(target)
        except TypeError:
            reference = None
        already = taken.setdefault(id(requirement), set())
        if reference is not None:
            if reference in already:
                return f"{requirement.phrase} cannot choose {target} twice (CR 115.3)"
            already.add(reference)
        if controller is not None and controllers is not None:
            controllers.setdefault(id(requirement), set()).add(controller)
        if types is not None and shared_types is not None:
            common = shared_types.get(id(requirement))
            shared_types[id(requirement)] = types if common is None else common & types
        if mana_value is not None and totals is not None:
            totals[id(requirement)] = totals.get(id(requirement), 0) + mana_value
        return None

    def assign_to_owners(
        self,
        owners: Sequence[int],
        targets: Sequence[Any],
        caster: str,
        game: Any = None,
        source_id: UUID | None = None,
    ) -> dict[int, list[Any]]:
        """Bucket an already-legal announcement by which chosen mode instance
        each target belongs to (CR 700.2f: "Modal spells and abilities may
        have different targeting requirements for each mode").

        `owners` has one entry per entry of `self.requirements`, naming which
        0-based position in the chosen-modes list that requirement came from -
        exactly what `profile_for_modes_with_owners` returns alongside the
        profile itself. This replays the same slot-matching `check` uses
        (`_fill_slots`) but keeps the owner a slot came from instead of
        discarding it, so a caller can tell Kozilek's Command's "target
        player" apart from its "target creature" once both are flattened into
        one `choose_targets` announcement.

        Call only after `check(targets, ...)` already accepted this exact
        announcement - this raises if a target cannot be placed, but does none
        of `check`'s own count validation, and duplicating its slot search
        here (rather than threading owners through `_fill_slots` itself) is
        deliberate: `_fill_slots` is also used for the ordinary undifferentiated
        case, where no caller has an owner to give it.
        """
        if len(owners) != len(self.requirements):
            raise ValueError("owners must have exactly one entry per requirement")
        slots: list[tuple[TargetRequirement, int]] = []
        for owner, requirement in zip(owners, self.requirements, strict=True):
            if not requirement.unbounded:
                slots.extend([(requirement, owner)] * requirement.count)
        unbounded = [
            (requirement, owner)
            for owner, requirement in zip(owners, self.requirements, strict=True)
            if requirement.unbounded
        ]
        taken: dict[int, set[TargetRef]] = {}
        result: dict[int, list[Any]] = {}
        for target in targets:
            placed = False
            for index, (requirement, owner) in enumerate(slots):
                if self._why_not(requirement, target, caster, taken, game, source_id) is None:
                    slots.pop(index)
                    result.setdefault(owner, []).append(target)
                    placed = True
                    break
            if placed:
                continue
            for requirement, owner in unbounded:
                if self._why_not(requirement, target, caster, taken, game, source_id) is None:
                    result.setdefault(owner, []).append(target)
                    placed = True
                    break
            if not placed:
                raise ValueError(
                    f"{target} could not be assigned to any chosen mode's targeting "
                    f"requirement - call check() first to catch an illegal announcement"
                )
        return result

    def check_division(
        self, shares: Sequence[int], targets: Sequence[Any], *, amount: int | None = None
    ) -> None:
        """Raise if this is not a legal division of the effect (CR 601.2d).

        One share per target, in the order the targets were announced. Every
        share is at least one, because "each of these targets must receive at
        least one of whatever is being divided", and they add up to exactly the
        amount the card divides - CR 107.1a rules out splitting it any other
        way.

        `amount` overrides `self.division.amount` for a variable division
        (Shatterskull Smashing's X, doubled if X is 6 or more): the printed
        amount is `None` there because CR 107.3a's X is not fixed until the
        caster announces it, so the caller resolves the real number (from
        `Casting.x_value`, doubled per `Division.doubled_if_x_at_least`) and
        hands it in here rather than this method guessing at X itself.
        """
        if self.division is None:
            raise ValueError("this spell divides nothing, so there is no division to announce")
        total = self.division.amount if amount is None else amount
        if total is None:
            raise ValueError(
                f"{self.division.what} is a variable (X) division; pass amount= "
                f"with X already resolved (CR 107.3a, CR 601.2d)"
            )
        if len(shares) != len(targets):
            raise ValueError(
                f"the division needs one share per target: {len(shares)} shares for "
                f"{len(targets)} targets (CR 601.2d)"
            )
        if any(share < 1 for share in shares):
            raise ValueError(
                f"each target must receive at least one of the {self.division.what} (CR 601.2d)"
            )
        if sum(shares) != total:
            raise ValueError(
                f"the division must use all {total} {self.division.what}, "
                f"not {sum(shares)} (CR 601.2d)"
            )


# --------------------------------------------------------------------------
# Reading the templates
# --------------------------------------------------------------------------

_REMINDER = re.compile(r"\([^)]*\)")
_TRIGGER = re.compile(r"^(?:when|whenever|at )", re.IGNORECASE)
#: A quoted granted ability - Weapons Manufacturing's own "create a colorless
#: artifact token named Munitions with \"When this token leaves the
#: battlefield, it deals 2 damage to any target.\"" - is CR 111.3's *token's*
#: stated text, not this ability's own (CR 115.1's "target" template belongs
#: to whichever object's words print it). Stripped before anything below
#: scans for "target" so a granted ability quoting one can never be read as
#: this ability's own targeting requirement - `_TOKEN_KEYWORDS`'s `and`-joined
#: keyword tail never contains a quote mark, and a granted ability nested a
#: level deeper (Urza's Saga's own single-quoted "'This token gets +1/+1 for
#: each artifact you control.'") sits *inside* the outer double-quoted span
#: this already removes whole, so only the double-quote form needs matching
#: here.
_QUOTED_SPAN = re.compile(r'["“].*?["”]', re.DOTALL)
_ANY_TARGET = re.compile(r"\bany target\b", re.IGNORECASE)
#: Boulder Dash/Arc Trail's own second half: "1 damage to any other target."
#: Never matched by `_ANY_TARGET` itself - "other" sits between "any" and
#: "target", so the two are disjoint matches on the same text, not one
#: pattern's alternation. Peeled off in `_parse`, but *only* when a bare
#: `_ANY_TARGET` also matched earlier in the same text (CR 115.4's paired
#: idiom) - a solitary "any other target" with nothing before it (Iron Fist,
#: Living Weapon; Red Hulk; Screaming Nemesis) is left for the generic
#: `_TARGET_WORD` scan below, which reads its "other" as `excludes_source`
#: exactly as it always did.
_ANY_OTHER_TARGET = re.compile(r"\bany other target\b", re.IGNORECASE)
#: The plural matters: CR 115.4's damage wording is "among one or two targets",
#: with no noun after it at all.
_TARGET_WORD = re.compile(r"\btargets?\b", re.IGNORECASE)
_PLACEHOLDER = "\x00"

#: CR 115.7's wording for retargeting something already on the stack - "change a
#: target" (CR 115.7b), "change any targets" (CR 115.7c), "choose new targets"
#: (CR 115.7d). It names no requirement of its own, so it is dropped before the
#: templates are read rather than left to fail the parse.
_RETARGETING = re.compile(
    r"\bchoose\s+new\s+targets?\b|\bchange\s+(?:a|any|the)\s+targets?\b", re.IGNORECASE
)

#: "target spell **that targets** an artifact or creature you control"
#: (Fugitive Droid) - CR 601.2c's own noun-phrase "target" and, inside the
#: very same phrase, a *second* use of the word describing a property of
#: that spell's own targets, not a second targeting requirement of this
#: ability's own. `_TARGET_WORD`'s bare `\btargets?\b` scan cannot tell the
#: two apart on sight (the same ambiguity `_RETARGETING`'s own docstring
#: describes for "change/choose new target(s)"), so the word is swapped for
#: `_THAT_TARGETS_MARKER` before the scan ever runs - unlike `_RETARGETING`,
#: which drops its whole phrase because it carries no restriction to keep,
#: this keeps the phrase's own description in place (`_SPELL_TARGETS_GATE_
#: RE` reads the marker in `that`'s place) so `_read_phrase` still sees it.
_THAT_TARGETS_VERB_RE = re.compile(r"\bthat targets\b", re.IGNORECASE)
_THAT_TARGETS_MARKER = "\x02"

#: "This spell costs {N} less to cast if it targets a `<color>` spell."
#: (Mystical Dispute) - CR 601.2f's self-referential cost reduction, read for
#: real by `Game.cost_reduction_for`/`_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE`
#: in `models/game.py`. The verb "targets" here names no targeting
#: *requirement* of this ability's own (CR 115.1's "target" template is
#: always a noun phrase, "target `<noun>`") - it is a condition on a target
#: chosen elsewhere on the card - but `_TARGET_WORD` cannot tell the verb
#: apart from the noun-phrase marker on sight, so this sentence used to be
#: fed to `_read_phrase` anyway and fail the whole clause closed
#: (`understood=False`), which wrongly stopped Mystical Dispute's own
#: *second* sentence - "Counter target spell unless its controller pays
#: {3}." - from being read at all. Dropped before the scan, the same way
#: `machines/effects.py`'s own `_SELF_COST_REDUCTION_LINE_RE` drops it from
#: resolution text; duplicated rather than imported to avoid a circular
#: import (`machines/effects.py` already imports this module).
_SELF_COST_REDUCTION_LINE = re.compile(
    r"\bThis spell costs \{\d+\} less to cast if [^.]+\.\s*", re.IGNORECASE
)

#: "This spell costs {1} more to cast for each target beyond the first."
#: (Fireball; Launch the Fleet's identically-worded "Strive — ..." clause,
#: the optional em-dash prefix stripped along with it since CR 207.2c gives
#: the "Strive" ability word no rules meaning of its own) - the cost-increase
#: twin of `_SELF_COST_REDUCTION_LINE` just above, and the identical
#: preamble-poisoning bug: its own bare "target" is not a noun phrase at all
#: ("beyond the first" is not a noun `_read_phrase` can read), so it used to
#: fail the *whole* profile closed (`understood=False`) - not merely leaving
#: this one clause unread, but silently un-enforcing every real restriction
#: on the card. Fireball's own "any number of targets" happens to accept
#: anything anyway, but Launch the Fleet's "any number of target creatures"
#: does not, and a land was a legal target for it until this was stripped.
#: `machines/casting.py`'s own `_COST_INCREASE_PER_TARGET_RE` is what
#: actually prices the increase (CR 601.2f); this is only the same read-it-
#: out-of-the-way fix `machines/effects.py`'s own `_COST_INCREASE_PER_TARGET_
#: LINE_RE` already applies to the resolution text, duplicated here for the
#: identical circular-import reason `_SELF_COST_REDUCTION_LINE` is. One or
#: more mana symbols (`\{[^}]+\}(?:\{[^}]+\})*`), matching `_COST_INCREASE_
#: PER_TARGET_RE`'s own amount group and `effects.py`'s twin - Aerial
#: Formation's off-pool "costs {2}{U} more" is the multi-symbol proof.
_COST_INCREASE_PER_TARGET_LINE = re.compile(
    r"\b(?:Strive\s*—\s*)?This spell costs \{[^}]+\}(?:\{[^}]+\})* more to cast for each "
    r"target beyond the first\.\s*",
    re.IGNORECASE,
)

#: "The copy targets that token." (Frontline Heroism, following its own
#: "... then copy that spell.") - CR 707.10's forced retarget, stated as a
#: declaration of what the copy now points at rather than a choice anyone
#: makes. `_RETARGETING` already drops the *permission* shape ("You may
#: choose new targets for the copy.", Alania, Divergent Storm); this is the
#: sibling *declarative* shape, and it names no targeting requirement of its
#: own for the same reason - the copy's target is decided by
#: `machines/effects.py`'s own resolution code
#: (`_parse_create_token_then_copy_spell_retargeted_clause`), not chosen by
#: this ability's controller at announcement (CR 603.3d).
_COPY_TARGETS_DECLARATION = re.compile(r"\bThe copy targets? [^.]+\.\s*", re.IGNORECASE)

#: "... a spell that targets only a single creature you control ..."
#: (Frontline Heroism's own trigger *condition*, CR 603.1's "[Whenever]
#: [condition], [effect]"). This is a fact `machines/triggers.py`'s
#: `condition_matches` checks about an *already-chosen* target elsewhere on
#: the stack, not a "target `<noun>`" requirement of this ability's own
#: CR 603.3d announcement - but `_TARGET_WORD` cannot tell a condition's
#: "targets" apart from an effect's, so it used to be fed to `_read_phrase`
#: and fail the whole ability closed. `machines/triggers.py` carries the
#: identical regex (`_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE`) for the same
#: reason on the condition-matching side; duplicated here rather than shared
#: to avoid a circular import between the two modules.
_TARGETS_ONLY_SINGLE_CREATURE_CONDITION_CLAUSE = re.compile(
    r"\bthat targets only a single creature you control\b", re.IGNORECASE
)

#: "... with a single target" (Bolt Bend's "Change the target of target spell
#: or ability with a single target") - CR 115.9a's "[spell or ability] with [a
#: number of] targets", a *property of the thing being targeted*, not a second
#: "target `<noun>`" of the spell's own. The bare `_TARGET_WORD` scan cannot
#: tell the two apart on sight, so this phrase is replaced by
#: `_SINGLE_TARGET_PLACEHOLDER` before the scan runs - the same
#: strip-before-reading trick `_RETARGETING` and
#: `_TARGETS_ONLY_SINGLE_CREATURE_CONDITION_CLAUSE` already use - and `_parse`
#: then hands the restriction to the requirement it was printed after, as
#: `TargetRequirement.required_target_count`. Left in the text it read as a
#: whole second requirement, and Bolt Bend asked for two targets, which no
#: announcement could ever satisfy.
_SINGLE_TARGET_RESTRICTION = re.compile(r"\bwith a single target\b", re.IGNORECASE)

#: "target spell or ability" (Bolt Bend, Redirect Lightning, Deflecting Swat,
#: Spellskite) - one requirement that CR 115.2(b) lets reach either kind of
#: stack object, a spell or an ability (CR 113.1c makes an ability on the
#: stack an object). Read by `_read_phrase` as the plain "spell" requirement
#: widened to abilities, so it used to be read as "target spell" alone and an
#: ability could never be chosen.
_SPELL_OR_ABILITY = re.compile(r"^\s*spell or ability\b", re.IGNORECASE)
_SINGLE_TARGET_PLACEHOLDER = "\x01"

#: "target spell that targets `<description>`" (Fugitive Droid: "an artifact
#: or creature you control"; Siren Stormtamer: "you or a creature you
#: control") - CR 601.2c's ordinary "target spell", further restricted by a
#: property of *that spell's own targets* rather than of the spell itself.
#: `_read_phrase`'s ordinary noun-phrase grammar has nothing to say about the
#: word "targets" appearing a second time inside the same phrase (it is not a
#: card type, a colour, or any other adjective a "target ..." phrase already
#: reads), so this is its own shape, read before the generic chain the same
#: way `_SPELL_OR_ABILITY` is.
_SPELL_TARGETS_GATE_RE = re.compile(
    rf"^\s*spell(?P<or_ability> or ability)? that {_THAT_TARGETS_MARKER}"
    r" (?P<clause>[a-z].*?)\.?$",
    re.IGNORECASE,
)
#: "you" alone (Siren Stormtamer's own first disjunct, "targets you or a
#: creature you control").
_TARGETS_YOU_RE = re.compile(r"^you$", re.IGNORECASE)
#: "you or a `<type>`[ or `<type>`] you control" - CR 115.1's "or" tried
#: before the plain type-list shape below, which would otherwise read
#: "you" itself as an unrecognised leading type word and fail the whole
#: clause.
_TARGETS_YOU_OR_TYPES_RE = re.compile(
    r"^you or (?P<types>(?:an? )?[a-z]+(?:\s+or\s+(?:an? )?[a-z]+)*) you control$",
    re.IGNORECASE,
)
#: "a `<type>`[ or `<type>`] you control" (Fugitive Droid's own "an artifact
#: or creature you control", no "you" disjunct at all).
_TARGETS_TYPES_YOU_CONTROL_RE = re.compile(
    r"^(?P<types>(?:an? )?[a-z]+(?:\s+or\s+(?:an? )?[a-z]+)*) you control$", re.IGNORECASE
)


def _read_must_target_types(text: str) -> "SortedFrozenSet[Type] | None":
    """ "`<type>`[ or `<type>`]" - CR 300.1's card types this parser knows,
    read the same closed `_TYPE_NOUNS` vocabulary every other type-list
    reader in this module already uses. `None` when any word is not one of
    them - the fail-closed signal for the clause that named it."""
    words = [
        re.sub(r"^an?\s+", "", part.strip(), flags=re.IGNORECASE).lower()
        for part in re.split(r"\s+or\s+", text.strip())
        if part.strip()
    ]
    if not words or any(word not in _TYPE_NOUNS for word in words):
        return None
    return frozenset(_TYPE_NOUNS[word] for word in words)


#: CR 601.2d's two templates, the amount and what is being divided.
_DIVIDED = re.compile(
    r"\b(?:deals?\s+(?P<damage>[\w]+)\s+damage\s+divided(?:\s+as\s+you\s+choose)?\s+among"
    r"|distributes?\s+(?P<counters>[\w]+)\s+(?P<kind>\S+)\s+counters?"
    r"(?:\s+divided)?(?:\s+as\s+you\s+choose)?\s+among)\b",
    re.IGNORECASE,
)

#: "activated or triggered ability" and its shorter relatives (CR 113.1c).
_ABILITY_PHRASE = re.compile(
    r"^\s*(?:(?:activated|triggered|loyalty)\s+(?:or\s+|and\s+)?)*abilit(?:y|ies)\b",
    re.IGNORECASE,
)


#: The tail after "target activated or triggered ability": "you control",
#: "from a[n] <card type> source", or both (Echo, Perceptive Prodigy).
_ABILITY_YOU_CONTROL_FROM_SOURCE_RE = re.compile(
    r"^(?P<you>you control)?\s*(?:from an? (?P<type>[a-z]+) source)?$", re.IGNORECASE
)


def _ability_source_types(target: Any, game: Any) -> frozenset[Type] | None:
    """The card types of an ability's source (CR 113.7): computed while it is
    on the battlefield, its last known information once it has left
    (CR 113.7a), `None` when there is no source to read."""
    source = None
    if game is not None:
        finder = getattr(target, "source", None)
        if callable(finder):
            source = finder(game)
    if source is None:
        source = getattr(target, "source_last_known", None)
    if source is None:
        return None
    if getattr(source, "zone", None) is Zone.BATTLEFIELD and game is not None:
        return frozenset(game.characteristics_of(source).types)
    last_known = getattr(source, "last_known_types", None)
    if last_known is not None:
        return frozenset(last_known)
    return frozenset(getattr(source, "types", ()) or ())


def _ability_kinds_named(words: str) -> frozenset[AbilityKind]:
    """The CR 113.3 categories `_ABILITY_PHRASE`'s words name: "triggered" is
    CR 113.3c's, "activated" CR 113.3b's, and "loyalty" is an activated
    ability too (CR 606.1). No category word names none, which `rejects`
    reads as any."""
    named = {word.lower() for word in re.findall(r"activated|triggered|loyalty", words, re.I)}
    kinds = set()
    if "triggered" in named:
        kinds.add(AbilityKind.TRIGGERED)
    if named & {"activated", "loyalty"}:
        kinds.add(AbilityKind.ACTIVATED)
    return frozenset(kinds)


#: "... or colorless spell" (Consign to Memory's "target triggered ability or
#: colorless spell") - the tail left over once `_ABILITY_PHRASE` has consumed
#: the ability half of the compound. Generalised across CR 105.2's whole
#: color-*count* vocabulary (`_Adjectives.color_count`'s own set), not
#: hardcoded to "colorless" alone, since the identical "ability or
#: `<color-count>` spell" shape would read the same way for a hypothetical
#: "... or monocolored spell".
_ABILITY_OR_COLOR_COUNT_SPELL_RE = re.compile(
    r"^or\s+(?P<color_count>multicolored|monocolored|colorless)\s+spell$", re.IGNORECASE
)

_TYPE_NOUNS = {
    "creature": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "battle": Type.BATTLE,
    # CR 300.1 lists instant and sorcery among the card types. Neither can be a
    # permanent, so both only ever turn up beside "card" or "spell" (CR 109.2a,
    # CR 109.2b) - "target instant or sorcery card in your graveyard".
    "instant": Type.INSTANT,
    "sorcery": Type.SORCERY,
}

#: Every subtype word CR 205.3g/h/i/k/q close off as its own card type's -
#: artifact types (Equipment, Vehicle, ...), enchantment types, land types,
#: the instant/sorcery spell types, and the battle type - reversed onto the
#: `Type` each one belongs to. Read from `machines/layers.py`'s own
#: `CLOSED_SUBTYPE_LISTS` rather than a second, drifting copy of the same
#: enumeration. Deliberately excludes CR 205.3m's creature types (in the
#: hundreds, never enumerated here - see `_is_bare_subtype_word`'s own
#: docstring) and CR 205.3j's planeswalker types (the same shape, no closed
#: list): those stay unrecognised outside the shapes already read elsewhere.
_CLOSED_LIST_TYPE_OF: dict[str, Type] = {
    subtype.lower(): card_type
    for card_type, subtypes in CLOSED_SUBTYPE_LISTS.items()
    for subtype in subtypes
}

#: "target creature or Equipment card ..." (Nahiri, the Unforgiving) - a
#: two-item noun list whose first item is an ordinary CR 300.1 card type and
#: whose second is a bare CR 205.3g/h/i/k/q subtype word standing in for its
#: own elided type, the same elision `_is_bare_subtype_word` already reads
#: for a *lone* subtype (Greasefang, Okiba Boss's "target Vehicle card") -
#: here as the second half of an "or" instead of the whole noun. See
#: `_split_type_or_closed_subtype_card`'s own docstring for why this cannot
#: be merged into the ordinary noun-list loop's single `card_types`/
#: `required_subtypes` pair.
_TYPE_OR_CLOSED_SUBTYPE_CARD_RE = re.compile(
    r"^\s*(?P<first>[a-z]+)\s+or\s+(?P<subtype>[A-Z][A-Za-z]*)\s+(?P<noun>card|permanent)\b"
)

#: CR 105.1: "there are five colors in the Magic game: white, blue, black,
#: red, and green." Read as a leading adjective, the same as a card type or
#: supertype adjective - "target black or red permanent" (Celestial Purge).
#: Deliberately five, not six: "colorless" is CR 105.2c's *absence* of color,
#: not a sixth color to check for membership in a `colors` tuple the way the
#: five real ones are, and no card in this wave's pool needs it read.
_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}
#: CR 205.4a: "the supertypes are basic, legendary, ongoing, snow, and world" -
#: verified this session (`knowledge_search`), closed at five. Read the same
#: way as `_TYPE_NOUNS`: bare for "target basic land"
#: (`TargetRequirement.required_supertypes`), "non-" prefixed for "target
#: nonbasic land" (`excluded_supertypes`, `_negated_supertype`). "ongoing"
#: only ever appears on a Scheme card this engine does not model, but the word
#: is still read correctly rather than left to fail the parse.
_SUPERTYPE_NOUNS = {
    "basic": Supertype.BASIC,
    "legendary": Supertype.LEGENDARY,
    "ongoing": Supertype.ONGOING,
    "snow": Supertype.SNOW,
    "world": Supertype.WORLD,
}
_PERMANENT_NOUNS = frozenset({"permanent"})
#: A bare "card", with no type in front of it, is never on the battlefield -
#: it needs a zone clause to say where it is (CR 115.2, CR 400.1).
_CARD_NOUNS = frozenset({"card"})
_PLAYER_NOUNS = frozenset({"player", "opponent"})
_SPELL_NOUNS = frozenset({"spell"})
_QUALIFIERS = frozenset({"tapped", "untapped", "another", "other"})

#: Adjectives that say what state the permanent has to be in, rather than what
#: it is. "tapped" is a game state too, but it lives on the permanent.
_TAPPED_ADJECTIVES = {"tapped": True, "untapped": False}
_COMBAT_ADJECTIVES = {
    "attacking": CombatState.ATTACKING,
    "blocking": CombatState.BLOCKING,
}
#: "another"/"other" are read as `TargetRequirement.excludes_source` rather
#: than ignored - see `_Adjectives.take`. `knowledge_search` found no single
#: numbered CR rule defining the word (searched this session); the closest
#: confirmed anchor is CR 115.5, "a spell or ability on the stack is an
#: illegal target for itself", which is the same idea for a different kind of
#: self-reference. This is implemented conservatively off the plain English
#: word rather than a rule number that could not be verified.

_CONTROL_CLAUSE = re.compile(
    r"^(?:that\s+)?(you\s+control|you\s+own|you\s+don't\s+control|an\s+opponent\s+controls|"
    r"your\s+opponents\s+control|"
    r"that\s+player\s+or\s+that\s+planeswalker's\s+controller\s+controls|"
    r"that\s+player\s+controls|defending\s+player\s+controls)\b",
    re.IGNORECASE,
)
_ZONE_CLAUSE = re.compile(
    r"\b(?:from|in)\s+"
    r"(?:(?P<whose>your|their|an? opponent'?s?|that player'?s|a single|any single|a|an|any)\s+)?"
    r"(?P<zone>graveyards|graveyard|hands|hand|libraries|library|exile)\b",
    re.IGNORECASE,
)
_ZONES = {
    "graveyard": Zone.GRAVEYARD,
    "graveyards": Zone.GRAVEYARD,
    "hand": Zone.HAND,
    "hands": Zone.HAND,
    "library": Zone.LIBRARY,
    "libraries": Zone.LIBRARY,
    "exile": Zone.EXILE,
}

#: "target creature card exiled with The Darkness Crystal" - CR 201.5's
#: self-reference by printed name, read generically: whatever name follows
#: "exiled with" is never compared against anything, since a permanent's own
#: text can only ever mean itself here (see `TargetRequirement.exiled_with_
#: source`'s own docstring).
_EXILED_WITH_RE = re.compile(r"^exiled with\b", re.IGNORECASE)

#: "other than a/an <quality> card" - Surgical Extraction's own "other than a
#: basic land card" on a bare "target card in a graveyard". `<quality>` is one
#: or two words (a supertype, a card type, or both - "basic land" is both at
#: once), read the same vocabulary `_SUPERTYPE_NOUNS`/`_TYPE_NOUNS` already
#: use for a *leading* adjective, just applied to a *trailing* exclusion
#: clause instead.
_OTHER_THAN_CARD_RE = re.compile(
    r"\bother than (?:a|an)\s+(?P<quality>[a-z]+(?:\s+[a-z]+)?)\s+card\b", re.IGNORECASE
)


def _read_other_than_exclusion(
    tail: str,
) -> tuple[frozenset[Supertype], frozenset[Type]] | None:
    """`_OTHER_THAN_CARD_RE`'s own quality, split into excluded supertypes and
    card types - CR 205.4a's "basic" only ever appears on a land, so "other
    than a basic land card" is correctly read by excluding the supertype
    alone; a hypothetical "other than an artifact card" would exclude the
    card type instead, and either word could appear alone or together.

    Returns `(frozenset(), frozenset())` - a real "no exclusion", not a
    refusal - when `tail` carries no such clause at all. Fails closed
    (`None`) when the clause is attempted but names a quality this wave does
    not recognise, rather than silently admitting a card its own text says
    is excluded.
    """
    match = _OTHER_THAN_CARD_RE.search(tail)
    if match is None:
        return frozenset(), frozenset()
    words = match.group("quality").lower().split()
    supertype_words = [word for word in words if word in _SUPERTYPE_NOUNS]
    type_words = [word for word in words if word in _TYPE_NOUNS]
    if len(supertype_words) + len(type_words) != len(words):
        return None  # a word this parser does not read as either
    if supertype_words and type_words:
        # A compound like "basic land card": excluding *both* the type and
        # the supertype independently would over-exclude (every land, basic
        # or not, once `excluded_card_types` alone contains LAND). CR 205.4a
        # closes "basic" to lands only ("the supertypes are basic,
        # legendary, ongoing, snow, and world", and only a land is ever
        # printed with "Basic" on its type line), so excluding the
        # supertype alone already excludes exactly the compound noun with no
        # separate type exclusion needed. That substitution is not sound for
        # the other four supertypes (a legendary creature, a snow anything,
        # a world enchantment all pair a supertype with a type that is *not*
        # exclusive to it), so anything but "basic" here is refused rather
        # than guessed at.
        if set(supertype_words) != {"basic"}:
            return None
        return frozenset({Supertype.BASIC}), frozenset()
    if supertype_words:
        return frozenset(_SUPERTYPE_NOUNS[word] for word in supertype_words), frozenset()
    return frozenset(), frozenset(_TYPE_NOUNS[word] for word in type_words)


#: Keyed on oracle text alone, not `(card.name, text)`: a card's `Card`
#: instance must never sit inside this cache, because `Card` is
#: `ConfigDict(extra="ignore")` rather than frozen, and a cached instance is
#: shared - unboundedly - across every game the process ever runs. Stamping
#: one game's `Card` into a profile that a later, unrelated game then reads
#: back out would let a mutation in the first game leak into the second.
#: `source_card` is therefore never stored here; `targeting_profile` stamps it
#: onto a fresh copy of the cached profile on every call instead.
_CACHE: dict[str, TargetingProfile] = {}


def targeting_profile(card: Card) -> TargetingProfile:
    """What this card's spell may target. Cached, since oracle text never changes.

    A modal card gets `understood=False`: which targets it requires depends on
    which modes were chosen (CR 700.2c), and that choice has not been made yet.
    Ask `profile_for_modes` once it has.

    An Aura is the one card type whose target is not printed in its text.
    CR 303.4a: "An Aura spell requires a target, **which is defined by its
    enchant ability**." So `Enchant creature` is read as though the card said
    "target creature", which is what CR 702.5a means by "restricts what an Aura
    spell can target".
    """
    # `front_oracle_text`, not `oracle_text`: Scryfall leaves the top-level
    # field null for a `transform`/`modal_dfc` card, which left every such
    # spell (Shatterskull Smashing, Valakut Awakening, Sink into Stupor,
    # Turntimber Symbiosis) with no target requirement read from its text at
    # all - same family as `effect_for`'s fix in `Game.resolve_top`.
    text = card.front_oracle_text
    profile = _CACHE.get(text)
    if profile is None:
        if modal_profile(card):
            profile = TargetingProfile(understood=False)
        elif text and _EARTHBEND.search(_spell_text(text)):
            # Rockalanche prints "Earthbend X, ..." directly as a sorcery's
            # own effect, not as a permanent's triggered ability - the same
            # CR 701.66a keyword `profile_for_text` already special-cases for
            # an ability, needed here too so the spell announces its target
            # at all (CR 601.2c): the word "target" is in the keyword's own
            # rules meaning, never printed on the card, and the ordinary
            # scan below finds nothing to read unless told. Checked against
            # `_spell_text(text)`, not the raw text: Badgermole Cub's own
            # "When this creature enters, earthbend 1." is a *triggered
            # ability's* line (CR 113.1c chooses its target when the ability
            # goes on the stack, not when the creature is cast), and
            # `_spell_text` already strips exactly that kind of line - the
            # bug this line guards against is the *creature spell itself*
            # wrongly demanding a target because the word "earthbend"
            # appears somewhere in its printed text.
            profile = _parse(_EARTHBEND_TARGET_TEXT, spell_only=False)
        elif (kicked_alternative := kicked_instead_target_text(text or "")) is not None:
            # "Choose target creature you own. If this spell was kicked,
            # instead choose any number of target creatures you own." - read
            # unkicked here; `Casting.targeting` and `Game._resolution_profile`
            # read the kicked alternative once a kicker is paid (CR 601.2c).
            profile = _parse(kicked_alternative[0])
        else:
            profile = _parse(text)
            profile = _with_aura_target(card, profile)
        _CACHE[text] = profile
    # Stamped here, on every call, rather than baked into the cached entry:
    # this is the card whose qualities CR 702.16b compares against a
    # protected target, and it must be *this* call's `card`, never whichever
    # game's `Card` happened to populate the cache first.
    return profile.model_copy(update={"source_card": card})


#: "Choose `<target phrase>`. If this spell was kicked, instead choose
#: `<target phrase>`." - The Eagles Are Coming!: CR 601.2c's "A spell may
#: require some targets only if an alternative or additional cost (such as a
#: kicker cost) ... is paid" - the kicked spell's targets replace the
#: unkicked ones (CR 614.1a's "instead"), rather than adding to them.
_KICKED_INSTEAD_TARGETS_RE = re.compile(
    r"^(?:kicker [^\n]*\n)?choose (?P<base>[^.\n]*\btargets?\b[^.\n]*)\.\s*"
    r"if this spell was kicked, instead choose (?P<kicked>[^.\n]*\btargets?\b[^.\n]*)\.",
    re.IGNORECASE,
)


def kicked_instead_target_text(text: str) -> tuple[str, str] | None:
    """The unkicked and kicked "choose ..." sentences of a spell whose kicker
    changes which targets it chooses (`_KICKED_INSTEAD_TARGETS_RE`), each
    written as its own sentence for `profile_for_text`, or `None`."""
    match = _KICKED_INSTEAD_TARGETS_RE.search(text.strip())
    if match is None:
        return None
    return f"choose {match.group('base')}.", f"choose {match.group('kicked')}."


def _with_aura_target(card: Card, profile: TargetingProfile) -> TargetingProfile:
    """CR 303.4a: an Aura spell's target comes from its enchant ability.

    Prepended rather than appended, because the enchant target is the Aura
    spell's first and usually only one - and an Aura whose text also says
    "target" keeps that requirement after it.

    A card that is not an Aura, or whose enchant restriction the parser cannot
    read, is left exactly as it was.
    """
    if "Aura" not in card.subtypes:
        return profile
    restrictions = [
        (ability.parameter or "").strip()
        for ability in keyword_abilities(card)
        if ability.canonical.lower() == "enchant" and (ability.parameter or "").strip()
    ]
    added: list[TargetRequirement] = []
    for restriction in restrictions:
        read = _parse(f"target {restriction}")
        if not read.understood or not read.requirements:
            return TargetingProfile(understood=False)
        added.extend(read.requirements)
    if not added:
        return profile
    return TargetingProfile(
        requirements=(*added, *profile.requirements),
        understood=profile.understood,
        division=profile.division,
    )


def profile_for_modes(
    card: Card,
    chosen: Sequence[int | str | Mode],
    x_value: int | None = None,
) -> TargetingProfile:
    """What a modal card may target, given the modes its caster chose.

    CR 700.2c: only the chosen modes contribute targets. Each chosen mode is
    read on its own and the requirements are concatenated in the order the
    modes were announced, so Kozilek's Command choosing "target player scries
    X" and "exile target creature" asks for one player and one creature and
    nothing else.

    A mode chosen twice, where the card allows that (CR 700.2d), contributes
    its targets twice - each instance of the mode chooses its own.

    `x_value` is the value the caster announced for X (CR 107.3a). Without it,
    a mode whose target count is X cannot be counted and the whole profile is
    left unchecked.

    Raises if the card is not modal; there is nothing to derive from.

    See `profile_for_modes_with_owners` for the same profile plus which chosen
    mode instance each requirement came from - what per-mode target slicing
    needs and this function does not itself track.
    """
    profile, _owners = profile_for_modes_with_owners(card, chosen, x_value)
    return profile


def profile_for_modes_with_owners(
    card: Card,
    chosen: Sequence[int | str | Mode],
    x_value: int | None = None,
) -> tuple[TargetingProfile, list[int]]:
    """`profile_for_modes`, plus a same-length list saying which 0-based
    position in `chosen` each entry of `profile.requirements` came from.

    CR 700.2f: "Modal spells and abilities may have different targeting
    requirements for each mode." A caster announcing targets for several
    modes at once hands `Casting.choose_targets` one flat list with no record
    of which target was meant for which mode - `TargetingProfile.assign_to_owners`
    is what turns that flat list back into one bucket per mode, and it needs
    this `owners` list to know where each requirement's slot came from.
    """
    modal = modal_profile(card)
    if modal is None:
        raise ValueError(f"{card.name} is not a modal card")

    modes = [modal.mode(spec) for spec in chosen]
    requirements: list[TargetRequirement] = []
    owners: list[int] = []
    understood = modal.understood
    division: Division | None = None
    for index, mode in enumerate(modes):
        parsed = _parse(mode_rules_text(mode, x_value))
        requirements.extend(parsed.requirements)
        owners.extend([index] * len(parsed.requirements))
        understood = understood and parsed.understood
        if parsed.division is not None:
            # Two modes each dividing something would need a division apiece;
            # no card in the pool does it, so refuse rather than guess.
            division = parsed.division if division is None else None
    profile = TargetingProfile(
        requirements=tuple(requirements),
        understood=understood,
        division=division,
        source_card=card,
    )
    return profile, owners


#: CR 701.66a: "Earthbend N" means "Target land you control becomes a 0/0
#: land creature ..." - the word "target" is in the keyword's own *meaning*,
#: never in what a card actually prints ("Earthbend 1.", no reminder text
#: required - Bumi, Unleashed prints exactly that with none at all). The
#: ordinary word-scan below finds nothing to read unless it is told, once,
#: what the rule itself already says the target is.
#:
#: The *instruction* only - "earthbend" followed by its N or X. The bare verb
#: in a trigger condition (Avatar Aang's "Whenever you waterbend, earthbend,
#: firebend, or airbend, draw a card.") names the action as an event (CR
#: 701.66b) and targets nothing; reading it as the instruction used to make
#: that draw trigger demand "target land you control", so it was removed
#: from the stack (CR 603.3d) whenever its controller had no land.
_EARTHBEND = re.compile(r"\bearthbend (?:\d+|x)\b", re.IGNORECASE)
_EARTHBEND_TARGET_TEXT = "target land you control"

#: "up to one target nonland card of each card type from your graveyard" -
#: Uldaros Theorix's own ETB. CR 601.2c's "an appropriate object ... for each
#: target the spell requires" reads "of each card type" as one independent
#: "up to one" requirement *per* CR 300.1 nonland card type, not a single
#: requirement the ordinary word-scan below could express: the scan reads one
#: "target ..." noun phrase into one `TargetRequirement`, and there is no
#: single set of restrictions ("card_types={...}") that would enforce "no two
#: chosen targets share a type" the way eight separate up-to-one slots do for
#: free (CR 115.3 only ever compares targets *within* one requirement).
#: Special-cased the same way Earthbend is, just above, rather than widening
#: the scan to a shape nothing else in the pool needs.
_UP_TO_ONE_OF_EACH_CARD_TYPE_RE = re.compile(
    r"up to one target nonland card of each card type from your graveyard", re.IGNORECASE
)
#: CR 300.1's card types, minus land (the clause's own "nonland") and the
#: substitute-deck-only types (Conspiracy, Dungeon, Phenomenon, Plane,
#: Scheme, Vanguard) that never occupy an ordinary graveyard slot - the same
#: restriction to real, `Type`-modelled card types every other "nonland
#: card" reader in this engine already applies.
_NONLAND_CARD_TYPES: tuple[Type, ...] = tuple(t for t in Type if t is not Type.LAND)


def _up_to_one_of_each_card_type_profile() -> TargetingProfile:
    """`_UP_TO_ONE_OF_EACH_CARD_TYPE_RE`'s shape, built directly rather than
    through `_parse`'s own text scan: one "up to one" requirement per
    `_NONLAND_CARD_TYPES` member, each restricted to a card in the caster's
    own graveyard (CR 109.4/CR 108.4a's owner fallback, via `ControllerRestriction.YOU`)
    of that one type. A type with no candidate card at announcement offers no
    legal target for its own requirement and simply goes unfilled (CR 115.6's
    "up to one" already allows zero), which is what lets this profile stay
    fixed rather than depending on the graveyard's live contents.
    """
    requirements = tuple(
        TargetRequirement(
            phrase=f"up to one target nonland {card_type.value} card from your graveyard",
            count=1,
            minimum=0,
            card_types=frozenset({card_type}),
            allows_cards=True,
            allows_players=False,
            zones=frozenset({Zone.GRAVEYARD}),
            controller=ControllerRestriction.YOU,
        )
        for card_type in _NONLAND_CARD_TYPES
    )
    return TargetingProfile(requirements=requirements, understood=True)


#: CR 603.12's own wording - "checked immediately after being created" - is
#: what draws the line: everything from "when you do" onward is a *second*
#: triggered ability's text, not the one being profiled. Cut before the
#: ordinary scan sees it, so a reflexive clause's own "target creature or
#: planeswalker" (Grist, the Hunger Tide's "-2") is never read as the outer
#: ability's target. `re.IGNORECASE | re.DOTALL` matches `_REFLEXIVE_CLAUSE_RE`
#: in `machines/effects.py`: the two have to agree on where the boundary is,
#: or one module could see a target the other has already sliced away.
#:
#: CR 603.12's other template - "when [something happens] this way," - is the
#: same cut for the same reason: Agatha's Soul Cauldron's "Exile target card
#: from a graveyard. When a creature card is exiled this way, put a +1/+1
#: counter on target creature you control." announces only the first
#: sentence's target now; the second belongs to the reflexive ability CR
#: 603.3d creates later. `machines/effects.py`'s own
#: `_EXILE_TARGET_REFLEXIVE_CREATURE_RE` has to agree on this same boundary.
_REFLEXIVE_CLAUSE_TAIL = re.compile(
    r"\bwhen you do,.*$|\bwhen [^,]+ this way,.*$", re.IGNORECASE | re.DOTALL
)

#: The same two CR 603.12 templates as `_REFLEXIVE_CLAUSE_TAIL`, but capturing
#: what comes *after* the comma instead of cutting it - the reflexively
#: created ability's own words, read by `reflexive_consequence_text` below.
_REFLEXIVE_CLAUSE_CONSEQUENCE_RE = re.compile(
    r"\bwhen you do,\s*(?P<consequence>.*)$|\bwhen [^,]+ this way,\s*(?P<consequence2>.*)$",
    re.IGNORECASE | re.DOTALL,
)

#: "For each opponent, `<verb phrase>` [up to one] target `<description>`
#: that player/opponent controls[, ...]." - Hapatra, the Desert Frost's,
#: Hapatra, the Desert Fang's, Lich's Relic's own reflexive consequence and
#: Frenzied Gorespawn's goad, all sharing this one grammar. CR 601.2c/603.3d
#: target *every* instance of the word "target" a spell or ability's text
#: prints, and "for each opponent" prints one such instance per opponent (CR
#: 102.3's "opponents are all players not on their team" - not fixed at two),
#: which the ordinary word-scan below cannot express: it reads one
#: `TargetRequirement` per literal "target" word in the text, and this
#: sentence prints only one such word regardless of how many opponents there
#: are. Special-cased ahead of that scan the same way
#: `_EARTHBEND` already is, for the identical reason - the rule itself,
#: not the sentence's own count words, is what says how many targets this
#: asks for.
_FOR_EACH_OPPONENT_TARGET_RE = re.compile(
    r"for each opponent,[^.]*?\b(?P<up_to>up to one )?target (?P<desc>[^.]+?) "
    r"that (?:player|opponent) controls\b",
    re.IGNORECASE | re.DOTALL,
)


def reflexive_consequence_text(text: str) -> str | None:
    """CR 603.12's "`<action>`. When you do, `<consequence>`." (or "... this
    way, `<consequence>`.") - the reflexive ability's own words, or `None`
    when `text` prints neither shape.

    `profile_for_text` deliberately cuts this tail away, because CR 603.3d
    has the *reflexive* ability - not the one whose text this is - choose its
    own target once it is created and put on the stack, a separate CR 601.2c
    announcement from the outer trigger's. That correctly keeps the outer
    trigger's own `TargetingProfile` from claiming a target that belongs to
    an ability which does not exist yet. It also means a caller that wants
    the reflexive ability's *own* targeting shape - `Game.
    why_cannot_target_with_trigger`, so a scenario can pre-declare what CR
    603.12 reflexively creates for Earthbender Ascension's own Landfall
    ("... put a quest counter on this enchantment. When you do, if it has
    four or more quest counters on it, put a +1/+1 counter on target creature
    you control.") - needs the tail `profile_for_text` throws away, read back
    out here instead of re-deriving the same cut twice.
    """
    match = _REFLEXIVE_CLAUSE_CONSEQUENCE_RE.search(text)
    if match is None:
        return None
    consequence = match.group("consequence") or match.group("consequence2") or ""
    return consequence.strip()


def _for_each_opponent_profile(text: str) -> TargetingProfile | None:
    """`_FOR_EACH_OPPONENT_TARGET_RE`'s shape, or `None` if this is not it.

    One target per opponent, each independently optional (CR 115.6's "up to
    one") - not a fixed count `TargetRequirement.count` can hold, since the
    number of opponents is game state `profile_for_text` cannot see (it
    reads text alone). `unbounded=True` (CR 107.1c's own "no stated
    maximum" shape) covers any player count without needing to know it in
    advance, and `distinct_controllers=True` is what stops two of those
    unbounded slots from being filled by the same opponent's own two
    permanents instead of two different opponents' one each - the
    per-target legality check (`controller=OPPONENT`) and the cross-target
    one already exist for Run Away Together's "controlled by different
    players"; this reuses both rather than inventing a per-opponent-count
    mechanism of its own.
    """
    match = _FOR_EACH_OPPONENT_TARGET_RE.search(text)
    if match is None:
        return None
    description = match.group("desc").strip()
    base = permanent_description(description)
    if base is None:
        return None
    mandatory = match.group("up_to") is None
    requirement = base.model_copy(
        update={
            "phrase": f"target {description} an opponent controls",
            "count": 0,
            "minimum": 1 if mandatory else 0,
            "unbounded": True,
            "distinct_controllers": True,
            "one_per_opponent": mandatory,
            "controller": ControllerRestriction.OPPONENT,
        }
    )
    return TargetingProfile(requirements=(requirement,))


def profile_for_text(text: str) -> TargetingProfile:
    """What one piece of rules text may target, read on its own (CR 115.1).

    `targeting_profile` answers for a *spell*, so it drops the lines that belong
    to a triggered or activated ability - those choose their own targets when
    they go on the stack rather than when the permanent is cast (CR 113.1c makes
    such an ability its own object). This is the way in for that text: hand it
    the ability's own words and it reads them whole.

    Tishana's Tidebinder's "counter up to one target activated or triggered
    ability" is the case that needs it.

    Earthbend is special-cased ahead of the ordinary scan: every call site that
    needs a targeted ability's restriction - `Game._ask_trigger_targets` (CR
    601.2c's announcement), `Game.why_cannot_target_with_trigger`,
    `Game.resolve_target`'s CR 608.2b recheck, and `Game.activate_ability`'s
    own CR 602.2b announcement - funnels through this one function, so
    teaching it here is what makes "Earthbend N" targetable at every one of
    those without three separate patches. The reflexive-clause cut just below
    rides the same funnel: a card whose text reads "you may `<action>`. When
    you do, `<consequence with a target>`." (CR 603.12, Grist, the Hunger
    Tide's "-2") is announcing *no* target of its own at all - the target
    belongs to the reflexive ability CR 603.12 creates only once the action
    has happened, and CR 603.3d chooses it when *that* ability goes on the
    stack, not now. Before this cut, Guide of Souls' "Whenever you attack, you
    may pay {E}{E}{E}. When you do, put two +1/+1 counters ... on target
    attacking creature" had its reflexive target harvested onto the outer
    "Whenever you attack" trigger instead: CR 608.2b's recheck then applied to
    the wrong ability, so the outer trigger could fizzle over a target it
    never legitimately had, and the {E}{E}{E} offer it was gating would never
    even be reached.
    """
    text = _REFLEXIVE_CLAUSE_TAIL.sub("", text)
    if _EARTHBEND.search(text):
        return _parse(_EARTHBEND_TARGET_TEXT, spell_only=False)
    if _UP_TO_ONE_OF_EACH_CARD_TYPE_RE.search(text):
        return _up_to_one_of_each_card_type_profile()
    for_each_opponent = _for_each_opponent_profile(text)
    if for_each_opponent is not None:
        return for_each_opponent
    return _parse(_REMINDER.sub("", text), spell_only=False)


def targeting_trigger_text(card: Card) -> str | None:
    """The first printed triggered ability on `card` whose own words target
    something, or `None` when it has none.

    A spell can have `targeting_profile(card).max_targets == 0` - no target
    of its own - and still print a triggered ability that targets: Ulamog,
    the Ceaseless Hunger's cast trigger ("When you cast this spell, exile two
    target permanents.") and Ravenous Chupacabra's enters-the-battlefield
    trigger ("When this creature enters, destroy target creature an opponent
    controls.") are both this shape. CR 115.1d: that ability's own target(s)
    "are chosen as the ability is put on the stack; see rule 603.3d" - a
    separate CR 601.2c-shaped announcement from the spell's, made later, once
    the trigger is actually on the stack (CR 603.3/603.3d). `Casting.
    _check_targets` asks this so it can refuse inline targets offered at cast
    time with that real reason instead of the bare "too many targets" CR
    601.2c already gives a spell with no targets of its own.

    Reads exactly the abilities `Game.why_cannot_target_with_trigger` reads:
    every printed `TriggeredAbility` (`parse_abilities` - the parser this
    module already asks about via `targeting_profile`'s `_spell_text` cut),
    plus CR 702's keyword-shorthand triggers (`keyword_triggered_abilities`;
    "Partner with" is the pool's example), each asked through this module's
    own `profile_for_text` - the same reading `why_cannot_target_with_trigger`
    checks a scripted target against, so "has a targeting trigger" here means
    exactly what "the trigger would accept a target" means there. A trigger
    that parses but requires none (a plain "when you cast this spell, draw a
    card" cantrip clause) is not a targeting trigger and is skipped; a card
    printing several targeting triggers returns the first one.
    """
    printed = [
        ability for ability in parse_abilities(card) if isinstance(ability, TriggeredAbility)
    ] + keyword_triggered_abilities(card)
    for ability in printed:
        profile = profile_for_text(ability.text)
        if profile.understood and profile.requirements:
            return ability.text
    return None


#: CR 207.2c's ability word, or CR 207.2d's flavor word, as Scryfall prints
#: it: a short capitalised phrase and an em dash in front of the real ability.
#: Both "have no special rules meaning", so they are cut before the line is
#: judged. Bounded to a few words so a sentence that merely contains an em
#: dash is left alone.
_ABILITY_WORD_PREFIX = re.compile(r"^[A-Z][^—\n]{0,40}?\s+—\s+")

#: CR 714.2's own chapter symbol: "{rN1}, {rN2}—[Effect]" (CR 714.2c),
#: written out by Scryfall as one or more Roman numerals (CR 714.2a: "the
#: numeral I represents 1, II represents 2, III represents 3, and so on"),
#: comma-joined when a Saga shares one chapter ability across several
#: numbers, then an em dash. "A chapter symbol is a keyword ability that
#: represents a triggered ability" (CR 714.2), so an entire chapter line is
#: excluded the same way a printed "When ..."/"Whenever ..."/"At ..." line
#: already is below - unlike `_ABILITY_WORD_PREFIX`, which only strips its
#: own prefix off a line the rest of which stays in the spell's own text,
#: since an ability word never turns the sentence after it into a separate
#: object with its own targets the way a chapter ability does (CR 603.3d: a
#: chapter ability, like any triggered ability, chooses its own targets
#: when it goes on the stack, not when the Saga is cast). Bounded to four
#: Roman-numeral characters per number so an ordinary capitalised word
#: before a real em dash is never mistaken for one.
_CHAPTER_SYMBOL_LINE = re.compile(r"^[IVX]{1,4}(?:,\s*[IVX]{1,4})*\s*—")


def _spell_text(oracle_text: str) -> str:
    """The lines that are part of casting the spell, not of an ability.

    A triggered or activated ability on a permanent chooses its own targets
    when it goes on the stack, not when the permanent is cast, so those lines
    are dropped before anything is parsed.
    """
    lines: list[str] = []
    for line in oracle_text.splitlines():
        stripped = _REMINDER.sub("", line).strip()
        if _CHAPTER_SYMBOL_LINE.match(stripped):
            continue
        # CR 207.2c: "An ability word appears in italics at the beginning of
        # some abilities ... they have no special rules meaning", and CR 207.2d
        # says the same of a flavor word. Scryfall prints both as "<Word> — "
        # in front of the ability, which hid the "When" from the trigger test
        # below: Mister Negative's "Darkforce Inversion — When Mister Negative
        # enters, you may exchange life totals with target opponent" survived
        # into the *spell's* profile, so a plain creature spell looked like it
        # required a target.
        # Only for the test below - the line itself is kept whole, because
        # `_read_revolt_mana_value_override` matches on "Revolt — ..." and
        # would lose Fatal Push's wider number if the word were cut here.
        without_word = _ABILITY_WORD_PREFIX.sub("", stripped)
        # A colon inside a quoted grant is the *token's* activated ability
        # (CR 111.3), not this line's own cost - Spawning Breath's "deals 1
        # damage to any target. Create a 0/1 ... token. It has "Sacrifice
        # this token: Add {C}."" is still the spell's own line.
        if not stripped or ":" in _QUOTED_SPAN.sub("", stripped) or _TRIGGER.match(without_word):
            continue
        lines.append(stripped)
    return "\n".join(lines)


#: Revolt (an ability word, CR 207.2c) printed as its own paragraph after the
#: base clause - Fatal Push's "Revolt — Destroy that creature if it has mana
#: value 4 or less instead if a permanent left the battlefield under your
#: control this turn." Read generically off the text shape, not off this
#: card's name: any card printing the same "Revolt — <verb> that <noun> if it
#: has mana value N or less instead if a permanent left the battlefield under
#: your control this turn." paragraph gets the same wider number substituted
#: in when `TargetRequirement.comparison_value_if_revolt` fires.
_REVOLT_MANA_VALUE_OVERRIDE_RE = re.compile(
    r"revolt\s*[—-]\s*.*?mana value (?P<n>\d+) or less instead if a permanent "
    r"left the battlefield under your control this turn\.?",
    re.IGNORECASE | re.DOTALL,
)


def _read_revolt_mana_value_override(text: str) -> int | None:
    """The wider mana-value number a card's own Revolt paragraph names, or
    `None` if it prints no such paragraph at all."""
    match = _REVOLT_MANA_VALUE_OVERRIDE_RE.search(text)
    return None if match is None else int(match.group("n"))


def spell_profile_for_text(text: str, card: Card | None = None) -> TargetingProfile:
    """What a *spell* whose text has already been rewritten may target.

    `targeting_profile` is the normal way in, but it takes a `Card` and so
    always reads the printed text. A spell with `{X}` in its mana cost has to
    be read with X already substituted (CR 107.3a: X is announced at
    CR 601.2b, before targets at CR 601.2c, so it is always known by then),
    and that rewritten text has no `Card` to hang off.

    Distinct from `profile_for_text`, which reads text *whole* because its job
    is one ability's own words. A spell must drop the lines belonging to its
    triggered and activated abilities - CR 113.1c makes such an ability its
    own object, choosing its own targets when it goes on the stack, not when
    the permanent is cast. Walking Ballista is the card that proves it: its
    "It deals 1 damage to any target" is an activated ability, and reading the
    card whole made the *creature spell* look like it required a target.
    """
    profile = _parse(text, spell_only=True)
    if card is not None:
        profile = _with_aura_target(card, profile)
        # CR 702.16b compares a protected target against the source card's
        # qualities, so the profile has to carry it - `targeting_profile`
        # stamps this on every branch and this path was losing it.
        profile = profile.model_copy(update={"source_card": card})
    return profile


#: "If the gift was promised, instead return target nonland permanent an
#: opponent controls to its owner's hand." (Into the Flood Maw) - CR 702.174k's
#: "promised" and CR 702.174m's "the spell's controller chooses those targets
#: only if the gift was promised". Read generically off the keyword's own
#: template wording, not off this printing's name: any future gift card
#: whose replacement clause uses the same "If the gift was promised, instead
#: ..." shape is read the same way. Spans from the trigger phrase to the
#: next sentence boundary (or the end of the text), the same "cut to the next
#: `.`/`;`" convention `_read_phrase`'s own `span` slicing already uses -
#: which is how `_parse` tells a "target" inside this clause apart from an
#: ordinary second requirement.
_GIFT_PROMISED_INSTEAD_CLAUSE = re.compile(
    r"\bif the gift was promised,\s*instead\b.*?(?=[.;]|$)", re.IGNORECASE | re.DOTALL
)


def _parse(oracle_text: str, spell_only: bool = True) -> TargetingProfile:
    text = _spell_text(oracle_text) if spell_only else oracle_text
    text = _QUOTED_SPAN.sub("", text)
    text = _RETARGETING.sub("", text)
    text = _THAT_TARGETS_VERB_RE.sub(f"that {_THAT_TARGETS_MARKER}", text)
    text = _SELF_COST_REDUCTION_LINE.sub("", text)
    text = _COST_INCREASE_PER_TARGET_LINE.sub("", text)
    text = _COPY_TARGETS_DECLARATION.sub("", text)
    text = _TARGETS_ONLY_SINGLE_CREATURE_CONDITION_CLAUSE.sub("", text)
    text = _SINGLE_TARGET_RESTRICTION.sub(_SINGLE_TARGET_PLACEHOLDER, text)
    mentions = len(_TARGET_WORD.findall(text))
    if not mentions:
        return TargetingProfile()

    revolt_override = _read_revolt_mana_value_override(text)
    division = _read_division(text)
    requirements: list[TargetRequirement] = []
    any_targets = len(_ANY_TARGET.findall(text))
    requirements.extend(
        TargetRequirement(
            phrase="any target",
            card_types=ANY_TARGET_TYPES,
            allows_players=True,
        )
        for _ in range(any_targets)
    )
    text = _ANY_TARGET.sub(_PLACEHOLDER, text)
    if any_targets:
        # CR 115.4's paired idiom (Boulder Dash, Arc Trail): a plain "any
        # target" already matched above, so a further "any other target" in
        # this same text is the same bare shape again, naming a *different*
        # object than what "any target" already named - not, as a solitary
        # "any other target" always means elsewhere (`_ANY_OTHER_TARGET`'s
        # own docstring), a source exclusion. Read here, ahead of the
        # generic `_TARGET_WORD` scan below, so it never falls into
        # `_read_phrase`'s `excludes_source` reading - the wrong mechanism
        # for a spell, which is never a legal target of its own damage to
        # begin with.
        other_targets = len(_ANY_OTHER_TARGET.findall(text))
        requirements.extend(
            TargetRequirement(
                phrase="any other target",
                card_types=ANY_TARGET_TYPES,
                allows_players=True,
                distinct_from_prior_requirement=True,
            )
            for _ in range(other_targets)
        )
        text = _ANY_OTHER_TARGET.sub(_PLACEHOLDER, text)
    promised_spans = [match.span() for match in _GIFT_PROMISED_INSTEAD_CLAUSE.finditer(text)]

    scan = list(_TARGET_WORD.finditer(text))
    for position, match in enumerate(scan):
        # Each "target" is read on its own, so "target creature and target
        # land" is two requirements rather than one confused one.
        requirement = _read_phrase(text[: match.start()], text[match.end() :])
        if requirement is None:
            return TargetingProfile(requirements=tuple(requirements), understood=False)
        # CR 115.9a's "with a single target" belongs to the requirement it was
        # printed after, and nothing further along: the span searched stops at
        # the next "target" word and at the end of the sentence, so a second
        # requirement in the same sentence never inherits the first one's
        # restriction.
        span_end = scan[position + 1].start() if position + 1 < len(scan) else len(text)
        span = re.split(r"[.;]", text[match.end() : span_end])[0]
        if _SINGLE_TARGET_PLACEHOLDER in span:
            requirement = requirement.model_copy(update={"required_target_count": 1})
        if (
            revolt_override is not None
            and requirement.comparison_attribute is ComparisonAttribute.MANA_VALUE
            and requirement.comparison_operator is ComparisonOperator.LESS_OR_EQUAL
        ):
            requirement = requirement.model_copy(
                update={"comparison_value_if_revolt": revolt_override}
            )
        # CR 702.174m: a "target" inside a "if the gift was promised, instead
        # ..." clause is not a second requirement of the spell's own - it is
        # what the *previous* requirement's own slot asks for instead, once
        # the gift was promised (`TargetRequirement.if_gift_promised`,
        # `TargetingProfile.for_gift_promise`). Attached to whichever
        # requirement was read immediately before it; a promised clause with
        # nothing preceding it (none in the pool today) has nothing to attach
        # to and is dropped, the same way an unreadable phrase elsewhere
        # fails rather than guesses.
        if any(start <= match.start() < end for start, end in promised_spans):
            if requirements:
                requirements[-1] = requirements[-1].model_copy(
                    update={"if_gift_promised": requirement}
                )
            continue
        requirements.append(requirement)

    return TargetingProfile(requirements=tuple(requirements), division=division)


#: Shatterskull Smashing's second sentence: "If X is 6 or more, [Name] deals
#: twice X damage divided as you choose among them instead." Generalised on
#: the threshold and card name, not keyed to this one printing - any future
#: card phrasing the identical doubling condition reads the same way.
_DOUBLED_IF_X_AT_LEAST_RE = re.compile(
    r"\bif x is (?P<threshold>\d+) or more\b[^.]*\btwice x\b", re.IGNORECASE | re.DOTALL
)


def _read_division(text: str) -> Division | None:
    """The effect this text divides among its targets, if any (CR 601.2d).

    "Electrolyze deals 2 damage divided as you choose among one or two targets"
    and "Distribute two +1/+1 counters among one or two target creatures" are
    the two fixed-amount shapes; both put the amount before the word "among"
    and the targets after it. A third shape has no fixed amount at all -
    Shatterskull Smashing's "deals X damage divided as you choose among up to
    two target creatures and/or planeswalkers" - CR 107.3a's X, not resolved
    until the caster announces it as part of the same casting (`Division.
    amount` is `None` for this one), optionally doubled by a second sentence
    `_DOUBLED_IF_X_AT_LEAST_RE` reads off the same whole text.
    """
    match = _DIVIDED.search(text)
    if match is None:
        return None
    if match.group("damage") is not None:
        word = match.group("damage").lower()
        if word == "x":
            doubled = _DOUBLED_IF_X_AT_LEAST_RE.search(text)
            threshold = int(doubled.group("threshold")) if doubled else None
            return Division(amount=None, what="damage", doubled_if_x_at_least=threshold)
        amount = parse_count(word)
        return None if amount is None else Division(amount=amount, what="damage")
    amount = parse_count(match.group("counters").lower())
    if amount is None:
        return None
    return Division(amount=amount, what=f"{match.group('kind')} counters")


def _read_count(prefix: str) -> tuple[int, int | None, bool] | None:
    """How many targets this "target" asks for, as (fewest, most, variable).

    A most of None means there is no maximum. `variable` is True when the count
    is an X that has not been announced yet. None instead of a triple means the
    parser could not read the count at all.

    - "target creature" is exactly one.
    - "up to three target creatures" is nought to three (CR 115.6).
    - "one or two target creatures" is one or two - Abzan Charm and Electrolyze
      both word their division that way, and CR 601.2d then makes each chosen
      target take at least one share.
    - "any number of target players' graveyards" is nought upwards: CR 107.1c,
      "if a rule or ability instructs a player to choose 'any number,' that
      player may choose any positive number or zero".

    Digits are read as well as words, because a mode's X is substituted before
    it is parsed: "up to X target cards" becomes "up to 2 target cards" once
    the caster has announced X (CR 107.3a).

    An X still standing is not a failure to read the text - the text is clear,
    the value simply is not chosen yet. CR 107.3 makes X "a placeholder for a
    number that needs to be determined" and CR 601.2b determines it one step
    before CR 601.2c announces the targets, so the count is left wide open
    rather than the phrase left unread: nought targets to no maximum, with
    `variable` saying why.

    "another"/"other" ("up to one **other** target creature") sit between the
    count and the word "target" itself, so they are dropped before the last
    three words are read - otherwise "up to one other" reads as the fixed
    count "other", which is not a number, and the whole phrase falls back to
    a mandatory exactly-one. `_excludes_source` is what actually reads the
    word; this function only has to stop it from breaking the count.

    "one, two, or three target creatures" - Arc Lightning, Inferno Titan, and
    21 other Modern cards CR 601.2d divides this way - is a longer list than
    the two-number "one or two" shape above, read by `_read_numeric_list`
    over every word, not just the last three: a version of this reader that
    only looked at the tail end used to read "two, or three" out of the full
    list and silently drop the leading "one", pinning the floor at two
    instead of one (Arc Lightning could not legally be cast at a single
    target even though the card's own text lists "one" first).

    `prefix` is everything before this "target", which for an activated or
    loyalty ability still carries its own printed cost - Liliana of the
    Veil's own "-2: Target player sacrifices a creature." (CR 118 costs
    never contain the word "target", so nothing is lost by cutting them
    off). A cost's number is not a target count: CR 601.2b pays or
    announces the cost, CR 601.2c chooses targets, two different questions
    that happen to share one sentence purely by how the card is printed.
    Trimmed to the text after the last cost-terminating colon (or the last
    sentence break) before tokenizing, so "-3: Target creature ..." and
    "{3}: Target creature ..." both read the plain, unmarked "target
    creature" as CR 115.1's own default of exactly one, the same as a "{T}:"
    or "{1}{U}:" cost already did by accident (a non-numeric trailing token
    such as "t" used to push the cost's own digit out of the scan's last
    three words) - this makes that safe by construction instead of by luck.
    """
    boundary = max(prefix.rfind(":"), prefix.rfind("."), prefix.rfind(";"))
    if boundary != -1:
        prefix = prefix[boundary + 1 :]
    all_words = [w for w in re.findall(r"[\w'-]+", prefix.lower()) if w not in _SOURCE_EXCLUDING]
    words = all_words[-3:]
    if words[-3:] == ["any", "number", "of"]:
        return 0, None, False
    if len(words) >= 3 and words[-3] == "up" and words[-2] == "to":
        if words[-1] == "x":
            return 0, None, True
        count = parse_count(words[-1])
        return None if count is None else (0, count, False)
    numeric_list = _read_numeric_list(all_words)
    if numeric_list is not None:
        fewest, most = numeric_list
        return fewest, most, False
    if words and words[-1] == "x":
        return 0, None, True
    if words and words[-1] not in {"a", "an"} and (count := parse_count(words[-1])) is not None:
        return count, count, False
    return 1, 1, False


def _read_numeric_list(words: list[str]) -> tuple[int, int] | None:
    """The count list at the very end of `words` - "one, two, or three"
    (commas are not word characters, so `re.findall(r"[\\w'-]+", ...)`
    already tokenizes that as `["one", "two", "or", "three"]` with no comma
    of its own to read) or the plain two-item "one or two" - as (fewest,
    most).

    CR 601.2d always prints a division's choices in ascending order, so the
    first number in the list is the floor and the last is the ceiling. Reads
    backward from the word right before a trailing "or" (or the Oxford
    "and/or", which tokenizes as the two words "and", "or"), consuming
    countable words one at a time and stopping at the first word that is not
    one - which is what lets this run against the *whole* prefix rather than
    a fixed-width window: whatever sits further back (an "among", a verb, an
    unrelated word) simply is not a count and ends the scan on its own.

    `None` when the end of `words` is not at least two counts joined by
    "or"/"and or" - a single trailing count, or a phrase that happens to end
    in an unrelated "... or <something>" that is not itself a number.
    """
    if len(words) < 3 or words[-2] != "or":
        return None
    last = parse_count(words[-1])
    if last is None:
        return None
    index = len(words) - 3
    if index >= 0 and words[index] == "and":
        index -= 1
    counts = [last]
    while index >= 0 and (count := parse_count(words[index])) is not None:
        counts.append(count)
        index -= 1
    if len(counts) < 2:
        return None
    fewest, most = counts[-1], counts[0]
    return (fewest, most) if fewest <= most else None


#: "up to one **other** target creature", "exile **another** target permanent":
#: both sit right before the word "target", in `_read_phrase`'s `prefix`, not
#: after it - real WOTC templates never write "target other creature".
_SOURCE_EXCLUDING = frozenset({"other", "another"})


def _excludes_source(prefix: str) -> bool:
    """Whether this "target ..." phrase excludes the ability's own source.

    "other"/"another" is read off the plain word immediately before "target" -
    see `_SOURCE_EXCLUDING`'s note and `TargetRequirement.excludes_source` for
    why no single CR number backs this rather than a rule citation.
    """
    words = re.findall(r"[\w'-]+", prefix.lower())
    return bool(words) and words[-1] in _SOURCE_EXCLUDING


#: A single CR 205.3m creature-type word, capitalized the way Oracle text
#: always capitalizes a subtype - never a plain English noun mid-sentence, so
#: this is what tells "Vampire" apart from a word this parser already reads
#: some other way.
#: The hyphen is not decoration: CR 205.3m's creature-type list is where
#: "Assembly-Worker" lives, and Mishra's Factory's "Target Assembly-Worker
#: creature gets +1/+1 until end of turn" was the pool's last unreadable
#: targeting phrase because this pattern stopped at the hyphen. Each
#: hyphenated part is capitalized the same way, which is what keeps an
#: ordinary hyphenated English word out.
_SUBTYPE_WORD_RE = re.compile(r"^[A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*$")


def _is_bare_subtype_word(raw: str, lowered: str) -> bool:
    """Whether one word, as originally capitalized, is a CR 205.3m creature
    type standing in for the elided noun "creature" - the single-item case
    `_read_subtype_list`'s own docstring says is deliberately left to the
    caller below, now that Aeronaut Cavalry's "another target Soldier you
    control" needs it. A real English noun is never capitalized mid-sentence,
    so `_SUBTYPE_WORD_RE`'s shape plus absence from every noun/adjective
    vocabulary this parser already reads (`_ALL_NOUNS`, `_SUPERTYPE_NOUNS`,
    `_COLOR_WORDS`) is what tells a bare subtype apart from an ordinary noun.

    CR 305.6's five basic land types are excluded on top - "target Forest"
    (Utopia Sprawl's own enchant restriction, read as a target the same way
    `_read_phrase` reads anything else) names a *land* subtype, not an elided
    "creature", and reading it as one used to force `card_types={CREATURE}`
    onto a land-only target and refuse the very Forest the Aura was meant to
    enchant. CR 205.3m's actual creature-type list runs into the hundreds and
    is deliberately not enumerated here the same way it never has been - this
    one exclusion is the specific collision an in-pool card actually hit, not
    a first step toward a maintained whitelist.
    """
    return bool(_SUBTYPE_WORD_RE.match(raw)) and not (
        lowered in _ALL_NOUNS
        or lowered in _SUPERTYPE_NOUNS
        or lowered in _COLOR_WORDS
        or raw in BASIC_LAND_TYPES
    )


def _read_subtype_list(noun_phrase: str) -> tuple[list[str], str] | None:
    """ "Vampire, Werewolf, or Zombie[.]" (Slayer of the Wicked): a bare CR
    205.3m creature-type list used as the target noun itself, Oracle
    templating eliding the word "creature" that would otherwise follow it
    (CR 302.3's "Creature — Human Soldier" shows the same subtypes named on a
    type line). Returns the lower-cased type words plus a display string for
    `TargetRequirement.phrase`, or `None` if this is not that shape.

    Read only when there are **two or more** items, every one of them a
    single capitalized word absent from every noun/adjective vocabulary this
    parser already knows (`_ALL_NOUNS`, `_SUPERTYPE_NOUNS`, `_COLOR_WORDS`) -
    a real English noun is never capitalized mid-sentence, so this cannot be
    confused with "target Aura" or any other card-type/supertype word. The
    two-item floor is deliberate: a lone capitalized word is left to the
    ordinary parser below (and so still fails open, `understood=False`) since
    nothing in the pool needs the singular form and a wider reading risks
    misreading a name or a compound type this wave has not seen.
    """
    stripped = re.split(r"[.;]", noun_phrase)[0].strip()
    stripped = re.sub(r"\s+creatures?$", "", stripped, flags=re.IGNORECASE).strip().rstrip(".")
    if not stripped:
        return None
    raw_items = [
        item.strip() for item in re.split(r",\s*or\s+|,\s*|\s+or\s+", stripped) if item.strip()
    ]
    if len(raw_items) < 2:
        return None
    for item in raw_items:
        if not _is_bare_subtype_word(item, item.lower()):
            return None
    display = ", ".join(raw_items[:-1] + [f"or {raw_items[-1]}"])
    return [item.lower() for item in raw_items], display


def _read_one_compound_item(raw_item: list[str], lower_item: list[str]) -> dict[str, object] | None:
    """One item of a mixed compound noun list - "Forest", "green
    enchantment", "green planeswalker" - as its own fully independent
    card-type/subtype/color reading, or `None` when this item's own shape is
    not one of the ones `_read_compound_target_alternatives` reads.

    Deliberately narrow: a leading run of color words, then exactly one
    trailing noun that is a CR 300.1 card type, a CR 305.6 basic land type
    standing alone (the elided "land" the same way a bare creature type
    elides "creature"), or a bare CR 205.3m creature type. Nothing this
    parser does not already know how to read elsewhere is guessed at here;
    an item with more than that (its own adjectives, a further noun, a
    supertype) returns `None` and the whole compound reading is abandoned in
    favor of the ordinary merge below.
    """
    index = 0
    colors: set[Color] = set()
    while index < len(lower_item) and lower_item[index] in _COLOR_WORDS:
        colors.add(_COLOR_WORDS[lower_item[index]])
        index += 1
    remaining_raw = raw_item[index:]
    remaining_lower = lower_item[index:]
    if len(remaining_lower) != 1:
        return None
    word = remaining_lower[0]
    singular = word[:-1] if word.endswith("s") and word[:-1] in _ALL_NOUNS else word
    if singular in _TYPE_NOUNS:
        return {
            "card_types": frozenset({_TYPE_NOUNS[singular]}),
            "required_subtypes": frozenset(),
            "required_colors": frozenset(colors),
        }
    if remaining_raw[0] in BASIC_LAND_TYPES:
        # CR 305.6's five basic land types, standing in for the elided noun
        # "land" - Nissa's Defeat's own "target Forest" among its own
        # compound list, the land-subtype twin of the creature-type elision
        # `_is_bare_subtype_word` reads below.
        return {
            "card_types": frozenset({Type.LAND}),
            "required_subtypes": frozenset({word}),
            "required_colors": frozenset(colors),
        }
    if _is_bare_subtype_word(remaining_raw[0], word):
        # CR 205.3g/h/i/k/q's *closed* subtype lists (Equipment, Vehicle, an
        # enchantment type, ...) each elide their own card type, never
        # "creature" - `_split_type_or_closed_subtype_card`'s own docstring
        # (the two-item "target creature or Equipment card" shape) is the
        # identical bug this reads the same fix for, one list item at a time
        # rather than only the first/last pair of a two-item list. Checked
        # before the CR 205.3m creature-type fallback below, since a closed
        # list is a strict lookup and a creature type never collides with it.
        closed_type = _CLOSED_LIST_TYPE_OF.get(word)
        if closed_type is not None:
            return {
                "card_types": frozenset({closed_type}),
                "required_subtypes": frozenset({word}),
                "required_colors": frozenset(colors),
            }
        return {
            "card_types": frozenset({Type.CREATURE}),
            "required_subtypes": frozenset({word}),
            "required_colors": frozenset(colors),
        }
    return None


def _read_compound_target_alternatives(
    words: list[str], raw_words: list[str]
) -> list[dict[str, object]] | None:
    """A comma/"or"/"and"-joined noun list whose items do not all carry the
    same adjectives - Nissa's Defeat's own "target Forest, green
    enchantment, or green planeswalker": one bare land subtype beside two
    color-qualified card types. The ordinary noun-list loop in `_read_phrase`
    merges every item's own adjectives into one shared set, which is correct
    only when every item actually shares them (Liliana's Defeat's "target
    black creature or black planeswalker" does; this does not) - seeing
    `TargetRequirement.alternatives`'s own docstring for why that is wrong
    here specifically.

    `words`/`raw_words` are the *whole* tokenized noun phrase, exactly as
    `_read_phrase`'s own loop receives them - this is tried only when nothing
    trails the noun list at all (checked by the caller, since a trailing
    "you control"/comparison clause is read once for the whole compound, not
    per item, and this reader has no way to tell such a tail apart from a
    fourth list item). Returns one dict per item (each shaped like
    `_read_one_compound_item`'s own return), or `None` when any item is not
    that shape, or there are fewer than two - the caller falls back to the
    ordinary merge exactly as before this reader existed.
    """
    raw_items: list[list[str]] = [[]]
    lower_items: list[list[str]] = [[]]
    for raw, lowered in zip(raw_words, words, strict=True):
        if lowered in {"or", "and", ","}:
            raw_items.append([])
            lower_items.append([])
            continue
        raw_items[-1].append(raw)
        lower_items[-1].append(lowered)
    raw_items = [item for item in raw_items if item]
    lower_items = [item for item in lower_items if item]
    if len(raw_items) < 2:
        return None
    specs: list[dict[str, object]] = []
    for raw_item, lower_item in zip(raw_items, lower_items, strict=True):
        spec = _read_one_compound_item(raw_item, lower_item)
        if spec is None:
            return None
        specs.append(spec)
    return specs


def _split_type_or_closed_subtype_card(
    text: str,
) -> tuple[str, str, str, Type, str] | None:
    """ "target creature or Equipment card ..." (Nahiri, the Unforgiving): the
    first item is a plain CR 300.1 card type, the second a bare CR
    205.3g/h/i/k/q subtype word eliding its own type the way a lone "target
    Vehicle card" (Greasefang, Okiba Boss) already does.

    Equipment is an artifact subtype, never a creature one (CR 301.5), so
    merging the two items into a single `card_types`/`required_subtypes` pair
    the way an ordinary shared-adjective noun list does (`target black
    creature or black planeswalker`) would be wrong two different ways: it
    would make `card_types` read "creature or artifact" (fine on its own),
    but `required_subtypes` would then demand the target carry the
    "equipment" subtype *too* - `_rejects_card`'s subtype check is an "any
    of these" gate, but it still applies on top of the type check, not
    instead of it, so a plain Grizzly Bears would wrongly fail for not being
    an Equipment. CR 115.1's target is satisfied by *either* half, so the two
    are genuinely disjunctive - `_read_phrase` reads the first half as the
    ordinary noun phrase and turns the second into a full, independent
    `TargetRequirement.alternatives` entry instead.

    Returns `(first_word, noun_word, subtype_word, subtype_type, reduced_text)`
    where `reduced_text` is `text` with the "or `<Subtype>`" clause spliced
    out, so the caller reads the rest of the phrase (zone, comparison,
    controller, ...) exactly the ordinary way, once, for the first half alone.
    `None` when this is not that shape, or the capitalized word is not one of
    the CR's own *closed* subtype lists (`_CLOSED_LIST_TYPE_OF`) - a creature
    type here ("target creature or Soldier card") still fails open exactly as
    it always has, since CR 205.3m's list is never enumerated.
    """
    match = _TYPE_OR_CLOSED_SUBTYPE_CARD_RE.match(text)
    if match is None:
        return None
    first_word = match.group("first").lower()
    if first_word not in _TYPE_NOUNS:
        return None
    subtype_type = _CLOSED_LIST_TYPE_OF.get(match.group("subtype").lower())
    if subtype_type is None:
        return None
    noun_word = match.group("noun").lower()
    subtype_word = match.group("subtype").lower()
    reduced_text = f"{first_word} {noun_word}{text[match.end() :]}"
    return first_word, noun_word, subtype_word, subtype_type, reduced_text


#: "target `<quality>` card or card with `<keyword>`" - Jacob Frye's own
#: "target Assassin card or card with freerunning from your graveyard". The
#: second item is a whole card of its own described only by a keyword
#: ability it has (CR 702.1), not one more noun sharing the first item's
#: adjectives, so it is read as an independent `TargetRequirement.
#: alternatives` entry rather than merged into the first reading.
_OR_CARD_WITH_KEYWORD_RE = re.compile(
    r"\bcards? or cards? with (?P<keyword>[a-z]+(?: strike)?)\b", re.IGNORECASE
)


#: "target `<supertype>` or `<quality>` card" - Nashi, Moon's Legacy's
#: "target legendary or Rat card from your graveyard". The supertype (CR
#: 205.4a) and the subtype are two independent disjuncts - a legendary card
#: *or* a Rat card - whereas the ordinary adjective reader keeps one shared
#: `required_supertypes`/`required_subtypes` pair that has to hold at once.
#: Read as the second disjunct's own requirement plus an `alternatives` entry
#: for the supertype alone.
_SUPERTYPE_OR_QUALITY_CARD_RE = re.compile(
    r"^\s*(?P<supertype>legendary|basic|snow) or "
    r"(?P<other>(?!cards?\b)[a-z][\w-]* (?P<noun>cards?))\b",
    re.IGNORECASE,
)


#: "target creature on the battlefield or creature card in a graveyard"
#: (Taskmaster, Mercenary Mimic) - two disjuncts in two different zones: a
#: permanent, or a card in a graveyard. Read as the first disjunct's own
#: requirement plus an `alternatives` entry for the second (CR 115.1).
_ON_THE_BATTLEFIELD_OR_CARD_RE = re.compile(
    r"^\s*(?P<first>[a-z][\w -]*?) on the battlefield or "
    r"(?P<second>[a-z][\w -]*?cards? in (?:a|your|an opponent's) graveyards?)\b",
    re.IGNORECASE,
)


#: " other than enchanted creature" - see `TargetRequirement.excludes_enchanted`.
_OTHER_THAN_ENCHANTED_RE = re.compile(r" other than enchanted creature\b", re.IGNORECASE)


def _read_phrase(prefix: str, suffix: str, *, strict: bool = False) -> TargetRequirement | None:
    """Turn one "target ..." phrase into a requirement, or None if unreadable.

    `strict` also refuses a phrase with words left over once every clause this
    reader knows has been taken off - the ordinary target scan tolerates a
    trailing tail it does not read, `permanent_description` must not.
    """
    spell_targets_gate = _SPELL_TARGETS_GATE_RE.match(suffix)
    if spell_targets_gate is not None:
        # Checked ahead of `_SPELL_OR_ABILITY` below: that pattern's own
        # `.match` (a prefix test, not a full match) would otherwise claim
        # "spell or ability that targets `<description>`" too, recurse on
        # the bare "spell" base, and silently drop the "that targets
        # `<description>`" tail - an unreadable restriction that quietly let
        # every spell through, exactly the wrong-object bug this module's
        # own `required_colors` docstring warns against.
        base = _read_phrase(prefix, " spell", strict=strict)
        if base is None or not base.allows_cards:
            return None
        clause = spell_targets_gate.group("clause").strip()
        you_or_types = _TARGETS_YOU_OR_TYPES_RE.fullmatch(clause)
        you_only = _TARGETS_YOU_RE.fullmatch(clause)
        types_only = _TARGETS_TYPES_YOU_CONTROL_RE.fullmatch(clause)
        if you_or_types is not None:
            types = _read_must_target_types(you_or_types.group("types"))
            if types is None:
                return None
            update: dict[str, object] = {
                "must_target_you": True,
                "must_target_types": types,
                "must_target_you_control": True,
            }
        elif you_only is not None:
            update = {"must_target_you": True}
        elif types_only is not None:
            types = _read_must_target_types(types_only.group("types"))
            if types is None:
                return None
            update = {"must_target_types": types, "must_target_you_control": True}
        else:
            return None
        phrase = f"{base.phrase} that targets {clause}"
        if spell_targets_gate.group("or_ability") is not None:
            base = base.model_copy(
                update={"phrase": phrase.replace("spell", "spell or ability", 1)}
            )
            update["allows_abilities"] = True
        else:
            base = base.model_copy(update={"phrase": phrase})
        return base.model_copy(update=update)
    spell_or_ability = _SPELL_OR_ABILITY.match(suffix)
    if spell_or_ability is not None:
        # CR 115.2(b)/CR 113.1c: "target spell or ability" reaches both kinds
        # of stack object. Read as the plain "spell" requirement first, so
        # every rider after it ("with a single target", a controller clause)
        # lands exactly where it did, then widened to abilities as well.
        base = _read_phrase(prefix, " spell" + suffix[spell_or_ability.end() :], strict=strict)
        if base is None or not base.allows_cards:
            return None
        return base.model_copy(
            update={
                "phrase": base.phrase.replace("spell", "spell or ability", 1),
                "allows_abilities": True,
            }
        )
    split = _split_type_or_closed_subtype_card(suffix)
    if split is not None:
        # See `_split_type_or_closed_subtype_card`'s own docstring: read the
        # first half ordinarily (recursing on the reduced text), then wrap
        # its result with the second half as a full independent alternative
        # (`TargetRequirement.alternatives`, CR 115.1) rather than merging
        # the two into one `card_types`/`required_subtypes` pair.
        first_word, noun_word, subtype_word, subtype_type, reduced_suffix = split
        base = _read_phrase(prefix, reduced_suffix, strict=strict)
        if base is None:
            return None
        alternative = base.model_copy(
            update={
                "phrase": f"target {subtype_word} {noun_word}",
                "card_types": frozenset({subtype_type}),
                "required_subtypes": frozenset({subtype_word}),
                "alternatives": (),
            }
        )
        return base.model_copy(
            update={
                "phrase": f"{base.phrase} or {subtype_word} {noun_word}",
                "alternatives": base.alternatives + (alternative,),
            }
        )
    other_than_enchanted = _OTHER_THAN_ENCHANTED_RE.search(suffix)
    if other_than_enchanted is not None:
        base = _read_phrase(
            prefix,
            suffix[: other_than_enchanted.start()] + suffix[other_than_enchanted.end() :],
            strict=strict,
        )
        if base is None:
            return None
        return base.model_copy(
            update={
                "phrase": f"{base.phrase} other than enchanted creature",
                "excludes_enchanted": True,
            }
        )
    battlefield_or_card = _ON_THE_BATTLEFIELD_OR_CARD_RE.match(suffix)
    if battlefield_or_card is not None:
        tail = suffix[battlefield_or_card.end() :]
        base = _read_phrase(prefix, " " + battlefield_or_card.group("first") + tail, strict=strict)
        alternative = _read_phrase(
            prefix, " " + battlefield_or_card.group("second") + tail, strict=strict
        )
        if base is None or alternative is None:
            return None
        return base.model_copy(
            update={
                "phrase": f"{base.phrase} on the battlefield or "
                + alternative.phrase.removeprefix("target "),
                "alternatives": (*base.alternatives, alternative),
            }
        )
    supertype_or = _SUPERTYPE_OR_QUALITY_CARD_RE.match(suffix)
    if supertype_or is not None:
        tail = suffix[supertype_or.end() :]
        base = _read_phrase(prefix, supertype_or.group("other") + tail, strict=strict)
        alternative = _read_phrase(
            prefix,
            supertype_or.group("supertype") + " " + supertype_or.group("noun") + tail,
            strict=strict,
        )
        if base is None or alternative is None:
            return None
        return base.model_copy(
            update={
                "phrase": f"target {supertype_or.group('supertype').lower()} or "
                + base.phrase.removeprefix("target "),
                "alternatives": (*base.alternatives, alternative),
            }
        )
    or_keyword = _OR_CARD_WITH_KEYWORD_RE.search(re.split(r"[.;]", suffix)[0])
    if or_keyword is not None:
        base = _read_phrase(
            prefix,
            suffix[: or_keyword.start()] + "card" + suffix[or_keyword.end() :],
            strict=strict,
        )
        if base is None or not base.allows_cards:
            return None
        keyword = or_keyword.group("keyword").lower()
        alternative = TargetRequirement(
            phrase=f"target card with {keyword}",
            allows_cards=True,
            zones=base.zones,
            controller=base.controller,
            required_keyword=keyword,
        )
        return base.model_copy(
            update={
                "phrase": f"{base.phrase} or card with {keyword}",
                "alternatives": (*base.alternatives, alternative),
            }
        )
    excludes_source = _excludes_source(prefix)
    counted = _read_count(prefix)
    if counted is None:
        return None
    minimum, most, variable = counted
    unbounded = most is None
    count = 0 if most is None else most

    noun_phrase = re.split(r"[.;]", suffix)[0]

    # A bare `.match` (not `.fullmatch`) used to silently misread "triggered
    # ability or colorless spell" (Consign to Memory) as the whole target
    # being "an ability", dropping "or colorless spell" on the floor -
    # `understood=True` with a wrong, actively-enforced restriction, worse
    # than not checking at all. The tail past the ability phrase is now
    # inspected explicitly: empty (Tishana's Tidebinder's plain "target
    # activated or triggered ability") keeps the old ability-only reading,
    # `_ABILITY_OR_COLOR_COUNT_SPELL_RE`'s "or `<color-count>` spell" shape
    # reads the genuine compound below, and anything else still fails the
    # whole phrase closed (`understood=False`) rather than being guessed at.
    ability = _ABILITY_PHRASE.match(noun_phrase)
    if ability is not None:
        tail = noun_phrase[ability.end() :].strip()
        source_restricted = _ABILITY_YOU_CONTROL_FROM_SOURCE_RE.fullmatch(tail) if tail else None
        if source_restricted is not None:
            # "... ability you control[ from a[n] <type> source]" (Lithoform
            # Engine; Echo, Perceptive Prodigy): the controller and the
            # source's card type (CR 113.7).
            source_type = source_restricted.group("type")
            source_card_type = _TYPE_NOUNS.get(source_type.lower()) if source_type else None
            if source_type and source_card_type is None:
                return None
            return TargetRequirement(
                phrase="target " + " ".join(noun_phrase.split()).lower(),
                count=count,
                minimum=minimum,
                unbounded=unbounded,
                variable_count=variable,
                allows_cards=False,
                allows_abilities=True,
                ability_kinds=_ability_kinds_named(ability.group(0)),
                ability_source_types=(
                    frozenset({source_card_type}) if source_card_type is not None else frozenset()
                ),
                controller=(
                    ControllerRestriction.YOU
                    if source_restricted.group("you")
                    else ControllerRestriction.ANY
                ),
                zones=frozenset({Zone.STACK}),
                excludes_source=excludes_source,
            )
        if not tail:
            # CR 115.2(b): an ability on the stack is an object that cannot
            # exist on the battlefield, and a spell may target one when it
            # says so.
            return TargetRequirement(
                phrase="target " + " ".join(ability.group(0).split()).lower(),
                count=count,
                minimum=minimum,
                unbounded=unbounded,
                variable_count=variable,
                allows_cards=False,
                allows_abilities=True,
                ability_kinds=_ability_kinds_named(ability.group(0)),
                zones=frozenset({Zone.STACK}),
                excludes_source=excludes_source,
            )
        compound = _ABILITY_OR_COLOR_COUNT_SPELL_RE.match(tail)
        if compound is not None:
            # "target triggered ability or colorless spell" (Consign to
            # Memory) - a disjunction across two different noun *kinds*, not
            # just two nouns of the same kind ("target artifact or
            # enchantment" stays inside `card_types`). One `allows_abilities
            # and allows_cards` requirement covers both halves: `rejects`
            # already dispatches an ability target to `_rejects_ability` and
            # a card target to `_rejects_card` before either field is
            # consulted, so an ability is judged only by
            # `allows_abilities`/`controller` and a spell only by
            # `allows_cards`/`zones`/`color_count` - the two halves never
            # interfere with each other on the same requirement.
            return TargetRequirement(
                phrase="target "
                + " ".join(ability.group(0).split()).lower()
                + " or "
                + compound.group("color_count").lower()
                + " spell",
                count=count,
                minimum=minimum,
                unbounded=unbounded,
                variable_count=variable,
                allows_cards=True,
                allows_abilities=True,
                ability_kinds=_ability_kinds_named(ability.group(0)),
                zones=frozenset({Zone.STACK}),
                color_count=compound.group("color_count").lower(),
                excludes_source=excludes_source,
            )
        return None  # a compound this parser cannot finish reading: fail closed

    subtype_list = _read_subtype_list(noun_phrase)
    if subtype_list is not None:
        subtypes, display = subtype_list
        # CR 205.3m: a bare creature-type list used as the noun itself always
        # means creatures of those types - "target Vampire, Werewolf, or
        # Zombie" (Slayer of the Wicked) - so `card_types` still carries the
        # ordinary CR 300.1 creature-type check on top of the disjunction.
        return TargetRequirement(
            phrase="target " + display,
            count=count,
            minimum=minimum,
            unbounded=unbounded,
            variable_count=variable,
            card_types=frozenset({Type.CREATURE}),
            required_subtypes=frozenset(subtypes),
            excludes_source=excludes_source,
        )

    # The comma is kept as its own token (not just a separator) so an
    # Oxford-comma noun list - "target artifact, enchantment, or nonbasic
    # land" - can be told apart from an ordinary "target creature you
    # control": see the noun-reading loop below.
    #
    # `raw_words` keeps the original capitalization alongside `words`'
    # lower-cased tokens, index for index - the noun-reading loop below needs
    # it to tell Aeronaut Cavalry's bare "Soldier" (CR 205.3m, elided
    # "creature") apart from an ordinary lower-case English noun the way
    # `_read_subtype_list` already does for its own two-or-more-item list.
    # Read *before* tokenization, not after: the counter-kind spelling
    # ("+1/+1", "-1/-1") uses "+"/"/" characters the word tokenizer below
    # does not keep, so a clause extracted from the already-tokenized `rest`
    # the way `required_keyword`'s own plain-word vocabulary safely is would
    # never see the literal symbols to match against.
    required_counter_kind, noun_phrase = _extract_required_counter_kind(noun_phrase)
    raw_words = re.findall(r"[\w'-]+|,", noun_phrase)
    words = re.findall(r"[\w'-]+|,", noun_phrase.lower())
    if not words:
        # CR 115.4: "any target," "another target," "two targets," "or similar
        # rather than 'target [something]'" - creature, player, planeswalker or
        # battle. This is Electrolyze's "among one or two targets".
        return TargetRequirement(
            phrase="target",
            count=count,
            minimum=minimum,
            unbounded=unbounded,
            variable_count=variable,
            card_types=ANY_TARGET_TYPES,
            allows_players=True,
            excludes_source=excludes_source,
        )
    adjectives, index = _read_adjectives(raw_words, words)
    card_types: set[Type] = set()
    required_subtypes: set[str] = set()
    #: Which of `card_types` arrived by eliding a closed-list subtype word
    #: (CR 205.3g/h/i/k/q) standing alone for its own noun - "target
    #: Equipment, instant, or sorcery card" (Thor, God of Thunder) elides
    #: Equipment's own artifact type here, tracked separately so the post-loop
    #: split below can tell it apart from "instant"/"sorcery", which name
    #: their own card type directly and carry no subtype requirement at all.
    #: See the split just after the loop for why the two cannot share one
    #: flat `required_subtypes` the ordinary way a uniform list does.
    subtype_elided_types: set[Type] = set()
    allows_players = False
    opponent_only = False
    allows_cards = False
    zones = {Zone.BATTLEFIELD}
    must_be_tapped: bool | None = adjectives.must_be_tapped
    bare_card = False
    nouns_read = 0
    noun_end = index
    or_any_spell = False
    #: Whether a bare "spell" was read as the *very first* noun-list token -
    #: decided only once the whole noun list is in (see the `spell_seen`
    #: handling right after the loop below), since at that point there is no
    #: way yet to tell "target spell" alone (`zones` stays {STACK}) apart
    #: from "target spell or creature" (Fatehold Charm, `or_any_spell`).
    #: "spell" anywhere *after* the first token already has `after_conjunction`
    #: (just below) to decide it immediately - see the branch itself.
    spell_seen = False
    #: Whether the token just skipped was a noun-list conjunction. "Target
    #: creature spell" and "target creature or spell" differ by this word and
    #: by nothing else - see `TargetRequirement.or_any_spell`. Left `True`
    #: across an intervening per-item adjective (Icy Reception's "creature or
    #: **legendary** spell" - CR 205.4a's supertype word sits between the "or"
    #: and the noun it belongs to), since the adjective is part of the same
    #: item as the noun that follows it, not a fresh item of its own.
    after_conjunction = False

    while index < len(words):
        word = words[index]
        if word in {"or", "and", ","}:
            # Between items of a noun list - "artifact, enchantment, or
            # nonbasic land" - and otherwise meaningless here; skip straight
            # to the next item rather than treating it as the end of the list
            # or as an unread noun.
            index += 1
            after_conjunction = True
            continue
        if nouns_read and adjectives.take(raw_words[index], word):
            # Each item in an Oxford-comma (or plain "or"/"and") noun list may
            # carry its own leading adjective - Boseiju's "nonbasic" belongs
            # only to "land", the third item in "artifact, enchantment, or
            # nonbasic land" - so a fresh adjective is tried before every noun
            # after the first, not only before the very first one.
            index += 1
            continue
        # "target player's hand" and "target players' graveyards" both target
        # the player; the possessive names what the effect then reaches into.
        bare = word[:-2] if word.endswith("'s") else word.rstrip("'")
        singular = bare[:-1] if bare.endswith("s") and bare[:-1] in _ALL_NOUNS else bare
        if singular in _CARD_NOUNS:
            # "target cards from graveyards", with no card type in front of it.
            allows_cards = True
            bare_card = True
        elif singular in _TYPE_NOUNS:
            card_types.add(_TYPE_NOUNS[singular])
            allows_cards = True
        elif singular in _PERMANENT_NOUNS:
            allows_cards = True
        elif singular in _SPELL_NOUNS:
            allows_cards = True
            if nouns_read == 0:
                # "spell" is the very first noun-list token - either the
                # whole list ("target spell" alone) or the first item of a
                # two-kind list ("target spell or creature", Fatehold
                # Charm). Deferred - see `spell_seen` just below the loop.
                spell_seen = True
            elif after_conjunction:
                # "spell" reached across an "or"/"and" from an earlier item -
                # "target creature or spell" (Aang, Swift Savior), or, with a
                # per-item adjective of its own in between, "target creature
                # or legendary spell" (Icy Reception). CR 112.1's "A spell is
                # a card on the stack" of no particular card type, alongside
                # whatever the earlier item(s) already restricted `card_types`
                # to - the same two-kind disjunction `or_any_spell` exists for,
                # decided immediately here since a *later* item's own noun is
                # never itself ambiguous the way the very first one is.
                or_any_spell = True
            else:
                # "spell" glued directly onto a preceding type word within
                # the *same* item, no conjunction between them - "target
                # creature spell or planeswalker spell" (Subtlety). Every
                # item here names a spell of some card type, not a permanent,
                # so this is CR 112.1's plain "spell on the stack"
                # restriction regardless of how many such items there are.
                zones = {Zone.STACK}
        elif singular in _PLAYER_NOUNS:
            allows_players = True
            opponent_only = opponent_only or singular == "opponent"
        elif word in _QUALIFIERS:
            if word in {"tapped", "untapped"}:
                must_be_tapped = word == "tapped"
            elif word in _SOURCE_EXCLUDING:
                excludes_source = True
            index += 1
            continue
        elif raw_words[index] in BASIC_LAND_TYPES and (
            index + 1 >= len(words) or words[index + 1] in {"or", "and", ","}
        ):
            # CR 305.6's five basic land types, standing in for the elided
            # noun "land" - Nissa's Defeat's own "target Forest, green
            # enchantment, or green planeswalker": "Forest" prints no
            # following noun at all, the same elision `_is_bare_subtype_word`
            # reads for a creature type, but explicitly excluded from that
            # branch (see its own docstring) since a land subtype is not an
            # elided *creature*. Read at any position in a noun list, not
            # only the first, since the five basic land types are a small,
            # fully enumerable, unambiguous set - unlike CR 205.3m's
            # hundreds of creature types, there is no real English word this
            # could be confused with. The lookahead (end of words, or
            # another list item) keeps "target Forest you control" and
            # "target Forest card in your graveyard" from swallowing a real
            # following noun the way `_is_bare_subtype_word`'s own docstring
            # already guards against for creature types.
            required_subtypes.add(word)
            card_types.add(Type.LAND)
            subtype_elided_types.add(Type.LAND)
            allows_cards = True
        elif nouns_read == 0 and _is_bare_subtype_word(raw_words[index], word):
            # Aeronaut Cavalry's "another target Soldier you control" - CR
            # 205.3m's creature-type word standing alone as the target noun,
            # the elided-"creature" shape `_read_subtype_list` reads for two
            # or more items; here it is exactly one, so it falls to this
            # branch instead rather than the early-return special case, which
            # is also how "you control" past it still reaches the ordinary
            # `control_match` handling below.
            #
            # The elision only happens when nothing else is standing in for
            # the noun. Greasefang, Okiba Boss's "target Vehicle card from
            # your graveyard" prints the noun itself, and a Vehicle card is
            # an *artifact* card (CR 205.3 lists Vehicle among the artifact
            # subtypes, and CR 301.7 is what makes a Vehicle a creature only
            # once it is crewed) - adding `Type.CREATURE` here would make
            # every Vehicle in a graveyard an illegal target for the one card
            # that names them. So a following noun ("card", "permanent",
            # "spell", or a card type) is taken as the real noun and the
            # subtype simply qualifies it.
            required_subtypes.add(word)
            following = words[index + 1] if index + 1 < len(words) else ""
            following_bare = following[:-1] if following.endswith("s") else following
            if following_bare not in _ALL_NOUNS:
                # CR 205.3m's elision only ever stands in for "creature" -
                # "target Equipment you control" (Blacksmith's Talent) is
                # never "target Equipment creature you control" (Equipment
                # is CR 205.3g's artifact subtype). A bare subtype word this
                # engine knows to be some *other* card type's - artifact,
                # enchantment, land, battle, planeswalker - elides that card
                # type instead, never creature.
                other_type = noncreature_subtype_card_type(word)
                if other_type is not None:
                    card_types.add(Type(other_type))
                    subtype_elided_types.add(Type(other_type))
                else:
                    card_types.add(Type.CREATURE)
                    subtype_elided_types.add(Type.CREATURE)
            allows_cards = True
        elif nouns_read == 0 and not adjectives.read:
            return None  # an adjective the parser does not know: fail open
        else:
            break

        nouns_read += 1
        index += 1
        noun_end = index
        after_conjunction = False

    # "target creature token you control": the adjective may follow its noun.
    if nouns_read and noun_end < len(words) and words[noun_end] == "token":
        adjectives.must_be_token = True
        noun_end += 1

    if spell_seen:
        # "spell" was the very first noun-list token. Exactly one noun total
        # ("target spell") is CR 112.1's spell on the stack and nothing else,
        # so `zones` narrows to it the way it always has. More than one
        # ("target spell or creature", Fatehold Charm) is CR 115.1's
        # either-or between a stack object of no particular type and a
        # permanent-type restriction that keeps its own default `zones`
        # ({BATTLEFIELD}) - `or_any_spell` is what lets a spell on the stack
        # satisfy the requirement too, without narrowing `zones` itself and
        # silently refusing every permanent. "spell" reached *after* the
        # first token ("target creature or spell", Aang, Swift Savior; other
        # shapes too) was already decided immediately inside the loop, by
        # `after_conjunction`.
        if nouns_read > 1:
            or_any_spell = True
        else:
            zones = {Zone.STACK}

    rest = " ".join(words[noun_end:])
    controller = ControllerRestriction.ANY
    owned_by_caster = False

    # Read out of the way before the comparison scan sees it: this clause looks
    # exactly like a mana-value bound and is not one (see
    # `_COLORS_OF_MANA_SPENT_CONDITION`).
    rest = _COLORS_OF_MANA_SPENT_CONDITION.sub("", rest).strip()

    # Same reason, for CR 613.4b's own effect verb rather than a restriction -
    # see `_SETS_BASE_POWER_TOUGHNESS_EFFECT`.
    rest = _SETS_BASE_POWER_TOUGHNESS_EFFECT.sub("", rest).strip()

    total_mana_value_at_most, rest = _extract_total_mana_value(rest)

    comparison = _extract_comparison(rest)
    if comparison is _COMPARISON_UNREADABLE:
        # A comparison was clearly attempted and this parser could not finish
        # reading it - fail the whole phrase rather than target past it.
        return None
    (
        comparison_attribute,
        comparison_operator,
        comparison_value,
        comparison_count,
        rest,
    ) = comparison
    comparison_x_definition: str | None = None
    if comparison_attribute is not None and comparison_value is None and comparison_count is None:
        # CR 107.3c: "with mana value X or less, where X is ..." defines X in
        # the text, so the bound is that expression rather than an unbound X.
        where_x = _WHERE_X_DEFINITION.search(rest)
        if where_x is not None:
            comparison_x_definition = where_x.group("expression").strip()
            rest = rest[: where_x.start()].strip()

    distinct_controllers, rest = _extract_distinct_controllers(rest)

    share_a_card_type, rest = _extract_share_a_card_type(rest)

    required_keyword, rest = _extract_required_keyword(rest)

    attacking_alone, rest = _extract_attacking_alone(rest)

    attacked_this_turn, rest = _extract_attacked_this_turn(rest)

    entered_this_turn, rest = _extract_entered_this_turn(rest)

    crewed_source_this_turn, rest = _extract_crewed_this_turn(rest)

    color_presence, rest = _extract_color_presence(rest)
    color_count = adjectives.color_count
    if color_presence:
        if color_count is not None:
            # A phrase naming two color-count categories at once ("target
            # multicolored permanent that's one or more colors") is not a
            # shape any printing in the pool uses - refuse rather than guess
            # which one wins.
            return None
        color_count = "colored"

    trailing_colors, rest = _extract_color_disjunction(rest)

    if not nouns_read:
        # Nothing but adjectives: "target token you control". CR 111.1 makes a
        # token a permanent, so that is what is left once the adjectives are
        # taken off. Only accepted when what follows is a clause this parser
        # reads, so an unknown *noun* still fails open rather than widening into
        # "any permanent".
        if not adjectives.read or not _only_known_clauses(rest):
            return None
        allows_cards = True

    extra_excluded_supertypes: frozenset[Supertype] = frozenset()
    extra_excluded_types: frozenset[Type] = frozenset()
    exiled_with_source = False
    if rest.startswith("card") or bare_card:
        # "target creature card in your graveyard" is a card, not a permanent,
        # and so is a bare "target card". Either way the zone has to be stated:
        # a card that is not a permanent is somewhere else (CR 115.2).
        zone_match = _ZONE_CLAUSE.search(rest)
        if zone_match is None:
            if _EXILED_WITH_RE.search(rest) is not None:
                # "exiled with `<name>`" (The Darkness Crystal) - the zone is
                # exile, always, and the self-reference is the whole point of
                # the clause (see `_EXILED_WITH_RE`'s own docstring).
                zones = {Zone.EXILE}
                exiled_with_source = True
            else:
                return None
        else:
            zones = {_ZONES[zone_match.group("zone").lower()]}
            whose = zone_match.group("whose")
            if whose is not None and whose.lower() == "your":
                controller = ControllerRestriction.YOU
            elif whose is not None and ("opponent" in whose.lower() or whose.lower() == "their"):
                # "from an opponent's graveyard" (Dire Fleet Daredevil),
                # "in their graveyard" - CR 109.5's "you"/"your" is the
                # default the bare "a"/"an"/"any" forms already read as no
                # restriction at all; this is the other side of that same
                # distinction, read the same way `_CONDITION_CONTROLS_N`'s
                # own "an opponent controls" already is.
                controller = ControllerRestriction.OPPONENT
            elif whose is not None and whose.lower().startswith("that player"):
                # "from that player's graveyard" (Shark Shredder, Killer
                # Clone's own combat-damage trigger) - CR 400.7/108.4a's owner
                # fallback for a card with no controller reads the same
                # `controller_or_owner` this restriction already tests, so
                # the only new thing needed is binding "that player" itself,
                # the identical `ControllerRestriction.EVENT_PLAYER`
                # "... that player controls" already uses for a permanent -
                # see `TargetingProfile.for_event_player` and
                # `models.game._that_player_of`, extended alongside this to
                # recognise the phrase in a zone clause too.
                controller = ControllerRestriction.EVENT_PLAYER
            # "... other than a basic land card" (Surgical Extraction) - a
            # compound-noun exclusion on the bare "target card" itself, past
            # the zone clause. Read here rather than by `_Adjectives`, which
            # only ever reads a leading adjective *before* the noun it
            # excludes ("target nonbasic land"); this "other than" tail comes
            # after the noun and the zone both.
            exclusion = _read_other_than_exclusion(rest[zone_match.end() :])
            if exclusion is None:
                return None
            extra_excluded_supertypes, extra_excluded_types = exclusion
    else:
        control_match = _CONTROL_CLAUSE.match(rest)
        if control_match is not None:
            control_words = re.sub(r"\s+", " ", control_match.group(1).lower())
            if control_words == "you own":
                owned_by_caster = True
            else:
                controller = _CONTROLLERS[control_words]

    if strict and not _nothing_left_unread(
        rest, bare_card=bare_card, comparison_read=comparison_attribute is not None
    ):
        return None

    # A mixed compound noun list - Nissa's Defeat's own "target Forest, green
    # enchantment, or green planeswalker" - whose items do not all carry the
    # same color. Read only when there genuinely is a per-item divergence:
    # a uniform list ("target black creature or black planeswalker",
    # "target artifact or enchantment") is left to the ordinary merge above
    # exactly as before this reader existed, so nothing already passing
    # changes representation for no reason. See `_read_compound_target_
    # alternatives` and `TargetRequirement.alternatives`.
    compound_card_types = frozenset(card_types)
    compound_required_subtypes = frozenset(required_subtypes)
    compound_alternatives: tuple[TargetRequirement, ...] = ()
    if nouns_read >= 2:
        compound_items = _read_compound_target_alternatives(words[:noun_end], raw_words[:noun_end])
        if compound_items is not None and (
            len({item["required_colors"] for item in compound_items}) > 1
            or
            # Thor, God of Thunder's own "target Equipment, instant, or
            # sorcery card": no color divergence at all, but one item (the
            # closed-list-subtype "Equipment") carries a `required_subtypes`
            # the others do not - the identical "shared adjectives merge is
            # wrong here" problem `TargetRequirement.alternatives` exists
            # for, just on the subtype axis instead of the color one.
            len({item["required_subtypes"] for item in compound_items}) > 1
        ):
            first, *rest_items = compound_items
            compound_card_types = first["card_types"]  # type: ignore[assignment]
            compound_required_subtypes = first["required_subtypes"]  # type: ignore[assignment]
            compound_required_colors = first["required_colors"]
            compound_alternatives = tuple(
                TargetRequirement(
                    phrase="target "
                    + " or ".join(
                        sorted(kind.value for kind in item["card_types"])  # type: ignore[arg-type]
                    ),
                    card_types=item["card_types"],  # type: ignore[arg-type]
                    required_subtypes=item["required_subtypes"],  # type: ignore[arg-type]
                    required_colors=item["required_colors"],  # type: ignore[arg-type]
                    allows_cards=allows_cards,
                    zones=frozenset(zones),
                    controller=controller,
                )
                for item in rest_items
            )
        else:
            compound_required_colors = frozenset(adjectives.required_colors)
    else:
        compound_required_colors = frozenset(adjectives.required_colors)

    if (
        nouns_read >= 2
        and not compound_alternatives
        and required_subtypes
        and (card_types - subtype_elided_types)
        and subtype_elided_types
    ):
        # `_read_compound_target_alternatives` above cannot read Thor, God of
        # Thunder's own "target Equipment, instant, or sorcery card" at all -
        # every item there needs its own trailing noun ("green planeswalker"),
        # and this list has only one, shared by the whole thing ("sorcery
        # card"). `subtype_elided_types` tracked which types actually came
        # with a subtype requirement as the ordinary merge loop ran; anything
        # left over in `card_types` never had one, so folding the whole set's
        # `required_subtypes` onto it the flat way would wrongly refuse a
        # plain instant or sorcery for not being Equipment. Split the same
        # way `_split_type_or_closed_subtype_card` already splits a two-item
        # version of the identical shape: the subtype-eliding type(s) keep
        # the requirement as their own `alternatives` entry, and the type(s)
        # that never carried one become the base requirement with none.
        compound_card_types = frozenset(card_types - subtype_elided_types)
        compound_required_subtypes = frozenset()
        compound_alternatives = (
            TargetRequirement(
                phrase="target " + " or ".join(sorted(kind.value for kind in subtype_elided_types)),
                card_types=frozenset(subtype_elided_types),
                required_subtypes=frozenset(required_subtypes),
                allows_cards=allows_cards,
                zones=frozenset(zones),
                controller=controller,
            ),
        )

    # A trailing "that's `<color>` or `<color>`" (Refute Destiny, Terminal
    # Criticism) restricts the whole compound noun at once, the same way a
    # leading color adjective would - unioned in here rather than earlier so
    # it survives whichever of the two branches above ran.
    compound_required_colors = compound_required_colors | trailing_colors

    return TargetRequirement(
        phrase=" ".join(["target", *(word for word in words[:noun_end] if word != ",")]),
        count=count,
        minimum=minimum,
        unbounded=unbounded,
        variable_count=variable,
        card_types=compound_card_types,
        required_subtypes=compound_required_subtypes,
        excluded_subtypes=frozenset(adjectives.excluded_subtypes),
        excluded_card_types=frozenset(adjectives.excluded_types) | extra_excluded_types,
        required_supertypes=frozenset(adjectives.required_supertypes),
        excluded_supertypes=frozenset(adjectives.excluded_supertypes) | extra_excluded_supertypes,
        required_colors=compound_required_colors,
        excluded_colors=frozenset(adjectives.excluded_colors),
        allows_cards=allows_cards,
        allows_players=allows_players,
        opponent_only=opponent_only and not allows_cards,
        zones=frozenset(zones),
        or_any_spell=or_any_spell,
        controller=controller,
        owned_by_caster=owned_by_caster,
        must_be_tapped=must_be_tapped,
        excludes_source=excludes_source or adjectives.excludes_source,
        exiled_with_source=exiled_with_source,
        must_be_token=adjectives.must_be_token,
        color_count=color_count,
        historic=adjectives.historic,
        combat_states=frozenset(adjectives.combat_states),
        excluded_combat_states=frozenset(adjectives.excluded_combat_states),
        must_be_attacking_alone=attacking_alone,
        must_have_attacked_this_turn=attacked_this_turn,
        must_have_entered_this_turn=entered_this_turn,
        must_have_crewed_source_this_turn=crewed_source_this_turn,
        alternatives=compound_alternatives,
        comparison_attribute=comparison_attribute,
        comparison_operator=comparison_operator,
        comparison_value=comparison_value,
        comparison_count=comparison_count,
        comparison_x_definition=comparison_x_definition,
        distinct_controllers=distinct_controllers,
        share_a_card_type=share_a_card_type,
        total_mana_value_at_most=total_mana_value_at_most,
        required_keyword=required_keyword,
        required_counter_kind=required_counter_kind,
    )


def _nothing_left_unread(rest: str, *, bare_card: bool, comparison_read: bool) -> bool:
    """Whether `_read_phrase` consumed a whole permanent description.

    A card in a zone ("creature card in your graveyard") is not a permanent,
    so it never counts. What may remain is a control clause, and the bare
    "with" a comparison leaves behind once its own words are taken out."""
    if bare_card or rest.startswith("card"):
        return False
    leftover = rest.strip()
    control = _CONTROL_CLAUSE.match(leftover)
    if control is not None:
        leftover = leftover[control.end() :].strip()
    if comparison_read:
        leftover = re.sub(r"^with\b", "", leftover).strip()
    return not leftover


def permanent_description(text: str) -> TargetRequirement | None:
    """Read an untargeted permanent description - "a nontoken creature", "a
    creature token", "a creature with flying" - with the grammar a "target
    ..." phrase uses, so an edict's "sacrifices a <description> of their
    choice" and a target restriction can never disagree about what a word
    means (CR 111.1 token-ness, CR 205.2a card types, "non-" types, a
    trailing "with <keyword>" or comparison).

    `text` is the description without its article. Returns the requirement,
    for `TargetRequirement.rejects` to test each permanent against, or None
    when any word is left unread or the description could name something
    other than a permanent on the battlefield (a player, an ability, a card in
    another zone, "another" or "that you control" relative to someone). Being
    affected by it is not being targeted (CR 115.10a); only the description is
    shared.
    """
    requirement = _read_phrase("", text.strip(), strict=True)
    if requirement is None:
        return None
    if (
        not requirement.allows_cards
        or requirement.allows_players
        or requirement.allows_abilities
        or requirement.zones != frozenset({Zone.BATTLEFIELD})
        or requirement.controller is not ControllerRestriction.ANY
        or requirement.excludes_source
        or requirement.exiled_with_source
        or requirement.or_any_spell
    ):
        return None
    return requirement


class _Adjectives:
    """The run of adjectives in front of the noun of a "target ..." phrase."""

    def __init__(self) -> None:
        self.excluded_types: set[Type] = set()
        self.required_supertypes: set[Supertype] = set()
        self.excluded_supertypes: set[Supertype] = set()
        self.required_colors: set[Color] = set()
        self.excluded_colors: set[Color] = set()
        self.excluded_subtypes: set[str] = set()
        self.combat_states: set[CombatState] = set()
        self.excluded_combat_states: set[CombatState] = set()
        self.must_be_tapped: bool | None = None
        self.must_be_token: bool | None = None
        self.color_count: str | None = None
        self.historic = False
        self.excludes_source = False
        self.read = 0

    def take(self, raw: str, word: str) -> bool:
        """Read one word as an adjective, or say it is not one.

        `raw` keeps its original capitalization alongside `word`'s lower-cased
        form - `_negated_subtype`, like `_is_bare_subtype_word` it is built
        on, needs the capitalization to tell "non-Human" (CR 205.3m,
        CR 702.140a's own mutate wording) apart from an ordinary lower-case
        English word that merely starts with "non-".
        """
        if word in _TAPPED_ADJECTIVES:
            self.must_be_tapped = _TAPPED_ADJECTIVES[word]
        elif word in _COMBAT_ADJECTIVES:
            self.combat_states.add(_COMBAT_ADJECTIVES[word])
        elif (excluded_combat := _negated_combat_state(word)) is not None:
            self.excluded_combat_states.add(excluded_combat)
        elif word == "token":
            self.must_be_token = True
        elif word == "nontoken":
            self.must_be_token = False
        elif word in {"another", "other"}:
            self.excludes_source = True
        elif word in _SUPERTYPE_NOUNS:
            self.required_supertypes.add(_SUPERTYPE_NOUNS[word])
        elif word in _COLOR_WORDS:
            self.required_colors.add(_COLOR_WORDS[word])
        elif word in {"multicolored", "monocolored", "colorless"}:
            self.color_count = word
        elif word == "historic":
            self.historic = True
        elif (excluded := _negated_type(word)) is not None:
            self.excluded_types.add(excluded)
        elif (excluded_super := _negated_supertype(word)) is not None:
            self.excluded_supertypes.add(excluded_super)
        elif (excluded_color := _negated_color(word)) is not None:
            self.excluded_colors.add(excluded_color)
        elif (excluded_subtype := _negated_subtype(raw, word)) is not None:
            self.excluded_subtypes.add(excluded_subtype)
        else:
            return False
        self.read += 1
        return True


def _negated_type(word: str) -> Type | None:
    """The card type a "non-" adjective rules out, if it is one.

    The CR spells no rule for the prefix; it uses it - "nontoken permanent"
    (CR 110.3), "noncreature spell" (CR 702.108a) - and CR 300.1 is the list of
    card types it can be put in front of.
    """
    if not word.startswith("non") or len(word) <= 3:
        return None
    return _TYPE_NOUNS.get(word[3:].lstrip("-"))


def _negated_combat_state(word: str) -> CombatState | None:
    """The combat state a "non-" adjective rules out, if it is one -
    "nonattacking" (Spider-Man, To the Rescue), "nonblocking" - read the
    identical way `_negated_type`/`_negated_supertype` already are, against
    `_COMBAT_ADJECTIVES` rather than `_TYPE_NOUNS`/`_SUPERTYPE_NOUNS`."""
    if not word.startswith("non") or len(word) <= 3:
        return None
    return _COMBAT_ADJECTIVES.get(word[3:].lstrip("-"))


def _negated_supertype(word: str) -> Supertype | None:
    """The supertype a "non-" adjective rules out, if it is one.

    Read the same way `_negated_type` reads a card type - "nonbasic land"
    (CR 205.4c) is the pool's shape - but against `_SUPERTYPE_NOUNS`
    (CR 205.4a) rather than `_TYPE_NOUNS`, since a supertype is not a card
    type (CR 205.4b: "an object's supertype is independent of its card type").
    """
    if not word.startswith("non") or len(word) <= 3:
        return None
    return _SUPERTYPE_NOUNS.get(word[3:].lstrip("-"))


def _negated_color(word: str) -> Color | None:
    """The color a "non-" adjective rules out, if it is one - "target
    nonblack creature" (Cradle to Grave), "target nonwhite creature"
    (Sunlance). Read the identical way `_negated_type`/`_negated_supertype`
    already are, against `_COLOR_WORDS` (CR 105.1's five colors) rather than
    `_TYPE_NOUNS`/`_SUPERTYPE_NOUNS`.

    CR 105.2's "An object can be one or more of the five colors, or it can be
    no color at all" is why this is a genuinely different check from
    `required_colors`' own membership test, not merely its logical opposite
    spelled differently: a colorless object satisfies *neither* a required
    color nor an excluded one, since it has none of any color to begin with.
    `TargetRequirement.rejects`' own set-intersection checks for both fields
    already get this right without special-casing colorless at all - an
    empty `_current_colors(target, game)` set intersects nothing, so the
    excluded-color check never rejects it.
    """
    if not word.startswith("non") or len(word) <= 3:
        return None
    return _COLOR_WORDS.get(word[3:].lstrip("-"))


def _negated_subtype(raw: str, word: str) -> str | None:
    """The CR 205.3m creature type a "non-" adjective rules out, if it is one -
    "Target non-Human creature you control" (Fight as One's own second mode;
    CR 702.140a's mutate reminder text: "targets a non-Human creature").

    Read the same "non-" prefix `_negated_type`/`_negated_supertype`/
    `_negated_color` already read for their own vocabularies, but against
    `_is_bare_subtype_word`'s capitalized-word check rather than a small
    closed dictionary - CR 205.3m's creature-type list runs into the
    hundreds, the same reason `_is_bare_subtype_word` itself does not
    enumerate one. The difference from its three siblings is the hyphen:
    Oracle fuses a negated card type, supertype, or color directly onto the
    prefix ("noncreature", "nonbasic", "nonblack"), but keeps a negated
    creature type hyphenated ("non-Human", "non-Zombie") the same way a
    *positive* hyphenated creature type is (Assembly-Worker) - so this reads
    `raw` after splitting on that hyphen, not `word` after stripping "non"
    the way its siblings do.
    """
    if not word.startswith("non-") or len(raw) <= 4:
        return None
    tail_raw = raw[4:]
    tail_word = word[4:]
    if _is_bare_subtype_word(tail_raw, tail_word):
        return tail_word
    return None


def _read_adjectives(raw_words: list[str], words: list[str]) -> tuple[_Adjectives, int]:
    """The leading adjectives, and where the noun starts after them.

    "attacking or blocking creature" is one run of two: the conjunction is
    swallowed only when an adjective follows it, so "creature or land" is still
    two nouns rather than one adjective and a noun.

    A comma joins a run the same way: Skyclave Apparition's "nonland, nontoken
    permanent" and Thief of Existence's "noncreature, nonland permanent" are
    each two restrictions on one noun (CR 110.4's permanent types, CR 111.1's
    tokens), and every one of them applies - the adjectives accumulate on
    `_Adjectives` exactly as they do with no comma between them.

    `raw_words` runs parallel to `words`, index for index, keeping the
    original capitalization `_Adjectives.take` needs to read a negated
    creature type ("non-Human") apart from an ordinary word - the same
    `raw_words`/`words` split `_read_phrase`'s own noun-reading loop already
    keeps, for the identical reason.
    """
    adjectives = _Adjectives()
    index = 0
    while index < len(words) and adjectives.take(raw_words[index], words[index]):
        index += 1
        joined = index + 1
        if (
            joined < len(words)
            and words[index] in {"or", "and", ","}
            and _is_adjective(words[joined])
        ):
            index += 1
        elif (
            joined + 1 < len(words)
            and words[index] == ","
            and words[joined] in {"or", "and"}
            and _is_adjective(words[joined + 1])
        ):
            # The serial comma closing a list of three or more: Offspring's
            # Revenge's "red, white, or black creature card" (CR 105.2's
            # colors, any one of which satisfies the requirement).
            index += 2
    return adjectives, index


def _is_adjective(word: str) -> bool:
    return (
        word in _TAPPED_ADJECTIVES
        or word in _COMBAT_ADJECTIVES
        or word in {"token", "nontoken", "another", "other"}
        or word in _SUPERTYPE_NOUNS
        or word in _COLOR_WORDS
        or word in {"multicolored", "monocolored", "colorless"}
        or _negated_type(word) is not None
        or _negated_supertype(word) is not None
        or _negated_color(word) is not None
    )


def _only_known_clauses(rest: str) -> bool:
    """Whether what follows an adjective run is a clause this parser reads.

    Nothing at all counts, and so does a control clause or a zone clause. An
    unread word there means an unread requirement, not a bare permanent.
    """
    if not rest:
        return True
    control = _CONTROL_CLAUSE.match(rest)
    if control is not None and control.end() == len(rest):
        return True
    zone = _ZONE_CLAUSE.match(rest)
    return zone is not None and zone.end() == len(rest)


#: CR 202.3 (mana value), CR 208.1/208.2 (power/toughness): the three
#: characteristics the pool ever compares a target against. Read off the
#: plain word rather than a rule number for "power or toughness" itself -
#: there is no CR rule for that disjunction, only for each characteristic on
#: its own.
_COMPARISON_ATTR = {
    "mana value": ComparisonAttribute.MANA_VALUE,
    "converted mana cost": ComparisonAttribute.MANA_VALUE,
    "power or toughness": ComparisonAttribute.POWER_OR_TOUGHNESS,
    "power": ComparisonAttribute.POWER,
    "toughness": ComparisonAttribute.TOUGHNESS,
}

#: A cheap pre-check: does this clause even *attempt* a comparison? Requires
#: the attribute word to be directly followed (past an optional "is") by a
#: number, an unbound X, or a comparison word. Without this, "target
#: creature's power and toughness" (Twisted Image swaps them, it does not
#: compare them) would be mistaken for an unreadable comparison and the whole
#: profile would fail to parse for a card that carries no restriction at all -
#: `_COMPARISON_CLAUSE` needs a real number or "X" nearby to match, but
#: "power and toughness" has neither, so this gate is what tells "no
#: comparison here" apart from "a comparison this parser cannot finish
#: reading" (Prismatic Ending).
_COMPARISON_ATTEMPT = re.compile(
    r"\b(?:mana value|converted mana cost|power|toughness)\b"
    r"\s+(?:is\s+)?(?:or\s+)?(?:x\b|\d+\b|equal\b|less\b|greater\b)",
    re.IGNORECASE,
)

#: Every count a comparison may name in place of a printed number, keyed by the
#: named group `_COMPARISON_CLAUSE` captures it with. See `ComparisonCount` for
#: why only counts knowable at CR 601.2c may live here.
_COMPARISON_COUNTS = {
    "controllers_graveyard": ComparisonCount.CONTROLLERS_GRAVEYARD_CARDS,
    "source_loyalty": ComparisonCount.SOURCE_LOYALTY,
    "colors_spent_source": ComparisonCount.SOURCE_COLORS_SPENT,
}

#: The comparison itself, once `_COMPARISON_ATTEMPT` says one is being made.
#: Order inside the alternation matters: "N or less/greater" and the spelled-
#: out "less/greater than or equal to N" are tried before the bare "N" so a
#: qualified number is never misread as an unqualified one. The strict
#: "less/greater than `<Name>`'s loyalty" branch (Nahiri, the Unforgiving) is
#: tried after the "... or equal to ..." branches for the same reason, even
#: though the two cannot actually collide (nothing here ends in "'s
#: loyalty" for a plain number): `.+?` is non-greedy so it stops at the
#: *first* "'s loyalty" it finds, never swallowing a trailing clause past it
#: (see `ComparisonCount.SOURCE_LOYALTY`'s own docstring for why the name
#: itself is never checked against anything).
_COMPARISON_CLAUSE = re.compile(
    r"\b(?P<attr>mana value|converted mana cost|power or toughness|power|toughness)\b"
    r"\s+(?:is\s+)?"
    r"(?:"
    r"(?P<num_or>x|\d+)\s+or\s+(?P<dir>less|greater)"
    r"|(?P<count_dir>less|greater) than or equal to the number of "
    r"(?:cards in (?P<controllers_graveyard>its controller'?s? graveyard)"
    r"|colors of mana spent to cast (?P<colors_spent_source>this creature|this spell|it))\b"
    r"|less than or equal to\s+(?P<le_num>x|\d+)\b"
    r"|greater than or equal to\s+(?P<ge_num>x|\d+)\b"
    r"|(?P<strict_dir>less|greater) than (?P<source_loyalty>.+?)'s loyalty\b"
    r"|equal to\s+(?P<eq_num>x|\d+)\b"
    r"|(?P<bare_num>x|\d+)\b"
    r")",
    re.IGNORECASE,
)

#: `_COMPARISON_CLAUSE`'s pattern, for a dispatcher that has to accept exactly
#: the comparisons this reader enforces (`machines/effects.py`'s counterspell
#: predicate) rather than keep a second, narrower copy of the grammar.
COMPARISON_CLAUSE_PATTERN = _COMPARISON_CLAUSE.pattern

#: "where X is <expression>" after an X comparison (CR 107.3c) - Spellstutter
#: Sprite's "..., where X is the number of Faeries you control".
_WHERE_X_DEFINITION = re.compile(r"(?:,\s*)?\bwhere\s+x\s+is\s+(?P<expression>.+)$", re.IGNORECASE)

#: Returned by `_extract_comparison` when a comparison was clearly attempted
#: but this parser could not finish reading it - the whole "target ..." phrase
#: has to fail rather than silently keep going with no restriction at all.
_COMPARISON_UNREADABLE = object()


def _extract_comparison(
    rest: str,
) -> (
    tuple[
        ComparisonAttribute | None,
        ComparisonOperator | None,
        int | None,
        ComparisonCount | None,
        str,
    ]
    | object
):
    """Read a trailing "with mana value N or less" clause out of `rest`.

    Returns `(attribute, operator, value, count, remaining_rest)` - the first
    four fields are `None` and `remaining_rest` is `rest` unchanged when there
    is no comparison at all. `value` is `None` on its own when the comparison
    is real but its number cannot be pinned down yet: an unbound X (CR 107.3 -
    "target creature with mana value X or less" read before X is announced) or
    a bare "with mana value X" (Tamiyo, Compleated Sage; Postmortem Lunge),
    which means "equal to X" (CR 107.1a's ordinary use of a variable).

    `count` is set instead, with `value` left `None`, when the card names a
    count in place of a number - Drown in the Loch's "less than or equal to the
    number of cards in its controller's graveyard". That is a real targeting
    restriction whose bound is only knowable from the game, so it is carried on
    the requirement as a `ComparisonCount` and evaluated at every check rather
    than fixed here.

    Returns the `_COMPARISON_UNREADABLE` sentinel when `_COMPARISON_ATTEMPT`
    found the start of a comparison this function could not finish reading.
    The caller has to fail the whole phrase in that case (`understood=False`)
    rather than read past the clause: a restriction the parser cannot evaluate
    must never be dropped silently.
    """
    if not _COMPARISON_ATTEMPT.search(rest):
        return None, None, None, None, rest
    match = _COMPARISON_CLAUSE.search(rest)
    if match is None:
        return _COMPARISON_UNREADABLE
    attribute = _COMPARISON_ATTR[match.group("attr").lower()]
    if match.group("count_dir") is not None:
        operator = (
            ComparisonOperator.LESS_OR_EQUAL
            if match.group("count_dir").lower() == "less"
            else ComparisonOperator.GREATER_OR_EQUAL
        )
        count = next(
            kind
            for group, kind in _COMPARISON_COUNTS.items()
            if match.group(group) is not None  # noqa: B023 - `match` is not reassigned
        )
        return attribute, operator, None, count, rest[: match.start()] + rest[match.end() :]
    if match.group("strict_dir") is not None:
        # "less/greater than `<Name>`'s loyalty" (Nahiri, the Unforgiving) -
        # a strict inequality (CR 107.1a's plain English "less than", not "or
        # less") against a count this parser reads off the game rather than
        # off the card, exactly like `count_dir` just above; see
        # `ComparisonOperator.LESS_THAN`'s own docstring for why it is a
        # distinct operator rather than `LESS_OR_EQUAL` with the bound
        # shifted by one.
        operator = (
            ComparisonOperator.LESS_THAN
            if match.group("strict_dir").lower() == "less"
            else ComparisonOperator.GREATER_THAN
        )
        count = next(
            kind
            for group, kind in _COMPARISON_COUNTS.items()
            if match.group(group) is not None  # noqa: B023 - `match` is not reassigned
        )
        return attribute, operator, None, count, rest[: match.start()] + rest[match.end() :]
    if match.group("num_or") is not None:
        operator = (
            ComparisonOperator.LESS_OR_EQUAL
            if match.group("dir").lower() == "less"
            else ComparisonOperator.GREATER_OR_EQUAL
        )
        token = match.group("num_or")
    elif match.group("le_num") is not None:
        operator, token = ComparisonOperator.LESS_OR_EQUAL, match.group("le_num")
    elif match.group("ge_num") is not None:
        operator, token = ComparisonOperator.GREATER_OR_EQUAL, match.group("ge_num")
    elif match.group("eq_num") is not None:
        operator, token = ComparisonOperator.EQUAL, match.group("eq_num")
    else:
        operator, token = ComparisonOperator.EQUAL, match.group("bare_num")
    value = None if token.lower() == "x" else int(token)
    remaining = rest[: match.start()] + rest[match.end() :]
    return attribute, operator, value, None, remaining


#: Prismatic Ending's converge clause: "Converge — Exile target nonland
#: permanent **if its mana value is less than or equal to the number of colors
#: of mana spent to cast this spell**." Read out of the way rather than turned
#: into a comparison, because it is not one.
#:
#: CR 601.2c announces targets; CR 601.2f determines the total cost and
#: CR 601.2h pays it, both afterwards. So at the moment this spell's target is
#: chosen there is no "number of colors of mana spent" yet - the clause cannot
#: restrict what may be targeted, and CR 115.10a's line is the same one from
#: the other side: only what the word "target" marks is a target. The target
#: here is the plain "target nonland permanent", which is exactly what this
#: parser must report so that CR 601.2c refuses a *land*; the mana-value
#: condition is judged once, at resolution, by `machines/effects.py`'s own
#: converge parser off `CastRecord.mana_spent`.
#:
#: Before this, `_COMPARISON_ATTEMPT` saw "mana value ... less" here, found no
#: digit for `_COMPARISON_CLAUSE`, and failed the whole phrase closed - which
#: meant `understood=False` and *no* targeting check at all, so a land was a
#: legal announcement. Converge is an ability word (CR 207.2c); the "Converge —"
#: prefix itself needs no handling here, as nothing before the word "target" is
#: read as part of the noun phrase.
_COLORS_OF_MANA_SPENT_CONDITION = re.compile(
    r"\bif its mana value is less than or equal to the number of colors of mana "
    r"spent to cast this spell\b",
    re.IGNORECASE,
)


#: CR 613.4b: "has base power and toughness N/N" sets the target's own base
#: power and toughness - Multiply by Zero's "Target creature **has base power
#: and toughness 0/0** until end of turn" and Perfected Theory's own two
#: modes. This is the resolving effect itself, not a restriction on what may
#: be targeted, and it sits directly after the noun with nothing else between
#: (no "with"/"you control" clause a real restriction would need) - but
#: `_COMPARISON_ATTEMPT` cannot tell that apart from "target creature with
#: toughness 0" on sight, because tokenizing "0/0" ahead of this reader drops
#: the "/" and leaves "toughness" directly in front of a bare digit, which is
#: exactly `_COMPARISON_CLAUSE`'s own shape for a real bound. Stripped out
#: whole - the whole tail is the effect's own verb phrase, not a further
#: target restriction - before the comparison scan ever sees it, the same way
#: `_COLORS_OF_MANA_SPENT_CONDITION` is read out of the way just above.
#:
#: The same verb phrase follows a type change too - Metamorphic Blast's
#: "target creature **becomes a white Rabbit with base power and toughness
#: 0/1**" - where "becomes" already marks it as the effect (CR 205.1a), never
#: a restriction on what may be targeted.
_SETS_BASE_POWER_TOUGHNESS_EFFECT = re.compile(
    r"\b(?:has|becomes\b.*?\bwith) base power and toughness\b.*$", re.IGNORECASE
)


#: "Choose two target creatures **controlled by different players**" (Run Away
#: Together). Anchored at the start of what is left after the noun, where an
#: ordinary "you control" clause would sit - the two are alternatives, and this
#: one restricts the targets against each other rather than against the caster.
_DIFFERENT_CONTROLLERS_RE = re.compile(r"^controlled by different players\b", re.IGNORECASE)


def _extract_distinct_controllers(rest: str) -> tuple[bool, str]:
    """Read a "controlled by different players" clause out of `rest`, or leave
    it untouched when there is none - see `TargetRequirement.distinct_controllers`."""
    match = _DIFFERENT_CONTROLLERS_RE.match(rest)
    if match is None:
        return False, rest
    return True, rest[match.end() :].strip()


#: "two target nonland permanents **that share a card type**" (Burglar's
#: Plot, Shifting Loyalties) - see `TargetRequirement.share_a_card_type`.
_SHARE_A_CARD_TYPE_RE = re.compile(r"^that share a card type\b", re.IGNORECASE)


def _extract_share_a_card_type(rest: str) -> tuple[bool, str]:
    """Read a "that share a card type" clause out of `rest`, or leave it
    untouched when there is none."""
    match = _SHARE_A_CARD_TYPE_RE.match(rest)
    if match is None:
        return False, rest
    return True, rest[match.end() :].strip()


#: "with total mana value `<n>` or less" - see
#: `TargetRequirement.total_mana_value_at_most`.
_TOTAL_MANA_VALUE_RE = re.compile(
    r"^with total mana value (?P<n>\d+|[a-z]+) or less\b", re.IGNORECASE
)


def _extract_total_mana_value(rest: str) -> tuple[int | None, str]:
    """Read a "with total mana value N or less" clause out of `rest`, or leave
    it untouched when there is none."""
    match = _TOTAL_MANA_VALUE_RE.match(rest)
    if match is None:
        return None, rest
    raw = match.group("n")
    bound = int(raw) if raw.isdigit() else parse_count(raw, article=False)
    if bound is None:
        return None, rest
    return bound, rest[match.end() :].strip()


def _computed_mana_value(target: Any, game: Any) -> float | None:
    """A target's mana value for `total_mana_value_at_most`: the computed one
    for a permanent (a copy effect changes it, CR 707.2), the printed one
    elsewhere, `None` for a target without one (a bare id, a player)."""
    mana_value = getattr(target, "mana_value", None)
    if mana_value is None:
        return None
    if game is not None and getattr(target, "zone", None) is Zone.BATTLEFIELD:
        characteristics_of = getattr(game, "characteristics_of", None)
        if characteristics_of is not None:
            return float(characteristics_of(target).mana_value)
    return float(mana_value)


def _computed_card_types(target: Any, game: Any) -> frozenset[Type] | None:
    """A target's card types for `share_a_card_type`: the computed ones for a
    permanent on the battlefield (CR 613.1d), the printed ones elsewhere, or
    `None` for a target whose types cannot be read (a bare id, a player)."""
    types = getattr(target, "types", None)
    if types is None:
        return None
    if game is not None and getattr(target, "zone", None) is Zone.BATTLEFIELD:
        characteristics_of = getattr(game, "characteristics_of", None)
        if characteristics_of is not None:
            return frozenset(characteristics_of(target).types)
    return frozenset(types)


#: A "with `<keyword>`" clause modifying the noun - "target creature you
#: don't control with flying" (Kraul Harpooner). Deliberately a small,
#: explicit vocabulary rather than "with (?P<keyword>.+)": an unrecognised
#: "with" clause (a counter, "with the highest power", CR 205.2a shapes this
#: reader is not meant to reach) is left exactly as unenforced as it always
#: was, rather than newly failing the whole phrase closed - only a
#: *recognised* keyword gains enforcement here.
#:
#: Not anchored to the end of the string: Kraul Harpooner's own "with flying"
#: happens to sit at a sentence boundary ("...with flying. This creature
#: gets..."), but Tomik, Orzhov Lawmage's "target creature with a +1/+1
#: counter on it gains flying until end of turn." keeps the restriction and
#: the resolving verb in one sentence, so a trailing `$` never matched there
#: at all - `_extract_required_keyword`/`_extract_required_counter_kind`
#: below splice the clause out of wherever it sits instead.
_WITH_KEYWORD_RE = re.compile(
    r"\bwith\s+(?P<keyword>flying|reach|trample|menace|haste|vigilance|"
    r"first strike|double strike|defender|deathtouch|lifelink)\b",
    re.IGNORECASE,
)

#: "with a `<kind>` counter on it" - Tomik, Orzhov Lawmage's own "target
#: creature with a +1/+1 counter on it". `_WITH_KEYWORD_RE`'s own docstring
#: names a counter clause as exactly the "with" shape it deliberately leaves
#: unread; this is that shape's own reader, CR 122.1's counter-kind grammar
#: (a bare word, or one of the two +N/-N power/toughness spellings) rather
#: than "with `<word>`" in general. See `_WITH_KEYWORD_RE`'s docstring for why
#: this is not anchored to the end of the string either.
_WITH_COUNTER_RE = re.compile(
    r"\bwith an? (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|them)\b", re.IGNORECASE
)

#: A small, deliberately narrow vocabulary of resolution verbs that always
#: mark the end of a target's own restrictive clauses and the start of what
#: the ability actually does to it - Tomik's "gains", a mass-pump's "gets",
#: a land turning into a creature's "becomes" (Jolrael, Voice of Zhalfir's
#: own shape), "loses". Confining a "with `<restriction>`" search to the text
#: *before* the first one of these, rather than the whole remaining sentence,
#: is what tells Tomik's "target creature with a +1/+1 counter on it gains
#: flying ..." (the counter clause restricts the target) apart from
#: Jolrael's "target land ... becomes ... a Bird creature with flying and
#: haste ..." (the keyword there describes what the target *becomes*, not a
#: restriction on what may be targeted) - the same distinction CR 608.2c's
#: printed order already draws between an instruction's target and what it
#: goes on to do. Without this cut, dropping `_WITH_KEYWORD_RE`'s old
#: end-anchor made "with flying" match Jolrael's *effect* text and wrongly
#: refuse every land without flying already on it as an illegal target.
#:
#: "`<verb>` `<destination>` the battlefield" joins the same vocabulary for
#: the identical reason, one preposition later: Persist's "Return target
#: nonlegendary creature card from your graveyard **to the battlefield**
#: with a -1/-1 counter on it." and Daydream's "..., then return that card
#: **to the battlefield** under its owner's control with a +1/+1 counter on
#: it." both put their own counter clause after this phrase, describing the
#: counter the return is about to place - CR 122.2 has already stripped any
#: the card carried before it changed zones, so a graveyard or exiled card
#: never has one to be restricted by. No target's own restrictive clause in
#: the pool ever contains "to the battlefield" (a target is described by what
#: it *is*, never by where an effect is about to move it), so this is a safe
#: general cutoff, not a card-specific one - proven on Makeshift Mannequin's
#: differently-worded, differently-named ("mannequin") counter of the same
#: shape.
_TARGET_CLAUSE_VERB_RE = re.compile(
    r"\b(?:gains?|gets?|becomes?|loses?|(?:to|onto)\s+the\s+battlefield)\b", re.IGNORECASE
)


def _before_target_clause_verb(text: str) -> str:
    """The prefix of `text` up to (not including) the first resolution verb
    `_TARGET_CLAUSE_VERB_RE` recognises - the scope a "with `<restriction>`"
    search is confined to, so it never reaches into what the ability *does*
    once its target is chosen."""
    match = _TARGET_CLAUSE_VERB_RE.search(text)
    return text if match is None else text[: match.start()]


def _extract_required_keyword(rest: str) -> tuple[str | None, str]:
    """Read a "with `<keyword>`" clause out of `rest` (CR 702), spliced out
    from wherever it sits ahead of the resolving verb, or leave `rest`
    untouched when there is none - see `_WITH_KEYWORD_RE`."""
    match = _WITH_KEYWORD_RE.search(_before_target_clause_verb(rest))
    if match is None:
        return None, rest
    remainder = (rest[: match.start()] + " " + rest[match.end() :]).strip()
    return match.group("keyword").lower(), remainder


def _extract_required_counter_kind(rest: str) -> tuple[str | None, str]:
    """Read a "with a `<kind>` counter on it" clause out of `rest`
    (CR 122.1), spliced out from wherever it sits ahead of the resolving
    verb, or leave `rest` untouched when there is none - see
    `_WITH_COUNTER_RE`. `kind` is normalised the identical way `machines/
    effects._counter_kind` already normalises a printed counter word:
    lower-cased, the two power/toughness spellings kept literal."""
    match = _WITH_COUNTER_RE.search(_before_target_clause_verb(rest))
    if match is None:
        return None, rest
    remainder = (rest[: match.start()] + " " + rest[match.end() :]).strip()
    return match.group("kind").lower(), remainder


#: "target permanent that's one or more colors" (Devourer of Destiny, Ugin,
#: Eye of the Storms) - CR 105.2's presence check, the negation of CR 105.2c's
#: colorless, read as a trailing relative clause rather than a leading
#: adjective (unlike "multicolored"/"monocolored"/"colorless", which always
#: sit in front of the noun). "that's" is the only contraction the pool's
#: printings use; a hypothetical plural "that are one or more colors" is a
#: different noun ("permanents", All Is Dust's own dedicated parser in
#: `machines/effects.py` already reads that shape) and is deliberately not
#: matched here.
_COLOR_PRESENCE_RE = re.compile(r"\bthat'?s\s+one\s+or\s+more\s+colors\b", re.IGNORECASE)


def _extract_color_presence(rest: str) -> tuple[bool, str]:
    """Read a trailing "that's one or more colors" clause out of `rest`
    (CR 105.2), or leave it untouched when there is none."""
    match = _COLOR_PRESENCE_RE.search(rest)
    if match is None:
        return False, rest
    return True, (rest[: match.start()] + rest[match.end() :]).strip()


#: "target creature or planeswalker **that's green or blue**" (Refute
#: Destiny), "target creature or planeswalker **that's blue or red**"
#: (Terminal Criticism) - CR 105.1's five colors, read as a trailing relative
#: clause the identical way `_COLOR_PRESENCE_RE` reads "that's one or more
#: colors" just above, rather than as a leading adjective
#: (`_Adjectives.required_colors`'s own "target black creature" shape): the
#: restriction here sits after a *compound* noun ("creature or planeswalker")
#: and applies to the whole disjunction at once, not to either noun alone.
#: One color alone ("that's green") is read the identical way; the trailing
#: "(?:,?\s+or\s+...)?" group is simply absent then.
_COLOR_DISJUNCTION_RE = re.compile(
    r"\bthat'?s\s+(?P<colors>(?:white|blue|black|red|green)"
    r"(?:,\s*(?:white|blue|black|red|green))*"
    r"(?:,?\s+or\s+(?:white|blue|black|red|green))?)\b",
    re.IGNORECASE,
)


def _extract_color_disjunction(rest: str) -> tuple[frozenset[Color], str]:
    """Read a trailing "that's `<color>`[, `<color>`...] or `<color>`" clause
    out of `rest` (CR 105.1), or leave it untouched (returning an empty set)
    when there is none - see `_COLOR_DISJUNCTION_RE`. The returned colors feed
    `TargetRequirement.required_colors`, whose membership check is already an
    "any of these" disjunction - exactly what "green or blue" means."""
    match = _COLOR_DISJUNCTION_RE.search(rest)
    if match is None:
        return frozenset(), rest
    words = re.findall(r"[a-z]+", match.group("colors").lower())
    colors = frozenset(_COLOR_WORDS[word] for word in words if word in _COLOR_WORDS)
    return colors, (rest[: match.start()] + rest[match.end() :]).strip()


#: "target creature that attacked this turn" (Hexhaven Dueling Arena) - a
#: trailing relative clause read the same way `_COLOR_PRESENCE_RE` reads
#: "that's one or more colors": stripped out, and remembered as a flag rather
#: than left for the rest of the parser to choke on.
_ATTACKED_THIS_TURN_RE = re.compile(r"\bthat attacked this turn\b", re.IGNORECASE)


def _extract_attacked_this_turn(rest: str) -> tuple[bool, str]:
    """Read a trailing "that attacked this turn" clause out of `rest`, or
    leave it untouched when there is none."""
    match = _ATTACKED_THIS_TURN_RE.search(rest)
    if match is None:
        return False, rest
    return True, (rest[: match.start()] + rest[match.end() :]).strip()


#: "target creature you control that's attacking alone" (Crowd of True
#: Believers) - the identical trailing-relative-clause shape `_ATTACKED_
#: THIS_TURN_RE` already reads, for CR 506.5's live "alone" state instead of
#: a per-turn historical fact. "That's"/"that is"/"who's"/"who is" all
#: introduce it; every printing in the pool uses the contraction, but the
#: full form costs nothing extra to accept.
_ATTACKING_ALONE_RE = re.compile(r"\bthat'?s attacking alone\b", re.IGNORECASE)


def _extract_attacking_alone(rest: str) -> tuple[bool, str]:
    """Read a trailing "that's attacking alone" clause out of `rest`, or
    leave it untouched when there is none."""
    match = _ATTACKING_ALONE_RE.search(rest)
    if match is None:
        return False, rest
    return True, (rest[: match.start()] + rest[match.end() :]).strip()


#: "target creature that entered this turn" (Mabel, Valley Hero's trigger;
#: Gallia, the Merrymaker's activated ability) - a per-turn historical fact
#: ("this turn" always means the current turn, regardless of how many times
#: control of the permanent or of priority has changed; no single CR number
#: states this generally - CR 500.1's turn structure is the closest numbered
#: rule, and this comment does not claim it says more than that), read the
#: identical way `_ATTACKED_THIS_TURN_RE` reads its own "that
#: attacked this turn": stripped out here, enforced at
#: `_rejects_entered_this_turn` against the turn number `CardState.
#: turn_entered` already carries (`Game.turn.turn_number` is the "turn
#: history on `Game`" this checks it against - no separate per-turn set is
#: needed the way `Game.attacked_this_turn` is, since every permanent already
#: remembers the turn it arrived).
_ENTERED_THIS_TURN_RE = re.compile(r"\bthat entered this turn\b", re.IGNORECASE)


def _extract_entered_this_turn(rest: str) -> tuple[bool, str]:
    """Read a trailing "that entered this turn" clause out of `rest`, or
    leave it untouched when there is none."""
    match = _ENTERED_THIS_TURN_RE.search(rest)
    if match is None:
        return False, rest
    return True, (rest[: match.start()] + rest[match.end() :]).strip()


#: "target creature that crewed it this turn" (Turtle Van) - the identical
#: trailing-relative-clause shape `_ATTACKED_THIS_TURN_RE`/`_ENTERED_THIS_
#: TURN_RE` already read, for CR 702.122b's own per-turn historical fact
#: instead: "it" is this ability's own source Vehicle (CR 201.5's "this"
#: self-reference, spelled "it" for a non-legendary permanent the way
#: `machines/abilities.legendary_self_pronoun_normalized` already spells a
#: legendary one's own self-pronoun), enforced at `_rejects_crewed_this_
#: turn` against `source_id` rather than against a bare board-wide fact.
_CREWED_THIS_TURN_RE = re.compile(r"\bthat crewed it this turn\b", re.IGNORECASE)


def _extract_crewed_this_turn(rest: str) -> tuple[bool, str]:
    """Read a trailing "that crewed it this turn" clause out of `rest`, or
    leave it untouched when there is none."""
    match = _CREWED_THIS_TURN_RE.search(rest)
    if match is None:
        return False, rest
    return True, (rest[: match.start()] + rest[match.end() :]).strip()


_ALL_NOUNS = frozenset(_TYPE_NOUNS) | _PERMANENT_NOUNS | _PLAYER_NOUNS | _SPELL_NOUNS | _CARD_NOUNS
_CONTROLLERS = {
    "you control": ControllerRestriction.YOU,
    "you don't control": ControllerRestriction.NOT_YOU,
    "an opponent controls": ControllerRestriction.OPPONENT,
    "your opponents control": ControllerRestriction.OPPONENT,
    "that player controls": ControllerRestriction.EVENT_PLAYER,
    "defending player controls": ControllerRestriction.DEFENDING_PLAYER,
    "that player or that planeswalker's controller controls": (
        ControllerRestriction.PRIOR_TARGET_PLAYER
    ),
}
