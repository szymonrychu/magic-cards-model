import re
from collections.abc import Callable, Iterable
from random import Random
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import canonical_subtype
from ...models.card import Color, Type
from ...models.card_state import (
    CardState,
    ChoiceKind,
    Counter,
    ExileAnnotation,
    ExileMarker,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.token import (
    TokenDefinition,
    create_tokens,
    is_token,
    token_copy_of,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    QUANTITY,
    Quantity,
    QuantitySource,
    count_pattern,
    parse_count,
    parse_quantity,
    quantity_pattern,
    where_x_pattern,
)
from .. import combat as combat_rules
from ..abilities import (
    TriggerEvent,
)
from ..casting import (
    PlayAction,
    annotate_exile,
)
from ..chosen_type import (
    shares_creature_type,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    DelayedTrigger,
    PayOrElseReturnExiledCard,
    ReflexiveConsequence,
    ReturnEachExiledToBattlefieldUnderOwner,
    ReturnExiledCardAndAddCounters,
    anaphoric_delayed_trigger,
    sacrificed_by_its_controller,
)
from ..layers import (
    Characteristics,
)
from ..legacy_keywords import parse_champion_clause, parse_clash_clause
from ..linked_exile import (
    parse_return_all_linked_to_hand_lose_life_clause,
    parse_return_linked_creature_clause,
    parse_return_other_linked_cards_to_hand_clause,
)
from ..targeting import (
    TargetRequirement,
    permanent_description,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import (
    _SACRIFICED_MANA_VALUE_TERM,
    AbilityEffect,
    ClauseEffect,
    Effect,
    ExileAntecedent,
    TargetedClause,
    _SacrificeRestriction,
)
from .library import _source_escaped


def counter_targets(game: "Game", spell: CardState) -> None:
    """Counter each targeted spell, putting it into its owner's graveyard.

    A counterspell whose target has already left the stack does nothing, which
    is what happens when the target was itself countered first (CR 608.2b).
    """
    for reference in spell.targets:
        if not reference.is_card:
            continue
        target = next((item for item in game.stack if item.id == reference.card_id), None)
        if target is not None:
            game.counter(target)


def _counter_unless_pays_effect(
    amount: int, *, to_exile: bool = False, to_library: Literal["top", "bottom"] | None = None
) -> Effect:
    """ "Counter target spell unless its controller pays {N}." (CR 118.12a).

    Read as one CR 608.2c instruction, not two: the question is put to the
    *targeted* spell's controller (`Game.may_pay_mana`'s `player`, not this
    counterspell's caster), because CR 118.12a's "[a player] may [do
    something else]" names whoever the "unless" clause names. A target that
    has already left the stack (CR 608.2b: countered first, resolved, or
    otherwise gone) is simply skipped, the same as plain `counter_targets`.

    `to_exile` overrides CR 701.6a's "a countered spell is put into its
    owner's graveyard" - Syncopate's own second sentence, the same override
    `_parse_counter_then_exile_instead_of_graveyard_pair` already gives Force
    of Negation's plain counter.

    `amount` is a number by the time this is built. An `{X}` in the printed
    text never reaches here as a literal: CR 107.3a's X is announced as the
    spell is cast and holds while it is on the stack, so `effect_for`
    substitutes the announced value into the oracle text before the clause is
    read (`substitute_x`), and this sees Syncopate's "{X}" as the "{2}" the
    caster actually paid for.
    """

    def effect(game: "Game", spell: CardState) -> None:
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            paid = game.may_pay_mana(
                target.controller, amount, source=spell.name, source_id=source_id_of(spell)
            )
            if not paid:
                game.counter(target, to_exile=to_exile, to_library=to_library)

    return effect


#: "Counter target `<phrase>` unless its controller pays {N}." on an
#: *activated or triggered* ability - Malevolent Hermit's "{U}, Sacrifice this
#: creature: Counter target noncreature spell unless its controller pays
#: {3}." The spell-only reading in `dispatch.py` is `for_spell`-gated;
#: CR 118.12a's question goes to the targeted spell's controller either way,
#: and `_counter_unless_pays_effect` reads only the targets and the stack, both
#: of which an `AbilityOnStack` carries (Hope-Ender Coatl's "unless they pay"
#: already reaches it from a trigger).
_ABILITY_COUNTER_UNLESS_PAYS_RE = re.compile(
    r"^counter (?P<phrase>target [^.]*?spell) unless its controller pays \{(?P<n>\d+)\}\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_ability_counter_unless_pays_clause(text: str) -> AbilityEffect | None:
    """`_ABILITY_COUNTER_UNLESS_PAYS_RE`'s shape, or `None`."""
    if "unless its controller pays" not in text:
        return None
    match = _ABILITY_COUNTER_UNLESS_PAYS_RE.fullmatch(text.strip())
    if match is None or not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None
    return _counter_unless_pays_effect(int(match.group("n")))


#: "1/1 colorless Thopter artifact creature token with flying" - Hangarback
#: Walker, Thopter Assembly.
THOPTER = TokenDefinition(
    types=(Type.ARTIFACT, Type.CREATURE),
    subtypes=("Thopter",),
    power=1,
    toughness=1,
    keywords=("Flying",),
)


def hangarback_dies(game: "Game", ability: AbilityOnStack) -> None:
    """Hangarback Walker: "When this creature dies, create a 1/1 colorless Thopter
    artifact creature token with flying for each +1/+1 counter on this creature."

    The count is read off the counters the permanent had **as it last existed on
    the battlefield**. CR 122.2 destroys counters on a zone change and CR 603.10a
    makes a dies trigger look back in time at the object as it was, which is what
    `CardState.last_known_counters` (CR 704.8) is holding by the time this runs.
    """
    source = ability.source(game)
    if source is None:
        return
    counters = source.counters if source.zone is Zone.BATTLEFIELD else source.last_known_counters
    create_tokens(game, THOPTER, ability.controller, counters[Counter.PLUS_ONE])


#: ecl-T8: a card's own trailing "Exile `<its own name>`." - CR 201.5's own
#: self-reference, the same shape Worlds Within Worlds' and Burning Wish's
#: printings already carry (see `_EXILE_ALL_CREATURES_THEN_HAND_REFILL_RE`'s
#: own tail), generalised here into its own single-clause reader so any card
#: ending its text this way is covered, not just that one combined shape.
#: Read as a *name*, not by comparing against the resolving object's own
#: printed name: CR 201.5 always means "this object", and nothing else in a
#: card's own text ever exiles a specific other nontoken permanent by a bare
#: capitalised phrase with no "target"/"that"/"it" in front of it.
_EXILE_SELF_NAME_CLAUSE_RE = re.compile(r"^exile (?P<name>[A-Z][A-Za-z' ,.-]*[A-Za-z])\.?$")


@MIXED_CLAUSE.rung("s7", for_spell=FORWARD)
def _parse_exile_self_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_EXILE_SELF_NAME_CLAUSE_RE`'s shape - only ever a spell (CR 608.2n's
    own graveyard step is what this clause overrides for an instant or
    sorcery; nothing in the pool prints it on an ability)."""
    if not for_spell:
        return None
    if _EXILE_SELF_NAME_CLAUSE_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        if spell.zone is Zone.STACK:
            game.exile_cards([spell])

    return effect


def each_player_exiles_sacrifices_and_returns_creatures(game: "Game", spell: CardState) -> None:
    """Living End: "Each player exiles all creature cards from their graveyard,
    then sacrifices all creatures they control, then puts all cards they
    exiled this way onto the battlefield."

    Three CR 608.2c instructions, each performed for every player before the
    next one starts, rather than one player's whole sequence before the next
    player's: CR 101.4's APNAP order only orders *choices*, and nothing here
    is a choice, so there is no rules reason to interleave them by player
    instead of by step - and doing it by step is what keeps "sacrifices all
    creatures they control" from ever seeing a creature this same effect just
    exiled from a graveyard onto nobody's battlefield yet.

    - **CR 701.13a / 406.2** - exile is "move it to the exile zone from
      wherever it is"; a graveyard is as good a wherever as any.
      `Game.exile_permanent` takes any `CardState` regardless of its current
      zone, so it exiles a graveyard card exactly the way it exiles a
      permanent.
    - **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
      the battlefield directly to its owner's graveyard" - `Game.sacrifice`.
    - **CR 400.7, CR 110.2a** - a card put onto the battlefield this way is a
      new object, not the graveyard card come back to life; `Game.
      put_onto_battlefield` is the Tooth and Nail path this effect reuses.

    Only *cards* were exiled, so a creature token that got sacrificed at the
    second step is simply gone (CR 111.7) - it was never eligible for the
    first step and has nothing to return at the third.
    """
    exiled_by_player: dict[str, list[CardState]] = {}
    for player in game.players_in_game:
        creatures = [state for state in list(player.graveyard) if state.is_creature]
        exiled_by_player[player.username] = [game.exile_permanent(state) for state in creatures]

    for player in game.players_in_game:
        controlled = [
            permanent
            for permanent in list(game.battlefield)
            if permanent.controller == player.username
            and game.characteristics_of(permanent).is_creature
        ]
        for permanent in controlled:
            game.sacrifice(permanent)

    for player in game.players_in_game:
        for state in exiled_by_player[player.username]:
            game.put_onto_battlefield(state, player.username)


def _then_exile_self(rest: Effect, *, time_counters: int | None = None) -> Effect:
    """`rest`, then CR 608.2c's last written instruction: the spell exiles
    itself as it resolves, so CR 608.2n's move to its owner's graveyard never
    happens (the same `Game.exile_cards` the Burning Wish family's own
    "Exile `<this>`" uses).

    With `time_counters`, the card arrives in exile with that many time
    counters on it; a card that has suspend is then suspended (CR 702.62b)
    and its keyword's own exile-zone triggers take it from there. A card a
    replacement effect sent somewhere other than exile gets none."""

    def effect(game: "Game", spell: CardState) -> None:
        rest(game, spell)
        game.exile_cards([spell])
        if time_counters and spell.zone is Zone.EXILE:
            game.add_counters(spell, Counter.TIME, time_counters)

    return effect


def exile_ability_targets(game: "Game", ability: AbilityOnStack) -> None:
    """Exile every card this ability still legally targets (CR 608.2b).

    Not battlefield-only: CR 406.2/701.13a exile "from whatever zone it's
    currently in", and Faerie Macabre's "Exile up to two target cards from
    graveyards" and Keen-Eyed Curator's "Exile target card from a graveyard"
    both name one - measured working end to end this session
    (`tests/scenarios/test_targeted_effect_parser.py`). `game.resolve_targets`
    already rechecks each target against the printed restriction's own zones
    (CR 608.2b), and `Game.exile_permanent` is zone-agnostic (see its
    docstring), so nothing else here needs to filter by zone - doing so used
    to silently drop every graveyard-exile card's whole effect.

    One look-alike stays unreached by this: Tormod's Crypt and Bojuka Bog's
    "exile target player's graveyard" *targets the player*, not a card
    (`allows_cards=False`), so this function's `isinstance(target, CardState)`
    check silently skips it - that shape is `exile_target_players_graveyard`
    below instead, a separate clause the parser routes to on sight of the
    "player's graveyard" phrase rather than this function ever seeing it.
    Kozilek's Command's "Exile up to X target cards from graveyards" is one
    mode of a modal spell and *does* reach this function now, through
    `resolve_modal_spell` (`parse_mode_effect` falls back to
    `parse_mixed_effect_for_spell`, which reads this shape the same way any
    non-modal card's text would).
    """
    linked = _source_reads_its_exiled_cards(game, ability)
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState):
            exiled = game.exile_permanent(target)
            if linked and exiled.zone is Zone.EXILE:
                # CR 607.2a: the object's other ability refers to "the exiled
                # card", and only to a card this ability exiled - so the card
                # is marked as exiled with the ability's source.
                exiled.exile_annotation = linked_exile_annotation(game, ability, exiled)


def linked_exile_annotation(
    game: "Game", ability: AbilityOnStack, card: CardState
) -> ExileAnnotation:
    """The CR 607.2a link a card exiled by `ability` carries back to the
    object the ability came from: its id and - CR 400.7 - which incarnation
    of it (`AbilityOnStack.source_stamp`), so a permanent that left and came
    back does not read its earlier self's pile."""
    return ExileAnnotation(
        marker=ExileMarker.LINKED,
        owner=card.owner,
        turn_exiled=game.turn.turns_taken if game.turn is not None else None,
        linked_permanent_id=ability.source_id,
        linked_permanent_stamp=ability.source_stamp,
    )


#: An instruction to exile (CR 607.2a's "instructs a player to exile one or
#: more cards") somewhere in an ability's own text.
_EXILE_INSTRUCTION_RE = re.compile(r"\bexiles?\b", re.IGNORECASE)


def link_cards_exiled_during(
    game: "Game", ability: AbilityOnStack, exiled_before: set[UUID]
) -> None:
    """CR 607.2a / CR 406.6 for every exile an ability's resolution made:
    when the object has "an activated or triggered ability printed on it that
    instructs a player to exile one or more cards and an ability printed on
    it that refers either to 'the exiled cards' or to cards 'exiled with
    [this object]'", the cards the first one exiled are the second one's pile.

    `Game._resolve_ability` calls this once the effect has run, with the ids
    that were already in exile beforehand. Whatever is newly in exile and was
    not given a pile of its own by the effect (`exile_annotation is None`) is
    linked to the ability's source - Voltaic Visionary's "Exile the top card
    of your library", Pyxis of Pandemonium's "Each player exiles the top card
    of their library face down" - with no per-parser wiring: which clause did
    the exiling is irrelevant to the structural test CR 607.2a states. A
    face-down card keeps having no characteristics (`CardState.has_no_
    characteristics`: a bare `LINKED` link grants no play)."""
    if ability.source_id is None or not _EXILE_INSTRUCTION_RE.search(ability.ability.text or ""):
        return
    if not _source_reads_its_exiled_cards(game, ability):
        return
    for card in game.exile:
        if not isinstance(card, CardState) or card.id in exiled_before:
            continue
        if card.exile_annotation is None and card.zone is Zone.EXILE:
            card.exile_annotation = linked_exile_annotation(game, ability, card)


#: CR 607.2a's second ability: "refers either to 'the exiled cards' or to
#: "Exile up to `<n>` target card(s) from a/graveyards. If a/at least one
#: creature card was exiled this way, `<rider>`." / "... For each creature
#: card exiled this way, `<rider>`." - Graveyard Trespasser's own trigger
#: ("exile up to one target card from a graveyard. If a creature card was
#: exiled this way, each opponent loses 1 life and you gain 1 life.") and its
#: night face Graveyard Glutton's count-scaled twin ("exile up to two target
#: cards from graveyards. For each creature card exiled this way, ...").
#: Soul-Shackled Zombie's "exile up to two target cards from a single
#: graveyard. If at least one creature card was exiled this way, each
#: opponent loses 2 life and you gain 2 life." is the same binary shape with
#: a different quantifier word and a different drain amount - proof this
#: reader is not fitted to either printed sentence.
_EXILE_GRAVEYARD_THEN_CREATURE_RIDER_RE = re.compile(
    r"^exile (?P<phrase>up to (?:one|two|three|four|\d+) target cards? from "
    r"(?:a |a single |an? )?graveyards?)\.\s*"
    r"(?P<mode>if an? creature card was exiled this way|"
    r"if at least one creature card was exiled this way|"
    r"for each creature card exiled this way),\s*"
    r"(?P<rider>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_exile_graveyard_then_creature_rider_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EXILE_GRAVEYARD_THEN_CREATURE_RIDER_RE`'s shape.

    "If a/at least one creature card was exiled this way" runs `rider` once
    when at least one exiled card was a creature card (CR 608.2c: the
    antecedent's own instruction runs first, then the conditional one);
    "for each creature card exiled this way" runs it once *per* creature
    card exiled - Graveyard Glutton's own drain doubling on a double hit,
    the same "for each" multiplier every other reader here already gives a
    per-count rider. CR 400.7/CR 700.4: whether an exiled card "is a creature
    card" is read off the card itself before it moves (`Type.CREATURE in
    target.types`), the same instant `exile_ability_targets` reads it.
    """
    match = _EXILE_GRAVEYARD_THEN_CREATURE_RIDER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    rider_text = match.group("rider").strip()
    rider = (
        parse_mixed_effect_for_spell(rider_text) if for_spell else parse_mixed_effect(rider_text)
    )
    if rider is None:
        return None
    for_each = match.group("mode").strip().lower().startswith("for each")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        creature_cards = 0
        for target in game.resolve_card_targets(stack_object):
            is_creature = Type.CREATURE in target.types
            game.exile_permanent(target)
            if is_creature:
                creature_cards += 1
        if creature_cards <= 0:
            return
        repeats = creature_cards if for_each else 1
        for _ in range(repeats):
            rider(game, stack_object)

    return effect


#: cards 'exiled with [this object]'".
_LINKED_EXILE_READER_RE = re.compile(r"\bthe exiled cards?\b|\bexiled with\b", re.IGNORECASE)


def _source_reads_its_exiled_cards(game: "Game", ability: AbilityOnStack) -> bool:
    """Whether the resolving ability's source has another printed ability that
    reads the cards this one exiles (CR 607.2a, CR 406.6) - Skyclave
    Apparition's "the exiled card's owner creates ...". Read off the card's own
    oracle text, so every object printing the linked pair gets the link."""
    if not isinstance(ability, AbilityOnStack) or ability.source_id is None:
        # A spell exiling its targets (Utter End, Celestial Purge) is not an
        # ability of an object with a linked reader; nothing to link.
        return False
    # CR 113.7a/608.2h: a source that has ceased to exist is read from its
    # last known information, so a token's linked pair still links.
    source = ability.source_or_last_known(game)
    if not isinstance(source, CardState):
        return False
    own = ability.ability.text
    for line in (source.card.front_oracle_text or "").splitlines():
        if own and (own in line or line in own):
            continue
        if _LINKED_EXILE_READER_RE.search(line):
            return True
    return False


def exile_target_players_graveyard(game: "Game", stack_object: "StackObject") -> None:
    """Bojuka Bog / Tormod's Crypt: "exile target player's graveyard."

    CR 115.1: "The targets are object(s) and/or player(s) the spell or ability
    will affect" - here the *target* is the player, not a card, which is why
    `exile_ability_targets`'s `isinstance(target, CardState)` check can never
    reach this shape (`_targets_understood`'s `allow_player_targets` gate is
    what tells the two apart while parsing). `game.resolve_targets` already
    reruns CR 608.2b for a player target - gone from the game is illegal,
    still in it is not - so by the time this runs the player is a real,
    current `Player`.

    CR 404.1: "A player's graveyard is their discard pile", one of the
    per-player zones on `Player`, not the target itself. Once the player is
    confirmed legal, every card sitting in *their* graveyard right now - full
    or empty, the caster's own or an opponent's - is exiled one by one through
    `Game.exile_permanent` (CR 406.2/701.13a: exile moves an object "from
    whatever zone it's currently in", so a graveyard card is as reachable as a
    permanent). An empty graveyard is exactly as legal a target as a full one:
    nothing in CR 115 or CR 608.2b conditions targeting a player on what is in
    their zones, only on whether they are still in the game.
    """
    for target in game.resolve_targets(stack_object):
        if isinstance(target, Player):
            for card_state in list(target.graveyard):
                game.exile_permanent(card_state)


def exile_all_graveyards(game: "Game", stack_object: "StackObject") -> None:
    """Rest in Peace: "exile all graveyards."

    No target at all - every player's graveyard, own included (CR 404.1), is
    emptied into the shared exile zone (CR 406.2/701.13a). `game.players_in_game`
    is CR 104.3a's still-playing set, so a player who has already conceded or
    lost contributes nothing (there is no graveyard left to read a rule about).

    Rest in Peace's second sentence - "If a card or token would be put into a
    graveyard from anywhere, exile it instead" - is a static replacement
    effect (CR 614), a different ability entirely from this one's ETB trigger,
    and is not attempted here: `machines/effects.py` has no home for a
    graveyard-redirecting replacement effect the way `machines/replacement.py`
    already does for "enters tapped". It is not counted by this file's own
    sweep either, the same way a shockland's own replacement text is not -
    see `docs/mcp-tools.md`/`scripts/sweep_pool.py`'s own scope note.
    """
    for player in game.players_in_game:
        for card_state in list(player.graveyard):
            game.exile_permanent(card_state)


#: "Exile all cards from `<players>` hand(s) and graveyard(s)." - one
#: instruction (CR 406.2) emptying two of each named player's own zones (CR
#: 402.1, CR 404.1), over every player scope it is printed with: "all"
#: (Worldfire: every player), "all opponents'" (Ashiok, Nightmare Weaver's
#: `-10`: CR 102.2/102.3's opponents, sparing the controller), and "target
#: player's" (Identity Crisis: a CR 115.1 player target). The two zones may
#: be listed in either order, singular or plural.
_EXILE_ALL_CARDS_FROM_HANDS_AND_GRAVEYARDS_RE = re.compile(
    r"^exile all cards from "
    r"(?:(?P<all>all)|(?P<opponents>all opponents'|each opponent's)|"
    r"(?P<phrase>target (?:player|opponent)'s)) "
    r"(?:hands? and graveyards?|graveyards? and hands?)\.?$",
    re.IGNORECASE,
)


def _exile_hands_and_graveyards(players: Iterable[Player], game: "Game") -> None:
    """Every card in each of `players`' hand and graveyard, exiled as one
    instruction (CR 406.2) - one `Game.exile_cards` batch, so a "one or more
    cards leave your graveyard" trigger sees one event per graveyard."""
    cards: list[CardState] = []
    for player in players:
        cards.extend(player.hand)
        cards.extend(player.graveyard)
    game.exile_cards(cards)


def _parse_exile_all_cards_from_hands_and_graveyards_clause(
    clause: str,
) -> TargetedClause | None:
    """`_EXILE_ALL_CARDS_FROM_HANDS_AND_GRAVEYARDS_RE`'s shape, or `None`."""
    match = _EXILE_ALL_CARDS_FROM_HANDS_AND_GRAVEYARDS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if match.group("all"):

        def exile_every_players(game: "Game", stack_object: "StackObject") -> None:
            _exile_hands_and_graveyards(list(game.players_in_game), game)

        return exile_every_players
    if match.group("opponents"):

        def exile_opponents(game: "Game", stack_object: "StackObject") -> None:
            controller = game.controller_of(stack_object)
            _exile_hands_and_graveyards(_opponents(game, controller.username), game)

        return exile_opponents
    if not _targets_understood(match.group("phrase"), allow_player_targets=True):
        return None

    def exile_target_players(game: "Game", stack_object: "StackObject") -> None:
        targets = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        _exile_hands_and_graveyards(targets, game)

    return exile_target_players


def exile_each_opponents_graveyard(game: "Game", stack_object: "StackObject") -> None:
    """Soul-Guide Lantern / Ashiok, Dream Render: "exile each opponent's
    graveyard."

    No target either (CR 115.1 has nothing to target here, the same as
    `exile_all_graveyards`), but a *player-set qualifier* narrows which
    graveyards: CR 102.2's "opponent" (the other player, in the two-player
    case this pool's decks are built for) rather than CR 404.1's every
    player. This is `exile_all_graveyards`'s filtered twin, not that
    function reused with a different loop - `exile_all_graveyards` walks
    `game.players_in_game` unfiltered, and routing "each opponent's
    graveyard" through it would exile the ability's own controller's
    graveyard too, which reads as a working card until the controller is the
    one holding Soul-Guide Lantern's own reflection off their own dead
    Snapcaster Mage. `_opponents` is the same helper `damage_each_opponent`
    (Guttersnipe) already uses for this word.
    """
    controller = game.controller_of(stack_object)
    for opponent in _opponents(game, controller.username):
        for card_state in list(opponent.graveyard):
            game.exile_permanent(card_state)


#: Reused by `_exile_matching_from_all_graveyards`, defined lower in this file
#: next to `_HAND_EXILE_COLOR_WORDS` - forward reference is fine, since this is
#: only ever called once the whole module has finished importing.
def _graveyard_exile_quality_matcher(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for "cards that are `<quality>`" - Sanctifier en-Vec's
    "black or red" - or `None` if this wave cannot read every word of it.

    Reuses `_hand_exile_quality_matcher`'s single-word colour/type reading
    (CR 105.2c's five colours, CR 205.2a's card types) rather than duplicating
    it, splitting on "or"/comma the same way `_quality_matcher` does for a
    search's stated quality. Fail-closed per word: a quality this wave cannot
    read - a supertype, a subtype - refuses the whole clause (CR 608.2c)
    rather than exiling the wrong, narrower set of cards silently.
    """
    words = [
        word.strip() for word in re.split(r",\s*|\s+or\s+", quality.strip().lower()) if word.strip()
    ]
    if not words:
        return None
    matchers = []
    for word in words:
        matcher = _hand_exile_quality_matcher(word)
        if matcher is None:
            return None
        matchers.append(matcher)

    def matches(state: CardState) -> bool:
        return any(matcher(state) for matcher in matchers)

    return matches


def _exile_matching_from_all_graveyards(
    matches: Callable[[CardState], bool],
) -> TargetedClause:
    """Sanctifier en-Vec: "exile all cards that are black or red from all
    graveyards" - the filtered twin of `exile_all_graveyards`, keeping only
    the cards `matches` accepts (CR 404.1's graveyards, CR 406.2/701.13a's
    exile). No target either; every player's graveyard is read, the caster's
    own included, the same as the unfiltered shape.

    Sanctifier en-Vec's own second sentence is the same kind of static
    replacement effect Rest in Peace's is, and is left unattempted for the
    same reason - see `exile_all_graveyards`.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for player in game.players_in_game:
            for card_state in list(player.graveyard):
                if matches(card_state):
                    game.exile_permanent(card_state)

    return effect


def destroy_ability_targets(game: "Game", ability: AbilityOnStack) -> None:
    """Destroy each permanent this ability still legally targets (CR 701.8a).

    "To destroy a permanent, move it from the battlefield to its owner's
    graveyard." Ghost Quarter's half of the deal. The other half - "Its
    controller may search their library for a basic land card, put it onto the
    battlefield" - is `_parse_search_clause`'s "its controller may" shape (see
    `_build_search_clause`), a separate clause because it is the *opponent's*
    optional choice and not the activator's.
    """
    for target in game.resolve_targets(ability):
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
            game.destroy(target)


#: Winnowing's own convoke spell body: "For each player, you choose a
#: creature that player controls. Then each player sacrifices all other
#: creatures they control that don't share a creature type with the chosen
#: creature they control." No "target" word at all - CR 608.2b's own
#: resolution-time choice (the caster chooses, for every player, which of
#: that player's own creatures the rest of that player's board is judged
#: against), not CR 601.2c targeting, so this reads at resolution rather
#: than through `machines/targeting.py`.
_WINNOWING_SACRIFICE_RE = re.compile(
    r"^for each player, you choose a creature that player controls\. then each player "
    r"sacrifices all other creatures they control that don'?t share a creature type "
    r"with the chosen creature they control\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s17", for_spell=True)
def _parse_shared_type_sacrifice_clause(text: str, *, for_spell: bool) -> Effect | None:
    """`_WINNOWING_SACRIFICE_RE`'s shape, or `None`.

    CR 101.4's APNAP order governs both halves: the choices are made in that
    order (`_players_in_apnap_order`), and so is judging each player's own
    board once every choice has been made - a player with no creature at all
    is simply skipped, both as a chooser (CR 608.2b never offers a choice
    with no legal object) and as a sacrificer (nothing there to keep or
    lose)."""
    if not for_spell:
        return None
    whole = _strip_non_effect_preamble(text).strip()
    if _WINNOWING_SACRIFICE_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        source_id = source_id_of(spell)
        order = _players_in_apnap_order(game)
        chosen: dict[str, CardState] = {}
        for player in order:
            creatures = [
                state
                for state in game.permanents_controlled_by(player.username)
                if Type.CREATURE in game.characteristics_of(state).types
            ]
            if not creatures:
                continue
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose a creature {player.username} controls",
                    source=spell.name,
                    amount=1,
                    cards=tuple(state.id for state in creatures),
                    source_id=source_id,
                )
            )
            assert isinstance(answer, tuple)
            if answer:
                found = game.find_by_id(answer[0])
                if isinstance(found, CardState):
                    chosen[player.username] = found
        for player in order:
            pick = chosen.get(player.username)
            if pick is None:
                continue
            for creature in list(game.permanents_controlled_by(player.username)):
                if creature.id == pick.id:
                    continue
                if Type.CREATURE not in game.characteristics_of(creature).types:
                    continue
                if shares_creature_type(game, creature, pick):
                    continue
                if creature.zone is Zone.BATTLEFIELD:
                    game.sacrifice(creature)

    return effect


#: "Search your library for a creature card with mana value equal to 1 plus
#: the sacrificed creature's mana value, put that card onto the battlefield
#: [with an additional +1/+1 counter on it], then shuffle." (Neoform, Prime
#: Speaker Vannifar, Enigmatic Incarnation) and "Search your library for a
#: creature card with mana value X or less, where X is 2 plus the sacrificed
#: creature's mana value. Put that card onto the battlefield, then shuffle."
#: (Eldritch Evolution) - one instruction with two bounds: an equality, or
#: CR 107.3c's self-defined X as a ceiling. The offset and the additional
#: counter count are read through `numbers.COUNT` rather than pinned.
_SEARCH_MV_EQUAL_TO_SACRIFICED_RE = re.compile(
    r"^search (?:your|their) library for (?:a|an) (?P<quality>.+?) card with mana value "
    rf"(?:equal to {count_pattern('equal', article=False)}"
    rf"|x or less, where x is {count_pattern('at_most', article=False)}) "
    rf"{_SACRIFICED_MANA_VALUE_TERM}[,.] "
    r"put (?:that card|it) onto the battlefield"
    rf"(?: with {count_pattern('counters')} additional \+1/\+1 counters? on it)?"
    r",? then shuffle\.?$",
    re.IGNORECASE,
)

#: `(game, searching player, the sacrificed permanent's mana value, source
#: name, source id)` - the search half, run once whoever did the sacrificing
#: has said what the sacrificed permanent's mana value was.
_SacrificedManaValueSearch = Callable[["Game", Player, float, str, str | None], None]


def _sacrificed_mana_value_search(text: str) -> _SacrificedManaValueSearch | None:
    """`_SEARCH_MV_EQUAL_TO_SACRIFICED_RE`'s shape, compiled into a search
    that is handed the sacrificed permanent's mana value by its caller - the
    spell or ability that paid a cost (`_parse_search_mv_equal_to_sacrificed_
    clause`), or the "you may sacrifice ... If you do, ..." that sacrificed
    it while resolving (`_parse_conditional_sacrifice_clause`).

    CR 701.23a is the search, CR 701.23b is why failing to find is legal (a
    stated quality), and `_search_library` folds CR 701.24a's shuffle in.
    Fail-closed on a quality `_search_quality_is_readable` cannot read
    (CR 608.2c: no half-run instruction).

    **The +1/+1 counter is put on after the permanent has entered**, not as
    part of the entering event: `Game.enter_the_battlefield` takes no
    externally supplied counters, and nothing between the two moments can
    tell the difference - CR 704.3 checks state-based actions only when a
    player would receive priority, never mid-resolution.
    """
    match = _SEARCH_MV_EQUAL_TO_SACRIFICED_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches_quality = _quality_matcher(quality)
    equal = match.group("equal")
    offset = parse_count(equal if equal is not None else match.group("at_most"), article=False)
    if offset is None:
        return None
    counters_word = match.group("counters")
    counters = 0 if counters_word is None else parse_count(counters_word)
    if counters is None:
        return None

    def run(
        game: "Game",
        player: Player,
        sacrificed: float,
        source: str,
        source_id: str | None,
    ) -> None:
        bound = offset + sacrificed

        def matches(state: CardState) -> bool:
            if not matches_quality(state):
                return False
            return state.mana_value == bound if equal is not None else state.mana_value <= bound

        found = _search_library(game, player, matches, source=source, source_id=source_id)
        if found is None:
            return
        permanent = game.put_onto_battlefield(found, player.username)
        if counters and permanent is not None and permanent.zone is Zone.BATTLEFIELD:
            game.add_counters(permanent, Counter.PLUS_ONE, counters)

    return run


def _cost_sacrificed_mana_value(game: "Game", stack_object: "StackObject") -> float | None:
    """The mana value "the sacrificed `<type>`" had, when the sacrifice paid
    a cost: an activated ability's own (CR 602.2b) off `AbilityOnStack.cost_
    sacrificed_mana_values`, a spell's additional cost (CR 118.8a) off
    `CastRecord.additional_cost_mana_values`. Both were taken as the cost was
    paid, so CR 608.2h's last known information survives a sacrificed token
    ceasing to exist (CR 704.5d) and a copy's copied mana cost (CR 707.2).
    `None` when nothing was sacrificed to pay for it."""
    if isinstance(stack_object, AbilityOnStack):
        if stack_object.cost_sacrificed_mana_values:
            return stack_object.cost_sacrificed_mana_values[0]
        if stack_object.cost_sacrificed_card_ids:
            return game.last_known_mana_value(stack_object.cost_sacrificed_card_ids[0])
        return None
    record = game.cast_record(stack_object)
    if record.additional_cost_mana_values:
        return record.additional_cost_mana_values[0]
    if record.additional_cost_cards:
        return game.last_known_mana_value(record.additional_cost_cards[0])
    return None


def _may_sacrifice_for_its_mana_value(
    game: "Game",
    stack_object: "StackObject",
    restriction: "_SacrificeRestriction",
    printed: str,
    *,
    for_spell: bool,
) -> float | None:
    """CR 118.12's optional cost, "you may sacrifice `<restriction>`", paid
    while resolving: `None` when the player declines (or cannot - CR 608.2d
    never offers an impossible "yes"), else the sacrificed permanent's mana
    value, read while it is still on the battlefield (CR 608.2h: the computed
    one, so a copy counts as what it copies)."""
    player = game.controller_of(stack_object)
    source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
    candidates = restriction.candidates(game, player, source_id)
    if not game.ask(
        Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=f"sacrifice {printed}",
            source=source_name,
            affirmative_is_legal=_sacrifice_is_payable(restriction.quantity, candidates),
            source_id=source_id_of(stack_object),
        )
    ):
        return None
    chosen = _choose_permanents_to_sacrifice(
        game,
        player,
        restriction,
        candidates,
        source_name=source_name,
        source_id=source_id_of(stack_object),
    )
    if not chosen:
        return None
    mana_value = game.last_known_mana_value(chosen[0])
    for permanent in chosen:
        game.sacrifice(permanent)
    game.record_count(len(chosen))
    return mana_value


def _exile_cards_from_graveyard(
    game: "Game",
    player: Player,
    count: int,
    source: str,
    *,
    source_id: str | None,
    predicate: Callable[[CardState], bool] | None = None,
) -> list[CardState]:
    """CR 608.2d: `player` exiles `count` cards of their own choice from
    their own graveyard. There is no CR 701.9b-style subrule naming who
    chooses for an *exile* the way discard's own explicit text does for a
    discard - this reads the choice off CR 608.2d's general rule instead,
    the same "the player announces these [choices] while applying the
    effect" that already backs every other CR 608.2d choice in this file.
    `player` is always the one the *sentence's own subject* names (the
    targeted player, or CR 607.1's "that player" anaphora back to a
    triggered ability's own condition) - never the resolving spell's or
    ability's controller, exactly the distinction `_discard_cards` already
    keeps for a discard aimed at someone else.

    A graveyard shorter than `count` (or, with `predicate`, a matching-card
    pool shorter than `count`) is not a violation - CR 609.3, "if an effect
    attempts to do something impossible, it does only as much as possible":
    every card (matching, if narrowed) goes, the same floor `_discard_cards`
    already applies to a short hand.
    """
    pool = [card for card in player.graveyard if predicate is None or predicate(card)]
    needed = min(count, len(pool))
    if needed <= 0:
        game.record_count(0)
        return []
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=f"exile {needed} card(s) from your graveyard",
            source=source,
            amount=needed,
            cards=tuple(state.id for state in pool),
            source_id=source_id,
            exact=True,
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in pool}
    exiled = game.exile_cards([by_id[card_id] for card_id in chosen_ids])
    game.record_count(len(exiled))
    return exiled


def regenerate_ability_targets(game: "Game", stack_object: "StackObject") -> None:
    """Create a CR 701.19a regeneration shield on each permanent this still
    legally targets - Asceticism's `{1}{G}`, Welding Jar's sacrifice ability.

    `Game.regenerate` is the whole of it. CR 701.19c: "Neither activating an
    ability that creates a regeneration shield nor casting a spell that
    creates a regeneration shield is the same as regenerating a permanent" -
    the tapping, the damage removal and the removal from combat all happen
    when the shield is *spent*, in `machines/replacement._regeneration_
    effects`, and never here.
    """
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState):
            game.regenerate(target)


#: The Darkness Crystal: "Put target creature card exiled with The Darkness
#: Crystal onto the battlefield tapped under your control with two additional
#: +1/+1 counters on it." `machines/targeting.py`'s `TargetRequirement.
#: exiled_with_source` is what makes "target ... card exiled with `<name>`" a
#: real, checked target (CR 115.1) rather than a definite reference like
#: Ugin's Labyrinth's "the exiled card" - this parser only has to read what
#: happens once a legal one is chosen.
_PUT_EXILED_TARGET_ONTO_BATTLEFIELD_RE = re.compile(
    r"^put (?P<phrase>target .+?) onto the battlefield(?P<tapped> tapped)? "
    rf"under your control(?: with (?P<n>{COUNT}) additional (?P<kind>\+1/\+1|-1/-1|[a-z]+) "
    r"counters? on it)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_put_exiled_target_onto_battlefield_clause(text: str) -> AbilityEffect | None:
    """`_PUT_EXILED_TARGET_ONTO_BATTLEFIELD_RE`'s shape.

    CR 122.6: counters an effect adds once a permanent is already on the
    battlefield are a distinct event from CR 614.12's "enters with N
    counters" replacement - added here with `Game.add_counters` after `Game.
    put_onto_battlefield` has already run, the same order `enter_the_
    battlefield`'s own docstring describes for that different case.
    """
    match = _PUT_EXILED_TARGET_ONTO_BATTLEFIELD_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False, battlefield_only=False):
        return None
    tapped = match.group("tapped") is not None
    amount = parse_count(match.group("n")) if match.group("n") else None
    kind = _counter_kind(match.group("kind")) if match.group("kind") else None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        controller = game.controller_of(ability).username
        game.put_onto_battlefield(target, controller, tapped=tapped)
        if amount and kind is not None:
            game.add_counters(target, kind, amount)

    return effect


# --------------------------------------------------------------------------
# "Whenever a player casts a spell from their hand, that player exiles it
# [, ...]" - Knowledge Pool and Possibility Storm's shared opening clause.
# --------------------------------------------------------------------------

#: Knowledge Pool: "Whenever a player casts a spell from their hand, that
#: player exiles it. If the player does, they may cast a spell from among
#: other cards exiled with this artifact without paying its mana cost."
#: Possibility Storm: "Whenever a player casts a spell from their hand, that
#: player exiles it, then exiles cards from the top of their library until
#: they exile a card that shares a card type with it. That player may cast
#: that card without paying its mana cost. Then they put all cards exiled
#: with this enchantment on the bottom of their library in a random order."
#: Both confirmed with `resolve_cards` in the session that wrote this - the
#: opening clause is byte-identical, matched here on the *whole*, unsplit
#: `effect_text` (`TriggeredAbility.effect`, everything after "a player casts
#: a spell from their hand,") for the same reason `_ability_effect_or_notice`'s
#: docstring gives four other times: Knowledge Pool's second sentence, "If
#: the player does, ...", is CR 118.12 anaphora back to the first, and
#: `_prepare_effect_clauses` would cut the two apart at the period before
#: either parser saw the dependency between them.
_CAST_FROM_HAND_THEN_EXILE_RE = re.compile(
    r"^that player exiles it(?P<tail>.*)$", re.IGNORECASE | re.DOTALL
)

#: Knowledge Pool's own tail. "This `<type>`" is CR 201.4's plain self-
#: reference by printed type (artifact, here) rather than a name - Possibility
#: Storm prints the identical shape with "this enchantment", which is why the
#: word is a wildcard rather than the literal "artifact".
_KNOWLEDGE_POOL_TAIL_RE = re.compile(
    r"^\.\s*if the player does,\s*they may cast a spell from among other cards exiled with "
    r"this \w+ without paying its mana cost\.?$",
    re.IGNORECASE,
)

#: Possibility Storm's own tail - a genuinely different template from
#: Knowledge Pool's past the shared opening: dig from the top of the library
#: until a card sharing a type with the exiled spell turns up (CR 701.17a's
#: "look at cards from the top of a library" shape, bounded by a type match
#: rather than a count), offer that one card (not a choice among several),
#: then bottom everything this ability exiled that was not cast.
_POSSIBILITY_STORM_TAIL_RE = re.compile(
    r"^,\s*then exiles cards from the top of (?:their|his or her) library until they exile a "
    r"card that shares a card type with it\.\s*"
    r"that player may cast that card without paying its mana cost\.\s*"
    r"then they put all cards exiled with this \w+ on the bottom of (?:their|his or her) "
    r"library in a random order\.?$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Reading a permanent's own CR 607.2a pile: "cards exiled with this <object>"
# --------------------------------------------------------------------------

#: "you may cast `<spell>` from among cards [you own] exiled with this
#: `<object>`[ without paying its mana cost]" - a resolution-time cast (CR
#: 608.2g) out of the source's own linked pile (CR 607.2a). Boiling Rock
#: Rioter's attack trigger ("you may cast an Ally spell from among cards you
#: own exiled with this creature" - the mana cost is paid, only the timing is
#: granted) and Kaho, Minamo Historian's "{X}, {T}: You may cast a spell with
#: mana value X from among cards exiled with Kaho without paying its mana
#: cost." (the name normalised to "this permanent"). The spell description is
#: CR 205's type/subtype words (`_quality_matcher`), optionally bounded by an
#: exact mana value - "X" is the activation's announced X (CR 107.3a).
_CAST_FROM_LINKED_EXILE_RE = re.compile(
    r"^you may cast (?:an? (?:(?P<quality>.+?) )?spell(?: with mana value (?P<mv>\d+|x))? "
    r"from among cards (?P<own>you own )?|(?P<card>a card) )exiled with (?:this \w+|it)"
    r"(?P<free> without paying its mana cost)?\.?$",
    re.IGNORECASE,
)
#: Krang & Shredder's Disappear prints the singular "you may cast a card
#: exiled with Krang & Shredder without paying its mana cost." - the same
#: resolution-time cast out of the linked pile (the card's own ruling: "You
#: cast the card while Krang & Shredder's last ability is resolving and still
#: on the stack. ... Timing restrictions based on its types are ignored."),
#: read by the `card` branch of the pattern above.

#: "until end of turn, you may play a card exiled with `<this>`." - Raphael,
#: Most Attitude's attack trigger. CR 601.1a's "play" (a land drop or a
#: cast) out of CR 607.2a's linked pile, for the rest of the turn (CR 514.2),
#: through the priority system rather than during the resolution - and "a
#: card", so the first card played ends the rest (`PlayPermission.choice_
#: group`, the same "one of those cards" Nashi's grant uses).
_PLAY_A_CARD_EXILED_WITH_RE = re.compile(
    r"^until end of turn, you may play (?P<one>a card|cards) exiled with (?:this \w+|it)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s3", for_spell=FORWARD)
def _parse_play_a_card_exiled_with_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_PLAY_A_CARD_EXILED_WITH_RE`: a `PlayPermission` (CR 601.3) for every
    face-up card in the source's own pile (`_linked_pile`, that incarnation
    of it - CR 400.7), timing untouched (the ruling: "you must still follow
    any timing restrictions and permissions, including those based on the
    card's type"). Ability-only: a spell has no linked pile."""
    if for_spell:
        return None
    match = _PLAY_A_CARD_EXILED_WITH_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    one_of = match.group("one").lower() == "a card"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        controller = game.controller_of(stack_object).username
        for card in _linked_pile(game, stack_object):
            if card.zone is not Zone.EXILE or not card.face_up:
                continue
            game.grant_play_permission(
                card,
                controller,
                action=PlayAction.PLAY,
                pays_mana_cost=True,
                source_name=stack_object.source_name,
                rule="CR 601.3, CR 607.2a",
                zone=Zone.EXILE,
                until_end_of_turn=True,
                choice_group=stack_object.id if one_of else None,
            )

    return effect


#: Pyxis of Pandemonium's "Each player turns face up all cards they own exiled
#: with this artifact, then puts all permanent cards among them onto the
#: battlefield." CR 406.3's face-down pile, CR 607.2a-linked to the object,
#: turned over by its owner and its permanent cards (CR 110.4a) put onto the
#: battlefield under that same player's control (CR 110.2a).
_TURN_LINKED_FACE_UP_THEN_PUT_PERMANENTS_RE = re.compile(
    r"^each player turns face up all cards they own exiled with this \w+, "
    r"then puts all permanent cards among them onto the battlefield\.?$",
    re.IGNORECASE,
)

#: CR 110.4a: "an artifact, battle, creature, enchantment, land, or
#: planeswalker card."
_LINKED_PERMANENT_CARD_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)


#: "search your library for up to `<n>` `<quality>` cards, exile them, then
#: shuffle" - Kaho, Minamo Historian's enters trigger, the exiling half of its
#: linked pair (CR 607.2a; `link_cards_exiled_during` links what it exiles).
#: CR 701.23b: a search for cards with a stated quality may find fewer than
#: asked, down to none - "up to" says so outright. Ugin, Eye of the Storms'
#: "any number of" form, which prints a permission after it, is read with that
#: permission by `_parse_exile_then_play_permission_clauses` instead.
_SEARCH_UP_TO_AND_EXILE_RE = re.compile(
    rf"^search your library for up to (?P<n>{COUNT}) (?P<quality>.+?) cards?, "
    r"exile (?:it|them), then shuffle\.?$",
    re.IGNORECASE,
)


#: "Put a card exiled with this `<object>` into its owner's hand." - Roads
#: Go Ever, Ever On's own Saga chapters II and III (CR 714.2c: a Saga chapter
#: ability with an identical instruction can print on more than one chapter
#: line at once, "II, III —", which `parse_abilities` already turns into two
#: separate `TriggeredAbility`s of the same text, so this reader closes both
#: without needing to know that). CR 608.2d makes the pick mandatory only
#: when the linked pile actually has a card in it - with none left (both
#: already returned, or nothing was ever exiled), there is nothing to ask.
_PUT_CARD_EXILED_WITH_IT_INTO_OWNERS_HAND_RE = re.compile(
    r"^put an? card exiled with this \w+ into its owner'?s hand\.?$", re.IGNORECASE
)


def _put_card_exiled_with_it_into_owners_hand_effect(game: "Game", ability: AbilityOnStack) -> None:
    candidates = [state for state in _linked_pile(game, ability) if state.zone is Zone.EXILE]
    if not candidates:
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=ability.controller,
            prompt="put a card exiled with this into its owner's hand",
            source=ability.source_name,
            source_id=source_id_of(ability),
            amount=1,
            cards=tuple(state.id for state in candidates),
        )
    )
    by_id = {state.id: state for state in candidates}
    chosen = by_id.get(chosen_ids[0]) if chosen_ids else None
    # CR 400.1: exile is a shared zone, never a player's own - `Player.move`
    # refuses to lift a card out of one (`refuse_shared_zone`). `Game.exile`
    # is the list to remove it from instead, the same two-step
    # `_parse_cast_from_hand_then_exile_clause`'s own Possibility Storm
    # bottoming already uses to leave exile for a player zone.
    if chosen is not None and chosen in game.exile:
        game.exile.remove(chosen)
        game.player(chosen.owner).add(chosen, Zone.HAND)


@ABILITY_TEXT.rung("s9")
def _parse_linked_exile_clause(text: str) -> AbilityEffect | None:
    """`_CAST_FROM_LINKED_EXILE_RE`, `_TURN_LINKED_FACE_UP_THEN_PUT_
    PERMANENTS_RE` or `_SEARCH_UP_TO_AND_EXILE_RE`, read off the whole
    ability text."""
    stripped = " ".join(text.split())
    match = _CAST_FROM_LINKED_EXILE_RE.fullmatch(stripped)
    if match is not None:
        return _cast_from_linked_exile_effect(match)
    if _TURN_LINKED_FACE_UP_THEN_PUT_PERMANENTS_RE.fullmatch(stripped):
        return _turn_linked_face_up_then_put_permanents
    match = _SEARCH_UP_TO_AND_EXILE_RE.fullmatch(stripped)
    if match is not None:
        return _search_up_to_and_exile_effect(match)
    if _PUT_CARD_EXILED_WITH_IT_INTO_OWNERS_HAND_RE.fullmatch(stripped):
        return _put_card_exiled_with_it_into_owners_hand_effect
    match = _EXILE_ONE_OF_THOSE_CREATURES_RE.fullmatch(stripped)
    if match is not None:
        return _exile_one_of_those_creatures_effect(optional=match.group("may") is not None)
    return None


#: "you may exile one of those creatures" - the tail of a blocks / becomes
#: blocked trigger over "one or more creatures" (Godsend): the creatures are
#: the other half of the blocking pairs (CR 509.3e).
_EXILE_ONE_OF_THOSE_CREATURES_RE = re.compile(
    r"(?P<may>you may )?exile one of those creatures\.?", re.IGNORECASE
)


def _those_creatures_of_a_block_trigger(game: "Game", ability: AbilityOnStack) -> list[CardState]:
    """ "Those creatures" of a trigger on a creature that blocks or becomes
    blocked by one or more creatures (CR 509.3e): the attackers the creature
    blocks when it is the blocker, the creatures blocking it when it is the
    attacker - the creature being the ability's own source or the permanent
    that source is attached to (CR 301.5a)."""
    event = ability.event
    if event is None or event.event is not TriggerEvent.BLOCKS:
        return []
    source = ability.source_or_last_known(game)
    pair = {event.subject_id, event.related_id}
    creature_id = (
        source.id
        if source.id in pair
        else source.attached_to
        if source.attached_to in pair
        else None
    )
    if creature_id is None:
        return []
    if creature_id == event.subject_id:
        ids = [a.attacker_id for a in game.combat.attacks if creature_id in a.blockers]
    else:
        attack = game.combat.attack_by(creature_id)
        ids = list(attack.blockers) if attack is not None else []
    found = (game.find_by_id(card_id) for card_id in ids)
    return [card for card in found if isinstance(card, CardState) and card.zone is Zone.BATTLEFIELD]


def _exile_one_of_those_creatures_effect(*, optional: bool) -> AbilityEffect:
    def effect(game: "Game", ability: AbilityOnStack) -> None:
        candidates = _those_creatures_of_a_block_trigger(game, ability)
        if not candidates:
            return
        controller = game.controller_of(ability).username
        if optional and not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=controller,
                prompt="exile one of those creatures",
                source=ability.source_name,
                source_id=source_id_of(ability),
                cards=tuple(card.id for card in candidates),
            )
        ):
            return
        chosen = candidates[0]
        if len(candidates) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt="choose one of those creatures to exile",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(card.id for card in candidates),
                )
            )
            assert isinstance(answer, tuple)
            chosen = next(card for card in candidates if card.id == answer[0])
        game.exile_permanent(chosen)

    return effect


def _cast_from_linked_exile_effect(match: re.Match[str]) -> AbilityEffect | None:
    """`_CAST_FROM_LINKED_EXILE_RE`'s cast.

    CR 608.2d: the "may" is offered only when a legal choice exists - a card
    in the pile that fits the description, that the caster owns when the
    text says "you own", is face up (CR 406.3b: a face-down card can be cast
    only if its caster may look at it, and nothing here lets them), and that
    `Game.can_cast_during_resolution` finds castable. Then `DecisionKind.
    CHOOSE_CARDS` for which one, the order Knowledge Pool's own free cast
    already uses, and `Game.cast_during_resolution` casts it (CR 608.2g) -
    paying its mana cost unless the text waives it."""
    quality = match.group("quality")
    if quality is not None and not _card_description_is_readable(quality):
        return None
    matches_quality = _quality_matcher(quality) if quality is not None else None
    mv_word = match.group("mv")
    a_card = match.group("card") is not None
    own = match.group("own") is not None
    free = match.group("free") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        caster = game.controller_of(ability).username
        mana_value: int | None = None
        if mv_word is not None:
            mana_value = int(mv_word) if mv_word.isdigit() else (ability.x_value or 0)
        candidates = [
            card
            for card in _linked_pile(game, ability)
            if card.face_up
            and not card.card.is_land
            and (not own or card.owner == caster)
            and (matches_quality is None or matches_quality(card))
            and (mana_value is None or (card.card.cmc or 0) == mana_value)
            and game.can_cast_during_resolution(card, caster)
        ]
        described = (
            "a card"
            if a_card
            else "a spell"
            if quality is None
            else with_indefinite_article(f"{quality} spell")
        )
        cost_words = " without paying its mana cost" if free else ""
        taken = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=caster,
                prompt=(
                    f"cast {described} exiled with {ability.source_name}{cost_words}"
                    if a_card
                    else f"cast {described} from among cards exiled with {ability.source_name}"
                    f"{cost_words}"
                ),
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=bool(candidates),
                cards=tuple(card.id for card in candidates),
            )
        )
        if not taken:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=caster,
                prompt=f"choose a card to cast{cost_words}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(card.id for card in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        chosen = {card.id: card for card in candidates}[chosen_ids[0]]
        game.cast_during_resolution(
            chosen,
            caster,
            source_name=ability.source_name,
            rule="CR 608.2g",
            pays_mana_cost=not free,
        )

    return effect


def _turn_linked_face_up_then_put_permanents(game: "Game", ability: AbilityOnStack) -> None:
    """`_TURN_LINKED_FACE_UP_THEN_PUT_PERMANENTS_RE`'s effect.

    Each player, in APNAP order (CR 101.4), turns face up the cards they own
    in the pile; then each puts the permanent cards among their own onto the
    battlefield - CR 110.2a puts each under the player who put it there, its
    owner. Cards that are not permanent cards stay in exile, face up now."""
    pile = _linked_pile(game, ability)
    players = _players_in_apnap_order(game)
    for player in players:
        for card in pile:
            if card.owner == player.username and card.zone is Zone.EXILE:
                card.face_up = True
    for player in players:
        for card in pile:
            if (
                card.owner == player.username
                and card.zone is Zone.EXILE
                and _LINKED_PERMANENT_CARD_TYPES.intersection(card.types)
            ):
                game.put_onto_battlefield(card, player.username)


def _exile_cast_spell_or_none(
    game: "Game", ability: AbilityOnStack
) -> tuple[CardState, str] | None:
    """The shared "that player exiles it" half of both effects below.

    `None` when CR 118.12's mandatory action could not even be started - the
    cast spell named by `ability.event.subject_id` is no longer on the stack,
    because a second copy of this same permanent's own trigger already
    exiled it (two Knowledge Pools: the ability that resolves *second* finds
    nothing left to exile) or because the spell was countered in response
    while this trigger sat above it. Either way, CR 118.12's "if the player
    does" (Knowledge Pool) and Possibility Storm's own unconditional
    anaphora both read false in that case - the caller does nothing further,
    matching `docs/scenario-tests.md`'s own two-Pools and countered-in-
    response cases.

    Returns the exiled spell and **`GameEvent.player`** - who cast it, and
    therefore who does the exiling and gets the free cast (CR 602.2b's
    controller of the *triggered ability* has nothing to do with this: the
    condition is "a player casts a spell", not "you cast a spell", so this
    fires for either seat, and the ability's own `controller` is Knowledge
    Pool's controller, not the caster). Using `ability.controller` here is
    the trap: it would hand the Pool's controller a free spell every time an
    opponent cast something.
    """
    event = ability.event
    if event is None or event.subject_id is None or event.player is None:
        return None
    spell = game.find_by_id(event.subject_id)
    if not isinstance(spell, CardState) or spell not in game.stack:
        return None
    game.exile_from_stack(spell)
    return spell, event.player


def _knowledge_pool_free_cast_effect(game: "Game", ability: AbilityOnStack) -> None:
    """Knowledge Pool's second ability, once `_parse_cast_from_hand_then_
    exile_clause` has matched `_KNOWLEDGE_POOL_TAIL_RE`.

    The exiled spell is linked to the permanent (CR 607.2a) exactly the way
    `_parse_imprint_clause`'s hand-exile shape already links its own choice -
    self-linked, per CR 607.1c, since this same ability is what a *later*
    trigger reads to find it again. `Game.cards_imprinted_on` is CR 607.3's
    plural: every card this permanent has ever exiled this way, across every
    trigger, not just this one - "other cards exiled with this artifact"
    (excluding, by id, only the card *this* trigger just exiled, never a
    same-named copy exiled earlier).

    The choice follows `_parse_imprint_clause`'s own established order
    (`docs/engine-coverage.md`'s Imprint row): `DecisionKind.MAY` with
    `affirmative_is_legal` true only when a legal candidate exists (CR
    608.2d), then `DecisionKind.CHOOSE_CARDS` for which one. No new
    `DecisionKind` - both already exist and are answered everywhere a client
    talks to this engine.

    `Game.can_cast_during_resolution` filters the candidate list *before*
    the MAY is even asked - a card with no legal target (CR 601.2c), too few
    legal modes (CR 700.2a), an unpayable mandatory cost (CR 118.3) or a CR
    611.1 prohibition is not a legal choice (CR 608.2d), so it is never
    offered as one. The cast is `Game.cast_during_resolution`.
    """
    result = _exile_cast_spell_or_none(game, ability)
    if result is None:
        return
    spell, exiler = result
    source_id = ability.source_id
    if source_id is None:
        return
    spell.exile_annotation = ExileAnnotation(
        marker=ExileMarker.IMPRINTED, owner=spell.owner, linked_permanent_id=source_id
    )
    candidates = [
        card
        for card in game.cards_imprinted_on(source_id)
        if card.id != spell.id and game.can_cast_during_resolution(card, exiler)
    ]
    decision = Decision(
        kind=DecisionKind.MAY,
        player=exiler,
        prompt=(
            f"cast a spell from among other cards exiled with {ability.source_name} "
            "without paying its mana cost"
        ),
        source=ability.source_name,
        source_id=source_id_of(ability),
        affirmative_is_legal=bool(candidates),
        cards=tuple(card.id for card in candidates),
    )
    if not game.ask(decision):
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=exiler,
            prompt="choose a card to cast without paying its mana cost",
            source=ability.source_name,
            source_id=source_id_of(ability),
            amount=1,
            cards=tuple(card.id for card in candidates),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {card.id: card for card in candidates}
    chosen = by_id[chosen_ids[0]]
    game.cast_during_resolution(chosen, exiler, source_name=ability.source_name, rule="CR 608.2g")


def _possibility_storm_effect(game: "Game", ability: AbilityOnStack) -> None:
    """Possibility Storm, once `_parse_cast_from_hand_then_exile_clause` has
    matched `_POSSIBILITY_STORM_TAIL_RE`.

    Structurally `machines.keywords.cascade` with a different stopping
    condition and a different resting place for the exiled spell itself:
    dig from the top of the library, sharing a card type with the just-
    exiled spell rather than a lesser mana value, offer the one hit found (not
    a choice among several - CR 608.2d's plain "may", the same shape
    `_parse_hideaway_play_clause` uses for its own single fixed card), then
    bottom **everything this ability exiled** that was not cast - the exiled
    spell itself included, since it is "exiled with this enchantment" too
    (CR 607.2a) and this card names no other resting place for it, unlike
    Knowledge Pool's silence (which is exactly why Knowledge Pool's own
    unused cards stay in exile forever and this card's do not).

    `Game.can_cast_during_resolution` gates the "may cast" the same way it gates
    Knowledge Pool's menu: an uncastable hit (CR 611.1's flat prohibitions,
    or CR 601.2c's no-legal-target) is never offered the choice at all.

    The shuffle is `Random`, seeded off `Game.shuffle_seed`/`shuffles_
    performed` the same reproducible way `machines.keywords.cascade` and
    every other "bottom in a random order" clause in this module already
    are, not a bare `Random()` a scenario could not pin down.
    """
    result = _exile_cast_spell_or_none(game, ability)
    if result is None:
        return
    spell, exiler = result
    source_id = ability.source_id
    if source_id is None:
        return
    spell.exile_annotation = ExileAnnotation(
        marker=ExileMarker.IMPRINTED, owner=spell.owner, linked_permanent_id=source_id
    )
    owner = game.player(exiler)
    spell_types = set(spell.types)
    dug: list[CardState] = []
    hit: CardState | None = None
    while owner.library:
        state = owner.library[0]
        # CR 400.1's one shared exile zone, through CR 406.2's door - not
        # `owner.move(state, Zone.EXILE)` plus an append, which listed each
        # dug card in the real exile zone *and* in a pile of its owner's own.
        game.exile_cards([state])
        state.exile_annotation = ExileAnnotation(
            marker=ExileMarker.IMPRINTED, owner=state.owner, linked_permanent_id=source_id
        )
        dug.append(state)
        if set(state.types) & spell_types:
            hit = state
            break

    cast_hit = False
    if hit is not None and game.can_cast_during_resolution(hit, exiler):
        decision = Decision(
            kind=DecisionKind.MAY,
            player=exiler,
            prompt=with_board_priced_cost(
                game, f"cast {hit.name} without paying its mana cost", hit, exiler
            ),
            source=ability.source_name,
            source_id=source_id_of(ability),
            affirmative_is_legal=True,
            cards=(hit.id,),
        )
        if game.ask(decision):
            cast_hit = (
                game.cast_during_resolution(
                    hit, exiler, source_name=ability.source_name, rule="CR 608.2g"
                )
                is not None
            )

    bottomed = [spell, *(state for state in dug if not (cast_hit and state is hit))]
    rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:possibility-storm")  # noqa: S311
    rng.shuffle(bottomed)
    game.shuffles_performed += 1
    for state in bottomed:
        if state in game.exile:
            game.exile.remove(state)
            owner.add(state, Zone.LIBRARY)  # the bottom of the library


@ABILITY_TEXT.rung("s9")
def _parse_cast_from_hand_then_exile_clause(text: str) -> AbilityEffect | None:
    """Knowledge Pool's and Possibility Storm's shared opening clause - see
    the block comment above `_CAST_FROM_HAND_THEN_EXILE_RE` for the two
    printings and why this reads the whole, unsplit text.

    Tried by `_ability_effect_or_notice` ahead of `_prepare_effect_clauses`'
    per-clause split, joining four existing precedents that whole docstring
    already lists for the same reason: `_parse_conditional_sacrifice_clause`'s
    "you may sacrifice ... If you do, ..." (CR 118.12), `_parse_mana_adding_
    trigger`'s "adds an additional <mana>", `parse_casting_rule_clause`'s
    "instant and sorcery spells ... cost {1} less", and `_parse_choose_name_
    search_and_exile_whole_text` - each an instruction `_CLAUSE_SEPARATOR`'s
    bare-comma/period/"and" splitting would otherwise cut apart before a
    per-clause parser ever saw the dependency between the halves.

    A recognised head with an unread tail refuses the *whole* ability
    (`CastFromHandExileNotice`) rather than exiling the spell and dropping
    the tail - one paragraph is one ability (`docs/scenario-tests.md`), and a
    half-applied "exiled it but nothing else happened" is a wrong board that
    looks like a legal one.
    """
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _CAST_FROM_HAND_THEN_EXILE_RE.match(whole)
    if match is None:
        return None
    tail = match.group("tail")
    if _KNOWLEDGE_POOL_TAIL_RE.match(tail) is not None:
        return _knowledge_pool_free_cast_effect
    if _POSSIBILITY_STORM_TAIL_RE.match(tail) is not None:
        return _possibility_storm_effect

    def unread_tail_notice_only(game: "Game", ability: AbilityOnStack) -> None:
        game.cast_from_hand_exile_notices.append(
            CastFromHandExileNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=tail
            )
        )

    return _with_unparsed_remainder(unread_tail_notice_only, tail)


#: "You may cast this card for as long as it remains exiled." - Emrakul, the
#: Exigent Doom's own second sentence of the same ability, self-referential
#: ("this card") rather than `_PLAY_PERMISSION_RE`'s "it"/"that card" aimed
#: at something the effect just exiled: here the exiling already happened as
#: the activation's own *cost* ("Exile this card from your hand:"), so there
#: is no antecedent exile clause in the effect text to pair it with - only
#: CR 601.3's grant, on the source itself.
_SELF_CAST_WHILE_EXILED_RE = re.compile(
    r"^you may cast this (?:card|permanent) for as long as it remains exiled\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s35")
def _parse_self_cast_while_exiled_clause(text: str) -> AbilityEffect | None:
    """`_SELF_CAST_WHILE_EXILED_RE`'s shape.

    No `until_end_of_turn` and no `condition`: CR 601.3's "as long as it
    remains exiled" is not a turn-boxed duration and names no board
    condition to recheck, unlike Null Summoner's Threshold-gated sibling
    static (`_grant_cast_exiled_card_permission_from_sibling_static`) - the
    permission is simply live for as long as this exact exiled object (CR
    400.7) exists, which `PlayPermission.names` already keys on.
    """
    if _SELF_CAST_WHILE_EXILED_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        controller = game.controller_of(ability)
        game.grant_play_permission(
            source,
            controller.username,
            action=PlayAction.CAST,
            pays_mana_cost=True,
            source_name=source.name,
            rule="CR 601.3",
            zone=source.zone,
            until_end_of_turn=False,
        )

    return effect


#: "Destroy target X and target Y." (Fumarole's "Destroy target creature and
#: target land.") - two independent, simultaneously-chosen targets in one
#: sentence, not two clauses. `_CLAUSE_SEPARATOR`'s bare-"and" split cuts this
#: into "Destroy target creature" and "target land" - a fragment with no verb
#: nothing here reads - the same "and" trap `_parse_x_damage_divided_and_
#: doubled_clause` and `_parse_look_top_n_may_battlefield_creature_bonus_
#: clause` already route around by reading their own sentence whole, ahead of
#: `split_effect_clauses`. `machines/targeting.py`'s own `profile_for_text`
#: already reads "target creature and target land" as two `TargetRequirement`s
#: (verified this session), so once the whole phrase reaches
#: `_targets_understood` intact, `destroy_ability_targets` - already built to
#: destroy *every* target a spell or ability still legally has, not just the
#: first - needs nothing new.
_DESTROY_TWO_TARGETS_RE = re.compile(
    r"^destroy (?P<phrase>target [^.]+? and target [^.]+?)\.?$", re.IGNORECASE
)


@SPELL_TEXT.rung("s18")
def _parse_destroy_two_targets_clause(effect_text: str) -> Effect | None:
    """`_DESTROY_TWO_TARGETS_RE`'s shape, or `None` if this is not it.

    `_targets_understood` deliberately refuses a phrase with more than one
    "target" requirement (its own docstring: "two 'target' words is two
    requirements, not this shape") - right for every single-target verb
    clause elsewhere in this file, wrong here, where two requirements is
    exactly the point. This repeats `_targets_understood`'s own per-
    requirement checks (understood, no unenforced "if", battlefield-only, a
    plain mandatory single target, not a player) across *both*
    requirements instead of refusing on sight of the second one.
    """
    whole = _strip_non_effect_preamble(effect_text).strip()
    match = _DESTROY_TWO_TARGETS_RE.fullmatch(whole)
    if match is None:
        return None
    if not _two_battlefield_targets_understood(match.group("phrase"), up_to_one=False):
        return None
    return destroy_ability_targets  # type: ignore[return-value]


#: Shredder's Technique's own body: "Destroy target creature or enchantment.
#: If an enchantment was destroyed this way, you lose 2 life." CR 608.2c's
#: "this way" rider on the base clause's *own* single target - not one of
#: `numbers.Half`'s counted "N `<verb>` this way" amounts (Radiant Lotus's
#: own "for each artifact sacrificed this way"), which count across a list;
#: here there is exactly one target, and "this way" asks only whether *it*
#: had the named card type at the moment it was destroyed. Read generally on
#: the type word, so a future "Destroy target artifact or creature. If an
#: artifact was destroyed this way, ..." reaches the identical reader.
_DESTROY_TARGET_THEN_RIDER_IF_TYPE_DESTROYED_RE = re.compile(
    r"^destroy target (?P<phrase>.+?)\.\s*"
    r"if an? (?P<type>[a-z]+) was destroyed this way,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s7", for_spell=True)
def _parse_destroy_target_then_rider_if_type_destroyed_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DESTROY_TARGET_THEN_RIDER_IF_TYPE_DESTROYED_RE`'s shape, or `None`.

    The base "destroy target `<phrase>`." is read whole through the ordinary
    `_parse_targeted_clause` (CR 608.2b's legality recheck, indestructible,
    regeneration and all its other nuances included, unrepeated here), and
    the rider fires only afterward, off the target's own computed
    characteristics (`Game.characteristics_of`) captured the instant before
    that clause runs - CR 400.7: once destroyed it is a new object in the
    graveyard with no memory of what it was.
    """
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _DESTROY_TARGET_THEN_RIDER_IF_TYPE_DESTROYED_RE.fullmatch(whole)
    if match is None:
        return None
    base = _parse_targeted_clause(f"destroy target {match.group('phrase')}.", for_spell=for_spell)
    if base is None:
        return None
    try:
        wanted_type = Type(match.group("type").lower())
    except ValueError:
        return None
    consequence_text = match.group("consequence").strip()
    consequence = (
        parse_player_effect_for_spell(consequence_text)
        if for_spell
        else parse_mixed_effect(consequence_text)
    )
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        # CR 400.7: captured before the move, since a destroyed card is a new
        # object in the graveyard with no memory of what it was.
        pre_move = {
            target.id: (target, game.characteristics_of(target).types)
            for target in targets
            if target.zone is Zone.BATTLEFIELD
        }
        base(game, stack_object)
        destroyed_a_wanted_type = any(
            wanted_type in types
            for target, types in pre_move.values()
            if target.zone is not Zone.BATTLEFIELD  # actually moved - CR 701.8a
        )
        if destroyed_a_wanted_type:
            consequence(game, stack_object)

    return effect


#: "Exile all but the bottom card of each opponent's library." (Jace,
#: Reality Sculptor's own `0`) and "Exile all but the bottom card of target
#: player's library." (Nicol Bolas, the Arisen's `-12`, off-set) - the same
#: instruction over two different subjects, an unscoped group ("each
#: opponent's") and CR 115.1's ordinary player target ("target player's"),
#: the identical split `_EACH_SACRIFICES_OF_THEIR_CHOICE_RE`'s own `who`
#: reads between "opponent" and "player". `<n>` is optional (CR 107.3f's
#: bare "the bottom card" prints no number at all) and defaults to one.
#:
#: The same instruction also comes with the players as the sentence's own
#: subject - "each player exiles all but the bottom six cards of their
#: library face down" (Doomsday Excruciator) - which is every player, the
#: controller included, each on their own library ("their"). "Face down" is
#: CR 406.3's hidden exile: the cards can't be examined and (CR 406.3a) have
#: no characteristics.
_EXILE_ALL_BUT_BOTTOM_OF_LIBRARY_RE = re.compile(
    r"^(?:(?P<subject>each player|each opponent) exiles?|exile) "
    rf"all but the bottom (?:{count_pattern('n')} )?cards? of "
    r"(?P<who>each opponent'?s|target player'?s|their|his or her) librar(?:y|ies)"
    r"(?P<face_down> face down)?\.?$",
    re.IGNORECASE,
)


def _parse_exile_all_but_bottom_of_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EXILE_ALL_BUT_BOTTOM_OF_LIBRARY_RE`'s shape.

    CR 609.3: a library holding `n` or fewer cards is left untouched - there
    is nothing above the bottom `n` to exile. Read off `player.library`
    (`CardState.zone_change_stamp`'s own bottom-is-last ordering, the same
    "library[0] is the top" convention every mill/look-at-top reader in this
    module already shares), and moved as one `Game.exile_cards` batch so
    CR 603.2c's "one event, however many cards" trigger shape is preserved.
    """
    match = _EXILE_ALL_BUT_BOTTOM_OF_LIBRARY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    n = parse_count(match.group("n")) if match.group("n") else 1
    if n is None or n < 0:
        return None
    who = match.group("who").lower()
    subject = (match.group("subject") or "").lower()
    # "their library" needs the "each player/opponent exiles" subject to name
    # whose, and a subject never pairs with a second, different owner.
    if bool(subject) != (who in ("their", "his or her")):
        return None
    targeted = who.startswith("target")
    everyone = subject == "each player"
    face_down = match.group("face_down") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if targeted:
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
        elif everyone:
            players = _players_in_apnap_order(game)
        else:
            controller = game.controller_of(stack_object).username
            players = [player for player in game.players_in_game if player.username != controller]
        for player in players:
            library = list(player.library)
            if len(library) <= n:
                continue
            exiled = game.exile_cards(library[: len(library) - n])
            if face_down:
                for card_state in exiled:
                    if card_state.zone is Zone.EXILE:
                        # CR 406.3/406.3a: hidden, no characteristics.
                        card_state.face_up = False

    return effect


#: "exile that many cards from the bottom of your library" (The Temporal
#: Anchor), "exile the top two cards of your library", "exile the bottom card
#: of your library": N cards off one end of the controller's own library (CR
#: 401.2 - the library's order is kept, and `library[0]` is the top). "that
#: many" is the count channel's number (`that_many`), read as it resolves.
_EXILE_FROM_OWN_LIBRARY_END_RE = re.compile(
    rf"^exile (?:the (?P<end>top|bottom) (?:card|{count_pattern('n')} cards) of your library"
    r"|(?P<that_many>that many) cards from the (?P<that_end>top|bottom) of your library)\.?$",
    re.IGNORECASE,
)


def _parse_exile_from_own_library_end_clause(clause: str) -> TargetedClause | None:
    """`_EXILE_FROM_OWN_LIBRARY_END_RE`'s shape: one `Game.exile_cards` batch
    (CR 603.2c's one event), however many the library still holds (CR 609.3:
    only what can be done is done)."""
    match = _EXILE_FROM_OWN_LIBRARY_END_RE.fullmatch(clause.strip())
    if match is None:
        return None
    carried = match.group("that_many") is not None
    bottom = (match.group("end") or match.group("that_end")).lower() == "bottom"
    n = parse_count(match.group("n")) if match.group("n") else 1
    if n is None or n < 0:
        return None
    stripped = clause.strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        count = n
        if carried:
            counted = _that_many_or_notice(
                game,
                stripped,
                source_id=stack_object.source_id,
                source_name=stack_object.source_name,
            )
            if counted is None:
                return
            count = counted
        if count <= 0:
            return
        library = list(game.controller_of(stack_object).library)
        chosen = library[-count:] if bottom else library[:count]
        if chosen:
            game.exile_cards(chosen)

    return effect  # type: ignore[return-value]


#: "exile target nonland permanent an opponent controls until this
#: enchantment leaves the battlefield" (Static Prison). Checked *ahead* of
#: `_EXILE_TARGET_RE` below: that pattern's own phrase is `.*target.+`, a
#: superset that would otherwise swallow the whole "until ... leaves the
#: battlefield" tail into its own restriction and have it refused by
#: `_TRAILING_DURATION_RE` (see that guard's own docstring) - correct for
#: every *other* trailing duration this wave still cannot reverse, but wrong
#: for this one specific shape, which now has a real reversal.
#:
#: **CR 610.2** (verified this session): "Some one-shot effects create a
#: delayed triggered ability, which instructs a player to do something later
#: in the game (usually at a specific time) rather than as the spell or
#: ability that's creating them doing it immediately." The architect's own
#: pointer, confirmed rather than assumed: the return is a *second one-shot
#: effect*, created now (CR 603.7a) and firing whenever the enchantment
#: actually leaves, not a `ContinuousEffects` duration this engine would have
#: to notice has "expired" - modelled with exactly the `DelayedTrigger`
#: machinery `machines/delayed.py` already built for warp and for earthbend's
#: own two-sibling "dies or is put into exile" shape, extended to the three
#: departure routes this pool's permanents can actually take (destroyed,
#: sacrificed - both `TriggerEvent.DIES` - exiled, or bounced to hand).
#:
#: The phrase used to require "target" as the very next word after "exile ",
#: so Prayer of Binding's real "exile up to one target nonland permanent an
#: opponent controls until this enchantment leaves the battlefield" (an "up
#: to" count ahead of the word "target") never matched at all - silent, per
#: the number sweep. `.*target.+?` is the same loose phrase shape
#: `_EXILE_TARGET_RE` already uses for the plain "exile target ..." family;
#: the count word itself is read by `_targets_understood(count_agnostic=
#: True)` below, not by this regex.
#:
#: "aura" joined the type alternation for Dimensional Exile's own "until this
#: Aura leaves the battlefield" (TMT): the CR 610.3 "until" shape this whole
#: regex reads is unchanged, but an Aura (CR 303.4's enchantment subtype)
#: names itself by that subtype rather than by the card type "enchantment" -
#: the identical templating gap `_EXILE_TARGETS_UNTIL_LEAVES_THEN_COUNTERS_RE`
#: below never had, since no pool card yet paired that shape with an Aura.
_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE = re.compile(
    r"^exile (?P<phrase>.*target.+?) until this "
    r"(?:permanent|enchantment|artifact|creature|planeswalker|aura) leaves the battlefield$",
    re.IGNORECASE,
)


def _parse_exile_until_leaves_battlefield_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): nothing in the pool prints this
    shape on a spell, and the "this `<type>`" pronoun needs a live source
    object on the battlefield to watch (`ability.source(game)`), which only
    an ability - never a spell resolving itself off the stack - carries.

    `count_agnostic=True`, the same reading `_targets_understood`'s own
    docstring already gives Mindbreak Trap's "exile any number of target
    spells": Prayer of Binding and Touch the Spirit Realm both print "exile
    up to one target ..." here, CR 115.6's zero-or-one, not the exactly-one
    `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE` used to enforce alone. Every
    legal target is exiled and watched, the same "one departure watch per
    exiled card" shape `_parse_exile_targets_until_leaves_then_counters`
    (Lagrella, the Magpie) already uses for its own count-agnostic "any
    number of other target creatures" - "up to one" is not a fourth shape,
    only a narrower bound on the same one.
    """
    if for_spell:
        return None
    match = _EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return  # CR 608.2b/115.6: no (legal) target chosen; nothing to exile.
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return  # CR 610.3b: the source already left after this triggered; nothing moves.
        for target in targets:
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move; nothing to bring back later.
            _watch_for_departure_and_return_exiled_card(game, source, exiled, ability.controller)

    return effect


#: Lagrella, the Magpie's whole ability: "When Lagrella enters, exile any
#: number of other target creatures controlled by different players until
#: Lagrella leaves the battlefield. When an exiled card enters under your
#: control this way, put two +1/+1 counters on it."
#:
#: Read whole, ahead of `split_effect_clauses`, because the second sentence is
#: not an instruction to carry out now at all - it is a **delayed** triggered
#: ability (CR 603.7a: "delayed triggered abilities are created during the
#: resolution of spells or abilities") whose subject is exactly the card the
#: first sentence exiled. Cut apart, neither half means anything on its own.
#:
#: The count is any number, so unlike `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE`
#: above every target is exiled, each with its own CR 610.3 return pair.
_EXILE_TARGETS_UNTIL_LEAVES_THEN_COUNTERS_RE = re.compile(
    r"^exile (?P<phrase>.+?) until this "
    r"(?:permanent|enchantment|artifact|creature|planeswalker|aura) leaves the battlefield\.\s*"
    r"when an exiled card enters under your control this way, "
    rf"put (?P<n>{COUNT}) (?P<kind>[+-]\d+/[+-]\d+|\w+) counters? on it\.?$",
    re.IGNORECASE,
)


def _watch_for_the_exiled_card_returning_and_add_counters(
    game: "Game",
    source: CardState,
    exiled: CardState,
    controller: str,
    kind: Counter | str,
    amount: int,
) -> None:
    """Lagrella's second sentence, as the delayed triggered ability it is.

    "When an exiled card enters under your control this way, put two +1/+1
    counters on it." CR 603.7a creates it here, as the exiling ability
    resolves; CR 603.7d/e make its source and controller Lagrella and
    Lagrella's controller, taken as that ability resolved; CR 603.7b spends it
    the first time it fires. A separate `DelayedTrigger` rather than something
    the return callback does inline, because it really is a separate ability:
    it goes on the stack when the card comes back (CR 603.3) and can be
    responded to there.

    "This way" is what `subject_id` carries - only the card this resolution
    exiled, not any card that happens to enter.
    """
    game.create_delayed_trigger(
        DelayedTrigger(
            text=(
                f"When {exiled.name} enters under {controller}'s control this way, put "
                f"{amount} {kind} counters on it."
            ),
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
            controller=controller,
            source_id=source.id,
            source_name=source.name,
            subject_id=exiled.id,
            expected_zone=Zone.BATTLEFIELD,
            effect=ReturnExiledCardAndAddCounters(counter_kind=kind, amount=amount),
        )
    )


@ABILITY_TEXT.rung("s14")
def _parse_exile_targets_until_leaves_then_counters(text: str) -> AbilityEffect | None:
    """Lagrella, the Magpie, read off her own printed text.

    CR 610.3: "Some one-shot effects cause an object to change zones 'until' a
    specified event occurs. A second one-shot effect is created immediately
    after the specified event. This second one-shot effect returns the object
    ..." - which is the departure watch
    `_watch_for_departure_and_return_exiled_card` already builds for Static
    Prison, run once per exiled card here because "any number of other target
    creatures" is a whole list rather than the single target that shape was
    written for.

    Panharmonicon doubling the *enters* ability doubles the exile and nothing
    else: each resolution makes its own delayed trigger, and a second
    resolution aimed at a creature the first one already exiled has no legal
    target left at all (CR 608.2b).
    """
    match = _EXILE_TARGETS_UNTIL_LEAVES_THEN_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    # CR 107.1c's "any number" is count-agnostic for exile the same way
    # `_targets_understood`'s own docstring says it is for Mindbreak Trap: the
    # verb repeats once per legal target and stops.
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    kind = _counter_kind(match.group("kind"))
    amount = parse_count(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return  # CR 113.7a: nothing left to watch leave the battlefield.
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        for target in targets:
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move.
            _watch_for_departure_and_return_exiled_card(game, source, exiled, ability.controller)
            _watch_for_the_exiled_card_returning_and_add_counters(
                game, source, exiled, ability.controller, kind, amount
            )

    return effect


#: "Regenerate this creature/permanent/artifact." - Ancient Silverback's
#: `{G}` ability, the same self-reference shape `_COUNTER_ON_SELF_RE` reads
#: (CR 201.5, CR 700.7), rather than a target at all (CR 115.1a: a permanent
#: naming itself is never targeting). Ability-only, like that shape - a spell
#: is never itself a permanent on the battlefield to regenerate.
_REGENERATE_SELF_RE = re.compile(
    r"^regenerate this (?:creature|permanent|artifact)\.?$", re.IGNORECASE
)


def _parse_regenerate_self_clause(clause: str) -> AbilityEffect | None:
    """`_REGENERATE_SELF_RE`'s shape - CR 701.19a's shield, on the ability's
    own source rather than on something it targets.
    """
    if _REGENERATE_SELF_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.regenerate(source)

    return effect


#: "This creature can't be regenerated this turn." (Knight of the Holy Nimbus's
#: `{2}` ability, which only the controller's opponents may activate) - the
#: source's own CR 701.19c grant, ending with the turn (CR 611.2a).
_SELF_CANT_BE_REGENERATED_RE = re.compile(
    r"^this (?:creature|permanent|artifact) can'?t be regenerated this turn\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s36")
def _regenerate_self_cant_be_regenerated_this_turn(text: str) -> AbilityEffect | None:
    """`_SELF_CANT_BE_REGENERATED_RE`'s shape: the grant line
    `replacement._regeneration_effects` and the static regeneration read off
    the computed characteristics."""
    if _SELF_CANT_BE_REGENERATED_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..replacement.model import CANT_BE_REGENERATED_LINE
        from .damage import _grant_line_until_end_of_turn

        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            _grant_line_until_end_of_turn(game, ability, [source], CANT_BE_REGENERATED_LINE)

    return effect


#: "Regenerate each creature you control." (Wail of the Nim's first mode,
#: Wrap in Vigor, Golgari Charm, Loxodon Hierarch) - CR 701.19a's shield on
#: every permanent of the group as the spell or ability resolves (CR 608.2h:
#: the group is fixed then; one entering later gets none). The group is a
#: CR 205.2a type list read off the computed board (`_parse_mass_type_
#: qualifier`) among the permanents the resolving controller controls.
_REGENERATE_EACH_YOU_CONTROL_RE = re.compile(
    r"^regenerate each (?P<group>[a-z ,]+?) you control\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_regenerate_each_you_control_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_REGENERATE_EACH_YOU_CONTROL_RE`'s shape; see the banner above."""
    stripped = " ".join(clause.split())
    if not stripped.lower().startswith("regenerate each "):
        return None
    match = _REGENERATE_EACH_YOU_CONTROL_RE.fullmatch(stripped)
    if match is None:
        return None
    qualifies = _parse_mass_type_qualifier(match.group("group"))
    if qualifies is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        group = [
            permanent
            for permanent in game.permanents_controlled_by(controller)
            if qualifies(game.characteristics_of(permanent))
        ]
        for permanent in group:
            game.regenerate(permanent)

    return effect


#: Skyclave Apparition's leaves-the-battlefield half: "the exiled card's owner
#: creates an X/X blue Illusion creature token, where X is the mana value of
#: the exiled card." CR 607.2a links "the exiled card" to the cards the same
#: object's other ability exiled (`ExileMarker.LINKED`, read by
#: `Game.cards_imprinted_on`); CR 111.2 makes the creating player - the exiled
#: card's owner - the token's owner and controller. The descriptor is read by
#: `_parse_generic_token_descriptor`, and X is the named characteristic of the
#: exiled card, summed over several linked cards (CR 607.3).
_EXILED_CARD_OWNER_CREATES_X_TOKEN_RE = re.compile(
    r"^the exiled card'?s owner creates an? x/x (?P<desc>.+?) tokens?"
    r"(?:\s+with\s+(?P<tail>.+?))?,?\s*where x is the (?P<attr>mana value|power|toughness) "
    r"of the exiled card\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_exiled_card_owner_creates_x_token_clause(text: str) -> AbilityEffect | None:
    """`_EXILED_CARD_OWNER_CREATES_X_TOKEN_RE`'s shape, or `None`.

    A card that has left exile is no longer "the exiled card" (CR 607.2a reads
    cards in the exile zone only), so it counts for nothing. CR 607.3: when the
    linked ability exiled several cards, "the exiled card" gets several answers
    and a variable uses their sum - so each owner of linked cards creates one
    token whose X is the sum over that owner's cards. X is not floored at zero:
    CR 107.1b lets an effect set a creature's power and toughness to a negative
    value, and a mana value of 0 simply makes a 0/0 that state-based actions
    put into the graveyard.
    """
    match = _EXILED_CARD_OWNER_CREATES_X_TOKEN_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    words = match.group("desc").strip().split()
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None or Type.CREATURE not in definition.types:
        return None
    attribute = match.group("attr").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if ability.source_id is None:
            return
        totals: dict[str, int] = {}
        for exiled in game.cards_imprinted_on(ability.source_id):
            if attribute == "mana value":
                value: float | int | None = exiled.mana_value
            elif attribute == "power":
                value = exiled.power
            else:
                value = exiled.toughness
            if value is None:
                continue
            owner = exiled.owner or game.controller_of(ability).username
            totals[owner] = totals.get(owner, 0) + int(value)
        for owner, size in totals.items():
            create_tokens(
                game, definition.model_copy(update={"power": size, "toughness": size}), owner
            )

    return effect


#: CR 118.12a's "unless" cost choice: "sacrifice `<object>` unless you
#: discard a card[ at random]." - Bebop & Rocksteady's own "Whenever Bebop &
#: Rocksteady attack or block, sacrifice a permanent unless you discard a
#: card." (a plain, controller's-choice-of-permanent sacrifice) and Argentum
#: Masticore's own upkeep trigger "sacrifice this creature unless you discard
#: a card" (self-sacrifice). CR 118.12a, verified this session: "'[Do
#: something] unless [a player does something else].' This means the same
#: thing as '[A player may do something else]. If [that player doesn't], [do
#: something].'" - `game.may` asks the discard as the *optional* half (CR
#: 608.2d, no impossible choice: never offered with an empty hand), and the
#: sacrifice only happens when it is declined or impossible, the identical
#: shape `_loses_life_unless_step` already runs for the "loses life unless
#: they discard/sacrifice" punisher template.
_SACRIFICE_UNLESS_DISCARD_RE = re.compile(
    r"^sacrifice (?:(?P<self_ref>this (?:creature|permanent|artifact|enchantment|"
    r"planeswalker|land))|an? (?P<choice>[a-z][a-z' ]*?)) unless you discard a card"
    r"(?P<random> at random)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_sacrifice_unless_discard_trigger(text: str) -> AbilityEffect | None:
    """`_SACRIFICE_UNLESS_DISCARD_RE`'s shape."""
    match = _SACRIFICE_UNLESS_DISCARD_RE.fullmatch(text.strip())
    if match is None:
        return None
    self_ref = match.group("self_ref") is not None
    choice_description = match.group("choice")
    random_discard = match.group("random") is not None
    sacrifice_of_choice: ClauseEffect | None = None
    if not self_ref:
        assert choice_description is not None
        if permanent_description(choice_description) is None:
            return None
        sacrifice_of_choice = _sacrifice_of_choice_clause_effect(
            choice_description, 1, with_indefinite_article(choice_description)
        )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        prompt = "discard a card rather than sacrifice a permanent"
        discarded = bool(player.hand) and game.may(
            player, prompt, source=ability.source_name, source_id=source_id_of(ability)
        )
        if discarded:
            if random_discard:
                _discard_at_random(game, player, 1, ability.source_name)
            else:
                _discard_cards(
                    game, player, 1, ability.source_name, source_id=source_id_of(ability)
                )
            return
        if self_ref:
            source = ability.source(game)
            if source is not None and source.zone is Zone.BATTLEFIELD:
                game.sacrifice(source)
            return
        assert sacrifice_of_choice is not None
        sacrifice_of_choice(game, player, ability.source_name, source_id_of(ability))

    return effect


#: "Sacrifice this <type> unless you pay {E}[{E}...]." (Static Prison) - a
#: fixed-amount CR 107.14/118.3 energy cost that averts the sacrifice rather
#: than causing a bonus. Only the self-referential "this <type>" subject is
#: read, the same restriction `machines/cost.py`'s `_PHRASE_EXERT_SELF` and
#: `_COUNTER_SELF_SUBJECT` hold their own self-referential cost shapes to - a
#: printed cost naming some other permanent would need target resolution this
#: template does not have.
_SACRIFICE_UNLESS_PAY_ENERGY_RE = re.compile(
    r"^sacrifice this (?:creature|permanent|artifact|enchantment|planeswalker|land) "
    r"unless you pay (?P<e>(?:\{e\})+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s25")
def _parse_sacrifice_unless_pay_energy(text: str) -> AbilityEffect | None:
    """CR 107.14, CR 118.3: "Sacrifice this <type> unless you pay {E}...",
    read off the ability's own printed text (Static Prison's upkeep trigger).

    `Game.may_pay_energy` is the same fixed-amount question `may_pay_life`
    already asks for CR 119.4's life-total floor, turned the other way round:
    paying is what avoids the sacrifice, so a "no" - declined, or illegal for
    lack of energy - sacrifices the source instead of doing nothing.
    """
    match = _SACRIFICE_UNLESS_PAY_ENERGY_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = len(re.findall(r"\{e\}", match.group("e"), re.IGNORECASE))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        player = game.player(ability.controller)
        paid = game.may_pay_energy(
            player, amount, source=ability.source_name, source_id=source_id_of(ability)
        )
        if not paid:
            game.sacrifice(source)

    return effect


#: "Sacrifice this <type> unless you pay {1}." - the upkeep tax Kataki, War's
#: Wage and Magus of the Tabernacle hand every artifact/creature as a quoted
#: trigger (and Phyrexian Soulgorger-style printed upkeep costs). CR 118.12a:
#: "'[Do something] unless [a player does something else].' This means the same
#: thing as '[A player may do something else]. If [that player] doesn't,
#: [do something].'" - the controller is asked to pay the mana (CR 608.2g lets
#: untapped sources be tapped for it) and the source is sacrificed when they
#: decline or cannot. Mana symbols only: `{E}` is the energy twin above.
_SACRIFICE_UNLESS_PAY_MANA_RE = re.compile(
    r"^sacrifice this (?:creature|permanent|artifact|enchantment|planeswalker|land|token) "
    r"unless you pay (?P<cost>(?:\{(?!e\})[^}]+\})+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s25")
def _parse_sacrifice_unless_pay_mana(text: str) -> AbilityEffect | None:
    """`_SACRIFICE_UNLESS_PAY_MANA_RE`'s shape (CR 118.12a, CR 701.21a)."""
    match = _SACRIFICE_UNLESS_PAY_MANA_RE.fullmatch(text.strip())
    if match is None:
        return None
    cost = ManaCost.parse(match.group("cost"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
            return
        paid = game.may_pay_mana_cost(
            game.player(ability.controller),
            cost,
            source=ability.source_name,
            source_id=source_id_of(ability),
            prompt=f"pay {cost} or sacrifice {source.name}",
        )
        if not paid:
            game.sacrifice(source)

    return effect


#: "You may exile a nonland card with mana value `<n>` or less from your hand.
#: If you do, it becomes plotted." (Jace Reawakened's second +1). CR 702.170c:
#: a plotted card is an exiled card its owner may later cast for free
#: (CR 702.170d) - the exile pile marker (CR 406.4) is the fact, so the card
#: need not print plot itself. "If you do" runs only when a card was exiled
#: (CR 608.2c).
_MAY_EXILE_FROM_HAND_BECOMES_PLOTTED_RE = re.compile(
    r"^you may exile an? nonland card with mana value (?P<limit>\d+) or less from your hand\.\s*"
    r"if you do, it becomes plotted\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s25")
def _parse_may_exile_from_hand_becomes_plotted(text: str) -> AbilityEffect | None:
    """`_MAY_EXILE_FROM_HAND_BECOMES_PLOTTED_RE`'s shape (CR 702.170c)."""
    match = _MAY_EXILE_FROM_HAND_BECOMES_PLOTTED_RE.fullmatch(text.strip())
    if match is None:
        return None
    limit = int(match.group("limit"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        candidates = [
            card for card in player.hand if not card.card.is_land and card.mana_value <= limit
        ]
        if not candidates:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"you may exile a nonland card with mana value {limit} or less to plot it",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                exact=False,
                cards=tuple(card.id for card in candidates),
                card_labels=tuple(card.name for card in candidates),
                default_cards=(),
            )
        )
        by_id = {card.id: card for card in candidates}
        picked = next((by_id[i] for i in chosen if i in by_id), None) if chosen else None
        if picked is None:
            return
        game.exile_permanent(picked)
        if picked.zone is Zone.EXILE:
            annotate_exile(picked, ExileMarker.PLOTTED, picked.owner, game)

    return effect


# --------------------------------------------------------------------------
# "Exile the top N cards of your library. [You may ]put <any number of|all>
# <quality> cards from among them onto the battlefield." (CR 406.1's exile,
# CR 110.2's put)
# --------------------------------------------------------------------------
#
# Xenagos, the Reveler's `-6`: "Exile the top seven cards of your library. You
# may put any number of creature and/or land cards from among them onto the
# battlefield." and Tezzeret, Master of the Bridge's `-8`: "Exile the top ten
# cards of your library. Put all artifact cards from among them onto the
# battlefield." - one shape, two quantifiers. "Any number of" is CR 107.1c's
# own built-in optionality (zero included), so the player chooses among the
# qualifying cards; "all" asks nothing. "Them" is the cards this instruction
# just exiled, never the rest of the exile zone, and whatever is not put onto
# the battlefield simply stays exiled - there is no "the rest" instruction to
# move it. CR 609.3: a library shorter than N exiles what there is.
_EXILE_TOP_N_PUT_FROM_AMONG_RE = re.compile(
    rf"^exile the top (?P<n>{COUNT}) cards of your library\.\s*"
    r"(?:(?P<may>you may )?put (?P<quantifier>any number of|all) )"
    r"(?P<quality>[a-z]+(?:(?:,| or| and/or) [a-z]+)*?) cards?"
    r" from among them onto the battlefield(?P<tapped> tapped)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s32")
def _parse_exile_top_n_put_from_among_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_TOP_N_PUT_FROM_AMONG_RE`'s shape - see the banner above."""
    match = _EXILE_TOP_N_PUT_FROM_AMONG_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).strip().split())
    )
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    quality = re.sub(r"\s+and/or\s+", " or ", match.group("quality"))
    if not _search_quality_is_readable(quality):
        return None
    quality_matches = _quality_matcher(quality)
    choose = match.group("quantifier").lower() == "any number of"
    if not choose and match.group("may") is not None:
        return None
    tapped = match.group("tapped") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        top = list(controller.library[:count])
        if not top:
            return
        exiled = [state for state in game.exile_cards(top) if state.zone is Zone.EXILE]
        candidates = [state for state in exiled if quality_matches(state)]
        chosen = candidates
        if choose and candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="put any number of them onto the battlefield",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=len(candidates),
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            chosen = [state for card_id in chosen_ids if (state := by_id.get(card_id)) is not None]
        for state in chosen:
            if state.zone is Zone.EXILE:
                game.put_onto_battlefield(state, controller.username, tapped=tapped)

    return effect


#: "you may exile <this object's name>, then return him/her/it/them to the
#: battlefield[ tapped][ transformed] under his/her/its/their owner's control."
#: - Ajani, Nacatl Pariah's Cats-die trigger, and the same self-referential
#: blink idiom wherever else it is printed. The targeted twin is
#: `_RETURN_TO_BATTLEFIELD_RE` above, which reads "exile *target* X, then
#: return it ..."; this one names its own object instead (CR 201.5: "text that
#: refers to the object it's on by name means just that particular object"), so
#: there is no target and CR 608.2b's recheck has nothing to check.
#:
#: The control clause is required, exactly as it is for the targeted shape: a
#: bare "return him to the battlefield" names no controller, and CR 110.2a
#: leaves that to the effect, which one regex on one sentence cannot decide.
_MAY_EXILE_SELF_THEN_RETURN_RE = re.compile(
    r"^you may exile (?P<name>[^,]+), then return (?:it|him|her|them)"
    r" to the battlefield"
    r"(?P<tapped> tapped)?"
    r"(?P<transformed> transformed)?"
    r" under (?:its|his|her|their) owner's control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s25")
def _parse_may_exile_self_then_return_clause(text: str) -> AbilityEffect | None:
    """ "You may exile <this>, then return it to the battlefield transformed
    under its owner's control." as one CR 608.2c instruction.

    Ajani, Nacatl Pariah's "Whenever one or more other Cats you control die"
    trigger, read off its own printed text with no registry row. Two rules make
    it one instruction rather than two:

    - CR 201.5 - the name is a reference to the very object the ability is on,
      so the exile needs no target and no choice of what to exile.
    - CR 712.14a - "transformed" describes how it *enters*, which is why the
      return goes through `Game.put_onto_battlefield(transformed=True)` rather
      than transforming the permanent afterwards: CR 306.5b's loyalty counters
      are put on as it enters, and read off the face that is up.

    The "you may" is `DecisionKind.MAY` (CR 608.2d), the same shape
    `_parse_conditional_sacrifice_clause` uses. Declining does nothing at all;
    accepting runs both halves or, if CR 111.8 refuses the exile for a token,
    neither - never the exile alone, which would be strictly worse than doing
    nothing (the trap `_LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE` exists for).
    """
    match = _MAY_EXILE_SELF_THEN_RETURN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    named = match.group("name").strip()
    tapped = match.group("tapped") is not None
    transformed = match.group("transformed") is not None
    prompt = f"exile {named}, then return {'it' if not transformed else 'it transformed'}"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        # CR 201.5: the name means *this* object. A source whose name has
        # nothing to do with the printed one is not what this sentence is
        # about, so nothing happens rather than the wrong permanent blinking.
        if named.lower() not in (source.name or "").lower():
            return
        decision = Decision(
            kind=DecisionKind.MAY,
            player=ability.controller,
            prompt=prompt,
            source=ability.source_name,
            source_id=source_id_of(ability),
            affirmative_is_legal=True,
        )
        if not game.ask(decision):
            return
        exiled = game.exile_permanent(source)
        if exiled.zone is not Zone.EXILE:
            return  # CR 111.8: a token refused the move; nothing to return.
        owner = exiled.owner or ability.controller
        game.put_onto_battlefield(exiled, owner, tapped=tapped, transformed=transformed)

    return effect


#: "Exile `<this object's name>`, then return it to the battlefield[
#: tapped][ transformed] under its owner's/your control." - the mandatory
#: twin of `_MAY_EXILE_SELF_THEN_RETURN_RE`, with no "you may": Vorinclex //
#: The Grand Evolution's own activated ability ("{6}{G}{G}: Exile Vorinclex,
#: then return it to the battlefield transformed under its owner's
#: control."), and the same sentence on any Saga's own chapter III ("Exile
#: this Saga, then return it to the battlefield transformed under your
#: control.") - creatures and planeswalkers print "its owner's control"
#: while a Saga prints "your control" (its controller and owner necessarily
#: match, being an enchantment nobody else can put on the battlefield), so
#: both are read here rather than pinning the parser to one phrasing.
_EXILE_SELF_THEN_RETURN_RE = re.compile(
    r"^exile (?P<name>this [a-z]+|[^,]+), then return (?:it|him|her|them)"
    r" to the battlefield"
    r"(?P<tapped> tapped)?"
    r"(?P<transformed> transformed)?"
    r" under (?:(?:its|his|her|their) owner'?s|your) control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s25")
def _parse_exile_self_then_return_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_SELF_THEN_RETURN_RE`'s shape - see
    `_parse_may_exile_self_then_return_clause`'s docstring for the two rules
    (CR 201.5, CR 712.14a) that make this one CR 608.2c instruction. This one
    is unconditional: no `DecisionKind.MAY` is asked, both halves simply run.

    An *activated* ability's `effect_text` reaches this already run through
    `self_normalized_effect_text` (`activated_effect_for` always normalizes,
    unlike `trigger_effect_for`'s try-unnormalized-first order) - Vorinclex's
    own literal "Exile Vorinclex" arrives here as "Exile this permanent".
    "This `<noun>`" is CR 700.7's own self-reference regardless of which
    generic noun the normalizer or the printed card used ("this saga", "this
    creature", "this permanent", ...), so it is read as `named = None` (the
    object needs no name check at all) rather than compared against the
    source's own name, which is what let this shape fall through silently:
    "this permanent" is never a substring of "Vorinclex".
    """
    match = _EXILE_SELF_THEN_RETURN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    name_text = match.group("name").strip()
    named = None if name_text.lower().startswith("this ") else name_text
    tapped = match.group("tapped") is not None
    transformed = match.group("transformed") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        # CR 201.5: the name means *this* object - refused for anything else,
        # the same guard `_parse_may_exile_self_then_return_clause` uses.
        if named is not None and named.lower() not in (source.name or "").lower():
            return
        exiled = game.exile_permanent(source)
        if exiled.zone is not Zone.EXILE:
            return  # CR 111.8: a token refused the move; nothing to return.
        owner = exiled.owner or ability.controller
        game.put_onto_battlefield(exiled, owner, tapped=tapped, transformed=transformed)

    return effect


#: "<effect>. [If <condition>, ]exile <this object>, then return it to the
#: battlefield[ transformed][ under its owner's/your control]." - an
#: instruction that ends by sending its own source out and back:
#:
#:   Shiva, Warden of Ice III    "Tap all lands your opponents control. Exile
#:                               Shiva, then return it to the battlefield
#:                               (front face up)."
#:   The True Scriptures III     "Put all creature cards from all graveyards
#:                               onto the battlefield under your control.
#:                               Exile this Saga, then return it ..."
#:   Ifrit, Warden of Inferno    "Add {R}{R}{R}{R}. If Ifrit has three or more
#:   II, III                     lore counters on it, exile it, then return it
#:                               to the battlefield (front face up)."
#:   Jace, Vryn's Prodigy        "Draw a card, then discard a card. If there
#:                               are five or more cards in your graveyard,
#:                               exile Jace, then return him to the
#:                               battlefield transformed under his owner's
#:                               control."
#:
#: The leading effect is whatever the ordinary dispatcher reads it as; this
#: only owns the trailing return. The "(front face up)" reminder is stripped
#: before any effect text is parsed (CR 207.2a), and it restates CR 712.14's
#: default for a double-faced card put onto the battlefield from exile, so a
#: return with no "transformed" is a front-face-up return.
_THEN_EXILE_SELF_AND_RETURN_RE = re.compile(
    r"^(?P<prefix>.+?\.)\s*(?:if (?P<condition>[^,]+), )?"
    r"exile (?P<name>this [a-z]+|it|him|her|[^,.]+), then return (?:it|him|her)"
    r" to the battlefield(?P<transformed> transformed)?"
    r"(?: under (?:(?:its|his|her|their) owner'?s|your) control)?\s*\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s43")
def _parse_then_exile_self_and_return_clause(text: str) -> AbilityEffect | None:
    """`_THEN_EXILE_SELF_AND_RETURN_RE`'s shape.

    CR 608.2c: the leading effect runs first, and only then is the condition
    asked - Jace counts his graveyard *after* his own discard. The condition
    goes through `Game.condition_holds`, and one `condition_is_readable`
    cannot place makes the whole paragraph unread rather than half-run.

    The return is the source as it was when the ability was put on the stack
    (`AbilityOnStack.source_stamp`, CR 400.7): a Saga that left and came back
    in response is a new object this chapter knows nothing about. The object
    that comes back is a new one as well, front face up by default (CR
    712.14) or back face up when the sentence says "transformed" (CR
    712.14a).
    """

    match = _THEN_EXILE_SELF_AND_RETURN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    condition = match.group("condition")
    if condition is not None and not _effect_condition_is_readable(condition):
        return None
    name_text = match.group("name").strip()
    named = (
        None
        if name_text.lower().startswith("this ") or name_text.lower() in {"it", "him", "her"}
        else name_text
    )
    transformed = match.group("transformed") is not None
    leading = _ability_effect_or_notice(match.group("prefix").strip())
    if leading is None:
        return None
    if getattr(leading, "__name__", "").endswith("notice_only"):
        # The leading instruction fails closed; so does the whole paragraph.
        return leading

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        leading(game, ability)
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
            return
        if named is not None and named.lower() not in (source.name or "").lower():
            return
        if condition is not None and not game.condition_holds(
            ability.controller, condition, source=source
        ):
            return
        exiled = game.exile_permanent(source)
        if exiled.zone is not Zone.EXILE:
            return  # CR 111.8: a token refused the move; nothing to return.
        owner = exiled.owner or ability.controller
        game.put_onto_battlefield(exiled, owner, transformed=transformed)

    return effect


#: "exile a card from your hand" / "exile two cards from your hand" as a
#: resolution instruction, not a cost - Gemstone Caverns' own opening-hand
#: rider ("If you do, exile a card from your hand."), read by
#: `machines/opening_hand.py` through `trigger_effect_for` like any other
#: effect text. CR 701.13a: "To exile an object, move it to the exile zone
#: from wherever it is." The cards are the resolving player's own choice
#: (CR 608.2d); a hand holding fewer than the count exiles what is there.
_EXILE_CARDS_FROM_YOUR_HAND_RE = re.compile(
    rf"^exile {count_pattern('n', article=True)} cards? from your hand\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_exile_cards_from_your_hand_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_CARDS_FROM_YOUR_HAND_RE`'s shape: the controller chooses that
    many cards from their own hand, and `Game.exile_cards` puts them into the
    one shared exile zone (CR 400.1)."""
    match = _EXILE_CARDS_FROM_YOUR_HAND_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"), article=True)
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        hand = list(player.hand)
        if not hand:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=text.strip().rstrip(".").lower(),
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=min(count, len(hand)),
                cards=tuple(state.id for state in hand),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {state.id: state for state in hand}
        game.exile_cards([by_id[card_id] for card_id in chosen])

    return effect


#: "Target opponent exiles the top four cards of their library, then you may
#: put any number of land cards that player owns from exile onto the
#: battlefield under your control." - Oblivion Sower's own cast trigger.
#: `_parse_exile_top_of_other_libraries_antecedent`'s own "target opponent
#: exiles the top `<n>` cards of their library" shape (`_EXILE_TOP_OF_OTHER_
#: LIBRARIES_RE`'s `target_exiles` branch) is reused whole for the
#: antecedent (CR 603.3d: a triggered ability's target is chosen the same
#: way a spell's is, CR 601.2c) - only the consequent is new: CR 110.2a's
#: "put onto the battlefield under [a stated] control" rather than
#: `_PLAY_PERMISSION_RE`'s cast/play permission that antecedent is usually
#: paired with. CR 108.3: an exiled card stays owned by whoever owned it, so
#: `Game.put_onto_battlefield`'s own `controller` argument here is the
#: resolving ability's controller - never the opponent whose library was
#: exiled, and never conflated with ownership.
_TARGET_OPPONENT_EXILE_TOP_THEN_PUT_LANDS_RE = re.compile(
    r"^(?P<antecedent>target (?:opponent|player) exiles the top "
    rf"(?:card|{COUNT} cards) of their library), then you may put any number of "
    r"land cards that player owns from exile onto the battlefield under your control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_target_opponent_exile_top_then_put_lands_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_TARGET_OPPONENT_EXILE_TOP_THEN_PUT_LANDS_RE`'s shape - see the
    banner above. No land among the exiled cards (or nothing exiled at all,
    an illegal or gone target - CR 608.2b) asks nothing and puts nothing."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).strip().split())
    match = _TARGET_OPPONENT_EXILE_TOP_THEN_PUT_LANDS_RE.fullmatch(whole)
    if match is None:
        return None
    antecedent = _parse_exile_top_of_other_libraries_antecedent(match.group("antecedent"))
    if antecedent is None:
        return None
    exile_tops, _ = antecedent

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        exiled = exile_tops(game, ability)
        lands = [state for state in exiled if state.zone is Zone.EXILE and Type.LAND in state.types]
        if not lands:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=(
                    "put any number of the exiled land cards onto the battlefield under "
                    "your control"
                ),
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=len(lands),
                exact=False,
                cards=tuple(state.id for state in lands),
            )
        )
        by_id = {state.id: state for state in lands}
        for card_id in chosen_ids:
            state = by_id.get(card_id)
            if state is not None and state.zone is Zone.EXILE:
                game.put_onto_battlefield(state, controller.username)

    return effect


# ---------------------------------------------------------------------------
# Mass destruction and mass sacrifice: "destroy each <qualifier>" and "each
# player sacrifices all <qualifier>" - CR 701.8a's destroy and CR 701.21a's
# sacrifice, each applied to every matching permanent on the battlefield
# rather than to a target CR 601.2c would announce and CR 608.2b would
# recheck. The family: All Is Dust (sacrifice, colored), Engineered
# Explosives and Culling Ritual (destroy, mana value against a printed
# constant or a self-referential counter count), Oblivion Stone (destroy,
# absence of a named counter, then an unconditional counter sweep). Wrath of
# the Skies shares the same "destroy each <qualifier> with mana value <cmp>"
# shape but is matched by its own dedicated parser above, ahead of this one,
# for its energy-payment right-hand side.
# ---------------------------------------------------------------------------

#: "destroy each/all <qualifier>[ without a <kind> counter on it][ with mana
#: value <cmp>]." <qualifier> is `_parse_mass_type_qualifier`'s grammar.
#: "all" reads exactly like "each" here - CR 205.2a's plural qualifier names
#: no different a group than "each" does - and Brotherhood's End's "Destroy
#: all artifacts with mana value 3 or less" is the wording that needs it.
_DESTROY_EACH_RE = re.compile(r"^destroy (?:each|all) (?P<rest>.+?)\.?$", re.IGNORECASE | re.DOTALL)

#: "<qualifier> without a <kind> counter on it" - Oblivion Stone's own
#: absence-of-a-counter restriction (CR 122.1: a counter's presence or
#: absence is state the effect can read, not a characteristic).
_MASS_WITHOUT_COUNTER_RE = re.compile(
    r"^(?P<qualifier>.+?) without a (?P<kind>[a-z]+) counter on it$", re.IGNORECASE
)

#: "<qualifier> with mana value equal to <rhs>" / "<qualifier> with mana
#: value N or less"/"...or greater" / "<qualifier> with mana value X" - CR
#: 202.3's number, compared against a printed constant, a count read off the
#: clause's own source, or (Steel Hellkite's own "with mana value X") CR
#: 107.3a's variable as the activating ability's own paid X.
_MASS_MANA_VALUE_RE = re.compile(
    r"^(?P<inner>.+?) with mana value (?:"
    r"equal to (?P<eq>.+)"
    r"|(?P<n>\d+) or (?P<dir>less|greater)"
    r"|(?P<bare_x>x)"
    r")$",
    re.IGNORECASE,
)

#: "<qualifier> whose controller was dealt combat damage by this creature
#: this turn" (Steel Hellkite) - the identical "dealt combat damage" tail
#: `machines/targeting.py`'s own "target player who ..." / "controlled by a
#: player who ..." readers use, here modifying a mass-destruction subject's
#: own controller instead of a target's. Stripped ahead of every other
#: mass-destroy qualifier (`_MASS_MANA_VALUE_RE` included) since it is the
#: outermost clause in the printed sentence.
_MASS_CONTROLLER_DEALT_DAMAGE_RE = re.compile(
    r"^(?P<qualifier>.+?) whose controller (?P<tail>was dealt .+? this turn)$", re.IGNORECASE
)

#: "<qualifier> with power N or greater" / "... toughness N or less" - CR
#: 208.1's numbers compared against a printed constant: Elspeth, Sun's
#: Champion's -3 ("Destroy all creatures with power 4 or greater") and The
#: Battle of Bywater's "power 3 or greater". Read off the computed board
#: (CR 613.1) as the effect is applied (CR 608.2h), so a counter or a pump
#: in response is seen; an object with no power at all never matches.
_MASS_POWER_TOUGHNESS_RE = re.compile(
    r"^(?P<inner>.+?) with (?P<stat>power|toughness) (?P<n>\d+) or (?P<dir>less|greater)$",
    re.IGNORECASE,
)

#: "<qualifier> that entered [the battlefield] this turn" - Force of
#: Despair's own "Destroy all creatures that entered this turn." CR 400.7's
#: "entered the battlefield this turn" is `CardState.turn_entered` compared
#: against the current turn, the identical reading `machines/targeting.py`'s
#: own `must_have_entered_this_turn` already gives the same phrase for a
#: *targeted* restriction and `_parse_mass_return_entered_this_turn_clause`
#: gives it for its own mass-return subject - read here a third time for a
#: mass-*destruction*'s subject instead, sharing none of the mass-destroy
#: qualifier grammar (type, counter, mana value) it is ANDed alongside.
_MASS_ENTERED_THIS_TURN_RE = re.compile(
    r"^(?P<qualifier>.+?) that entered(?: the battlefield)? this turn$", re.IGNORECASE
)

#: "the number of <kind> counters on this <noun>" - Engineered Explosives's
#: own self-referential right-hand side: "Destroy each nonland permanent
#: with mana value equal to the number of charge counters on this artifact."
_MASS_COUNTERS_ON_SELF_RE = re.compile(
    r"^the number of (?P<kind>[a-z]+) counters on this \w+$", re.IGNORECASE
)


def _parse_mass_mv_rhs(text: str) -> Callable[["Game", CardState | None], int | None] | None:
    """The right-hand side of a mass-destruction mana-value comparison: a
    printed constant (Culling Ritual's "2") or a count of counters on the
    clause's own source (Engineered Explosives's "the number of charge
    counters on this artifact"). Returns `None` for text neither shape reads.
    """
    stripped = text.strip()
    if stripped.isdigit():
        value = int(stripped)

        def constant(game: "Game", source: CardState | None) -> int | None:
            return value

        return constant
    match = _MASS_COUNTERS_ON_SELF_RE.fullmatch(stripped)
    if match is None:
        return None
    kind = match.group("kind").lower()

    def counters_on_source(game: "Game", source: CardState | None) -> int | None:
        if source is None:
            return None
        # CR 603.10a / CR 400.7: Engineered Explosives sacrifices itself as
        # part of this same activation's cost, so by the time this ability
        # resolves it is a fresh, empty object in the graveyard -
        # `CardState.move_to` clears `counters` and keeps what was there on
        # `last_known_counters` for exactly this "look back at what just
        # left" reference. A source that never left keeps reading its live
        # counters, which is the general case for any future card sharing
        # this shape without a self-sacrifice cost.
        counters = (
            source.counters if source.zone is Zone.BATTLEFIELD else source.last_known_counters
        )
        return counters[kind]

    return counters_on_source


def _parse_mass_mv_comparison(
    match: re.Match[str],
) -> Callable[["Game", Characteristics, CardState | None, int | None], bool] | None:
    """`_MASS_MANA_VALUE_RE`'s comparison half, as a predicate over
    (game, candidate's characteristics, this clause's own source, the
    activating ability's own paid X - CR 107.3a, Steel Hellkite's "mana
    value X" - or `None` for a spell/constant/counter comparison that never
    reads one).
    """
    eq_rhs = match.group("eq")
    if eq_rhs is not None:
        rhs = _parse_mass_mv_rhs(eq_rhs)
        if rhs is None:
            return None

        def equals(
            game: "Game",
            chars: Characteristics,
            source: CardState | None,
            x_value: int | None = None,
        ) -> bool:
            threshold = rhs(game, source)
            return threshold is not None and chars.mana_value == threshold

        return equals

    if match.group("bare_x") is not None:

        def equals_x(
            game: "Game",
            chars: Characteristics,
            source: CardState | None,
            x_value: int | None = None,
        ) -> bool:
            return x_value is not None and chars.mana_value == x_value

        return equals_x

    n_text = match.group("n")
    direction = match.group("dir")
    if n_text is None or direction is None:
        return None
    bound = int(n_text)
    if direction.lower() == "less":

        def at_most(
            game: "Game",
            chars: Characteristics,
            source: CardState | None,
            x_value: int | None = None,
        ) -> bool:
            return chars.mana_value <= bound

        return at_most

    def at_least(
        game: "Game", chars: Characteristics, source: CardState | None, x_value: int | None = None
    ) -> bool:
        return chars.mana_value >= bound

    return at_least


#: A trailing controller restriction on a mass destroy/exile qualifier -
#: Ajani, Strength of the Pride's own "exile this permanent and each artifact
#: and creature your opponents control." CR 205.2a's type-and-restriction
#: reading (`_parse_mass_type_qualifier`) explicitly refuses a controller
#: word rather than guessing at it (see that function's own docstring), so
#: it is stripped here, ahead of every other suffix `_parse_mass_destroy_
#: predicate` already reads, and checked against the resolving ability's own
#: source controller instead - the same "you"/"your opponents" pair
#: `_CHOSEN_NAME_GROUP_LOSES_RE`'s `scope` group already reads for a group
#: static, generalised for a mass destroy/exile sweep too.
_MASS_CONTROLLER_SCOPE_RE = re.compile(
    r"^(?P<inner>.+?)\s+(?P<scope>you control|your opponents control|you don't control)$", re.IGNORECASE
)


def _parse_mass_destroy_predicate(
    rest: str,
) -> Callable[["Game", CardState, CardState | None, int | None], bool] | None:
    """The whole description behind `_DESTROY_EACH_RE`'s `rest` group - a
    type qualifier, an optional controller restriction, an optional
    absence-of-counter restriction, an optional mana-value comparison, and
    an optional "whose controller was dealt combat damage ... this turn"
    restriction (Steel Hellkite), ANDed together - as a predicate over
    (game, candidate permanent, this clause's own source, the activating
    ability's own paid X if any).
    """
    text = rest.strip()
    controller_dealt_damage_test = None
    controller_match = _MASS_CONTROLLER_DEALT_DAMAGE_RE.fullmatch(text)
    if controller_match is not None:
        from ..conditions.history import dealt_damage_clause_test

        controller_dealt_damage_test = dealt_damage_clause_test(controller_match.group("tail"))
        if controller_dealt_damage_test is None:
            return None
        text = controller_match.group("qualifier").strip()
    controller_scope: str | None = None
    scope_match = _MASS_CONTROLLER_SCOPE_RE.fullmatch(text)
    if scope_match is not None:
        controller_scope = scope_match.group("scope").lower()
        text = scope_match.group("inner").strip()
    entered_this_turn = False
    entered_match = _MASS_ENTERED_THIS_TURN_RE.fullmatch(text)
    if entered_match is not None:
        entered_this_turn = True
        text = entered_match.group("qualifier").strip()
    stat_comparison: Callable[[Characteristics], bool] | None = None
    stat_match = _MASS_POWER_TOUGHNESS_RE.fullmatch(text)
    if stat_match is not None:
        stat_comparison = _mass_stat_comparison(
            stat_match.group("stat").lower(),
            int(stat_match.group("n")),
            at_least=stat_match.group("dir").lower() == "greater",
        )
        text = stat_match.group("inner").strip()
    mv_comparison = None
    mv_match = _MASS_MANA_VALUE_RE.fullmatch(text)
    if mv_match is not None:
        mv_comparison = _parse_mass_mv_comparison(mv_match)
        if mv_comparison is None:
            return None
        text = mv_match.group("inner").strip()
    counter_kind = None
    without_match = _MASS_WITHOUT_COUNTER_RE.fullmatch(text)
    if without_match is not None:
        counter_kind = without_match.group("kind").lower()
        text = without_match.group("qualifier").strip()
    # "other" (Myojin of Cleansing Fire's "Destroy all other creatures"): every
    # match except the clause's own source permanent.
    excludes_source = False
    if (other := re.match(r"^other\s+", text, re.IGNORECASE)) is not None:
        excludes_source = True
        text = text[other.end() :].strip()
    # CR 111.1: "token"/"nontoken" - Aether Snap's "exile all tokens", a
    # "creature token", a "nontoken creature". A bare "tokens" is every
    # token permanent.
    token_wanted: bool | None = None
    token_match = re.fullmatch(r"(?P<inner>.*?)\s*\btokens?", text, re.IGNORECASE)
    if token_match is not None:
        token_wanted = True
        text = token_match.group("inner").strip() or "permanent"
    elif (nontoken := re.match(r"^nontoken\s+", text, re.IGNORECASE)) is not None:
        token_wanted = False
        text = text[nontoken.end() :].strip()
    type_matches = _parse_mass_type_qualifier(text)
    if type_matches is None:
        return None

    def predicate(
        game: "Game",
        permanent: CardState,
        source: CardState | None,
        x_value: int | None = None,
    ) -> bool:
        if excludes_source and source is not None and permanent.id == source.id:
            return False
        if controller_scope is not None:
            if source is None:
                return False
            is_yours = permanent.controller == source.controller
            if controller_scope == "you control" and not is_yours:
                return False
            if controller_scope in ("your opponents control", "you don't control") and is_yours:
                return False
        if token_wanted is not None and is_token(permanent) is not token_wanted:
            return False
        chars = game.characteristics_of(permanent)
        if not type_matches(chars):
            return False
        if counter_kind is not None and chars.counters.get(counter_kind, 0) > 0:
            return False
        if stat_comparison is not None and not stat_comparison(chars):
            return False
        if entered_this_turn:
            turn = game.turn
            if turn is None or permanent.turn_entered != turn.turns_taken:
                return False
        if mv_comparison is not None and not mv_comparison(game, chars, source, x_value):
            return False
        return controller_dealt_damage_test is None or (
            chars.controller is not None
            and controller_dealt_damage_test(game, chars.controller, source)
        )

    return predicate


def _mass_stat_comparison(
    stat: str, bound: int, *, at_least: bool
) -> Callable[[Characteristics], bool]:
    """`_MASS_POWER_TOUGHNESS_RE`'s comparison: the computed power or
    toughness (CR 208.1, CR 613.1) against a printed bound, "or greater"
    inclusive upward and "or less" inclusive downward. `None` - an object with
    no such number - matches neither direction."""

    def compare(chars: Characteristics) -> bool:
        value = chars.power if stat == "power" else chars.toughness
        if value is None:
            return False
        return value >= bound if at_least else value <= bound

    return compare


def _destroy_matching(
    game: "Game",
    predicate: Callable[["Game", CardState, CardState | None, int | None], bool],
    source: CardState | None,
    x_value: int | None = None,
) -> int:
    """Destroy every permanent on the battlefield right now that `predicate`
    holds for, and answer how many actually left.

    CR 608.2f: "some spells and abilities include actions taken on multiple
    ... objects. In most cases, each such action is processed simultaneously."
    The candidate set is snapshotted from `game.battlefield` once, before
    anything is destroyed, so an earlier destruction in this same loop (and
    whatever state-based or triggered consequence it causes) cannot change
    what the rest of the loop still sees; each permanent's zone is rechecked
    immediately before its own `destroy` call for the same reason CR 608.2b
    rechecks a target - a permanent an earlier step in this loop already
    removed cannot be destroyed again. `Game.destroy` itself is what enforces
    CR 702.12b's indestructible, so an indestructible candidate is identified
    here but does not count toward the returned total. `x_value` is CR
    107.3a's X as an activating ability paid it (Steel Hellkite's own "mana
    value X"); `None` for a spell or an ability whose cost carries none.
    """
    destroyed = 0
    for permanent in [p for p in list(game.battlefield) if predicate(game, p, source, x_value)]:
        if permanent.zone is Zone.BATTLEFIELD:
            game.destroy(permanent)
            if permanent.zone is not Zone.BATTLEFIELD:
                destroyed += 1
    return destroyed


@SPELL_TEXT.rung("s21")
@MIXED_CLAUSE.rung("s35")
def _parse_destroy_each_clause(sentence: str) -> TargetedClause | None:
    """ "Destroy each <qualifier>[ without a counter][ with mana value ...]."
    on its own, with no second instruction - Engineered Explosives's whole
    ability text. `source` is the spell itself, or the activating ability's
    own source permanent (CR 113.7a: found by id, whatever zone it is in
    now), since nothing here is targeted at all.
    """
    match = _DESTROY_EACH_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("rest"))
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        x_value = getattr(stack_object, "x_value", None)
        _destroy_matching(game, predicate, source, x_value)

    return effect


#: "Exile each/all <qualifier>." - the exile-side twin of `_DESTROY_EACH_RE`,
#: sharing its qualifier grammar (`_parse_mass_destroy_predicate`) since
#: CR 205.2a's card-type-and-restriction reading does not care which verb
#: sweeps the battlefield. Overwrite the Multiverse's "Exile all creatures."
#: is the pool's only printing of the shape, but the qualifier grammar reads
#: any of Wrath of the Skies's own type lists the same way `_DESTROY_EACH_RE`
#: already does, so a future "exile all artifacts and creatures" reads too.
_EXILE_EACH_RE = re.compile(r"^exile (?:each|all) (?P<rest>.+?)\.?$", re.IGNORECASE | re.DOTALL)


def _exile_matching(
    game: "Game",
    predicate: Callable[["Game", CardState, CardState | None], bool],
    source: CardState | None,
) -> int:
    """Exile every permanent on the battlefield right now that `predicate`
    holds for, as one CR 608.2f/603.2c instruction (`Game.exile_cards`, the
    same batch door `airbend` uses), and answer how many actually left - the
    exile-side twin of `_destroy_matching`.

    The candidate set is snapshotted from `game.battlefield` once, before
    anything moves, for the same reason `_destroy_matching` snapshots its own:
    an earlier exile in this same sweep (and whatever it triggers) must not
    change what the rest of the sweep still sees.
    """
    candidates = [
        permanent for permanent in list(game.battlefield) if predicate(game, permanent, source)
    ]
    exiled = game.exile_cards(candidates)
    return sum(1 for card in exiled if card.zone is Zone.EXILE)


@MIXED_CLAUSE.rung("s35")
def _parse_exile_each_clause(sentence: str) -> TargetedClause | None:
    """ "Exile each/all <qualifier>." on its own - `_EXILE_EACH_RE`'s shape.

    `Game.record_count` records how many actually left (CR 608.2c: "later
    text on the card may modify the meaning of earlier text"), which is what
    lets a later "the number of `<type>` exiled this way" clause -
    `count_expression`'s `_COUNT_THIS_WAY_RE` branch, read through
    `counted_this_way` - answer Overwrite the Multiverse's own "Empower Jace
    X, where X is the number of creatures exiled this way" correctly, whether
    every creature on the battlefield was exiled or none were.
    """
    match = _EXILE_EACH_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("rest"))
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        count = _exile_matching(game, predicate, source)
        game.record_count(count)

    return effect


#: "If `<condition>`, exile this permanent and each `<qualifier>`." - Ajani,
#: Strength of the Pride's own 0 loyalty ability, "If you have at least 15
#: life more than your starting life total, exile Ajani and each artifact and
#: creature your opponents control." (its own name already rewritten to
#: "this permanent" by `self_normalized_effect_text`). The leading "if" is a
#: loyalty ability's own plain conditional instruction (CR 606.2, CR 608.2c),
#: not a triggered ability's intervening *if* (CR 603.4) - there is no
#: trigger event here to recheck - so it is read the same way `_IF_CONDITION_
#: YOU_WIN_THE_GAME_RE` already reads one: `_effect_condition_is_readable`/
#: `Game.condition_holds`, never a second condition grammar. The group half
#: reuses `_parse_mass_destroy_predicate`'s qualifier grammar - including the
#: controller restriction `_MASS_CONTROLLER_SCOPE_RE` reads - so "your
#: opponents control" is never a second copy of `_EXILE_EACH_RE`'s own
#: reading. CR 608.2f/603.2c: the source's own exile and the group sweep are
#: one `Game.exile_cards` batch, not two separate moves.
_IF_CONDITION_EXILE_SELF_AND_EACH_RE = re.compile(
    r"^if (?P<condition>.+?), exile this permanent and each (?P<rest>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s39", for_spell=False)
def _parse_if_condition_exile_self_and_each_clause(
    sentence: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_CONDITION_EXILE_SELF_AND_EACH_RE`'s shape. Ability-only: "this
    permanent" names the resolving ability's own source (CR 700.7), which a
    spell not yet on the battlefield has none of."""
    if for_spell:
        return None
    match = _IF_CONDITION_EXILE_SELF_AND_EACH_RE.fullmatch(sentence.strip())
    if match is None or not _effect_condition_is_readable(match.group("condition")):
        return None
    predicate = _parse_mass_destroy_predicate(match.group("rest"))
    if predicate is None:
        return None
    condition_text = match.group("condition").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        controller = game.controller_of(stack_object)
        source = stack_object.source_or_last_known(game)
        if not game.condition_holds(controller.username, condition_text, source):
            return
        candidates = [
            permanent for permanent in list(game.battlefield) if predicate(game, permanent, source)
        ]
        if (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and all(permanent.id != source.id for permanent in candidates)
        ):
            candidates.append(source)
        exiled = game.exile_cards(candidates)
        game.record_count(len(exiled))

    return effect


#: "Sacrifice all `<qualifier>` you control." - Emrakul, the World Anew's own
#: leaves-the-battlefield trigger ("sacrifice all creatures you control"),
#: Death Pit Offering's own enters-the-battlefield trigger, the identical
#: sentence. `_UNTAP_ALL_YOU_CONTROL_RE`'s own shape, substituting CR
#: 701.21a's sacrifice for an untap - same "you control" restriction, same
#: `_parse_mass_type_qualifier` qualifier grammar.
_SACRIFICE_ALL_YOU_CONTROL_RE = re.compile(
    r"^sacrifice all (?P<qualifier>.+?) you control\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s35")
def _parse_sacrifice_all_you_control_clause(sentence: str) -> TargetedClause | None:
    """`_SACRIFICE_ALL_YOU_CONTROL_RE`'s shape - CR 701.21a: to sacrifice a
    permanent is to move it, as its controller, from the battlefield directly
    to its owner's graveyard - not targeted, so every matching permanent the
    controller has right now goes simultaneously (CR 608.2f), with no
    legality recheck to make and no choice to offer: "all" leaves nothing to
    decide, unlike a counted "sacrifice a creature" cost."""
    match = _SACRIFICE_ALL_YOU_CONTROL_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    type_matches = _parse_mass_type_qualifier(match.group("qualifier"))
    if type_matches is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        for permanent in list(game.battlefield):
            if permanent.zone is not Zone.BATTLEFIELD:
                continue
            if game.controller_of(permanent).username != controller.username:
                continue
            if type_matches(game.characteristics_of(permanent)):
                game.sacrifice(permanent)

    return effect


#: Uneasy Alliance: "Exile enchanted creature." - a Sacrifice-this-Aura
#: activated ability's own first clause. CR 601.2h/113.7a: the Aura leaves the
#: battlefield paying its own cost, before the ability it granted itself no
#: longer needs it ever resolves, so "enchanted creature" can only be read
#: through `_attached_object`'s existing last-known-attachment fallback
#: (`CardState.last_known_attached_to`) - the same one Enchanted River's
#: Grasp's "tap enchanted creature" already relies on for its own trigger.
#: "Destroy equipped creature." is the identical template on an Equipment's
#: own sacrifice ability and is read the same way, though none of the pool's
#: printings need it yet.
_DESTROY_OR_EXILE_ATTACHED_RE = re.compile(
    r"^(?P<verb>destroy|exile) (?:enchanted|equipped|fortified) "
    r"(?:creature|permanent|land|artifact)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s35")
def _parse_destroy_or_exile_attached_clause(clause: str) -> TargetedClause | None:
    """`_DESTROY_OR_EXILE_ATTACHED_RE`'s shape."""
    match = _DESTROY_OR_EXILE_ATTACHED_RE.fullmatch(clause.strip())
    if match is None:
        return None
    verb = match.group("verb").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        attached = _attached_object(game, stack_object)
        if attached is None:
            return
        if verb == "exile":
            game.exile_permanent(attached)
        else:
            game.destroy(attached)

    return effect


#: Oblivion Stone's own second activated ability: "Destroy each nonland
#: permanent without a fate counter on it, then remove all fate counters
#: from all permanents." - one CR 608.2c instruction in two clauses joined
#: by "then", the second an unconditional sweep of every permanent still on
#: the battlefield, not only the ones the first clause just destroyed.
_DESTROY_EACH_THEN_REMOVE_ALL_COUNTERS_RE = re.compile(
    r"^destroy each (?P<clause>.+? without a (?P<kind>[a-z]+) counter on it), "
    r"then remove all (?P=kind) counters from all permanents\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s25")
def _parse_destroy_each_then_remove_all_counters(text: str) -> AbilityEffect | None:
    """`_DESTROY_EACH_THEN_REMOVE_ALL_COUNTERS_RE`'s shape: destroy every
    matching permanent, then remove every counter of the named kind from
    every permanent still on the battlefield - including ones the first half
    did not touch, and including ones that never had the counter at all
    (CR 122: removing zero of a kind that is not there is simply nothing to
    remove, not an error).
    """
    match = _DESTROY_EACH_THEN_REMOVE_ALL_COUNTERS_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("clause"))
    if predicate is None:
        return None
    kind = match.group("kind").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        _destroy_matching(game, predicate, source)
        for permanent in list(game.battlefield):
            present = permanent.counters[kind]
            if present:
                permanent.remove_counters(kind, present)

    return effect


#: Culling Ritual: "Destroy each nonland permanent with mana value 2 or
#: less. Add {B} or {G} for each permanent destroyed this way." - the second
#: instruction counts the first's own result, the mirror image of Wrath of
#: the Skies (whose *first* instruction is the payment the *second* counts).
_DESTROY_EACH_THEN_ADD_MANA_PER_DESTROYED_RE = re.compile(
    r"^destroy each (?P<clause>.+?)\.\s*"
    r"add (?P<colors>\{[wubrgc]\}(?:\s+or\s+\{[wubrgc]\})+) for each permanent destroyed "
    r"this way\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s20")
def _parse_destroy_each_then_add_mana_per_destroyed(text: str) -> Effect | None:
    """`_DESTROY_EACH_THEN_ADD_MANA_PER_DESTROYED_RE`'s shape.

    The colour of each unit of mana is the controller's own choice (CR
    601.2b's kind of choice, made as the spell resolves), asked once per
    permanent destroyed rather than once for the whole batch - "for each
    permanent destroyed this way" counts mana in per-unit terms (CR 107.4),
    and nothing pins every unit to the same colour. `DecisionKind.CHOOSE_A_
    QUALITY` is the kind CR 614.12a's own "choose a color" already asks
    through; reused here with `options` narrowed to the two colours this
    card actually offers rather than all five.
    """
    match = _DESTROY_EACH_THEN_ADD_MANA_PER_DESTROYED_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("clause"))
    if predicate is None:
        return None
    symbols = tuple(
        dict.fromkeys(s.upper() for s in _MANA_SYMBOL_RE.findall(match.group("colors")))
    )
    if len(symbols) < 2:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        destroyed = _destroy_matching(game, predicate, spell)
        if destroyed <= 0:
            return
        player = game.controller_of(spell)
        pool = player.mana_pool
        for _ in range(destroyed):
            decision = Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=player.username,
                prompt=f"choose a color for {spell.name}'s mana",
                source=spell.name,
                source_id=source_id_of(spell),
                options=symbols,
            )
            value = game.ask(decision)
            assert isinstance(value, str)
            pool.add(Color(value))

    return effect


def each_player_sacrifices_colored_permanents(game: "Game", spell: CardState) -> None:
    """`_EACH_PLAYER_SACRIFICES_COLORED_RE`'s shape.

    CR 608.2f: the action is processed for every player. Nothing about
    *which* permanents each player sacrifices is a choice - it is "all" of a
    fixed description, not "a" or "N of their choice" - so there is no
    CR 101.4 APNAP order to get right or wrong here; `game.players_in_game`
    is walked only for a stable, repeatable order, the same reasoning
    `each_player_exiles_sacrifices_and_returns_creatures` above already
    documents for its own "each player" steps. Each player's own candidates
    are snapshotted before any of them are sacrificed, so one player's
    sacrifice (and whatever it triggers) cannot change what a later player's
    own step still sees.
    """
    for player in game.players_in_game:
        controlled = [
            permanent
            for permanent in list(game.battlefield)
            if permanent.controller == player.username
            and bool(game.characteristics_of(permanent).colors)
        ]
        for permanent in controlled:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)


#: "Exile all creatures. Each player may put any number of creature cards
#: from their hand onto the battlefield. Then put all cards exiled this way
#: into their owners' hands. Exile `<this>`." - Worlds Within Worlds. Four
#: sentences, one CR 608.2c instruction: the exiled set is CR 607.1
#: anaphora ("cards exiled this way") back to the first sentence's own
#: exile, and the battlefield-bound cards from the second sentence are
#: excluded from it - only what stays in exile at the end goes to hand.
_EXILE_ALL_CREATURES_THEN_HAND_REFILL_RE = re.compile(
    r"^exile all creatures\.\s*"
    r"each player may put any number of creature cards from their hand "
    r"onto the battlefield\.\s*"
    r"then put all cards exiled this way into their owners'? hands\.\s*"
    r"exile (?:this (?:card|spell|sorcery)|[a-z' ,-]+)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s6")
def _parse_exile_all_creatures_then_hand_refill_clause(text: str) -> Effect | None:
    """`_EXILE_ALL_CREATURES_THEN_HAND_REFILL_RE`'s shape, or `None`."""
    if _EXILE_ALL_CREATURES_THEN_HAND_REFILL_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        exiled = [
            game.exile_permanent(state) for state in list(game.battlefield) if state.is_creature
        ]
        exiled = [state for state in exiled if state.zone is Zone.EXILE]
        # "Each player may put any number of creature cards from their hand
        # onto the battlefield" - a wholly separate pool of cards from what
        # the first sentence just exiled (which step 3 below returns to
        # hand unconditionally, whatever a player does here).
        for player in game.players:
            while True:
                candidates = [
                    state for state in player.hand if state.zone is Zone.HAND and state.is_creature
                ]
                if not candidates:
                    break
                taken = game.may(
                    player,
                    "put a creature card from your hand onto the battlefield",
                    source=spell.name,
                    source_id=source_id_of(spell),
                    cards=tuple(candidates),
                )
                if not taken:
                    break
                chosen_id = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt="choose a creature card to put onto the battlefield",
                        source=spell.name,
                        source_id=source_id_of(spell),
                        amount=1,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                assert isinstance(chosen_id, tuple)
                chosen = next(state for state in candidates if state.id == chosen_id[0])
                game.put_onto_battlefield(chosen, player.username)
        # "Then put all cards exiled this way into their owners' hands" -
        # every creature step 1 exiled, unconditionally (CR 111.8: a token
        # that never actually reached exile is skipped, since it has no
        # owner's hand to return to).
        for state in exiled:
            if state.zone is Zone.EXILE:
                game.return_to_hand(state)
        # CR 201.5's own self-reference: "Exile Worlds Within Worlds." -
        # the identical shape Burning Wish's own "Exile Burning Wish."
        # already needs `_resolve_top`'s own `spell.zone is Zone.EXILE`
        # check for (CR 608.2n's graveyard step then finds no spell left
        # on its way there).
        if spell.zone is Zone.STACK:
            game.exile_cards([spell])

    return effect


# --------------------------------------------------------------------------
# Wave W6: Fatal Push's Revolt line, Prismatic Ending's Converge, and Toxic
# Deluge's "pay X life" additional cost feeding a mass -X/-X
# --------------------------------------------------------------------------

#: "<Destroy/Exile> target ... if it has mana value N or less.\nRevolt —
#: <same verb> that ... if it has mana value M or less instead if a permanent
#: left the battlefield under your control this turn." Read as one CR 608.2c
#: instruction: the numbers themselves are not read here at all - Fatal
#: Push's real work already happened in `machines/targeting.py`'s own
#: `_read_revolt_mana_value_override`, which bakes both thresholds into the
#: `TargetRequirement` that `Game.legal_target` re-checks on resolution
#: (CR 608.2b) and consults live Revolt state for (an ability word, CR
#: 207.2c). All this clause has to do is recognise the two-paragraph shape so
#: the whole ability is not thrown away as an unreadable second sentence, and
#: hand back the same unconditional destroy/exile verb every other "target
#: ..." clause in this file already uses - the conditional part of "if it has
#: mana value N or less" is enforced entirely by the targeting layer, not by
#: this effect.
#:
#: The label itself is optional here, not required: `_prepare_effect_
#: clauses`'s own ability-word strip (CR 207.2c, `_strip_ability_word_
#: labels`) already removes "Revolt — " from `whole` before this ever sees
#: it, the same way `_COUNTER_INSTEAD_IF_POWER_RE` already treats Stubborn
#: Denial's own "Ferocious — " as optional - kept optional rather than
#: dropped outright so this still matches text that reached it some other
#: way, unstripped.
_REVOLT_DESTROY_OR_EXILE_RE = re.compile(
    r"^(?P<verb>destroy|exile) (?P<phrase>target .+?) if it has mana value \d+ or less\."
    r"\s*(?:revolt\s*[—-]\s*)?(?P=verb) that .+? if it has mana value \d+ or less instead if a "
    r"permanent left the battlefield under your control this turn\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_revolt_destroy_or_exile_clause(effect_text: str) -> Effect | None:
    """`_REVOLT_DESTROY_OR_EXILE_RE`'s shape, or `None` if this is not it."""
    match = _REVOLT_DESTROY_OR_EXILE_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    return (
        destroy_ability_targets
        if match.group("verb").lower() == "destroy"
        else exile_ability_targets
    )


#: Suspend Aggression: "Exile target nonland permanent and the top card of
#: your library. For each of those cards, its owner may play it until the
#: end of their next turn." Read whole: the second sentence's "those cards"
#: is CR 607.1 anaphora over *both* objects the first sentence exiled - a
#: targeted permanent and a self-referential library card in the same
#: breath - which `split_effect_clauses`'s own period/`"and"` cuts would
#: otherwise scatter across clauses no per-clause reader shares state
#: between.
#:
#: `PlayPermission.player` is each card's own **owner** (CR 108.3), not the
#: resolving spell's controller - the one shape `_parse_exile_then_play_
#: permission_clauses` (this file's general "exile ..., you may play it"
#: combinator) does not cover, since every one of its own printings grants
#: the permission to the *controller* who did the exiling. `expires_end_of_
#: next_turn=True` ties the grant to `PlayPermission.player` (`Game.
#: begin_turn_for`'s own check is `permission.player == username`), which is
#: exactly "their own next turn" for whichever player that is - an opponent
#: whose permanent was exiled, or this spell's own controller for the
#: library card, independently.
_EXILE_TARGET_NONLAND_AND_TOP_OWNER_MAY_PLAY_RE = re.compile(
    r"^exile (?P<phrase>target nonland permanent) and the top card of your library\.\s*"
    r"for each of those cards, its owner may play it until the end of their next turn\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_exile_target_and_top_owner_may_play_clause(effect_text: str) -> Effect | None:
    """`_EXILE_TARGET_NONLAND_AND_TOP_OWNER_MAY_PLAY_RE`'s shape, or `None`."""
    match = _EXILE_TARGET_NONLAND_AND_TOP_OWNER_MAY_PLAY_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        source = spell.card.name
        exiled: list[CardState] = []
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                moved = game.exile_permanent(target)
                if moved.zone is Zone.EXILE:
                    exiled.append(moved)
        if controller.library:
            moved = game.exile_permanent(controller.library[0])
            if moved.zone is Zone.EXILE:
                exiled.append(moved)
        for card in exiled:
            if card.owner is None:
                continue
            game.grant_play_permission(
                card,
                card.owner,
                action=PlayAction.PLAY,
                source_name=source,
                until_end_of_turn=False,
                expires_end_of_next_turn=True,
            )

    return effect


#: "Destroy target creature. If it wasn't attacking, its controller draws a
#: card." - Prophesied End's own two sentences, `_parse_anaphoric_clause_
#: pair`'s own shape with a combat-state gate (CR 506.4's own attacking
#: status) between the destruction and the rider. No off-set second printing
#: of this exact wording was found; recorded rather than asserted in
#: `docs/engine-coverage.md`, and generality is instead the general "if it
#: wasn't `<combat state>`" gate this reads off the board, not a literal
#: match on Prophesied End's own sentence.
_IF_IT_WASNT_ATTACKING_RE = re.compile(r"^if it wasn'?t attacking,\s*(?P<rest>.+)$", re.IGNORECASE)


def _parse_destroy_then_if_not_attacking_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_IT_WASNT_ATTACKING_RE`'s shape; see the banner above."""
    verb_match = _DESTROY_TARGET_RE.fullmatch(first)
    if verb_match is None:
        return None
    if not _targets_understood(
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=True
    ):
        return None
    cond_match = _IF_IT_WASNT_ATTACKING_RE.fullmatch(second.strip())
    if cond_match is None:
        return None
    subject_match = _ANAPHORIC_SUBJECT_RE.fullmatch(cond_match.group("rest").strip())
    if subject_match is None:
        return None
    consequence = _parse_referent_clause(subject_match.group("rest"))
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        referent = game.controller_of(target)
        power = game.power_of(target)
        was_attacking = game.is_attacking(target)
        game.destroy(target)
        if target.zone is Zone.BATTLEFIELD:
            return
        if not was_attacking:
            consequence(game, referent, power, source, source_id_of(stack_object))

    return effect


#: "Destroy target `<X>`. If that permanent was a[n] `<quality>`, draw a
#: card." - Budding Insurgent's own consequence; the real, off-set printing
#: with the identical "draw a card" consequence is Nissa's Defeat's own
#: wording ("If that permanent was a Nissa planeswalker, draw a card.") -
#: also in this pool, so genuine off-pool proof of the shape instead comes
#: from Liliana's Defeat's own second consequence, "her controller loses N
#: life" ("her" being the destroyed planeswalker, read by its own last-known
#: controller rather than the caster - CR 603.10a/704.8's look-back, the same
#: source `_COUNTER_COUNT_CLAUSE`'s own "it had no -1/-1 counters on it"
#: reads). "That permanent" checked against the same `permanent_description`
#: grammar `_EACH_SACRIFICES_OF_THEIR_CHOICE_RE` already reads, snapshotted
#: before the destruction the same way `_parse_anaphoric_clause_pair`
#: snapshots its own referent's controller and power.
_IF_THAT_PERMANENT_WAS_A_RE = re.compile(
    rf"^if that permanent was an? (?P<quality>.+?),\s*"
    rf"(?:draw (?P<n>{COUNT}) cards?"
    rf"|(?:his|her|its|their) controller loses (?P<life>{COUNT}) life)\.?$",
    re.IGNORECASE,
)


def _parse_destroy_then_if_that_permanent_was_draw_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_THAT_PERMANENT_WAS_A_RE`'s shape; see the banner above."""
    verb_match = _DESTROY_TARGET_RE.fullmatch(first)
    if verb_match is None:
        return None
    if not _targets_understood(
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=True
    ):
        return None
    cond_match = _IF_THAT_PERMANENT_WAS_A_RE.fullmatch(second.strip())
    if cond_match is None:
        return None
    requirement = permanent_description(cond_match.group("quality"))
    if requirement is None:
        return None
    draw_amount = parse_count(cond_match.group("n")) if cond_match.group("n") else None
    life_amount = parse_count(cond_match.group("life")) if cond_match.group("life") else None
    if draw_amount is None and life_amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        matches = requirement.rejects(target, controller.username, game) is None
        target_controller_username = game.controller_of(target).username
        game.destroy(target)
        if target.zone is Zone.BATTLEFIELD:
            return
        if not matches:
            return
        if draw_amount is not None:
            game.draw_cards(controller, draw_amount)
        elif life_amount is not None:
            game.lose_life(game.player(target_controller_username), life_amount)

    return effect


#: "Exile target `<X>`. If that permanent's mana value was N or less, return
#: it to the battlefield tapped under your control. Exile it at the
#: beginning of the next end step." - Vindictive Triumph's whole text. The
#: MV-conditional gate is the same shape Carnivorous Canopy's own "If that
#: permanent's mana value was 3 or less, proliferate." reads (a different,
#: real off-set consequence); no off-set second printing of this exact
#: combined return-then-delayed-re-exile consequence was found - recorded
#: rather than asserted, in `docs/engine-coverage.md`.
_EXILE_IF_MV_RETURN_THEN_RE_EXILE_RE = re.compile(
    r"^exile target (?P<desc>.+?)\.\s*if that permanent'?s mana value was (?P<mv>\d+) or "
    r"less, return it to the battlefield tapped under your control\.\s*"
    r"exile it at the beginning of the next end step\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s11", for_spell=True)
def _parse_exile_if_mv_return_then_re_exile_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_EXILE_IF_MV_RETURN_THEN_RE_EXILE_RE`'s shape; see the banner above."""
    match = _EXILE_IF_MV_RETURN_THEN_RE_EXILE_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(
        f"target {match.group('desc').strip()}", count_agnostic=True, battlefield_only=True
    ):
        return None
    threshold = int(match.group("mv"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        source_id = (
            stack_object.id if isinstance(stack_object, CardState) else stack_object.source_id  # type: ignore[union-attr]
        )
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        mana_value = target.mana_value
        game.exile_permanent(target)
        if target.zone is not Zone.EXILE or mana_value > threshold:
            return
        entered = game.put_onto_battlefield(target, controller.username, tapped=True)
        if entered.zone is not Zone.BATTLEFIELD:
            return
        trigger = anaphoric_delayed_trigger(
            "Exile it at the beginning of the next end step.",
            subject=entered,
            controller=controller.username,
            source_id=source_id,
            source_name=source_name,
            game=game,
        )
        if trigger is not None:
            game.create_delayed_trigger(trigger)

    return effect


#: "return it/that card/that permanent/that creature to the battlefield[
#: tapped][ transformed][ under its owner's/your control][ with [an
#: additional] `<n>` `<kind>` counter(s) on it]." - the return half of
#: Ephemerate's own "Exile target creature you control, then return it to
#: the battlefield under its owner's control." (CR 608.2c: one instruction in
#: two sentences), and of the same "blink" idiom wherever else a card states
#: it as a direct instruction rather than through a delayed trigger -
#: `machines/delayed.return_subject_to_battlefield_under_owner` already
#: covers Phelia's own "at the beginning of the next end step" variant, and
#: `machines/keywords.persist_return`/`earthbend` cover the two keyworded
#: shapes; none of the three reach this regex, and this one does not reach
#: them. `fullmatch` only, and no bare "return it to the battlefield." with
#: none of the four optional groups - that shape names no controller at all
#: and CR 110.2a leaves it to whoever the effect names elsewhere, which is
#: not something a lone regex on this one sentence can decide, so it is left
#: unread (see `_UNREAD_RETURN_TO_BATTLEFIELD_RE` below) rather than guessed.
#:
#: The trailing counter rider is Daydream's own "... under its owner's
#: control with a +1/+1 counter on it" - the identical CR 122.1
#: counter-placed-as-it-arrives shape `_RETURN_FROM_YOUR_GRAVEYARD_TO_
#: BATTLEFIELD_WITH_COUNTER_RE` already reads for the graveyard-targeted
#: family, read here too since a blinked permanent arrives exactly the same
#: way a reanimated one does (CR 614.12, 604.1a).
_RETURN_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?:it|them|that (?:card|permanent|creature)|those (?:cards|permanents|creatures))"
    r" to the battlefield"
    r"(?P<tapped> tapped)?"
    r"(?P<transformed> transformed)?"
    r"(?: under (?P<control>its owner's|their owners?'?s?|your) control)?"
    rf"(?: with an? (?:additional )?(?:(?P<counter_n>{COUNT}) )?(?P<counter>[a-z0-9+/-]+) "
    r"counters? on (?:it|them))?\.?$",
    re.IGNORECASE,
)


def _parse_exile_then_return_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Exile target X, then return it to the battlefield ..." as one CR
    608.2c instruction, or `None` if this shape does not match.

    The exile half is `_EXILE_TARGET_RE`, exactly the shape `exile_ability_
    targets` reads alone - CR 608.2b's target-legality recheck belongs only
    to it, since "it" in the second sentence is CR 400.7's anaphora back to
    whatever the first sentence found, not a target of its own (the same
    reasoning `_parse_anaphoric_clause_pair` already documents for "its
    controller ...").

    `Game.exile_permanent` then `Game.put_onto_battlefield` are the same two
    primitives `each_player_exiles_sacrifices_and_returns_creatures` already
    uses for Living End, so what comes back is CR 400.7's genuine new object:
    a fresh `zone_change_stamp`, no memory of its counters (CR 122.2), and
    summoning-sick again (CR 302.6, 508.1a) - `move_to`'s battlefield branch
    sets that unconditionally and this function never touches it.

    CR 110.2a is why the controller is read off the card's own words rather
    than defaulted to whoever controls the resolving spell or ability: "If an
    effect instructs a player to put an object onto the battlefield, that
    object enters the battlefield under that player's control unless the
    effect states otherwise" - Ephemerate states otherwise ("under its
    owner's control"), so `exiled.owner`, not the caster, is who `Game.
    put_onto_battlefield` is called with. Owner and controller are never
    collapsed into one question: a creature blinked out from under an
    opponent's control returns to the *opponent*, not to whoever cast
    Ephemerate, exactly when the card says "its owner's control", and to the
    caster only when it says "your control" instead.
    """
    return_match = _RETURN_TO_BATTLEFIELD_RE.fullmatch(second.strip())
    if return_match is None:
        return None
    exile_match = _EXILE_TARGET_RE.fullmatch(first.strip())
    if exile_match is None:
        return None
    if not _targets_understood(exile_match.group("phrase"), count_agnostic=True):
        return None

    tapped = return_match.group("tapped") is not None
    transformed = return_match.group("transformed") is not None
    control = return_match.group("control")
    counter_word = return_match.group("counter")
    counter_kind = _counter_kind(counter_word) if counter_word else None
    counter_n_word = return_match.group("counter_n")
    counter_amount = (
        ((parse_count(counter_n_word) if counter_n_word else 1) or 1) if counter_word else 0
    )

    owners_control = control is not None and control.lower() != "your"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        exiled_cards: list[CardState] = []
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move; nothing to return.
            exiled_cards.append(exiled)
        # "Exile two target creatures ..., then return them" (Gone Fishing,
        # Displace): every card is exiled first and all of them return as
        # one event (CR 603.6a), so each newcomer's enters ability sees the
        # others.
        with game.entering_together():
            for exiled in exiled_cards:
                owner = exiled.owner or controller
                new_controller = owner if owners_control else controller
                # CR 712.14a: "transformed" is how it *enters*, not something
                # done to it afterwards - the difference is CR 306.5b's
                # loyalty counters, which are put on as it enters and read
                # off the face that is up. Transforming after the fact left a
                # planeswalker back face on the battlefield at 0 loyalty,
                # dead to CR 704.5i.
                permanent = game.put_onto_battlefield(
                    exiled, new_controller, tapped=tapped, transformed=transformed
                )
                if counter_kind is not None and permanent.zone is Zone.BATTLEFIELD:
                    game.add_counters(permanent, counter_kind, counter_amount)

    return effect


#: Stubborn Denial's second sentence: "Ferocious — If you control a creature
#: with power 4 or greater, counter that spell instead." The leading word is
#: an *ability word* (CR 207.2c: "Ability words appear in italics at the
#: beginning of some abilities ... they have no special rules meaning"), so it
#: is accepted and discarded rather than matched by name - any future card
#: printing the same conditional upgrade under a different ability word reads
#: the same way. "Instead" is what makes this one instruction with the
#: sentence before it rather than a second counter: it replaces CR 118.12a's
#: "unless its controller pays" outcome, it does not run after it.
_COUNTER_INSTEAD_IF_POWER_RE = re.compile(
    r"^(?:[A-Za-z' ]+ — )?if you control a creature with power (?P<power>\d+) or greater, "
    r"counter that spell instead$",
    re.IGNORECASE,
)


def _parse_counter_unless_pays_then_condition_upgrade_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Stubborn Denial's whole card as one CR 608.2c instruction: "Counter
    target noncreature spell unless its controller pays {1}. Ferocious — If
    you control a creature with power 4 or greater, counter that spell
    instead."

    Read as a pair on purpose. Taken separately the second sentence would be a
    second counter of the same spell, which is not what "instead" means: the
    condition *replaces* the first sentence's CR 118.12a outcome, so when it
    holds nobody is offered the payment at all.

    The condition is checked as this spell resolves, not as it was cast
    (CR 608.2: "the spell's instructions are followed in the order written"),
    and it reads the *computed* power off `Game.power_of` (CR 613.4, CR 613.5)
    rather than the printed one, so a pumped creature counts.
    """
    if not for_spell:
        return None
    unless = _COUNTER_UNLESS_PAYS_RE.fullmatch(first.strip())
    upgrade = _COUNTER_INSTEAD_IF_POWER_RE.fullmatch(second.strip())
    if unless is None or upgrade is None:
        return None
    amount = int(unless.group("n"))
    threshold = int(upgrade.group("power"))
    unless_effect = _counter_unless_pays_effect(amount)

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        # CR 613.5: "creature" is layer 4's answer, not the printed type line -
        # an animated land with power 4 satisfies ferocious. One board for the
        # whole sweep; `Game.power_of` recomputes it per call.
        board = game.computed_board()
        big = any(
            (chars := board.of(state)).is_creature
            and chars.power is not None
            and chars.power >= threshold
            for state in game.permanents_controlled_by(controller.username)
        )
        if not big:
            unless_effect(game, spell)
            return
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is not None:
                game.counter(target)

    return effect


#: "If it doesn't have suspend, it gains suspend." - the rider Delay, Suspend,
#: Jhoira of the Ghitu and Taigam, Master Opportunist all print after putting
#: time counters on a card in exile. "It" is CR 400.7's anaphor for the card
#: the sentence before just exiled.
_GAINS_SUSPEND_RE = re.compile(r"^if it doesn'?t have suspend, it gains suspend\.?$", re.IGNORECASE)

#: "If the spell is countered this way, exile it with `<n>` time counters on it
#: instead of putting it into its owner's graveyard" (Delay) - CR 608.2c's
#: own "later text ... may modify the meaning of earlier text": the counter
#: of the sentence before is redirected to exile, with counters.
_COUNTERED_THIS_WAY_EXILE_WITH_COUNTERS_RE = re.compile(
    rf"^if (?:that|the) spell is countered this way, exile it with (?P<n>{COUNT}) "
    r"time counters? on it instead of putting it into its owner'?s graveyard\.?$",
    re.IGNORECASE,
)

#: "put `<n>` time counters on it" - the second half of Suspend's own "Exile
#: target creature and put two time counters on it.", which
#: `split_effect_clauses` has already cut at " and ".
_PUT_TIME_COUNTERS_ON_IT_RE = re.compile(
    rf"^(?:and )?put (?P<n>{COUNT}) time counters? on it\.?$", re.IGNORECASE
)


#: "it gains suspend" (Epochrasite) beside the conditional "if it doesn't have
#: suspend, it gains suspend" (Taigam, Master Opportunist) - the bare form is
#: printed only where the exiled card cannot already have suspend.
_GAINS_SUSPEND_EITHER_RE = re.compile(
    r"^(?:if it doesn'?t have suspend, )?it gains suspend\.?$", re.IGNORECASE
)

#: "exile it with three time counters on it" (Epochrasite's dies trigger, "it"
#: the dead creature) and "exile the spell you cast with four time counters on
#: it" (Taigam's cast trigger, the spell whose cast triggered it).
_EXILE_REFERENT_WITH_TIME_COUNTERS_RE = re.compile(
    rf"^(?:then )?exile (?P<ref>it|the spell you cast|that spell) with (?P<n>{COUNT}) "
    r"time counters? on it\.?$",
    re.IGNORECASE,
)

_COPY_IT_RE = re.compile(r"^copy (?:it|that spell)\.?$", re.IGNORECASE)


def _parse_exile_referent_into_suspend_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """A triggered ability's own referent exiled with time counters, then
    granted suspend (CR 702.62a, CR 702.62b), one CR 608.2c instruction:

    - "exile it with N time counters on it and it gains suspend" - "it" is
      the ability's source, found by CR 603.10a's look-back only while it is
      still the graveyard incarnation its dies event made (CR 400.7e,
      `_dead_self_found`).
    - "copy it, then exile the spell you cast with N time counters on it. If
      it doesn't have suspend, it gains suspend." - the spell whose cast
      triggered the ability (`ability.event`), copied first (CR 707.10), then
      exiled off the stack (CR 701.13a, not countered) while it is still there.

    Ability-only: both referents are found through `AbilityOnStack`.
    """
    if for_spell:
        return None
    start = index
    copy_first = _COPY_IT_RE.fullmatch(clauses[index].strip()) is not None
    if copy_first:
        index += 1
    if index + 1 >= len(clauses):
        return None
    exile = _EXILE_REFERENT_WITH_TIME_COUNTERS_RE.fullmatch(clauses[index].strip())
    if exile is None or not _GAINS_SUSPEND_EITHER_RE.fullmatch(clauses[index + 1].strip()):
        return None
    counters = parse_count(exile.group("n"))
    if counters is None:
        return None
    self_referent = exile.group("ref").lower() == "it" and not copy_first

    def exile_referent_into_suspend(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        if self_referent:
            source = _dead_self_found(game, ability)
            if source is None or source.zone is Zone.BATTLEFIELD:
                return
            game.exile_permanent(source)
            grant_suspend(game, source, counters)
            return
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        if copy_first:
            game.copy_spell(spell, ability.controller)
        game.exile_from_stack(spell)
        grant_suspend(game, spell, counters)

    return index + 2 - start, exile_referent_into_suspend


def _parse_exile_into_suspend_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Two printed shapes, one mechanic - exile a card with time counters on
    it, then "If it doesn't have suspend, it gains suspend." (CR 702.62a,
    702.62b), read as one CR 608.2c instruction:

    - Delay: "Counter target spell. If the spell is countered this way, exile
      it with three time counters on it instead of putting it into its
      owner's graveyard. If it doesn't have suspend, it gains suspend." The
      exile is a rider on the *counter* (CR 701.6a): a spell that can't be
      countered (CR 113.6g) stays on the stack, so "countered this way" is
      false and nothing is exiled, counted or granted.
    - Suspend: "Exile target creature and put two time counters on it. If it
      doesn't have suspend, it gains suspend." - a permanent exiled off the
      battlefield (CR 406.2), counters placed once it is there.

    In both, a target gone by resolution (CR 608.2b) is simply not touched.
    A triggered ability's own referent (Epochrasite, Taigam) is
    `_parse_exile_referent_into_suspend_clauses`.
    """
    referent = _parse_exile_referent_into_suspend_clauses(clauses, index, for_spell=for_spell)
    if referent is not None:
        return referent
    if index + 2 >= len(clauses):
        return None
    first = clauses[index].strip()
    second = clauses[index + 1].strip()
    if not _GAINS_SUSPEND_RE.fullmatch(clauses[index + 2].strip()):
        return None
    countered = _COUNTERED_THIS_WAY_EXILE_WITH_COUNTERS_RE.fullmatch(second)
    if countered is not None and _COUNTER_TARGET_SPELL_RE.fullmatch(first):
        counters = parse_count(countered.group("n"))
        if counters is None:
            return None

        def counter_into_suspend(game: "Game", stack_object: "StackObject") -> None:
            for reference in stack_object.targets:
                if not reference.is_card:
                    continue
                target = next((item for item in game.stack if item.id == reference.card_id), None)
                if not isinstance(target, CardState):
                    continue
                game.counter(target, to_exile=True)
                if target in game.stack:
                    continue  # CR 113.6g: not countered, so not "this way".
                grant_suspend(game, target, counters)

        return 3, counter_into_suspend

    put = _PUT_TIME_COUNTERS_ON_IT_RE.fullmatch(second)
    exile = _EXILE_TARGET_RE.fullmatch(first)
    if put is None or exile is None:
        return None
    if not _targets_understood(exile.group("phrase"), count_agnostic=False, battlefield_only=True):
        return None
    counters = parse_count(put.group("n"))
    if counters is None:
        return None

    def exile_into_suspend(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            game.exile_permanent(target)
            grant_suspend(game, target, counters)

    return 3, exile_into_suspend


def _hand_exile_quality_matcher(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for `_HAND_EXILE_RE`'s "a `<quality>` card", or `None` if
    this wave cannot read it.

    Fail-closed on purpose: an unrecognised quality refuses the whole clause
    (`_parse_imprint_clause`) rather than asking "you may exile a card from
    your hand" about the wrong cards - see `_unreadable_imprint_quality` for
    what happens to a quality this refuses, which is not silence.
    """
    lowered = quality.strip().lower()
    if lowered in _HAND_EXILE_COLOR_WORDS:
        color = _HAND_EXILE_COLOR_WORDS[lowered]
        if color is None:
            return lambda state: not state.colors
        return lambda state: color in state.colors
    # "a nonland card" (Semblance Anvil): the negation of a card type word -
    # every card whose types lack it.
    negated = lowered.startswith("non")
    try:
        card_type = Type(lowered[3:] if negated else lowered)
    except ValueError:
        return None
    if negated:
        return lambda state: card_type not in state.types
    return lambda state: card_type in state.types


def _hand_exile_mv_matcher(mv: str | None, cmp: str | None) -> Callable[[CardState], bool]:
    """CR 202.3's mana value, bounded by `_HAND_EXILE_RE`'s optional "with mana
    value N or greater/less" - both directions, unlike `_bounded_quality_
    matcher`'s search-only ceiling, because Ugin's Labyrinth's own restriction
    is a floor ("or greater").
    """
    if mv is None:
        return lambda state: True
    bound = int(mv)
    if cmp == "greater":
        return lambda state: state.mana_value >= bound
    return lambda state: state.mana_value <= bound


def _hand_exile_description(match: re.Match[str]) -> str:
    """`_HAND_EXILE_RE`'s clause as the noun phrase the card prints, for a prompt.

    **Word order is the whole job.** The quality is an adjective ("colorless")
    and the mana-value bound qualifies the *card*, so the noun sits between
    them - "a colorless card with mana value 7 or greater", which is exactly
    how Ugin's Labyrinth prints it (verified with `resolve_cards`). Building
    the description as "`<quality>` with mana value ..." and letting each
    prompt append "card" afterwards put the noun last, and published
    "exile a colorless with mana value 7 or greater card from your hand" to a
    live seat. The full phrase, article and all, is therefore assembled here
    once instead of half here and half at each prompt.
    """
    description = f"{match.group('quality').strip()} card"
    if match.group("mv"):
        description = f"{description} with mana value {match.group('mv')} or {match.group('cmp')}"
    return f"{_article(description)} {description}"


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_imprint_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Imprint — When this land enters, you may exile a colorless card with
    mana value 7 or greater from your hand." (Ugin's Labyrinth), read off the
    ability's own printed text so no registry row is needed.

    CR 608.2d: nobody is *made* to exile anything, so this is a plain "you
    may" - `DecisionKind.MAY` - with `affirmative_is_legal` set to whether a
    legal card exists in hand at all: if none does, the choice is not merely a
    bad idea, it is impossible, and CR 608.2d forbids choosing it (the same
    `affirmative_is_legal` shape `may_pay_life` already uses for CR 119.4).
    *Which* card, once "yes" is legal and chosen, is `DecisionKind.CHOOSE_
    CARDS`, the same CR 608.2d machinery `seasoned_pyromancer`'s discard and
    `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`'s "put a
    permanent card into your hand" both use.

    The exiled card is annotated `ExileMarker.IMPRINTED`, pointing back at the
    resolving permanent's own id - the only thing a later "exiled with this
    land" ability (`ManaCondition.imprinted`, `Game.card_imprinted_on`) can
    mean, since "imprint" itself carries no rules meaning of its own
    (CR 207.2c).
    """
    match = _HAND_EXILE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    quality_matches = _hand_exile_quality_matcher(match.group("quality"))
    if quality_matches is None:
        return None
    mv_matches = _hand_exile_mv_matcher(match.group("mv"), match.group("cmp"))
    description = _hand_exile_description(match)

    def matches(state: CardState) -> bool:
        return quality_matches(state) and mv_matches(state)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = [state for state in player.hand if matches(state)]
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=f"exile {description} from your hand",
            source=source_name,
            affirmative_is_legal=bool(candidates),
            # The qualifying cards, so the yes/no is answered knowing what is
            # on offer. The hand is a hidden zone (CR 400.2), so a client
            # cannot work them out from the game state; `Game.ask` labels them
            # by name on the way out.
            cards=tuple(state.id for state in candidates),
            source_id=source_id_of(stack_object),
        )
        if not game.ask(decision):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"choose {description} to exile",
                source=source_name,
                amount=1,
                cards=tuple(state.id for state in candidates),
                source_id=source_id_of(stack_object),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in candidates}
        chosen = by_id[chosen_ids[0]]
        player.cards_in(Zone.HAND).remove(chosen)
        chosen.move_to(Zone.EXILE)
        chosen.exile_annotation = ExileAnnotation(
            marker=ExileMarker.IMPRINTED, owner=chosen.owner, linked_permanent_id=source_id
        )
        game.exile.append(chosen)

    return effect


_CAST_EXILED_CARD_FREE_RE = re.compile(
    r"^you may cast the exiled card without paying its mana cost$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_cast_exiled_card_free_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "You may cast the exiled card without paying its mana cost." (Living
    Lore's "If you do" consequence): "the exiled card" is the card exiled with
    this permanent as it entered (CR 607.2a), cast as the ability resolves
    (CR 608.2g). The source may already be gone (it was sacrificed first), which
    is fine - the link is by id."""
    if for_spell or _CAST_EXILED_CARD_FREE_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=False)
        controller = game.controller_of(stack_object).username
        for card in game.cards_exiled_with(source_id, None):
            game.may_cast_during_resolution(
                card,
                controller,
                prompt=f"cast {card.name} without paying its mana cost",
                source=source_name,
                source_id=source_id_of(stack_object),
                source_name=source_name,
                rule="CR 608.2g",
            )

    return effect


#: "You may cast it from your graveyard this turn." (Skyclave Shade's landfall
#: trigger, its source card sitting in the graveyard): CR 601.3's permission to
#: cast the ability's own source from the graveyard, for the rest of the turn
#: (CR 611.2a). A source that has since left the graveyard is a new object
#: (CR 400.7) and is handed nothing.
_CAST_SELF_FROM_GRAVEYARD_RE = re.compile(
    r"^you may cast (?:it|this \w+) from your graveyard this turn$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_cast_self_from_graveyard_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    if for_spell or _CAST_SELF_FROM_GRAVEYARD_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        game.grant_play_permission(
            source,
            game.controller_of(stack_object).username,
            action=PlayAction.CAST,
            source_name=stack_object.source_name,
            zone=Zone.GRAVEYARD,
            rule="CR 601.3",
        )

    return effect


#: A die-roll results table (CR 706.3a): "<instructions>. Roll a dN. <low>[-<high>] | <what
#: happens> ..." - read by `machines/d20_tables.py` (Wizard's Spellbook, Chaos Channeler,
#: Swarming Goblins, The Deck of Many Things' modified roll).


@ABILITY_TEXT.rung("s1")
def _parse_roll_table_text(text: str) -> AbilityEffect | None:
    """`d20_tables.roll_table_effect`'s shape, or None."""
    if "roll a" not in text.lower() or " | " not in text:
        return None
    return roll_table_effect(text)


#: Unstable Glyphbridge: "for each player, choose a creature with power 2 or
#: less that player controls. Then destroy all creatures except creatures
#: chosen this way." - CR 608.2d's resolution-time choices (no targets, CR
#: 115.1), made by the controller in APNAP order (CR 101.4), then one CR
#: 701.8a destroy of every other creature at once.
_FOR_EACH_PLAYER_CHOOSE_THEN_DESTROY_REST_RE = re.compile(
    r"^for each player, (?:you )?choose a creature"
    r"(?: with (?P<stat>power|toughness|mana value) (?P<n>\d+) or (?P<dir>less|greater))? "
    r"that player controls\. then destroy all (?:other )?creatures"
    r"(?: except (?:creatures|those) chosen this way)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s1")
def _parse_destroy_all_but_chosen_per_player_text(text: str) -> AbilityEffect | None:
    """`_FOR_EACH_PLAYER_CHOOSE_THEN_DESTROY_REST_RE`'s shape. A player with
    no creature meeting the quality is skipped as a chooser (CR 608.2d)."""
    if not text.lower().startswith("for each player, ") or "destroy all" not in text.lower():
        return None
    match = _FOR_EACH_PLAYER_CHOOSE_THEN_DESTROY_REST_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    stat = (match.group("stat") or "").lower()
    bound = int(match.group("n")) if match.group("n") else 0
    at_most = (match.group("dir") or "less").lower() == "less"

    def qualifies(game: "Game", creature: CardState) -> bool:
        if not stat:
            return True
        if stat == "mana value":
            value: float | None = creature.mana_value
        elif stat == "power":
            value = game.power_of(creature)
        else:
            value = game.toughness_of(creature)
        if value is None:
            return False
        return value <= bound if at_most else value >= bound

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..named_choice_rows import choose_and_record_object

        board = game.computed_board()
        kept: set[UUID] = set()
        for player in _players_in_apnap_order(game):
            candidates = [
                state
                for state in game.permanents_controlled_by(player.username)
                if board.of(state).is_creature and qualifies(game, state)
            ]
            picked = choose_and_record_object(
                game,
                ability,
                candidates,
                prompt=f"choose a creature {player.username} controls",
            )
            if picked is not None:
                kept.add(picked.id)
        doomed = [
            state
            for state in game.battlefield
            if board.of(state).is_creature and state.id not in kept
        ]
        for creature in doomed:
            if creature.zone is Zone.BATTLEFIELD:
                game.destroy(creature)

    return effect


#: "Destroy this enchantment." (Experimental Frenzy's `{3}{R}` ability) - CR 701.8a's
#: destroy on the ability's own source, a self-reference (CR 201.5, CR 115.1a) rather
#: than a target. Ability-only: a spell is never a permanent on the battlefield.
_DESTROY_SELF_RE = re.compile(r"^destroy this \w+$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_destroy_self_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_DESTROY_SELF_RE`'s shape: destroy the ability's source if it is still
    the permanent on the battlefield (CR 400.7: a source that already left is a
    new object, so there is nothing to destroy)."""
    if for_spell or _DESTROY_SELF_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.destroy(source)

    return effect


#: Every noun `_sacrifice_restriction` accepts after "this " - a card type
#: (CR 205.2a) or the bare word "permanent" itself. Slayer of the Wicked's
#: "target Vampire, Werewolf, or Zombie" kind of compound restriction is not
#: read here any more than it is by `_targets_understood` - a restriction
#: this wave cannot pin down to a single `Type` fails the whole clause
#: (see `_sacrifice_restriction`), which is what earns it a `ConditionalClause
#: Notice` instead of silently offering to sacrifice anything at all.
_SACRIFICE_SELF_NOUNS: frozenset[str] = frozenset({member.value for member in Type}) | {"permanent"}


#: "`<quantity>` [other ]`<description>`" - "a creature", "two Islands",
#: "three other nonland permanents", "one or more Treasures" - and "another
#: `<description>`", which is "one other". The description is read by
#: `machines/targeting.permanent_description`, the grammar an edict's "sacrifices
#: a `<description>` of their choice" already shares with a "target ..." phrase.
_COUNTED_SACRIFICE_RE = re.compile(
    rf"^(?:(?P<another>another)|(?P<quantity>{QUANTITY})\s+(?P<other>other\s+)?)\s*"
    r"(?P<description>.+)$",
    re.IGNORECASE,
)


def _sacrifice_restriction(
    restriction: str, *, allow_it: bool = False
) -> _SacrificeRestriction | None:
    """`restriction` - the text between "sacrifice" and the following period -
    read as "this `<type>`" (the permanent bearing the ability itself,
    Sanctum of Ugin) or a counted description of permanents the player
    controls: "another creature" (Disciple of Freyalise), "a creature"
    (Grist, the Hunger Tide's "-2"), "two Islands" (Leviathan), "three other
    nonland permanents" (Scavenger's Talent), "one or more Treasures".

    The candidates are read off the battlefield at resolution time - never at
    parse time, since what is on the battlefield changes between then and
    resolution - and off the *computed* battlefield (CR 613.5): "sacrifice a
    creature" may be paid with a land animated into one. "Another" and
    "other" exclude the ability's own source. Only the player's own
    permanents count (CR 701.21a: "A player can't sacrifice ... something
    that's a permanent they don't control").

    The count is `numbers.parse_quantity`'s. X here appears in no cost, so
    CR 107.3f lets the controller choose it as the ability resolves: it is
    read as "however many the player sacrifices", at least one for the
    sacrifice to have been done at all (CR 118.12's "if/when you do"), and a
    later X or "that many" reads the number chosen through the count channel
    (`that_many`). "That many" is refused - this reader has no count to take
    it from - so the whole clause fails closed rather than sacrificing a
    guessed amount.

    Anything else - a description `permanent_description` cannot read -
    comes back `None`, fail-closed.
    """
    printed = restriction.strip()
    restriction = printed.lower()
    if (allow_it and restriction == "it") or restriction.startswith("this "):
        # Furnace Scamp's "you may sacrifice it": in an ability's own "you may
        # sacrifice <it>. If you do, ..." the pronoun is the source itself.
        # Only `allow_it` callers may read it so: elsewhere "it" is some
        # earlier sentence's object (a token just created, say).
        noun = restriction.removeprefix("this ").strip()
        if restriction != "it" and noun not in _SACRIFICE_SELF_NOUNS:
            return None

        def self_candidates(game: "Game", player: Player, source_id: UUID) -> list[CardState]:
            permanent = game.find_by_id(source_id)
            if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
                return []
            return [permanent]

        return _SacrificeRestriction(True, self_candidates, _ONE_PERMANENT)

    # The printed case, not the lowered one: a subtype reads capitalised ("Islands").
    match = _COUNTED_SACRIFICE_RE.fullmatch(printed)
    if match is None:
        return None
    if match.group("another") is not None:
        quantity: Quantity | None = _ONE_PERMANENT
    else:
        quantity = parse_quantity(match.group("quantity"))
    if quantity is None or quantity.source is QuantitySource.THAT_MANY:
        return None
    if quantity.source is QuantitySource.X and quantity.expression is not None:
        # "X, where X is ..." defines X (CR 107.3c); this reader does not.
        return None
    if quantity.amount is not None and quantity.amount < 1:
        return None
    excludes_source = match.group("another") is not None or match.group("other") is not None
    subtype = _bare_subtype_word(match.group("description"))
    requirement = None if subtype is not None else permanent_description(match.group("description"))
    or_requirements: list[Any] | None = None
    if subtype is None and requirement is None:
        or_requirements = _or_description_requirements(match.group("description"))
        if or_requirements is None:
            return None

    def counted_candidates(game: "Game", player: Player, source_id: UUID | None) -> list[CardState]:
        own = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if not (excludes_source and permanent.id == source_id)
        ]
        if subtype is not None:
            # CR 613.5: the computed subtypes, so a type-changed land counts.
            return computed_permanents(
                game, own, lambda chars: subtype in {word.lower() for word in chars.subtypes}
            )
        if or_requirements is not None:
            return [
                p
                for p in own
                if any(req.rejects(p, player.username, game) is None for req in or_requirements)
            ]
        assert requirement is not None
        return [p for p in own if requirement.rejects(p, player.username, game) is None]

    return _SacrificeRestriction(False, counted_candidates, quantity)


def _or_description_requirements(description: str) -> list[Any] | None:
    """Two or more single permanent descriptions joined by "or a"/"or an" -
    "a token or a land" (West Wind Avatar's own "you may sacrifice a token or
    a land") - each read on its own by `machines.targeting.permanent_
    description` and combined as a disjunction: the sacrificed permanent must
    satisfy at least one of them.

    This is the identical "or a"/"or an" restatement `_SEARCH_DESCRIPTION_
    JOIN_RE` already splits a library search's own "a basic Plains card or a
    creature card ..." on (Starfield Shepherd) - the same English construction,
    read here for a sacrifice cost's description instead of a search's. A bare
    "token or land" (no restated article) is not this shape and is left to
    `permanent_description` itself, which already reads a plain comma/"or"
    list of single words with no article between them.

    `None` when there is only one part (nothing to split - `permanent_
    description` gets first refusal on that, which is why `_sacrifice_
    restriction` only calls this once `permanent_description` has already
    failed) or when any part does not read on its own, so an unrecognised
    half fails the whole restriction closed rather than sacrificing against a
    narrower requirement than what was printed.
    """
    parts = _SEARCH_DESCRIPTION_JOIN_RE.split(description)
    if len(parts) < 2:
        return None
    requirements = [permanent_description(part.strip()) for part in parts]
    if any(requirement is None for requirement in requirements):
        return None
    return requirements


def _sacrifice_is_payable(quantity: Quantity, candidates: list[CardState]) -> bool:
    """CR 118.3: "A player can't pay a cost without having the necessary
    resources to pay it fully." An exact count needs that many candidates; a
    range ("one or more", "any number of", "up to N") needs at least one,
    since sacrificing nothing is not doing it (CR 118.12's "if you do")."""
    if quantity.exact and quantity.amount is not None:
        return len(candidates) >= quantity.amount
    return len(candidates) >= max(quantity.minimum or 0, 1)


#: "Sacrifice `<restriction>`. Return `<quantity>` cards from your graveyard
#: to your hand, where X is `<expr>`. [Exile this card.]" - Bound's own whole
#: effect (Bound // Determined), generalised past its own printed wording:
#: the sacrifice restriction is `_sacrifice_restriction`'s general "a
#: `<type>`"/"another `<type>`"/counted-subtype grammar (not hardcoded to
#: "creature"), the returned quantity is `parse_quantity`'s ("up to X", "up
#: to `<n>`", a fixed count), and the magnitude expression is read through
#: `_is_referent_color_count_expression` - so a future printing sharing the
#: shape with a different sacrificed type or exact count reads for free. The
#: trailing "Exile this card"/"Exile this spell"/"Exile it" is optional and,
#: when present, is CR 201.5's reference to this very spell (the same
#: "Exile <this>" shape `_parse_reveal_from_outside_the_game_into_hand_
#: clause`'s own Burning Wish family already reads on a resolving spell) -
#: CR 608.2n's own default graveyard step never runs for it.
#:
#: Read whole, ahead of the comma/period split: the second sentence's "that
#: `<type>`"/"it" is CR 400.7 anaphora back to what the first sentence just
#: sacrificed, and no per-clause parser sees far enough back to answer it -
#: the same reason `_DRAW_AND_GAIN_OFF_SACRIFICED_RE` above is read whole
#: rather than split.
_MANDATORY_SACRIFICE_THEN_RETURN_TO_HAND_RE = re.compile(
    rf"^sacrifice (?P<restriction>[^.]+)\.\s*"
    rf"return {quantity_pattern('quantity')} cards? from your graveyard to your hand"
    rf"{where_x_pattern('expr')}\.\s*"
    r"(?P<exile>exile (?:this card|this spell|it)\.?)?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s15", for_spell=True)
def _parse_mandatory_sacrifice_then_return_to_hand_clause(
    text: str, *, for_spell: bool
) -> Effect | None:
    """`_MANDATORY_SACRIFICE_THEN_RETURN_TO_HAND_RE`'s shape - Bound's own
    whole effect.

    Spell-only: "Exile this card" (CR 201.5) names the resolving spell
    itself, which only a spell still on the stack has occasion to say about
    itself.

    CR 701.21a's sacrifice has no failure mode among the player's own
    permanents, but CR 609.3 ("If an effect attempts to do something
    impossible, it does only as much as possible") governs the case this
    reader's own restriction can leave empty: no legal permanent to
    sacrifice at all. Nothing is sacrificed, the second sentence's anaphora
    has no referent, and CR 107.2 answers a magnitude that can't be
    determined with zero - X is 0 and nothing is returned, rather than the
    whole effect failing closed.

    The returned cards are chosen freely from the whole graveyard (CR
    608.2d) up to X, including the very permanent the first sentence just
    sacrificed - it is sitting right there in the graveyard by the time this
    second sentence runs. "Up to" always permits choosing fewer, including
    none.
    """
    if not for_spell:
        return None
    match = _MANDATORY_SACRIFICE_THEN_RETURN_TO_HAND_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    restriction = _sacrifice_restriction(match.group("restriction"))
    if restriction is None:
        return None
    quantity = parse_quantity(match.group("quantity"))
    if quantity is None:
        return None
    expr = match.group("expr")
    if quantity.source is QuantitySource.X:
        if expr is None or not _is_referent_color_count_expression(expr):
            return None
    elif expr is not None:
        # A fixed/ranged count printing its own unrelated "where X is ..."
        # tail is not this shape - fail closed rather than ignoring it.
        return None
    exiles_self = match.group("exile") is not None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        source_name = spell.name
        source_id = source_id_of(spell)
        candidates = restriction.candidates(game, controller, spell.id)
        sacrificed: CardState | None = None
        if candidates:
            chosen = _choose_permanents_to_sacrifice(
                game,
                controller,
                restriction,
                candidates,
                source_name=source_name,
                source_id=source_id,
            )
            if chosen:
                sacrificed = chosen[0]
                game.sacrifice(sacrificed)
        if quantity.source is QuantitySource.X:
            wanted_max = 0 if sacrificed is None else _referent_color_count(sacrificed)
        else:
            wanted_max = quantity.amount or 0
        pool = list(controller.graveyard)
        wanted = min(wanted_max, len(pool))
        if wanted > 0:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        "choose a card to return to your hand"
                        if wanted == 1
                        else f"choose up to {wanted} cards to return to your hand"
                    ),
                    source=source_name,
                    source_id=source_id,
                    amount=wanted,
                    exact=False,
                    cards=tuple(state.id for state in pool),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in pool}
            for card_id in chosen_ids:
                state = by_id.get(card_id)
                if state is not None and state.zone is Zone.GRAVEYARD:
                    game.return_to_hand(state)
        if exiles_self:
            game.exile_cards([spell])

    return effect


#: The "if you do" consequence's signature once the optional cost has been
#: paid: the resolving object's controller, the sacrificed permanent's power
#: read before it left the battlefield (`None` only the way `Game.power_of`
#: is already `None` - an unresolved `*` characteristic-defining ability, not
#: a magnitude-free consequence, which never calls this argument at all), and
#: the source name for `Game.may`/`Game.ask` prompts a nested search still
#: needs.
_SacrificeConsequence = Callable[["Game", Player, int | None, str, str | None], None]


def _parse_sacrifice_consequence(consequence: str) -> _SacrificeConsequence | None:
    """The "If you do, `<consequence>`" half, read as either a magnitude-
    threaded pair of clauses ("you gain X life and draw X cards, where X is
    that creature's power", Disciple of Freyalise) or a plain mandatory
    search ("search your library for a colorless creature card, reveal it,
    put it into your hand, then shuffle", Sanctum of Ugin - mandatory because
    CR 118.12's own "you may" already gated the sacrifice; nothing asks a
    second "you may" for the consequence itself, which is why this reaches
    `_search_and_place_for` with `optional=False` rather than going through
    `_parse_search_clause`'s "you may " subject group).
    """
    consequence = consequence.strip().rstrip(".").strip()

    magnitude_match = re.fullmatch(
        r"(?P<body>.+?),\s*where X is (?P<expr>.+)", consequence, re.IGNORECASE | re.DOTALL
    )
    if magnitude_match is not None:
        if not _is_referent_power_expression(magnitude_match.group("expr")):
            return None
        run = _parse_x_magnitude_body(magnitude_match.group("body"))
        if run is None:
            return None

        def magnitude_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            run(game, player, max(power, 0) if power is not None else 0)

        return magnitude_effect

    search_match = _SEARCH_AND_PUT_RE.fullmatch(consequence)
    if search_match is not None:
        search_run = _search_and_place_for(search_match, optional=False)
        if search_run is None:
            return None

        def search_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            search_run(game, player, source, source_id)

        return search_effect

    draw_match = _DRAW_N_CARDS_RE.fullmatch(consequence)
    if draw_match is not None:
        count = parse_count(draw_match.group("count"))
        if count is None:
            return None

        def draw_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            game.draw_cards(player.username, count)

        return draw_effect

    return None


@ABILITY_TEXT.rung("s19", for_spell=False)
@SPELL_TEXT.rung("s15", for_spell=True)
def _parse_conditional_sacrifice_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """ "You may sacrifice `<restriction>`. If you do, `<consequence>`." (CR
    118.12), read off the ability's own printed text so no registry row is
    needed - Disciple of Freyalise's and Sanctum of Ugin's own defect before
    this wave: both used to resolve doing nothing, with nothing anywhere
    recording that a choice had gone unoffered.

    The "you may" is `DecisionKind.MAY` with `affirmative_is_legal` set to
    whether a legal permanent to sacrifice actually exists right now (see
    `_sacrifice_restriction`) - the same shape `_parse_imprint_clause` and
    `may_pay_life` already use for their own CR 608.2d/CR 119.4 impossible-
    option cases. Once "yes" is chosen, CR 118.12 says the consequence runs
    regardless of anything downstream - CR 701.21a's sacrifice has no failure
    mode for a permanent the player controls, so "did you do it" is only ever
    "did you say yes", never a second check on the board afterward.
    """
    match = _MAY_SACRIFICE_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if for_spell and match.group("restriction").strip().lower() == "it":
        return None
    restriction = _sacrifice_restriction(match.group("restriction"), allow_it=True)
    if restriction is None:
        return None
    consequence_text = match.group("consequence")
    if re.search(r"\botherwise\b", consequence_text, re.IGNORECASE):
        # "Otherwise, ..." (Giant Opportunity) is a second branch on the same
        # payment; reading only the "if you do" half would drop it.
        return None
    single = restriction.quantity.exact and restriction.quantity.amount == 1
    if not single and re.search(r"where x is", consequence_text, re.IGNORECASE):
        # "that creature's power" names one sacrificed permanent.
        return None
    # "... with mana value equal to 1 plus the sacrificed enchantment's mana
    # value" (Enigmatic Incarnation) reads the permanent this very sentence
    # sacrificed, so it is handed that mana value rather than looking for a
    # cost that was never paid.
    mana_value_search = _sacrificed_mana_value_search(consequence_text)
    consequence = (
        None if mana_value_search is not None else _parse_sacrifice_consequence(consequence_text)
    )
    clause: TargetedClause | None = None
    if consequence is None and mana_value_search is None:
        # Any other instruction ("untap this creature", "return a creature
        # card from your graveyard to the battlefield ...") is read by the
        # ordinary clause parser and run against the same resolving object.
        # "copy that spell and you may choose new targets for the copy"
        # (Mica, Reader of Ruins) is one CR 707.10c instruction the
        # clause splitter's bare "and" cut would slice in two.
        # "this creature deals 3 damage to that player" (Furnace Scamp) is
        # CR 607.1 anaphora back to the trigger's own event, read here
        # because the ordinary clause parser has no event to resolve it from.
        clause = _parse_copy_that_spell_clause(
            consequence_text, for_spell=for_spell
        ) or _parse_damage_that_player_clause(consequence_text, for_spell=for_spell)
        clause = clause or (
            parse_mixed_effect_for_spell(consequence_text)  # type: ignore[assignment]
            if for_spell
            else parse_mixed_effect(consequence_text)
        )
        if clause is None:
            return None
    prompt = f"sacrifice {match.group('restriction').strip()}"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = restriction.candidates(game, player, source_id)
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=prompt,
            source=source_name,
            affirmative_is_legal=_sacrifice_is_payable(restriction.quantity, candidates),
            source_id=source_id_of(stack_object),
        )
        if not game.ask(decision):
            return
        chosen = _choose_permanents_to_sacrifice(
            game,
            player,
            restriction,
            candidates,
            source_name=source_name,
            source_id=source_id_of(stack_object),
        )
        if not chosen:
            return
        power = game.power_of(chosen[0]) if len(chosen) == 1 else None
        # CR 608.2h: read while it is still a permanent.
        sacrificed_mana_value = game.last_known_mana_value(chosen[0])
        for permanent in chosen:
            game.sacrifice(permanent)
        # CR 608.2c: "If you do, draw that many cards" (Sephiroth, One-Winged
        # Angel) reads how many were actually sacrificed.
        game.record_count(len(chosen))
        if mana_value_search is not None:
            mana_value_search(
                game, player, sacrificed_mana_value, source_name, source_id_of(stack_object)
            )
        elif consequence is not None:
            consequence(game, player, power, source_name, source_id_of(stack_object))
        elif clause is not None:
            clause(game, stack_object)  # type: ignore[arg-type]

    return effect


# --------------------------------------------------------------------------
# "Exile target card from a graveyard. When a creature card is exiled this
# way, <consequence>." (CR 603.12) - Agatha's Soul Cauldron's `{T}` ability.
# --------------------------------------------------------------------------
#
# A second CR 603.12 shape, alongside `_parse_reflexive_sacrifice_clause`
# above: the action is unconditional (an ordinary "exile target card", no
# "you may"), and what makes the reflexive ability exist is not a player's
# choice but *what kind of card* the first sentence actually exiled - CR
# 603.12's own "trigger based on whether the trigger event ... occurred" reads
# here as "was the exiled card a creature card", checked against the object
# `game.exile_permanent` just moved, once, right after it moves. Reusing
# `create_reflexive_trigger` rather than building a second reflexive-ability
# primitive, per the trap this wave was warned about.
#
# `profile_for_text`'s `_REFLEXIVE_CLAUSE_TAIL` cuts this same "when ... this
# way," tail before reading the outer ability's own target, so the activation
# only ever announces the first sentence's "target card from a graveyard" -
# the second target ("target creature you control") is announced later, when
# the reflexive ability itself goes on the stack (CR 603.3d), exactly the way
# `_parse_reflexive_sacrifice_clause`'s own consequence target is.

_EXILE_TARGET_REFLEXIVE_CREATURE_RE = re.compile(
    r"^exile (?P<phrase>target card from a graveyard)\.\s*"
    r"when a creature card is exiled this way,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s32")
def _parse_exile_target_card_reflexive_creature_counter(text: str) -> AbilityEffect | None:
    """`_EXILE_TARGET_REFLEXIVE_CREATURE_RE`'s shape - Agatha's Soul
    Cauldron's `{T}` ability.

    CR 400.7/CR 700.4: whether the exiled object "is a creature card" is read
    off the card itself, not the battlefield's layer 6 (it never reaches the
    battlefield at all), so `Type.CREATURE in target.types` - CR 113.6c's
    off-battlefield grant included - is checked on the object
    `game.exile_permanent` is about to move.
    """
    match = _EXILE_TARGET_REFLEXIVE_CREATURE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    consequence_text = match.group("consequence").strip()
    if parse_mixed_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        exiled_a_creature = False
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState):
                continue
            is_creature = Type.CREATURE in target.types
            game.exile_permanent(target)
            if is_creature:
                exiled_a_creature = True
        if not exiled_a_creature:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "you may exile your hand. If you do, `<consequence>`." - Herigast,
#: Erupting Nullkite's own cast trigger ("When you cast this spell, you may
#: exile your hand. If you do, draw three cards."). CR 118.12's "[A player]
#: may [do something]. If [that player] does, [effect]" reads exiling the
#: whole hand as the cost paid during this same resolution (CR 701.13a is
#: the exile keyword action; CR 608.2c moves the hand as one instruction,
#: `Game.exile_cards`'s own batch), never a discard's own graveyard
#: destination - the mana/life/energy "if you do" twins above pay a
#: resource, this one pays an action, but CR 118.12 reads all of them the
#: same way. `pay_consequence_effect` is shared with every other twin.
_MAY_EXILE_HAND_IF_YOU_DO_RE = re.compile(
    r"^you may exile your hand\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_may_exile_hand_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_MAY_EXILE_HAND_IF_YOU_DO_RE`'s shape, or `None`."""
    match = _MAY_EXILE_HAND_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    consequence = pay_consequence_effect(match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may(
            player,
            "exile your hand",
            source=source_name,
            source_id=source_id_of(ability),
        )
        if not paid:
            return
        hand = list(player.hand)
        if hand:
            game.exile_cards(hand)
        consequence(game, ability)

    return effect


_FOR_EACH_OPPONENT_DESTROY_RE = re.compile(
    r"^for each opponent, destroy (?:up to one )?target (?P<desc>.+?) that player controls\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_for_each_opponent_destroy_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """ "For each opponent, destroy up to one target `<X>` that player
    controls." - the real, off-set printing Age of Ultron's own Saga chapter
    I ("destroy up to one target nonartifact creature that player
    controls."), and Lich's Relic's own reflexive consequence.
    """
    match = _FOR_EACH_OPPONENT_DESTROY_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.destroy(target)

    return effect


#: "exile `<target phrase>` from your graveyard. [If you do, ]copy it. You
#: may cast the copy[ without paying its mana cost]." and its "... from your
#: graveyard and copy it. ..." sibling - Jacob Frye's "exile up to one target
#: Assassin card or card with freerunning from your graveyard. If you do,
#: copy it. You may cast the copy.", Nashi, Moon's Legacy's "exile up to one
#: target legendary or Rat card from your graveyard and copy it. You may cast
#: the copy.", Demilich's and Founding the Third Path's "Copy it." form.
#:
#: CR 707.12: "An effect that instructs a player to cast a copy of an object
#: (and not just copy a spell) follows the rules for casting spells, except
#: that the copy is created in the same zone the object is in" - the card is
#: exiled first, so the copy is made in exile, and with no "without paying
#: its mana cost" its costs are paid (CR 601.2f-h). CR 707.10a: "If a copy of
#: a card is in any zone other than the stack or the battlefield, it ceases
#: to exist" - a copy not cast is removed. CR 707.10f: a cast copy of a
#: permanent spell becomes a token as it resolves (`Game.resolve_top`).
_EXILE_TARGET_CARD_COPY_IT_CAST_RE = re.compile(
    r"^exile (?:up to one )?target [^.]+? from (?:your|a) graveyard"
    r"(?:\s+and copy it|\.\s*(?:if you do,\s*)?copy it)\.\s*"
    r"you may cast the copy(?P<free> without paying its mana cost)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_exile_target_card_copy_it_cast_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_TARGET_CARD_COPY_IT_CAST_RE`'s shape, or `None`.

    The target itself is `machines/targeting.profile_for_text`'s ordinary
    reading of the phrase (CR 601.2c/603.3d). "If you do" (CR 608.2c) is the
    exile actually happening: a target gone by resolution (CR 608.2b) or none
    chosen for "up to one" means nothing is copied. The cast is `Game.
    may_cast_during_resolution` - a `MAY` (CR 608.2d), then the real casting
    machine with the copy's own targets and costs.
    """
    match = _EXILE_TARGET_CARD_COPY_IT_CAST_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    free = match.group("free") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD
        ]
        if not targets:
            return
        for original in game.exile_cards(targets):
            if original.zone is not Zone.EXILE:
                continue  # CR 608.2c: "if you do" - it was not exiled.
            copy = CardState(
                card=original.card,
                zone=Zone.EXILE,
                controller=controller.username,
                owner=controller.username,  # CR 112.2a
                is_copy=True,
            )
            game.exile.append(copy)
            game.may_cast_during_resolution(
                copy,
                controller.username,
                prompt=(
                    f"cast the copy of {copy.name}"
                    + (" without paying its mana cost" if free else "")
                ),
                source=source_name,
                source_id=source_id_of(ability),
                source_name=source_name,
                rule="CR 707.12",
                pays_mana_cost=not free,
            )
            if copy.zone is Zone.EXILE and copy in game.exile:
                game.exile.remove(copy)  # CR 707.10a

    return effect


#: "Exile up to one target nonland card of each card type from your
#: graveyard. Copy those cards. You may cast any number of spells with total
#: mana value `<n>` or less from among the copies without paying their mana
#: costs." - Uldaros Theorix's own ETB. The targeting itself is not read
#: here at all: `machines/targeting.py`'s own `_up_to_one_of_each_card_type_
#: profile` special-case builds the eight independent "up to one" per-type
#: requirements this whole-text shape needs (CR 601.2c), the same way
#: Earthbend's own target is special-cased there rather than in this file -
#: this parser only has to read what happens once those targets are chosen.
_EXILE_ONE_OF_EACH_TYPE_COPY_CAST_RE = re.compile(
    r"^exile up to one target nonland card of each card type from your graveyard\.\s*"
    r"copy those cards\.\s*"
    r"you may cast any number of spells with total mana value (?P<total>\d+) or less "
    r"from among the copies without paying their mana costs\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s22")
def _parse_exile_one_of_each_type_copy_cast_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_ONE_OF_EACH_TYPE_COPY_CAST_RE`'s shape, or `None`.

    CR 707.2/CR 707.12: each exiled card is copied into a fresh, uncast
    `CardState` in exile (`is_copy=True`), the identical "copy created in the
    zone the object is in" `_parse_copy_exiled_card_and_cast` already builds
    for Isochron Scepter, just once per exiled original instead of once for
    an imprinted card.

    CR 707.12a: "An effect that creates multiple copies and says a player
    'may cast' those objects allows that player to choose individually, for
    each of those objects, whether or not to cast it" - read here as one
    `Game.may_cast_during_resolution` per copy, asked in the fixed order the
    copies were made (itself the order the targets were resolved in, CR
    601.2c), each one narrowed by whatever is left of the total budget
    (`mana_value_below`, strict, so `remaining + 1` keeps a copy exactly
    `remaining` costly legal - CR 702.85a's identical "less than" bound).
    Unaffordable copies are skipped without a question - the same "an option
    CR 608.2d can't legally choose is never offered" `can_cast_during_
    resolution` already enforces for every other resolution-time cast.
    Permanent copies become tokens the moment they resolve (CR 111.13,
    CR 707.10f) entirely through the engine's own general spell-resolution
    path (`Game.resolve_top`'s `spell.is_copy` check) - nothing here has to
    ask for that reminder-text behaviour by name.
    """
    match = _EXILE_ONE_OF_EACH_TYPE_COPY_CAST_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    total_bound = int(match.group("total"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD
        ]
        if not targets:
            return
        exiled = game.exile_cards(targets)
        copies: list[CardState] = []
        for original in exiled:
            if original.zone is not Zone.EXILE:
                continue
            copy = CardState(
                card=original.card,
                zone=Zone.EXILE,
                controller=controller.username,
                owner=controller.username,  # CR 112.2a
                is_copy=True,
            )
            game.exile.append(copy)
            copies.append(copy)
        if not copies:
            return

        remaining_budget = total_bound
        for copy in copies:
            if copy.zone is not Zone.EXILE:
                continue
            if (copy.card.cmc or 0) >= remaining_budget + 1:
                continue
            cast = game.may_cast_during_resolution(
                copy,
                controller.username,
                prompt=(
                    f"cast the copy of {copy.name} without paying its mana cost "
                    f"(total mana value {remaining_budget} or less remaining)"
                ),
                source=source_name,
                source_id=source_id_of(ability),
                source_name=source_name,
                rule="CR 707.12",
                mana_value_below=remaining_budget + 1,
            )
            if cast is not None:
                remaining_budget -= copy.card.cmc or 0

        # CR 707.10a: any copy never cast (declined, or priced out of the
        # remaining budget) does not linger in exile once this ability is
        # done offering it.
        for copy in copies:
            if copy.zone is Zone.EXILE and copy in game.exile:
                game.exile.remove(copy)

    return effect


#: "Destroy up to one other target creature. Its controller amasses
#: `<subtype>` X, where X is that creature's power. If you controlled that
#: creature, draw a card." - Azog, Moria's Ruin's own enters trigger. Read
#: whole, ahead of the ordinary clause split, for the identical CR 400.7
#: anaphora reason `_parse_anaphoric_clause_pair` above already documents for
#: "its controller ..." - except this shape chains a *third* sentence off the
#: same referent ("if you controlled that creature"), which that pair reader
#: has no room for. `amass` is CR 701.47a's keyword action, performed by the
#: destroyed creature's own controller (the referent), not the caster - the
#: `amass()` function above already takes `controller` as a plain parameter
#: for exactly this, Bolg of the North's own amass just below reusing it the
#: same way for its own (self) controller.
_DESTROY_THEN_AMASS_BY_REFERENT_THEN_DRAW_IF_CONTROLLED_RE = re.compile(
    r"^destroy (?P<phrase>.*target.+?)\.\s*"
    r"its controller amasses (?P<subtype>[A-Za-z][a-z]*) x,\s*"
    r"where x is that creature'?s power\.\s*"
    r"if you controlled that creature, draw (?P<draw_n>a|one|\d+) cards?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_destroy_then_amass_by_referent_then_draw_if_controlled_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DESTROY_THEN_AMASS_BY_REFERENT_THEN_DRAW_IF_CONTROLLED_RE`'s shape.

    The referent's controller and last-known power are snapshotted **before**
    `Game.destroy` moves the target off the battlefield (CR 608.2i), the same
    order `_parse_anaphoric_clause_pair` already takes for its own "its
    controller gains life equal to its power" - reading either afterward
    would see `CardState.move_to`'s emptied husk. A legal target the destroy
    itself fails to move (CR 702.12b's indestructible) still had a controller
    and a power, so the amass and the conditional draw both still run (the
    printed rulings for this exact "destroy ... its controller ..." shape,
    quoted on `_parse_anaphoric_clause_pair`'s own docstring, say so). CR
    107.1b floors a negative last-known power at zero for the amass amount;
    Azog's own draw is a plain CR 121.1 draw, gated on whether *this*
    ability's own controller - not the destroyed creature's - is the one who
    controlled it before it left.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _DESTROY_THEN_AMASS_BY_REFERENT_THEN_DRAW_IF_CONTROLLED_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=True):
        return None
    subtype = match.group("subtype")
    draw_amount = parse_count(match.group("draw_n"))
    if draw_amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        caster = game.controller_of(stack_object).username
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        referent = game.controller_of(target).username
        power = game.power_of(target)
        game.destroy(target)
        amass(
            game,
            referent,
            subtype,
            max(power or 0, 0),
            source,
            source_id=source_id_of(stack_object),
        )
        if referent == caster:
            game.draw_cards(caster, draw_amount)

    return effect


#: "You may sacrifice another creature. When you do, `<this>` deals damage
#: equal to that creature's power to another target creature. If excess
#: damage was dealt this way, amass `<subtype>` X, where X is that excess
#: damage." - Bolg of the North's own enters trigger. CR 607.1's linked
#: abilities (the "When you do" clause refers only to the sacrifice this same
#: paragraph's own first sentence offered, CR 603.11's own "trigger condition
#: in the middle of the ability") is treated the identical CR 118.12 way
#: `_parse_conditional_sacrifice_clause` already treats a plain "If you do":
#: the sacrifice is an optional cost, paid (or not) when the ability
#: resolves, and everything after "when you do" runs only once it was.
#: Reuses that reader's own `_sacrifice_restriction`/`_sacrifice_is_payable`/
#: `_choose_permanents_to_sacrifice` primitives rather than a second copy of
#: CR 608.2d's impossible-option gating. CR 120.10's excess damage is read
#: the identical way `_parse_damage_then_empower_if_excess_clause` already
#: reads it for Violent Echoes, off `_lethal_amount_before_damage` taken
#: *before* `Game.deal_damage` runs; the only difference is the consequence
#: (`amass`, CR 701.47a, by this ability's own controller - the bare "amass
#: `<subtype>` X" names no referent the way Azog's own "its controller
#: amasses" does) rather than Violent Echoes' `empower_jace`.
_MAY_SACRIFICE_THEN_DAMAGE_THEN_AMASS_IF_EXCESS_RE = re.compile(
    r"^you may sacrifice (?P<restriction>[^.]+)\.\s*"
    r"when you do,\s*.*?\bdeals? damage equal to that creature'?s power to "
    r"(?P<phrase>.*target.+?)\.\s*"
    r"if excess damage was dealt (?:to that (?:permanent|creature) )?this way,\s*"
    r"amass (?P<subtype>[A-Za-z][a-z]*) x,\s*where x is that excess damage\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_may_sacrifice_then_damage_then_amass_if_excess_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_MAY_SACRIFICE_THEN_DAMAGE_THEN_AMASS_IF_EXCESS_RE`'s shape.

    Ability-only: CR 118.12's "you may" optional cost is asked at resolution
    (this text is the ability's own effect, not a cost printed before a
    colon), the same restriction `_parse_conditional_sacrifice_clause`
    already holds itself to for every other "you may sacrifice" shape.
    """
    if for_spell:
        return None
    whole = _strip_non_effect_preamble(text).strip()
    match = _MAY_SACRIFICE_THEN_DAMAGE_THEN_AMASS_IF_EXCESS_RE.fullmatch(whole)
    if match is None:
        return None
    restriction = _sacrifice_restriction(match.group("restriction"))
    if restriction is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    subtype = match.group("subtype")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        candidates = restriction.candidates(game, player, source_id)
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=f"sacrifice {match.group('restriction').strip()}",
            source=source_name,
            affirmative_is_legal=_sacrifice_is_payable(restriction.quantity, candidates),
            source_id=source_id_of(stack_object),
        )
        if not game.ask(decision):
            return
        chosen = _choose_permanents_to_sacrifice(
            game,
            player,
            restriction,
            candidates,
            source_name=source_name,
            source_id=source_id_of(stack_object),
        )
        if not chosen:
            return
        power = game.power_of(chosen[0]) if len(chosen) == 1 else None
        for permanent in chosen:
            game.sacrifice(permanent)
        if power is None:
            return
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        pre_lethal = _lethal_amount_before_damage(game, target)
        assert isinstance(stack_object, AbilityOnStack)
        dealt = game.deal_damage(target, max(power, 0), source=stack_object.source(game))
        if pre_lethal is None:
            return
        excess = dealt - pre_lethal
        if excess > 0:
            amass(
                game,
                player.username,
                subtype,
                excess,
                source_name,
                source_id=source_id_of(stack_object),
            )

    return effect


#: Hold for Ransom's granted "{7}: Hold for Ransom's controller sacrifices it and
#: draws a card." - once the Aura's name is read as the grant's source, "it" is
#: the Aura itself (the ransom is paid by the held creature's controller; the
#: Aura's controller is the one who sacrifices it and draws). The ability is the
#: enchanted creature's, so the Aura is whichever attached permanent states the
#: grant (CR 113.10a, CR 701.21a).
_AURA_CONTROLLER_SACRIFICES_IT_AND_DRAWS_RE = re.compile(
    r"^(?:this permanent|this creature|[A-Z][^.,]*?)'s controller "
    r"sacrifices it and draws a card\.?$"
)


@ABILITY_TEXT.rung("s36")
def _parse_granting_aura_sacrificed_and_draws(text: str) -> AbilityEffect | None:
    """`_AURA_CONTROLLER_SACRIFICES_IT_AND_DRAWS_RE`'s shape."""
    stripped = " ".join(text.split())
    if _AURA_CONTROLLER_SACRIFICES_IT_AND_DRAWS_RE.fullmatch(stripped) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        held = ability.source(game)
        if held is None:
            return
        for aura in list(game.battlefield):
            if aura.attached_to != held.id:
                continue
            if not any(
                "sacrifices it and draws a card" in line
                for line in game.characteristics_of(aura).abilities
            ):
                continue
            owner = game.controller_of(aura).username
            game.sacrifice(aura)
            if aura.zone is not Zone.BATTLEFIELD:
                game.draw_cards(owner, 1)

    return effect


#: "the blocking creature's controller sacrifices it at end of combat" - The
#: Ring's third ability (CR 701.54c), read as a delayed triggered ability (CR
#: 603.7, CR 511.2) about the blocking creature its own "becomes blocked by a
#: creature" trigger names. `_parse_delayed_timing_clause` has already split
#: off the timing; this is the verb phrase left over.
_BLOCKING_CREATURE_SACRIFICED_RE = re.compile(
    r"^the blocking creature's controller sacrifices (?:it|that creature)$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_blocking_creature_sacrificed_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "[At <timing>,] the blocking creature's controller sacrifices it [at
    <timing>]." - an ability only (a spell has no block event to read), whose
    "blocking creature" is its trigger event's blocker: a CR 509.1a blocking
    pair's `GameEvent.subject_id` is always the blocker, which is also what
    CR 509.3d's "becomes blocked by a creature" triggers once for.

    The delayed ability waits for the step (CR 511.2 for "end of combat") and
    sacrifices the blocker through its controller *then*
    (`SacrificedByItsController`, CR 701.21a), unless it has left the
    battlefield in the meantime (CR 603.7c)."""
    if for_spell:
        return None
    timing = _parse_delayed_timing_clause(clause)
    if timing is None:
        return None
    step, verb = timing
    if _BLOCKING_CREATURE_SACRIFICED_RE.fullmatch(verb) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.event is not TriggerEvent.BLOCKS or event.subject_id is None:
            return
        blocker = game.find_by_id(event.subject_id)
        if not isinstance(blocker, CardState) or blocker.zone is not Zone.BATTLEFIELD:
            return
        game.create_delayed_trigger(
            DelayedTrigger(
                text=clause,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=blocker.id,
                expected_zone=Zone.BATTLEFIELD,
                expected_stamp=blocker.zone_change_stamp,
                effect=sacrificed_by_its_controller,
            )
        )

    return effect


#: "exile any number of other nonland permanents you own and control" -
#: Yorion, Sky Nomad's untargeted choice (CR 107.1c), made as the ability
#: resolves. `<description>` is any permanent description
#: `targeting.permanent_description` reads; "other" leaves the source out;
#: the ownership/control tail narrows the candidates.
_EXILE_ANY_NUMBER_OF_YOUR_PERMANENTS_RE = re.compile(
    r"^exile any number of (?P<other>other )?(?P<description>.+?) "
    r"you (?P<relation>own and control|control)$",
    re.IGNORECASE,
)
#: "Return those cards to the battlefield [under their owner's control]" -
#: the verb half once `_parse_delayed_timing_clause` has taken the timing
#: off; CR 610.3c makes the owner's control the default when unsaid.
_RETURN_THOSE_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?:them|those cards|those permanents) to the battlefield"
    r"(?P<tapped> tapped)?(?: under (?:its|their) owners?'?s? control)?$",
    re.IGNORECASE,
)


def _parse_exile_any_number_of_your_permanents_then_delayed_return_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_EXILE_ANY_NUMBER_OF_YOUR_PERMANENTS_RE` followed by a delayed
    `_RETURN_THOSE_TO_BATTLEFIELD_RE` - Yorion's "exile any number of other
    nonland permanents you own and control. Return those cards to the
    battlefield at the beginning of the next end step."

    No target: the controller chooses among the candidates as the ability
    resolves (CR 107.1c - zero is an answer, and then nothing is delayed).
    What actually reached exile is remembered by id and exile stamp on
    `ReturnEachExiledToBattlefieldUnderOwner` (CR 603.7c); a token ceases to
    exist there (CR 704.5d) and so is never found again.
    """
    if index + 1 >= len(clauses):
        return None
    exile_match = _EXILE_ANY_NUMBER_OF_YOUR_PERMANENTS_RE.fullmatch(
        clauses[index].strip().rstrip(".")
    )
    if exile_match is None:
        return None
    description = exile_match.group("description").strip()
    requirement = (
        None
        if description.lower() in ("permanent", "permanents")
        else permanent_description(description)
    )
    if requirement is None and description.lower() not in ("permanent", "permanents"):
        return None
    timing = _parse_delayed_timing_clause(clauses[index + 1])
    if timing is None:
        return None
    step, verb = timing
    return_match = _RETURN_THOSE_TO_BATTLEFIELD_RE.fullmatch(verb.strip())
    if return_match is None:
        return None
    tapped = return_match.group("tapped") is not None
    excludes_source = exile_match.group("other") is not None
    must_own = exile_match.group("relation").lower().startswith("own")
    delayed_text = clauses[index + 1].strip().rstrip(".") + "."
    prompt = clauses[index].strip().rstrip(".")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
        controller = game.controller_of(stack_object).username
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller)
            if not (excludes_source and permanent.id == source_id)
            and (not must_own or permanent.owner == controller)
            and (requirement is None or requirement.rejects(permanent, controller, game) is None)
        ]
        if not candidates:
            return
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=prompt,
                source=source_name,
                source_id=source_id_of(stack_object),
                amount=len(candidates),
                exact=False,
                cards=tuple(permanent.id for permanent in candidates),
            )
        )
        assert isinstance(answer, tuple)
        chosen = [permanent for permanent in candidates if permanent.id in answer]
        exiled: list[CardState] = []
        for permanent in chosen:
            game.exile_permanent(permanent)
            if permanent.zone is Zone.EXILE:
                exiled.append(permanent)
        if not exiled:
            return
        game.create_delayed_trigger(
            DelayedTrigger(
                text=delayed_text,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=controller,
                source_id=source_id,
                source_name=source_name,
                effect=ReturnEachExiledToBattlefieldUnderOwner(
                    subjects=tuple(
                        (card_state.id, card_state.zone_change_stamp) for card_state in exiled
                    ),
                    tapped=tapped,
                ),
            )
        )

    return 2, effect


#: "exile the top card of that player's library" - Ragavan, Nimble Pilferer's
#: own second clause. "That player" is CR 607.1's within-one-ability anaphora
#: back to a combat-damage-to-a-player trigger's own event (CR 120.2a) - the
#: player the damage landed on - not a target the ability ever announces
#: (CR 601.2c never runs for it), so this reads `ability.event.player` rather
#: than `stack_object.targets` the way `_LOOK_AT_TOP_CARD_RE`'s "target
#: player's library" reads an actual target.
_EXILE_TOP_OF_THAT_PLAYERS_LIBRARY_RE = re.compile(
    r"^exile the top card of that player's library$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_exile_that_players_library_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): a spell has no `ability.event` to
    resolve "that player" against, and nothing in the pool prints this shape
    on a spell.
    """
    if for_spell:
        return None
    if not _EXILE_TOP_OF_THAT_PLAYERS_LIBRARY_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        username = event.player if event is not None else None
        if username is None:
            return
        player = game.player(username)
        if player.library:
            game.exile_permanent(player.library[0])

    return effect


#: "defending player exiles the top twenty cards of their library" - Ulamog,
#: the Ceaseless Hunger's own attack trigger. "Defending player" is CR
#: 508.5/508.6's anaphora back to the attack the trigger's own condition
#: ("Whenever Ulamog attacks") watched: the player, or - had the attack named
#: a planeswalker or a battle - that permanent's controller, worked out by
#: `machines.combat.defending_player` off the event's own `defender`
#: (`GameEvent.defender`, CR 508.1a). Not a target: CR 601.2c never runs for a
#: triggered ability with no printed "target", so this reads `ability.event`
#: exactly as `_parse_exile_that_players_library_clause` reads "that player"
#: off a different event field just above.
_DEFENDING_PLAYER_EXILES_TOP_N_RE = re.compile(
    rf"^defending player exiles the top (?P<count>{COUNT}) cards? of their library$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s28", for_spell=FORWARD)
def _parse_defending_player_exiles_top_n_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): a spell has no `ability.event` to
    resolve "defending player" against, and no spell in the pool attacks.
    """
    if for_spell:
        return None
    match = _DEFENDING_PLAYER_EXILES_TOP_N_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = parse_count(match.group("count"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.defender is None:
            return
        username = combat_rules.defending_player(game, event.defender)
        if username is None:
            return
        player = game.player(username)
        for card in player.library[:count]:
            game.exile_permanent(card)

    return effect


#: "Counter that spell." - Vexing Bauble's and Chalice of the Void's own
#: templated effect clause, both times following a `TriggerEvent.CAST_SPELL`
#: condition. "That spell" is **CR 607.1** linked-ability anaphora back to the
#: spell whose casting made the ability trigger, not something CR 601.2c ever
#: asked this ability's controller to choose as a target - the same
#: `ability.event`-not-`stack_object.targets` distinction
#: `_parse_exile_that_players_library_clause` right above draws for "that
#: player's library".
_COUNTER_THAT_SPELL_RE = re.compile(r"^counter that spell$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s28", for_spell=FORWARD)
def _parse_counter_that_spell_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """Ability-only (`for_spell=False`): a spell has no `ability.event` to
    resolve "that spell" against, and nothing in the pool prints this clause
    on a spell rather than a triggered ability.

    Read by shape rather than by card name, so a future card printing this
    exact clause after any `CAST_SPELL` condition is covered for free -
    unlike a `TRIGGER_EFFECTS` row keyed to one card, which cannot.
    """
    if for_spell:
        return None
    if not _COUNTER_THAT_SPELL_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        # **CR 701.6a**: "A countered spell is put into its owner's
        # graveyard" - by way of `Game.counter`, which also honours a
        # rebound or flashback spell's own replaced destination rather than
        # always the graveyard. A spell that has already left the stack
        # (countered first, or resolved ahead of this ability) is simply not
        # there to counter - the ordinary CR 608.2b "the target is gone"
        # outcome, even though this was never a target to begin with.
        if spell is not None and spell in game.stack:
            game.counter(spell)

    return effect


#: "Exile the top card of your library. You may play that card this turn."
#: (Invasion of Kaldheim's back face own discard trigger, Charforger's
#: identical activated-ability shape - both real, Modern/Pioneer-legal
#: printings) - a mandatory CR 400.2 exile (no "you may" on the exile
#: itself, unlike `_MAY_EXILE_TOP_CARD_RE`'s Daredevil, Man Without Fear
#: shape) followed by `_PLAY_PERMISSION_RE`'s own permission grant. Read as
#: two whole sentences rather than folded into `_prepare_effect_clauses`'s
#: per-clause split, so a future duration on the permission half (a bare
#: period boundary either way) is still `_PLAY_PERMISSION_RE`'s own to read.
_EXILE_TOP_CARD_MANDATORY_RE = re.compile(r"^exile the top card of your library$", re.IGNORECASE)


@ABILITY_TEXT.rung("s1")
def _parse_exile_top_card_then_play_permission_clause(effect_text: str) -> AbilityEffect | None:
    """`_EXILE_TOP_CARD_MANDATORY_RE` followed by `_PLAY_PERMISSION_RE`'s
    "that card" permission, or `None`."""
    sentences = [part.strip() for part in effect_text.strip().split(".") if part.strip()]
    if len(sentences) != 2:
        return None
    if _EXILE_TOP_CARD_MANDATORY_RE.fullmatch(sentences[0]) is None:
        return None
    permission = _PLAY_PERMISSION_RE.fullmatch(sentences[1])
    if permission is None or permission.group("subject").lower() != "that card":
        return None
    duration = _permission_duration(permission)
    if duration is None:
        return None
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        if not controller.library:
            return
        card = game.exile_permanent(controller.library[0])
        game.grant_play_permission(
            card,
            controller.username,
            action=action,
            pays_mana_cost=not free,
            source_name=ability.source_name,
            rule="CR 601.3",
            zone=card.zone,
            until_end_of_turn=duration is PermissionDuration.THIS_TURN,
            expires_end_of_next_turn=duration is PermissionDuration.NEXT_TURN,
            until_next_end_step_of=(
                controller.username if duration is PermissionDuration.NEXT_END_STEP else None
            ),
        )

    return effect


#: "Search your library for any number of <quality> cards, exile them, then
#: shuffle" - Ugin, Eye of the Storms' −11. Distinct from `_SEARCH_AND_PUT_RE`
#: in three ways, which is why it is its own pattern rather than another
#: alternative in that one: the count is CR 107.1c's "any number" rather than
#: "a card", the destination is exile rather than the hand or the battlefield,
#: and the sentence has a second sentence bound to it (the permission above)
#: that `_SEARCH_AND_PUT_RE`'s `fullmatch` discipline would refuse anyway.
_SEARCH_AND_EXILE_ANY_NUMBER_RE = re.compile(
    r"^search your library for any number of (?P<quality>.+?) cards, "
    r"exile them, then shuffle$",
    re.IGNORECASE,
)


def _parse_exile_antecedent(clause: str) -> tuple[ExileAntecedent, bool] | None:
    """One exiling clause, plus whether it exiles more than one card.

    Two shapes, both already printed in this pool:

    - "exile the top card of that player's library" (Ragavan), where "that
      player" is CR 120.2a's damaged player read off the trigger's own event,
      exactly as `_parse_exile_that_players_library_clause` reads it. The card
      stays **owned** by that player (CR 108.3) - only the permission moves.
    - "search your library for any number of `<quality>` cards, exile them,
      then shuffle" (Ugin's −11). CR 107.1c: "if a rule or ability instructs a
      player to choose 'any number,' that player may choose any positive number
      or zero", so finding nothing is a legal answer and the permission is then
      granted to nothing at all. CR 701.23b says the same from the search's
      side, which is why `optional=True`: every card found is offered
      individually and may be declined.

    Anything else comes back `None`, and the whole two-clause instruction goes
    unread rather than half-read (CR 608.2c).
    """
    stripped = clause.strip()

    if match := _EXILE_TOP_OF_YOUR_LIBRARY_RE.fullmatch(stripped):
        # Experimental Synthesizer's "top card" (Bonehoard Dracosaur's own
        # "top two cards" is the same shape, generalized on the count): the
        # controller's own top N (CR 108.3: its owner, and the player the
        # permission goes to, are the same). `exiles_many` (the pair's own
        # plural-pronoun check) is whether more than one card is named, not
        # whether the library actually held that many - CR 107.1b/608.2b have
        # nothing to say about a search or exile running short, it just
        # exiles what is there.
        # "that many cards from the top" (Chandra, Legacy of Fire's 0) is the
        # count channel's number (`that_many`), read as it resolves.
        carried = match.group("that_many") is not None
        raw_n = match.group("n")
        where_x = match.group("where_x")
        # Jessica Jones, Private Eye's own "the top X cards ..., where X is
        # this permanent's power" (CR 107.3f, after `_self_normalized_
        # effect_text`'s own CR 201.5 rewrite has already turned the card's
        # printed name into "this permanent") - `amount_expression` reads the
        # definition against the ability's own source, with no announced X
        # (CR 107.3a) to fall back on, since this activation's cost carries
        # none.
        x_expression = None
        if raw_n is not None and raw_n.lower() == "x":
            if where_x is None:
                return None
            x_expression = amount_expression(where_x)
            if x_expression is None:
                return None
            n = 1  # placeholder; recomputed per-resolution below
        else:
            n = parse_count(raw_n) if raw_n else 1

        def exile_own_top(game: "Game", ability: AbilityOnStack) -> list[CardState]:
            player = game.controller_of(ability)
            exiled: list[CardState] = []
            count = n
            if carried:
                counted = _that_many_or_notice(
                    game, stripped, source_id=ability.source_id, source_name=ability.source_name
                )
                if counted is None:
                    return []
                count = counted
            elif x_expression is not None:
                source = ability.source(game)
                if source is None:
                    return []
                count = x_expression(game, ability.controller, source, 0)
            for _ in range(count):
                if not player.library:
                    break
                exiled.append(game.exile_permanent(player.library[0]))
            return exiled

        return exile_own_top, carried or x_expression is not None or n > 1

    if _EXILE_TOP_OF_THAT_PLAYERS_LIBRARY_RE.fullmatch(stripped):

        def exile_top(game: "Game", ability: AbilityOnStack) -> list[CardState]:
            event = ability.event
            username = event.player if event is not None else None
            if username is None:
                return []
            player = game.player(username)
            if not player.library:
                return []
            return [game.exile_permanent(player.library[0])]

        return exile_top, False

    match = _SEARCH_AND_EXILE_ANY_NUMBER_RE.fullmatch(stripped)
    if match is not None:
        quality = match.group("quality")
        if not _search_quality_is_readable(quality):
            return None
        matches = _quality_matcher(quality)

        def search_and_exile(game: "Game", ability: AbilityOnStack) -> list[CardState]:
            player = game.controller_of(ability)
            found = game.search_library(
                player,
                matches,
                count=len(player.library),
                optional=True,
                source=ability.source_name,
                source_id=source_id_of(ability),
            )
            return [game.exile_permanent(card) for card in found]

        return search_and_exile, True

    return None


#: "Exile cards from the top of your library until you exile `<n>` `<quality>`
#: cards[ with mana value `<m>` or less]. You may cast one of those `<n>`
#: cards without paying its mana cost. Put one of them into your hand. Then
#: put the other cards exiled this way on the bottom of your library in a
#: random order." - Invasion of Alara's own Siege ETB. A Scryfall search for
#: "you may cast one of those" turns up no other printing of this exact
#: multi-card impulse shape, so the count and quality are read generally
#: (`{COUNT}`/`_bounded_quality_matcher`, the same readers every other
#: exile-until quality already uses) rather than hardcoded to "two"/"4",
#: even though only this one card is proven against it.
#:
#: The process itself is `machines/keywords.exile_until`, generalised from
#: "stop on the first match" to "stop once `n` matches have been seen" -
#: cascade and discover are the same process with their own keyword-defined
#: stop. What happens to the `n` matches afterward was checked against this
#: printing's own Scryfall rulings (2023-04-14): casting one is optional
#: (CR 608.2g/CR 118.9) and leaves the *other* match(es) still to place;
#: exactly one match always goes to hand, and any match neither cast nor
#: handed "will remain in exile. It won't be put on the bottom of your
#: library" - only the non-matching mill fodder does, in a random order
#: (CR 701.24a's shuffle verb is never printed here, matching `puts_
#: graveyard_on_bottom_of_library`'s and cascade's own un-shuffled bottoming).
_EXILE_UNTIL_N_QUALITY_CAST_ONE_FREE_RE = re.compile(
    rf"^exile cards from the top of your library until you exile (?P<n>{COUNT}) "
    r"(?P<quality>.+?) cards?(?: with mana value (?P<max_mv>\d+) or less)?\.\s*"
    r"you may cast one of those (?P<n2>[a-z]+) cards without paying its mana cost\.\s*"
    r"put one of them into your hand\.\s*"
    r"then put the other cards exiled this way on the bottom of your library "
    r"in a random order\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s1")
def _parse_exile_until_n_quality_cast_one_free_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_UNTIL_N_QUALITY_CAST_ONE_FREE_RE`'s shape, or `None`."""
    whole = _strip_non_effect_preamble(text).strip()
    match = _EXILE_UNTIL_N_QUALITY_CAST_ONE_FREE_RE.fullmatch(whole)
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None or count <= 0 or match.group("n").lower() != match.group("n2").lower():
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _bounded_quality_matcher(quality, match.group("max_mv"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..keywords import exile_until

        controller = game.controller_of(ability)
        exiled = exile_until(
            game,
            controller,
            lambda state, seen: sum(1 for card in seen if matches(card)) >= count,
            source_name=ability.source_name,
        )
        found = [card for card in exiled if matches(card)]
        rest = [card for card in exiled if card not in found]
        if found:
            _offer_free_casts_from_among(
                game,
                found,
                controller.username,
                source_name=ability.source_name,
                source_id=source_id_of(ability),
                play=False,
                limit=1,
                zone=Zone.EXILE,
            )
        # CR 400.1: exile is a shared zone, never a player's own - `Player.
        # move` refuses to lift a card out of one. `Game.exile` is the list
        # to remove it from instead, the same two-step
        # `_merge_may_exile_discarded_card_then_play_permission_clauses`
        # region's own Possibility Storm bottoming already uses to leave
        # exile for a player zone.
        remaining = [card for card in found if card in game.exile]
        if remaining:
            chosen = remaining[0]
            if len(remaining) > 1:
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt="choose one of those cards to put into your hand",
                        source=ability.source_name,
                        source_id=source_id_of(ability),
                        amount=1,
                        cards=tuple(card.id for card in remaining),
                        card_labels=tuple(card.name for card in remaining),
                    )
                )
                assert isinstance(chosen_ids, tuple)
                by_id = {card.id: card for card in remaining}
                chosen = by_id[chosen_ids[0]] if chosen_ids else remaining[0]
            game.exile.remove(chosen)
            game.player(chosen.owner).add(chosen, Zone.HAND)
            # Every other matching card that was neither cast nor handed
            # (possible only when `count` > 2, or when the caster declined
            # both the cast and left more than one candidate) stays in
            # exile forever - the printed ruling above, never bottomed.
        if rest:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:exile-until-n-bottom"
            )
            rng.shuffle(rest)
            for card in rest:
                if card in game.exile:
                    game.exile.remove(card)
                    game.player(card.owner).add(card, Zone.LIBRARY)
            game.shuffles_performed += 1

    return effect


_EXILE_UNTIL_TOTAL_MANA_VALUE_RE = re.compile(
    r"^exile cards from the top of your library until you exile cards with total "
    r"mana value (?P<n>\d+) or greater$",
    re.IGNORECASE,
)


def _parse_exile_until_antecedent(clause: str) -> "tuple[ExileAntecedent, bool] | None":
    """The exile-until process as an antecedent (CR 607.1) for the sentence
    after it, plus whether it names more than one card.

    - "until you exile a <quality> card": the antecedent is the one card that
      stopped the process ("that card", singular). A library that runs out
      first stopped on nothing, so there is nothing to name. The cards exiled
      on the way are named by nothing and stay in exile (CR 406.1).
    - "until you exile cards with total mana value N or greater": the
      antecedent is every card exiled ("them", plural) - the total is over all
      of them (CR 202.3's mana value; a land's is 0).
    """
    from ..keywords import exile_until

    stripped = clause.strip().rstrip(".")
    if match := _EXILE_UNTIL_QUALITY_RE.fullmatch(stripped):
        quality = match.group("quality")
        if not _search_quality_is_readable(quality):
            return None
        matches = _quality_matcher(quality)

        def exile_until_quality(game: "Game", stack_object: "StackObject") -> list[CardState]:
            owner = game.controller_of(stack_object)
            exiled = exile_until(
                game,
                owner,
                lambda state, _: matches(state),
                source_name=stack_object.name,
            )
            return [exiled[-1]] if exiled and matches(exiled[-1]) else []

        return exile_until_quality, False

    if match := _EXILE_UNTIL_TOTAL_MANA_VALUE_RE.fullmatch(stripped):
        threshold = int(match.group("n"))

        def exile_until_total(game: "Game", stack_object: "StackObject") -> list[CardState]:
            owner = game.controller_of(stack_object)
            return exile_until(
                game,
                owner,
                lambda _, exiled: sum(state.card.cmc for state in exiled) >= threshold,
                source_name=stack_object.name,
            )

        return exile_until_total, True

    return None


def _parse_exile_until_antecedent_third_person(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    """`_EXILE_UNTIL_QUALITY_THIRD_PERSON_RE`'s shape: "that player" is
    CR 120.2a's damaged player, read off the triggering event exactly as
    `_parse_exile_that_players_library_clause`/`_EXILE_TOP_OF_THAT_PLAYERS_
    LIBRARY_RE` already read it for a fixed count - the exile-until process
    itself is `keywords.exile_until`, unchanged."""
    from ..keywords import exile_until

    stripped = clause.strip().rstrip(".")
    match = _EXILE_UNTIL_QUALITY_THIRD_PERSON_RE.fullmatch(stripped)
    if match is None:
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def exile_until_quality(game: "Game", stack_object: "StackObject") -> list[CardState]:
        if not is_ability(stack_object) or stack_object.event is None:
            return []
        username = stack_object.event.player
        if username is None:
            return []
        owner = game.player(username)
        exiled = exile_until(
            game, owner, lambda state, _: matches(state), source_name=stack_object.source_name
        )
        return [exiled[-1]] if exiled and matches(exiled[-1]) else []

    return exile_until_quality, False


#: "target opponent exiles cards from the top of their library until they
#: exile a `<quality>` card" - Stolen Goods' own shape (verified: real,
#: Modern-legal Scryfall printing), the identical `keywords.exile_until`
#: process again, this time over a chosen target rather than CR 120.2a's
#: damaged player.
_EXILE_UNTIL_QUALITY_TARGET_OPPONENT_RE = re.compile(
    r"^target opponent exiles cards from the top of (?:their|his or her) library until "
    r"(?:they|that player|he or she) exiles? an? (?P<quality>[\w' ,-]+?) card$",
    re.IGNORECASE,
)


def _parse_exile_until_antecedent_target_opponent(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    """`_EXILE_UNTIL_QUALITY_TARGET_OPPONENT_RE`'s shape: the exiled player is
    this ability's own chosen target (CR 601.2c/603.3d), read the same way
    `_parse_exile_target_card_antecedent` already reads a target for an
    "exile target ... card" clause - `game.resolve_targets` rather than the
    event `_parse_exile_until_antecedent_third_person` reads."""
    from ..keywords import exile_until

    stripped = clause.strip().rstrip(".")
    match = _EXILE_UNTIL_QUALITY_TARGET_OPPONENT_RE.fullmatch(stripped)
    if match is None:
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def exile_until_quality(game: "Game", stack_object: "StackObject") -> list[CardState]:
        owner = next(
            (target for target in game.resolve_targets(stack_object) if isinstance(target, Player)),
            None,
        )
        if owner is None:
            return []
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        exiled = exile_until(game, owner, lambda state, _: matches(state), source_name=source_name)
        return [exiled[-1]] if exiled and matches(exiled[-1]) else []

    return exile_until_quality, False


#: "each opponent exiles cards from the top of their library until they exile
#: a `<quality>` card" (Krang & Shredder's enters-or-attacks trigger) and
#: "each player exiles ..." (Etali, Primal Conqueror's enters trigger) - the
#: same `keywords.exile_until` process `_EXILE_UNTIL_QUALITY_TARGET_OPPONENT_
#: RE` reads for one chosen player, run for every player the subject names,
#: in APNAP order (CR 101.4). The cards exiled are CR 607.2a's pile for any
#: "exiled with `<this>`" reader the object prints (`link_cards_exiled_
#: during`, run once the ability has resolved).
_EACH_PLAYER_EXILES_UNTIL_QUALITY_RE = re.compile(
    r"^each (?P<who>opponent|player) exiles cards from the top of (?:their|his or her) library "
    r"until (?:they|that player|he or she) exiles? an? (?P<quality>[\w' ,-]+?) card\.?$",
    re.IGNORECASE,
)


def _each_player_exile_until(clause: str) -> "ExileAntecedent | None":
    """`_EACH_PLAYER_EXILES_UNTIL_QUALITY_RE`'s process, returning the card
    that stopped each player's run (the `<quality>` card "exiled this way"),
    in APNAP order - or None when the clause is not that shape."""
    from ..keywords import exile_until

    match = _EACH_PLAYER_EXILES_UNTIL_QUALITY_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)
    opponents_only = match.group("who").lower() == "opponent"

    def exile_each(game: "Game", stack_object: "StackObject") -> list[CardState]:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        stoppers: list[CardState] = []
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller:
                continue
            exiled = exile_until(
                game, player, lambda state, _: matches(state), source_name=source_name
            )
            if exiled and matches(exiled[-1]):
                stoppers.append(exiled[-1])
        return stoppers

    return exile_each


@MIXED_CLAUSE.rung("s3", for_spell=FORWARD)
def _parse_each_player_exiles_until_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_EXILES_UNTIL_QUALITY_RE` standing alone (Krang &
    Shredder's trigger): the exiling is the whole instruction, and what the
    object does with the cards later is its other, linked ability's."""
    exile_each = _each_player_exile_until(clause)
    if exile_each is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        exile_each(game, stack_object)

    return effect


#: "exile target instant or sorcery card from an opponent's graveyard" (Dire
#: Fleet Daredevil) - the exiling clause's own verb performs the move, unlike
#: `_parse_chosen_target_card_antecedent`'s "choose target ... card", which
#: only picks the object out without moving it. A common enough template
#: (Magic's own general "exile target [quality] card [from zone]" shape,
#: never fully read before this) that no card name is worth pinning to it.
#: The quality group also takes an Oxford-comma list ("Equipment, instant, or
#: sorcery card" - Thor, God of Thunder), the same comma `_EXILE_UNTIL_
#: QUALITY_RE`'s own quality group already accepts.
_EXILE_TARGET_CARD_RE = re.compile(
    r"^exile target (?P<quality>[\w' ,-]*?)cards?"
    r"(?: from (?:an? opponent's|your|their) (?P<zone>graveyard|hand|library))?$",
    re.IGNORECASE,
)


def _parse_exile_target_card_antecedent(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    """`_EXILE_TARGET_CARD_RE`'s shape: the object is the ability's own
    target (CR 601.2c, CR 603.3d), already validated by `machines/targeting`
    and rechecked on resolution (CR 608.2b) - `game.resolve_card_targets`
    finds it, exactly as `_parse_chosen_target_card_antecedent` already does
    for a "choose target" clause - but this clause's own verb is "exile", so
    the effect below actually performs that move rather than merely reading
    where the target already sat.
    """
    if _EXILE_TARGET_CARD_RE.fullmatch(clause.strip()) is None:
        return None

    def exile_target(game: "Game", stack_object: "StackObject") -> list[CardState]:
        return [
            game.exile_permanent(card)
            for card in game.resolve_card_targets(stack_object)
            if card.zone is not Zone.EXILE
        ]

    return exile_target, False


def _parse_exile_until_leaves_battlefield_antecedent(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    """`_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE`'s own shape, as an
    antecedent for a trailing play permission - Hostage Taker's "exile
    another target creature or artifact until this creature leaves the
    battlefield. You may cast that card for as long as it remains exiled,
    and mana of any type can be spent to cast that spell." CR 610.2's
    watch-and-return is set up exactly as `_parse_exile_until_leaves_
    battlefield_clause` already sets it up alone - `_watch_for_departure_
    and_return_exiled_card` returns the card to the battlefield if Hostage
    Taker itself leaves before the permission is used; CR 400.7 already
    makes that watch a no-op once the card has left exile to be cast
    instead, since the object it was watching is gone by then.
    """
    match = _EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def exile_until_source_leaves(game: "Game", stack_object: "StackObject") -> list[CardState]:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None:
            return []  # CR 113.7a: the source is already gone; nothing left to watch leave.
        exiled: list[CardState] = []
        for target in game.resolve_card_targets(stack_object):
            if target.zone is Zone.EXILE:
                continue
            moved = game.exile_permanent(target)
            if moved.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move.
            _watch_for_departure_and_return_exiled_card(
                game, source, moved, stack_object.controller
            )
            exiled.append(moved)
        return exiled

    return exile_until_source_leaves, False


#: "If that spell would be put into a graveyard, exile it instead." - Dire
#: Fleet Daredevil's and Nita, Forum Conciliator's own further rider on
#: exactly this permission shape (CR 604.5's "some static abilities apply
#: while a spell is on the stack", the identical mechanism flashback's own
#: second static already uses - see `machines/replacement._stack_replacements`).
_EXILE_INSTEAD_OF_GRAVEYARD_RE = re.compile(
    r"^if (?:it|that spell|those spells) would be put into a graveyard,? "
    r"exile (?:it|them) instead\.?$",
    re.IGNORECASE,
)


#: "If <condition>, exile the top N cards instead." - Burning Curiosity's own
#: "If this spell's additional cost was paid, exile the top three cards
#: instead.", printed *between* the exile it replaces and the permission
#: sentence whose "those cards" (CR 607.1) then names whichever set was
#: really exiled. CR 614.1a: "instead" replaces the earlier instruction whole.
#: The condition is any `Game.condition_holds` reads (`condition_is_readable`
#: gates it at parse time), not the additional cost by name.
_EXILE_TOP_INSTEAD_RE = re.compile(
    rf"^if (?P<condition>[^,]+), exile the top (?P<n>{COUNT}) cards? instead$",
    re.IGNORECASE,
)


def _parse_exile_top_instead_clause(
    clause: str,
) -> "tuple[str, ExileAntecedent] | None":
    """`_EXILE_TOP_INSTEAD_RE`'s condition and the alternative exile, or `None`."""

    match = _EXILE_TOP_INSTEAD_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or not _effect_condition_is_readable(match.group("condition")):
        return None
    alternative = _parse_exile_antecedent(f"exile the top {match.group('n')} cards of your library")
    if alternative is None:
        return None
    return match.group("condition").strip(), alternative[0]


def _spell_safe_exile_antecedent(clause: str) -> "tuple[ExileAntecedent, bool] | None":
    """The exiling clauses a resolving *spell* can name its own permission
    over: the controller's own top N (`_EXILE_TOP_OF_YOUR_LIBRARY_RE` without
    "that many", which reads an ability's own count channel) and the
    exile-until process. Ragavan's "that player" needs a trigger's own event
    and Ugin's search names an ability as the searcher, so both stay
    ability-only."""
    match = _EXILE_TOP_OF_YOUR_LIBRARY_RE.fullmatch(clause.strip())
    if match is not None and match.group("that_many") is None:
        return _parse_exile_antecedent(clause)
    return _parse_exile_until_antecedent(clause) or _parse_exile_until_antecedent_target_opponent(
        clause
    )


def _parse_exile_then_play_permission_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> "tuple[int, TargetedClause] | None":
    """ "[exile or choose some cards]. <duration>, you may cast/play
    them[, and mana of any type can be spent to cast it][. If that spell
    would be put into a graveyard, exile it instead.]" - however many
    clauses `split_effect_clauses` cut the whole instruction into (2 to 5),
    read here as one CR 608.2c instruction rather than as independent
    clauses, matching `_merge_each_player_clauses`'s own `(consumed, effect)`
    return shape for a merge wider than a fixed pair.

    Read as one instruction because none of the trailing sentences has a
    meaning of its own: CR 607.1's within-one-ability anaphora - "it"/"that
    card"/"that spell" - points back at whatever the first clause exiled,
    and the any-type-mana and graveyard-redirect riders both modify *this
    exact grant*, not some independent effect. Splitting any of them off
    would either grant a permission over nothing, or grant the permission
    without the rider that makes it worth granting at all. CR 608.2c has no
    notion of running half an instruction, and this project's paragraph-
    atomic rule says the same.

    The duration is whichever one the permission sentence printed
    (`_permission_duration`, CR 611.2a): "this turn"/"until end of turn",
    "until the end of your next turn" (`PlayPermission.expires_end_of_next_
    turn`), "until your next end step" (`PlayPermission.until_next_end_step_
    of`) or "for as long as it remains exiled".

    An "If <condition>, exile the top N cards instead." clause between the
    exile and the permission (Burning Curiosity, `_EXILE_TOP_INSTEAD_RE`)
    swaps the exile for the larger one when the condition holds as the
    instruction resolves (CR 608.2c), and the permission then names what was
    really exiled.

    A spell reaches this with the antecedents `_spell_safe_exile_antecedent`
    reads - the impulse spells (Reckless Impulse, Burning Curiosity, Haste
    Magic) and modes (Riveteers Charm) - or a chosen target card; an ability
    with every antecedent `_parse_exile_antecedent` and its siblings read.
    """
    if index + 1 >= len(clauses):
        return None
    instead: tuple[str, ExileAntecedent] | None = None
    permission_index = index + 1
    if index + 2 < len(clauses):
        instead = _parse_exile_top_instead_clause(clauses[index + 1])
        if instead is not None:
            permission_index = index + 2
    permission = _PLAY_PERMISSION_RE.fullmatch(clauses[permission_index].strip().rstrip(","))
    if permission is None:
        return None
    duration = _permission_duration(permission)
    if duration is None:
        # No duration, or both: not the sentence this reads.
        return None
    antecedent = _parse_chosen_target_card_antecedent(clauses[index])
    if antecedent is None:
        antecedent = _parse_exile_top_of_other_libraries_antecedent(clauses[index])
    if antecedent is None:
        antecedent = (
            _spell_safe_exile_antecedent(clauses[index])
            if for_spell
            else (
                _parse_exile_target_card_antecedent(clauses[index])
                or _parse_exile_until_leaves_battlefield_antecedent(clauses[index])
                or _parse_exile_antecedent(clauses[index])
                or _parse_exile_until_antecedent(clauses[index])
                or _parse_exile_until_antecedent_target_opponent(clauses[index])
            )
        )
    if antecedent is None:
        return None
    if (
        instead is not None
        and _EXILE_TOP_OF_YOUR_LIBRARY_RE.fullmatch(clauses[index].strip()) is None
    ):
        # "exile the top N cards instead" replaces only an exile of the top.
        return None
    exile, exiles_many = antecedent
    plural = permission.group("subject").lower() in _PLURAL_PERMISSION_SUBJECTS
    if plural != exiles_many:
        # The pronoun does not agree in number with the clause it points at, so
        # this is not the shape it looked like. Refuse rather than guess.
        return None
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None

    consumed = permission_index - index + 1
    any_type_mana = False
    if index + consumed < len(clauses) and _ANY_TYPE_MANA_STANDALONE_RE.fullmatch(
        clauses[index + consumed].strip()
    ):
        any_type_mana = True
        consumed += 1

    exile_instead = False
    if index + consumed < len(clauses) and _EXILE_INSTEAD_OF_GRAVEYARD_RE.fullmatch(
        clauses[index + consumed].strip()
    ):
        exile_instead = True
        consumed += 1

    pays_life = False
    if index + consumed < len(clauses) and _PAY_LIFE_FOR_MANA_VALUE_RE.fullmatch(
        clauses[index + consumed].strip()
    ):
        if free:
            return None
        pays_life = True
        consumed += 1
    one_of = permission.group("subject").lower().startswith("one of")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        chosen_exile = exile
        if instead is not None:
            condition, alternative = instead
            source = stack_object if isinstance(stack_object, CardState) else None
            held = game.condition_holds(controller, condition, source)
            if held is None:
                notice = ConditionalClauseNotice(
                    source_id=(
                        stack_object.id
                        if isinstance(stack_object, CardState)
                        else stack_object.source_id
                    ),
                    source_name=source_name,
                    text=f"If {condition}, exile the top cards instead",
                )
                if notice not in game.conditional_clause_notices:
                    game.conditional_clause_notices.append(notice)
            elif held:
                chosen_exile = alternative
        for card in chosen_exile(game, stack_object):
            game.grant_play_permission(
                card,
                controller,
                action=action,
                pays_mana_cost=not free and not pays_life,
                source_name=source_name,
                rule="CR 601.3",
                zone=card.zone,
                any_type_mana=any_type_mana,
                until_end_of_turn=duration is PermissionDuration.THIS_TURN,
                expires_end_of_next_turn=duration is PermissionDuration.NEXT_TURN,
                until_next_end_step_of=(
                    controller if duration is PermissionDuration.NEXT_END_STEP else None
                ),
                exile_instead_of_graveyard=exile_instead,
                pays_life_for_mana_value=pays_life,
                choice_group=stack_object.id if one_of else None,
            )

    return consumed, effect


#: "For each of those cards, its owner may play it for as long as it remains
#: exiled." / "... its owner may play it until the end of their next turn." -
#: the permission goes to each exiled card's own **owner** (CR 108.3), not to
#: the controller who did the exiling, the one thing `_PLAY_PERMISSION_RE`
#: (always "you"/"they") cannot say. The "for each of those cards" lead and the
#: "for as long as that card remains exiled" lead are both the same CR 607.1
#: anaphora over whatever the exile clause moved; the pronoun is distributive,
#: so it never has to agree in number with the exile clause.
_OWNER_PLAY_PERMISSION_RE = re.compile(
    r"^(?:for each (?:of (?:those|these) cards|card exiled this way), )?"
    r"(?P<leading>for as long as (?:that card|it|they) (?:remains?) exiled, )?"
    r"its owner may (?P<action>cast|play) (?:it|that card)"
    r"(?P<free> without paying its mana cost)?"
    r"(?P<trailing> for as long as it remains exiled| until the end of their next turn)?$",
    re.IGNORECASE,
)

#: "A spell cast [by an opponent] this way costs {2} more to cast." - the
#: CR 601.2f cost increase riding on `_OWNER_PLAY_PERMISSION_RE`'s grant.
#: "By an opponent" restricts it to a permission whose owner is an opponent of
#: the controller of the ability or spell that exiled the card (Soul
#: Partition); without it the increase applies to every owner (Elite
#: Spellbinder, whose only exiled card is an opponent's anyway).
_OWNER_PERMISSION_COST_INCREASE_RE = re.compile(
    r"^a spell cast (?P<opponent>by an opponent )?this way costs (?P<increase>(?:\{[^}]+\})+) "
    r"more to cast$",
    re.IGNORECASE,
)

#: "exile [up to X | up to N | any number of] target `<permanents>`" - the
#: battlefield exile whose objects a trailing permission names. Targets are
#: validated by `machines/targeting.py` (count words and X included) and
#: rechecked on resolution (CR 608.2b); a token is exiled too (CR 701.13a) but
#: is no card, so the permission skips it (CR 111.7).
_EXILE_TARGET_PERMANENTS_RE = re.compile(
    r"^exile (?P<phrase>(?:up to |any number of )?(?:\w+ )?target .+)$", re.IGNORECASE
)


def _parse_exile_target_permanents_antecedent(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    match = _EXILE_TARGET_PERMANENTS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=True):
        return None

    def exile_targets(game: "Game", stack_object: "StackObject") -> list[CardState]:
        exiled = [
            game.exile_permanent(card)
            for card in game.resolve_card_targets(stack_object)
            if card.zone is Zone.BATTLEFIELD
        ]
        return [card for card in exiled if card.zone is Zone.EXILE]

    return exile_targets, True


def _parse_exile_targets_then_owner_play_permission_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> "tuple[int, TargetedClause] | None":
    """ "Exile up to X target creatures. For each of those cards, its owner may
    play it for as long as it remains exiled." as one CR 608.2c instruction
    (the permission sentence only means something against what the first
    exiled). Each exiled card's owner gets a `PlayPermission` through
    `Game.grant_play_permission`, which stamps the card's `zone_change_stamp`,
    so it ends the moment the card leaves exile (CR 400.7)."""
    if index + 1 >= len(clauses):
        return None
    permission = _OWNER_PLAY_PERMISSION_RE.fullmatch(clauses[index + 1].strip().rstrip(","))
    if permission is None:
        return None
    leading, trailing = permission.group("leading"), permission.group("trailing")
    if bool(leading) == bool(trailing):
        return None
    next_turn = bool(trailing) and "next turn" in trailing.lower()
    antecedent = _parse_exile_target_permanents_antecedent(clauses[index])
    if antecedent is None:
        return None
    exile, _ = antecedent
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None
    consumed = 2
    increase: ManaCost | None = None
    increase_opponents_only = False
    if index + 2 < len(clauses):
        rider = _OWNER_PERMISSION_COST_INCREASE_RE.fullmatch(clauses[index + 2].strip())
        if rider is not None:
            if free:
                return None
            increase = ManaCost.parse(rider.group("increase"))
            increase_opponents_only = rider.group("opponent") is not None
            consumed = 3

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        controller = game.controller_of(stack_object).username
        for card in exile(game, stack_object):  # type: ignore[arg-type]
            if card.owner is None or is_token(card):
                continue
            game.grant_play_permission(
                card,
                card.owner,
                action=action,
                pays_mana_cost=not free,
                source_name=source_name,
                rule="CR 601.3",
                zone=card.zone,
                until_end_of_turn=False,
                expires_end_of_next_turn=next_turn,
                cost_increase=(
                    None if increase_opponents_only and card.owner == controller else increase
                ),
            )

    return consumed, effect


#: "If `<condition>`, exile the top card of your library. You may play that
#: card until the end of your next turn." - Elemental Mascot's own Opus
#: rider. False, and CR 608.2c has nothing to run: nothing was exiled, so
#: there is no "that card" for the permission sentence to name, exactly as
#: if the whole two-sentence instruction had simply been skipped.
_IF_CONDITION_LEADING_RE = re.compile(r"^if (?P<condition>[^,]+),\s*(?P<rest>.+)$", re.IGNORECASE)


def _parse_conditional_exile_then_play_permission_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> "tuple[int, TargetedClause] | None":
    """Elemental Mascot's whole Opus rider as one CR 608.2c instruction -
    see the banner above. Reuses `_parse_exile_then_play_permission_clauses`
    outright for the exile-and-permission half (on a rewritten clause list
    with the leading "if `<condition>`," stripped from the first clause),
    wrapped in the same resolution-time condition check every other printed
    "if" here goes through - an unreadable condition fails closed with a
    `ConditionalClauseNotice` rather than guessing.
    """
    match = _IF_CONDITION_LEADING_RE.fullmatch(clauses[index].strip())
    if match is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    rewritten = [match.group("rest").strip(), *clauses[index + 1 :]]
    inner = _parse_exile_then_play_permission_clauses(rewritten, 0, for_spell=for_spell)
    if inner is None:
        return None
    consumed, inner_effect = inner

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        held = _condition_holds_for_stack_object(game, stack_object, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=(
                    stack_object.name
                    if isinstance(stack_object, CardState)
                    else stack_object.source_name  # type: ignore[union-attr]
                ),
                text=clauses[index],
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            inner_effect(game, stack_object)

    return consumed, effect


def _parse_exile_then_play_permission_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """The plain two-clause case, for callers that only ever hand this a
    fixed pair - see `_parse_exile_then_play_permission_clauses`, which this
    delegates to with no rider clauses available to find."""
    merged = _parse_exile_then_play_permission_clauses([first, second], 0, for_spell=for_spell)
    return None if merged is None else merged[1]


#: "Target player sacrifices `<n>` `<description>`[ of their choice]." - the
#: edict template (CR 701.21a), aimed at a chosen player instead of "each
#: opponent"/"each player" (`_EACH_SACRIFICES_OF_THEIR_CHOICE_RE`) or the
#: specific player whose own step just triggered ("that player",
#: `_THAT_PLAYER_SACRIFICES_OF_THEIR_CHOICE_RE`) - a genuinely different
#: subject each time, CR 115.1's own "target [something]" grammar rather
#: than either of those two's anaphora. "Of their choice" is optional:
#: sacrifice is always the controller's own choice among what they control
#: whether or not a card bothers to say so (CR 701.21a) - Liliana of the
#: Veil's own "-2" omits the phrase, Diabolic Edict prints it, and both mean
#: the identical thing, so the same reader takes either. The description is
#: `machines/targeting.permanent_description`, the same target grammar
#: `_EACH_SACRIFICES_OF_THEIR_CHOICE_RE` already reuses.
#:
#: "Target opponent" reads identically (G7): CR 701.21a does not care
#: whether the target is narrowed to an opponent or left as any player, and
#: Archon of Cruelty's own trigger ("target opponent sacrifices a creature
#: or planeswalker of their choice, ...") is the card that exposed this half
#: being unread - the regex only ever matched the literal word "player".
_TARGET_PLAYER_SACRIFICES_RE = re.compile(
    rf"^(?P<who>target (?:player|opponent)) sacrifices (?P<n>{COUNT}) (?P<description>.+?)"
    r"(?: of their choice)?(?P<tail> with [^.]+?)?\.?$",
    re.IGNORECASE,
)

#: The bare verb, subject already stripped - "sacrifices a creature or
#: planeswalker of their choice" - read the identical way `_DISCARD_A_CARD_
#: RE`/`_discard_cards` already are: as one item of a `_parse_shared_
#: subject_clauses` verb list (G7), whose own subject (already carried by
#: that reader) supplies the player this runs against. Deliberately kept out
#: of `parse_clause_effect` itself: that function is the shared bare-verb
#: vocabulary many unrelated callers already reuse, and widening it here
#: would risk changing how some other card's own unrelated "sacrifice" text
#: (a cost line, "sacrifice this creature") reads; this private matcher is
#: reached only from the one caller that means this shape.
_BARE_SACRIFICE_OF_CHOICE_RE = re.compile(
    rf"^sacrifices? (?P<n>{COUNT}) (?P<description>.+?)"
    r"(?: of (?:your|their) choice)?(?P<tail> with [^.]+?)?$",
    re.IGNORECASE,
)


def _sacrifice_of_choice_clause_effect(
    description: str, count: int, wanted_words: str, *, excludes_source: bool = False
) -> ClauseEffect:
    """One player's own CR 701.21a/608.2d choice among their own permanents
    matching `description` - the body both `_parse_target_player_sacrifices_
    clause` (over whichever player `resolve_targets` hands it) and
    `_parse_bare_sacrifice_of_choice_clause` (over whichever player G7's
    subject-carry pass hands it) run, factored out once so the two share the
    identical "no impossible choice"/CR 608.2d floor rather than keeping two
    copies of it.

    `excludes_source` is "another <thing>" / "<thing> other than this
    <noun>" (Liege of the Pit, Rust Elemental): the ability's own source is
    never a candidate, so with nothing else to sacrifice nothing is (CR 701.21a:
    a player sacrifices only a permanent they control, and "other" rules the
    source out).
    """
    requirement = permanent_description(description)
    assert requirement is not None

    def effect(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if requirement.rejects(permanent, player.username, game) is None
            and not (excludes_source and str(permanent.id) == source_id)
        ]
        if not candidates:
            return
        if len(candidates) <= count:
            chosen = candidates
        else:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"sacrifice {wanted_words}",
                    source=source,
                    amount=count,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id,
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return effect


#: "Sacrifice a permanent." (Lorehold Command's fourth mode), "sacrifice a
#: creature or land" (Thalia and The Gitrog Monster's attack trigger) - CR
#: 701.21a's sacrifice with no subject: the resolving spell's or ability's
#: controller sacrifices one permanent of their choice among those they
#: control that match the description (`permanent_description`, the target
#: grammar). Nothing is targeted (CR 115.10a); with none to sacrifice nothing
#: happens (CR 608.2d), and anything after it in the same text still does.
_SACRIFICE_ONE_OF_CHOICE_RE = re.compile(
    r"^sacrifice (?P<article>another|an?|one) "
    r"(?P<description>(?!other\b|another\b)[a-z][a-z ,'-]*?)\.?$",
    re.IGNORECASE,
)

#: "a creature other than this creature" (Liege of the Pit, Demonic
#: Taskmaster) - `_SACRIFICE_ONE_OF_CHOICE_RE`'s description with the source
#: named out of the choice, the same exclusion "another creature" makes.
_OTHER_THAN_THIS_RE = re.compile(r"^(?P<description>.+?) other than this [a-z]+$", re.IGNORECASE)


def _read_sacrifice_choice(text: str) -> tuple[str, bool] | None:
    """`_SACRIFICE_ONE_OF_CHOICE_RE`'s `(description, excludes_source)`, or None
    when `text` is not that shape or names something `permanent_description`
    cannot read."""
    match = _SACRIFICE_ONE_OF_CHOICE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    description = match.group("description").strip()
    excludes_source = match.group("article").lower() == "another"
    other_than_this = _OTHER_THAN_THIS_RE.fullmatch(description)
    if other_than_this is not None:
        description = other_than_this.group("description").strip()
        excludes_source = True
    if permanent_description(description) is None:
        return None
    return description, excludes_source


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_sacrifice_one_of_choice_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SACRIFICE_ONE_OF_CHOICE_RE`'s shape; see the banner above."""
    stripped = " ".join(clause.split())
    if not stripped.lower().startswith("sacrifice "):
        return None
    choice = _read_sacrifice_choice(stripped)
    if choice is None:
        return None
    description, excludes_source = choice
    per_player = _sacrifice_of_choice_clause_effect(
        description, 1, with_indefinite_article(description), excludes_source=excludes_source
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        per_player(game, game.controller_of(stack_object), source, source_id_of(stack_object))

    return effect


#: "Sacrifice a Mountain. If you do, this Saga deals 3 damage to each
#: creature." (The First Eruption's chapter III), "sacrifice a Human. If you
#: can't, ..." (Archdemon of Greed) - `_SACRIFICE_ONE_OF_CHOICE_RE`'s
#: sacrifice with a CR 608.2c rider on whether it happened: "If you do" runs
#: the rest only when a permanent was sacrificed, "If you don't"/"If you
#: can't" only when none was (CR 608.2d: nothing to sacrifice). Read whole,
#: ahead of the clause splitter, which would otherwise hand the rider's
#: consequence to a clause reader with its condition cut off. A consequence
#: that does not read fails closed with a notice rather than running
#: unconditionally. The optional form, "you may sacrifice a Food. If you do,
#: ..." (Bristlebud Farmer), asks the "you may" only when there is something
#: to sacrifice (CR 608.2d), and "If you do" is whether a permanent was.
_SACRIFICE_THEN_IF_YOU_RE = re.compile(
    r"^(?P<may>you may )?(?P<sacrifice>sacrifice (?:another|an?|one) [^.]+?)\.\s*"
    r"if you (?P<branch>do|don'?t|can'?t|cannot),\s*(?P<rest>.+?)\.?$",
    re.IGNORECASE,
)


def _readable_ability_effect(text: str) -> AbilityEffect | None:
    """The whole-ability reader's effect for `text`, or None when it reads
    nothing or only a fail-closed notice stand-in - a rider that is only a
    notice must not make the sentence around it look handled."""
    effect = _ability_effect_or_notice(text)
    if effect is None or getattr(effect, "__name__", "").endswith("notice_only"):
        return None
    return effect


#: "Exile this token." / "Exile this creature." - the ability's own source
#: leaves the battlefield for exile (CR 406.1), but only if it is still the
#: object the ability came from (CR 400.7): the closing line of a granted or
#: copied "At end of combat, exile this token." (CR 707.9a).
_EXILE_SELF_RE = re.compile(r"^exile this (?P<noun>[a-z]+)\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s27")
def _parse_exile_self(text: str) -> AbilityEffect | None:
    """`_EXILE_SELF_RE`'s shape."""
    if not text.startswith(("Exile this ", "exile this ")):
        return None
    match = _EXILE_SELF_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    if match.group("noun").lower() not in _SACRIFICE_SELF_NOUNS | {"token"}:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and (ability.source_stamp is None or source.zone_change_stamp == ability.source_stamp)
        ):
            game.exile_permanent(source)

    return effect


#: "tap this creature" / "tap this creature and it deals 9 damage to you" /
#: "tap this creature and you lose 4 life" - the "If you can't" rider of a
#: Demon's upkeep sacrifice (CR 701.26a: tapping turns the permanent sideways).
#: The tail after "and" is read as its own instruction, with "it"/"this
#: <noun>" as the subject naming the same source.
_TAP_SELF_RIDER_RE = re.compile(
    r"^tap this (?P<noun>[a-z]+)(?: and (?P<tail>.+?))?\.?$", re.IGNORECASE
)
_SELF_SUBJECT_TAIL_RE = re.compile(r"^(?:it|this [a-z]+) (?P<verb>.+)$", re.IGNORECASE)


def _tap_self_rider_effect(text: str) -> AbilityEffect | None:
    """`_TAP_SELF_RIDER_RE`'s shape: tap the ability's own source if it is
    still the permanent that triggered, then run the tail."""
    match = _TAP_SELF_RIDER_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    noun = match.group("noun").lower()
    if noun not in _SACRIFICE_SELF_NOUNS:
        return None
    tail_effect: AbilityEffect | None = None
    tail = match.group("tail")
    if tail is not None:
        subject = _SELF_SUBJECT_TAIL_RE.fullmatch(tail.strip())
        tail_text = f"this {noun} {subject.group('verb')}." if subject else tail.strip() + "."
        tail_effect = parse_mixed_effect(tail_text)
        if tail_effect is None:
            return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and (ability.source_stamp is None or source.zone_change_stamp == ability.source_stamp)
        ):
            source.tap()
        if tail_effect is not None:
            tail_effect(game, ability)

    return effect


#: "this creature deals 4 damage to that creature" as the rider of a
#: sacrifice pair (Flame-Kin War Scout): "that creature" is the creature the
#: trigger's event is about (CR 608.2c's anaphora back to "When another
#: creature enters"), which the source - already sacrificed, so read from its
#: last known information (CR 113.7a) - deals the damage to.
_SELF_DEALS_DAMAGE_TO_THAT_CREATURE_RE = re.compile(
    rf"^this [a-z]+ deals (?P<n>{COUNT}) damage to that creature\.?$", re.IGNORECASE
)


def _event_creature_damage_effect(text: str) -> AbilityEffect | None:
    """`_SELF_DEALS_DAMAGE_TO_THAT_CREATURE_RE`'s shape. A blocks event names
    its other half instead of its subject, so that event is left to the
    general reader."""
    match = _SELF_DEALS_DAMAGE_TO_THAT_CREATURE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    general = _readable_ability_effect(text)
    if amount is None or general is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        if event.event is TriggerEvent.BLOCKS:
            general(game, ability)
            return
        referent = game.find_by_id(event.subject_id)
        if (
            isinstance(referent, CardState)
            and referent.zone is Zone.BATTLEFIELD
            and Type.CREATURE in game.characteristics_of(referent).types
        ):
            game.deal_damage(referent, amount, source=ability.source_or_last_known(game))

    return effect


def _sacrifice_rider_effect(text: str) -> AbilityEffect | None:
    """The consequence of a sacrifice branch on an ability: the event
    creature's damage, any whole-ability reading, else the tap-this-permanent
    compound."""
    return (
        _event_creature_damage_effect(text)
        or _readable_ability_effect(text)
        or _tap_self_rider_effect(text)
    )


def _sacrifice_then_if_you_effect(
    text: str, *, for_spell: bool, optional: bool = False
) -> TargetedClause | None:
    """`_SACRIFICE_THEN_IF_YOU_RE`'s shape; see the banner above. `optional`
    reads only the "you may sacrifice" form, otherwise only the bare one."""
    whole = " ".join(_strip_non_effect_preamble(text).split())
    if not whole.lower().startswith("you may sacrifice " if optional else "sacrifice "):
        return None
    match = _SACRIFICE_THEN_IF_YOU_RE.fullmatch(whole)
    if match is None:
        return None
    choice = _read_sacrifice_choice(match.group("sacrifice"))
    if choice is None:
        return None
    description, excludes_source = choice
    if optional and excludes_source:
        # "you may sacrifice another <thing>. If you do, ..." keeps the
        # consequence readers that know the sacrificed permanent (its mana
        # value, its type) - this reader has no memory of what went.
        return None
    requirement = permanent_description(description)
    assert requirement is not None
    per_player = _sacrifice_of_choice_clause_effect(
        description, 1, with_indefinite_article(description), excludes_source=excludes_source
    )
    rest = match.group("rest").strip() + "."
    consequence: Callable[[Game, Any], None] | None = (
        parse_mixed_effect_for_spell(rest) if for_spell else _sacrifice_rider_effect(rest)
    )
    wants_sacrifice = match.group("branch").lower() == "do"

    def names(stack_object: "StackObject") -> tuple[UUID | None, str]:
        if isinstance(stack_object, CardState):
            return stack_object.id, stack_object.card.name
        return stack_object.source_id, stack_object.source_name

    if consequence is None:

        def sacrifice_rider_notice_only(game: "Game", stack_object: "StackObject") -> None:
            source_id, source_name = names(stack_object)
            notice = ConditionalClauseNotice(
                source_id=source_id, source_name=source_name, text=whole
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)

        return sacrifice_rider_notice_only

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source_id, source_name = names(stack_object)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if requirement.rejects(permanent, player.username, game) is None
            and not (excludes_source and permanent.id == source_id)
        ]
        if optional and (
            not candidates
            or not game.may(
                player,
                match.group("sacrifice"),
                source=source_name,
                source_id=source_id_of(stack_object),
            )
        ):
            candidates = []
        else:
            per_player(game, player, source_name, source_id_of(stack_object))
        sacrificed = any(permanent.zone is not Zone.BATTLEFIELD for permanent in candidates)
        if sacrificed == wants_sacrifice:
            consequence(game, stack_object)  # type: ignore[arg-type]

    return effect


@ABILITY_TEXT.rung("s40", before=["dispatch.parse_mixed_effect"])
def _parse_sacrifice_then_if_you_ability_text(text: str) -> TargetedClause | None:
    return _sacrifice_then_if_you_effect(text, for_spell=False)


@ABILITY_TEXT.rung("s40", before=["dispatch.parse_mixed_effect"])
def _parse_may_sacrifice_then_if_you_ability_text(text: str) -> TargetedClause | None:
    """The optional form, tried after the narrower whole-text "you may
    sacrifice ... If you do" readers in earlier segments and ahead of the
    clause splitter (see `_SACRIFICE_THEN_IF_YOU_RE`'s banner)."""
    return _sacrifice_then_if_you_effect(text, for_spell=False, optional=True)


#: "Sacrifice this creature. If you do, this creature deals 4 damage to that
#: creature." (Flame-Kin War Scout), "sacrifice this artifact. If you do, this
#: artifact deals 10 damage to that player." (Booby Trap) - CR 701.21a's
#: sacrifice of the ability's own source with a CR 608.2c rider that runs only
#: when the sacrifice happened. The rider is read as its own whole ability
#: text, so the trigger event's referent ("that creature", "that player")
#: keeps reading across the pair, and it runs after the sacrifice with the
#: source's last known information (CR 113.7a).
_SACRIFICE_SELF_THEN_IF_YOU_DO_RE = re.compile(
    r"^sacrifice (?:it|this [a-z]+)\.\s*if you do,\s*(?P<rest>.+?)\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s40", before=["dispatch.parse_mixed_effect"])
def _parse_sacrifice_self_then_if_you_do_ability_text(text: str) -> AbilityEffect | None:
    """`_SACRIFICE_SELF_THEN_IF_YOU_DO_RE`'s shape; see the banner above."""
    whole = " ".join(_strip_non_effect_preamble(text).split())
    if not whole.lower().startswith("sacrifice "):
        return None
    match = _SACRIFICE_SELF_THEN_IF_YOU_DO_RE.fullmatch(whole)
    if match is None:
        return None
    sacrifice = _parse_sacrifice_self_clause(whole.split(".")[0], for_spell=False)
    consequence = _sacrifice_rider_effect(match.group("rest").strip() + ".")
    if sacrifice is None or consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        was_there = (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and (ability.source_stamp is None or source.zone_change_stamp == ability.source_stamp)
        )
        sacrifice(game, ability)
        if was_there and source is not None and source.zone is not Zone.BATTLEFIELD:
            consequence(game, ability)

    return effect


@SPELL_TEXT.rung("s11", for_spell=True)
def _parse_sacrifice_then_if_you_spell_text(text: str, *, for_spell: bool) -> TargetedClause | None:
    return _sacrifice_then_if_you_effect(text, for_spell=True)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_target_player_sacrifices_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_PLAYER_SACRIFICES_RE`'s shape - CR 701.21a's edict, aimed at
    one targeted player. A player with fewer matching permanents than `n`
    sacrifices everything they have (CR 608.2d: no impossible choice), and
    one with exactly `n` is never asked either - the same floor
    `_EACH_SACRIFICES_OF_THEIR_CHOICE_RE` already applies.
    """
    match = _TARGET_PLAYER_SACRIFICES_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("who"), allow_player_targets=True):
        return None
    count = parse_count(match.group("n"))
    description = match.group("description").strip()
    if match.group("tail") is not None:
        description = f"{description}{match.group('tail')}"
    requirement = permanent_description(description)
    if requirement is None or count is None or count < 1:
        return None
    wanted_words = with_indefinite_article(description) if count == 1 else f"{count} {description}"
    per_player = _sacrifice_of_choice_clause_effect(description, count, wanted_words)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        for target in game.resolve_targets(stack_object):
            if isinstance(target, Player):
                per_player(game, target, source, source_id_of(stack_object))

    return effect


def _parse_bare_sacrifice_of_choice_clause(part: str) -> ClauseEffect | None:
    """`_BARE_SACRIFICE_OF_CHOICE_RE`'s shape - one verb phrase of a G7
    `_parse_shared_subject_clauses` list, already stripped of its subject."""
    match = _BARE_SACRIFICE_OF_CHOICE_RE.fullmatch(part.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    description = match.group("description").strip()
    if match.group("tail") is not None:
        description = f"{description}{match.group('tail')}"
    requirement = permanent_description(description)
    if requirement is None or count is None or count < 1:
        return None
    wanted_words = with_indefinite_article(description) if count == 1 else f"{count} {description}"
    return _sacrifice_of_choice_clause_effect(description, count, wanted_words)


def _processable_exile_piles(game: "Game", controller: str) -> list[list[CardState]]:
    """The exiled cards `controller`'s opponents own, as the piles a player
    chooses among: every face-up card on its own, and each opponent's
    face-down cards grouped by the exile pile they sit in
    (`CardState.exile_annotation`) - CR 406.3 lets nobody look at a
    face-down card, so the player picks a pile and the card comes from it at
    random (the rulings on Wasteland Strangler)."""
    piles: list[list[CardState]] = []
    hidden: dict[tuple[str, object], list[CardState]] = {}
    for state in game.exile:
        if not isinstance(state, CardState) or state.zone is not Zone.EXILE:
            continue
        owner = state.owner
        if owner is None or owner == controller:
            continue
        if state.face_down:
            hidden.setdefault((owner, state.exile_annotation), []).append(state)
        else:
            piles.append([state])
    piles.extend(hidden.values())
    return piles


def _process_exiled_cards(
    game: "Game", player: Player, count: int, *, source: str, source_id: str | None
) -> bool:
    """Put `count` cards `player`'s opponents own from exile into their
    owners' graveyards, `player` choosing which (a random one from a chosen
    face-down pile), and say whether it was done. Fewer eligible cards than
    `count` means the cost can't be paid at all, so nothing moves."""
    piles = _processable_exile_piles(game, player.username)
    if sum(len(pile) for pile in piles) < count:
        return False
    for _ in range(count):
        piles = [pile for pile in _processable_exile_piles(game, player.username) if pile]
        if not piles:
            return False
        chosen_pile = piles[0]
        if len(piles) > 1:
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="choose a card an opponent owns in exile to put into its owner's graveyard",
                source=source,
                source_id=source_id,
                amount=1,
                cards=tuple(pile[0].id for pile in piles),
            )
            (picked,) = game.ask(decision)
            chosen_pile = next(pile for pile in piles if pile[0].id == picked)
        card = chosen_pile[0]
        if len(chosen_pile) > 1:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:process-exile")  # noqa: S311
            game.shuffles_performed += 1
            card = rng.choice(chosen_pile)
        card.face_up = True
        game.put_into_graveyard(card)
    return True


#: "Exile the top eight cards of your library. You may cast instant and
#: sorcery spells from among them this turn without paying their mana
#: costs." - Ral, Monsoon Mage's own −8. Generalized on the count and on the
#: type list the same way `_TYPE_COST_DECREASE` (`machines/cost.py`) reads
#: "Instant and sorcery spells you cast cost {1} less to cast." - a card
#: found among the exiled batch is only offered the grant if it carries one
#: of the named types, unlike Ugin, Eye of the Storms' −11 (any colorless
#: nonland card) or `_parse_exile_then_play_permission_clauses`
#: (every card, no type filter at all).
#:
#: Matched against the *whole, unsplit* text (like `_parse_choose_name_
#: search_and_exile_whole_text` above) rather than as a two-clause merge:
#: `_prepare_effect_clauses`'s own "and"-splitting cuts "instant and sorcery
#: spells" into two fragments before any clause-indexed parser ever sees the
#: sentence whole, the same trap that function's own docstring names.
_EXILE_TOP_THEN_CAST_TYPES_FREE_THIS_TURN_RE = re.compile(
    rf"^exile the top (?P<count>{COUNT}) cards? of your library\. you may cast "
    r"(?P<types>(?:creature|instant|sorcery|artifact|enchantment|planeswalker|land)"
    r"(?: and (?:creature|instant|sorcery|artifact|enchantment|planeswalker|land))?) "
    r"spells from among them this turn without paying their mana costs\.?$",
    re.IGNORECASE,
)


def _parse_exile_top_then_cast_types_free_this_turn_whole_text(
    text: str, *, for_spell: bool
) -> Effect | None:
    """Ral, Monsoon Mage's whole −8, as one CR 608.2c instruction - "them" in
    the second sentence is CR 607.1 anaphora back to the first sentence's own
    exile, the same reason `_parse_exile_then_play_permission_clauses`
    reads its own pair together rather than splitting them.

    Ability-only (no spell in the pool prints this shape). CR 118.9's "without
    paying their mana costs" is `pays_mana_cost=False`; the ordinary
    `until_end_of_turn=True` grant (not the longer `expires_end_of_next_turn`
    Wrenn's Resolve's own "your next turn" wording needs) matches "this turn"
    exactly. Only the cards among the exiled batch that carry one of the
    named types are ever granted a permission - the rest simply sit in exile,
    unreachable by this ability's own words, same as an unused Ugin find.
    """
    if for_spell:
        return None
    match = _EXILE_TOP_THEN_CAST_TYPES_FREE_THIS_TURN_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None
    words = [word.strip().lower() for word in match.group("types").split(" and ")]
    try:
        types = tuple(Type(word) for word in words)
    except ValueError:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        top = list(player.library[:count])
        for card in top:
            exiled = game.exile_permanent(card)
            if any(t in exiled.types for t in types):
                game.grant_play_permission(
                    exiled,
                    player.username,
                    action=PlayAction.CAST,
                    pays_mana_cost=False,
                    source_name=ability.source_name,
                    rule="CR 601.3",
                )

    return effect


#: "Exile the top X cards of target opponent's library. You may play lands
#: and cast spells from among cards exiled this way without paying their
#: mana costs." (Gix, Yawgmoth Praetor). Unlike `_EXILE_TOP_THEN_CAST_TYPES_
#: FREE_THIS_TURN_RE` right above (a lingering `PlayPermission` good for the
#: rest of the turn), Gix's own ruling is explicit: "You must play the cards
#: as you resolve the last ability. You can't wait and play them later" - a
#: CR 608.2g mid-resolution offer, not CR 601.3's standing permission, and
#: "lands and spells" both, not spells alone. `Game.may_cast_during_
#: resolution`'s own `play=True` already reads either kind correctly
#: (`_play_land_during_resolution` for a land, `cast_during_resolution`
#: otherwise); this loops it once per exiled card until none are left or the
#: player declines, matching "from among cards exiled this way" naming a
#: whole batch rather than Ral, Monsoon Mage's single-cast grant.
_EXILE_TOP_THEN_PLAY_DURING_RESOLUTION_RE = re.compile(
    rf"^exile the top (?P<count>{COUNT}) cards? of target opponent'?s library\.\s*"
    r"you may play lands and cast spells from among cards exiled this way "
    r"without paying (?:its|their) mana costs?\.?$",
    re.IGNORECASE,
)


def _parse_exile_top_then_play_during_resolution_whole_text(
    text: str, *, for_spell: bool
) -> Effect | None:
    """`_EXILE_TOP_THEN_PLAY_DURING_RESOLUTION_RE`'s shape - Gix, Yawgmoth
    Praetor's whole activated ability, as one CR 608.2c instruction.

    Ability-only: nothing in the pool prints this on a spell, and CR 601.2c
    targeting (`target opponent`) is an ability's own announcement
    (CR 602.2b), read off `game.resolve_targets(ability)` the same way every
    other targeted activated-ability effect in this file already is.
    """
    if for_spell:
        return None
    match = _EXILE_TOP_THEN_PLAY_DURING_RESOLUTION_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        opponent = next(
            (target for target in game.resolve_targets(ability) if isinstance(target, Player)),
            None,
        )
        if opponent is None:
            return
        top = list(opponent.library[:count])
        if not top:
            return
        _offer_free_casts_from_among(
            game,
            list(game.exile_cards(top)),
            ability.controller,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
            play=True,
        )

    return effect


#: "Exile it" (Ancient Adamantoise's own dies trigger) - CR 603.10a's
#: look-back "it", naming the ability's own source rather than a target.
#: Distinct from `_EXILE_THAT_CARD_RE`, whose "that card" is a card an
#: earlier clause in the *same* ability chose from a revealed hand, not the
#: source itself.
_EXILE_IT_RE = re.compile(r"^exile it$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_exile_dead_self_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Exile it" - moves the ability's own source to exile from wherever
    CR 700.4's move just put it (almost always the graveyard, since this only
    ever prints on a dies trigger in the pool). `_dead_self_found` is CR
    113.7a's fail-soft (a source that can no longer be found does nothing
    rather than raising) plus, once there is a dies event to check, CR
    400.7e's own tighter "only the incarnation the event created, only while
    it is still there" - see that helper's own docstring for why.

    Ability-only (`for_spell=False`): nothing in the pool prints this on a
    spell, and `AbilityOnStack.source`/`.event` are what finds the departed
    object - a resolving spell has no equivalent lookup for "itself" once its
    resolution has already moved it elsewhere.
    """
    if for_spell:
        return None
    if not _EXILE_IT_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = _dead_self_found(game, ability)
        if source is None:
            return
        game.exile_permanent(source)

    return effect


#: "Exile this artifact and all cards from all graveyards." (Silent Gravestone)
#: - the source and every graveyard card in one CR 608.2c instruction. The
#: bare "and" between the two objects is masked in `split_effect_clauses`
#: (`text._EXILE_SELF_AND_ALL_GRAVEYARDS_RE`) so the sentence reaches this
#: reader whole instead of as "exile this artifact" / "all cards from all
#: graveyards".
_EXILE_SELF_AND_ALL_GRAVEYARDS_RE = re.compile(
    r"^exile this [a-z]+ and all cards from all graveyards$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_exile_self_and_all_graveyards_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EXILE_SELF_AND_ALL_GRAVEYARDS_RE`'s shape. Ability-only: "this
    <type>" is the permanent the ability came from.

    CR 406.2 / CR 701.13a: exile moves an object to the exile zone from
    wherever it is, so one pass over every graveyard (the still-playing set,
    CR 104.3a) plus the source covers both halves. The source is exiled only
    if it is still the incarnation that made the ability (CR 400.7 - a
    permanent that has left and returned is a new object); the graveyards go
    regardless, since the ability exists independently of its source
    (CR 113.7a).
    """
    if for_spell:
        return None
    if _EXILE_SELF_AND_ALL_GRAVEYARDS_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source(game)
        if (
            source is not None
            and source.zone is Zone.BATTLEFIELD
            and (ability.source_stamp is None or source.zone_change_stamp == ability.source_stamp)
        ):
            game.exile_permanent(source)
        for player in game.players_in_game:
            for card_state in list(player.graveyard):
                game.exile_permanent(card_state)

    return effect


# --------------------------------------------------------------------------
# Wave W1 (revisited): "choose a card name"/"the same name as that card",
# then search a graveyard, a hand, and a library for cards with that name and
# exile them (CR 701.23a, run three times, once per zone) - The Stone Brain
# and Surgical Extraction. Matched whole, ahead of `_parse_mixed_clauses`'
# ordinary per-clause splitting: both cards' own "graveyard, hand, and
# library" and "with that name and exile them" each carry a bare "and"
# `_CLAUSE_SEPARATOR` would otherwise cut into unreadable fragments, so this
# reads the whole `text` argument `_parse_mixed_clauses` already has in
# scope, before `_prepare_effect_clauses` ever runs on it - the same
# "read it whole, then dispatch" shape `_parse_conditional_sacrifice_clause`
# uses from its own callers, reached from inside this wave's own dispatch
# surface instead of `_ability_effect_or_notice`/`_spell_effect_or_notice`.
#
# CR 701.23a: "To search for a card in a zone, look at all cards in that zone
# (even if it's a hidden zone) and find a card that matches the given
# description." Verified this session, along with the rest of the P7 zone
# widening's own citations (CR 701.23b/d, CR 701.24b/e) already recorded on
# `Game.search_library` in `models/game.py`, which both cards' own search
# reuses via its `zone` parameter - the wiring that parameter existed for.
# --------------------------------------------------------------------------


#: "sacrifice it" / "sacrifice this <noun>" - the ability's own source, named
#: the same self-referential way `_EXILE_IT_RE` and
#: `_RETURN_IT_TO_OWNERS_HAND_RE` above name theirs. The Millennium Calendar's
#: state trigger (CR 603.8) prints "sacrifice it"; Dress Down prints "sacrifice
#: this enchantment", Ball Lightning "sacrifice this creature", and a card
#: printing its own name reaches here as "this permanent" once
#: `trigger_effect_for` has normalised it. `noun` is checked against
#: `_SACRIFICE_SELF_NOUNS`, the same set `_sacrifice_restriction` reads.
_SACRIFICE_IT_RE = re.compile(
    r"^sacrifice (?:it|this (?P<noun>[a-z]+))(?: unless (?P<unless>.+?))?$", re.IGNORECASE
)


#: The conditions an "unless ..." tail on a self-sacrifice is read with, each
#: asked about the ability's own source. Uro and Kroxa's "unless it escaped".
#: A tail not listed here fails the whole clause, so it is never sacrificed
#: (or spared) on a condition nobody read.
_SELF_SACRIFICE_UNLESS_CONDITIONS: dict[str, Callable[["Game", CardState], bool]] = {
    "it escaped": _source_escaped,
}


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_sacrifice_self_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Sacrifice it" / "Sacrifice this enchantment" - CR 701.21a's keyword
    action aimed at the ability's own source: "To sacrifice a permanent, its
    controller moves it from the battlefield directly to its owner's
    graveyard."

    An "unless <condition>" tail (Uro, Titan of Nature's Wrath's "sacrifice it
    unless it escaped") is read through `_SELF_SACRIFICE_UNLESS_CONDITIONS`
    and checked as the ability resolves; when it holds, nothing is sacrificed.

    CR 113.7a keeps the ability alive once its source is gone ("Once activated
    or triggered, an ability exists on the stack independently of its source"),
    so a source that is no longer on the battlefield - already sacrificed,
    destroyed, or bounced in response - is simply not sacrificed again, and the
    rest of the ability still runs. That fail-soft is the same one
    `_parse_exile_dead_self_clause` gives its own self-reference. A source that
    left and came back is a new object (CR 400.7), which `source_stamp` tells
    apart from the object that triggered, so it is not sacrificed either.

    Ability-only (`for_spell=False`): a resolving spell is not a permanent and
    has no "it" of this kind to sacrifice.
    """
    if for_spell:
        return None
    match = _SACRIFICE_IT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    noun = match.group("noun")
    # A subtype names the source as well as a card type does - See Red's
    # "sacrifice this Aura" (CR 205.3) - and so does "this token" (CR 111.1),
    # the noun a quoted ability granted to a token or a copy that becomes one
    # prints for itself (Choreographed Sparks' "At the beginning of the end
    # step, sacrifice this token.").
    if (
        noun is not None
        and noun.lower() not in _SACRIFICE_SELF_NOUNS
        and noun.lower() != "token"
        and canonical_subtype(noun) is None
    ):
        return None
    unless_text = match.group("unless")
    unless = None
    if unless_text is not None:
        unless = _SELF_SACRIFICE_UNLESS_CONDITIONS.get(unless_text.strip().lower())
        if unless is None:
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if ability.source_stamp is not None and source.zone_change_stamp != ability.source_stamp:
            return
        if unless is not None and unless(game, source):
            return
        game.sacrifice(source)

    return effect


#: "sacrifice the chosen creature" - the object an as-enters choice recorded
#: on the ability's own source (CR 614.12a), Tyrannical Pitlord's leaves-the-
#: battlefield trigger.
_SACRIFICE_CHOSEN_CREATURE_RE = re.compile(r"^sacrifice the chosen creature$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_sacrifice_chosen_creature_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Sacrifice the chosen creature" - CR 701.21a aimed at the permanent the
    source recorded as it entered (`ChoiceKind.OBJECT`). The source has left the
    battlefield by the time a leaves-the-battlefield trigger resolves, so its
    last-known choice (CR 603.10a) is read; a chosen creature that is already
    gone is simply not sacrificed (CR 608.2b)."""
    if for_spell or _SACRIFICE_CHOSEN_CREATURE_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        source = ability.source(game)
        chosen = None if source is None else source.choice
        if chosen is None or chosen.kind is not ChoiceKind.OBJECT:
            return
        for permanent in game.battlefield:
            if str(permanent.id) == chosen.value:
                game.sacrifice(permanent)
                return

    return effect


#: Deadly Cover-Up's own whole spell: "Destroy all creatures. If evidence
#: was collected, exile a card from an opponent's graveyard. Then search its
#: owner's graveyard, hand, and library for any number of cards with that
#: name and exile them. That player shuffles, then draws a card for each
#: card exiled from their hand this way." A mass destruction
#: (`_parse_mass_destroy_predicate`'s own qualifier grammar, general to any
#: printed type list - not pinned to "creatures") ahead of a CR 118.12-style
#: conditional graveyard-hate tail that reuses `_search_and_exile_matching_
#: name`, the identical search-exile-shuffle-draw The Stone Brain's and
#: Surgical Extraction's own readers already established two sections
#: above: the chosen graveyard card's own name never has to be separately
#: exiled, since it is itself a graveyard card carrying that name and so is
#: swept up by the very search it names. `<condition>` is any `Game.
#: condition_holds` reads, and "your graveyard" alongside "an opponent's" is
#: read the same generic way the CR 701.4a family and every other
#: whose-zone reader in this module already keep the two apart.
_MASS_DESTROY_THEN_CONDITIONAL_GRAVEYARD_HATE_RE = re.compile(
    r"^destroy (?:each|all) (?P<destroy_rest>[^.]+)\.\s*"
    r"if (?P<condition>[^,]+), exile a card from (?P<whose>an opponent'?s|your) graveyard\.\s*"
    r"then search its owner'?s graveyard, hand, and library for any number of cards "
    r"with that name and exile them\.\s*"
    r"that player shuffles, then draws a card for each card exiled from their hand this way\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_mass_destroy_then_conditional_graveyard_hate_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_MASS_DESTROY_THEN_CONDITIONAL_GRAVEYARD_HATE_RE`'s shape, or `None`.

    Spell-only: nothing in the pool prints this shape as an ability. The
    condition is checked once, as the spell resolves, against the spell
    itself (`game.condition_holds`) - the same object `_parse_counter_
    unless_pays_then_condition_amount_upgrade_pair` already reads its own
    linked condition against.
    """
    if not for_spell:
        return None
    match = _MASS_DESTROY_THEN_CONDITIONAL_GRAVEYARD_HATE_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    destroy_predicate = _parse_mass_destroy_predicate(match.group("destroy_rest"))
    if destroy_predicate is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    whose = match.group("whose").lower()

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        source_id = source_id_of(spell)
        _destroy_matching(game, destroy_predicate, spell)
        held = game.condition_holds(controller.username, condition_text, spell)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id,
                source_name=spell.name,
                text=text,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if not held:
            return
        if whose == "your":
            zones_owner = controller
        else:
            zones_owner = _choose_an_opponent(game, controller, spell.name, source_id)
        if zones_owner is None:
            return
        candidates = list(zones_owner.graveyard)
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"exile a card from {zones_owner.username}'s graveyard",
                source=spell.name,
                source_id=source_id,
                amount=1,
                exact=True,
                cards=tuple(state.id for state in candidates),
            )
        )
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id.get(chosen_ids[0])
        if chosen is None:
            return
        _exiled, exiled_from_hand = _search_and_exile_matching_name(
            game,
            zones_owner,
            chosen.name,
            chooser=controller,
            cap=None,
            source=spell.name,
            source_id=source_id,
        )
        if exiled_from_hand:
            game.draw_cards(zones_owner.username, exiled_from_hand)

    return effect


# --------------------------------------------------------------------------
# TMT T7: end-step/attack flicker of new objects (CR 400.7), an optional-
# payment delayed return (CR 118.12), a next-upkeep delayed random discard,
# an entered-this-turn mass bounce, a reflexive dies-exile (CR 603.12), and
# same-name mass reanimation from a graveyard. Every reader below is tried
# from `_ability_effect_or_notice`, ahead of `parse_mixed_effect`'s ordinary
# clause split, because each one's own printed text carries a bare "and" or a
# multi-sentence anaphora `split_effect_clauses` would otherwise cut into
# unreadable fragments - the same "read it whole first" treatment that
# function's own docstring already gives `_parse_choose_name_search_and_
# exile_whole_text` and `_parse_delayed_blink_clauses`.
# --------------------------------------------------------------------------

#: "exile up to one target `<X>` and up to one target `<Y>`[ and up to one
#: target `<Z>` ...]. Then return them to the battlefield under their
#: owners' control." - Don & Leo, Problem Solvers' own end-step trigger
#: (TMT). Two *independent* optional targets joined by a bare "and"
#: (`split_effect_clauses` cuts there), each "up to one" (CR 115.6) and of a
#: different description - `_targets_understood` refuses this outright
#: (its own docstring: "two 'target' words is two requirements, not this
#: shape"), correctly, for every *other* verb in this file, none of which
#: needs to treat two independently-optional targets as one instruction. This
#: shape does: CR 608.2c runs "exile ... and ..." as a single sentence, and
#: what happens to whatever was actually chosen (0, 1, or every one of them)
#: is identical regardless of how many separate descriptions produced it, so
#: this reader checks each requirement itself instead of going through that
#: shared gate.
_EXILE_SEVERAL_UP_TO_ONE_TARGETS_THEN_RETURN_RE = re.compile(
    r"^exile (?P<phrase>up to one target .+? and up to one target .+?)\.\s*"
    r"then (?P<return_text>return them to the battlefield.*)$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s36")
def _parse_exile_several_up_to_one_targets_then_return_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_SEVERAL_UP_TO_ONE_TARGETS_THEN_RETURN_RE`'s shape, or `None`.

    Every requirement `profile_for_text` reads off the exile phrase must be
    its own "up to one" (CR 115.6's zero-or-one: `minimum == 0`, `maximum ==
    1`, never unbounded), live only on the battlefield, and never a player -
    the same three checks `_targets_understood` already makes for a *single*
    requirement, just applied per-requirement here since there is more than
    one. Fewer than two requirements defers to `_parse_exile_then_return_
    clause_pair`'s own single-target reading further down the chain, so this
    reader never competes with, or changes the result of, that
    already-tested path.

    The return half is exactly `_RETURN_TO_BATTLEFIELD_RE` - "return them to
    the battlefield under their owners' control" is that regex's plural
    "them"/"their owners'" branch, already built for Gone Fishing and
    Displace's own multi-target blinks.
    """
    match = _EXILE_SEVERAL_UP_TO_ONE_TARGETS_THEN_RETURN_RE.fullmatch(
        " ".join(text.strip().split())
    )
    if match is None:
        return None
    profile = profile_for_text(match.group("phrase"))
    if not profile.understood or len(profile.requirements) < 2:
        return None
    for requirement in profile.requirements:
        if requirement.unbounded or requirement.minimum != 0 or requirement.maximum != 1:
            return None
        if requirement.zones != frozenset({Zone.BATTLEFIELD}):
            return None
        if requirement.allows_players:
            return None
    return_match = _RETURN_TO_BATTLEFIELD_RE.fullmatch(match.group("return_text").strip())
    if return_match is None:
        return None
    tapped = return_match.group("tapped") is not None
    transformed = return_match.group("transformed") is not None
    control = return_match.group("control")
    counter_word = return_match.group("counter")
    counter_kind = _counter_kind(counter_word) if counter_word else None
    counter_n_word = return_match.group("counter_n")
    counter_amount = (
        ((parse_count(counter_n_word) if counter_n_word else 1) or 1) if counter_word else 0
    )
    owners_control = control is not None and control.lower() != "your"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability).username
        exiled_cards: list[CardState] = []
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move.
            exiled_cards.append(exiled)
        if not exiled_cards:
            return
        with game.entering_together():  # CR 603.6a: one arrival, together
            for exiled in exiled_cards:
                owner = exiled.owner or controller
                new_controller = owner if owners_control else controller
                permanent = game.put_onto_battlefield(
                    exiled, new_controller, tapped=tapped, transformed=transformed
                )
                if counter_kind is not None and permanent.zone is Zone.BATTLEFIELD:
                    game.add_counters(permanent, counter_kind, counter_amount)

    return effect


#: "exile up to one [other] target creature you own, then return it to the
#: battlefield under your control tapped and attacking." - The Neutrinos'
#: own attack trigger (TMT). `split_effect_clauses`'s bare "and" between
#: "attacking" and the rest cuts this into three unreadable fragments
#: (verified: `['exile ...', 'return it to the battlefield ... tapped',
#: 'attacking']`), so it is read whole here instead, the tapped-and-attacking
#: twin of `_parse_exile_then_return_clause_pair`'s plain "tapped".
_EXILE_TARGET_THEN_RETURN_TAPPED_AND_ATTACKING_RE = re.compile(
    r"^exile (?P<phrase>up to one .*?target.+?), then return it to the battlefield under "
    r"(?P<control>your|its owner'?s) control tapped and attacking\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_exile_target_then_return_tapped_and_attacking_clause(
    text: str,
) -> AbilityEffect | None:
    """`_EXILE_TARGET_THEN_RETURN_TAPPED_AND_ATTACKING_RE`'s shape, or `None`.

    CR 508.4: a creature put onto the battlefield attacking was never
    *declared* an attacker, so nothing here raises an "attacks" event - the
    same non-event `models.token._put_onto_the_battlefield_attacking` already
    keeps for a token created attacking, reused verbatim (that function reads
    only `CardState`-level fields, never anything token-specific).

    No defender is named on the card, and CR 508.4's own text leaves "which
    defending player" to the controller's choice when nothing else specifies
    it - but this trigger only ever fires while its own source **is itself
    currently attacking** ("whenever ~ attack"), so the returned creature
    reads as joining that same attack rather than opening a fresh choice of
    its own, the identical reading `_parse_return_target_from_graveyard_
    tapped_and_attacking_clause` already gives Grim Reaper, Lethal
    Legionnaire's own reflexive reanimation (that reader's own docstring:
    "with no attacked player/planeswalker named, the reanimated creature
    attacks whoever/whatever the resolving ability's own source is currently
    attacking", CR 508.4c). A source that is not (somehow) found attacking
    right now - CR 113.7a's source already gone, or the trigger firing with
    no live `Attack` to read - does nothing rather than guessing a defender.

    Ability-only: `game.combat.attack_by` reads the resolving ability's own
    source (`AbilityOnStack.source`), which only an ability - never a
    resolving spell - carries; nothing in the pool prints this on a spell.
    """
    match = _EXILE_TARGET_THEN_RETURN_TAPPED_AND_ATTACKING_RE.fullmatch(
        " ".join(text.strip().split())
    )
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    owners_control = match.group("control").lower() != "your"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        current_attack = game.combat.attack_by(source.id)
        if current_attack is None:
            return  # CR 113.7a / no live attack to join.
        controller = game.controller_of(ability)
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        exiled = game.exile_permanent(targets[0])
        if exiled.zone is not Zone.EXILE:
            return
        new_controller = (
            (exiled.owner or controller.username) if owners_control else (controller.username)
        )
        entered = game.put_onto_battlefield(exiled, new_controller, tapped=True)
        if entered.zone is not Zone.BATTLEFIELD:
            return
        from ...models.token import _put_onto_the_battlefield_attacking

        _put_onto_the_battlefield_attacking(game, entered, current_attack.defender)

    return effect


#: "exile up to one other target creature. At the beginning of the next end
#: step, you may pay `<cost>`. If you don't, return that card to the
#: battlefield under its owner's control." - Koya, Death from Above's own
#: enters-the-battlefield trigger (TMT). Three clauses `split_effect_clauses`
#: cuts apart on their own periods; read whole here since the third's "if you
#: don't" is CR 118.12's own anaphora back to the second's "you may pay", and
#: the second's "that card" (CR 400.7) is whatever the first sentence's own
#: exile just moved - the identical linkage `_parse_delayed_blink_clauses`
#: already threads through its own "that card", now with a real choice
#: sitting between the exile and the return instead of an unconditional one.
_EXILE_THEN_PAY_OR_ELSE_RETURN_RE = re.compile(
    r"^exile (?P<phrase>up to one (?:other )?target creature)\.\s*"
    r"at the beginning of the next end step, you may pay (?P<cost>(?:\{[^}]+\})+)\.\s*"
    r"if you don'?t, return that card to the battlefield under its owner'?s control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_exile_then_pay_or_else_return_clause(text: str) -> AbilityEffect | None:
    """`_EXILE_THEN_PAY_OR_ELSE_RETURN_RE`'s shape, or `None`.

    The exile is unconditional and immediate; the payment question is asked
    later, when the delayed trigger it creates now resolves at the next end
    step (CR 603.7a). `PayOrElseReturnExiledCard` is that delayed effect: pay,
    and the card stays in exile; don't, and it returns under its owner's
    control (CR 610.3c's default, which is also all this printing ever
    names).
    """
    match = _EXILE_THEN_PAY_OR_ELSE_RETURN_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    cost = ManaCost.try_parse(match.group("cost"))
    if cost is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        exiled = game.exile_permanent(targets[0])
        if exiled.zone is not Zone.EXILE:
            return
        game.create_delayed_trigger(
            DelayedTrigger(
                text=(
                    f"At the beginning of the next end step, you may pay "
                    f"{match.group('cost')}. If you don't, return that card to the "
                    f"battlefield under its owner's control."
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=controller.username,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=exiled.id,
                expected_zone=Zone.EXILE,
                expected_stamp=exiled.zone_change_stamp,
                effect=PayOrElseReturnExiledCard(cost=cost),
            )
        )

    return effect


#: Northampton Farm's own linked-exile-return pair (TMT), read off
#: `machines/linked_exile.py`'s two per-clause parsers. Both clauses split
#: cleanly (`['Return a creature card exiled with this land to the
#: battlefield under your control', "Return each other card exiled with this
#: land to its owner's hand"]`), so this only has to run whichever one a
#: clause is, in printed order - `_ability_effect_or_notice` calls it on the
#: *whole*, unsplit ability text, so the split happens here rather than
#: through `parse_mixed_effect`, keeping both clauses' shared "this land" the
#: one thing `machines/linked_exile.py` has to reason about.
@ABILITY_TEXT.rung("s38")
def _parse_linked_exile_return_pair_clause(text: str) -> AbilityEffect | None:
    """Northampton Farm's own two-sentence ability, or Endless Sands' own
    (Modern-legal proof printing) single-sentence one - `None` if `text` is
    neither.

    Northampton Farm's pair: both parsers are tried against each of exactly
    two sentences (a period-separated split is safe here: neither clause's
    own printed text contains a bare " and " or a mid-sentence period), and
    both must match - CR 608.2c never runs half of a printed ability, so one
    recognised sentence next to one this module cannot read still fails the
    whole thing closed rather than silently dropping the unreadable half.

    Endless Sands prints only the first half ("Return each creature card
    exiled with this land to the battlefield under its owner's control.")
    with no "sweep up the rest" sentence at all - CR 607.2a's link still
    holds (its own single ability both exiles and reads "exiled with"), there
    is simply nothing left over to name a second instruction for.
    """
    sentences = [part.strip() for part in text.strip().split(".") if part.strip()]
    if len(sentences) == 1:
        return parse_return_linked_creature_clause(sentences[0])
    if len(sentences) != 2:
        return None
    first = parse_return_linked_creature_clause(sentences[0])
    second = parse_return_other_linked_cards_to_hand_clause(sentences[1])
    if first is None or second is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        first(game, ability)
        game.announce_batched_events()  # CR 603.2c: one event per instruction
        second(game, ability)

    return effect


@ABILITY_TEXT.rung("s38")
def _parse_champion_clause(text: str) -> AbilityEffect | None:
    """Champion's two linked triggers (CR 702.72a) - see
    `legacy_keywords.parse_champion_clause`."""
    return parse_champion_clause(text)


@ABILITY_TEXT.rung("s38")
def _parse_clash_clause(text: str) -> AbilityEffect | None:
    """Clash with an opponent (CR 701.30b) and its win/otherwise branches - see
    `legacy_keywords.parse_clash_clause`."""
    return parse_clash_clause(text)


@ABILITY_TEXT.rung("s38")
def _parse_return_all_linked_to_hand_lose_life_clause(text: str) -> AbilityEffect | None:
    """Asmodeus the Archfiend's {B} - see
    `linked_exile.parse_return_all_linked_to_hand_lose_life_clause`."""
    return parse_return_all_linked_to_hand_lose_life_clause(text)


#: "`<antecedent>`. [Then ]you may exile `<self>` and `<n>` cards named
#: `<name>` from your graveyard. If you do, `<consequence>`." (CR 118.12's
#: cost-paid-on-resolution "if you do", CR 201.5's self-reference) - the
#: Approach cycle's own "a deck can have any number of cards named
#: `<name>`" template: Sphinx's Approach's own "you may exile **this
#: spell**", Dragon's Approach's own "you may exile **Dragon's Approach**"
#: (the literal printed name - never validated against the resolving
#: spell's actual name here, the same "the source is never named here"
#: reading the damage-dealing clause family already gives a literal source
#: prefix). `<antecedent>` is read and run exactly as it would be on its
#: own (a plain draw, a damage clause, ...), and `<consequence>` is always
#: a search-and-put, but neither is hardcoded to one shape - both are
#: re-dispatched through the ordinary spell parser.
_MAY_EXILE_SELF_AND_NAMED_COPIES_IF_YOU_DO_RE = re.compile(
    r"^(?P<antecedent>.+?)\.\s*(?:then\s+)?you may exile "
    r"(?:this spell|this card|[^.]+?) and "
    rf"(?P<n>{COUNT}) cards? named (?P<name>.+?) from your graveyard\.\s*"
    r"if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s16")
def _parse_may_exile_self_and_named_copies_if_you_do_clause(text: str) -> Effect | None:
    """`_MAY_EXILE_SELF_AND_NAMED_COPIES_IF_YOU_DO_RE`'s shape, or `None`.

    The antecedent always happens first (it carries no "may" of its own),
    read through `_spell_effect_or_notice` exactly as it would be alone.
    Then CR 118.12: exiling is the cost paid *as this spell resolves*, not
    a separate action with its own success or failure to check - "if you
    do" is answered by whether the player said yes, matching `_parse_
    conditional_sacrifice_clause`'s own reading of the identical rule.
    `Game.exile_cards` moves the resolving spell itself and every chosen
    graveyard copy together, as one CR 608.2b instruction - the same call
    `_parse_reveal_from_outside_the_game_into_hand_clause` already makes for
    Burning Wish's own bare "Exile <this>." on a spell still mid-resolution
    (popped off the stack, no zone of its own until this gives it one).
    """
    match = _MAY_EXILE_SELF_AND_NAMED_COPIES_IF_YOU_DO_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    antecedent_text = match.group("antecedent").strip()
    if not antecedent_text.endswith("."):
        antecedent_text += "."
    antecedent_effect = _spell_effect_or_notice(antecedent_text)
    if antecedent_effect is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    copy_name = match.group("name").strip()
    consequence_text = match.group("consequence").strip()
    consequence_effect = parse_mixed_effect_for_spell(consequence_text)
    if consequence_effect is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        antecedent_effect(game, spell)
        controller = game.controller_of(spell)
        candidates = [
            card for card in controller.graveyard if card.name.lower() == copy_name.lower()
        ]
        needed = min(count, len(candidates))
        if not game.may(
            controller,
            f"exile this spell and {needed} card(s) named {copy_name} from your graveyard",
            source=spell.name,
            source_id=source_id_of(spell),
        ):
            return
        chosen: list[CardState] = []
        if needed:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"choose {needed} card(s) named {copy_name} to exile from your graveyard"
                    ),
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=needed,
                    cards=tuple(candidate.id for candidate in candidates),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {candidate.id: candidate for candidate in candidates}
            chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        game.exile_cards([spell, *chosen])
        # CR 118.12: "if you do" is answered by the cost having been paid,
        # not by what it happened to accomplish - the consequence runs
        # whether or not the graveyard held every one of the named copies.
        consequence_effect(game, spell)

    return effect


#: Hex Magic: "Exile all the cards from your hand, then draw that many
#: cards. Until the end of your next turn, you may play cards exiled this
#: way." and Invasion of Kaldheim's own triggered-ability twin, "When this
#: Siege enters, exile all cards from your hand, ..." (no "the" before
#: "cards" - a real, differently-worded printing of the identical
#: instruction, not a second copy of it). Read as one CR 608.2c instruction
#: chain (the exile-and-draw sentence, then the grant that names what was
#: just exiled), matched against the whole printed text rather than split
#: into per-clause fragments the way `_parse_mixed_clauses` would otherwise
#: cut the "then" and the second sentence apart with nothing here to read
#: either half back together.
#:
#: The grant is `PlayPermission` again, one per card actually exiled, with
#: `until_next_turn_of` set for CR 611.2a's "until the end of your next
#: turn" - the same field `Wish`'s own grant leaves at its default
#: `until_end_of_turn=True` because Wish's own window is only "this turn".
_EXILE_HAND_DRAW_THEN_PLAY_UNTIL_NEXT_TURN_RE = re.compile(
    r"^exile all(?: of)?(?: the)? cards? from your hand, then draw that many cards\.\s*"
    r"until the end of your next turn, you may play cards exiled this way\.?$",
    re.IGNORECASE,
)


def _exile_hand_draw_then_play_until_next_turn(
    game: "Game", controller: Player, source_name: str
) -> None:
    """`_EXILE_HAND_DRAW_THEN_PLAY_UNTIL_NEXT_TURN_RE`'s shape, shared by
    Hex Magic's own spell body and Invasion of Kaldheim's identical
    triggered-ability one - see that regex's own docstring."""
    hand_cards = list(controller.hand)
    # One instruction, one batch, into CR 400.1's shared exile zone
    # (CR 406.2) - not `Player.move` plus an append, which listed every
    # card of the hand in the real exile zone and in a pile of its
    # controller's own at the same time.
    game.exile_cards(hand_cards)
    game.draw_cards(controller.username, len(hand_cards))
    for card in hand_cards:
        game.grant_play_permission(
            card,
            controller.username,
            action=PlayAction.PLAY,
            pays_mana_cost=True,
            source_name=source_name,
            zone=Zone.EXILE,
            rule="CR 601.3",
            until_next_turn_of=controller.username,
        )


@SPELL_TEXT.rung("s21")
def _parse_exile_hand_draw_then_play_until_next_turn_clause(effect_text: str) -> Effect | None:
    """`_EXILE_HAND_DRAW_THEN_PLAY_UNTIL_NEXT_TURN_RE`'s shape on a spell,
    or `None`."""
    if _EXILE_HAND_DRAW_THEN_PLAY_UNTIL_NEXT_TURN_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        _exile_hand_draw_then_play_until_next_turn(game, game.controller_of(spell), spell.name)

    return effect


@ABILITY_TEXT.rung("s1")
def _parse_exile_hand_draw_then_play_until_next_turn_ability_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_EXILE_HAND_DRAW_THEN_PLAY_UNTIL_NEXT_TURN_RE`'s shape on a
    triggered ability (Invasion of Kaldheim's own Siege ETB), or `None`."""
    if _EXILE_HAND_DRAW_THEN_PLAY_UNTIL_NEXT_TURN_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        _exile_hand_draw_then_play_until_next_turn(
            game, game.player(ability.controller), ability.source_name
        )

    return effect


#: The printed, non-keyword twin of ward (CR 702.21a) on a becomes-target
#: trigger: "counter that spell unless its controller discards a card"
#: (Reality Smasher), "counter that spell or ability unless its controller
#: pays {2}" (Frost Titan). "that spell [or ability]" is the object that did
#: the targeting (`GameEvent.targeted_by`); the cost after the verb is any
#: printed cost `machines/cost.total_cost_for_phrase` reads, the verb put
#: back into its imperative form ("discards a card" -> "discard a card").
_COUNTER_TARGETING_OBJECT_UNLESS_RE = re.compile(
    r"^counter that (?:spell or ability|spell|ability) unless its controller "
    r"(?P<verb>pays|discards|sacrifices|exiles|returns) (?P<rest>.+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s23")
def _parse_counter_targeting_object_unless_clause(text: str) -> AbilityEffect | None:
    """`_COUNTER_TARGETING_OBJECT_UNLESS_RE`'s shape.

    CR 118.12a: ""[Do something] unless [a player does something else]"
    means the same thing as "[A player may do something else]. If [that
    player doesn't], [do something]."" - the targeting object's controller
    is offered the cost through `Game.may_pay_unless_cost` (the same path
    ward's own `_ward_effect` takes), and a cost they cannot pay (CR 118.3)
    is simply not paid. Unpaid, the object is countered (CR 701.6a). A
    targeting object already gone from the stack leaves nothing to counter
    and nobody is asked.
    """
    match = _COUNTER_TARGETING_OBJECT_UNLESS_RE.fullmatch(text.strip())
    if match is None:
        return None

    from ..cost import total_cost_for_phrase

    verb = match.group("verb").lower()
    rest = match.group("rest").strip()
    if verb == "pays":
        phrase = rest if rest.startswith("{") else f"pay {rest}"
    else:
        phrase = f"{verb[:-1]} {rest}"
    if total_cost_for_phrase(phrase) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.targeted_by is None:
            return
        targeting = next(
            (item for item in game.stack if getattr(item, "id", None) == event.targeted_by),
            None,
        )
        if targeting is None:
            return
        payer = game.controller_of(targeting).username
        cost = total_cost_for_phrase(phrase, payer)
        if cost is not None and game.may_pay_unless_cost(
            payer,
            cost.assign_payer(payer),
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        game.counter(targeting)

    return effect


# --------------------------------------------------------------------------
# "Sacrifice N <group>." (CR 701.21a) with the player choosing which
# --------------------------------------------------------------------------
#
# Lotus Field's own enters trigger, "sacrifice two lands." CR 701.21a: "To
# sacrifice a permanent, its controller moves it from the battlefield
# directly to its owner's graveyard." Which two is not stated, so it is
# CR 608.2d's choice, made by the ability's controller as it resolves, among
# the permanents *they* control - a sacrifice can only ever be of one's own
# permanent (CR 701.21a's "its controller"), which is why the candidate set
# is `Game.permanents_controlled_by` and never the whole battlefield.
#
# Fewer permanents than the printed number means sacrificing every one there
# is: CR 608.2d's "the player can't choose an option that's illegal or
# impossible" leaves the rest simply undone rather than the instruction
# failing, and Lotus Field with one other land in play really does sacrifice
# itself and that land.

#
# "Sacrifice any number of lands." (Scapeshift) is the same instruction with
# CR 107.1c's "any number" - zero upward, the player's own choice - and the
# number actually sacrificed is recorded for the next clause's "that many"
# (Scapeshift's "Search your library for up to that many land cards").
_SACRIFICE_N_GROUP_RE = re.compile(
    rf"^sacrifice (?:(?P<any>any number of)|(?P<n>{COUNT})) (?P<group>[a-z]+s)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_sacrifice_n_of_a_group_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SACRIFICE_N_GROUP_RE`'s shape - Lotus Field's "sacrifice two lands."
    and Scapeshift's "Sacrifice any number of lands."

    The group is one of CR 205.2a's card types, read off the *computed* board
    (`Game.computed_board`) the same way `_parse_mass_type_qualifier` reads a mass
    destruction's own group, so an animated land is still a land and a
    permanent that only became a creature through a continuous effect counts
    as one. Anything else - a subtype, a colour, "another creature you
    control" - is not read and takes the clause down with it.
    """
    match = _SACRIFICE_N_GROUP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    any_number = match.group("any") is not None
    count = None if any_number else parse_count(match.group("n"))
    if count is None and not any_number:
        return None
    card_type = _singular_card_type(match.group("group"))
    if card_type is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        board = game.computed_board()
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if card_type in board.of(permanent).types
        ]
        if not candidates:
            game.record_count(0)
            return
        wanted = len(candidates) if count is None else min(count, len(candidates))
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=(
                    f"sacrifice any number of {card_type.value}s"
                    if any_number
                    else f"sacrifice {wanted} {card_type.value}(s)"
                ),
                source=source_name,
                amount=wanted,
                cards=tuple(state.id for state in candidates),
                source_id=source_id_of(stack_object),
                exact=not any_number,
            )
        )
        by_id = {state.id: state for state in candidates}
        sacrificed = 0
        for card_id in chosen_ids:
            permanent = by_id.get(card_id)
            if permanent is not None and permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)
                sacrificed += 1
        # CR 608.2c: Scapeshift's "up to that many" is the number sacrificed.
        game.record_count(sacrificed)

    return effect


# --------------------------------------------------------------------------
# "Each opponent sacrifices a <description> of their choice." (CR 701.21a)
# --------------------------------------------------------------------------
#
# The edict template: Sheoldred's Edict's three modes, Yawning Fissure's
# land, Clip Wings' "a creature of their choice with flying" (the qualifier
# printed after "of their choice"). Nothing is targeted (CR 115.10a); each
# sacrificing player chooses among the permanents *they* control that match
# the description (CR 701.21a: a player can only sacrifice a permanent they
# control), while the effect is applied (CR 608.2d). With several such
# players, CR 101.4 has them choose in APNAP order and the sacrifices then
# happen together, so every choice is made before anything leaves.
#
# The description is `machines/targeting.permanent_description`, the target
# grammar itself, so "nontoken", "token", "non<type>", a type list joined by
# "or", and a trailing "with <keyword>" read the same here as after "target".
# A player with no matching permanent sacrifices nothing and is asked nothing
# (CR 608.2d: no impossible choice); one with exactly as many as required has
# no choice to make and is not asked either.

_EACH_SACRIFICES_OF_THEIR_CHOICE_RE = re.compile(
    rf"^each (?P<who>opponent|player) sacrifices (?P<n>{COUNT}) (?P<description>.+?) "
    r"of their choice(?P<tail> with [^.]+?)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s33")
def _parse_each_sacrifices_of_their_choice_clause(clause: str) -> TargetedClause | None:
    """`_EACH_SACRIFICES_OF_THEIR_CHOICE_RE`'s shape; see the banner above."""
    match = _EACH_SACRIFICES_OF_THEIR_CHOICE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    description = match.group("description").strip()
    if match.group("tail") is not None:
        description = f"{description}{match.group('tail')}"
    requirement = permanent_description(description)
    if requirement is None or count < 1:
        return None
    opponents_only = match.group("who").lower() == "opponent"
    wanted_words = with_indefinite_article(description) if count == 1 else f"{count} {description}"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        chosen: list[CardState] = []
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller:
                continue
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if requirement.rejects(permanent, player.username, game) is None
            ]
            if len(candidates) <= count:
                chosen.extend(candidates)
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"sacrifice {wanted_words}",
                    source=source_name,
                    amount=count,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen.extend(by_id[card_id] for card_id in chosen_ids if card_id in by_id)
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return effect


# --------------------------------------------------------------------------
# "<Player> sacrifices an <type> and a <type> of their choice." (CR 701.21a)
# --------------------------------------------------------------------------
#
# The multi-type edict: Structural Collapse's "Target player sacrifices an
# artifact and a land of their choice.", To the Slaughter's "that player
# sacrifices a creature and a planeswalker of their choice". One slot per
# listed description; the sacrificing player chooses one permanent for each
# slot from the permanents they control (CR 701.21a), a slot with nothing to
# fill it is skipped (CR 608.2d: no impossible choice), and everything chosen
# is sacrificed together once every choice is made.
#
# One permanent can fill only one slot - it is one object and can be
# sacrificed once - so an artifact land is either the artifact or the land.
# A player who can fill more slots with different permanents must: a slot is
# only offered the permanents that still leave the most slots fillable
# (`_one_of_each_choice`), so a lone artifact land is never spent on the land
# slot while the artifact slot goes empty.

_MULTI_SLOT_SPLIT_RE = re.compile(r"\s+and\s+(?=(?:an?|one)\s)", re.IGNORECASE)

_PLAYER_SACRIFICES_ONE_OF_EACH_RE = re.compile(
    r"^(?P<who>target (?:player|opponent)|each (?:opponent|player)) sacrifices "
    r"(?P<slots>an? [^.]+? and an? [^.]+?) of their choice\.?$",
    re.IGNORECASE,
)


def _one_of_each_slots(text: str) -> list[tuple[str, TargetRequirement]] | None:
    """`text` ("an artifact and a land") as one `(description, requirement)`
    per slot, or `None` when it is not two or more article-led descriptions
    this engine reads whole."""
    parts = _MULTI_SLOT_SPLIT_RE.split(text.strip())
    if len(parts) < 2:
        return None
    slots: list[tuple[str, TargetRequirement]] = []
    for part in parts:
        description = re.sub(r"^(?:an?|one)\s+", "", part.strip(), flags=re.IGNORECASE)
        requirement = permanent_description(description)
        if requirement is None:
            return None
        slots.append((description, requirement))
    return slots


def _one_of_each_choice(
    game: "Game",
    player: Player,
    slots: list[tuple[str, TargetRequirement]],
    source: str,
    source_id: str | None,
) -> list[CardState]:
    """The permanents `player` chooses to fill `slots`, in slot order, each
    slot offered only the permanents that keep the greatest number of slots
    fillable (see the banner above). A slot with a single such permanent is
    not asked about."""
    pool = list(game.permanents_controlled_by(player.username))
    matching = [
        [
            permanent
            for permanent in pool
            if requirement.rejects(permanent, player.username, game) is None
        ]
        for _description, requirement in slots
    ]

    def fillable(index: int, used: frozenset[str]) -> int:
        if index == len(slots):
            return 0
        best = fillable(index + 1, used)
        for permanent in matching[index]:
            if permanent.id not in used:
                best = max(best, 1 + fillable(index + 1, used | {permanent.id}))
        return best

    chosen: list[CardState] = []
    used: frozenset[str] = frozenset()
    for index, (description, _requirement) in enumerate(slots):
        target = fillable(index, used)
        candidates = [
            permanent
            for permanent in matching[index]
            if permanent.id not in used and 1 + fillable(index + 1, used | {permanent.id}) == target
        ]
        if not candidates:
            continue
        pick = candidates[0]
        if len(candidates) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"sacrifice {with_indefinite_article(description)}",
                    source=source,
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id,
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            picked = [by_id[card_id] for card_id in answer if card_id in by_id]
            if picked:
                pick = picked[0]
        chosen.append(pick)
        used = used | {pick.id}
    return chosen


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_player_sacrifices_one_of_each_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`_PLAYER_SACRIFICES_ONE_OF_EACH_RE`'s sentence among `text`'s sentences.

    Read before the clause split because that split cuts the sentence at its
    own "and" (`_clauses_around_sentences`)."""
    lowered = text.lower()
    if " sacrifices " not in lowered or " of their choice" not in lowered:
        return None

    def reader(sentences: list[str], index: int) -> tuple[int, TargetedClause] | None:
        effect = _parse_player_sacrifices_one_of_each_clause(sentences[index], for_spell=for_spell)
        return None if effect is None else (1, effect)

    return _clauses_around_sentences(text, reader, for_spell=for_spell)


def _parse_player_sacrifices_one_of_each_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_PLAYER_SACRIFICES_ONE_OF_EACH_RE`'s shape; see the banner above.

    "Target player/opponent" is the one targeted player (CR 115.1), "each
    player/opponent" is every such player choosing in APNAP order (CR 101.4)
    before anything is sacrificed."""
    match = _PLAYER_SACRIFICES_ONE_OF_EACH_RE.fullmatch(clause.strip())
    if match is None:
        return None
    who = match.group("who").lower()
    if who.startswith("target") and not _targets_understood(who, allow_player_targets=True):
        return None
    slots = _one_of_each_slots(match.group("slots"))
    if slots is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        source_id = source_id_of(stack_object)
        if who.startswith("target"):
            players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        else:
            players = [
                player
                for player in _players_in_apnap_order(game)
                if who == "each player" or player.username != controller
            ]
        chosen: list[CardState] = []
        for player in players:
            chosen.extend(_one_of_each_choice(game, player, slots, source, source_id))
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return effect


#: "Target opponent sacrifices/exiles a creature or planeswalker with the
#: greatest mana value among creatures and planeswalkers they control." -
#: a *targeted* edict (the opponent, not the permanent, CR 115.10a still
#: applies: nothing about which permanent is chosen is targeted), narrowed to
#: whichever of the named types has the highest mana value on their board.
#: The real, off-set printings are Riveteers Charm's own mode one
#: ("sacrifices", CR 701.21a) and Blot Out/End of the Hunt's identical shape
#: with "exiles" (CR 701.10a) in its place - the same selection, a different
#: verb for what happens to the one chosen.
#:
#: The untargeted "each opponent"/"each player" subject is the same selection
#: run once per player (Flare of Malice, Soul Shatter: "Each opponent
#: sacrifices a creature or planeswalker with the greatest mana value among
#: creatures and planeswalkers they control."): CR 101.4 has every such player
#: choose in APNAP order and the sacrifices then happen simultaneously, the
#: greatest computed per player (CR 202.3).
_TARGET_OPPONENT_SACRIFICE_GREATEST_MV_RE = re.compile(
    r"^(?P<who>target opponent|each opponent|each player) (?P<verb>sacrifices|exiles) an? "
    r"(?P<kinds>[a-z]+(?:\s+or\s+[a-z]+)*)"
    r"(?: they control)? with the greatest mana value among "
    r"(?P<pool>[a-z]+(?:\s+(?:and|or)\s+[a-z]+)*) they control\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_target_opponent_sacrifice_greatest_mv_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_OPPONENT_SACRIFICE_GREATEST_MV_RE`'s shape; see the banner
    above. CR 701.21a/701.10a: "That player chooses which ... " - the
    resolving player is the *target* (or, untargeted, each player the subject
    names), not this ability's controller, so any real choice among a tie for
    the greatest mana value is theirs.
    """
    match = _TARGET_OPPONENT_SACRIFICE_GREATEST_MV_RE.fullmatch(clause.strip())
    if match is None:
        return None
    verb = match.group("verb").lower()
    who = match.group("who").lower()
    targeted = who == "target opponent"
    if targeted and not _targets_understood("target opponent", allow_player_targets=True):
        return None
    pool_words = re.split(r"\s+(?:and|or)\s+", match.group("pool"))
    pool_types = {_singular_card_type(word) for word in pool_words}
    if None in pool_types or not pool_types:
        return None
    opponents_only = who == "each opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if targeted:
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ][:1]
        else:
            controller = game.controller_of(stack_object).username
            players = [
                player
                for player in _players_in_apnap_order(game)
                if not (opponents_only and player.username == controller)
            ]
        board = game.computed_board()
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        chosen: list[CardState] = []
        for player in players:
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if pool_types & set(board.of(permanent).types)
            ]
            if not candidates:
                continue
            highest = max(permanent.mana_value for permanent in candidates)
            tied = [permanent for permanent in candidates if permanent.mana_value == highest]
            if len(tied) == 1:
                chosen.append(tied[0])
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"{verb[:-1]} a permanent with the greatest mana value",
                    source=source_name,
                    amount=1,
                    exact=True,
                    cards=tuple(permanent.id for permanent in tied),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in tied}
            pick = by_id.get(chosen_ids[0]) if chosen_ids else None
            if pick is not None:
                chosen.append(pick)
        for permanent in chosen:
            if permanent.zone is not Zone.BATTLEFIELD:
                continue
            if verb == "exiles":
                game.exile_permanent(permanent)
            else:
                game.sacrifice(permanent)

    return effect


#: "Each opponent sacrifices a creature with the greatest power among
#: creatures that player controls." / "Target opponent sacrifices a creature
#: with the greatest power among creatures they control." - the edict narrowed
#: to the sacrificing player's own highest-stat permanents (Gix's Command's
#: fourth mode, Professor Onyx's -3, Consumed by Greed). CR 701.21a: the
#: sacrifice is not targeted at the permanent (CR 115.10a), so hexproof or
#: protection on it stops nothing, and indestructible does not matter. The
#: greatest value is computed per player as the effect resolves (CR 608.2h),
#: and a tie for it is that player's own choice (CR 101.4 for several players,
#: APNAP order, every choice made before anything leaves).
_SACRIFICE_GREATEST_STAT_RE = re.compile(
    r"^(?P<who>each opponent|each player|target opponent|target player) sacrifices an? "
    r"(?P<kinds>[a-z]+(?:\s+or\s+[a-z]+)*) with the greatest (?P<stat>power|toughness) among "
    r"(?P<pool>[a-z]+(?:\s+(?:and|or)\s+[a-z]+)*) (?P<whose>that player controls|they control)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_sacrifice_greatest_stat_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SACRIFICE_GREATEST_STAT_RE`'s shape; see the banner above."""
    match = _SACRIFICE_GREATEST_STAT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    who = match.group("who").lower()
    targeted = who.startswith("target")
    if targeted and not _targets_understood(who, allow_player_targets=True):
        return None
    if targeted and match.group("whose").lower() != "they control":
        return None  # "that player" would name nobody the target does not already.
    kind_types = {_singular_card_type(word) for word in re.split(r"\s+or\s+", match.group("kinds"))}
    pool_types = {
        _singular_card_type(word) for word in re.split(r"\s+(?:and|or)\s+", match.group("pool"))
    }
    if None in kind_types or None in pool_types or not kind_types <= pool_types:
        return None
    stat = match.group("stat").lower()
    opponents_only = who == "each opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        if targeted:
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
        else:
            players = [
                player
                for player in _players_in_apnap_order(game)
                if not (opponents_only and player.username == controller)
            ]
        board = game.computed_board()
        chosen: list[CardState] = []
        for player in players:
            pool = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if pool_types & set(board.of(permanent).types)
            ]

            def value(permanent: CardState) -> int:
                number = (
                    game.power_of(permanent) if stat == "power" else game.toughness_of(permanent)
                )
                return number if number is not None else 0

            if not pool:
                continue
            greatest = max(value(permanent) for permanent in pool)
            tied = [
                permanent
                for permanent in pool
                if value(permanent) == greatest and kind_types & set(board.of(permanent).types)
            ]
            if len(tied) <= 1:
                chosen.extend(tied)
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"sacrifice a permanent with the greatest {stat}",
                    source=source_name,
                    amount=1,
                    exact=True,
                    cards=tuple(permanent.id for permanent in tied),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in tied}
            pick = by_id.get(chosen_ids[0]) if chosen_ids else None
            if pick is not None:
                chosen.append(pick)
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return effect


#: "Each player sacrifices `<a description>` of their choice. If you
#: sacrificed `<a description>` this way, `<consequence>`." - Garruk, Veiled
#: Butcher's own `-2`, and the real, off-set printing Rise of the
#: Witch-king's identical wording. CR 608.2c's own "if you did" family
#: (mirroring `_MAY_SACRIFICE_IF_YOU_DO_RE`'s shape) checked against *this*
#: ability's own controller specifically, not any player - "each player"
#: still has every player sacrifice, but only the controller's own choice
#: gates the consequence. The rider clause is anchored to an article or a
#: count ("a"/"an"/`COUNT`) ahead of "this way", the same anchor
#: `_MAY_SACRIFICE_IF_YOU_DO_RE`'s own family uses, rather than a bare
#: "sacrificed [^,]+ this way" - Oracle's own CR 608.2c riders never phrase
#: this without one, and the anchor keeps a stray comma-free clause earlier
#: in the same sentence from being swallowed into the rider by mistake.
_EACH_SACRIFICES_THEN_IF_YOU_DID_RE = re.compile(
    rf"^each (?P<who>opponent|player) sacrifices (?P<n>{COUNT}) (?P<description>.+?) "
    r"of their choice(?P<tail> with [^.]+?)?\.\s*"
    rf"if you sacrificed (?:a|an|{COUNT}) [^.]+? this way,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s17", for_spell=False)
@SPELL_TEXT.rung("s11", for_spell=True)
def _parse_each_sacrifices_then_if_you_did_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_EACH_SACRIFICES_THEN_IF_YOU_DID_RE`'s shape; see the banner above."""
    match = _EACH_SACRIFICES_THEN_IF_YOU_DID_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    description = match.group("description").strip()
    if match.group("tail") is not None:
        description = f"{description}{match.group('tail')}"
    requirement = permanent_description(description)
    if requirement is None or count is None or count < 1:
        return None
    opponents_only = match.group("who").lower() == "opponent"
    wanted_words = with_indefinite_article(description) if count == 1 else f"{count} {description}"
    consequence_text = match.group("consequence").strip()
    consequence_effect = (
        parse_mixed_effect(consequence_text)
        if not for_spell
        else parse_mixed_effect_for_spell(consequence_text)
    )
    if consequence_effect is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        controller_sacrificed = False
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller:
                continue
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if requirement.rejects(permanent, player.username, game) is None
            ]
            if not candidates:
                continue
            if len(candidates) <= count:
                chosen = candidates
            else:
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"sacrifice {wanted_words}",
                        source=source_name,
                        amount=count,
                        cards=tuple(permanent.id for permanent in candidates),
                        source_id=source_id_of(stack_object),
                    )
                )
                by_id = {permanent.id: permanent for permanent in candidates}
                chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
            for permanent in chosen:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.sacrifice(permanent)
                    if player.username == controller:
                        controller_sacrificed = True
        if controller_sacrificed:
            consequence_effect(game, stack_object)  # type: ignore[arg-type]

    return effect


#: "That player sacrifices `<n>` `<description>` of their choice." -
#: Sheoldred, Whispering One's own "At the beginning of each opponent's
#: upkeep, that player sacrifices a creature of their choice." "That player"
#: (CR 607.1 anaphora) is whichever specific opponent's upkeep just began -
#: `GameEvent.player` - not "each opponent" all at once
#: (`_EACH_SACRIFICES_OF_THEIR_CHOICE_RE`'s own shape, a genuinely different
#: sentence): the trigger already fires once per opponent, at the start of
#: *their* step, so only that one player ever chooses here.
_THAT_PLAYER_SACRIFICES_OF_THEIR_CHOICE_RE = re.compile(
    rf"^that player sacrifices (?P<n>{COUNT}) (?P<description>.+?) "
    r"of their choice(?P<tail> with [^.]+?)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_that_player_sacrifices_of_their_choice_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_THAT_PLAYER_SACRIFICES_OF_THEIR_CHOICE_RE`'s shape. Ability-only: a
    spell has no `ability.event` to read "that player" against."""
    if for_spell:
        return None
    match = _THAT_PLAYER_SACRIFICES_OF_THEIR_CHOICE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    description = match.group("description").strip()
    if match.group("tail") is not None:
        description = f"{description}{match.group('tail')}"
    requirement = permanent_description(description)
    if requirement is None or count is None or count < 1:
        return None
    wanted_words = with_indefinite_article(description) if count == 1 else f"{count} {description}"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.player is None:
            return
        username = event.player
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(username)
            if requirement.rejects(permanent, username, game) is None
        ]
        if not candidates:
            return
        if len(candidates) <= count:
            chosen = candidates
        else:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=username,
                    prompt=f"sacrifice {wanted_words}",
                    source=ability.source_name,
                    amount=count,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id_of(ability),
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return effect


# --------------------------------------------------------------------------
# Bringer of the Last Gift: a mass sacrifice and a mass reanimation, linked
# --------------------------------------------------------------------------
#
# "Each player sacrifices all other creatures they control. Then each player
# returns all creature cards from their graveyard that weren't put there this
# way to the battlefield."
#
# "That weren't put there this way" is what forces the two sentences to be
# read together: the second sentence's candidate set is defined by what the
# first sentence did, so each graveyard has to be snapshotted *before* the
# sacrifices and the returns taken from that snapshot. CR 608.2f's
# simultaneity is what makes the snapshot right rather than merely
# convenient.
#
# "All other creatures they control" excludes the source itself (CR 700.7),
# and only the source - every other creature its controller has goes too.

_EACH_PLAYER_SACRIFICES_THEN_MASS_REANIMATE_RE = re.compile(
    r"^each player sacrifices all other creatures they control\.\s*"
    r"then each player returns all creature cards from their graveyard "
    r"that weren'?t put there this way to the battlefield\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s32")
def _parse_each_player_sacrifices_then_mass_reanimate(text: str) -> AbilityEffect | None:
    """`_EACH_PLAYER_SACRIFICES_THEN_MASS_REANIMATE_RE`'s shape - Bringer of
    the Last Gift's own enters trigger, whose intervening *if* ("if you cast
    it", CR 608.2a: "If a triggered ability has an intervening 'if' clause,
    it checks whether the clause's condition is true. If it isn't, the ability
    is removed from the stack and does nothing") is `machines/triggers.py`'s
    business and has already been checked by the time this runs.

    Each returned card arrives under **its own graveyard's owner's** control,
    not the trigger controller's: the sentence's subject is "each player",
    and CR 110.2a's "unless the effect states otherwise" is exactly that
    statement.
    """
    if _EACH_PLAYER_SACRIFICES_THEN_MASS_REANIMATE_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        source_id = source.id if source is not None else None
        before: dict[str, list[CardState]] = {
            player.username: [
                state for state in list(player.graveyard) if Type.CREATURE in state.types
            ]
            for player in game.players_in_game
        }
        doomed: list[CardState] = []
        board = game.computed_board()
        for player in game.players_in_game:
            for permanent in game.permanents_controlled_by(player.username):
                if permanent.id == source_id:
                    continue
                if Type.CREATURE in board.of(permanent).types:
                    doomed.append(permanent)
        for permanent in doomed:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)
        for player in game.players_in_game:
            for state in before.get(player.username, []):
                if state.zone is Zone.GRAVEYARD:
                    game.put_onto_battlefield(state, player.username)

    return effect


def _cost_sacrificed_stat_total(game: "Game", ability: AbilityOnStack, attribute: str) -> int:
    """The summed power or toughness of every creature this activation's own
    cost sacrificed, as CR 608.2h's last known information. Read off the
    snapshot `Game.activate_ability` took as the cost was paid, so a pumped
    creature counts as pumped and a sacrificed token that has since ceased to
    exist (CR 704.5d) still counts. A `*` that never became a number counts 0.
    """
    snapshot = (
        ability.cost_sacrificed_powers
        if attribute == "power"
        else ability.cost_sacrificed_toughnesses
    )
    if not snapshot and ability.cost_sacrificed_card_ids:
        found = (game.find_by_id(card_id) for card_id in ability.cost_sacrificed_card_ids)
        snapshot = tuple(getattr(state, attribute) for state in found if state is not None)
    return sum(value for value in snapshot if value is not None)


#: "Exile target <filter> card [with mana value ...] from <your|a> graveyard.
#: Create a token that's a copy of <it|that card>[, except <exception>]." -
#: Nahiri, the Unforgiving's 0, Tamiyo, Compleated Sage's -X, Offspring's
#: Revenge. The second sentence's pronoun is the card the first just exiled
#: (CR 608.2c: later text refers back to earlier text), never the ability's source.
_EXILE_CARD_THEN_TOKEN_COPY_RE = re.compile(
    r"^exile (?P<phrase>target .+?) from (?P<zone>your graveyard|a graveyard)\.\s*"
    r"create a token that'?s a copy of (?:it|that card)"
    r"(?:, except (?P<except>.+?))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s12", for_spell=False)
@SPELL_TEXT.rung("s9", for_spell=True)
def _parse_exile_card_then_token_copy_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EXILE_CARD_THEN_TOKEN_COPY_RE`'s shape, or `None`.

    CR 707.2: the token copies the card's copiable values as it now is in
    exile; CR 707.9b's exception (Offspring's Revenge's "except it's 1/1") is
    `_read_token_copy_except`'s. CR 608.2b: a target that left the graveyard
    is illegal, the ability does nothing, and no copy is made - the copy is
    made only of a card this resolution actually exiled.
    """
    match = _EXILE_CARD_THEN_TOKEN_COPY_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    phrase = f"{match.group('phrase')} from {match.group('zone')}"
    if not _targets_understood(phrase, battlefield_only=False):
        return None
    not_legendary = False
    listed = _read_copy_exception_list(match.group("except"))
    if listed is not None:
        # The Cloning of Shredder's chapter I: "except it isn't legendary and
        # is a Mutant in addition to its other types" (CR 707.9b).
        added, power, toughness, added_type = (
            listed.added_abilities,
            listed.power,
            listed.toughness,
            listed.added_creature_type,
        )
        not_legendary = listed.not_legendary
    else:
        exception = _read_token_copy_except(match.group("except"))
        if exception is None:
            return None
        added, power, toughness, added_type = exception

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue
            token_copy_of(
                game,
                exiled,
                controller,
                added_abilities=added,
                power=power,
                toughness=toughness,
                added_creature_type=added_type,
                not_legendary=not_legendary,
            )

    return effect


#: Mimic Vat's imprint: "you may exile that card. If you do, return each
#: other card exiled with this artifact to its owner's graveyard." - "that
#: card" is the dying creature's card, now in the graveyard (CR 603.10a's
#: look-back leaves the trigger's event naming it); the exile is linked to
#: the source (CR 607.2a) and every *other* card of that pile goes back
#: (CR 118.12's "if you do").
_MAY_EXILE_THAT_CARD_RETURN_OTHERS_RE = re.compile(
    r"^you may exile (?:that card|it)\.\s*if you do, return each other card exiled with "
    r"(?:this [a-z]+|it) to its owner['’]?s graveyard\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s14")
def _parse_may_exile_that_card_return_others_clause(text: str) -> AbilityEffect | None:
    """`_MAY_EXILE_THAT_CARD_RETURN_OTHERS_RE`'s shape, or `None`."""
    if _MAY_EXILE_THAT_CARD_RETURN_OTHERS_RE.fullmatch(" ".join(text.strip().split())) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None or ability.source_id is None:
            return
        card = game.find_by_id(event.subject_id)
        if not isinstance(card, CardState) or card.zone is not Zone.GRAVEYARD:
            return
        controller = game.controller_of(ability)
        if not game.may(
            controller,
            f"exile {card.name}",
            source=ability.source_name,
            source_id=source_id_of(ability),
            cards=(card,),
        ):
            return
        exiled = game.exile_permanent(card)
        if exiled.zone is not Zone.EXILE:
            return
        exiled.exile_annotation = linked_exile_annotation(game, ability, exiled)
        for other in game.cards_exiled_with(ability.source_id, ability.source_stamp):
            if other.id != exiled.id:
                game.put_into_graveyard(other)

    return effect


#: "Put a <quality> card exiled with <this object> onto the battlefield under
#: your control[ with <n> <kind> counter(s) on it]." - Emperor of Bones,
#: Sisters of Stone Death, Yggdrasil, Rebirth Engine, Tomb of the Dusk Rose.
#: CR 607.2a: "exiled with this object" is the pile this object's own
#: exiling ability made, read by `Game.cards_exiled_with`.
_PUT_CARD_EXILED_WITH_SELF_RE = re.compile(
    rf"^put (?:a|an|one) (?P<quality>[a-z ]+?) card exiled with "
    r"(?:this [a-z]+|it|him|her) onto the battlefield under your control"
    rf"(?: with (?P<counter_n>{COUNT}) (?P<counter>[a-z0-9+/-]+) counters? on it)?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s13")
def _parse_put_card_exiled_with_self_clause(text: str) -> AbilityEffect | None:
    """`_PUT_CARD_EXILED_WITH_SELF_RE`'s shape, or `None`.

    No target (CR 115.1 - "a creature card", not "target"): the controller
    chooses among the matching cards in the source's own linked pile as the
    ability resolves (CR 608.2d). The pile is the source *as this object*
    (`AbilityOnStack.source_stamp`, CR 400.7). Counters are placed as it
    arrives, the way `_parse_return_cards_from_your_graveyard_clause`
    already places Scavenger's Talent's finality counter (CR 122.1h).
    """
    match = _PUT_CARD_EXILED_WITH_SELF_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    matches = _quality_matcher(match.group("quality"))
    counter_kind = match.group("counter")
    counter_amount = parse_count(match.group("counter_n")) if counter_kind else 0
    if counter_kind and not counter_amount:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if ability.source_id is None:
            return
        candidates = [
            card
            for card in game.cards_exiled_with(ability.source_id, ability.source_stamp)
            if matches(card)
        ]
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=ability.controller,
                prompt="choose a card exiled with this permanent to put onto the battlefield",
                source=ability.source_name,
                amount=1,
                cards=tuple(card.id for card in candidates),
                source_id=source_id_of(ability),
            )
        )
        by_id = {card.id: card for card in candidates}
        for card_id in chosen_ids:
            permanent = game.put_onto_battlefield(by_id[card_id], ability.controller)
            if counter_kind and permanent.zone is Zone.BATTLEFIELD:
                game.add_counters(permanent, counter_kind.lower(), counter_amount or 0)

    return effect


#: "If you cast a spell this way, pay life equal to its mana value rather
#: than pay[ing] its mana cost." - Inside Information's and Nashi, Moon Sage's
#: Scion's rider on the permission sentence before it: CR 118.9's
#: alternative cost, required by the permission (CR 118.9b), carried on
#: `PlayPermission.pays_life_for_mana_value`.
_PAY_LIFE_FOR_MANA_VALUE_RE = re.compile(
    r"^if you cast a spell this way, pay life equal to its mana value rather than "
    r"pay(?:ing)? its mana cost\.?$",
    re.IGNORECASE,
)

#: "exile the top `<n>` cards of target `<player>`'s library" (Inside
#: Information) and "exile the top card of each `<player>`'s library" (Nashi,
#: Moon Sage's Scion) - libraries other than the controller's own, which
#: `_EXILE_TOP_OF_YOUR_LIBRARY_RE` reads. The cards stay owned by their
#: owners (CR 108.3); a permission after them goes to the controller.
#: Widened (C02-T5) to the same exile said by the targeted player: Doom
#: Reigns Supreme's "target opponent exiles the top five cards of their
#: library" (CR 406.2 - who performs the exile does not change what is
#: exiled, or whose library it came from).
_EXILE_TOP_OF_OTHER_LIBRARIES_RE = re.compile(
    rf"^(?:exile the top (?:card|(?P<n>{COUNT}) cards) of "
    r"(?:(?P<target>target (?:opponent|player))|each (?P<each>opponent|player))'s library"
    rf"|(?P<target_exiles>target (?:opponent|player)) exiles the top (?:card|(?P<m>{COUNT}) cards)"
    r" of their library)$",
    re.IGNORECASE,
)


def _parse_exile_top_of_other_libraries_antecedent(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    """`_EXILE_TOP_OF_OTHER_LIBRARIES_RE`'s shape, as an antecedent for a
    trailing play permission. A targeted library is rechecked on resolution
    (CR 608.2b: an illegal target player is skipped); "each player" runs in
    turn order starting with the active player (CR 101.4's APNAP order). A
    library shorter than the count gives what it has."""
    match = _EXILE_TOP_OF_OTHER_LIBRARIES_RE.fullmatch(clause.strip())
    if match is None:
        return None
    count_word = match.group("n") or match.group("m")
    count = parse_count(count_word) if count_word else 1
    if count is None:
        return None
    targeted = match.group("target") is not None or match.group("target_exiles") is not None
    opponents_only = (match.group("each") or "").lower() == "opponent"

    def exile_tops(game: "Game", stack_object: "StackObject") -> list[CardState]:
        controller = game.controller_of(stack_object).username
        if targeted:
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
        else:
            players = [
                game.player(username)
                for username in game._turn_order_from_active()
                if not (opponents_only and username == controller)
            ]
        exiled: list[CardState] = []
        for player in players:
            for _ in range(count):
                if not player.library:
                    break
                exiled.append(game.exile_permanent(player.library[0]))
        return exiled

    return exile_tops, not targeted or count_word is not None


@MIXED_CLAUSE.rung("s2")
def _parse_exile_top_of_other_libraries_clause(clause: str) -> TargetedClause | None:
    """`_EXILE_TOP_OF_OTHER_LIBRARIES_RE` standing alone - Maralen, Fae
    Ascendant's "exile the top two cards of target opponent's library." and
    Ashiok, Nightmare Weaver's "+2: Exile the top three cards of target
    opponent's library." (CR 406.2). Whatever the cards are for is the
    object's other, linked ability's business (CR 607.2a,
    `link_cards_exiled_during`)."""
    antecedent = _parse_exile_top_of_other_libraries_antecedent(clause.strip().rstrip("."))
    if antecedent is None:
        return None
    exile_tops, _ = antecedent

    def effect(game: "Game", stack_object: "StackObject") -> None:
        exile_tops(game, stack_object)

    return effect


#: "Target player exiles the top X cards of their library, where X is the
#: total mana value of cards you own in exile." - Ashiok, Wicked
#: Manipulator's -7. X is CR 202.3's sum over the controller's own (CR 108.3
#: ownership, not control) cards in exile, read when the ability resolves.
_TARGET_PLAYER_EXILES_TOP_X_OWNED_EXILE_RE = re.compile(
    r"^target (?:opponent|player) exiles the top x cards of their library, "
    r"where x is the total mana value of cards you own in exile$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s2")
def _parse_target_player_exiles_top_x_owned_exile_clause(clause: str) -> TargetedClause | None:
    """`_TARGET_PLAYER_EXILES_TOP_X_OWNED_EXILE_RE`'s shape; a library shorter
    than X gives what it has."""
    if _TARGET_PLAYER_EXILES_TOP_X_OWNED_EXILE_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        amount = int(sum(state.mana_value for state in game.exile if state.owner == controller))
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            for _ in range(amount):
                if not target.library:
                    break
                game.exile_permanent(target.library[0])

    return effect


#: Exile the top `<n>` cards of a library face down, then a play permission
#: that lasts "for as long as they remain exiled" - Flameshape's "Look at the
#: top two cards of your library and exile them face down. For as long as
#: they remain exiled, you may play them if you control a Wizard." and
#: Expensive Taste's "Exile the top two cards of target opponent's library
#: face down. You may look at and play those cards for as long as they remain
#: exiled." Read whole: `split_effect_clauses` cuts both at the bare "and",
#: stranding "exile them face down" and "play those cards" with nothing to
#: point at (CR 608.2c).
_FACE_DOWN_EXILE_PLAY_RE = re.compile(
    rf"^(?:look at the top (?P<look_n>{COUNT}) cards of your library and exile them face down"
    rf"|exile the top (?P<n>{COUNT}) cards of (?P<whose>your|target opponent's|target player's)"
    r" library face down)\.\s*"
    r"(?:for as long as (?:they|those cards) remain exiled, you may (?P<look1>look at and )?"
    r"(?P<action1>play|cast) (?:them|those cards)(?: if (?P<condition>[^.]+))?"
    r"|you may (?P<look2>look at and )?(?P<action2>play|cast) (?:them|those cards) for as long "
    r"as they remain exiled)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s14")
def _parse_face_down_exile_play_clause(effect_text: str) -> TargetedClause | None:
    """`_FACE_DOWN_EXILE_PLAY_RE`'s shape.

    CR 406.3: the cards are exiled face down, and the effect's controller -
    told to look at them first, or allowed to look at them after - may keep
    looking (`Game.look`, recorded as the cards arrive in exile). CR 406.3a
    lets the exiling effect allow them to be played, and turns a card face
    up just before it is played. The permission (CR 601.3) goes to the
    controller, pays the card's own mana cost, has no end but the card
    leaving exile (CR 400.7), and carries "if `<condition>`" as a live
    condition (`PlayPermission.condition`) - gated at parse time by
    `condition_is_readable`, so an unread condition leaves the whole text
    unread rather than silently dropped.
    """

    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _FACE_DOWN_EXILE_PLAY_RE.fullmatch(whole)
    if match is None:
        return None
    condition = match.group("condition")
    if condition is not None and not _effect_condition_is_readable(condition):
        return None
    count = parse_count(match.group("look_n") or match.group("n"))
    if count is None:
        return None
    whose = (match.group("whose") or "your").lower()
    targeted = whose.startswith("target")
    action_word = (match.group("action1") or match.group("action2")).lower()
    action = PlayAction.PLAY if action_word == "play" else PlayAction.CAST

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        if targeted:
            owners = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
        else:
            owners = [game.player(controller)]
        for owner in owners:
            for card_state in list(owner.library[:count]):
                moved = game.exile_permanent(card_state)
                if moved is None or moved.zone is not Zone.EXILE:
                    continue
                moved.face_up = False
                game.look(moved, controller, source=source_name)
                game.grant_play_permission(
                    moved,
                    controller,
                    action=action,
                    pays_mana_cost=True,
                    source_name=source_name,
                    rule="CR 601.3",
                    zone=Zone.EXILE,
                    until_end_of_turn=False,
                    condition=condition,
                )

    return effect


#: "For each opponent, exile up to one target `<X>` that player controls[
#: until this `<type>` leaves the battlefield| and that player gains life
#: equal to its power]." - Celebrate the Mountain-king's and Haytham Kenway's
#: "until" form (CR 610.3) and Luminate Primordial's life rider. The
#: per-opponent target is `machines/targeting._FOR_EACH_OPPONENT_TARGET_RE`'s
#: (one "up to one" target per opponent, CR 115.6, distinct controllers).
_FOR_EACH_OPPONENT_EXILE_RE = re.compile(
    r"^for each opponent, exile up to one target (?P<desc>.+?) that player controls"
    r"(?:(?P<until> until this (?:permanent|enchantment|artifact|creature|planeswalker) leaves "
    r"the battlefield)|(?P<life> and that player gains life equal to its power))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_for_each_opponent_exile_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_FOR_EACH_OPPONENT_EXILE_RE`'s shape.

    The "until" form is ability-only, like `_parse_exile_until_leaves_
    battlefield_clause`: it watches its own source leave (CR 610.3), and CR
    610.3b moves nothing when the source already left after the ability
    triggered. Each exiled card returns under its owner's control (CR
    610.3c) through `_watch_for_departure_and_return_exiled_card`. The life
    rider's "that player" is the exiled permanent's controller as it left,
    and "its power" its last known power (CR 608.2h).
    """
    match = _FOR_EACH_OPPONENT_EXILE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    until = match.group("until") is not None
    if until and for_spell:
        return None
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    gains_life = match.group("life") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        source: CardState | None = None
        if until:
            assert isinstance(stack_object, AbilityOnStack)
            source = stack_object.source(game)
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return  # CR 610.3b: the source already left; nothing moves.
        for target in targets:
            former_controller = game.controller_of(target).username
            power = game.characteristics_of(target).power or 0
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move.
            if source is not None:
                _watch_for_departure_and_return_exiled_card(game, source, exiled, controller)
            if gains_life and power > 0:
                game.gain_life(game.player(former_controller), power)

    return effect


#: Everything Pizza's own multi-part sacrifice ability, read whole: "Target
#: player gains `<n>` life and draws a card. Each of your opponents discards
#: a card. This `<noun>` deals `<n>` damage to any target. Put `<n>` +1/+1
#: counters on up to one target creature." Four sentences, three separate CR
#: 115.1 targets (a player, "any target", and an optional creature) declared
#: together as the ability is put on the stack (CR 601.2c via CR 602.2b), and
#: read together here because a per-clause split has nowhere to keep straight
#: which resolved object answers which sentence.
_MULTI_PART_SACRIFICE_GAIN_DRAW_DISCARD_DAMAGE_COUNTERS_RE = re.compile(
    r"^target player gains (?P<life>" + COUNT + r") life and draws a card\.\s*"
    r"each of your opponents discards a card\.\s*"
    r"this (?P<noun>[a-z]+) deals (?P<damage>" + COUNT + r") damage to any target\.\s*"
    r"put (?P<counters>" + COUNT + r") \+1/\+1 counters on up to one target creature\.?$",
    re.IGNORECASE,
)


def _parse_multi_part_sacrifice_gain_draw_discard_damage_counters_clause(
    text: str,
) -> AbilityEffect | None:
    """`_MULTI_PART_SACRIFICE_GAIN_DRAW_DISCARD_DAMAGE_COUNTERS_RE`'s shape -
    Everything Pizza's own activated ability, which sacrifices its source as
    part of the cost (CR 602.2b/601.2h): by the time this resolves the
    artifact is already in its owner's graveyard, so "this artifact" is read
    through `AbilityOnStack.source_or_last_known` (CR 608.2h) exactly the way
    `_parse_reveal_until_land_damage_clause` already reads a sacrificed
    Goblin Charbelcher's own "this artifact deals damage".

    The three targets are read back off `Game.resolve_targets`, in the order
    CR 601.2c/602.2b declared them: a player (mandatory), then "any target"
    (mandatory, CR 115.4 lets it be a creature, player, planeswalker, or
    battle), then up to one target creature (CR 115.6's "up to one", so it
    may be absent). The first `Player` found is read as the mandatory
    "target player" slot - it is declared first, so it is the first one this
    reads - and removed from the pool before the remaining slots are read
    positionally; a target that became illegal between announcement and
    resolution (CR 608.2b) is already missing from `resolve_targets`, which
    the same positional reading trades away as the one part of CR 601.2c's
    declared order it cannot fully recover once that has happened.
    """
    match = _MULTI_PART_SACRIFICE_GAIN_DRAW_DISCARD_DAMAGE_COUNTERS_RE.fullmatch(
        " ".join(text.split())
    )
    if match is None:
        return None
    life = parse_count(match.group("life"))
    damage = parse_count(match.group("damage"))
    counters = parse_count(match.group("counters"))
    if life is None or damage is None or counters is None:
        return None
    # CR 601.2c: which requirement each target was announced for
    # (`TargetRef.slot`), by phrase - "any target" may itself be a player, so
    # the first player found is not necessarily the "target player".
    phrases = [r.phrase.lower() for r in profile_for_text(text).requirements]
    wanted = [
        phrases.index(p) if p in phrases else None
        for p in ("target player", "any target", "target creature")
    ]

    def by_slot(game: "Game", ability: AbilityOnStack) -> list[Any] | None:
        if None in wanted or any(ref.slot is None for ref in ability.targets):
            return None
        found: list[Any] = [None, None, None]
        for ref in ability.targets:
            if ref.slot in wanted:
                found[wanted.index(ref.slot)] = game.legal_target(ability, ref)
        return found

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        source_id = source_id_of(ability)
        slotted = by_slot(game, ability)
        remaining: list[Any] = list(game.resolve_targets(ability))
        player_target: Player | None = None
        if slotted is not None:
            player_target = slotted[0] if isinstance(slotted[0], Player) else None
            remaining = slotted[1:]
        else:
            for candidate in remaining:
                if isinstance(candidate, Player):
                    player_target = candidate
                    remaining.remove(candidate)
                    break
        if player_target is not None:
            game.gain_life(player_target, life)
            game.draw_cards(player_target.username, 1)
        for opponent in _opponents(game, ability.controller):
            _discard_cards(game, opponent, 1, ability.source_name, source_id=source_id)
        any_target = remaining[0] if remaining else None
        if any_target is not None:
            game.deal_damage(any_target, damage, source=source)
        creature_target = remaining[1] if len(remaining) > 1 else None
        if isinstance(creature_target, CardState):
            game.add_counters(creature_target, Counter.PLUS_ONE, counters)

    return effect


#: "Destroy all other creatures that were dealt damage this turn." (Death-Rattle
#: Oni) - CR 701.8a's destroy over the group fixed as the effect begins (CR
#: 611.2c), narrowed by the damage history (`Game.damage_dealt_this_turn`, CR
#: 120.1) read through the same `object_dealt_damage_clause_test` the damage
#: families' "each creature dealt damage this turn" uses. "Other" leaves out
#: the ability's own source.
_DESTROY_ALL_DEALT_DAMAGE_RE = re.compile(
    r"^destroy all (?P<other>other )?(?P<noun>creatures|permanents) that (?:were|was) "
    r"dealt damage this turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_destroy_all_dealt_damage_this_turn_text(text: str) -> AbilityEffect | None:
    """`_DESTROY_ALL_DEALT_DAMAGE_RE`'s shape."""
    if "dealt damage this turn" not in text:
        return None
    match = _DESTROY_ALL_DEALT_DAMAGE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from ..conditions.history import object_dealt_damage_clause_test

    dealt = object_dealt_damage_clause_test("was dealt damage this turn")
    if dealt is None:
        return None
    creatures_only = match.group("noun").lower() == "creatures"
    other = match.group("other") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        board = game.computed_board()
        group = [
            permanent
            for permanent in game.battlefield
            if not (other and permanent.id == ability.source_id)
            and (not creatures_only or board.of(permanent).is_creature)
            and dealt(game, permanent, None)
        ]
        for permanent in group:
            if permanent.zone is Zone.BATTLEFIELD:
                game.destroy(permanent)

    return effect


#: "Destroy that creature." / "destroy that planeswalker." as a whole trigger
#: effect - CR 603.2: the object the triggering event concerns (the creature
#: that blocked, the planeswalker that was dealt combat damage; see
#: `ep01_r3_amounts.event_referent_permanent`). Nothing to destroy once it has
#: left the battlefield (CR 608.2b).
_DESTROY_EVENT_REFERENT_RE = re.compile(
    r"^destroy that (?P<noun>creature|planeswalker|permanent|artifact|enchantment|land)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_destroy_event_referent_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_DESTROY_EVENT_REFERENT_RE`'s shape. Ability-only: a spell has no event."""
    if for_spell or not clause.startswith(("destroy that ", "Destroy that ")):
        return None
    if _DESTROY_EVENT_REFERENT_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        referent = event_referent_permanent(game, stack_object)
        if isinstance(referent, CardState) and referent.zone is Zone.BATTLEFIELD:
            game.destroy(referent)

    return effect


@ABILITY_TEXT.rung("s25")
def _parse_destroy_it_event_text(text: str) -> AbilityEffect | None:
    """ "destroy it": the object the trigger's event names
    (`ep02_r1_controller_recipients.destroy_event_subject_effect`)."""
    return destroy_event_subject_effect(text)


_DESTROY_IT_NO_REGENERATION_RE = re.compile(
    r"^destroy it\.\s*it can'?t be regenerated\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s25")
def _parse_destroy_it_cant_regenerate_event_text(text: str) -> AbilityEffect | None:
    """ "Destroy it. It can't be regenerated." (Death Pits of Rath): the
    object the trigger's event names, destroyed with CR 701.19c's prohibition
    on regeneration, only while it is still on the battlefield (CR 608.2b)."""
    if _DESTROY_IT_NO_REGENERATION_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        referent = event_referent_permanent(game, stack_object)
        if isinstance(referent, CardState) and referent.zone is Zone.BATTLEFIELD:
            game.destroy(referent, regeneration_allowed=False)

    return effect


#: "Sacrifice a permanent for each 1 life you lost." (Lich's Tomb) - the
#: trigger's own life-loss amount (CR 119.3, `GameEvent.amount`), one permanent
#: of the controller's choice per point (CR 701.21a).
_SACRIFICE_PER_LIFE_LOST_RE = re.compile(
    r"^sacrifice an? (?P<what>[a-z ]+?) for each 1 life you lost\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_sacrifice_per_life_lost_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SACRIFICE_PER_LIFE_LOST_RE`'s shape (ability-only: it reads the event)."""
    if for_spell or "for each 1 life you lost" not in clause:
        return None
    match = _SACRIFICE_PER_LIFE_LOST_RE.fullmatch(clause.strip())
    if match is None or permanent_description(match.group("what")) is None:
        return None
    what = match.group("what")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        lost = stack_object.event.amount if stack_object.event is not None else None
        if not lost or lost <= 0:
            return
        player = game.player(game.controller_of(stack_object).username)
        _sacrifice_of_choice_clause_effect(what, lost, f"{lost} {what}s")(
            game, player, stack_object.source_name, str(stack_object.source_id)
        )

    return effect


#: "Choose a creature at random that attacked this turn. Destroy that
#: creature." (Metzali, Tower of Triumph): one creature, picked uniformly at
#: random among the creatures declared as attackers this turn (CR 508.1a)
#: still on the battlefield, then destroyed (CR 701.8a). The pick is seeded
#: off the game's `shuffle_seed` and the resolving ability's own id - both
#: fixed per game - so a replay picks the same creature.
_DESTROY_RANDOM_ATTACKED_RE = re.compile(
    r"^choose an? (?P<kind>creature|permanent) at random that attacked this turn\.\s*"
    r"destroy (?:that creature|it)$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s10")
def _parse_destroy_random_attacked_creature_text(text: str) -> TargetedClause | None:
    """`_DESTROY_RANDOM_ATTACKED_RE`'s shape. No creature attacked this turn
    is nothing to choose (CR 609.3: do as much as possible)."""
    if "at random that attacked this turn" not in text.lower():
        return None
    if _DESTROY_RANDOM_ATTACKED_RE.fullmatch(" ".join(text.strip().rstrip(".").split())) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        attacked = {entry.object_id for entry in game.turn_history if entry.kind == "attacked"}
        candidates = [
            permanent
            for permanent in game.battlefield
            if permanent.id in attacked and game.characteristics_of(permanent).is_creature
        ]
        if not candidates:
            return
        rng = Random(f"{game.shuffle_seed}:at-random:{stack_object.id}")  # noqa: S311
        game.destroy(rng.choice(candidates))

    return effect


from ..d20_tables import roll_table_effect  # noqa: E402
from ..ep01_r3_amounts import event_referent_permanent  # noqa: E402
from ..ep02_r1_controller_recipients import destroy_event_subject_effect  # noqa: E402
from ..free_cast_price import with_board_priced_cost  # noqa: E402
from ._common import (  # noqa: E402
    _ANAPHORIC_SUBJECT_RE,
    _ANY_TYPE_MANA_STANDALONE_RE,
    _COUNTER_TARGET_SPELL_RE,
    _COUNTER_UNLESS_PAYS_RE,
    _DESTROY_TARGET_RE,
    _DRAW_N_CARDS_RE,
    _EXILE_TARGET_RE,
    _EXILE_TOP_OF_YOUR_LIBRARY_RE,
    _EXILE_UNTIL_QUALITY_RE,
    _EXILE_UNTIL_QUALITY_THIRD_PERSON_RE,
    _HAND_EXILE_COLOR_WORDS,
    _HAND_EXILE_RE,
    _MANA_SYMBOL_RE,
    _MAY_SACRIFICE_IF_YOU_DO_RE,
    _ONE_PERMANENT,
    _PLAY_PERMISSION_RE,
    _PLURAL_PERMISSION_SUBJECTS,
    _SEARCH_AND_PUT_RE,
    _SEARCH_DESCRIPTION_JOIN_RE,
    CastFromHandExileNotice,
    ConditionalClauseNotice,
    PermissionDuration,
    _card_description_is_readable,
    _effect_condition_is_readable,
    _opponents,
    _parse_delayed_timing_clause,
    _parse_mass_type_qualifier,
    _permanent_id_and_name,
    _permission_duration,
    _players_in_apnap_order,
    _quality_matcher,
    _targets_understood,
    computed_permanents,
    pay_consequence_effect,
)
from .amounts import (  # noqa: E402
    _bounded_quality_matcher,
    _parse_x_magnitude_body,
    _that_many_or_notice,
    amount_expression,
)
from .continuous import (  # noqa: E402
    _attached_object,
    _for_each_opponent_target_phrase,
    _with_unparsed_remainder,
    grant_suspend,
)
from .control_copy import _parse_copy_that_spell_clause, _read_copy_exception_list  # noqa: E402
from .counters import _counter_kind  # noqa: E402
from .damage import _lethal_amount_before_damage, _parse_damage_that_player_clause  # noqa: E402
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_targeted_clause,
    _spell_effect_or_notice,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
    parse_player_effect_for_spell,
)
from .draw_discard import _discard_at_random, _discard_cards  # noqa: E402
from .library import _dead_self_found  # noqa: E402
from .merges import _clauses_around_sentences, _offer_free_casts_from_among  # noqa: E402
from .modal import (  # noqa: E402
    _choose_an_opponent,
    _choose_permanents_to_sacrifice,
    _condition_holds_for_stack_object,
    _linked_pile,
)
from .returns import (  # noqa: E402
    _two_battlefield_targets_understood,
    _watch_for_departure_and_return_exiled_card,
)
from .search import (  # noqa: E402
    _search_and_exile_matching_name,
    _search_and_place_for,
    _search_library,
    _search_quality_is_readable,
    _search_up_to_and_exile_effect,
)
from .text import (  # noqa: E402
    _article,
    _bare_subtype_word,
    _is_referent_color_count_expression,
    _is_referent_power_expression,
    _parse_chosen_target_card_antecedent,
    _parse_referent_clause,
    _referent_color_count,
    _singular_card_type,
    _strip_non_effect_preamble,
)
from .tokens import (  # noqa: E402
    _parse_generic_token_descriptor,
    _read_token_copy_except,
    amass,
)
