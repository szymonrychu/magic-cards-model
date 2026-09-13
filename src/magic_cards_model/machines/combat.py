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

import re
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from magic_cards_model.phrases import with_indefinite_article

from ..models.card import Type
from ..models.card_state import CardState, TargetRef
from ..models.zone import Zone
from .abilities import (
    TriggerEvent,
    keywords_in_lines,
    layer_readable_sentences,
    unread_keyword_tokens,
)
from .decisions import Decision, DecisionKind
from .triggers import GameEvent

#: What a creature may attack besides a player (CR 306.6, 310.5).
ATTACKABLE_PERMANENT_TYPES = frozenset({Type.PLANESWALKER, Type.BATTLE})

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game, Targetable


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
    #: CR 702.2a-c: a static ability that changes what counts as lethal damage
    #: when this creature assigns it, and adds a state-based action (CR 704.5h).
    DEATHTOUCH = "deathtouch"
    #: CR 702.15b: damage dealt by a source with lifelink makes its controller
    #: gain that much life, in addition to the damage's other results.
    LIFELINK = "lifelink"
    #: CR 702.14a-c: the five basic landwalks. Landwalk is an evasion ability
    #: (CR 702.14b) whose name carries the land type it looks for, so the
    #: members are spelled out rather than derived.
    PLAINSWALK = "plainswalk"
    ISLANDWALK = "islandwalk"
    SWAMPWALK = "swampwalk"
    MOUNTAINWALK = "mountainwalk"
    FORESTWALK = "forestwalk"


#: Keywords no combat rule reads, that a permanent may still have and a caller
#: may still ask about.
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
    }
)


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
    # `state.keywords`, not `state.card.keywords`: a face-down permanent has no
    # text at all (CR 702.37c, CR 708.2), so it has none of the printing's
    # keywords however plainly the card says them.
    return any(printed.lower() == wanted for printed in state.keywords)


