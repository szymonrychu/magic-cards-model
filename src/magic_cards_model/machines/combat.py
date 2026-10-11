"""Combat, as a state machine (CR 506-511).

The turn machine already walks through the five combat steps; this is what
happens inside them. Three turn-based actions do the work, none of which use
the stack:

- **Declare attackers** (CR 508.1). The active player picks untapped creatures
  they control that are not summoning sick, and says what each one is attacking.
  Attacking taps them (CR 508.1f) unless they have vigilance (CR 702.20b).
- **Declare blockers** (CR 509.1). The defending player picks untapped creatures
  they control and says which attacker each one blocks. The declaration is
  legal or illegal as a whole, which is what lets menace work at all.
- **Combat damage** (CR 510). Everything assigns at once (CR 510.2), so the
  whole assignment is computed against the pre-damage board and only then dealt.
  First strike and double strike split this into two steps (CR 510.4).
  CR 510.3a then puts what triggered onto the stack, which `combat_damage_step`
  does at the end of the step - the same thing `Game.declare_attackers` and
  `Game.declare_blockers` do for CR 508.2b and CR 509.2a.

Everything combat asks about a permanent is asked of the computed board, not of
the printing: CR 613.5 has the layer system applied "continually and
automatically", so `has_keyword`, `_power_of`, `_toughness_of` and
`_evasion_restriction_sentences` all take the `Game` and read
`Game.characteristics_of`. A keyword or a "can't be blocked" sentence granted in
layer 6 is there and one removed by Dress Down is gone. Each of those functions
still answers off the printing when it is handed no game, which is all there is
for a card outside the battlefield.

Damage names its source (CR 120.1), so CR 615's prevention shields, CR 609.7b's
recheck and CR 702.16e's protection all apply to combat damage - `deal_damage`
consults them and returns what actually landed, which is what deathtouch
(CR 702.2b) and lifelink (CR 702.15b) key off.

There is no damage assignment order sub-step in the current rules: after
CR 509.1 declares the blockers, CR 509.2a puts the triggers on the stack and
the active player gets priority - nothing in between orders the blockers.
CR 510.1c instead governs how a blocked creature divides its damage among the
creatures blocking it, so the order blockers were declared in is the order
damage walks through here - `declare_blockers` takes them in that order.
"""

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ConfigDict, Field

from magic_cards_model.phrases import with_indefinite_article

from ..data.subtypes import canonical_subtype
from ..models.card import Color, Type
from ..models.card_state import CardState, Counter, TargetRef
from ..models.mana import ManaCost
from ..models.token import is_token
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from ..snapshot import EngineModel
from .abilities import (
    keyword_abilities_in_lines,
    keywords_in_lines,
    layer_readable_sentences,
    unread_keyword_tokens,
)
from .decisions import Decision, DecisionKind, source_id_of
from .designations import designation_holds, split_as_long_as
from .triggers import ExtraTriggerEvent, GameEvent

#: What a creature may attack besides a player (CR 306.6, 310.5).
ATTACKABLE_PERMANENT_TYPES = frozenset({Type.PLANESWALKER, Type.BATTLE})

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game, Targetable
    from .layers import ComputedBoard


class Keyword(StrEnum):
    """The keyword abilities combat cares about, as Scryfall spells them.

    Scryfall's `keywords` field is title case ("First strike"), so every lookup
    goes through `has_keyword`, which compares case-insensitively.
    """

    FLYING = "flying"
    REACH = "reach"
    TRAMPLE = "trample"
    MENACE = "menace"
    HASTE = "haste"
    VIGILANCE = "vigilance"
    FIRST_STRIKE = "first strike"
    DOUBLE_STRIKE = "double strike"
    #: CR 702.3a-b: "Defender is a static ability. A creature with defender
    #: can't attack."
    DEFENDER = "defender"
    #: CR 702.147a: "Decayed represents a static ability and a triggered
    #: ability. 'Decayed' means 'This creature can't block' and 'When this
    #: creature attacks, sacrifice it at end of combat.'" Only the static
    #: half ("can't block", CR 509.1b) is read here, off `has_keyword` in
    #: `block_refusal` below, so a printed, granted, or CR 122.1b keyword-
    #: counter decayed all refuse a block the same way. The triggered half
    #: ("sacrifice it at end of combat", CR 603.7/511.2) is
    #: `machines/keywords.py::_decayed_ability`'s `_TRIGGER_EXPANSIONS` entry.
    DECAYED = "decayed"
    #: CR 702.28a-b: "Shadow is an evasion ability." "A creature with shadow
    #: can't be blocked by creatures without shadow, and a creature without
    #: shadow can't be blocked by creatures with shadow." Read in
    #: `block_refusal`, both directions.
    SHADOW = "shadow"
    #: CR 702.13a-b: "Intimidate is an evasion ability." "A creature with
    #: intimidate can't be blocked except by artifact creatures and/or
    #: creatures that share a color with it." Read in `block_refusal`.
    INTIMIDATE = "intimidate"
    #: CR 702.2a-c: a static ability that changes what counts as lethal damage
    #: when this creature assigns it, and adds a state-based action (CR 704.5h).
    DEATHTOUCH = "deathtouch"
    #: CR 702.15b: damage dealt by a source with lifelink makes its controller
    #: gain that much life, in addition to the damage's other results.
    LIFELINK = "lifelink"
    #: CR 702.14a-c: the five basic landwalks. Landwalk is an evasion ability
    #: (CR 702.14b) whose name carries the land type it looks for, so the
    #: members are spelled out rather than derived.
    #: CR 702.90a-c / CR 120.3b, 120.3d: damage from a source with infect
    #: gives a player poison counters and a creature -1/-1 counters. Read by
    #: `Game.deal_damage` for every damage event, combat or not.
    INFECT = "infect"
    #: CR 702.80a / CR 120.3d: damage from a source with wither puts -1/-1
    #: counters on a creature rather than marking damage.
    WITHER = "wither"
    #: CR 702.164a-c / CR 120.3g: "toxic N" - combat damage to a player also
    #: gives poison counters equal to the creature's total toxic value
    #: (`total_toxic_value`), applied in `_deal_combat_damage`.
    TOXIC = "toxic"
    PLAINSWALK = "plainswalk"
    ISLANDWALK = "islandwalk"
    SWAMPWALK = "swampwalk"
    MOUNTAINWALK = "mountainwalk"
    FORESTWALK = "forestwalk"


#: Keywords the `Keyword` enum does not carry, that a permanent may still have
#: and a caller may still ask about - ones no combat rule reads, and the two
#: evasion abilities `block_refusal` reads by name.
#:
#: Deliberately not members of `Keyword`: that enum is the combat vocabulary and
#: is iterated elsewhere as "every keyword a grant or a counter can name" -
#: `machines/layers.py::_keyword_counter_lines` turns each member into CR 122.1b
#: keyword-counter text, and none of these is a counter this engine mints. They
#: belong to the reading vocabulary (`_computed_keywords`) and to
#: `machines/layers.py::_KNOWN_KEYWORDS`'s grant whitelist, which is why they are
#: named here once instead of twice.
KEYWORDS_OUTSIDE_COMBAT: frozenset[str] = frozenset(
    {
        # CR 702.12a: "Indestructible is a static ability."
        "indestructible",
        # CR 702.11a: "Hexproof is a static ability."
        "hexproof",
        # CR 702.18a: "Shroud is a static ability."
        "shroud",
        # CR 702.118a-b / CR 702.36a-b: evasion abilities `block_refusal` reads
        # by name, so a grant ("gain fear", "gain skulk") is recognised too.
        "skulk",
        "fear",
    }
)


#: Canonical granted-ability text for "can attack as though it/they didn't
#: have defender" (Ghalta the Immovable's group grant over creatures it
#: controls; Surveillance Phantasm's self one). `machines/layers.py`'s static
#: parsers grant this one fixed string regardless of the printed pronoun, so
#: `attack_refusal` below checks a single literal rather than pattern-matching
#: the source's own wording - the same normalisation every other grant there
#: already does by capitalising a bare keyword instead of keeping the printed
#: casing.
ATTACK_WITHOUT_DEFENDER_TEXT = "Can attack as though it didn't have defender."


def _can_attack_despite_defender(creature: CardState, game: "Game") -> bool:
    """CR 702.3b's "can't attack" is what a static grant like Ghalta the
    Immovable's or Surveillance Phantasm's overrides - read off the computed
    board (CR 613.5) the same way `has_keyword` reads defender itself.
    """
    return game.characteristics_of(creature).has_ability(ATTACK_WITHOUT_DEFENDER_TEXT)


#: Ghalta the Immovable's group grant: "Each creature you control with
#: toughness greater than its power assigns combat damage equal to its
#: toughness rather than its power." The condition (toughness greater than
#: power) lives in the `Selector` that grants this - `machines/layers.py`'s
#: `CreaturesControlledByWhereToughnessExceedsPower` - so by the time this
#: text is present on the computed board (CR 613.5), the condition already
#: holds and `_assignment_power_of` below does not need to re-check it.
ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT = (
    "Assigns combat damage equal to its toughness rather than its power."
)

#: Loot, the Anomaly's self grant: "If Loot's power is negative, he assigns
#: combat damage as though his power were positive." Same "the Selector
#: already checked it" shape as the text above, one object instead of a team.
ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT = "Assigns combat damage as though its power were positive."


def _assignment_power_of(game: "Game | None", creature: CardState) -> int | None:
    """How much damage this creature assigns (CR 510.1a's "equal to its
    power"), with the two alternate-assignment grants above applied on top of
    `_power_of`. `attack_refusal` and CR 510.1a's zero-or-less rule both still
    read the ordinary `_power_of`/`_toughness_of` - only the amount actually
    *assigned* changes.
    """
    power = _power_of(game, creature)
    if power is None or game is None:
        return power
    if creature.assigns_no_combat_damage_this_combat:
        # Master of Cruelties' own attack trigger: "This creature assigns
        # no combat damage this combat." - a one-shot override on the
        # *assignment*, distinct from CR 510.1a's own "0 or less power
        # assigns nothing", so it applies even to a creature with real
        # power.
        return 0
    chars = game.characteristics_of(creature)
    if chars.has_ability(ASSIGNS_DAMAGE_AS_TOUGHNESS_TEXT):
        toughness = _toughness_of(game, creature)
        if toughness is not None:
            return toughness
    if power < 0 and chars.has_ability(ASSIGNS_DAMAGE_AS_THOUGH_POSITIVE_TEXT):
        return -power
    return power


#: Which land type each landwalk ability looks for (CR 702.14a, CR 305.6).
LANDWALK_TYPES: dict[Keyword, str] = {
    Keyword.PLAINSWALK: "Plains",
    Keyword.ISLANDWALK: "Island",
    Keyword.SWAMPWALK: "Swamp",
    Keyword.MOUNTAINWALK: "Mountain",
    Keyword.FORESTWALK: "Forest",
}


def has_keyword(state: CardState, keyword: Keyword | str, game: "Game | None" = None) -> bool:
    """True if this permanent has the keyword right now (CR 702, CR 613.5).

    With a game, the answer comes off the computed board: CR 613.5 says "the
    application of continuous effects as described by the layer system is
    continually and automatically performed by the game", so a keyword taken
    away in layer 6 is gone and one granted there is there. Humility and Dress
    Down are the cards in the pool that make the difference visible.

    Without a game there is no board to compute, so the printing's own Scryfall
    `keywords` field is the answer - which is what every caller used before and
    is still right for a permanent nothing is affecting.
    """
    wanted = str(keyword).lower()
    computed = _computed_keywords(state, game, wanted)
    if computed is not None:
        return wanted in computed
    if state.zone is Zone.STACK and any(
        line.strip().rstrip(".").lower() == wanted for line in state.granted_ability_texts
    ):
        # A keyword a spell on the stack gained (CR 113.10) - Spinerock
        # Tyrant's "those spells gain wither", Judith, Carnage Connoisseur's
        # "That spell gains deathtouch and lifelink" (`machines/cast_copies`).
        return True
    # `state.keywords`, not `state.card.keywords`: a face-down permanent has no
    # text at all (CR 702.37c, CR 708.2), so it has none of the printing's
    # keywords however plainly the card says them.
    return any(printed.lower() == wanted for printed in state.keywords)


def source_had_keyword(state: CardState, keyword: Keyword | str, game: "Game") -> bool:
    """Whether a damage source has a keyword, by last known information once
    it has left the battlefield (CR 702.90d, CR 702.80b).

    "If an object is no longer in the zone it's expected to be in as an effect
    causes it to deal damage, its last known information is used to determine
    whether it had infect" - `CardState.last_known_keywords` is that snapshot,
    taken by `Game._note_left_battlefield` while the layer system still
    answered for the permanent. With no snapshot the object is where it deals
    damage from - a spell on the stack, a card in a hand or graveyard - and
    its own keywords answer (CR 702.90e, 702.80c: the rules "function no
    matter what zone an object ... deals damage from").
    """
    if state.zone is not Zone.BATTLEFIELD and state.last_known_keywords is not None:
        return str(keyword).lower() in state.last_known_keywords
    return has_keyword(state, keyword, game)


_ALL_DAMAGE_WITHER_RE = re.compile(
    r"all damage is dealt as though its source had wither\.?(?: \(.*\))?", re.IGNORECASE
)


def all_damage_has_wither(game: "Game") -> bool:
    """CR 702.80a through a CR 604.2 static ability: some permanent says "All
    damage is dealt as though its source had wither." (Everlasting Torment),
    whoever controls it, so every source - a spell or a noncreature one too -
    deals damage as -1/-1 counters to creatures."""
    board = game.computed_board()
    return any(
        _ALL_DAMAGE_WITHER_RE.fullmatch(line.strip())
        for permanent in game.battlefield
        for line in board.of(permanent).abilities
        if "wither" in line
    )


def keywords_as_it_exists(state: CardState, game: "Game") -> tuple[str, ...]:
    """Every keyword the layer system leaves this permanent with, lowercased
    and sorted - the snapshot `CardState.last_known_keywords` stores."""
    computed = _computed_keywords(state, game)
    if computed is None:
        computed = {printed.lower() for printed in state.keywords}
    return tuple(sorted(computed))


def total_toxic_value(state: CardState, game: "Game") -> int:
    """CR 702.164b: "A creature's total toxic value is the sum of all N values
    of toxic abilities that creature has."

    Read off the computed ability lines (CR 613.5), so a printed "Toxic 1"
    and a granted one (Prosthetic Injector's "has toxic 1") are two
    instances and add up, and one taken away in layer 6 is gone.
    """
    characteristics = game.characteristics_of(state) if state.zone is Zone.BATTLEFIELD else None
    lines = (
        list(characteristics.abilities)
        if characteristics is not None
        else [line for line in state.oracle_text.splitlines() if line.strip()]
    )
    vocabulary = _reading_vocabulary(state, (Keyword.TOXIC.value,))
    return sum(
        ability.count or 0
        for ability in keyword_abilities_in_lines(lines, vocabulary)
        if ability.canonical.lower() == Keyword.TOXIC.value
    )


class KeywordLineNotice(EngineModel):
    """One computed ability line that is part CR 702 keywords and part something
    this engine's keyword reader cannot name.

    `machines/abilities.py::_parse_keywords` is all-or-nothing on purpose: a
    line is CR 702.1's "only the name of the ability as a keyword" repeated, or
    it is not a keyword line at all, and reading half of one would grant an
    ability the card does not have. Nevinyrral, Urborg Tyrant's "Hexproof from
    artifacts, creatures, and enchantments" is that trap (CR 702.11f). A
    station symbol's line ("5+ | Flying, trample", CR 721.2a) never reaches
    this record: it is read as the station static ability it is.

    Dropping the line is therefore right; dropping it silently is not. This is
    the record that says which tokens went unread, the same "unreadable is not
    the same as no effect" record `EvasionNotice`, `UndefinedPowerNotice`, and
    `LayerNotice` already keep. Its absence is what made the defect that
    produced this class invisible: Emrakul, the Promised End's
    "Flying, trample, protection from instants" read as no keywords at all
    because `protection` was outside the reading vocabulary, and a 13/13 flier
    with trample quietly became blockable by a ground creature and dealt its
    defending player nothing.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The computed line, as the layer system left it (CR 613.5)."""
    unread: tuple[str, ...]
    """The tokens on it that matched no keyword in the reading vocabulary."""


def _reading_vocabulary(state: CardState, wanted: tuple[str, ...]) -> list[str]:
    """Every keyword name a computed line of `state` may be read with.

    `keywords_in_lines` has no keyword table of its own: the caller says which
    keywords it cares about, and getting that list wrong is not a missed
    keyword but a lost line, because `_parse_keywords` discards a comma line
    with one token it cannot match.

    Three sources, and the permanent's own is the one that was missing. This
    module's `Keyword` is the combat vocabulary; `KEYWORDS_OUTSIDE_COMBAT` adds
    what a grant may name that no combat rule reads; `state.keywords` adds what
    this printing actually says, which is how `protection from instants` and
    `ward {2}` stop taking flying down with them. `wanted` adds whatever is
    being asked about, so a keyword granted by an effect and named by nobody
    else is still found.

    `state.keywords` is the computed list, not `state.card.keywords`: a
    face-down permanent has no text (CR 702.37c, CR 708.2) and contributes
    nothing here, which is what keeps its printed flying unreadable rather than
    smuggling it back in as vocabulary. Vocabulary is only ever permission to
    *recognise* a word the computed text already says - it grants nothing.
    """
    return (
        [keyword.value for keyword in Keyword]
        + sorted(KEYWORDS_OUTSIDE_COMBAT)
        + [printed.lower() for printed in state.keywords]
        + [word for word in wanted if word]
    )


def _record_keyword_line_notices(
    game: "Game", state: CardState, lines: list[str], vocabulary: list[str]
) -> None:
    """Record every line of `lines` that went unread for want of one token.

    Deduped by source and line text, mirroring `attack_refusal`'s dedup of
    `EvasionNotice` by `source_id`: `has_keyword` is asked dozens of times a
    combat and the gap is a property of the line, not of the question.
    """
    for line in lines:
        unread = unread_keyword_tokens(line, vocabulary)
        if not unread:
            continue
        if any(
            notice.source_id == state.id and notice.text == line
            for notice in game.keyword_line_notices
        ):
            continue
        game.keyword_line_notices.append(
            KeywordLineNotice(source_id=state.id, source_name=state.name, text=line, unread=unread)
        )


def _computed_keywords(state: CardState, game: "Game | None", *wanted: str) -> set[str] | None:
    """The keywords the layer system leaves this permanent with, or None.

    None means there is nothing to compute against - no game, or a card that is
    not a permanent, since CR 613 applies to objects on the battlefield and a
    card in a hand has only what is printed on it.
    """
    if game is None or state.zone is not Zone.BATTLEFIELD:
        return None
    characteristics = game.characteristics_of(state)
    if characteristics is None:
        return None
    vocabulary = _reading_vocabulary(state, wanted)
    lines = list(characteristics.abilities)
    _record_keyword_line_notices(game, state, lines, vocabulary)
    return keywords_in_lines(lines, vocabulary)


class Attack(EngineModel):
    """One attacking creature and what it is attacking (CR 508.1).

    `blockers` is in declaration order, which is the order combat damage is
    assigned through (CR 510.1c). `blocked` stays true once blockers have been
    declared for it even if every blocker later leaves combat (CR 509.1h) -
    which is exactly why such an attacker deals no damage at all.
    """

    attacker_id: UUID
    defender: TargetRef
    blockers: list[UUID] = Field(default_factory=list)
    blocked: bool = False
    blocked_by: list[UUID] = Field(default_factory=list)
    """Every creature that has blocked this attacker this combat, in the
    order each began to, including any since removed from combat - the
    history Balduvian Warlord's "creatures it was blocking that hadn't become
    blocked by another creature this combat" asks about (CR 509.1h), which
    `blockers` (who is blocking *now*) cannot answer."""


