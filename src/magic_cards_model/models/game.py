"""A single game: the players, the shared zones, and where the turn is."""

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from enum import StrEnum
from random import Random
from typing import Annotated, Any, ClassVar
from uuid import NAMESPACE_OID, UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..ids import install_id_allocator, reset_id_allocator
from ..machines import combat as combat_rules
from ..machines.abilities import (
    AbilityKind,
    ActivatedAbility,
    CostKind,
    CouldProduce,
    TriggeredAbility,
    TriggerEvent,
    granted_mana_abilities,
    parse_abilities,
    parse_mana_abilities,
)
from ..machines.casting import (
    AlternativeCostOption,
    AlternativeCostSource,
    Casting,
    KeywordCastOption,
    PlayAction,
    PlayPermission,
    _printed_alternative_total_cost,
    granted_cast_options,
    keyword_cast_options,
    marker_cast_options,
    play_permissions_on,
    spell_has_type_word,
    static_free_cast_grants,
    usable_play_permission,
    why_cannot_cast_restriction,
)
from ..machines.casting_restrictions import (
    CastingRuleEffect,
    CastingRuleKind,
    cannot_be_countered,
)
from ..machines.combat import (
    Attack,
    CombatMachine,
    EvasionNotice,
    Keyword,
    KeywordLineNotice,
    UndefinedPowerNotice,
    has_keyword,
)
from ..machines.cost import (
    ComponentKind,
    CostComponent,
    CostModifierKind,
    CostModifierNotice,
    CostPayment,
    TotalCost,
    alternative_cost_offers,
    among_colors,
    cost_component_for_phrase,
    cost_modifier_effect,
    discard_cost,
    exile_cost,
    increase,
    looks_like_unparsed_cost_modifier,
    loyalty_cost,
    pay_life_cost,
    sacrifice_cost,
    spend_restriction,
    tap_cost,
    total_cost_for_phrase,
    untap_cost,
)
from ..machines.decisions import (
    CardSplit,
    Decision,
    DecisionKind,
    DecisionPending,
    DecisionScript,
    PendingDecision,
    ask_attackers,
    ask_blockers,
    ask_mulligan,
    ask_trigger_order,
    default_answer,
    legal_options,
    rule_for_kind,
)
from ..machines.delayed import (
    DelayedEffectSpec,
    DelayedTrigger,
    DelayedTriggers,
    ExileWarped,
    rebound_recast,
    return_subject_to_hand,
)
from ..machines.effects import (
    AnaphoricClauseNotice,
    CastFromHandExileNotice,
    ConditionalClauseNotice,
    ControlReplacementNotice,
    DelayedClauseNotice,
    ImprintNotice,
    ModeNotice,
    ReflexiveClauseNotice,
    SuspendRedirectNotice,
    UnmodeledTriggerEffectNotice,
    activated_effect_for,
    devotion_to,
    effect_for,
    trigger_effect_for,
)
from ..machines.keywords import (
    ascend_state_based_actions,
    attachment_state_based_actions,
    aura_state_based_actions,
    equipment_state_based_actions,
    has_rebound,
    is_indestructible,
    keyword_effect_for,
    turn_face_up_cost,
    why_cannot_turn_face_up,
)
from ..machines.layers import (
    BASIC_LAND_TYPES,
    Characteristics,
    ComputedBoard,
    ContinuousEffect,
    ContinuousEffects,
    Duration,
    Layer,
    LayerContext,
    LayerNotice,
    additional_land_plays,
    count_card_types,
    grant_ability,
    only_this_incarnation,
    spend_effect_effects,
)
from ..machines.modes import modal_profile, substitute_x
from ..machines.objects_as_costs import convoke as pay_convoke
from ..machines.objects_as_costs import delve as pay_delve
from ..machines.objects_as_costs import improvise as pay_improvise
from ..machines.opening_hand import (
    RIDERS,
    OpeningHandAction,
    OpeningHandActionKind,
    OpeningHandNotice,
    read_opening_hand_actions,
)
from ..machines.priority import PriorityMachine, PriorityOutcome
from ..machines.replacement import (
    DrawRedirection,
    EventKind,
    ReplaceableEvent,
    UnreadableCopyExceptionNotice,
    UnwiredChoiceNotice,
    apply_replacements,
    draw_redirection_for,
)
from ..machines.targeting import (
    TargetingProfile,
    profile_for_modes,
    profile_for_modes_with_owners,
    profile_for_text,
    targeting_profile,
)
from ..machines.triggers import (
    AbilityOnStack,
    CastConditionNotice,
    ExtraTriggerEvent,
    GameEvent,
    InterveningIfNotice,
    TargetingNotice,
    TargetingNoticeKind,
    activated_abilities_from_lines,
    activated_abilities_of,
    added_ability_lines,
    apnap_order,
    granted_activated_abilities_of,
    intervening_if_holds,
    mana_added_event,
    rewritten_ability_lines,
    state_triggers_for,
    tapped_for_mana_event,
    triggers_for,
)
from ..machines.turn import (
    MAIN_PHASES,
    STEP_SEQUENCE,
    Step,
    TurnMachine,
)
from ..serialization import SortedFrozenSet, SortedSet
from .action import Action
from .card import Card, Color, Layout, Supertype, Type
from .card_state import (
    CardState,
    ChoiceKind,
    Counter,
    ExileAnnotation,
    ExileMarker,
    TargetRef,
    planeswalkers_with_zero_loyalty,
)
from .mana import ManaCost, ManaPool, ManaSpend, ManaSpendEffect
from .player import Player
from .token import TokenState, move_refused, tokens_that_cease_to_exist
from .zone import Zone

#: Anything a spell can point at and then affect (CR 115.1).
Targetable = CardState | Player

#: What the stack holds. A spell is the card itself (CR 112.1); an ability is a
#: separate object with no card behind it (CR 405.1, 113.1c).
#:
#: A discriminated union on `state_class` (`CardState.state_class`,
#: `TokenState.state_class`, `AbilityOnStack.state_class`), not a plain
#: `CardState | AbilityOnStack`. `TokenState` needs its own explicit arm even
#: though it is a `CardState` subclass: pydantic builds `shared_zones`'s
#: schema from the field's declared type, an untagged union tries each arm's
#: *exact* schema against a `TokenState` instance, matches neither `CardState`
#: nor `AbilityOnStack`, and warns - `PydanticSerializationUnexpectedValue`,
#: once per arm per object, every time a dump reaches this field. Naming
#: `TokenState` as its own tagged arm gives pydantic an exact match to pick
#: instead of guessing. `CardState._resolve_token_subclass`'s wrap validator/
#: serializer pair (`models/card_state.py`) stays in place for the one field
#: that still needs it: `Player.zones` (`models/player.py`) is a bare
#: `list[CardState]`, not this union, and narrowing that pair to only this
#: union's shape would break `Player.zones`'s own `TokenState` round trip
#: silently.
StackObject = Annotated[CardState | TokenState | AbilityOnStack, Field(discriminator="state_class")]

#: CR 702.16a: "Protection is a static ability, written 'Protection from
#: [quality]'." CR 702.16g makes "protection from A and from B" two abilities,
#: so the qualities are split apart rather than kept as one phrase.
_PROTECTION = re.compile(r"protection from ([^.;\n]+)", re.IGNORECASE)

#: The *unresolved* half of a protection phrase: a grant that names the quality
#: by a choice still to be made rather than by the quality itself. Mother of
#: Runes prints "gains protection from the color of your choice until end of
#: turn", and reading that sentence off her own printing yields the quality
#: "the color of your choice until end of turn", which names no colour and no
#: card type.
#:
#: CR 702.16a: "This quality is usually a color ... but can be any
#: characteristic value or information" - a choice not yet made is neither, so
#: the phrase is dropped here rather than carried as a quality nothing can ever
#: match. What Mother actually grants is written onto the *target* by
#: `machines/layers.py` as a resolved "Protection from red" line, and that line
#: is what `Game._effective_protection_qualities` reads.
_UNRESOLVED_PROTECTION_QUALITY = re.compile(
    r"^(?:a |the )?(?:color|colour|card type|quality) of your choice\b", re.IGNORECASE
)

#: "You have protection from the chosen card name" - Runed Halo's second line,
#: and the only shape in the pool that grants protection to a *player*. The
#: quality is the CR 614.12a name chosen as the permanent entered, which
#: `machines/replacement.py` stores on `CardState.choice`.
_PLAYER_PROTECTION_FROM_CHOSEN_NAME = re.compile(
    r"^you have protection from the chosen card name\b", re.IGNORECASE
)

#: A cost sentence that names the permanent its ability is printed on -
#: "Exert this land", "Sacrifice this creature". CR 602.1a: an activated
#: ability's source is the object it is printed on, so "this" is that object and
#: only the caller building the cost knows which it is.
_SELF_REFERENCE = re.compile(r"\bthis\b", re.IGNORECASE)


def _cost_refers_to_self(text: str, permanent: CardState) -> bool:
    """Whether a printed cost sentence names *this* permanent (CR 602.1a).

    Most printings use the generic "this <type>" `_SELF_REFERENCE` already
    reads, but some (The Filigree Sylex's "{T}, Sacrifice The Filigree
    Sylex: ...", Grist, the Hunger Tide's short "Grist" before the comma)
    name the permanent's own printed name instead - CR 201.5: "Text that
    refers to the object it's on by name means just that particular object."
    Checked as a whole word, not a bare substring, so a shorter card's name
    that happens to be a prefix of another word in the cost sentence is never
    mistaken for a reference.

    `_exiles_itself_by_name` below is the same CR 201.5 self-reference,
    narrowed to the one shape `cost_component_for_phrase`'s `_PHRASE_EXILE`
    needs it exactly-matched for (The Stone Brain's "Exile The Stone Brain",
    Abstergo Entertainment's "Exile Abstergo Entertainment") - this function
    stays the general "does this cost sentence refer to `permanent` at all"
    question the `SACRIFICE`/`DISCARD` and generic `OTHER` self-reference
    fill-ins below ask.
    """
    if _SELF_REFERENCE.search(text):
        return True
    front = permanent.card.name.split("//")[0].strip()
    names = {front}
    if "," in front:
        names.add(front.split(",", 1)[0].strip())
    return any(name and re.search(rf"\b{re.escape(name)}\b", text) for name in names)


def _exiles_itself_by_name(text: str, permanent: "CardState") -> bool:
    """Whether `text` is "Exile `<permanent's own printed name>`" - CR 201.5's
    other self-reference form: "If an object's text uses the object's own
    name, it's referring to that object, even if there are other objects with
    the same name." The Stone Brain's own "Exile The Stone Brain" (and
    Abstergo Entertainment's "Exile Abstergo Entertainment") is the pool's
    only example of this on a cost line; `_SELF_REFERENCE` only ever catches
    the "this `<type>`" spelling (CR 700.7), not a bare printed name.

    An exact match (case-insensitive) on "exile `<name>`" alone, not a
    substring search - a cost line naming some *other* object by name (a
    hypothetical "Exile a card named `<X>`") is a different shape entirely and
    must not be waved through as if it referred to `permanent`.
    """
    return text.strip().rstrip(".").lower() == f"exile {permanent.name.lower()}"


#: CR 601.2f cost reduction of the shape Emrakul, the Promised End prints.
#: Narrow on purpose: the amount, and the thing being counted, are both read
#: back out and anything else is left alone rather than guessed at.
_COSTS_LESS_PER_CARD_TYPE = re.compile(
    r"costs \{(\d+)\} less to cast for each card type among cards in your graveyard",
    re.IGNORECASE,
)

#: CR 601.2f's *other* self-referential reduction shape: "This spell costs
#: `<N>` less to cast if it targets a `<color>` spell." (Mystical Dispute).
#: Unlike Emrakul's row above, the condition is not a fact about the board -
#: it is about *this spell's own announced target* (CR 601.2c), which is
#: chosen before the cost is determined (CR 601.2f is a later step), so this
#: is read against `Casting.targets` rather than the battlefield. Narrow on
#: purpose, the same way as the row above: the amount and the one condition
#: shape actually printed are read back out and nothing else is guessed at -
#: a hypothetical "... if it targets a creature you control" is a different
#: shape this regex does not match, and would leave the reduction at {0}
#: rather than a wrong guess.
_COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE = re.compile(
    r"costs \{(\d+)\} less to cast if it targets a "
    r"(?P<color>white|blue|black|red|green) spell",
    re.IGNORECASE,
)

#: CR 601.2f's per-turn-history reduction: "This spell costs {2} less to cast
#: for each card you've cycled or discarded this turn." (Hollow One, text
#: confirmed with `resolve_cards` this session). Unlike Emrakul's row above,
#: what is counted is not a zone but a *history* - CR 701.9a's discards, and
#: CR 702.29a's cycling, which discards the card to pay an activation cost and
#: so is one and the same event (CR 702.29d says the pair "cycles or discards"
#: fires "only once when a card is cycled"). `Game.cards_discarded_this_turn`
#: is the counter; nothing else in the engine remembers this.
_COSTS_LESS_PER_CARD_DISCARDED_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each card you'?ve cycled or discarded this turn",
    re.IGNORECASE,
)

#: The *domain* shape: "This spell costs {N} less to cast for each basic land
#: type among lands you control." (Scion of Draco at {2}, Leyline Binding at
#: {1} - both confirmed with `resolve_cards` this session). "Domain" is an
#: ability word and has no rule of its own beyond CR 207.2c ("Ability words
#: ... have no special rules meaning"), so the em-dashed word is deliberately
#: outside the match and only the sentence it labels is read. CR 305.6 fixes
#: the five types being counted: "The basic land types are Plains, Island,
#: Swamp, Mountain, and Forest."
_COSTS_LESS_PER_BASIC_LAND_TYPE_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each basic land type among lands you control",
    re.IGNORECASE,
)

#: Obsidian Charmaw's own board-count shape (text confirmed with
#: `resolve_cards` this session): "This spell costs {1} less to cast for each
#: land your opponents control that could produce {C}." "Could produce" is
#: CR 106.7: "The type of mana a permanent could produce at any time includes
#: any type of mana that an ability of that permanent would produce if the
#: ability were to resolve at that time" - so this is asked of the land's mana
#: abilities, not of any mana actually made.
_COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE = re.compile(
    r"costs \{(\d+)\} less to cast for each land your opponents control "
    r"that could produce \{C\}",
    re.IGNORECASE,
)

#: CR 702.41a's affinity, read off the keyword line rather than off its
#: reminder text (which is CR 207.2 italics with no game function): "Affinity
#: is a static ability that functions while the spell with affinity is on the
#: stack. 'Affinity for [text]' means 'This spell costs {1} less to cast for
#: each [text] you control.'" The amount is always {1} - it is fixed by the
#: rule, not printed - so unlike every other row here there is no group to
#: read it out of.
_AFFINITY_RE = re.compile(r"\baffinity for (?P<what>[A-Za-z]+)", re.IGNORECASE)

#: What "[text]" in CR 702.41a's "Affinity for [text]" can name, mapped to the
#: thing to count on the battlefield. Card types (CR 205.2a) on the left of the
#: split, basic land types (CR 305.6) on the right; anything else is left
#: unread rather than guessed at, so an affinity variant this does not know
#: reduces nothing instead of reducing wrongly.
_AFFINITY_CARD_TYPES: dict[str, Type] = {
    "artifacts": Type.ARTIFACT,
    "creatures": Type.CREATURE,
    "enchantments": Type.ENCHANTMENT,
    "lands": Type.LAND,
}
_AFFINITY_SUBTYPES: dict[str, str] = {
    "plains": "Plains",
    "islands": "Island",
    "swamps": "Swamp",
    "mountains": "Mountain",
    "forests": "Forest",
}

#: Gran-Gran's conditional discount, the one shape in the pool that is neither
#: a flat static decrease (the Medallion cycle, which `cost_modifier_effect`
#: already reads) nor a per-count self-discount: "Noncreature spells you cast
#: cost {1} less to cast as long as there are three or more Lesson cards in
#: your graveyard." (text confirmed with `resolve_cards` this session). It is
#: another permanent's static ability, so it is read in
#: `static_cost_modifiers_for` rather than in `cost_reduction_for`, and it is
#: all-or-nothing: the graveyard count is a gate, not a multiplier.
_COSTS_LESS_WHILE_GRAVEYARD_COUNT_RE = re.compile(
    r"(?P<excludes>non)?(?P<type>creature|artifact|enchantment|instant|sorcery|land) "
    r"spells you cast cost \{(?P<amount>\d+)\} less to cast as long as there are "
    r"(?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d+) or more "
    r"(?P<subtype>[A-Za-z' -]+?) cards in your graveyard",
    re.IGNORECASE,
)

#: The number words `_COSTS_LESS_WHILE_GRAVEYARD_COUNT_RE` accepts, since a
#: card prints "three or more", never "3 or more".
_NUMBER_WORDS: dict[str, int] = {
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

#: Ral, Monsoon Mage's own back-face intrinsic (CR 306.5b's own "additional"
#: shape, layered on top of the printed loyalty number rather than replacing
#: it): "enters with an additional loyalty counter on him/her/it/them for
#: each instant and sorcery spell you've cast this turn." Generalized on the
#: pronoun; the spell-type qualifier is read narrowly (this is the one
#: printing in the pool) but by the words "instant"/"sorcery" rather than by
#: card name, so a future card naming a different type pairing the same way
#: is not silently mismatched onto this one's amount.
_ADDITIONAL_LOYALTY_PER_INSTANT_SORCERY_RE = re.compile(
    r"enters with an additional loyalty counter on (?:it|him|her|them) for each "
    r"instant and sorcery spell you'?ve cast this turn",
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
            if not quality or _UNRESOLVED_PROTECTION_QUALITY.match(quality):
                continue
            if quality not in qualities:
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
#: Diamond City: "Activate only if two or more creatures entered the
#: battlefield under your control this turn." Number words, matching the
#: printed wording rather than digits, the same convention `_ACTIVATE_ONLY_IF_
#: CONTROL` follows.
_ACTIVATE_ONLY_IF_ENTERED_THIS_TURN = re.compile(
    r"activate only if (?P<count>\w+) or more creatures entered the battlefield "
    r"under your control this turn",
    re.IGNORECASE,
)
#: Shifting Woodland's own *Delirium* activation gate: "Activate only if
#: there are four or more card types among cards in your graveyard."
#: CR 207.2c: *Delirium* is an ability word with no rules meaning of its
#: own - the whole restriction is this one sentence, the activated-ability
#: cousin of Unholy Heat's/Violent Urge's *delirium* clauses (which gate a
#: resolution effect and a static ability instead of an activation).
_ACTIVATE_ONLY_IF_DELIRIUM = re.compile(
    r"activate only if there (?:is|are) (?P<count>\w+) or more card types "
    r"among cards in your graveyard",
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


def _is_minus_symbol(printed: str) -> bool:
    """Whether a printed loyalty symbol is a negative one (CR 107.7).

    "Negative loyalty symbols point downward and feature a minus sign followed
    by a number or an X." Both the typographic minus WOTC prints (U+2212) and a
    plain hyphen are accepted, since the oracle text this is read from uses the
    former and hand-written text tends to use the latter.
    """
    return printed.strip().startswith(("−", "-"))


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


#: A static ability that stops other permanents' activated abilities from being
#: activated at all - Karn, the Great Creator's "Activated abilities of artifacts
#: your opponents control can't be activated."
#:
#: CR 611.1: "A continuous effect modifies characteristics of objects, modifies
#: control of objects, or affects players or **the rules of the game**, for a
#: fixed or indefinite period." This shape is the last of those three: it changes
#: no characteristic, so `machines/layers.py` has nothing to write - CR 613's
#: layers are for characteristics, control, and copiable values - and the effect
#: is felt where the rules ask whether an activation is legal, which is CR 602.5:
#: "A player can't begin to activate an ability that's prohibited from being
#: activated." CR 604.2 and CR 611.3b bound it to while its source is on the
#: battlefield, which is why `_activation_prohibition` reads the battlefield
#: fresh every time rather than caching anything (CR 611.3a: not "locked in").
#:
#: The optional "unless they're mana abilities" tail is Pithing Needle's and
#: Disruptor Flute's wording; those two name the ability's *source by chosen
#: name* rather than by quality, so they do not match this shape and keep the
#: `UnwiredChoiceNotice` they already get (`machines/replacement.py`).
_ACTIVATION_PROHIBITION_RE = re.compile(
    r"^activated abilities of (?P<subjects>[a-z, ]+?)"
    r"(?P<opponents> your opponents control)?"
    r" can't be activated(?P<mana_exempt> unless they're mana abilities)?\.?$",
    re.IGNORECASE,
)

#: A sentence that prohibits activation but is not the shape above - matched
#: only to fail closed with a notice rather than let it read as permission.
_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE = re.compile(
    r"^activated abilities of .+ can't be activated", re.IGNORECASE
)

#: A static ability that stops players gaining life at all - Leyline of
#: Punishment's "Players can't gain life.", Sulfuric Vortex's and Rampaging
#: Ferocidon's "Players can't gain life." on the same one-sentence shape.
#:
#: This is the same *kind* of continuous effect as `_ACTIVATION_PROHIBITION_RE`
#: above and is here for the same reason: it changes no characteristic of any
#: object, so `machines/layers.py` has nothing to write - CR 613's layers are
#: for characteristics, control, and copiable values. CR 611.1 puts it in the
#: last of its three categories, "affects players or the rules of the game",
#: and CR 119.7 is where the rules read it back ("If an effect says that a
#: player can't gain life ..."). CR 604.2 and CR 611.3 bound it to while its
#: source is on the battlefield, which is why `life_gain_prohibited` rescans
#: the battlefield on every call rather than caching (CR 611.3a: not "locked
#: in").
#:
#: "Players" and "Each player" are both printed; a prohibition naming one
#: player specifically ("You can't gain life") is a different shape and is
#: deliberately not matched here - see `_LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE`.
_LIFE_GAIN_PROHIBITION_RE = re.compile(
    r"^(?:players|each player) can't gain life\.?$", re.IGNORECASE
)

#: A sentence that prohibits life gain but is not the symmetric shape above -
#: matched only to fail closed with a notice rather than let it read as
#: permission, exactly as `_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE` does.
_LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE = re.compile(r"\bcan't gain life\b", re.IGNORECASE)

#: "You may activate abilities of creatures you control as though those
#: creatures had haste." - Tyvar, Jubilant Brawler's and Shang-Chi, Master of
#: Kung Fu's shared static, the two printings carrying this sentence in the
#: pool. Read as a shape, not by name.
#:
#: CR 609.4: "Some effects state that a player may do something 'as though'
#: some condition were true or a creature can do something 'as though' some
#: condition were true. This applies only to the stated effect. For purposes
#: of that effect, treat the game exactly as if the stated condition were
#: true. For all other purposes, treat the game normally." The stated effect
#: here is *activating abilities*, so exactly one of haste's two clauses is
#: borrowed - CR 702.10c, "its controller can activate its activated abilities
#: whose cost includes the tap symbol or the untap symbol even if that creature
#: hasn't been controlled by that player continuously since their most recent
#: turn began" - and CR 702.10b's attacking clause is not. The creature does
#: not gain the haste keyword either, so `machines/combat.py`'s `has_keyword`
#: reads nothing new off the computed board and `can_attack` still refuses.
#:
#: Like `_ACTIVATION_PROHIBITION_RE` this is a continuous effect that affects
#: the rules of the game rather than any object's characteristics (CR 611.1),
#: so `machines/layers.py` has nothing to write for it (CR 613.11) and the
#: battlefield is rescanned on every call instead of the answer being cached
#: (CR 611.3a: not "locked in").
#:
#: "Creatures you control" is the whole subject vocabulary read here, with
#: CR 613's usual "other" exclusion allowed for. A qualified subject - a
#: subtype, a colour, a count gate - is a subject reader this file does not
#: have (`machines/layers.py` owns that one, for anthems, and its selectors
#: are written against a computed `Board` rather than a single permanent), so
#: such a sentence fails closed through
#: `_LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE` below with a `LayerNotice`
#: rather than being granted to every creature its controller has.
_HASTE_ACTIVATION_PERMISSION_RE = re.compile(
    r"^you may activate abilities of (?P<other>other )?creatures you control "
    r"as though (?:those creatures|they) had haste\.?$",
    re.IGNORECASE,
)

#: A sentence that grants activation "as though ... haste" but is not the shape
#: above - matched only to fail closed with a notice rather than let it read as
#: silence, the mirror of `_LOOKS_LIKE_ACTIVATION_PROHIBITION_RE`. A permission
#: this engine cannot read costs a legal activation rather than allowing an
#: illegal one, which is why it is recorded instead of guessed at.
_LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE = re.compile(
    r"^you may activate\b.*\bas though\b.*\bhaste\b", re.IGNORECASE
)

#: Pithing Needle's and Disruptor Flute's "sources with the chosen name", which
#: name their subjects by a CR 614.12a choice rather than by a quality. Left
#: alone here on purpose: `machines/replacement.py` already records an
#: `UnwiredChoiceNotice` for exactly those two lines, and a second record on a
#: second list would be the same gap counted twice.
_CHOSEN_NAME_SUBJECT_RE = re.compile(r"\bthe chosen\b", re.IGNORECASE)


class ActivationProhibition(BaseModel):
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


def _parse_activation_prohibition(text: str) -> ActivationProhibition | None:
    """Read one static ability sentence as an activation prohibition, or None.

    The subject list is a plain "A, B, and C" of card-type plurals; anything
    else - a chosen name, a quality that is not a card type - comes back None
    and is recorded rather than guessed at.
    """
    match = _ACTIVATION_PROHIBITION_RE.match(text.strip())
    if match is None:
        return None
    subjects = match.group("subjects").lower().replace(" and ", ", ")
    words = [word.strip() for word in subjects.split(",") if word.strip()]
    if not words:
        return None
    if words == ["permanents"]:
        qualities: tuple[Type, ...] = ()
    else:
        types = [_card_type_named(word) for word in words]
        if any(card_type is None for card_type in types):
            return None
        qualities = tuple(card_type for card_type in types if card_type is not None)
    return ActivationProhibition(
        qualities=qualities,
        opponents_only=match.group("opponents") is not None,
        mana_abilities_exempt=match.group("mana_exempt") is not None,
    )


class Reveal(BaseModel):
    """One card shown to all players (CR 701.20a).

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
    origin_zone: Zone = Zone.HAND
    """Where the spell was cast **from** (CR 601.2a), copied from `Casting.
    origin_zone` as the spell goes on the stack. CR 702.88a's rebound applies
    "if this spell was cast from your hand" - a card cast from the graveyard
    (Flashback), from exile (Rebound's own recast), or anywhere else never
    triggers it a second time, which is exactly what would build an infinite
    exile-and-recast loop if this were read off anything but the announcement
    itself."""
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
    kicked: int = 0
    """How many times a kicker cost was paid (CR 702.33d), copied from
    `Casting.kicked`."""
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


class ObjectCostOffer(BaseModel):
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
            # CR 400.1's optional eighth zone, shared like the rest of these.
            # Empty in every game that is not being played for ante (CR 407.2).
            Zone.ANTE: [],
        }
    )
    priority: PriorityMachine | None = None
    combat: CombatMachine = Field(default_factory=CombatMachine)
    lands_played: dict[str, int] = Field(default_factory=dict)
    casting_rule_effects: list[CastingRuleEffect] = Field(default_factory=list)
    """CR 611.1's third kind of continuous effect - one that "affects players
    or the rules of the game" rather than any object's characteristics, so
    the layer system (CR 613) has nothing to compute for it. Ranger-Captain of
    Eos's "Your opponents can't cast noncreature spells this turn" is
    recorded here when its sacrifice-cost ability resolves, and Teferi, Time
    Raveler's "+1: Until your next turn, you may cast sorcery spells as
    though they had flash" is recorded here too - both outlive the instant
    they were created, unlike Teferi's *other* half (his static restricting
    opponents to sorcery-speed timing), which is read straight off the
    battlefield by `machines.casting_restrictions.sorcery_speed_restriction_
    source` and needs no record at all. `cleanup_step` drops the
    "until end of turn" entries and `begin_turn_for` drops the "until your
    next turn" ones, exactly as `play_permissions` already does for its own
    two durations."""
    play_permissions: list[PlayPermission] = Field(default_factory=list)
    """CR 601.3's dynamic half: permissions a resolving effect handed out to
    specific cards - Ugin, Eye of the Storms' −11, Ragavan, Nimble Pilferer's
    combat-damage trigger. Granted through `grant_play_permission`, read
    through `machines/casting.usable_play_permission`, and dropped in the
    cleanup step (CR 514.2). Deliberately a list of per-object records rather
    than a flag on the cards: see `PlayPermission`'s own docstring."""
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

    Not the whole of CR 104.4. **CR 104.4b's mandatory-action loop is detected
    in exactly one shape and no other**: a chain of CR 605.1b triggered mana
    abilities resolving inline off a single activation, bounded by
    `resolve_triggered_mana_abilities`. That is DDR#990's Caged Sun under Toph,
    the First Metalbender, where CR 605.4a keeps every link off the stack so no
    player ever receives priority to break it. This is *not* general loop
    detection: a loop built out of anything that does reach the stack, or out of
    replacement effects, or out of two permanents triggering each other, is
    still undetected and will hang or recurse rather than draw.

    CR 104.4c's "an effect may state that the
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

    creatures_cant_attack_until_turns_taken: int | None = None
    """CR 508.1c: "restrictions (effects that say a creature can't attack...)"
    - Orim's Chant's kicked "creatures can't attack this turn" is a blanket
    one, over every creature any player controls, not read off any single
    permanent's own static text the way `combat.has_keyword`'s `Keyword.
    DEFENDER` check is. Recorded as the `TurnMachine.turns_taken` value the
    turn it was granted on, the same "this turn" comparison `PlayPermission.
    expired` already makes for its own `granted_turns_taken` - simpler than a
    `casting_rule_effects`-style list, since nothing in the pool prints this
    restriction more than once at a time or needs to say who granted it.
    `combat.attack_refusal` reads it directly; nothing needs to clear it
    early, since the comparison itself goes stale the moment the turn ends."""

    players_skipping_next_untap: dict[str, int] = Field(default_factory=dict)
    """How many of a username's upcoming untap steps are replaced with
    nothing (CR 614.10: "skip [something]" is a replacement effect). Brine
    Elemental's "each opponent skips their next untap step" is the only card
    in the pool that grants this; `untap_step` decrements one entry per
    skipped step and drops the key once it reaches zero. A count rather than
    a flag on purpose, so two stacked grants (two Brine Elementals turned
    face up against the same opponent) cost that opponent two untap steps,
    matching CR 614.10a's "waits for the first occurrence that isn't
    skipped" read once per grant.
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

    cast_condition_notices: list[CastConditionNotice] = Field(default_factory=list)
    """One entry per "Whenever you cast a ... spell" condition (CR 601.2,
    603.2) that named a mana-value restriction `condition_matches` recognised
    but could not parse into a number and a direction. The condition fails
    closed - the ability does not trigger - rather than being treated as
    unrestricted, the same "recognised but unreadable is not the same as
    absent" reasoning `intervening_if_notices` already applies."""

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

    cast_from_hand_exile_notices: list[CastFromHandExileNotice] = Field(default_factory=list)
    """One entry per "Whenever a player casts a spell from their hand, that
    player exiles it[, ...]" effect (Knowledge Pool's, Possibility Storm's)
    whose tail - what happens after the exile - this wave could not read.
    Knowledge Pool's own reported defect: ability 2 used to resolve, put
    nothing in exile, grant no free cast, and leave the cast spell sitting on
    the stack, with nothing anywhere recording that a clause had gone
    unread. The same unreadable-is-not-the-same-as-no-effect record every
    other notice list here keeps."""

    conditional_clause_notices: list[ConditionalClauseNotice] = Field(default_factory=list)
    """One entry per "you may sacrifice `<restriction>`. If you do,
    `<consequence>`." effect (CR 118.12) whose restriction or consequence
    could not be read - Disciple of Freyalise's and Sanctum of Ugin's own
    defect before this list existed: both used to resolve offering no choice
    at all, with nothing anywhere recording that a choice had gone unoffered.
    The same unreadable-is-not-the-same-as-no-effect record every other
    notice list here keeps."""

    reflexive_clause_notices: list[ReflexiveClauseNotice] = Field(default_factory=list)
    """One entry per "`<action>`. When you do, `<consequence>`." effect
    (CR 603.12) whose action or consequence could not be read - Guide of
    Souls' own defect before this list existed: its attack trigger's "you may
    pay {E}{E}{E}" resolved offering no choice at all (paying energy is a
    missing primitive, `docs/engine-coverage.md`), with nothing anywhere
    recording that a choice had gone unoffered. The same unreadable-is-not-
    the-same-as-no-effect record every other notice list here keeps."""

    unwired_choice_notices: list[UnwiredChoiceNotice] = Field(default_factory=list)
    """One entry per sentence of a card that reads back its own CR 614.12a
    "as [this] enters, choose ..." answer in a shape this wave does not
    perform - Runed Halo's player-granted protection, Pithing Needle's and
    Disruptor Flute's activation/casting restrictions by name, Cavern of
    Souls' restricted-mana grant. See `UnwiredChoiceNotice` for why each of
    the four is out of scope and what would be needed to wire it. The one
    payoff this wave performs end to end - "adds an additional ..." mana - is
    excluded from this list entirely, and Voice of All's permanent-targeted
    protection grant already gets a `LayerNotice` for free from the existing
    static-ability sweep, so it is not duplicated here either."""

    unreadable_copy_exception_notices: list[UnreadableCopyExceptionNotice] = Field(
        default_factory=list
    )
    """One entry per "enter as a copy of X, except ..." replacement whose
    exception tail this session's parser could not read - see
    `UnreadableCopyExceptionNotice`. Recorded instead of silently applying the
    copy with no exception, which is the fix for a real defect: Echoing Deeps
    copying a graveyard land without ever becoming a Cave, because a `None`
    meaning "unreadable" and a `None` meaning "nothing printed" collapsed into
    the same `effect.copy_exception or CopyException()` default."""

    suspend_redirect_notices: list[SuspendRedirectNotice] = Field(default_factory=list)
    """One entry per "counter target spell. If it is countered this way,
    exile it with N time counters ... . If it doesn't have suspend, it gains
    suspend." effect (Delay) - recognised, but deliberately not executed,
    because CR 702.62a's suspend is not built anywhere in this engine
    (`ExileMarker` has no `SUSPENDED` entry, nothing removes a time counter at
    upkeep) and countering the spell while silently dropping "it gains
    suspend" would leave the card exiled with no way back, which is not what
    it says. See `SuspendRedirectNotice` for why the whole paragraph fails
    closed instead of half-executing it."""

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

    keyword_line_notices: list[KeywordLineNotice] = Field(default_factory=list)
    """One entry per computed ability line (CR 613.5) that is part CR 702
    keyword and part something `machines/combat.py`'s reading vocabulary cannot
    name - Extinguisher Battleship's "5+ | Flying, trample", where CR 721.2a's
    station symbol makes the whole line conditional, and Nevinyrral, Urborg
    Tyrant's "Hexproof from artifacts, creatures, and enchantments", which
    CR 702.11f makes shorthand for several separate abilities. The line is
    dropped whole rather than half-read, because half-reading it would grant an
    ability unconditionally that the card grants conditionally; this is the
    record that it was dropped, the same unreadable-is-not-the-same-as-no-effect
    entry `EvasionNotice` and `UndefinedPowerNotice` keep. Before this list
    existed the drop was silent, which is how Emrakul, the Promised End lost
    flying and trample on the computed board with nothing saying so."""

    undefined_power_notices: list[UndefinedPowerNotice] = Field(default_factory=list)
    """One entry per creature `combat._power_of` was asked to assign combat
    damage for but could not compute a power for - a printed `*` with no
    characteristic-defining ability the engine reads. `power or 0` used to
    fold that into a real 0 rather than record the gap; now the creature
    assigns no combat damage for the step and this is why, the same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps."""

    unmodeled_trigger_effect_notices: list[UnmodeledTriggerEffectNotice] = Field(
        default_factory=list
    )
    """One entry per triggered ability whose condition fired for real but whose
    resolution clause names a mechanism this engine has no primitive for at
    all - a per-instance cast permission, an unbounded card-count choice, a
    target restricted by the trigger event rather than the ability's own
    printed text. See `UnmodeledTriggerEffectNotice`'s own docstring for the
    three cases this wave found (Ragavan, Nashi, Questing Beast). The same
    unreadable-is-not-the-same-as-no-effect record every other notice list
    here keeps."""

    control_replacement_notices: list[ControlReplacementNotice] = Field(default_factory=list)
    """One entry per resolving spell whose text reads as a CR 614.1a
    "if [a permanent] would enter the battlefield under [a player]'s
    control, it enters under [another player]'s control instead" -
    Gather Specimens is the fixture pool's example. Recognised by shape but
    not built: `ReplaceableEvent` has no field for a replacement to redirect
    an entering permanent's controller into, and nothing here represents a
    temporary, spell-conjured replacement rule watching every future zone
    change the way `machines/replacement.py`'s `parse_replacement_effects`
    reads a permanent's own printed one. See `ControlReplacementNotice`."""

    opening_hand_notices: list[OpeningHandNotice] = Field(default_factory=list)
    """One entry per card paragraph that claims a CR 103.6 opening-hand action
    the engine did not carry out - a paragraph that mentions an opening hand but
    matches neither CR 103.6a's nor CR 103.6b's template, or one that matches but
    carries a rider `machines/opening_hand.py`'s `RIDERS` has no entry for. The
    action is then not offered at all, so nothing reads as permission while doing
    less than the card says. The same unreadable-is-not-the-same-as-no-effect
    record every other notice list here keeps."""

    opening_hand_actions_taken: bool = False
    """Whether CR 103.6's sequence has already run for this game.

    CR 103.6b: "Each card may be revealed this way only on[ce]" - the excerpt
    truncates, but running the sequence twice would break it, and CR 103.6 puts
    the sequence between one completed mulligan process and one first turn.
    `take_opening_hand_actions` is idempotent because of this flag."""

    pregame_seed: str = ""
    """Seed prefix for every reshuffle CR 103.5's mulligans cause in this game.

    A mulligan shuffles (CR 103.5), so the pregame is the one part of starting a
    game that consumes randomness, and it has to stay reproducible now that the
    process is driven declaration by declaration rather than by one call. The
    `Match` that dealt the hands sets this to the same prefix its own
    `_game_seed` builds, so the per-mulligan seed string is byte for byte the one
    the blocking loop derived and a replay with the same declarations is
    identical. Empty for a game nobody dealt a deck to, which never mulligans.
    """

    mulligan_declarations: dict[str, bool] = Field(default_factory=dict)
    """This round's CR 103.5 declarations, by username. True is "take a mulligan".

    CR 103.5: "First, the starting player declares whether they will take a
    mulligan. Then each other player in turn order does the same. Once each
    player has made a declaration, all players who decided to take mulligans do
    so at the same time." The declarations have to be *collected* before any of
    them is acted on, and this is where they wait. Cleared as each round
    resolves, so it always holds the round in progress and nothing else.
    """

    opening_hand_seat: int = 0
    """Which seat is taking its CR 103.6 opening-hand actions, as an index into `players`.

    CR 103.6: "the starting player may take any such actions in any order. Then
    ea[ch ...]" - the excerpt truncates, but the starting player going first and
    the other players following is stated outright, and `players` is seated with
    the starting player first. So this walks that list, one seat at a time, and
    a seat is done when it says so.
    """

    opening_hand_reveals: list[UUID] = Field(default_factory=list)
    """Cards revealed from an opening hand under CR 103.6b, in the order shown.

    "The card remains revealed until the first turn begins." A `Reveal` in
    `reveals` is CR 701.20a's momentary showing and says nothing about how long
    it lasts; this is the separate, longer-lived fact CR 103.6b creates, kept as
    ids because the cards themselves stay in hand (CR 701.20b)."""

    reveals: list[Reveal] = Field(default_factory=list)
    """Every card that has been revealed this game (CR 701.20a), in order.

    Public information, and *only* what was actually shown: a reveal out of a
    hidden group of cards - a hand, a library, a sideboard outside the game -
    puts one entry here per card the effect named, never the group it came
    from. Anything reading this to decide what an opponent may see gets the
    reveal and nothing around it. See `Reveal`."""

    spells_cast_this_turn: dict[str, list[CardState]] = Field(default_factory=dict)
    """Every spell each player has cast this turn, keyed by controller
    (CR 601.2a marks the casting event; `put_on_stack` records it here).
    Feeds Damping Sphere's per-spell cost increase and
    `_first_spell_this_turn_holds`'s "first [type] spell you've cast this
    turn" intervening *if* clauses. Cleared when a new turn begins."""

    cards_drawn_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many cards each player has actually drawn this turn, keyed by the
    player who drew them.

    CR 121.2: "Cards may only be drawn one at a time. If a player is instructed
    to draw multiple cards, that player performs that many individual card
    draws." So this counts individual draws, not instructions - which is what
    makes an ordinal condition ("you draw your third card in a turn", Tamiyo,
    Inquisitive Student) answerable at all.

    Counted in `draw_cards`, inside the loop over the cards that were *really*
    drawn, immediately before the `TriggerEvent.DRAWS_A_CARD` emit for that
    same card. Before, because the matcher
    (`machines/triggers._unread_condition_matches`) reads this counter while
    the event is being dispatched and compares it for equality with the
    ordinal - counting afterwards would leave the third draw reading two and
    the ability would silently never fire. A draw that a replacement effect
    reduced to nothing produced no card and is not counted (CR 603.2g: "An
    ability triggers only if its trigger event actually occurs").

    Cleared when a new turn begins, the same reset `spells_cast_this_turn`
    already gets."""

    permanents_sacrificed_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many permanents each player has sacrificed this turn, keyed by the
    controller who sacrificed them.

    CR 701.21a: "To sacrifice a permanent, its controller moves it from the
    battlefield directly to its owner's graveyard." That is a distinct action
    from the destruction or the bounce that also move a permanent off the
    battlefield, which is why `permanents_left_battlefield_this_turn` cannot
    answer "you sacrificed a permanent this turn" (Phoenix Fleet Airship's
    intervening *if*, CR 603.4): a destroyed permanent left the battlefield
    and was never sacrificed.

    Recorded in `sacrifice`, next to the `TriggerEvent.IS_SACRIFICED` emit, by
    the controller the permanent had while it was still on the battlefield -
    the player CR 701.21a names as the one doing the sacrificing. A count
    rather than a flag, so a future card asking "two or more" has the number;
    today only "at least one" is ever asked. Cleared when a new turn begins."""

    open_payment_pools: dict[str, ManaPool] = Field(default_factory=dict)
    """The working mana pool of each player's currently open `CostPayment`.

    CR 106.4: mana a player has produced and not yet spent is in their mana
    pool. `machines/cost.CostPayment` works on a *copy* of that pool so a
    cancelled payment (CR 733.1) throws away only what it produced, which
    means that between CR 601.2g's mana abilities and CR 601.2h's payment the
    player's own `ManaPool` underreports: the mana the payment just made is
    real, unspent, and invisible there.

    Nothing cared until a continuous effect had to count it. Omnath, Locus of
    Mana's "Omnath gets +1/+1 for each unspent green mana you have" is read by
    `computed_board`, and DDR#955 is exactly the case where the mana is
    sitting in an open payment - four green produced for Momentous Fall, with
    the sacrifice paid before it (CR 601.2h's "in any order"). Registered by
    `CostPayment._seed_payer_pool` and dropped when the payment is paid,
    cancelled or rewound, so it is never a second pool a player owns - it
    *replaces* the player's own for as long as it is open, since it opened as
    a copy of it.

    """

    permanents_left_battlefield_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many permanents each player controlled at the moment those
    permanents left the battlefield this turn, keyed by that controller.

    Feeds Revolt (an ability word, CR 207.2c - `knowledge_search` found no
    numbered rule for Revolt itself beyond that) and any other card whose text
    reads "a permanent you controlled left the battlefield this turn": Fatal
    Push's own "if a permanent left the battlefield under your control this
    turn." Recorded at the moment of the move (`destroy`, `sacrifice`,
    `exile_permanent`, `return_to_hand` all route through `_note_left_
    battlefield`), by the controller the permanent had *while it was still on
    the battlefield* - not the owner, since revolt asks who controlled it, and
    not whoever controls the object now that it has moved to an uncontrolled
    zone. A count, not a bare flag, so nothing here has to guess whether two
    departures in the same turn matter to some future card; today only
    "at least one" is ever asked. Cleared when a new turn begins, the same
    reset `spells_cast_this_turn` already gets."""

    spells_cast_last_turn: dict[str, list[CardState]] = Field(default_factory=dict)
    """What `spells_cast_this_turn` held during the turn before this one.

    The werewolves' question (CR 603.4's intervening *if*): Duskwatch Recruiter
    transforms "if no spells were cast last turn" and Krallenhorde Howler
    transforms back "if a player cast two or more spells last turn". Neither is
    answerable from `spells_cast_this_turn`, which is emptied as a new turn
    begins - so it is snapshotted here at that same moment instead of being
    thrown away. A spell is counted when it is cast (CR 601.2a, CR 601.2i),
    which is exactly what `put_on_stack` already records.
    """

    cards_discarded_this_turn: dict[str, int] = Field(default_factory=dict)
    """How many cards each player has cycled or discarded this turn, keyed by
    the player who discarded them.

    CR 701.9a is the discard itself ("To discard a card, move it from its
    owner's hand to that player's graveyard"), and CR 702.29a makes cycling a
    discard too: "'Cycling [cost]' means '[Cost], Discard this card: Draw a
    card.'" - the card is discarded to pay an activation cost, so one cycled
    card is one discarded card and is counted once, never twice, which is the
    same "only once when a card is cycled" CR 702.29d spells out for the
    triggered-ability version of the question.

    Recorded in `discard_cards`, the single place a discard is instructed
    (`machines/cost.py`'s discard cost component - which is what a cycling
    activation pays - and `machines/effects.py`'s discard effects both route
    there). `Player.discard_to_maximum_hand_size`, the cleanup step's CR 514.1
    discard, is the one path that still does not, so a cleanup discard is not
    counted here; nothing can be cast between it and the turn ending, so no
    cost this feeds could read it.

    Feeds Hollow One's own "This spell costs {2} less to cast for each card
    you've cycled or discarded this turn" (CR 601.2f). Cleared when a new turn
    begins, the same reset `spells_cast_this_turn` already gets."""

    life_gained_this_turn: SortedSet[str] = Field(default_factory=set)
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

    once_per_turn_triggers: dict[str, int] = Field(default_factory=dict)
    """How often a "this ability triggers only once each turn" ability has
    already triggered this turn, keyed `"<source id>:<printed condition>"` -
    CR 603.2h: "A triggered ability may have an instruction ... This ability
    triggers only if its source's controller has not yet taken the indicated
    action that turn." Caretaker's Talent's own "Whenever one or more tokens
    you control enter, draw a card. This ability triggers only once each
    turn." is the only printing in the pool; `machines/triggers.triggers_for`
    reads and increments this instead of putting a second copy of the same
    trigger on the stack later in the same turn. Cleared when a new turn
    begins, alongside `activations`/`loyalty_activations`."""

    resolving: StackObject | None = Field(default=None, exclude=True, repr=False)
    """The object currently resolving, or None (CR 608.2).

    `resolve_top` pops the object off the stack before running its effect, so
    while a spell resolves it is on no zone at all. CR 724.1b's "including the
    object that's resolving" needs to be able to name it, and this is the only
    place that can. Excluded from serialisation: it is live only for the length
    of one resolution and means nothing in a stored board."""

    turn_ended_exiled_ids: SortedSet[UUID] = Field(default_factory=set, exclude=True, repr=False)
    """Spells CR 724.1b exiled while they were resolving.

    `end_the_turn` gives the resolving spell a zone (exile) that `resolve_top`
    would otherwise overwrite with the graveyard or the battlefield a few lines
    later. This is how the two halves agree; each id is consumed once."""

    state_trigger_latches: dict[str, UUID] = Field(default_factory=dict)
    """Which CR 603.8 state trigger is currently held shut, and by what.

    CR 603.8: an ability that triggers on a game state rather than an event
    "doesn't trigger again until it has left the stack". Keyed
    `"<source id>:<printed condition>"`, the value is the id of the
    `AbilityOnStack` that triggered - `machines/triggers.state_triggers_for`
    drops the entry the moment that object is neither on the stack nor waiting
    in `pending_triggers`, so the latch opens for a resolved ability and a
    *countered* one alike (CR 701.6a: countering removes it from the stack).
    Not cleared per turn: the latch is about the stack, not the turn."""

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

    coin_flips_performed: int = 0
    """How many coin flips this game has done, counting up - `shuffles_performed`'s
    own convention (see its docstring), applied to CR 705.1's own randomness
    instead: `flip_coin` seeds each flip from `f"{shuffle_seed}:
    {coin_flips_performed}:coin"`, so a scenario asserting on the result
    stays reproducible and the second flip of a game differs from the first."""

    schema_version: int
    """The engine schema version this `Game` was built or decoded at - T9 of
    the stateless-library plan.

    **What this tracks, and why it is not `__version__`.** `magic_cards_model
    .__version__` (`src/magic_cards_model/__init__.py`) names a package
    release; it changes for reasons that have nothing to do with whether a
    decoded snapshot still means what it meant when it was written - a new
    public helper, a packaging fix, a docstring pass. Gating replay safety on
    it would force a bump on every irrelevant release and, worse, would not
    force one on the change that actually matters: correcting an entry in
    `machines/effects.py`'s `EFFECTS` (card-name-keyed), a mana-ability parse
    in `machines/abilities.py`, a `DelayedEffectSpec` in `machines/delayed.py`,
    a continuous-effect spec in `machines/layers.py`, or `machines/triggers.
    py`'s condition matching - none of which need to move the package version
    at all. This field is a separate, purpose-built counter, starting at
    `CURRENT_SCHEMA_VERSION` (see that `ClassVar`'s own docstring for exactly
    when to bump it), that exists for exactly one question: "does a `Game`
    dumped by the build that wrote it still mean the same thing decoded here?"

    **Why a bare `int` field with no default, not a defaulted one.** A
    defaulted field would let a decoded dict that is simply missing this key -
    every snapshot written before this field existed, and any future decode
    input nobody stamped - fill in `CURRENT_SCHEMA_VERSION` silently and pass
    as though it were current. That is exactly the shape `memory/silent-
    default-dispatch-tables.md` names as this codebase's dominant defect: "a
    lookup that defaults instead of refusing." `_check_schema_version` below
    (a `mode="before"` validator, so it sees the raw input before pydantic
    would apply any default) refuses both a present-but-different version and
    an absent one, with two distinct messages - **fail closed** is the
    documented policy for both, deliberately, per this task's own directive.
    That refusal fires on every construction path alike (`Game(...)`,
    `Game.model_validate(...)`, and `Game` nested inside `Match.games`, since
    a `mode="before"` validator is compiled into the type's own core schema
    rather than being a classmethod override some entry points could route
    around) - which is exactly why every fresh-construction call site in this
    repo (`Match.start_game`, the scenario harness, and the handful of bare
    `Game(players=...)` sites in `tests/`) now passes
    `schema_version=Game.CURRENT_SCHEMA_VERSION` explicitly rather than
    relying on a default: nothing builds a `Game` without saying, out loud,
    what engine version it is built at.

    **The migration answer for pre-versioning data**, stated plainly since the
    task asked for a deliberate choice rather than an accident: there is no
    real pre-versioning data anywhere this engine persists to yet (`GameStore`
    in `magic-cards-model-api` is in-memory only; PostgreSQL persistence is
    the very next phase this task exists to prepare for), so "migrate it
    forward" has no data to act on and would be inventing a guarantee nobody
    can honour - a decoded snapshot's *behaviour*, not just its shape, is what
    is unknown, and no mechanical upgrade can restore behaviour that was never
    recorded. A versionless snapshot is therefore refused exactly like a
    mismatched one, with a message that says so, rather than assumed current.
    """

    #: The schema version a fresh `Game` is stamped with and the only one
    #: `_check_schema_version` accepts on decode. Bump this whenever a change
    #: would make a `Game.model_dump()` produced by the *previous* value mean
    #: something different decoded under the *new* one - which is a wider set
    #: of changes than "the dump's shape changed":
    #:
    #: - A field added to, removed from, renamed on, or retyped on `Game` or
    #:   anything reachable from its dump (`Player`, `CardState`,
    #:   `AbilityOnStack`, a `DelayedEffectSpec` variant's `kind`, a
    #:   `machines/layers.py` continuous-effect spec, ...), or a changed
    #:   default for one of those fields.
    #: - A behavioural change to anything a decoded `Game`'s *own recorded
    #:   state* could already be pointing at by name or kind: an `EFFECTS`
    #:   entry in `machines/effects.py` gaining, losing, or changing its
    #:   resolution (this is the case `docs/engine-coverage.md` calls out by
    #:   name - a card that resolved as a no-op under the old build and does
    #:   something under the new one is exactly a state resolving differently
    #:   with no signal, the failure mode this whole field exists to catch),
    #:   a `machines/abilities.py` mana-ability parse, a `DelayedEffectSpec`'s
    #:   resolution, a `machines/triggers.py` condition match, a layer
    #:   application in `machines/layers.py`, or any other name-/kind-keyed
    #:   dispatch a `CardState` already on a decoded battlefield, stack, or
    #:   pending-trigger list could reach.
    #:
    #: Not bumped for a change that cannot affect any state that could
    #: already exist - a docstring, a test, a refactor with no behavioural
    #: delta, or a wholly new mechanic/keyword no printing in the pool used
    #: before this change existed to write it. When genuinely unsure whether a
    #: change qualifies, bump it: a spurious bump costs a discarded stale
    #: snapshot on the next decode; a missed one costs a wrong game nobody
    #: detects, which is the entire problem this field exists to solve.
    CURRENT_SCHEMA_VERSION: ClassVar[int] = 5
    """Bumped 1 -> 2: `CardState` gained `state_class` (defect 2, the
    `engine-stateless-library` review) - a field added to `CardState`, per the
    bump rule above, and one whose absence would change what a decode of a
    copy-of-a-permanent-spell mid-stack means (a plain `CardState` loses CR
    111.8's protection the moment it becomes a token, silently).

    Bumped 2 -> 3: `AbilityOnStack` gained `state_class` (T3, the
    `StackObject`-discriminated-union task) - a field added to a persisted
    model, per the bump rule above, needed to turn `StackObject` from an
    untagged `CardState | AbilityOnStack` union into a discriminated one so a
    `TokenState` in `Game.shared_zones` dumps without a
    `PydanticSerializationUnexpectedValue` warning. A snapshot written at
    version 2 has no `state_class` on any `AbilityOnStack` it holds, so
    decoding it at version 3 would fail the union's own discriminator lookup
    with no signal beyond a raw pydantic error - refusing it at the schema
    check instead names the real reason.

    Bumped 3 -> 4: `TargetRef` gained `zone_change_stamp` (CR 400.7/608.2b -
    the blink-versus-removal-spell defect: a target that changed zones and
    came back is a new object even though `CardState.id` did not change, and
    nothing previously recorded which incarnation a target reference named).
    A snapshot written at version 3 has every `TargetRef` on the stack with
    no stamp at all, which `Game.legal_target` reads as "cannot judge the
    zone-change half of CR 608.2b" rather than as evidence of anything - a
    silent fail-open on the exact rule this field exists to enforce, so a
    version-3 snapshot is refused rather than decoded as if it were current.

    Bumped 4 -> 5: `Game` gained `keyword_line_notices`, and - the half that
    actually matters - `machines/combat.py::has_keyword` reads a computed
    ability line with a wider vocabulary than it used to. A version-4 snapshot
    is a board on which Emrakul, the Promised End has no flying and no trample,
    because `protection from instants` sharing their line took them down with
    it; decoded under version 5 the same board has both. That is a
    name-keyed dispatch resolving differently on state that already exists -
    the bump rule's second bullet exactly - and it changes who may block whom
    and how much damage a defending player takes, so a version-4 snapshot is
    refused rather than replayed into a different game.
    """

    @model_validator(mode="before")
    @classmethod
    def _check_schema_version(cls, data: Any) -> Any:
        """Refuse to decode a `Game` snapshot at any schema version other
        than `CURRENT_SCHEMA_VERSION`, and refuse one with no version at all -
        see `schema_version`'s own docstring for why both are refusals rather
        than a silent default. `mode="before"` so this runs on the raw input,
        before pydantic could fill in a default and make "missing" look like
        "current", and so it fires uniformly on `Game(...)`, `Game.
        model_validate(...)`, and `Game` decoded as an element of
        `Match.games` alike.
        """
        if not isinstance(data, Mapping):
            # Not a mapping decode input - a `Game` instance being re-wrapped,
            # or another shape pydantic's own validation will reject on its
            # own terms. Nothing here to check against a raw dict.
            return data
        if "schema_version" not in data:
            raise SchemaVersionMismatch(
                "Game snapshot carries no schema_version field, so it predates "
                "engine schema versioning (current: "
                f"{cls.CURRENT_SCHEMA_VERSION}). Refusing to decode it: engine "
                "behaviour is a function of (state, engine version), not of "
                "state alone, and an unversioned snapshot gives no way to know "
                "which engine version's behaviour it was recorded under."
            )
        found = data["schema_version"]
        if found != cls.CURRENT_SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                f"Game snapshot was written at schema_version={found!r}, but "
                f"this build decodes schema_version={cls.CURRENT_SCHEMA_VERSION}. "
                "Refusing to decode a mismatched snapshot: a name-keyed "
                "registry or text parser change between those versions may "
                "make this state resolve differently than it did when it was "
                "written, silently. Replay it on the engine version that wrote "
                "it, or migrate it explicitly - decoding it here unmigrated is "
                "not safe."
            )
        return data

    game_uid: UUID = Field(default_factory=uuid4)
    """This `Game`'s own identity, mixed into every id `_allocate_id` mints.

    `shuffle_seed` is what makes two games *shuffle* identically when they
    share a seed (CR 701.24a) - by design, since a replay must reshuffle the
    same way. An object id has the opposite requirement: it must be unique,
    never shared with any other object anywhere, including another game built
    at the default `shuffle_seed=0`. Deriving ids from `shuffle_seed` alone
    made every such game mint the identical sequence
    `uuid5(NAMESPACE_OID, "0:0")`, `"0:1"`, ... - two unrelated games colliding
    on every id in lockstep. `game_uid` is a plain serialised field precisely
    so it survives a decode: a snapshot replayed twice carries the same
    `game_uid` both times (byte-identical replay, `objects_created`'s own
    guarantee below), while a freshly built `Game` gets a fresh one via
    `uuid4`'s own randomness (unique identity, this field's guarantee) -
    `default_factory` runs once per construction, never on `model_validate`
    decoding an already-serialised value.
    """

    objects_created: int = 0
    """How many object ids this game has minted, counting up -
    `shuffles_performed`'s own convention (see its docstring), applied to
    `ids.new_id` instead of `Random`. Every mutating public method installs
    `_allocate_id` as this context's id allocator for the span of its own
    call, through `_id_allocator_scope` (see its docstring), so a game
    replayed from the same decoded snapshot - the same sequence of calls -
    mints the same ids, in the same order, both times.

    Scoped to the one call that installs it, and reset again once it returns,
    rather than installed once for the object's whole life: two unrelated
    `Game`s built moments apart in the same process would otherwise both start
    minting from whatever `_allocate_id` produces first and leave that
    allocator sitting active for whichever next call anywhere in the process
    happens to create an object - a card built for a *different* game's
    opening hand, say - which is a real collision, not merely a cosmetic one:
    two distinct objects would compare equal by id."""

    draw_redirections: list[DrawRedirection] = Field(default_factory=list)
    """CR 614.1a replacement effects a resolved spell left behind, taking one
    player's draws for another - Plagiarize.

    Kept beside `prevention_shields` and for the same reason: the source is a
    graveyard card by the time the effect ever applies, and the effect has a
    duration of its own (CR 514.2 ends it in the cleanup step, which is where
    `discard_to_maximum_hand_size` clears the list)."""

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

    def _allocate_id(self) -> UUID:
        """One `uuid5(game_uid, objects_created)` id - see `game_uid`'s own
        docstring for why identity, not `shuffle_seed`, is the namespace, and
        `objects_created`'s for why this is installed per call rather than
        once."""
        allocated = uuid5(NAMESPACE_OID, f"{self.game_uid}:{self.objects_created}")
        self.objects_created += 1
        return allocated

    @contextmanager
    def _id_allocator_scope(self) -> Iterator[None]:
        """Install `_allocate_id` as this context's id allocator for the
        span of the `with` block, restoring whatever was installed before on
        exit - `objects_created`'s own docstring is why every mutating public
        method needs this rather than installing once for the object's whole
        life.

        Every one of those methods opens its own `with self._id_allocator_
        scope():` rather than sharing one scope across a whole request:
        `install_id_allocator` returns the `ContextVar` `Token` `reset_id_
        allocator` needs, so nesting is safe by construction - an inner
        scope's exit restores the outer scope's allocator (this same one,
        when both belong to the same game) rather than clobbering it with
        `None`. `pass_priority` calling `resolve_top`, which is also called on
        its own by another caller, is exactly this shape.
        """
        token = install_id_allocator(self._allocate_id)
        try:
            yield
        finally:
            reset_id_allocator(token)

    def model_post_init(self, _context: object) -> None:
        usernames = [player.username for player in self.players]
        for player in self.players:
            # CR 701.9a's discard has to be able to consult the game, because
            # CR 702.35a's madness replaces where the discarded card lands. A
            # `Player` on its own has nothing to ask; this is the back-reference
            # that lets `Player.discard` find the rules. Excluded from the
            # serialised model, so it cannot make the game state cyclic.
            player.game = self
        for zone_cards in self.shared_zones.values():
            # `CardState.bind_to_game` (CR 613.5) is what makes `power`/
            # `toughness` ask the layer engine instead of falling back to the
            # printed value plus counters. `Game.put_onto_battlefield` is its
            # only production call site, so a permanent already on the
            # battlefield the moment a `Game` is built straight from a dict -
            # every cold `model_validate` - never got bound at all, and
            # answered with the printed value even under an anthem, silently
            # different from the same game played continuously. This binds
            # every `CardState` the game holds, shared zones and each player's
            # own, the same walk `card_state.bind_all_to_game` does by hand.
            for state in zone_cards:
                if isinstance(state, CardState):
                    state.bind_to_game(self)
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    state.bind_to_game(self)
        for stack_item in (*self.stack, *self.pending_triggers):
            # `AbilityOnStack.keyword_activation.game` (`machines/keywords.
            # KeywordActivation.game`) is the same shape as `Player.game`
            # above - excluded from serialisation because it is a live `Game`,
            # relinked here rather than kept as a cycle. Both `self.stack` and
            # `self.pending_triggers` can hold an `AbilityOnStack` (`CostPayment.
            # _discard_triggers_caused` checks the same two places for the
            # identical reason), so both are walked even though only an
            # *activated* ability ever actually carries a `keyword_activation` -
            # a triggered one has none to relink.
            #
            # Only `self.stack` is walked among `shared_zones` - not every zone
            # the dict's declared type (`dict[Zone, list[StackObject]]`) would
            # in principle allow an `AbilityOnStack` into. That is correct
            # today: every place this engine puts an `AbilityOnStack` anywhere
            # puts it on the stack (`battlefield`'s own docstring already says
            # as much - "Only cards ever live here, never abilities" - and the
            # same is true of exile, command, and ante, none of which any
            # activation or trigger path ever touches). It is still brittle
            # against the type as written, which says nothing that would stop
            # a future zone from holding one; if that ever changes, this walk
            # has to widen with it rather than silently leaving a relink gap
            # the type system would not catch.
            if not isinstance(stack_item, AbilityOnStack):
                continue
            if stack_item.keyword_activation is not None:
                activation = stack_item.keyword_activation
                activation.game = self
                if activation.payment is not None:
                    # `KeywordActivation.payment` (`machines/cost.CostPayment`)
                    # has the identical `game: Any = Field(exclude=True)` shape,
                    # and without this a resumed crew/equip/cycling payment
                    # that is still `PENDING` - an open ward-shaped cost mid
                    # activation - comes back unable to seed its payer's pool
                    # or find anything it tapped (CR 733.1's rewind needs
                    # `game` to find the payer and the tapped sources by id).
                    activation.payment.game = self
            if stack_item.unless_payment is not None:
                # `AbilityOnStack.unless_payment` (CR 702.21a's ward) is the
                # other `CostPayment` this object can hold, sitting beside
                # `keyword_activation` rather than inside it - relinked the
                # same way and for the same reason: `_seed_payer_pool` needs
                # `game` to have run at all, and a payment paused mid-payment
                # (`begin_paying`, still `PENDING`) needs it seeded to resume.
                stack_item.unless_payment.game = self
        if self.turn is None:
            self.turn = TurnMachine(players=usernames)
        if self.priority is None:
            self.priority = PriorityMachine(players=usernames)
            # A fresh `TurnMachine` rests at `Step.UNTAP`, where CR 502.4 gives
            # nobody priority. Saying so from the first moment is the point:
            # a client polling a just-built game must not be told the active
            # player is on the clock when the only legal next thing is the
            # step ending.
            self.sync_priority_with_step()

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

        CR 613.5: read off the computed board, not the printed line - Blood
        Moon (CR 305.7's set-a-land's-subtype path) replaces a nonbasic
        land's subtypes with Mountain, and a permanent controlled by
        `_controlled_land_types` is the one every consumer here means to ask
        about right now, not the printed card underneath it.
        """
        board = self.computed_board()
        return frozenset(
            subtype
            for state in self.permanents_controlled_by(controller)
            if state.zone is Zone.BATTLEFIELD and Type.LAND in board.of(state).types
            for subtype in board.of(state).subtypes
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

        Run under `_id_allocator_scope`: `_untap_step_impl`'s own `emit` per
        untapped permanent mints a fresh `AbilityOnStack` id for every
        "becomes untapped" trigger it finds. `turn_based_actions` already
        reaches this from inside `advance`'s own scope, but the api's `set_
        step` also calls it directly on its own (`engine_api.py` around line
        953), so it needs a scope of its own rather than relying on that
        nesting.
        """
        with self._id_allocator_scope():
            self._untap_step_impl()

    def _untap_step_impl(self) -> None:
        """The rest of `untap_step` - see its own docstring for why it is split out."""
        active = self.active_player
        self.begin_turn_for(active.username)
        remaining = self.players_skipping_next_untap.get(active.username, 0)
        if remaining > 0:
            # CR 614.10: "skip [something]" replaces the step with nothing -
            # nothing untaps and no BECOMES_UNTAPPED event fires, exactly as
            # if the step never happened.
            if remaining > 1:
                self.players_skipping_next_untap[active.username] = remaining - 1
            else:
                del self.players_skipping_next_untap[active.username]
            return
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
        - **CR 703.4f / 505.4 / 714.3c** - the precombat main phase puts a lore
          counter on each Saga the active player controls with one or more
          chapter abilities (`saga_lore_step`).
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
        elif step is Step.PRECOMBAT_MAIN:
            self.saga_lore_step()
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
            self.declare_attackers(self._resolve_declaration(attacks))

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
            defender = combat_rules.defending_player(self, attack.defender)
            attackers_by_defender.setdefault(defender, []).append(attack.attacker_id)

        blocks: list[tuple[CardState, CardState]] = []
        for username in self._turn_order_from_active():
            if username not in attackers_by_defender:
                continue
            blocks.extend(
                self._resolve_declaration(
                    ask_blockers(
                        self.decisions,
                        username,
                        prompt="declare blockers",
                        attackers=tuple(attackers_by_defender[username]),
                    )
                )
            )
        if blocks:
            self.declare_blockers(blocks)

    def _resolve_declaration(
        self, pairs: "list[tuple[CardState | UUID, CardState | Player | TargetRef | UUID | str]]"
    ) -> list[tuple[CardState, "CardState | Player | TargetRef | str"]]:
        """Turn one `ask_attackers`/`ask_blockers` answer's pairs into the
        `CardState`/`Player`/`str` objects `declare_attackers`/
        `declare_blockers` expect.

        A scripted or defaulted answer already names real objects - every
        scenario in `tests/scenarios/` stages `(CardState, Targetable | str)`
        pairs directly (see `_ask_declaration`), where `Targetable` is
        `CardState | Player` - and passes through here unchanged, `Player`
        included. A recorded `Answer.pairs` entry (a tape of `DeclaredPair`,
        see `machines/decisions.py`) names cards by id instead, because a
        `DeclaredPair` cannot hold a live `CardState` reference; those ids are
        resolved here, against the board as it stands right now.
        `_ask_declaration` already turns a `DeclaredPair`'s `defender_player`
        into the plain username `str` this method's passthrough branch
        already handles, so a recorded attack on a player reaches this method
        exactly the way a scripted one does.

        An id naming nothing in any zone this game can see is refused rather
        than dropped or silently skipped (CR 508.1a's/CR 509.1a's declaration
        is the whole creature or defender named, not whichever of it can be
        found) - see `memory/silent-default-dispatch-tables.md`.
        """
        resolved: list[tuple[CardState, CardState | Player | TargetRef | str]] = []
        for creature, target in pairs:
            creature_state = (
                creature if isinstance(creature, CardState) else self.find_by_id(creature)
            )
            if creature_state is None:
                raise ValueError(f"declaration names {creature!r}, not a card in any zone")
            if isinstance(target, CardState | Player | TargetRef | str):
                resolved.append((creature_state, target))
                continue
            target_state = self.find_by_id(target)
            if target_state is None:
                raise ValueError(
                    f"declaration names {target!r} as a defender, but no such card exists "
                    f"in any zone"
                )
            resolved.append((creature_state, target_state))
        return resolved

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

    def saga_lore_step(self) -> None:
        """CR 703.4f, 505.4, 714.3c: a lore counter on each Saga the active
        player controls with one or more chapter abilities, as their
        precombat main phase begins.

        "This turn-based action doesn't use the stack" (CR 714.3c) - straight
        through `add_counters`, same as any other counter placed outside a
        resolving effect, which is what lets `_emit_lore_counters_added` fire
        CR 107.15a's chapter trigger for whichever threshold this crosses.
        Every Saga controlled gets exactly one, all "simultaneously" the way
        CR 703.4f's own wording has it - order between different Sagas is
        never observable here since nothing this engine reads depends on it.
        """
        active = self.active_player
        for permanent in self.permanents_controlled_by(active.username):
            if permanent.is_saga and permanent.chapter_numbers:
                self.add_counters(permanent, Counter.LORE, 1)

    def end_the_turn(self) -> None:
        """CR 724.1's "end the turn" procedure - Time Stop's whole text.

        CR 724.1: "Some cards end the turn. When an effect ends the turn, follow
        these steps in order, as they differ from the normal process for
        resolving spells and abilities (see rule 608)." The steps this performs,
        each looked up:

        - **CR 724.1a** - "If there are any triggered abilities that triggered
          before this process began but haven't been put onto the stack yet,
          those abilities cease to exist. They won't be put onto the stack."
          `pending_triggers` is emptied.
        - **CR 724.1b** - "Exile every object on the stack, including the object
          that's resolving." An ability on the stack has no card behind it
          (CR 405.1), so it simply ceases to exist; a spell is a card and goes
          to the exile zone. The resolving object is `Game.resolving`, and
          **CR 608.2m** is why exiling it does not stop it: "If an instant
          spell, sorcery spell, or ability that can legally resolve leaves the
          stack once it starts to resolve, it will continue to resolve fully."
          So Time Stop's own remaining text - a spliced-on card's, say - still
          runs after this returns.
        - **CR 724.1d** - "The current phase and/or step ends. If this happens
          during combat, remove all creatures and planeswalkers from combat. The
          game skips straight to the cleanup step." The turn machine's pointer
          is moved to `Step.CLEANUP` directly; the cleanup step's own turn-based
          actions (CR 514.1, 514.2) are `cleanup_step`'s job and are *not*
          performed here, which is what leaves an "until end of turn" effect
          still running for whatever resolves next.
        - **CR 724.1f** - "No player gets priority during this process, so
          triggered abilities are not put onto the stack." Nothing here calls
          `put_triggers_on_stack` or touches the priority machine.

        **Unverified**: `knowledge_search` in this session could not return
        CR 724.1c or CR 724.1e, so neither is implemented or cited here.
        """
        with self._id_allocator_scope():
            assert self.turn is not None
            self.pending_triggers = []  # CR 724.1a
            for stack_object in list(self.stack):  # CR 724.1b
                self.stack.remove(stack_object)
                if isinstance(stack_object, CardState):
                    self._take_out_of_every_zone(stack_object)
                    self.combat.remove(stack_object.id)
                    stack_object.move_to(Zone.EXILE)
                    self.exile.append(stack_object)
                    self.cast_records.pop(stack_object.id, None)
            resolving = self.resolving
            if isinstance(resolving, CardState) and resolving not in self.exile:
                # CR 724.1b's "including the object that's resolving" - already
                # popped off the stack by `resolve_top`, so it is exiled by name.
                self._take_out_of_every_zone(resolving)
                self.combat.remove(resolving.id)
                resolving.move_to(Zone.EXILE)
                self.exile.append(resolving)
                self.turn_ended_exiled_ids.add(resolving.id)
            # CR 724.1d, the combat half: removing every creature and planeswalker
            # from combat is `CombatMachine.clear`'s whole job.
            self.combat.clear()
            self.turn.advance_to(Step.CLEANUP)
            # CR 724.1f: "No player gets priority during this process". The pointer
            # now rests in a cleanup step with an emptied `pending_triggers` and an
            # exiled stack, so CR 514.3's ordinary "no player receives priority"
            # is the state to be in, and this is what puts it there.
            self.sync_priority_with_step()

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
        with self._id_allocator_scope():
            discarded = self.active_player.discard_to_maximum_hand_size()
            self.remove_all_damage()
            self.continuous_effects.end_the_turn(self)  # CR 514.2, the other half
            self.delayed_triggers.expire_this_turn()  # CR 514.2, the delayed-trigger half
            self.prevention_shields = [
                shield
                for shield in self.prevention_shields
                if not shield.spent and not shield.until_end_of_turn
            ]
            # CR 514.2's same sentence again, for the draw redirections: an
            # "until end of turn" replacement effect ends here, *after* the
            # discard above - which is the whole of DDR#957's ruling, since a
            # draw that happens earlier in this same cleanup step is still
            # replaced.
            self.draw_redirections = [
                redirection
                for redirection in self.draw_redirections
                if not redirection.until_end_of_turn
            ]
            self._bottom_unused_cascade_permissions()
            # CR 514.2's same sentence: "all 'until end of turn' ... effects end".
            # A card exiled by Ugin's −11 stays exiled and stops being castable.
            # A Wrenn's Resolve/Reckless Impulse grant (`expires_end_of_next_turn`)
            # is dropped here too, but only once `Game.begin_turn_for` has already
            # marked `owner_next_turn_started` for it (that player's own next turn
            # has begun) *and* this cleanup belongs to that same turn - i.e. this
            # is that turn's own end, not some later one.
            self.play_permissions = [
                permission
                for permission in self.play_permissions
                if not permission.until_end_of_turn
                and not (
                    permission.expires_end_of_next_turn
                    and permission.owner_next_turn_started
                    and self.turn.active_player == permission.player
                )
            ]
            # CR 514.2's same sentence, for CR 611.1's "affects the rules of the
            # game" effects: Ranger-Captain of Eos's "this turn" noncreature ban.
            self.casting_rule_effects = [
                effect
                for effect in self.casting_rule_effects
                if effect.duration is not Duration.UNTIL_END_OF_TURN
            ]
            return discarded

    def _bottom_unused_cascade_permissions(self) -> None:
        """CR 702.85a's own sentence: "Put the exiled cards on the bottom in a
        random order" reaches every card cascade exiled and did not cast, not
        only the ones the choice was declined for. Called just before this
        same step drops expired `PlayPermission`s (CR 514.2), so an
        accepted-but-never-driven cascade cast is swept to the bottom here
        instead of silently vanishing into a dropped permission with the card
        still sitting in exile - see `PlayPermission.bottom_if_unused`'s own
        docstring for why this only ever applies to cascade's grant and not
        Ugin's, Ragavan's, or Suspend's.

        Only a permission that is (a) marked `bottom_if_unused`, (b) about to
        be dropped by this same step's `until_end_of_turn` filter just below
        - `permission.expired(self)` is not the test here, because it compares
        against `TurnMachine.turns_taken` and this runs *before* that counter
        moves on to the next turn, the same reason the unconditional filter
        below cannot use it either - and (c) still pointing at a card
        genuinely sitting unclaimed in the zone it was granted from (CR
        400.7's identity check, `PlayPermission.names`) qualifies. A card
        already cast, or moved some other way, is left alone.
        """
        for permission in self.play_permissions:
            if not permission.bottom_if_unused or not permission.until_end_of_turn:
                continue
            card = self.find_by_id(permission.card_id)
            if card is None or not permission.names(card) or card.zone is not permission.zone:
                continue
            owner = self.player(card.owner or permission.player)
            zone_cards = self.shared_zones.get(permission.zone)
            if zone_cards is not None and card in zone_cards:
                zone_cards.remove(card)
            owner.add(card, Zone.LIBRARY)  # the bottom of the library

    def remove_all_damage(self) -> None:
        """Wipe damage marked on every permanent (CR 514.2, 703.4p).

        The unspent regeneration shields go with it, for the same reason and
        in the same breath: CR 701.19a's shield protects a permanent "the next
        time it would be destroyed **this turn**", so one nobody spent expires
        exactly when every other "until end of turn" effect does.
        """
        for permanent in self.battlefield:
            permanent.damage = 0
            permanent.regeneration_shields = 0

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
        # Teferi, Time Raveler's +1: "Until your next turn" ends the moment
        # this player's next turn would begin (CR 800.4m), the same instant
        # `end_for_next_turn` clears its own layer effects for this player.
        self.casting_rule_effects = [
            effect
            for effect in self.casting_rule_effects
            if not (
                effect.duration is Duration.UNTIL_YOUR_NEXT_TURN
                and effect.until_next_turn_of == username
            )
        ]
        # Two different "next turn" permissions expire off this same hook, and
        # they are not the same shape. Hex Magic's own "Until the end of your
        # next turn, you may play cards exiled this way" (CR 800.4m again) is
        # carried by `PlayPermission.until_next_turn_of` and is dropped here,
        # the same moment as the two stores above. Wrenn's Resolve / Reckless
        # Impulse's own "until the end of your next turn" is carried by
        # `expires_end_of_next_turn` and is *not* dropped here: the moment this
        # is `username`'s own turn beginning again, past the turn it was granted
        # on, that permission's "next turn" has arrived, so it is only marked -
        # `Game.cleanup_step` removes it at this turn's own cleanup, once
        # `owner_next_turn_started` is set. Dropping happens first so a
        # permission carrying both is not marked on its way out.
        self.play_permissions = [
            permission.model_copy(update={"owner_next_turn_started": True})
            if (
                permission.player == username
                and permission.expires_end_of_next_turn
                and not permission.owner_next_turn_started
                and permission.granted_turns_taken != self.turn.turns_taken
            )
            else permission
            for permission in self.play_permissions
            if permission.until_next_turn_of != username
        ]

    def can_activate_tap_ability(self, permanent: CardState) -> bool:
        """Whether a `{T}` ability of this permanent may be activated (CR 302.6).

        Only creatures are affected: a land or an artifact taps the turn it
        arrives. Read off the computed board (CR 613.5), not the printed type
        line, so a permanent a continuous effect turned into a creature this
        turn - The Filigree Sylex after Karn, the Great Creator's +1 - is
        still held to the restriction: CR 302.6 asks how long the permanent
        has been controlled, not how long it has been a creature, so an
        artifact already on the battlefield before this turn began stays
        exempt the moment it becomes a creature, while one that entered and
        was animated in the same turn is held back. Haste turns the
        restriction off (CR 702.10c) - `has_keyword` is passed this `Game` too,
        so a haste granted by a continuous effect (layer 6) counts, not only
        one printed on the card. So does an effect that only says to treat the
        creature *as though* it had haste, without granting the keyword: see
        `activation_haste_permission` for why CR 609.4 makes that reach here
        and nowhere else.
        """
        if not self.characteristics_of(permanent).is_creature:
            return True
        if not permanent.summoning_sick or has_keyword(permanent, Keyword.HASTE, self):
            return True
        return self.activation_haste_permission(permanent) is not None

    def activation_haste_permission(self, permanent: CardState) -> str | None:
        """The permanent granting "activate ... as though it had haste", or None.

        CR 609.4: an "as though" effect applies **only to the stated effect**,
        and the stated effect on Tyvar, Jubilant Brawler and Shang-Chi, Master
        of Kung Fu is activating abilities - so this is consulted by
        `can_activate_tap_ability` (CR 302.6's first sentence, CR 702.10c) and
        by nothing else. `machines/combat.can_attack` deliberately does not
        call it: CR 302.6's second sentence and CR 702.10b are a different
        thing to be treated as true, and this sentence does not state it.

        Read off the printed static lines of everything on the battlefield on
        every call, never cached (CR 604.2, CR 611.3a), the same scan
        `_activation_prohibition` makes for the opposite direction, and gated
        on `_still_has_static_line` so a source that lost its abilities in
        layer 6 grants nothing (CR 613.1f).

        **Whose creatures.** "Creatures you control" - "you" is the *source's*
        controller (CR 109.5), so an opponent's Tyvar reaches nothing of yours.
        The subject has no "other" in it on either printing, which is why
        Shang-Chi may activate its own `{T}` the turn it arrives; the optional
        "other" is still read, because a printing that carries it would
        otherwise be granted a permission it does not print.

        A sentence of this family whose subject this file cannot read is
        recorded as a `LayerNotice` and grants nothing, rather than being
        rounded up to every creature its controller has.
        """
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not _LOOKS_LIKE_HASTE_ACTIVATION_PERMISSION_RE.match(text):
                    continue
                match = _HASTE_ACTIVATION_PERMISSION_RE.match(text)
                if match is None:
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                if self.controller_of(permanent).username != self.controller_of(source).username:
                    continue
                if match.group("other") is not None and permanent.id == source.id:
                    continue
                return source.name
        return None

    def note_cast(
        self,
        spell: CardState,
        *,
        keyword: str | None = None,
        origin_zone: Zone = Zone.HAND,
        face: str | None = None,
        exile_annotation: "ExileAnnotation | None" = None,
        modes: list[int] | None = None,
        mode_targets: list[list[TargetRef]] | None = None,
        x_value: int = 0,
        mana_spent: dict[Color, int] | None = None,
        spend_effects: list[str] | None = None,
        kicked: int = 0,
        additional_cost_cards: list[UUID] | None = None,
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
            origin_zone=origin_zone,
            face=face,
            exile_annotation=exile_annotation,
            modes=list(modes or []),
            mode_targets=[list(slice_) for slice_ in mode_targets or []],
            x_value=x_value,
            mana_spent=dict(mana_spent or {}),
            spend_effects=tuple(spend_effects or ()),
            kicked=kicked,
            additional_cost_cards=list(additional_cost_cards or []),
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
        with self._id_allocator_scope():
            return self._put_on_stack(card_state, controller)

    def _put_on_stack(self, card_state: CardState, controller: str) -> CardState:
        """The rest of `put_on_stack`, run with `_allocate_id` installed - see
        `objects_created`'s own docstring for why that installation is scoped
        to this one call rather than done once for the object's whole life."""
        # CR 400.7: the card is about to become a new object on the stack, so
        # its origin has to be read *now* - `GameEvent.origin_zone` is what
        # Knowledge Pool's "from their hand" and Appa, Steadfast Guardian's
        # "from exile" restrict a CAST_SPELL trigger to (`machines/triggers.
        # _origin_zone_matches`).
        #
        # `card_state.zone` is *not* reliably that answer any more by the
        # time this method runs: `machines/casting.Casting._move_to_the_
        # stack` moves the card onto `game.stack` itself, at CR 601.2a's own
        # "first step" of the announcement, well before `Casting.cast()`
        # calls this method - so for a spell cast the ordinary way,
        # `card_state.zone` already reads `Zone.STACK` here, which is not an
        # origin at all. `Casting.cast()` calls `Game.note_cast` with the
        # real origin before it ever reaches this method (see that method's
        # own `self.origin_zone`), so the `CastRecord` it just wrote is
        # consulted first; `cast_free_from_exile` is the one other caller,
        # ordered the same way for the same reason (its own docstring), so
        # its record is there too. `card_state.zone` is the fallback for a
        # spell that reaches here with no record at all - there is no such
        # path in this engine today, but reading a zone that has not been
        # moved yet is still the right default if one is ever added.
        record = self.cast_records.get(card_state.id)
        origin_zone = record.origin_zone if record is not None else card_state.zone
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
        # CR 202.3e: while this spell is on the stack, an {X} in its cost is
        # the value actually chosen for X, not CR 107.3g's off-stack "X is 0"
        # reading `card_state.card.cmc` gives - `Game.note_cast` (called by
        # `Casting.cast` before this) already has that value on record, the
        # same one CR 107.3m's own X-counters replacement in
        # `machines/replacement.py` reads. Chalice of the Void's "mana value
        # equal to the number of charge counters" needs this real number, not
        # the printed one - see `GameEvent.amount`'s docstring.
        # CR 107.3i: "all instances of X on an object have the same value at
        # any given time" - Walking Ballista's `{X}{X}` is two symbols each
        # worth the one chosen X, so the printed cmc (which already reads
        # both as 0, CR 107.3g) gains `count * x_value`, not just `x_value`.
        mana_value = card_state.card.cmc or 0
        x_count = (card_state.mana_cost or "").count("{X}")
        if x_count:
            mana_value += x_count * self.cast_record(card_state).x_value
        self.emit(
            GameEvent(
                event=TriggerEvent.CAST_SPELL,
                subject_id=card_state.id,
                subject_name=card_state.name,
                subject_controller=controller,
                subject_card=card_state.card,
                subject_types=card_state.types,
                subject_subtypes=card_state.subtypes,
                subject_colors=card_state.colors,
                player=controller,
                amount=int(mana_value),
                origin_zone=origin_zone,
            )
        )
        # CR 117.3c gives priority straight back to the caster, so this is the
        # "next time a player would receive priority" of CR 603.3 - a cast
        # trigger goes on the stack above the spell that caused it.
        self.put_triggers_on_stack()
        return card_state

    def resolve_top(self) -> StackObject:
        """Resolve the top of the stack, recording what is resolving (CR 608.2).

        The object is popped off the stack before its effect runs, so nothing
        downstream could otherwise answer "which object is resolving right
        now?" - and CR 724.1b needs exactly that: "Exile every object on the
        stack, **including the object that's resolving**." `Game.resolving` is
        that answer, live only for the length of one resolution.
        """
        if self.stack_is_empty:
            raise ValueError("the stack is empty")
        self.resolving = self.stack[-1]
        try:
            with self._id_allocator_scope():
                return self._resolve_top()
        finally:
            self.resolving = None

    def _resolve_top(self) -> StackObject:
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
        # CR 107.3a: X is fixed for the whole spell once announced, but only
        # for a spell that actually has `{X}` in its own mana cost - a spell
        # whose text defines its own X some other way (CR 107.3f) gets no
        # substitution at all, which is `effect_for`'s own `x_value=None`
        # default. `spell.mana_cost` already reads the up face of a DFC.
        x_value = self.cast_record(spell).x_value if "{X}" in (spell.mana_cost or "") else None
        effect = effect_for(spell.name, spell.oracle_text, x_value=x_value)
        if effect is not None:
            try:
                effect(self, spell)
            except Exception:
                # CR 400.1: "a zone is a place where objects can be during a
                # game" and every object not outside the game is in exactly
                # one. `spell` was already popped off `self.stack` above, so
                # once it is resolving it has no zone of its own until this
                # function gives it one again - the graveyard placement a few
                # lines down (non-permanent) or `enter_the_battlefield`
                # (permanent). If `effect` raises before reaching either -
                # which is exactly what `Game.ask` does when CR 608.2d refuses
                # a mid-resolution answer, an empty `choose_cards` reply among
                # them - the spell is left popped from the stack and
                # nowhere else: this is the bug reported from game
                # 535264e8458e461d874d0d38f4b1866e, where Malevolent Rumble
                # vanished from every zone and the deck came up 59 of 60.
                #
                # CR 733.1 governs a player's illegal action: "the entire
                # action is reversed and any payments already made are
                # canceled" (already the model `machines/cost.py`'s own
                # `unpay` follows for an aborted payment, citing the same
                # rule). There is no way back onto the stack mid-resolution -
                # CR 608.2 has no such step - so the closest legal landing
                # spot is the one CR 608.2n/307.2/304.2 already mandate as the
                # *last* step of every instant's and sorcery's resolution: its
                # owner's graveyard. A permanent spell that could not finish
                # entering is sent there too, the same place CR 608.3e already
                # sends one whose controller "can't put it onto the
                # battlefield" (Worms of the Earth's own example). Whatever
                # the effect had not yet done when it raised - the revealed
                # cards `malevolent_rumble` had not yet moved off the library,
                # here - simply never happened, which is the fail-closed,
                # nothing-half-applied posture this project's abilities keep
                # everywhere else.
                #
                # The refusal itself is already on record: `Game.ask` appends
                # every `Decision` to `self.decisions.asked` before it
                # validates the answer, so the question that could not be
                # legally answered is not lost even though its effect never
                # ran. This re-raises afterwards rather than swallowing the
                # error, matching the existing convention for every other
                # illegal `Game.ask` answer (`Seasoned Pyromancer`'s own
                # `test_an_illegal_discard_answer_is_refused_without_
                # corrupting_the_hand`) - the caller still learns the answer
                # was refused at the moment it was given; the difference this
                # branch fixes is that the spell no longer disappears while
                # that exception unwinds.
                self.put_into_graveyard(spell, resolving=True)
                self.cast_records.pop(spell.id, None)
                self._before_priority()
                raise

        self._create_resolution_replacements(spell)

        if spell.id in self.turn_ended_exiled_ids:
            # CR 724.1b exiled this spell while it was resolving, and CR 608.2m
            # let it finish resolving anyway ("If an instant spell, sorcery
            # spell, or ability that can legally resolve leaves the stack once
            # it starts to resolve, it will continue to resolve fully"). It has
            # already been given a zone, so neither of the two placements below
            # applies - it does not reach a graveyard and it does not enter the
            # battlefield.
            self.turn_ended_exiled_ids.discard(spell.id)
            self.cast_records.pop(spell.id, None)
            self._before_priority()
            return spell

        if spell.is_permanent:
            # CR 608.3, 608.3a: a resolving permanent spell "becomes a permanent
            # and enters the battlefield under the control of the spell's
            # controller". It was cast, so Containment Priest does not catch it.
            if spell.is_copy:
                # CR 707.10f: "Some effects copy a permanent spell. As that
                # copy resolves, it ceases being a copy of a spell and becomes
                # a token permanent." CR 111.13 says the same from the token
                # side - "A copy of a permanent spell becomes a token as it
                # resolves. The token has the characteristics of the spell
                # that became that token. The token is not 'created' for the
                # purposes of any replacement effect" - and CR 608.3f is the
                # resolution step itself. `CardState.token` is the flag
                # `models/token.is_token` and CR 111.7's state-based action
                # both read; setting it here, rather than at `copy_spell`, is
                # what "as that copy resolves" means: while it is still a
                # spell on the stack it is a copy of a spell, not a token.
                # Nothing is "created", so no token-creation replacement
                # effect (Doubling Season) applies - which is exactly why this
                # sets the flag directly instead of routing through
                # `models/token.create_tokens`.
                spell.token = True
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
            self._apply_mana_spend_effects(spell)
            self._create_resolution_delayed_triggers(spell)
            # Deliberately *not* popped here, unlike the graveyard-bound branch
            # below. CR 608.2a rechecks a triggered ability's intervening *if*
            # again as it resolves, and an "enters, if [mana] was spent to cast
            # it" ability (Wistfulness) is only created *now* - it has not
            # resolved yet, and will not until a later priority round, by which
            # time this permanent is long past `enter_the_battlefield`. Popping
            # the record here left that later recheck reading `CastRecord()`'s
            # empty default (`cast_record`'s own fallback) - "no mana was
            # spent" - and the ability silently did nothing on every resolution
            # even though it had correctly gone on the stack in the first
            # place (`test_wistfulness_paid_with_double_blue_draws_two_then_
            # discards_one` is the regression test). The record is keyed by
            # `spell.id`, which never changes while this incarnation persists
            # (CR 400.7), so it stays correct for as long as the permanent
            # does; a later recast of the same physical card after it leaves
            # and returns overwrites it with a fresh record before this one
            # could ever be misread as belonging to that new cast.
        else:
            # CR 614.1: the move to the graveyard is an event like any other, so
            # it goes through the replacement effects. That is the hook
            # CR 702.34a's flashback exile, CR 715.3d's Adventure exile, and
            # CR 702.88a's rebound exile all hang off - each replaces where the
            # card goes as it leaves the stack.
            #
            # Rebound's own delayed trigger (CR 702.88a's "at the beginning of
            # your next upkeep") is created here rather than inside the
            # replacement effect itself: `_create_rebound_delayed_trigger`
            # needs to know whether the spell was cast from hand, and that is
            # `Game.cast_records[spell.id]` - which is popped two lines below,
            # so it has to be read before `put_into_graveyard` runs, not after.
            #
            # Popped here, unlike the permanent branch above: a non-permanent
            # spell's own "when you cast this" trigger (if any) sits *above* it
            # on the stack and has already resolved by the time control
            # reaches this branch (CR 603.3), and nothing else this engine
            # builds watches a graveyard-bound spell's own cast facts once it
            # is there - so there is no later recheck this needs to survive
            # for, and leaving it around risks nothing but also gains nothing.
            cast_from_hand = self.cast_record(spell).origin_zone is Zone.HAND
            self.put_into_graveyard(spell, resolving=True)
            self._create_rebound_delayed_trigger(spell, cast_from_hand)
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

        `trigger.id` is re-minted here rather than trusted from the caller:
        `DelayedTrigger.id`'s `default_factory=new_id` runs the moment the
        caller constructs it, which for `DelayedTrigger(text=..., ...)`
        written as this call's own argument is *before* the line below ever
        opens `_id_allocator_scope` - Python builds the argument first. A
        caller already inside another scope (`machines/effects.py`, mid-
        resolution) gets an id from that outer scope either way; one with
        none open - most of `tests/scenarios/`'s own direct `Game.
        create_delayed_trigger` calls - minted a bare `uuid4()` that survived
        nowhere else, so overwriting it here is free: nothing has read or
        stored the pre-mint id yet.
        """
        with self._id_allocator_scope():
            trigger = trigger.model_copy(update={"id": self._allocate_id()})
            return self.delayed_triggers.create(trigger)

    def create_reflexive_trigger(
        self,
        *,
        text: str,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        callback: DelayedEffectSpec,
    ) -> AbilityOnStack:
        """Create a reflexive triggered ability (CR 603.12) and queue it for
        the stack.

        `machines/effects.py`'s "you may sacrifice ... When you do, ..."
        clause is the way in: called only once the action it reflects has
        actually happened (Grist, the Hunger Tide's sacrifice), which is what
        lets `DelayedTriggers.create_reflexive` treat CR 603.12's "checked
        immediately after being created" as already satisfied rather than
        something to watch for.

        Appending straight to `pending_triggers` - the same queue `emit`
        fills for every ordinary trigger - is what makes `put_triggers_on_
        stack` pick this up the next time a player would receive priority
        (CR 603.3), asking its own targets then rather than now (CR 603.3d),
        and giving opponents a real stack object to respond to (CR 405.6a).
        """
        with self._id_allocator_scope():
            ability = self.delayed_triggers.create_reflexive(
                text=text,
                controller=controller,
                source_id=source_id,
                source_name=source_name,
                callback=callback,
            )
            self.pending_triggers.append(ability)
            return ability

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
                    effect=ExileWarped(),
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
            self._grant_dash_haste(spell)
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
                    effect=return_subject_to_hand,
                )
            )

    def _grant_dash_haste(self, permanent: CardState) -> None:
        """The third of CR 702.109a's three abilities: haste for a dashed permanent.

        "Dash represents three abilities: two static abilities that function
        while the card with dash is on the stack, one of which may create a
        delayed triggered ability, and a static ability that functions while
        the card with dash is on the battlefield" - the battlefield one is the
        haste grant, and it holds for as long as the dash cost was paid, which
        is for as long as this object is this object.

        No new fact is needed to know that: `Game.cast_records` survives a
        permanent spell's resolution (the record is deliberately not popped in
        `resolve_top`'s permanent branch), so `was_cast_with(spell, "Dash")` -
        which the delayed return-to-hand trigger beside this already asks - is
        the whole condition.

        Granting an ability is layer 6 (CR 613.1f: "Layer 6: Ability-adding
        effects, keyword counters, ability-removing effects, and effects that
        say an object can't have an ability are applied"), and haste is a
        static ability (CR 702.10a), so this is a plain `Layer.ABILITY`
        continuous effect - built the same way `machines/casting.
        grant_suspend_haste` builds suspend's, with its own description rather
        than through that function, since the description names the rule it
        comes from and this one is CR 702.109a's, not CR 702.62a's.

        `only_this_incarnation` scopes it to the exact object that just entered
        (CR 400.7 makes a permanent that leaves and returns a new object), so a
        Ragavan bounced by dash's own end-step trigger and recast for its mana
        cost does not inherit haste from the turn it was dashed.
        """
        store = self.continuous_effects
        store.add(
            ContinuousEffect(
                description=f"{permanent.name}: dash grants haste (CR 702.109a)",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                modification=grant_ability("Haste"),
            ),
            self,
        )

    def _create_rebound_delayed_trigger(self, spell: CardState, cast_from_hand: bool) -> None:
        """CR 702.88a's own delayed trigger: "At the beginning of your next
        upkeep, you may cast this card from exile without paying its mana
        cost."

        Created only once `put_into_graveyard` has already redirected this
        exact spell into exile because of its own rebound replacement
        (`machines/replacement._stack_replacements`) - not merely because the
        card happens to print the keyword. A card cast from anywhere but hand
        never gets that redirect (CR 702.88a's own "if this spell was cast
        from your hand"), which `cast_from_hand` - read by the caller from
        `Game.cast_records` *before* `resolve_top` pops it - is what decides;
        checking `spell.zone` here as well catches the case where the card
        has rebound printed but a *different* replacement effect sent it
        somewhere other than exile first (CR 616.1: only one effect can
        finally decide where an object goes).
        """
        if not cast_from_hand or not has_rebound(spell.card) or spell.zone is not Zone.EXILE:
            return
        controller = spell.controller or self.active_player.username
        self.delayed_triggers.create(
            DelayedTrigger(
                text=(
                    "At the beginning of your next upkeep, you may cast "
                    "this card from exile without paying its mana cost."
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.UPKEEP,
                # CR 702.88a says "your next upkeep", not "the next upkeep" -
                # Emrakul's own extra-turn trigger is the precedent for
                # `only_when_active` scoping a delayed trigger to one
                # player's turns. Without it, this one-shot trigger
                # (CR 603.7b) would spend itself on the *other* player's
                # upkeep if that happens to come first, and never fire again.
                only_when_active=controller,
                controller=controller,
                source_id=spell.id,
                source_name=spell.name,
                subject_id=spell.id,
                expected_zone=Zone.EXILE,  # CR 603.7c
                expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                effect=rebound_recast,
            )
        )

    def cast_free_from_exile(
        self, card: CardState, controller: str, *, keyword: str | None = None
    ) -> CardState | None:
        """CR 702.88a/b: cast `card` straight out of exile, choosing new
        targets (CR 601.2c) and paying no mana cost (CR 118.9's alternative
        cost, via CR 702.88b's "follows the rules for paying alternative
        costs").

        This is not the interactive `machines/casting.Casting` state machine -
        there is no live announcement to drive from inside a resolving
        ability's effect function, only the same "ask the resolving object's
        controller" pattern `_ask_trigger_targets` already uses for a
        triggered ability's own CR 603.3d target announcement. If the card
        needs a target and none is legal, CR 601.2c makes casting it illegal
        in the first place, so nothing is put on the stack at all - `None` is
        returned exactly the way `_ask_trigger_targets` returns no targets for
        "nothing satisfies the restriction" rather than casting the spell
        anyway with an empty target list.

        `Game.note_cast` records `origin_zone=Zone.EXILE` so a card that
        rebounds *again* by some other effect's rebound (there is only one in
        the pool, but the record does not know that) is never mistaken for
        one cast from hand a second time. Called **before** `put_on_stack`,
        not after: that method reads the `CastRecord` this call writes to
        learn the cast's real origin for its own `GameEvent.origin_zone`
        (CR 400.7 - the card is already a stack object by the time `put_on_
        stack` could otherwise ask `card.zone`, which is why it cannot simply
        read the zone itself here the way it does for a plain hand-cast). A
        free cast this method makes is from exile, never from hand, and
        `Knowledge Pool`'s and `Possibility Storm`'s own "casts a spell from
        their hand" trigger reads exactly this to avoid re-triggering on the
        free cast it itself granted.

        `keyword` is `CastRecord.keyword` - CR 601.2b's own "the player
        announces ... any keyword actions". `None` by default, because most
        of this method's callers cast under no keyword at all: Fight
        Rigging's hideaway free cast (CR 702.75a) and Isochron Scepter's
        copy-and-cast (CR 707.10) are alternative-cost casts granted by a
        printed ability, not a keyword action, and Knowledge Pool's and
        Possibility Storm's own free casts (CR 118.9's alternative cost, read
        off the card's own "without paying its mana cost" text) are the same
        shape - no keyword names any of them. Only `_create_rebound_delayed_
        trigger`'s callback actually rebounds (CR 702.88a), and passes
        `keyword="Rebound"` itself; every other call site used to get that
        same label unconditionally, which mislabelled a hideaway or
        Isochron-copy cast's `CastRecord` as a rebound it never was.
        """
        with self._id_allocator_scope():
            profile = profile_for_text(card.oracle_text or "")
            targets: list[TargetRef] = []
            if profile.requirements:
                candidates = self._legal_target_candidates(profile, controller, card.id)
                if not candidates:
                    return None  # CR 601.2c: no legal target, casting is illegal.
                decision = Decision(
                    kind=DecisionKind.CHOOSE_TARGETS,
                    player=controller,
                    prompt=f"choose targets for {card.name}",
                    source=card.name,
                    targets=tuple(TargetRef.coerce(candidate) for candidate in candidates),
                    target_maximum=profile.max_targets,
                    # CR 601.2c: mandatory, capped at how many legal targets
                    # actually exist (`candidates` is truthy here, but may still
                    # be fewer than the printed requirement asks for).
                    target_minimum=min(profile.min_targets, len(candidates)),
                )
                chosen = self.ask(decision)
                assert isinstance(chosen, (list, tuple))
                targets = list(chosen)
            card.targets = targets
            self.note_cast(card, keyword=keyword, origin_zone=Zone.EXILE)
            self.put_on_stack(card, controller)
            return card

    def has_legal_free_cast(self, card: CardState, controller: str) -> bool:
        """Whether `cast_free_from_exile(card, controller)` would actually
        cast something, without doing it.

        Two independent ways a nominally-legal-looking free cast is not
        actually one, both checked here rather than discovered by trying and
        failing:

        - **CR 611.1** - a flat prohibition ("Your opponents can't cast
          noncreature spells this turn", Grafdigger's Cage's graveyard/library
          ban) holds at any timing. `machines.keywords.cascade` already checks
          this for its own free cast (`why_cannot_cast_restriction`); this
          reuses the same function rather than a second copy of the same
          check.
        - **CR 601.2c** - casting a targeted spell is illegal when nothing
          satisfies its restriction, which `cast_free_from_exile` itself only
          discovers by asking for targets and getting none back, returning
          `None` afterwards.

        An ability offering a *choice* among several exiled cards - Knowledge
        Pool's own free cast - needs to know this **before** asking, so an
        uncastable card can be left off the menu (CR 608.2d: "the player
        can't choose an option that's illegal or impossible") instead of
        being offered, chosen, and only then discovered to do nothing.
        """
        if why_cannot_cast_restriction(card, controller, self) is not None:
            return False
        profile = profile_for_text(card.oracle_text or "")
        if not profile.requirements:
            return True
        return bool(self._legal_target_candidates(profile, controller, card.id))

    def copy_spell(self, spell: CardState, controller: str | None = None) -> CardState:
        """CR 707.10: put a copy of `spell` onto the stack.

        "To copy a spell ... means to put a copy of it onto the stack; a copy
        of a spell isn't cast." Unlike `cast_free_from_exile`, this does not
        go through `put_on_stack` at all - that method's own CAST_SPELL emit
        is exactly the event CR 707.10 says does *not* happen for a copy, and
        `spells_cast_this_turn` (Alania's own "the first instant spell ...
        you've cast this turn" reads it) must not count a copy as a cast
        either.

        CR 707.2: the copy acquires the original's copiable values - built
        around the same `Card`, since `machines/effects.py` has no
        modification to apply here - "and, for an object on the stack,
        choices made when casting or activating it (mode, targets, the value
        of X, ...)"; `targets` is carried over verbatim, and a caller wanting
        CR 707.10c's "new targets" permission chooses them afterward the same
        way `cast_free_from_exile` lets a resolving ability choose targets
        for what it casts. `division` (CR 601.2d's damage split) travels too,
        being a simple scalar copiable value; `x_value` lives on `Game.
        cast_record`, keyed by the *original* spell's own id, and `modes`/
        `mode_targets` live on `CastRecord` too - neither is copied here, so
        a copy of an `{X}` spell or a modal spell is not yet modelled (see
        `docs/engine-coverage.md`). Nothing in the pool copies either.

        The copy is controlled by `controller` if given, or by the original
        spell's own controller otherwise - who controls a copy is CR 707.10b's
        business and this wave could not confirm its exact wording in this
        session (`docs/engine-coverage.md` records the gap), so the fallback
        picked here is the one no card in the pool exercises differently:
        Alania, Divergent Storm's own copy names no controller of its own.

        CR 707.10f/111.13: a copy of a *permanent* spell becomes a token as
        it resolves (`token=True`, set below in `_resolve_top_impl` once it
        does), so the object it becomes has to already be a `TokenState` -
        `token` alone is not enough. `TokenState.move_to`'s CR 111.8 override
        ("a token that has left the battlefield can't move ... back onto the
        battlefield") and its `left_the_battlefield` bookkeeping only exist
        on that subclass; a plain `CardState` with `token` flipped true reads
        as a token everywhere `models/token.is_token` is asked, but a second
        zone change through it never sees CR 111.8 refuse it, and a decode
        of it - which reads the same `token` flag - builds a real
        `TokenState` where the live game never had one, so the two disagree
        about a rule the live game was silently missing all along (T10's own
        finding). Built `token=False` here regardless, matching the existing
        comment at the resolution site: while still a copy of a spell on the
        stack it is not yet a token (CR 707.10f's "as that copy resolves").
        A copy of a non-permanent spell (an instant or sorcery) never becomes
        a token at all, so it stays a plain `CardState`.
        """
        with self._id_allocator_scope():
            controller = controller or spell.controller or self.controller_of(spell).username
            state_type = TokenState if spell.is_permanent else CardState
            copy = state_type(
                card=spell.card,
                zone=Zone.STACK,
                controller=controller,
                owner=spell.owner,
                is_copy=True,
                token=False,
                targets=list(spell.targets),
                face_played=spell.face_played,
                land_face_played=spell.land_face_played,
                division=spell.division,
            )
            self.stack.append(copy)
            return copy

    def offer_new_targets_for_copy(
        self, copy: CardState, controller: str, *, source_name: str = ""
    ) -> None:
        """CR 707.10c-shaped permission: "you may choose new targets for the
        copy" (Alania, Divergent Storm being the only printing in the pool).

        A plain `MAY` (CR 608.2d), then the same `CHOOSE_TARGETS` question
        `cast_free_from_exile` asks - reusing `_legal_target_candidates`
        rather than a second target-legality reader. Declining, or a
        restriction this session's targeting reader cannot parse at all,
        leaves the copy with whatever it already had (CR 707.2's copied
        targets), never with none chosen instead - "new targets" is an
        option to replace them, not a second, separate targeting event that
        could come back empty.
        """
        profile = profile_for_text(copy.oracle_text or "")
        if not profile.understood or not profile.requirements:
            return
        candidates = self._legal_target_candidates(profile, controller, copy.id)
        if not candidates:
            return
        if not self.may(
            self.player(controller), "choose new targets for the copy", source=source_name
        ):
            return
        decision = Decision(
            kind=DecisionKind.CHOOSE_TARGETS,
            player=controller,
            prompt=f"choose new targets for the copy of {copy.name}",
            source=source_name,
            targets=tuple(TargetRef.coerce(candidate) for candidate in candidates),
            target_maximum=profile.max_targets,
            # Deliberately 0, not `profile.min_targets`: CR 707.10c is "you may
            # choose new targets for the copy. If you choose to change one or
            # more of the targets, follow the rules ... in rule 601.2c-601.2d"
            # - the mandatory floor only binds *after* a target is actually
            # being changed. Choosing to change none, having already said
            # `may` above, is still a legal outcome (the copy keeps CR 707.2's
            # copied targets), not the `may`'s own decline read twice.
        )
        chosen = self.ask(decision)
        assert isinstance(chosen, (list, tuple))
        if chosen:
            copy.targets = list(chosen)

    #: How many triggered mana abilities may resolve inline, back to back, off
    #: one activation before the engine calls it a CR 104.4b loop. There is no
    #: printing in the pool that legitimately chains more than a handful, and a
    #: real loop is unbounded, so any bound well clear of the honest cases
    #: separates the two. See `resolve_triggered_mana_abilities`.
    TRIGGERED_MANA_ABILITY_LOOP_BOUND: ClassVar[int] = 64

    def resolve_triggered_mana_abilities(self, triggered: Sequence[AbilityOnStack]) -> None:
        """Resolve CR 605.1b's triggered mana abilities inline (CR 605.4a).

        CR 605.1b: "A triggered ability is a mana ability if it meets all of the
        following criteria: it doesn't require a target (see rule 115.6), it
        triggers from the activation or resolution of an activated mana ability
        ...". CR 605.4a then keeps it off the stack: it "resolves immediately
        after the mana ability that triggered it, without waiting for priority".

        Everything handed here already triggered off `ExtraTriggerEvent.
        MANA_ADDED`, which is raised only by a mana ability resolving, so the
        remaining criteria are the two checked below: no target, and an effect
        that could add mana.

        Each resolution that actually puts mana in the pool re-raises the same
        event from the same source, because a triggered mana ability's own
        "add" is itself something causing a player to add mana - which is what
        makes DDR#990's Caged Sun-under-Toph loop a loop at all.

        **CR 104.4b** is the bound: "If a game that's not using the limited
        range of influence option (including a two-player game) somehow enters
        a 'loop' of mandatory actions, repeating a sequence of events with no
        way to stop, the game is a draw." Past
        `TRIGGERED_MANA_ABILITY_LOOP_BOUND` consecutive inline resolutions off
        one activation, `Game.drawn` is set and the chain stops.
        """
        pending = list(triggered)
        resolved = 0
        while pending:
            ability = pending.pop(0)
            if ability not in self.pending_triggers:
                continue
            printed = ability.ability
            if not isinstance(printed, TriggeredAbility):
                continue
            if ability.targets or not printed.effect.lower().strip().startswith("add "):
                continue  # CR 605.5: not a mana ability.
            if resolved >= self.TRIGGERED_MANA_ABILITY_LOOP_BOUND:
                # CR 104.4b. See `Game.drawn`'s own docstring for what this
                # detection does and does not cover.
                self.drawn = True
                return
            self.pending_triggers.remove(ability)
            source = ability.source(self)
            before = dict(self.player(ability.controller).mana_pool.floating)
            self._resolve_ability(ability)
            resolved += 1
            after = self.player(ability.controller).mana_pool.floating
            added = [
                color
                for color, count in after.items()
                for _ in range(count - before.get(color, 0))
                if count > before.get(color, 0)
            ]
            if added and source is not None:
                pending.extend(self.emit(mana_added_event(source, self, mana_added=added)))

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

        Some of `machines/effects.py`'s ability effects apply one clause of
        their printed text unconditionally (Fight Rigging's own +1/+1 counter,
        Cori-Steel Cutter's own token, Tyvar's and Six's own mill) and only
        *then* ask a later CR 608.2d question about an optional clause that
        follows it (the free cast, the attach, the return, the pick from among
        the milled cards). That earlier mutation is not something to reverse
        if the later question can't be legally answered and `Game.ask` raises
        - CR 733.1's reversal is for an action that "can't legally complete",
        and the first clause already did, in full, exactly as printed
        (CR 608.2c's textual order). What was not guaranteed before this fix
        is the bookkeeping below: `discard` and `_before_priority` never ran
        if `effect` raised, the same gap `Game.resolve_top` had for a spell's
        own final-resolution step before it started catching and re-raising.
        Left alone here, an ability that got that far - counter or token or
        milled cards already real - would leave the stack with CR 608.2n's own
        "ceases to exist" bookkeeping undone and CR 704.3's state-based-action
        check skipped before whatever comes next, which is its own kind of
        half-applied state even though no zone placement needs reversing.
        """
        try:
            if self.spell_fizzles(ability):
                self.fizzled.append(ability.id)
            elif self._intervening_if_still_true(ability):
                delayed = self.delayed_triggers.trigger_for(ability)
                if delayed is not None:
                    # CR 603.7: a delayed triggered ability's effect is not
                    # printed anywhere, so it comes from `machines/delayed.py`
                    # rather than from the registry keyed on the source
                    # card's text.
                    run = self.delayed_triggers.effect_for(ability)
                    if run is not None:
                        run(self, ability, delayed)
                else:
                    effect = self._effect_of(ability)
                    if effect is not None:
                        effect(self, ability)
        except Exception:
            self.delayed_triggers.discard(ability)  # CR 608.2n: it ceases to exist
            self._before_priority()
            raise

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
        if isinstance(ability.ability, TriggeredAbility):
            # `event` may be None, and that is not "no effect": CR 603.8's
            # state triggers ("Some triggered abilities trigger when a game
            # state ... is true, rather than triggering when an event occurs")
            # have no `TriggerEvent` to name, and neither does a condition the
            # parser reads without matching one of the enumerated events -
            # Caged Sun's "Whenever a land's ability causes you to add one or
            # more mana of the chosen color". `trigger_effect_for` takes
            # `TriggerEvent | None` and keys such a row on the condition text,
            # so gating on the event here was refusing to look the effect up
            # at all.
            return trigger_effect_for(
                ability.source_name, ability.ability.event, ability.ability.effect
            )
        if isinstance(ability.ability, ActivatedAbility):
            if ability.ability.class_level_target is not None:
                # CR 716.2a's own mechanical half - "This Class's level
                # becomes N" - generalised off the level bar itself rather
                # than a card-name-keyed row, so any Class works the same way.
                target = ability.ability.class_level_target

                def become_level(game: "Game", stack_object: "AbilityOnStack") -> None:
                    permanent = stack_object.source(game)
                    if permanent is not None:
                        permanent.class_level = target

                return become_level
            index = self._activated_index(ability)
            if index is not None:
                # CR 107.3a's X, only when the printed cost actually carries
                # one (Fiend Artisan's `{X}{B/G}`) - the same "only if {X} is
                # in the mana cost" gate `resolve_top` uses for a spell's own
                # `x_value`, so an ordinary ability's bare "X" in its rules
                # text (CR 107.3f) is never mistaken for this one.
                x_value = ability.x_value if "{X}" in ability.ability.cost else None
                return activated_effect_for(
                    ability.source_name, index, ability.ability.effect, x_value=x_value
                )
        return None

    def _activated_index(self, ability: AbilityOnStack) -> int | None:
        source = ability.source(self)
        if source is None or source.card is None:
            return None
        # `self.activated_abilities` now, not `activated_abilities_of` on the
        # bare card directly - it is the one place printed and
        # `CardState.granted_ability_texts` abilities are already combined
        # (Urza's Saga chapter II's own granted token-making ability), and
        # this index has to agree with that same combined, ordered list or a
        # granted ability's index would disagree with the one `activate_
        # ability` used to put it on the stack in the first place.
        for index, printed in enumerate(self.activated_abilities(source)):
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
        # CR 712.8f, 603.10: judged by the face that's actually up on the
        # battlefield (`CardState.types`/`.subtypes`, land-face aware), not
        # `permanent.card.types`'s front-face-only read - a Witch-Blessed
        # Meadow entering as a land is not a creature entering.
        #
        # CR 613.5 then has the layer system "continually and automatically"
        # applied, so the types and subtypes a trigger condition is judged
        # against are the *computed* ones, not the printed ones - exactly the
        # read `tapped_for_mana_event` and `mana_added_event` already document.
        # A Forest entering under Dryad of the Ilysian Grove ("Lands you
        # control are every basic land type in addition to their other types",
        # layer 4, CR 613.1d) really is a Mountain entering, which is what
        # Valakut, the Molten Pinnacle's "Whenever a Mountain you control
        # enters" has to see. `enter_the_battlefield` has already appended the
        # permanent and stamped its effects (CR 613.7a) before emitting this,
        # so the computed board is the post-entry one CR 603.10 asks about.
        types, subtypes = permanent.types, permanent.subtypes
        if permanent.zone is Zone.BATTLEFIELD:
            characteristics = self.characteristics_of(permanent)
            types, subtypes = characteristics.types, characteristics.subtypes
        return GameEvent(
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
            subject_id=permanent.id,
            subject_name=permanent.name,
            subject_controller=permanent.controller,
            subject_card=permanent.card,
            subject_types=types,
            subject_subtypes=subtypes,
            player=permanent.controller,
        )

    def _emit_lore_counters_added(self, card_state: CardState, added: int) -> None:
        """CR 107.15a: a chapter ability triggers "when one or more lore
        counters are put onto this Saga" - CR 122.6 makes that true both for
        counters put on while already on the battlefield (`add_counters`) and
        for CR 714.3a's own intrinsic first one, put on as the Saga enters
        (`enter_the_battlefield`). Both routes call this with `added` set to
        how many just went on, and `machines/triggers.condition_matches`
        works out which of the Saga's own `TriggeredAbility.chapter`
        thresholds that crossed from the total already on it.
        """
        if added <= 0 or not card_state.is_saga or card_state.zone is not Zone.BATTLEFIELD:
            return
        self.emit(
            GameEvent(
                event=TriggerEvent.LORE_COUNTERS_ADDED,
                subject_id=card_state.id,
                subject_name=card_state.name,
                subject_controller=card_state.controller,
                subject_card=card_state.card,
                player=card_state.controller,
                amount=added,
            )
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
        with self._id_allocator_scope():
            sources: list[CardState] = list(self.battlefield)
            # CR 113.6m: "An ability whose cost or effect specifies that it moves
            # the object it's on out of a particular zone functions only in that
            # zone" - Arclight Phoenix's "At the beginning of combat on your turn,
            # ... return this card from your graveyard to the battlefield" is one,
            # and a graveyard card was never asked about any event at all, so it
            # could not fire. Every card in every graveyard is offered here and
            # `machines/triggers.triggers_for` filters on
            # `zones_ability_functions_in`, which still answers "battlefield" for
            # everything that has not earned otherwise - so this widens what is
            # *asked*, never what triggers.
            for player in self.players:
                sources.extend(player.graveyard)
            # CR 702.62a: "The second and third [suspend abilities] are
            # triggered abilities that function in the exile zone." Nothing in
            # exile was ever offered here, so a suspended card was never asked
            # about `TriggerEvent.BEGINNING_OF_STEP` and its time counters
            # only ever came off when a caller removed one by hand.
            #
            # Deliberately *not* the whole exile pile the way the graveyards
            # above are. Exile is one shared zone (`Game.shared_zones`) holding
            # every foretold, plotted, madness-discarded, cascaded and
            # hidden-away card in the game, and offering all of them would ask
            # each about every event that ever happens. CR 702.62b's own
            # three-clause definition of "suspended" - "in the exile zone, has
            # suspend, and has a time counter on it", which is exactly
            # `CardState.is_suspended` - is the filter, so the widening stays
            # the size of the rule that needed it.
            sources.extend(card for card in self.exile if card.is_suspended)
            if event.event is TriggerEvent.CAST_SPELL:
                sources = self.spells_on_stack + sources
            elif (
                event.event
                in (
                    TriggerEvent.DIES,
                    TriggerEvent.IS_SACRIFICED,
                    TriggerEvent.SPELL_IS_COUNTERED,
                    TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
                    TriggerEvent.LEAVES_THE_BATTLEFIELD,
                    # CR 702.62a's third ability, "When the last time counter
                    # is removed from this card": by the time the event is
                    # raised the card has no time counters left, so CR
                    # 702.62b no longer calls it suspended and the widening
                    # above has already stopped offering it. The card is
                    # named as the event's own subject and asked here for the
                    # same reason the four departures above are - the state
                    # the condition is about is the state it was in a moment
                    # ago.
                    ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED,
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
            # CR 603.8: a state trigger watches a game state, not an event, so it
            # is swept for after every event rather than matched against one. This
            # is what lets a countered state trigger fire again immediately - the
            # counter event is emitted from `Game.counter` after the ability has
            # already been removed from the stack (CR 701.6a).
            triggered = triggered + state_triggers_for(self)
            self.pending_triggers.extend(triggered)
            return triggered

    def put_triggers_on_stack(self) -> list[AbilityOnStack]:
        """Put everything that has triggered onto the stack (CR 603.3, 603.3b).

        CR 603.3b orders them: "each player, in APNAP order, puts each triggered
        ability they control on the stack in any order they choose". The active
        player goes first, so the active player's trigger sits *lowest* and
        resolves *last*. Within one player's abilities the order is that
        player's own choice, put to them by `_order_triggers_by_controller`
        through `machines/decisions.ask_trigger_order`; an unscripted, unasked
        player keeps the order they triggered in, which is what makes a
        scenario reproducible.

        This is the only path in the engine that puts more than one object on
        the stack at once. Every other stack append - a cast spell, an
        activated ability, a single `copy_spell` - is one object, so CR 405.3
        ("if an effect puts two or more objects on the stack at the same time,
        those controlled by the active player are put on lowest, followed by
        each other player's objects in APNAP order") is honoured here, by
        `machines/triggers.apnap_order`, or nowhere - because there is nowhere
        else it applies.

        Targets are chosen here, not when the ability triggered (CR 603.3d).

        A `choose_trigger_targets` answer is consumed by this one batch and no
        other: it is thrown away once every waiting ability has had its turn,
        so a later, separate trigger sharing the same source name (a second
        cast of the same card, or an unrelated delayed trigger printed on the
        same card) is asked fresh rather than inheriting a stale answer.

        Putting an ability on the stack can itself trigger something: CR 115.1c
        makes a targeted ability's targets chosen as it goes on the stack, and
        anything watching "becomes the target of ... an ability" (ward,
        CR 702.21a; Loki, God of Mischief) triggers on that. CR 603.3 puts
        *those* on the stack "the next time a player would receive priority" -
        which has still not happened, since this whole batch runs before
        anybody gets priority - so this drains repeatedly rather than leaving
        them for a later call that a scenario may never make.
        """
        with self._id_allocator_scope():
            placed: list[AbilityOnStack] = []
            # CR 603.8 / CR 704.1a: a state trigger is a triggered ability whose
            # condition is a game state, so it is swept for here too - a state that
            # became true while an ability was resolving (or that was true before
            # anything ever happened, so no event was emitted to sweep on) has still
            # triggered, and CR 603.3 puts it on the stack at this same moment.
            self.pending_triggers.extend(state_triggers_for(self))
            while self.pending_triggers:
                placed.extend(self._put_pending_triggers_on_stack())
                self.pending_triggers.extend(state_triggers_for(self))
            return placed

    def _put_pending_triggers_on_stack(self) -> list[AbilityOnStack]:
        """One CR 603.3b batch: everything waiting right now, in APNAP order."""
        if not self.pending_triggers:
            return []
        assert self.turn is not None

        waiting, self.pending_triggers = self.pending_triggers, []
        waiting = [item for item in waiting if self.is_in_game(item.controller)]  # CR 800.4d
        ordered = self._order_triggers_by_controller(
            apnap_order(waiting, self._turn_order_from_active())
        )
        placed: list[AbilityOnStack] = []
        for ability in ordered:
            targets = self._targets_for_trigger(ability)
            if targets is None:
                # CR 603.3d: "if a choice is required when the triggered
                # ability goes on the stack but no legal choices can be made
                # for it, ... the ability is simply removed from the stack" -
                # for a mandatory target (`target_minimum` > 0) with no legal
                # candidate at all, that means it never goes on in the first
                # place, not that it goes on choosing nothing.
                continue
            ability.targets = list(targets)
            self.stack.append(ability)
            self._emit_ability_becomes_target(ability)
            placed.append(ability)
        for ability in ordered:
            self.trigger_targets.pop(ability.source_name, None)
            self.trigger_targets.pop(ability.source_name.split("//")[0].strip(), None)
        return placed

    def _order_triggers_by_controller(self, ordered: list[AbilityOnStack]) -> list[AbilityOnStack]:
        """CR 603.3b's second half: each controller orders their own block.

        "First, each player, in APNAP order, puts each triggered ability they
        control on the stack in any order they choose." `apnap_order` settles
        which player's block goes on first and no more than that - within one
        block the order is the player's, and until this existed it was the
        order the abilities happened to trigger in, which nobody was asked
        about.

        `apnap_order` is a stable sort by seat, so one controller's abilities
        are already contiguous; each run is handed to `ask_trigger_order` and
        re-laid in the answer, bottom of the stack first. A block of one is not
        a choice and `ask_trigger_order` does not ask about it; an unscripted
        block of several keeps the order it triggered in, which is what
        `default_answer` returns, so nothing moves unless a caller says so.
        """
        result: list[AbilityOnStack] = []
        index = 0
        while index < len(ordered):
            stop = index
            while stop < len(ordered) and ordered[stop].controller == ordered[index].controller:
                stop += 1
            block = ordered[index:stop]
            index = stop
            if len(block) < 2:
                result.extend(block)
                continue
            by_id = {ability.id: ability for ability in block}
            chosen = ask_trigger_order(
                self.decisions,
                block[0].controller,
                tuple((ability.id, ability.source_name) for ability in block),
                # Two copies of one card is the ordinary case for this
                # question, so the source name alone does not distinguish the
                # options - the ability's own text does. Nothing downstream can
                # recover it: CR 603.3b is asked one step before CR 603.3 puts
                # these on the stack, so at this moment they are in no zone at
                # all and this frame is the only thing still holding them.
                ability_texts=tuple(ability.ability.text for ability in block),
            )
            result.extend(by_id[ability_id] for ability_id in chosen)
        return result

    def _emit_ability_becomes_target(self, ability: AbilityOnStack) -> None:
        """The objects this ability targeted have become targets (CR 115.1).

        "Some spells and abilities require their controller to choose one or
        more targets for them ... These targets are declared as part of the
        process of putting the spell or ability on the stack." CR 115.1c is the
        activated half ("An activated ability is targeted if it identifies
        something it will affect by using the phrase 'target [something]'") and
        CR 603.3d the triggered half, and both land here: `machines/casting.
        Casting._emit_becomes_target` is the spell-only twin of this, and
        nothing raised the event for an ability's targets at all, so ward
        (CR 702.21a) never saw an activated ability coming and Loki, God of
        Mischief's "becomes the target of an ability you control" could not
        fire.

        Raised once the ability is already on the stack, for two reasons: the
        targets are settled at that point (CR 602.2b imports CR 601.2c
        wholesale for an activated ability), and `machines/triggers.
        _becomes_target_names_ability` tells an ability apart from a spell by
        looking `targeted_by` up among `Game.abilities_on_stack` - an id that
        is not there yet reads as a spell.

        Only permanents are asked. CR 110.1: "A permanent is a card or token on
        the battlefield", so an object anywhere else is not one - the same
        filter the spell twin applies, since every condition in this pool is
        about a permanent (or a player, which carries no `card_id` to ask
        about) becoming a target.
        """
        for target in ability.targets:
            if not target.is_card or target.card_id is None:
                continue
            targeted = self.find_by_id(target.card_id)
            if targeted is None or targeted.zone is not Zone.BATTLEFIELD:
                continue
            self.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_TARGET,
                    subject_id=targeted.id,
                    subject_name=targeted.name,
                    subject_controller=targeted.controller,
                    subject_card=targeted.card,
                    targeted_by=ability.id,
                    player=ability.controller,
                )
            )

    def _targets_for_trigger(self, ability: AbilityOnStack) -> list[TargetRef] | None:
        """What this triggered ability targets, as it goes on the stack (CR 603.3d).

        A scripted `choose_trigger_targets(card_name, ...)` answer wins outright
        - it is keyed by name rather than by ability instance on purpose, so
        two simultaneous triggers sharing a name (Ugin, Eye of the Storms'
        pair of "when you cast this spell" lines) both see it. Nothing
        scripted falls through to `_ask_trigger_targets`, which asks this
        ability *instance*, addressed to its own controller.

        `None` (only ever from `_ask_trigger_targets`) means CR 603.3d removed
        this ability from the stack before it was ever placed - see there.
        """
        front = ability.source_name.split("//")[0].strip()
        if ability.source_name in self.trigger_targets:
            return self.trigger_targets[ability.source_name]
        if front in self.trigger_targets:
            return self.trigger_targets[front]
        return self._ask_trigger_targets(ability)

    def _ask_trigger_targets(self, ability: AbilityOnStack) -> list[TargetRef] | None:
        """Ask a triggered ability's own controller for its targets (CR 603.3d).

        "The remainder of the process for putting a triggered ability on the
        stack is identical to the process for casting a spell listed in rules
        601.2c-601.2d" - so this is CR 601.2c's target announcement, put to
        `ability.controller` through the ordinary `Game.ask` `CHOOSE_TARGETS`
        question, with the legal candidates worked out by
        `TargetRequirement.rejects` - the same checker `activate_ability` and
        `choose_trigger_targets` already use.

        Three things can leave this with no targets, and something to say
        about why, recorded on `targeting_notices` rather than silently
        returned as if nothing were amiss (the DDR#978-shaped defect: an
        ability that does nothing looks identical to one with nothing to
        point at):

        - the restriction itself could not be read at all
          (`TargetingProfile.understood` is False) - `TargetingNoticeKind.UNPARSED`,
          an engine gap this returns `[]` for, same as ever;
        - nothing on the battlefield satisfies it right now, but the
          requirement was optional anyway (CR 115.6's "up to N", CR 107.1c's
          "any number of" - `profile.min_targets` is 0) -
          `TargetingNoticeKind.NO_LEGAL_TARGET`, a legal game state
          (CR 608.2d's own "nobody says otherwise" default), not a bug -
          returns `[]`, and the ability still goes on the stack choosing
          nothing;
        - nothing satisfies it and the requirement was mandatory
          (`profile.min_targets` > 0, a plain "target permanent" with no
          "up to") - CR 603.3d: "if a choice is required when the triggered
          ability goes on the stack but no legal choices can be made for it,
          ... the ability is simply removed from the stack." Returns `None`
          so the caller never places it, rather than the pre-fix behaviour of
          putting it on the stack anyway with an empty target list, where it
          would sit doing nothing while still occupying a stack slot CR
          603.3d says it should never have taken.

        An ability with no targeting requirement at all is not asked anything
        and gets no notice either - there is nothing to be silent about.
        """
        printed = ability.ability
        text = printed.text if isinstance(printed, TriggeredAbility) else ""
        profile = profile_for_text(text)
        return self._ask_targets(
            profile, ability.controller, ability.source_id, ability.source_name, text
        )

    def _ask_targets(
        self,
        profile: TargetingProfile,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        text: str,
    ) -> list[TargetRef] | None:
        """Ask `controller` for `profile`'s targets, addressed to `source_name` (CR 601.2c).

        The shared machinery behind both halves of CR 602.2b/603.3d's "the
        remainder of the process ... is identical to the process for casting a
        spell": a triggered ability's own announcement (`_ask_trigger_targets`)
        and an activated ability's, when its caller supplies no targets
        (`Game.activate_ability`). Both ask through the ordinary `CHOOSE_TARGETS`
        question, with the legal candidates worked out by `_legal_target_candidates`
        - the same checker `machines/targeting.py`'s `TargetingProfile.check`
        already uses - so this module does not grow a second target grammar.

        Three things can leave this with no targets, and something to say
        about why, recorded on `targeting_notices` rather than silently
        returned as if nothing were amiss (the DDR#978-shaped defect: an
        ability that does nothing looks identical to one with nothing to
        point at):

        - the restriction itself could not be read at all
          (`TargetingProfile.understood` is False) - `TargetingNoticeKind.UNPARSED`,
          an engine gap this returns `[]` for, same as ever;
        - nothing on the battlefield satisfies it right now, but the
          requirement was optional anyway (CR 115.6's "up to N", CR 107.1c's
          "any number of" - `profile.min_targets` is 0) -
          `TargetingNoticeKind.NO_LEGAL_TARGET`, a legal game state
          (CR 608.2d's own "nobody says otherwise" default), not a bug -
          returns `[]`, and the ability still goes on the stack choosing
          nothing;
        - nothing satisfies it and the requirement was mandatory
          (`profile.min_targets` > 0, a plain "target permanent" with no
          "up to") - `None`, so the caller never puts the ability where it
          would sit doing nothing: CR 603.3d removes a triggered ability from
          the stack in this case, and CR 601.2e/602.2b makes an activation
          with no legal target for a mandatory requirement illegal to begin
          at all (the same refusal `Game.cast_free_from_exile` already gives
          a spell with no legal target, CR 601.2c).

        An ability with no targeting requirement at all is not asked anything
        and gets no notice either - there is nothing to be silent about.
        """
        if not profile.understood:
            self.targeting_notices.append(
                TargetingNotice(
                    kind=TargetingNoticeKind.UNPARSED,
                    source_id=source_id,
                    source_name=source_name,
                    text=text,
                )
            )
            return []
        if not profile.requirements:
            return []

        candidates = self._legal_target_candidates(profile, controller, source_id)
        if not candidates:
            self.targeting_notices.append(
                TargetingNotice(
                    kind=TargetingNoticeKind.NO_LEGAL_TARGET,
                    source_id=source_id,
                    source_name=source_name,
                    text=text,
                )
            )
            return None if profile.min_targets > 0 else []

        decision = Decision(
            kind=DecisionKind.CHOOSE_TARGETS,
            player=controller,
            prompt=f"choose targets for {source_name}",
            source=source_name,
            targets=tuple(TargetRef.coerce(candidate) for candidate in candidates),
            target_maximum=profile.max_targets,
            target_minimum=min(profile.min_targets, len(candidates)),
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
        # ... unless the step is one that hands none out (CR 502.4, 514.3). A
        # resolution cannot happen in the untap step at all, but Time Stop's
        # CR 724.1 drops the pointer into cleanup mid-resolution, and priority
        # must not come back on the way out of it.
        self.sync_priority_with_step()

    def _take_out_of_every_zone(self, card_state: CardState) -> None:
        """Lift a card out of wherever it currently is, shared zones included."""
        for player in self.players:
            for zone_cards in player.zones.values():
                if card_state in zone_cards:
                    zone_cards.remove(card_state)
        for zone_cards in self.shared_zones.values():
            if card_state in zone_cards:
                zone_cards.remove(card_state)

    def _create_resolution_replacements(self, spell: CardState) -> None:
        """A resolving spell that leaves a replacement effect behind (CR 614.1a).

        Plagiarize is the printing: "Until end of turn, if target player would
        draw a card, instead that player skips that draw and you draw a card."
        There is nothing for `machines/effects.py` to do when it resolves - no
        object moves, no counter is placed - and nothing for the layer engine
        either, because CR 614 is not one of CR 613's layers. What it leaves is
        a `DrawRedirection` on `Game.draw_redirections`, exactly the way a
        resolved prevention spell leaves a CR 615.1 shield.

        The targeted player is read off the spell's own announced targets,
        which CR 608.2b has already rechecked (`spell_fizzles` ran above and a
        spell whose only target became illegal never got here).
        """
        target = next(
            (
                ref.username
                for ref in spell.targets
                if ref.username is not None and self.is_in_game(ref.username)
            ),
            None,
        )
        controller = self.controller_of(spell).username
        redirection = draw_redirection_for(spell.oracle_text or "", controller, target)
        if redirection is not None:
            self.draw_redirections.append(redirection)

    def _apply_mana_spend_effects(self, permanent: CardState) -> None:
        """CR 106.6's additional effect, applied to the permanent that spell
        just became.

        "Some spells or abilities that produce mana ... have an additional
        effect that affects the spell or ability that mana is spent on." Arena
        of Glory's "If that mana is spent on a creature spell, it gains haste
        until end of turn." is the printing: the sentence travelled with the
        mana (`ManaPool.spend_effects`), the payment recorded which of it was
        actually spent here (CR 601.2h, `ManaPayment.spend_effects_spent`) and
        `CastRecord.spend_effects` carried it through announcement.

        Applied after `enter_the_battlefield` because that is where the object
        gains a battlefield to be a permanent on: the grant is an ordinary
        layer 6 continuous effect (CR 613.1f) with an "until end of turn"
        duration, and every reader of haste - `Game.can_attack`, the summoning
        sickness check - already asks the computed board.

        A spell that is not the card type the sentence names gets nothing, and
        a sentence this engine cannot read gets nothing either; neither is
        refused, because this clause only ever gives something away.
        """
        sentences = self.cast_record(permanent).spend_effects
        if not sentences:
            return
        for sentence in sentences:
            for effect in spend_effect_effects(sentence, permanent, self.continuous_effects.tick()):
                self.continuous_effects.add(effect, self)

    def _note_left_battlefield(self, permanent: CardState) -> None:
        """Record Revolt's own condition: a permanent left the battlefield
        this turn (an ability word, CR 207.2c - Fatal Push's own printed
        wording, "a permanent left the battlefield under your control this
        turn", names no further numbered rule).

        Called by every route a permanent takes off the battlefield -
        `destroy`/`sacrifice` (through `put_into_graveyard`), `exile_permanent`,
        `return_to_hand` - at the point each already knows the move started
        there, before the move itself runs. Recorded regardless of where the
        permanent ends up: a replacement effect that redirects the destination
        (Rest in Peace) still moved it *off* the battlefield first, and Revolt
        asks only about leaving, not about arriving anywhere in particular.
        Controller, not owner - CR 108.4a's fallback is for a card with no
        controller at all, which a battlefield permanent always has.
        """
        # CR 608.2h: "If an effect requires information from the game ... the
        # answer is determined only once, when the effect is applied." An
        # effect that has to ask about a permanent which is no longer one -
        # Momentous Fall's "You draw cards equal to the sacrificed creature's
        # power", whose sacrifice CR 601.2h paid before the spell was even on
        # the stack - has nothing left to read once the continuous effects
        # stop applying. This is the last instant they still do.
        permanent.remember_last_known_power_toughness()
        controller = permanent.controller
        if controller is None:
            return
        self.permanents_left_battlefield_this_turn[controller] = (
            self.permanents_left_battlefield_this_turn.get(controller, 0) + 1
        )

    def revolt_active_for(self, controller: str) -> bool:
        """Whether Revolt's condition holds for `controller` right now: CR
        207.2c's ability word, printed as "a permanent you controlled left
        the battlefield this turn" (Fatal Push: "...under your control this
        turn"). Checked at resolution, not at announcement - the same instant
        `Game.legal_target`'s CR 608.2b recheck already reads other resolution-
        time conditions from."""
        return self.permanents_left_battlefield_this_turn.get(controller, 0) > 0

    def _additional_entering_loyalty(self, card_state: CardState) -> int:
        """Ral, Monsoon Mage's back face: "Ral enters with an additional
        loyalty counter on him for each instant and sorcery spell you've
        cast this turn." CR 306.5b's intrinsic "enters with N loyalty
        counters" (`CardState._enter_with_loyalty`, applied by `move_to`
        before this is ever called) only ever reads the printed number - it
        has no `Game` to ask a dynamic "for each ... this turn" question of,
        so the additional half is read here instead, off whichever face is
        now up, generalized on the spell types named rather than pinned to
        this one printing.

        Read from `card_state.oracle_text` - which already reads the back
        face once `CardState.transform`/`move_to(transformed=True)` has
        flipped it up - so this only ever finds Ral's own sentence on Ral,
        and finds nothing on every other permanent, transformed or not.
        """
        if not card_state.is_planeswalker:
            return 0
        text = card_state.oracle_text or ""
        match = _ADDITIONAL_LOYALTY_PER_INSTANT_SORCERY_RE.search(text)
        if match is None:
            return 0
        controller = card_state.controller or self.active_player.username
        cast = self.spells_cast_this_turn.get(controller, [])
        return sum(
            1 for spell in cast if Type.INSTANT in spell.types or Type.SORCERY in spell.types
        )

    def enter_the_battlefield(
        self,
        card_state: CardState,
        controller: str,
        *,
        tapped: bool = False,
        transformed: bool = False,
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
        with self._id_allocator_scope():
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
            # CR 712.14a: "if a spell or ability puts a double-faced card onto the
            # battlefield 'transformed' ..., it enters the battlefield with its
            # back face up." Set *before* the move, because `move_to` is where
            # CR 306.5b's intrinsic "enters with loyalty counters equal to its
            # printed loyalty" is applied, and the printed loyalty a transformed
            # Ajani, Nacatl Pariah enters with is his back face's 3 - read off
            # whichever face is up. A card that has no back face is left alone
            # (CR 701.28c's "nothing happens" for the sibling action).
            card_state.transformed = transformed and card_state.card.back_face is not None
            card_state.move_to(Zone.BATTLEFIELD)
            card_state.tapped = event.tapped
            # CR 702.131 (ascend): "entered this turn" needs a turn-number stamp,
            # not just a boolean, the same way `ExileAnnotation.turn_exiled` is -
            # see `CardState.turn_entered`. Stamped here, the one choke point
            # every route onto the battlefield runs through.
            card_state.turn_entered = self.turn.turn_number if self.turn is not None else None
            # CR 613.5: from here on this permanent's power and toughness are
            # whatever the layer engine says they are. A characteristic-defining
            # ability (CR 604.3, 613.4a) gives Tarmogoyf a power the printing does
            # not have, and an anthem in layer 7d makes a Grizzly Bears a 3/3.
            # Unbound, `CardState.power` answers with the printed value plus
            # counters (CR 122.1a), which is the wrong answer for anything a
            # continuous effect touches - and combat's CR 510.1a assignment and
            # CR 704.5g's lethal check both read it directly.
            card_state.bind_to_game(self)
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

            extra_loyalty = self._additional_entering_loyalty(card_state)
            if extra_loyalty:
                self.add_counters(card_state, Counter.LOYALTY, extra_loyalty)

            self.emit(self._enters_event(card_state))
            # CR 714.3a's own intrinsic lore counter (`CardState.move_to`, applied
            # before this point) is not routed through `add_counters` - the same
            # direct-write choice `_enter_with_loyalty` already makes for a
            # planeswalker's own entering loyalty - so it needs its own emission
            # for CR 107.15a's chapter I to trigger the moment the Saga arrives.
            self._emit_lore_counters_added(card_state, card_state.lore_counters)
            return card_state

    def put_onto_battlefield(
        self,
        card_state: CardState,
        controller: str,
        *,
        tapped: bool = False,
        transformed: bool = False,
    ) -> CardState:
        """Put a card onto the battlefield without casting it (CR 110.2a).

        This is the Tooth and Nail path. CR 601.2 defines casting as taking a
        card "from where it is (usually the hand), put it on the stack, and pay
        its costs" - a card put straight onto the battlefield never does any of
        that, so no casting event occurs and CR 603.2's "an ability triggers only
        if its trigger event actually occurs" (CR 603.2g) means a "when you cast
        this spell" ability never fires. Enters-the-battlefield abilities do
        (CR 603.6a), because that event *did* happen.

        `transformed` is CR 712.14a's "onto the battlefield transformed": the
        permanent arrives with its back face up, and so with that face's
        characteristics from the moment it exists - including the printed
        loyalty CR 306.5b puts on as it enters, which is the only way a
        creature face like Ajani, Nacatl Pariah becomes a planeswalker with any
        loyalty at all.
        """
        with self._id_allocator_scope():
            return self.enter_the_battlefield(
                card_state, controller, tapped=tapped, transformed=transformed, was_cast=False
            )

        # -- the pregame sequence (CR 103.5, CR 103.6) ----------------------------
        #
        # A game dealt from decklists *rests* in `Step.MULLIGAN` and then in
        # `Step.PREGAME_ACTIONS`, and every seat acts through the methods below.
        # Neither step asks anybody anything: `declare_mulligan`,
        # `take_opening_hand_action` and `finish_opening_hand_actions` are told an
        # answer that has already been made, so nothing here ever waits on a person.
        #
        # That is the whole point of the restructure. The previous shape ran both
        # sequences inside one call that put every question through `Game.ask`; with
        # a live seat behind an API that blocks until a human answers,
        # starting a game took one full answer timeout *per question per seat* -
        # measured at 1200 s (4 x 300 s) for two seats across both sequences - while
        # holding the game lock. A step the game rests in has no wait to hold: the
        # game sits there, publishes what it is waiting for, and moves the moment the
        # last seat has spoken.
        #
        # `settle_pregame` is the headless path and keeps the old behaviour exactly:
        # it asks each seat through the ordinary decision machinery, where an
        # unanswered question falls through to `default_answer` immediately.

    @property
    def in_pregame(self) -> bool:
        """Whether the game is still before CR 103.8's first turn."""
        return self.turn is not None and self.turn.in_pregame

    def begin_pregame(self, seed_prefix: str = "") -> Step:
        """Put this game in CR 103.5's mulligan step, before any turn has begun.

        Called by `Match.start_game` once the hands are dealt. `seed_prefix` is
        where every mulligan reshuffle's seed comes from - see `pregame_seed`.
        """
        assert self.turn is not None
        with self._id_allocator_scope():
            self.pregame_seed = seed_prefix
            self.mulligan_declarations = {}
            step = self.turn.begin_pregame()
            self._resolve_mulligan_round_if_ready()
            return self.turn.step if self.turn.in_pregame else step

    # -- CR 103.5: the mulligan process ---------------------------------------

    @property
    def mulligan_seats(self) -> list[Player]:
        """Players who have not yet kept a hand, in CR 103.5's declaration order.

        "First, the starting player declares whether they will take a mulligan.
        Then each other player in turn order does the same." `self.players` is
        seated with the starting player first, so walking it is that order.
        """
        return [player for player in self.players if not player.hand_kept]

    @property
    def awaiting_mulligan_declarations(self) -> list[str]:
        """Who still owes a declaration this round, in turn order.

        A player at CR 103.5's ceiling - "a player can take mulligans until their
        opening hand would be zero cards, after which they may not take further
        mulligans" - is offered no declaration at all and so is never awaited;
        keeping a hand of nothing is what is left to them.
        """
        if self.turn is None or self.turn.step is not Step.MULLIGAN:
            return []
        return [
            player.username
            for player in self.mulligan_seats
            if player.can_mulligan and player.username not in self.mulligan_declarations
        ]

    def declare_mulligan(self, username: str, take: bool) -> Step:
        """Record one seat's CR 103.5 declaration, resolving the round when it completes.

        This is the live seat's whole move, and it blocks on nothing: the answer
        is passed in, already made. When the last seat still owed a declaration
        has spoken, the round resolves here - "once each player has made a
        declaration, all players who decided to take mulligans do so at the same
        time" - and either a fresh round opens or the process is over and the
        game moves to `Step.PREGAME_ACTIONS`.

        Returns the step the game is in afterwards, which is how a caller learns
        that its declaration was the one that finished the round.
        """
        assert self.turn is not None
        if self.turn.step is not Step.MULLIGAN:
            raise ValueError(
                f"CR 103.5's mulligan process is not under way - the game is at {self.turn.step}"
            )
        player = self.player(username)
        if player.hand_kept:
            raise ValueError(f"{username} has already kept a hand")
        if username in self.mulligan_declarations:
            raise ValueError(f"{username} has already declared this round")
        if take and not player.can_mulligan:
            raise ValueError(
                f"{username} cannot mulligan past a hand of nothing "
                f"({player.mulligans_taken} taken) (CR 103.5)"
            )

        with self._id_allocator_scope():
            self.mulligan_declarations[username] = take
            self._resolve_mulligan_round_if_ready()
            return self.turn.step

    def _resolve_mulligan_round_if_ready(self) -> None:
        """Carry out one round of CR 103.5 once every declaration is in.

        Nothing happens while a seat still owes one. When they are all in:

        - if nobody declared a mulligan, everybody keeps, paying CR 103.5's
          bottoming cost, and the process is over;
        - otherwise "all players who decided to take mulligans do so at the same
          time" - every declaration was collected before any of this ran, which
          is what makes them simultaneous - and the players who declared against
          keep instead. A fresh round then opens for whoever mulliganed.

        A seat with no legal mulligan left counts as a declaration to keep, which
        is why the process always terminates: a player who keeps mulliganing runs
        out of hand.
        """
        assert self.turn is not None
        if self.turn.step is not Step.MULLIGAN:
            return
        if self.awaiting_mulligan_declarations:
            return

        deciding = self.mulligan_seats
        declarations = [
            (player, self.mulligan_declarations.get(player.username, False)) for player in deciding
        ]
        self.mulligan_declarations = {}

        for player, take in declarations:
            if take:
                # The same seed string the blocking loop derived, component for
                # component, so a replay with the same declarations is identical.
                player.mulligan(
                    f"{self.pregame_seed}:mulligan:{player.username}:{player.mulligans_taken}"
                )
        for player, take in declarations:
            if not take:
                player.keep_hand(self._bottom_for_keep(player))

        if not self.mulligan_seats:
            # CR 103.6 begins "once the mulligan process ... is complete".
            self.turn.advance()

    def _bottom_for_keep(self, player: Player) -> list[CardState] | None:
        """Which cards this player puts on the bottom when they keep (CR 103.5).

        CR 103.5c and CR 800.6 both name the quantity - "the number of cards that
        player will put on the bottom of their library" - and `cards_to_bottom`
        computes it; *which* cards they are is the player's own choice.

        Asked as a `CHOOSE_CARDS` question through `Game.ask`, the same CR 608.2d
        machinery `ask_cleanup_discard` uses for CR 701.9b's discard, and
        deliberately **not** a new `DecisionKind`: "choose exactly N of these
        cards, from one zone, in an order that matters" is precisely what that
        kind already is, its `exact` validation already refuses a wrong-sized or
        stray-card answer, and every client that can already render a
        `CHOOSE_CARDS` question can render this one with no change.

        This one *is* a `Game.ask`, and it is the one place in the pregame that
        stays one: it is only reached for a player who has already mulliganed at
        least once, it has a correct default (the back of the hand, which is what
        `Player.keep_hand(None)` bottoms), and a client that wants a human to
        choose can script or provide the answer before the declaration that
        triggers it. Two properties that buys:

        - **The default is unchanged.** `default_answer` for an exact
          `CHOOSE_CARDS` returns "the back of `cards`, in the order the caller
          offered them", and the hand is offered here in hand order - byte for
          byte the list `Player.keep_hand(None)` builds. An unscripted,
          unprovided game bottoms exactly what it bottomed before, so every
          seeded replay holds.
        - **Nothing random happens here**, so the reshuffle seeds are untouched
          by asking.

        `None` is returned when there is nothing to bottom, so the question is not
        put at all - a choice among zero cards is not a choice.
        """
        needed = player.cards_to_bottom
        if needed <= 0:
            return None
        hand = list(player.hand)
        chosen = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"put {needed} card(s) on the bottom of your library",
                amount=needed,
                cards=tuple(state.id for state in hand),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {state.id: state for state in hand}
        return [by_id[card_id] for card_id in chosen]

    # -- settling a pregame with nobody there to answer -----------------------

    def settle_pregame(self) -> Step:
        """Run the whole pregame through the ordinary decision machinery.

        The headless path, and the one every scenario that just wants a game to
        play uses. Each declaration goes through `ask_mulligan` and each CR 103.6
        action through `Game.ask`, so a scripted answer wins, then the replay
        tape, and only when neither speaks does `default_answer` stand - keep
        the dealt hand, decline every opening-hand action. That is immediate
        and deterministic, which is exactly what it was before this became a
        rested-in step.

        Returns the step the game ends in: `Step.UNTAP` of CR 103.8's first turn,
        unless the game was never in the pregame at all.
        """
        assert self.turn is not None
        with self._id_allocator_scope():
            while self.turn.step is Step.MULLIGAN:
                pending = self.awaiting_mulligan_declarations
                for username in pending:
                    self.declare_mulligan(username, ask_mulligan(self.decisions, username))
                if not pending:
                    # Every seat left is at CR 103.5's ceiling, so the round has
                    # no questions in it at all and nothing triggered its
                    # resolution. Resolving it keeps every remaining hand, which
                    # ends the process.
                    self._resolve_mulligan_round_if_ready()
                # Anything else means a round resolved and a fresh one opened
                # for whoever mulliganed, which is the loop going round again.
                # It always terminates: a player who keeps mulliganing runs out
                # of hand.

            if self.turn.step is Step.PREGAME_ACTIONS:
                self.take_opening_hand_actions()
            return self.turn.step

    # -- opening-hand actions (CR 103.6) --------------------------------------

    def opening_hand_options(self, username: str) -> list[Decision]:
        """The CR 103.6 actions this seat may take right now, in hand order.

        "Some cards allow a player to take actions with them from their opening
        hand." A card that offers none, and a card whose restriction is not met
        (Gemstone Caverns in the starting player's hand), produce nothing here:
        the card does not "allow a player to take" that action, which is
        CR 103.6's own condition for there being a question at all.

        Read fresh off the hand every time, so an action already taken - the card
        has left the hand under CR 103.6a - is gone from the list. The `source`
        of each `Decision` names the card, and `Decision.card` its id, which is
        what `take_opening_hand_action` is keyed by.
        """
        player = self.player(username)
        return [decision for decision, _, _ in self._opening_hand_offers(player)]

    def _opening_hand_offers(
        self, player: Player
    ) -> list[tuple[Decision, OpeningHandAction, CardState]]:
        """Every CR 103.6 action on offer to this player, with what carries it."""
        assert self.turn is not None
        starting_player = self.turn.starting_player
        offers: list[tuple[Decision, OpeningHandAction, CardState]] = []
        for card_state in list(player.hand):
            actions, notices = read_opening_hand_actions(card_state.card)
            seen = {(notice.card_name, notice.text) for notice in self.opening_hand_notices}
            for notice in notices:
                if (notice.card_name, notice.text) not in seen:
                    self.opening_hand_notices.append(notice)
            for action in actions:
                if action.requires_not_starting_player and player.username == starting_player:
                    continue
                if card_state.id in self.opening_hand_reveals:
                    # CR 103.6b: "Each card may be revealed this way only
                    # once." A card put onto the battlefield under CR 103.6a
                    # leaves the hand, so the loop above stops offering it on
                    # its own - but a *revealed* card stays in hand
                    # (CR 701.20b), so without this it was offered again after
                    # being taken, for ever. Through the API that read as a
                    # button that did nothing: the action really was performed
                    # each time, and the panel came back unchanged.
                    continue
                offers.append(
                    (
                        Decision(
                            kind=DecisionKind.OPENING_HAND_ACTION,
                            player=player.username,
                            prompt=action.text,
                            source=card_state.name,
                            card=card_state.id,
                        ),
                        action,
                        card_state,
                    )
                )
        return offers

    def take_opening_hand_action(self, username: str, card: UUID) -> None:
        """Take one CR 103.6 action with a card in this seat's opening hand.

        The live seat's move, and it blocks on nothing: taking it *is* the
        answer, and a seat that wants none calls `finish_opening_hand_actions`
        instead. "The starting player may take any such actions in any order" -
        so the order within a seat is the seat's, and this performs whichever
        card it is handed.

        Refused when it is not this seat's turn in CR 103.6's order, when the
        game is not in the opening-hand step, and when the named card offers no
        action - a card that does not allow the action is not permission to take
        it.
        """
        assert self.turn is not None
        if self.turn.step is not Step.PREGAME_ACTIONS:
            raise ValueError(
                f"CR 103.6's opening-hand actions are not under way - "
                f"the game is at {self.turn.step}"
            )
        if username != self.opening_hand_actor:
            raise ValueError(
                f"it is {self.opening_hand_actor}'s turn to take opening-hand "
                f"actions, not {username}'s (CR 103.6)"
            )
        player = self.player(username)
        with self._id_allocator_scope():
            for _, action, card_state in self._opening_hand_offers(player):
                if card_state.id == card:
                    self._perform_opening_hand_action(action, card_state, player)
                    return
        raise ValueError(f"no card in {username}'s opening hand offers that action (CR 103.6)")

    @property
    def opening_hand_actor(self) -> str | None:
        """Whose CR 103.6 actions the game is waiting on, or None if it is not waiting."""
        if self.turn is None or self.turn.step is not Step.PREGAME_ACTIONS:
            return None
        if self.opening_hand_seat >= len(self.players):
            return None
        return self.players[self.opening_hand_seat].username

    def finish_opening_hand_actions(self, username: str) -> Step:
        """This seat is done taking CR 103.6 actions; pass to the next one.

        When the last seat is done the pregame is over and CR 103.8's first turn
        begins - `Step.UNTAP`, turn 1, with `turn_number` and `turns_taken`
        moving off zero for the first time. Nothing untaps and nobody draws
        because of this: it moves the pointer, and the untap step's own
        turn-based actions happen when the game advances out of it, exactly as on
        every later turn.
        """
        with self._id_allocator_scope():
            assert self.turn is not None
            if self.turn.step is not Step.PREGAME_ACTIONS:
                raise ValueError(
                    f"CR 103.6's opening-hand actions are not under way - "
                    f"the game is at {self.turn.step}"
                )
            if username != self.opening_hand_actor:
                raise ValueError(
                    f"it is {self.opening_hand_actor}'s turn to take opening-hand "
                    f"actions, not {username}'s (CR 103.6)"
                )
            self.opening_hand_seat += 1
            if self.opening_hand_seat >= len(self.players):
                self.opening_hand_actions_taken = True
                self.turn.advance()  # CR 103.8: the starting player takes their first turn
            return self.turn.step

    def take_opening_hand_actions(self) -> list[Decision]:
        """CR 103.6's sequence: after the mulligan, before the first turn.

        "Some cards allow a player to take actions with them from their opening
        hand. Once the mulligan process (see rule 103.5) is complete, the
        starting player may take any such actions in any order. Then ea[ch other
        player ...]" - the excerpt from `knowledge_search` truncates there, so
        what is implemented is only what it states outright: the starting player
        first, then the rest, each player's own actions in an order this engine
        picks (hand order) because the rule leaves it free.

        `self.players` is seated with the starting player first (CR 103.8,
        `TurnMachine.starting_player`), so walking it *is* that order - the same
        list and the same reasoning `Match.run_mulligans` already uses for
        CR 103.5's declarations. CR 101.4's APNAP ordering is not what applies
        here: no turn has begun, so there is no active player, and CR 103.6
        states its own order.

        Every action is optional - "may take any such actions" - so every one is
        put to its player as a `DecisionKind.OPENING_HAND_ACTION` question and
        an unscripted player declines (see `machines/decisions.py`). A player
        holding no card that offers one is asked nothing at all, and a card
        whose restriction is not met (Gemstone Caverns in the starting player's
        hand) offers no action, so it is not asked either: the card does not
        "allow a player to take" that action, which is CR 103.6's own condition
        for there being a question.

        Nothing in this sequence is random, so nothing here needs the match seed
        that `Match.run_mulligans` derives for its reshuffles: given the same
        declarations and the same scripted answers, a replay reproduces it
        exactly.

        This is the **ask-driven** whole-sequence path: it puts every action to
        its player through `Game.ask`, which is what an unattended game wants and
        what every scenario here uses. A live seat that blocks on each answer
        should not be driven this way - it is one blocking wait per offer - and
        uses `opening_hand_options`, `take_opening_hand_action` and
        `finish_opening_hand_actions` instead, which ask nobody anything.

        Returns the questions that were put, in order. Idempotent: CR 103.6's
        sequence happens once per game, and CR 103.6b's "each card may be
        revealed this way only on[ce]" would be broken by a second run. When the
        game is resting in `Step.PREGAME_ACTIONS` this finishes every remaining
        seat, so it leaves the game at `Step.UNTAP` of CR 103.8's first turn.
        """
        with self._id_allocator_scope():
            if self.opening_hand_actions_taken:
                return []

            asked: list[Decision] = []
            in_pregame = self.turn is not None and self.turn.step is Step.PREGAME_ACTIONS

            if not in_pregame:
                # No pregame to walk - a game built board-first, which never entered
                # `Step.MULLIGAN`. The seat-by-seat bookkeeping has nothing to track,
                # so the sequence is run over the players directly and marked done.
                self.opening_hand_actions_taken = True
                for player in list(self.players):
                    asked.extend(self._ask_opening_hand_actions_of(player))
                return asked

            while (actor := self.opening_hand_actor) is not None:
                asked.extend(self._ask_opening_hand_actions_of(self.player(actor)))
                self.finish_opening_hand_actions(actor)

            return asked

    def _ask_opening_hand_actions_of(self, player: Player) -> list[Decision]:
        """Put every CR 103.6 action on offer to one player, in hand order.

        Every action is optional - "may take any such actions" - so every one is
        a `DecisionKind.OPENING_HAND_ACTION` question and an unscripted player
        declines (see `machines/decisions.py`). A player holding no card that
        offers one is asked nothing at all.
        """
        asked: list[Decision] = []
        for decision, action, card_state in self._opening_hand_offers(player):
            if card_state.zone is not Zone.HAND:
                # An earlier action already moved it out of the opening hand;
                # CR 103.6a/103.6b both act on a card *in* the hand.
                continue
            asked.append(decision)
            if self.ask(decision) is not True:
                continue
            self._perform_opening_hand_action(action, card_state, player)
        return asked

    def _perform_opening_hand_action(
        self,
        action: OpeningHandAction,
        card_state: CardState,
        player: Player,
    ) -> None:
        """Carry out one accepted CR 103.6 action, then its rider.

        CR 103.6a puts the card onto the battlefield; CR 103.6b reveals it and
        leaves it where it is (CR 701.20b). The rider - the card's own trailing
        "If you do, ..." - runs afterwards, in the order the card prints it, and
        is looked up by name in `machines/opening_hand.py`'s `RIDERS`. An action
        with a rider and no entry there never reaches here: it is refused while
        being read, with a notice.
        """
        if action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD:
            self.put_onto_battlefield(card_state, player.username)
            if action.counter and card_state.zone is Zone.BATTLEFIELD:
                # "with a luck counter on it" - part of how it begins the game
                # there, so it is put on as soon as the permanent exists.
                self.add_counters(card_state, action.counter)
        else:
            # CR 103.6b: revealed, and it stays in hand (CR 701.20b).
            self.reveal(card_state, source=card_state.name)
            self.opening_hand_reveals.append(card_state.id)

        rider = RIDERS.get(card_state.card.name) if action.rider else None
        if rider is not None:
            rider(self, card_state, player)

    # -- decisions made during resolution (CR 608.2d) -------------------------

    def _with_card_labels(self, decision: Decision) -> Decision:
        """Name the cards a question offers (`Decision.card_labels`).

        A question carries `CardState` ids in `cards` - the candidates of a
        `CHOOSE_CARDS`, the cards being looked at by a `SCRY` or a `SURVEIL`,
        the qualifying cards a `MAY` is about - and for a question about a
        *hidden* zone (CR 400.2: the library and the hand) a client
        holding the game state cannot turn those ids into cards - only the
        player looking at the zone may, and the whole point of asking is that
        they are being shown it. Ugin's Labyrinth published "you may exile a
        colorless card with mana value 7 or greater from your hand" to a live
        seat with nothing naming which cards qualified; the choice that follows
        it named them only by id.

        So the label travels with every question, filled in once here rather
        than at each of the thirty-odd askers - a caller that already built its
        own labels (`search_library`, `ask_trigger_order`, whose ids are not
        cards at all) keeps them untouched.

        All-or-nothing: if any id names nothing this game can find, the labels
        are left empty rather than misaligned, because `card_labels` is
        documented as positionally aligned with `cards` and a client indexing
        into a partial list would read the wrong name for the wrong card.
        """
        if decision.card_labels or not decision.cards:
            return decision
        states = [self.find_by_id(card_id) for card_id in decision.cards]
        if any(state is None for state in states):
            return decision
        return replace(decision, card_labels=tuple(state.name for state in states if state))

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

        A scripted answer always wins; failing that, the replay tape
        (`decisions.recorded`, see `machines/decisions.py`'s "Pausing instead
        of blocking") is read next, and only once neither has anything - no
        unconsumed tape entry either - does this raise `DecisionPending`
        (when `decisions.pause_when_unanswered` is set) or, failing that too,
        let `default_answer` speak for the player.

        Every `CHOOSE_CARDS` question is labelled on its way through here - see
        `_with_card_labels` - so a client is never handed a list of ids naming
        cards it cannot see.
        """
        decision = self._with_card_labels(decision)
        self.decisions.asked.append(decision)
        allowed = legal_options(decision)
        found, value = self.decisions.take(decision)
        if not found:
            found, value = self.decisions.take_from_tape(decision)
        if not found and self.decisions.pause_when_unanswered:
            raise DecisionPending(
                PendingDecision(
                    seq=len(self.decisions.asked) - 1,
                    decision=decision,
                    rule=rule_for_kind(decision.kind),
                )
            )
        if not found:
            return default_answer(decision)

        if decision.kind in (
            DecisionKind.MAY,
            DecisionKind.PAY_LIFE,
            DecisionKind.PAY_ENERGY,
            DecisionKind.PAY_MANA,
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
            if value not in allowed:
                raise ValueError(
                    f"{decision.prompt}: that option is illegal, so CR 608.2d "
                    f"does not allow choosing it"
                )
            return value

        if decision.kind is DecisionKind.PAY_ENERGY_AMOUNT:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs an integer amount of energy")
            if value < 0 or value > decision.amount:
                raise ValueError(
                    f"{decision.prompt}: cannot pay {value} energy, only {decision.amount} "
                    f"available (CR 118.3, CR 107.14)"
                )
            return value

        if decision.kind is DecisionKind.PAY_LIFE_AMOUNT:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs an integer amount of life")
            if value < 0 or value > decision.amount:
                raise ValueError(
                    f"{decision.prompt}: cannot pay {value} life, life total is only "
                    f"{decision.amount} (CR 119.4)"
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
            if len(set(value)) != len(value):
                # One card is one object (CR 109.1) and can be chosen once.
                # Naming it twice would, for a search, take it out of the zone
                # twice; for a discard it would claim to discard two cards
                # while moving one.
                raise ValueError(f"{decision.prompt}: the same card cannot be chosen twice")
            if decision.exact:
                if len(value) != decision.amount:
                    raise ValueError(
                        f"{decision.prompt}: needs {decision.amount} card(s) chosen, "
                        f"{len(value)} given"
                    )
            elif len(value) > decision.amount:
                # CR 107.1c: "any number" runs zero up to every card offered,
                # never a fixed count - Valakut Awakening's own "any number of
                # cards from your hand" is the shape `exact=False` reads.
                raise ValueError(
                    f"{decision.prompt}: at most {decision.amount} card(s) may be chosen "
                    f"(CR 107.1c), {len(value)} given"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_TARGETS:
            if not isinstance(value, (tuple, list)):
                raise ValueError(f"{decision.prompt}: needs a tuple of targets")
            chosen = [TargetRef.coerce(target) for target in value]
            # `decision.targets` is the candidate pool this decision was built
            # with (`_ask_targets`, `_legal_target_candidates`), each entry
            # already carrying the `zone_change_stamp` its `CardState` had at
            # that moment (CR 601.2c/603.3d's announcement). A caller such as
            # `magic_cards_model_api.decisions.targets_answer` names a target
            # by a bare id with no stamp of its own - `TargetRef.__eq__`
            # ignores the stamp, so it still matches here, but swapping it for
            # its canonical pool entry is what actually carries the stamp
            # onto `self.targets`/`ability.targets` afterwards. Without this,
            # a target chosen through that path could never be judged illegal
            # by CR 608.2b's zone-change clause - the fix would be a no-op
            # over exactly the surface the bug was reported from.
            by_identity = {ref: ref for ref in decision.targets}
            stray = [str(ref) for ref in chosen if ref not in by_identity]
            if stray:
                raise ValueError(f"{decision.prompt}: not a legal target: {', '.join(stray)}")
            chosen = [by_identity[ref] for ref in chosen]
            if decision.target_maximum is not None and len(chosen) > decision.target_maximum:
                raise ValueError(
                    f"{decision.prompt}: too many targets chosen, at most "
                    f"{decision.target_maximum} (CR 115.6)"
                )
            if len(chosen) < decision.target_minimum:
                # CR 601.2c: "the player announces their choice of an
                # appropriate object or player for each target the spell
                # requires" - a plain "target permanent" is mandatory, not a
                # "you may", so declining while a legal target exists is
                # refused the same way an illegal target already is. CR 603.3d
                # extends this verbatim to a triggered ability's own
                # announcement.
                raise ValueError(
                    f"{decision.prompt}: at least {decision.target_minimum} target(s) "
                    f"must be chosen, {len(chosen)} given, while a legal target exists "
                    f"(CR 601.2c, CR 603.3d)"
                )
            return chosen

        if decision.kind is DecisionKind.CHOOSE_A_QUALITY:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{decision.prompt}: needs a chosen value (CR 614.12a)")
            if decision.options and value not in decision.options:
                raise ValueError(
                    f"{decision.prompt}: {value!r} is not among the legal choices "
                    f"({', '.join(decision.options)})"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_A_MODE:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{decision.prompt}: needs a chosen mode (CR 700.2a)")
            if decision.options and value not in decision.options:
                raise ValueError(
                    f"{decision.prompt}: {value!r} is not among the printed modes "
                    f"({', '.join(decision.options)})"
                )
            return value

        if decision.kind is DecisionKind.PUT_ON_TOP_OR_BOTTOM:
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs a top-or-bottom bool answer")
            return value

        if decision.kind is DecisionKind.OPENING_HAND_ACTION:
            # CR 103.6's "may take any such actions": a yes-or-no, both branches
            # always legal - a restriction the card prints (Gemstone Caverns'
            # "you're not the starting player") stops the question being asked
            # at all rather than making one answer illegal.
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
            return value

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
        with self._id_allocator_scope():
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

    def may_pay_energy(
        self, player: Player | str, amount: int, *, source: str | None = None
    ) -> bool:
        """ "You may pay {E}{E}..." / "...unless you pay {E}", asked and then
        paid (CR 107.14, CR 118.3, CR 608.2d).

        CR 107.14: "To pay {E}, a player removes one energy counter from
        themselves." CR 118.3: "A player can't pay a cost without having the
        necessary resources to pay it fully" - so the affirmative is illegal
        below `amount` energy, exactly the shape `may_pay_life` already uses
        for CR 119.4's life-total floor, and the same reason: a scripted "yes"
        below the floor is a rules violation, not merely a bad idea, so it is
        removed from `legal_options` rather than trusted to self-police.

        Static Prison's "sacrifice this enchantment unless you pay {E}" reads
        this the same call the other way round: paying is what avoids the
        sacrifice rather than what causes a bonus, but the payment itself -
        can it be paid, and does paying spend exactly `amount` energy and
        nothing else - is identical either way.

        Returns whether the energy was paid, and pays it. A "no" answer -
        whether scripted, taped, or the fixed-cost default (`default_answer`
        takes the affirmative when it is legal, same as `PAY_LIFE`) - leaves
        the player's energy untouched.
        """
        if isinstance(player, str):
            player = self.player(player)
        payable = amount <= 0 or player.energy >= amount
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_ENERGY,
                player=player.username,
                prompt=f"pay {amount} energy",
                source=source,
                amount=amount,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        if amount > 0:
            player.remove_counters(Counter.ENERGY, amount)
        return True

    def may_pay_mana(self, player: Player | str, amount: int, *, source: str | None = None) -> bool:
        """ "Unless its controller pays {N}", asked and then paid (CR 118.12a,
        CR 608.2d) - Censor's and Mystical Dispute's shape.

        CR 118.12a: "[Do something] unless [a player does something else]"
        means "[a player] may [do something else]. If [that player] doesn't,
        [effect]." - the same reading `may_pay_energy` already gives Static
        Prison's own "unless", just with the branches swapped: paying here is
        what *avoids* the counter, not what triggers a bonus.

        Only mana already floating in the player's pool counts. CR 608.2g
        lets a player activate mana abilities right here, but nothing calls
        this mid-resolution with an interactive tap step, so a player who
        would have to tap a land is refused exactly as if they had no mana at
        all - see `docs/engine-coverage.md`.

        Returns whether the mana was paid, and spends it.
        """
        if isinstance(player, str):
            player = self.player(player)
        payable = amount <= 0 or player.mana_pool.total >= amount
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_MANA,
                player=player.username,
                prompt=f"pay {{{amount}}} or the spell is countered",
                source=source,
                amount=amount,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        if amount > 0:
            player.mana_pool.pay(ManaCost.parse(f"{{{amount}}}"))
        return True

    def may_pay_mana_cost(
        self, player: Player | str, cost: ManaCost, *, source: str | None = None
    ) -> bool:
        """ "Pay {cost}. If you don't, ..." with a real (possibly colored) mana
        cost rather than `may_pay_mana`'s bare generic amount - the Pact
        cycle's own delayed-trigger shape (CR 603.7, CR 118.12a's "unless"
        read the other way round): "At the beginning of your next upkeep, pay
        {2}{G}{G}. If you don't, you lose the game."

        Same limitation as `may_pay_mana`: only mana already floating in the
        pool counts (CR 608.2g's interactive tap step is not modelled
        mid-resolution), so a player who could only pay by tapping a land is
        refused exactly as if they had no mana at all.

        Returns whether the cost was paid, and pays it.
        """
        if isinstance(player, str):
            player = self.player(player)
        payable = player.mana_pool.can_pay(cost)
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_MANA,
                player=player.username,
                prompt=f"pay {cost}",
                source=source,
                amount=cost.converted,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        player.mana_pool.pay(cost)
        return True

    def pay_any_amount_of_energy(
        self,
        player: Player | str,
        *,
        source: str | None = None,
        prompt: str = "pay any amount of {E}",
    ) -> int:
        """ "You may pay any amount of {E}" (Galvanic Discharge, Wrath of the
        Skies) - CR 107.14, CR 118.3, CR 608.2d's variable-amount cousin of
        `may_pay_energy`.

        Unlike a fixed `{E}{E}{E}`, this is a real choice among every amount
        from 0 up to however much energy the player has *right now* - `amount`
        pays no more than that (CR 118.3), and 0 is always legal (declining).
        `Game.ask` validates the answer is an int in that range; nothing here
        or in `default_answer` ever substitutes the maximum for an unscripted
        or declined answer - CR 608.2d's choice is the player's, not an
        optimiser's, and a card that keys its own effect off the amount paid
        (Galvanic Discharge's damage, Wrath of the Skies's mana-value ceiling)
        would silently always deal maximum damage or destroy everything if
        this ever defaulted upward.

        Returns however much was actually paid (0 if declined or unaffordable
        to pay more), and pays exactly that - never a partial amount on top of
        a partial deduction, since the whole payment is one `remove_counters`
        call once the amount is already known to be legal.
        """
        if isinstance(player, str):
            player = self.player(player)
        available = player.energy
        decision = Decision(
            kind=DecisionKind.PAY_ENERGY_AMOUNT,
            player=player.username,
            prompt=prompt,
            source=source,
            amount=available,
        )
        paid = self.ask(decision)
        assert isinstance(paid, int)
        if paid > 0:
            player.remove_counters(Counter.ENERGY, paid)
        return paid

    def pay_any_amount_of_life(
        self,
        player: Player | str,
        *,
        source: str | None = None,
        prompt: str = "pay any amount of life",
    ) -> int:
        """ "You may pay any amount of life" (Necrodominance) - CR 119.4's
        variable-amount cousin of `may_pay_life`, mirroring `pay_any_amount_
        of_energy` exactly: a real choice from 0 up to the player's *current*
        life total (CR 119.4: legal "only if their life total is greater
        than or equal to the amount of the payment", which paying down to
        exactly 0 satisfies), never defaulted upward for an unscripted
        answer - Necrodominance's own "draw that many cards" would otherwise
        silently draw the maximum every time.

        Returns however much was actually paid (0 if declined), and pays
        exactly that.
        """
        if isinstance(player, str):
            player = self.player(player)
        available = player.life
        decision = Decision(
            kind=DecisionKind.PAY_LIFE_AMOUNT,
            player=player.username,
            prompt=prompt,
            source=source,
            amount=available,
        )
        paid = self.ask(decision)
        assert isinstance(paid, int)
        if paid > 0:
            player.lose_life(paid)
        return paid

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
        with self._id_allocator_scope():
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
                    # CR 701.22a's own two destinations, quoted above, so a client
                    # does not have to infer them from the kind.
                    moved_label="bottom of your library",
                    kept_label="top of your library",
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
        with self._id_allocator_scope():
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
                    # CR 701.25a's own two destinations, quoted above: the same
                    # "rest on top" as a scry, a different first half.
                    moved_label="your graveyard",
                    kept_label="top of your library",
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

    def look_at_top_and_split(
        self,
        player: Player | str,
        count: int,
        *,
        moved_label: str,
        kept_label: str,
        source: str | None = None,
        prompt: str | None = None,
    ) -> tuple[list[CardState], list[CardState]]:
        """Look at the top `count` cards and split them into two groups, the
        same CR 608.2d question `scry` and `surveil` already ask (CR 701.22a,
        CR 701.25a) generalised past those two rules' own fixed pair of
        destinations.

        `scry` always puts the `CardSplit.moved` half on the *bottom* of the
        library and the rest back on *top*; `surveil` always puts `moved` in
        the *graveyard*. Duskwatch Recruiter's activated ability ("look at the
        top three cards of your library. You may reveal a creature card from
        among them and put it into your hand. Put the rest on the bottom of
        your library in any order.") needs neither pair - its chosen half goes
        to *hand* and its rest half goes to the *bottom* - so this method asks
        the identical CardSplit question CR 701.22a/701.25a already share and
        then, unlike `scry`/`surveil`, does nothing to `player.library` at all:
        both returned groups are already off the library, in the answer's own
        order, and it is entirely the caller's job to decide where each group
        actually goes. That is what lets a caller reach a pair of destinations
        neither built-in rule has, without a third method duplicating the
        look-then-split machinery `_look_at_top`/`_split_top` already hold.

        Reuses `DecisionKind.SCRY` rather than adding a new kind - the
        question underneath ("which of these `count` cards move to the first
        group, and in what order do the rest come back") is exactly the one
        `scry` already asks; only what a caller does with the two halves
        afterward differs.

        Returns `(moved, rest)`. `CR 701.22a`'s question, not `CR 701.22a`'s
        answer's placement - callers using this for something CR 701.22a does
        not describe (Duskwatch Recruiter's is CR 702's "look at" wording, not
        scry) are answerable to their own card's printed order, not this
        method's name.

        `moved_label` and `kept_label` are required, and required for exactly
        that reason: the two destinations live only in the caller, so a
        question published without them tells a client nothing about where
        either half goes and every client is left to guess the scry pair.
        Devourer of Destiny is the card that broke on that guess - its picked
        half stays on *top* and its rest is *exiled*, the opposite of a scry
        on both halves - so the destinations now travel with the question,
        stamped onto `Decision.moved_label` / `Decision.kept_label`.

        Which half is `moved` is the caller's choice and is *not* fixed to
        "the half that leaves the library": `moved` is the pile the player
        actively opts into. For a scry that is the bottomed cards; for
        Devourer's "you may put one of those cards back on top" it is the one
        card put back. Keeping it that way is what makes the empty answer -
        what an unscripted or declining player gives - the correct decline for
        both. See `Decision.moved_label`.
        """
        if isinstance(player, str):
            player = self.player(player)
        if count <= 0:
            return [], []

        looked_at = self._look_at_top(player, count)
        answer = self.ask(
            Decision(
                kind=DecisionKind.SCRY,
                player=player.username,
                prompt=prompt or f"look at the top {count} card(s)",
                source=source,
                amount=count,
                cards=tuple(state.id for state in looked_at),
                moved_label=moved_label,
                kept_label=kept_label,
            )
        )
        assert isinstance(answer, CardSplit)
        moved, rest = self._split_top(player, looked_at, answer)
        library = player.library
        for state in looked_at:
            if state in library:
                library.remove(state)
        return moved, rest

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

    def flip_coin(self) -> bool:
        """CR 705.1: flip a coin, "a two-sided object with ... equal likelihood
        that either side lands face up." Returns `True` for a win (heads, by
        this engine's own arbitrary but fixed convention - CR 705.1 leaves
        which side is which to the players, and nothing here distinguishes
        them further than win/lose the way `condition_matches`'s callers
        already read "if you win/lose the flip").

        Seeded from `shuffle_seed` and `coin_flips_performed`, the same
        reproducibility convention `shuffle` uses for its own randomness (see
        that method's own docstring) - a scenario asserting on the result of
        a flip needs a fixed outcome, not a live coin.
        """
        rng = Random(f"{self.shuffle_seed}:{self.coin_flips_performed}:coin")  # noqa: S311
        self.coin_flips_performed += 1
        return rng.random() < 0.5

    def search_library(
        self,
        player: Player | str,
        matches: Callable[[CardState], bool],
        *,
        count: int = 1,
        optional: bool = False,
        shuffle: bool = True,
        source: str | None = None,
        zone: Zone = Zone.LIBRARY,
    ) -> list[CardState]:
        """Search one of a player's zones, take what was found out of it, and
        (library only) shuffle.

        CR 701.23a: "To search for a card in a zone, look at all cards in that
        zone (even if it's a hidden zone) and find a card that matches the given
        description." The whole zone is visible to the searcher, which is why
        this takes a predicate over every card rather than looking only at the
        top. `zone` names *which* zone (CR 701.23a's search is always of one
        zone at a time) and defaults to the library, this method's original and
        still most common use - `search_library` keeps its name so every
        existing library search stays untouched, rather than being renamed out
        from under them for a widening only some callers need.

        The Stone Brain's and Surgical Extraction's own "search its owner's
        graveyard, hand, and library" is not a hidden search of all three zones
        at once; it is CR 701.23a's ordinary single-zone search, run three
        times, once per zone this same predicate applies to unchanged.

        **One choice, over every candidate at once.** CR 701.23a's searcher
        looks at the whole zone and *finds a card*: the choice is which of the
        matching cards they want, made once. This used to be a walk - each
        matching card in zone order got its own yes/no question - and that is a
        different game. A walk never lets the searcher say what they want, only
        decline what they are shown, so a Wooded Foothills activated to fetch a
        Breeding Pool could only decline candidates until Breeding Pool happened
        to come up next, and after CR 701.24b's shuffle "next" is arbitrary. The
        live bug this closes is exactly that: one decline, and the seat was
        handed a basic Forest.

        So the question is a single `DecisionKind.CHOOSE_CARDS` carrying every
        legal candidate in `cards`, with `card_labels` naming them (the zone may
        be hidden, so a client cannot look the ids up itself), and the answer
        names the cards the searcher wants. It is asked at all only when there
        is something to decide: a mandatory search whose candidates do not
        outnumber `count` has exactly one legal answer and is taken without
        asking, the same way `Game.ask` forces a question with one option.

        CR 701.23b is the rule that makes a search *declinable*: "If a player is
        searching a hidden zone for cards with a stated quality ... that player
        isn't required to find some or all of those cards even if they're
        present in that zone." That is `optional=True`, and it is asked as an
        inexact question (`exact=False`): any number of the candidates from zero
        up to `count` is a legal answer, so finding nothing is a real answer a
        searcher may give.

        CR 701.23d is the other branch: "If a player is searching a hidden zone
        simply for a quantity of cards, such as 'a card' or 'three cards,' that
        player must find that many cards (or as many as possible, if the zone
        doesn't contain that many)." That is `optional=False`, asked as an exact
        question for `min(count, len(candidates))` cards - "as many as possible"
        - so the searcher chooses *which*, never *whether*.

        CR 400.2 makes the graveyard, battlefield, stack and exile public zones
        and the library and hand hidden ones, and this method deliberately does
        not branch on that. What CR 400.2 changes is whether CR 701.23b/701.23d
        apply at all - both are written about hidden zones - not whether
        CR 701.23a's find is a choice; a search of a public zone that matches
        more cards than it takes is still the searcher picking which, and
        picking is the same question with the same shape. The hidden/public
        difference is therefore carried by `optional`, which the caller sets
        from its own card's text, rather than inferred from the zone here: a
        public-zone search is simply never `optional=True`, and every
        zone-widened caller in this pool already passes `optional=False`.

        The default answer, when nobody is scripted or provided, is
        `Decision.default_cards`: the candidates in zone order, up to `count`.
        That is what this engine found when the search was a walk whose `MAY`
        questions defaulted to yes, so an unscripted fetch still fetches.

        CR 701.23e: nothing is revealed unless the effect says so, so nothing is
        revealed here.

        The cards found are removed from `zone` and returned; the caller
        decides where they go. `shuffle` only ever does anything when
        `zone` is `Zone.LIBRARY` - CR 701.24b's post-search shuffle is a
        library-specific rule with no hand or graveyard equivalent - so a
        caller searching another zone can leave it at its default with no
        effect.
        """
        with self._id_allocator_scope():
            if isinstance(player, str):
                player = self.player(player)

            candidates = [state for state in player.cards_in(zone) if matches(state)]
            limit = min(count, len(candidates))
            found: list[CardState] = candidates[:limit]
            if candidates and (optional or len(candidates) > limit):
                chosen = self.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=(
                            f"choose up to {limit} card(s) to find while searching "
                            f"your {zone.value}"
                            if optional
                            else f"choose {limit} card(s) to find while searching your {zone.value}"
                        ),
                        source=source,
                        amount=limit,
                        cards=tuple(state.id for state in candidates),
                        card_labels=tuple(state.name for state in candidates),
                        exact=not optional,
                        default_cards=tuple(state.id for state in found),
                    )
                )
                assert isinstance(chosen, tuple)
                by_id = {state.id: state for state in candidates}
                found = [by_id[card_id] for card_id in chosen]

            for state in found:
                player.cards_in(zone).remove(state)
            if shuffle and zone is Zone.LIBRARY:
                self.shuffle_library(player)
            return found

        # -- revealing, and cards outside the game (CR 701.20, CR 400.11) --------

    def reveal(self, card_state: CardState, source: str | None = None) -> CardState:
        """Show one card to all players (CR 701.20a), and record that it was shown.

        "To reveal a card, show that card to all players for a brief time."
        CR 701.20b: "Revealing a card doesn't cause it to leave the zone it's
        in" - so nothing moves here, and a caller that also moves the card does
        that separately, in the order its own text states.

        The reveal is credited to the card's owner, which is who is holding it
        in every case the rules reach: a card revealed out of a hidden group is
        revealed by the player whose group it is (their hand, their library,
        their sideboard outside the game, CR 400.11a). `Reveal` explains why
        exactly one entry is appended per card shown, and why that matters for
        anything downstream deciding what an opponent may see.
        """
        with self._id_allocator_scope():
            self.reveals.append(
                Reveal(
                    card_id=card_state.id,
                    card_name=card_state.name,
                    revealed_by=card_state.owner or "",
                    zone=card_state.zone,
                    source=source,
                )
            )
            return card_state

    def face_up_cards_in_exile(
        self,
        owner: str | None = None,
        matches: Callable[[CardState], bool] | None = None,
    ) -> list[CardState]:
        """Exiled cards that are face up (CR 406.3), optionally narrowed.

        CR 406.3: "Exiled cards are, by default, kept face up and may be
        examined by any player at any time. Cards 'exiled face down' can't be
        examined by any player except when instructions allow it." So a
        face-down exiled card is not merely hidden - it is not a card an effect
        that says "choose a face-up card in exile" may be pointed at, and
        CR 406.3a adds that it "has no characteristics" at all, which means
        asking whether it is an artifact has no answer to give.

        `owner` filters by CR 108.3 ownership, which is what a "you own" clause
        needs - deliberately not by controller: exile is a shared zone and the
        object in it may be one an opponent put there.
        """
        return [
            state
            for state in self.exile
            if not state.face_down
            and (owner is None or state.owner == owner)
            and (matches is None or matches(state))
        ]

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
        with self._id_allocator_scope():
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
                    # CR 121.2's individual draw, counted before it is announced.
                    # `machines/triggers` answers "you draw your third card in a
                    # turn" by reading `cards_drawn_this_turn` *while* the event
                    # below is being dispatched, so the count has to already
                    # include this card or the ordinal would never match.
                    self.cards_drawn_this_turn[player.username] = (
                        self.cards_drawn_this_turn.get(player.username, 0) + 1
                    )
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

    def exchange_life_totals(self, a: Player | str, b: Player | str) -> int:
        """Two players exchange life totals (CR 701.12a, CR 701.12c).

        CR 701.12a: "A spell or ability may instruct players to exchange
        something (for example, life totals ...) as part of its resolution.
        When such a spell or ability resolves, if the entire exchange can't
        happen, no part of the exchange occurs." `Player.exchange_life_totals`
        is where that all-or-nothing decision lives, together with CR 119.7 and
        CR 119.8's two reasons for refusing; this is the wrapper a resolving
        spell or ability actually reaches, the counterpart of `gain_life`.

        The **events** are this method's own job. CR 701.12c makes the exchange
        gains and losses ("each player gains or loses the amount of life
        necessary to equal the other player's previous life total"), so a
        trigger watching "whenever a player gains life" (CR 119.9) or loses it
        must see them - and the `Player` primitive adjusts the totals without
        emitting anything, exactly as `Player.gain_life` does under
        `Game.gain_life`. One event per player who actually moved: a player
        whose total was already equal gained and lost nothing, and CR 603.2g
        gives a trigger nothing to fire on there.

        No replacement effects are applied to the halves. CR 701.12c does say
        "Replacement effects may modify these gains and losses", and this does
        not do that yet - routing the halves back through `Game.gain_life`
        would re-ask CR 119.7 *after* the all-or-nothing decision had already
        been made on the pre-replacement amounts, which is the wrong order. It
        is recorded in `docs/engine-coverage.md` rather than half-built here.

        Returns the life **this** player - `a` - lost by the exchange, negative
        if they gained: Mister Negative's "If you lost life this way, draw that
        many cards" is the question, and it is asked from one side.
        """
        if isinstance(a, str):
            a = self.player(a)
        if isinstance(b, str):
            b = self.player(b)

        before = {a.username: a.life, b.username: b.life}
        lost = a.exchange_life_totals(b)
        for player in (a, b):
            moved = player.life - before[player.username]
            if moved > 0:
                self.emit(GameEvent(event=TriggerEvent.GAINS_LIFE, player=player.username))
            elif moved < 0:
                self.emit(GameEvent(event=TriggerEvent.LOSES_LIFE, player=player.username))
        return lost

    def life_gain_prohibited(self, username: str) -> str | None:
        """Why this player can't gain life right now, or None (CR 119.7).

        CR 119.7: "If an effect says that a player can't gain life ..." - this
        is where that effect is found. Leyline of Punishment's "Players can't
        gain life." changes no characteristic of any object, so CR 613's layers
        have nothing to write and `machines/layers.py` is the wrong home; the
        effect belongs to CR 611.1's third category, "affects players or the
        rules of the game", and is read where the rules ask the question.

        The battlefield is rescanned on every call rather than cached, because
        CR 604.2 bounds a static ability's continuous effect to while its
        source is on the battlefield and CR 611.3a says such an effect "isn't
        'locked in'". A Leyline destroyed mid-turn stops prohibiting at once.

        The shapes in the pool are symmetric - "Players can't gain life"
        catches its own controller too - so no controller comparison is made.
        A sentence that prohibits life gain in a shape
        `_LIFE_GAIN_PROHIBITION_RE` cannot read records a `LayerNotice` and is
        **not** treated as permission, the same way `_activation_prohibition`
        fails closed on an unreadable prohibition.
        """
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not _LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE.search(text):
                    continue
                if not _LIFE_GAIN_PROHIBITION_RE.match(text):
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                return f"{username} can't gain life: {source.name} says so (CR 119.7, CR 611.1)"
        return None

    def add_counters(self, permanent: CardState, kind: str, amount: int = 1) -> int:
        """Put counters on a permanent, replacement effects included (CR 122.1).

        CR 122.6: "Some spells and abilities refer to counters being put on an
        object. This refers to putting counters on that object while it's on the
        battlefield and also to an object that's given counters as it enters the
        battlefield" - so both routes reach the same replaceable event, which is
        what lets Doubling Season double a Kalonian Hydra's four printed counters
        as it arrives.
        """
        with self._id_allocator_scope():
            if amount <= 0:
                return permanent.counter_count(kind)

            event = ReplaceableEvent(
                kind=EventKind.ADD_COUNTERS, card=permanent, counter_kind=kind, amount=amount
            )
            apply_replacements(self, event)
            if event.amount <= 0:
                return permanent.counter_count(kind)
            new_total = permanent.add_counters(kind, event.amount)
            if str(kind) == str(Counter.LORE):
                self._emit_lore_counters_added(permanent, event.amount)
            self._emit_counters_put(permanent, str(kind), event.amount)
            return new_total

    def _emit_counters_put(self, permanent: CardState, kind: str, amount: int) -> None:
        """CR 122.6's generic "counters are put on this object" event.

        "Some spells and abilities refer to counters being put on an object.
        This refers to putting counters on that object while it's on the
        battlefield and also to an object that's given counters as it enters
        the battlefield" - Basking Broodscale's and Emperor of Bones'
        "Whenever one or more +1/+1 counters are put on this creature".

        One event per instruction, carrying the whole amount. CR 603.2c: "An
        ability triggers only once each time its trigger event occurs. However,
        it can trigger repeatedly if one event contains multiple occurrences" -
        and "one or more counters" is not several occurrences, it is one
        occurrence with a count, so two counters arriving together fire the
        ability once. The count travels on `GameEvent.amount` for any clause
        that later refers back to how many.

        The kind travels too (CR 122.1 leaves the set of counter kinds open, so
        it is a plain string), which is what stops a charge counter firing a
        condition that names +1/+1.

        Only a permanent is asked: the conditions in this pool are all
        self-referential ("this creature"), and CR 110.1 makes an object a
        permanent only while it is on the battlefield.
        """
        if amount <= 0 or permanent.zone is not Zone.BATTLEFIELD:
            return
        # CR 613.5: the object's characteristics for this event are the
        # computed ones, not the printed type line (CR 613.1's starting
        # point) - a land animated by earthbend is a creature only there.
        chars = self.characteristics_of(permanent)
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.COUNTERS_PUT,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_controller=permanent.controller,
                subject_card=permanent.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                counter_kind=kind,
                amount=amount,
                player=permanent.controller,
            )
        )

    def return_to_hand(self, permanent: CardState) -> CardState:
        """Return a permanent to its owner's hand (CR 701.19a is "return").

        CR 111.8 refuses this for a token that has already left the battlefield,
        which is the rule that stops a Raise Dead or a flicker effect recurring a
        dead token: "If such a token would change zones, it remains in its
        current zone instead."

        Emits `TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND` when the move was
        actually from the battlefield - the third of the three "left the
        battlefield" events alongside `DIES` and `LEAVES_BATTLEFIELD_TO_EXILE`,
        added for Static Prison's "until this enchantment leaves the
        battlefield" (CR 610.3c's kind of one-shot return): a bounced
        Static Prison is exactly as much a departure as a destroyed or exiled
        one, and nothing watched this path before.
        """
        with self._id_allocator_scope():
            if move_refused(permanent, Zone.HAND) is not None:
                return permanent
            was_on_battlefield = permanent in self.battlefield
            if was_on_battlefield:
                self._note_left_battlefield(permanent)
            self._take_out_of_every_zone(permanent)
            self.combat.remove(permanent.id)  # CR 506.4
            self._owner_of(permanent).add(permanent, Zone.HAND)
            if was_on_battlefield:
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
                        subject_id=permanent.id,
                        subject_name=permanent.name,
                        subject_controller=permanent.controller,
                        subject_card=permanent.card,
                        player=permanent.controller,
                    )
                )
                # CR 603.6c: the generic departure, alongside the destination-
                # specific event just above - see `Game.put_into_graveyard`'s
                # matching emit for why both fire.
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=permanent.id,
                        subject_name=permanent.name,
                        subject_controller=permanent.controller,
                        subject_card=permanent.card,
                        player=permanent.controller,
                    )
                )
            return permanent

    def put_cards_into_library(
        self, cards: Sequence[CardState], *, to_bottom: bool = False
    ) -> list[CardState]:
        """Move cards into their owners' libraries as one instruction (CR 401.1).

        Each card goes into its own owner's library - CR 401.1's "when a game
        begins, each player's deck becomes their library" is a per-player zone,
        and a card put into a library goes into the library of the player who
        owns it. `to_bottom` picks which end; the list order is kept either way,
        so the first card named ends up nearest the top when going to the top.

        One `ExtraTriggerEvent.PUT_INTO_LIBRARY` event is raised for the whole
        instruction, carrying how many cards it moved. CR 603.2c: an ability
        triggers once per event, and "whenever one or more cards are put into a
        library from anywhere" (Wan Shi Tong, All-Knowing) is one event with a
        count, not one event per card - so Brainstorm putting two cards back is
        a single trigger.

        **A card already in a library is not put into one.** Scry and surveil
        (CR 701.22a, CR 701.25a) reorder cards that never left the zone, so
        nothing was "put into" a library and no event is raised for them; such
        a card is still moved to the requested end, but it does not count
        towards the event and, if every card was already there, no event is
        raised at all.

        A card leaving the battlefield or a graveyard on its way raises those
        departures too, the same events the single-card moves already raise:
        CR 603.6c's `LEAVES_THE_BATTLEFIELD` per permanent, and CR 603.10a's
        `LEAVES_GRAVEYARD` batched per graveyard alongside the library event.

        Run under `_id_allocator_scope`, the same as `put_into_graveyard`/
        `exile_permanent`/`return_to_hand`/`ante`: `CardState.move_to` mints a
        fresh `zone_change_stamp` per card and `emit` below may put a
        triggered ability on `pending_triggers`, both persisted ids that need
        to be deterministic for a decoded replay to reproduce them - found by
        T10's own round-trip/replay invariant the moment a scenario actually
        tucked a permanent off the battlefield through this method, which no
        earlier scenario had exercised.
        """
        with self._id_allocator_scope():
            moved: list[CardState] = []
            newly_in_library: list[CardState] = []
            left_battlefield: list[CardState] = []
            by_graveyard: dict[str, list[CardState]] = {}
            for card_state in cards:
                if move_refused(card_state, Zone.LIBRARY) is not None:
                    continue
                was_in_library = card_state.zone is Zone.LIBRARY
                graveyard_owner = self._graveyard_owner_of(card_state)
                if card_state in self.battlefield:
                    self._note_left_battlefield(card_state)
                    self._detach_dependents(card_state)
                    left_battlefield.append(card_state)
                self._take_out_of_every_zone(card_state)
                self.combat.remove(card_state.id)  # CR 506.4
                owner = self._owner_of(card_state)
                owner.add(card_state, Zone.LIBRARY)
                moved.append(card_state)
                if not was_in_library:
                    newly_in_library.append(card_state)
                if graveyard_owner is not None:
                    by_graveyard.setdefault(graveyard_owner, []).append(card_state)
            if not to_bottom:
                # `Player.add` appends, which is the bottom (CR 401.2's single
                # face-down pile, ordered top-first here). Lift this instruction's
                # cards back out and put them on the front, keeping the order they
                # were named in.
                for card_state in reversed(moved):
                    library = self._owner_of(card_state).library
                    library.remove(card_state)
                    library.insert(0, card_state)
            for gone in left_battlefield:
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=gone.id,
                        subject_name=gone.name,
                        subject_controller=gone.controller,
                        subject_card=gone.card,
                        player=gone.controller,
                    )
                )
            for owner_name, gone_cards in by_graveyard.items():
                self._emit_left_graveyard(owner_name, gone_cards, exiled=False)
            if newly_in_library:
                self.emit(
                    GameEvent(
                        event=ExtraTriggerEvent.PUT_INTO_LIBRARY,
                        player=self._owner_of(newly_in_library[0]).username,
                        amount=len(newly_in_library),
                    )
                )
            return moved

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

        The zone-change half of that sentence is CR 400.7: an object that
        moved to a new zone and back is "a new object with no memory of, or
        relation to, its previous existence", even though this engine keeps
        the same `CardState.id` across the move (an Ephemerate-style blink
        while a single-target removal spell targeting the blinked permanent
        sits on the stack is the reported shape - `find_by_id` alone cannot
        tell the two incarnations apart, only `zone_change_stamp` can).
        `target.zone_change_stamp` is `None` when no live object was on hand
        to read one from at announcement (`TargetRef.zone_change_stamp`'s own
        docstring), and a reference this method cannot judge is treated as
        still legal rather than made to fizzle on a guess - the same posture
        already taken for an unparsed restriction, just below.

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

        if (
            isinstance(thing, CardState)
            and target.zone_change_stamp is not None
            and thing.zone_change_stamp != target.zone_change_stamp
        ):
            # CR 608.2b/CR 400.7: the object `find_by_id` just found is a new
            # object, not the one this reference named at announcement.
            return None

        source_card = self._source_card_of(spell)
        if source_card is not None and self.protection_refusal(thing, source_card) is not None:
            # CR 702.16b, checked again here because protection can be gained
            # after a spell was legally announced.
            return None

        if isinstance(spell, AbilityOnStack):
            # `x_value` substituted first, the same reason `activate_ability`
            # and `create_continuous_effect_of_ability` both do it before
            # building a profile off this ability's text - The Mycosynth
            # Gardens' own "target nontoken artifact you control with mana
            # value X" is a real restriction once X is known, not an
            # unreadable one, and a re-check that used the literal "X" would
            # judge every legal target illegal (`comparison_value=None`
            # matches nothing) rather than treat the restriction as read.
            ability_text = (
                substitute_x(spell.ability.text, spell.x_value)
                if isinstance(spell.ability, ActivatedAbility) and "{X}" in spell.ability.cost
                else spell.ability.text
            )
            profile = profile_for_text(ability_text)
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

    def targetable_objects(self) -> list[Any]:
        """Every object a target could name right now: every player, every
        card in a public zone (CR 400.2 - the battlefield, every graveyard,
        every exile), and every spell or ability on the stack.

        This is engine knowledge, not API knowledge - moved out of
        `magic_cards_model_api.affordances._all_targetables`, which hardcoded
        the same walk, so `legal_targets` below and any future caller share
        one answer to "what could a target possibly name" instead of the api
        maintaining a second copy that could drift from the engine's own
        rules. A hand or library card is deliberately absent - nothing in
        this pool targets one, and enumerating a hidden zone is exactly what
        the visibility layer exists to prevent.
        """
        things: list[Any] = list(self.players)
        for zone in (Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.EXILE):
            for state in self.shared_zones.get(zone, []):
                if isinstance(state, CardState):
                    things.append(state)
        # The battlefield and exile are shared zones (CR 400.1: "The other
        # zones are shared by all players"), already walked once each above
        # via `self.shared_zones` - `Player.zones` never holds either one.
        # Only the graveyard is a real per-player zone. `Player.cards_in` was
        # `zones.setdefault(zone, [])`, so asking it for `Zone.BATTLEFIELD`/
        # `Zone.EXILE` here used to both return nothing (every permanent and
        # exiled card was already added above, so nothing was lost) and
        # permanently add two spurious empty keys to every player's own
        # serialized `zones` as a side effect of a read-only query - a
        # documented pure query mutating the game it was asked about. It
        # raises `SharedZoneError` now rather than answering at all.
        for player in self.players:
            things.extend(player.cards_in(Zone.GRAVEYARD))
        things.extend(self.stack)
        return things

    def _announcement_profile(
        self,
        state: CardState,
        *,
        ability_index: int | None,
        modes: list[int] | None,
        x_value: int | None,
    ) -> TargetingProfile:
        """What `state` may legally target, for an announcement that has not
        happened yet - `legal_targets`'s own reading of CR 601.2c/700.2c,
        before any `Casting` or `AbilityOnStack` exists to ask.

        The same three-way read `magic_cards_model_api.affordances._profile_for`
        used to hardcode: an activated ability's own effect text names the
        profile when `ability_index` is given; a modal card's *chosen* modes
        name it when `modes` is given (CR 700.2c: an unchosen mode's targets do
        not apply); the whole card's text, with `x_value` substituted first
        (CR 107.3a), otherwise. Kept in the engine so `legal_actions` and any
        other caller ask the same question the api's UI hints already did,
        rather than the api holding the only copy of how to ask it.
        """
        if ability_index is not None:
            ability = self.activated_abilities(state)[ability_index]
            effect = getattr(ability, "effect", None) or getattr(ability, "text", "")
            return profile_for_text(substitute_x(effect, x_value))
        modal = modal_profile(state.card)
        if modes and modal is not None:
            chosen = modal.resolve(modes)
            profile, _owners = profile_for_modes_with_owners(state.card, chosen, x_value)
            return profile
        if modal is None and x_value is not None and state.card.oracle_text:
            return profile_for_text(substitute_x(state.card.oracle_text, x_value))
        return targeting_profile(state.card)

    def legal_targets(
        self,
        source: CardState,
        caster: str,
        *,
        ability_index: int | None = None,
        modes: list[int] | None = None,
        x_value: int | None = None,
    ) -> tuple[tuple[Any, ...], ...]:
        """Every legal target for each requirement `source` would announce
        right now, one tuple per requirement (CR 601.2c) - the enumerating
        cousin of `legal_target` above, which only rechecks one target already
        chosen (CR 608.2b).

        `TargetRequirement.rejects` is the single predicate both this and
        `legal_target` call, so a candidate list built here can never disagree
        with what an actual announcement would accept or refuse - the same
        argument `could_pay_mana_cost` already makes for `auto_tap`
        (`machines/cost.py`).

        Returns `()` when the profile could not be read or names no
        requirements at all (an unmodelled targeting phrase, or a card with
        none) - an empty tuple of tuples rather than a tuple of empty ones, so
        a caller can tell "nothing here targets" from "every requirement
        happens to have no legal candidate right now".
        """
        profile = self._announcement_profile(
            source, ability_index=ability_index, modes=modes, x_value=x_value
        )
        if not profile.understood or not profile.requirements:
            return ()
        pool = self.targetable_objects()
        result: list[tuple[Any, ...]] = []
        for requirement in profile.requirements:
            legal = tuple(
                thing
                for thing in pool
                if not (thing is source and source.zone is not Zone.STACK)
                and requirement.rejects(thing, caster, self, source.id) is None
            )
            result.append(legal)
        return tuple(result)

    def legal_actions(self, player: str, *, pending: PendingDecision | None = None) -> list[Action]:
        """Every legal action `player` could take right now -
        `machines.legal_actions.legal_actions` bound here, since three of
        `machines/cost.py`'s own docstrings already cite it as `Game.
        legal_actions`. See that module's own docstring for what "legal"
        means (never gated on affordability), what a pending `Decision` does
        to the answer, and what is deliberately not enumerated.
        """
        from ..machines.legal_actions import legal_actions as _legal_actions

        return _legal_actions(self, player, pending=pending)

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

        A **non-modal** spell whose own mana cost has `{X}` (Postmortem
        Lunge's "target creature card with mana value X") gets the same
        substitution `machines/casting.Casting.targeting` already applies at
        announcement - `targeting_profile(spell.card)` alone never resolves a
        bare "X" (CR 107.3a's value is not part of the card's own printed
        text), so without this the CR 608.2b recheck this method exists for
        would refuse every target forever, on a card the caster legally
        targeted moments earlier.

        A **split card's** (CR 709) chosen half reads its own text too, the
        same case `Casting.targeting`'s own docstring explains -
        `targeting_profile(spell.card)` always reads the combined printing's
        *front* half (`Card.front_oracle_text`), never the half actually
        cast. Left unfixed, this recheck refused every legal target on a
        split card's back half forever - the CR 608.2b recheck this method
        exists for judging the back half's own restriction against the
        front half's - found auditing Repudiate // Replicate's Replicate
        half ("Create a token that's a copy of target creature you
        control.") against Wear // Tear's own front-face-only "target
        artifact" requirement. `spell.oracle_text` already reads the chosen
        half while the spell is on the stack (`CardState.up_face`), so this
        only has to stop *discarding* that in favour of the combined
        printing - `spell.card.layout is Layout.SPLIT` scopes it the same
        way `CardState.face_played`'s own docstring does, so a modal-DFC or
        Adventure spell (already read correctly through `spell.mana_cost`'s
        `{X}` branch or the plain fallback) is untouched.
        """
        record = self.cast_records.get(spell.id)
        if record is not None and record.modes:
            try:
                return profile_for_modes(spell.card, record.modes, record.x_value or None)
            except ValueError:
                # Not a modal card after all; fall through to its plain text.
                pass
        if spell.card.layout is Layout.SPLIT and spell.face_played is not None:
            return profile_for_text(spell.oracle_text)
        if record is not None and "{X}" in (spell.mana_cost or ""):
            return profile_for_text(substitute_x(spell.oracle_text, record.x_value))
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

        The quality is matched by `source_has_quality`, which reads both
        flavours CR 702.16a names - "This quality is usually a color (as in
        'protection from black') but can be any characteristic value or
        information" - so a colour quality refuses a targeting spell here
        exactly as it prevents that source's damage in `protection_from_damage`.
        Reading only the card-type half here was a real split: Lightning Bolt
        could still be *announced* at a creature with protection from red, and
        only its damage was prevented on resolution, which is CR 702.16e doing
        CR 702.16b's job.

        A quality this engine cannot read is not enforced - see
        `docs/engine-coverage.md`.

        A **player** target is answered by `Player.protection_refusal`, which
        matches the card-name flavour off `Player.protection_from` (Runed
        Halo's CR 614.12a chosen name), unioned with the grants currently on
        the battlefield - see `player_protection_qualities`.
        """
        if isinstance(target, Player):
            return self._player_protection_refusal(target, source)
        if not isinstance(target, CardState):
            return None
        for quality in self._effective_protection_qualities(target):
            if self.source_has_quality_of_card(source, quality):
                return (
                    f"{target.name} has protection from {quality}, so {source.name} "
                    f"cannot target it (CR 702.16b)"
                )
        return None

    def _player_protection_refusal(self, target: Player, source: "Card") -> str | None:
        """Why a *player's* protection stops `source` targeting them (CR 702.16b).

        Two sources of quality, unioned: what the player carries on
        `Player.protection_from` - the card-name flavour, which
        `Player.protection_refusal` matches - and what the battlefield is
        granting them right now (`player_protection_qualities`), which is read
        fresh so the grant ends with its permanent (CR 604.2).
        """
        refusal = target.protection_refusal(source)
        if refusal is not None:
            return refusal
        for quality in self.player_protection_qualities(target.username):
            if quality == source.name or self.source_has_quality_of_card(source, quality):
                return (
                    f"{target.username} has protection from {quality}, so {source.name} "
                    f"cannot target them (CR 702.16b)"
                )
        return None

    def player_protection_qualities(self, username: str) -> list[str]:
        """Every quality the battlefield currently grants this *player*
        protection from (CR 702.16a, CR 613.10).

        CR 613.10: "Some continuous effects affect players rather than objects.
        For example, an effect might give a player protection from red." That
        is this, and it is deliberately **not** a CR 613 layer: the layers write
        characteristics onto objects, and a player is not an object, so
        `machines/layers.py`'s permanent-only sweep has nowhere to put it.

        Read fresh from the battlefield on every call rather than latched onto
        the player, because CR 604.2 bounds a static ability's continuous effect
        to while its source is on the battlefield - a Runed Halo that leaves
        must take its protection with it, and a value written once onto
        `Player.protection_from` would outlive its source.
        """
        qualities: list[str] = []
        for permanent in self.battlefield:
            if self.controller_of(permanent).username != username:
                continue
            for line in (permanent.card.oracle_text or "").split("\n"):
                if not _PLAYER_PROTECTION_FROM_CHOSEN_NAME.match(line.strip()):
                    continue
                chosen = permanent.choice
                # The line says "the chosen **card name**", so only a
                # CR 614.12a card-name choice answers it - a colour choice on
                # some other permanent is not this quality.
                if chosen is None or chosen.kind is not ChoiceKind.CARD_NAME:
                    continue
                if chosen.value and chosen.value not in qualities:
                    qualities.append(chosen.value)
        return qualities

    def source_has_quality_of_card(self, source: "Card", quality: str) -> bool:
        """`source_has_quality` for a bare `Card` rather than a `CardState`.

        The targeting half of CR 702.16b is asked about the *card* behind a
        spell or an ability's source, while the damage half (CR 702.16e) is
        asked about a `CardState`. Both read the same two flavours of quality,
        so the reading lives in one place and this is the adapter.
        """
        wanted = quality.strip().lower()
        card_type = _card_type_named(wanted)
        if card_type is not None:
            return card_type in source.types
        color = _COLOR_WORDS.get(wanted)
        if color is not None:
            return color in source.colors
        return False

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

    def _apply_damage_to_permanent(self, permanent: CardState, amount: int) -> None:
        """What damage does to a permanent, by what the permanent is (CR 120.3).

        CR 120.3 opens with "Damage may have **one or more** of the following
        results, depending on ... the characteristics of the damage's recipient"
        - so this is a list of independent results, not a dispatch table with a
        fallback, and a permanent that is both a creature and a planeswalker
        (an animated Gideon) takes both.

        - **CR 120.3c** - "Damage dealt to a planeswalker causes that many
          loyalty counters to be removed from that planeswalker." **CR 306.8**
          says the same from the planeswalker's side. This is a result of the
          damage event itself and happens now; no state-based action is
          involved. The only state-based action here is the one *after* it -
          CR 306.9 / CR 704.5i put a planeswalker at 0 loyalty into its owner's
          graveyard, which `check_state_based_actions` already does.
        - **CR 120.3e** - "Damage dealt to a creature by a source with neither
          wither nor infect causes that much damage to be marked on that
          creature." Marking is the *creature* result, which is why it is not
          this method's default: marking damage on anything else invents
          bookkeeping the rules never asked for, and it is exactly what hid the
          missing CR 120.3c - a planeswalker attacked for lethal came out of
          combat with `damage=9` and its nine loyalty counters intact.

        Anything that is neither takes the damage and nothing happens, which is
        CR 120.3's own answer: no listed result applies to it. Damage to a
        battle (CR 120.3h, defense counters) is the one result still missing,
        because the battle card type is not modelled at all - see
        `docs/engine-coverage.md`.

        Which types those are is CR 613.5's question, so it is asked of the
        computed board rather than the printing: an animated planeswalker is a
        creature only there, and a planeswalker turned into a plain enchantment
        by Song of the Dryads is no longer one there either.
        """
        types = (
            self.characteristics_of(permanent).types
            if permanent.zone is Zone.BATTLEFIELD
            else permanent.types
        )
        if Type.PLANESWALKER in types:
            # CR 120.3c removes "that many" counters, and there may not be that
            # many: `Counters.remove` refuses to take more than are present
            # (CR 118.3), so the removal is clamped to what is on the walker.
            # The excess is not damage that goes anywhere else - CR 702.19f is
            # explicit that even trample's excess cannot reach the player
            # unless the attacker has trample over planeswalkers.
            present = permanent.counter_count(Counter.LOYALTY)
            if present > 0:
                permanent.remove_counters(Counter.LOYALTY, min(amount, present))
        if Type.CREATURE in types:
            permanent.mark_damage(amount)

    def deal_damage(
        self, target: Targetable, amount: int, *, source: "CardState | None" = None
    ) -> int:
        """Deal damage to a permanent or a player, and say how much landed.

        What damage *does* is CR 120.3's list, and it depends on what took it:
        a player loses that much life (CR 120.3a), a planeswalker has that many
        loyalty counters removed (CR 120.3c), a creature has that much damage
        marked on it (CR 120.3e). `_apply_damage_to_permanent` is the whole of
        the permanent half - see it for why marking is not the default.

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
        with self._id_allocator_scope():
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
                self._apply_damage_to_permanent(target, event.amount)
            # CR 613.5: the source's characteristics for this event are the
            # computed ones while it is still a permanent - a land animated
            # by earthbend is a creature only there - and the printed type
            # line otherwise (a spell or ability off the battlefield has
            # nothing for the layer system to compute).
            source_types = source.types if source is not None else None
            source_subtypes = source.subtypes if source is not None else None
            if source is not None and source.zone is Zone.BATTLEFIELD:
                source_chars = self.characteristics_of(source)
                source_types = source_chars.types
                source_subtypes = source_chars.subtypes
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
                    subject_types=source_types,
                    subject_subtypes=source_subtypes,
                    player=target.username if isinstance(target, Player) else None,
                    combat=event.combat,
                    amount=event.amount,
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
        with self._id_allocator_scope():
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
        if shield.excluded_source_subtypes and event.source is not None:
            # CR 609.7b's recheck, against the source's subtypes as they are
            # now. An anonymous source is not excluded by name, so it stays
            # covered - the opposite of `source_quality`'s rule below, and for
            # the same reason: a shield that *names* what it covers cannot
            # match an unknown source, and one that names what it does *not*
            # cover cannot rule an unknown source out.
            subtypes = {
                subtype.lower() for subtype in self.characteristics_of(event.source).subtypes
            }
            if subtypes & {excluded.lower() for excluded in shield.excluded_source_subtypes}:
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

        A permanent's own types and colours are the ones asked about - CR
        613.5's computed board while `source` is still on the battlefield (a
        land animated by earthbend is a creature only there), and the
        printed `CardState` for anything else, which is CR 702.16a's own
        second clause: "any sources not on the battlefield that are of that
        card type" reads the printed characteristics by name.
        """
        wanted = quality.strip().lower()
        types, colors = source.types, source.colors
        if source.zone is Zone.BATTLEFIELD:
            chars = self.characteristics_of(source)
            types, colors = chars.types, chars.colors
        card_type = _card_type_named(wanted)
        if card_type is not None:
            return card_type in types
        color = _COLOR_WORDS.get(wanted)
        if color is not None:
            return color in colors
        return False

    def protection_from_damage(self, event: ReplaceableEvent) -> str | None:
        """Why protection prevents this damage, or None (CR 702.16e).

        "Any damage that would be dealt by sources that have the stated quality
        to a permanent or player with protection is prevented."

        Damage with no known source is never prevented here: CR 702.16e asks
        about the source's qualities, and an anonymous source has none to check.

        The rule says "to a permanent **or player** with protection", so a
        damage event aimed at a player is read the same way, against the
        qualities that player holds (`Player.protection_from`, the card-name
        flavour) and the ones the battlefield grants them right now
        (`player_protection_qualities`).
        """
        if event.kind is not EventKind.DAMAGE or event.source is None:
            return None
        if event.card is None:
            return self._player_protection_from_damage(event)
        for quality in self._effective_protection_qualities(event.card):
            if self.source_has_quality(event.source, quality):
                return (
                    f"{event.card.name} has protection from {quality}, so damage from "
                    f"{event.source.name} is prevented (CR 702.16e)"
                )
        return None

    def _player_protection_from_damage(self, event: ReplaceableEvent) -> str | None:
        """CR 702.16e's player half: damage from a source with the stated
        quality, aimed at a player with protection from it, is prevented."""
        player = event.player
        if player is None or event.source is None:
            return None
        qualities = list(player.protection_from)
        for quality in self.player_protection_qualities(player.username):
            if quality not in qualities:
                qualities.append(quality)
        for quality in qualities:
            if quality == event.source.name or self.source_has_quality(event.source, quality):
                return (
                    f"{player.username} has protection from {quality}, so damage from "
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
        with self._id_allocator_scope():
            if amount < 0:
                raise ValueError("cannot deal negative damage")
            if isinstance(player, str):
                player = self.player(player)
            if amount == 0:
                return player.life
            lost = player.lose_life(amount)
            self.emit(GameEvent(event=TriggerEvent.LOSES_LIFE, player=player.username))
            return lost

    def counter(self, spell: StackObject, *, to_exile: bool = False) -> StackObject:
        """Counter a spell or an ability on the stack: it never resolves (CR 701.6).

        CR 113.9: an activated or triggered ability on the stack is not a spell,
        but it can still be countered by an effect that counters abilities. It
        goes nowhere when it is - there is no card behind it (CR 405.1) - while a
        countered spell is put into its owner's graveyard.

        `to_exile` is Force of Negation's and Delay's own override - "exile it
        instead of putting it into its owner's graveyard" - read by
        `machines/effects.py`'s paired clause parsers off the card's second
        sentence. It moves the card straight to the shared exile zone rather
        than through `put_into_graveyard`'s own CR 614 replacement check,
        because the card was never headed for a graveyard to begin with; the
        card's own text is what is redirecting it, not a separate replacement
        effect watching for the move.

        Countering is a trigger event in its own right (CR 701.6a is the verb,
        CR 603.10e the look back in time), which is why the event is emitted
        after the spell has moved to its graveyard (or exile): the subject is
        found where it went, and the trigger reads it as it last existed on
        the stack.

        **"This spell can't be countered" is enforced here**, and here only.
        CR 113.6g: "An object's ability that states it can't be countered or
        can't be copied functions on the stack", so the ability is live exactly
        while the spell this method was handed is sitting on the stack.
        CR 701.6a is the verb it makes impossible - "to counter a spell or
        ability means to cancel it, removing it from the stack" - so the
        refusal is simply that the removal does not happen: the object is
        returned untouched, still on the stack, and **no** counter event is
        emitted, because nothing was countered for a trigger to watch.

        The guard sits above the `to_exile` branch on purpose. Force of
        Negation's and Delay's "exile it instead of putting it into its owner's
        graveyard" is a rider on the countering, not an alternative to it; if
        the countering cannot happen, there is no graveyard-bound move for the
        rider to redirect, so an uncounterable spell is not exiled either.

        The counterspell that failed is not refused or rewound anywhere - it
        was legally cast and legally resolved (CR 608.2b knows nothing about
        counterability) and simply fails to do the one thing it says.
        """
        with self._id_allocator_scope():
            if spell not in self.stack:
                raise ValueError(f"{spell.name} is not on the stack")
            if cannot_be_countered(spell):
                return spell
            self.stack.remove(spell)
            if isinstance(spell, CardState):
                if to_exile:
                    self._take_out_of_every_zone(spell)
                    self.combat.remove(spell.id)  # CR 506.4
                    spell.move_to(Zone.EXILE)
                    self.exile.append(spell)
                else:
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

    def exile_from_stack(self, spell: CardState) -> CardState:
        """Exile a spell straight off the stack - CR 701.13a's exile verb, a
        different move from `counter`'s CR 701.6a entirely, not a variant of
        it.

        Knowledge Pool's and Possibility Storm's identical opening clause -
        "Whenever a player casts a spell from their hand, that player exiles
        it" - is CR 601.2a's third way a spell can leave the stack besides
        resolving or being countered ("A spell remains on the stack until it
        resolves ... is countered, or a rule or effect moves it elsewhere").
        This is that move, and it is built as its own method rather than a
        call to `counter(spell, to_exile=True)` because that method's
        `to_exile` branch is wrong for this shape in exactly the two ways its
        own docstring warns against:

        - **`counter`'s `cannot_be_countered` guard sits above its `to_exile`
          branch.** CR 113.6g's "can't be countered" disables CR 701.6a's
          counter verb only; exiling is a different verb (CR 701.13a) that
          the same clause says nothing about, so a spell that can't be
          countered is exiled all the same - going through `counter` would
          wrongly let such a spell resolve untouched instead.
        - **`counter` always emits `TriggerEvent.SPELL_IS_COUNTERED`.**
          Nothing here was countered - CR 701.6a's "cancel it" never
          happened, the spell is simply relocated - so emitting that event
          would wrongly fire every "whenever a spell is countered" ability in
          the game for a spell that only left the stack.

        What *is* reused, because it is correct for both moves: the spell is
        taken out of every zone (`_take_out_of_every_zone` - exile and the
        stack are both shared zones, CR 400.1), removed from combat (CR
        506.4 - moot for a spell that was never a permanent, kept for the
        same symmetry `counter` keeps it for), and its `CastRecord` popped
        so a later intervening *if* about how it was cast fails closed
        instead of reading a stale record for an object that, per CR 400.7,
        is now new (`machines/triggers._cast_record_for_clause`).
        `CardState.move_to` already resets `targets` for every destination
        but the stack (CR 400.7), so the exiled spell keeps none - no
        further cleanup is needed for that half.
        """
        with self._id_allocator_scope():
            if spell not in self.stack:
                raise ValueError(f"{spell.name} is not on the stack")
            self.stack.remove(spell)
            self._take_out_of_every_zone(spell)
            self.combat.remove(spell.id)  # CR 506.4
            spell.move_to(Zone.EXILE)
            self.exile.append(spell)
            self.cast_records.pop(spell.id, None)
            return spell

    def destroy(self, permanent: CardState, *, regeneration_allowed: bool = True) -> CardState:
        """Put a permanent into its controller's graveyard.

        `regeneration_allowed=False` is CR 701.19c's prohibition, which a
        caller passes when the effect doing the destroying printed "can't be
        regenerated" (Wrath of God's "Destroy all creatures. They can't be
        regenerated."). CR 701.19c: such effects "cause regeneration shields
        to not be applied" - they do not remove the shield, so an unspent one
        is still standing for the next destruction this turn, which is why
        this is an argument to the destruction rather than a flag stamped on
        the permanent.

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

        Run under `_id_allocator_scope`: `put_into_graveyard` below mints
        `permanent`'s new `zone_change_stamp` (`CardState.move_to`) and may
        emit a "dies" trigger of its own, both persisted ids. `check_state_
        based_actions`' own CR 704.5g/704.5h handling does not call this -
        `_state_based_actions_once` inlines the same `destruction_happens`-
        then-`put_into_graveyard` shape under its own scope instead - so this
        method has no wrapped caller to rely on: the api's `run_state_based_
        actions` calls it directly, once per creature with lethal damage,
        before ever calling `check_state_based_actions` itself
        (`engine_api.py` around line 861).
        """
        with self._id_allocator_scope():
            return self._destroy_impl(permanent, regeneration_allowed=regeneration_allowed)

    def _destroy_impl(
        self, permanent: CardState, *, regeneration_allowed: bool = True
    ) -> CardState:
        """The rest of `destroy` - see its own docstring for why it is split out."""
        if is_indestructible(permanent, self):
            return permanent  # CR 702.12b
        if not self.destruction_happens(permanent, regeneration_allowed=regeneration_allowed):
            return permanent
        return self.put_into_graveyard(permanent)

    def regenerate(self, permanent: CardState) -> None:
        """Create a CR 701.19a regeneration shield on `permanent`.

        "If the effect of a resolving spell or ability regenerates a
        permanent, it creates a replacement effect that protects the permanent
        the next time it would be destroyed this turn." Creating the shield is
        all that happens now - CR 701.19c is explicit that "neither activating
        an ability that creates a regeneration shield nor casting a spell that
        creates a regeneration shield is the same as regenerating a
        permanent", so nothing is tapped, no damage is removed, and nothing is
        taken out of combat until the shield is actually spent
        (`machines/replacement._regeneration_effects`).

        A permanent that is no longer on the battlefield gets no shield: CR
        701.19a protects it against being *destroyed*, and CR 701.8a's
        destruction only ever happens there.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return
        permanent.regeneration_shields += 1

    def destruction_happens(
        self, permanent: CardState, *, regeneration_allowed: bool = True
    ) -> bool:
        """Whether this destruction survives CR 614's replacement effects.

        CR 701.8c: "A regeneration effect replaces a destruction event", and
        CR 614.8 says regeneration is a destruction-replacement effect whose
        "instead" is implicit. Umbra armor (CR 702.89a) is the same shape
        without the counters. Both need the destruction to be a *replaceable
        event* in its own right rather than the graveyard move it would
        otherwise become, which is why this is raised before
        `put_into_graveyard` and separately from the `ZONE_CHANGE` that
        follows it.

        False means the destruction was called off and the permanent stays on
        the battlefield - nothing moves, nothing dies, no trigger fires.
        """
        event = apply_replacements(
            self,
            ReplaceableEvent(
                kind=EventKind.DESTROY,
                card=permanent,
                player=self.controller_of(permanent),
                regeneration_allowed=regeneration_allowed,
            ),
        )
        return event.happens

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

        Run under `_id_allocator_scope`, the same as `destroy` just above:
        `put_into_graveyard` mints `permanent`'s new `zone_change_stamp` and
        may emit a "dies" trigger of its own, both persisted ids - found
        unscoped by T10's round-trip/replay invariant, which is what a
        sacrifice minting a plain `uuid4()` here looks like once a decoded
        replay is asked to reproduce it.
        """
        with self._id_allocator_scope():
            return self._sacrifice_impl(permanent)

    def _sacrifice_impl(self, permanent: CardState) -> CardState:
        """The rest of `sacrifice` - see its own docstring for why it is split out."""
        if permanent not in self.battlefield:
            raise ValueError(f"{permanent.name} is not a permanent on the battlefield")
        # CR 701.21a names the permanent's controller as the player who
        # sacrifices it, so the record is kept under the controller it still
        # has here, before the move to the graveyard takes it away. Recorded
        # alongside the event rather than instead of it: the event is what
        # CR 603.10a's look-back triggers watch, and this is what CR 603.4's
        # "you sacrificed a permanent this turn" clause reads afterwards.
        sacrificer = permanent.controller
        if sacrificer is not None:
            self.permanents_sacrificed_this_turn[sacrificer] = (
                self.permanents_sacrificed_this_turn.get(sacrificer, 0) + 1
            )
        # CR 613.5: the sacrificed permanent's characteristics for this event
        # are the computed ones (a land animated by earthbend is a creature
        # only there), taken while it is still on the battlefield above.
        chars = self.characteristics_of(permanent)
        self.emit(
            GameEvent(
                event=TriggerEvent.IS_SACRIFICED,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_controller=permanent.controller,
                subject_card=permanent.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                player=permanent.controller,
            )
        )
        return self.put_into_graveyard(permanent)

    def discard_cards(
        self, username: str | None, cards: list[CardState], source: str | None = None
    ) -> list[CardState]:
        """Discard `cards` together, as one CR 701.9a instruction, and fire
        "whenever you discard one or more cards" once for the whole batch.

        CR 603.2c: "An ability triggers only once each time its trigger event
        occurs. However, it can trigger repeatedly if one event contains
        multiple occurrences." A cost or an effect that discards several
        cards at once ("discard two cards", a cleanup discard down to
        maximum hand size, a `{Q}: Discard a card` cost) does so as a single
        instruction with a count, which is exactly what Captain Howler, Sea
        Scourge's own "for each card discarded this way" reads - so this
        emits one `DISCARDS_A_CARD` event carrying `amount=len(cards)`
        rather than one event per card. `machines.keywords.discard` still
        does the actual move, card by card, so madness (CR 702.35a) keeps
        replacing where each one lands.

        This is the one place that emits `DISCARDS_A_CARD` - `machines/
        cost.py`'s discard cost component and `machines/effects.py`'s
        `_discard_cards` both call it instead of moving cards straight to
        the graveyard, so a discard paid as a cost and a discard an effect
        causes both fire the trigger; `Player.discard_to_maximum_hand_size`
        (the cleanup step, CR 514.1) is the one remaining discard path that
        does not yet route through here - see `docs/engine-coverage.md`.
        """
        with self._id_allocator_scope():
            from ..machines.keywords import discard as discard_one  # avoids an import cycle

            discarded: list[CardState] = []
            for card in cards:
                discarded.append(discard_one(self, card, username))
            if not discarded:
                return discarded
            # CR 601.2f's "for each card you've cycled or discarded this turn"
            # (Hollow One) counts cards, not instructions, so a two-card discard
            # adds two. `username` may be None for a player-less scenario; there is
            # nobody to attribute the count to then, and nothing can read it back.
            if username is not None:
                self.cards_discarded_this_turn[username] = self.cards_discarded_this_turn.get(
                    username, 0
                ) + len(discarded)
            self.emit(
                GameEvent(
                    event=TriggerEvent.DISCARDS_A_CARD,
                    player=username,
                    amount=len(discarded),
                )
            )
            return discarded

    def put_into_graveyard(self, card_state: CardState, *, resolving: bool = False) -> CardState:
        """Move a card to its owner's graveyard, replacement effects included.

        Every route to a graveyard runs through here: a destroyed permanent, a
        resolved instant, a countered spell, a spell that fizzled. Each is "a
        card would be put into a graveyard", which is the event Rest in Peace,
        Leyline of the Void, Necrodominance, and Sanctifier en-Vec all watch for
        (CR 400.6, 614.1a).

        `resolving` is narrower than "this card is leaving the stack": it is
        true only for a spell's own successful CR 608 resolution, never for a
        countered spell (CR 701.6, which never resolves) or a fizzled one (CR
        608.2b, which explicitly "doesn't resolve" either). CR 702.88a's
        rebound reads "as it resolves" and needs exactly that distinction;
        `resolve_top` is the only caller that ever passes it `True`.

        A token's *first* trip here is allowed and is the whole of CR 111.7's
        parenthesis - "if a token changes zones, applicable triggered abilities
        will trigger before the token ceases to exist" - so a dying token really
        does reach a graveyard and really does fire its dies trigger (CR 700.4).
        A second trip is refused by CR 111.8.
        """
        with self._id_allocator_scope():
            if move_refused(card_state, Zone.GRAVEYARD) is not None:
                return card_state

            origin = card_state.zone
            was_on_battlefield = card_state in self.battlefield
            # CR 613.5 / CR 608.2h: the permanent's characteristics for both
            # emitters below are the computed ones - a land animated by
            # earthbend is a creature only there - snapshotted here, while it
            # is still on the battlefield, because the DIES emitter fires
            # after `_take_out_of_every_zone` below, once `characteristics_of`
            # would `KeyError` on it.
            left_battlefield_chars = (
                self.characteristics_of(card_state) if was_on_battlefield else None
            )
            if was_on_battlefield:
                self._note_left_battlefield(card_state)
                assert left_battlefield_chars is not None
                # CR 603.6c: the generic departure fires regardless of where the
                # card ends up - a replacement effect redirecting the destination
                # below still means this permanent left the battlefield.
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=card_state.id,
                        subject_name=card_state.name,
                        subject_controller=card_state.controller,
                        subject_card=card_state.card,
                        subject_types=left_battlefield_chars.types,
                        subject_subtypes=left_battlefield_chars.subtypes,
                        player=card_state.controller,
                    )
                )

            event = ReplaceableEvent(
                kind=EventKind.ZONE_CHANGE,
                card=card_state,
                origin=Zone.BATTLEFIELD if was_on_battlefield else origin,
                destination=Zone.GRAVEYARD,
                resolving=resolving,
            )
            apply_replacements(self, event)

            self._take_out_of_every_zone(card_state)
            self.combat.remove(card_state.id)  # CR 506.4

            if event.destination is Zone.GRAVEYARD:
                self._owner_of(card_state).add(card_state, Zone.GRAVEYARD)
            elif event.destination is Zone.EXILE:
                card_state.move_to(Zone.EXILE)
                self.exile.append(card_state)
            elif event.destination is Zone.LIBRARY:
                # Green Sun's Zenith's own "Shuffle [this] into its owner's
                # library" (`machines/replacement.py`'s `_stack_replacements`
                # redirects the destination here, off that same sentence). CR
                # 701.24c: the library is shuffled the moment the card lands in
                # it, even though it arrived straight off the stack rather than
                # out of a search - there is no separate scripted "then shuffle"
                # clause for this one the way a search effect prints its own.
                owner = self._owner_of(card_state)
                owner.add(card_state, Zone.LIBRARY)
                self.shuffle_library(owner)
            else:
                raise ValueError(f"a graveyard replacement sent {card_state.name} nowhere")

            # CR 700.4: it only died if it actually reached a graveyard from the
            # battlefield. Exiled instead, the dies event never happened (CR 614.6).
            if was_on_battlefield and event.destination is Zone.GRAVEYARD:
                assert left_battlefield_chars is not None
                self.emit(
                    GameEvent(
                        event=TriggerEvent.DIES,
                        subject_id=card_state.id,
                        subject_name=card_state.name,
                        subject_controller=card_state.controller,
                        subject_card=card_state.card,
                        # CR 603.10a: dies is a look-back event - the
                        # snapshot taken above, while the permanent was still
                        # on the battlefield, is that look-back: a live
                        # `characteristics_of` here would `KeyError` on an
                        # object `_take_out_of_every_zone` has already moved.
                        subject_types=left_battlefield_chars.types,
                        subject_subtypes=left_battlefield_chars.subtypes,
                        player=card_state.controller,
                    )
                )
            return card_state

    def card_imprinted_on(self, permanent_id: UUID) -> CardState | None:
        """The card exiled *with* `permanent_id`, if any.

        Both markers that mean "exiled with this permanent" count: `ExileMarker.
        IMPRINTED`, left by `_parse_imprint_clause`, and `ExileMarker.HIDEAWAY`,
        left by CR 702.75a's own expansion. The two ability words differ; the
        link they leave behind is the same one, and a later ability naming "the
        exiled card" does not care which sentence exiled it.

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
        found = self.cards_imprinted_on(permanent_id)
        return found[0] if found else None

    def cards_imprinted_on(self, permanent_id: UUID) -> list[CardState]:
        """Every card exiled *with* `permanent_id` - CR 607.3's plural half of
        `card_imprinted_on`'s own linked-ability read.

        Ugin's Labyrinth and Fight Rigging's hideaway both ever exile at most
        one card with themselves, which is all `card_imprinted_on` (now this
        method's first hit, kept for those two callers) ever needed. Knowledge
        Pool links up to three cards per player on entry (CR 607.2a's own
        "each player exiles the top three cards of their library") plus
        whatever its second ability has exiled on earlier triggers (CR
        607.1c: an ability is linked to itself), and a later trigger has to
        offer *all* of them, not just the first one this scan happens to
        reach - the exact plural CR 607.3 names outright: "the ability refers
        to each of the exiled cards."

        Returned in the shared exile zone's own order, which is insertion
        order (`Game.exile_permanent`/`exile_top_of_library` append), not any
        particular game-meaningful order - nothing in the pool asks for one.
        """
        return [
            card
            for card in self.exile
            if (annotation := card.exile_annotation) is not None
            and annotation.marker in (ExileMarker.IMPRINTED, ExileMarker.HIDEAWAY)
            and annotation.linked_permanent_id == permanent_id
        ]

    def exile_permanent(self, permanent: CardState) -> CardState:
        """Move a permanent to the shared exile zone.

        Refused for a token that has already left the battlefield (CR 111.8).

        Emits `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE` when the move was
        actually from the battlefield - the "or is put into exile" half of
        CR 701.66a's earthbend, and the general battlefield-to-exile event
        `machines/triggers.py` never had before: `DIES` already exists for the
        battlefield-to-graveyard half of the same idea, but nothing watched
        this one, so a delayed trigger waiting for it had nothing to fire on.

        A card exiled *out of a graveyard* raises the graveyard pair as well -
        `ExtraTriggerEvent.LEAVES_GRAVEYARD` (CR 603.10a names "abilities that
        trigger when a card leaves a graveyard" outright) and
        `ExtraTriggerEvent.EXILED_FROM_GRAVEYARD` (CR 406.2: "To exile an
        object is to put it into the exile zone from whatever zone it's
        currently in", read here for the graveyard as that zone). One card, so
        `amount=1`; `exile_cards` is the batch door for an instruction that
        moves several at once.
        """
        with self._id_allocator_scope():
            origin_graveyard_owner = self._graveyard_owner_of(permanent)
            self._exile_move(permanent)
            if origin_graveyard_owner is not None and permanent.zone is Zone.EXILE:
                self._emit_left_graveyard(origin_graveyard_owner, [permanent])
            return permanent

    def _exile_move(self, permanent: CardState) -> CardState:
        """`exile_permanent`'s move and its battlefield events, with the
        graveyard pair left to the caller - so `exile_cards` can raise one
        event for a whole instruction (CR 603.2c)."""
        if move_refused(permanent, Zone.EXILE) is not None:
            return permanent
        was_on_battlefield = permanent in self.battlefield
        if was_on_battlefield:
            self._note_left_battlefield(permanent)
            self._detach_dependents(permanent)
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
            # CR 603.6c: the generic departure, alongside the destination-
            # specific event just above - see `Game.put_into_graveyard`'s
            # matching emit for why both fire.
            self.emit(
                GameEvent(
                    event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    player=permanent.controller,
                )
            )
        return permanent

    @property
    def ante_zone(self) -> list[CardState]:
        """CR 400.1's optional eighth zone, shared and public (CR 400.2)."""
        return self.shared_zones[Zone.ANTE]  # type: ignore[return-value]

    def ante(self, card_state: CardState, anteing_player: str | None = None) -> bool:
        """Ante a card, and answer whether it actually moved (CR 407.4).

        CR 407.4: "To ante an object is to put that object into the ante zone
        from whichever zone it's currently in. The owner of an object is the
        only player who can ante that object." Both halves are here: the move
        is out of *whatever* zone the card is in, and a player who is not the
        owner is refused outright rather than quietly succeeding.

        The boolean is what Jeweled Bird's "Ante this artifact. **If you do**,
        ..." reads: an ante that was refused leaves the whole rest of the
        ability undone, which is the stolen-Bird ruling DDR#666 walks through.

        `anteing_player` defaults to the card's own controller, which is who is
        activating the ability that says to ante it - and for a permanent an
        opponent has stolen, that is exactly the player CR 407.4 refuses.

        CR 407.3 is why there is no other door into this zone: "A few cards
        have the text 'Remove this card from your deck before playing if you're
        not playing for ante.' These are the only cards that can add or remove
        cards from the ante zone or change a card's ownership."
        """
        with self._id_allocator_scope():
            anteing_player = (
                anteing_player if anteing_player is not None else card_state.controller_or_owner
            )
            owner = card_state.owner
            if owner is None or anteing_player != owner:
                return False
            was_on_battlefield = card_state in self.battlefield
            if was_on_battlefield:
                self._note_left_battlefield(card_state)
                self._detach_dependents(card_state)
            self._take_out_of_every_zone(card_state)
            self.combat.remove(card_state.id)  # CR 506.4
            card_state.move_to(Zone.ANTE)
            self.ante_zone.append(card_state)
            if was_on_battlefield:
                # CR 603.6c's generic departure. There is no ante-specific trigger
                # event, and nothing in the pool watches for one.
                self.emit(
                    GameEvent(
                        event=TriggerEvent.LEAVES_THE_BATTLEFIELD,
                        subject_id=card_state.id,
                        subject_name=card_state.name,
                        subject_controller=card_state.controller,
                        subject_card=card_state.card,
                        player=card_state.controller,
                    )
                )
            return True

    def exile_cards(self, cards: Sequence[CardState]) -> list[CardState]:
        """Exile several cards as one instruction (CR 406.2).

        The batch door onto `exile_permanent`. Everything about the move itself
        is identical - each card goes through the same path, keeping the
        battlefield departure events, CR 111.8's token refusal and CR 506.4's
        combat clean-up - but the graveyard pair is raised **once** for the
        whole instruction rather than once per card.

        That is CR 603.2c: "An ability triggers only once each time its trigger
        event occurs. However, it can trigger repeatedly if one event contains
        multiple occurrences." A condition written "whenever **one or more**
        cards leave your graveyard" (Hardened Academic) is asking about the
        event, not about each card in it, so a delve payment that exiles five
        cards (CR 702.66a: "For each generic mana in this spell's total cost,
        you may exile a card from your graveyard rather than pay that mana") is
        one event with `amount=5`, and the ability triggers once.

        Grouped by whose graveyard each card left, because "your graveyard" is
        read off the owner of the zone: two graveyards emptied by one
        instruction are two events, one per graveyard, each with its own count.
        """
        with self._id_allocator_scope():
            by_graveyard: dict[str, list[CardState]] = {}
            exiled: list[CardState] = []
            for card_state in cards:
                owner = self._graveyard_owner_of(card_state)
                self._exile_move(card_state)
                exiled.append(card_state)
                if owner is not None and card_state.zone is Zone.EXILE:
                    by_graveyard.setdefault(owner, []).append(card_state)
            for owner, gone in by_graveyard.items():
                self._emit_left_graveyard(owner, gone)
            return exiled

    def _graveyard_owner_of(self, card_state: CardState) -> str | None:
        """Whose graveyard this card is in right now, if it is in one.

        CR 404.1's graveyard is a per-player zone, and the "your" in "whenever
        one or more cards leave **your** graveyard" is the player whose
        graveyard it was - not whoever's effect moved the card - so this
        answers by finding the zone the card is actually sitting in rather than
        by reading `CardState.owner`.
        """
        if card_state.zone is not Zone.GRAVEYARD:
            return None
        for player in self.players:
            if any(state is card_state for state in player.graveyard):
                return player.username
        return None

    def _emit_left_graveyard(
        self, owner: str, gone: list[CardState], *, exiled: bool = True
    ) -> None:
        """The events one batch of cards leaving a graveyard raises (CR 603.10a, 406.2).

        `ExtraTriggerEvent.LEAVES_GRAVEYARD` is CR 603.10a's own category -
        "abilities that trigger when a card leaves a graveyard" - and
        `ExtraTriggerEvent.EXILED_FROM_GRAVEYARD` is the narrower one that also
        names where the card went, which Ketramose, the New Dawn's "one or more
        cards are put into exile from graveyards and/or the battlefield" reads.
        Both are true of the same move, so both fire, the same way
        `LEAVES_BATTLEFIELD_TO_EXILE` and `LEAVES_THE_BATTLEFIELD` already do -
        but only when exile is where the cards actually went. `exiled=False` is
        a graveyard departure to somewhere else (a library, a hand), which is
        CR 603.10a's event and not CR 406.2's.

        `player` is the owner of the graveyard, which is what the matcher
        compares against the ability's controller for "your graveyard".

        The subject is filled in only when exactly one card left: a condition
        with a type restriction ("an instant or sorcery card leaves your
        graveyard", Murktide Regent) reads `subject_types`, and a batch of
        several cards has no single answer to give it. Left unset, that
        condition simply does not match - the same direction every other
        unanswerable question in this engine fails in, rather than picking one
        card of the batch and pretending it was the whole event.
        """
        if not gone:
            return
        only = gone[0] if len(gone) == 1 else None
        events = [ExtraTriggerEvent.LEAVES_GRAVEYARD]
        if exiled:
            events.append(ExtraTriggerEvent.EXILED_FROM_GRAVEYARD)
        for event in events:
            self.emit(
                GameEvent(
                    event=event,
                    subject_id=only.id if only is not None else None,
                    subject_name=only.name if only is not None else None,
                    subject_card=only.card if only is not None else None,
                    subject_types=only.types if only is not None else None,
                    subject_subtypes=only.subtypes if only is not None else None,
                    player=owner,
                    amount=len(gone),
                )
            )

    def _detach_dependents(self, permanent: CardState) -> None:
        """Nothing stays attached to a permanent that just left (CR 704.5m, 704.5n).

        `CardState.move_to` (CR 400.7) already clears `permanent`'s *own*
        `attachment` as it leaves - what it cannot clear is every *other*
        permanent's `attached_to`, which points at `permanent.id` rather than
        at the object itself. This engine mutates a `CardState` in place
        rather than minting a fresh id when it returns (`zone_change_stamp`
        is the id-survives-the-round-trip marker instead - see
        `DelayedTrigger.expected_stamp`), so a permanent exiled and put back
        onto the battlefield **within the same resolution** - Ephemerate's
        "exile ..., then return it" is one instruction, with no state-based
        action check in between (CR 704.3 only runs before a player would
        next receive priority) - would otherwise have the exact same id both
        times, and an Aura or Equipment still holding that id would silently
        "follow" the blink with nothing ever catching it: the ordinary
        `aura_state_based_actions`/`equipment_state_based_actions` sweep in
        `check_state_based_actions` never gets a turn to run against the
        moment in between where the id was genuinely gone.

        Clearing the pointer here, the instant the permanent actually leaves,
        is what a live SBA sweep would have found anyway had one run right
        then: the ordinary sweep that *does* run once the whole spell finishes
        resolving is what turns this into the real CR 704.5m/n consequence -
        an Aura pointing at nothing goes to its owner's graveyard, an
        Equipment pointing at nothing simply stays on the battlefield
        unattached - so this only ever moves that discovery earlier, never
        replaces it.
        """
        for other in self.battlefield:
            if other.id != permanent.id and other.attached_to == permanent.id:
                other.unattach()

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
        - **CR 704.5s** - a Saga whose lore counters (CR 714.3) are at least its
          final chapter number (CR 714.2e), and that is not the source of a
          chapter ability that has triggered but not yet left the stack, goes
          to its owner's graveyard.

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

        Run under `_id_allocator_scope`: each round's `_state_based_actions_
        once` mints a `zone_change_stamp` for every permanent it moves to a
        graveyard (CR 704.5f/704.5g/704.5h/704.5i/704.5m/704.5z/704.5s) and
        may emit a "dies" trigger for each, all persisted ids. `pass_priority`
        and `resolve_top` already reach this from inside their own scopes,
        but the api's `run_state_based_actions` calls it directly too
        (`engine_api.py` around line 862), so it needs a scope of its own
        rather than relying on that nesting.
        """
        with self._id_allocator_scope():
            return self._check_state_based_actions_impl()

    def _check_state_based_actions_impl(self) -> list[CardState]:
        """The rest of `check_state_based_actions` - see its own docstring
        for why it is split out."""
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
            # And the mana pools go with them, for the same reason: Omnath,
            # Locus of Mana's "Omnath gets +1/+1 for each unspent green mana
            # you have" counts something the layer engine cannot see standing
            # on the battlefield either.
            unspent_mana_by_controller={
                player.username: dict(self.unspent_mana_of(player).floating)
                for player in self.players_in_game
            },
        )
        return self.continuous_effects.board(self.battlefield, context, self)

    def unspent_mana_of(self, player: Player) -> ManaPool:
        """The mana this player has produced and not yet spent (CR 106.4).

        Their own `ManaPool`, except while a `CostPayment` of theirs is open:
        that payment opened as a copy of this very pool and every mana ability
        activated for it (CR 601.2g) adds into the copy, so the copy is the
        one that knows what is actually unspent. See `open_payment_pools`.
        """
        return self.open_payment_pools.get(player.username, player.mana_pool)

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
        leaving += [state for state in self._legend_rule_losers(board) if state not in leaving]
        # CR 704.5m, read off the Aura's own enchant ability (CR 702.5a) by
        # `machines/keywords.py`, which owns the reader `Casting` uses for the
        # announcement half of the same sentence.
        leaving += [state for state in aura_state_based_actions(self) if state not in leaving]
        leaving += [state for state in self._roles_beyond_the_newest(board) if state not in leaving]
        # CR 704.5i: "If a planeswalker has loyalty 0, it's put into its owner's
        # graveyard." Loyalty is the counter count (CR 306.5c), which is what
        # `planeswalkers_with_zero_loyalty` reads.
        leaving += [
            state
            for state in planeswalkers_with_zero_loyalty(self.battlefield)
            if state not in leaving
        ]
        # CR 704.5s, CR 714.4: a Saga whose lore counters reached its final
        # chapter number, once nothing left to run off it is still triggered.
        leaving += [state for state in self._sagas_to_put_into_graveyard() if state not in leaving]
        # `put_into_graveyard` rather than `destroy`, because CR 701.8b says only
        # CR 704.5g and CR 704.5h destroy: CR 704.5f, the legend rule (704.5j),
        # CR 704.5i, CR 704.5m and CR 704.5z all read "is put into its owner's
        # graveyard".
        # The two that *do* destroy have already had CR 702.12b applied to them
        # by `_dies_to_state_based_action`, so an indestructible permanent is not
        # in this list for either of them - and an indestructible 0/0 is, which
        # is the point of the distinction.
        for state in leaving:
            # CR 704.5g and CR 704.5h are destructions (CR 701.8b), so a
            # destruction-replacement - regeneration, umbra armor - gets its
            # say before the move. Everything else in `leaving` is "put into
            # its owner's graveyard" and cannot be replaced that way; CR 704.5f
            # states it outright ("Regeneration can't replace this event").
            if self._destroyed_by_state_based_action(state, board) and not self.destruction_happens(
                state
            ):
                continue
            self.put_into_graveyard(state)

        # CR 704.5n, after the round that killed the host: an Equipment whose
        # creature has just left becomes unattached and *stays on the
        # battlefield*, so it is not part of `leaving`. CR 704.3 makes every
        # applicable action one simultaneous event and then checks again, which
        # is what the caller's loop does. It runs after CR 704.5m so that an Aura
        # is already off the battlefield by the time it looks: `equipment_state_based_actions`
        # does not check that what it is unattaching is an Equipment.
        equipment_state_based_actions(self)
        # CR 704.5p, immediately after it: "If a battle or creature is attached
        # to an object or player, it becomes unattached and remains on the
        # battlefield." Unconditional where CR 704.5n asks whether the host is
        # legal, and read off the *computed* types (CR 613.5), which is how
        # CR 301.5c's "An Equipment that's also a creature can't equip a
        # creature" is enforced when a layer 4 effect animates an Equipment
        # that is already equipping something.
        attachment_state_based_actions(self)
        # CR 702.131b (ascend): "Any time you control ten or more permanents
        # and you don't have the city's blessing, you get the city's blessing
        # for the rest of the game." Not itself a triggered ability with a
        # stack object (CR 603.8's state-trigger shape), so it is checked here
        # alongside the equipment and Aura background checks rather than
        # through `machines/triggers.py`.
        ascend_state_based_actions(self)
        return leaving + gone_tokens

    def _roles_beyond_the_newest(self, board: ComputedBoard) -> list[CardState]:
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
        `entered`. `board` is the one `_state_based_actions_once` already
        computed one frame earlier - CR 613.5's computed subtypes, not the
        printed `CardState.subtypes`, threaded in rather than recomputed so a
        board read from `.types`/`.subtypes` here never risks the exponential
        nested-computation trap a plain `CardState` read would (see
        `_asking_the_board`'s own docstring).
        """
        stamps = self.continuous_effects.entered
        groups: dict[tuple[UUID, str], list[CardState]] = {}
        for permanent in self.battlefield:
            if "Role" not in board.of(permanent).subtypes or permanent.attached_to is None:
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

    def _sagas_to_put_into_graveyard(self) -> list[CardState]:
        """CR 704.5s, CR 714.4: every Saga whose lore counters have reached
        its final chapter number, except one that is still the source of a
        chapter ability that "has triggered but not yet left the stack" -
        read here as either still `pending_triggers` (CR 603.3's window
        between triggering and actually being put on the stack) or already an
        `AbilityOnStack` in `self.stack` (CR 608.2n's window up to
        resolution) - a chapter III still resolving must not have its own
        Saga vanish out from under it mid-effect.
        """
        still_owed = {
            item.source_id
            for item in (*self.pending_triggers, *self.abilities_on_stack)
            if isinstance(item.ability, TriggeredAbility) and item.ability.chapter is not None
        }
        return [
            permanent
            for permanent in self.battlefield
            if permanent.lore_counters_exhausted and permanent.id not in still_owed
        ]

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

    def _destroyed_by_state_based_action(self, state: CardState, board: ComputedBoard) -> bool:
        """Which of the state-based actions taking this permanent is a *destroy*.

        CR 701.8b names exactly two: CR 704.5g's lethal damage and CR 704.5h's
        damage from a deathtouch source. CR 704.5f's toughness of 0 or less,
        the legend rule, CR 704.5i, CR 704.5m and CR 704.5z all read "is put
        into its owner's graveyard" instead, so a destruction-replacement must
        not reach them.

        CR 704.5f wins where both would apply: a creature at 0 toughness is put
        into the graveyard whatever damage is marked on it, and regeneration
        cannot replace that event. So a 0-toughness creature answers False here
        even when it also has lethal damage marked.
        """
        if is_indestructible(state, self):
            return False  # CR 702.12b - it was never in `leaving` for these two
        if self._toughness_is_zero_or_less(state, board):
            return False  # CR 704.5f, not a destruction
        try:
            toughness = board.of(state).toughness
        except KeyError:
            toughness = state.toughness
        if toughness is None:
            return state.dealt_deathtouch_damage  # CR 704.5h needs no arithmetic
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

    def _legend_rule_losers(self, board: ComputedBoard) -> list[CardState]:
        """The legendary permanents the legend rule puts into graveyards (CR 704.5j).

        "If two or more legendary permanents with the same name are controlled
        by the same player, **that player chooses one of them**, and the rest
        are put into their owners' graveyards."

        The choice is real and is asked, one `CHOOSE_CARDS` question per
        (controller, name) group. Two players each holding two copies of the
        same legend is two separate choices made at the same time, which is
        what CR 101.4 orders: "If multiple players would make choices and/or
        take actions at the same time, the active player ... makes any choices
        required, then the next player in turn order". So the groups are walked
        in `_turn_order_from_active` order, active player first, and the
        question for each of that player's groups is put before the next
        player's.

        **The group is offered reversed.** `default_answer` for an exact
        `CHOOSE_CARDS` answers with the *back* of the offered cards, so
        reversing the group makes the unscripted default keep the copy that has
        been on the battlefield longest - the behaviour every scenario that
        does not care about the choice was already relying on. A scenario that
        does care answers the question instead.

        CR 613.5: grouped by the computed supertypes and name, not the
        printed ones - `BecomeACopy` (CR 707.2, 707.4) writes both, so a
        clone copying a legendary permanent has to be seen as sharing that
        legend's name and Legendary supertype, or the collision this rule
        exists for goes unnoticed.
        """
        groups: dict[str, dict[str, list[CardState]]] = {}
        for state in self.battlefield:
            chars = board.of(state)
            if Supertype.LEGENDARY not in chars.supertypes:
                continue
            controller = self.controller_of(state).username
            groups.setdefault(controller, {}).setdefault(chars.name, []).append(state)

        losers: list[CardState] = []
        for username in self._turn_order_from_active():
            for name, copies in groups.get(username, {}).items():
                if len(copies) < 2:
                    continue
                kept = self._ask_which_legend_to_keep(username, name, copies)
                losers.extend(state for state in copies if state is not kept)
        return losers

    def _ask_which_legend_to_keep(
        self, username: str, name: str, copies: list[CardState]
    ) -> CardState:
        """CR 704.5j's "that player chooses one of them", asked once per group."""
        offered = list(reversed(copies))
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=username,
            prompt=f"choose which {name} to keep (CR 704.5j)",
            amount=1,
            exact=True,
            cards=tuple(state.id for state in offered),
        )
        chosen_ids = self.ask(decision)
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in copies}
        for card_id in chosen_ids:
            kept = by_id.get(card_id)
            if kept is not None:
                return kept
        # An answer that named nothing on offer keeps the longest-standing
        # copy, the same as the unscripted default - the legend rule is a
        # state-based action and has to reach an answer.
        return copies[0]

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

        **CR 800.4n is the one exception**: "When a player leaves the game,
        objects that player owns in the ante zone do not leave the game." The
        ante zone is skipped entirely here for that reason.
        """
        assert self.turn is not None
        for zone, zone_cards in self.shared_zones.items():
            if zone is Zone.ANTE:
                continue  # CR 800.4n
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
        # CR 613.5: the attacker's characteristics for this event are the
        # computed ones - a land animated by earthbend is a creature only
        # there - and it is still on the battlefield here (CR 508.1a).
        chars = self.characteristics_of(creature)
        self.emit(
            GameEvent(
                event=TriggerEvent.ATTACKS,
                subject_id=creature.id,
                subject_name=creature.name,
                subject_controller=self.controller_of(creature).username,
                subject_card=creature.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                defender=attack.defender,
                player=self.controller_of(creature).username,
            )
        )
        return attack

    def declare_attackers(self, attacks: list[tuple[CardState, "Targetable | str"]]) -> None:
        """Declare a whole attack at once, in order (CR 508.1, 508.2b)."""
        with self._id_allocator_scope():
            for creature, defender in attacks:
                self.declare_attacker(creature, defender)
            if attacks:
                # CR 508.3d: "An ability that reads 'Whenever [a player]
                # attacks, . . .' triggers if one or more creatures that
                # player controls are declared as attackers" - once for the
                # whole declaration, not once per attacker, so this is its own
                # subject-less event alongside each creature's own ATTACKS
                # event above.
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
        with self._id_allocator_scope():
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

    # -- permission to play a card from somewhere else (CR 601.3) ----------

    def grant_play_permission(
        self,
        card: CardState,
        player: str,
        *,
        action: PlayAction = PlayAction.CAST,
        pays_mana_cost: bool = True,
        source_name: str = "",
        rule: str = "CR 601.3",
        zone: Zone = Zone.EXILE,
        until_end_of_turn: bool = True,
        bottom_if_unused: bool = False,
        immediate: bool = False,
        until_next_turn_of: str | None = None,
        expires_end_of_next_turn: bool = False,
        flashback: bool = False,
    ) -> PlayPermission:
        """CR 601.3: let `player` play this one card out of `zone`, for a turn.

        The primitive behind Ugin, Eye of the Storms' "−11: ... Until end of
        turn, you may cast those cards without paying their mana costs." and
        Ragavan, Nimble Pilferer's "... Until end of turn, you may cast that
        card." Both are the same shape: a resolving ability names cards it has
        just exiled and says who may play them and for how long.

        `immediate=True` is the other shape - CR 117.2e's own "resolving...
        abilities may instruct players to take actions" grant, with no printed
        "until end of turn" - Suspend's third ability (CR 702.62a) is the one
        that uses it. See `PlayPermission.immediate`'s own docstring for why
        that needs `granted_step` rather than `until_end_of_turn`.

        The permission is stamped with the object's `zone_change_stamp`
        (CR 400.7), so it dies the moment the card moves - it cannot be
        re-earned by a card that leaves exile and returns, and it never leaks
        to a different card in the same pile.

        `player` is who may play it, which CR 108.3 leaves free to differ from
        the owner: Ragavan exiles from the damaged player's library and hands
        the permission to the Ragavan controller.

        `pays_mana_cost=False` is CR 118.9's "without paying its mana cost".
        `action=PlayAction.PLAY` is CR 601.1a's wider word, which reaches the
        land drop; `PlayAction.CAST` never does.

        `bottom_if_unused` is `PlayPermission.bottom_if_unused` - see its own
        docstring for why cascade passes `True` here and nothing else does.

        `until_next_turn_of` is CR 800.4m's "until the end of your next turn"
        duration (Hex Magic) rather than a plain "until end of turn" - see
        `PlayPermission.until_next_turn_of`'s own docstring. Passing it forces
        `until_end_of_turn=False` regardless of the argument given, since the
        two durations are mutually exclusive and `Game.begin_turn_for` (not
        `Game.cleanup_step`) is what drops this one.
        `expires_end_of_next_turn=True` is Wrenn's Resolve's/Reckless
        Impulse's longer "until the end of your next turn" grant - see
        `PlayPermission.expires_end_of_next_turn`'s own docstring. A caller
        passing this should also pass `until_end_of_turn=False`, so
        `Game.cleanup_step`'s ordinary same-turn sweep leaves it alone.

        `flashback=True` is CR 702.34a's grant handed out as a permission
        rather than read off a printed keyword line - Past in Flames' and the
        spell Flashback's "... gains flashback ... equal to its mana cost" -
        see `PlayPermission.flashback`'s own docstring for why its second,
        exile-on-leaving-the-stack half still has to apply, and for why
        Underworld Breach (which grants escape, not flashback) is not one.
        """
        with self._id_allocator_scope():
            turn = self.turn
            permission = PlayPermission(
                card_id=card.id,
                zone_change_stamp=card.zone_change_stamp,
                player=player,
                zone=zone,
                action=action,
                pays_mana_cost=pays_mana_cost,
                flashback=flashback,
                source_name=source_name,
                rule=rule,
                until_end_of_turn=until_end_of_turn and until_next_turn_of is None,
                granted_turns_taken=None if turn is None else int(turn.turns_taken),
                bottom_if_unused=bottom_if_unused,
                immediate=immediate,
                granted_step=None if turn is None else turn.step,
                until_next_turn_of=until_next_turn_of,
                expires_end_of_next_turn=expires_end_of_next_turn,
            )
            self.play_permissions.append(permission)
            return permission

    def play_permission_for(
        self, card: CardState, player: str, action: PlayAction = PlayAction.CAST
    ) -> PlayPermission | None:
        """The live permission letting `player` take `action` with `card`, or None."""
        return usable_play_permission(self, card, player, action)

    def alternative_costs_for(self, card: CardState, caster: str) -> list[AlternativeCostOption]:
        """CR 118.9's alternative-cost menu for `card`, answerable before any
        `Casting` exists.

        `magic_cards_model_api.affordances.alternative_costs` used to build a
        throw-away `Casting` on a `dry_run_copy(game)` purely to ask this
        question - CR 601.2a moves the card to the stack as the *first* step
        of proposing a cast, so answering "what could this be cast for"
        needed a whole deep copy of the game just to avoid mutating the real
        one. This is the pure port instead: the same PRINTED and KEYWORD
        halves `Casting.alternative_costs` builds, read directly off
        `alternative_cost_offers`, `keyword_cast_options`, `marker_cast_options`,
        and `granted_cast_options` - none of which need a live announcement,
        because none of them ask anything a `Casting` in flight would know
        that `card.zone` does not already say.

        `legal_actions` is what this is for: Force of Negation for `{1}{U}{U}`
        and pitched are two different cast actions with two different costs,
        and this is how it finds the second one without ever moving the card.

        All four of `Casting.alternative_costs`'s sources are reproduced,
        PERMISSION and STATIC included. Both were once thought to need an
        in-flight `Casting`'s own state - they do not: `play_permissions_on`
        is keyed off `card`'s own CR 400.7 identity, which `card` already
        carries before any `Casting` exists, and `static_free_cast_grants`
        (cascade, Ugin's exiled cards, Omniscience) is a pure read of
        `self.battlefield`/`caster`. This is the same gap that made a
        cascade hit or an Omniscience-enabled spell invisible to this menu.
        """
        options: list[AlternativeCostOption] = []
        origin_zone = card.zone
        for offer in alternative_cost_offers(card.card):
            cost = _printed_alternative_total_cost(offer.phrase, payer=caster)
            unavailable: str | None = None
            if cost is None:
                unavailable = f"{card.name}'s alternative cost {offer.phrase!r} could not be read"
            elif offer.requires_not_your_turn and not (
                self.turn is not None and self.turn.active_player != caster
            ):
                unavailable = (
                    f"{card.name}'s alternative cost can only be paid on an opponent's turn"
                )
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PRINTED,
                    rule="CR 118.9",
                    source_name=card.name,
                    description=offer.phrase,
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=unavailable,
                )
            )

        keyword_options: list[tuple[str, KeywordCastOption]] = [
            (card.name, option)
            for option in keyword_cast_options(card.card) + marker_cast_options(card)
        ]
        # CR 610.5: a keyword another permanent grants as this spell is cast is
        # an alternative cost like any other printed one.
        keyword_options.extend(
            (granted.source_name, granted.option)
            for granted in granted_cast_options(self, card, caster, origin_zone)
        )
        for offering_card, keyword_option in keyword_options:
            if keyword_option.pays_mana_cost:
                # A permission that still charges the mana cost (warp's second
                # half, flashback still charging a cost) is a zone permission,
                # not a CR 118.9 alternative cost.
                continue
            cost = keyword_option.cost
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.KEYWORD,
                    rule=keyword_option.rule,
                    source_name=offering_card,
                    keyword=keyword_option.keyword,
                    description=str(cost) if cost is not None else "nothing",
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=keyword_option.why_not(card, caster, self, origin=origin_zone),
                )
            )

        for permission in play_permissions_on(self, card):
            if permission.pays_mana_cost:
                continue
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PERMISSION,
                    rule=permission.rule,
                    source_name=permission.source_name,
                    # CR 107.3b keeps "no cost at all" apart from a cost of
                    # {0}, so this says nothing rather than {0}.
                    description="nothing",
                    cost=None,
                    unavailable=permission.why_not(card, caster, self),
                )
            )

        for source_name, grant in static_free_cast_grants(self, caster):
            unavailable = None
            if origin_zone is not grant.zone:
                unavailable = (
                    f"{source_name} only applies to spells cast from your "
                    f"{grant.zone.value} (CR 118.9)"
                )
            elif grant.type_word and not spell_has_type_word(card.card, grant.type_word):
                unavailable = (
                    f"{source_name} only applies to {grant.type_word} spells, and "
                    f"{card.name} is not one"
                )
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.STATIC,
                    rule="CR 118.9",
                    source_name=source_name,
                    description="nothing",
                    cost=None,
                    unavailable=unavailable,
                )
            )
        return options

    def object_cost_offers(self, card: CardState, player: str) -> dict[str, "ObjectCostOffer"]:
        """Which objects could be spent on `card`'s cost, and for what -
        convoke (CR 702.51a), delve (CR 702.66a), improvise (CR 702.126a),
        crew (CR 702.122a).

        `magic_cards_model_api.affordances.object_costs` used to import
        `machines/objects_as_costs.py` directly and walk the battlefield and
        graveyard itself to answer this; that walk is engine knowledge, not
        api shaping, so it lives here now. The api keeps `_label`, the dict
        shaping, and `object_costs`'s own three-key dict - this only answers
        *which cards are eligible*, the same `ObjectOffer.why_not` predicate
        the actual payment (`machines/objects_as_costs.convoke`/`delve`/
        `improvise`) uses, so a candidate list here can never disagree with
        what paying would accept.

        Only the keys that apply are present - a card with none of these
        gets an empty dict.
        """
        from ..machines.objects_as_costs import convoke_offer as _convoke_offer
        from ..machines.objects_as_costs import (
            crew_number,
            crew_offer,
            delve_offer,
            has_convoke,
            has_delve,
            has_improvise,
            improvise_offer,
            is_vehicle_permanent,
        )

        battlefield = self.battlefield
        out: dict[str, ObjectCostOffer] = {}
        if has_convoke(card.card):
            offer = _convoke_offer()
            out["convoke"] = ObjectCostOffer(
                rule="CR 702.51a",
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
            )
        if has_delve(card.card):
            offer = delve_offer()
            out["delve"] = ObjectCostOffer(
                rule="CR 702.66a",
                candidates=[
                    c
                    for c in self.player(player).graveyard
                    if offer.why_not(c, player, self) is None
                ],
            )
        if has_improvise(card.card):
            offer = improvise_offer()
            out["improvise"] = ObjectCostOffer(
                rule="CR 702.126a",
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
            )
        # CR 613.5: whether this permanent is a Vehicle is the computed
        # answer, not the printed type line - Toph, the First Metalbender's
        # "nontoken artifacts you control are lands" and any layer-4 subtype
        # change both reach it, and a crewed Vehicle stays one.
        if is_vehicle_permanent(card, self):
            offer = crew_offer(card)
            out["crew"] = ObjectCostOffer(
                rule="CR 702.122a",
                number=crew_number(card.card),
                candidates=[c for c in battlefield if offer.why_not(c, player, self) is None],
            )
        return out

    def assert_quiescent(self) -> None:
        """Raise loudly if the game is sitting mid-announcement or mid-resolution.

        `Casting` and `CostPayment` (see `Game.cast` below) are locals that
        never outlive one call - they are not `Game` fields, so nothing about
        them is ever written into a `Game.model_dump()`. A caller who drives
        their step-by-step API by hand and forgets to reach `cast()`/`cancel()`
        or `pay()`/`rewind()` before letting the `Game` be persisted leaves no
        trace of the object that could still finish or cancel the action - a
        card sitting on the stack that decodes back with no `Casting` behind
        it any more. `Game.resolving` (unset outside the length of one
        `resolve_top` call) and `open_payment_pools` (emptied the moment a
        `CostPayment` is paid, cancelled or rewound - `CostPayment._register_
        pool`/`_unregister_pool`) are the two pieces of `Game` state such an
        abandoned action would leave behind, so together they are what this
        checks.
        """
        if self.resolving is not None:
            raise AssertionError(
                f"game is mid-resolution: {self.resolving!r} is still Game.resolving "
                "with no resolve_top() call left on the stack to finish or undo it"
            )
        if self.open_payment_pools:
            raise AssertionError(
                "game has an open CostPayment for "
                f"{sorted(self.open_payment_pools)} with no CostPayment object left "
                "to pay or rewind it"
            )

    def cast(
        self,
        card: CardState,
        caster: str,
        *,
        modes: Sequence[int | str] | None = None,
        x_value: int | None = None,
        targets: Sequence[Any] | None = None,
        division: Sequence[int] | None = None,
        keyword: str | None = None,
        alternative_cost: int | str | None = None,
        choosing: list[CardState] | None = None,
        convoke: Sequence[tuple[CardState, Color | None]] | None = None,
        delve: Sequence[CardState] | None = None,
        improvise: Sequence[CardState] | None = None,
        mana_sources: Sequence[CardState | tuple[CardState, Sequence[Color]]] | None = None,
        splice: Sequence[UUID] | None = None,
    ) -> CardState:
        """Cast `card` for `caster`, start to finish, as one atomic action.

        CR 601.2 lays casting out as an ordered sequence: propose (601.2a),
        announce modes and any alternative or variable costs (601.2b),
        announce targets (601.2c), announce a division among them (601.2d), a
        legality check (601.2e), determine the total cost (601.2f), activate
        mana abilities (601.2g), pay (601.2h) - and only then, at 601.2i,
        "the spell becomes cast." `Casting`/`CostPayment` model that sequence
        as an object the caller drives one step at a time (CR 601.2a already
        moves the card onto the stack, well before the cast is either legal
        or paid for), which is exactly what leaves a half-finished
        announcement observable to a caller that stops driving it partway
        through. This method is what makes the whole sequence atomic by
        construction instead of by caller discipline: both objects are
        created here, driven start to finish here, and never returned or
        stored anywhere `self` keeps a reference to - they are gone the
        moment this call returns, one way or the other.

        What makes reversing it safe, when it has to be reversed, is CR
        601.2's own closing sentence together with CR 601.6: "If a player is
        unable to comply with the requirements of a step ... the casting of
        the spell is illegal; the game returns to the moment before the
        casting of that spell was proposed." CR 733.1 spells out what that
        return means: "the entire action is reversed and any payments
        already made are canceled ... If the action was casting a spell, the
        spell returns to the zone it came from." `Casting.cancel` and
        `CostPayment.rewind` are this engine's own implementation of exactly
        that - and they restore the card's pre-move CR 400.7 identity stamp,
        not merely its zone, because CR 400.7's "an object that moves from
        one zone to another becomes a new object with no memory of ... its
        previous existence" is what a `PlayPermission` or a delayed trigger
        watching that exact object would otherwise lose. Every step below
        that can refuse raises `ValueError`; it is caught once, here, both
        objects are rewound (each rewind is already safe to call whether or
        not that step ever ran), and the exception is re-raised - so a caller
        of `Game.cast` either gets back a spell on the stack with its cost
        paid, or an untouched game and an exception, with nothing in between
        for it, or a decode of `self`, to ever observe.

        The keyword parameters mirror what `magic_cards_model_api.engine_api.
        cast_card` drives by hand today, minus the pieces that belong to an
        HTTP request rather than to the rule itself (a card looked up by id
        or name, a dry-run probe that is never atomic by definition since it
        must leave no trace whether or not the cast would succeed):
        `modes`/`x_value` and `targets`/`division` are CR 601.2b-d's own
        announcements; `keyword` and `alternative_cost` (with `choosing` for
        the objects either one's cost needs, such as a pitched card) are the
        two ways CR 601.3's permission to cast can be claimed, alongside a
        live `PlayPermission` this method checks for automatically wherever
        `keyword` and `alternative_cost` are both left unclaimed; `convoke`
        (CR 702.51a/b), `delve` (CR 702.66a/b) and `improvise` (CR 702.126a/b)
        apply "only after the total cost ... is determined", so they run
        against the open payment rather than the announcement; and
        `mana_sources` are the abilities this call may activate on `caster`'s
        behalf (CR 601.2g) - a bare source lets the engine choose what colour
        it makes, a `(source, colors)` pair pins it.

        `splice` is CR 702.47a: card ids, never names, matching `Action.
        splice_options`' own `SpliceOption.card_id` - this library's actions
        are ids only, and a caller holding two copies of the same splice card
        has to be able to name which one it means. Each id is applied with
        `Casting.splice_by_id` before `determine_cost`, because folding a
        splice cost into `additional_costs` changes the total cost CR 601.2f
        determines (`Casting._splice_card` nulls the announcement's own stale
        `payment` for exactly that reason).
        """
        origin_zone = card.zone
        # CR 601.3's dynamic half is asked before CR 601.2a's move, exactly
        # like `engine_api.cast_card` asks it - the object `usable_play_
        # permission` looks for is recorded against the pre-move CR 400.7
        # stamp, and `origin_zone` itself is read now for the same reason.
        permitted = origin_zone is Zone.EXILE and self.play_permission_for(card, caster) is not None
        # A `Casting` that fails to build (CR 601.3's static half, checked in
        # its own `model_post_init`) has moved nothing and leaves nothing to
        # rewind, so this is not inside the try/except below.
        casting = Casting(spell=card, caster=caster, origin_zone=origin_zone, game=self)
        payment: CostPayment | None = None
        try:
            if alternative_cost is not None:
                casting.use_alternative_cost(alternative_cost, choosing=choosing)
            elif keyword:
                casting.use_keyword(keyword)
            elif permitted:
                casting.use_permission()
            if modes:
                casting.choose_modes(modes, x_value=x_value)
            if targets:
                casting.choose_targets(list(targets))
            for card_id in splice or ():
                casting.splice_by_id(card_id)
            payment = casting.determine_cost(x_value=x_value)
            if division is not None:
                casting.announce_division(division)
            for creature, color in convoke or ():
                pay_convoke(payment, casting.spell, creature, color)
            if delve:
                pay_delve(payment, casting.spell, *delve)
            if improvise:
                pay_improvise(payment, casting.spell, *improvise)
            unpinned: list[CardState] = []
            for entry in mana_sources or ():
                if isinstance(entry, tuple):
                    source, colors = entry
                    payment.tap_for_mana(source, list(colors))
                else:
                    unpinned.append(entry)
            if unpinned and payment.shortfall:
                payment.auto_tap(unpinned)
            payment.pay()
            state = casting.cast()
        except ValueError:
            if payment is not None:
                payment.rewind()
            if not casting.is_settled:
                casting.cancel()
            raise
        self.put_on_stack(state, casting.caster)
        self.retain_priority(casting.caster)
        return state

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
        if land.zone is not Zone.HAND:
            # CR 305.1 plays a land "from their hand"; CR 701.18a's "from the
            # zone it's in (usually the hand)" is the wider action, and only an
            # effect can open one of those other zones (CR 601.3's twin for
            # lands). A `PlayPermission` that says *cast* is not one of them -
            # CR 601.1a keeps playing a land and casting a spell apart.
            permission = self.play_permission_for(land, username, PlayAction.PLAY)
            if permission is None:
                granted = play_permissions_on(self, land)
                if granted:
                    # A permission names this object and does not stretch this
                    # far - say which way it falls short (cast-not-play, wrong
                    # player, expired) rather than "nothing allows this".
                    raise ValueError(
                        granted[0].why_not(land, username, self, action=PlayAction.PLAY)
                    )
                raise ValueError(
                    f"nothing allows {username} to play {land.name} from the "
                    f"{land.zone.value} (CR 305.1, CR 701.18a)"
                )

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
        with self._id_allocator_scope():
            self.enter_the_battlefield(land, username, was_cast=False)
            self.put_triggers_on_stack()
        return land

    # -- determining a spell's total cost (CR 601.2f) ----------------------

    def cost_reduction_for(
        self,
        spell: CardState,
        caster: str | None = None,
        targets: Sequence[TargetRef] | None = None,
    ) -> ManaCost:
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

        Mystical Dispute's own shape reads a different kind of "right now":
        "This spell costs {2} less to cast if it targets a blue spell." is not
        a fact about the board at all, it is about *this spell's own
        announced target* (CR 601.2c), which is chosen before CR 601.2f
        determines the cost - `targets` is `Casting.targets` at that moment,
        the same `list[TargetRef]` `choose_targets` already populated.
        Without `targets` (a caller that never passed any) this half simply
        finds nothing to check, the same as any other condition this reads
        finding no match.

        Four more shapes read the same "right now", each counting something
        different, and all of them generic-mana reductions that CR 118.7a
        confines to the generic component ("Effects that reduce a cost by an
        amount of generic mana affect only the generic mana component of that
        cost. They can't affect the colored or colorless mana components") -
        `ManaCost.minus` is what enforces that, so Leyline Binding's {5}{W}
        with all five basic land types out settles on {W} rather than {0}:

        - **a per-turn history** - Hollow One's "for each card you've cycled or
          discarded this turn", counted in `cards_discarded_this_turn`;
        - **domain** - Scion of Draco's and Leyline Binding's "for each basic
          land type among lands you control" (CR 305.6's five). *Domain* is an
          ability word, and CR 207.2c gives ability words "no special rules
          meaning", so there is no rule to cite beyond the sentence itself;
        - **an opponent's board** - Obsidian Charmaw's "for each land your
          opponents control that could produce {C}", which CR 106.7 defines as
          "any type of mana that an ability of that permanent would produce if
          the ability were to resolve at that time";
        - **affinity** - CR 702.41a: "'Affinity for [text]' means 'This spell
          costs {1} less to cast for each [text] you control.'" Read off the
          keyword line, not off its reminder text, which CR 207.2 makes
          italics with no game function.

        Every shape found is added up rather than raced: nothing in the pool
        prints two, but a card that did would get both, which is what CR 601.2f
        says happens ("Some effects may increase or reduce the cost to pay",
        plural). A card whose reduction sentence this does not recognise
        reduces nothing.
        """
        # Same DFC-family fix as `effect_for` above: a modal-DFC/transform
        # spell's reduction clause lives on `card_faces`, not the raw
        # top-level `oracle_text` field, so this has to read `oracle_text`
        # (which already falls back to the up face) rather than `card.oracle_text`.
        text = spell.oracle_text or ""
        owner = caster or spell.controller or self.active_player.username
        amount = 0

        match = _COSTS_LESS_PER_CARD_TYPE.search(text)
        if match is not None:
            types = {card_type for card in self.player(owner).graveyard for card_type in card.types}
            amount += int(match.group(1)) * len(types)

        discarded = _COSTS_LESS_PER_CARD_DISCARDED_RE.search(text)
        if discarded is not None:
            amount += int(discarded.group(1)) * self.cards_discarded_this_turn.get(owner, 0)

        domain = _COSTS_LESS_PER_BASIC_LAND_TYPE_RE.search(text)
        if domain is not None:
            amount += int(domain.group(1)) * len(self.basic_land_types_controlled(owner))

        charmaw = _COSTS_LESS_PER_OPPONENT_COLORLESS_LAND_RE.search(text)
        if charmaw is not None:
            lands = [
                permanent
                for permanent in self.battlefield
                if permanent.controller is not None
                and permanent.controller != owner
                and Type.LAND in self.characteristics_of(permanent).types
                and self.could_produce_colorless(permanent)
            ]
            amount += int(charmaw.group(1)) * len(lands)

        affinity = _AFFINITY_RE.search(text)
        if affinity is not None:
            amount += self._affinity_count(affinity.group("what").lower(), owner)

        target_match = _COSTS_LESS_IF_TARGETS_COLOR_SPELL_RE.search(text)
        if target_match is not None and targets:
            color = _COLOR_WORDS[target_match.group("color").lower()]
            for ref in targets:
                if ref.is_player:
                    continue
                target = self.find_by_id(ref.card_id)
                # CR 109.2b: "spell" means an object on the stack - a target
                # that has already left the stack (countered, or already
                # resolved by the time this is asked) is not a spell any
                # more and cannot satisfy "if it targets a ... spell".
                if target is None or target.zone is not Zone.STACK:
                    continue
                if color in target.colors:
                    amount += int(target_match.group(1))
                    break

        return ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()

    def basic_land_types_controlled(self, controller: str) -> frozenset[str]:
        """The basic land types (CR 305.6) among lands this player controls -
        *domain*, which CR 207.2c leaves as an ability word with no rules
        meaning of its own.

        CR 305.6: "The basic land types are Plains, Island, Swamp, Mountain,
        and Forest. If an object uses the words 'basic land type,' it's
        referring to one of these subtypes."

        Read off `characteristics_of`, not off the printed type line, because
        CR 613.1d's layer 4 is where a land *gains* a type: Dryad of the
        Ilysian Grove's "Lands you control are every basic land type in
        addition to their other types" makes one land worth all five, and
        counting the printing would miss it. A land whose types layer 4 has not
        touched reads back exactly what it prints, so nothing else changes.
        """
        return frozenset(
            subtype
            for permanent in self.permanents_controlled_by(controller)
            for chars in [self.characteristics_of(permanent)]
            if Type.LAND in chars.types
            for subtype in chars.subtypes
            if subtype in BASIC_LAND_TYPES
        )

    def could_produce_colorless(self, permanent: CardState) -> bool:
        """Whether this permanent could produce {C} right now (CR 106.7).

        CR 106.7: "The type of mana a permanent could produce at any time
        includes any type of mana that an ability of that permanent would
        produce if the ability were to resolve at that time" - so this asks the
        permanent's mana abilities what they would add, never whether any mana
        was actually made. Obsidian Charmaw's "for each land your opponents
        control that could produce {C}" is the only reader today.

        Printed abilities and `granted_ability_texts`'s own are both asked, the
        same pair `machines/cost.py` taps a source with: Urza's Saga chapter I
        grants "{T}: Add {C}." onto a land that prints no mana ability at all,
        and that land could produce {C}. The board-conditional clauses ("If you
        control an Urza's Mine and an Urza's Power-Plant, add {C}{C}{C}
        instead") are resolved through `ManaAbility.effective`, so the answer is
        the one that holds for the board as it stands - which is what "at any
        time" in CR 106.7 pins it to.

        `any_color` abilities are not counted: CR 106.1b makes colorless one of
        the six *types* of mana but not one of the five colors, so "one mana of
        any color" is never {C}.
        """
        return Color.COLORLESS in self.colors_could_produce(permanent)

    def colors_could_produce(
        self, permanent: CardState, *, skip_could_produce_abilities: bool = False
    ) -> frozenset[Color]:
        """Every type of mana this permanent could produce right now (CR 106.7).

        CR 106.7: "The type of mana a permanent could produce at any time
        includes any type of mana that an ability of that permanent would
        produce if the ability were to resolve at that time." So each of its
        mana abilities is asked what it would add, against the board as it
        stands - never whether any mana was actually made, whether the
        permanent is untapped, or whether its controller could pay to activate
        it.

        "Type" is CR 106.1b's six, colorless included, so `Color.COLORLESS` is
        a member of the answer like any other. An `any_color` ability
        contributes CR 106.1a's five colours and not colorless.

        Printed and `granted_ability_texts` abilities are both asked, the same
        pair `machines/cost.py` taps a source with: Urza's Saga chapter I
        grants "{T}: Add {C}." onto a land that prints no mana ability at all.

        **`skip_could_produce_abilities` is the recursion guard.** Reflecting
        Pool's own "{T}: Add one mana of any type that a land you control could
        produce" is itself a land whose type is defined by a survey, so
        surveying a board of two Reflecting Pools - or a Pool and an Exotic
        Orchard pointed at each other - would recurse forever. CR 106.7 has no
        fixed point to offer there, so a permanent whose ability is itself a
        survey contributes nothing to someone else's survey; every other land
        answers normally. The answer stays under-inclusive rather than wrong,
        which is the same direction `colors_land_types_could_produce` errs in.
        """
        granted = granted_mana_abilities(permanent.granted_ability_texts)
        rewritten = rewritten_ability_lines(self, permanent)
        if rewritten is not None:
            # CR 613.5: once a continuous effect has rewritten the printed
            # lines, those computed lines are the ones this permanent has -
            # which is where a Blood Mooned nonbasic land's intrinsic "{T}: Add
            # {R}" comes from (CR 305.6), since nothing prints it. The grants
            # are still added on top, being layer 6 effects (CR 613.1f) applied
            # after the layer 4 change that caused the rewrite, so a Blood
            # Mooned Urza's Saga "could produce" both {R} and its chapter I
            # {C} - which is what CR 106.7 is asking.
            abilities = granted_mana_abilities(rewritten) + granted
        else:
            # Plus whatever layer 4 added without removing anything: a land
            # granted a basic land type could produce that type's mana
            # (CR 305.6), which is exactly what CR 106.7 is asking about.
            abilities = (
                parse_mana_abilities(permanent.card, permanent.up_face_name)
                + granted
                + granted_mana_abilities(added_ability_lines(self, permanent))
            )
        if not abilities:
            return frozenset()
        controller = permanent.controller_or_owner
        land_types = self._controlled_land_types(controller)
        own_counters = frozenset(permanent.counters.counts)
        has_imprinted_card = self.card_imprinted_on(permanent.id) is not None

        colors: set[Color] = set()
        for ability in abilities:
            if ability.could_produce is not None:
                if skip_could_produce_abilities:
                    continue
                surveyed = self._could_produce_survey(ability.could_produce, controller)
                options, any_color = ability.effective(
                    land_types,
                    own_counters,
                    has_imprinted_card,
                    could_produce_colors=surveyed,
                )
            else:
                options, any_color = ability.effective(land_types, own_counters, has_imprinted_card)
            if any_color:
                colors.update(_COLOR_WORDS.values())
            for option in options:
                colors.update(option)
        return frozenset(colors)

    def _could_produce_survey(
        self, which: CouldProduce, controller: str | None
    ) -> frozenset[Color]:
        """CR 106.7's survey itself: the types of mana the lands the clause
        names could produce right now.

        Reflecting Pool asks about "a land you control", Exotic Orchard about
        "a land an opponent controls" - `CouldProduce` is which. Every surveyed
        land is asked with the recursion guard on, so a survey never consults
        another survey (see `colors_could_produce`).

        CR 613.5: "land" here is the computed board, not the printed line -
        Toph, the First Metalbender's "Nontoken artifacts you control are
        lands in addition to their other types" makes an artifact a land the
        survey has to see, and the printed `CardState.types` never would.
        """
        colors: set[Color] = set()
        board = self.computed_board()
        for land in self.battlefield:
            if Type.LAND not in board.of(land).types:
                continue
            land_controller = self.controller_of(land).username
            if which is CouldProduce.LANDS_YOU_CONTROL:
                if land_controller != controller:
                    continue
            elif land_controller == controller:
                continue
            colors.update(self.colors_could_produce(land, skip_could_produce_abilities=True))
        return frozenset(colors)

    def _affinity_count(self, what: str, controller: str) -> int:
        """How much CR 702.41a's affinity takes off, in generic mana.

        "'Affinity for [text]' means 'This spell costs {1} less to cast for
        each [text] you control.'" - one generic per matching permanent, and
        the {1} is the rule's, not the card's, so the count *is* the amount.
        A "[text]" neither `_AFFINITY_CARD_TYPES` nor `_AFFINITY_SUBTYPES`
        names is left at nothing rather than guessed at.
        """
        card_type = _AFFINITY_CARD_TYPES.get(what)
        subtype = _AFFINITY_SUBTYPES.get(what)
        if card_type is None and subtype is None:
            return 0
        counted = 0
        for permanent in self.permanents_controlled_by(controller):
            chars = self.characteristics_of(permanent)
            matches = (card_type is not None and card_type in chars.types) or (
                subtype is not None and subtype in chars.subtypes
            )
            # One permanent is one count however many ways it matches: CR
            # 205.2b makes an artifact creature both types, and "affinity for
            # artifacts" counts artifacts, not card types.
            counted += 1 if matches else 0
        return counted

    def static_cost_modifiers_for(
        self, spell: CardState, caster: str | None = None
    ) -> tuple[list[ManaCost], list[ManaCost], int | None]:
        """Board-wide static cost increases, decreases, and the floor in play
        right now (CR 601.2f, 611.3).

        Unlike `cost_reduction_for`, which reads *this* spell's own text for a
        self-discount, this reads every *other* permanent's static ability for
        a tax, a discount, or a floor on spells in general: Sphere of
        Resistance and Thorn of Amethyst's flat increases, Damping Sphere's
        per-spell-this-turn increase, Trinisphere's floor, the Medallion
        cycle's/Ral, Monsoon Mage's own color- or type-scoped discount.
        `Casting.total_cost` folds this in for every ordinary cast, so nothing
        has to opt in the way `determine_total_cost` does for a self-reduction.

        A permanent whose text names a card-type qualifier ("Noncreature
        spells cost {1} more") only taxes a spell that lacks that type
        (CR 205.2b: a multi-type card is checked against all of them). A
        permanent whose ability requires being untapped (Trinisphere's own
        clause) is skipped while tapped (CR 611.3b: a static ability's effect
        applies only while its source carries it). `COLOR_DECREASE`/
        `TYPE_DECREASE` are controller-scoped ("spells *you* cast"): only
        counted when the permanent's controller is `caster`.

        Text that reads like a cost modifier but does not match one of
        `cost_modifier_effect`'s recognised shapes - Grand Arbiter Augustin
        IV's controller-relative "Spells your opponents cast cost {1} more to
        cast" - is neither applied nor silently skipped: a `CostModifierNotice`
        is appended to `cost_modifier_notices` instead (DDR#978 - an increase
        that fails to apply looks identical to ordinary play). Deduplicated by
        source, since this runs every time a cost is priced.

        A loyalty-ability-granted, time-boxed discount - Ral, Monsoon Mage's
        own "+1: Until your next turn, instant and sorcery spells you cast
        cost {1} less to cast." - is not read off any live permanent's text
        (Ral may have transformed away since granting it), so it is folded in
        separately here from `casting_rule_effects`
        (`CastingRuleKind.INSTANT_SORCERY_COST_REDUCTION_GRANT`), the same
        `Duration.UNTIL_YOUR_NEXT_TURN` record Teferi, Time Raveler's own +1
        already uses.
        """
        caster = caster or spell.controller or self.active_player.username
        increases: list[ManaCost] = []
        decreases: list[ManaCost] = []
        floor: int | None = None
        already_noticed = {notice.source_id for notice in self.cost_modifier_notices}

        for permanent in self.battlefield:
            # Same DFC-family fix as `effect_for`: `oracle_text` reads the up
            # face, `card.oracle_text` is null for a modal-DFC/transform
            # permanent and would silently skip its static ability.
            # `class_ability_text` narrows further for a Class permanent
            # (CR 716.2a): a level-gated paragraph is not "in effect" yet.
            #
            # Read line by line, not as one blob: CR 604.1 makes each
            # sentence-per-line its own static ability (Grand Arbiter
            # Augustin IV prints three - two readable color discounts and one
            # controller-relative tax this wave still cannot read), and
            # `cost_modifier_effect` only ever answers for the *first* shape
            # it recognises in whatever text it is given. Reading the whole
            # card at once would either apply only the first ability and
            # silently drop the rest, or (worse) let one recognised line's
            # match suppress the fail-closed notice the *other*, unreadable
            # line still needs - splitting first is what keeps each ability
            # independent, matching this project's "one paragraph is one
            # ability" rule instead of quietly merging every line on a card
            # into a single verdict.
            #
            # Only a genuine `AbilityKind.STATIC` line qualifies (CR 604.1's
            # own "written as statements" versus CR 602.1's "[Cost]:
            # [Effect]" for an activated ability). `class_ability_text` still
            # prints an activated or triggered ability's line right alongside
            # a static one, and `cost_modifier_effect`'s own shapes are
            # unanchored substring matches - Ral, Leyline Prodigy's +1
            # ("Until your next turn, instant and sorcery spells you cast
            # cost {1} less to cast.") contains that exact discount sentence
            # inside an activated ability's *effect*, gated on the loyalty
            # cost being paid and on `Duration.UNTIL_YOUR_NEXT_TURN` (recorded
            # separately as a `CastingRuleEffect` once actually activated -
            # see `create_instant_sorcery_cost_reduction_grant`). Without this
            # filter the mere printed line made the discount permanent and
            # unconditional the instant Ral transformed, whether or not the
            # +1 was ever activated: a real defect this wave closes.
            up_face_name = permanent.up_face_name or permanent.card.name
            static_lines = {
                ability.raw.strip()
                for ability in parse_abilities(permanent.card)
                if ability.face == up_face_name
                and ability.kind is AbilityKind.STATIC
                and (ability.class_level is None or ability.class_level <= permanent.class_level)
            }
            for line in (permanent.class_ability_text or "").split("\n"):
                text = line.strip()
                if not text or text not in static_lines:
                    continue
                # Read before `cost_modifier_effect`, which has no shape for a
                # discount *gated* on a count rather than scaled by one:
                # Gran-Gran's "Noncreature spells you cast cost {1} less to
                # cast as long as there are three or more Lesson cards in your
                # graveyard." The gate is checked against the graveyard as it
                # stands when CR 601.2f determines the cost, which is five
                # steps after CR 601.2a moved the spell being cast off it -
                # so flashing back one of exactly three Lessons leaves two and
                # gets no discount.
                gated = _COSTS_LESS_WHILE_GRAVEYARD_COUNT_RE.search(text)
                if gated is not None:
                    if self._gated_discount_applies(gated, spell, permanent, caster):
                        decreases.append(ManaCost.parse(f"{{{int(gated.group('amount'))}}}"))
                    continue

                effect = cost_modifier_effect(text)
                if effect is None:
                    if (
                        looks_like_unparsed_cost_modifier(text)
                        and permanent.id not in already_noticed
                    ):
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
                    if (
                        effect.excludes_type is not None
                        and effect.excludes_type in spell.card.types
                    ):
                        continue
                    increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.NAMED_INCREASE:
                    # Disruptor Flute: "Spells with the chosen name cost {3}
                    # more to cast." The name is CR 614.12a's choice, made as
                    # the permanent entered and recorded on `CardState.choice`;
                    # nothing about the printed line says who it taxes, so a
                    # Flute that somehow never made its choice taxes nothing
                    # and says so rather than quietly applying to everything.
                    chosen = permanent.choice
                    if chosen is None or chosen.kind is not ChoiceKind.CARD_NAME:
                        if permanent.id not in already_noticed:
                            already_noticed.add(permanent.id)
                            self.cost_modifier_notices.append(
                                CostModifierNotice(
                                    source_id=permanent.id, source_name=permanent.name, text=text
                                )
                            )
                        continue
                    if chosen.value == spell.name or chosen.value == spell.card.name:
                        increases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.PER_SPELL_INCREASE:
                    prior = len(self.spells_cast_this_turn.get(caster, []))
                    if prior:
                        increases.append(ManaCost.parse(f"{{{effect.amount * prior}}}"))
                elif effect.kind is CostModifierKind.COLOR_DECREASE:
                    if permanent.controller != caster:
                        continue
                    if effect.applies_to_color in spell.colors:
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                elif effect.kind is CostModifierKind.TYPE_DECREASE:
                    if permanent.controller != caster:
                        continue
                    if effect.excludes_type is not None:
                        if effect.excludes_type not in spell.types:
                            decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))
                    elif effect.applies_to_types is not None and any(
                        t in spell.types for t in effect.applies_to_types
                    ):
                        decreases.append(ManaCost.parse(f"{{{effect.amount}}}"))

        for grant in self.casting_rule_effects:
            if (
                grant.kind == CastingRuleKind.INSTANT_SORCERY_COST_REDUCTION_GRANT
                and grant.controller == caster
                and grant.amount is not None
                and (Type.INSTANT in spell.types or Type.SORCERY in spell.types)
            ):
                decreases.append(ManaCost.parse(f"{{{grant.amount}}}"))

        return increases, decreases, floor

    def _gated_discount_applies(
        self,
        gated: "re.Match[str]",
        spell: CardState,
        source: CardState,
        caster: str,
    ) -> bool:
        """Whether a `_COSTS_LESS_WHILE_GRAVEYARD_COUNT_RE` line discounts this
        spell right now - Gran-Gran's "Noncreature spells you cast cost {1}
        less to cast as long as there are three or more Lesson cards in your
        graveyard."

        Three gates, all of which have to hold:

        - **whose spell** - "spells *you* cast" is controller-scoped, the same
          way `CostModifierKind.COLOR_DECREASE`/`TYPE_DECREASE` already are, so
          the permanent's controller has to be the caster;
        - **which spells** - "Noncreature" excludes the named type (CR 205.2b:
          an object with more than one card type "satisf[ies] the criteria for
          any effect that applies to any of their card types", so an artifact
          creature is a creature spell and gets nothing);
        - **the gate itself** - "three or more `<X>` cards in your graveyard",
          counted against the caster's graveyard as it stands. The count is a
          gate, not a multiplier: four Lessons discount exactly as much as
          three do.

        The counted noun is matched against both card types (CR 205.2a) and
        subtypes (CR 205.3) - "Lesson" is a subtype of an instant or sorcery
        card, and the same sentence would read "creature cards" on a card that
        printed one.
        """
        if source.controller is not None and source.controller != caster:
            return False

        named = gated.group("type").lower()
        spell_type = next((t for t in Type if t.value.lower() == named), None)
        if spell_type is not None:
            has_type = spell_type in spell.types
            if bool(gated.group("excludes")) == has_type:
                return False

        wanted = gated.group("count").lower()
        needed = int(wanted) if wanted.isdigit() else _NUMBER_WORDS.get(wanted, 0)
        if not needed:
            return False

        noun = gated.group("subtype").strip().lower()
        counted = 0
        for card_state in self.player(caster).graveyard:
            subtypes = {subtype.lower() for subtype in card_state.subtypes}
            types = {card_type.value.lower() for card_type in card_state.types}
            if noun in subtypes or noun in types:
                counted += 1
        return counted >= needed

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
        on its own, so a scenario that wants Emrakul's discount - or Mystical
        Dispute's own "if it targets a blue spell" - calls this instead of
        `casting.determine_cost()`. Routing it into `machines/casting.py` is
        the tidier home - see `docs/engine-coverage.md`. `casting.targets`
        (CR 601.2c's announcement, already made by the time CR 601.2f runs)
        is what Mystical Dispute's own condition reads.
        """
        reduction = self.cost_reduction_for(
            casting.spell,  # type: ignore[attr-defined]
            casting.caster,  # type: ignore[attr-defined]
            targets=casting.targets,  # type: ignore[attr-defined]
        )
        if reduction.symbols:
            # Appended straight onto the casting's reductions rather than through
            # `reduce_cost`, which belongs to CR 601.2b and refuses to run once
            # targets have been chosen. CR 601.2f is a later step than that.
            casting.cost_reductions.append(reduction)  # type: ignore[attr-defined]
        return casting.determine_cost()  # type: ignore[attr-defined]

    # -- activated abilities (CR 602) --------------------------------------

    def activated_abilities(self, permanent: CardState) -> list[ActivatedAbility]:
        """Every activated ability this permanent has, printed then granted.

        CR 602.1: an activated ability is written `[Cost]: [Effect.]
        [Activation instructions (if any).]`. The index into this list is what
        `activate_ability` and `machines/effects.py` key on.

        Narrowed to the face that is up (CR 712.8d, 712.8e, 712.8f, CR 109.3):
        a transformed Ajani, Nacatl Pariah has his back face's `+2`, `0` and
        `−4` and nothing else, and Duskwatch Recruiter loses its `{2}{G}` look
        the moment it becomes Krallenhorde Howler. `_activated_index` reads the
        same face, so an ability's index stays the index of this list.

        Printed abilities come first, then `CardState.granted_ability_texts`'s
        own - Urza's Saga's chapter II grant ("This Saga gains '{2}, {T}:
        Create a 0/0 colorless Construct artifact creature token ...'") is the
        only source of these in the pool. Appending rather than interleaving
        keeps a printed ability's own index stable as more get granted.

        **CR 613.5 / CR 707.2**: when a continuous effect has rewritten the
        permanent's computed ability text away from the printed card - a layer 1
        copy effect is the only shape that does - the *computed* abilities are
        the ones it has, and the printed card is not consulted at all. A land
        that has become a copy of Sol Ring offers `{T}: Add {C}{C}` and nothing
        of its own. `rewritten_ability_lines` answers None for every permanent
        whose printed lines all survive, so an ordinary grant still appends and
        every printed ability's index stays where it was.
        """
        granted = granted_activated_abilities_of(permanent.granted_ability_texts)
        rewritten = rewritten_ability_lines(self, permanent)
        if rewritten is not None:
            # A rewrite replaces the *printed* text, and nothing more. An
            # ability granted to this object by something that already resolved
            # is a separate continuous effect (CR 611.2) applied in layer 6
            # (CR 613.1f), which is after both layer 1's copy effects
            # (CR 613.2c) and layer 4's type changes (CR 613.1d) - so it is
            # still on the object however thoroughly the printed lines were
            # rewritten, and has to be appended here too.
            #
            # Urza's Saga under Blood Moon is the case that needs it: CR 305.7
            # sets its subtype to Mountain and takes away every ability its
            # rules text generated, leaving the computed line list as just the
            # Mountain's intrinsic "{T}: Add {R}" (CR 305.6) - but the "{T}: Add
            # {C}" and the Construct maker its chapters already granted are
            # untouched, so the land taps for {C} *or* {R} and still makes
            # tokens. Dropping the grants here made it a bare Mountain.
            base = activated_abilities_from_lines(rewritten, permanent.card, permanent.up_face_name)
            already = {ability.raw for ability in base}
            return base + [ability for ability in granted if ability.raw not in already]
        # An ability a continuous effect *added* without taking any printed one
        # away - the intrinsic "{T}: Add [mana symbol]" that comes with a basic
        # land type granted in layer 4 (CR 305.6, CR 613.1d), which is how
        # Urborg turns every land into a black source. Appended last so every
        # printed ability keeps the index it had.
        added = activated_abilities_from_lines(
            added_ability_lines(self, permanent), permanent.card, permanent.up_face_name
        )
        base = activated_abilities_of(permanent.card, permanent.up_face_name) + granted
        seen = {ability.raw for ability in base}
        return base + [ability for ability in added if ability.raw not in seen]

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
        that object is on the battlefield" is the default, and an ability whose
        printed text names a different zone is refused here too - the zone
        `machines/abilities._activated_ability_zone` read off the text
        (`ActivatedAbility.zone`, with `zone_rule` naming which CR 113.6
        sub-rule put it there: CR 113.6b for "activate only from your
        graveyard", CR 113.6j for a cost that cannot be paid on the
        battlefield, CR 113.6m for an effect that moves the card out of a named
        zone). Both directions are checked: Gollum, Patient Plotter's
        graveyard-only ability is not activatable while Gollum is on the
        battlefield, and an ordinary battlefield ability is not activatable
        from anywhere else. Off-battlefield activation itself goes through
        `machines/keywords.off_battlefield_activation`, which checks the same
        zone - see `docs/engine-coverage.md`.

        A life payment in the cost is checked as well: **CR 119.4** - "If a cost
        or effect allows a player to pay an amount of life greater than 0, the
        player may do so only if their life total is greater than or equal to
        the amount of the payment" - with **CR 119.4b**'s "players can always
        pay 0 life" as the exemption. Paying down to exactly 0 is legal; losing
        the game at 0 life is a separate state-based action (CR 704.5a),
        checked when a player would next receive priority.
        """
        abilities = self.activated_abilities(permanent)
        if index >= len(abilities):
            return f"{permanent.name} has no activated ability number {index}"
        ability = abilities[index]
        controller = controller or self.controller_of(permanent).username

        if ability.zone is not None and permanent.zone is not ability.zone:
            # CR 113.6b/113.6j/113.6m, whichever `machines/abilities.py` read
            # off the printed text: an ability that functions in one named zone
            # does not exist to be activated from any other. Checked before the
            # flat battlefield rule below so the refusal names the real reason
            # - "functions in the graveyard" rather than "not on the
            # battlefield" - and so the battlefield itself is refused too,
            # which is DDR#970's Gollum sacrificing itself to its own
            # graveyard-only ability.
            return (
                f"{permanent.name}'s ability functions in the {ability.zone.value}, "
                f"but it is in the {permanent.zone.value} ({ability.zone_rule})"
            )
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

        prohibited = self._activation_prohibition(permanent, ability)
        if prohibited is not None:
            return prohibited

        if ability.mana is not None and ability.mana.unparsed_rider is not None:
            # CR 405.6c: "If a mana ability both produces mana and has
            # another effect, the mana is produced and the other effect
            # happens immediately." An effect this parser cannot read is not
            # one it can silently drop - the paragraph is one ability and it
            # resolves whole or not at all (see the mana ability rider row
            # in docs/engine-coverage.md), refused here, before any cost is
            # paid, rather than after `{T}` is already spent.
            return (
                f"{permanent.name}'s mana ability has an effect this engine cannot read "
                f"({ability.mana.unparsed_rider!r}), so it refuses to activate rather than "
                "silently dropping it (CR 405.6c)"
            )

        life_owed = 0
        for piece in ability.costs:
            if piece.kind is CostKind.PAY_LIFE:
                digits = re.search(r"\d+", piece.text)
                life_owed += int(digits.group()) if digits else 0
        if life_owed > 0 and self.player(controller).life < life_owed:
            # CR 119.4: an amount of life greater than 0 may be paid "only if
            # their life total is greater than or equal to the amount of the
            # payment" - CR 119.4b's "players can always pay 0 life" is why
            # only a positive amount is checked at all. Refused here, before
            # anything is announced, rather than at `CostPayment.pay` time:
            # an ability nobody can pay for is not one to offer.
            return (
                f"{controller} cannot pay {life_owed} life from a life total of "
                f"{self.player(controller).life}, so {permanent.name}'s ability "
                "cannot be activated (CR 119.4)"
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

        if ability.class_level_target is not None:
            # CR 716.2a: "[Cost]: Level N" means "[Cost]: This Class's level
            # becomes N. Activate only if this Class is level N-1 and only as
            # a sorcery" - both halves of that sentence, checked the same way
            # "Activate only as a sorcery" already is below for an ordinary
            # printed instruction, since this one is never actually printed
            # as words on the card.
            if not self.can_cast_sorcery(controller):
                return (
                    f"{permanent.name}'s Level {ability.class_level_target} bar can only be "
                    f"activated as a sorcery: {controller}'s main phase, with the stack empty "
                    "(CR 716.2a, CR 307.5)"
                )
            required = ability.class_level_target - 1
            if permanent.class_level != required:
                return (
                    f"{permanent.name} is level {permanent.class_level}, not level {required}, "
                    f"so its Level {ability.class_level_target} bar cannot be activated "
                    "(CR 716.2a)"
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

        CR 613.5: every count below is read off the computed board - a card
        type (Liquimetal Coating's "becomes an artifact"), a creature's
        power, or whether it is a creature at all (an earthbent land) can
        each be true only there.
        """
        instructions = ability.instructions or ""
        controlled = self.permanents_controlled_by(controller)
        board = self.computed_board()

        match = _ACTIVATE_ONLY_IF_CONTROL.search(instructions)
        if match is not None:
            needed = _CONDITION_COUNT_WORDS.get(match.group("count").lower())
            card_type = _card_type_named(match.group("quality"))
            if needed is not None and card_type is not None:
                count = sum(1 for state in controlled if card_type in board.of(state).types)
                return count >= needed

        match = _ACTIVATE_ONLY_IF_POWER.search(instructions)
        if match is not None:
            threshold = int(match.group("power"))
            return any(
                board.of(state).is_creature
                and board.of(state).power is not None
                and board.of(state).power >= threshold
                for state in controlled
            )

        match = _ACTIVATE_ONLY_IF_ENTERED_THIS_TURN.search(instructions)
        if match is not None:
            needed = _CONDITION_COUNT_WORDS.get(match.group("count").lower())
            if needed is not None:
                turn_number = getattr(self.turn, "turn_number", None)
                if turn_number is None:
                    return False
                entered = sum(
                    1
                    for state in controlled
                    if board.of(state).is_creature and state.turn_entered == turn_number
                )
                return entered >= needed

        match = _ACTIVATE_ONLY_IF_DELIRIUM.search(instructions)
        if match is not None:
            needed = _CONDITION_COUNT_WORDS.get(match.group("count").lower())
            if needed is not None:
                return count_card_types(self.player(controller).graveyard) >= needed

        return True

    def _activation_prohibition(
        self, permanent: CardState, ability: ActivatedAbility
    ) -> str | None:
        """Why a static ability in play forbids this activation, or None (CR 602.5).

        "A player can't begin to activate an ability that's prohibited from
        being activated." The prohibitions read here are the ones a permanent's
        own static ability creates - CR 604.2: "Static abilities create
        continuous effects ... These effects are active as long as the permanent
        with the ability remains on the battlefield" - which is why the whole
        battlefield is re-read on every call rather than cached (CR 611.3a: a
        continuous effect from a static ability "isn't 'locked in'; it applies
        at any given moment to whatever its text indicates").

        **Whose permanents.** Karn, the Great Creator says "your opponents
        control", and "your" is the *source's* controller, not the activating
        player's - so the artifact is checked against Karn's controller. A
        permanent the source's own controller controls is never caught, which
        is the half of this rule that a one-player scenario cannot see. The
        symmetric printings of the same shape (Collector Ouphe, Clarion
        Conqueror) omit that clause and catch every permanent, their
        controller's included, which is what `opponents_only` distinguishes.

        **Which permanents.** The quality is read off the *computed* board
        (CR 613.5, `characteristics_of`), so an artifact Karn's own `+1`
        animated is still an artifact and still prohibited, and a permanent an
        effect turned into an artifact becomes prohibited the moment it does.

        A sentence that prohibits activation in a shape `_parse_activation_
        prohibition` cannot read is **not** silently treated as permission: it
        records a `LayerNotice` - the record kept for a static ability whose
        continuous effect this engine did not build - and the activation is
        left alone. That is the one direction that fails safe here; refusing
        every activation on an unreadable sentence would lock up boards the
        sentence was never about.
        """
        for source in list(self.battlefield):
            for line in parse_abilities(source.card):
                if line.kind is not AbilityKind.STATIC:
                    continue
                text = (line.text or "").strip()
                if not _LOOKS_LIKE_ACTIVATION_PROHIBITION_RE.match(text):
                    continue
                if _CHOSEN_NAME_SUBJECT_RE.search(text):
                    continue
                prohibition = _parse_activation_prohibition(text)
                if prohibition is None:
                    self._record_unread_static_line(source, text)
                    continue
                if not self._still_has_static_line(source, text):
                    continue
                if prohibition.opponents_only and (
                    self.controller_of(permanent).username == self.controller_of(source).username
                ):
                    # "your opponents control": the source's controller's own
                    # permanents are untouched.
                    continue
                if prohibition.qualities and not any(
                    self._has_computed_type(permanent, quality) for quality in prohibition.qualities
                ):
                    continue
                if prohibition.mana_abilities_exempt and ability.mana is not None:
                    # CR 605.1a: a mana ability the sentence spares.
                    continue
                return (
                    f"{permanent.name}'s activated abilities can't be activated: "
                    f"{source.name} says so (CR 602.5, CR 611.1)"
                )
        return None

    def _record_unread_static_line(self, source: CardState, text: str) -> None:
        """Record a static ability sentence this engine could not read (CR 611.1).

        The static ability generates a continuous effect that affects the rules
        of the game, and nothing here built it - which is exactly what
        `LayerNotice` records for a static ability whose continuous effect went
        unmade. Both directions land here: a prohibition read as permission
        would let an illegal activation through, and a *permission* read as
        silence keeps a legal one out. One entry per source, not one per query:
        `why_cannot_activate` and `can_activate_tap_ability` are both called
        constantly.
        """
        already = {
            notice.source_id
            for notice in self.continuous_effects.layer_notices
            if notice.text == text
        }
        if source.id in already:
            return
        self.continuous_effects.layer_notices.append(
            LayerNotice(source_id=source.id, source_name=source.name, text=text)
        )

    def _still_has_static_line(self, permanent: CardState, text: str) -> bool:
        """Whether the computed board still shows this static line (CR 613.1f).

        The static-ability twin of `_still_has_ability`: a permanent that lost
        all abilities in layer 6 has no prohibition to enforce either.
        """
        try:
            computed = self.characteristics_of(permanent)
        except KeyError:
            return True
        if not computed.abilities:
            return not (permanent.oracle_text or "").strip()
        return any(text in line or line in text for line in computed.abilities)

    def _has_computed_type(self, permanent: CardState, card_type: Type) -> bool:
        """Whether the permanent has this card type right now (CR 613.5)."""
        try:
            return card_type in self.characteristics_of(permanent).types
        except KeyError:
            return card_type in permanent.types

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
        if any(ability.raw == text for text in permanent.granted_ability_texts):
            # An ability *granted* to this object is a continuous effect from
            # the resolution that granted it (CR 611.2), applied in layer 6
            # (CR 613.1f) - after the layer 4 type change (CR 613.1d) whose
            # CR 305.7 clause strips the abilities generated from the land's
            # own rules text. So layer 4 taking the printed text away cannot
            # take this one, and the computed line list - which holds what
            # survived layer 4 - is not the place to look for it.
            #
            # Urza's Saga under Blood Moon is the case: chapter I's granted
            # "{T}: Add {C}." used to be found here only by accident, as a
            # substring of the printed chapter line "I - This Saga gains
            # '{T}: Add {C}.'". Blood Moon removes that printed line, and the
            # grant was refused with it.
            return True
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
            elif _cost_refers_to_self(text, permanent):
                chosen = [permanent]
            else:
                chosen = []
            return builder(*chosen, payer=controller, required=1, description=text)

        chosen = []
        while pool and len(chosen) < component.required:
            chosen.append(pool.pop(0))
        if not chosen and _cost_refers_to_self(text, permanent):
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
        exiling: list[CardState] | None = None,
        x_value: int = 0,
    ) -> TotalCost:
        """The total cost of one activation (CR 602.1a, 601.2f).

        CR 602.1a: "the activation cost is everything before the colon". Each
        comma-separated piece was classified by `machines/abilities.py`; this
        turns those pieces into the `TotalCost` that `machines/cost.py` knows how
        to pay. A piece that asks for an object - sacrifice, discard, or the
        "exile a creature card ... and pay its mana cost" shape Back from the
        Brink prints - takes the next card from `sacrificing`, `discarding`,
        or `exiling`; leaving it empty builds a cost that correctly refuses to
        be paid (CR 118.3) rather than one that cannot be built.

        `x_value` is CR 107.3a's X, announced as this activation begins
        (CR 602.2b), the same moment `Casting.determine_cost` fixes X for a
        spell. `ManaCost.with_x` folds it in when the printed cost has one -
        Fiend Artisan's `{X}{B/G}` - and is a no-op otherwise, so every other
        activated ability in the pool is unaffected.
        """
        ability = self.activated_abilities(permanent)[index]
        controller = controller or self.controller_of(permanent).username
        sacrifices = list(sacrificing or [])
        discards = list(discarding or [])
        exiles = list(exiling or [])

        mana = ManaCost()
        components = []
        for piece in ability.costs:
            if piece.kind is CostKind.MANA:
                mana = increase(mana, ManaCost.parse(piece.text).with_x(x_value))
            elif piece.kind is CostKind.TAP:
                components.append(tap_cost(permanent, payer=controller, description=piece.text))
            elif piece.kind is CostKind.UNTAP:
                # CR 107.6: "The untap symbol is {Q}. The untap symbol in an
                # activation cost means 'Untap this permanent.'" The exact
                # mirror of the `{T}` branch above - "this permanent" is the
                # permanent whose ability is being activated, which a bare
                # symbol never names in words for `_cost_refers_to_self` to
                # read. CR 602.5a gates both symbols the same way for a
                # creature, and `why_cannot_activate` already checks that pair.
                components.append(untap_cost(permanent, payer=controller, description=piece.text))
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
                # counter change it asks for is the cost itself.
                #
                # CR 107.7: "Negative loyalty symbols point downward and
                # feature a minus sign followed by a number or an X." A `−X`
                # symbol therefore has no amount of its own - the amount is the
                # X the activating player announces, which CR 602.2b puts at
                # this same moment (the whole of CR 601.2b's announcement,
                # X included). That is `x_value`, already threaded here from
                # `begin_activating`, so the cost is built from it and negated
                # for a minus symbol.
                #
                # CR 606.6 - "A loyalty ability with a negative loyalty cost
                # ... can't be activated unless the permanent has at least that
                # many loyalty counters on it" - is then enforced against the
                # *resolved* amount by `loyalty_cost`'s own payment, which is
                # what makes an announced X larger than the loyalty on the
                # permanent an unpayable cost rather than a silently clamped
                # one.
                amount = ability.loyalty.amount if ability.loyalty else None
                if amount is None:
                    if ability.loyalty is None or not _is_minus_symbol(ability.loyalty.printed):
                        # Not a readable symbol at all - not "−X", just
                        # unparsed. Refusing beats guessing an amount.
                        raise ValueError(f"cannot build a cost for {piece.text!r}")
                    amount = -x_value
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
                if component is None and _exiles_itself_by_name(piece.text, permanent):
                    # CR 201.5: "if an object's text uses its own name, it is
                    # referring to that particular object" - the same
                    # self-reference `_SELF_REFERENCE`'s bare "this" already
                    # reads, spelled with the printed name instead. The Stone
                    # Brain's own "Exile The Stone Brain" and Abstergo
                    # Entertainment's own "Exile Abstergo Entertainment" are
                    # the pool's examples: `_PHRASE_EXILE` only reads "exile
                    # this card" or a quality-and-count phrase, neither of
                    # which a bare self-name is, so it comes back `None` and
                    # is built here instead - straight from the battlefield
                    # (CR 113.6: an activated ability's source is normally
                    # there), the same empty-then-filled shape
                    # `_SELF_REFERENCE`'s branch below uses for "this".
                    component = exile_cost(
                        payer=controller,
                        required=1,
                        description=piece.text,
                        zone=Zone.BATTLEFIELD,
                    )
                if component is None:
                    # A printed cost sentence that is *mana* wearing an action
                    # word - "Waterbend {3}" is CR 701.67a's "Pay [cost]", and
                    # the permission it carries (tap an untapped artifact or
                    # creature for each generic mana) is CR 701.67b's alternate
                    # payment method, which belongs to an open `CostPayment`
                    # rather than to the total cost. `cost_component_for_phrase`
                    # only ever builds non-mana components, so it cannot answer
                    # for one; `total_cost_for_phrase` reads the whole sentence
                    # and hands back both halves.
                    whole = total_cost_for_phrase(piece.text, controller)
                    if whole is not None and whole.mana.symbols:
                        mana = increase(mana, whole.mana.with_x(x_value))
                        components.extend(whole.components)
                        continue
                if component is None:
                    raise ValueError(f"cannot build a cost for {piece.text!r}")
                if not component.cards and (
                    _cost_refers_to_self(piece.text, permanent)
                    or _exiles_itself_by_name(piece.text, permanent)
                ):
                    # "Exert **this** land": only the caller knows which
                    # permanent the ability is on, so the reader builds the
                    # component empty and it is filled in here (CR 602.1a - the
                    # ability's source is the object it is printed on).
                    component = component.model_copy(update={"cards": [permanent]})
                if not component.cards and exiles and component.kind is ComponentKind.EXILE:
                    # Back from the Brink's own shape, the exile half chosen
                    # from `exiling` the same way `_choice_cost` fills
                    # `sacrificing`/`discarding` - this component was not
                    # built through `_choice_cost` because its `CostKind` is
                    # `OTHER`, not `SACRIFICE`/`DISCARD`.
                    chosen: list[CardState] = []
                    while exiles and len(chosen) < component.required:
                        chosen.append(exiles.pop(0))
                    component = component.model_copy(update={"cards": chosen})
                if component.pay_mana_cost_of_chosen:
                    # CR 118.9's own alternative-cost shape, aimed at the just
                    # -chosen card's *own* printed mana cost rather than a
                    # fixed one - only known now that a card was chosen.
                    for card in component.cards:
                        printed = card.card.mana_cost or ""
                        if printed:
                            mana = increase(mana, ManaCost.parse(printed))
                components.append(component)

        if ability.cost_reduction is not None:
            # CR 601.2f, applied to an activated ability's own cost via CR
            # 602.2b: "This ability costs [N] less to activate for each
            # [quality] you control" - read structurally off
            # `ActivatedAbility.cost_reduction` (`machines/abilities.py`
            # already split it from the effect as its own static ability, not
            # a clause of it - see `ActivationCostReduction`'s docstring).
            mana = mana.minus(self.activation_cost_reduction_for(permanent, ability, controller))

        return TotalCost(mana=mana, components=components).assign_payer(controller)

    def activation_cost_reduction_for(
        self, permanent: CardState, ability: ActivatedAbility, controller: str
    ) -> ManaCost:
        """What `ability`'s own "costs [N] less to activate for each [quality]
        you control" sentence takes off its cost right now (CR 601.2f via CR
        602.2b) - the activated-ability twin of `cost_reduction_for`, which
        only ever reads a *spell's* own self-discount.

        The quality is read generically, off its own words - a CR 205.4a
        supertype ("legendary"), a CR 205.2a card type ("creature"), or both -
        the same way `_activation_condition_holds`'s "Activate only if you
        control ..." already counts a quality, so a future card printing this
        exact sentence with a different quality needs no table row either.
        CR 613.5: read off the computed board, not the printed
        `state.card.types`/`.supertypes` - a clone (`BecomeACopy`, CR 707.2,
        707.4) that has become a legendary creature is one only there.

        A quality this cannot read at all records a `CostModifierNotice`
        rather than quietly reducing by nothing - the same "unreadable is not
        the same as no effect" rule `static_cost_modifiers_for` already keeps
        for a permanent's *other* static cost text (DDR#978).
        """
        reduction = ability.cost_reduction
        if reduction is None:
            return ManaCost()

        words = reduction.quality.strip().lower().split()
        supertypes: list[Supertype] = []
        types: list[Type] = []
        for word in words:
            singular = word.removesuffix("s")
            try:
                supertypes.append(Supertype(singular))
                continue
            except ValueError:
                pass
            try:
                types.append(Type(singular))
                continue
            except ValueError:
                pass
        if not types:
            already_noticed = any(
                notice.source_id == permanent.id for notice in self.cost_modifier_notices
            )
            if not already_noticed:
                self.cost_modifier_notices.append(
                    CostModifierNotice(
                        source_id=permanent.id,
                        source_name=permanent.name,
                        text=ability.raw,
                    )
                )
            return ManaCost()

        board = self.computed_board()
        count = sum(
            1
            for state in self.permanents_controlled_by(controller)
            if state.zone is Zone.BATTLEFIELD
            and all(t in board.of(state).types for t in types)
            and all(s in board.of(state).supertypes for s in supertypes)
        )
        amount = reduction.amount * count
        return ManaCost.parse(f"{{{amount}}}") if amount else ManaCost()

    def mana_color_options(
        self, permanent: CardState, index: int = 0, controller: str | None = None
    ) -> tuple[Color, ...]:
        """Every colour `activate_ability`'s own `color=` would accept for
        this mana ability right now (CR 605.1a), or empty when it makes no
        real choice - a single fixed colour, or none at all (CR 106.5).

        Read the same way `activate_ability`'s own mana fast path resolves
        one (CR 605.3b): `ManaAbility.effective`, narrowed by the same
        board-derived CR 106.7 survey and CR 614.12a chosen-colour reading
        that path already computes, then Mox Amber's own CR 106.5 "among
        legendary creatures and planeswalkers you control" narrowing
        (`among_colors`, read off the ability's printed effect text) - so a
        pure enumeration caller (`machines/legal_actions.py`) is offered
        exactly the colours a real activation would accept, not a superset
        guessed from the printed text alone that `activate_ability` would
        then refuse.

        `machines/legal_actions.py`'s own `Action` has no field for a live
        `ManaAbility`, only for ids and plain data - this is what lets it
        name the choice as `Action.color_options` instead: without it, an
        `ACTIVATE_MANA` action for a choice-offering ability (a dual land,
        Birds of Paradise's "any color") was reported affordable with no way
        for a caller to actually complete the call `activate_ability`
        demands.
        """
        ability = self.activated_abilities(permanent)[index]
        if ability.mana is None:
            return ()
        controller = controller or self.controller_of(permanent).username
        land_types = self._controlled_land_types(controller)
        own_counters = frozenset(permanent.counters.counts)
        has_imprinted_card = self.card_imprinted_on(permanent.id) is not None
        chosen = permanent.choice
        chosen_color = (
            Color(chosen.value) if chosen is not None and chosen.kind is ChoiceKind.COLOR else None
        )
        could_produce_colors = (
            self._could_produce_survey(ability.mana.could_produce, controller)
            if ability.mana.could_produce is not None
            else None
        )
        options, any_color = ability.mana.effective(
            land_types,
            own_counters,
            has_imprinted_card,
            could_produce_colors=could_produce_colors,
            chosen_color=chosen_color,
        )
        colors: list[Color] = []
        if any_color:
            colors.extend(_COLOR_WORDS.values())
        elif len(options) > 1:
            for option in options:
                for color in option:
                    if color not in colors:
                        colors.append(color)
        allowed = among_colors(ability.effect, self, controller)
        if allowed is not None:
            colors = [color for color in colors if color in allowed]
        return tuple(colors)

    def begin_turning_face_up(
        self, permanent: CardState, controller: str | None = None
    ) -> CostPayment:
        """Announce turning a face-down morph creature face up, and open its
        payment (CR 702.37e).

        "Any time you have priority, you may turn a face-down permanent you
        control with a morph ability face up. This is a special action; it
        doesn't use the stack. To do this, show all players what the
        permanent's morph cost would be if it were face up, pay that cost,
        then turn the permanent face up." Mirrors `begin_activating`'s own
        two-call split (open the payment, then finish the action) for
        exactly the same reason: paying can take more than one priority-free
        moment (tapping several lands), and CR 116.1 lets a special action
        be taken any time its controller could take one, not only once the
        whole cost is already in hand.

        Raises if the special action is unavailable at all (CR 702.37e's own
        parenthetical, or a permanent that is not face down here), before
        anything has been spent.
        """
        refusal = why_cannot_turn_face_up(permanent)
        if refusal is not None:
            raise ValueError(refusal)
        controller = controller or self.controller_of(permanent).username
        total = turn_face_up_cost(permanent, controller)
        assert total is not None  # `why_cannot_turn_face_up` already checked this
        return CostPayment.for_total(total, game=self, payer=controller)

    def turn_face_up(self, permanent: CardState, controller: str | None = None) -> CardState:
        """Finish turning a face-down permanent face up (CR 702.37e, 708.8).

        The cost is paid by the caller through `begin_turning_face_up`; this
        is the half that actually reveals the card and fires whatever
        watches for it - Brine Elemental's own "When this creature is turned
        face up, each opponent skips their next untap step" is the only
        printing in the pool with such a trigger.

        No stack, no priority pass (CR 116): the emitted `TURNED_FACE_UP`
        event still queues an ordinary triggered ability the normal way
        (CR 603.3, `put_triggers_on_stack` puts it on the stack the next time
        a player would receive priority) - a special action skips the stack
        for *itself*, not for what it triggers.
        """
        with self._id_allocator_scope():
            controller = controller or self.controller_of(permanent).username
            permanent.turn_face_up()
            self.emit(
                GameEvent(
                    event=TriggerEvent.TURNED_FACE_UP,
                    subject_id=permanent.id,
                    subject_name=permanent.name,
                    subject_controller=permanent.controller,
                    subject_card=permanent.card,
                    player=controller,
                )
            )
            return permanent

    def begin_activating(
        self,
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        sacrificing: list[CardState] | None = None,
        discarding: list[CardState] | None = None,
        exiling: list[CardState] | None = None,
        x_value: int = 0,
    ) -> CostPayment:
        """Announce an activation and open its payment (CR 602.2a, 602.2b).

        Raises if the ability is prohibited from being activated at all
        (CR 602.5), before anything has been spent.

        `x_value` is CR 107.3a's X, announced now (CR 602.2b puts the whole of
        CR 601.2b's announcement, X included, at this same moment) - the
        caller must hand the identical value to `activate_ability` afterward,
        the same two-call split `Casting.determine_cost`/`choose_modes` and
        `Casting.cast` already require of a spell's X.
        """
        refusal = self.why_cannot_activate(permanent, index, controller)
        if refusal is not None:
            raise ValueError(refusal)
        controller = controller or self.controller_of(permanent).username
        total = self.activation_cost(
            permanent,
            index,
            controller,
            sacrificing=sacrificing,
            discarding=discarding,
            exiling=exiling,
            x_value=x_value,
        )
        # CR 106.6: an activation is what Shang-Chi's and Eldrazi Temple's
        # mana is restricted *to*, and what Cavern of Souls's and Delighted
        # Halfling's is restricted *from*, so the payment is told which it is
        # and whose ability it belongs to (the source's characteristics are
        # what "abilities of creature sources" asks about, not the ability's).
        # ...and those characteristics are the *computed* ones (CR 613.5): a
        # land animated into a creature is a creature source, so Shang-Chi's
        # mana pays for its abilities. `permanent.card` here was the printed
        # front face, wrong for a transformed permanent even before layers.
        # `machines/legal_actions.py` asks the identical question when it
        # enumerates the same activation, and the two must not disagree.
        return CostPayment.for_total(
            total,
            game=self,
            payer=controller,
            spend=ManaSpend.activating(self.characteristics_of(permanent)),
        )

    def activate_ability(
        self,
        permanent: CardState,
        index: int = 0,
        controller: str | None = None,
        *,
        targets: list[object] | None = None,
        color: Color | None = None,
        x_value: int = 0,
        exiled_for_cost: CardState | None = None,
        sacrificed_for_cost: list[CardState] | None = None,
    ) -> AbilityOnStack | None:
        """Finish activating: put the ability on the stack (CR 602.2).

        `sacrificed_for_cost` is the sacrifice twin of `exiled_for_cost` -
        the same permanents the caller already handed to `begin_activating`'s
        `sacrificing=`, repeated here because `AbilityOnStack.
        cost_sacrificed_card_ids` is where a resolving effect that asks about
        them (Witch's Oven's "if the sacrificed creature's toughness was 4 or
        greater") can find them again. CR 602.2b pays the cost before this
        object exists, so nothing else on the ability remembers the choice.

        `exiled_for_cost` is the card chosen to pay a cost like Back from the
        Brink's own "Exile a creature card from your graveyard and pay its
        mana cost" (`machines/cost.exile_and_pay_mana_cost_cost`) - the same
        card the caller already handed to `begin_activating`'s `exiling=`,
        repeated here because `AbilityOnStack` is where the resolving effect
        can find it again (CR 601.2b's choice, remembered past the moment it
        was made). `None` for every other ability, which is most of them.

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
        with self._id_allocator_scope():
            ability = self.activated_abilities(permanent)[index]
            controller = controller or self.controller_of(permanent).username

            # CR 602.2b: "the remainder of the process for activating an ability is
            # identical to the process for casting a spell", so CR 601.2c applies -
            # the targets are announced and checked here, against the ability's own
            # text rather than the card's spell text (CR 113.1c).
            #
            # `x_value` is substituted in first when the printed cost carries an
            # {X} at all (CR 107.3a: X is announced as part of paying the cost,
            # CR 601.2b/602.2b, a step already finished by the time targets are
            # announced, CR 601.2c) - The Mycosynth Gardens' own "target nontoken
            # artifact you control with mana value X" is unreadable by `machines/
            # targeting.py` with a literal "X" still in it (nothing there resolves
            # a bare letter to a number), so without this every such target would
            # be refused outright rather than checked against the real, paid X.
            #
            # A **loyalty** ability spells its X differently: CR 107.7's negative
            # symbol is written "−X", not "{X}", so the `{X}`-in-the-cost test
            # above does not see it. Tamiyo, Compleated Sage's "−X: Exile target
            # nonland permanent card with mana value X from your graveyard" is that
            # shape, and its target clause needs the same substitution for the same
            # reason - `LoyaltyCost.variable` is what marks the symbol as carrying
            # a chosen X.
            has_variable_loyalty = ability.loyalty is not None and ability.loyalty.variable
            text = (
                substitute_x(ability.text, x_value)
                if "{X}" in ability.cost or has_variable_loyalty
                else ability.text
            )
            profile = profile_for_text(text)
            if profile.understood and profile.requirements:
                if targets is None:
                    # The caller supplied nothing, so this is not yet a target
                    # announcement (CR 601.2c) at all - ask, the same way a
                    # triggered ability's own announcement is asked
                    # (`_ask_targets`, shared with `_ask_trigger_targets`). An
                    # explicit list, even an empty one, is a real answer already
                    # given and is checked below instead, exactly as before.
                    asked = self._ask_targets(
                        profile, controller, permanent.id, permanent.name, text
                    )
                    if asked is None:
                        # CR 601.2e, imported wholesale by CR 602.2b: a proposed
                        # activation that cannot legally be completed - here, a
                        # mandatory target (CR 601.2c) with no legal object or
                        # player to name - never happens at all, the same refusal
                        # `Game.cast_free_from_exile` already gives a spell with
                        # no legal target for the same reason (CR 601.2c).
                        raise ValueError(
                            f"{permanent.name}'s ability requires a target, but no legal "
                            "target exists, so it cannot be activated (CR 601.2c, CR 602.2b)"
                        )
                    targets = asked
                else:
                    profile.check(list(targets), controller, self, source_id=permanent.id)

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
                # CR 700.5's devotion, for Nykthos, Shrine to Nyx's own "Add an
                # amount of mana of that color equal to your devotion to that
                # color." Counted here rather than on the `ManaAbility` because
                # only the game knows the board (`ManaAbility.
                # amount_from_devotion`'s own docstring), and counted to the
                # colour the activating player just chose, which is what "that
                # color" points back at.
                devotion = (
                    devotion_to(self, controller, color)
                    if ability.mana.amount_from_devotion and color is not None
                    else None
                )
                # The two board-derived narrowings `ManaAbility.effective` asks
                # for. Without them this fast path resolved the ability against
                # the printed text alone, while `machines/cost.py`'s auto-tap
                # solver - which calls the same `effective` - already narrowed;
                # the two disagreed about what the very same source produces.
                #
                # CR 614.12a's chosen colour (Utopia Sprawl's "As this Aura
                # enters, choose a color", read back by "Add one mana of the
                # chosen color"), recorded on the permanent as it entered.
                chosen = permanent.choice
                chosen_color = (
                    Color(chosen.value)
                    if chosen is not None and chosen.kind is ChoiceKind.COLOR
                    else None
                )
                # CR 106.7's survey, for Reflecting Pool and Exotic Orchard.
                could_produce_colors = (
                    self._could_produce_survey(ability.mana.could_produce, controller)
                    if ability.mana.could_produce is not None
                    else None
                )
                produced_mana = ability.mana.resolve(
                    land_types,
                    own_counters,
                    color,
                    has_imprinted_card,
                    count=devotion,
                    could_produce_colors=could_produce_colors,
                    chosen_color=chosen_color,
                )
                # CR 106.5, for the third narrowing: "of any color among legendary
                # creatures and planeswalkers you control" (Mox Amber). The colour
                # the activating player named has to be one the board actually
                # defines - an empty board defines none, and an ability that would
                # produce mana of an undefined type produces no mana instead.
                # `machines/cost.py` already applies this on the payment path; a
                # direct activation reached the same ability without it, so the
                # same Mox Amber made nothing when tapped for a spell and one mana
                # of any colour when activated on its own.
                allowed = among_colors(ability.effect, self, controller)
                if allowed is not None:
                    undefined = [produced for produced in produced_mana if produced not in allowed]
                    if undefined:
                        raise ValueError(
                            f"{permanent.name} cannot add "
                            f"{''.join(f'{{{produced.value}}}' for produced in undefined)}: "
                            f"no permanent it surveys defines that color, so the ability "
                            f"produces no mana (CR 106.5)"
                        )
                # CR 106.6: a "Spend this mana only to ..." sentence in this
                # ability's own effect text restricts the mana it just made. The
                # tag goes on the mana in the pool, not on `permanent` - the mana
                # ability has resolved (CR 605.3b) and the mana outlives it, so a
                # source that leaves the battlefield takes nothing back with it.
                # `permanent` is passed only to resolve "the chosen type"
                # (CR 614.12a records the answer on the object that was asked).
                restriction = spend_restriction(ability.effect, permanent)
                # CR 106.6's other clause, tagged onto the same mana and for the
                # same reason: "have an additional effect that affects the spell
                # or ability that mana is spent on". Arena of Glory's "If that
                # mana is spent on a creature spell, it gains haste until end of
                # turn." is read off the ability's own trailing text by
                # `machines/abilities.parse_mana_abilities`, so there is nothing
                # to re-parse here - the sentence only has to reach the pool.
                spend_effect = (
                    ManaSpendEffect(text=ability.mana.spend_effect)
                    if ability.mana.spend_effect
                    else None
                )
                for produced in produced_mana:
                    self.player(controller).mana_pool.add(
                        produced, restriction=restriction, spend_effect=spend_effect
                    )
                # CR 405.6c: "If a mana ability both produces mana and has
                # another effect, the mana is produced and the other effect
                # happens immediately." `why_cannot_activate` already refused
                # this activation outright when the rider could not be read, so
                # reaching here means it is either absent or a known shape -
                # Talisman of Resilience's "This artifact deals 1 damage to
                # you." is what taught this engine the shape existed at all.
                if ability.mana.rider is not None:
                    rider = ability.mana.rider
                    if rider.kind == "damage_to_controller":
                        self.deal_damage(self.player(controller), rider.amount, source=permanent)
                    elif rider.kind == "lose_life":
                        self.player(controller).lose_life(rider.amount)
                    elif rider.kind == "gain_life":
                        self.gain_life(controller, rider.amount)
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
                    self.emit(tapped_for_mana_event(permanent, self, mana_added=produced_mana))
                if produced_mana:
                    # Not CR 106.12's tap event but its sibling: an ability caused
                    # this player to add mana. Caged Sun's own condition asks about
                    # the adding, not the tapping, so a mana ability with no `{T}`
                    # in its cost raises this one just the same.
                    triggered = self.emit(
                        mana_added_event(permanent, self, mana_added=produced_mana)
                    )
                    # CR 605.4a: a triggered mana ability "doesn't go on the stack
                    # ... It simply resolves immediately after the mana ability
                    # that triggered it, without waiting for priority."
                    self.resolve_triggered_mana_abilities(triggered)
                self.put_triggers_on_stack()
                return None

            on_stack = AbilityOnStack(
                kind=AbilityKind.ACTIVATED,
                ability=ability,
                source_id=permanent.id,
                source_name=permanent.name,
                controller=controller,
                targets=[TargetRef.coerce(target) for target in targets or []],
                x_value=x_value,
                cost_exiled_card_id=exiled_for_cost.id if exiled_for_cost is not None else None,
                cost_sacrificed_card_ids=tuple(state.id for state in (sacrificed_for_cost or [])),
            )
            self.stack.append(on_stack)
            # CR 602.2b's target announcement has settled (CR 601.2c, imported
            # wholesale), and the ability is on the stack, so anything watching
            # "becomes the target of ... an ability" now has an event to see.
            self._emit_ability_becomes_target(on_stack)
            # CR 117.3c hands priority straight back, so anything that triggered
            # while the cost was paid goes on the stack now - above the ability.
            self.put_triggers_on_stack()
            return on_stack

    # -- priority ----------------------------------------------------------

    #: CR 502.4, quoted, and the refusal anybody trying to act in untap gets.
    UNTAP_HAS_NO_PRIORITY: ClassVar[str] = (
        "no player receives priority during the untap step, so no spells can be "
        "cast or resolve and no abilities can be activated or resolve (CR 502.4)"
    )

    #: CR 514.3, quoted. Only used for a cleanup step CR 514.3a did not except.
    CLEANUP_HAS_NO_PRIORITY: ClassVar[str] = (
        "normally, no player receives priority during the cleanup step, so no "
        "spells can be cast and no abilities can be activated (CR 514.3)"
    )

    @property
    def step_grants_priority(self) -> bool:
        """Whether anybody receives priority in the step now in progress.

        `TurnMachine.grants_priority` answers for the *shape* of the step and is
        the whole answer for eleven of the twelve. The cleanup step is the one it
        cannot answer, because CR 514.3 only says "normally" and CR 514.3a's
        exception is about game state:

        CR 514.3a: "At this point, the game checks to see if any state-based
        actions would be performed and/or any triggered abilities are waiting to
        be put onto the stack (including those that trigger 'at the beginnin[g of
        the next cleanup step]')."

        So a cleanup step with something waiting in `pending_triggers` - or with
        an object already on the stack, which is that same trigger a moment later
        - is a cleanup step in which players do receive priority. An empty one is
        CR 514.3's ordinary case and grants none.

        **Not modelled, and unverified**: `knowledge_search` in this session
        returns CR 514.3a only as far as the sentence quoted above, so the rest
        of that rule - what the game does *after* it finds something waiting,
        including whether a further cleanup step begins - is not implemented and
        is not cited. What is implemented is the half the excerpt states: such a
        cleanup step is not one in which nobody receives priority.
        """
        assert self.turn is not None
        if self.turn.step is Step.CLEANUP:
            return bool(self.pending_triggers) or bool(self.stack)
        return self.turn.grants_priority

    @property
    def priority_holder(self) -> str | None:
        """Who has priority right now, or None if nobody does (CR 502.4, 514.3).

        The single honest answer for a client asking "whose move is it". None is
        not "unknown" and not "the game is stuck" - it is the untap step (or an
        ordinary cleanup step) saying that the next thing to happen is the step
        ending, not a player acting.
        """
        return None if self.priority is None else self.priority.holder

    def sync_priority_with_step(self) -> None:
        """Withhold or restore priority to match the step now in progress.

        Called at every point the step pointer moves. CR 502.4 and CR 514.3 are
        the two withholding rules and their own wording is what gets stored, so
        the refusal a caller gets back is the rule.
        """
        assert self.turn is not None
        if self.priority is None:
            return
        if self.step_grants_priority:
            self.priority.grant()
        elif self.turn.step is Step.UNTAP:
            self.priority.withhold(self.UNTAP_HAS_NO_PRIORITY)
        elif self.turn.step is Step.CLEANUP:
            self.priority.withhold(self.CLEANUP_HAS_NO_PRIORITY)
        else:
            self.priority.grant()

    def pass_priority(self, username: str) -> PriorityOutcome:
        """Pass priority. If everyone passes, resolve the top of the stack.

        CR 117.4: "If all players pass in succession ... the spell or ability
        on top of the stack resolves or, if the stack is empty, the phase or
        step ends." CR 405.5: the next step or phase then begins - nobody has
        to move the game on; passing is saying "I am done for now". So on
        END_STEP the turn rolls forward here, with everything that boundary
        brings (CR 500.5's mana-pool emptying among them), and the next
        step's first priority round starts with its active player (CR 117.1).

        Refused outright in a step that grants nobody priority (CR 502.4, 514.3),
        with that rule's own words. The refusal comes *before* CR 704.3's
        state-based check and CR 603.3's stacking below, because both of those
        are "the next time a player would receive priority" moments and this is
        not one: running them here would put an untap-step trigger straight onto
        the stack, which is the very thing CR 502.4's second sentence forbids.
        """
        assert self.priority is not None
        if self.priority.withheld is not None:
            # Through `require`, so a player who is not at the table at all is
            # still told *that* first: "carol is not in this game" outranks
            # "nobody has priority", because the second answer would be just as
            # true next turn and would send the caller looking in the wrong place.
            self.priority.require(username)
        with self._id_allocator_scope():
            # CR 704.3, then CR 603.3: state-based actions, then anything that
            # has triggered goes on the stack, before the pass is acted on -
            # the next player (or nobody, if the stack resolves) is about to
            # receive priority. This is also the check a special action like
            # playing a land relies on: CR 116.2a hands out no priority of its
            # own, so the legend rule or any other state-based action it
            # caused is caught here, the next time anyone would receive
            # priority.
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

        Run under `_id_allocator_scope`: `_check_state_based_actions_and_
        stack_triggers` below both checks state-based actions (a graveyard
        move's `zone_change_stamp`) and calls `put_triggers_on_stack`, which
        mints a fresh `AbilityOnStack` id for every trigger it moves off
        `pending_triggers`. `pass_priority` and `resolve_top` already reach
        the same helper from inside their own scopes, but the api calls this
        directly after every `cast_card`, `activate_ability`, `cycle_card`
        and `declare_attack` (`engine_api.py`, e.g. around lines 375, 440,
        608, 731), so it needs a scope of its own.
        """
        with self._id_allocator_scope():
            return self._retain_priority_impl(username)

    def _retain_priority_impl(self, username: str) -> str:
        """The rest of `retain_priority` - see its own docstring for why it
        is split out."""
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
        with self._id_allocator_scope():
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
        """Who controls this object. Unlabelled cards belong to the active player.

        For a permanent this is CR 613.1b's layer 2 answer, not a stored one:
        `CardState.controller` consults the computed board (CR 613.5), so a
        "gain control of it until end of turn" effect reaches every caller
        here - combat, the state-based actions, a delayed trigger - without
        any of them knowing the layer system exists. An `AbilityOnStack`'s
        controller is a plain field, and rightly: CR 603.3 fixes it when the
        ability is put on the stack.
        """
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
        with self._id_allocator_scope():
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

    def player_loses_the_game(self, username: str) -> None:
        """CR 104.3e: "An effect may state that a player loses the game."

        Applied immediately as the stating effect resolves, not deferred to a
        state-based-action sweep the way life-loss (CR 104.3b), an empty-library
        draw (CR 104.3c), and ten-or-more poison counters (CR 104.3d) all are -
        104.3e carries none of those three's "the next time a player would
        receive priority" wording. `end_in_draw`'s own CR 104.4c loss is the
        same shape: call `_lose_the_game` directly and check for a winner right
        away, rather than only setting a flag for a later check.

        A no-op for a player already gone - `_lose_the_game` is not idempotent
        about `_player_left`'s cleanup, and CR 104.3a already makes "losing
        stays gone" the rule (`check_state_based_actions`'s own docstring).
        """
        if not self.is_in_game(username):
            return
        self._lose_the_game(username)
        self._check_for_a_winner()

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

        Nothing is put on the stack in the untap step, where no player receives
        priority (CR 502.4); CR 502.4's own second sentence holds those triggers
        over ("Any ability that triggers during this step will be held until the
        n[ext time a player would receive priority]"), which is what leaving
        them in `pending_triggers` does. A cleanup step holds them over too
        *unless* CR 514.3a's exception applies - see `step_grants_priority`, and
        the note there on how far that rule could be verified.

        Two refusals, both raised before anything moves:

        - **CR 117.3a**: the active player is the one whose decision this is -
          or, under a CR 723.5 control effect, whoever is deciding for them.
          Anyone else is refused outright.
        - **CR 500.2 / CR 117.4 / CR 405.5**: a step or phase that grants
          priority (i.e. not one of CR 500.3's untap/cleanup exceptions -
          `step_grants_priority`) ends only once the stack is empty and every player has
          passed in succession. A non-empty stack means that has not happened
          yet, so advancing past it here would strand whatever is waiting -
          the caller must pass priority and let it resolve instead.
        """
        assert self.turn is not None
        if self.is_over:
            raise ValueError("the game is over")
        if self.turn.in_pregame:
            # CR 500.1's steps are parts of a turn and no turn has begun yet, so
            # there is no step to advance and no active player whose decision it
            # would be. The pregame moves when its own sequence completes.
            raise ValueError(
                f"the game is still in its pregame ({self.turn.step}) - "
                f"CR 103.8's first turn has not begun. Settle CR 103.5's "
                f"mulligans and CR 103.6's opening-hand actions first"
            )

        decider = self.controller_of_player(self.turn.active_player)
        if username is None:
            username = decider
        if username != decider:
            raise ValueError(
                f"{username} may not advance the turn - only {decider} may, as "
                f"{self.turn.active_player}'s active-player decision (CR 117.3a, 723.5)"
            )
        if self.step_grants_priority and not self.stack_is_empty:
            raise ValueError(
                f"cannot advance past {self.turn.step} while the stack is "
                f"non-empty - pass priority instead (CR 500.2)"
            )

        with self._id_allocator_scope():
            return self._advance_past_checks()

    def _advance_past_checks(self) -> Step:
        """The rest of `advance`, run with `_allocate_id` installed.

        Split out only so `advance` can wrap it in `_id_allocator_scope` -
        see `objects_created`'s docstring for why that installation is scoped
        to this one call rather than done once for the object's whole life.
        """
        assert self.turn is not None
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
            # The condition is what happened, not who is still in combat:
            # CR 508.8 keys off "declared as attackers or put onto the
            # battlefield attacking", so CR 506.4 removing an attacker after
            # the fact does not un-skip the combat. Both halves of that union
            # set `attacked_this_combat` - `combat.declare_attacker` for the
            # declaration, `models/token._put_onto_the_battlefield_attacking`
            # for Parhelion II's Angels and Ilharg's creature card, which
            # CR 508.4c says were never declared - so the flag is the whole of
            # it and asking `combat.attacks` here would be the wrong reading
            # anyway. Only the automatic path
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
            self.once_per_turn_triggers = {}  # CR 603.2h restrictions are per turn too
            # Snapshotted, not dropped: "last turn" is a question the
            # werewolves ask every upkeep (CR 603.4) and nothing else can
            # answer once this is cleared.
            self.spells_cast_last_turn = self.spells_cast_this_turn
            self.spells_cast_this_turn = {}
            self.permanents_left_battlefield_this_turn = {}
            self.permanents_sacrificed_this_turn = {}
            self.cards_drawn_this_turn = {}
            self.cards_discarded_this_turn = {}
            self.life_gained_this_turn = set()
            # `play_permissions` is deliberately **not** cleared here. CR 514.2
            # ends an "until end of turn" effect in the cleanup step and
            # `cleanup_step` does exactly that; a game driven step by step may
            # never run one, and `PlayPermission.expired` - which compares
            # `turns_taken` - is what answers correctly in that case. Purging
            # here as well would replace that specific refusal ("that turn is
            # over") with the generic "nothing allows this", which is a worse
            # message for the same wrong move.
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

        # CR 603.3, before anyone has priority - and only where anyone does.
        # CR 502.4's second sentence is the untap half: "Any ability that
        # triggers during this step will be held until the n[ext time a player
        # would receive priority]", which is exactly leaving it in
        # `pending_triggers`. The cleanup half is CR 514.3a: a cleanup step with
        # something waiting *is* one where players receive priority, so the
        # waiting abilities go on the stack here rather than being held over.
        if self.step_grants_priority:
            self.put_triggers_on_stack()

        if self.priority is not None:
            self.priority.reset(self.turn.active_index)
        # CR 502.4 / CR 514.3: and then take it straight back off the ones that
        # grant nobody priority, so `priority_holder` says nobody rather than
        # naming a player who may not act.
        self.sync_priority_with_step()
        return step

    def advance_to(self, step: Step) -> Step:
        """Move the turn marker forward through every boundary up to `step`.

        The full funnel is `advance`, which also performs what each *beginning*
        needs - beginning-of-step triggers, turn-based actions, state-based
        actions, priority. This one crosses boundaries only, and at each of
        them performs the step-end turn-based action CR 500.5 requires: mana
        pools empty as every crossed step ends. Raises if `step` has already
        passed this turn, exactly as `TurnMachine.advance_to` does.

        Refuses while the game is still in its pregame, for `advance`'s reason:
        the steps this walks are CR 500's, and CR 103.8's first turn has not
        begun. `TurnMachine.advance_to` will move the raw pointer through the
        pregame for a caller that genuinely wants only the pointer moved.
        """
        assert self.turn is not None
        if self.turn.in_pregame:
            raise ValueError(
                f"the game is still in its pregame ({self.turn.step}) - "
                f"CR 103.8's first turn has not begun. Settle CR 103.5's "
                f"mulligans and CR 103.6's opening-hand actions first"
            )
        if STEP_SEQUENCE.index(step) < STEP_SEQUENCE.index(self.turn.step):
            raise ValueError(f"{step} already passed this turn, currently at {self.turn.step}")
        while self.turn.step is not step:
            self.turn.advance()
            self.empty_mana_pools()
        self.sync_priority_with_step()  # CR 502.4, 514.3
        return self.turn.step