class KeywordLineNotice(BaseModel):
    """One computed ability line that is part CR 702 keywords and part something
    this engine's keyword reader cannot name.

    `machines/abilities.py::_parse_keywords` is all-or-nothing on purpose: a
    line is CR 702.1's "only the name of the ability as a keyword" repeated, or
    it is not a keyword line at all, and reading half of one would grant an
    ability the card does not have unconditionally. Extinguisher Battleship's
    "5+ | Flying, trample" is exactly that trap - CR 721.2a makes the whole line
    conditional on five charge counters, so keeping the `trample` off it would
    be a fabricated grant.

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


class Attack(BaseModel):
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


class CombatMachine(BaseModel):
    """Who is attacking whom, who is blocking, and how much damage is done.

    Everything is held by id rather than by object, so the combat state is one
    serializable record next to the battlefield rather than a second copy of it.
    """

    attacks: list[Attack] = Field(default_factory=list)
    blockers_declared: bool = False
    damage_steps_done: int = 0
    first_strike_step_happened: bool = False
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

    def clear(self) -> None:
        """Everything is removed from combat as the combat phase ends (CR 511.3)."""
        self.attacks = []
        self.blockers_declared = False
        self.damage_steps_done = 0
        self.first_strike_step_happened = False
        self.attacked_this_combat = False


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
    if has_keyword(creature, Keyword.DEFENDER, game):
        # CR 702.3b: "A creature with defender can't attack." Checked after
        # tapping and summoning sickness so a Wall that is also tapped still
        # reports the reason a scenario is most likely asking about.
        return f"{creature.name} has defender and cannot attack (CR 702.3b)"
    restricted_until = getattr(game, "creatures_cant_attack_until_turns_taken", None)
    if restricted_until is not None and int(game.turn.turns_taken) == restricted_until:
        # CR 508.1c: a blanket "creatures can't attack this turn" restriction
        # (Orim's Chant, kicked), not read off any one permanent's own static
        # text the way the defender check above is.
        return f"{creature.name} can't attack this turn (CR 508.1c)"

    return _defender_refusal(game, defender, active)


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
    if not set(game.characteristics_of(permanent).types) & ATTACKABLE_PERMANENT_TYPES:
        return f"{permanent.name} is not a player, planeswalker, or battle"
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
        game.emit(
            GameEvent(
                event=TriggerEvent.BECOMES_TAPPED,
                subject_id=creature.id,
                subject_name=creature.name,
                subject_controller=game.controller_of(creature).username,
                subject_card=creature.card,
                player=game.controller_of(creature).username,
            )
        )

    game.combat.attacked_this_combat = True  # CR 508.8 reads the declaration
    attack = Attack(attacker_id=creature.id, defender=defender)
    game.combat.attacks.append(attack)
    return attack


# -- declaring blockers ----------------------------------------------------


class EvasionNotice(BaseModel):
    """One attacker whose own "can't be blocked" restriction text could not be
    read into a block refusal (CR 509.1a).

    Unlike flying (CR 702.9b), reach (CR 702.17b), or landwalk (CR 702.14c), a
    plain "can't be blocked" restriction carries no keyword name of its own -
    it is read straight off the attacker's oracle text by
    `evasion_restriction_refusal`, and only the two shapes that function reads
    are enforced. A sentence that opens the same way ("<subject> can't be
    blocked ...") but is not one of them is not silently treated as no
    restriction at all: `looks_like_unparsed_evasion_restriction` catches it
    and `block_refusal` records one of these instead, the same "unreadable is
    not the same as no effect" record `LayerNotice`, `TargetingNotice`,
    `InterveningIfNotice`, `ModeNotice`, and `AnaphoricClauseNotice` already
    keep for their own gaps.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The attacker's own oracle text, for whoever reads the notice later."""


def _evasion_restriction_sentences(attacker: CardState, game: "Game | None" = None) -> list[str]:
    """Self-referential "can't be blocked" sentences the attacker has *now*
    (CR 509.1a): the subject must be "this creature" or the card's own name
    (CR 509.1a's restriction is on the attacker itself; nothing in the pool
    grants "can't be blocked" to *another* creature the way Akroma's Memorial
    grants protection, so that shape is not read here - see
    `docs/engine-coverage.md`).

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

    A legendary permanent's own text names itself by its short name, the part
    before the comma - "April O'Neil can't be blocked ..." on a card printed
    "April O'Neil, Kunoichi Trainee" - the same self-reference
    `machines/triggers.py`'s `_self_referential` already reads.
    """
    # `attacker.name`/`attacker.oracle_text` already read the up face (CR
    # 712.8d/712.8f); `card.name`/`card.oracle_text` are the raw Scryfall
    # fields, null (`oracle_text`) or combined "Front // Back" (`name`) for a
    # modal-DFC/transform permanent - same family as `effect_for`'s fix.
    short_name = attacker.name.split(",")[0].strip()
    subject = re.compile(
        rf"^(?:this creature|{re.escape(short_name)})\b.*can't be blocked\b",
        re.IGNORECASE,
    )
    sentences = _computed_ability_sentences(attacker, game)
    return [sentence for sentence in sentences if subject.search(sentence)]


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
                sentence
                for ability in characteristics.abilities
                for sentence in layer_readable_sentences(ability)
            ]
    return layer_readable_sentences(state.oracle_text)


#: The Mindskinner: "The Mindskinner can't be blocked." - unconditional.
_CANT_BE_BLOCKED_RE = re.compile(r"can't be blocked\.?$", re.IGNORECASE)

#: Questing Beast: "Questing Beast can't be blocked by creatures with power 2
#: or less." - the one qualified shape read; other qualifiers (a colour, a
#: keyword) are not in the pool and are not attempted.
_CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE = re.compile(
    r"can't be blocked by creatures with power (?P<power>\d+) or less\.?$", re.IGNORECASE
)