class CombatMachine(EngineModel):
    """Who is attacking whom, who is blocking, and how much damage is done.

    Everything is held by id rather than by object, so the combat state is one
    serializable record next to the battlefield rather than a second copy of it.
    """

    attacks: list[Attack] = Field(default_factory=list)
    blockers_declared: bool = False
    damage_steps_done: int = 0
    first_strike_step_happened: bool = False
    first_strike_damage_step: bool = False
    """Whether the combat damage step now in progress is CR 510.4's
    first-strike step - the read `Game.is_first_strike_damage_step` exposes.

    Unlike `first_strike_step_happened` (sticky for the rest of combat, CR
    510.4's own signal that a second step is owed), this flips back to False
    once the second step begins, which is what tells the two occurrences of
    `Step.COMBAT_DAMAGE` apart while the game sits paused between them.
    """
    first_strike_step_ids: list[UUID] = Field(default_factory=list)
    """The attackers and blockers that had first strike or double strike as
    the first-strike step began (CR 510.4's "as the first combat damage step
    began").

    Snapshotted once, when that step begins, rather than re-read live in the
    second step: CR 702.7c and CR 702.4c-d both turn on what a creature *had
    then*, not on what it has now, so a creature that struck once and later
    lost the ability it struck with must not strike again, and one that never
    struck must strike in the second step even if it is granted first strike
    in between (`deals_damage_this_step` reads this list rather than asking
    `has_keyword` a second time for the second step).
    """
    attacked_this_combat: bool = False
    """Whether anybody attacked this combat, either way CR 508.8 counts.

    CR 508.8 is a union of two histories - "If no creatures are declared as
    attackers **or put onto the battlefield attacking**, skip the declare
    blockers and combat damage steps" - and neither half is "is any creature
    attacking right now". `declare_attacker` sets this for the first half and
    `models/token._put_onto_the_battlefield_attacking` for the second (CR
    508.4); a creature put onto the battlefield attacking was never *declared*
    (CR 508.4c), and CR 508.8 does not ask that it was.

    Because it is a history, CR 506.4's `remove` takes a creature out of combat
    without un-setting this: the thing CR 508.8 asks about already happened.
    Only `clear` resets it, at the end of combat (CR 511.3).
    """
    declared_attacking_power: int = 0
    """The total power the creatures declared as attackers this combat had
    as they were declared (CR 508.1) - pack tactics' "you attacked with
    creatures with total power N or greater this combat" (CR 207.2c). A
    history like `attacked_this_combat`: a creature put onto the battlefield
    attacking never "attacked" (CR 508.4) and adds nothing, and a later
    change to an attacker's power does not rewrite it. Reset by `clear`."""

    @property
    def attacker_ids(self) -> list[UUID]:
        return [attack.attacker_id for attack in self.attacks]

    @property
    def blocker_ids(self) -> list[UUID]:
        return [blocker for attack in self.attacks for blocker in attack.blockers]

    @property
    def is_active(self) -> bool:
        return bool(self.attacks)

    def attack_by(self, attacker_id: UUID) -> Attack | None:
        return next((a for a in self.attacks if a.attacker_id == attacker_id), None)

    def attack_blocked_by(self, blocker_id: UUID) -> Attack | None:
        return next((a for a in self.attacks if blocker_id in a.blockers), None)

    def remove(self, card_id: UUID) -> None:
        """Take a permanent out of combat (CR 506.4).

        An attacker that goes takes its whole attack with it. A blocker that
        goes stops blocking, but the creature it was blocking stays blocked.
        """
        self.attacks = [a for a in self.attacks if a.attacker_id != card_id]
        for attack in self.attacks:
            if card_id in attack.blockers:
                attack.blockers.remove(card_id)

    def unblock_attacks_blocked_only_by(self, blocker_id: UUID) -> list[UUID]:
        """Each attacker `blocker_id` had blocked and no other creature had
        this combat becomes unblocked (CR 509.1h's "an effect says that it
        becomes ... unblocked"). Returns the attackers it unblocked."""
        unblocked = []
        for attack in self.attacks:
            if attack.blocked and attack.blocked_by and set(attack.blocked_by) == {blocker_id}:
                attack.blocked = False
                unblocked.append(attack.attacker_id)
        return unblocked

    def add_blocker(self, blocker_id: UUID, attacker_id: UUID) -> None:
        """An effect makes `blocker_id` block `attacker_id` (CR 509.3b): it is
        blocking that attacker, which becomes (or stays) blocked (CR 509.1h).
        Not a declaration, so CR 509.1b/509.1c's restrictions and
        requirements are not consulted."""
        attack = self.attack_by(attacker_id)
        if attack is None:
            return
        if blocker_id not in attack.blockers:
            attack.blockers.append(blocker_id)
        if blocker_id not in attack.blocked_by:
            attack.blocked_by.append(blocker_id)
        attack.blocked = True

    def clear(self) -> None:
        """Everything is removed from combat as the combat phase ends (CR 511.3)."""
        self.attacks = []
        self.blockers_declared = False
        self.damage_steps_done = 0
        self.first_strike_step_happened = False
        self.first_strike_damage_step = False
        self.first_strike_step_ids = []
        self.attacked_this_combat = False
        self.declared_attacking_power = 0


# -- declaring attackers ---------------------------------------------------


def attack_refusal(game: "Game", creature: CardState, defender: TargetRef) -> str | None:
    """Why this creature cannot be declared as an attacker, or None (CR 508.1a).

    CR 508.1a: "The chosen creatures must be untapped, they can't also be
    battles, and each one must either have haste or have been ..." controlled
    by the active player since their most recent turn began - which is what
    `CardState.summoning_sick` tracks (CR 302.6, 702.10b).
    """
    assert game.turn is not None
    active = game.turn.active_player

    if creature.zone is not Zone.BATTLEFIELD:
        return f"{creature.name} is in {creature.zone.value}, not on the battlefield"
    if creature.phased_out:
        return f"{creature.name} is phased out (CR 702.26b)"
    if not game.characteristics_of(creature).is_creature:
        # Read off the computed board (CR 613.5), not the printed type line,
        # so a permanent a continuous effect turned into a creature - Karn,
        # the Great Creator's animated Trinisphere - can attack like any other.
        return f"{creature.name} is not a creature"
    if game.controller_of(creature).username != active:
        return f"{creature.name} is not controlled by the active player"
    if game.combat.attack_by(creature.id) is not None:
        # Checked before "is tapped", or attacking taps it and the second
        # declaration reports the wrong reason.
        return f"{creature.name} is already attacking"
    if creature.tapped:
        return f"{creature.name} is tapped"
    if creature.summoning_sick and not has_keyword(creature, Keyword.HASTE, game):
        return f"{creature.name} has summoning sickness and no haste"
    if has_keyword(creature, Keyword.DEFENDER, game) and not _can_attack_despite_defender(
        creature, game
    ):
        # CR 702.3b: "A creature with defender can't attack." Checked after
        # tapping and summoning sickness so a Wall that is also tapped still
        # reports the reason a scenario is most likely asking about.
        return f"{creature.name} has defender and cannot attack (CR 702.3b)"
    own_restriction = _self_attack_restriction_sentence(creature, game)
    if own_restriction is not None:
        # CR 508.1c: "The active player checks each creature they control to
        # see whether it's affected by any restrictions (effects that say a
        # creature can't attack ...)." - its own unconditional "This creature
        # can't attack." line, printed or granted (Twisted Caverns' "Target
        # creature can't attack until your next turn", CR 613.1f).
        return f'{creature.name} can\'t attack: "{own_restriction}" (CR 508.1c)'
    restricted_until = getattr(game, "creatures_cant_attack_until_turns_taken", None)
    if restricted_until is not None and int(game.turn.turns_taken) == restricted_until:
        # CR 508.1c: a blanket "creatures can't attack this turn" restriction
        # (Orim's Chant, kicked), not read off any one permanent's own static
        # text the way the defender check above is.
        return f"{creature.name} can't attack this turn (CR 508.1c)"

    from .combat_statics import extra_attack_refusal, power_threshold_restriction_refusal

    return (
        self_card_count_restriction_refusal(game, creature, "attack")
        or self_control_count_restriction_refusal(game, creature, "attack")
        or power_threshold_restriction_refusal(game, creature, "attack")
        or _defender_refusal(game, defender, active)
        or group_attack_restriction_refusal(game, creature, defender)
        or extra_attack_refusal(game, creature, defender)
    )


#: A creature's own "can't attack [or block] unless there are N or more cards
#: in <zone>" - Ketramose, the New Dawn's "Ketramose can't attack or block
#: unless there are seven or more cards in exile." and Deep-Sea Terror's "This
#: creature can't attack unless there are seven or more cards in your
#: graveyard." CR 508.1c/509.1b's "can't attack/block unless some condition is
#: met", the condition a count of one zone: the shared exile zone, the
#: controller's own graveyard, or every graveyard (CR 400.1).
_SELF_CANT_UNLESS_CARD_COUNT_RE = re.compile(
    r"\bcan't (?P<what>attack or block|attack|block) unless there (?:is|are) "
    rf"(?P<count>{COUNT}) or more cards? in (?P<zone>exile|your graveyard|all graveyards)\.?$",
    re.IGNORECASE,
)


def is_self_card_count_restriction_line(text: str) -> bool:
    """Whether a static line is `_SELF_CANT_UNLESS_CARD_COUNT_RE`'s shape with
    a readable count - what `support.py` counts handled."""
    match = _SELF_CANT_UNLESS_CARD_COUNT_RE.search(text.strip())
    return match is not None and parse_count(match["count"], article=True) is not None


def _cards_in(game: "Game", zone: str, controller: str | None) -> int:
    """How many cards the restriction's zone holds right now."""
    if zone == "exile":
        return len(game.exile)
    if zone == "all graveyards":
        return sum(len(player.graveyard) for player in game.players_in_game)
    if controller is None:
        return 0
    return len(game.player(controller).graveyard)


def self_card_count_restriction_refusal(
    game: "Game", creature: CardState, action: str
) -> str | None:
    """Why this creature's own "can't `action` unless there are N or more
    cards in <zone>" stops it now, or None (CR 508.1c for "attack", CR 509.1b
    for "block"). Read off its computed abilities (CR 613.5), so a creature
    that lost the ability is not restricted, and counted at the moment asked
    (CR 611.3a)."""
    subjects = _self_reference_alternatives(creature)
    subject = re.compile(rf"^(?:{'|'.join(re.escape(name) for name in subjects)})\b", re.IGNORECASE)
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for sentence in _computed_ability_sentences(creature, game):
        match = _SELF_CANT_UNLESS_CARD_COUNT_RE.search(sentence)
        if match is None or not subject.search(sentence):
            continue
        if action not in match["what"].lower().split(" or "):
            continue
        needed = parse_count(match["count"], article=True)
        if needed is None:
            continue
        have = _cards_in(game, match["zone"].lower(), creature.controller)
        if have < needed:
            return f'{creature.name} can\'t {action}: "{sentence}" - there are {have} ({rule})'
    return None


# -- costs to attack (CR 508.1h) ----------------------------------------------

#: "Creatures can't attack you unless their controller pays {2} for each
#: creature they control that's attacking you." (Ghostly Prison, Propaganda,
#: Windborn Muse) and "creatures can't attack you unless their controller pays
#: {1} for each of those creatures" (Dain, Lord of the Iron Hills, behind its
#: enduring-story gate) - CR 508.1h's cost to attack, charged per creature
#: attacking the permanent's controller. Two wordings of one per-attacker
#: cost; the "you" is the permanent's controller (CR 109.5).
_ATTACK_COST_RE = re.compile(
    r"^creatures can't attack you unless their controller pays (?P<cost>(?:\{[^}]+\})+) "
    r"for each (?:creature they control that's attacking you|of those creatures)\.?$",
    re.IGNORECASE,
)


def _attack_cost_match(line: str) -> "tuple[re.Match[str], str | None] | None":
    """`_ATTACK_COST_RE`'s match for one ability line and the designation
    that gates it (`machines/designations.py`), or None."""
    text = line.strip()
    condition: str | None = None
    gated = split_as_long_as(text)
    if gated is not None:
        condition, text = gated
    match = _ATTACK_COST_RE.fullmatch(text)
    if match is None or ManaCost.try_parse(match["cost"]) is None:
        return None
    return match, condition


def is_attack_cost_line(line: str) -> bool:
    """Whether a static line is a per-attacker cost to attack its controller
    (CR 508.1h) - what `support.py` counts handled."""
    return _attack_cost_match(line) is not None


@dataclass(frozen=True)
class AttackCost:
    """One permanent's per-creature cost to attack its controller."""

    source: CardState
    cost: ManaCost
    sentence: str


def attack_costs_against(game: "Game", defender: TargetRef) -> list[AttackCost]:
    """The costs each creature attacking `defender` must pay (CR 508.1h),
    one per permanent that charges it - read off the computed board (CR
    613.5, CR 611.3a) at the moment asked, a designation gate checked
    against the charging permanent's controller. An attack on a planeswalker
    or battle is not an attack on "you", and costs nothing here."""
    if not defender.is_player or defender.username is None:
        return []
    board = game.computed_board()
    costs: list[AttackCost] = []
    for source in game.battlefield:
        characteristics = board.of(source)
        if characteristics.controller != defender.username:
            continue
        for line in characteristics.abilities:
            if "can't attack you unless" not in line.lower():
                continue
            found = _attack_cost_match(line)
            if found is None:
                continue
            match, condition = found
            if condition is not None and not designation_holds(
                condition, game.player(defender.username)
            ):
                continue
            cost = ManaCost.try_parse(match["cost"])
            if cost is None:
                continue
            costs.append(AttackCost(source, cost, line.strip()))
    return costs


def total_attack_cost(
    game: "Game", attacks: "list[tuple[CardState, TargetRef]]"
) -> tuple[ManaCost, list[str]]:
    """CR 508.1h's total cost to attack for a declaration, and a line per
    charge naming what it is for. A player "is not required to pay" it
    (CR 508.1d) - `most_obedient_attack` skips a defender that charges."""
    total = ManaCost.parse("")
    reasons: list[str] = []
    from .combat_statics import extra_attack_costs

    for creature, defender in attacks:
        for charge in [
            *attack_costs_against(game, defender),
            *extra_attack_costs(game, creature, defender),
        ]:
            total = total.plus(charge.cost)
            reasons.append(f"{creature.name}: {charge.cost} ({charge.source.name})")
    return total, reasons


#: A creature's own "can't attack [or block] unless you control `<count>`
#: `<quality>`" - Chief Warg's Company's "This creature can't attack unless
#: you control two or more other Wolves.", Mouser Mark III's and Steelclad
#: Serpent's "... unless you control another artifact.", Gadrak, the Crown-
#: Scourge's "... unless you control four or more artifacts." and War
#: Falcon's "... unless you control a Knight or a Soldier." CR 508.1c/509.1b's
#: "can't attack/block unless some condition is met", the condition a count
#: of the creature's controller's own permanents.
_SELF_CANT_UNLESS_CONTROL_RE = re.compile(
    r"\bcan't (?P<what>attack or block|attack|block) unless you control "
    rf"(?:(?P<article>an?|another)|(?P<count>{COUNT}) or more(?P<other> other)?) "
    r"(?P<quality>[^.]+?)\.?$",
    re.IGNORECASE,
)


def _control_quality(quality: str) -> "list[tuple[Type | None, str | None]] | None":
    """ "Wolves" -> [(None, "wolf")]; "artifacts" -> [(ARTIFACT, None)];
    "Knight or a Soldier" -> two alternatives. Each word a card type (CR
    205.2a) or a subtype (CR 205.3), singular or plural - or None for anything
    else ("creature with power 4 or greater"), which restricts nothing rather
    than guessing."""
    alternatives: list[tuple[Type | None, str | None]] = []
    for part in re.split(r"\s+or\s+(?:an?\s+)?", quality.strip()):
        word = part.strip()
        if " " in word or not word:
            return None
        lowered = word.lower()
        card_type = next(
            (t for t in Type if lowered in (t.value.lower(), t.value.lower() + "s")), None
        )
        if card_type is not None:
            alternatives.append((card_type, None))
            continue
        subtype = canonical_subtype(word)
        if subtype is None:
            return None
        alternatives.append((None, subtype))
    return alternatives or None


def _self_control_count_match(text: str) -> "tuple[re.Match[str], int, list] | None":
    match = _SELF_CANT_UNLESS_CONTROL_RE.search(text.strip())
    if match is None:
        return None
    needed = 1 if match["article"] else parse_count(match["count"], article=False)
    quality = _control_quality(match["quality"])
    if needed is None or quality is None:
        return None
    return match, needed, quality


def is_self_control_count_restriction_line(text: str) -> bool:
    """Whether a static line is `_SELF_CANT_UNLESS_CONTROL_RE`'s shape with a
    readable count and quality - what `support.py` counts handled."""
    return _self_control_count_match(text) is not None


def self_control_count_restriction_refusal(
    game: "Game", creature: CardState, action: str
) -> str | None:
    """Why this creature's own "can't `action` unless you control `<count>`
    [other] `<quality>`" stops it now, or None (CR 508.1c for "attack", CR
    509.1b for "block"). Read off its computed abilities and the computed
    board (CR 613.5), counted at the moment asked (CR 611.3a); "another" and
    "other" leave the creature itself out of its own count."""
    subjects = _self_reference_alternatives(creature)
    subject = re.compile(rf"^(?:{'|'.join(re.escape(name) for name in subjects)})\b", re.IGNORECASE)
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for sentence in _computed_ability_sentences(creature, game):
        found = _self_control_count_match(sentence)
        if found is None or not subject.search(sentence):
            continue
        match, needed, quality = found
        if action not in match["what"].lower().split(" or "):
            continue
        excludes_self = (match["article"] or "").lower() == "another" or bool(match["other"])
        board = game.computed_board()
        have = 0
        for permanent in game.permanents_controlled_by(creature.controller or ""):
            if excludes_self and permanent.id == creature.id:
                continue
            chars = board.of(permanent)
            subtypes = {subtype.lower() for subtype in chars.subtypes}
            if any(
                (card_type is None or card_type in chars.types)
                and (subtype is None or subtype in subtypes)
                for card_type, subtype in quality
            ):
                have += 1
        if have < needed:
            return f'{creature.name} can\'t {action}: "{sentence}" - you control {have} ({rule})'
    return None


#: CR 508.1c: a permanent's static "can't attack" restriction on creatures in
#: general rather than on itself - Ensnaring Bridge's "Creatures with power
#: greater than the number of cards in your hand can't attack.", Reverence's
#: "Creatures with power 2 or less can't attack you.", Peacekeeper's
#: "Creatures can't attack." The power qualifier and the "you" scope are both
#: optional parts of the one template.
_GROUP_CANT_ATTACK_RE = re.compile(
    r"creatures(?: with power (?P<comparison>[^.]+?))? can't attack(?P<you> you)?\.?",
    re.IGNORECASE,
)

