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

from pydantic import BaseModel, ConfigDict

from magic_cards_model.phrases import with_indefinite_article

from ..models.card import Card, Color, Supertype, Type
from ..models.card_state import CardState, ExileMarker, TargetRef
from ..models.zone import Zone
from ..serialization import SortedFrozenSet
from .abilities import keyword_abilities
from .combat import has_keyword
from .layers import BASIC_LAND_TYPES
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
    """ "or less", "or greater", or a bare equality (CR 107.1a's ordinary numbers)."""

    LESS_OR_EQUAL = "le"
    GREATER_OR_EQUAL = "ge"
    EQUAL = "eq"


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


class TargetRequirement(BaseModel):
    """One "target ..." the spell asks for, and what satisfies it."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    count: int = 1
    """The most targets this requirement takes. Ignored when `unbounded`."""
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

    allows_cards: bool = True
    allows_players: bool = False
    allows_abilities: bool = False
    """True for "target activated or triggered ability" (CR 115.2, CR 113.1c)."""
    opponent_only: bool = False
    zones: SortedFrozenSet[Zone] = frozenset({Zone.BATTLEFIELD})
    controller: ControllerRestriction = ControllerRestriction.ANY
    must_be_tapped: bool | None = None
    excludes_source: bool = False
    """True for "target *other* ..." / "*another* target ...": the permanent
    the ability or spell is on cannot be its own target. `knowledge_search`
    found no single numbered CR rule defining "another"/"other" this session;
    this is read off the plain-English word, the same way `must_be_tapped` is
    read off "tapped" rather than off a rule number."""
    or_any_spell: bool = False
    """True for a noun list whose last item is a bare "spell" reached across an
    "or" - Aang, Swift Savior's "airbend up to one other **target creature or
    spell**".

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

    required_keyword: str | None = None
    """"with flying" in "target creature you don't control with flying"
    (Kraul Harpooner) - a trailing keyword-ability clause, read off the same
    closed CR 702 evasion/combat vocabulary `machines/combat.py::Keyword`
    already speaks. Only a small, explicitly named set is read
    (`_WITH_KEYWORD_RE`) rather than any "with <word>" at all: an unrecognised
    "with" clause is left exactly as before this field existed - silently
    unenforced - so a card this narrow reader does not know about does not
    regress from "ignored" to "the whole targeting text refuses to parse"."""

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
        """
        if getattr(target, "is_ability", False):
            return self._rejects_ability(target, caster)
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

    def _rejects_ability(self, target: Any, caster: str) -> str | None:
        """CR 113.1c: an ability on the stack is an object, and can be targeted.

        CR 115.2 only lets a spell reach it when the spell says so, so a
        requirement that did not read "target ... ability" refuses it. Mana
        abilities never get here: they do not use the stack and "can't be
        targeted, countered, or otherwise responded to" (CR 605.3b, CR 605.4a).
        """
        if not self.allows_abilities:
            return f"{self.phrase} cannot target {target.name}, which is an ability on the stack"
        target_count = self._rejects_target_count(target)
        if target_count is not None:
            return target_count
        controller = getattr(target, "controller", None)
        if self.controller is ControllerRestriction.ANY or controller is None:
            return None
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
        if self.or_any_spell and target.zone is Zone.STACK:
            # "... or spell" (CR 112.1: "A spell is a card on the stack"), the
            # second half of a two-kind noun list - see `or_any_spell`. Nothing
            # further to check: the phrase named no type for this half.
            return None
        if target.zone not in self.zones:
            wanted = " or ".join(sorted(zone.value for zone in self.zones))
            return (
                f"{self.phrase} needs a target in the {wanted}, "
                f"but {target.name} is in the {target.zone.value}"
            )
        if self.exiled_with_source:
            annotation = target.exile_annotation
            linked = (
                annotation is not None
                and annotation.marker is ExileMarker.IMPRINTED
                and source_id is not None
                and annotation.linked_permanent_id == source_id
            )
            if not linked:
                return (
                    f"{self.phrase} needs a card exiled with this permanent, "
                    f"and {target.name} is not one"
                )
        if self.card_types or self.excluded_card_types:
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
        if self.required_supertypes and not (
            set(self._current_supertypes(target, game)) & self.required_supertypes
        ):
            wanted = " or ".join(sorted(kind.value for kind in self.required_supertypes))
            return (
                f"{self.phrase} needs {with_indefinite_article(wanted)} permanent, "
                f"and {target.name} is not one"
            )
        if self.excluded_supertypes and (
            set(self._current_supertypes(target, game)) & self.excluded_supertypes
        ):
            unwanted = " or ".join(sorted(kind.value for kind in self.excluded_supertypes))
            return (
                f"{self.phrase} cannot target {with_indefinite_article(unwanted)} permanent, "
                f"and {target.name} is one"
            )
        if self.required_subtypes and not any(
            word.lower() in self.required_subtypes for word in self._current_subtypes(target, game)
        ):
            wanted = " or ".join(sorted(self.required_subtypes))
            return (
                f"{self.phrase} needs {with_indefinite_article(wanted)}, "
                f"and {target.name} is not one"
            )
        if self.required_colors and not (
            set(self._current_colors(target, game)) & self.required_colors
        ):
            wanted = " or ".join(sorted(color.name.lower() for color in self.required_colors))
            return (
                f"{self.phrase} needs {with_indefinite_article(wanted)} permanent, "
                f"and {target.name} is not one"
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
        comparison = self._rejects_comparison(target, game, caster)
        if comparison is not None:
            return comparison
        keyword = self._rejects_required_keyword(target, game)
        if keyword is not None:
            return keyword
        target_count = self._rejects_target_count(target)
        if target_count is not None:
            return target_count
        return self._rejects_controller(target, caster)

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
                f"{self.phrase} needs a creature with {self.required_keyword}, "
                f"and {target.name} is not"
            )
        return None

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
        if not self.combat_states:
            return None
        combat = getattr(game, "combat", None)
        if combat is None:
            return None
        if CombatState.ATTACKING in self.combat_states and combat.attack_by(target.id) is not None:
            return None
        blocking = CombatState.BLOCKING in self.combat_states
        if blocking and combat.attack_blocked_by(target.id) is not None:
            return None
        wanted = " or ".join(sorted(state.value for state in self.combat_states))
        return f"{self.phrase} needs a creature that is {wanted}, and {target.name} is not"

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
        self, target: CardState, game: Any, caster: str | None = None
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
        """
        if self.comparison_attribute is None:
            return None
        label = self.comparison_attribute.value.replace("_", " ")
        comparison_value = self.comparison_value
        if comparison_value is None and self.comparison_count is not None:
            comparison_value = self._counted_bound(target, game)
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

    def _counted_bound(self, target: CardState, game: Any) -> int | None:
        """The number a `comparison_count` names, right now, or None if it
        cannot be counted from what the caller supplied.

        Drown in the Loch's "the number of cards in its controller's graveyard"
        is the only shape so far. "Its controller" is the *target's* - CR 108.4a
        sends the question to the owner instead only for a card that has no
        controller at all (CR 109.4: "only objects on the stack or on the
        battlefield have a controller"), which is what `controller_or_owner`
        already answers for a card sitting in a graveyard or hand.

        None here means the restriction is unevaluable, and `_rejects_comparison`
        then refuses the target rather than waving it through - the same
        fail-closed choice it already makes for an unbound X.
        """
        if self.comparison_count is not ComparisonCount.CONTROLLERS_GRAVEYARD_CARDS:
            return None
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

    def _comparison_holds(self, value: float, comparison_value: int) -> bool:
        assert self.comparison_operator is not None
        if self.comparison_operator is ComparisonOperator.LESS_OR_EQUAL:
            return value <= comparison_value
        if self.comparison_operator is ComparisonOperator.GREATER_OR_EQUAL:
            return value >= comparison_value
        return value == comparison_value

    def _comparison_words(self, comparison_value: int) -> str:
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
        if self.controller is ControllerRestriction.ANY or controller is None:
            return None
        if self.controller is ControllerRestriction.YOU and controller != caster:
            return f"{self.phrase} needs a permanent {caster} controls, and {target.name} is not"
        not_yours = {ControllerRestriction.OPPONENT, ControllerRestriction.NOT_YOU}
        if self.controller in not_yours and controller == caster:
            return f"{self.phrase} cannot target {target.name}, which {caster} controls"
        return None

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