def evasion_restriction_refusal(
    game: "Game", attacker: CardState, blocker: CardState
) -> str | None:
    """Why the attacker's own "can't be blocked" text refuses this blocker, or
    None (CR 509.1a).

    Read straight off the attacker's own oracle text rather than off
    `Keyword`: unlike flying or menace, this restriction has no keyword name of
    its own, so nothing in this module's vocabulary can name it. Only the two
    shapes above are read; a sentence that looks like an attempt at a third is
    caught by `looks_like_unparsed_evasion_restriction` instead of silently
    doing nothing.
    """
    for sentence in _evasion_restriction_sentences(attacker, game):
        if match := _CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE.search(sentence):
            threshold = int(match.group("power"))
            blocker_power = game.power_of(blocker)
            if blocker_power is not None and blocker_power <= threshold:
                return (
                    f"{attacker.name} can't be blocked by creatures with power "
                    f"{threshold} or less, and {blocker.name} has power {blocker_power} "
                    "(CR 509.1a)"
                )
        elif _CANT_BE_BLOCKED_RE.search(sentence):
            return f"{attacker.name} can't be blocked (CR 509.1a)"
    return None


def looks_like_unparsed_evasion_restriction(
    attacker: CardState, game: "Game | None" = None
) -> bool:
    """True if some self-referential sentence of the attacker's abilities reads
    like a "can't be blocked" restriction but is not one of the two shapes
    `evasion_restriction_refusal` reads - the fail-closed signal `block_refusal`
    turns into an `EvasionNotice` rather than a block that silently goes through
    unrestricted.

    Reads the same computed sentences the refusal does (CR 613.5), so a
    restriction the layer system has removed does not leave a notice behind
    claiming something was missed.
    """
    return any(
        _CANT_BE_BLOCKED_RE.search(sentence) is None
        and _CANT_BE_BLOCKED_BY_POWER_OR_LESS_RE.search(sentence) is None
        for sentence in _evasion_restriction_sentences(attacker, game)
    )


def block_refusal(game: "Game", blocker: CardState, attack: Attack) -> str | None:
    """Why this creature cannot block that attacker, or None (CR 509.1a-b).

    Covers the base requirements, who the attacker is attacking (CR 802.4a),
    and the evasion abilities that need nothing but the attacker and the
    blocker to decide: flying (CR 702.9b), reach (CR 702.17b), and a plain
    "can't be blocked" restriction read off the attacker's own text
    (CR 509.1a).
    """
    attacker = game.find_by_id(attack.attacker_id)
    if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
        return "that creature is no longer attacking"

    if blocker.zone is not Zone.BATTLEFIELD:
        return f"{blocker.name} is in {blocker.zone.value}, not on the battlefield"
    if not game.characteristics_of(blocker).is_creature:
        # Computed, not printed (CR 613.5) - see `attack_refusal`'s identical
        # check for why.
        return f"{blocker.name} is not a creature"
    if blocker.tapped:
        return f"{blocker.name} is tapped"

    defending = defending_player(game, attack.defender)
    if game.controller_of(blocker).username != defending:
        return f"{blocker.name} is not controlled by {defending}"

    if has_keyword(attacker, Keyword.FLYING, game) and not (
        has_keyword(blocker, Keyword.FLYING, game) or has_keyword(blocker, Keyword.REACH, game)
    ):
        return f"{attacker.name} has flying and {blocker.name} has neither flying nor reach"

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

    return landwalk_refusal(game, attacker, defending)


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
    (CR 702.111b). Each creature may block only one attacker (CR 509.1a).
    """
    seen: set[UUID] = set()
    for attacker_id, blockers in declared.items():
        for blocker in blockers:
            if blocker.id in seen:
                return f"{blocker.name} cannot block more than one attacker"
            seen.add(blocker.id)

        attacker = game.find_by_id(attacker_id)
        if attacker is None:
            continue
        if has_keyword(attacker, Keyword.MENACE, game) and 0 < len(blockers) < 2:
            return f"{attacker.name} has menace and cannot be blocked by fewer than two creatures"
    return None


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

    for attack in combat.attacks:
        chosen = declared[attack.attacker_id]
        attack.blockers = [blocker.id for blocker in chosen]
        # CR 509.1h: once blocked, a creature stays blocked for the rest of combat.
        attack.blocked = attack.blocked or bool(chosen)
    combat.blockers_declared = True


def defending_player(game: "Game", defender: TargetRef) -> str | None:
    """Who is defending against an attack on `defender` (CR 508.5): the player
    themselves, or - when the attack names a planeswalker or a battle - that
    permanent's controller.

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
        return game.controller_of(permanent).username
    return None


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

    In a first-strike step, only first strikers and double strikers assign. In
    the step after one, the double strikers assign again alongside everything
    that has neither ability.
    """
    first = has_keyword(state, Keyword.FIRST_STRIKE, game)
    double = has_keyword(state, Keyword.DOUBLE_STRIKE, game)
    if first_strike_step:
        return first or double
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

    for attack in combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        for blocker_id in attack.blockers:
            blocker = game.find_by_id(blocker_id)
            if blocker is None or blocker.zone is not Zone.BATTLEFIELD:
                continue
            if not deals_damage_this_step(blocker, first_strike_step=first_strike_step, game=game):
                continue
            # CR 510.1d: a blocker whose attacker has gone assigns no damage.
            if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
                continue
            power = _power_of(game, blocker)
            if power is None:
                _record_undefined_power(game, blocker)
            elif power > 0:
                assignments.append((blocker, attacker, power))

    for source, target, amount in assignments:
        _deal_combat_damage(game, source, target, amount)

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

    if isinstance(target, CardState) and has_keyword(source, Keyword.DEATHTOUCH, game):
        # CR 702.2b: destroyed as a state-based action, whatever its toughness.
        target.dealt_deathtouch_damage = True
    if has_keyword(source, Keyword.LIFELINK, game):
        # CR 702.15b / CR 120.3f, and CR 702.15e keeps each source's life gain
        # a separate event, which is why this is inside the per-source loop.
        game.gain_life(game.controller_of(source), dealt)
    return dealt


class UndefinedPowerNotice(BaseModel):
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
    remaining = None if toughness is None else toughness - blocker.damage - already_assigned
    if has_keyword(attacker, Keyword.DEATHTOUCH, game):
        return 0 if remaining is not None and remaining <= 0 else 1
    return remaining


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
    """
    power = _power_of(game, attacker)
    if power is None:
        _record_undefined_power(game, attacker)
        return []
    if power <= 0:  # CR 510.1a
        return []

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
_ATTACKS_EACH_COMBAT_RE = re.compile(
    r"^(?:(?P<subject>.+?) )?attacks each (?:combat|turn) if able\.?$", re.IGNORECASE
)