#: The power comparison inside that template: "N or less"/"N or greater", or
#: "less/greater than <bound>", where the bound is a number or a count
#: `effects.count_expression` reads ("the number of cards in your hand").
_POWER_COMPARISON_RE = re.compile(
    r"(?:(?P<number>\d+) or (?P<direction>less|greater)"
    r"|(?P<strict>less|greater) than (?P<bound>.+))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GroupAttackRestriction:
    """One parsed "creatures [with power <comparison>] can't attack [you]"
    sentence (CR 508.1c)."""

    sentence: str
    #: "less_or_equal", "greater_or_equal", "less", "greater", or None for no
    #: power qualifier at all.
    operator: str | None = None
    #: A printed bound, or None when `bound_expression` supplies it.
    bound: int | None = None
    bound_expression: str | None = None
    #: "can't attack you": only attacks on the restriction's controller.
    only_attacks_on_controller: bool = False
    #: "Creatures with flying can't attack you ..." (Storm, Windrider;
    #: Sandwurm Convergence): only creatures that have this keyword.
    keyword: str | None = None
    #: "Creatures without flying can't attack you." (Form of the Dragon) -
    #: the same `keyword` field, negated: only a creature that *lacks* it is
    #: restricted.
    keyword_negated: bool = False
    #: "... or planeswalkers you control" (Sandwurm Convergence): attacks on
    #: the controller's planeswalkers are refused too.
    also_planeswalkers: bool = False
    #: "... or block creatures you control" (Storm, Windrider): the same
    #: creatures can't block the controller's creatures (CR 509.1b).
    blocks_creatures_you_control: bool = False


#: "Creatures with flying can't attack you or block creatures you control."
#: (Storm, Windrider); "Creatures with flying can't attack you or
#: planeswalkers you control." (Sandwurm Convergence) - the group picked out
#: by a keyword it has (CR 702) rather than by power, with an optional
#: planeswalker scope (CR 508.1c) and an optional block restriction on the
#: same group (CR 509.1b).
_KEYWORD_GROUP_CANT_ATTACK_RE = re.compile(
    r"creatures with (?P<keyword>[a-z]+(?: [a-z]+)?) can't attack you"
    r"(?P<planeswalkers> or planeswalkers you control)?"
    r"(?P<block> or block creatures you control)?\.?",
    re.IGNORECASE,
)

#: "Creatures without flying can't attack you." (Form of the Dragon) - the
#: negated twin of `_KEYWORD_GROUP_CANT_ATTACK_RE` just above: the same
#: template with "without" in place of "with", restricting every creature
#: that *lacks* the named keyword instead of every one that has it.
_NEGATED_KEYWORD_GROUP_CANT_ATTACK_RE = re.compile(
    r"creatures without (?P<keyword>[a-z]+(?: [a-z]+)?) can't attack you"
    r"(?P<planeswalkers> or planeswalkers you control)?"
    r"(?P<block> or block creatures you control)?\.?",
    re.IGNORECASE,
)


def parse_group_attack_restriction(sentence: str) -> GroupAttackRestriction | None:
    """Read one static sentence into a `GroupAttackRestriction`, or None when
    it is not that template or its comparison cannot be evaluated."""
    text = sentence.strip()
    keyword_group = _KEYWORD_GROUP_CANT_ATTACK_RE.fullmatch(text)
    if keyword_group is not None:
        keyword = keyword_group.group("keyword").lower()
        if keyword not in {member.value.lower() for member in Keyword}:
            return None
        return GroupAttackRestriction(
            sentence=text,
            only_attacks_on_controller=True,
            keyword=keyword,
            also_planeswalkers=keyword_group.group("planeswalkers") is not None,
            blocks_creatures_you_control=keyword_group.group("block") is not None,
        )
    negated_keyword_group = _NEGATED_KEYWORD_GROUP_CANT_ATTACK_RE.fullmatch(text)
    if negated_keyword_group is not None:
        keyword = negated_keyword_group.group("keyword").lower()
        if keyword not in {member.value.lower() for member in Keyword}:
            return None
        return GroupAttackRestriction(
            sentence=text,
            only_attacks_on_controller=True,
            keyword=keyword,
            keyword_negated=True,
            also_planeswalkers=negated_keyword_group.group("planeswalkers") is not None,
            blocks_creatures_you_control=negated_keyword_group.group("block") is not None,
        )
    match = _GROUP_CANT_ATTACK_RE.fullmatch(text)
    if match is None:
        return None
    only_you = match.group("you") is not None
    comparison = match.group("comparison")
    if comparison is None:
        return GroupAttackRestriction(sentence=text, only_attacks_on_controller=only_you)
    power = _POWER_COMPARISON_RE.fullmatch(comparison.strip())
    if power is None:
        return None
    if power.group("number") is not None:
        return GroupAttackRestriction(
            sentence=text,
            operator=f"{power.group('direction').lower()}_or_equal",
            bound=int(power.group("number")),
            only_attacks_on_controller=only_you,
        )
    bound_text = power.group("bound").strip()
    operator = power.group("strict").lower()
    if bound_text.isdigit():
        return GroupAttackRestriction(
            sentence=text,
            operator=operator,
            bound=int(bound_text),
            only_attacks_on_controller=only_you,
        )
    # Imported here: `machines/effects.py` imports this module at load time.
    from .effects import count_expression

    if count_expression(bound_text) is None:
        return None
    return GroupAttackRestriction(
        sentence=text,
        operator=operator,
        bound_expression=bound_text,
        only_attacks_on_controller=only_you,
    )


def is_group_attack_restriction_line(line: str) -> bool:
    """Whether a static line is one `group_attack_restriction_refusal` enforces."""
    return bool(_static_group_attack_restrictions(line))


def _static_group_attack_restrictions(line: str) -> list[GroupAttackRestriction]:
    """The restrictions one ability line states as a *static* ability (CR
    604.1). An activated or triggered line's effect is a resolving ability's
    one-shot continuous effect (CR 611.2), never a standing restriction, so
    `static_only` keeps its cost or trigger condition from being stripped
    and the rest applied permanently."""
    return [
        restriction
        for sentence in layer_readable_sentences(line, static_only=True)
        if (restriction := parse_group_attack_restriction(sentence)) is not None
    ]


def _power_restricted(restriction: GroupAttackRestriction, power: int, bound: int) -> bool:
    if restriction.operator == "less_or_equal":
        return power <= bound
    if restriction.operator == "greater_or_equal":
        return power >= bound
    if restriction.operator == "less":
        return power < bound
    return power > bound


def _self_attack_restriction_sentence(creature: CardState, game: "Game") -> str | None:
    """The creature's own unconditional "can't attack" sentence - "This
    creature can't attack." or "... can't attack or block." - among its
    computed abilities (CR 613.5), or None."""
    subjects = _self_reference_alternatives(creature)
    pattern = re.compile(
        rf"^(?:{'|'.join(re.escape(name) for name in subjects)}) can't attack"
        r"(?: or block)?\.?$",
        re.IGNORECASE,
    )
    for sentence in _computed_ability_sentences(creature, game):
        if pattern.match(sentence.strip()):
            return sentence.strip()
    return None


#: Master of Cruelties' own static: "This creature can only attack alone."
#: CR 508.1c's restriction is "it can't attack unless it attacks alone"
#: (CR 506.5: "A creature attacks alone if it's the only creature declared
#: as an attacker during the declare attackers step") - a restriction about
#: the *whole* declaration, unlike the unconditional "can't attack" sentence
#: just above, so this is only the sentence-finder; `Game.
#: _refuse_attack_alone_violations` is where the declared party is actually
#: checked against it.
def self_attack_alone_only_sentence(creature: CardState, game: "Game") -> str | None:
    """The creature's own "can only attack alone" sentence among its
    computed abilities (CR 613.5), or None."""
    subjects = _self_reference_alternatives(creature)
    pattern = re.compile(
        rf"^(?:{'|'.join(re.escape(name) for name in subjects)}) can only attack alone\.?$",
        re.IGNORECASE,
    )
    for sentence in _computed_ability_sentences(creature, game):
        if pattern.match(sentence.strip()):
            return sentence.strip()
    return None


def reads_self_attack_alone_line(line: str, name: str) -> bool:
    """Whether one printed static line of a creature named `name` is its own
    "can only attack alone" (CR 508.1c) - the restriction
    `self_attack_alone_only_sentence` finds and
    `Game._refuse_attack_alone_violations` enforces on every declaration;
    `support.py`'s credit for it."""
    if "can only attack alone" not in line.lower():
        return False
    subjects = "|".join(re.escape(subject) for subject in _self_reference_names(name))
    pattern = re.compile(rf"^(?:{subjects}) can only attack alone\.?$", re.IGNORECASE)
    sentences = [strip_ability_word(sentence) for sentence in layer_readable_sentences(line)]
    return bool(sentences) and all(pattern.match(sentence.strip()) for sentence in sentences)


def group_attack_restriction_refusal(
    game: "Game", creature: CardState, defender: TargetRef
) -> str | None:
    """Why a battlefield permanent's static group restriction stops this
    creature attacking this defender, or None (CR 508.1c).

    Read off the computed board at the moment asked (CR 611.3a, 613.5), so a
    pump, a draw or a discard before the declaration all count, and a
    permanent that lost the ability or left the battlefield restricts nothing
    (CR 604.2). "You"/"your" is the restricting permanent's controller
    (CR 109.5), whoever controls the creature.
    """
    board = game.computed_board()
    for source in game.battlefield:
        source_characteristics = board.of(source)
        controller = source_characteristics.controller
        for ability in source_characteristics.abilities:
            if "can't attack" not in ability.lower():
                continue
            for restriction in _static_group_attack_restrictions(ability):
                if restriction.only_attacks_on_controller and not (
                    (defender.is_player and defender.username == controller)
                    or (
                        restriction.also_planeswalkers
                        and _is_planeswalker_controlled_by(game, defender, controller)
                    )
                ):
                    continue
                if restriction.keyword is not None:
                    has_it = has_keyword(creature, restriction.keyword, game)
                    if has_it if restriction.keyword_negated else not has_it:
                        continue
                detail = ""
                if restriction.operator is not None:
                    power = board.of(creature).power
                    if power is None:
                        continue
                    bound = restriction.bound
                    if bound is None:
                        from .effects import count_expression

                        reader = count_expression(restriction.bound_expression or "")
                        if reader is None:
                            continue
                        bound = reader(game, controller)
                    if not _power_restricted(restriction, power, bound):
                        continue
                    detail = f" (its power is {power}"
                    if restriction.bound_expression is not None:
                        detail += f"; {restriction.bound_expression} of {controller} is {bound}"
                    detail += ")"
                target = f" {controller}" if restriction.only_attacks_on_controller else ""
                return (
                    f"{creature.name} can't attack{target}: {source.name} "
                    f'says "{restriction.sentence}"{detail} (CR 508.1c)'
                )
    return None


def _is_planeswalker_controlled_by(
    game: "Game", defender: TargetRef, controller: str | None
) -> bool:
    """Whether `defender` is a planeswalker `controller` controls (CR 306)."""
    if defender.is_player or defender.card_id is None:
        return False
    permanent = game.find_by_id(defender.card_id)
    if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
        return False
    chars = game.characteristics_of(permanent)
    return Type.PLANESWALKER in chars.types and chars.controller == controller


def group_block_restriction_refusal(
    game: "Game", blocker: CardState, attacker: CardState
) -> str | None:
    """Why a battlefield permanent's "creatures with `<keyword>` can't ...
    block creatures you control" stops this block, or None (CR 509.1b) -
    Storm, Windrider's second half. "You" is the restricting permanent's
    controller (CR 109.5); read off the computed board when asked (CR
    613.5)."""
    board = game.computed_board()
    attacker_controller = board.of(attacker).controller
    for source in game.battlefield:
        source_characteristics = board.of(source)
        controller = source_characteristics.controller
        if controller != attacker_controller:
            continue
        for ability in source_characteristics.abilities:
            if "can't attack" not in ability.lower():
                continue
            for restriction in _static_group_attack_restrictions(ability):
                if not restriction.blocks_creatures_you_control or restriction.keyword is None:
                    continue
                if not has_keyword(blocker, restriction.keyword, game):
                    continue
                return (
                    f"{blocker.name} can't block {attacker.name}: {source.name} "
                    f'says "{restriction.sentence}" (CR 509.1b)'
                )
    return None


def _cant_be_attacked(game: "Game", permanent: CardState) -> bool:
    """Whether the permanent's own computed text says "`<it>` can't be attacked"
    (The Aetherspark while attached to a creature), read off the computed board
    (CR 613.5) so it holds only while the ability does (CR 611.3a)."""
    names = {name.lower() for name in _self_reference_alternatives(permanent)} | {"this permanent"}
    for sentence in _computed_ability_sentences(permanent, game):
        match = _CANT_BE_ATTACKED_SENTENCE_RE.fullmatch(sentence.strip())
        if match is not None and match["subject"].lower() in names:
            return True
    return False


_CANT_BE_ATTACKED_SENTENCE_RE = re.compile(
    r"^(?P<subject>.+?) can't be attacked\.?$", re.IGNORECASE
)


def _defender_refusal(game: "Game", defender: TargetRef, active: str) -> str | None:
    """Whether this is something the active player may attack (CR 508.1a, 508.1c)."""
    if defender.is_player:
        username = defender.username
        if username == active:
            return "a creature cannot attack its own controller"
        if username is None or not game.is_in_game(username):
            return f"{username} is not a player in this game"
        return None

    permanent = game.resolve_target(defender)
    if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
        return "that permanent is not on the battlefield"
    # `game.characteristics_of(permanent).types`, not `permanent.types` and
    # not `permanent.card.types`: a transformed Ajani, Nacatl Pariah is a
    # planeswalker (CR 712.8e) and may be attacked, and a modal double-faced
    # permanent played as its land face is not (CR 712.8f) - `permanent.types`
    # already reads whichever face is up, so it gets both of those right, but
    # it is still only CR 613.1's *starting point*. CR 613.5 has the layer
    # system applied "continually", so a layer-4 effect that grants
    # planeswalker or battle after that starting point is read must be seen
    # too, the same reasoning `characteristics_of` already gets right for
    # every other computed read in this file.
    types = set(game.characteristics_of(permanent).types)
    if not types & ATTACKABLE_PERMANENT_TYPES:
        return f"{permanent.name} is not a player, planeswalker, or battle"
    if _cant_be_attacked(game, permanent):
        return f"{permanent.name} can't be attacked (CR 508.1c)"
    if Type.BATTLE in types:
        # CR 310.9b: "A battle's protector can never attack it. A battle can
        # be attacked by any attacking player for whom its protector is a
        # defending player. Notably, a Siege battle can be attacked by its
        # own controller." Who controls it is not the question. Any in-game
        # protector other than the active player is treated as a defending
        # player, which holds while every opponent is one (a two-player
        # game, CR 506.2, or the attack multiple players option, CR 506.2a).
        protector = permanent.protector
        if protector == active:
            return (
                f"{permanent.name} is protected by {active}, and a battle's "
                "protector can never attack it (CR 310.9b)"
            )
        if protector is None or not game.is_in_game(protector):
            return f"{permanent.name} has no protector to defend it (CR 310.9b)"
        return None
    if game.controller_of(permanent).username == active:
        return f"{permanent.name} is not controlled by an opponent"
    return None


def attackable_defenders(game: "Game", active: str) -> list[TargetRef]:
    """Everything `active` could have a creature attack right now: each other
    player still in the game, and each planeswalker or battle that
    `_defender_refusal` accepts - the same test a declared attack is held to.

    CR 508.4's choice for a creature put onto the battlefield attacking is
    made among exactly these ("which defending player, planeswalker a
    defending player controls, or battle a defending player protects").
    """
    candidates = [
        TargetRef.coerce(player.username)
        for player in game.players_in_game
        if player.username != active
    ]
    candidates.extend(TargetRef.coerce(permanent) for permanent in game.battlefield)
    return [
        candidate for candidate in candidates if _defender_refusal(game, candidate, active) is None
    ]


def declare_attacker(game: "Game", creature: CardState, defender: TargetRef) -> Attack:
    """Declare one attacker, tapping it unless it has vigilance.

    Tapping is not a cost - attacking simply causes it (CR 508.1f) - so a
    creature that is somehow already tapped is refused earlier rather than
    failing to pay. A creature that taps this way became tapped (CR 701.26a),
    which is its own trigger event; one with vigilance (CR 702.20b) never
    taps, and so never fires it.
    """
    refusal = attack_refusal(game, creature, defender)
    if refusal is not None:
        raise ValueError(refusal)

    if not has_keyword(creature, Keyword.VIGILANCE, game):
        creature.tap()  # CR 508.1f
        # CR 613.5: the subject's actual types, as `Game.emit_became_tapped`
        # documents.
        game.emit_became_tapped(creature, declared_attacker=True)

    game.combat.attacked_this_combat = True  # CR 508.8 reads the declaration
    attack = Attack(attacker_id=creature.id, defender=defender)
    game.combat.attacks.append(attack)
    game.combat.declared_attacking_power += game.power_of(creature) or 0
    return attack


# -- declaring blockers ----------------------------------------------------


class EvasionNotice(EngineModel):
    """One permanent whose own "can't be blocked" *or* "can't block" text
    could not be fully read into a block refusal (CR 509.1b).

    Unlike flying (CR 702.9b), reach (CR 702.17b), or landwalk (CR 702.14c),
    neither restriction carries a keyword name of its own - each is read
    straight off the permanent's own oracle text, the attacker's by
    `evasion_restriction_refusal` and the blocker's by
    `self_block_restriction_refusal`, and only the shapes those two functions
    read are enforced. A sentence that opens the same way ("<subject> can't be
    blocked ..." or "<subject> can't block ...") but is not one of the read
    shapes is not silently treated as no restriction at all:
    `looks_like_unparsed_evasion_restriction` and
    `looks_like_unparsed_self_block_restriction` catch it and `block_refusal`
    records one of these instead, the same "unreadable is not the same as no
    effect" record `LayerNotice`, `TargetingNotice`, `InterveningIfNotice`,
    `ModeNotice`, and `AnaphoricClauseNotice` already keep for their own gaps.
    One list serves both directions because they are the same rule's two
    mirror-image halves - CR 509.1b's "can't be blocked" (an evasion ability
    on the attacker) and its "can't block" (a restriction on the blocker
    itself) - read by the same fail-closed discipline.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The permanent's own oracle text, for whoever reads the notice later."""


def _self_reference_alternatives(state: CardState) -> tuple[str, ...]:
    """Every way `state`'s own oracle text could name itself in a
    self-restriction sentence, longest first so a regex alternation tries the
    most specific match: the generic "this creature"/"this token", the full
    printed name, the short name before a comma (CR 201.5c's legendary
    short-name convention - "April O'Neil can't be blocked ..." on a card
    printed "April O'Neil, Kunoichi Trainee" - the same self-reference
    `machines/triggers.py`'s `_self_referential` already reads), and - Zurgo
    Bellstriker's own templating, "Zurgo can't block creatures with power 2
    or greater." on a card with no comma at all - the bare first word of a
    comma-less name.

    `state.name` already reads the up face (CR 712.8d/712.8f) - same family
    as `effect_for`'s fix for a modal-DFC/transform permanent's raw,
    "Front // Back"-combined `card.name`.
    """
    return _self_reference_names(state.name)


def _self_reference_names(name: str) -> tuple[str, ...]:
    """`_self_reference_alternatives` for a bare name."""
    words = name.split()
    candidates = {"this creature", "this token", name, name.split(",")[0].strip()}
    if len(words) > 1 and "," not in name:
        candidates.add(words[0])
    return tuple(
        sorted((candidate for candidate in candidates if candidate), key=len, reverse=True)
    )


def _evasion_restriction_sentences(attacker: CardState, game: "Game | None" = None) -> list[str]:
    """Self-referential "can't be blocked" sentences the attacker has *now*
    (CR 509.1b): the subject must be one of `_self_reference_alternatives`
    (CR 509.1b's restriction is on the attacker itself). A group grant -
    Deepchannel Mentor's "Blue creatures you control can't be blocked." - is
    not read here directly: `layers._group_evasion_grant_builder` grants it
    onto each qualifying creature as a self-referential line, which this
    reader then picks up like any printed one.

    Which sentences those are is CR 613.5's question, the same one `has_keyword`
    asks: "the application of continuous effects as described by the layer
    system is continually and automatically performed by the game", so the
    abilities the layer system leaves the permanent with are the answer and the
    printed oracle text is not. Dress Down is the card in the pool that makes
    the difference visible - "Creatures lose all abilities" is a layer 6
    ability-removing effect (CR 613.1f), and a Mindskinner that has lost its
    text can be blocked like anything else.

    Without a game there is no board to compute (a card outside the
    battlefield has only what is printed on it), so the printing's own text is
    the answer - which is what every caller used before.

    A sentence also counts here when it reads "can't block or be blocked by
    <description>" rather than "can't be blocked" outright - Realm of Koh's
    Spirit token's own compound restriction, whose "be blocked by" half is a
    second, independent evasion restriction sharing one description with its
    "can't block" half (`_self_block_restriction_sentences` reads that half).
    """
    subjects = _self_reference_alternatives(attacker)
    subject = re.compile(
        rf"^(?:{'|'.join(re.escape(name) for name in subjects)})\b"
        rf".*(?:can't be blocked\b|can't block or be blocked by\b)",
        re.IGNORECASE,
    )
    sentences = _computed_ability_sentences(attacker, game)
    return [sentence for sentence in sentences if subject.search(sentence)]


def attacker_cap_restriction(defender: CardState, game: "Game | None" = None) -> str | None:
    """The sentence granting `defender` (a planeswalker or battle being
    attacked) a "no more than one creature can attack this `<subject>` each
    combat" restriction (CR 508.1c), off the computed board - or `None`.

    Read the same self-referential way `_evasion_restriction_sentences`
    already reads "can't be blocked": "this planeswalker"/"this battle" (a
    granted line - Tomik, Orzhov Lawmage's own "Planeswalkers you control
    have '...'", `machines.layers._group_quoted_ability_grant_builder`), or
    the card's own short name (a self-printed line - The Eternal Wanderer's
    own "No more than one creature can attack The Eternal Wanderer each
    combat.", off-set). Unlike CR 508.1c's *per-creature* restrictions
    (`attack_refusal`), this one is a fact about the *defender*, checked once
    per declared attack against it rather than once per attacking creature -
    which is why it lives here, read by `Game.declare_attackers` over the
    whole declaration, rather than inside `attack_refusal`.
    """
    short_name = defender.name.split(",")[0].strip()
    subject = re.compile(
        rf"no more than one creature can attack (?:this planeswalker|this battle|"
        rf"{re.escape(short_name)})\b.*each combat",
        re.IGNORECASE,
    )
    for sentence in _computed_ability_sentences(defender, game):
        if subject.search(sentence):
            return sentence
    return None


def _computed_ability_sentences(state: CardState, game: "Game | None") -> list[str]:
    """The permanent's abilities as sentences, off the computed board (CR 613.5).

    Falls back to the printed text when there is nothing to compute against -
    no game, or a card that is not on the battlefield, since CR 613 applies to
    objects on the battlefield.
    """
    if game is not None and state.zone is Zone.BATTLEFIELD:
        characteristics = game.characteristics_of(state)
        if characteristics is not None:
            return [
                strip_ability_word(sentence)
                for ability in characteristics.abilities
                for sentence in layer_readable_sentences(ability)
            ]
    return [
        strip_ability_word(sentence) for sentence in layer_readable_sentences(state.oracle_text)
    ]


#: An ability word or flavor word label in front of a sentence - "Intangibility
#: - Ghost can't be blocked." (Ghost, Spectral Saboteur). CR 207.2c: an ability
#: word "has no special rules meaning", so a restriction reader reads the
#: sentence behind it.
_ABILITY_WORD_LABEL_RE = re.compile(r"^[A-Z][^.\u2014]*? \u2014 (?P<rest>\S.*)$")


def strip_ability_word(sentence: str) -> str:
    """`sentence` with a leading ability-word label removed (CR 207.2c)."""
    match = _ABILITY_WORD_LABEL_RE.match(sentence.strip())
    return match.group("rest") if match else sentence


#: The Mindskinner: "The Mindskinner can't be blocked." - unconditional.
_CANT_BE_BLOCKED_RE = re.compile(r"can't be blocked\.?$", re.IGNORECASE)

#: Stature, Size Shifter: "Stature can't be blocked if her power is 1 or
#: less."; Thieves' Tools' grant, "This creature can't be blocked as long as
#: its power is 3 or less." - the plain restriction (CR 509.1b) that applies
#: only while the attacker's own power, as the layer system leaves it (CR
#: 613.5), is at or under the printed number.
_CANT_BE_BLOCKED_WHILE_POWER_AT_MOST_RE = re.compile(
    r"can't be blocked (?:if|as long as) (?:its|his|her|their) power is (?P<power>\d+) or "
    r"less\.?$",
    re.IGNORECASE,
)

#: Questing Beast: "Questing Beast can't be blocked by creatures with power 2
#: or less." - the one power-qualified shape given its own dedicated reader;
#: a colour (Vine Mare) or keyword (Skyscythe Engulfer) qualifier is read by
#: the general `_CANT_BE_BLOCKED_BY_DESCRIPTION_RE` fallback instead of a
#: shape of its own.
_CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE = re.compile(
    r"can't be blocked by creatures with power (?P<power>\d+) or less\.?$", re.IGNORECASE
)

#: April O'Neil, Kunoichi Trainee: "April O'Neil can't be blocked by
#: creatures with power 3 or greater." - the mirror direction of Questing
#: Beast's "or less" (`_CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE`), read the same
#: way: a printed number compared against the *blocker's* computed power
#: (CR 613.5), never the attacker's own.
_CANT_BE_BLOCKED_BY_POWER_OR_GREATER_RE = re.compile(
    r"can't be blocked by creatures with power (?P<power>\d+) or greater\.?$", re.IGNORECASE
)

#: Fugitive Droid: "This creature can't be blocked if an artifact entered
#: the battlefield under your control this turn."; Tanglewalker's own group
#: grant, once read onto a creature by `layers._group_evasion_grant_builder`:
#: "This creature can't be blocked as long as defending player controls an
#: artifact land." - CR 509.1b's restriction with an arbitrary printed
#: condition rather than a power comparison of its own, "if" and "as long as"
#: accepted the same way `_CANT_BE_BLOCKED_WHILE_POWER_AT_MOST_RE` already
#: takes both for its own power comparison. The condition itself is read the
#: same generic way every other condition-gated reader in the pool already
#: asks `Game.condition_holds` - `machines/conditions/history._counted_entered`
#: already claims "an artifact entered the battlefield under your control
#: this turn" for an intervening "if"/"as long as"/modal condition, so this is
#: not a new condition reader, only a new *place* that hands a tail to the
#: existing one.
_CANT_BE_BLOCKED_IF_CONDITION_RE = re.compile(
    r"can't be blocked (?:if|as long as) (?P<condition>.+?)\.?$", re.IGNORECASE
)

#: "can't be blocked by creatures with greater power" - a comparison against
#: the attacker's own power rather than a printed number. The Ring grants it
#: to its controller's Ring-bearer (CR 701.54c); CR 509.1b is the block it
#: refuses.
_CANT_BE_BLOCKED_BY_GREATER_POWER_RE = re.compile(
    r"can't be blocked by creatures with greater power\.?$", re.IGNORECASE
)

#: Duskwatch Hunter: "This creature can't be blocked by tokens." - CR 111.1's
#: token-ness (`models.token.is_token`), read off the blocker rather than off
#: `_CREATURE_DESCRIPTION_RE`'s closed "creatures?" noun: "tokens" is a
#: different count noun than "creatures", not a "creatures" sentence with an
#: adjective in front of it, so it gets its own shape rather than stretching
#: that regex's literal word to match a different one.
_CANT_BE_BLOCKED_BY_TOKENS_RE = re.compile(r"can't be blocked by tokens\.?$", re.IGNORECASE)

#: Realm of Koh's Spirit token: "can't block or be blocked by <description>."
#: - one shared description restricting both halves of the compound: the
#: "be blocked by" half is an evasion restriction read here, and the "can't
#: block" half feeds `_parse_self_block_restriction` below.
_CANT_BLOCK_OR_BE_BLOCKED_BY_RE = re.compile(
    r"can't block or be blocked by (?P<description>.+?)\.?$", re.IGNORECASE
)

#: "can't be blocked except by creatures with `<keyword>`." - Speed, Young
#: Avenger's own granted rider ("target creature with haste can't be blocked
#: this turn except by creatures with haste"; `machines/effects.py`'s
#: `_TARGET_CANT_BE_BLOCKED_RE` grants exactly this text, verbatim, once the
#: keyword names a real `Keyword` member). CR 509.1b's restriction with its
#: own "unless" shape folded onto it: the attacker still can't be
#: blocked, except by a creature that itself has the named keyword right now
#: (CR 613.5 - a blocker that gains the keyword mid-combat qualifies; one
#: that loses it does not).
_CANT_BE_BLOCKED_EXCEPT_BY_KEYWORD_RE = re.compile(
    r"can't be blocked except by creatures with (?P<keyword>[a-z][a-z ]*?)\.?$", re.IGNORECASE
)


def block_exception_keyword(name: str) -> "Keyword | None":
    """`name`, lowercased and stripped, as a `Keyword` member - or `None` when
    it names something `evasion_restriction_refusal` has no keyword for. Kept
    to a real `Keyword`, the same closed vocabulary `has_keyword` already
    answers every other combat question against, so an exception naming a
    keyword outside it fails closed (`looks_like_unparsed_evasion_
    restriction`) rather than silently exempting nothing - or everything."""
    try:
        return Keyword(name.strip().lower())
    except ValueError:
        return None


#: A bare card-type adjective inside a creature description - Hinterland
#: Drake's "artifact creatures". Only the types the pool actually needs are
#: read; an adjective this does not recognise, and is not a "non-<subtype>"
#: exclusion, a colour (`_CREATURE_DESCRIPTION_COLOR_WORDS`) or a real
#: subtype either, leaves the whole description unparsed rather than
#: guessed at.
_CREATURE_DESCRIPTION_TYPE_WORDS: dict[str, "Type"] = {
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
}

#: The five colour words a creature description can lead with - Vine Mare's
#: "can't be blocked by black creatures" (CR 105.1), White Scarab's granted
#: "Enchanted creature can't be blocked by white creatures." Kept as its own
#: small copy the way `casting.py`'s and `layers.py`'s own `_COLOR_WORDS`
#: already are: `combat.py` cannot import either module at module scope
#: (`layers.py` imports `combat.py`, so the reverse import would cycle).
_CREATURE_DESCRIPTION_COLOR_WORDS: dict[str, "Color"] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}