class Division(BaseModel):
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


class TargetingProfile(BaseModel):
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
        self, targets: list[Any], caster: str, game: Any = None, source_id: UUID | None = None
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
        read the spell's own targeting text.
        """
        self._check_protection(targets, game)

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

        if self.division is not None and len(targets) > self.division.amount:
            raise ValueError(
                f"too many targets to divide {self.division.amount} {self.division.what} among: "
                f"each target must receive at least one (CR 601.2d)"
            )

        self._fill_slots(targets, caster, game, source_id)

    def _check_protection(self, targets: list[Any], game: Any) -> None:
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
            refusal = refusal_of(target, self.source_card)
            if refusal is not None:
                raise ValueError(refusal)

    def _fill_slots(
        self, targets: list[Any], caster: str, game: Any = None, source_id: UUID | None = None
    ) -> None:
        """Match each chosen target to a requirement it satisfies (CR 601.2c)."""
        slots = [
            requirement
            for requirement in self.requirements
            if not requirement.unbounded
            for _ in range(requirement.count)
        ]
        unbounded = [r for r in self.requirements if r.unbounded]
        taken: dict[int, set[TargetRef]] = {}
        controllers: dict[int, set[str]] = {}

        for target in targets:
            reasons: list[str] = []
            for index, slot in enumerate(slots):
                reason = self._why_not(slot, target, caster, taken, game, source_id, controllers)
                if reason is None:
                    slots.pop(index)
                    break
                reasons.append(reason)
            else:
                for requirement in unbounded:
                    reason = self._why_not(
                        requirement, target, caster, taken, game, source_id, controllers
                    )
                    if reason is None:
                        break
                    reasons.append(reason)
                else:
                    raise ValueError("illegal target: " + "; ".join(dict.fromkeys(reasons)))

    @staticmethod
    def _why_not(
        requirement: TargetRequirement,
        target: Any,
        caster: str,
        taken: dict[int, set[TargetRef]],
        game: Any = None,
        source_id: UUID | None = None,
        controllers: dict[int, set[str]] | None = None,
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
_SINGLE_TARGET_PLACEHOLDER = "\x01"

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

_NUMBERS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

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
    r"^(?:that\s+)?(you\s+control|you\s+don't\s+control|an\s+opponent\s+controls|"
    r"your\s+opponents\s+control)\b",
    re.IGNORECASE,
)
_ZONE_CLAUSE = re.compile(
    r"\b(?:from|in)\s+(?:(?P<whose>your|a|an|any)\s+)?"
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
        else:
            profile = _parse(text)
            profile = _with_aura_target(card, profile)
        _CACHE[text] = profile
    # Stamped here, on every call, rather than baked into the cached entry:
    # this is the card whose qualities CR 702.16b compares against a
    # protected target, and it must be *this* call's `card`, never whichever
    # game's `Card` happened to populate the cache first.
    return profile.model_copy(update={"source_card": card})


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
_EARTHBEND = re.compile(r"\bearthbend\b", re.IGNORECASE)
_EARTHBEND_TARGET_TEXT = "target land you control"

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
    return _parse(_REMINDER.sub("", text), spell_only=False)


#: CR 207.2c's ability word, or CR 207.2d's flavor word, as Scryfall prints
#: it: a short capitalised phrase and an em dash in front of the real ability.
#: Both "have no special rules meaning", so they are cut before the line is
#: judged. Bounded to a few words so a sentence that merely contains an em
#: dash is left alone.
_ABILITY_WORD_PREFIX = re.compile(r"^[A-Z][^—\n]{0,40}?\s+—\s+")


def _spell_text(oracle_text: str) -> str:
    """The lines that are part of casting the spell, not of an ability.

    A triggered or activated ability on a permanent chooses its own targets
    when it goes on the stack, not when the permanent is cast, so those lines
    are dropped before anything is parsed.
    """
    lines: list[str] = []
    for line in oracle_text.splitlines():
        stripped = _REMINDER.sub("", line).strip()
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
        if not stripped or ":" in stripped or _TRIGGER.match(without_word):
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
    text = _SELF_COST_REDUCTION_LINE.sub("", text)
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
        amount = _count_word(word)
        return None if amount is None else Division(amount=amount, what="damage")
    amount = _count_word(match.group("counters").lower())
    if amount is None:
        return None
    return Division(amount=amount, what=f"{match.group('kind')} counters")


def _count_word(word: str) -> int | None:
    """A number written as a word, or as a digit once X has been substituted."""
    if word.isdigit():
        return int(word)
    return _NUMBERS.get(word)


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
    """
    words = [w for w in re.findall(r"[\w'-]+", prefix.lower()) if w not in _SOURCE_EXCLUDING]
    words = words[-3:]
    if words[-3:] == ["any", "number", "of"]:
        return 0, None, False
    if len(words) >= 3 and words[-3] == "up" and words[-2] == "to":
        if words[-1] == "x":
            return 0, None, True
        count = _count_word(words[-1])
        return None if count is None else (0, count, False)
    if len(words) >= 3 and words[-2] == "or":
        fewest, most = _count_word(words[-3]), _count_word(words[-1])
        if fewest is not None and most is not None:
            return (fewest, most, False) if fewest <= most else None
    if words and words[-1] == "x":
        return 0, None, True
    if words and words[-1] not in {"a", "an"} and (count := _count_word(words[-1])) is not None:
        return count, count, False
    return 1, 1, False


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


