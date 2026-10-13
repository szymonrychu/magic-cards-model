import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from ...data.subtypes import canonical_subtype
from ...models.card import Color, Layout, Supertype, Type
from ...models.card_state import (
    DEVOTION_BONUS_TEXT,
    PERMANENT_TYPES,
    CardState,
    Counter,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.token import (
    PREDEFINED,
    create_tokens,
    is_token,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    MULTIPLIER,
    ORDINAL,
    count_pattern,
    halve,
    parse_count,
    parse_half,
    parse_multiplier,
    parse_ordinal,
)
from ..abilities import (
    ActivatedAbility,
    TriggeredAbility,
)
from ..casting import (
    PlayAction,
)
from ..conditions.cast_record import treasure_mana_spent_to_cast
from ..converge import colors_of_mana_spent
from ..cost import (
    removes_announced_number_of_counters,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..ep01_r3_amounts import (
    cast_spell_mana_value,
    counters_on_it_total,
    creatures_blocked_by,
    creatures_blocking,
    creatures_that_crewed,
    event_subject_stat,
    event_terms_enabled,
)
from ..ep02_r1_graveyard_counts import (
    graveyard_count_expression,
    parse_damage_pair_where_x_ability,
    parse_damage_pair_where_x_spell,
    parse_graveyard_count_clause,
    parse_pump_then_additional_per_count_ability,
    parse_pump_then_additional_per_count_spell,
    parse_search_value_at_most_count_ability,
    parse_search_value_at_most_count_spell,
    parse_tapped_attacking_tokens_for_each_ability,
)
from ..ep02_r1_life_amounts import life_this_turn_count
from ..ep02_r2_devotion_domain_party import up_to_x_targets, where_x_pump_text_normalised
from ..ep02_r2_cards_in_zone_counts import (
    hand_count_expression,
    parse_attached_pump_until_end_of_turn_clause,
    parse_cast_any_number_from_hand_free_clause,
    parse_defending_player_clause,
    parse_hand_difference_spell,
    parse_mill_by_stat_then_return_self_and_milled,
    parse_no_maximum_hand_size_while_controlling_clause,
    parse_return_half_permanents_spell,
    parse_search_target_library_and_exile,
)
from ..layers import (
    BASIC_LAND_TYPES,
    Characteristics,
    ComputedBoard,
    ContinuousEffect,
    Duration,
    Layer,
    LayerNotice,
    Sublayer,
    _only,
    modify_power_toughness,
    only_this_incarnation,
    parsed_layer_effects,
)
from ..modes import (
    substitute_x,
)
from ..targeting import (
    permanent_description,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
    resolution_key,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import (
    _OBJECT_ANAPHOR,
    _UNQUOTED_PREFIX,
    AbilityEffect,
    AmountReader,
    ClauseEffect,
    Effect,
    TargetedClause,
)


def _x_substituted_spell_text(game: "Game", spell: CardState) -> str | None:
    """The spell's own text with CR 107.3a's announced X written in, when its
    mana cost carries `{X}` and its text names X - `None` otherwise, which
    leaves `effects_for` reading the printed text exactly as before.
    Fractalize's "base power and toughness each equal to X plus 1" is only a
    number once X is known; X is fixed for the spell's whole resolution
    (CR 107.3a), so substituting it before the layer reader runs is the
    same substitution `effect_for` already made to route the spell here."""
    text = spell.oracle_text or ""
    if "{X}" not in (spell.mana_cost or "") or not re.search(r"(?<![\w{])X(?![\w}])", text):
        return None
    record = game.cast_record_of(spell)
    if record is None:
        return None
    return substitute_x(text, record.x_value)


def _cast_trigger_x_value(game: "Game", ability: AbilityOnStack) -> int | None:
    """The announced X (CR 107.3a) of the spell that triggered `ability` via a
    cast-trigger event, or `None` when there is no cast-trigger event or no
    cast record of it - `_cast_trigger_mana_spent_x_value`'s own twin, for a
    "When you cast this spell, ... X ..." clause whose X is the just-
    announced value on the spell itself (Genesis Hydra, Old Stickfingers)
    rather than a "where X is <expr>" self-defined one (CR 107.3c), which
    `amount_expression` already reads for those. A triggered ability
    announces no X of its own (`AbilityOnStack.x_value`'s docstring), so this
    is never read off `ability` itself."""
    record = _cast_trigger_record(game, ability)
    return None if record is None else record.x_value


# --------------------------------------------------------------------------
# A shared count expression: "the number of <type> you control" / "... cards
# in your graveyard" (CR 205.2a's card types)
# --------------------------------------------------------------------------
#
# Several cards define a variable magnitude this way - Craterhoof Behemoth's
# own pump ("where X is the number of creatures you control") and Grist, the
# Hunger Tide's -5 ("equal to the number of creature cards in your
# graveyard") are the two in this wave's pool - and each used to need its own
# one-off reader (`_read_referent_power_expression`'s "its power",
# `_parse_mass_mv_rhs`'s counters-on-self, `LayerContext.graveyard_of`'s own
# graveyard slice). `count_expression` is the shared one: given the phrase
# after "the number of", it returns a function of `(game, controller)` - not
# a value - because CR 611.2c only fixes the *result* at the moment a caller
# actually evaluates it, not the expression itself; Craterhoof's own
# docstring on `_run_mass_pump` is where that one evaluation happens.
#: "the number of" is optional so the identical shape also reads a "for each
#: <qualifier> you control" multiplier - Immaculate Magistrate's own "Put a
#: +1/+1 counter on target creature for each Elf you control" - once
#: `_for_each_expression` has already stripped the "for each" off and handed
#: this whichever bare phrase is left, singular or plural either way.
#: `<qualifier>` may itself carry a leading CR 110.5 status word
#: ("tapped"/"untapped") - Harvest Season's own "the number of tapped
#: creatures you control" and Ben-Ben, Akki Hermit's "the number of
#: untapped Mountains you control" - which a single `[a-z]+` group used to
#: swallow as part of the qualifier itself rather than reading separately,
#: so a status-qualified phrase never matched this pattern at all.
#:
#: A leading "nontoken" (CR 111.1) reads the identical way - Sally Pride,
#: Lioness Leader's own "the number of nontoken creatures you control" and
#: Lena, Selfless Champion's off-set "a ... token for each nontoken creature
#: you control" (`_TOKEN_FOR_EACH_TAIL_RE`'s own "each" tail reaches this
#: same function) - excluding a token from the count rather than requiring
#: one the way a bare "token(s)" qualifier does not exist in this shape at
#: all (Caretaker's Talent's own "one or more tokens" is an *entry*
#: condition, not a count expression).
#:
#: A leading colour list (CR 105.1) narrows it the same way - Chaotic
#: Backlash's "the number of white and/or blue permanents they control" counts
#: a permanent that is either colour - and "on the battlefield" (Chain
#: Reaction's "the number of creatures on the battlefield", War Report's
#: "the number of artifacts on the battlefield") counts everyone's.
_COUNT_COLOR_WORD = r"(?:white|blue|black|red|green)"
_COUNT_YOU_CONTROL_RE = re.compile(
    r"^(?:the )?(?:number of )?(?:(?P<status>tapped|untapped|attacking) )?"
    r"(?:(?P<nontoken>nontoken) )?"
    rf"(?:(?P<colors>{_COUNT_COLOR_WORD}(?:(?: and/or | or ){_COUNT_COLOR_WORD})*) )?"
    r"(?:(?P<snow>snow|nonsnow|basic|nonbasic) )?"
    r"(?P<qualifier>[a-z]+) "
    r"(?P<whose>you control|they control|your opponents control|on the battlefield)$"
    # CR 508.1k: every attacking creature, whoever controls it - Path of
    # Bravery's "the number of attacking creatures", with no "you control".
    r"|^(?:the )?number of (?P<attacking_any>attacking) (?P<attacking_qualifier>[a-z]+)$",
    re.IGNORECASE,
)
#: Same relaxation, for Lotleth Giant's "for each creature card in your
#: graveyard" - the singular counterpart of "the number of creature cards in
#: your graveyard" this regex already read.
#: The qualifier may also be a two-type "`<A>` and `<B>`" list - Steal the
#: Show's and Blitz of the Thunder-Raptor's own "the number of instant and
#: sorcery cards in your graveyard" - which is a count of the union, not a
#: card that is somehow both at once (Invade the City's "Amass Zombies X,
#: where X is the number of instant and sorcery cards in your graveyard" is
#: the identical phrase, off-pool, so this reads for it too).
_COUNT_CARDS_IN_YOUR_GRAVEYARD_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<qualifier>[a-z]+(?:\s+and\s+[a-z]+)?) cards? "
    r"in your graveyard$",
    re.IGNORECASE,
)
_COUNT_NUMBER_PLUS_RE = re.compile(r"^(?P<n>\d+|[a-z]+) plus (?P<rest>.+)$", re.IGNORECASE)
#: "the number of creatures and/or Spacecraft you control" (Focus Fire) and
#: "the number of permanents you control that are creatures and/or Vehicles"
#: (Collision Course): a count of the permanents that are *any* item of an
#: "and/or" (or "or", or a plain "and": Road Rage's "the number of Mounts and
#: Vehicles you control", Runebound Wolf's "Wolves and Werewolves") list of card
#: types and subtypes - a permanent that is two of them (a crewed Vehicle, a
#: changeling) is still one permanent and counts once.
_COUNT_TYPE_LIST_WORD = r"[A-Za-z]+"
_COUNT_TYPE_LIST = rf"{_COUNT_TYPE_LIST_WORD}(?:,? (?:and/or|and|or) {_COUNT_TYPE_LIST_WORD})+"
_COUNT_AND_OR_YOU_CONTROL_RE = re.compile(
    rf"^(?:the )?number of (?P<list>{_COUNT_TYPE_LIST}) "
    r"(?P<whose>you control|your opponents control)$"
    rf"|^(?:the )?number of permanents (?P<whose2>you control|your opponents control) "
    rf"that are (?P<list2>{_COUNT_TYPE_LIST})$",
    re.IGNORECASE,
)
#: "the number of cards with a cycling ability in your graveyard" (Zenith
#: Flare): a graveyard count by a keyword ability the card carries.
_COUNT_CARDS_WITH_KEYWORD_ABILITY_IN_YOUR_GRAVEYARD_RE = re.compile(
    r"^(?:the )?number of cards with an? (?P<keyword>[a-z]+) ability in your graveyard$",
    re.IGNORECASE,
)
#: Hearth Elemental's own "the number of cards in your graveyard that are
#: instant cards, sorcery cards, and/or have an Adventure." - the "that are
#: `<list>`" twin of `_COUNT_CARDS_IN_YOUR_GRAVEYARD_RE`'s own leading-
#: qualifier shape, needed because this phrasing repeats "cards" once per
#: list item rather than once for the whole list, and because one item can be
#: CR 715's own idiom instead of a card type at all. `list` is split and read
#: word by word in `count_expression` itself.
_COUNT_CARDS_IN_GRAVEYARD_QUALITY_LIST_RE = re.compile(
    r"^(?:the )?number of cards in your graveyard that are (?P<list>.+)$", re.IGNORECASE
)
#: "have an Adventure" (CR 715.2) - Scryfall's own name for the same rule is
#: the `Layout.ADVENTURE` a card's `layout` field already carries (Stoke
#: Genius's own back face is what makes Hearth Elemental one), read here
#: rather than through `types_of`/`subtypes_of`: "Adventure" prints in a
#: face's own type line the way a *subtype* does ("Sorcery — Adventure"), not
#: as a quality of the whole card the way this clause needs it, and `Card.
#: layout` is the one field Scryfall already computes that question from.
_ADVENTURE_CARD_CLAUSE_RE = re.compile(r"^have an adventure$", re.IGNORECASE)
#: "`<type>` cards" - one item of the list above, always plural (never a bare
#: type word the way `_COUNT_CARDS_IN_YOUR_GRAVEYARD_RE`'s leading qualifier
#: is), so it needs its own singular-then-lookup rather than reusing that
#: regex's own trailing "cards?" against a list already split apart.
_TYPE_CARDS_CLAUSE_RE = re.compile(r"^(?P<type>[a-z]+) cards$", re.IGNORECASE)
#: Domain (CR 702.94-adjacent naming; no keyword ability of its own, just a
#: fixed count expression templated identically on every card that uses it):
#: Tribal Flames' "the number of basic land types among lands you control".
#: `BASIC_LAND_TYPES` is CR 305.6's five (`.layers` already names them for
#: `machines/targeting.py`'s own basic-land exclusion); this counts how many
#: of those five subtypes are on any land the given player controls, read off
#: the computed board (CR 613.5) the same way `count_expression`'s other
#: readers already are, so a land that has *become* a basic type through a
#: continuous effect still counts.
_COUNT_BASIC_LAND_TYPES_RE = re.compile(
    # The singular "basic land type among lands you control" is the same count
    # spelled as a "for each" (Tromp the Domains' "+1/+1 for each basic land
    # type among lands you control").
    r"^(?:the )?(?:number of )?basic land types? among lands you control$",
    re.IGNORECASE,
)
#: Tam, the Possibility's own X definition: "the number of planeswalker
#: types among planeswalkers you control." CR 205.3j: "Planeswalkers have
#: their own unique set of subtypes; these subtypes are called planeswalker
#: types" - an open-but-named-in-full list (verified this session with
#: `mise run rules:find 205.3j`), but every one of them is a subtype a
#: permanent can carry only while it also has the planeswalker card type, so
#: counting distinct subtypes among the controller's own planeswalkers needs
#: no closed word list the way `BASIC_LAND_TYPES` (a five-item CR 305.6
#: subset of every land subtype) does.
_COUNT_PLANESWALKER_TYPES_RE = re.compile(
    r"^(?:the )?number of planeswalker types among planeswalkers you control$", re.IGNORECASE
)
#: "the number of cards exiled this way" (Corpseweft), "each artifact
#: sacrificed this way" (Radiant Lotus, through `_for_each_multiplier`) - a
#: count of what this object's own cost or earlier instruction moved,
#: `counted_this_way`.
_COUNT_THIS_WAY_RE = re.compile(
    r"^(?:the )?number of (?P<noun>[a-z ]+?) "
    r"(?P<verb>exiled|sacrificed|discarded|milled|tapped) this way$",
    re.IGNORECASE,
)
#: "the total power of the sacrificed creatures" (Soulblast, Corpse Cobble),
#: "the total mana value of the discarded cards" (Nahiri's Wrath) - a sum
#: over what the resolving spell's own additional cost paid with that verb
#: (CR 118.8, 601.2h), read off its cast record's snapshots (CR 608.2h's last
#: known information; CR 202.3's mana value), `total_of_paid_for_cost`.
_TOTAL_OF_PAID_RE = re.compile(
    r"^(?:the )?total (?P<stat>power|mana value) of the "
    r"(?P<verb>sacrificed|discarded|exiled|tapped) (?P<noun>[a-z ]+)$",
    re.IGNORECASE,
)
#: The `ComponentKind` value each "this way" verb names (`CastRecord.
#: additional_cost_kinds`).
_THIS_WAY_VERB_KINDS = {
    "exiled": "exile",
    "sacrificed": "sacrifice",
    "discarded": "discard",
    "tapped": "tap",
}
#: "the number of cards in your hand" - Jolrael, Voice of Zhalfir's own X.
#: Not a filtered count the way the two above are: CR 402.1 makes the hand a
#: zone with no type restriction to read ("the hand is where a player holds
#: cards that have been drawn"), so every card in it counts, whatever it is.
#: CR 700.8's party, counted (Practiced Tactics, Allied Assault).
_COUNT_CREATURES_IN_YOUR_PARTY_RE = re.compile(
    r"^(?:the )?(?:number of )?creatures? in your party$", re.IGNORECASE
)
_COUNT_CARDS_IN_YOUR_HAND_RE = re.compile(r"^(?:the )?number of cards in your hand$", re.IGNORECASE)
#: "the number of cards in your library" - Tamiyo, Seasoned Scholar's own -7
#: count, halved by `_amount_term`'s "half ..., rounded up" term. Every card
#: in the library counts, the same unfiltered reading
#: `_COUNT_CARDS_IN_YOUR_HAND_RE` applies to the hand.
_COUNT_CARDS_IN_YOUR_LIBRARY_RE = re.compile(
    r"^(?:the )?number of cards in your library$", re.IGNORECASE
)
#: "the amount of life you gained this turn" - Germinate Recruits' own X
#: (CR 107.3f) and Enlightened Confidant's own mana-value ceiling (FRA
#: stream S8), the same expression built independently for two different
#: reported cards. `Game.life_gained_amount_this_turn` is the per-player
#: running total `Player.gain_life` keeps for exactly this, the amount twin
#: of `life_gained_this_turn`'s plain boolean Ocelot Pride's intervening
#: *if* already reads.
_AMOUNT_OF_LIFE_GAINED_THIS_TURN_RE = re.compile(
    r"^(?:the )?amount of life you(?:'ve| have)? gained this turn$", re.IGNORECASE
)
#: "the number of cards you've discarded this turn" - Jiang Yanggu, Alone's
#: own "for each card you've discarded this turn" and Misty Knight, Hero for
#: Hire's identically worded "draw a card for each card you've discarded
#: this turn" (off-set: an activated ability rather than an attack trigger).
#: `Game.cards_discarded_this_turn` is the same per-player running total
#: `Game.static_cost_modifiers_for`'s own "costs `<n>` less to cast for each
#: card you've discarded this turn" (Hollow One) already reads for a cost
#: reduction - the identical fact, read here for a count instead.
_COUNT_CARDS_DISCARDED_THIS_TURN_RE = re.compile(
    r"^(?:the number of )?cards? you(?:'ve| have)? discarded this turn$", re.IGNORECASE
)
#: "`<nontoken >`creature that died under your control this turn" - Vile
#: Redeemer's own cast trigger ("for each nontoken creature that died under
#: your control this turn"). CR 700.4: "dies" is put into a graveyard from
#: the battlefield; `Game.nontoken_creatures_died_under_control_this_turn` is
#: the per-controller, nontoken-only running total (the plain, non-nontoken
#: form is left for a future card to add, since nothing in the pool prints it
#: yet - a bare "creature that died under your control this turn" would
#: return `None` here rather than double-counting against the nontoken
#: total).
_COUNT_NONTOKEN_CREATURES_DIED_UNDER_CONTROL_RE = re.compile(
    r"^(?:the number of )?nontoken creatures? that died under your control this turn$",
    re.IGNORECASE,
)
#: "creature[s] that died under your control this turn" - Callous
#: Sell-Sword's "for each creature that died under your control this turn",
#: Liliana's Standard Bearer's "the number of creatures that died under your
#: control this turn". CR 700.4: "dies" is put into a graveyard from the
#: battlefield - a token dies too - and "under your control" is who
#: controlled it as it died (CR 603.10a), both read off `Game.turn_history`'s
#: "to_graveyard" entries.
_COUNT_CREATURES_DIED_UNDER_CONTROL_RE = re.compile(
    r"^(?:the number of )?creatures? that died under your control this turn$",
    re.IGNORECASE,
)
#: "the number of cards you've drawn this turn" - Fractal Anomaly's own X.
#: `Game.cards_drawn_this_turn` is EC4's own per-player running total,
#: already read by `machines/conditions/history._drew`'s "you drew two or
#: more cards this turn" (CR 121.2) - the identical fact, read here for a
#: count instead of a threshold check.
_COUNT_CARDS_DRAWN_THIS_TURN_RE = re.compile(
    r"^(?:the number of )?cards? you(?:'ve| have)? drawn this turn$", re.IGNORECASE
)
#: "the damage already dealt to you this turn" - Final Punishment's own
#: amount, its "that player" already written as "you" for the player it is
#: counted for (`_TARGET_PLAYER_REFERENCES`).
_COUNT_DAMAGE_ALREADY_DEALT_TO_YOU_RE = re.compile(
    r"^(?:the )?damage already dealt to you this turn$", re.IGNORECASE
)
#: "the number of permanents you've sacrificed this turn" - Obsessive
#: Pursuit's own X (CR 701.21a), read off `Game.turn_history`'s "sacrificed"
#: entries the same way `machines/conditions/history._sacrificed` already
#: counts them for its own boolean "you've sacrificed a `<quality>` this
#: turn" - the identical fact, unfiltered, as a count instead of a threshold
#: check.
_COUNT_PERMANENTS_SACRIFICED_THIS_TURN_RE = re.compile(
    r"^(?:the number of )?permanents? you(?:'ve| have)? sacrificed this turn$", re.IGNORECASE
)
#: "the number of differently named `<qualifier>` you control" - Emil,
#: Vastlands Roamer's own "the number of differently named lands you
#: control", generalised over the qualifier rather than fixed to lands.
_DIFFERENTLY_NAMED_QUALIFIER_RE = re.compile(
    r"^(?:the number of )?differently named (?P<qualifier>[a-z]+) you control$", re.IGNORECASE
)
#: "the number of cards in your graveyard" - Yuriko, Hope from the Shadows's
#: own X. The unfiltered twin of `_COUNT_CARDS_IN_YOUR_GRAVEYARD_RE`: CR
#: 500.2's graveyard has no type restriction of its own either, so every
#: card in it counts, whatever it is - the identical reasoning
#: `_COUNT_CARDS_IN_YOUR_HAND_RE` already applies to CR 402.1's hand.
_COUNT_CARDS_IN_YOUR_GRAVEYARD_UNFILTERED_RE = re.compile(
    r"^(?:the )?number of cards in your graveyard$", re.IGNORECASE
)
#: "the greatest power among creatures you control" - Tyvar, the Pummeler's
#: own X. Not a count of anything: an extremum over a characteristic, which
#: is why it needs its own reader rather than a wider qualifier on the two
#: counting shapes above.
#: Armor Wars' "the greatest mana value among artifacts you control" (One with
#: the Machine's own amount) is the same extremum over CR 202.3's mana value.
_GREATEST_CHARACTERISTIC_AMONG_RE = re.compile(
    r"^(?:the )?greatest (?P<characteristic>power|toughness|mana value) among "
    r"(?P<qualifier>[a-z]+) you control$",
    re.IGNORECASE,
)
#: "different power among creatures you control" - Loot, the Nexus's own
#: mana ability count. Not the extremum `_GREATEST_CHARACTERISTIC_AMONG_RE`
#: reads: this is the number of *distinct* values the characteristic takes
#: (a 1/1, a 1/1, and a 3/3 is two different powers, not three), so it needs
#: its own reader rather than reusing that one's max.
_DIFFERENT_CHARACTERISTIC_AMONG_RE = re.compile(
    r"^different (?P<characteristic>power|toughness) among (?P<qualifier>[a-z]+) you control$",
    re.IGNORECASE,
)


#: CR 122.1: a counter is "a marker placed on an object or player", and the
#: set of kinds is open - poison (CR 122.1f), energy (CR 107.14), experience,
#: rad (CR 122.1i) and ticket all sit on *players*. Whose counters is the
#: tail: "you have", "your opponents have" (their total), "target player
#: has", "they have"/"that player has" (an anaphor only the caller can
#: resolve), and "among players" (everyone's total, Vault 12: The
#: Necropolis).
_PLAYER_COUNTER_KIND = r"(?P<kind>\{e\}|\+1/\+1|-1/-1|[a-z]+)"
_PLAYER_COUNTER_WHO = (
    r"(?P<who>you have|your opponents have|target (?:player|opponent) has"
    r"|they have|that player has|among (?:all )?players|(?:all )?players have)"
)
_PLAYER_COUNTER_COUNT_RE = re.compile(
    rf"^(?:(?:the )?(?:total )?(?:number|amount) of )?{_PLAYER_COUNTER_KIND}"
    rf"(?: counters?)? {_PLAYER_COUNTER_WHO}$",
    re.IGNORECASE,
)


def _player_counters_held(game: "Game", username: str, kind: str) -> int:
    return game.player(username).counters[kind]


def parse_player_counter_phrase(phrase: str) -> tuple[str, str] | None:
    """`(kind, whose)` of a count of counters on players - `kind` the counter
    key (`"poison"`, `"energy"`, ...) and `whose` one of "you have", "your
    opponents have", "target player has", "they have", "that player has",
    "among players" (every spelling folded onto those) - or `None` when
    `phrase` is not one. Shared by the effect reader below and the layer
    engine's static "for each poison counter your opponents have"."""
    match = _PLAYER_COUNTER_COUNT_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    word = match.group("kind").lower()
    if word != "{e}" and "counter" not in phrase.lower():
        return None
    kind = str(Counter.ENERGY if word == "{e}" else _counter_kind(word))
    who = match.group("who").lower()
    if who.startswith("target "):
        who = "target player has"
    elif who.startswith("among") or who.endswith("players have"):
        who = "among players"
    return kind, who


def player_counter_count(
    phrase: str, *, anaphoric: bool = False
) -> Callable[["Game", str], int] | None:
    """Parse a count of counters on players - "the number of poison counters
    you have", "poison counter your opponents have", "the total number of rad
    counters among players", "{E} you have" - into `(game, controller) ->
    int`, or `None` when `phrase` is not one.

    The kind is any counter word (CR 122.1's open set) or `{E}` (energy,
    CR 107.14). "Your opponents" is the total over every other player and
    "among players" the total over all of them; "target player/opponent has"
    reads the one player the resolving object targets (CR 608.2b: 0 when none
    is left). "They have"/"that player has" name a player only the caller
    knows, so they read through `anaphoric=True`, where the function's second
    argument is that player's username rather than the controller's, and are
    `None` otherwise.

    CR 608.2h: the count is determined once, when the effect applies - the
    caller keeps the `int`, not the function.
    """
    parsed = parse_player_counter_phrase(phrase)
    if parsed is None:
        return None
    kind, who = parsed
    if who in ("they have", "that player has"):
        if not anaphoric:
            return None
        return lambda game, username: _player_counters_held(game, username, kind)
    if anaphoric:
        return None
    if who == "you have":
        return lambda game, controller: _player_counters_held(game, controller, kind)
    if who == "your opponents have":
        return lambda game, controller: sum(
            opponent.counters[kind] for opponent in _opponents(game, controller)
        )
    if who == "target player has":
        return lambda game, _controller: _count_for_targeted_player(
            game, lambda g, username: _player_counters_held(g, username, kind)
        )
    return lambda game, _controller: sum(player.counters[kind] for player in game.players_in_game)


_AS_YOU_CAST_SUFFIX = " as you cast this spell"
_WHERE_X_AS_YOU_CAST_RE = re.compile(
    r",?\s*where X is (?P<expr>[^.]+? as you cast this spell)\s*\.", re.IGNORECASE
)


def _locked_or_live(game: "Game", controller: str, live: Callable[["Game", str], int]) -> int:
    """The X `Casting` recorded for the spell now resolving, else the live count."""
    record = game.cast_record_of(game.resolving)
    return live(game, controller) if record is None else record.x_value


def locked_amount_as_cast(game: "Game", text: str, caster: str) -> int | None:
    """The count `text` defines with "where X is `<count>` as you cast this
    spell", evaluated now for `caster` - `None` when the text prints no such
    definition or the count is one `count_expression` cannot read. Called by
    `Casting` while the spell is being cast (CR 601.2d: the division needs the
    total), the one moment the count is fixed."""
    if "as you cast this spell" not in text:
        return None
    defined = _WHERE_X_AS_YOU_CAST_RE.search(text)
    if defined is None:
        return None
    reader = count_expression(defined.group("expr"))
    return None if reader is None else reader(game, caster)


def _count_permanents_matching_any(
    listed: str, *, opponents: bool
) -> Callable[["Game", str], int] | None:
    """`_COUNT_AND_OR_YOU_CONTROL_RE`'s count: every item must be a card type
    (CR 205.2a) or a printed subtype, else the whole count is left unread
    rather than counting only the half it knew."""
    words = [
        word
        for word in re.split(r",?\s*(?:and/or|and|or)\s+|,\s*", listed, flags=re.IGNORECASE)
        if word
    ]
    wanted_types = frozenset(
        card_type for word in words if (card_type := _singular_card_type(word)) is not None
    )
    wanted_subtypes = frozenset(
        subtype
        for word in words
        if _singular_card_type(word) is None
        and (subtype := _singular_subtype_for_count_expression(word)) is not None
    )
    if len(wanted_types) + len(wanted_subtypes) != len(words):
        return None

    def count_matching_any(game: "Game", controller: str) -> int:
        board = game.computed_board()
        found = 0
        for permanent in game.battlefield:
            computed = board.of(permanent)
            owner = computed.controller
            if owner is None or (owner != controller) != opponents:
                continue
            if wanted_types & set(computed.types) or any(
                word.lower() in wanted_subtypes for word in computed.subtypes
            ):
                found += 1
        return found

    return count_matching_any


# --------------------------------------------------------------------------
# NW-06 counted terms: filtered permanent counts, shared creature types,
# per-turn deaths, coloured symbols, graveyard negations, colour pairs
# --------------------------------------------------------------------------

#: "the number of creatures you control with power 2 or less" (Arabella,
#: Abandoned Doll), "the number of equipped creatures you control" (Barret
#: Wallace, Jor Kadeen), "the number of modified creatures you control other
#: than this creature" (Thundering Raiju), "the number of permanents you
#: control with oil counters on them" (Urabrask's Anointer), "the total mana
#: value of other permanents you control" (Summon: Bahamut): one counted (or
#: summed) group of the controller's permanents, narrowed by a quality, a
#: characteristic bound or a counter kind, optionally leaving the source out.
#: A phrase carrying none of those narrowings is `_COUNT_YOU_CONTROL_RE`'s.
_FILTERED_PERMANENT_COUNT_RE = re.compile(
    r"^(?:the )?(?P<measure>number of|total mana value of) (?P<other>other )?"
    r"(?:(?P<status>tapped|untapped) )?(?:(?P<quality>modified|equipped) )?"
    r"(?P<qualifier>[a-z]+) you control(?: named (?P<named>[^.]+?))?"
    r"(?P<other_than> other than (?:this (?:creature|permanent|artifact|enchantment)|it))?"
    r"(?: with (?:(?P<stat>power|toughness|mana value) (?P<bound>\d+) or "
    r"(?P<direction>less|greater|more)|(?:(?:a|an|one or more) )?"
    r"(?P<counter>[a-z0-9+/-]+) counters? on (?:them|it)))?$",
    re.IGNORECASE,
)
#: The cheap literal gate in front of `_FILTERED_PERMANENT_COUNT_RE`: the full
#: pool classifies through `count_expression` on its hot path.
_FILTERED_PERMANENT_COUNT_MARKERS = (
    "equipped ",
    "modified ",
    " with ",
    "total mana value",
    "other ",
    " named ",
)
#: "the greatest number of creatures you control that have a creature type in
#: common" (Basalt Ravager, Skemfar Shadowsage, White Lotus Tile).
_GREATEST_SHARED_CREATURE_TYPE_RE = re.compile(
    r"^(?:the )?greatest number of (?P<qualifier>[a-z]+) you control that "
    r"(?:have|share) a creature type in common$",
    re.IGNORECASE,
)
#: "the number of creatures that died this turn" (Spymaster's Vault), "the
#: number of nontoken creatures that died this turn", "the number of Zubera
#: that died this turn" (Ember-Fist Zubera): whoever controlled them.
_COUNT_DIED_THIS_TURN_RE = re.compile(
    r"^(?:the )?number of (?:(?P<nontoken>nontoken) )?(?P<qualifier>[a-z]+) that died this turn$",
    re.IGNORECASE,
)
#: "the number of red mana symbols in the mana costs of permanents you control"
#: (Outrage Shaman, Heartlash Cinder): CR 700.5's devotion count, named by the
#: chroma ability word's own template.
_COUNT_COLORED_MANA_SYMBOLS_RE = re.compile(
    rf"^(?:the )?number of (?P<color>{_COUNT_COLOR_WORD}) mana symbols? in the mana costs? of "
    r"permanents you control$",
    re.IGNORECASE,
)
#: "the number of noncreature, nonland cards in your graveyard" (Dragonfly
#: Swarm, Summon: Esper Ramuh, The Lord Master of Hell).
_COUNT_NONTYPE_CARDS_IN_YOUR_GRAVEYARD_RE = re.compile(
    r"^(?:the )?number of (?P<list>non-?[a-z]+(?:(?:, and |, | and )non-?[a-z]+)*) cards? "
    r"in your graveyard$",
    re.IGNORECASE,
)
#: "the number of different color pairs among permanents you control that are
#: exactly two colors" (Niv-Mizzet, Guildpact).
_COUNT_COLOR_PAIRS_RE = re.compile(
    r"^(?:the )?number of different (?:color|colour) pairs among permanents you control "
    r"that are exactly two colors$",
    re.IGNORECASE,
)
#: "that creature's power|toughness" read off the resolving trigger's event.
_EVENT_SUBJECT_STAT_RE = re.compile(
    r"^that (?:creature|permanent)['’]s (?P<stat>power|toughness)$", re.IGNORECASE
)
#: "creature it's blocking" / "creature blocking it" (see `_for_each_multiplier`).
_CREATURES_BLOCKING_RE = re.compile(
    r"^creatures? (?:it['’]s blocking|(?P<blocked_by_it>blocking it))$", re.IGNORECASE
)
#: "the number of times it was kicked" (Deathforge Shaman's "twice ..."): CR
#: 702.33d's count, read off the cast record of the spell the permanent was.
_TIMES_KICKED_RE = re.compile(
    r"^(?:the )?number of times (?:it|this (?:creature|permanent|artifact|enchantment|spell)) "
    r"was kicked$",
    re.IGNORECASE,
)

#: A count that may need the resolving source ("other than this creature").
SourcedCount = Callable[["Game", str, "CardState | None"], int]


def _is_equipped(game: "Game", board: "ComputedBoard", permanent: CardState) -> bool:
    """Whether any Equipment is attached to `permanent` right now (CR 301.5),
    read off the computed board's subtypes (CR 613.5)."""
    return any(
        other.attached_to == permanent.id and "Equipment" in board.of(other).subtypes
        for other in game.battlefield
    )


def _filtered_permanent_count(phrase: str) -> tuple[SourcedCount, bool] | None:
    """`_FILTERED_PERMANENT_COUNT_RE`'s count and whether it needs the source
    object (an "other"/"other than this creature" narrowing)."""
    match = _FILTERED_PERMANENT_COUNT_RE.fullmatch(phrase)
    if match is None:
        return None
    total_mana_value = match.group("measure").lower().startswith("total")
    quality = (match.group("quality") or "").lower()
    other = match.group("other") is not None or match.group("other_than") is not None
    stat = (match.group("stat") or "").lower()
    counter_word = match.group("counter")
    named = (match.group("named") or "").strip().lower()
    if not (total_mana_value or quality or other or stat or counter_word or named):
        return None  # a plain "the number of <type> you control" is not this reader's
    qualifier = match.group("qualifier")
    counts_any_permanent = qualifier.lower() in ("permanent", "permanents")
    card_type = None if counts_any_permanent else _singular_card_type(qualifier)
    subtype = None
    if not counts_any_permanent and card_type is None:
        subtype = _singular_subtype_for_count_expression(qualifier)
        if subtype is None:
            return None
    status = (match.group("status") or "").lower()
    bound = int(match.group("bound")) if match.group("bound") else 0
    at_most = (match.group("direction") or "").lower() == "less"
    counter_kind = _counter_kind(counter_word) if counter_word else None

    def count(game: "Game", controller: str, source: CardState | None) -> int:
        from ..conditions.board import permanent_is_modified

        board = game.computed_board()
        total = 0
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if other and source is not None and permanent.id == source.id:
                continue
            if named and permanent.name.lower() != named:
                continue  # "named Hare Apparent" (Hare Apparent): by printed name
            if card_type is not None and card_type not in chars.types:
                continue
            if subtype is not None and not any(word.lower() == subtype for word in chars.subtypes):
                continue
            if status and permanent.tapped != (status == "tapped"):
                continue
            if quality == "equipped" and not _is_equipped(game, board, permanent):
                continue
            if quality == "modified" and not permanent_is_modified(game, permanent, chars):
                continue
            if stat:
                value = (
                    chars.numeric_power
                    if stat == "power"
                    else chars.numeric_toughness
                    if stat == "toughness"
                    else int(chars.mana_value)
                )
                if (value > bound) if at_most else (value < bound):
                    continue
            if counter_kind is not None and not chars.counters.get(counter_kind, 0) > 0:
                continue
            total += int(chars.mana_value) if total_mana_value else 1  # CR 202.3
        return total

    return count, other


def _greatest_shared_creature_type_count(phrase: str) -> Callable[["Game", str], int] | None:
    """The largest group of `<qualifier>` the controller has that share one
    creature type (CR 205.3m). A changeling is every creature type (CR 702.73a),
    which the computed board already says in its subtypes."""
    match = _GREATEST_SHARED_CREATURE_TYPE_RE.fullmatch(phrase)
    if match is None:
        return None
    card_type = _singular_card_type(match.group("qualifier"))
    if card_type is None:
        return None
    from ...data.creature_types import creature_types

    def greatest_shared(game: "Game", controller: str) -> int:
        known = frozenset(creature_types())
        board = game.computed_board()
        sharing: dict[str, int] = {}
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller or card_type not in chars.types:
                continue
            for kind in known.intersection(chars.subtypes):
                sharing[kind] = sharing.get(kind, 0) + 1
        return max(sharing.values(), default=0)  # CR 107.2: nothing to count is 0

    return greatest_shared


def _died_this_turn_count(phrase: str) -> Callable[["Game", str], int] | None:
    """The turn's graveyard arrivals from the battlefield (CR 700.4) that were
    `<qualifier>` as they last existed (CR 603.10a), `Game.turn_history`'s
    "to_graveyard" entries - whoever controlled them, tokens included unless
    "nontoken"."""
    match = _COUNT_DIED_THIS_TURN_RE.fullmatch(phrase)
    if match is None:
        return None
    card_type = _singular_card_type(match.group("qualifier"))
    subtype = (
        None
        if card_type is not None
        else _singular_subtype_for_count_expression(match.group("qualifier"))
    )
    if card_type is None and subtype is None:
        return None
    nontoken = match.group("nontoken") is not None

    def died_this_turn(game: "Game", _controller: str) -> int:
        found = 0
        for entry in game.turn_history:
            chars = entry.characteristics
            if entry.kind != "to_graveyard" or chars is None:
                continue
            if card_type is not None and card_type not in chars.types:
                continue
            if subtype is not None and not any(word.lower() == subtype for word in chars.subtypes):
                continue
            if nontoken and chars.is_token:
                continue
            found += 1
        return found

    return died_this_turn


def _colored_mana_symbols_count(phrase: str) -> Callable[["Game", str], int] | None:
    match = _COUNT_COLORED_MANA_SYMBOLS_RE.fullmatch(phrase)
    if match is None:
        return None
    color = _COLOR_WORD_TO_COLOR[match.group("color").lower()]
    return lambda game, controller: devotion_to(game, controller, color)


def _nontype_cards_in_graveyard_count(phrase: str) -> Callable[["Game", str], int] | None:
    match = _COUNT_NONTYPE_CARDS_IN_YOUR_GRAVEYARD_RE.fullmatch(phrase)
    if match is None:
        return None
    excluded: set[Type] = set()
    for word in re.findall(r"non-?([a-z]+)", match.group("list").lower()):
        card_type = _singular_card_type(word)
        if card_type is None:
            return None
        excluded.add(card_type)

    def count_in_graveyard(game: "Game", controller: str) -> int:
        return sum(
            1 for card in game.player(controller).graveyard if not excluded.intersection(card.types)
        )

    return count_in_graveyard


def _color_pairs_count(phrase: str) -> Callable[["Game", str], int] | None:
    if _COUNT_COLOR_PAIRS_RE.fullmatch(phrase) is None:
        return None

    def count_pairs(game: "Game", controller: str) -> int:
        board = game.computed_board()
        pairs = {
            frozenset(chars.colors)
            for permanent in game.battlefield
            if (chars := board.of(permanent)).controller == controller
            and len(set(chars.colors)) == 2
        }
        return len(pairs)

    return count_pairs


def _nw06_counted_term(stripped: str) -> Callable[["Game", str], int] | None:
    """The source-free counted terms of NW-06, behind literal gates."""
    lowered = stripped.lower()
    if any(marker in lowered for marker in _FILTERED_PERMANENT_COUNT_MARKERS):
        filtered = _filtered_permanent_count(stripped)
        if filtered is not None:
            counted, needs_source = filtered
            if needs_source:
                return None
            return lambda game, controller: counted(game, controller, None)
    if "in common" in lowered:
        return _greatest_shared_creature_type_count(stripped)
    if "died this turn" in lowered:
        return _died_this_turn_count(stripped)
    if "mana symbol" in lowered:
        return _colored_mana_symbols_count(stripped)
    if "cards in your graveyard" in lowered and "non" in lowered:
        return _nontype_cards_in_graveyard_count(stripped)
    if "color pairs" in lowered or "colour pairs" in lowered:
        return _color_pairs_count(stripped)
    return None


def count_expression(phrase: str) -> Callable[["Game", str], int] | None:
    """Parse "the number of <type>[s] you control" or "... card(s) in your
    graveyard" into `(game, controller) -> int`, or `None` if `phrase` is not
    one of those two shapes.

    "You control" is read off the *computed* board (CR 613.5) - a creature
    that only became one through a continuous effect still counts, the same
    correction this wave's Ajani/Leyline reading of "each Cat you control"
    needs (CR 613.4, CR 205.3). "In your graveyard" is a zone question, not a
    layers one, so it reads `CardState.types` directly (CR 205.2a) - already
    the front-face-safe read `Card.types` gives a double-faced card outside
    the battlefield, per `models/card_state.py`'s `types` property.

    The returned function re-reads the board or graveyard every time it is
    called; it is the caller's job to call it exactly once, at the moment
    CR 611.2c fixes the magnitude, and keep the resulting `int` rather than
    the function itself.
    """
    stripped = phrase.strip().rstrip(".")
    if stripped.lower().endswith(_AS_YOU_CAST_SUFFIX):
        # "... as you cast this spell" (Jaws of Stone, Monstrous Onslaught):
        # the count was fixed while the spell was being cast (CR 601.2d needs it
        # to announce the division) and `Casting` recorded it as the cast's X,
        # so resolution reads that back instead of recounting a board a
        # response may have changed. A spell with no cast record (never cast
        # through a `Casting`) has nothing locked and counts live.
        live = count_expression(stripped[: -len(_AS_YOU_CAST_SUFFIX)])
        if live is None:
            return None
        return lambda game, controller: _locked_or_live(game, controller, live)
    if " plus " in stripped and (offset := _COUNT_NUMBER_PLUS_RE.fullmatch(stripped)) is not None:
        # "1 plus the number of cards named ... in all graveyards" (Kjeldoran
        # War Cry's mass pump, which reads its X through this function alone):
        # a fixed number added to one count, evaluated together (CR 608.2c).
        fixed = parse_count(offset.group("n"))
        counted_rest = count_expression(offset.group("rest"))
        if fixed is None or counted_rest is None:
            return None
        return lambda game, controller: fixed + counted_rest(game, controller)
    if (half := parse_half(stripped)) is not None:
        # "half the number of creature cards in your graveyard, rounded up"
        # (Ghoulcaller's Harvest): CR 107.1a - the card prints which way the
        # fraction rounds - over any count this function reads.
        counted_whole = count_expression(half.of)
        if counted_whole is None:
            return None
        round_up = half.round_up
        return lambda game, controller: halve(counted_whole(game, controller), round_up=round_up)
    from ..counter_effects import counter_history_count

    if (history_count := counter_history_count(stripped)) is not None:
        return history_count
    if "counters on" in stripped.lower() and (
        counters_held := _COUNTERS_ON_YOUR_PERMANENTS_RE.fullmatch(stripped)
    ):
        return _counters_on_permanents_you_control(counters_held)
    if (player_counters := player_counter_count(stripped)) is not None:
        return player_counters
    if "devoured" in stripped.lower() and (devoured := _devoured_count(stripped)) is not None:
        return devoured
    if "mana spent to cast" in stripped and _COLORS_OF_MANA_SPENT_TO_CAST_IT_RE.fullmatch(stripped):
        # "where X is the number of colors of mana spent to cast this spell"
        # (Radiant Flames, Kaleidoscorch): the converge count, read off the
        # spell now resolving - any damage/amount clause that defines its X
        # this way reads through here instead of needing a template per card.
        return _colors_spent_on_resolving
    if stripped.lower() == "that number":
        # The count channel (`Game.record_count`): the number an earlier
        # instruction of the same resolving object recorded (CR 608.2c) - the
        # "that number" `_amount_term` already reads, here for a "where X is"
        # definition (the discarded card's mana value, below).
        return lambda game, _controller: game.recorded_count() or 0
    if _COUNT_CREATURES_IN_YOUR_PARTY_RE.fullmatch(stripped):
        # CR 700.8a: "the number of creatures in a player's party ... is
        # performed automatically by the game and results in a number between
        # zero and four"; CR 700.8b's one-role-per-creature count, maximised,
        # is `designations.party_size`'s own matching.
        from ..designations import party_size

        return lambda game, controller: party_size(game, controller)
    if "devotion to" in stripped.lower() and (devotion := _devotion_count(stripped)) is not None:
        return devotion  # CR 700.5
    if _COUNT_BASIC_LAND_TYPES_RE.fullmatch(stripped):
        # Domain: Tribal Flames' own X definition. `BASIC_LAND_TYPES` names
        # CR 305.6's five; a land counts once per distinct basic type it
        # carries, on the computed board so a continuous effect that grants
        # one (Urborg, Tomb of Yawgmoth) still counts.
        def count_basic_land_types(game: "Game", controller: str) -> int:
            board = game.computed_board()
            found = {
                subtype
                for permanent in game.battlefield
                if board.of(permanent).controller == controller
                and Type.LAND in board.of(permanent).types
                for subtype in board.of(permanent).subtypes
                if subtype in BASIC_LAND_TYPES
            }
            return len(found)

        return count_basic_land_types

    if _COUNT_PLANESWALKER_TYPES_RE.fullmatch(stripped):
        # Tam, the Possibility's own X definition (CR 205.3j) - see
        # `_COUNT_PLANESWALKER_TYPES_RE`'s own docstring for why no closed
        # word list is needed.
        def count_planeswalker_types(game: "Game", controller: str) -> int:
            board = game.computed_board()
            found = {
                subtype
                for permanent in game.battlefield
                if board.of(permanent).controller == controller
                and Type.PLANESWALKER in board.of(permanent).types
                for subtype in board.of(permanent).subtypes
            }
            return len(found)

        return count_planeswalker_types

    if ("and/or" in stripped or " and " in stripped or " or " in stripped) and (
        listed := _COUNT_AND_OR_YOU_CONTROL_RE.fullmatch(stripped)
    ) is not None:
        return _count_permanents_matching_any(
            listed.group("list") or listed.group("list2"),
            opponents=(listed.group("whose") or listed.group("whose2")).lower()
            == "your opponents control",
        )

    if match := _COUNT_YOU_CONTROL_RE.fullmatch(stripped):
        # CR 110.5: status (tapped/untapped) is a permanent's physical state,
        # not a characteristic the computed board's layers touch, so it is
        # read straight off `CardState.tapped` rather than through `board.of`.
        # CR 508.1k: "attacking" (Kinscaer Sentry's own "the number of
        # attacking creatures you control") is combat state, read the
        # identical way off `Game.combat.attacker_ids` rather than tapped
        # status - a creature can be attacking and untapped at once (a
        # vigilance attacker), so this is never folded into the tapped check.
        status = match.group("status") or match.group("attacking_any")
        wants_tapped = (
            None
            if status is None or status.lower() == "attacking"
            else (status.lower() == "tapped")
        )
        wants_attacking = status is not None and status.lower() == "attacking"
        # "your opponents control" (Smaug, Wicked Worm's own "the number of
        # artifacts your opponents control") is the identical count, over the
        # complement of the controller's own permanents rather than their
        # own - `_belongs_to_opponent` below is the same "someone else, and
        # someone" reading `creatures_controlled_by_opponents_of` already
        # documents (a permanent with no controller at all belongs to
        # neither side).
        whose = match.group("whose")
        wants_anyone = whose is None or whose.lower() == "on the battlefield"
        wants_opponents = whose is not None and whose.lower() == "your opponents control"
        wants_nontoken = match.group("nontoken") is not None
        qualifier = match.group("qualifier") or match.group("attacking_qualifier")
        wanted_colors = frozenset(
            _COLOR_WORD_TO_COLOR[word]
            for word in re.findall(_COUNT_COLOR_WORD, match.group("colors") or "", re.IGNORECASE)
        )

        def _has_wanted_color(colors: "Sequence[Color]") -> bool:
            # CR 105.1/105.2: "white and/or blue" is any permanent that is at
            # least one of them; no colour list asks nothing.
            return not wanted_colors or bool(wanted_colors & set(colors))

        snow_word = (match.group("snow") or "").lower()
        # CR 205.4g: a snow permanent is any permanent with the supertype
        # snow; a nonsnow permanent is any that does not have it. CR 205.4a
        # lists "basic" among the supertypes the same way, so a nonbasic land
        # is any land without it (Weight of Spires's "nonbasic lands").
        wanted_supertype = Supertype.BASIC if "basic" in snow_word else Supertype.SNOW
        wants_supertype = not snow_word.startswith("non")

        def _has_wanted_snow(supertypes: "Sequence[Supertype]") -> bool:
            return not snow_word or (wanted_supertype in supertypes) == wants_supertype

        def _belongs_to_group(board_controller: str | None, controller: str) -> bool:
            if wants_anyone:
                return True
            if wants_opponents:
                return board_controller is not None and board_controller != controller
            return board_controller == controller

        # "permanents" is every card type at once (CR 110.1): Touch of the
        # Eternal's "the number of permanents you control".
        counts_any_permanent = qualifier.lower() in ("permanent", "permanents")
        card_type = _singular_card_type(qualifier)
        if card_type is None and counts_any_permanent:

            def count_permanents_on_board(game: "Game", controller: str) -> int:
                board = game.computed_board()
                return sum(
                    1
                    for permanent in game.battlefield
                    if _belongs_to_group(board.of(permanent).controller, controller)
                    and _has_wanted_color(board.of(permanent).colors)
                    and _has_wanted_snow(board.of(permanent).supertypes)
                    and (wants_tapped is None or permanent.tapped == wants_tapped)
                    and (not wants_attacking or permanent.id in game.combat.attacker_ids)
                    and (not wants_nontoken or not is_token(permanent))
                )

            return count_permanents_on_board
        if card_type is None:
            subtype = _singular_subtype_for_count_expression(qualifier)
            if subtype is None:
                return None

            def count_subtype_on_board(game: "Game", controller: str) -> int:
                # "the number of Faeries you control" (CR 205.3m's creature
                # types, or any other printed subtype) on the computed board,
                # so a changeling or a type-changing effect counts.
                board = game.computed_board()
                return sum(
                    1
                    for permanent in game.battlefield
                    if _belongs_to_group(board.of(permanent).controller, controller)
                    and any(word.lower() == subtype for word in board.of(permanent).subtypes)
                    and _has_wanted_color(board.of(permanent).colors)
                    and _has_wanted_snow(board.of(permanent).supertypes)
                    and (wants_tapped is None or permanent.tapped == wants_tapped)
                    and (not wants_attacking or permanent.id in game.combat.attacker_ids)
                    and (not wants_nontoken or not is_token(permanent))
                )

            return count_subtype_on_board

        def count_on_board(game: "Game", controller: str) -> int:
            board = game.computed_board()
            return sum(
                1
                for permanent in game.battlefield
                if _belongs_to_group(board.of(permanent).controller, controller)
                and card_type in board.of(permanent).types
                and _has_wanted_color(board.of(permanent).colors)
                and _has_wanted_snow(board.of(permanent).supertypes)
                and (wants_tapped is None or permanent.tapped == wants_tapped)
                and (not wants_attacking or permanent.id in game.combat.attacker_ids)
                and (not wants_nontoken or not is_token(permanent))
            )

        return count_on_board

    if "graveyard" in stripped.lower() and (in_graveyard := graveyard_count_expression(stripped)):
        # EP-02 R1 T5: "[the number of] <description> cards [named N] in your
        # graveyard / all graveyards", card types among, different mana values.
        return in_graveyard

    if " in " in stripped and (in_zone := hand_count_expression(stripped)) is not None:
        # EP-02 R2 T2: "[the number of] cards in your hand / their hand / your
        # opponents' hands", cards with a keyword in a graveyard.
        return in_zone

    if " ability in your graveyard" in stripped.lower() and (
        with_ability := _COUNT_CARDS_WITH_KEYWORD_ABILITY_IN_YOUR_GRAVEYARD_RE.fullmatch(stripped)
    ):
        # Zenith Flare's "the number of cards with a cycling ability in your
        # graveyard": a card has the ability when its printing carries that
        # keyword; CR 702.29f makes every typecycling a cycling ability.
        wanted_keyword = with_ability.group("keyword").lower()

        def count_cards_with_keyword_ability(game: "Game", controller: str) -> int:
            return sum(
                1
                for state in game.player(controller).graveyard
                if any(
                    keyword.lower() == wanted_keyword
                    or (wanted_keyword == "cycling" and keyword.lower().endswith("cycling"))
                    for keyword in state.keywords
                )
            )

        return count_cards_with_keyword_ability

    if match := _COUNT_CARDS_IN_YOUR_GRAVEYARD_RE.fullmatch(stripped):
        qualifier = match.group("qualifier")
        if " and " in qualifier:
            # "instant and sorcery cards" (Steal the Show, Blitz of the
            # Thunder-Raptor, Invade the City) - the union of the two types,
            # never a card that is somehow both at once; every word must
            # resolve to a real CR 205.2a type, or the whole count is left
            # unread rather than silently counting only the half it knew.
            card_types = [_singular_card_type(word.strip()) for word in qualifier.split(" and ")]
            if any(card_type is None for card_type in card_types):
                return None
            wanted_types = frozenset(card_type for card_type in card_types if card_type is not None)

            def count_type_list_in_graveyard(game: "Game", controller: str) -> int:
                return sum(
                    1
                    for state in game.player(controller).graveyard
                    if wanted_types & set(state.types)
                )

            return count_type_list_in_graveyard
        card_type = _singular_card_type(qualifier)
        if card_type is not None:

            def count_in_graveyard(game: "Game", controller: str) -> int:
                return sum(
                    1 for state in game.player(controller).graveyard if card_type in state.types
                )

            return count_in_graveyard

        # A qualifier that is not one of CR 205.2a's card types - Calamitous
        # Cave-In's own "the number of Cave cards in your graveyard" names a
        # land subtype (CR 205.3i), and Combustion Technique's own "the
        # number of Lesson cards in your graveyard" (CR 715) names a spell
        # subtype - the same fallback `count_on_board`'s own "you control"
        # branch above already takes.
        subtype = _singular_subtype_for_count_expression(match.group("qualifier"))
        if subtype is None:
            return None

        def count_subtype_in_graveyard(game: "Game", controller: str) -> int:
            return sum(
                1
                for state in game.player(controller).graveyard
                if any(word.lower() == subtype for word in state.subtypes)
            )

        return count_subtype_in_graveyard

    if match := _COUNT_CARDS_IN_GRAVEYARD_QUALITY_LIST_RE.fullmatch(stripped):
        # Hearth Elemental: split the comma/"and"/"or"/"and-or" list back
        # into its own clauses and read each one - a card type ("instant
        # cards") or CR 715's "have an Adventure" - failing the whole
        # expression closed the instant one clause is neither, the same
        # posture the "and" list just above already takes for a card type it
        # cannot place.
        clauses = [
            clause.strip()
            for clause in re.split(
                r",\s*(?:and/or\s+|and\s+|or\s+)?|\s+and/or\s+|\s+and\s+|\s+or\s+",
                match.group("list"),
                flags=re.IGNORECASE,
            )
            if clause.strip()
        ]
        wants_adventure = False
        wanted_types: set[Type] = set()
        for clause in clauses:
            if _ADVENTURE_CARD_CLAUSE_RE.fullmatch(clause):
                wants_adventure = True
                continue
            type_match = _TYPE_CARDS_CLAUSE_RE.fullmatch(clause)
            card_type = _singular_card_type(type_match.group("type")) if type_match else None
            if card_type is None:
                return None
            wanted_types.add(card_type)
        if not wanted_types and not wants_adventure:
            return None

        def count_quality_list_in_graveyard(game: "Game", controller: str) -> int:
            return sum(
                1
                for state in game.player(controller).graveyard
                if (wanted_types & set(state.types))
                or (wants_adventure and state.card.layout is Layout.ADVENTURE)
            )

        return count_quality_list_in_graveyard

    if match := _COUNT_THIS_WAY_RE.fullmatch(stripped):
        verb = match.group("verb").lower()
        return lambda game, _controller: counted_this_way(game, verb)

    if match := _TOTAL_OF_PAID_RE.fullmatch(stripped):
        total_verb = match.group("verb").lower()
        stat = match.group("stat").lower()
        return lambda game, _controller: total_of_paid_for_cost(game, total_verb, stat)

    if _COUNT_CARDS_IN_YOUR_HAND_RE.fullmatch(stripped):

        def count_in_hand(game: "Game", controller: str) -> int:
            return len(game.player(controller).hand)

        return count_in_hand

    if _COUNT_CARDS_IN_YOUR_LIBRARY_RE.fullmatch(stripped):

        def count_in_library(game: "Game", controller: str) -> int:
            return len(game.player(controller).library)

        return count_in_library

    if (life_total := life_this_turn_count(stripped)) is not None:
        return life_total

    if _AMOUNT_OF_LIFE_GAINED_THIS_TURN_RE.fullmatch(stripped):

        def life_gained_amount(game: "Game", controller: str) -> int:
            return game.life_gained_amount_this_turn.get(controller, 0)

        return life_gained_amount

    if _COUNT_CARDS_DISCARDED_THIS_TURN_RE.fullmatch(stripped):

        def cards_discarded_this_turn(game: "Game", controller: str) -> int:
            return game.cards_discarded_this_turn.get(controller, 0)

        return cards_discarded_this_turn

    if _COUNT_NONTOKEN_CREATURES_DIED_UNDER_CONTROL_RE.fullmatch(stripped):

        def nontoken_creatures_died_under_control(game: "Game", controller: str) -> int:
            return game.nontoken_creatures_died_under_control_this_turn.get(controller, 0)

        return nontoken_creatures_died_under_control

    if _COUNT_CREATURES_DIED_UNDER_CONTROL_RE.fullmatch(stripped):

        def creatures_died_under_control(game: "Game", controller: str) -> int:
            return sum(
                1
                for entry in game.turn_history
                if entry.kind == "to_graveyard"
                and entry.player == controller
                and entry.characteristics is not None
                and Type.CREATURE in entry.characteristics.types
            )

        return creatures_died_under_control

    if _COUNT_CARDS_IN_YOUR_GRAVEYARD_UNFILTERED_RE.fullmatch(stripped):

        def count_in_graveyard_unfiltered(game: "Game", controller: str) -> int:
            return len(game.player(controller).graveyard)

        return count_in_graveyard_unfiltered

    if match := _SPELLS_CAST_THIS_TURN_AMOUNT_RE.fullmatch(stripped):
        return _spells_cast_this_turn_count(match)

    if _COUNT_DAMAGE_ALREADY_DEALT_TO_YOU_RE.fullmatch(stripped):
        # CR 120.3a counts what was *dealt*: `Game.damage_dealt_this_turn`
        # holds each damage event as it happened, after prevention (CR 615.6:
        # prevented damage never happens), so it never held the prevented part.
        def damage_already_dealt_to_you(game: "Game", controller: str) -> int:
            return sum(
                event.amount
                for event in game.damage_dealt_this_turn
                if event.recipient_player == controller
            )

        return damage_already_dealt_to_you

    if _COUNT_CARDS_DRAWN_THIS_TURN_RE.fullmatch(stripped):
        # EC4's own running per-player total (`machines/conditions/history.
        # _drew`'s identical read of `Game.cards_drawn_this_turn`, reused
        # here for a count instead of a boolean) - Fractal Anomaly's own X:
        # "Create a 0/0 green and blue Fractal creature token and put X
        # +1/+1 counters on it, where X is the number of cards you've drawn
        # this turn."
        def cards_drawn_this_turn(game: "Game", controller: str) -> int:
            return game.cards_drawn_this_turn.get(controller, 0)

        return cards_drawn_this_turn

    if _COUNT_PERMANENTS_SACRIFICED_THIS_TURN_RE.fullmatch(stripped):

        def permanents_sacrificed_this_turn(game: "Game", controller: str) -> int:
            return sum(
                1
                for entry in game.turn_history
                if entry.kind == "sacrificed" and entry.player == controller
            )

        return permanents_sacrificed_this_turn

    if match := _DIFFERENTLY_NAMED_QUALIFIER_RE.fullmatch(stripped):
        # "the number of differently named `<qualifier>` you control" - Emil,
        # Vastlands Roamer's own X for its Fractal token's counters ("the
        # number of differently named lands you control"), generalised over
        # the qualifier the same way `count_expression`'s other board reads
        # are, rather than fixed to lands: CR 201.4a's own copiable name is
        # what "differently named" compares (a token with no name of its own
        # never joins any group, the same nameless-token reading `Game.
        # legend_rule_groups` already gives CR 201.4a for the legend rule).
        card_type = _singular_card_type(match.group("qualifier"))
        subtype = (
            None
            if card_type is not None
            else _singular_subtype_for_count_expression(match.group("qualifier"))
        )
        if card_type is None and subtype is None:
            return None

        def count_differently_named(game: "Game", controller: str) -> int:
            board = game.computed_board()
            names: set[str] = set()
            for permanent in game.battlefield:
                chars = board.of(permanent)
                if chars.controller != controller:
                    continue
                if card_type is not None and card_type not in chars.types:
                    continue
                if subtype is not None and subtype not in {word.lower() for word in chars.subtypes}:
                    continue
                name = permanent.name
                if name:
                    names.add(name)
            return len(names)

        return count_differently_named

    if match := _GREATEST_CHARACTERISTIC_AMONG_RE.fullmatch(stripped):
        # ecl-T1's Pummeler for Hire ("the greatest power among Giants you
        # control") and Sunderflock ("the greatest mana value among
        # Elementals you control") name a creature *subtype*, not one of CR
        # 205.2a's card types - `_singular_card_type` misses both, so a
        # subtype the same vocabulary `count_expression`'s own "the number of
        # `<qualifier>` you control" already reads (`_singular_subtype_for_
        # count_expression`) is tried second, never guessed at when neither
        # matches.
        card_type = _singular_card_type(match.group("qualifier"))
        subtype = (
            None
            if card_type is not None
            else _singular_subtype_for_count_expression(match.group("qualifier"))
        )
        if card_type is None and subtype is None:
            return None
        wants_power = match.group("characteristic").lower() == "power"
        wants_mana_value = match.group("characteristic").lower() == "mana value"

        def greatest_among(game: "Game", controller: str) -> int:
            board = game.computed_board()
            values: list[int] = []
            for permanent in game.battlefield:
                chars = board.of(permanent)
                if chars.controller != controller:
                    continue
                if card_type is not None and card_type not in chars.types:
                    continue
                if subtype is not None and not any(
                    word.lower() == subtype for word in chars.subtypes
                ):
                    continue
                if wants_mana_value:
                    values.append(int(permanent.mana_value))  # CR 202.3
                    continue
                # CR 208.5: "If a creature somehow has no value for its power,
                # its power is 0. The same is true for toughness." - a `*`
                # printing whose characteristic-defining ability nothing has
                # defined counts as 0, not as absent, which is exactly what
                # `numeric_power`/`numeric_toughness` already answer.
                values.append(chars.numeric_power if wants_power else chars.numeric_toughness)
            # CR 107.2: "If anything needs to use a number that can't be
            # determined, either as a result or in a calculation, it uses 0
            # instead" - an empty group is not an error, it is X = 0.
            return max(values) if values else 0

        return greatest_among

    if match := _DIFFERENT_CHARACTERISTIC_AMONG_RE.fullmatch(stripped):
        card_type = _singular_card_type(match.group("qualifier"))
        if card_type is None:
            return None
        wants_power = match.group("characteristic").lower() == "power"

        def different_among(game: "Game", controller: str) -> int:
            board = game.computed_board()
            values: set[int] = set()
            for permanent in game.battlefield:
                chars = board.of(permanent)
                if chars.controller != controller or card_type not in chars.types:
                    continue
                # CR 208.5: no value for power/toughness reads as 0, the same
                # `greatest_among` above already relies on.
                values.add(chars.numeric_power if wants_power else chars.numeric_toughness)
            return len(values)

        return different_among

    if (nw06_term := _nw06_counted_term(stripped)) is not None:
        return nw06_term

    # "the number of colors among `<qualifier>` you control" - Vivid's own
    # amount (CR 207.2c: an ability word has no rules meaning; the count is
    # CR 105.1's colors among a group of permanents, CR 105.2c excluding
    # colorless). `machines/vivid.py` is the one reader every Vivid card's
    # "where X is ..." shares, reused unchanged by the CDA (`layers.
    # _COLOR_COUNT_CDA_RE`) and the self cost reduction (`Game.cost_
    # reduction_for`) that print the identical phrase in a different position.
    from ..vivid import colors_among_count_expression

    colors_among = colors_among_count_expression(stripped)
    if colors_among is not None:
        return colors_among

    from ..ep02_r1_counted_permanents import counted_group_reader

    if (counted := counted_group_reader(stripped)) is not None:
        return lambda game, controller: counted(game, controller, None)

    return None


#: The two joining words an amount expression prints between its terms -
#: Slumbering Trudge's "three minus X".
_AMOUNT_OPERATOR_RE = re.compile(r"\s+(minus|plus)\s+", re.IGNORECASE)
#: "twice <term>", "three times <term>", "five times X" - CR 107.1's plain
#: arithmetic on one term: Burn at the Stake's "three times the number of
#: creatures tapped this way", Crackle with Power's "five times X".
_AMOUNT_TWICE_RE = re.compile(rf"^(?P<multiplier>{MULTIPLIER}) (?P<term>.+)$", re.IGNORECASE)


def _greatest_mana_value_among(cards: "Sequence[CardState]") -> int:
    """The shared arithmetic behind every "greatest mana value among `<pile>`"
    reader: CR 107.2's rule that "the greatest/least/... among" an empty set
    is 0, since there is no value to compare.
    """
    values = [state.mana_value for state in cards]
    return int(max(values)) if values else 0


def _greatest_mana_value_among_cards_in_exile(game: "Game", *_: object) -> int:
    """ "The greatest mana value among cards in exile" (Ulamog, the Defiler).

    Every card in exile, whoever owns it, read as it is when the amount is
    needed. A card exiled face down contributes 0: CR 406.3a, "A card exiled
    face down has no characteristics", and CR 202.3a, "The mana value of an
    object with no mana cost is 0", which `CardState.mana_value` already
    answers. An empty exile is 0 rather than an error: "the greatest ...
    among" an empty set is a number that can't be determined, and CR 107.2
    uses 0 for it.
    """
    return _greatest_mana_value_among(game.exile)


def _greatest_mana_value_among_cards_in_your_graveyard(
    game: "Game", controller: str, *_: object
) -> int:
    """ "The greatest mana value among cards in your graveyard" (Hapatra, the
    Desert Fang's own ETB trigger) - "your" is the ability's controller
    (CR 108.7), read live the same way the exile-wide reader above is.
    """
    return _greatest_mana_value_among(game.player(controller).graveyard)


#: "the number of `<kind>` counters on it" / "... on this `<noun>`" - a term
#: naming the object the expression is evaluated for, the way
#: `_OBJECT_CHARACTERISTIC_RE` names its power: Ulamog, the Defiler's own
#: "annihilator X, where X is the number of +1/+1 counters on it".
_OBJECT_COUNTER_COUNT_RE = re.compile(
    r"^the number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on (?:it|this [a-z]+)$",
    re.IGNORECASE,
)


#: Converge's own "for each `<description>`"/"where X is `<expr>`" term:
#: "color of mana spent to cast it" (Magmablood/Rancorous/Wildgrowth
#: Archaic), and "colors of mana spent to cast this spell/creature" for a
#: future printing that spells the count out that way instead of the "for
#: each" shape. See `machines/converge.colors_of_mana_spent`.
_COLORS_OF_MANA_SPENT_TO_CAST_IT_RE = re.compile(
    r"^(?:the number of )?colors? of mana spent to cast (?:it|this (?:spell|creature|permanent))$",
    re.IGNORECASE,
)


#: "the number of Goblins it devoured" (Voracious Dragon), "creature it
#: devoured" (Skullmulcher's and Marrow Chomper's "for each creature it
#: devoured"): CR 702.82b's count, read off `CardState.devoured` of the
#: permanent whose ability is resolving.
_DEVOURED_COUNT_RE = re.compile(
    r"^(?:the number of )?(?P<quality>[a-z][a-z'-]*?)s? it devoured$", re.IGNORECASE
)


def _devoured_count(phrase: str) -> Callable[["Game", str], int] | None:
    """`_DEVOURED_COUNT_RE`'s count: how many of the objects the resolving
    ability's source devoured (CR 702.82b) had the named card type or
    subtype as they last existed. The source is read as it is now or last
    existed (CR 608.2h), so the count survives the permanent leaving."""
    match = _DEVOURED_COUNT_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    word = match.group("quality")
    card_type = _singular_card_type(word)
    subtype = None if card_type is not None else _singular_subtype_for_count_expression(word)
    if card_type is None and subtype is None:
        return None

    def count(game: "Game", _controller: str) -> int:
        resolving = game.resolving
        if resolving is not None and is_ability(resolving):
            resolving = resolving.source_or_last_known(game)
        if not isinstance(resolving, CardState):
            return 0
        return sum(
            1
            for devoured in resolving.devoured
            if (card_type is not None and card_type in devoured.types)
            or (
                subtype is not None
                and subtype in {printed.lower() for printed in devoured.subtypes}
            )
        )

    return count


def _colors_spent_on_resolving(game: "Game", _controller: str) -> int:
    """Converge's count (CR 207.2c; `machines/converge.colors_of_mana_spent`)
    for whatever is resolving now: the spell itself, or - for a trigger written
    on a permanent ("When this creature enters, ... where X is the number of
    colors of mana spent to cast this creature") - the permanent its ability
    came from, whose cast record `Game._carry_cast_record` re-keyed onto it
    (CR 400.7a)."""
    resolving = game.resolving
    if resolving is not None and is_ability(resolving):
        resolving = resolving.source_or_last_known(game)
    return colors_of_mana_spent(game, resolving)


#: "the number of Equipment attached to him" (Whiplash, Vengeful Engineer;
#: Shagrat, Loot Bearer's "... attached to Shagrat", its name already
#: "this permanent") - a count of one subtype attached to the object the
#: expression is evaluated for (CR 301.5a: an Equipment is attached to the
#: creature it equips), read as the effect applies (CR 608.2h).
_OBJECT_ATTACHED_COUNT_RE = re.compile(
    r"^the number of (?P<subtype>[A-Za-z]+) attached to (?:it|him|her|this [a-z]+)$",
    re.IGNORECASE,
)


#: "instant and sorcery card exiled with it" (Murktide Regent) - CR 607.2q's
#: link, written by `machines/objects_as_costs.delve` onto every card a
#: delve payment exiles as `ExileAnnotation.linked_permanent_id`. `types`
#: is optional the same way `_SPELLS_CAST_THIS_TURN_AMOUNT_RE` below's is -
#: a bare "cards exiled with it" would count every one, though no printing in
#: the pool omits the type list yet.
_CARDS_EXILED_WITH_IT_RE = re.compile(
    r"^(?:(?P<types>[a-z, ]+?) )?cards? exiled with it$", re.IGNORECASE
)

#: "instant and sorcery spell you've cast this turn" (Ral, Leyline Prodigy) -
#: `Game.spells_cast_this_turn`'s own running per-player list, CR 601.2i's
#: "any abilities that trigger when a spell is cast" moment being the same
#: moment this list gains an entry.
_SPELLS_CAST_THIS_TURN_AMOUNT_RE = re.compile(
    r"^(?:the number of )?(?P<other>other )?(?:(?P<types>[a-z, ]+?) )?spells? you'?ve cast "
    r"this turn$",
    re.IGNORECASE,
)


def _spells_cast_this_turn_count(match: re.Match[str]) -> Callable[["Game", str], int] | None:
    """`_SPELLS_CAST_THIS_TURN_AMOUNT_RE`'s count: the spells `controller` has
    cast this turn (`Game.spells_cast_this_turn`, written as each becomes cast,
    CR 601.2i), narrowed to a type list when one is printed. "Other" leaves out
    the spell now resolving - Thunder Salvo's own "2 plus the number of other
    spells you've cast this turn" does not count itself - and is the whole
    list when nothing is resolving. `None` for a type list this cannot read."""
    types = None if match.group("types") is None else _read_type_word_list(match.group("types"))
    if match.group("types") is not None and types is None:
        return None
    leaves_out_resolving = match.group("other") is not None

    def count_spells_cast_this_turn(game: "Game", controller: str) -> int:
        resolving = game.resolving if leaves_out_resolving else None
        return sum(
            1
            for state in game.spells_cast_this_turn.get(controller, [])
            if (resolving is None or state.id != resolving.id)
            and (types is None or set(state.types) & types)
        )

    return count_spells_cast_this_turn


#: "2 or the greatest power among Dinosaurs you control, whichever is greater"
#: (Triumphant Chomp): the larger (or, "whichever is less", the smaller) of two
#: terms, each read as any other term of an amount is.
_WHICHEVER_IS_RE = re.compile(
    r"^(?P<first>.+?) or (?P<second>.+?),? whichever is (?P<which>greater|less)$", re.IGNORECASE
)


#: "the amount of damage dealt to it this turn" (Tangled Colony).
_DAMAGE_DEALT_TO_IT_THIS_TURN_RE = re.compile(
    r"^(?:the )?(?:amount of )?damage dealt to (?:it|this (?:creature|permanent)) this turn$",
    re.IGNORECASE,
)


#: "the amount of damage those creatures dealt to that player" (Quartzwood
#: Crasher): the combat damage the creatures a batched "one or more
#: `<description>` deal combat damage to a player" trigger counted
#: (`machines/triggers.batched_combat_damage_sources`, CR 603.2c) dealt to
#: the player of that event in that step - each one's latest combat damage to
#: that player on the damage ledger (CR 120.3: each is its own damage).
_DAMAGE_THOSE_CREATURES_DEALT_RE = re.compile(
    r"^(?:the )?amount of damage those creatures dealt to that player$", re.IGNORECASE
)


def _damage_those_creatures_dealt(game: "Game", controller: str) -> int:
    """`_DAMAGE_THOSE_CREATURES_DEALT_RE`'s value for the resolving trigger."""
    from ..triggers import batched_combat_damage_sources

    resolving = game.resolving
    if not isinstance(resolving, AbilityOnStack) or resolving.event is None:
        return 0
    event = resolving.event
    condition = getattr(resolving.ability, "condition", None)
    if event.player is None or not condition:
        return 0
    sources = set(batched_combat_damage_sources(game, condition, controller, event) or ())
    total = 0
    for record in reversed(game.damage_dealt_this_turn):
        if not sources:
            break
        if (
            record.combat
            and record.recipient_player == event.player
            and record.source_id in sources
        ):
            total += record.amount
            sources.discard(record.source_id)
    return total


#: "its mana value" / "this permanent's mana value" - the object the
#: expression is evaluated for (Terminal Velocity's granted leaves trigger).
_ITS_MANA_VALUE_RE = re.compile(
    r"^(?:its|this (?:creature|permanent|artifact|token)(?:'|\u2019)s) mana value$",
    re.IGNORECASE,
)


#: "the number of counters on permanents you control" / "the number of +1/+1
#: counters on creatures you control" (Hydra Trainer's X) - CR 122.1: every
#: counter of the named kind (any kind when none is printed) on the permanents
#: of that type the controller has, read off the computed board (CR 613.5).
_COUNTERS_ON_YOUR_PERMANENTS_RE = re.compile(
    r"^the (?:total )?number of (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters on "
    r"(?P<what>permanents|creatures|artifacts|enchantments|lands|planeswalkers) you control$",
    re.IGNORECASE,
)


def _counters_on_permanents_you_control(match: re.Match[str]) -> Callable[["Game", str], int]:
    kind = None if match.group("kind") is None else _counter_kind(match.group("kind"))
    what = match.group("what").lower()
    wanted = None if what == "permanents" else _singular_card_type(what.removesuffix("s"))

    def count(game: "Game", controller: str) -> int:
        total = 0
        for permanent in game.permanents_controlled_by(controller):
            if wanted is not None and wanted not in game.characteristics_of(permanent).types:
                continue
            total += (
                sum(permanent.counters.counts.values())
                if kind is None
                else (permanent.counters[kind])
            )
        return total

    return count


def _amount_term(term: str) -> AmountReader | None:
    """One term of `amount_expression`, or `None` when it is not readable."""
    text = term.strip()
    lowered = text.lower()
    if "whichever is" in lowered and (extremum := _WHICHEVER_IS_RE.fullmatch(text)) is not None:
        first = _amount_term(extremum.group("first"))
        second = _amount_term(extremum.group("second"))
        if first is None or second is None:
            return None
        pick = max if extremum.group("which").lower() == "greater" else min
        return lambda game, controller, obj, x: pick(
            first(game, controller, obj, x), second(game, controller, obj, x)
        )
    constant = parse_count(text)
    if constant is not None:
        return lambda _game, _controller, _object, _x: constant
    if "devoured" in lowered and (devoured := _devoured_count(text)) is not None:
        # Ahead of the permanent counts below, which would otherwise read
        # "the number of Goblins" off the board and drop "it devoured".
        return lambda game, controller, _object, _x: devoured(game, controller)
    if (half := parse_half(text)) is not None:
        # CR 107.1a: the card prints which way a fractional result rounds;
        # `numbers.parse_half` refuses a "half" that does not say.
        inner = _amount_term(half.of)
        if inner is None:
            return None
        round_up = half.round_up
        return lambda game, controller, obj, x: halve(
            inner(game, controller, obj, x), round_up=round_up
        )
    if match := _OBJECT_COUNTER_COUNT_RE.fullmatch(text):
        kind = _counter_kind(match.group("kind"))

        def read_object_counters(
            _game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            # CR 608.2h: the object as it is now, or as it last existed.
            return 0 if obj is None else obj.counters[kind]

        return read_object_counters
    if lowered == "x":
        return lambda _game, _controller, _object, x: x
    if "times" in lowered and _TIMES_KICKED_RE.fullmatch(text):

        def read_times_kicked(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            # CR 702.33d, read as the object last existed (CR 608.2h): the cast
            # record of the spell this permanent was (CR 400.7d), none when it
            # was never cast.
            record = None if obj is None else game.cast_record_of(obj)
            return 0 if record is None else record.kicked

        return read_times_kicked
    if any(marker in lowered for marker in _FILTERED_PERMANENT_COUNT_MARKERS) and (
        filtered := _filtered_permanent_count(text)
    ):
        sourced = filtered[0]
        return lambda game, controller, obj, _x: sourced(game, controller, obj)
    from ..ep02_r1_counted_permanents import counted_group_reader

    if (counted := counted_group_reader(text)) is not None:
        return lambda game, controller, obj, _x: counted(
            game, controller, None if obj is None else str(obj.id)
        )
    if (
        "mana value" in lowered
        and event_terms_enabled()
        and _CAST_SPELL_MANA_VALUE_RE.fullmatch(text)
    ):
        # Off a "whenever you cast a spell" trigger "its" / "that spell's" is the
        # spell the cast event names (Teval, Arbiter of Virtue): the event's own
        # mana value (CR 202.3e - X counted as announced).
        def read_cast_mana_value(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            cast_value = cast_spell_mana_value(game)
            if cast_value is not None:
                return cast_value
            return 0 if obj is None else int(obj.mana_value)

        return read_cast_mana_value
    if "mana value" in lowered and _ITS_MANA_VALUE_RE.fullmatch(text):
        # CR 202.3: the object's mana value, as it last existed if it has left
        # the battlefield (CR 603.10a looks back in time for a leaves trigger).
        return lambda _game, _controller, obj, _x: 0 if obj is None else int(obj.mana_value)
    if event_terms_enabled() and (event_stat := _EVENT_SUBJECT_STAT_RE.fullmatch(text)) is not None:
        # "that creature's power" off a trigger whose event names a creature
        # (Terror of the Peaks' "another creature you control enters"): the
        # subject as it last existed (CR 608.2h).
        wants_power = event_stat.group("stat").lower() == "power"

        def read_event_subject_stat(
            game: "Game", _controller: str, _obj: CardState | None, _x: int
        ) -> int:
            return event_subject_stat(game, wants_power=wants_power)

        return read_event_subject_stat
    if lowered == "the difference between its power and toughness":
        # Doran, Besieged by Time's own X: "it gets +X/+X until end of turn,
        # where X is the difference between its power and toughness." Every
        # printed "the difference between `<A>` and `<B>`" this engine has
        # seen (Spry and Mighty's own "the difference between the chosen
        # creatures' powers" is the other one, read separately since its two
        # terms are two different objects rather than one object's own two
        # characteristics) is a non-negative magnitude - the greater minus
        # the lesser, never a signed subtraction - so a creature with more
        # toughness than power gets exactly the pump a creature with more
        # power than toughness does. `obj` is the object the amount is
        # evaluated for (CR 608.2h): here, the attacking or blocking creature
        # itself (`_parse_event_subject_variable_pump_clause`'s own "it"),
        # read off the computed board (CR 613.5) the same way every other
        # object-characteristic term in this function does.
        def read_power_toughness_difference(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            if obj is None:
                return 0
            power = game.power_of(obj) or 0
            toughness = game.toughness_of(obj) or 0
            return abs(power - toughness)

        return read_power_toughness_difference
    if lowered in ("your life total", "their life total", "its controller's life total"):
        # ecl-T8: Ajani, Outland Chaperone's own "-8: Look at the top X cards
        # of your library, where X is your life total." CR 119.1's current
        # total, read as the effect applies (CR 608.2h) off the resolving
        # object's own controller - the same `controller` argument every
        # other term here already receives.
        return lambda game, controller, _object, _x: game.player(controller).life
    if lowered in (
        "your starting life total",
        "their starting life total",
        "his starting life total",
        "her starting life total",
    ):
        # CR 103.4/119.1: Torgaar, Famine Incarnate's "up to one target
        # player's life total becomes half their starting life total,
        # rounded down" and The Endstone's "your life total becomes half
        # your starting life total, rounded up" both reach this through
        # `parse_half`'s own recursive `_amount_term(half.of)` call - this
        # term is the base a "half `<this>`, rounded ..." wraps, the
        # identical composition `_HALF_OF_OWN_LIBRARY_RE`'s sibling terms
        # already lean on - and Resolute Archangel's/Long Rest's/Oketra's
        # Last Mercy's own bare "equal to your starting life total" reaches
        # it directly, the "equal to " prefix stripped by the life-total-
        # becomes reader before this is ever asked. `controller` is
        # whichever player this amount is being asked about (CR 608.2h),
        # never assumed to be "you" - the same convention "your life total"
        # just above already keeps.
        return lambda game, controller, _object, _x: game.player(controller).starting_life
    if lowered == "the highest life total among all players":
        # Arbiter of Knollridge's own ETB: "each player's life total
        # becomes the highest life total among all players" (CR 119.1,
        # CR 102.1's whole player set). Read fresh each time this is asked -
        # the life-total-becomes reader snapshots every player's answer
        # before applying any of them, so this always sees the totals as
        # they stood before the effect began adjusting anyone's.
        return lambda game, _controller, _object, _x: max(
            (player.life for player in game.players_in_game), default=0
        )
    if lowered == "the lowest life total among all players":
        # Repay in Kind's own twin: "each player's life total becomes the
        # lowest life total among all players."
        return lambda game, _controller, _object, _x: min(
            (player.life for player in game.players_in_game), default=0
        )
    if lowered == "that number":
        # Invincible Hymn's "Count the number of cards in your library.
        # Your life total becomes that number." and Touch of the Eternal's
        # "count the number of permanents you control. Your life total
        # becomes that number." - CR 608.2c's own "later text ... may modify
        # the meaning of earlier text": the *first* sentence's "Count the
        # number of `<expr>`" clause (`_parse_count_the_number_of_clause`)
        # records the count through `Game.record_count`, the identical
        # channel every other "that many"/"that much" reader in this file
        # (`that_many`) already reads back - "that number" is simply that
        # same channel's own noun for a plain count rather than a count of
        # cards moved.
        return lambda game, _controller, _object, _x: game.recorded_count() or 0
    if _COLORS_OF_MANA_SPENT_TO_CAST_IT_RE.fullmatch(text):
        # Converge (CR 207.2c), the enters-with position: Magmablood/
        # Rancorous/Wildgrowth Archaic's own "This creature enters with a
        # +1/+1 counter on it for each color of mana spent to cast it." -
        # `_COUNTER_FOR_EACH` (`machines/replacement.py`) already reads the
        # "for each `<description>`" tail into this `amount_expression` call;
        # what was missing was this one term, reusing the exact reader
        # Prismatic Ending's own converge clause and CR 702.44b's Sunburst
        # already carry (`machines/converge.colors_of_mana_spent`), off
        # `obj` - the entering permanent, whose `Game.cast_record_of` still
        # answers this once `Game._carry_cast_record` has re-keyed it from
        # the spell that resolved into it (CR 400.7a/400.7b).
        return lambda game, _controller, obj, _x: colors_of_mana_spent(game, obj)
    if match := _OBJECT_ATTACHED_COUNT_RE.fullmatch(text):
        attached_subtype = canonical_subtype(match.group("subtype"))
        if attached_subtype is None:
            return None

        def read_attached_count(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            if obj is None:
                return 0
            board = game.computed_board()
            return sum(
                1
                for permanent in game.battlefield
                if permanent.attached_to == obj.id
                and attached_subtype in {word.lower() for word in board.of(permanent).subtypes}
            )

        return read_attached_count
    if match := _AMOUNT_TWICE_RE.fullmatch(text):
        factor = parse_multiplier(match.group("multiplier"))
        inner = _amount_term(match.group("term"))
        if factor is None or inner is None:
            return None
        return lambda game, controller, obj, x: factor * inner(game, controller, obj, x)
    if "those creatures dealt" in lowered and _DAMAGE_THOSE_CREATURES_DEALT_RE.fullmatch(text):
        return lambda game, controller, _object, _x: _damage_those_creatures_dealt(game, controller)
    if "damage dealt to" in lowered and _DAMAGE_DEALT_TO_IT_THIS_TURN_RE.fullmatch(text):
        # Tangled Colony's "X is the amount of damage dealt to it this turn":
        # `obj` is the resolving ability's source, which a dies trigger finds
        # in the graveyard - the ledger still answers (CR 608.2h).
        from ..conditions.history import damage_dealt_to_object_this_turn

        return lambda game, _controller, obj, _x: (
            0 if obj is None else damage_dealt_to_object_this_turn(game, obj.id)
        )
    if lowered == "the greatest mana value among cards in exile":
        return lambda game, _controller, _object, _x: _greatest_mana_value_among_cards_in_exile(
            game
        )
    if lowered == "the number of times you descended this turn":
        # CR 700.11's own count question - The Mycotyrant's "create X ...
        # tokens ..., where X is the number of times you descended this
        # turn." `Game.descend_count` is the same running total
        # `intervening_if_holds`'s "you descended this turn" reads.
        return lambda game, controller, _object, _x: game.descend_count(controller)
    if lowered == "the greatest mana value among cards in your graveyard":
        return lambda game, controller, _object, _x: (
            _greatest_mana_value_among_cards_in_your_graveyard(game, controller)
        )
    if lowered == "the amount of mana spent to cast this spell":
        # CR 601.2h, self-referential (CR 700.7's own "this spell") - Molten
        # Note's own "deals damage ... equal to the amount of mana spent to
        # cast this spell": `obj` is the resolving spell itself
        # (`deal_damage_equal_to_expression`'s own docstring already
        # documents that convention for every "this <noun>" term this
        # function reads), whose `CastRecord` this reads directly rather
        # than through `machines/conditions/cast_record`'s boolean-only
        # "N or more mana was spent" reader - this term needs the number
        # itself, not a threshold comparison. Flashback pays the flashback
        # cost as the spell is cast (CR 702.34a), which `Casting`/`Game.
        # note_cast` already record into the same `mana_spent` this reads,
        # so a flashback-cast Molten Note counts what it actually paid.
        def read_mana_spent_to_cast_this_spell(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            if obj is None:
                return 0
            record = game.cast_record_of(obj)
            return record.total_mana_spent if record is not None else 0

        return read_mana_spent_to_cast_this_spell
    if match := _OBJECT_CHARACTERISTIC_RE.fullmatch(text):
        # CR 208.1's power/toughness, CR 208.5's zero default for a value
        # that can't be determined (the object has already left the
        # battlefield, or a `*` characteristic-defining ability has nothing
        # to compute from).
        characteristic = match.group("characteristic").lower()
        if characteristic == "loyalty":

            def read_object_loyalty(
                _game: "Game", _controller: str, obj: CardState | None, _x: int
            ) -> int:
                if obj is None:
                    return 0
                counters = obj.counters if obj.zone is Zone.BATTLEFIELD else obj.last_known_counters
                return counters[Counter.LOYALTY]

            return read_object_loyalty
        wants_power = characteristic == "power"

        def read_object_characteristic(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            if obj is None:
                return 0
            value = game.power_of(obj) if wants_power else game.toughness_of(obj)
            return max(value, 0) if value is not None else 0

        return read_object_characteristic
    if match := _CARDS_EXILED_WITH_IT_RE.fullmatch(text):
        types = None if match.group("types") is None else _read_type_word_list(match.group("types"))
        if match.group("types") is not None and types is None:
            return None

        def count_cards_exiled_with_it(
            game: "Game", _controller: str, obj: CardState | None, _x: int
        ) -> int:
            # CR 607.2q: only cards `machines/objects_as_costs.delve` (or
            # another exile-while-paying-a-cost ability) linked to *this*
            # entering object - `ExileAnnotation.links_to` matches on id
            # alone, which is right here: the link was written while `obj`
            # was still the spell on the stack, before its own zone change
            # to the battlefield gave it a fresh `zone_change_stamp`.
            if obj is None:
                return 0
            return sum(
                1
                for card in game.exile
                if card.exile_annotation is not None
                and card.exile_annotation.links_to(obj.id, None)
                and (types is None or set(card.types) & types)
            )

        return count_cards_exiled_with_it
    if match := _SPELLS_CAST_THIS_TURN_AMOUNT_RE.fullmatch(text):
        counted_spells = _spells_cast_this_turn_count(match)
        if counted_spells is None:
            return None
        return lambda game, controller, _obj, _x: counted_spells(game, controller)
    counted = count_expression(text) or _devotion_count(text)
    if counted is not None:
        return lambda game, controller, _object, _x: counted(game, controller)
    return None


def amount_expression(phrase: str) -> AmountReader | None:
    """Read the `<expr>` of "counters ... equal to `<expr>`" into a reader, or
    `None` when any term of it is unreadable.

    Terms are a literal number, X, "twice `<term>`", or one of the game-value
    counts `count_expression` and `_devotion_count` already read; "minus" and
    "plus" join them left to right. The caller supplies X: CR 107.3m's X of the
    spell that became the entering object, or the resolving ability's own X.

    CR 107.1b: "If a calculation that would determine the result of an effect
    yields a negative number, zero is used instead" - three minus X for X=5 is
    zero counters.
    """
    parts = _AMOUNT_OPERATOR_RE.split(phrase.strip().rstrip("."))
    readers = [_amount_term(term) for term in parts[0::2]]
    if not readers or any(reader is None for reader in readers):
        return None
    operators = [operator.lower() for operator in parts[1::2]]
    first, *rest = [reader for reader in readers if reader is not None]

    def evaluate(game: "Game", controller: str, obj: CardState, x: int) -> int:
        total = first(game, controller, obj, x)
        for operator, reader in zip(operators, rest, strict=True):
            value = reader(game, controller, obj, x)
            total = total - value if operator == "minus" else total + value
        return max(total, 0)  # CR 107.1b

    return evaluate


def _fixed_or_where_x_amount(raw: str, where_x: str | None) -> AmountReader | None:
    """One `numbers.count_pattern(x=True)` capture plus an optional
    `numbers.where_x_pattern()` tail, read into a uniform `AmountReader` -
    shared by the CR 701 keyword actions embedded in ability/effect text
    (earthbend, amass) and the mass-damage "N damage to each ..." shape,
    none of which carry a spell's own announced X (CR 107.3a) to substitute
    against: their X, when they print one, is always the printed "where X is
    `<expr>`" of CR 107.3f, evaluated through `amount_expression` the same
    way `_parse_put_counters_equal_to_clause` reads its own "equal to
    `<expr>`" tail.

    `None` when `raw` is "x"/"X" but the clause names no definition, or names
    one `amount_expression` cannot read - CR 107.3a's self-announced X is a
    spell-cast concept these keyword actions have no channel to ask a player
    about, so an undefined X here fails closed rather than being treated as
    zero or guessed at.
    """
    if raw.strip().lower() == "x":
        if where_x is None:
            return None
        return amount_expression(where_x)
    amount = parse_count(raw)
    if amount is None:
        return None
    return lambda _game, _controller, _obj, _x: amount


#: "your devotion to <color>" (CR 700.5) - Gray Merchant of Asphodel's own
#: magnitude. Read separately from `count_expression`'s "number of <type>
#: you control"/"<type> cards in your graveyard" family above: a genuinely
#: different expression shape (a color, not a card type; every permanent's
#: mana cost, not a filtered count of permanents), not a wider qualifier
#: grammar bolted onto that one.
_DEVOTION_RE = re.compile(
    r"^your devotion to (?P<color>white|blue|black|red|green)$", re.IGNORECASE
)


def _devotion_count(phrase: str) -> Callable[["Game", str], int] | None:
    """ "your devotion to `<color>`" -> `(game, controller) -> int` (CR 700.5):
    the number of mana symbols of that color among the mana costs of
    permanents `controller` controls.

    CR 107.4e: "A hybrid mana symbol is also a colored mana symbol" of each
    color it carries, and `ManaSymbol.colors` (`models/mana.py`) already
    carries every symbol kind's colors uniformly - plain colored, hybrid,
    monocolored hybrid, and Phyrexian alike - so this reads that field
    directly rather than special-casing hybrid or Phyrexian mana itself.

    CR 700.5a's "face-down spells and permanents are considered to lack a
    mana cost" is not read here: nothing in the pool needs a face-down
    permanent's devotion, and `CardState.mana_cost` (already up-face-aware,
    per `models/card_state.py`) is what this reads instead.
    """
    match = _DEVOTION_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    color = _COLOR_WORD_TO_COLOR[match.group("color").lower()]

    def count_devotion(game: "Game", controller: str) -> int:
        return devotion_to(game, controller, color)

    return count_devotion


def devotion_to(game: "Game", controller: str, color: Color) -> int:
    """CR 700.5: "A player's devotion to [color] is equal to the number of
    mana symbols of that color among the mana costs of permanents that player
    controls."

    Pulled out of `_devotion_count`'s closure so `Game.activate_ability` can
    reach the identical count for Nykthos, Shrine to Nyx's own mana ability -
    a mana ability never touches the stack (CR 605.3b), so it never reaches
    any of this module's clause parsers and needs the primitive rather than
    the phrase reader. Every caveat in `_devotion_count`'s docstring (CR
    107.4e's hybrid symbols, CR 700.5a's face-down permanents) applies here
    unchanged, since this is the body that used to be there.
    """
    total = 0
    for permanent in game.permanents_controlled_by(controller):
        cost = permanent.mana_cost
        if not cost:
            continue
        for symbol in ManaCost.parse(cost).symbols:
            if color in symbol.colors:
                total += 1
    # CR 604.2: "Your devotion to each color and each combination of colors is
    # increased by one" (Altar of the Pantheon) - one per such permanent.
    board = game.computed_board()
    total += sum(
        1
        for permanent in game.permanents_controlled_by(controller)
        if board.of(permanent).has_ability(DEVOTION_BONUS_TEXT)
    )
    return total


#: "each opponent loses X life, where X is your devotion to `<color>`." -
#: Gray Merchant of Asphodel's and Erebos, God of the Dead's shared "devotion
#: drain" template. Distinct from `_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE`'s
#: "loses life equal to `<expr>`" shape just above (Grist's own, with no X in
#: it at all) - this one names X explicitly and then defines it separately.
_OPPONENT_LOSES_X_LIFE_WHERE_X_IS_RE = re.compile(
    r"^each opponent loses x life, where x is (?P<expr>.+?)\.?$", re.IGNORECASE
)
#: "You gain life equal to the life lost this way." - the paired second
#: sentence, CR 119.3's *actual* amount lost (after any floor or prevention),
#: not a second evaluation of the first sentence's X.
_GAIN_LIFE_EQUAL_TO_LIFE_LOST_RE = re.compile(
    r"^you gain life equal to the life lost this way$", re.IGNORECASE
)


def _parse_devotion_drain_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Gray Merchant of Asphodel's whole paragraph: "each opponent loses X
    life, where X is your devotion to black. You gain life equal to the life
    lost this way." Read as one CR 608.2c instruction pair - the life gained
    is what each opponent's `Player.lose_life` actually took off, summed
    across every opponent, not a recomputed devotion total, so this evaluates
    devotion once and then measures the real life-total delta.
    """
    if index + 1 >= len(clauses):
        return None
    first_match = _OPPONENT_LOSES_X_LIFE_WHERE_X_IS_RE.fullmatch(clauses[index].strip())
    if first_match is None:
        return None
    counter = _devotion_count(first_match.group("expr"))
    if counter is None:
        return None
    if _GAIN_LIFE_EQUAL_TO_LIFE_LOST_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        amount = counter(game, controller.username)
        if amount <= 0:
            return
        total_lost = 0
        for opponent in _opponents(game, controller.username):
            before = opponent.life
            game.lose_life(opponent, amount)
            total_lost += before - opponent.life
        if total_lost > 0:
            game.gain_life(controller, total_lost)  # CR 119.10: replacements apply

    return 2, effect


#: The literal magnitude, as the printed sentence writes it before the number
#: is known. Substituted once, at resolution: CR 608.2h, "the answer is
#: determined only once, when the effect is applied", and CR 611.2c fixes the
#: set of objects the resulting continuous effect applies to at the same
#: moment. Every standalone "X" in the sentence is the same variable (CR
#: 107.3f), so a plain "-X/-0" (Yuriko, Hope from the Shadows) substitutes
#: the identical way the symmetric "X/X" (Jolrael, Voice of Zhalfir) does -
#: `_X_TOKEN_RE` is not anchored to the "X/X" shape at all.
_X_TOKEN_RE = re.compile(r"(?<![\w])X(?![\w])")

#: "that creature's power"/"that creature's toughness" - Arni, Renowned
#: Champion's own X ("Whenever another creature you control enters, Arni
#: gets +X/+0 until end of turn, where X is that creature's power.") *and*
#: Xenagos, God of Revels' own X ("... another target creature you control
#: gains haste and gets +X/+X until end of turn, where X is that creature's
#: power."). CR 400.7's anaphora reads "that creature" off the *nearest*
#: antecedent noun, which is a genuinely different object for each of these
#: two: Arni's ability names no target at all, so "that creature" can only
#: be CR 603.2's triggering object (`GameEvent.subject_id`); Xenagos's own
#: ability *does* target a creature earlier in the same instruction, and
#: that target - not whatever merely triggered the ability - is what "that
#: creature" reads back to. `_is_referent_power_expression`'s own "that
#: `<type>`'s power" is the narrower, sacrifice-consequence-only twin of
#: this - a *different* mechanism (`_parse_sacrifice_consequence`) for a
#: *different* antecedent (what an additional cost consumed), not reused
#: here on purpose.
_THAT_CREATURES_CHARACTERISTIC_RE = re.compile(
    r"^that creature'?s (?P<characteristic>power|toughness)$", re.IGNORECASE
)


def _event_subject_characteristic_expr(
    expr: str,
) -> Callable[["Game", "AbilityOnStack"], int] | None:
    """ "that creature's power"/"that creature's toughness", read off
    whatever CR 400.7 says "that creature" is - the ability's own target, if
    it named one, otherwise the triggering event's subject (CR 603.2) - at
    the moment the ability resolves (CR 608.2h fixes the value once, here).
    `Game.power_of`/`toughness_of`, `None`-safe the same way `_OBJECT_
    CHARACTERISTIC_RE`'s own reader already is for an object that has since
    left the battlefield or whose `*` characteristic-defining ability has
    nothing to compute from.
    """
    match = _THAT_CREATURES_CHARACTERISTIC_RE.fullmatch(expr.strip().rstrip("."))
    if match is None:
        return None
    wants_power = match.group("characteristic").lower() == "power"

    def read(game: "Game", ability: "AbilityOnStack") -> int:
        targeted = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        subject = targeted[0] if targeted else None
        if subject is None:
            event = ability.event
            if event is None or event.subject_id is None:
                return 0
            subject = game.find_by_id(event.subject_id)
        if subject is None:
            return 0
        value = game.power_of(subject) if wants_power else game.toughness_of(subject)
        return max(value, 0) if value is not None else 0

    return read


#: "its power"/"its toughness" on a sentence whose own subject is the
#: source - Armored Armadillo's "This creature gets +X/+0 until end of turn,
#: where X is its toughness." (CR 700.7's "this creature" is what "its"
#: points back to).
_SELF_SUBJECT_SENTENCE_RE = re.compile(r"^this (?:creature|permanent)\b", re.IGNORECASE)
_ITS_CHARACTERISTIC_RE = re.compile(r"^its (?P<characteristic>power|toughness)$", re.IGNORECASE)


def _source_characteristic_expr(
    expr: str, template: str
) -> Callable[["Game", "AbilityOnStack"], int] | None:
    """ "this creature's power" (Brambleguard Captain; War Machine, Legacy of
    Iron's own name already rewritten to "this permanent", CR 201.5) - the
    *source's* characteristic, not the target's - and "its toughness" when
    the pumped subject is the source itself (Armored Armadillo). Read once as
    the ability resolves (CR 608.2h), off the last known value if the source
    has left the battlefield."""
    stripped = expr.strip().rstrip(".")
    match = _SOURCE_CHARACTERISTIC_RE.fullmatch(stripped)
    if match is None and _SELF_SUBJECT_SENTENCE_RE.match(template.strip()):
        match = _ITS_CHARACTERISTIC_RE.fullmatch(stripped)
    if match is None:
        return None
    characteristic = match.group("characteristic").lower()

    def read(game: "Game", ability: "AbilityOnStack") -> int:
        return _source_characteristic(game, ability.source(game), characteristic)

    return read


@ABILITY_TEXT.rung("s36")
def _parse_where_x_is_continuous_effect(effect_text: str) -> AbilityEffect | None:
    """A continuous-effect sentence whose power and toughness are an X the
    ability defines in its own words - Jolrael, Voice of Zhalfir's symmetric
    "X/X" animation, and Yuriko, Hope from the Shadows's asymmetric "-X/-0"
    pump.

    The mass-pump path (`_parse_mass_pump_clause`) has read a trailing "where
    X is ..." since it was written, but only for the "creatures you control
    get +X/+X" subject; every other continuous-effect shape reached
    `machines/layers.py` through `_is_layer_effect_text`, which cannot read a
    literal "X" in place of a number. This is the same substitution for the
    general sentence: lift the definition out, resolve it once (CR 608.2h),
    and hand the resulting literal to the same `parsed_layer_effects` parser
    `_run_mass_pump` already uses.

    Returns `None` unless the substituted sentence is one that parser can
    actually read, so an unreadable animation stays unread rather than being
    half-applied.

    A sibling sentence beside the X-defined one - Aerid Konstrari's own "{6}:
    Create a Heartwood token. Then this creature gets +X/+0 until end of
    turn, where X is the number of artifacts you control." - is composed the
    same way `_compose_layer_effect_with_remainder_for_ability` composes an
    ordinary (non-X) layer sentence's own sibling, in the printed order (CR
    608.2c): `parsed_layer_effects` itself already silently skips a sentence
    outside its own territory (by design, for the battlefield sweep this
    same builder also serves), which used to mean the token-creation
    instruction never ran at all once this function's own gate started
    passing for the pump half beside it.
    """
    text = where_x_pump_text_normalised(effect_text.strip())
    match = _WHERE_X_IS_INLINE_RE.search(text)
    if match is None:
        return None
    template = (text[: match.start()] + text[match.end() :]).strip()
    controller_magnitude_expr = count_expression(match.group("expr"))
    event_magnitude_expr = (
        None
        if controller_magnitude_expr is not None
        else _event_subject_characteristic_expr(match.group("expr"))
        or _source_characteristic_expr(match.group("expr"), template)
    )
    if controller_magnitude_expr is None and event_magnitude_expr is None:
        return None
    if not _X_TOKEN_RE.search(template):
        return None
    if parsed_layer_effects(_X_TOKEN_RE.sub("1", template)) is None:
        return None
    sentences = _plain_resolution_sentences(template)
    pump_index = next((i for i, s in enumerate(sentences) if _X_TOKEN_RE.search(s)), None)
    if pump_index is None:
        return None
    pump_sentence = sentences[pump_index]
    if parsed_layer_effects(_X_TOKEN_RE.sub("1", pump_sentence)) is None:
        # The X sentence is no pump itself ("You gain X life and draw X cards,
        # where X is ..." beside a pump of its own): reading the whole text's
        # pump as this sentence's would drop the instruction (Camaraderie).
        return None
    if re.search(r"\bcounters?\b", pump_sentence, re.IGNORECASE):
        # "Distribute X +1/+1 counters among ..." (Undercity Upheaval) names an
        # X but modifies no power or toughness: placing counters is not a layer
        # pump, and `parsed_layer_effects` would skip the sentence it cannot
        # read and claim the rest.
        return None
    remainder_sentences = [s for i, s in enumerate(sentences) if i != pump_index]
    pump_first = pump_index == 0 or not remainder_sentences
    remainder_text = " ".join(remainder_sentences)
    remainder_effect = parse_mixed_effect(remainder_text) if remainder_text else None
    capped_by_x = up_to_x_targets(pump_sentence)

    def run_pump(game: "Game", ability: AbilityOnStack) -> None:
        # CR 608.2h: a source its own cost removed (Priest of the Haunted Edge's
        # "{T}, Sacrifice this creature: Target creature gets -X/-X ...") is
        # still the source of this ability; only a pump that is *of the source
        # itself* has nothing to act on once it has left the battlefield.
        source = ability.source_or_last_known(game)
        if source is None:
            return
        source_gone = ability.source(game) is None or source.zone is not Zone.BATTLEFIELD
        magnitude = (
            controller_magnitude_expr(game, ability.controller)
            if controller_magnitude_expr is not None
            else event_magnitude_expr(game, ability)  # type: ignore[misc]
        )
        literal = _X_TOKEN_RE.sub(str(magnitude), pump_sentence)
        builder = parsed_layer_effects(literal)
        if builder is None:
            continuous_effects(game).layer_notices.append(
                LayerNotice(source_id=source.id, source_name=source.name, text=literal)
            )
            return
        # Craterclaw Colossus's own "creatures you control gain trample and
        # get +X/+0 ..." names no target at all (CR 611.2c's fixed-at-
        # resolution group) - `_mass_creature_group_targets` is the same
        # resolver `_run_mass_pump` uses for the symmetric "+X/+X" shape,
        # tried first so a group subject is never mistaken for "this
        # creature" alone.
        group_targets = _mass_creature_group_targets(game, ability.controller, source.id, literal)
        if group_targets is not None:
            targets = group_targets
        else:
            profile = profile_for_text(literal)
            requires_target = profile.understood and bool(profile.requirements)
            if not requires_target and source_gone:
                return
            targets = game.resolve_card_targets(ability) if requires_target else [source]
        if capped_by_x:
            targets = targets[: max(magnitude, 0)]
        if not targets:
            # CR 115.6: "up to one target" legally choosing zero, or every
            # chosen target since gone illegal (CR 608.2b) - nothing to affect.
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        context = layer_context_for(game, game.controller_of(ability))
        for built in builder(source, timestamp, targets, context):
            if built.holds(game):
                store.add(built)

    def run_remainder(game: "Game", ability: AbilityOnStack) -> None:
        if remainder_effect is not None:
            remainder_effect(game, ability)
        elif remainder_text:
            game.layer_remainder_notices.append(
                LayerRemainderNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=remainder_text,
                )
            )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if pump_first:
            run_pump(game, ability)
            run_remainder(game, ability)
        else:
            run_remainder(game, ability)
            run_pump(game, ability)

    if remainder_text and remainder_effect is None:
        return _with_unparsed_remainder(effect, remainder_text)
    return effect


#: R0a-T7: Frontline Rush's own second mode, "Target creature gets +X/+X
#: until end of turn, where X is the number of creatures you control." - the
#: spell-side twin of `_parse_where_x_is_continuous_effect` immediately
#: above, for a *targeted* subject (a modal spell's own mode -
#: `resolve_modal_spell` swaps `spell.targets` to the chosen mode's own slice
#: before running this, so `game.resolve_card_targets` already reads the right
#: target) or a *mass* one (Roilmage's Trick's "Creatures your opponents control
#: get -X/-0 ...", fixed by `_mass_creature_group_targets` as the spell
#: resolves). The `_source_characteristic_expr`/`_event_subject_characteristic_
#: expr` magnitudes stay `AbilityOnStack`-only - an `AbilityOnStack`'s own
#: `.source`/`.event`, none of which a resolving spell's `CardState` carries.
#: `profile_for_text(literal)` reads whether the substituted sentence targets
#: at all, and `game.resolve_card_targets(spell)` is the identical CR 608.2b
#: recheck `create_continuous_effect`/`_create_continuous_effect_for_mode_text`
#: already give every other spell-side layer effect.
def _parse_where_x_is_continuous_effect_for_spell(effect_text: str) -> Effect | None:
    """The spell-side twin of `_parse_where_x_is_continuous_effect` - see the
    banner above."""
    text = where_x_pump_text_normalised(effect_text.strip())
    match = _WHERE_X_IS_INLINE_RE.search(text)
    if match is None:
        return None
    template = (text[: match.start()] + text[match.end() :]).strip()
    magnitude_expr = count_expression(match.group("expr"))
    if magnitude_expr is None:
        return None
    if not _X_TOKEN_RE.search(template):
        return None
    if parsed_layer_effects(_X_TOKEN_RE.sub("1", template)) is None:
        return None
    sentences = _plain_resolution_sentences(template)
    pump_index = next((i for i, s in enumerate(sentences) if _X_TOKEN_RE.search(s)), None)
    if pump_index is None:
        return None
    pump_sentence = sentences[pump_index]
    if parsed_layer_effects(_X_TOKEN_RE.sub("1", pump_sentence)) is None:
        # The X sentence is no pump itself ("You gain X life and draw X cards,
        # where X is ..." beside a pump of its own): reading the whole text's
        # pump as this sentence's would drop the instruction (Camaraderie).
        return None
    if re.search(r"\bcounters?\b", pump_sentence, re.IGNORECASE):
        # "Distribute X +1/+1 counters among ..." (Undercity Upheaval) names an
        # X but modifies no power or toughness: placing counters is not a layer
        # pump, and `parsed_layer_effects` would skip the sentence it cannot
        # read and claim the rest.
        return None
    remainder_sentences = [s for i, s in enumerate(sentences) if i != pump_index]
    pump_first = pump_index == 0 or not remainder_sentences
    remainder_text = " ".join(remainder_sentences)
    remainder_effect = parse_mixed_effect_for_spell(remainder_text) if remainder_text else None
    capped_by_x = up_to_x_targets(pump_sentence)

    def run_pump(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        magnitude = magnitude_expr(game, controller.username)
        literal = _X_TOKEN_RE.sub(str(magnitude), pump_sentence)
        builder = parsed_layer_effects(literal)
        if builder is None:
            continuous_effects(game).layer_notices.append(
                LayerNotice(source_id=spell.id, source_name=spell.card.name, text=literal)
            )
            return
        # A mass subject ("Creatures your opponents control get -X/-0 ...",
        # Roilmage's Trick) names no target: its group is fixed here (CR 611.2c)
        # by the same resolver the ability-side twin uses, tried first so a
        # group is never mistaken for the spell itself.
        group_targets = _mass_creature_group_targets(game, controller.username, spell.id, literal)
        if group_targets is not None:
            targets = group_targets
        else:
            profile = profile_for_text(literal)
            requires_target = profile.understood and bool(profile.requirements)
            targets = game.resolve_card_targets(spell) if requires_target else [spell]
        if capped_by_x:
            targets = targets[: max(magnitude, 0)]
        if not targets:
            # CR 115.6: "up to one target" legally choosing zero, or every
            # chosen target since gone illegal (CR 608.2b) - nothing to affect.
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        context = layer_context_for(game, controller)
        for built in builder(spell, timestamp, targets, context):
            if built.holds(game):
                store.add(built)

    def run_remainder(game: "Game", spell: CardState) -> None:
        if remainder_effect is not None:
            remainder_effect(game, spell)
        elif remainder_text:
            game.layer_remainder_notices.append(
                LayerRemainderNotice(
                    source_id=spell.id, source_name=spell.card.name, text=remainder_text
                )
            )

    def effect(game: "Game", spell: CardState) -> None:
        if pump_first:
            run_pump(game, spell)
            run_remainder(game, spell)
        else:
            run_remainder(game, spell)
            run_pump(game, spell)

    return effect


#: "Target creature gets +2/+2 until end of turn for each creature sacrificed
#: this way." (Vicious Betrayal), "... +1/+1 ... for each creature you
#: control." (Might of the Masses), "... -1/-1 ... for each Swamp you
#: control." (Defile) - a targeted pump scaled by a "for each" count, the
#: spell-side twin of `_MASS_PUMP_FOR_EACH_RE`'s mass pump. The count is
#: `_for_each_multiplier`'s, taken once as the spell resolves (CR 608.2h).
_TARGET_PUMP_FOR_EACH_RE = re.compile(
    r"^(?P<subject>(?:up to one )?target [^.]+?) gets? "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn "
    r"for each (?P<each>[^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s1", for_spell=FORWARD, before=["dispatch._parse_targeted_clause"])
def _parse_target_pump_for_each_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TARGET_PUMP_FOR_EACH_RE`'s shape on a resolving spell: the count is
    read once, multiplied into a literal "+N/+N until end of turn" sentence,
    and that sentence's own layer effect (CR 611.2, CR 613.4c) is applied to
    each target still legal (CR 608.2b)."""
    if not for_spell:
        return None
    match = _TARGET_PUMP_FOR_EACH_RE.fullmatch(clause.strip())
    if match is None:
        return None
    subject = match.group("subject")
    if not _targets_understood(subject):
        return None
    multiplier = _for_each_multiplier(match.group("each"))
    if multiplier is None:
        return None
    power, toughness = int(match.group("power")), int(match.group("toughness"))
    if parsed_layer_effects(f"{subject} gets {power:+d}/{toughness:+d} until end of turn.") is None:
        return None

    def effect(game: "Game", spell: "StackObject") -> None:
        assert isinstance(spell, CardState)
        _apply_for_each_pump(game, spell, subject, power, toughness, multiplier)

    return effect


def _subject_targets(game: "Game", spell: CardState, subject: str) -> list[CardState]:
    """The spell's resolved card targets that `subject`'s "you control" /
    "an opponent controls" / "you don't control" names. A spell with several
    target clauses carries one flat target list, so a clause names its own
    by who controls them (CR 608.2b already dropped the illegal ones)."""
    targets = game.resolve_card_targets(spell)
    lowered = subject.lower()
    caster = game.controller_of(spell).username
    if "you control" in lowered:
        return [t for t in targets if game.controller_of(t).username == caster]
    if "an opponent controls" in lowered or "you don't control" in lowered:
        return [t for t in targets if game.controller_of(t).username != caster]
    return targets


def _apply_for_each_pump(
    game: "Game",
    spell: CardState,
    subject: str,
    power: int,
    toughness: int,
    multiplier: Callable[["Game", str, str | None], int],
) -> None:
    """`power`/`toughness` times `multiplier`'s count, taken once as the spell
    resolves (CR 608.2h), as a layer effect (CR 611.2, CR 613.4c) on the first
    target `subject` names - or on each of them when it names no controller."""
    controller = game.controller_of(spell)
    count = multiplier(game, controller.username, str(spell.id))
    literal = f"{subject} gets {power * count:+d}/{toughness * count:+d} until end of turn."
    builder = parsed_layer_effects(literal)
    if builder is None:
        continuous_effects(game).layer_notices.append(
            LayerNotice(source_id=spell.id, source_name=spell.card.name, text=literal)
        )
        return
    targets = _subject_targets(game, spell, subject)
    if not targets:
        return
    store = continuous_effects(game)
    timestamp = store.tick()
    context = layer_context_for(game, controller)
    for built in builder(spell, timestamp, targets, context):
        if built.holds(game):
            store.add(built)


#: "Then that creature deals damage equal to its power to target creature an
#: opponent controls." - the bite that follows a pump (Spoils of the Hunt's
#: second sentence). "Then" is CR 608.2c's ordering word, never part of the
#: instruction.
_PUMP_BITE_RIDER_RE = re.compile(
    rf"^(?:then )?{_OBJECT_ANAPHOR} deals damage equal to its power to "
    r"(?P<phrase>.*\btarget\b.+)$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_pump_for_each_then_bite_text(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """ "Target creature you control gets +N/+M until end of turn for each
    `<count>`. Then that creature deals damage equal to its power to target
    creature an opponent controls." as one CR 608.2c instruction.

    Its own reader because the spell carries both creatures as one flat
    target list: the pump belongs to the one the caster controls and the bite
    lands on the other, which the generic anaphor pair (it reads the first
    sentence on every target) cannot tell apart. The count is read as the
    spell resolves (CR 608.2h) - a cast-time count such as the mana from a
    Treasure that paid for it (CR 601.2h) comes off the cast record - and the
    bite is read afterwards, from the creature's power as pumped."""
    if (
        not for_spell
        or "for each" not in text.lower()
        or "deals damage equal to" not in text.lower()
    ):
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(" ".join(text.split())))
    if len(sentences) != 2:
        return None
    pump = _TARGET_PUMP_FOR_EACH_RE.fullmatch(sentences[0].strip())
    rider = _PUMP_BITE_RIDER_RE.fullmatch(sentences[1].strip().rstrip("."))
    if pump is None or rider is None:
        return None
    subject = pump.group("subject")
    if subject.lower() != "target creature you control" or not _targets_understood(subject):
        return None
    if not _targets_understood(rider.group("phrase"), count_agnostic=True):
        return None
    multiplier = _for_each_multiplier(pump.group("each"))
    if multiplier is None:
        return None
    power, toughness = int(pump.group("power")), int(pump.group("toughness"))
    if parsed_layer_effects(f"{subject} gets {power:+d}/{toughness:+d} until end of turn.") is None:
        return None

    def effect(game: "Game", spell: "StackObject") -> None:
        assert isinstance(spell, CardState)
        _apply_for_each_pump(game, spell, subject, power, toughness, multiplier)
        _resolve_bite_damage(game, spell, "power")

    return [effect]


def _bounded_quality_matcher(
    quality: str | None, max_mv: str | None, mv_cmp: str = "less"
) -> Callable[[CardState], bool]:
    """`_quality_matcher`, ANDed with a mana value bound when the sentence
    names one - Ranger-Captain of Eos's ceiling ("with mana value 1 or less")
    or Conduit of Ruin's/Fierce Empath's floor ("with mana value 7/6 or
    greater").

    Mana value is CR 202.3's number, `Card.cmc` here. An **X** in this spot
    (Green Sun's Zenith, Fiend Artisan) never reaches this function at all:
    `_SEARCH_AND_PUT_RE`'s `max_mv` group is `\\d+` and does not match the
    letter X, so the whole clause fails to match and the search-clause parser
    returns `None` for it - the engine does not model the X binding (CR 107.3),
    and failing closed here is that gap staying closed rather than silently
    treating X as unbounded or as zero.
    """
    # CR 701.23d's bare "a card": no restriction to apply, so every card in
    # the library qualifies.
    base = (lambda _state: True) if quality is None else _quality_matcher(quality)
    if max_mv is None:
        return base
    bound = int(max_mv)
    if mv_cmp == "greater":

        def matches_floor(state: CardState) -> bool:
            return base(state) and state.mana_value >= bound

        return matches_floor

    def matches_ceiling(state: CardState) -> bool:
        return base(state) and state.mana_value <= bound

    return matches_ceiling


#: A life total changed by a counted amount: "Target player gains X life,
#: where X is the greatest power among creatures they control" (Inscription
#: of Abundance), "Target opponent loses life equal to the number of
#: creatures they control" (Villainous Wrath) - reached here with the target
#: subject already stripped by `_TARGET_PLAYER_OR_OPPONENT_VERB_RE`, so the
#: verb is third person - and the first-person "you gain X life, where X is
#: ..." / "you gain life equal to ..." of a resolving spell's own controller.
#: The amount is `amount_expression`'s.
_COUNTED_LIFE_CHANGE_RE = re.compile(
    r"^(?P<you>you )?(?P<verb>gain|gains|lose|loses) "
    r"(?:x life,? where x is (?P<where>.+)|life equal to (?P<equal>.+))$",
    re.IGNORECASE,
)


#: "its ..." / "that creature's ..." / "the sacrificed creature's ..." - an
#: amount read off an object named elsewhere in the sentence.
_ANAPHORIC_OBJECT_TERM_RE = re.compile(r"\b(?:its|that \w+'s|the \w+ \w+'s)\b", re.IGNORECASE)


#: "its mana value" / "that spell's mana value" - the spell a cast trigger names.
_CAST_SPELL_MANA_VALUE_RE = re.compile(r"^(?:its|that spell['’]s) mana value$", re.IGNORECASE)


def _parse_counted_life_change_clause(clause: str) -> ClauseEffect | None:
    """`_COUNTED_LIFE_CHANGE_RE`'s shape, or `None`.

    The clause's player is whoever the dispatcher runs it for: the resolving
    object's controller for "you gain ...", the chosen target for "target
    player gains ..." (`_TARGET_PLAYER_OR_OPPONENT_VERB_RE`). A third-person
    verb's "they control" is that player's board; a third-person clause whose
    amount says "you"/"your" names the *controller*, a different player this
    `ClauseEffect` is not handed, so it is refused (fails closed) rather than
    counted off the wrong board. A first-person clause cannot say "they".

    The amount is read once, as the clause is carried out (CR 608.2h), and a
    negative result is 0 (CR 107.1b, inside `amount_expression`).
    """
    match = _COUNTED_LIFE_CHANGE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    verb = match.group("verb").lower()
    third_person = verb.endswith("s")
    if third_person == bool(match.group("you")):
        return None
    expression = (match.group("where") or match.group("equal")).strip()
    if _ANAPHORIC_OBJECT_TERM_RE.search(expression) and not (
        event_terms_enabled() and _CAST_SPELL_MANA_VALUE_RE.fullmatch(expression)
    ):
        # "you gain life equal to its toughness" (Momentous Fall) names an
        # object an earlier clause chose - an anaphora (CR 608.2c) this
        # single-clause reader has no referent for, never this effect's own
        # source. Left to the readers that carry the referent.
        return None
    if third_person:
        if _YOU_OR_YOUR_RE.search(expression):
            return None
        for pattern, replacement in _TARGET_PLAYER_REFERENCES:
            expression = pattern.sub(replacement, expression)
    elif _THEY_CONTROL_RE.search(expression):
        return None
    reader = amount_expression(expression)
    if reader is None:
        return None
    gains = verb.startswith("gain")

    def counted_life_change(
        game: "Game", player: Player, source: str, source_id: str | None
    ) -> None:
        obj = game.find_by_id(UUID(source_id)) if source_id is not None else None
        amount = reader(game, player.username, obj, 0)
        if gains:
            game.gain_life(player, amount)
        else:
            game.lose_life(player, amount)

    return counted_life_change


#: "loses half their life, rounded up" (Dark Leo & Shredder's own combat
#: damage trigger, via `_parse_that_player_clause`'s "that player " strip) /
#: "loses half your life, rounded down" - CR 107.1a's own rounding-direction
#: requirement on a fractional result, read the identical `numbers.parse_half`
#: `_amount_term` (`machines/replacement.py`'s enters-with-counters position)
#: already reuses, except the thing being halved here is not a count at all
#: but the clause's own player's *current life total* (CR 119.1) - "their"/
#: "his"/"her"/"your" all read as "this clause's own player", never a
#: different one, so no anaphora resolution belongs here the way `_ANAPHORIC_
#: OBJECT_TERM_RE` refuses one for `_parse_counted_life_change_clause` above.
#: "gains half ... life" is not a printed shape in the pool and is
#: deliberately left unread rather than guessed at.
_HALF_LIFE_LOSS_RE = re.compile(
    r"^loses half (?:their|his|her|your) life,\s*rounded (?P<direction>up|down)\.?$",
    re.IGNORECASE,
)


def _parse_half_life_loss_clause(clause: str) -> ClauseEffect | None:
    """`_HALF_LIFE_LOSS_RE`'s shape, or `None`."""
    match = _HALF_LIFE_LOSS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    round_up = match.group("direction").lower() == "up"

    def half_life_loss(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        game.lose_life(player, halve(player.life, round_up=round_up))

    return half_life_loss


#: CR 608.2c's own counting instruction: "Count the number of `<expr>`."
#: Invincible Hymn's "Count the number of cards in your library. Your life
#: total becomes that number." and Touch of the Eternal's "count the number
#: of permanents you control. Your life total becomes that number." -
#: `Game.record_count` is the same "later text ... may modify the meaning of
#: earlier text" channel `that_many`'s own callers already write to (Jaya
#: Ballard's "Discard up to three cards, then draw that many cards"); "that
#: number" (`_amount_term`'s own new branch, above) is simply this file's
#: existing count channel under the noun a life total counts with instead of
#: a number of cards.
_COUNT_THE_NUMBER_OF_RE = re.compile(r"^count the number of (?P<expr>.+)$", re.IGNORECASE)


def _parse_count_the_number_of_clause(clause: str) -> ClauseEffect | None:
    """`_COUNT_THE_NUMBER_OF_RE`'s shape, or `None`."""
    match = _COUNT_THE_NUMBER_OF_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    reader = count_expression("the number of " + match.group("expr"))
    if reader is None:
        return None

    def count_the_number_of(
        game: "Game", player: Player, source: str, source_id: str | None
    ) -> None:
        game.record_count(reader(game, player.username))

    return count_the_number_of


#: "(other) `<qualifier>` you control[ with power/toughness/mana value `<n>`
#: or greater/less]" - Keruga, the Macrosage's "for each other permanent you
#: control with mana value 3 or greater" and Blessing of Frost's "for each
#: creature you control with power 4 or greater". `<qualifier>` is a card
#: type (`_singular_card_type`) or subtype (`_singular_subtype_for_count_
#: expression`) the same way `count_expression`'s own "number of `<qualifier>`
#: you control" reads it, plus the bare word "permanent(s)" for no type
#: filter at all (CR 110.1).
#: "... with a `<kind>` counter on it" narrows the count to permanents
#: carrying at least one counter of that kind (CR 122.1) - Armorcraft Judge's
#: "for each creature you control with a +1/+1 counter on it", Eluge, the
#: Shoreless Sea's "for each land you control with a flood counter on it".
#: A colour adjective in front of the noun (CR 105.1, CR 105.2c) - Breaker of
#: Creation's "for each colorless permanent you control".
_QUALIFIER_YOU_CONTROL_RE = re.compile(
    rf"^(?P<other>other )?(?:(?P<color>colorless|white|blue|black|red|green) )?"
    rf"(?P<qualifier>[a-z]+) you control"
    rf"(?: with (?P<attr>power|toughness|mana value) (?P<n>{COUNT}) or (?P<dir>greater|less)"
    r"| with (?:an?|one or more) (?P<counter>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|them))?$",
    re.IGNORECASE,
)


_COLOR_WORDS_FOR_COUNT: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _for_each_qualifier_count(phrase: str) -> Callable[["Game", str, str | None], int] | None:
    """`_QUALIFIER_YOU_CONTROL_RE`'s shape as a `(game, controller, source_id)
    -> int` reader, or `None` when `phrase` is not that shape.

    "other" (Keruga's own "other permanent") excludes the permanent whose id
    is `source_id` - CR 110.1's own object, not the ability - from the count;
    a static or triggered ability's `source_id` is the permanent it triggers
    from, the same one CR 608.2h already lets a "for each" count exclude by
    name when a card prints "other".
    """
    match = _QUALIFIER_YOU_CONTROL_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    qualifier_word = match.group("qualifier")
    universal = qualifier_word.lower() in ("permanent", "permanents")
    card_type = None if universal else _singular_card_type(qualifier_word)
    subtype = (
        None
        if universal or card_type is not None
        else _singular_subtype_for_count_expression(qualifier_word)
    )
    if not universal and card_type is None and subtype is None:
        return None
    other = match.group("other") is not None
    attr = match.group("attr")
    bound = parse_count(match.group("n")) if match.group("n") else None
    greater = match.group("dir") == "greater" if match.group("dir") else None
    counter = _counter_kind(match.group("counter")) if match.group("counter") else None
    color_word = (match.group("color") or "").lower()

    def count(game: "Game", controller: str, source_id: str | None) -> int:
        board = game.computed_board()
        total = 0
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if color_word == "colorless" and chars.colors:
                continue  # CR 105.2c: colorless is having no colour at all
            if (
                color_word
                and color_word != "colorless"
                and (_COLOR_WORDS_FOR_COUNT[color_word] not in chars.colors)
            ):
                continue
            if other and source_id is not None and str(permanent.id) == source_id:
                continue
            if not universal:
                if card_type is not None and card_type not in chars.types:
                    continue
                if card_type is None and not any(
                    word.lower() == subtype for word in chars.subtypes
                ):
                    continue
            if counter is not None and not permanent.counters[counter]:
                continue
            if attr is not None:
                if attr == "power":
                    value = chars.numeric_power
                elif attr == "toughness":
                    value = chars.numeric_toughness
                else:
                    value = permanent.mana_value
                if greater and value < bound:
                    continue
                if not greater and value > bound:
                    continue
            total += 1
        return total

    return count


#: "color among [other] `<quality>` you control" - Karn, Gilded Guardian's
#: own "draw a card for each color among other artifacts you control"
#: (CR 105.1's five colors, counted once each no matter how many qualifying
#: permanents share one), and Chromatic Orrery's own "color among permanents
#: you control" with no "other" at all - the ability's own source counts
#: toward the total there, unlike Karn's "other" excluding it.
_COLOR_AMONG_OTHER_QUALITY_RE = re.compile(
    r"^colors? among (?:(?P<other>other) )?(?P<qualifier>.+?) you control$", re.IGNORECASE
)


#: "for each `<kind>` counter on it"/"... on this `<noun>`" - Vexing Sphinx's
#: own dies trigger ("draw a card for each age counter on it") and Hangarback
#: Walker's registry-row twin ("create a token ... for each +1/+1 counter on
#: this creature") are the identical CR 122.1/122.2 read: the count is the
#: *source's* own counters, not anything the controller boards, so this
#: reads `source_id` off `game.find_by_id` rather than the `controller`
#: parameter `_for_each_qualifier_count`'s board scan uses. CR 603.10a's
#: "look back in time" for a dies trigger is what makes `last_known_counters`
#: the right half of the ternary once the source is gone from the
#: battlefield - `Counter`-keyed removal on a zone change (CR 122.2) empties
#: `.counters` itself by the time this ever runs, the same reason
#: `hangarback_dies` reads the identical ternary rather than `.counters`
#: alone.
_COUNTER_ON_IT_RE = re.compile(
    r"^(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on (?:it|this \w+)$", re.IGNORECASE
)


#: The Master of Lake-town's own "for each graveyard with seven or more
#: cards in it." - CR 400.1's graveyard zone, one per player, counted the
#: same board-wide way Obsidian Charmaw's "for each land your opponents
#: control that could produce {C}" already is, just over every player's
#: graveyard rather than a permanent quality.
_GRAVEYARDS_WITH_N_OR_MORE_CARDS_RE = re.compile(
    rf"^graveyards? with {count_pattern('count')} or more cards? in (?:it|them)$",
    re.IGNORECASE,
)


#: "(other) attacking `<qualifier>`" - Goblin Piledriver's own "for each other
#: attacking Goblin", Cenn's Heir's "for each other attacking Kithkin", Charging
#: Hooligan's "for each attacking creature". CR 508.1k makes an attacking
#: creature one chosen as an attacker and not yet removed from combat, whoever
#: controls it (the printing says no "you control"), so this walks
#: `Game.combat.attacker_ids`; "other" leaves out the ability's own source
#: (`source_id`), and CR 608.2h has the count taken once, as the effect applies.
_ATTACKING_QUALIFIER_RE = re.compile(
    r"^(?P<other>other )?attacking (?:(?P<color>colorless|white|blue|black|red|green) )?"
    r"(?P<qualifier>[a-z]+)$",
    re.IGNORECASE,
)


def _for_each_attacking_count(phrase: str) -> Callable[["Game", str, str | None], int] | None:
    """`_ATTACKING_QUALIFIER_RE`'s shape as a `(game, controller, source_id)
    -> int` reader, or `None` when `phrase` is not that shape."""
    match = _ATTACKING_QUALIFIER_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    qualifier_word = match.group("qualifier")
    universal = qualifier_word.lower() in ("permanent", "permanents")
    card_type = None if universal else _singular_card_type(qualifier_word)
    subtype = (
        None
        if universal or card_type is not None
        else _singular_subtype_for_count_expression(qualifier_word)
    )
    if not universal and card_type is None and subtype is None:
        return None
    other = match.group("other") is not None
    color_word = (match.group("color") or "").lower()

    def count(game: "Game", _controller: str, source_id: str | None) -> int:
        board = game.computed_board()
        total = 0
        for permanent in game.battlefield:
            if permanent.id not in game.combat.attacker_ids:
                continue
            if other and source_id is not None and str(permanent.id) == source_id:
                continue
            chars = board.of(permanent)
            if color_word == "colorless" and chars.colors:
                continue
            if (
                color_word
                and color_word != "colorless"
                and _COLOR_WORDS_FOR_COUNT[color_word] not in chars.colors
            ):
                continue
            if card_type is not None and card_type not in chars.types:
                continue
            if (
                card_type is None
                and subtype is not None
                and not any(word.lower() == subtype for word in chars.subtypes)
            ):
                continue
            total += 1
        return total

    return count


#: "`<qualifier>` target opponent controls" / "... target player controls" -
#: a "for each" count over the resolving object's own targeted player.
_TARGET_PLAYER_CONTROLS_TAIL_RE = re.compile(
    r"^(?P<inner>.+?) target (?:opponent|player) controls$", re.IGNORECASE
)


def _count_for_targeted_player(game: "Game", counted: Callable[["Game", str], int]) -> int:
    """`counted` for the player the resolving object targets, 0 when it
    targets none still legal (CR 608.2b)."""
    resolving = game.resolving
    if resolving is None:
        return 0
    for target in game.resolve_targets(resolving):
        if isinstance(target, Player):
            return counted(game, target.username)
    return 0


#: "for each mana from a Treasure that was spent to cast this spell" (Spoils
#: of the Hunt): CR 601.2h's spent mana, of which CR 106.3 keeps the source -
#: the part of it a Treasure produced, read off the spell's own cast record.
_TREASURE_MANA_SPENT_EACH_RE = re.compile(
    r"^mana from an? treasure (?:that was )?spent to cast (?:this spell|it)$", re.IGNORECASE
)


#: "1 life your opponents have lost this turn" - Rakdos, Lord of Riots's
#: cost reduction and Neheb, the Eternal's mana: one for each point of life
#: lost, summed over the controller's opponents.
_LIFE_LOST_BY_OPPONENTS_EACH_RE = re.compile(
    r"1 life (?:your opponents have|each opponent has|an opponent has) lost this turn",
    re.IGNORECASE,
)


def _for_each_multiplier(phrase: str) -> Callable[["Game", str, str | None], int] | None:
    """The count of an "N `<effect>` for each `<phrase>`" tail, as a
    `(game, controller, source_id) -> int` reader, or `None` when `phrase` is
    not one this wave can read.

    Tries, in order: Kaito, Bane of Nightmares' own "opponent who lost life
    this turn" (folded in here rather than pinned to its exact whole
    sentence, as `_DRAW_FOR_EACH_OPPONENT_WHO_LOST_LIFE_RE` used to);
    `_COUNTER_ON_IT_RE`'s own source-relative counter count;
    `_for_each_qualifier_count`'s "(other) `<qualifier>` you control[ with
    ...]"; and `count_expression`'s own "the number of `<qualifier>` you
    control" / "... cards in your graveyard/hand" shapes, for a card that
    spells the count out that way instead.
    """
    stripped = phrase.strip().rstrip(".")
    if _TREASURE_MANA_SPENT_EACH_RE.fullmatch(stripped):
        # Fixed as the spell was cast (CR 601.2h), never the Treasures still
        # on the board as it resolves.
        def count_treasure_mana_spent(game: "Game", _controller: str, source_id: str | None) -> int:
            # A spell is off the stack by the time its own effect runs, so the
            # resolving object is asked before the board.
            resolving = game.resolving
            if isinstance(resolving, CardState) and str(resolving.id) == source_id:
                return treasure_mana_spent_to_cast(game, resolving)
            source = None if source_id is None else game.find_by_id(UUID(source_id))
            return treasure_mana_spent_to_cast(game, source)

        return count_treasure_mana_spent
    if target_player := _TARGET_PLAYER_CONTROLS_TAIL_RE.fullmatch(stripped):
        # Kithkin Zealot's "for each black and/or red permanent target
        # opponent controls": counted on the targeted player's board (CR
        # 115.1 names them; CR 608.2h counts once, as the effect applies).
        counted = count_expression(f"{target_player.group('inner')} you control")
        if counted is None:
            return None
        return lambda game, _controller, _source_id: _count_for_targeted_player(game, counted)
    types_among = card_types_among_spells_cast_reader(stripped)
    if types_among is not None:
        # CR 608.2h: counted once, as the effect applies.
        return lambda game, controller, _source_id: len(types_among(game, controller))
    if "blocking" in stripped and (blocking := _CREATURES_BLOCKING_RE.fullmatch(stripped)):
        # "for each creature it's blocking" (Guardian of the Gateless) / "for
        # each creature blocking it" (Elvish Berserker): the combat count at
        # resolution (CR 608.2h), the ability's source being the creature.
        count_blockers = blocking.group("blocked_by_it") is not None

        def count_creatures_in_block(game: "Game", _controller: str, source_id: str | None) -> int:
            source = None if source_id is None else game.find_by_id(UUID(source_id))
            if source is None:
                return 0
            if count_blockers:
                return creatures_blocking(game, source)
            return creatures_blocked_by(game, source)

        return count_creatures_in_block
    if stripped.lower() == "creature that crewed it this turn":
        # Luxurious Locomotive: this turn's crew history for the source Vehicle.
        def count_creatures_that_crewed(
            game: "Game", _controller: str, source_id: str | None
        ) -> int:
            source = None if source_id is None else game.find_by_id(UUID(source_id))
            return 0 if source is None else creatures_that_crewed(game, source)

        return count_creatures_that_crewed
    if match := _COUNTER_ON_IT_RE.fullmatch(stripped):
        # No kind word ("for each counter on it", Kinsbaile Borderguard) counts
        # every counter on the object (CR 122.1).
        kind = _counter_kind(match.group("kind")) if match.group("kind") else None

        def count_counters_on_it(game: "Game", _controller: str, source_id: str | None) -> int:
            if source_id is None:
                return 0
            source = game.find_by_id(UUID(source_id))
            if source is None:
                return 0
            return counters_on_it_total(source, kind)

        return count_counters_on_it
    if match := _COLOR_AMONG_OTHER_QUALITY_RE.fullmatch(stripped):
        qualifier = match.group("qualifier").strip().lower()
        # CR 110.4a's own "permanent" umbrella (Chromatic Orrery's own
        # "permanents you control") is not one of CR 205.2a's fifteen card
        # types `_singular_card_type` reads - `is_permanent` is the same
        # check `_named_type_matcher`'s own bare "permanent" word already
        # uses elsewhere in this file.
        if qualifier in ("permanent", "permanents"):

            def qualifies(chars: Characteristics) -> bool:
                return bool(set(chars.types) & PERMANENT_TYPES)
        else:
            card_type = _singular_card_type(qualifier)
            if card_type is None:
                return None

            def qualifies(chars: Characteristics) -> bool:
                return card_type in chars.types

        excludes_source = match.group("other") is not None

        def count_colors_among_other(game: "Game", controller: str, source_id: str | None) -> int:
            # CR 105.2: the *number of colors* represented at least once
            # among the qualifying permanents, not a per-permanent count -
            # two artifacts sharing a color are one colour toward the
            # total, not two. "Other" (CR 601.2c's own reading elsewhere)
            # excludes this ability's own source, read off `source_id`
            # rather than the card's own name, so a token or an unnamed
            # source reads correctly too - Chromatic Orrery's own printing
            # has no "other" at all, so its own source counts.
            board = game.computed_board()
            colors: set[Color] = set()
            for permanent in game.battlefield:
                chars = board.of(permanent)
                if chars.controller != controller or not qualifies(chars):
                    continue
                if excludes_source and source_id is not None and str(permanent.id) == source_id:
                    continue
                colors.update(chars.colors)
            return len(colors)

        return count_colors_among_other
    if stripped.lower() == "opponent who lost life this turn":

        def count_opponents_who_lost_life(
            game: "Game", controller: str, source_id: str | None
        ) -> int:
            # CR 608.2h: the count is taken once, when the effect applies -
            # every card is drawn against this one number, not re-counted
            # between draws.
            return sum(
                1 for opponent in _opponents(game, controller) if opponent.life_lost_this_turn > 0
            )

        return count_opponents_who_lost_life
    if _LIFE_LOST_BY_OPPONENTS_EACH_RE.fullmatch(stripped):

        def count_life_opponents_lost(game: "Game", controller: str, source_id: str | None) -> int:
            # CR 119.3: every point of life the opponents lost this turn,
            # damage included (CR 120.3a), summed across them.
            return sum(opponent.life_lost_this_turn for opponent in _opponents(game, controller))

        return count_life_opponents_lost
    graveyard_size_match = _GRAVEYARDS_WITH_N_OR_MORE_CARDS_RE.fullmatch(stripped)
    if graveyard_size_match is not None:
        threshold = parse_count(graveyard_size_match.group("count"))
        if threshold is not None:

            def count_graveyards_at_least(
                game: "Game", _controller: str, _source_id: str | None
            ) -> int:
                # CR 400.1: every player's own graveyard is counted, not just
                # the ability's controller's - The Master of Lake-town's own
                # "for each graveyard with seven or more cards in it" says
                # nothing about whose.
                return sum(1 for player in game.players if len(player.graveyard) >= threshold)

            return count_graveyards_at_least
    qualifier_reader = _for_each_qualifier_count(stripped) or _for_each_attacking_count(stripped)
    if qualifier_reader is not None:
        return qualifier_reader
    if this_way := _COUNT_THIS_WAY_RE.fullmatch(f"number of {stripped}"):
        # "for each artifact sacrificed this way" (Radiant Lotus).
        verb = this_way.group("verb").lower()
        return lambda game, _controller, _source_id: counted_this_way(game, verb)
    generic = count_expression(stripped)
    if generic is not None:
        return lambda game, controller, _source_id: generic(game, controller)
    from ..ep02_r1_counted_permanents import counted_group_reader

    return counted_group_reader(stripped) or _for_each_described_count(stripped)


#: "`<description>` you control", the control clause anywhere in it -
#: Overgrown Battlement's "creature you control with defender", Leafkin
#: Avenger's "creature with power 4 or greater you control", Cabal
#: Stronghold's "basic Swamp you control". The rest is read with the
#: target grammar (`targeting.permanent_description`), so a "for each" count
#: and a target restriction can never disagree about what a word means.
_DESCRIBED_CONTROL_CLAUSE_RE = re.compile(
    r"\s+(?P<whose>you control|your opponents control|on the battlefield)(?=\s|$)",
    re.IGNORECASE,
)
#: CR 201.2's name, trailing a description - Powerstone Shard's "artifact you
#: control named Powerstone Shard".
_DESCRIBED_NAMED_RE = re.compile(r"^(?P<rest>.+?)\s+named\s+(?P<name>[A-Z][\w',-]*(?: [\w',-]+)*)$")
#: "`<quality>` card(s) in your graveyard" whose quality is more than one
#: word - Crypt of Agadeem's "black creature card in your graveyard"; read
#: with the search grammar's `_quality_matcher` (a colour word qualifying a
#: type word).
_DESCRIBED_CARDS_IN_YOUR_GRAVEYARD_RE = re.compile(
    r"^(?P<quality>.+?) cards? in your graveyard$", re.IGNORECASE
)


def _for_each_described_count(phrase: str) -> Callable[["Game", str, str | None], int] | None:
    """The "for each `<description>`" counts the narrower readers above do
    not reach, as a `(game, controller, source_id) -> int` reader, or `None`
    when any word of the description is left unread.

    - **On the battlefield**: one control clause ("you control" / "your
      opponents control", or "on the battlefield" for everyone's) wherever
      it sits, an optional trailing "named
      `<name>`" (CR 201.2a: same name), and a permanent description the target
      grammar reads in full - supertypes (CR 205.4a's "basic"), colours,
      keywords (CR 702.3a's defender), and power/toughness/mana value
      comparisons. Read off the computed board (CR 613.5).
    - **In your graveyard**: a card description `_quality_matcher` reads in
      full - a colour word qualifying a type word.

    CR 608.2h: whoever calls this counts once, as the effect applies.
    """
    # "the number of creatures you control with defender" (Axebane Guardian's
    # "where X is") is the identical count spelled as a number.
    text = re.sub(r"^(?:the )?number of ", "", " ".join(phrase.split()), flags=re.IGNORECASE)
    graveyard = _DESCRIBED_CARDS_IN_YOUR_GRAVEYARD_RE.fullmatch(text)
    if graveyard is not None:
        quality = graveyard.group("quality")
        if not _card_description_is_readable(quality):
            return None
        matches_card = _quality_matcher(quality)

        def count_described_cards(game: "Game", controller: str, _source_id: str | None) -> int:
            return sum(1 for card in game.player(controller).graveyard if matches_card(card))

        return count_described_cards
    clauses = list(_DESCRIBED_CONTROL_CLAUSE_RE.finditer(text))
    if len(clauses) != 1:
        return None
    clause = clauses[0]
    whose = clause.group("whose").lower()
    opponents = whose == "your opponents control"
    # Priest of Titania's "Elf on the battlefield": no control clause at all,
    # so every player's permanents count.
    anyone = whose == "on the battlefield"
    description = f"{text[: clause.start()]}{text[clause.end() :]}".strip()
    name: str | None = None
    if named := _DESCRIBED_NAMED_RE.fullmatch(description):
        description, name = named.group("rest"), named.group("name")
    if description.lower() in ("permanent", "permanents"):
        requirement = None
    else:
        requirement = permanent_description(description)
        if requirement is None:
            return None

    def count_described(game: "Game", controller: str, _source_id: str | None) -> int:
        board = game.computed_board()
        total = 0
        for permanent in game.battlefield:
            chars = board.of(permanent)
            owner = chars.controller
            if opponents and (owner is None or owner == controller):
                continue
            if not opponents and not anyone and owner != controller:
                continue
            if name is not None and chars.name != name:
                continue
            if requirement is not None and requirement.rejects(permanent, controller, game):
                continue
            total += 1
        return total

    return count_described


def _amount_reader(n_text: str, where_text: str | None) -> Callable[["Game", str], int] | None:
    """`n_text` is one of `numbers.AMOUNT`'s own captures ("2", "two", "x");
    `where_text` is the expression after "where X is", or `None` when the
    card prints no where-clause. Returns a `(game, controller) -> int` reader
    of the count, or `None` when `n_text` is CR 107.3a's X with nothing
    readable to determine it by.

    `n_text` alone (no where-clause) is not CR 107.3a's X *announced* at
    cast: `Game.scry`/`Game.surveil`'s own callers here are triggered and
    static abilities, which carry no announced X for this reader to reach -
    only a card that spells its own X out with "where X is `<expr>`" (Oath of
    Jace's "scry X, where X is the number of planeswalkers you control")
    gives this anything to evaluate.
    """
    count = parse_count(n_text)
    if count is not None:
        return lambda _game, _controller: count
    if where_text is None:
        return None
    evaluator = count_expression(where_text)
    if evaluator is None:
        return None
    return evaluator


#: "Distribute `<n>` `<kind>` counters among `<count-phrase>` `<quality>` you
#: control." with no word "target" at all - Awaken the Maelstrom's own "one,
#: two, or three creatures you control" and Blessing of Frost's "any number
#: of creatures you control" (both real, Modern/Pioneer-legal printings of
#: the identical untargeted shape). CR 601.2d's own division-by-announcement
#: is about targets specifically ("among one or more **targets**"), so a
#: phrase with no "target" in it names a CR 608.2d choice made as the
#: ability resolves instead - which creatures, then how many each gets.
_UP_TO_WORD = r"[a-z]+"
_DISTRIBUTE_UNTARGETED_COUNT_PHRASE_RE = re.compile(
    rf"^(?:any number of|(?:{_UP_TO_WORD}(?:,\s*{_UP_TO_WORD})*,?\s+or\s+)?"
    rf"(?P<max>{_UP_TO_WORD}))$",
    re.IGNORECASE,
)


def _max_untargeted_recipients(count_phrase: str) -> int | None:
    """The ceiling `_DISTRIBUTE_UNTARGETED_COUNT_PHRASE_RE` names, or `None`
    for "any number of" (uncapped by anything but how many creatures the
    controller actually has). "one, two, or three" and every other ascending
    enumerated list names its own maximum last, so only the final word is
    read for a number - `parse_count` on the whole phrase would choke on the
    commas."""
    match = _DISTRIBUTE_UNTARGETED_COUNT_PHRASE_RE.fullmatch(count_phrase.strip())
    if match is None:
        return None
    max_word = match.group("max")
    if max_word is None:
        return None  # "any number of"
    return parse_count(max_word)


#: A trigger condition whose only number is its subject's counters - Shadow
#: Urchin's "a creature you control with one or more counters on it dies".
_CONDITION_SUBJECT_COUNTERS_RE = re.compile(
    r"\bwith (?:a|an|one or more) (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on it\b",
    re.IGNORECASE,
)


def _that_many_counters_on_event_subject(game: "Game", resolving: "AbilityOnStack") -> int | None:
    """ "that many" after a trigger condition "... with one or more
    [`<kind>`] counters on it ..." - the number of those counters on the
    event's subject, read as it last existed if it has left the battlefield
    (CR 603.10a). `None` when the condition names no such counters."""
    ability = resolving.ability
    if not isinstance(ability, TriggeredAbility) or resolving.event is None:
        return None
    match = _CONDITION_SUBJECT_COUNTERS_RE.search(ability.condition)
    if match is None or resolving.event.subject_id is None:
        return None
    subject = game.find_by_id(resolving.event.subject_id)
    if not isinstance(subject, CardState):
        return None
    counters = subject.counters if subject.zone is Zone.BATTLEFIELD else subject.last_known_counters
    if match.group("kind") is None:
        return sum(counters.counts.values())
    return counters[_counter_kind(match.group("kind"))]


def that_many(game: "Game", stack_object: "StackObject | None" = None) -> int | None:
    """The number a "that many"/"that much" points back at - the one reader
    of the number sweep's count channel (group 0b).

    In order:

    - the count the resolving object's own latest counted instruction
      recorded (`Game.recorded_count`) - CR 608.2c: "The controller of the
      spell or ability follows its instructions in the order written ...
      later text on the card may modify the meaning of earlier text", so
      Jaya Ballard's "Discard up to three cards, then draw that many cards"
      draws what the discard actually moved;
    - else the amount the triggering event carried (`GameEvent.amount`) -
      Marauding Mako's cards discarded, Photon's combat damage, The Earth
      King's qualifying attackers - CR 603.2c's one event, however many
      occurrences it contains.

    `stack_object` defaults to `Game.resolving`. `None` when neither is
    there, so every caller fails closed (`_that_many_or_notice`) instead of
    reading zero as though nothing happened.
    """
    recorded = game.recorded_count()
    if recorded is not None:
        return recorded
    resolving = stack_object if stack_object is not None else game.resolving
    if isinstance(resolving, AbilityOnStack) and resolving.event is not None:
        if resolving.event.amount is None:
            counted = _that_many_counters_on_event_subject(game, resolving)
            if counted is not None:
                return counted
        return resolving.event.amount
    if (
        isinstance(resolving, AbilityOnStack)
        and isinstance(resolving.ability, ActivatedAbility)
        and resolving.x_value is not None
        and removes_announced_number_of_counters(resolving.ability.cost)
    ):
        # The Astonishing Ant-Man's "Remove any number of +1/+1 counters ...:
        # Create that many ..." and Geistflame Reservoir's "... that much
        # damage": the count removed as the cost was paid, announced as the
        # ability was activated (CR 107.3a, CR 602.2b).
        return resolving.x_value
    return None


def _paid_for_cast_cost(game: "Game", verb: str) -> list[int] | None:
    """The positions in the resolving spell's `CastRecord.additional_cost_
    cards` that its additional cost paid with `verb` (CR 118.8, 601.2h) -
    `None` when the resolving object is not a spell, or its cost paid nothing
    with that verb, so the caller falls back to its other readings."""
    resolving = game.resolving
    kind = _THIS_WAY_VERB_KINDS.get(verb)
    if not isinstance(resolving, CardState) or kind is None:
        return None
    record = game.cast_record_of(resolving)
    if record is None:
        return None
    positions = [index for index, paid in enumerate(record.additional_cost_kinds) if paid == kind]
    return positions or None


def counted_this_way(game: "Game", verb: str) -> int:
    """ "`<noun>` `<verb>` this way" - how many objects the resolving
    object moved with that verb: first its own activation cost's (CR 602.2b
    pays the cost before the ability exists, so the paid objects are carried
    on it - `AbilityOnStack.cost_exiled_card_ids` /
    `cost_sacrificed_card_ids`), or a spell's own additional cost's (CR
    601.2h: paid before it was cast - Burn at the Stake's "the number of
    creatures tapped this way", Vicious Betrayal's "for each creature
    sacrificed this way", off `CastRecord.additional_cost_kinds`), else the
    count its own latest instruction recorded (`Game.recorded_count`, CR
    608.2c). Nothing moved is zero, not an unknown: "the number of cards
    exiled this way" with none exiled is 0.
    """
    resolving = game.resolving
    if isinstance(resolving, AbilityOnStack):
        paid = {
            "exiled": resolving.cost_exiled_card_ids,
            "sacrificed": resolving.cost_sacrificed_card_ids,
        }.get(verb, ())
        if paid:
            return len(paid)
    cast_paid = _paid_for_cast_cost(game, verb)
    if cast_paid is not None:
        return len(cast_paid)
    recorded = game.recorded_count()
    return recorded if recorded is not None else 0


def total_of_paid_for_cost(game: "Game", verb: str, stat: str) -> int:
    """ "the total `<stat>` of the `<verb>` `<noun>`" - the sum, over what
    the resolving spell's additional cost paid with `verb`, of each object's
    power or mana value as the record snapshotted it when the cost was paid
    (CR 608.2h's last known information: the sacrificed creatures are gone,
    a sacrificed token has ceased to exist, CR 704.5d). Nothing paid is 0
    (CR 107.2)."""
    positions = _paid_for_cast_cost(game, verb)
    if not positions:
        return 0
    resolving = game.resolving
    assert isinstance(resolving, CardState)
    record = game.cast_record_of(resolving)
    assert record is not None
    values = (
        record.additional_cost_powers if stat == "power" else record.additional_cost_mana_values
    )
    return max(
        int(sum(values[index] for index in positions if index < len(values))),
        0,
    )


def _that_many_or_notice(
    game: "Game",
    text: str,
    *,
    source_id: "UUID | str | None",
    source_name: str,
    stack_object: "StackObject | None" = None,
) -> int | None:
    """`that_many`, or - when it has nothing to read - an
    `UnmodeledTriggerEffectNotice` naming `text` and `None`, so the clause
    moves nothing rather than a guessed number."""
    count = that_many(game, stack_object)
    if count is None:
        game.unmodeled_trigger_effect_notices.append(
            UnmodeledTriggerEffectNotice(
                source_id=source_id, source_name=source_name, text=text.strip()
            )
        )
    return count


#: Shatterskull Smashing: "deals X damage divided as you choose among up to
#: two target creatures and/or planeswalkers. If X is 6 or more, [Name] deals
#: twice X damage divided as you choose among them instead." Read whole, like
#: `_UNDERGROWTH_PUMP_AND_FIGHT_RE` above: "them" in the second sentence is
#: anaphoric (CR 400.7) for whatever the first sentence's target phrase named,
#: one CR 608.2c instruction across two sentences rather than something
#: `split_effect_clauses` could cut apart and still read. Tried on the
#: *unsubstituted* text (the literal word "x", never a caster's chosen
#: number) - `machines/targeting.py`'s own `Division.doubled_if_x_at_least`
#: reads the identical threshold for CR 601.2d's announcement, so the two
#: stay in lockstep without either one hard-coding the other's answer.
_X_DAMAGE_DIVIDED_DOUBLED_RE = re.compile(
    r"^.*\bdeals? x damage divided as you choose among "
    r"(?P<phrase>up to \S+ target[^.]+)\.\s*"
    r"if x is (?P<threshold>\d+) or more,.*deals twice x damage divided as you choose "
    r"among them instead\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s16")
def _parse_x_damage_divided_and_doubled_clause(text: str) -> Effect | None:
    """Shatterskull Smashing's own shape - see `_X_DAMAGE_DIVIDED_DOUBLED_RE`.

    X is read at resolution off `Game.cast_record` (CR 107.3a), doubled if it
    meets the printed threshold, and the total is paid out through the same
    `_deal_divided_damage_shares` `deal_divided_damage` uses - the caster's
    real CR 601.2d announcement (`spell.division`) if there is one, an even
    split otherwise.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _X_DAMAGE_DIVIDED_DOUBLED_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    threshold = int(match.group("threshold"))

    def effect(game: "Game", spell: CardState) -> None:
        x_value = game.cast_record(spell).x_value
        total = 2 * x_value if x_value >= threshold else x_value
        _deal_divided_damage_shares(game, spell, total)

    return effect


# --------------------------------------------------------------------------
# Damage whose amount is an expression `_DAMAGE_TARGET_RE`'s plain count
# cannot carry: arithmetic over X (Crackle with Power's "five times X",
# Crater's Claws's "X plus 2"), an "equal to <expr>" dealt to "each of" a
# group of targets (Nahiri's Wrath), and an "equal to <expr>" that counts
# what the *targeted player* has (Chaotic Backlash's "they control").
# --------------------------------------------------------------------------

#: "deals five times X damage to each of up to X targets" (Crackle with
#: Power), "deals X plus 2 damage to any target" (Crater's Claws's ferocious
#: alternative), "deals twice X damage to target creature". `expr` must carry
#: one of CR 107.1's operators - a bare count or X stays with
#: `_DAMAGE_TARGET_RE`.
_EXPRESSION_DAMAGE_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? "
    rf"(?P<expr>(?:{MULTIPLIER} )?(?:x|{COUNT})(?: (?:plus|minus) (?:x|{COUNT}))*) "
    r"damage to (?P<phrase>any target|.*?\btargets?\b.*?)\.?$",
    re.IGNORECASE,
)
#: "deals damage equal to `<expr>` to each of up to X target creatures and/or
#: planeswalkers" (Nahiri's Wrath): every target chosen takes the whole
#: amount, which "each of" says outright.
_EQUAL_TO_DAMAGE_TO_EACH_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? damage equal to (?P<expr>[^.]+?) to "
    r"each of (?P<phrase>[^.]*?\btargets?\b[^.]*?)\.?$",
    re.IGNORECASE,
)
#: "deals damage to target player equal to twice the number of white and/or
#: blue permanents they control" (Chaotic Backlash), "deals damage to target
#: player equal to the number of cards in that player's hand" (Sudden
#: Impact): `expr` names the targeted player ("they", "their", "that
#: player"), never the caster.
_DAMAGE_TO_PLAYER_EQUAL_TO_THEIR_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? damage to "
    r"(?P<phrase>target (?:player|opponent)) equal to (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)
#: "deals damage to target creature equal to the number of nonbasic lands that
#: creature's controller controls" (Weight of Spires): the amount counts what
#: the *target's controller* has, read for each target as the spell resolves.
_DAMAGE_TO_PERMANENT_EQUAL_TO_ITS_CONTROLLERS_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? damage to "
    r"(?P<phrase>[^.]*?\btargets?\b[^.]*?) equal to (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)
#: The targeted player's own words inside `_DAMAGE_TO_PLAYER_EQUAL_TO_THEIR_RE`
#: 's `expr`, rewritten to the second person `count_expression` reads, then
#: evaluated for that player (CR 608.2h).
_TARGET_PLAYER_REFERENCES = (
    (
        re.compile(r"\b(?:they|that (?:player|opponent)) controls?\b", re.IGNORECASE),
        "you control",
    ),
    # "the number of cards they've drawn this turn" (Cerebral Vortex), "the
    # number of cards that player has drawn this turn" (Molten Psyche).
    (re.compile(r"\b(?:they've|they have|that player has)\b", re.IGNORECASE), "you've"),
    # "the damage already dealt to that player this turn" (Final Punishment).
    (
        re.compile(r"\bdealt to (?:that player|them|target (?:player|opponent))\b", re.IGNORECASE),
        "dealt to you",
    ),
    (re.compile(r"\b(?:their|that (?:player|opponent)'s)\b", re.IGNORECASE), "your"),
)
#: "the number of nonbasic lands that creature's controller controls" (Weight of
#: Spires): the controller of the creature the spell targets, so the same
#: second-person rewrite for each target's own controller.
_TARGET_CONTROLLER_REFERENCES = (
    (
        re.compile(
            r"\b(?:that|the targeted) (?:creature|permanent|planeswalker|battle)'s controller "
            r"controls\b",
            re.IGNORECASE,
        ),
        "you control",
    ),
)
#: A subject that is itself chosen - "Target creature you control deals
#: damage equal to its power to each of ..." (bite) - is not the spell
#: dealing damage, and is left to the readers built for it.
_TARGETED_SUBJECT_RE = re.compile(r"\btarget\b|\bthat creature\b", re.IGNORECASE)


#: "`<it|this permanent>` deals damage equal to `<expr>` to each `<type>`
#: [and each `<type>`]." - non-targeted, simultaneous damage (CR 120.1,
#: CR 608.2c) whose amount is an `amount_expression` read once as the ability
#: resolves (CR 608.2h) off the source's last known information (CR 603.10a).
_EQUAL_TO_DAMAGE_TO_EACH_GROUP_RE = re.compile(
    r"^(?:it|this (?:creature|permanent|artifact)) deals damage equal to (?P<expr>[^.]+?) to "
    r"each (?:non-?(?P<non>[a-z]+) )?(?P<groups>[a-z]+(?: and each [a-z]+)*)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s35", for_spell=FORWARD)
def _parse_expression_damage_to_each_group_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EQUAL_TO_DAMAGE_TO_EACH_GROUP_RE`'s shape. Ability-only: the subject is
    the ability's own source, which a spell's "it" never is."""
    if for_spell or "deals damage equal to" not in clause.lower():
        return None
    match = _EQUAL_TO_DAMAGE_TO_EACH_GROUP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None
    types: set[Type] = set()
    for word in re.split(r"\s+and each\s+", match.group("groups")):
        card_type = _singular_card_type(word)
        if card_type is None:
            return None
        types.add(card_type)
    # "each non-Giant creature" (Thundercloud Shaman): the group minus anything
    # of that card type or creature type, read off the computed board.
    excluded_word = match.group("non")
    excluded_type = None if excluded_word is None else _singular_card_type(excluded_word)
    excluded_subtype = (
        None
        if excluded_word is None or excluded_type is not None
        else _singular_subtype_for_count_expression(excluded_word + "s")
        or _singular_subtype_for_count_expression(excluded_word)
    )
    if excluded_word is not None and excluded_type is None and excluded_subtype is None:
        return None

    def spared(chars: Characteristics) -> bool:
        if excluded_type is not None:
            return excluded_type in chars.types
        return excluded_subtype is not None and any(
            word.lower() == excluded_subtype for word in chars.subtypes
        )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source_or_last_known(game)
        amount = reader(game, stack_object.controller, source, stack_object.x_value or 0)
        board = game.computed_board()
        recipients = [
            permanent
            for permanent in list(game.battlefield)
            if types & set(board.of(permanent).types) and not spared(board.of(permanent))
        ]
        for permanent in recipients:
            game.deal_damage(permanent, amount, source=source)

    return effect


def _announced_x(game: "Game", stack_object: "StackObject") -> int:
    """CR 107.3a's X of the resolving spell or ability (0 when none was)."""
    if isinstance(stack_object, AbilityOnStack):
        return stack_object.x_value or 0
    return game.cast_record(stack_object).x_value or 0


def _deal_expression_damage(
    reader: AmountReader, *, for_target_player: bool = False
) -> TargetedClause:
    """Each target still legal (CR 608.2b) is dealt `reader`'s amount, read
    as the effect applies (CR 608.2h) with the resolving object's own X; the
    spell itself, or an ability's source, deals it (CR 120.1). With
    `for_target_player`, the amount is read for the targeted player (or the
    controller of the targeted permanent) rather than the caster."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        x_value = _announced_x(game, stack_object)
        if isinstance(stack_object, AbilityOnStack):
            source = stack_object.source_or_last_known(game)
        else:
            source = stack_object
        shared = None if for_target_player else max(reader(game, controller, source, x_value), 0)
        for target in game.resolve_targets(stack_object):
            amount = shared
            if amount is None:
                # A player is counted for themselves, a permanent for the
                # player who controls it (CR 608.2h: as the spell resolves).
                whose = (
                    target.username
                    if isinstance(target, Player)
                    else game.controller_of(target).username
                )
                amount = max(reader(game, whose, source, x_value), 0)
            game.deal_damage(target, amount, source=source)

    return effect


@MIXED_CLAUSE.rung("s1", for_spell=FORWARD, before=["dispatch._parse_targeted_clause"])
def _parse_expression_amount_damage_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EXPRESSION_DAMAGE_RE`, `_EQUAL_TO_DAMAGE_TO_EACH_RE` and
    `_DAMAGE_TO_PLAYER_EQUAL_TO_THEIR_RE`: damage whose amount is an
    `amount_expression` the plain damage readers do not carry. Every target
    takes the whole amount (CR 115.6's "up to" allows zero of them); "up to
    X" is bounded by the X announced (CR 601.2c), which the targeting reader
    reads off the announced text."""
    text = clause.strip()
    lowered = text.lower()
    if "damage" not in lowered or "target" not in lowered:  # every shape prints both
        return None
    for_target_player = False
    match = _EXPRESSION_DAMAGE_RE.fullmatch(text)
    if match is not None and not (
        re.search(r"\b(?:plus|minus|times|twice|thrice)\b", match.group("expr"), re.IGNORECASE)
        # A spell's bare, caster-announced X (CR 107.3a) with no definition
        # of its own: read off the cast record here rather than as
        # `_DAMAGE_TARGET_RE`'s fixed count, which has no number for it -
        # Crater's Claws's base "deals X damage to any target", read beside
        # its ferocious alternative.
        or (
            for_spell
            and match.group("expr").strip().lower() == "x"
            and not re.search(r"\b(?:where|for each)\b", match.group("phrase"), re.IGNORECASE)
        )
    ):
        match = None
    if match is None:
        match = _EQUAL_TO_DAMAGE_TO_EACH_RE.fullmatch(text)
    if match is None:
        match = _DAMAGE_TO_PLAYER_EQUAL_TO_THEIR_RE.fullmatch(text)
        references = _TARGET_PLAYER_REFERENCES
        if match is None:
            match = _DAMAGE_TO_PERMANENT_EQUAL_TO_ITS_CONTROLLERS_RE.fullmatch(text)
            references = _TARGET_CONTROLLER_REFERENCES
        if match is None:
            return None
        expr = match.group("expr")
        rewritten = expr
        for pattern, replacement in references:
            rewritten = pattern.sub(replacement, rewritten)
        if rewritten == expr:
            return None
        for_target_player = True
        reader = amount_expression(rewritten)
    else:
        reader = amount_expression(match.group("expr"))
    subject = re.split(r"\bdeals?\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    if reader is None or _TARGETED_SUBJECT_RE.search(subject):
        return None
    if not _targets_understood(
        match.group("phrase"), count_agnostic=True, allow_player_targets=True
    ):
        return None
    return _deal_expression_damage(reader, for_target_player=for_target_player)


#: "`<src>` deals damage to each player equal to the number of nonbasic lands
#: that player controls." (Sunspine Lynx) - each player's own count, every
#: amount fixed before the first is dealt (CR 608.2h, CR 120.3a), the rewrite
#: to the second person the same `_TARGET_PLAYER_REFERENCES` gives a targeted
#: player's.
_DAMAGE_EACH_PLAYER_EQUAL_TO_THEIRS_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? damage to each (?P<who>player|opponent) equal to "
    r"(?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_damage_each_player_equal_to_their_count_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DAMAGE_EACH_PLAYER_EQUAL_TO_THEIRS_RE`'s shape, spell or ability."""
    if "damage to each" not in clause.lower():
        return None
    match = _DAMAGE_EACH_PLAYER_EQUAL_TO_THEIRS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    # A leading condition ("Metalcraft - If you control three or more
    # artifacts, Molten Psyche deals ...") belongs to the conditional reader,
    # which hands this rung only the sentence after the comma (CR 608.2c).
    subject = re.split(r"\bdeals?\b", clause, maxsplit=1, flags=re.IGNORECASE)[0]
    if re.search(r"\bif\b|,", subject, re.IGNORECASE):
        return None
    expr = match.group("expr")
    rewritten = expr
    for pattern, replacement in _TARGET_PLAYER_REFERENCES:
        rewritten = pattern.sub(replacement, rewritten)
    # Each recipient's own count when the amount names them ("that player
    # controls"); otherwise one count of the caster's (Sorcerer Class's "the
    # number of instant and sorcery spells you've cast this turn"), fixed once
    # as the effect applies (CR 608.2h) and dealt to every recipient alike.
    per_player = rewritten != expr
    reader = amount_expression(rewritten)
    if reader is None:
        return None
    opponents_only = match.group("who").lower() == "opponent"
    names_that_spell = subject.strip().lower() == "that spell"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = _resolving_source(game, stack_object)
        if names_that_spell and isinstance(stack_object, AbilityOnStack):
            # "that spell" is the spell the trigger watched (CR 603.2), as it
            # last existed once it has left the stack (CR 608.2h).
            watched = (
                None
                if stack_object.event is None or stack_object.event.subject_id is None
                else game.find_by_id(stack_object.event.subject_id)
            )
            if isinstance(watched, CardState):
                source = watched
        controller = game.controller_of(stack_object).username
        shared = None if per_player else max(reader(game, controller, source, 0), 0)
        deals = [
            (
                source,
                player,
                max(reader(game, player.username, source, 0), 0) if shared is None else shared,
            )
            for player in game.players_in_game
            if not opponents_only or player.username != controller
        ]
        _deal_all(game, deals)

    return effect


@ABILITY_TEXT.rung("s36")
def _parse_damage_each_player_equal_to_listed_count_ability_text(
    text: str,
) -> AbilityEffect | None:
    """`_parse_damage_each_player_equal_to_their_count_clause`, read from the
    whole one-sentence ability when its count names two card types with "and"
    ("the number of instant and sorcery spells you've cast this turn", Sorcerer
    Class) - the clause splitter would cut the sentence at that "and", so the
    reader is handed the ability's text before any splitting."""
    lowered = text.lower()
    if "damage to each" not in lowered or " and " not in lowered:
        return None
    body = _strip_non_effect_preamble(text).strip()
    if body.count(".") > 1 or "," in body:
        return None
    return _parse_damage_each_player_equal_to_their_count_clause(body, for_spell=False)


#: "`<src>` deals X damage to `<recipient>`, where X is `<count>`" whose count
#: names the source itself ("other than this creature": Thundering Raiju's
#: "the number of modified creatures you control other than this creature"),
#: which the `(game, controller)` readers of the plain "where X" damage shapes
#: have no source to evaluate.
_WHERE_X_DAMAGE_SOURCE_COUNT_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? X damage to (?P<phrase>each opponent|each player|"
    r"[^,]*?\btargets?\b[^,]*?), where X is (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_where_x_damage_source_count_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_WHERE_X_DAMAGE_SOURCE_COUNT_RE`'s shape: X is read once as the effect
    applies (CR 608.2h), off the dealing object as it is or last was (CR
    113.7a) - amounts `count_expression` cannot read for lack of that source."""
    lowered = clause.lower()
    if "where x is" not in lowered or " other" not in lowered:
        return None
    match = _WHERE_X_DAMAGE_SOURCE_COUNT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    subject = re.split(r"\bdeals?\b", clause, maxsplit=1, flags=re.IGNORECASE)[0]
    expr = match.group("expr")
    if _TARGETED_SUBJECT_RE.search(subject) or count_expression(expr) is not None:
        return None
    reader = amount_expression(expr)
    if reader is None:
        return None
    phrase = match.group("phrase").lower()
    if phrase.startswith("each "):
        opponents_only = phrase == "each opponent"

        def spread(game: "Game", stack_object: "StackObject") -> None:
            source = _resolving_source(game, stack_object)
            controller = game.controller_of(stack_object).username
            amount = max(reader(game, controller, source, _announced_x(game, stack_object)), 0)
            _deal_all(
                game,
                [
                    (source, player, amount)
                    for player in game.players_in_game
                    if not opponents_only or player.username != controller
                ],
            )

        return spread
    if not _targets_understood(phrase, count_agnostic=True, allow_player_targets=True):
        return None
    return _deal_expression_damage(reader)


#: "Each opponent loses X life, where X is `<count>`." / "Each player gains X
#: life, where X is ..." (Skemfar Shadowsage's modes): the whole group, one
#: amount fixed as the effect applies (CR 608.2h) - or each recipient's own
#: when the count names them ("they control").
_EACH_PLAYER_LIFE_WHERE_X_RE = re.compile(
    r"^(?:then )?each (?P<who>opponent|player) (?P<verb>loses|gains) X life, "
    r"where X is (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_each_player_life_where_x_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_LIFE_WHERE_X_RE`'s shape, spell or ability."""
    if "where x is" not in clause.lower():
        return None
    match = _EACH_PLAYER_LIFE_WHERE_X_RE.fullmatch(clause.strip())
    if match is None:
        return None
    expr = match.group("expr")
    rewritten = expr
    for pattern, replacement in _TARGET_PLAYER_REFERENCES:
        rewritten = pattern.sub(replacement, rewritten)
    reader = amount_expression(rewritten)
    if reader is None:
        return None
    per_player = rewritten != expr
    opponents_only = match.group("who").lower() == "opponent"
    gains = match.group("verb").lower() == "gains"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = _resolving_source(game, stack_object)
        controller = game.controller_of(stack_object).username
        x_value = _announced_x(game, stack_object)
        shared = None if per_player else max(reader(game, controller, source, x_value), 0)
        recipients = [
            player
            for player in game.players_in_game
            if not opponents_only or player.username != controller
        ]
        amounts = [
            (
                player,
                max(reader(game, player.username, source, x_value), 0)
                if shared is None
                else shared,
            )
            for player in recipients
        ]
        for player, amount in amounts:
            if gains:
                game.gain_life(player, amount)
            else:
                game.lose_life(player, amount)

    return effect


# --------------------------------------------------------------------------
# CR 608.2h/611.2c multipliers on a targeted damage or counter amount: a
# fixed base "for each <expr>" (Immaculate Magistrate, Lotleth Giant), or
# CR 107.3a's X off a "where X is <expr>" tail (Tribal Flames, Scourge of
# Valkas). Both read once, as the ability begins to resolve, and are applied
# to every target alike - the same one-shot-then-fixed reading Craterhoof's
# own mass pump already gives its own "for each" (see `count_expression`'s
# own docstring).
# --------------------------------------------------------------------------


def _where_x_count_expression(phrase: str) -> Callable[["Game", str], int] | None:
    """`count_expression`, widened to accept CR 107.1's "plus"/"minus"
    between two terms - `_resolve_multiplied_amount`'s own "where X is ..."
    reading needs a `(game, controller) -> int` function, not `amount_
    expression`'s own `(game, controller, obj, x) -> int` `AmountReader`:
    there is no resolving object or announced X in scope at this call site,
    only the caster this damage/counter multiplier is computed for.

    Frantic Firebolt's own "where X is 2 plus the number of cards in your
    graveyard that are instant cards, sorcery cards, and/or have an
    Adventure." is the shape that needs this: a literal number offsetting a
    count `count_expression` alone already reads perfectly well, the
    identical "plus"/"minus" arithmetic `amount_expression` already gives
    every other position this engine reads a dynamic amount in - just
    re-read here against this function's own narrower signature rather than
    reusing that one directly.
    """
    parts = _AMOUNT_OPERATOR_RE.split(phrase.strip().rstrip("."))
    readers: list[Callable[[Game, str], int]] = []
    for term in parts[0::2]:
        term = term.strip()
        constant = parse_count(term)
        if constant is not None:
            readers.append(lambda _game, _controller, _constant=constant: _constant)
            continue
        reader = count_expression(term)
        if reader is None:
            return None
        readers.append(reader)
    operators = [operator.lower() for operator in parts[1::2]]

    def evaluate(game: "Game", controller: str) -> int:
        total = readers[0](game, controller)
        for operator, reader in zip(operators, readers[1:], strict=True):
            value = reader(game, controller)
            total = total - value if operator == "minus" else total + value
        return max(total, 0)  # CR 107.1b

    return evaluate


def _resolve_multiplied_amount(
    n: str, each: str | None, where_x: str | None
) -> Callable[["Game", str], int] | None:
    """The amount one of the damage/counter regexes above printed, as a
    function of `(game, controller)` evaluated once at resolution - `None`
    when the text names a multiplier this wave cannot read (an unfamiliar
    "for each"/"where X" expression, or a literal "x" with no definition to
    evaluate it against).
    """
    if n.lower() == "x":
        if where_x is None:
            return None
        return _where_x_count_expression(where_x)
    base = parse_count(n)
    if base is None:
        return None
    if each is None:
        return lambda _game, _controller: base
    multiplier = count_expression(each)
    if multiplier is None:
        return None
    return lambda game, controller: base * multiplier(game, controller)


#: The trigger condition's own "with one or more `<color>` mana symbols in
#: its mana cost" clause, read back from `TriggeredAbility.condition` at
#: resolution time - the color word this card's own token count is over.
_MANA_SYMBOLS_COLOR_IN_COST_CONDITION_RE = re.compile(
    r"with (?:one or more|at least one) (?P<color>white|blue|black|red|green) "
    r"mana symbols? in its mana cost",
    re.IGNORECASE,
)

_COLOR_WORD_TO_LETTER = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}


def color_pip_count_named_by_trigger(stack_object: "StackObject") -> int | None:
    """What "that many" counts when the trigger's own condition is "a spell
    with one or more `<color>` mana symbols in its mana cost" (Namor the
    Sub-Mariner): that colour's symbols in the cast spell's mana cost. `None`
    when the stack object is not a triggered ability with that condition, so
    a caller falls back to its own "that many" channel."""
    if not is_ability(stack_object) or stack_object.event is None:
        return None
    condition_text = getattr(stack_object.ability, "condition", None) or ""
    color_match = _MANA_SYMBOLS_COLOR_IN_COST_CONDITION_RE.search(condition_text)
    if color_match is None:
        return None
    letter = _COLOR_WORD_TO_LETTER.get(color_match.group("color").lower())
    card = stack_object.event.subject_card
    if letter is None or card is None:
        return 0
    return sum(
        1 for symbol in _MANA_SYMBOL_RE.findall(card.mana_cost or "") if symbol.upper() == letter
    )


def _x_sized_token_clause(zero_sized: str, size_reader: AmountReader) -> TargetedClause:
    """A token clause whose "X/X" is only known as it resolves: the clause is
    read again with the size written in, then run."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        if isinstance(stack_object, AbilityOnStack):
            # CR 608.2h: a size read off the source uses its last known
            # information once it has left its zone.
            source, x_value = stack_object.source_or_last_known(game), stack_object.x_value
        else:
            source, x_value = stack_object, 0
        size = size_reader(game, controller, source, x_value)
        literal = zero_sized.replace("0/0", f"{size}/{size}", 1)
        clause = _parse_token_clause(literal, for_spell=False)
        if clause is not None:
            clause(game, stack_object)

    return effect


#: "Create X `<descriptor>` tokens[ named `<Name>`][ with `<tail>`], where X
#: is `<expr>`." (CR 107.3f) - Germinate Recruits' own "where X is the amount
#: of life you gained this turn" and off-set Charisma Bobblehead's "where X
#: is the number of Bobbleheads you control". `_TOKEN_CLAUSE_RE`'s own `n`
#: group only ever reads a fixed `COUNT` word, never "X" - CR 107.3a's
#: announced X is substituted into that shape by `effect_for` before this
#: parser is ever tried, so a bare literal "X" reaching here always means CR
#: 107.3f's *other* X, one the card's own text defines and only `count_
#: expression` (already shared with every other "the number of ..." reader)
#: can evaluate - at resolution, not at parse time (CR 611.2c fixes the
#: magnitude once, the moment the effect applies).
_VARIABLE_COUNT_TOKEN_RE = re.compile(
    r"^(?:you )?(?:create )?x (?P<desc>.+?) \btokens?\b"
    r"(?:\s+named (?P<name>.+?))?"
    r"(?:\s+with\s+(?P<tail>.+?))?"
    r",?\s*where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


#: "Create a number of `<descriptor>` tokens equal to `<expr>`" (Goblin
#: Gathering) - the same variable-count token clause, with the count worded as
#: an "equal to" amount rather than "X ... where X is".
_NUMBER_OF_TOKENS_EQUAL_TO_RE = re.compile(
    r"^(?P<you>you )?(?P<verb>create )a number of (?P<rest>.+? \btokens?\b.*?) equal to "
    r"(?P<expr>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_variable_count_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_VARIABLE_COUNT_TOKEN_RE`'s shape, or `None` if this is not it."""
    stripped = clause.strip()
    if "a number of" in stripped.lower() and (
        counted := _NUMBER_OF_TOKENS_EQUAL_TO_RE.fullmatch(stripped)
    ):
        stripped = (
            f"{counted.group('you') or ''}{counted.group('verb')}x {counted.group('rest')}, "
            f"where X is {counted.group('expr')}"
        )
    match = _VARIABLE_COUNT_TOKEN_RE.fullmatch(stripped)
    if match is None:
        return None
    if "copy of" in clause.lower():
        return None  # CR 707.2 copying needs copiable values this wave does not read.
    words = match.group("desc").strip().split()
    tail = match.group("tail")
    name = match.group("name")

    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None

    predefined_name = " ".join(words)
    if tail is None and name is None and predefined_name in PREDEFINED:
        definition = PREDEFINED[predefined_name]
    else:
        definition = _parse_generic_token_descriptor(words, tail)
        if definition is None:
            return None
        if name is not None:
            definition = definition.model_copy(update={"name": name.strip()})

    reader = count_expression(match.group("expr"))
    if reader is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        count = reader(game, controller)
        if count > 0:
            create_tokens(game, definition, controller, count, tapped=tapped)

    return effect


#: "It gets +X/+X until end of turn, where X is `<expr>`." - Doran, Besieged
#: by Time's own attack-or-block trigger, the *variable*-magnitude sibling of
#: `_EVENT_SUBJECT_PUMP_RE`'s fixed "+N/+N": `parsed_layer_effects` (the
#: fixed shape's own builder) reads a literal number, never CR 107.3's X, so
#: this reads the magnitude itself, through `amount_expression`, evaluated
#: against the event's own subject - the attacking or blocking creature CR
#: 608.2h locks the amount in for, once, as the ability resolves - rather
#: than against the ability's source the way every other `amount_expression`
#: call in this file (whose `obj` is always the resolving spell or ability's
#: own object) already is.
_EVENT_SUBJECT_VARIABLE_PUMP_RE = re.compile(
    r"^(?:that (?P<noun>creature|permanent)|the blocking creature|it) gets \+x/\+x "
    r"until end of turn, where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_event_subject_variable_pump_clause(effect_text: str) -> AbilityEffect | None:
    """`_EVENT_SUBJECT_VARIABLE_PUMP_RE`'s shape, or `None`.

    Refused when the text mentions "target" anywhere, the same guard `_parse_
    event_subject_pump_clause` keeps: that shape is the ordinary target-
    resolution path, already correct.
    """
    stripped = effect_text.strip()
    if "target" in stripped.lower():
        return None
    match = _EVENT_SUBJECT_VARIABLE_PUMP_RE.match(stripped)
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        amount = reader(game, ability.controller, subject, ability.x_value)
        if amount <= 0:
            return
        source = ability.source(game)
        source_name = source.name if source is not None else ability.source_name
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source_name}: {subject.name} gets {amount:+d}/{amount:+d}",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=_only(subject.id),
                modification=modify_power_toughness(amount, amount),
            )
        )

    return effect


#: "... this is the `<ordinal>` time this ability has resolved this turn" -
#: the count is `Game.ability_resolutions_this_turn`, which already includes
#: the resolution in progress when the effect runs. Two printed shapes carry
#: it, each optionally followed by more "If it's the `<ordinal>` time,
#: `<effect>`." branches:
#:
#: - "`<effect>`. If this is the `<ordinal>` time this ability has resolved
#:   this turn, `<consequence>`." - an unconditional effect, then the
#:   conditional one (Sephiroth, Fabled SOLDIER; Soulbright Seeker);
#: - "`<effect>` if this is the `<ordinal>` time this ability has resolved
#:   this turn. If it's the `<ordinal>` time, `<effect>`. ..." - every effect
#:   conditional, one per resolution (Omnath, Locus of Creation; Belladonna
#:   Took; Vito, Fanatic of Aclazotz).
#:
#: The "if" is never CR 603.4's intervening "if" - it does not immediately
#: follow the trigger condition - so the ability always triggers and the
#: count is read only as it resolves.
_NTH_RESOLUTION_ANCHOR = (
    rf"this is the (?P<ordinal>{ORDINAL}) time this ability has resolved this turn"
)
_NTH_RESOLUTION_RE = re.compile(
    rf"^(?:(?P<first>.+?)\.\s*)?if {_NTH_RESOLUTION_ANCHOR}, (?P<then>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)
_NTH_RESOLUTION_LEADING_RE = re.compile(
    rf"^(?P<then>[^.]+?) if {_NTH_RESOLUTION_ANCHOR}\.?$",
    re.IGNORECASE | re.DOTALL,
)
#: One more branch: "If it's the `<ordinal>` time, `<effect>`." - "it" is
#: the same "this ability has resolved this turn" count the anchor names.
_NTH_RESOLUTION_BRANCH_RE = re.compile(
    rf"\.\s*if it(?:'|’)s the (?P<ordinal>{ORDINAL}) time, ", re.IGNORECASE
)


def _nth_resolution_branch_effect(text: str) -> AbilityEffect | None:
    """One branch's effect, read by the ordinary ability dispatcher - but
    never one of its fail-closed notice stand-ins, which would hide an
    unreadable branch inside a readable whole."""
    effect = _ability_effect_or_notice(text)
    if effect is None or getattr(effect, "__name__", "").endswith(("_notice_only", "_notice")):
        return None
    return effect


@ABILITY_TEXT.rung("s23")
def _parse_nth_resolution_clause(text: str) -> AbilityEffect | None:
    """`_NTH_RESOLUTION_RE`'s and `_NTH_RESOLUTION_LEADING_RE`'s shapes, each
    with any number of trailing `_NTH_RESOLUTION_BRANCH_RE` branches. The
    unconditional first sentence, if any, always runs; then the one branch
    naming this resolution's count runs, or none from the count after the
    last named one on."""
    stripped = _strip_non_effect_preamble(text).strip()
    pieces = _NTH_RESOLUTION_BRANCH_RE.split(stripped)
    head, rest = pieces[0], pieces[1:]
    match = _NTH_RESOLUTION_RE.fullmatch(head) or _NTH_RESOLUTION_LEADING_RE.fullmatch(head)
    if match is None:
        return None
    first_text = match.groupdict().get("first")
    first = parse_mixed_effect(first_text + ".") if first_text else None
    if first_text and first is None:
        return None
    raw_branches = [(match.group("ordinal"), match.group("then"))]
    raw_branches += list(zip(rest[0::2], rest[1::2], strict=True))
    branches: list[tuple[int, AbilityEffect]] = []
    for ordinal, branch_text in raw_branches:
        nth = parse_ordinal(ordinal)
        effect = _nth_resolution_branch_effect(branch_text.strip().rstrip(".") + ".")
        if nth is None or effect is None:
            return None
        branches.append((nth, effect))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if first is not None:
            first(game, ability)
        count = game.ability_resolutions_this_turn.get(resolution_key(ability), 0)
        for nth, then in branches:
            if count == nth:
                then(game, ability)

    return effect


#: "Whenever a creature you control attacks alone, it gets +X/+X until end
#: of turn, where X is the number of Kithkin you control." (Thoughtweft
#: Imbuer, CR 506.5) - the dynamic-X twin of `_SELF_ATTACK_PUMP_FOR_EACH_RE`
#: just above: that reader's own fixed-per-unit "for each" phrasing and this
#: one's "+X/+X, where X is ..." are the same magnitude spelled two different
#: ways, but the *subject* differs. `_attack_trigger_pump_subject` resolves
#: "it" to the *ability's own source* (CR 700.7's plain self-reference,
#: right for "Whenever this creature attacks, it gets ..."); Thoughtweft
#: Imbuer's own trigger condition never names itself at all - "a creature you
#: control attacks alone" fires off *any* attacker, so "it" is CR 603.2's
#: anaphora onto the triggering event's own subject, which is `_referent_of_
#: it`'s job, not that helper's.
#:
#: Power and toughness are each read independently as either "x" or a literal
#: number, so Akroan Hoplite's own "it gets +X/+0 until end of turn, where X
#: is the number of attacking creatures you control" (off-set proof: a
#: literal "+0" toughness alongside the dynamic power, and `count_expression`'s
#: own widened "attacking creatures you control" status read) is the same
#: shape as Thoughtweft Imbuer's "+X/+X", just with one side pinned.
_IT_GETS_DYNAMIC_X_PUMP_RE = re.compile(
    r"^it gets (?P<power_sign>[+-])(?P<power>x|\d+)/(?P<toughness_sign>[+-])(?P<toughness>x|\d+) "
    r"(?P<duration>until end of turn|until your next turn), where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s9")
def _parse_it_dynamic_x_pump_clause(text: str) -> AbilityEffect | None:
    """`_IT_GETS_DYNAMIC_X_PUMP_RE`'s shape; see the banner above."""
    match = _IT_GETS_DYNAMIC_X_PUMP_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    power_is_x = match.group("power").lower() == "x"
    toughness_is_x = match.group("toughness").lower() == "x"
    if not power_is_x and not toughness_is_x:
        # Neither side is dynamic at all - not this reader's shape, whatever
        # else it might be.
        return None
    counted = count_expression(match.group("expr"))
    if counted is None:
        return None
    power_sign = -1 if match.group("power_sign") == "-" else 1
    toughness_sign = -1 if match.group("toughness_sign") == "-" else 1
    fixed_power = None if power_is_x else int(match.group("power"))
    fixed_toughness = None if toughness_is_x else int(match.group("toughness"))
    until_next_turn = match.group("duration").strip().lower() == "until your next turn"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        referent = _referent_of_it(game, ability)
        if referent is None:
            return
        controller = game.controller_of(ability).username
        count = counted(game, controller)
        power = power_sign * count if fixed_power is None else power_sign * fixed_power
        toughness = (
            toughness_sign * count if fixed_toughness is None else toughness_sign * fixed_toughness
        )
        store = continuous_effects(game)
        duration = Duration.UNTIL_YOUR_NEXT_TURN if until_next_turn else Duration.UNTIL_END_OF_TURN
        store.add(
            ContinuousEffect(
                description=(
                    f"{ability.source_name}: {referent.name} gets {power:+d}/{toughness:+d}"
                ),
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=duration,
                until_next_turn_of=(controller if until_next_turn else None),
                source_id=ability.source_id,
                selector=only_this_incarnation(referent, referent.zone_change_stamp),
                modification=modify_power_toughness(power, toughness),
            )
        )

    return effect


@ABILITY_TEXT.rung("s9")
def _parse_it_dynamic_x_pump_then_if_clause(text: str) -> AbilityEffect | None:
    """ "`<it> gets +X/+X until end of turn, where X is <count>.` `Then if <its
    power is N or greater>, <instruction>.`" (Jor Kadeen, First Goldwarden): the
    pump (`_parse_it_dynamic_x_pump_clause`) is applied first, then the "Then
    if" sentence is read as its own ability text (CR 608.2c: in order) - its
    condition looks at the creature as the pump left it."""
    if "where X is" not in text or ". Then if " not in text:
        return None
    pump, _, rest = " ".join(text.strip().split()).partition(". Then if ")
    pumped = _parse_it_dynamic_x_pump_clause(pump + ".")
    if pumped is None:
        return None
    follow_up = _ability_effect_or_notice("Then if " + rest)
    if follow_up is None or not _readable_effect(follow_up):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        pumped(game, ability)
        follow_up(game, ability)

    return effect


#: "You gain half X life and draw half X cards. Round down each time." -
#: Hydroid Krasis's own cast trigger. CR 107.1a: "If a spell or ability could
#: generate a fractional number, the spell or ability will tell you whether
#: to round up or down" - printed here as one trailing sentence governing
#: *both* halves rather than `numbers.parse_half`'s own inline "half `<of>`,
#: rounded up/down" (Tamiyo, Seasoned Scholar), so this is its own shape, not
#: a second call site for that parser. The backreference (`(?P=of)`) requires
#: the identical printed expression on both sides, so this is not fitted to
#: the literal word "X" - it reads whatever quantity a card halves twice in a
#: row, and X (CR 107.3a's own value announced for the spell as it was cast,
#: never the ability's own - a triggered ability announces no X of its own,
#: the identical read `_parse_cast_trigger_look_top_x_take_one_clause` above
#: already gives Geometer's Arthropod) is simply the one term `amount_
#: expression` reads that this reader has to special-case, since the spell's
#: own announced X lives on its `CastRecord`, not on anything `amount_
#: expression`'s ordinary `(game, controller, obj, x)` callers already thread
#: through.
_HALF_X_LIFE_AND_DRAW_HALF_X_CARDS_RE = re.compile(
    r"^you gain half (?P<of>.+?) life and draw half (?P=of) cards\.\s*"
    r"round (?P<direction>up|down) each time\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s5")
def _parse_half_x_life_and_draw_half_x_cards_clause(effect_text: str) -> AbilityEffect | None:
    """`_HALF_X_LIFE_AND_DRAW_HALF_X_CARDS_RE`'s shape - see the banner
    above. `of` other than a bare "x" falls back to `amount_expression`,
    evaluated against the ability's own controller and source (0 for any
    embedded X of *its own*, since a triggered ability announces none) -
    unreadable there fails the whole clause closed rather than guessing.
    """
    match = _HALF_X_LIFE_AND_DRAW_HALF_X_CARDS_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    of = match.group("of").strip()
    round_up = match.group("direction").lower() == "up"
    is_x = of.lower() == "x"
    magnitude = None if is_x else amount_expression(of)
    if not is_x and magnitude is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        if is_x:
            amount = _cast_trigger_x_value(game, ability) or 0
        else:
            source = ability.source_or_last_known(game)
            assert magnitude is not None
            amount = 0 if source is None else magnitude(game, controller.username, source, 0)
        half = halve(max(amount, 0), round_up=round_up)  # CR 107.1b, then CR 107.1a
        if half <= 0:
            return
        game.gain_life(controller, half)
        game.draw_cards(controller.username, half)

    return effect


#: "You get X {E} (energy counters), then you may pay any amount of {E}.
#: Destroy each artifact, creature, and enchantment with mana value less than
#: or equal to the amount of {E} paid this way." (Wrath of the Skies) - the
#: same variable-amount energy payment as Galvanic Discharge, referenced by a
#: mass-destruction clause keyed off the amount paid instead of a target.
#: The qualifier is captured rather than spelled out, and handed to
#: `_parse_mass_type_qualifier` - the same grammar every other mass-destroy
#: clause in this module is read with. Keying the type list to this one card's
#: wording is what let the printed-vs-computed defect in below, and it would
#: not generalise to the next card printed with an energy-bounded sweep.
_X_ENERGY_PAY_DESTROY_BY_MANA_VALUE_RE = re.compile(
    r"^you get x \{e\}\s*(?:\([^()]*\))?,\s*then you may pay any amount of \{e\}\.\s*"
    r"destroy each (?P<qualifier>.+?) with mana value less than or "
    r"equal to the amount of \{e\} paid this way\.$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s16")
def _parse_x_energy_pay_destroy_by_mana_value(text: str) -> Effect | None:
    """Wrath of the Skies's own shape, see
    `_X_ENERGY_PAY_DESTROY_BY_MANA_VALUE_RE`.

    `X` is fixed once for the whole spell at announcement (CR 107.3a) and read
    back off `Game.cast_record` the same way `parse_mode_effect` already reads
    it for a modal card's own `X` mode.

    The sweep itself is `_destroy_matching` over a `_parse_mass_type_qualifier`
    predicate - the shared mass-destruction path, not a private loop. That is
    the fix for a real defect: this clause used to filter on `CardState.types`
    and `CardState.mana_value`, which are CR 613.1's *starting point* (the
    printed type line of whichever face is up, CR 712.8d), not the object's
    characteristics. CR 613.5 has the layer system applied "continually and
    automatically", so a land animated by earthbend (CR 701.66a) is a creature
    in layer 4 (CR 613.1d) whose mana value is 0 (CR 202.3a, "an object with
    no mana cost"), squarely inside any "2 or less" window - and it walked out
    of the sweep untouched. `game.characteristics_of`, which
    `_parse_mass_type_qualifier` reads, is the only right answer for anything
    on the battlefield.

    `_destroy_matching` also carries CR 608.2f's simultaneity: the candidate
    set is snapshotted before anything is destroyed, and each permanent's zone
    is rechecked immediately before its own destroy for the same reason CR
    608.2b rechecks a target.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _X_ENERGY_PAY_DESTROY_BY_MANA_VALUE_RE.fullmatch(whole)
    if match is None:
        return None
    type_matches = _parse_mass_type_qualifier(match.group("qualifier"))
    if type_matches is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        x_value = game.cast_record(spell).x_value
        if x_value > 0:
            game.add_player_counters(player, Counter.ENERGY, x_value)
        paid = game.pay_any_amount_of_energy(
            player, source=spell.card.name, source_id=source_id_of(spell)
        )
        if paid <= 0:
            return

        def matches(
            game: "Game",
            permanent: CardState,
            source: CardState | None,
            x_value: int | None = None,
        ) -> bool:
            chars = game.characteristics_of(permanent)
            return type_matches(chars) and chars.mana_value <= paid

        _destroy_matching(game, matches, spell)

    return effect


#: Converge (an ability word - `knowledge_search` found no numbered CR rule
#: for it this session, so none is cited): "Exile target nonland permanent if
#: its mana value is less than or equal to the number of colors of mana
#: spent to cast this spell." Deliberately its own parser rather than a
#: `machines/targeting.py` comparison: that count is not fixed until the
#: spell's cost is fully paid (CR 601.2g-i), which is *after* targets are
#: announced (CR 601.2c) - unlike Fatal Push's mana-value threshold, there is
#: no moment before resolution at which this count could restrict what may
#: legally be targeted, so the target itself is read as the plain, unrestricted
#: "target nonland permanent" `_targets_understood` already knows, and the
#: whole condition is judged once, at resolution, off `CastRecord.mana_spent`
#: (color keys only - `Color.COLORLESS` is generic mana, not one of CR 105.1's
#: five colors).
_CONVERGE_EXILE_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?exile target nonland permanent if its mana value is less than "
    r"or equal to the number of colors of mana spent to cast this spell\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_converge_exile_by_colors_spent(effect_text: str) -> Effect | None:
    """`_CONVERGE_EXILE_RE`'s shape, or `None` if this is not it."""
    if _CONVERGE_EXILE_RE.fullmatch(effect_text.strip()) is None:
        return None
    if not _targets_understood("target nonland permanent", count_agnostic=False):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        record = game.cast_record(spell)
        colors_spent = len(
            {color for color, amount in record.mana_spent.items() if amount > 0} - {Color.COLORLESS}
        )
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                mana_value = game.characteristics_of(target).mana_value
                if mana_value <= colors_spent:
                    game.exile_permanent(target)

    return effect


#: Converge (CR 207.2c): "Target player discards X cards, where X is the
#: number of colors of mana spent to cast this spell." (Arcane Omens).
#: `_targets_understood`'s own "target player" reading already accepts an
#: opponent-restricted variant too, so `who` is read rather than fixed.
_CONVERGE_DISCARD_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?target (?P<who>player|opponent) discards x cards?,\s*"
    r"where x is the number of colors of mana spent to cast this spell\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_converge_discard_by_colors_spent(effect_text: str) -> Effect | None:
    """`_CONVERGE_DISCARD_RE`'s shape, or `None` if this is not it. The
    discard call itself is `_parse_target_player_discards_clause`'s own -
    CR 701.9b's default chooser (the discarding player themselves) - reused
    rather than reimplemented, once `machines/converge.colors_of_mana_spent`
    has worked out how many cards that default chooser is discarding."""
    match = _CONVERGE_DISCARD_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    phrase = f"target {match.group('who')}"
    if not _targets_understood(phrase, allow_player_targets=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = colors_of_mana_spent(game, spell)
        if amount <= 0:
            return
        for target in game.resolve_targets(spell):
            if not isinstance(target, Player):
                continue
            needed = min(amount, len(target.hand))
            if needed <= 0:
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=target.username,
                    prompt=f"discard {needed} card(s)",
                    source=spell.name,
                    amount=needed,
                    cards=tuple(state.id for state in target.hand),
                    source_id=source_id_of(spell),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in target.hand}
            game.discard_cards(
                target.username, [by_id[card_id] for card_id in chosen_ids], source=spell.name
            )

    return effect


#: Converge (CR 207.2c): Archaic's Agony's own "Converge — `<name>` deals X
#: damage to target creature, where X is the number of colors of mana spent
#: to cast this spell. Exile cards from the top of your library equal to the
#: excess damage dealt to that creature this way. You may play those cards
#: until the end of your next turn." Read whole, the same reason `_DAMAGE_
#: THEN_EMPOWER_IF_EXCESS_RE` above is: the second sentence's CR 120.10
#: excess is measured against how much the first sentence actually dealt,
#: and the third sentence's grant names exactly what the second exiled.
#: `<name>` is read and thrown away - the source is always the resolving
#: spell regardless of what it is printed to be named after.
_CONVERGE_DAMAGE_THEN_EXILE_EXCESS_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?[A-Za-z][A-Za-z' -]*? deals x damage to target creature,\s*"
    r"where x is the number of colors of mana spent to cast this spell\.\s*"
    r"exile cards from the top of your library equal to the excess damage dealt to "
    r"that creature this way\.\s*you may play (?:those|these) cards until the end of "
    r"your next turn\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_converge_damage_then_exile_excess_clause(effect_text: str) -> Effect | None:
    """`_CONVERGE_DAMAGE_THEN_EXILE_EXCESS_RE`'s shape, or `None`.

    `_lethal_amount_before_damage` (CR 120.10, read just above for Violent
    Echoes' own excess-damage empower) has to run *before* `Game.deal_damage`
    marks the damage it measures against; `deal_damage`'s own return is the
    amount actually dealt (CR 609.7b's own prevention/replacement effects
    already applied), which is what CR 120.10's excess is measured against,
    not the printed/computed X. The exiled cards' play grant mirrors
    `_parse_exile_hand_draw_then_play_until_next_turn_clause`'s own
    "until the end of your next turn" shape (`until_next_turn_of`).
    """
    match = _CONVERGE_DAMAGE_THEN_EXILE_EXCESS_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood("target creature"):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = colors_of_mana_spent(game, spell)
        controller = game.controller_of(spell)
        for target in game.resolve_targets(spell):
            if not isinstance(target, CardState):
                continue
            pre_lethal = _lethal_amount_before_damage(game, target)
            dealt = game.deal_damage(target, amount, source=spell)
            if pre_lethal is None:
                continue
            excess = dealt - pre_lethal
            if excess <= 0:
                continue
            top = list(controller.library[:excess])
            if not top:
                continue
            for card in game.exile_cards(top):
                game.grant_play_permission(
                    card,
                    controller.username,
                    action=PlayAction.PLAY,
                    pays_mana_cost=True,
                    source_name=spell.name,
                    zone=Zone.EXILE,
                    rule="CR 601.3",
                    until_next_turn_of=controller.username,
                )

    return effect


#: Converge (CR 207.2c): Snarl Song's own "Converge — Create two 0/0 green
#: and blue Fractal creature tokens. Put X +1/+1 counters on each of them and
#: you gain X life, where X is the number of colors of mana spent to cast
#: this spell." The token-creation half is `_parse_token_clause`'s own
#: generic "create N `<desc>` token(s)" reader, reused whole rather than
#: reimplemented (it already reads any count, colour pair, and creature type
#: - nothing here is specific to a Fractal); what is new is the second
#: sentence's compound rider, which `_parse_referent_object_clause`'s own
#: `_RIDER_PUT_COUNTERS_RE`/`_RIDER_PUT_VARIABLE_COUNTERS_RE` cannot join to
#: an "and you gain X life" tail sharing the same "where X is" definition.
_CONVERGE_TOKENS_COUNTERS_AND_LIFE_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?(?P<token_clause>create [^.]+)\.\s*"
    r"put x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each of them and you gain x life,\s*"
    r"where x is the number of colors of mana spent to cast this spell\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_converge_fractal_tokens_and_life_clause(effect_text: str) -> Effect | None:
    """`_CONVERGE_TOKENS_COUNTERS_AND_LIFE_RE`'s shape, or `None`.

    The tokens actually created (a before/after id diff on `game.
    battlefield`, the same technique `_parse_token_then_object_anaphor_
    clause_pair` already uses for its own single-token rider) are each given
    the counters; the life gain is unconditional on X alone (CR 608.2c: "you
    gain X life" is its own instruction, not scaled by how many tokens
    happened to survive to be counted).
    """
    match = _CONVERGE_TOKENS_COUNTERS_AND_LIFE_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    token_effect = _parse_token_clause(match.group("token_clause").strip(), for_spell=True)
    if token_effect is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", spell: CardState) -> None:
        amount = colors_of_mana_spent(game, spell)
        before_ids = {existing.id for existing in game.battlefield}
        token_effect(game, spell)
        if amount <= 0:
            return
        created = [state for state in game.battlefield if state.id not in before_ids]
        for token in created:
            game.add_counters(token, kind, amount)
        game.gain_life(game.controller_of(spell), amount)

    return effect


#: Converge (CR 207.2c): Together as One's own "Converge — Target player
#: draws X cards, `<name>` deals X damage to any target, and you gain X
#: life, where X is the number of colors of mana spent to cast this spell."
#: Three different actors (a targeted player, a targeted anything, and the
#: caster) sharing one "where X is" definition in one CR 608.2c instruction -
#: read whole for the identical reason `_parse_converge_draw_damage_life_
#: clause`'s siblings above are, since `_CLAUSE_SEPARATOR`'s bare-comma/"and"
#: split would otherwise cut the shared X definition away from two of its
#: three uses. `spell.targets` is read by position rather than through the
#: aggregate `Game.resolve_targets`, because that call alone cannot tell
#: "target player" and "any target" apart once one becomes illegal and is
#: dropped from it - the same reason `TargetRequirement.SOURCE_LOYALTY`
#: reads its own count off `source_id` and not off a merged list. The
#: position is **not** printed order: `machines/targeting._parse` collects
#: every "any target" occurrence first, before its main left-to-right scan
#: of the remaining "target `<phrase>`" occurrences (see its own source for
#: why - `any_targets` is built and substituted out of the text before the
#: ordinary scan ever starts), so "any target"'s own requirement is always
#: `spell.targets[0]` here even though "target player" is printed first.
_CONVERGE_DRAW_DAMAGE_LIFE_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?target player draws x cards,\s*"
    r"[A-Za-z][A-Za-z' -]*? deals x damage to any target,\s*and you gain x life,\s*"
    r"where x is the number of colors of mana spent to cast this spell\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_converge_draw_damage_life_clause(effect_text: str) -> Effect | None:
    """`_CONVERGE_DRAW_DAMAGE_LIFE_RE`'s shape, or `None`."""
    match = _CONVERGE_DRAW_DAMAGE_LIFE_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    if not _targets_understood("any target", allow_player_targets=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = colors_of_mana_spent(game, spell)
        controller = game.controller_of(spell)
        refs = spell.targets
        # "any target" is collected first (see the comment above), "target
        # player" second.
        damage_target = game.legal_target(spell, refs[0]) if len(refs) > 0 else None
        player_target = game.legal_target(spell, refs[1]) if len(refs) > 1 else None
        if amount <= 0:
            return
        if isinstance(player_target, Player):
            game.draw_cards(player_target.username, amount)
        if damage_target is not None and not isinstance(damage_target, AbilityOnStack):
            game.deal_damage(damage_target, amount, source=spell)
        game.gain_life(controller, amount)

    return effect


#: Converge (CR 207.2c), proof of generality: Painful Truths' own "You draw
#: X cards and lose X life, where X is the number of colors of mana spent to
#: cast this spell." - the same amount, in a plain untargeted "you" clause
#: rather than any of Arcane Omens/Together as One's targeted shapes, proving
#: `machines/converge.colors_of_mana_spent` generalises to a third effect
#: position with no target at all.
_CONVERGE_DRAW_AND_LOSE_LIFE_RE = re.compile(
    r"^(?:[a-z][a-z '-]* — )?you draw x cards and lose x life,\s*"
    r"where x is the number of colors of mana spent to cast this spell\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_converge_draw_and_lose_life_clause(effect_text: str) -> Effect | None:
    """`_CONVERGE_DRAW_AND_LOSE_LIFE_RE`'s shape, or `None`."""
    if _CONVERGE_DRAW_AND_LOSE_LIFE_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = colors_of_mana_spent(game, spell)
        if amount <= 0:
            return
        controller = game.controller_of(spell)
        game.draw_cards(controller.username, amount)
        game.lose_life(controller, amount)

    return effect


#: Toxic Deluge: "As an additional cost to cast this spell, pay X life.\nAll
#: creatures get -X/-X until end of turn." The additional-cost line is
#: already stripped by `_strip_non_effect_preamble` (CR 118.8a: paid on the
#: way to the stack, not part of resolving the spell) before this ever sees
#: it, so only the second sentence is matched here, with its "X" still
#: literal - `effect_for`'s own X substitution only fires for a spell with
#: `{X}` in its *mana cost* (Green Sun's Zenith, Walking Ballista), and Toxic
#: Deluge's X is announced by the additional cost instead (CR 107.3f), so
#: this reads `Game.cast_record` for itself at resolution exactly the way
#: `_parse_x_energy_pay_destroy_by_mana_value` already does for its own
#: additional-cost X. `_run_mass_pump` and `_mass_creature_group_targets`'s
#: "all creatures" branch (see `machines/layers.py`'s widened
#: `_MASS_PUMP_UNTIL_EOT_RE`) are reused unchanged, with a negative magnitude
#: and no controller restriction - the shared primitive this wave was told to
#: build on rather than duplicate.
_X_LIFE_MASS_DEBUFF_RE = re.compile(
    r"^all creatures get -x/-x until end of turn\.?$", re.IGNORECASE
)


@SPELL_TEXT.rung("s14")
def _parse_x_life_mass_debuff(effect_text: str) -> Effect | None:
    """`_X_LIFE_MASS_DEBUFF_RE`'s shape, or `None` if this is not it."""
    if _X_LIFE_MASS_DEBUFF_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        x_value = game.cast_record(spell).x_value
        if x_value <= 0:
            return
        literal = f"All creatures get -{x_value}/-{x_value} until end of turn."
        _run_mass_pump(game, spell, game.controller_of(spell).username, literal, None)

    return effect


#: Fix What's Broken: "As an additional cost to cast this spell, pay X
#: life.\nReturn each artifact and creature card with mana value X from
#: your graveyard to the battlefield." - the additional-cost line is already
#: stripped by `_strip_non_effect_preamble` before this ever sees it, the
#: same way `_X_LIFE_MASS_DEBUFF_RE` reads Toxic Deluge's, so only the
#: second sentence is matched here, with its "X" still literal (`effect_
#: for`'s own substitution only fires for a spell with `{X}` in its printed
#: mana cost, and this X is announced by the additional cost instead, CR
#: 107.3f) - `Game.cast_record(spell).x_value` is read fresh at resolution,
#: exactly as `_parse_x_life_mass_debuff` already does for its own
#: additional-cost X. "Artifact and creature" is CR 205.2a's own two-type
#: union, read by `_parse_card_group_qualifier`'s widened "`<A>` and `<B>`"
#: branch (see that function) rather than a bespoke word pair here, so any
#: future card pairing a *different* two types with this exact "mana value
#: X" shape is covered for free.
_X_LIFE_RETURN_TYPES_MV_X_RE = re.compile(
    r"^return each (?P<types>.+?) cards? with mana value x from your graveyard "
    r"to the battlefield\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14")
def _parse_x_life_return_types_mv_x_clause(effect_text: str) -> Effect | None:
    """`_X_LIFE_RETURN_TYPES_MV_X_RE`'s shape, or `None` if this is not it."""
    match = _X_LIFE_RETURN_TYPES_MV_X_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    matches = _parse_card_group_qualifier(match.group("types"))
    if matches is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        # CR 119.4b: "players can always pay 0 life" - X=0 is a legal,
        # meaningful choice here (Ornithopter's own mana value 0 matches
        # it), unlike a magnitude-based effect (`_parse_x_life_mass_debuff`'s
        # own -X/-X) where 0 truly is a no-op. Only a genuinely negative
        # value - which CR 119.4's payment floor never produces - would be
        # nothing to match.
        x_value = game.cast_record(spell).x_value
        if x_value < 0:
            return
        controller = game.controller_of(spell)
        # CR 608.2f: the whole qualifying group moves as one action, so it is
        # snapshotted before any of it arrives - the same reasoning
        # `_parse_mass_return_from_graveyard_to_battlefield_clause` documents
        # for its own "return all ..." shape.
        chosen = [
            state
            for state in list(controller.graveyard)
            if matches(state) and state.mana_value == x_value
        ]
        with game.entering_together():  # CR 603.6a: one instruction, one event
            for state in chosen:
                if state.zone is Zone.GRAVEYARD:
                    game.put_onto_battlefield(state, controller.username)

    return effect


#: "you gain X life" / "draw X cards" - the two `_parse_x_magnitude_body`
#: clauses this wave reads with the sacrificed permanent's power substituted
#: in for X. Anything else in the "where X is ..." body (a token count, a
#: counter placed, a fixed-number clause `parse_clause_effect` already reads
#: on its own) is refused rather than guessed at.
_GAIN_X_LIFE_RE = re.compile(r"^(?:you )?gains? X life$", re.IGNORECASE)
_DRAW_X_CARDS_RE = re.compile(r"^draws? X cards?$", re.IGNORECASE)


def _parse_x_magnitude_body(body: str) -> Callable[["Game", Player, int], None] | None:
    """ "you gain X life and draw X cards" - the pre-"where X is" half of a
    magnitude-threaded consequence - split on the same bare " and " CR 608.2c
    treats as joining two instructions, with each half read by `_GAIN_X_LIFE_
    RE` or `_DRAW_X_CARDS_RE`. Fail-closed on any clause neither reads, the
    same discipline `_parse_player_clauses` already holds to for a plain
    (non-X) player clause.
    """
    parts = [part.strip() for part in re.split(r"\s+and\s+", body.strip()) if part.strip()]
    if not parts:
        return None
    steps: list[Callable[[Game, Player, int], None]] = []
    for part in parts:
        if _GAIN_X_LIFE_RE.fullmatch(part):
            steps.append(lambda game, player, amount: player.gain_life(amount))
        elif _DRAW_X_CARDS_RE.fullmatch(part):
            steps.append(lambda game, player, amount: game.draw_cards(player.username, amount))
        else:
            return None

    def run(game: "Game", player: Player, amount: int) -> None:
        for step in steps:
            step(game, player, amount)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return run


#: A count the reflexive ability's own text points back at: "up to that
#: many target creatures" (Swashbuckler Extraordinaire), and the X a
#: "sacrifice X" chose (Campsite Cuisine's "up to X target attacking
#: creatures", CR 107.3i: every X on the object is the same value).
_CARRIED_COUNT_RE = re.compile(r"\bthat many\b|\bX\b")


def _carry_count(text: str, count: int, *, x: bool) -> str:
    """`text` with the count its creating ability moved written in as a
    digit - "that many" always, a bare X only when `x` says the action's own
    count was an X. The reflexive ability is a new object (CR 603.12) that
    announces its own targets as it goes on the stack (CR 603.3d), so the
    number has to travel with its text, the same way a cast X is written
    into a spell's text as a digit before it is read (CR 107.3a)."""

    def swap(match: re.Match[str]) -> str:
        if match.group(0) == "X" and not x:
            return match.group(0)
        return str(count)

    return _CARRIED_COUNT_RE.sub(swap, text)


#: "damage equal to the sacrificed creature's power" / "damage equal to that
#: creature's power" - a reflexive consequence's amount (Tiger-Tribe Hunter,
#: Heart-Piercer Manticore): the power the sacrificed creature last had on
#: the battlefield (CR 608.2h), written into the reflexive ability's text as
#: a digit the way `_carry_count` writes a count (CR 603.12).
_SACRIFICED_POWER_DAMAGE_RE = re.compile(
    r"damage equal to (?:the sacrificed creature's|that creature's) power", re.IGNORECASE
)


def carries_sacrificed_power(text: str) -> bool:
    """Whether `text` sizes its damage by the sacrificed creature's power."""
    return _SACRIFICED_POWER_DAMAGE_RE.search(text) is not None


def _carry_sacrificed_power(text: str, power: int) -> str:
    """`text` with the sacrificed creature's last known power written in."""
    return _SACRIFICED_POWER_DAMAGE_RE.sub(f"{max(power, 0)} damage", text)


#: Kinscaer Sentry's attack trigger: "you may put a creature card with mana
#: value X or less from your hand onto the battlefield tapped and attacking,
#: where X is the number of attacking creatures you control." - the dynamic-X
#: mana-value-capped twin of `_PUT_CREATURE_FROM_HAND_ATTACKING_RE` just
#: above: the same CR 508.4 placement-into-combat primitive
#: (`models.token._put_onto_the_battlefield_attacking`), gated on a mana
#: value ceiling this reader alone needs, X fixed once (CR 608.2c: an
#: instruction's own count is determined as it is performed, not re-read
#: mid-resolution even though putting the chosen creature onto the
#: battlefield changes how many creatures are attacking) via `count_
#: expression`'s own "the number of attacking creatures you control" reader.
_PUT_CREATURE_MV_X_FROM_HAND_ATTACKING_RE = re.compile(
    r"^you may put an? (?P<group>[a-z]+) card with mana value x or less from your hand onto "
    r"the battlefield tapped and attacking, where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_put_creature_mv_x_from_hand_attacking(text: str) -> AbilityEffect | None:
    """`_PUT_CREATURE_MV_X_FROM_HAND_ATTACKING_RE`'s shape; see the banner
    above."""
    match = _PUT_CREATURE_MV_X_FROM_HAND_ATTACKING_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    matches_group = _parse_card_group_qualifier(match.group("group"))
    if matches_group is None:
        return None
    counted = count_expression(match.group("expr"))
    if counted is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ...models.token import _put_onto_the_battlefield_attacking

        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        limit = counted(game, controller.username)
        candidates = [
            state for state in controller.hand if matches_group(state) and state.mana_value <= limit
        ]
        if not candidates:
            return
        if not game.may(
            controller,
            "put a creature card from your hand onto the battlefield tapped and attacking",
            source=source_name,
            source_id=source_id_of(ability),
        ):
            return
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt=(
                f"choose a creature card with mana value {limit} or less to put onto the "
                "battlefield attacking"
            ),
            source=source_name,
            amount=1,
            cards=tuple(state.id for state in reversed(candidates)),
            source_id=source_id_of(ability),
        )
        chosen_ids = game.ask(decision)
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id[chosen_ids[0]]
        with game.entering_together():
            permanent = game.put_onto_battlefield(chosen, controller.username, tapped=True)
            if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
                return
            defender = _defender_of_controllers_attack(game, controller.username)
            if defender is not None:
                _put_onto_the_battlefield_attacking(game, permanent, defender)  # type: ignore[arg-type]

    return effect


#: "If you have seven or more cards in your graveyard, you may transform this
#: permanent." (Search for Azcanta, after its "Then" is cut off by the
#: splitter) and "If there are N or more cards in your graveyard, ..." - a
#: condition inside an effect, not an intervening *if* (CR 603.4), checked
#: when this clause is reached (CR 608.2c), after every instruction before it.
_IF_GRAVEYARD_COUNT_RE = re.compile(
    rf"^if (?:you have|there are) (?P<n>{COUNT}) or more cards in your graveyard, (?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


#: "Distribute X `<kind>` counters among `<targets>`, where X is `<count>`"
#: (Undercity Upheaval, with its ability-word prefix): the total is the count
#: the text defines, read through `count_expression` - for an "as you cast this
#: spell" count that is the X `Casting` locked while the division was announced
#: (CR 601.2d) - and paid out by the same `_distribute_counters_shares` the
#: fixed-number "Distribute N counters among" clause uses.
_DISTRIBUTE_X_COUNTERS_AMONG_TARGETS_RE = re.compile(
    r"^(?:[^—]+ — )?distributes? x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? among "
    r"(?P<phrase>.+?),\s*where X is (?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_distribute_x_counters_among_targets_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DISTRIBUTE_X_COUNTERS_AMONG_TARGETS_RE`'s shape, or `None`."""
    if "distribute" not in clause.lower():
        return None
    match = _DISTRIBUTE_X_COUNTERS_AMONG_TARGETS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    reader = count_expression(match.group("expr"))
    if reader is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        _distribute_counters_shares(game, stack_object, kind, reader(game, controller))

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_if_graveyard_count_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_IF_GRAVEYARD_COUNT_RE`'s shape: the controller's own graveyard is
    counted as the clause resolves, and the rest runs only at or above the
    threshold. The rest is any clause `_parse_mixed_clause` reads, optional
    or not (CR 608.2d); fail-closed when it reads nothing."""
    match = _IF_GRAVEYARD_COUNT_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    threshold = parse_count(match.group("n"))
    rest = match.group("rest").strip()
    inner = _parse_optional_mixed_clause(rest, for_spell=for_spell) or _parse_mixed_clause(
        rest, for_spell=for_spell
    )
    inner_clauses: list[TargetedClause] | None = None
    if inner is None:
        # Eye of Jace's own three comma/"and"-joined instructions
        # ("sacrifice this artifact, it deals 2 damage to each opponent,
        # and you gain 2 life") are CR 608.2c's own "in the order written",
        # not one clause `_parse_mixed_clause` can read whole - split and
        # read each the same way a whole ability's own text is.
        rest_clauses = _prepare_effect_clauses(rest)
        if rest_clauses is not None:
            read = [_parse_mixed_clause(part, for_spell=for_spell) for part in rest_clauses]
            if read and all(part is not None for part in read):
                inner_clauses = read  # type: ignore[assignment]
        if inner_clauses is None:
            # Eye of Jace's own three-item Oxford-comma list ("sacrifice
            # this artifact, it deals 2 damage to each opponent, and you
            # gain 2 life") - `_CLAUSE_SEPARATOR` never treats a bare comma
            # as a clause boundary (nothing else in the pool needed it to),
            # so every item but the last stays glued together above; split
            # on the list's own comma-plus-optional-"and" grammar instead.
            list_items = [
                item.strip().rstrip(",")
                for item in re.split(r",\s*(?:and\s+)?|\s+and\s+", rest)
                if item.strip().rstrip(",")
            ]
            if len(list_items) > 1:
                read = [_parse_mixed_clause(part, for_spell=for_spell) for part in list_items]
                if all(part is not None for part in read):
                    inner_clauses = read  # type: ignore[assignment]
        if inner_clauses is None:
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if len(game.controller_of(stack_object).graveyard) >= threshold:
            if inner is not None:
                inner(game, stack_object)
            else:
                assert inner_clauses is not None
                for part in inner_clauses:
                    part(game, stack_object)
                    game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def _bounded_revealed_card_matcher(
    quality_text: str | None, bound: int, *, at_least: bool
) -> Callable[[CardState], bool] | None:
    """A predicate for one of `_REVEAL_HAND_CHOOSE_TWO_BOUNDED_CARDS_THEN_
    DISCARD_RE`'s two conjuncts - CR 202.3's mana value bound, and
    `_nonland_or_typed_card_matcher`'s optional quality word (Distended
    Mindbender's own "nonland" on its first conjunct; the second names no
    quality at all, so any card, lands included, may satisfy it) - or `None`
    if the quality word is not one this file reads.
    """
    if quality_text is None:
        quality_matches: Callable[[CardState], bool] = lambda _state: True  # noqa: E731
    else:
        read_quality = _nonland_or_typed_card_matcher(quality_text)
        if read_quality is None:
            return None
        quality_matches = read_quality

    def matches(state: CardState) -> bool:
        if not quality_matches(state):
            return False
        return state.mana_value >= bound if at_least else state.mana_value <= bound

    return matches


_DAMAGE_AMOUNT_TO_RE = re.compile(
    rf"\b(?P<n>{COUNT}) damage to (?P<to>that |target |any )", re.IGNORECASE
)


_ALTERNATIVE_EXTRA_INSTRUCTION_RE = re.compile(
    r",|\band\s+(?:you|it|that|each|its)\b|\bthen\b", re.IGNORECASE
)


def _amount_substituted_base(base_text: str, alternative_text: str) -> str | None:
    """The base instruction with the alternative's damage amounts put in, when
    the alternative is the base again with only the numbers changed and every
    target named back by CR 400.7's "that" - Searing Blaze's landfall "deals
    3 damage to that player or planeswalker and 3 damage to that creature
    instead" over its base "deals 1 damage to target player or planeswalker
    and 1 damage to target creature that player ... controls". The targets
    stay the ones announced (CR 601.2c); only the amounts are replaced
    (CR 614.1a). `None` for any other shape."""
    if re.search(r"\btarget\b", alternative_text, re.IGNORECASE):
        return None
    base_amounts = list(_DAMAGE_AMOUNT_TO_RE.finditer(base_text))
    alternative_amounts = list(_DAMAGE_AMOUNT_TO_RE.finditer(alternative_text))
    if not base_amounts or len(base_amounts) != len(alternative_amounts):
        return None
    if any(found.group("to").lower() != "that " for found in alternative_amounts):
        return None
    if _ALTERNATIVE_EXTRA_INSTRUCTION_RE.search(alternative_text[alternative_amounts[-1].end() :]):
        # The alternative does more than renumber the base (Torch the Tower's
        # "... damage to that permanent and you scry 1"): substituting only
        # the amounts would silently drop that instruction.
        return None
    pieces: list[str] = []
    cursor = 0
    for base, alternative in zip(base_amounts, alternative_amounts, strict=True):
        pieces.append(base_text[cursor : base.start("n")])
        pieces.append(alternative.group("n"))
        cursor = base.end("n")
    pieces.append(base_text[cursor:])
    return "".join(pieces)


#: ", where X is <count>." closing a sentence - the definition CR 107.3c
#: reads off the ability's own text.
_WHERE_X_DEFINITION_RE = re.compile(r",\s*where X is (?P<expr>[^.]+)\.", re.IGNORECASE)


def _carry_where_x_forward(text: str) -> str:
    """`text` with a sentence's "where X is <count>" repeated onto each later
    sentence that uses X without defining it (CR 107.3c, 107.3i: X defined by
    the text has that value everywhere on the object) - Tezzeret, Master of
    the Bridge's "... where X is the number of artifacts you control. You
    gain X life." becomes two sentences each readable on its own. Returned
    unchanged when there is nothing to carry."""
    sentences = re.split(r"(?<=\.)\s+", text.strip())
    expression: str | None = None
    carried: list[str] = []
    for sentence in sentences:
        defined = _WHERE_X_DEFINITION_RE.search(sentence)
        if defined is not None:
            expression = defined.group("expr").strip()
        elif expression is not None and re.search(r"\bX\b", sentence):
            sentence = re.sub(r"\.?$", f", where X is {expression}.", sentence, count=1)
        carried.append(sentence)
    return " ".join(carried)


def _has_x_in_mana_cost(state: CardState) -> bool:
    """CR 107.3/202.1: whether this card's printed mana cost carries a
    variable ({X}) symbol - Paradox Surveyor's own "a card with {X} in its
    mana cost"."""
    return ManaCost.parse(state.mana_cost or "").x_count > 0


# --------------------------------------------------------------------------
# "the discarded card's mana value" - the card an earlier instruction of the
# same spell or ability discarded (CR 608.2c: later text refers back to what
# earlier text did). Blast of Genius's "Draw three cards, then discard a
# card. Blast of Genius deals damage equal to the discarded card's mana value
# to any target", Spellbound Dragon's "draw a card, then discard a card. This
# creature gets +X/+0 until end of turn, where X is the discarded card's mana
# value". The earlier instructions run through their own readers; the card
# they discarded is the one that newly reached a graveyard or exile (madness,
# CR 702.35a) marked as discarded, and its mana value (CR 202.3; a land's is
# 0, CR 202.3a) is handed to the later sentence as "that number" - the count
# channel (`Game.record_count`) every "that number" reader already reads.
# --------------------------------------------------------------------------

_DISCARDED_CARD_MANA_VALUE_RE = re.compile(r"\bthe discarded card's mana value\b", re.IGNORECASE)
_DISCARDS_A_CARD_RE = re.compile(r"\bdiscards? a card\b", re.IGNORECASE)


def _split_at_discarded_card_value(text: str) -> tuple[str, str] | None:
    """(the instructions that discard, the rest with "that number" for the
    discarded card's mana value), or `None` when `text` is not that shape."""
    whole = " ".join(text.strip().split())
    found = _DISCARDED_CARD_MANA_VALUE_RE.search(whole)
    if found is None:
        return None
    cut = whole.rfind(".", 0, found.start())
    if cut < 0:
        return None
    head, tail = whole[: cut + 1].strip(), whole[cut + 1 :].strip()
    if _DISCARDS_A_CARD_RE.search(head) is None:
        return None
    return head, _DISCARDED_CARD_MANA_VALUE_RE.sub("that number", tail)


def _cards_in_graveyards_and_exile(game: "Game") -> list[CardState]:
    return [card for player in game.players for card in player.graveyard] + list(game.exile)


def _then_with_discarded_card_value(
    head: "Callable[..., None]", tail: "Callable[..., None]"
) -> "Callable[[Game, StackObject], None]":
    """Run `head`, record the mana value of the card it discarded, run `tail`."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        before = {card.id for card in _cards_in_graveyards_and_exile(game)}
        head(game, stack_object)
        discarded = [
            card
            for card in _cards_in_graveyards_and_exile(game)
            if card.id not in before and card.discarded_by is not None
        ]
        game.record_count(int(sum(card.mana_value for card in discarded)))
        tail(game, stack_object)

    return effect


def _readable_effect(effect: object) -> bool:
    return (
        effect is not None
        and not _is_notice_only(effect)
        and getattr(effect, "unparsed_remainder", None) is None
    )


@SPELL_TEXT.rung(
    "s23",
    after=["dispatch.parse_mixed_effect_for_spell", "amounts._parse_where_x_is_pump_spell_text"],
)
def _parse_counted_amount_spell_text(text: str) -> Effect | None:
    """A spell body whose count is printed after the verb, see
    `ep02_r1_counted_permanents.parse_counted_amount_text`."""
    from ..ep02_r1_counted_permanents import parse_counted_amount_text

    return parse_counted_amount_text(text, for_spell=True)


@ABILITY_TEXT.rung("s40", after=["dispatch.parse_mixed_effect"])
def _parse_counted_amount_ability_text(text: str) -> AbilityEffect | None:
    """The ability side of the reader above."""
    from ..ep02_r1_counted_permanents import parse_counted_amount_text

    return parse_counted_amount_text(text, for_spell=False)


@SPELL_TEXT.rung("s21")
def _parse_discarded_card_value_spell_text(text: str) -> Effect | None:
    """The spell side of the banner above."""
    split = _split_at_discarded_card_value(_strip_non_effect_preamble(text))
    if split is None:
        return None
    head_effect = _spell_effect_or_notice(split[0])
    tail_effect = _spell_effect_or_notice(split[1])
    if not (_readable_effect(head_effect) and _readable_effect(tail_effect)):
        return None
    return _then_with_discarded_card_value(head_effect, tail_effect)


@SPELL_TEXT.rung("s23", after=("parse_mixed_effect_for_spell",))
def _parse_where_x_is_pump_spell_text(text: str) -> Effect | None:
    """A non-modal spell's "`<target>` gets +X/+X until end of turn, where X
    is `<count>`" (Allied Assault's "Up to two target creatures each get
    +X/+X until end of turn, where X is the number of creatures in your
    party") read by `_parse_where_x_is_continuous_effect_for_spell`, the
    reader a modal spell's own mode already goes through: X fixed once as
    the spell resolves (CR 608.2h), ahead of the generic layer fallback
    (`continuous._compose_layer_effect_with_remainder`), whose printed-text
    builder has no number for a self-defined X."""
    return _parse_where_x_is_continuous_effect_for_spell(_strip_non_effect_preamble(text))


#: "`<clause using X>` and `<clause using X>`, where X is `<expr>`." - one
#: sentence whose single "where X is" closes the *second* of two "and"-joined
#: instructions (Feast of Flesh's "deals X damage to target creature and you
#: gain X life, where X is 1 plus ..."). CR 107.3c: the definition gives X that
#: value everywhere on the object, but `split_effect_clauses` cuts at the
#: "and" and leaves the first clause with no definition at all (X would read
#: as an undefined 0), so each instruction is handed its own copy.
_WHERE_X_CLOSING_TWO_AND_CLAUSES_RE = re.compile(
    r"^(?P<head>[^.]*?\bX\b[^.]*?)\s+and\s+(?P<tail>(?:you|that player|it)\b[^.]*?\bX\b[^.]*?)"
    r",\s*where X is (?P<expr>[^.]+)\.$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_where_x_shared_by_two_and_clauses_spell_text(text: str) -> Effect | None:
    """The sentence above, rewritten as one "where X is" sentence per
    instruction and read by `parse_mixed_effect_for_spell` like any other."""
    if "where X is" not in text:
        return None
    body = _strip_non_effect_preamble(text)
    if (match := _WHERE_X_CLOSING_TWO_AND_CLAUSES_RE.fullmatch(body.strip())) is None:
        return None
    expr = match.group("expr")
    tail = match.group("tail")
    tail = tail[:1].upper() + tail[1:]
    rewritten = f"{match.group('head')}, where X is {expr}. {tail}, where X is {expr}."
    return parse_mixed_effect_for_spell(rewritten)


#: "`<clause using X>` and `<clause using X>`, where X is `<expr>`." and its
#: three-part serial list "`<clause>`, `<clause>`, and `<clause>`, where X is
#: `<expr>`." - one ability sentence whose single "where X is" closes the last
#: instruction (Arabella, Abandoned Doll's "it deals X damage to each opponent
#: and you gain X life, where X is ..."; Niv-Mizzet, Guildpact's "it deals X
#: damage to any target, target player draws X cards, and you gain X life,
#: where X is ..."). CR 107.3c gives X that value everywhere on the ability,
#: but the clause splitter leaves the earlier parts with no definition at all
#: (an undefined X reads as nothing), so every instruction shares the one.
_INSTRUCTION_SUBJECT = r"(?:you|that player|it|they|target|each|this [a-z]+)\b"
_WHERE_X_CLOSING_LIST_RE = re.compile(
    r"^(?P<first>[^.,]*?\bX\b[^.,]*?)"
    rf"(?:,\s+(?P<second>{_INSTRUCTION_SUBJECT}[^.,]*?\bX\b[^.,]*?),)?"
    rf"\s+and\s+(?P<last>{_INSTRUCTION_SUBJECT}[^.,]*?\bX\b[^.,]*?)"
    r",\s*where X is (?P<expr>[^.]+)\.$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s23")
def _parse_where_x_shared_by_list_ability_text(text: str) -> AbilityEffect | None:
    """The sentence above: X is evaluated once as the ability resolves (CR
    608.2h) and written into each instruction, which is then read as its own
    sentence - an instruction reader may have no "where X" form of its own
    (draw), and a number already in the text is what every one takes."""
    if "where X is" not in text:
        return None
    body = _strip_non_effect_preamble(text)
    match = _WHERE_X_CLOSING_LIST_RE.fullmatch(body.strip())
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None
    parts = [
        match.group(key) for key in ("first", "second", "last") if match.group(key) is not None
    ]

    def written_with(value: int) -> str:
        return " ".join(
            re.sub(r"\bX\b", str(value), part[:1].upper() + part[1:]) + "." for part in parts
        )

    if not _readable_effect(_ability_effect_or_notice(written_with(2))):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        value = max(reader(game, ability.controller, source, ability.x_value or 0), 0)
        resolved = _ability_effect_or_notice(written_with(value))
        if resolved is not None:
            resolved(game, ability)

    return effect


@ABILITY_TEXT.rung("s23")
def _parse_discarded_card_value_ability_text(text: str) -> AbilityEffect | None:
    """The ability side of the banner above (a triggered or activated
    ability's own effect)."""
    split = _split_at_discarded_card_value(_strip_non_effect_preamble(text))
    if split is None:
        return None
    head_effect = _ability_effect_or_notice(split[0])
    tail_effect = _ability_effect_or_notice(split[1])
    if not (_readable_effect(head_effect) and _readable_effect(tail_effect)):
        return None
    return _then_with_discarded_card_value(head_effect, tail_effect)


from ._common import (  # noqa: E402
    _COLOR_WORD_TO_COLOR,
    _MANA_SYMBOL_RE,
    _OBJECT_CHARACTERISTIC_RE,
    _SOURCE_CHARACTERISTIC_RE,
    _THEY_CONTROL_RE,
    _WHERE_X_IS_INLINE_RE,
    _YOU_OR_YOUR_RE,
    LayerRemainderNotice,
    UnmodeledTriggerEffectNotice,
    _card_description_is_readable,
    _nonland_or_typed_card_matcher,
    _opponents,
    _parse_card_group_qualifier,
    _parse_mass_type_qualifier,
    _permanent_id_and_name,
    _prepare_effect_clauses,
    _quality_matcher,
    _targets_understood,
)
from .continuous import (  # noqa: E402
    _cast_trigger_record,
    _defender_of_controllers_attack,
    _mass_creature_group_targets,
    _run_mass_pump,
    _with_unparsed_remainder,
    continuous_effects,
    layer_context_for,
)
from .counters import _counter_kind, _distribute_counters_shares  # noqa: E402
from .damage import (  # noqa: E402
    _deal_all,
    _deal_divided_damage_shares,
    _lethal_amount_before_damage,
    _resolve_bite_damage,
    _resolving_source,
    card_types_among_spells_cast_reader,
)
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _spell_effect_or_notice,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .draw_discard import _source_characteristic  # noqa: E402
from .modal import _parse_optional_mixed_clause  # noqa: E402
from .removal import _destroy_matching  # noqa: E402
from .text import (  # noqa: E402
    _plain_resolution_sentences,
    _read_type_word_list,
    _referent_of_it,
    _singular_card_type,
    _singular_subtype_for_count_expression,
    _strip_non_effect_preamble,
)
from .tokens import (  # noqa: E402
    _is_notice_only,
    _parse_generic_token_descriptor,
    _parse_token_clause,
)

# --------------------------------------------------------------------------
# EP-02 R1 T5: instructions whose amount is a count of cards in a graveyard.
# The parsers live in `machines/ep02_r1_graveyard_counts.py` beside the
# reader; each ladder gets one rung here, gated on the word "graveyard".
# --------------------------------------------------------------------------


@MIXED_CLAUSE.rung("s37", for_spell=FORWARD)
def _parse_graveyard_count_instruction_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Life change, mill, counters or mana scaled by a graveyard count."""
    return parse_graveyard_count_clause(clause, for_spell=for_spell)


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_graveyard_count_spell_text(effect_text: str) -> Effect | None:
    """Spell sentences the clause splitter would cut across (an "and" pair
    sharing one X, a search limited by a count, a pump plus a counted extra)."""
    return (
        parse_search_value_at_most_count_spell(effect_text)
        or parse_damage_pair_where_x_spell(effect_text)
        or parse_pump_then_additional_per_count_spell(effect_text)
        or parse_hand_difference_spell(effect_text)
        or parse_search_target_library_and_exile(effect_text)
        or parse_return_half_permanents_spell(effect_text)
    )


@ABILITY_TEXT.rung("s23")
def _parse_graveyard_count_ability_text(effect_text: str) -> AbilityEffect | None:
    """The ability side of `_parse_graveyard_count_spell_text`, and tokens that
    enter tapped and attacking per counted card."""
    return (
        parse_search_value_at_most_count_ability(effect_text)
        or parse_damage_pair_where_x_ability(effect_text)
        or parse_pump_then_additional_per_count_ability(effect_text)
        or parse_tapped_attacking_tokens_for_each_ability(effect_text)
        or parse_mill_by_stat_then_return_self_and_milled(effect_text)
    )


# --------------------------------------------------------------------------
# EP-02 R2 T2: "defending player <verb> ..." - any per-player clause run
# against the attacker's defending player.
# --------------------------------------------------------------------------


@MIXED_CLAUSE.rung("s37", for_spell=FORWARD)
def _parse_defending_player_instruction_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`parse_defending_player_clause`'s shape, gated on the literal subject."""
    return parse_defending_player_clause(clause, for_spell=for_spell)


@MIXED_CLAUSE.rung("s37", for_spell=FORWARD)
def _parse_attached_pump_until_end_of_turn_instruction_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`parse_attached_pump_until_end_of_turn_clause`'s shape, on an ability."""
    return parse_attached_pump_until_end_of_turn_clause(clause, for_spell=for_spell)


@MIXED_CLAUSE.rung("s37", for_spell=FORWARD)
def _parse_hand_rule_instruction_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """A hand-size rider or a free cast of any number of spells from the hand
    (Jin-Gitaxias // The Great Synthesis' chapters I and III)."""
    return parse_no_maximum_hand_size_while_controlling_clause(
        clause, for_spell=for_spell
    ) or parse_cast_any_number_from_hand_free_clause(clause, for_spell=for_spell)