#: One creature description inside a "can't block <description>", "can't be
#: blocked by <description>" or "can't block or be blocked by <description>"
#: sentence (CR 509.1b): an optional leading adjective - a recognised card-type
#: word, a colour (Vine Mare), a bare creature subtype ("Spirit"), or a
#: "non-<subtype>" exclusion (Realm of Koh's token's own "non-Spirit") -
#: followed by "creature(s)", with an optional trailing qualifier: a power or
#: toughness comparison (Zurgo Bellstriker's "with power 2 or greater",
#: Ghost of Ramirez DePietro's "with toughness 3 or greater" - the same "N or
#: less"/"N or greater" shape `_POWER_COMPARISON_RE` already reads for CR
#: 508.1c's group attack restriction) or a keyword the blocker must have
#: (Skyscythe Engulfer's "with flying" - CR 702's closed `Keyword` vocabulary,
#: the same one `_CANT_BE_BLOCKED_EXCEPT_BY_KEYWORD_RE`'s "except by creatures
#: with `<keyword>`" already reads).
_CREATURE_DESCRIPTION_RE = re.compile(
    r"^(?:(?P<adjective>[a-z][a-z'-]*)\s+)?creatures?"
    r"(?:\s+with\s+(?:"
    r"power\s+(?P<power_number>\d+)\s+or\s+(?P<power_direction>less|greater)"
    r"|toughness\s+(?P<toughness_number>\d+)\s+or\s+(?P<toughness_direction>less|greater)"
    r"|(?P<keyword>[a-z][a-z ]*?)"
    r"))?\.?$",
    re.IGNORECASE,
)

#: A bare plural (or singular) creature-type noun with no "creature(s)" word
#: at all - Juggernaut's "can't be blocked by Walls." (CR 205.3m: "Wall" is a
#: creature type in its own right, not an adjective in front of the count
#: noun "creatures" the way "artifact creatures"/"Spirit creatures" are).
#: `canonical_subtype` is what tells a real, pluralised creature type
#: ("Walls" -> "wall") from an ordinary English word this must not guess a
#: meaning for.
_BARE_SUBTYPE_DESCRIPTION_RE = re.compile(r"^[A-Za-z][A-Za-z'-]*$")


@dataclass(frozen=True)
class _CreatureDescriptionMatcher:
    """A parsed creature description (see `_CREATURE_DESCRIPTION_RE`), ready
    to judge one candidate creature against it (CR 613.5: computed, not
    printed)."""

    required_type: "Type | None" = None
    required_subtype: str | None = None
    excluded_subtype: str | None = None
    required_color: "Color | None" = None
    required_keyword: "Keyword | None" = None
    power_operator: str | None = None
    power_bound: int | None = None
    toughness_operator: str | None = None
    toughness_bound: int | None = None

    def matches(self, game: "Game", candidate: CardState) -> bool:
        characteristics = game.characteristics_of(candidate)
        if characteristics is None:
            return False
        if self.required_type is not None and self.required_type not in characteristics.types:
            return False
        if self.required_color is not None and self.required_color not in characteristics.colors:
            return False
        subtypes_lower = {subtype.lower() for subtype in characteristics.subtypes}
        if (
            self.required_subtype is not None
            and self.required_subtype.lower() not in subtypes_lower
        ):
            return False
        if self.excluded_subtype is not None and self.excluded_subtype.lower() in subtypes_lower:
            return False
        if self.power_operator is not None:
            power = game.power_of(candidate)
            if power is None:
                return False
            if self.power_operator == "greater_or_equal" and power < (self.power_bound or 0):
                return False
            if self.power_operator == "less_or_equal" and power > (self.power_bound or 0):
                return False
        if self.toughness_operator is not None:
            toughness = game.toughness_of(candidate)
            if toughness is None:
                return False
            if self.toughness_operator == "greater_or_equal" and toughness < (
                self.toughness_bound or 0
            ):
                return False
            if self.toughness_operator == "less_or_equal" and toughness > (
                self.toughness_bound or 0
            ):
                return False
        if self.required_keyword is not None:
            return has_keyword(candidate, self.required_keyword, game)
        return True


@dataclass(frozen=True)
class _CreatureDescriptionAlternatives:
    """ "`<a>` or `<b>`" - Blazing Torch's "Vampires or Zombies": the whole
    description is satisfied when *either* alternative's own closed grammar
    matches. CR 509.1b names no boolean combinator of its own; this reads
    the disjunction the same plain-English way `_parse_type_list` already
    reads "Wolf or Werewolf" for CR 508.1c/509.1b's group restrictions."""

    alternatives: tuple["_CreatureDescriptionMatcher", ...]

    def matches(self, game: "Game", candidate: CardState) -> bool:
        return any(alternative.matches(game, candidate) for alternative in self.alternatives)


#: Sacred Knight: "This creature can't be blocked by black and/or red
#: creatures." - an adjective *list* sharing one trailing noun phrase printed
#: once at the end ("creature(s)[ with ...]"), rather than once per adjective
#: the way "Vampires or Zombies" prints two complete, self-sufficient bare
#: subtypes with nothing elided. "and/or" (the same connective CR 702.9b
#: prints as "flying and/or reach") is the same inclusive-or
#: `_CreatureDescriptionAlternatives` already gives a bare "or" list; a plain
#: "or" joining the adjectives, and an Oxford-comma list of three or more
#: ending in ", or"/", and/or", read the identical way once the noun is
#: reattached. A plain "and" ("white and blue creatures") is deliberately
#: *not* read: it may mean a creature that is both, so it fails closed with
#: a notice rather than being guessed as "either".
_ELIDED_NOUN_LIST_RE = re.compile(
    r"^(?P<items>[a-z][a-z'-]*(?:(?:,\s*(?:and/or\s+|or\s+)?|\s+and/or\s+|\s+or\s+)[a-z][a-z'-]*)+)"
    r"\s+(?P<rest>creatures?.*)$",
    re.IGNORECASE,
)

_ELIDED_NOUN_LIST_ITEM_SEP_RE = re.compile(
    r",\s*(?:and/or\s+|or\s+)?|\s+and/or\s+|\s+or\s+", re.IGNORECASE
)


def _parse_elided_noun_list(description: str) -> "tuple[_CreatureDescriptionMatcher, ...] | None":
    """Read "black and/or red creatures" into one matcher per adjective, each
    reconstructed as "`<adjective>` `<the shared trailing noun phrase>`" and
    read by the ordinary single-description grammar - so a colour, card type,
    or subtype adjective in the list is read exactly the way it would be read
    alone (Sacred Knight's own two colours; nothing in the pool needs a third
    item or a mixed adjective kind, but the grammar does not special-case the
    count or the kind). `None` when the shape does not match, or when any
    item - reconstructed with the shared tail - does not itself parse."""
    match = _ELIDED_NOUN_LIST_RE.fullmatch(description.strip())
    if match is None:
        return None
    items = [item.strip() for item in _ELIDED_NOUN_LIST_ITEM_SEP_RE.split(match.group("items"))]
    items = [item for item in items if item]
    if len(items) < 2:
        return None
    rest = match.group("rest")
    matchers: list[_CreatureDescriptionMatcher] = []
    for item in items:
        matcher = _parse_single_creature_description(f"{item} {rest}")
        if matcher is None:
            return None
        matchers.append(matcher)
    return tuple(matchers)


def _parse_creature_description(
    description: str,
) -> "_CreatureDescriptionMatcher | _CreatureDescriptionAlternatives | None":
    """`_parse_single_creature_description`, widened to a disjunction of two
    or more descriptions - either each a complete, self-sufficient
    description joined by "or" (Blazing Torch's "Vampires or Zombies"), or an
    adjective list sharing one elided trailing noun phrase (Sacred Knight's
    "black and/or red creatures", `_parse_elided_noun_list`) - when the whole
    text is not itself one description.

    The whole-text reading is tried first and, when it succeeds, returned
    as-is: "creatures with power 2 or less" is one description whose own
    grammar happens to contain the word "or" (Questing Beast), not two
    descriptions "creatures with power 2" and "less" - splitting blind on
    every "or" before trying the whole text would misread it. Only a text
    the whole-text grammar cannot place is then tried as an elided-noun list,
    then as a plain disjunction of complete sides; if either shape's sides do
    not all parse, the whole thing fails closed rather than matching on the
    sides that do.
    """
    whole = _parse_single_creature_description(description)
    if whole is not None:
        return whole
    elided = _parse_elided_noun_list(description)
    if elided is not None:
        return _CreatureDescriptionAlternatives(alternatives=elided)
    parts = [part.strip() for part in re.split(r"\s+or\s+", description.strip(), flags=re.I)]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return None
    matchers: list[_CreatureDescriptionMatcher] = []
    for part in parts:
        matcher = _parse_single_creature_description(part)
        if matcher is None:
            return None
        matchers.append(matcher)
    return _CreatureDescriptionAlternatives(alternatives=tuple(matchers))


def _parse_single_creature_description(description: str) -> "_CreatureDescriptionMatcher | None":
    """Read a creature description - "artifact creatures", "non-Spirit
    creatures", "creatures with power 2 or greater", "creatures with flying",
    "black creatures", or a bare creature type ("Walls") - into a matcher, or
    None when it is not this closed grammar. That None is the fail-closed
    signal for whichever "can't be blocked ..."/"can't block ..." sentence it
    came from (or for `_parse_creature_description`'s own disjunction, one
    side of an "or"): a description this cannot judge is never silently
    treated as "matches nothing"."""
    text = description.strip()
    match = _CREATURE_DESCRIPTION_RE.fullmatch(text)
    if match is None:
        # No "creature(s)" noun at all - Juggernaut's bare "Walls" (CR
        # 205.3m). Read only when the whole description canonicalises to a
        # real creature type; an ordinary English word (Duskwatch Hunter's
        # "tokens", which is CR 111.1 token-ness rather than a subtype) is
        # left to its own reader instead of being guessed at here.
        if _BARE_SUBTYPE_DESCRIPTION_RE.fullmatch(text) is None:
            return None
        subtype = canonical_subtype(text)
        return None if subtype is None else _CreatureDescriptionMatcher(required_subtype=subtype)
    power_operator: str | None = None
    power_bound: int | None = None
    if match.group("power_number") is not None:
        power_bound = int(match.group("power_number"))
        power_operator = (
            "greater_or_equal"
            if match.group("power_direction").lower() == "greater"
            else "less_or_equal"
        )
    toughness_operator: str | None = None
    toughness_bound: int | None = None
    if match.group("toughness_number") is not None:
        toughness_bound = int(match.group("toughness_number"))
        toughness_operator = (
            "greater_or_equal"
            if match.group("toughness_direction").lower() == "greater"
            else "less_or_equal"
        )
    required_keyword: Keyword | None = None
    if match.group("keyword") is not None:
        required_keyword = block_exception_keyword(match.group("keyword"))
        if required_keyword is None:
            # Not one of `Keyword`'s closed vocabulary - fail closed rather
            # than silently matching every creature or none.
            return None
    bounds = {
        "power_operator": power_operator,
        "power_bound": power_bound,
        "toughness_operator": toughness_operator,
        "toughness_bound": toughness_bound,
        "required_keyword": required_keyword,
    }
    adjective = (match.group("adjective") or "").strip()
    if not adjective:
        return _CreatureDescriptionMatcher(**bounds)
    lowered = adjective.lower()
    if lowered.startswith("non-"):
        excluded = adjective[len("non-") :].strip()
        if not excluded:
            return None
        canonical_excluded = canonical_subtype(excluded)
        if canonical_excluded is None:
            return None
        return _CreatureDescriptionMatcher(excluded_subtype=canonical_excluded, **bounds)
    type_word = _CREATURE_DESCRIPTION_TYPE_WORDS.get(lowered)
    if type_word is not None:
        return _CreatureDescriptionMatcher(required_type=type_word, **bounds)
    color = _CREATURE_DESCRIPTION_COLOR_WORDS.get(lowered)
    if color is not None:
        return _CreatureDescriptionMatcher(required_color=color, **bounds)
    canonical = canonical_subtype(adjective)
    if canonical is None:
        return None
    return _CreatureDescriptionMatcher(required_subtype=canonical, **bounds)