def _read_phrase(prefix: str, suffix: str) -> TargetRequirement | None:
    """Turn one "target ..." phrase into a requirement, or None if unreadable."""
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
    adjectives, index = _read_adjectives(words)
    card_types: set[Type] = set()
    required_subtypes: set[str] = set()
    allows_players = False
    opponent_only = False
    allows_cards = False
    zones = {Zone.BATTLEFIELD}
    must_be_tapped: bool | None = adjectives.must_be_tapped
    bare_card = False
    nouns_read = 0
    noun_end = index
    or_any_spell = False
    #: Whether the token just skipped was a noun-list conjunction. "Target
    #: creature spell" and "target creature or spell" differ by this word and
    #: by nothing else - see `TargetRequirement.or_any_spell`.
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
        if nouns_read and adjectives.take(word):
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
            if nouns_read and after_conjunction:
                # "... or spell" - the second item of a two-kind noun list, not
                # the noun a preceding "creature" was qualifying. CR 112.1 puts
                # it on the stack and names no type for it; `or_any_spell` is
                # how the two halves stay separate restrictions rather than
                # collapsing into one conjunction. `zones` is left alone, so
                # the first half keeps whatever zone it named.
                or_any_spell = True
            else:
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
                card_types.add(Type.CREATURE)
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

    rest = " ".join(words[noun_end:])
    controller = ControllerRestriction.ANY

    # Read out of the way before the comparison scan sees it: this clause looks
    # exactly like a mana-value bound and is not one (see
    # `_COLORS_OF_MANA_SPENT_CONDITION`).
    rest = _COLORS_OF_MANA_SPENT_CONDITION.sub("", rest).strip()

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

    distinct_controllers, rest = _extract_distinct_controllers(rest)

    required_keyword, rest = _extract_required_keyword(rest)

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
            controller = _CONTROLLERS[re.sub(r"\s+", " ", control_match.group(1).lower())]

    return TargetRequirement(
        phrase=" ".join(["target", *(word for word in words[:noun_end] if word != ",")]),
        count=count,
        minimum=minimum,
        unbounded=unbounded,
        variable_count=variable,
        card_types=frozenset(card_types),
        required_subtypes=frozenset(required_subtypes),
        excluded_card_types=frozenset(adjectives.excluded_types) | extra_excluded_types,
        required_supertypes=frozenset(adjectives.required_supertypes),
        excluded_supertypes=frozenset(adjectives.excluded_supertypes) | extra_excluded_supertypes,
        required_colors=frozenset(adjectives.required_colors),
        allows_cards=allows_cards,
        allows_players=allows_players,
        opponent_only=opponent_only and not allows_cards,
        zones=frozenset(zones),
        or_any_spell=or_any_spell,
        controller=controller,
        must_be_tapped=must_be_tapped,
        excludes_source=excludes_source or adjectives.excludes_source,
        exiled_with_source=exiled_with_source,
        must_be_token=adjectives.must_be_token,
        color_count=color_count,
        historic=adjectives.historic,
        combat_states=frozenset(adjectives.combat_states),
        comparison_attribute=comparison_attribute,
        comparison_operator=comparison_operator,
        comparison_value=comparison_value,
        comparison_count=comparison_count,
        distinct_controllers=distinct_controllers,
        required_keyword=required_keyword,
    )