def is_attack_requirement_line(line: str, name: str) -> bool:
    """Whether one computed ability line of a creature named `name` is its own
    "attacks each combat if able" requirement (CR 508.1d)."""
    match = _ATTACKS_EACH_COMBAT_RE.fullmatch(line.strip())
    if match is None:
        return False
    subject = (match.group("subject") or "").strip().lower()
    return subject in ("", "this creature", "this permanent", name.lower())


def attack_requirement_holders(game: "Game", player: str) -> list[CardState]:
    """The creatures `player` controls that a requirement says attack each
    combat if able (CR 508.1d), read off the computed board (CR 613.5)."""
    board = game.computed_board()
    holders: list[CardState] = []
    for creature in game.permanents_controlled_by(player):
        characteristics = board.of(creature)
        if not characteristics.is_creature:
            continue
        if any(
            is_attack_requirement_line(line, creature.name) for line in characteristics.abilities
        ):
            holders.append(creature)
    return holders


def unobeyed_attack_requirement(game: "Game", declared: set[UUID]) -> CardState | None:
    """A creature whose requirement a declaration of `declared` disobeys
    although it could be obeyed, or `None` (CR 508.1d).

    Each requirement read here binds only its own creature, and CR 508.1a/c's
    checks are per creature, so the maximum number obeyable is every holder
    that could attack at all: a declaration leaving one of those out obeys
    fewer than the maximum. A creature that cannot attack - tapped, summoning
    sick without haste, under a restriction - carries no obeyable requirement.
    No "can't attack unless a player pays" cost is modelled, so CR 508.1d's
    unpaid-cost clause has nothing to exempt.
    """
    if game.turn is None:
        return None
    active = game.turn.active_player
    defenders = [
        TargetRef.coerce(player.username)
        for player in game.players_in_game
        if player.username != active
    ]
    for creature in attack_requirement_holders(game, active):
        if creature.id in declared:
            continue
        if any(attack_refusal(game, creature, defender) is None for defender in defenders):
            return creature
    return None