#: Juggernaut: "This creature can't be blocked by Walls." (a bare creature
#: type, CR 205.3m); Vine Mare: "... by black creatures." (a colour, CR
#: 105.1); Audacious Infiltrator: "... by artifact creatures." (a card type,
#: CR 509.1b's own reminder text: "an evasion ability ... restricts what can
#: block it"); Skyscythe Engulfer: "... by creatures with flying." (a
#: keyword, CR 702); Blazing Torch: "... by Vampires or Zombies." (a
#: disjunction, `_parse_creature_description`'s own widening). One general
#: "by `<description>`" shape, read the same way `_CANT_BLOCK_OR_BE_BLOCKED_
#: BY_RE`'s compound already reads its own evasion half -
#: `_parse_creature_description` is the single grammar behind both. Tried
#: only after every narrower "by ..." shape above (tokens, a bare power
#: comparison, "greater power") and `_CANT_BE_BLOCKED_BY_DESCRIPTION_WHILE_
#: CONDITION_RE` below have already had their turn, so this is a fallback for
#: the unconditional quality comparisons those do not cover, never a second
#: reading of the ones they do; a description outside the closed grammar (a
#: disjunction with a side this cannot place, or any other shape) is left
#: for `looks_like_unparsed_evasion_restriction`'s fail-closed notice.
_CANT_BE_BLOCKED_BY_DESCRIPTION_RE = re.compile(
    r"can't be blocked by (?P<description>.+?)\.?$", re.IGNORECASE
)

#: Arctic Foxes: "This creature can't be blocked by creatures with power 2 or
#: greater as long as defending player controls a snow land." - CR 509.1b's
#: quality comparison with an external condition folded onto it (rather than
#: the *attacker's own* power the way `_CANT_BE_BLOCKED_WHILE_POWER_AT_MOST_
#: RE` reads, or an unqualified condition the way `_CANT_BE_BLOCKED_IF_
#: CONDITION_RE` reads with no "by" at all): both the blocker's quality and
#: the board condition must hold. The condition itself is read through the
#: same `Game.condition_holds`/`condition_is_readable` registry every other
#: condition-gated reader in the pool already asks - "defending player
#: controls a snow land" is already one of `machines/conditions/board.py`'s
#: own "`<who>` controls `<amount>` `<quality>`" templates, so this widens
#: no condition grammar, only the *place* a tail like it can be handed to.
_CANT_BE_BLOCKED_BY_DESCRIPTION_WHILE_CONDITION_RE = re.compile(
    r"can't be blocked by (?P<description>.+?) (?:if|as long as) (?P<condition>.+?)\.?$",
    re.IGNORECASE,
)


def evasion_restriction_refusal(
    game: "Game", attacker: CardState, blocker: CardState
) -> str | None:
    """Why the attacker's own "can't be blocked" text refuses this blocker, or
    None (CR 509.1b: "A restriction may be created by an evasion ability (a
    static ability an attacking creature has that restricts what can block
    it)." - looked up this session; earlier waves of this reader cited
    509.1a, the declare-blockers *action* rather than the restriction that
    can make one particular declaration illegal, because the fuller lettered
    text was not readable in the session that first wrote it).

    Read straight off the attacker's own oracle text rather than off
    `Keyword`: unlike flying or menace, this restriction has no keyword name of
    its own, so nothing in this module's vocabulary can name it. The plain
    shape, the power/toughness-qualified shapes, the general "by
    `<description>`" shape (a subtype, card type, colour, a keyword quality,
    or a disjunction of two such qualities - `_parse_creature_description`),
    that same quality further gated by an external board condition (Arctic
    Foxes' "... as long as defending player controls a snow land"), and the
    "can't block or be blocked by <description>" compound's evasion half are
    read; a sentence that looks like an attempt at another shape is caught by
    `looks_like_unparsed_evasion_restriction` instead of silently doing
    nothing.
    """
    for sentence in _evasion_restriction_sentences(attacker, game):
        compound = _CANT_BLOCK_OR_BE_BLOCKED_BY_RE.search(sentence)
        if compound is not None:
            description = compound.group("description")
            matcher = _parse_creature_description(description)
            if matcher is not None and matcher.matches(game, blocker):
                return (
                    f'{attacker.name} can\'t be blocked by {description}: "{sentence}" (CR 509.1b)'
                )
            continue
        if match := _CANT_BE_BLOCKED_EXCEPT_BY_KEYWORD_RE.search(sentence):
            keyword_name = match.group("keyword").strip()
            keyword = block_exception_keyword(keyword_name)
            if keyword is None:
                # Not one of `Keyword`'s closed vocabulary - unread, so this
                # sentence falls through to `looks_like_unparsed_evasion_
                # restriction`'s fail-closed notice rather than being treated
                # as either "nobody may block" or "everybody may".
                continue
            if has_keyword(blocker, keyword, game):
                continue
            return (
                f"{attacker.name} can't be blocked except by creatures with "
                f"{keyword_name}, and {blocker.name} doesn't have {keyword_name} (CR 509.1b)"
            )
        if _CANT_BE_BLOCKED_BY_GREATER_POWER_RE.search(sentence):
            attacker_power = game.power_of(attacker)
            blocker_power = game.power_of(blocker)
            if (
                attacker_power is not None
                and blocker_power is not None
                and blocker_power > attacker_power
            ):
                return (
                    f"{attacker.name} can't be blocked by creatures with greater power, and "
                    f"{blocker.name} has power {blocker_power} to its {attacker_power} "
                    "(CR 509.1b)"
                )
            continue
        if match := _CANT_BE_BLOCKED_WHILE_POWER_AT_MOST_RE.search(sentence):
            ceiling = int(match.group("power"))
            attacker_power = game.power_of(attacker)
            if attacker_power is not None and attacker_power <= ceiling:
                return (
                    f"{attacker.name} can't be blocked while its power is {ceiling} or less, "
                    f"and its power is {attacker_power} (CR 509.1b)"
                )
            continue
        if match := _CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE.search(sentence):
            threshold = int(match.group("power"))
            blocker_power = game.power_of(blocker)
            if blocker_power is not None and blocker_power <= threshold:
                return (
                    f"{attacker.name} can't be blocked by creatures with power "
                    f"{threshold} or less, and {blocker.name} has power {blocker_power} "
                    "(CR 509.1b)"
                )
            continue
        if match := _CANT_BE_BLOCKED_BY_POWER_OR_GREATER_RE.search(sentence):
            threshold = int(match.group("power"))
            blocker_power = game.power_of(blocker)
            if blocker_power is not None and blocker_power >= threshold:
                return (
                    f"{attacker.name} can't be blocked by creatures with power "
                    f"{threshold} or greater, and {blocker.name} has power {blocker_power} "
                    "(CR 509.1b)"
                )
            continue
        if match := _CANT_BE_BLOCKED_IF_CONDITION_RE.search(sentence):
            condition = match.group("condition")
            held = game.condition_holds(
                game.controller_of(attacker).username or "", condition, attacker
            )
            if held:
                return f'{attacker.name} can\'t be blocked: "{sentence}" (CR 509.1b)'
            continue
        if match := _CANT_BE_BLOCKED_BY_DESCRIPTION_WHILE_CONDITION_RE.search(sentence):
            description = match.group("description")
            condition = match.group("condition")
            matcher = _parse_creature_description(description)
            if matcher is not None and matcher.matches(game, blocker):
                held = game.condition_holds(
                    game.controller_of(attacker).username or "", condition, attacker
                )
                if held:
                    return (
                        f"{attacker.name} can't be blocked by {description} while "
                        f'{condition}: "{sentence}" (CR 509.1b)'
                    )
            continue
        if _CANT_BE_BLOCKED_BY_TOKENS_RE.search(sentence):
            if is_token(blocker):
                return (
                    f"{attacker.name} can't be blocked by tokens, and {blocker.name} "
                    "is one (CR 509.1b, CR 111.1)"
                )
        elif match := _CANT_BE_BLOCKED_BY_DESCRIPTION_RE.search(sentence):
            description = match.group("description")
            matcher = _parse_creature_description(description)
            if matcher is not None and matcher.matches(game, blocker):
                return (
                    f'{attacker.name} can\'t be blocked by {description}: "{sentence}" (CR 509.1b)'
                )
        elif _CANT_BE_BLOCKED_RE.search(sentence):
            return f"{attacker.name} can't be blocked (CR 509.1b)"
    return None


#: Akawalli, the Seething Tower's descend 8 clause grants exactly this text
#: (`machines/layers.py`'s `_split_gated_grants`, the "not `has ...`, so
#: capitalise and grant verbatim" branch every non-keyword static clause in
#: that module goes through - the same path `ATTACK_WITHOUT_DEFENDER_TEXT`
#: above is a fixed literal for). Checked directly with `has_ability` the
#: same way that constant is, both because "can't be blocked by more than
#: one creature" has no keyword name of its own for `has_keyword` to look
#: up, and because a bare granted fragment with no subject and no trailing
#: full stop is not a `layer_readable_sentences` sentence at all (that
#: reader is built for a printed line's own full sentences, not a layer-6
#: literal): `_evasion_restriction_sentences`'s sentence-search approach
#: would silently never see this text, the same way it would never see
#: `ATTACK_WITHOUT_DEFENDER_TEXT` if that were checked through it instead of
#: directly.
BLOCKED_BY_AT_MOST_ONE_GRANT_TEXT = "Can't be blocked by more than one creature"


def _blocked_by_at_most_one_sentences(attacker: CardState, game: "Game | None" = None) -> list[str]:
    """Self-referential "can't be blocked by more than one creature" sentences
    the attacker has *now* (CR 613.5), read the same layer-aware way
    `_evasion_restriction_sentences` reads "can't be blocked" - Charging
    Rhino's own printed, unconditional "This creature can't be blocked by
    more than one creature." The other shape, Akawalli's conditional grant,
    is not a sentence in this sense at all - see `BLOCKED_BY_AT_MOST_ONE_
    GRANT_TEXT`'s own docstring - so `blocked_by_at_most_one_refusal` checks
    it separately, directly, before ever calling this.
    """
    subjects = _self_reference_alternatives(attacker)
    subject = re.compile(
        rf"^(?:{'|'.join(re.escape(name) for name in subjects)})\b"
        r".*can't be blocked by more than one creature\b",
        re.IGNORECASE,
    )
    sentences = _computed_ability_sentences(attacker, game)
    return [sentence for sentence in sentences if subject.search(sentence)]


def blocked_by_at_most_one_refusal(
    game: "Game", attacker: CardState, blocker_count: int
) -> str | None:
    """Why a block declaration with two or more blockers on `attacker` is
    illegal, or None (CR 509.1b): a restriction "an attacking creature has
    that restricts what can block it" (CR 509.1b), the reverse of menace, so
    it is checked against the whole finished declaration the same way
    `declaration_refusal` already checks menace - "how many creatures are
    blocking this attacker" is a fact about the declaration, not about one
    (blocker, attacker) pair, which is why this lives beside `declaration_
    refusal` rather than `block_refusal`.
    """
    if blocker_count < 2:
        return None
    if game is not None and game.characteristics_of(attacker).has_ability(
        BLOCKED_BY_AT_MOST_ONE_GRANT_TEXT
    ):
        return (
            f"{attacker.name} can't be blocked by more than one creature "
            f"(descend 8 grant, CR 509.1b)"
        )
    for sentence in _blocked_by_at_most_one_sentences(attacker, game):
        return (
            f'{attacker.name} can\'t be blocked by more than one creature: "{sentence}" (CR 509.1b)'
        )
    return None


#: A self-referential "can't be blocked by more than one creature." line (CR
#: 509.1b, the mirror of menace) as printed, with no game or `CardState`
#: needed to ask about it - `_blocked_by_at_most_one_sentences` above answers
#: the same question off a live board, but `scripts/sweep_pool.py`'s static-
#: ability classifier only ever has the bare printed text (the same
#: constraint `is_attack_requirement_line`/`is_group_attack_restriction_line`
#: already work under), so this mirrors those: an optional leading subject,
#: matched the same way, then the restriction's own fixed words.
_BLOCKED_BY_AT_MOST_ONE_LINE_RE = re.compile(
    r"^(?:(?P<subject>.+?) )?can't be blocked by more than one creature\.?$", re.IGNORECASE
)


def is_blocked_by_at_most_one_line(line: str, name: str) -> bool:
    """Whether one computed ability line of a creature named `name` is its own
    "can't be blocked by more than one creature" restriction (CR 509.1b) -
    Charging Rhino's own unconditional printed line - that `blocked_by_at_
    most_one_refusal` enforces from `declaration_refusal`."""
    match = _BLOCKED_BY_AT_MOST_ONE_LINE_RE.fullmatch(line.strip())
    if match is None:
        return False
    subject = (match.group("subject") or "").strip().lower()
    # `name` is the full printed name ("Rocksteady, Crash Courser"), but a
    # legendary's own printed line self-references by its short form
    # ("Rocksteady can't be blocked ..." - CR 201.5c), the same vocabulary
    # every other self-reference in this module reads
    # (`_self_reference_names`) - a bare string-equality check against the
    # full name alone missed every comma-shortened legendary self-reference.
    accepted = {"", "this creature", "this permanent"}
    accepted.update(candidate.lower() for candidate in _self_reference_names(name))
    return subject in accepted


def looks_like_unparsed_evasion_restriction(
    attacker: CardState, game: "Game | None" = None
) -> bool:
    """True if some self-referential sentence of the attacker's abilities reads
    like a "can't be blocked" restriction but is not one of the shapes
    `evasion_restriction_refusal` reads - the fail-closed signal `block_refusal`
    turns into an `EvasionNotice` rather than a block that silently goes through
    unrestricted.

    Reads the same computed sentences the refusal does (CR 613.5), so a
    restriction the layer system has removed does not leave a notice behind
    claiming something was missed.
    """
    for sentence in _evasion_restriction_sentences(attacker, game):
        if is_blocked_by_at_most_one_line(sentence, attacker.name):
            # CR 509.1b's "can't be blocked by more than one creature" -
            # read and enforced by `blocked_by_at_most_one_refusal` instead.
            continue
        compound = _CANT_BLOCK_OR_BE_BLOCKED_BY_RE.search(sentence)
        if compound is not None:
            if _parse_creature_description(compound.group("description")) is None:
                return True
            continue
        exception = _CANT_BE_BLOCKED_EXCEPT_BY_KEYWORD_RE.search(sentence)
        if exception is not None:
            if block_exception_keyword(exception.group("keyword")) is None:
                return True
            continue
        if not _reads_evasion_sentence(sentence):
            return True
    return False


def _condition_tail_is_readable(condition: str) -> bool:
    """Whether `Game.condition_is_readable` claims `condition` - a text-only
    check, no game needed, the same way every other static-line classifier in
    this module answers `scripts/sweep_pool.py`'s question. Imported at call
    time: `models.game` imports this module (for `Attack`, combat refusals),
    so the two cannot import each other at module scope."""
    from ..models.game import condition_is_readable

    return condition_is_readable(condition)


def _reads_evasion_sentence(sentence: str) -> bool:
    """Whether `evasion_restriction_refusal` reads all of one self "can't be
    blocked ..." sentence - the complement of `looks_like_unparsed_evasion_
    restriction`'s per-sentence test."""
    compound = _CANT_BLOCK_OR_BE_BLOCKED_BY_RE.search(sentence)
    if compound is not None:
        return _parse_creature_description(compound.group("description")) is not None
    exception = _CANT_BE_BLOCKED_EXCEPT_BY_KEYWORD_RE.search(sentence)
    if exception is not None:
        return block_exception_keyword(exception.group("keyword")) is not None
    if any(
        shape.search(sentence) is not None
        for shape in (
            _CANT_BE_BLOCKED_RE,
            _CANT_BE_BLOCKED_WHILE_POWER_AT_MOST_RE,
            _CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE,
            _CANT_BE_BLOCKED_BY_POWER_OR_GREATER_RE,
            _CANT_BE_BLOCKED_BY_GREATER_POWER_RE,
            _CANT_BE_BLOCKED_BY_TOKENS_RE,
        )
    ):
        return True
    # Arctic Foxes' quality-plus-condition compound - tried before the
    # general "by `<description>`" shape below, which would otherwise try
    # (and fail) to read the whole "`<description>` while `<condition>`"
    # tail as one plain description.
    while_condition_match = _CANT_BE_BLOCKED_BY_DESCRIPTION_WHILE_CONDITION_RE.search(sentence)
    if while_condition_match is not None:
        return _parse_creature_description(
            while_condition_match.group("description")
        ) is not None and _condition_tail_is_readable(while_condition_match.group("condition"))
    # The general "by `<description>`" shape (Juggernaut's "Walls", Vine
    # Mare's "black creatures", Skyscythe Engulfer's "creatures with
    # flying") - tried after every narrower "by ..." shape in the tuple
    # above (which already claimed "by tokens" and "by creatures with
    # greater power"), so this only ever answers for the quality
    # comparisons those do not cover.
    description_match = _CANT_BE_BLOCKED_BY_DESCRIPTION_RE.search(sentence)
    if description_match is not None:
        return _parse_creature_description(description_match.group("description")) is not None
    # Fugitive Droid's shape is tried last: it is the most general ("if
    # `<anything>`"), so a sentence one of the more specific shapes above
    # already reads (the power-comparison "if"/"as long as" shapes) is never
    # reached here - `any()` above already returned `True` for it.
    condition_match = _CANT_BE_BLOCKED_IF_CONDITION_RE.search(sentence)
    return condition_match is not None and _condition_tail_is_readable(
        condition_match.group("condition")
    )


@functools.lru_cache(maxsize=4096)
def _own_combat_restriction_re(name: str) -> re.Pattern[str]:
    """`name`'s own "<self> can't (be blocked|block)" subject regex, compiled once."""
    subjects = "|".join(re.escape(subject) for subject in _self_reference_names(name))
    return re.compile(rf"^(?:{subjects}) can't (?:be blocked|block)\b", re.IGNORECASE)


def reads_self_combat_restriction_line(line: str, name: str) -> bool:
    """Whether every sentence of one printed static line of a creature named
    `name` is its own "can't be blocked ..." or "can't block ..." (both CR
    509.1b) restriction that `evasion_restriction_refusal` and
    `self_block_restriction_refusal` enforce in full - `support.py`'s credit
    for it.

    Stricter than the enforcers' own sentence pick: the subject must be the
    creature itself and be followed directly by "can't", so a group subject
    ("this creature and other Zombies") or a condition in front of it is left
    to the reader that answers for those.
    """
    if "can't" not in line.lower():
        return False
    own = _own_combat_restriction_re(name)
    sentences = [strip_ability_word(sentence) for sentence in layer_readable_sentences(line)]
    if not sentences:
        return False
    for sentence in sentences:
        if own.search(sentence) is None:
            return False
        evasion = re.search(r"can't be blocked\b|can't block or be blocked by\b", sentence)
        if evasion is not None and not _reads_evasion_sentence(sentence):
            return False
        blocks = re.search(r"can't block\b", sentence, re.IGNORECASE)
        if blocks is not None and _parse_self_block_restriction(sentence) is None:
            return False
    return True


# -- the blocker's own "can't block" restriction (CR 509.1b) ----------------


#: Changeling Outcast: "This creature can't block and can't be blocked." -
#: the "can't block" half is unconditional here; the "can't be blocked" half
#: is independently read by `_CANT_BE_BLOCKED_RE` via
#: `evasion_restriction_refusal` (its tail already matches this compound).
_CANT_BLOCK_AND_CANT_BE_BLOCKED_RE = re.compile(
    r"can't block and can't be blocked\.?$", re.IGNORECASE
)

#: Uneasy Alliance's own grant, once on the enchanted creature's computed
#: abilities: "This creature can't attack or block." - CR 508.1c's and CR
#: 509.1b's restrictions from one sentence (CR 613.6): the attack half is
#: already read by `_self_attack_restriction_sentence`'s own "(?: or
#: block)?" tail; this is the block half, previously unread at all - nothing
#: here matched the literal substring "can't block" that `_self_block_
#: restriction_sentences`'s own subject filter and every `_parse_self_block_
#: restriction` shape were keyed on, so a creature printed with only this
#: combined restriction could still legally block.
_CANT_ATTACK_OR_BLOCK_RE = re.compile(r"can't attack or block\.?$", re.IGNORECASE)

#: Felhide Brawler, Howlpack Wolf, Marauding Boneslasher: "can't block unless
#: you control another <type>[ or <type>]." - a real, repeated template
#: (owner decision, 2026-09-23: every legal printing sharing it is enforced,
#: not left as a notice).
_CANT_BLOCK_UNLESS_CONTROL_ANOTHER_RE = re.compile(
    r"can't block unless you control another (?P<types>[a-z][a-z\s]*?)\.?$", re.IGNORECASE
)