class _Adjectives:
    """The run of adjectives in front of the noun of a "target ..." phrase."""

    def __init__(self) -> None:
        self.excluded_types: set[Type] = set()
        self.required_supertypes: set[Supertype] = set()
        self.excluded_supertypes: set[Supertype] = set()
        self.required_colors: set[Color] = set()
        self.combat_states: set[CombatState] = set()
        self.must_be_tapped: bool | None = None
        self.must_be_token: bool | None = None
        self.color_count: str | None = None
        self.historic = False
        self.excludes_source = False
        self.read = 0

    def take(self, word: str) -> bool:
        """Read one word as an adjective, or say it is not one."""
        if word in _TAPPED_ADJECTIVES:
            self.must_be_tapped = _TAPPED_ADJECTIVES[word]
        elif word in _COMBAT_ADJECTIVES:
            self.combat_states.add(_COMBAT_ADJECTIVES[word])
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


def _read_adjectives(words: list[str]) -> tuple[_Adjectives, int]:
    """The leading adjectives, and where the noun starts after them.

    "attacking or blocking creature" is one run of two: the conjunction is
    swallowed only when an adjective follows it, so "creature or land" is still
    two nouns rather than one adjective and a noun.

    A comma joins a run the same way: Skyclave Apparition's "nonland, nontoken
    permanent" and Thief of Existence's "noncreature, nonland permanent" are
    each two restrictions on one noun (CR 110.4's permanent types, CR 111.1's
    tokens), and every one of them applies - the adjectives accumulate on
    `_Adjectives` exactly as they do with no comma between them.
    """
    adjectives = _Adjectives()
    index = 0
    while index < len(words) and adjectives.take(words[index]):
        index += 1
        joined = index + 1
        if (
            joined < len(words)
            and words[index] in {"or", "and", ","}
            and _is_adjective(words[joined])
        ):
            index += 1
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
}