#: Craven Hulk: "can't block alone." - only makes sense against the finished
#: block declaration (CR 509.1b), the same way menace only makes sense there
#: - `declaration_refusal` enforces it (via `self_block_alone_refusal`), not
#: this per-(blocker, attacker) reader.
_CANT_BLOCK_ALONE_RE = re.compile(r"can't block alone\.?$", re.IGNORECASE)

#: Bloodghast, Carrion Feeder: "can't block." - unconditional, nothing after
#: "block" but the period.
_CANT_BLOCK_PLAIN_RE = re.compile(r"can't block\.\s*$", re.IGNORECASE)

#: Zurgo Bellstriker, Hinterland Drake: "can't block <description>." - a
#: qualified restriction, judged against the attacker with
#: `_parse_creature_description`.
_CANT_BLOCK_DESCRIPTION_RE = re.compile(r"can't block (?P<description>.+?)\.?$", re.IGNORECASE)


def _parse_type_list(text: str) -> tuple[str, ...] | None:
    """Read "Minotaur" or "Wolf or Werewolf" into the creature types any one
    of which satisfies "unless you control another <type>" - a disjunction,
    the same "or" reading `TargetRequirement.required_subtypes` already gives
    a bare type list elsewhere. None when a word is not a plain type name -
    the fail-closed signal for the sentence that named it.
    """
    parts = [part.strip() for part in re.split(r"\s+or\s+", text.strip(), flags=re.IGNORECASE)]
    parts = [part for part in parts if part]
    if not parts or any(not re.fullmatch(r"[A-Za-z][A-Za-z'-]*", part) for part in parts):
        return None
    return tuple(parts)


def _controls_another_of(game: "Game", subject: CardState, types: tuple[str, ...]) -> bool:
    """Whether `subject`'s controller controls another creature with any of
    `types` among its computed subtypes (CR 613.5) - Felhide Brawler's own
    "you control another Minotaur"."""
    controller = game.controller_of(subject).username
    wanted = {creature_type.lower() for creature_type in types}
    for other in game.permanents_controlled_by(controller):
        if other.id == subject.id:
            continue
        characteristics = game.characteristics_of(other)
        if characteristics is None or not characteristics.is_creature:
            continue
        if wanted & {subtype.lower() for subtype in characteristics.subtypes}:
            return True
    return False


@dataclass(frozen=True)
class _SelfBlockRestriction:
    """One parsed self "can't block ..." sentence (CR 509.1b), ready to judge
    against one particular attacker (`refusal`)."""

    sentence: str
    kind: str
    """"unconditional", "description", "unless_control_another", or "alone"."""
    description: str | None = None
    description_matcher: "_CreatureDescriptionMatcher | None" = None
    types: tuple[str, ...] | None = None

    def refusal(self, game: "Game", blocker: CardState, attacker: CardState) -> str | None:
        if self.kind == "unconditional":
            return f'{blocker.name} can\'t block: "{self.sentence}" (CR 509.1b)'
        if self.kind == "description":
            assert self.description_matcher is not None
            if self.description_matcher.matches(game, attacker):
                return (
                    f'{blocker.name} can\'t block {self.description}: "{self.sentence}" (CR 509.1b)'
                )
            return None
        if self.kind == "unless_control_another":
            assert self.types is not None
            if not _controls_another_of(game, blocker, self.types):
                return f'{blocker.name} can\'t block: "{self.sentence}" (CR 509.1b)'
            return None
        # "alone": enforced by `declaration_refusal` against the finished
        # declaration, not one (blocker, attacker) pair - the same reason
        # menace is not read here either.
        return None


def _parse_self_block_restriction(sentence: str) -> "_SelfBlockRestriction | None":
    """Read one self "can't block ..." sentence into a `_SelfBlockRestriction`,
    or None when it matches none of the shapes read here - the fail-closed
    signal `block_refusal` turns into an `EvasionNotice`.
    """
    text = sentence.strip()

    if _CANT_BLOCK_AND_CANT_BE_BLOCKED_RE.search(text) or _CANT_ATTACK_OR_BLOCK_RE.search(text):
        return _SelfBlockRestriction(sentence=text, kind="unconditional")

    if match := _CANT_BLOCK_OR_BE_BLOCKED_BY_RE.search(text):
        description = match.group("description")
        matcher = _parse_creature_description(description)
        if matcher is None:
            return None
        return _SelfBlockRestriction(
            sentence=text, kind="description", description=description, description_matcher=matcher
        )

    if match := _CANT_BLOCK_UNLESS_CONTROL_ANOTHER_RE.search(text):
        types = _parse_type_list(match.group("types"))
        if types is None:
            return None
        return _SelfBlockRestriction(sentence=text, kind="unless_control_another", types=types)

    if _CANT_BLOCK_ALONE_RE.search(text):
        return _SelfBlockRestriction(sentence=text, kind="alone")

    if _CANT_BLOCK_PLAIN_RE.search(text):
        return _SelfBlockRestriction(sentence=text, kind="unconditional")

    if match := _CANT_BLOCK_DESCRIPTION_RE.search(text):
        description = match.group("description")
        matcher = _parse_creature_description(description)
        if matcher is None:
            return None
        return _SelfBlockRestriction(
            sentence=text, kind="description", description=description, description_matcher=matcher
        )

    return None


def _self_block_restriction_sentences(state: CardState, game: "Game | None" = None) -> list[str]:
    """Self-referential "can't block ..." sentences `state` has *now*
    (CR 509.1b), read the same layer-aware way `_evasion_restriction_sentences`
    reads the attacker's "can't be blocked" (CR 613.5) - a layer 6 ability
    loss (Dress Down) removes this restriction too, and a layer 6 grant adds
    it even to a printing with no restriction of its own (CR 506.4a: not
    retroactively removing an already-declared block is a property of when
    this is read, at declaration, not of anything special here)."""
    subjects = _self_reference_alternatives(state)
    subject = re.compile(
        rf"^(?:{'|'.join(re.escape(name) for name in subjects)})\b.*"
        r"can't (?:block|attack or block)\b",
        re.IGNORECASE,
    )
    sentences = _computed_ability_sentences(state, game)
    return [sentence for sentence in sentences if subject.search(sentence)]


def self_block_restriction_refusal(
    game: "Game", blocker: CardState, attacker: CardState
) -> str | None:
    """Why the blocker's own "can't block" text refuses this attacker, or
    None (CR 509.1b): "The defending player checks each creature they
    control to see whether it's affected by any restrictions (effects that
    say a creature can't block, or that it can't block unless some condition
    is met)."
    """
    for sentence in _self_block_restriction_sentences(blocker, game):
        parsed = _parse_self_block_restriction(sentence)
        if parsed is None:
            continue
        refusal = parsed.refusal(game, blocker, attacker)
        if refusal is not None:
            return refusal
    return None


def looks_like_unparsed_self_block_restriction(
    blocker: CardState, game: "Game | None" = None
) -> bool:
    """True if some self-referential sentence of the blocker's abilities
    reads like a "can't block" restriction but is not one of the shapes
    `self_block_restriction_refusal` reads - the fail-closed signal
    `block_refusal` turns into an `EvasionNotice` rather than a block that
    silently goes through unrestricted."""
    return any(
        _parse_self_block_restriction(sentence) is None
        for sentence in _self_block_restriction_sentences(blocker, game)
    )


def self_block_alone_refusal(
    game: "Game", blocker: CardState, total_blockers_this_combat: int
) -> str | None:
    """Craven Hulk's "can't block alone.": only makes sense against the
    finished block declaration (CR 509.1b), the same way menace only makes
    sense there, so `declaration_refusal` calls this once per blocker in the
    finished declaration rather than `block_refusal` calling it per pair."""
    if total_blockers_this_combat != 1:
        return None
    for sentence in _self_block_restriction_sentences(blocker, game):
        if _CANT_BLOCK_ALONE_RE.search(sentence):
            return f'{blocker.name} can\'t block alone: "{sentence}" (CR 509.1b)'
    return None


def block_refusal(game: "Game", blocker: CardState, attack: Attack) -> str | None:
    """Why this creature cannot block that attacker, or None (CR 509.1a-b).

    Covers the base requirements, who the attacker is attacking (CR 802.4a),
    and the evasion/restriction abilities that need nothing but the attacker
    and the blocker to decide: flying (CR 702.9b), reach (CR 702.17b), the
    attacker's own "can't be blocked" text (CR 509.1b), and the blocker's own
    "can't block" text (CR 509.1b). "Can't block alone" (Craven Hulk) is the
    one shape that needs the whole finished declaration, so it is read by
    `declaration_refusal`/`self_block_alone_refusal` instead.
    """
    attacker = game.find_by_id(attack.attacker_id)
    if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
        return "that creature is no longer attacking"

    if blocker.zone is not Zone.BATTLEFIELD:
        return f"{blocker.name} is in {blocker.zone.value}, not on the battlefield"
    if blocker.phased_out:
        return f"{blocker.name} is phased out (CR 702.26b)"
    if not game.characteristics_of(blocker).is_creature:
        # Computed, not printed (CR 613.5) - see `attack_refusal`'s identical
        # check for why.
        return f"{blocker.name} is not a creature"
    if blocker.tapped:
        return f"{blocker.name} is tapped"

    defending = defending_player(game, attack.defender)
    if game.controller_of(blocker).username != defending:
        return f"{blocker.name} is not controlled by {defending}"

    if has_keyword(blocker, Keyword.DECAYED, game):
        # CR 702.147a's static half: "'Decayed' means 'This creature can't
        # block'" (CR 509.1b) - read off `has_keyword` rather than a printed
        # "can't block" sentence, so a decayed keyword counter (CR 122.1b) or
        # a grant refuses the block exactly like the printed keyword does.
        return f"{blocker.name} has decayed and can't block (CR 702.147a)"

    if has_keyword(attacker, Keyword.FLYING, game) and not (
        has_keyword(blocker, Keyword.FLYING, game) or has_keyword(blocker, Keyword.REACH, game)
    ):
        return f"{attacker.name} has flying and {blocker.name} has neither flying nor reach"

    attacker_shadow = has_keyword(attacker, Keyword.SHADOW, game)
    if attacker_shadow != has_keyword(blocker, Keyword.SHADOW, game):
        # CR 702.28b cuts both ways: shadow blocks and is blocked only by shadow.
        if attacker_shadow:
            return (
                f"{attacker.name} has shadow, so {blocker.name} - a creature without "
                f"shadow - cannot block it (CR 702.28b)"
            )
        return (
            f"{blocker.name} has shadow, so it cannot block {attacker.name} - a creature "
            f"without shadow (CR 702.28b)"
        )
    if has_keyword(attacker, Keyword.INTIMIDATE, game):
        # CR 702.13b, off the computed board (colors and types are layer-4/5
        # results, CR 613): artifact creatures and creatures sharing a color
        # with the attacker may block it; nothing else may.
        attacker_chars = game.characteristics_of(attacker)
        blocker_chars = game.characteristics_of(blocker)
        if Type.ARTIFACT not in blocker_chars.types and not (
            set(attacker_chars.colors) & set(blocker_chars.colors)
        ):
            return (
                f"{attacker.name} has intimidate, so {blocker.name} - neither an artifact "
                f"creature nor a creature sharing a color with it - cannot block it "
                f"(CR 702.13b)"
            )
    if has_keyword(attacker, "skulk", game):
        # CR 702.118b: "A creature with skulk can't be blocked by creatures
        # with greater power." Both powers off the computed board (CR 613).
        attacker_power = game.characteristics_of(attacker).power
        blocker_power = game.characteristics_of(blocker).power
        if (
            attacker_power is not None
            and blocker_power is not None
            and blocker_power > attacker_power
        ):
            return f"{attacker.name} has skulk and {blocker.name} has greater power (CR 702.118b)"

    if has_keyword(attacker, "fear", game):
        # CR 702.36b: "A creature with fear can't be blocked except by artifact
        # creatures and/or black creatures." Types and colours off the computed
        # board (CR 613).
        blocker_chars = game.characteristics_of(blocker)
        if Type.ARTIFACT not in blocker_chars.types and Color.BLACK not in blocker_chars.colors:
            return (
                f"{attacker.name} has fear and {blocker.name} is neither an artifact "
                f"creature nor a black creature (CR 702.36b)"
            )

    # CR 702.16f: "Attacking creatures with protection can't be blocked by
    # creatures that have the stated quality."
    quality = game.protection_quality_against(attacker, blocker)
    if quality is not None:
        return (
            f"{attacker.name} has protection from {quality}, so {blocker.name} "
            f"cannot block it (CR 702.16f)"
        )

    restriction = evasion_restriction_refusal(game, attacker, blocker)
    if restriction is not None:
        return restriction
    if looks_like_unparsed_evasion_restriction(attacker, game) and not any(
        notice.source_id == attacker.id for notice in game.evasion_notices
    ):
        game.evasion_notices.append(
            EvasionNotice(
                source_id=attacker.id,
                source_name=attacker.name,
                text=attacker.oracle_text,
            )
        )

    group_restriction = group_block_restriction_refusal(game, blocker, attacker)
    if group_restriction is not None:
        return group_restriction

    from .block_statics import block_only_refusal

    only_restriction = block_only_refusal(game, blocker, attacker)
    if only_restriction is not None:
        return only_restriction

    from .combat_statics import power_threshold_restriction_refusal

    self_restriction = self_block_restriction_refusal(
        game, blocker, attacker
    ) or self_card_count_restriction_refusal(game, blocker, "block")
    self_restriction = self_restriction or self_control_count_restriction_refusal(
        game, blocker, "block"
    )
    self_restriction = self_restriction or power_threshold_restriction_refusal(
        game, blocker, "block"
    )
    if self_restriction is not None:
        return self_restriction
    if looks_like_unparsed_self_block_restriction(blocker, game) and not any(
        notice.source_id == blocker.id for notice in game.evasion_notices
    ):
        game.evasion_notices.append(
            EvasionNotice(
                source_id=blocker.id,
                source_name=blocker.name,
                text=blocker.oracle_text,
            )
        )

    from .combat_statics import extra_block_refusal

    return extra_block_refusal(game, blocker, attacker) or landwalk_refusal(
        game, attacker, defending
    )


def landwalk_refusal(game: "Game", attacker: CardState, defending: str | None) -> str | None:
    """Why landwalk stops this attacker being blocked at all, or None (CR 702.14c).

    "A creature with landwalk can't be blocked as long as the defending player
    controls at least one land with the specified land type." It is an evasion
    ability (CR 702.14b) and it does not care what the *blocker* is, which is
    what makes it different from flying: nothing the defending player controls
    can block, so the refusal is about their lands rather than their creature.

    Only the five basic landwalks are read (CR 305.6). CR 702.14a allows other
    shapes - "nonbasic landwalk", "snow forestwalk" - and none are in the pool;
    a shape this does not know is not enforced, and `scripts/sweep_pool.py`
    reports it.
    """
    if defending is None:
        return None
    # One computed board for every keyword and every land, not one per land
    # per keyword (`Game.computed_board` recomputes the whole board each
    # call) - and computed, not `permanent.subtypes`, because a land's
    # subtype is layer 4 (CR 613.1d) like anything else CR 613.5 governs:
    # Urborg, Tomb of Yawgmoth makes every land a Swamp "in addition to its
    # other land types" and Blood Moon replaces a nonbasic land's types with
    # Mountain outright (CR 305.7), and swampwalk/mountainwalk have to see
    # either one.
    board = game.computed_board()
    for keyword, land_type in LANDWALK_TYPES.items():
        if not has_keyword(attacker, keyword, game):
            continue
        lands = [
            permanent
            for permanent in game.permanents_controlled_by(defending)
            if land_type in board.of(permanent).subtypes
        ]
        if lands:
            return (
                f"{attacker.name} has {keyword.value} and {defending} controls "
                f"{with_indefinite_article(land_type)}, so it cannot be blocked (CR 702.14c)"
            )
    return None


def declaration_refusal(game: "Game", declared: dict[UUID, list[CardState]]) -> str | None:
    """Why the whole block declaration is illegal, or None (CR 509.1).

    Some restrictions only make sense against the finished declaration rather
    than one blocker at a time - menace is the plain example, since a single
    blocker on a creature with menace is illegal but two are fine
    (CR 702.111b). "Can't block alone" (Craven Hulk) is the same kind of
    restriction (CR 509.1b): whether one blocker is the *only* one blocking
    this combat is a fact about the whole declaration, not about the
    (blocker, attacker) pair `block_refusal` is asked about. Each creature
    may block only one attacker (CR 509.1a). "Can't be blocked by more than
    one creature" (Charging Rhino; Akawalli, the Seething Tower's descend 8)
    is menace's mirror image, checked the same way (`blocked_by_at_most_one_
    refusal`).
    """
    from .block_statics import multi_block_refusal

    multi_refusal = multi_block_refusal(game, declared)
    if multi_refusal is not None:
        return multi_refusal
    seen: set[UUID] = set()
    all_blockers: list[CardState] = []
    for attacker_id, blockers in declared.items():
        for blocker in blockers:
            if blocker.id not in seen:
                seen.add(blocker.id)
                all_blockers.append(blocker)

        attacker = game.find_by_id(attacker_id)
        if attacker is None:
            continue
        if has_keyword(attacker, Keyword.MENACE, game) and 0 < len(blockers) < 2:
            return f"{attacker.name} has menace and cannot be blocked by fewer than two creatures"
        cap_refusal = blocked_by_at_most_one_refusal(game, attacker, len(blockers))
        if cap_refusal is not None:
            return cap_refusal
        from .combat_statics import group_blocked_by_at_most_one_refusal

        group_cap_refusal = group_blocked_by_at_most_one_refusal(game, attacker, len(blockers))
        if group_cap_refusal is not None:
            return group_cap_refusal

    for blocker in all_blockers:
        refusal = self_block_alone_refusal(game, blocker, len(all_blockers))
        if refusal is not None:
            return refusal
    from .combat_statics import extra_declaration_refusal

    return extra_declaration_refusal(game, declared)


def declare_blockers(game: "Game", blocks: list[tuple[CardState, CardState]]) -> None:
    """Declare the whole block for this combat (CR 509.1).

    `blocks` is `(blocker, attacker)` pairs, in the order the blockers should
    be assigned damage in (CR 510.1c). Nothing is recorded unless the entire
    declaration is legal, so a refused declaration leaves combat untouched.
    """
    combat = game.combat
    declared: dict[UUID, list[CardState]] = {attack.attacker_id: [] for attack in combat.attacks}

    for blocker, attacker in blocks:
        attack = combat.attack_by(attacker.id)
        if attack is None:
            raise ValueError(f"{attacker.name} is not attacking")
        refusal = block_refusal(game, blocker, attack)
        if refusal is not None:
            raise ValueError(refusal)
        declared[attacker.id].append(blocker)

    refusal = declaration_refusal(game, declared)
    if refusal is not None:
        raise ValueError(refusal)
    unobeyed = unobeyed_block_requirement(game, declared)
    if unobeyed is not None:
        raise ValueError(unobeyed)

    from .combat_statics import unobeyed_must_be_blocked_requirement

    unobeyed_must_be_blocked = unobeyed_must_be_blocked_requirement(game, declared)
    if unobeyed_must_be_blocked is not None:
        raise ValueError(unobeyed_must_be_blocked)

    from .block_statics import unobeyed_exact_blockers, unobeyed_lure_requirement

    unobeyed_lure = unobeyed_lure_requirement(game, declared) or unobeyed_exact_blockers(
        game, declared
    )
    if unobeyed_lure is not None:
        raise ValueError(unobeyed_lure)

    # CR 509.1d-f: the cost to block, paid in full before the blocks are made.
    game._pay_block_costs(blocks)

    for attack in combat.attacks:
        chosen = declared[attack.attacker_id]
        attack.blockers = [blocker.id for blocker in chosen]
        attack.blocked_by += [b.id for b in chosen if b.id not in attack.blocked_by]
        # CR 509.1h: once blocked, a creature stays blocked for the rest of combat.
        attack.blocked = attack.blocked or bool(chosen)
    combat.blockers_declared = True


def defending_player(game: "Game", defender: TargetRef) -> str | None:
    """Who is defending against an attack on `defender` (CR 508.5): the player
    themselves, the controller of a planeswalker, or the *protector* of a
    battle (CR 310.9d), which for a Siege is never its controller (CR
    310.12a).

    `CardState.protector` is kept after the battle leaves the battlefield or
    stops being a battle (CR 310.9g), which is CR 508.5's "the protector of
    the battle that creature was attacking before it was removed from
    combat".

    Takes the `TargetRef` directly rather than the whole `Attack`, so a
    triggered ability's own `GameEvent.defender` (CR 508.1a's same field,
    carried onto the event `Game.declare_attacker` emits) can ask this
    question too - Ulamog, the Ceaseless Hunger's "whenever Ulamog attacks,
    defending player ..." reads a defending player off an *event*, not off a
    live `Attack` still in `game.combat`.
    """
    if defender.is_player:
        return defender.username
    permanent = game.resolve_target(defender)
    if isinstance(permanent, CardState):
        if permanent.protector is not None:
            return permanent.protector
        return game.controller_of(permanent).username
    return None


def effect_block_candidates(game: "Game", blocker: CardState) -> list[CardState]:
    """The attacking creatures an effect can make `blocker` block (CR 509.3b):
    each attacking its controller, a planeswalker they control or a battle
    they protect (CR 509.1a's bound on what a blocker can be blocking). The
    declaration's restrictions and requirements (CR 509.1b, 509.1c) do not
    apply - an effect causing a block is not a declaration of blockers."""
    controller = game.controller_of(blocker).username
    found = []
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if attacker is None or attacker.id == blocker.id:
            continue
        if defending_player(game, attack.defender) == controller:
            found.append(attacker)
    return found


def protector_candidates(
    game: "Game", battle: CardState, board: "ComputedBoard | None" = None
) -> list[str]:
    """Who may be `battle`'s protector (CR 310.9a): for a Siege, its
    controller's opponents (CR 310.12a); for a battle with no battle type,
    only its controller. Siege is the only battle type (CR 205.3q). Players
    who have left the game are no candidates."""
    chars = board.of(battle) if board is not None else game.characteristics_of(battle)
    controller = chars.controller or game.controller_of(battle).username
    in_game = [player.username for player in game.players_in_game]
    if "Siege" in chars.subtypes:
        return [username for username in in_game if username != controller]
    return [controller] if controller in in_game else []


def choose_protector(
    game: "Game", battle: CardState, board: "ComputedBoard | None" = None
) -> str | None:
    """`battle`'s controller chooses its protector from
    `protector_candidates` (CR 310.9a, 310.11) - asked only when there is a
    real choice. None when nobody can be chosen."""
    candidates = protector_candidates(game, battle, board)
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    return str(
        game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=game.controller_of(battle).username,
                prompt=f"choose an opponent to protect {battle.name} (CR 310.12a)",
                source=battle.name,
                source_id=source_id_of(battle),
                options=tuple(candidates),
                quality="opponent",
            )
        )
    )


def battle_protector_state_based_actions(game: "Game", board: "ComputedBoard") -> list[CardState]:
    """CR 704.5x and 704.5y (CR 310.11): give each battle that needs one a
    new protector, chosen by its controller, and return the battles for
    which nobody can be chosen - those go to their owners' graveyards.

    704.5x covers a battle with no protector in the game, and only while no
    creature is attacking it; 704.5y a protector who can't be its protector
    (a Siege whose controller became its protector, CR 310.12a). `board` is
    the caller's computed board (CR 613.5), read rather than recomputed."""
    attacked = {
        attack.defender.card_id for attack in game.combat.attacks if not attack.defender.is_player
    }
    leaving: list[CardState] = []
    for battle in list(game.battlefield):
        if Type.BATTLE not in board.of(battle).types:
            continue
        protector = battle.protector
        if protector is None or not game.is_in_game(protector):
            if battle.id in attacked:
                continue  # CR 704.5x: not while it is being attacked
        elif protector in protector_candidates(game, battle, board):
            continue
        chosen = choose_protector(game, battle, board)
        if chosen is None:
            leaving.append(battle)
        else:
            battle.protector = chosen
    return leaving


# -- combat damage ---------------------------------------------------------


def combatants(game: "Game") -> list[CardState]:
    """Every attacking and blocking creature still on the battlefield."""
    ids = game.combat.attacker_ids + game.combat.blocker_ids
    found = (game.find_by_id(card_id) for card_id in ids)
    return [state for state in found if state is not None and state.zone is Zone.BATTLEFIELD]


def needs_first_strike_step(game: "Game") -> bool:
    """True if an extra combat damage step is needed (CR 510.4).

    Checked as the first combat damage step begins: if anything in combat has
    first strike or double strike, there are two damage steps rather than one.
    """
    return any(
        has_keyword(state, Keyword.FIRST_STRIKE, game)
        or has_keyword(state, Keyword.DOUBLE_STRIKE, game)
        for state in combatants(game)
    )


def deals_damage_this_step(
    state: CardState, *, first_strike_step: bool, game: "Game | None" = None
) -> bool:
    """Whether this creature assigns damage in the step about to happen (CR 510.4).

    CR 702.7a and CR 702.4a are static abilities like any other, so the answer
    comes off the computed board when there is one: a first strike granted in
    layer 6 makes the extra step happen (CR 510.4) and one removed by Humility
    stops it.

    In a first-strike step, only first strikers and double strikers assign -
    read live, since the step has not happened yet and nothing has snapshotted
    who qualifies.

    In the step after a first-strike step, CR 702.7c and CR 702.4c-d turn on
    what a creature *had as the first step began*, not on what it has now:
    `combat.first_strike_step_ids` is that snapshot, taken once by
    `combat_damage_step` below. A creature outside it never struck in the
    first step and strikes now regardless of its current keywords (CR 702.7c's
    permissive half - granting first strike in the window doesn't move it out
    of "never struck"); one inside it struck already and only strikes again if
    it currently has double strike (CR 702.7c's restrictive half, CR 702.4c-d).
    Reading `has_keyword` live for this question instead - `double or not
    first` alone - is exactly the bug this snapshot exists to avoid: a first
    striker that already struck and then loses first strike with no double
    strike would read `not first` as true and strike again.

    With no first-strike step this combat, there is only ever one step and
    this branch's own live reading is the whole answer: a creature with
    neither ability assigns (`not first` alone would already say so), and one
    granted first or double strike after the *only* step already ran gets no
    second step to matter in.
    """
    first = has_keyword(state, Keyword.FIRST_STRIKE, game)
    double = has_keyword(state, Keyword.DOUBLE_STRIKE, game)
    if first_strike_step:
        return first or double
    if game is not None and game.combat.first_strike_step_happened:
        return state.id not in game.combat.first_strike_step_ids or double
    return double or not first


def combat_damage_step(game: "Game") -> list[tuple["Targetable", int]]:
    """One combat damage step: assign, then deal it all at once (CR 510.1-510.2).

    Returns what was assigned, in assignment order, so a scenario can assert on
    the split rather than only on the wreckage. State-based actions run
    afterwards, as they do before any player would next get priority.
    """
    combat = game.combat
    first_strike_step = combat.damage_steps_done == 0 and needs_first_strike_step(game)
    if first_strike_step:
        combat.first_strike_step_happened = True
        combat.first_strike_damage_step = True
        combat.first_strike_step_ids = [
            state.id
            for state in combatants(game)
            if has_keyword(state, Keyword.FIRST_STRIKE, game)
            or has_keyword(state, Keyword.DOUBLE_STRIKE, game)
        ]
    else:
        combat.first_strike_damage_step = False

    assignments: list[tuple[CardState, Targetable, int]] = []
    # CR 702.19b: lethal damage takes into account "damage from other creatures
    # that's being assigned during the same combat damage step".
    assigned_this_step: dict[UUID, int] = {}

    # CR 510.1: attackers are announced first, then blockers - but nothing is
    # dealt until both are known, because combat damage is simultaneous.
    for attack in combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
            continue
        if not deals_damage_this_step(attacker, first_strike_step=first_strike_step, game=game):
            continue
        for target, amount in _attacker_assignment(game, attack, attacker, assigned_this_step):
            assignments.append((attacker, target, amount))
            if isinstance(target, CardState):
                assigned_this_step[target.id] = assigned_this_step.get(target.id, 0) + amount

    # CR 510.1d: a blocker assigns its combat damage to the creatures it is
    # blocking - all of it to one, divided as its controller chooses among two
    # or more ("can block an additional creature"). A blocker whose attacker
    # has gone assigns nothing to it.
    blocked_by_blocker: dict[UUID, list[CardState]] = {}
    for attack in combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
            continue
        for blocker_id in attack.blockers:
            blocked_by_blocker.setdefault(blocker_id, []).append(attacker)
    for blocker_id, blocked in blocked_by_blocker.items():
        blocker = game.find_by_id(blocker_id)
        if blocker is None or blocker.zone is not Zone.BATTLEFIELD:
            continue
        if not deals_damage_this_step(blocker, first_strike_step=first_strike_step, game=game):
            continue
        power = _assignment_power_of(game, blocker)
        if power is None:
            _record_undefined_power(game, blocker)
        elif power > 0:
            for target, amount in _blocker_assignment(game, blocker, blocked, power):
                assignments.append((blocker, target, amount))

    recorded = len(game.combat_damage_to_players_this_turn)
    for source, target, amount in assignments:
        _deal_combat_damage(game, source, target, amount)
    _emit_combat_damage_to_players(game, recorded)

    combat.damage_steps_done += 1
    game.check_state_based_actions()
    # CR 510.3a: "Any abilities that triggered on damage being dealt or while
    # state-based actions are performed afterward are put onto the stack before
    # the active player gets priority". Without this, `Game.emit` leaves them
    # in `pending_triggers` (CR 603.3) with nothing in the step that would move
    # them, and a "whenever this deals combat damage" ability - Ragavan - would
    # only reach the stack the next time some *other* part of the engine
    # happened to flush the queue. Ordering is CR 603.3b's, which
    # `put_triggers_on_stack` owns; the state-based actions run first because
    # CR 117.5 puts them first and the rule above has the deaths they cause
    # trigger into this same batch.
    #
    # `Game.declare_attackers` and `Game.declare_blockers` already do exactly
    # this for CR 508.2b and CR 509.2a - the combat damage step was the one
    # place in combat that emitted events and never let them onto the stack.
    game.put_triggers_on_stack()
    return [(target, amount) for _, target, amount in assignments]


def _emit_combat_damage_to_players(game: "Game", recorded: int) -> None:
    """CR 510.2's simultaneous damage as one `ExtraTriggerEvent.
    COMBAT_DAMAGE_TO_PLAYERS` event per player dealt combat damage this step
    - what a batched "one or more `<description>` deal combat damage to a
    player" trigger watches (CR 603.2c). `recorded` is how many records the
    turn's ledger held before this step, so the step's own are the tail the
    event's `amount` points at. No damage dealt to a player, no event
    (CR 603.2g)."""
    step_records = game.combat_damage_to_players_this_turn[recorded:]
    for player in dict.fromkeys(record.player for record in step_records):
        game.emit(
            GameEvent(
                event=ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS,
                player=player,
                combat=True,
                amount=len(step_records),
            )
        )


def _deal_combat_damage(game: "Game", source: CardState, target: "Targetable", amount: int) -> int:
    """Deal one creature's combat damage, then apply deathtouch and lifelink.

    Both keywords key off *damage that was actually dealt*, and `Game.deal_damage`
    returns it: a prevention effect (CR 615.1a) means the event dealt zero
    damage, and zero damage is not "dealt damage" for either CR 702.2b or
    CR 702.15b. Fog Bank is the card in the pool that makes the difference
    visible.

    The creature is named as the source, which is CR 120.1 - "An object that
    deals damage is the source of that damage" - and is what lets the prevention
    machinery answer the rules that ask about the source rather than the target:
    CR 609.7b's recheck, CR 615.8's "the next time a specific source would deal
    damage", and CR 702.16e's protection.
    """
    dealt = game.deal_damage(target, amount, source=source)
    if dealt <= 0:
        return 0

    # This function only ever deals combat damage (CR 510.2), so recording
    # the source here is Ruric Thar's "hexproof as long as they haven't dealt
    # combat damage yet" ledger - off *dealt* damage, the same way deathtouch
    # and lifelink below key off it: zero dealt is not "dealt" for any of the
    # three.
    game.combat_damage_dealt_this_turn_by.add(source.id)

    if isinstance(target, CardState) and has_keyword(source, Keyword.DEATHTOUCH, game):
        # CR 702.2b: destroyed as a state-based action, whatever its toughness.
        target.dealt_deathtouch_damage = True
    if has_keyword(source, Keyword.LIFELINK, game):
        # CR 702.15b / CR 120.3f, and CR 702.15e keeps each source's life gain
        # a separate event, which is why this is inside the per-source loop.
        game.gain_life(game.controller_of(source), dealt)
    # Imported here: `models.player` imports `machines.layers`, which imports
    # this module.
    from ..models.player import Player

    if isinstance(target, Player):
        # CR 702.76a's prowl asks what the source was "at the time it dealt
        # that damage" - its controller and creature types - so that is
        # captured here, off damage actually dealt, not looked up later.
        game.record_combat_damage_to_player(source, target.username)
        # CR 702.164c / CR 120.3g: combat damage dealt to a player by a
        # creature with toxic gives that player poison counters equal to its
        # total toxic value, "in addition to the damage's other results" -
        # so after infect's own poison, and only for damage actually dealt.
        toxic = total_toxic_value(source, game)
        if toxic > 0:
            game.add_player_counters(target, Counter.POISON, toxic)
    return dealt


class UndefinedPowerNotice(EngineModel):
    """One creature whose power could not be computed when combat needed it.

    A printed `*` with no characteristic-defining ability the engine can read
    leaves `Characteristics.power` (and `CardState.power`) `None` rather than a
    number - see `machines/layers.py`'s `_as_number`. CR 208.5 would treat that
    `*` as 0, and `power or 0` used to do exactly that: an unreadable power
    silently became a real, comparable number, which is indistinguishable from
    a creature that genuinely deals no damage. That is the same "unreadable is
    not the same as no effect" gap `LayerNotice`, `EvasionNotice` and the other
    notices already record, so a creature combat cannot compute a power for
    gets one of these instead of a fabricated 0, and assigns no combat damage
    for the step rather than a wrong amount.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str


def _power_of(game: "Game | None", creature: CardState) -> int | None:
    """CR 510.1a: a creature assigns combat damage equal to its power.

    "Each attacking creature and each blocking creature assigns combat damage
    equal to its power. Creatures that would assign 0 or less damage this way
    don't assign combat damage at all." Which power that is, is CR 613.5's
    question: the one the layer system leaves it with, not the printed value.
    `Game.power_of` computes the board; without a game the printed value plus
    counters (CR 122.1a) is all there is.

    None when that power is genuinely unknown - see `UndefinedPowerNotice`.
    Callers must not fold that into 0 themselves; they record the notice and
    skip the assignment instead.
    """
    return game.power_of(creature) if game is not None else creature.power


def _record_undefined_power(game: "Game | None", creature: CardState) -> None:
    """Record `creature`'s power as unreadable, once per creature (CR 510.1a).

    Mirrors `attack_refusal`'s dedup of `EvasionNotice` by `source_id`, so a
    creature whose power stays unreadable for the rest of combat is not
    reported once per damage step.
    """
    if game is None:
        return
    if any(notice.source_id == creature.id for notice in game.undefined_power_notices):
        return
    game.undefined_power_notices.append(
        UndefinedPowerNotice(source_id=creature.id, source_name=creature.name)
    )


def _toughness_of(game: "Game | None", creature: CardState) -> int | None:
    """This creature's toughness right now, layers included (CR 613.5)."""
    return game.toughness_of(creature) if game is not None else creature.toughness


def lethal_for(
    attacker: CardState,
    blocker: CardState,
    game: "Game | None" = None,
    already_assigned: int = 0,
) -> int | None:
    """How much damage counts as lethal when `attacker` assigns to `blocker`.

    CR 510.1c divides a blocked creature's damage among its blockers, each
    assigned lethal damage before the next gets any, and CR 702.19b says the
    same for what trample may send past them. Ordinarily that is toughness less
    damage already marked, which is `lethal_damage_remaining`.

    CR 702.2c is deathtouch's whole contribution to the arithmetic: "Any nonzero
    amount of combat damage assigned to a creature by a source with deathtouch is
    considered to be lethal damage for the purposes of determining if excess
    damage is being dealt." One is a nonzero amount, so one is lethal - which is
    what lets a 5/5 with deathtouch and trample put four through a 4/4 blocker.

    `already_assigned` is CR 702.19b's "damage from other creatures that's being
    assigned during the same combat damage step": a blocker that already has
    lethal damage coming needs nothing more.

    None when the blocker's toughness is not a number.
    """
    toughness = _toughness_of(game, blocker)
    if toughness is not None and game is not None:
        toughness = blocker.lethal_threshold  # power under Zilortha (CR 120.6)
    remaining = None if toughness is None else toughness - blocker.damage - already_assigned
    if has_keyword(attacker, Keyword.DEATHTOUCH, game):
        return 0 if remaining is not None and remaining <= 0 else 1
    return remaining


#: "You may have this creature assign its combat damage as though it
#: weren't blocked." (Rhox, Lone Wolf, Thorn Elemental, Spinebiter, Pride of
#: Lions, Wolf Pack, Deathcoil Wurm - and the same line granted rather than
#: printed: Zilortha, Apex of Ikoria's "For each non-Human creature you
#: control, you may have that creature assign its combat damage as though it
#: weren't blocked.", Siege Behemoth's "for each creature you control, ...",
#: Proud Wildbonder's "Creatures you control with trample have '...'",
#: Indomitable Might's "Enchanted creature's controller may have it assign
#: ..."). Not a CR-named keyword: the base rules the permission overrides are
#: CR 510.1c ("A blocked creature assigns its combat damage to the creatures
#: blocking it ...") and CR 510.1b ("An unblocked creature assigns its combat
#: damage to the player, planeswalker, or battle it's attacking ..."); this
#: permission lets its controller choose 510.1b's rule for a creature that is
#: in fact blocked, all-or-nothing (Rhox's own ruling: "You can't split the
#: damage assignment between them").
#:
#: `subject` accepts the same self-reference vocabulary a printed restriction
#: already does (`_self_reference_names`) - the granted line always reads
#: "this creature", but a printed line may equally name the card itself.
_ASSIGN_AS_THOUGH_UNBLOCKED_RE = re.compile(
    r"^you may have (?P<subject>.+?) assign its combat damage as though it "
    r"weren'?t blocked\.?$",
    re.IGNORECASE,
)

#: The fixed ability line `_ASSIGN_AS_THOUGH_UNBLOCKED_RE` reads, self-
#: referenced the way a granted ability ordinarily is (CR 700.7) - the text a
#: static grant (Zilortha's, Siege Behemoth's) attaches to each qualifying
#: creature, so the same detector below reads a granted line exactly as it
#: reads Rhox's own printed one.
ASSIGN_AS_THOUGH_UNBLOCKED_TEXT = (
    "You may have this creature assign its combat damage as though it weren't blocked."
)


def _grants_assign_as_though_unblocked(line: str, name: str) -> bool:
    match = _ASSIGN_AS_THOUGH_UNBLOCKED_RE.fullmatch(line.strip())
    if match is None:
        return False
    subject = match.group("subject").strip().lower()
    return subject in {candidate.lower() for candidate in _self_reference_names(name)}


def may_assign_as_though_unblocked(game: "Game", creature: CardState) -> bool:
    """Whether `creature` carries `_ASSIGN_AS_THOUGH_UNBLOCKED_RE`'s
    permission right now, printed or granted (CR 613.5's computed board)."""
    characteristics = game.characteristics_of(creature)
    return any(
        _grants_assign_as_though_unblocked(line, creature.name)
        for line in characteristics.abilities
    )


def _blocker_assignment(
    game: "Game", blocker: CardState, blocked: list[CardState], power: int
) -> list[tuple[CardState, int]]:
    """How one blocking creature divides its combat damage among the
    attackers it blocks (CR 510.1d): all of it to a single one; divided as
    its controller chooses among two or more. Unscripted and unpaused, the
    default is lethal damage to each in declaration order, the rest on the
    last."""
    if len(blocked) == 1:
        return [(blocked[0], power)]
    lethal = [
        power if needed is None else max(needed, 0)
        for needed in (lethal_for(blocker, attacker, game) for attacker in blocked)
    ]
    default: list[tuple[CardState, int]] = []
    remaining = power
    for attacker, needed in zip(blocked, lethal, strict=True):
        share = min(remaining, needed)
        if share > 0:
            default.append((attacker, share))
            remaining -= share
    if remaining > 0:
        if default:
            default[-1] = (default[-1][0], default[-1][1] + remaining)
        else:
            default.append((blocked[-1], remaining))
    targets = [TargetRef.to_card(attacker) for attacker in blocked]
    ref_of = {attacker.id: ref for attacker, ref in zip(blocked, targets, strict=True)}
    decision = Decision(
        kind=DecisionKind.ASSIGN_COMBAT_DAMAGE,
        player=game.controller_of(blocker).username,
        prompt=f"assign {power} combat damage from {blocker.name}",
        source=blocker.name,
        source_id=None,  # CR 703.4k: a turn-based action, not an object's.
        amount=power,
        cards=(blocker.id, *(attacker.id for attacker in blocked)),
        targets=tuple(targets),
        lethal_damage=tuple(lethal),
        default_damage=tuple((ref_of[attacker.id], amount) for attacker, amount in default),
        trample=False,
    )
    answer = game.ask(decision)
    assert isinstance(answer, tuple)
    by_id = {attacker.id: attacker for attacker in blocked}
    return [
        (by_id[ref.card_id], amount)
        for ref, amount in answer
        if ref.card_id in by_id and amount > 0
    ]