#: The comparison itself, once `_COMPARISON_ATTEMPT` says one is being made.
#: Order inside the alternation matters: "N or less/greater" and the spelled-
#: out "less/greater than or equal to N" are tried before the bare "N" so a
#: qualified number is never misread as an unqualified one.
_COMPARISON_CLAUSE = re.compile(
    r"\b(?P<attr>mana value|converted mana cost|power or toughness|power|toughness)\b"
    r"\s+(?:is\s+)?"
    r"(?:"
    r"(?P<num_or>x|\d+)\s+or\s+(?P<dir>less|greater)"
    r"|(?P<count_dir>less|greater) than or equal to the number of cards in "
    r"(?P<controllers_graveyard>its controller'?s? graveyard)\b"
    r"|less than or equal to\s+(?P<le_num>x|\d+)\b"
    r"|greater than or equal to\s+(?P<ge_num>x|\d+)\b"
    r"|equal to\s+(?P<eq_num>x|\d+)\b"
    r"|(?P<bare_num>x|\d+)\b"
    r")",
    re.IGNORECASE,
)

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


#: A trailing "with `<keyword>`" clause - "target creature you don't control
#: with flying" (Kraul Harpooner). Deliberately a small, explicit vocabulary
#: rather than "with (?P<keyword>.+)$": an unrecognised "with" clause (a
#: counter, "with the highest power", CR 205.2a shapes this reader is not
#: meant to reach) is left exactly as unenforced as it always was, rather
#: than newly failing the whole phrase closed - only a *recognised* keyword
#: gains enforcement here.
_WITH_KEYWORD_RE = re.compile(
    r"\bwith\s+(?P<keyword>flying|reach|trample|menace|haste|vigilance|"
    r"first strike|double strike|defender|deathtouch|lifelink)$",
    re.IGNORECASE,
)


def _extract_required_keyword(rest: str) -> tuple[str | None, str]:
    """Read a trailing "with `<keyword>`" clause out of `rest` (CR 702), or
    leave it untouched when there is none - see `_WITH_KEYWORD_RE`."""
    match = _WITH_KEYWORD_RE.search(rest)
    if match is None:
        return None, rest
    return match.group("keyword").lower(), rest[: match.start()].strip()


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


_ALL_NOUNS = frozenset(_TYPE_NOUNS) | _PERMANENT_NOUNS | _PLAYER_NOUNS | _SPELL_NOUNS | _CARD_NOUNS
_CONTROLLERS = {
    "you control": ControllerRestriction.YOU,
    "you don't control": ControllerRestriction.NOT_YOU,
    "an opponent controls": ControllerRestriction.OPPONENT,
    "your opponents control": ControllerRestriction.OPPONENT,
}