def _attacker_assignment(
    game: "Game",
    attack: Attack,
    attacker: CardState,
    assigned_this_step: dict[UUID, int] | None = None,
) -> list[tuple["Targetable", int]]:
    """How one attacking creature divides its damage (CR 510.1a-c, 702.19b).

    Unblocked, it all goes to whatever it is attacking. Blocked by exactly one
    creature without trample, it all goes to that creature (CR 510.1c). Every
    other blocked case is its controller's choice (CR 703.4k): two or more
    blockers are "divided as its controller chooses among them" (CR 510.1c),
    and with trample the excess past lethal damage may go to the attacked
    player or planeswalker (CR 702.19b). That choice is an
    `ASSIGN_COMBAT_DAMAGE` question; unscripted and unpaused, its default is
    lethal damage to each blocker in declaration order, then the rest through
    with trample or onto the last blocker without it.

    A blocked attacker carrying `may_assign_as_though_unblocked`'s permission
    gets one more choice ahead of all of that (CR 608.2d, "you may"): assign
    all its damage as though it were unblocked instead (CR 510.1b), skipping
    every blocker entirely. All-or-nothing, never split with the ordinary
    blocked division below (Rhox's own ruling).
    """
    power = _assignment_power_of(game, attacker)
    if power is None:
        _record_undefined_power(game, attacker)
        return []
    if power <= 0:  # CR 510.1a
        return []

    if attack.blocked and may_assign_as_though_unblocked(game, attacker):
        as_though_unblocked_defender = game.resolve_target(attack.defender)
        if as_though_unblocked_defender is not None and game.may(
            game.controller_of(attacker).username,
            f"have {attacker.name} assign its combat damage as though it weren't blocked",
            source=attacker.name,
            source_id=str(attacker.id),
        ):
            return [(as_though_unblocked_defender, power)]

    blockers = [
        blocker
        for blocker in (game.find_by_id(card_id) for card_id in attack.blockers)
        if blocker is not None and blocker.zone is Zone.BATTLEFIELD
    ]
    trample = has_keyword(attacker, Keyword.TRAMPLE, game)

    if not blockers:
        # CR 510.1c: blocked with every blocker gone means no damage at all,
        # unless trample sends it through anyway (CR 702.19d).
        if attack.blocked and not trample:
            return []
        defender = game.resolve_target(attack.defender)
        return [(defender, power)] if defender is not None else []

    already = assigned_this_step or {}
    # An unknowable toughness makes lethal damage unknowable too; it is held at
    # the whole power, so trample cannot be assigned past that blocker.
    lethal = [
        power if needed is None else max(needed, 0)
        for needed in (
            lethal_for(attacker, blocker, game, already.get(blocker.id, 0)) for blocker in blockers
        )
    ]
    defender = game.resolve_target(attack.defender) if trample else None

    default: list[tuple[Targetable, int]] = []
    remaining = power
    for blocker, needed in zip(blockers, lethal, strict=True):
        share = min(remaining, needed)
        if share > 0:
            default.append((blocker, share))
            remaining -= share
    if remaining > 0:
        if defender is not None:
            default.append((defender, remaining))
        elif default:
            default[-1] = (default[-1][0], default[-1][1] + remaining)
        else:
            default.append((blockers[-1], remaining))

    if len(blockers) == 1 and (defender is None or power <= lethal[0]):
        return default  # CR 510.1c: exactly one blocker, nothing to divide

    targets = [TargetRef.to_card(blocker) for blocker in blockers]
    if defender is not None:
        targets.append(attack.defender)
    ref_of = {blocker.id: ref for blocker, ref in zip(blockers, targets, strict=False)}
    decision = Decision(
        kind=DecisionKind.ASSIGN_COMBAT_DAMAGE,
        player=game.controller_of(attacker).username,
        prompt=f"assign {power} combat damage from {attacker.name}",
        source=attacker.name,
        source_id=None,  # CR 703.4k: a turn-based action, not an object's.
        amount=power,
        cards=(attacker.id, *(blocker.id for blocker in blockers)),
        targets=tuple(targets),
        lethal_damage=(*lethal, *([0] if defender is not None else [])),
        default_damage=tuple(
            (
                ref_of.get(target.id, attack.defender)
                if isinstance(target, CardState)
                else attack.defender,
                amount,
            )
            for target, amount in default
        ),
        trample=trample,
    )
    answer = game.ask(decision)
    assert isinstance(answer, tuple)
    by_id: dict[UUID, Targetable] = {blocker.id: blocker for blocker in blockers}
    chosen: list[tuple[Targetable, int]] = []
    for ref, amount in answer:
        recipient = by_id.get(ref.card_id, defender) if ref.card_id is not None else defender
        if recipient is not None and amount > 0:
            chosen.append((recipient, amount))
    return chosen


# -- attack requirements (CR 508.1d) -----------------------------------------

#: CR 508.1d's requirement as a creature's own ability line: "This creature
#: attacks each combat if able." (Juggernaut) and the same words granted with
#: no subject (Dragon's Rage Channeler's delirium grants "Attacks each combat if
#: able"). The whole line has to be the requirement, so the delirium static
#: that merely mentions the words is not one while its condition is false.
#: "attacks a player each combat if able" (Nahiri, the Unforgiving's +1,
#: granted as this same kind of line) is the narrower requirement: only an
#: attack on a player obeys it, never one on a planeswalker or battle.
_ATTACKS_EACH_COMBAT_RE = re.compile(
    r"^(?:(?P<subject>.+?) )?attacks (?P<player>a player )?each (?:combat|turn) if able\.?$",
    re.IGNORECASE,
)


def _attack_requirement_match(line: str, name: str) -> "re.Match[str] | None":
    match = _ATTACKS_EACH_COMBAT_RE.fullmatch(line.strip())
    if match is None:
        return None
    subject = (match.group("subject") or "").strip().lower()
    # CR 201.5c: a legendary permanent may refer to itself by a shortened
    # version of its name - Ares, God of War's own printed line reads "Ares
    # attacks each combat if able.", never the comma-suffixed full name.
    # `_self_reference_names` is the same short-name vocabulary every other
    # self-reference in this module already reads (`_self_reference_
    # alternatives`), so this accepts exactly what those do rather than
    # growing a second one.
    # "This token attacks each combat if able." - the quoted ability Alien
    # Invasion's Alien tokens are created with, a token's own text naming
    # itself "this token".
    accepted = {"", "this creature", "this permanent", "this token"}
    accepted.update(candidate.lower() for candidate in _self_reference_names(name))
    if subject not in accepted:
        return None
    return match


def is_attack_requirement_line(line: str, name: str) -> bool:
    """Whether one computed ability line of a creature named `name` is its own
    "attacks [a player] each combat if able" requirement (CR 508.1d)."""
    return _attack_requirement_match(line, name) is not None


def _own_attack_requirements(game: "Game", creature: CardState) -> list[bool]:
    """One entry per "attacks each combat if able" line the creature carries
    on the computed board (CR 613.5) - each one a requirement (CR 508.1d) -
    `True` for one that only an attack on a player obeys."""
    characteristics = game.characteristics_of(creature)
    requirements: list[bool] = []
    for line in characteristics.abilities:
        match = _attack_requirement_match(line, creature.name)
        if match is not None:
            requirements.append(match.group("player") is not None)
    from .combat_statics import extra_attack_requirements

    requirements.extend(extra_attack_requirements(game, creature))
    return requirements


def _own_attack_requirement_count(game: "Game", creature: CardState) -> int:
    """How many "attacks each combat if able" lines the creature carries."""
    return len(_own_attack_requirements(game, creature))


def attack_requirement_holders(game: "Game", player: str) -> list[CardState]:
    """The creatures `player` controls that some requirement says attack
    (CR 508.1d): an "attacks each combat if able" line on the computed board
    (CR 613.5), or the goaded designation (CR 701.15b)."""
    board = game.computed_board()
    holders: list[CardState] = []
    for creature in game.permanents_controlled_by(player):
        if not board.of(creature).is_creature:
            continue
        if creature.goaded_by or _own_attack_requirement_count(game, creature):
            holders.append(creature)
    return holders


def attack_requirements_obeyed(
    game: "Game", creature: CardState, defender: TargetRef | None
) -> int:
    """How many of `creature`'s attack requirements it obeys attacking
    `defender` (`None`: not attacking at all) - CR 508.1d's count, per creature.

    Each "attacks each combat if able" line is one requirement. Each goader
    adds two (CR 701.15b, 701.15c): "attacks each combat if able", obeyed by
    any attack, and "attacks a player other than [the goader] if able",
    obeyed only by attacking a player who is not that goader - never by
    attacking a planeswalker or battle, and never by attacking the goader.
    `goaded_by` holds each goader once (CR 701.15d), so a repeat goad adds
    nothing here.
    """
    if defender is None:
        return 0
    goaders = creature.goaded_by
    obeyed = len(goaders) + sum(
        1
        for player_only in _own_attack_requirements(game, creature)
        if defender.is_player or not player_only
    )
    if defender.is_player:
        obeyed += sum(1 for goader in goaders if goader != defender.username)
    return obeyed


def most_obedient_attack(game: "Game", creature: CardState) -> tuple[TargetRef | None, int]:
    """The defender `creature` could legally attack that obeys the most of its
    requirements, and that count - `(None, 0)` when it cannot attack at all
    (tapped, summoning sick, under a restriction: CR 508.1d counts only what
    can be obeyed "without disobeying any restrictions"). Ties go to the first
    defender in `attackable_defenders`' own order, an opponent in turn order
    first. Every defender is tried, planeswalkers and battles included: a
    restriction that only protects a player ("can't attack you") leaves the
    "attacks each combat" requirement obeyable against that player's
    planeswalker."""
    assert game.turn is not None
    best: TargetRef | None = None
    best_count = 0
    for defender in attackable_defenders(game, game.turn.active_player):
        if attack_refusal(game, creature, defender) is not None:
            continue
        if attack_costs_against(game, defender):
            # CR 508.1d: "If a creature can't attack unless a player pays a
            # cost, that player is not required to pay that cost" - an
            # attack that would cost something obeys nothing it must.
            continue
        count = attack_requirements_obeyed(game, creature, defender)
        if best is None or count > best_count:
            best, best_count = defender, count
    return best, best_count


@dataclass(frozen=True)
class UnobeyedAttackRequirement:
    """A creature whose requirements a declaration obeys fewer of than it
    could, and the reason, naming each requirement (CR 508.1d)."""

    creature: CardState
    reason: str


def _requirement_wording(game: "Game", creature: CardState) -> str:
    parts: list[str] = []
    requirements = _own_attack_requirements(game, creature)
    if any(not player_only for player_only in requirements):
        parts.append("attacks each combat if able")
    if any(requirements):
        parts.append("attacks a player each combat if able")
    for goader in creature.goaded_by:
        parts.append(
            f"is goaded by {goader} (CR 701.15b: it attacks each combat if able and "
            f"attacks a player other than {goader} if able)"
        )
    return " and ".join(parts)


def _defender_wording(game: "Game", defender: TargetRef) -> str:
    if defender.is_player:
        return str(defender.username)
    found = game.find_by_id(defender.card_id) if defender.card_id is not None else None
    return found.name if isinstance(found, CardState) else "that defender"


def unobeyed_attack_requirement(
    game: "Game", declared: Mapping[UUID, TargetRef]
) -> UnobeyedAttackRequirement | None:
    """A creature whose requirements the declaration `declared` (each
    attacker's id mapped to what it attacks) obeys fewer of than it could, or
    `None` (CR 508.1d).

    CR 508.1d compares the declaration's total obeyed requirements to the
    maximum obeyable. Every requirement read here binds only its own creature,
    and CR 508.1a/c's checks are per creature, so the maximum is each
    holder's own best attack (`most_obedient_attack`) summed: a declaration
    is short of it exactly when some holder obeys fewer than its own best -
    left home, or sent at a defender that obeys less (a goaded creature
    attacking its goader while another player could be attacked). In a
    two-player game the goader is the only player, so "a player other than"
    the goader cannot be obeyed and attacking the goader is the maximum.
    CR 508.1d's unpaid-cost clause is `most_obedient_attack`'s: a defender
    whose attack costs something (`attack_costs_against`) is never the best
    attack a holder is held to.
    """
    if game.turn is None:
        return None
    for creature in attack_requirement_holders(game, game.turn.active_player):
        chosen = declared.get(creature.id)
        best_defender, best = most_obedient_attack(game, creature)
        obeyed = attack_requirements_obeyed(game, creature, chosen)
        if best_defender is None or obeyed >= best:
            continue
        wording = _requirement_wording(game, creature)
        if chosen is None:
            reason = (
                f"{creature.name} {wording} and can attack, so a declaration without it "
                "obeys fewer requirements than it could"
            )
        else:
            reason = (
                f"{creature.name} {wording}; attacking {_defender_wording(game, chosen)} "
                f"obeys {obeyed} of its requirements, attacking "
                f"{_defender_wording(game, best_defender)} would obey {best}"
            )
        return UnobeyedAttackRequirement(creature, reason)
    return None


# -- block requirements (CR 509.1c) ------------------------------------------

#: CR 509.1c's requirement to block one named attacker, as the ability line
#: `effects._parse_target_blocks_self_if_able_clause` grants until end of turn
#: ("Target creature blocks this creature this turn if able." - Sisters of
#: Stone Death, Tangle Angler): "This creature blocks <attacker> each combat
#: if able." Only a block on an attacker with that name obeys it.
#:
#: The attacker name is optional (R0a-T7): Academic Dispute's own "Target
#: creature blocks this turn if able." names no attacker at all, granted as
#: "This creature blocks each combat if able." by `effects._parse_target_
#: blocks_if_able_then_may_gain_keyword_clause` - CR 509.1c's general
#: requirement, obeyed by blocking *any* legal attacker, not one named
#: object. `attacker` is `None` for that unnamed shape.
_BLOCKS_NAMED_EACH_COMBAT_RE = re.compile(
    r"^(?:this creature|this permanent) blocks(?: (?P<attacker>.+?))? each combat if able\.?$",
    re.IGNORECASE,
)


def _own_block_requirements(game: "Game", creature: CardState) -> list[str | None]:
    """The attacker name each block requirement line on `creature`'s computed
    board (CR 613.5) names - one entry per requirement (CR 509.1c). `None`
    for an unnamed requirement, obeyed by blocking any legal attacker."""
    names: list[str | None] = []
    for line in game.characteristics_of(creature).abilities:
        match = _BLOCKS_NAMED_EACH_COMBAT_RE.fullmatch(line.strip())
        if match is not None:
            attacker = match.group("attacker")
            names.append(attacker.lower() if attacker is not None else None)
    return names


def _block_requirements_obeyed(
    game: "Game", creature: CardState, attacker: CardState | None
) -> int:
    """How many of `creature`'s block requirements blocking `attacker`
    (`None`: not blocking) obeys. An unnamed requirement (`None`) is obeyed
    by blocking any legal attacker at all."""
    if attacker is None:
        return 0
    return sum(
        1
        for name in _own_block_requirements(game, creature)
        if name is None or name == attacker.name.lower()
    )


def _block_requirement_holders(game: "Game") -> list[CardState]:
    """Every creature a defending player controls that carries a block
    requirement this combat (CR 509.1c)."""
    defenders = {defending_player(game, attack.defender) for attack in game.combat.attacks}
    board = game.computed_board()
    holders: list[CardState] = []
    for username in defenders:
        if username is None:
            continue
        for creature in game.permanents_controlled_by(username):
            if board.of(creature).is_creature and _own_block_requirements(game, creature):
                holders.append(creature)
    return holders


def _most_obedient_block(game: "Game", creature: CardState) -> tuple[CardState | None, int]:
    """The attacker `creature` could block (`block_refusal`) that obeys the
    most of its requirements, and that count - `(None, 0)` when none obeys
    any."""
    best: CardState | None = None
    best_count = 0
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if not isinstance(attacker, CardState):
            continue
        count = _block_requirements_obeyed(game, creature, attacker)
        if count > best_count and block_refusal(game, creature, attack) is None:
            best, best_count = attacker, count
    return best, best_count


def _with_reassigned(
    declared: Mapping[UUID, list[CardState]], blocker: CardState, attacker_id: UUID
) -> dict[UUID, list[CardState]]:
    moved = {
        attacked: [chosen for chosen in blockers if chosen.id != blocker.id]
        for attacked, blockers in declared.items()
    }
    moved.setdefault(attacker_id, []).append(blocker)
    return moved


def unobeyed_block_requirement(
    game: "Game", declared: Mapping[UUID, list[CardState]], player: str | None = None
) -> str | None:
    """Why the block declaration `declared` (attacker id to its blockers)
    obeys fewer requirements than it could, or `None` (CR 509.1c).

    A declaration is short of CR 509.1c's maximum when some requirement
    holder could be moved onto the attacker its requirement names and the
    declaration would still break no restriction (`block_refusal` for the
    pair, `declaration_refusal` for the whole - menace, "can't block
    alone"): that declaration obeys more. Every requirement read here binds
    only its own creature, so one holder moved at a time finds each shortfall
    except one that only a second, requirement-free blocker joining could make
    legal (two blockers on a menace attacker) - a declaration this accepts
    rather than refuses. No "can't block unless a player pays" cost is
    modelled, so CR 509.1c's unpaid-cost clause has nothing to exempt.
    `player` narrows the check to one defending player's own creatures (CR
    802.4: each declares for their own).
    """
    blocking: dict[UUID, UUID] = {
        blocker.id: attacker_id
        for attacker_id, blockers in declared.items()
        for blocker in blockers
    }
    for creature in _block_requirement_holders(game):
        if player is not None and game.controller_of(creature).username != player:
            continue
        chosen_id = blocking.get(creature.id)
        chosen = game.find_by_id(chosen_id) if chosen_id is not None else None
        obeyed = _block_requirements_obeyed(
            game, creature, chosen if isinstance(chosen, CardState) else None
        )
        best, best_count = _most_obedient_block(game, creature)
        if best is None or best_count <= obeyed:
            continue
        if declaration_refusal(game, _with_reassigned(declared, creature, best.id)) is not None:
            continue
        where = "not blocking" if chosen is None else f"blocking {chosen.name}"
        return (
            f"{creature.name} blocks {best.name} each combat if able and can block it, "
            f"so {where} obeys fewer requirements than it could (CR 509.1c)"
        )
    return None


def required_block_declaration(game: "Game", username: str) -> list[tuple[UUID, UUID]]:
    """What an unscripted `username` declares instead of nobody: each of
    their requirement holders blocking the attacker it names (CR 509.1c),
    kept only while the whole declaration stays legal, repeated until
    nothing more can be added."""
    declared: dict[UUID, list[CardState]] = {
        attack.attacker_id: [] for attack in game.combat.attacks
    }
    pairs: list[tuple[UUID, UUID]] = []
    changed = True
    while changed:
        changed = False
        for creature in _block_requirement_holders(game):
            if game.controller_of(creature).username != username:
                continue
            if any(creature.id == blocker_id for blocker_id, _ in pairs):
                continue
            best, _count = _most_obedient_block(game, creature)
            if best is None:
                continue
            trial = _with_reassigned(declared, creature, best.id)
            if declaration_refusal(game, trial) is None:
                declared = trial
                pairs.append((creature.id, best.id))
                changed = True

    from .combat_statics import required_must_be_blocked_declaration

    pairs.extend(
        (blocker_id, attacker_id)
        for blocker_id, attacker_id in required_must_be_blocked_declaration(
            game, username, declared
        )
    )

    from .block_statics import required_exact_declaration, required_lure_declaration

    pairs.extend(required_lure_declaration(game, username, declared))
    pairs.extend(required_exact_declaration(game, username, declared))
    return pairs
