import functools
import re
from collections.abc import Callable, Iterable
from enum import StrEnum
from types import FunctionType
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import UUID

from pydantic import ConfigDict

from ...data.subtypes import subtype_vocabulary
from ...models.card import Color, Supertype, Type
from ...models.card_state import (
    CardState,
)
from ...models.player import Player
from ...models.zone import Zone
from ...numbers import (
    AMOUNT,
    COUNT,
    ORDINAL,
    Quantity,
    QuantitySource,
    count_pattern,
    where_x_pattern,
)
from ...snapshot import EngineModel
from ..abilities import (
    KEYWORD_ABILITY_NAMES,
    self_normalized_effect_text,
)
from ..delayed import (
    ANAPHORIC_TIMING_STEPS,
)
from ..layers import (
    Characteristics,
)
from ..modes import (
    is_modal_text,
)
from ..targeting import (
    COMPARISON_CLAUSE_PATTERN,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject


Effect = Callable[["Game", CardState], None]
AbilityEffect = Callable[["Game", AbilityOnStack], None]
#: One clause of a targeted effect, generic over what is resolving: a spell
#: names itself, a triggered or activated ability names the `AbilityOnStack` -
#: `Game.resolve_targets`/`Game.controller_of` already take either, so one
#: function serves both `Effect` and `AbilityEffect`.
TargetedClause = Callable[["Game", "StackObject"], None]


def _fresh_copy(reading: Any) -> Any:
    """A new function object sharing `reading`'s code, cells, defaults and
    attributes - a closure a reader built inside its own body
    (`<locals>` in its qualified name). Anything else (a module-level
    sentinel, whose identity callers compare) is handed back as is."""
    if not isinstance(reading, FunctionType) or "<locals>" not in reading.__qualname__:
        return reading
    clone = FunctionType(
        reading.__code__,
        reading.__globals__,
        reading.__name__,
        reading.__defaults__,
        reading.__closure__,
    )
    clone.__kwdefaults__ = reading.__kwdefaults__
    clone.__qualname__ = reading.__qualname__
    clone.__module__ = reading.__module__
    clone.__doc__ = reading.__doc__
    clone.__dict__.update(reading.__dict__)
    return clone


class memoised_reading[T]:  # noqa: N801 - used as a decorator
    """Memoise a text reader on the (pure) text it was handed.

    The pool prints the same sentence on many cards and a reading walks the
    reader's whole dispatch ladder. Every call still gets its own function
    object (`_fresh_copy`), which is what `unparsed_remainder`'s walk limit
    and `same_closure` count on; the code and cells underneath are shared.
    `cache_clear`/`cache_info` mirror a `functools` cache so the support
    oracle's cold-pass test can reset it.
    """

    def __init__(self, reader: Callable[[str], T | None]) -> None:
        self._reader = reader
        self._readings: dict[str, T | None] = {}
        # Instance attributes, not methods: the cold-pass test's cache walk
        # clears every module-level object that has both, and must find this
        # memo's instances, not the class.
        self.cache_clear = self._readings.clear
        self.cache_info = self._readings.__len__
        functools.update_wrapper(self, reader)

    def __call__(self, text: str) -> T | None:
        if text in self._readings:
            reading = self._readings[text]
            return None if reading is None else _fresh_copy(reading)
        reading = self._reader(text)
        self._readings[text] = reading
        return reading


class memoised_clauses:  # noqa: N801 - used as a decorator
    """`memoised_reading` for a clause-list reader taking `for_spell`: the
    (pure) text and flag key the memo, and every caller gets its own list."""

    def __init__(self, reader: Callable[..., list[TargetedClause] | None]) -> None:
        self._readings: dict[tuple[str, bool], tuple[TargetedClause, ...] | None] = {}
        self._reader = reader
        self.cache_clear = self._readings.clear
        self.cache_info = self._readings.__len__
        functools.update_wrapper(self, reader)

    def __call__(self, text: str, *, for_spell: bool) -> list[TargetedClause] | None:
        key = (text, for_spell)
        if key not in self._readings:
            read = self._reader(text, for_spell=for_spell)
            self._readings[key] = None if read is None else tuple(read)
        stored = self._readings[key]
        return None if stored is None else list(stored)


def computed_permanents(
    game: "Game",
    permanents: Iterable[CardState],
    predicate: Callable[[Characteristics], bool],
) -> list[CardState]:
    """Every permanent in `permanents` whose *computed* characteristics satisfy
    `predicate` - the one way this module is allowed to select battlefield
    permanents by what they are.

    `CardState.types`, `.subtypes`, `.supertypes`, `.colors` and `.mana_value`
    are CR 613.1's *starting point*: "the values of the characteristics printed
    on that card", read off whichever face is up (CR 712.8d). They are not the
    object's characteristics. CR 613.5 has the layer system applied
    "continually and automatically", so a land animated by earthbend (CR
    701.66a) is a creature by CR 613.1d's layer 4 - "in addition to its other
    types", CR 205.1b - with mana value 0, since CR 202.3a gives an object with
    no mana cost mana value 0. Filtering that board on the printed reads walks
    straight past it, which is exactly how Wrath of the Skies used to spare an
    animated land it should have swept.

    `Game.characteristics_of` recomputes the whole board per call (deliberately
    - see its docstring on what "continually" means), so a filter over N
    permanents that called it N times would run the layer stack N times. One
    `computed_board()` is taken here and every candidate read out of it, which
    is also what makes the whole filter see one consistent board rather than N
    successive ones.

    Only for permanents. `ComputedBoard.of` raises `KeyError` for anything not
    on the battlefield, and correctly so: no continuous effect reaches a card
    in a hand, graveyard, library or exile, so the printed read is the only
    answer there is for those and remains the right one.
    """
    board = game.computed_board()
    return [permanent for permanent in permanents if predicate(board.of(permanent))]


def _effect_condition_is_readable(condition: str, *, allow_anaphor: bool = False) -> bool:
    """`condition_is_readable` for a resolving effect's own "if" (CR 608.2c):
    a clause the shared condition readers claim only through an anaphor
    ("if it's a creature", "if that creature is a Bear") is refused unless
    `allow_anaphor` says the caller can actually resolve it.

    A spell's resolving effect has no such anaphor to offer - the object an
    anaphor there would name is whatever an *earlier instruction of that
    same effect* chose (a target, a revealed card), which `Game.
    condition_holds` has no way to know (`machines/conditions/objects.
    names_an_anaphor`) - so `allow_anaphor` stays `False` there. A
    *triggered* ability's own rider is different: CR 603.2's trigger event
    is already carried on `AbilityOnStack.event`, and `Game.condition_
    holds`'s own `event`/`ability` parameters exist for exactly this -
    Aunt May's own "Whenever another creature you control enters, you gain
    1 life. If it's a Spider, put a +1/+1 counter on it." reads "it" as the
    creature that entered, the trigger's own subject, not a spell's."""
    from ...models.game import builtin_condition_readable, condition_is_readable
    from ..conditions.objects import names_an_anaphor

    if not condition_is_readable(condition):
        return False
    if allow_anaphor:
        return True
    return builtin_condition_readable(condition.strip().rstrip(".").strip()) or not (
        names_an_anaphor(condition)
    )


_COLOR_LETTERS: tuple[str, ...] = ("W", "U", "B", "R", "G")


#: `(game, controller, object the counters go on, X) -> int`: one amount, read
#: at the moment the effect or replacement applies.
AmountReader = Callable[["Game", str, CardState | None, int], int]


#: "its power"/"its toughness" or "this creature's power"/"this permanent's
#: toughness" - a term naming the object the expression is being evaluated
#: for (Heroes' Bane's own "Put X +1/+1 counters on this creature, where X is
#: its power", Ouroboroid's "... on each creature you control, where X is
#: this creature's power"). Both point at the ability's own source, never a
#: different referent - `_read_referent_power_expression`/`_is_referent_
#: power_expression` above are the narrower "that <type>'s power" shape read
#: off a *different* object a clause names, which this is not.
#: "loyalty" is Nissa, Ascended Animist's own "where X is Nissa's loyalty"
#: (the name already rewritten to "this permanent" by
#: `self_normalized_effect_text`): CR 306.5c's loyalty is the planeswalker's
#: loyalty counters on the battlefield, and CR 608.2h's last known
#: information once it has left.
#: "its"/"this `<noun>`'s" power/toughness/loyalty, or a gendered pronoun
#: standing in for the same self-reference (CR 201.5, Iron Fist, Living
#: Weapon's own "damage equal to his power" - `legendary_self_pronoun_
#: normalized`'s own vocabulary, widened here since a quoted ability text
#: granted onto another permanent (`grant_ability`) is read back through
#: `amount_expression` directly rather than through that normalizer, which
#: only ever runs once, on the *printed* card text, before the quote marks
#: around the granted ability's own text are ever separated out).
_OBJECT_CHARACTERISTIC_RE = re.compile(
    r"^(?:its|his|her|this [a-z]+'s) (?P<characteristic>power|toughness|loyalty)$", re.IGNORECASE
)


class UnreadableCounterAmountNotice(EngineModel):
    """Counters whose "equal to `<expr>`" amount could not be evaluated.

    Recorded instead of placing a guessed number: the counters are not placed
    at all (a fail-closed skip), and this names the expression nobody read.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    expression: str


#: CR 105.1's five colors, spelled the way "your devotion to `<color>`" prints
#: them, to `Color`'s own single-letter enum value.
_COLOR_WORD_TO_COLOR: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


#: "this creature's power" / "this permanent's toughness" (a card's own name
#: already rewritten, CR 201.5) - the source's own characteristic as the
#: ability resolves (CR 608.2h), or as it last existed on the battlefield
#: if it has left.
_SOURCE_CHARACTERISTIC_RE = re.compile(
    r"^this (?:creature|permanent)'?s (?P<characteristic>power|toughness)$", re.IGNORECASE
)


#: ", where X is <expression>" wherever it sits in the sentence, rather than
#: only at the very end the way `_WHERE_X_IS_RE` above reads it for a mass
#: pump. Jolrael, Voice of Zhalfir prints another sentence *after* it: "up to
#: one target land you control becomes an X/X green and blue Bird creature
#: with flying and haste until end of turn, where X is the number of cards in
#: your hand. It's still a land." - so an end-anchored read finds nothing and
#: the whole animation falls through every parser in this file.
_WHERE_X_IS_INLINE_RE = re.compile(r",\s*where x is (?P<expr>[^.]+)", re.IGNORECASE)


class _CreatureRider(NamedTuple):
    """`_RETURN_CREATURE_RIDER_RE` read: P/T, creature types, the extra card
    types named, keywords, and whether "in addition to its other types"."""

    power: int
    toughness: int
    subtypes: tuple[str, ...]
    types: tuple[Type, ...]
    keywords: tuple[str, ...]
    in_addition: bool


# --------------------------------------------------------------------------
# What abilities do (CR 608.2 resolution, for objects that are not cards)
# --------------------------------------------------------------------------


def _opponents(game: "Game", username: str) -> list:
    return [player for player in game.players_in_game if player.username != username]


#: "[You may|Its controller may] search your[/their] library for a[n]
#: <quality> card[ with mana value N or less][, reveal it], put it/that card
#: into your hand OR onto the battlefield [tapped][, then shuffle]." - the
#: shape shared by every fetchland, Flagstones of Trokair's death trigger,
#: Expedition Map, Ghost Quarter and White Orchid Phantom's second half (the
#: *subject* is "its controller", not "you" - CR 701.23g's search is offered
#: to whichever player the sentence names), and Ranger-Captain of Eos (the
#: mana-value bound). `fullmatch` is deliberate: a card whose search is
#: followed by more text of its own - Nahiri, the Harbinger's -8 goes on to
#: grant haste and bounce the card it found - does not match, and falls
#: through to no scripted effect rather than a half-right one. The trailing
#: "then shuffle" is optional here because a clause reaching this regex from
#: the multi-clause dispatcher has already had its "then shuffle" tail
#: reattached by `_rejoin_search_clauses` - the group still has to be
#: *readable*, just not mandatory at the regex level.
#: One or more printed mana costs joined the way rules text lists them:
#: "{0} or {1}", "{1}, {2}, or {3}". Each cost is a run of mana symbols.
_MANA_COST_LIST = r"(?:\{[^}\s]+\})+(?:(?:,? or|,) (?:\{[^}\s]+\})+)*"


#: "with a mana ability" / "with <keyword>[ or <keyword>]" after the word
#: "card" - a quality the card *has* rather than a type it is. Waterlogged
#: Teachings' and Mystical Teachings' "a card with flash" (CR 702.8a's flash
#: is a keyword the card has in its library), Moonsilver Key's "an artifact
#: card with a mana ability" (CR 605.1). Only CR 702's own keyword names are
#: offered (`KEYWORD_ABILITY_NAMES`), longest first so "flashback" is never
#: read as "flash" plus leftover letters; any other "with ..." phrase still
#: does not match here and stays with whichever reader owns it.
_KEYWORD_NAME_ALTERNATION = "|".join(
    re.escape(name) for name in sorted(KEYWORD_ABILITY_NAMES, key=len, reverse=True)
)
_HAVING_PATTERN = (
    r"a mana ability|(?:" + _KEYWORD_NAME_ALTERNATION + r")"
    r"(?:,? or (?:" + _KEYWORD_NAME_ALTERNATION + r"))*"
)


_SEARCH_AND_PUT_RE = re.compile(
    # "Its controller may search ..." is deliberately not an alternative here
    # any more - that subject names a different player than whoever controls
    # the resolving spell or ability, and `_parse_anaphoric_clause_pair` reads
    # it off the *previous* clause's target instead of off this one's own
    # "subject" group (see that function and `_search_and_place_for`).
    r"(?P<subject>you may )?"
    # The count slot: CR 701.23d's plain "a card"/"three cards" (a quantity
    # with no printed maximum, which must be found - "must find that many
    # cards" - as many as possible when the library falls short) and CR
    # 701.23b's "up to N" (a stated-quality search, which never has to find
    # anything). `{COUNT}` never matches a bare "X": a cast-announced X
    # (CR 107.3a, Weird Harvest's own {X} in its mana cost) is substituted to
    # a digit by `effect_for` before a second parse attempt ever reaches this
    # regex - see that function's own docstring - so a literal "X" surviving
    # to here would be CR 107.3f's self-defined kind this wave does not read,
    # and failing to match at all (rather than matching and then failing to
    # read the count) is what lets that retry happen at all. "up to that
    # many" (The Earth King) is a count carried from an earlier instruction
    # or the trigger event, read through the count channel (`that_many`).
    #
    # `n_x` is the one case a bare "X" *does* match at this level: CR 107.3f's
    # own self-defined X, spelled out in a trailing "where X is <expr>"
    # clause (`where_x_pattern()` below) rather than announced by the cost -
    # Harvest Season's own "up to X basic land cards, where X is the number
    # of tapped creatures you control". `_read_search_count` refuses this
    # one too when `where_x` came back empty (a bare X with no definition
    # anywhere is CR 107.3a's kind, which the substitution retry above still
    # owns), so a card whose cost genuinely announces X is unaffected: the
    # unsubstituted pass still reads nothing here and the retry still runs.
    r"search (?:your|their) library for "
    # CR 107.1c's "any number of" (Nissa, Who Shakes the World's -8, Sarkhan
    # Unbroken's -8) is a count with no ceiling but the library itself;
    # `_read_search_count` reads it as the library's size at resolution, and
    # CR 701.23b already lets the searcher stop anywhere from zero up.
    rf"(?:(?P<any_number>any number of )|(?P<upto>up to )?(?:(?P<n>{COUNT})|(?P<n_x>[xX])"
    r"|(?P<that_many>that many)) )"
    # The quality is optional: CR 701.23d names "a card" as its own kind of
    # search - "If a player is searching a hidden zone simply for a quantity of
    # cards, such as 'a card' or 'three cards,' that player must find that many
    # cards" - so Ayara's Oathsworn's "search your library for a card" is not a
    # phrase with a missing restriction, it is a search with no restriction at
    # all. `_search_and_place_for` reads a `None` quality as "every card
    # qualifies".
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    # "a Room card that doesn't have the same name as a Room you control"
    # (Central Elevator // Promising Stairs, CR 201.2a's "two objects have the
    # same name" test) - CR 701.23a's own "description" a search may name
    # narrows to exclude candidates sharing a name with something the
    # searcher already controls of the stated type. Read generally (any
    # `<type-word> you control`), not gated to Rooms specifically, so any
    # future search naming a different type the same way is covered too.
    r"(?: that (?:doesn't|don't) have the same name as (?:a|another) "
    r"(?P<unique_word>[A-Za-z]+) you control)?"
    r"(?P<basic_land_type> with a basic land type)?"
    # "with mana value N or less" (Ranger-Captain of Eos's ceiling) or "with
    # mana value N or greater" (Fierce Empath's/Treasure Mage's floor) - CR
    # 202.3's number, bounded either direction the same way `_HAND_EXILE_RE`'s
    # imprint quality already is (`_hand_exile_mv_matcher`).
    r"(?: with mana value (?P<max_mv>\d+) or (?P<mv_cmp>less|greater))?"
    # "with mana cost {0} or {1}" (Urza's Saga chapter III) names printed
    # mana costs, not mana values: CR 202.1 makes a mana cost the mana
    # symbols, so {X} (mana value 0 in a library, CR 202.3e) is neither, and
    # CR 202.1b's "no mana cost" is not {0}. Read by `_exact_mana_cost_matcher`.
    r"(?: with mana cost (?P<mana_costs>"
    + _MANA_COST_LIST
    + r"))?"
    # "card with flash" / "card with a mana ability" - `_HAVING_PATTERN`.
    + r"(?: with (?P<having>"
    + _HAVING_PATTERN
    + r"))?"
    # Harvest Season's own X-defining tail, read the same way `_SCRY_RE`/
    # `_SURVEIL_RE` already read theirs, through `count_expression`. Not
    # `where_x_pattern()` itself: its capture is greedy, and Prismatic
    # Undercurrents' own rejoined "..., where X is `<expr>`, reveal those
    # cards, put them into your hand, then shuffle" gives a greedy `[^.]+`
    # nothing to stop at before the mandatory ", put ..." near the very end,
    # so it swallowed the optional "reveal" clause right along with the
    # expression - `count_expression` then failed on the run-together text
    # and the whole search fell back to a notice. A non-greedy capture finds
    # the expression's true end at the first point the rest of this pattern
    # can still match, which is exactly the boundary CR 608.2c's own
    # instruction actually falls on, whether or not a "reveal" clause follows.
    + r"(?:,\s*where\s+[xX]\s+is\s+(?P<where_x>[^.]+?))?"
    +
    # CR 701.23e: a printed reveal is a real reveal. "reveal it"/"them"
    # (Expedition Map, Primeval Titan) and "reveal that card"/"those cards"
    # (Trinket Mage, Tooth and Nail) are the same instruction, singular or
    # plural.
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?"
    r", put (?:it|them|that card|those cards) "
    r"(?P<dest>into your hand|into your graveyard|onto the battlefield(?P<tapped> tapped)?)"
    r"(?:, then shuffle)?\.?",
    re.IGNORECASE,
)


#: CR 105.2a "A monocolored object is exactly one of the five colors." and
#: CR 105.2b "A multicolored object is two or more of the five colors." - a
#: color *count*, not a color, so they sit beside `_HAND_EXILE_COLOR_WORDS`
#: rather than in it ("colorless", CR 105.2c, is already there). Glittering
#: Wish's "a multicolored card" is the printed shape.
_COLOR_COUNT_WORDS: dict[str, Callable[[int], bool]] = {
    "monocolored": lambda count: count == 1,
    "multicolored": lambda count: count >= 2,
}


def _historic(state: CardState) -> bool:
    """CR 700.6: "The term historic refers to an object that has the legendary
    supertype, the artifact card type, or the Saga subtype."

    Read off the computed characteristics on `CardState`, not off `Card`, so a
    permanent that gained the artifact type or the legendary supertype from a
    continuous effect counts, exactly as CR 700.6 describes an *object*.
    """
    return (
        Supertype.LEGENDARY in state.supertypes
        or Type.ARTIFACT in state.types
        or any(subtype.lower() == "saga" for subtype in state.subtypes)
    )


def _quality_matcher(quality: str) -> Callable[[CardState], bool]:
    """A predicate for "a `<quality>` card" out of a search sentence.

    "Basic land" adds CR 205.4c's supertype check on top of whatever the rest
    of the phrase already means. Anything else is one or more type/subtype
    words (each optionally qualified by a color, see `_quality_word_matcher`)
    joined by "or" or a comma - fetchlands print two, Flagstones one - and
    matching any one of them is enough, the same "or" the card prints.

    "Historic" is CR 700.6's own term - "The term historic refers to an object
    that has the legendary supertype, the artifact card type, or the Saga
    subtype" - one word standing for three unrelated checks, which is why it
    cannot be spelled as a type word. Monumental Henge prints it, with the
    rule paraphrased in its own reminder text.

    **A list made entirely of negations is a conjunction, not a disjunction.**
    Narset, Parter of Veils' "a noncreature, nonland card" means a card that
    is neither, and reading its comma as "or" would qualify every card in the
    game (a creature is nonland; a land is noncreature) - a fails-open answer,
    not merely a missed one. That is De Morgan on the positive phrase the card
    is negating ("creature or land"), so nothing about the "or" reading for
    positive words changes.
    """
    lowered = quality.strip().lower()
    if lowered.startswith("nonland "):
        # ecl-T8: Ajani, Outland Chaperone's own "nonland permanent cards
        # with mana value 3 or less" - CR 109.2's negation of CR 205.2a's
        # land card type, stacked on the rest of the phrase the identical
        # way "basic "/"snow "/"legendary " already do below.
        rest = _quality_matcher(lowered.removeprefix("nonland "))

        def nonland_matches(state: CardState) -> bool:
            return rest(state) and Type.LAND not in state.types

        return nonland_matches
    if lowered.startswith("basic "):
        rest = _quality_matcher(lowered.removeprefix("basic "))

        def basic_matches(state: CardState) -> bool:
            return rest(state) and Supertype.BASIC in state.supertypes

        return basic_matches
    # CR 205.4g: "Any permanent with the supertype 'snow' is a snow
    # permanent" - Glacial Revelation's own "snow permanent card". The
    # supertype check stacks on whatever the rest of the phrase already
    # means, the same way "basic " does above.
    if lowered.startswith("snow "):
        rest = _quality_matcher(lowered.removeprefix("snow "))

        def snow_matches(state: CardState) -> bool:
            return rest(state) and Supertype.SNOW in state.supertypes

        return snow_matches
    # CR 205.4a's legendary supertype, stacked on the rest of the phrase the
    # identical way "basic "/"snow " already do - Sisay, Weatherlight
    # Captain's own "a legendary permanent card" needs both halves at once
    # ("permanent" alone is CR 110.4a's six-type umbrella `_named_type_
    # matcher` already reads for a bare "permanent card"; "legendary" alone
    # was already readable as one word, but "legendary permanent" is two
    # words with no comma/"or" between them to split on, so it never reached
    # `_named_type_matcher` as either word on its own). Gated on there being
    # no comma/" or " anywhere in the phrase: Nashi, Searcher in the Dark's
    # own "legendary or enchantment" is a genuine two-word *disjunction*
    # ("legendary" is already one whole alternative on its own, CR 205.4a) -
    # `lowered.startswith("legendary ")` is true for that phrase too, and
    # stacking it onto "or enchantment" as though "or" were a noun instead of
    # letting the split below read "legendary" and "enchantment" as the two
    # separate alternatives they are broke that card's own reading.
    if lowered.startswith("legendary ") and not re.search(r",|\bor\b", lowered):
        rest = _quality_matcher(lowered.removeprefix("legendary "))

        def legendary_matches(state: CardState) -> bool:
            return rest(state) and Supertype.LEGENDARY in state.supertypes

        return legendary_matches
    if lowered == "historic":
        return _historic
    # "artifact, instant, or sorcery" (Bilbo, Thief in the Night): the Oxford
    # comma's ", or" is one separator, not a comma then an "or sorcery" word.
    words = [word.strip() for word in re.split(r",\s*(?:or\s+)?|\s+or\s+", lowered) if word.strip()]
    matchers = [_quality_word_matcher(word) for word in words]
    if len(words) > 1 and all(word.startswith("non") for word in words):

        def matches_none_of(state: CardState) -> bool:
            return all(matcher(state) for matcher in matchers)

        return matches_none_of

    def matches(state: CardState) -> bool:
        return any(matcher(state) for matcher in matchers)

    return matches


#: "or a" / "or an" between two whole card descriptions - Starfield
#: Shepherd's "a basic Plains card or a creature card with mana value 1 or
#: less". The article is what tells it apart from a list of types inside one
#: description ("a Mountain or Plains card"), which never repeats it.
_SEARCH_DESCRIPTION_JOIN_RE = re.compile(r"\s+or\s+an?\s+", re.IGNORECASE)


def _card_description_is_readable(quality: str) -> bool:
    """Whether `_quality_matcher` reads every word of one description's
    quality, following its own shapes word for word: a "basic " prefix,
    "historic" (CR 700.6), and a comma/"or" list of words, each a type word
    or one carrying a color or color-count adjective. A word it cannot read
    makes it match nothing, which is a search that silently finds nothing -
    this is what sends such a search to a notice instead."""
    lowered = quality.strip().lower()
    if lowered.startswith("basic "):
        return _card_description_is_readable(lowered.removeprefix("basic "))
    # "nonland permanent card" (Guardian Sunmare): `_quality_matcher` stacks
    # the negation on the rest of the phrase, so the rest is what must read.
    if lowered.startswith("nonland ") and not re.search(r",|\bor\b", lowered):
        return _card_description_is_readable(lowered.removeprefix("nonland "))
    # CR 205.4g/205.4a's "snow "/"legendary " prefixes stack on the rest of
    # the phrase exactly as `_quality_matcher` already reads them (see that
    # function's own docstring) - a search whose matcher can read "legendary
    # creature card" perfectly well was being sent to `NOTICE` anyway because
    # only this readability pre-check had never learned the same two
    # prefixes, which is what sent The Arkenstone // Seek the Heart's "Search
    # your library for a legendary creature card" to `search_description_
    # notice_only` even though the search itself already worked.
    if lowered.startswith("snow "):
        return _card_description_is_readable(lowered.removeprefix("snow "))
    if lowered.startswith("legendary ") and not re.search(r",|\bor\b", lowered):
        return _card_description_is_readable(lowered.removeprefix("legendary "))
    if lowered == "historic":
        return True
    # "artifact, instant, or sorcery" (Bilbo, Thief in the Night): the Oxford
    # comma's ", or" is one separator, not a comma then an "or sorcery" word.
    words = [word.strip() for word in re.split(r",\s*(?:or\s+)?|\s+or\s+", lowered) if word.strip()]
    if not words:
        return False
    for word in words:
        parts = word.split()
        if parts[0] in _COLOR_COUNT_WORDS or parts[0] in _HAND_EXILE_COLOR_WORDS:
            if len(parts) > 2 or (len(parts) == 2 and not _named_type_word_is_readable(parts[1])):
                return False
        elif (
            len(parts) == 2
            and parts[0] in subtype_vocabulary()
            and _named_type_word_is_readable(parts[1])
        ):
            # "`<subtype>` `<type>`" - Sphinx's Approach's own "a Sphinx
            # creature card" (CR 205.3): a printed subtype qualifying a card
            # type, read as a conjunction of the two - the same "adjective
            # then noun" shape the colour branch above already reads,
            # spelled with a subtype instead of a colour.
            continue
        elif len(parts) != 1 or not _named_type_word_is_readable(word):
            return False
    return True


class SearchDescriptionNotice(EngineModel):
    """One library search whose card description this engine cannot read.

    CR 701.23a's search finds "a card that matches the given description", and
    CR 701.23b makes finding nothing a legal answer - so a description read as
    matching nothing is indistinguishable from a real miss. A description
    with a qualifier `_SEARCH_DESCRIPTION_RE` does not take ("a creature card
    with power 5 or greater or a basic land card") is the shape. The search is
    not run at all, and this records why.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The search clause as printed."""


# --------------------------------------------------------------------------
# Putting creature cards onto the battlefield: a mana-value bound read off a
# sacrificed permanent, a look at the top N, a hand, the milled cards
# --------------------------------------------------------------------------

#: "plus the sacrificed `<type>`'s mana value" - the term every bound below
#: adds its printed offset to. Neoform, Prime Speaker Vannifar and Eldritch
#: Evolution print "creature"; Enigmatic Incarnation prints "enchantment";
#: the type is whatever the sacrifice itself was restricted to, so the word is
#: read and not pinned.
_SACRIFICED_MANA_VALUE_TERM = r"plus the sacrificed (?P<noun>[a-z]+)['’]s mana value"


class _PutDescription(NamedTuple):
    """What `_put_description` read: the printed description (for prompts),
    the quality, and the mana-value condition on top of it."""

    text: str
    quality: Callable[[CardState], bool]
    max_mv: int | None
    x_bound: bool
    parity: str | None

    def admits(self, state: CardState, x: float | None = None) -> bool:
        """Whether `state` is such a card - with `x` the value a "where X is
        ..." has fixed (CR 107.3c); an X-bounded description with no X yet
        admits nothing."""
        if not self.quality(state):
            return False
        mana_value = state.mana_value
        if self.max_mv is not None and mana_value > self.max_mv:
            return False
        if self.x_bound and (x is None or mana_value > x):
            return False
        return self.parity is None or (int(mana_value) % 2 == 0) == (self.parity == "even")


# --------------------------------------------------------------------------
# Single-clause player effects, read off the ability's own printed text
# --------------------------------------------------------------------------

#: A clause's effect on one player, once the controller has been worked out -
#: the same shape whether that controller came from a spell (CR 608.2c) or
#: from a triggered or activated ability (CR 603.3a, CR 602.2). `source` is a
#: display name only, passed through to `Game.scry`/`Game.surveil` for their
#: decision prompts.
ClauseEffect = Callable[["Game", Player, str, str | None], None]

# CR 119.3: "If an effect causes a player to gain life or lose life, that
# player's life total is adjusted accordingly." No card in the pool phrases
# this on anyone but "you" without also naming a target ("target player
# loses 1 life" - Blood Artist) or being a cost ("Pay 7 life" is CR 118, not
# an effect) - so only "you" is recognised; a targeted or "each"/"opponent"
# phrasing is deliberately left to the targeted-effects wave.
#: "you gain N life", and "you gain three times X life" (Martyr of Sands) once
#: CR 107.3a's X is substituted - a multiplier on the count, read the same way.
#: "[You may ]play `<n>` additional land(s) this turn." - Way of the
#: Paradox's own granted trigger ("... you gain 1 life. You may play an
#: additional land this turn."). CR 305.2's allowance increase, granted by
#: a *resolving* instruction rather than a permanent's own static ability
#: (`Game.grant_extra_land_play`, the resolved twin of `machines.layers.
#: additional_land_plays`'s static-ability reader) - unconditionally: the
#: printed "may" belongs to the *later* land play (CR 305.1's own ordinary
#: optionality) this grant makes legal, not to a CR 608.2d choice about
#: accepting the grant itself, so the leading "you may " is only ever
#: `_parse_optional_player_clause`'s own generic strip (which this shape
#: also matches with no prefix at all, for a card that ever prints the
#: grant as a plain "You get an additional land drop this turn"-shaped
#: mandatory instruction instead).
_ADDITIONAL_LAND_PLAY_RE = re.compile(
    rf"(?:you may )?play {count_pattern('n', article=True)} additional lands? this turn",
    re.IGNORECASE,
)


#: "they control" / "that player controls" inside a third-person clause's
#: amount - the player the clause is about (the targeted player named at the
#: start of the sentence), rewritten to the "you control"
#: `count_expression` reads for whichever player the amount is asked about.
_THEY_CONTROL_RE = re.compile(r"\b(?:they|that player) controls?\b", re.IGNORECASE)
#: "you"/"your" inside an amount.
_YOU_OR_YOUR_RE = re.compile(r"\byour?\b", re.IGNORECASE)


# CR 701.9a: "To discard a card, move it from its owner's hand to that
# player's graveyard." CR 701.9b: absent an override, the discarding player
# chooses which - Wistfulness's own "draw two cards, then discard a card" is
# exactly this default, unlike Thoughtseize's/Go Blank's own "target player
# discards ..." (`_TARGET_PLAYER_DISCARDS_RE`), which name a *different*
# player than whoever this clause's own `player` argument is. Deliberately
# does not read "you " ahead of "discard" the way `_DRAW_RE` optionally does:
# every printed shape in the pool either says "discard a card" bare (an
# ability's own effect, spoken as an instruction) or "you may discard a
# card" (peeled off by `_parse_optional_player_clause` before this ever
# runs), so there is no "you discard a card" shape left to also match.
#
# "up to `<n>`"/"any number of" - CR 107.1c's own "any positive number or
# zero" - a non-exact discard (`_discard_cards`'s own `exact` argument).
# `_discard_cards` records how many it moved, which a later "that many"
# reads (`that_many`, Group 0b's own count channel, merged since).
#
# `<quality>` (Borborygmos and Fblthp's own "discard any number of land
# cards") is optional and, when printed, any single word `_nonland_or_typed_
# card_matcher`/`_quality_matcher` already read - CR 701.9b's "the affected
# player chooses which card" narrowed to only the cards satisfying it, the
# same restriction `_discard_cards`'s own `predicate` now applies.
_DISCARD_A_CARD_RE = re.compile(
    rf"^discards? (?:(?P<any>any number of)|(?:(?P<upto>up to )?(?P<n>{AMOUNT})))\s+"
    rf"(?:(?P<quality>[a-z]+) )?cards?$",
    re.IGNORECASE,
)


# CR 114.2: "[Player] gets an emblem with [ability]." - Wrenn and Seven's -8
# ("You get an emblem with 'You have no maximum hand size.'"), Kaito, Bane
# of Nightmares' +1 ("You get an emblem with 'Ninjas you control get
# +1/+1.'"), Tamiyo, Inquisitive Student's -7. The quoted ability's own text
# becomes the emblem's own text in the command zone (`Game.create_emblem`),
# where its triggered and static abilities function (CR 114.4); `Player.
# has_no_maximum_hand_size` reads its "no maximum hand size" line.
_GET_AN_EMBLEM_RE = re.compile(
    r"""^(?:you|they) gets? an emblem with ["“](?P<text>.+)["”]\.?$""",
    re.IGNORECASE | re.DOTALL,
)


#: CR 701.25a / CR 701.22a. "Surveil X, where X is `<expr>`" (Cerebral
#: Download) reads `<expr>` through `count_expression`, the same reader
#: `amount_expression`'s own terms already call.
_SURVEIL_RE = re.compile(rf"surveils? (?P<n>{AMOUNT}){where_x_pattern()}", re.IGNORECASE)


#: "shuffle" (Ponder's, Pondering Mage's own "You may shuffle.") or "shuffle
#: your library" - CR 701.24a's action alone, with nothing else attached. A
#: search's own mandatory shuffle reads through `Game.search_library`
#: instead, never through here; this is only the bare, optional verb a "you
#: may" clause wraps (`_parse_optional_player_clause`).
_SHUFFLE_RE = re.compile(r"^shuffle(?: your library)?$", re.IGNORECASE)


_PAY_ANY_AMOUNT_OF_LIFE_RE = re.compile(r"^(?:you may )?pay any amount of life$", re.IGNORECASE)


#: "You may <clause>." (CR 608.2d turned into an optional wave-1 clause). This
#: is checked ahead of the plain shapes above, on the clause *before* the
#: optional wrapper is peeled off - `parse_clause_effect` itself never sees
#: the words "you may", so a bare "you may draw a card" still comes back
#: `None` from it, unchanged.
_YOU_MAY_RE = re.compile(r"^you may (?P<clause>.+)$", re.IGNORECASE | re.DOTALL)


#: Sentence boundaries, and the two joining words CR 608.2c's "in the order
#: written" has to step across: "you gain 1 life and get {E}" (Guide of
#: Souls) and "Scry 2, then draw a card" (Preordain).
_CLAUSE_SEPARATOR = re.compile(r"\.\s+|\n+|,?\s+\bthen\b\s+|\s+\band\b\s+", re.IGNORECASE)


#: "This spell costs {N} less to cast if [condition]." (Mystical Dispute) - a
#: static ability about *announcing* the spell (CR 601.2f), never part of
#: what it does on resolution. This self-referential reduction (as opposed to
#: `machines/cost.cost_modifier_effect`'s board-static "Spells cost {N} more
#: to cast", read off a *different* permanent) is now computed by
#: `Game.cost_reduction_for`/`_COSTS_LESS_IF_TARGETS_SPELL_RE`, opted
#: into by calling `Game.determine_total_cost(casting)` instead of
#: `casting.determine_cost()` directly - the same opt-in shape Emrakul, the
#: Promised End's own graveyard-count reduction already uses. Stripping the
#: sentence here still matters regardless: it keeps this line from being
#: misread as an unparseable resolution clause and taking "Counter target
#: spell unless its controller pays ..." down with it, since this dispatcher
#: only ever reads what a spell *does*, not what it costs.
_SELF_COST_REDUCTION_LINE_RE = re.compile(
    r"^(?:[A-Za-z' ]+ \u2014 )?This spell costs (?:\{[^{}]+\})+ less to cast (?:if|as long as) "
    r"[^.]+\.\s*",
    re.IGNORECASE | re.MULTILINE,
)

#: The other self-discount template, tied to an additional cost rather than a
#: condition - March of Otherworldly Light's "This spell costs {2} less to
#: cast for each card exiled this way." (following its own "As an additional
#: cost to cast this spell, you may exile any number of white cards from your
#: hand." sentence, which `_ADDITIONAL_COST_LINE_RE` already strips). Left
#: unstripped, `split_effect_clauses` reads it as a clause of its own that no
#: shape in this file matches, taking "Exile target artifact, creature, or
#: enchantment with mana value X or less." down with it - the same
#: preamble-poisoning bug `_SELF_COST_REDUCTION_LINE_RE` already fixes for
#: the conditional discount shape. The discount itself is not computed
#: anywhere in this engine (CR 118.8a's additional cost and CR 601.2f's cost
#: reduction are both about *paying*, not resolving) - only this line's
#: effect on an unrelated resolution sentence is fixed here.
_PER_COUNT_COST_REDUCTION_LINE_RE = re.compile(
    # An optional leading ability word (CR 207.2c: no rules meaning of its
    # own) - Rime Chill's and Wildvine Pummeler's own "Vivid — This spell
    # costs {1} less to cast for each color among permanents you control.",
    # stripped the same way `_SELF_COST_REDUCTION_LINE_RE` already tolerates
    # one for its own "if"/"as long as" shape. `\{[xX]|\d+\}` (rather than
    # only digits) also reads Sunderflock's own "costs {X} less to cast,
    # where X is the greatest mana value among Elementals you control." -
    # CR 601.2f's own X reduction, priced by `Game.cost_reduction_for`, never
    # here (this only stops the sentence poisoning `_parse_mixed_clauses`'s
    # per-clause fallback, the same as every other row in this preamble list).
    r"^(?:[A-Za-z' ]+ — )?This spell costs \{(?:[xX]|\d+)\} less to cast"
    r"(?:,? where [xX] is [^.]+| for each [^.]+)\.\s*",
    re.IGNORECASE | re.MULTILINE,
)

#: A third self-discount template, tied to a phase or step rather than a
#: condition or a count - Closing Statement's "This spell costs {2} less to
#: cast during your end step." Left unstripped, this poisoned
#: `_parse_mixed_clauses`'s per-clause fallback exactly the way the two
#: shapes above already document: "Destroy target creature or planeswalker
#: you don't control. Put a +1/+1 counter on up to one target creature you
#: control." reads fine clause by clause, but the whole card came back
#: unparsed because the preamble sentence ahead of it did not. The discount
#: itself is not computed here either, for the identical reason the "if"
#: shape above is not: CR 601.2f's reduction is about paying, not resolving.
_TIMING_COST_REDUCTION_LINE_RE = re.compile(
    r"^This spell costs \{\d+\} less to cast during [^.]+\.\s*", re.IGNORECASE | re.MULTILINE
)

#: The increase twin of the line above - "This spell costs {1} more to cast
#: for each target beyond the first." (Fireball, and Launch the Fleet's
#: identically-worded "Strive — ..." clause; CR 207.2c gives the "Strive"
#: ability word no rules meaning of its own, so the optional em-dash prefix
#: is stripped along with the sentence rather than treated as a separate
#: instruction). `machines/casting.py`'s own `_COST_INCREASE_PER_TARGET_RE`
#: is what actually prices it (CR 601.2f); this is only the same preamble-
#: poisoning fix `_SELF_COST_REDUCTION_LINE_RE` documents - left unstripped,
#: "Fireball deals X damage divided evenly, rounded down, among any number
#: of targets." would be read as the card's *second* clause rather than its
#: only resolving one, and `_parse_mixed_clauses`'s fail-closed-per-clause
#: rule would take it down too. One or more mana symbols
#: (`\{[^}]+\}(?:\{[^}]+\})*`), matching `_COST_INCREASE_PER_TARGET_RE`'s own
#: amount group rather than a single-symbol amount only - Aerial Formation's
#: off-pool "costs {2}{U} more" is the multi-symbol proof this generalises
#: past Fireball's/Launch the Fleet's own single generic {1}.
_COST_INCREASE_PER_TARGET_LINE_RE = re.compile(
    r"^(?:Strive\s*—\s*)?This spell costs \{[^}]+\}(?:\{[^}]+\})* more to cast for each "
    r"target beyond the first\.\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _prepare_effect_clauses(text: str) -> list[str] | None:
    """`text`, refused outright if modal (CR 700.2) and otherwise stripped of
    its non-effect preamble (CR 118.8a's additional cost line, "This spell
    can't be countered"), split into CR 608.2c clauses, and rejoined where a
    search's own "then shuffle" was cut apart from it - see
    `_rejoin_search_clauses`.

    Shared by the targeted clause parser, the player clause parser, and the
    mixed dispatcher below so all three refuse and strip and rejoin the same
    way. Before this was shared, only the targeted path bailed on a modal card
    - a modal card whose every mode happened to be a plain player clause
    (gain life, draw, ...) would have `split_effect_clauses` cut straight
    across the bullet points and run every mode as if it were one linear
    effect, which is a fails-open bug, not merely a missed one. Cathartic
    Reunion is the other half of the fix: its additional-cost line was being
    read as an unparseable effect clause and taking the whole thing down, when
    the cost is not part of resolution at all (CR 118.8a).
    """
    prepared = _prepared_effect_clauses(text)
    return None if prepared is None else list(prepared)


@functools.lru_cache(maxsize=16384)
def _prepared_effect_clauses(text: str) -> tuple[str, ...] | None:
    """`_prepare_effect_clauses`' answer, memoised per text as a tuple - the
    support oracle asks it of one text once per `_unreadable_*` probe."""
    if is_modal_text(text):
        return None
    clauses = _rejoin_search_clauses(split_effect_clauses(_strip_non_effect_preamble(text)))
    return tuple(clauses) or None


# --------------------------------------------------------------------------
# Single-clause TARGETED effects, read off the ability's own printed text
# --------------------------------------------------------------------------
#
# The targeted twin of the parser above: "Destroy target creature.", "Exile
# target artifact.", "<Source> deals N damage to target X." (and "to any
# target"), "Return target X to its owner's hand.", "Tap"/"Untap target X.",
# and "Put N +1/+1 (or -1/-1) counters on target X." One restriction ("target
# X") per clause. Destroy, exile, return, tap/untap, and put-counters accept
# CR 115.6's "up to N"/"N or M target ..." too, because the verb repeats
# itself once per legal target regardless of how many there are - `deal_damage`
# is the one exception, kept to exactly one mandatory target, because multiple
# damage targets divide a total at announcement (CR 601.2d) rather than
# repeating the verb, and that division is `deal_divided_damage`'s job, not
# this parser's. See `_targets_understood`'s `count_agnostic`.
#
# The restriction is read through `machines/targeting.py`'s own parser
# (`profile_for_text`) rather than a second regex here, and the same parser
# is what `Game.legal_target` rechecks on resolution (CR 608.2b) - so this
# module can never disagree with it about what a card targets.

#: This guard used to refuse *any* clause mentioning mana value, converted
#: mana cost, power, toughness, or "if" outright, because
#: `machines/targeting.py` used to read past a "with mana value N or less" /
#: "if it has mana value N or less" comparison without enforcing it -
#: `understood=True` with the comparison silently dropped. That is fixed now:
#: `TargetRequirement` carries `comparison_attribute` / `comparison_operator`
#: / `comparison_value`, read by `_read_phrase` and enforced for real by
#: `TargetRequirement.rejects` (`_rejects_comparison`), which `Game.legal_target`
#: consults on resolution (CR 608.2b) - verified this session:
#: `profile_for_text("target nonland permanent with mana value 3 or less")`
#: (Abrupt Decay) and `profile_for_text("target creature if it has mana value
#: 2 or less")` (Fatal Push) both now come back with `comparison_attribute`
#: set, and `_rejects_comparison` fails closed ("Fails closed, never open")
#: when the value cannot be pinned down. So the mana-value/power/toughness
#: half of the old blanket refusal is stale and is not carried forward.
#:
#: "if" on its own is not the same thing. `_read_phrase` only strips a
#: recognised comparison out of the leftover text after the noun; an
#: unrelated conditional - "target creature if it's your turn", or a second
#: "if" the parser does not tie to a comparison - is simply dropped as
#: unexamined leftover, with `understood` still left `True`. Trusting that
#: would still destroy or exile something broader than the card allows, so
#: `_targets_understood` refuses a phrase with "if" that is *not* accounted
#: for by an actual `comparison_attribute` it read out of that same phrase -
#: which is precisely what keeps Fatal Push working (its "if" *is* the
#: comparison) while still refusing a hypothetical unrelated conditional.
_UNENFORCED_CONDITIONAL_RE = re.compile(r"\bif\b", re.IGNORECASE)

#: A trailing duration on the clause itself - "exile target ... **until this
#: enchantment leaves the battlefield**" (Static Prison), "... **until end of
#: turn**". CR 611.2a: "A continuous effect generated by the resolution of a
#: spell or ability lasts as long as stated by the spell or ability creating
#: it (such as 'until end of turn'). If no duration is stated, it lasts
#: indefinitely." `destroy_ability_targets`/`exile_ability_targets`/etc. state
#: no duration at all - they act once and never reverse it - so they are only
#: a correct reading of a clause that likewise states none. A clause that
#: names one needs the reversal this wave does not build, and running the
#: verb without it would create a permanent effect out of a temporary one:
#: exiling "until this enchantment leaves the battlefield" for good. Refused
#: here, so the whole clause list comes back `None` (fail-closed) rather than
#: quietly dropping the duration.
_TRAILING_DURATION_RE = re.compile(r"\buntil\b|\bfor as long as\b", re.IGNORECASE)


def _targets_understood(
    phrase: str,
    *,
    count_agnostic: bool = False,
    battlefield_only: bool = True,
    allow_player_targets: bool = False,
) -> bool:
    """Whether this wave may act on `phrase` - "target creature", "any
    target", "up to two target creatures", "another target permanent".

    `phrase` is the *whole* "target ..." expression, count words included -
    "up to two" and "another" both sit **before** the word "target", so a
    caller that trimmed the phrase down to only what follows "target" would
    silently throw the count away and let this wave misread "up to two target
    creatures" as a single mandatory target. Confidence means all of:
    `machines/targeting.py` understood the phrase, it is exactly one
    requirement (two "target" words is two requirements, not this shape), any
    "if" in it is accounted for by a comparison the requirement actually
    carries rather than being unexamined leftover text (see
    `_UNENFORCED_CONDITIONAL_RE`), it does not carry a trailing duration this
    wave's unconditional verbs cannot honour, and - only when
    `battlefield_only` is set - every target it takes lives on the
    battlefield.

    `battlefield_only` is `True` by default because most of this file's verbs
    are: CR 701.8a only lets destroy move something "from the battlefield",
    and CR 701.26a/701.26b define tap and untap only for "a permanent", which
    CR 110.1 puts on the battlefield. `exile_ability_targets` and
    `return_ability_targets_to_hand` pass `False` - CR 406.2/701.13a exile
    "from whatever zone it's currently in", and "return" carries no CR-
    numbered keyword-action definition at all (CR 701 lists destroy, exile,
    and tap/untap but no "Return") - nothing in the rules restricts it to the
    battlefield the way CR 701.8a restricts destroy, so it reaches whichever
    zone the printed card names, and Faerie Macabre's "target cards from
    graveyards" and Raise Dead's "target creature card from your graveyard"
    are exactly what those two verbs are supposed to reach. Whichever zones
    the printed text names, `Game.legal_target` rechecks them again on
    resolution (CR 608.2b), so nothing here has to widen what is trusted.

    `count_agnostic=True` is CR 115.6's "up to N"/"N or M target ..." for a
    verb whose semantics genuinely do not change with the count - destroy,
    exile, tap, untap, return, and put-counters all just repeat themselves
    once per legal target, including "up to one" resolving to zero (CR 608.2b
    already skips an illegal target the same way). Damage joins them for
    exactly the same reason *unless* the card's own text divides the total
    (CR 601.2d's "divided as you choose", Electrolyze) - that shape is a
    different mechanism (`deal_divided_damage`, matched by `_DIVIDED_DAMAGE_
    RE` before this one is even tried) that this wave's `deal_damage`/
    `damage_ability_targets` do not model, so *that* caller keeps the strict
    single-mandatory-target rule. A plain "deals N damage to up to one target
    creature" (Mjolnir) or "to each of up to two target creatures" (Dual
    Shot) never divides anything - CR 115.6 is the whole rule - so every
    target chosen simply takes the full N, which is exactly what the ordinary
    per-target loop below already does once this flag lets it run.
    """
    if _TRAILING_DURATION_RE.search(phrase):
        return False
    profile = profile_for_text(phrase)
    if not profile.understood or len(profile.requirements) != 1:
        return False
    requirement = profile.requirements[0]
    if _UNENFORCED_CONDITIONAL_RE.search(phrase) and requirement.comparison_attribute is None:
        return False
    if battlefield_only and requirement.zones != frozenset({Zone.BATTLEFIELD}):
        return False
    if not allow_player_targets and requirement.allows_players:
        # Destroy, exile, return, tap/untap, and put-counters all operate on a
        # `CardState` only (`isinstance` checks throughout this file) - a
        # phrase that can name a *player* (Thraben Charm's "any number of
        # target players' graveyards") would otherwise "understand" the
        # phrase and hand back a verb that silently does nothing to the
        # player it targeted. Only `deal_damage`/`damage_ability_targets`
        # pass `allow_player_targets=True`, because CR 115.1's "any target"
        # genuinely includes a player and `Game.deal_damage` accepts one.
        return False
    if count_agnostic:
        # CR 107.1c: "If a rule or ability instructs a player to choose 'any
        # number,' that player may choose any positive number or zero." An
        # unbounded count is the same thing to a count-agnostic verb as "up to
        # N" is - the verb repeats once per legal target and stops - so
        # Mindbreak Trap's "Exile any number of target spells" is exactly as
        # readable as "Exile up to one target spell". This used to be refused
        # outright, one line above, which fails a card closed for a reason that
        # applies only to a count-*sensitive* verb.
        return True
    if requirement.unbounded:
        return False
    return requirement.minimum == 1 and requirement.maximum == 1


#: `phrase` always captures from the word "target" itself (or "any target")
#: to the end of the clause, count words and all - `_targets_understood`
#: needs the count word, if any, to see "up to two" and refuse it.
_DESTROY_TARGET_RE = re.compile(r"destroy (?P<phrase>(?:any target|.*target.+))", re.IGNORECASE)


_EXILE_TARGET_RE = re.compile(r"exile (?P<phrase>(?:any target|.*target.+))", re.IGNORECASE)
#: "Counter target spell." - the unconditional shape (CR 701.6a) - and its
#: qualified cousins, "Counter target `<qualifier>` spell." (Force of
#: Negation's "noncreature", a colour word, a card type). The qualifier is
#: read and thrown away: `counter_targets` walks whatever the caster actually
#: targeted, and CR 601.2c/`machines/targeting.py` is what enforces the
#: restriction at announcement, not this dispatcher. Still refused: Mystic
#: Confluence's "Counter target spell unless its controller pays {3}." and
#: Cryptic Command's own "Counter target spell or ability." - the trailing `$`
#: refuses anything printed after "spell" *other than* the predicate below,
#: rather than silently dropping a condition the card actually has. The
#: ability-or-spell shape gets its own regex below
#: (`_COUNTER_TARGET_ABILITY_OR_SPELL_RE`) instead of being folded in here.
_SPELL_QUALIFIER_WORD = (
    r"(?:non)?(?:creature|artifact|enchantment|land|planeswalker|instant|sorcery|battle"
    r"|white|blue|black|red|green|colorless|multicolored|monocolored)"
)
#: The qualifier as *printed*, which is one or more of the words above joined
#: by "or" - Flusterstorm's "instant or sorcery spell", against Force of
#: Negation's single "noncreature" - or, for three or more, the serial-comma
#: list Strix Serenade's "artifact, creature, or planeswalker spell" and Swan
#: Song's "enchantment, instant, or sorcery spell" print. `machines/
#: targeting.py` already reads the disjunction into `TargetRequirement.
#: card_types`; this only has to accept the shape, since the restriction is
#: enforced there and not here.
_SPELL_QUALIFIER = rf"{_SPELL_QUALIFIER_WORD}(?:(?:,(?: or)?| or) {_SPELL_QUALIFIER_WORD})*"
#: The predicate a counterspell may print *after* the noun - a bound on one of
#: the spell's own characteristics rather than a word about its type:
#:
#: - "with mana value 2" (Spell Snare). CR 202.3e: "When calculating the mana
#:   value of an object with an {X} in its mana cost, X is treated as 0 while
#:   the object is not on the stack, and X is treated as the number chosen for
#:   it while the object is on the stack" - so a spell's real, announced mana
#:   value is what this compares against, which is `Game.legal_target`'s job
#:   through `TargetRequirement.comparison_value`, not this dispatcher's.
#: - "with power or toughness 2 or less" (Stern Scolding), a disjunction over
#:   two printed characteristics of a creature spell.
#:
#: Read and thrown away here for exactly the reason the qualifier already is:
#: `counter_targets` counters whatever the caster legally targeted, and
#: CR 601.2c (announcement) plus CR 608.2b (the resolution recheck) are what
#: enforce the restriction, both in `machines/targeting.py`. Accepting the
#: tail is therefore not "dropping a condition" - it is letting the half of
#: the card that already reads the condition actually be reached.
#:
#: The comparison itself is `machines/targeting.py`'s own grammar
#: (`COMPARISON_CLAUSE_PATTERN`), not a copy of part of it, so every bound the
#: announcement check enforces is a bound this dispatcher accepts: a printed
#: number, and a computed one - Drown in the Loch's "less than or equal to the
#: number of cards in its controller's graveyard" and Spellstutter Sprite's
#: "X or less, where X is <expression>" (CR 107.3c). `where_x` is checked
#: readable by `count_expression` in `_parse_targeted_clause`.
_SPELL_PREDICATE = rf"with (?:{COMPARISON_CLAUSE_PATTERN})(?:,? where x is (?P<where_x>[^.]+?))?"
_COUNTER_TARGET_SPELL_RE = re.compile(
    rf"^counter target(?: {_SPELL_QUALIFIER})? spell(?: {_SPELL_PREDICATE})?\.?$",
    re.IGNORECASE,
)
#: "Counter target spell unless its controller pays {N}." (CR 118.12a) -
#: Censor and Mystical Dispute - with the same qualifier and predicate slots
#: the plain shape above carries, which is what reaches **Spell Pierce**
#: ("target noncreature spell") and **Flusterstorm** ("target instant or
#: sorcery spell"). Flusterstorm is the case that shows why a silent parse is
#: worse than a refused one: its storm ability (CR 702.40a) already worked, so
#: N copies went on the stack and every one of them resolved doing nothing.
#: See `_counter_unless_pays_effect`.
_COUNTER_UNLESS_PAYS_RE = re.compile(
    rf"^counter target(?: {_SPELL_QUALIFIER})? spell(?: {_SPELL_PREDICATE})? "
    r"unless its controller pays \{(?P<n>\d+)\}\.?$",
    re.IGNORECASE,
)


#: The plural half - "to their owners' hands" - is the same verb on a clause
#: naming more than one target (Marang River Regent's "return up to two other
#: target nonland permanents to their owners' hands"). "Return" has no CR-
#: numbered keyword-action definition (unlike destroy, exile, or tap/untap)
#: to make it anything but per-object, and `return_ability_targets_to_hand`
#: already loops over every target `Game.resolve_targets` still finds legal
#: (CR 608.2b), so
#: the only thing the singular pattern was missing was the printed plural.
#:
#: R0a-T7's own third destination - a bare "to your hand" (Get Out's "Return
#: one or two target creatures and/or enchantments you own to your hand.") -
#: is the identical move: CR 401 always returns a card to *its own* owner,
#: and "you own" is the targeting requirement's own restriction
#: (`owned_by_caster`), so every target this reaches is already the caster's
#: - "to your hand" and "to its owner's hand" describe the same destination
#: for such a target, and `return_ability_targets_to_hand`'s `Game.
#: return_to_hand` needs no new branch to reach it.
_RETURN_TARGET_RE = re.compile(
    r"return (?P<phrase>.*target.+?) to (?:its owner'?s hand|their owners'? hands|your hand)",
    re.IGNORECASE,
)


#: "Tap target X." and "Untap target X." - and Kiora's Follower's "Untap
#: *another* target permanent", where "another" sits between the verb and
#: "target" and is part of the captured phrase so a count word there is not
#: silently thrown away.
_TAP_UNTAP_TARGET_RE = re.compile(r"(?P<verb>tap|untap) (?P<phrase>.*target.+)", re.IGNORECASE)


#: "<Source> deals N damage to target X." and "... to any target." The source
#: is never named here - `deal_damage`/`damage_ability_targets` already read
#: it off whichever of a spell or an ability is resolving (CR 120.2b). The
#: leading prefix is needed for Lava Dart's own "Lava Dart deals 1 damage to
#: any target." (the source's literal printed name, not yet self-normalized
#: away when this is tried), but it must not be able to cross a quote mark:
#: under `fullmatch`, an unbounded `.*` swallowed Weapons Manufacturing's own
#: "create a colorless artifact token named Munitions with \"When this token
#: leaves the battlefield, it deals 2 damage to any target.\"" whole, reading
#: the *granted* ability's quoted text - the token's own, not the trigger's -
#: as this ability's entire effect. A quote character (straight or curly,
#: single or double - `_parse_token_tail` reads a granted ability's text
#: wrapped in either) blocks the prefix, so a clause whose "deals ... damage"
#: sits inside quotes fails this match entirely and falls through to
#: `_parse_token_clause`, which is the one that is supposed to read it.
#: An apostrophe *between two letters* is a possessive, not a quote, and is
#: let through: a modal card's mode names its source by its printed name
#: (CR 700.2a), and Kolaghan's Command's "Kolaghan's Command deals 2 damage
#: to any target." read as nothing until it was (battle 8 follow-up).
_UNQUOTED_PREFIX = r"(?:[^\"“”'‘’]|(?<=\w)['’](?=\w))*"
#: `n` reads `AMOUNT` (a fixed count or CR 107.3a's X) rather than plain
#: `COUNT` - Tribal Flames' "deals X damage to any target, where X is the
#: number of basic land types among lands you control" (Domain) and Scourge
#: of Valkas' "deals X damage to any target, where X is the number of
#: Dragons you control" both print a literal X here, evaluated at resolution
#: through `count_expression`'s reader for the `where_x` tail
#: (`numbers.where_x_pattern`).
#:
#: The optional " for each <expr>" tail is CR 608.2c's other multiplier
#: shape - Lotleth Giant's "deals 1 damage to target opponent for each
#: creature card in your graveyard" and Immaculate Magistrate's identically
#: shaped "put a +1/+1 counter on target creature for each Elf you control"
#: below - a fixed base multiplied by a count taken once, as the ability
#: resolves (CR 608.2h). Both tails are lazy (`.+?`/non-greedy `phrase`) so
#: a clause with neither still lets `phrase` swallow the whole rest of the
#: sentence exactly as it always did; only a clause that actually prints one
#: of the two tails stops `phrase` short of it.
_DAMAGE_TARGET_RE = re.compile(
    rf"{_UNQUOTED_PREFIX}\bdeals? (?P<n>{AMOUNT}) damage to "
    # ecl-T8: CR 115.3/115.4's "any other target" (Boulder Dash, Arc Trail) -
    # a bare phrase that ends at the word "target" itself, which the second,
    # generic alternative's own trailing `.+?` (at least one character after
    # "target") cannot match at all.
    rf"(?P<phrase>any target|any other target|.*?target.+?)"
    rf"(?: for each (?P<each>[^.]+?))?"
    # The sentence's own closing period is optional: an anaphor pair hands
    # its antecedent over with it still on, and without `\.?` the lazy
    # `phrase` swallowed ", where X is ...", leaving X unread.
    rf"{where_x_pattern()}\.?$",
    re.IGNORECASE,
)


#: "Put N +1/+1 (or -1/-1) counters on target X." and Anafenza's "on
#: *another* target tapped creature you control" - the same reasoning as
#: `_TAP_UNTAP_TARGET_RE`. `kind` is any single lowercase word, not only the
#: two P/T kinds: CR 122.1 leaves a counter's name open ("charge", "fate",
#: whatever a card invents), and Oblivion Stone's "Put a fate counter on
#: target permanent" is exactly that - a named counter with no rules of its
#: own, put on by a plain activated ability this shape already reads once the
#: kind word is not pinned to the two P/T spellings.
#:
#: Immaculate Magistrate's own "... on target creature for each Elf you
#: control" and Go-Shintai of Boundless Vigor's "... on target Shrine for
#: each Shrine you control" trail a for-each multiplier after the targeting
#: phrase - `phrase` stops short of it (non-greedy) so `_targets_understood`
#: is never asked to read "target creature for each Elf you control" as one
#: targeting restriction, and `each` carries the multiplier for
#: `count_expression` to read separately.
_COUNTER_TARGET_RE = re.compile(
    rf"put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    rf"(?P<phrase>.*target.+?)(?: for each (?P<each>[^.]+))?\.?$",
    re.IGNORECASE,
)


#: "<Source> deals N damage divided as you choose among one or two targets."
#: (Electrolyze), "among one, two, or three targets" (Arc Lightning), "among
#: any number of targets" (Pyrotechnics, Rolling Thunder - CR 107.1c, no
#: printed ceiling at all), or "among any number of target creatures and/or
#: planeswalkers your opponents control, where X is ..." (Ureni, the Song
#: Unending - a real printed restriction this time, not CR 115.4's bare
#: "targets"). `phrase` is read whole and handed to `_targets_understood`
#: the same way every other targeted clause's phrase is - `machines/
#: targeting.py`'s own `_read_count` (shared with `_COUNTER_TARGET_RE` et
#: al.) already reads "any number of", "up to N", and the "N, M, or K" list
#: shape uniformly, so there is no need to spell any of them out again here
#: as a second, parallel alternation the way an earlier wave's hard-coded
#: "one(?:, two)?,? or (?:two|three)" did - that fixed list is exactly why
#: this shape used to be silent on Pyrotechnics and Rolling Thunder at all.
#: `n` reads `AMOUNT`/`where_x_pattern` for Ureni and Rolling Thunder's own
#: X, evaluated through `count_expression` the same way `_DAMAGE_TARGET_RE`'s
#: does. The actual count chosen, and the caster's own CR 601.2d division
#: announcement, are still read off `spell.targets`/`spell.division` at
#: resolution - `_deal_divided_damage_shares` below never re-reads this
#: phrase.
#:
#: "<Name> deals X damage divided evenly, rounded down, among all creatures
#: target opponent controls." (Dwarven Catapult) - not a target *list* at
#: all despite superficially fitting "divided ... among <phrase>": CR 115.4's
#: only real target here is the single player named by "target opponent"/
#: "target player", and "all creatures ... controls" is CR 611.2c's
#: ordinary computed-at-resolution recipient set, the identical "all
#: <description> target player controls" grammar `_ALL_OF_TARGET_PLAYERS_RE`
#: already reads for Settle the Wreckage's "Exile all attacking creatures
#: target player controls." - not something the caster ever chooses or
#: announces a share for, per creature. Tried *before* `_DIVIDED_DAMAGE_RE`
#: below for exactly that reason: left to fall through to it,
#: `_targets_understood`'s own "target opponent" substring inside the
#: phrase reads as "understood" on its own, and the whole total would be
#: dealt once to the single targeted *player* instead of divided among the
#: creatures they control.
_DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE = re.compile(
    rf"^.*\bdeals? (?P<n>{AMOUNT}) damage divided "
    rf"(?:as you choose|(?P<evenly>evenly, rounded down)),? among all creatures "
    rf"target (?P<whose>opponent|player) controls{where_x_pattern()}\.?$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Single-clause TOKEN CREATION, read off the spell or ability's own text
# --------------------------------------------------------------------------
#
# CR 701.7a: "To create one or more tokens with certain characteristics, put
# the specified number of tokens with the specified characteristics onto the
# battlefield." A card names its token's characteristics in one of two shapes:
# "[create] [N] [P/T] [color(s)] [subtype(s)] [artifact] creature token[s]
# [with <keywords or a quoted ability>]" (Spectral Procession, Ajani, Nacatl
# Pariah, Wurmcoil Engine, Drowner of Truth), or CR 111.10's predefined tokens
# by name ("create a Food token"). `models/token.py` already holds what a
# token *is*; this is the other half W1-W3 built for damage, search, and
# player clauses - reading the noun phrase off the card's own printed text
# instead of a per-card `TokenDefinition` in this file.
#
# What is deliberately refused, both fail-closed for the reasons CR 707.2 and
# CR 608.2c give below:
#
# - **"a token that's a copy of ..."** (Repudiate, Fanatic of Rhonas's
#   eternalize, Caretaker's Talent, Tamiyo's -X) needs the copied object's
#   copiable values (CR 707.2), which this parser does not read off anything -
#   checked for and refused before the noun-phrase regex is even tried, so it
#   cannot be mistaken for one. Ocelot Pride's own "for each token you control
#   that entered this turn, create a token that's a copy of it" is the one
#   copy shape this file *does* read - `_parse_city_blessing_token_copy_clause`,
#   below the token-clause section, matches that exact templated shape
#   (CR 702.131's ascend / the city's blessing) and reads the copy through
#   `token_copy_of` (CR 707.2) rather than through this parser.
# - **A count this parser cannot read as a fixed number** - Hangarback
#   Walker's "for each +1/+1 counter on this creature", Seasoned Pyromancer's
#   "for each nonland card discarded this way" - is not a `COUNT` word at
#   all, so `_TOKEN_CLAUSE_RE` simply does not match text of that shape;
#   nothing silently falls back to a count of one.
# - **A tail after "with" that is not a single quoted ability or a keyword
#   from `_TOKEN_KEYWORDS`** fails the whole clause rather than dropping the
#   unread part - Hangarback Walker's "with flying for each +1/+1 counter on
#   this creature" is exactly this: `flying` alone is a known keyword, but the
#   tail as a whole is not, so `_parse_token_tail` returns nothing usable and
#   `_parse_generic_token_descriptor` refuses the whole token rather than
#   create one with the keyword and silently lose the count clause bolted onto
#   it (CR 608.2c has no notion of running half an instruction).


#: `desc` is everything between the count and the word "token(s)" - "1/1
#: white Spirit creature", "3/3 colorless Phyrexian Wurm artifact creature",
#: or a predefined token's own name ("Food", "tapped Powerstone"). `name` is
#: CR 111.4's own stated name - Weapons Manufacturing's "a colorless artifact
#: token **named Munitions** with ..." - between the noun phrase and the
#: tail, since that is where Oracle text always prints it (CR 111.9's
#: "create [name], a ..." appositive is a different shape this regex does not
#: read; `_parse_named_token_clause` below reads that one). `tail`
#: is whatever follows "with", read by `_parse_token_tail`. `\btokens?\b` a
#: whole word so a subtype that merely contains the letters "token" could
#: never match it - none in the pool do, but the boundary costs nothing. A
#: leading "you " (Verdant Kraken's "you create a ... token") is optional and
#: read the same as no subject at all - a spell or ability's own clauses are
#: always the resolving object's controller's actions either way.
_TOKEN_CLAUSE_RE = re.compile(
    rf"^(?:you )?(?:create )?(?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b"
    r"(?:\s+named (?P<name>.+?))?"
    r"(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: Keyword abilities simple enough to print as one bare word or two on a
#: token's tail - CR 702's list is much longer, but this is what the pool's
#: token-creating cards actually name. Read against `str.split`'s output
#: rather than the regex, so a compound like "first strike" survives the "or"
#: below untouched (`split_effect_clauses`'s own separator would otherwise cut
#: a bare "and" apart, which is why this is checked as parts, not re-split).
_TOKEN_KEYWORDS = {
    "flying",
    "deathtouch",
    "lifelink",
    "trample",
    "vigilance",
    "haste",
    "reach",
    "menace",
    "defender",
    "indestructible",
    "hexproof",
    "prowess",
    "first strike",
    "double strike",
    # CR 604.3a item (2): changeling "granted to the token it affects by the
    # effect that created the token" is a characteristic-defining ability -
    # Crib Swap's Shapeshifter. The keyword line is all it takes; the creature
    # types are `CardState.subtypes`/`machines/layers._changeling_effects`.
    "changeling",
    # CR 702.18a: "This permanent or player can't be the target of spells or
    # abilities" - a static ability read the same bare-word way as every other
    # entry here (`Game.hexproof_refusal`, the shared targeting check, already
    # reads it off `has_keyword`/the computed board once it is on the token;
    # Deadly Grub's own Insect is the pool's first token to print it).
    "shroud",
    # CR 702.14a: the five landwalks, bare keyword lines like the rest of this
    # set (Chasm Skulker's Squid tokens have islandwalk).
    "plainswalk",
    "islandwalk",
    "swampwalk",
    "mountainwalk",
    "forestwalk",
    # CR 702.147a - Jadar, Ghoulcaller of Nephalia's own "create a 2/2 black
    # Zombie creature token with decayed." `TokenDefinition.keywords` puts
    # "Decayed" on the token exactly as a real printing carries it, so
    # `machines/combat.has_keyword`/`machines/keywords.keyword_triggered_
    # abilities` read it off the token the same way they read Rot-Curse
    # Rakshasa's own printed keyword.
    "decayed",
    # CR 702.90a: infect, a static ability - Carrion Call's and Trigon of
    # Infestation's "Phyrexian Insect creature token(s) with infect".
    # `TokenDefinition.keywords` carries it as a printed keyword, so
    # `machines/combat.has_keyword` and CR 120.3b/120.3d's damage results read
    # it off the token exactly as they read it off a printed creature.
    "infect",
}

_TOKEN_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


#: A quoted span, masked while the list is split so a granted ability's own
#: commas and "and"s are never mistaken for a list boundary.
_QUOTED_SPAN_RE = re.compile(r"[\"“][^\"“”]*[\"”]")


class ModeNotice(EngineModel):
    """One chosen mode of a resolving modal spell (CR 700.2a) whose text this
    wave could not read into an effect.

    The same "unreadable is not the same as no effect" record `TargetingNotice`,
    `InterveningIfNotice`, `CostModifierNotice`, and `LayerNotice` already keep
    for their own gaps (see each's own docstring) - `resolve_modal_spell`
    appends one of these for a mode it cannot perform instead of the mode
    silently doing nothing, which would otherwise be indistinguishable from a
    mode that legitimately has no effect left to have (Mystic Confluence's
    "Draw a card." with the library empty, say).
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    mode_number: int
    """The mode's 1-based position on the card (CR 700.2), for a player or a
    log to point back at the printed bullet."""
    text: str
    """The mode's own printed text, X substituted, for whoever reads this
    notice later."""


# --------------------------------------------------------------------------
# Mixed targeted/player clauses in one effect
# --------------------------------------------------------------------------
#
# `parse_targeted_effect_for_spell` and `parse_player_effect_for_spell` are
# each a whole-effect parser: every clause has to be their one shape or the
# whole thing is refused. A card that mixes the two kinds of clause - Lightning
# Helix's "deals 3 damage to any target and you gain 3 life" is a targeted
# clause and a player clause back to back - parses under neither, and used to
# need a table row for exactly that reason. This tries all three parsers on
# each clause independently instead of picking one parser for the whole card -
# search joined this dispatcher in W3, which is how Ghost Quarter's "Destroy
# target land. Its controller may search ..." reads as two clauses of two
# different shapes with no table row.


#: "Its controller ...", "That creature's controller ...", "That player ..." -
#: CR 400.7's plain anaphoric back-reference to whatever `_DESTROY_TARGET_RE`/
#: `_EXILE_TARGET_RE`'s clause just targeted, not a fresh target of this
#: sentence's own. Solitude prints the first form ("That creature's
#: controller gains life..."), Ghost Quarter and White Orchid Phantom the
#: second ("Its controller may search..."), Boseiju the third ("That player
#: may search...") - all three name the same thing: whoever controls the
#: permanent the previous clause just destroyed or exiled.
_ANAPHORIC_SUBJECT_RE = re.compile(
    r"^(?:its controller|that [a-z]+'s controller|that player|they)\s+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


class AnaphoricClauseNotice(EngineModel):
    """One "<verb> target X. Its/that X's controller ..." effect whose second,
    anaphoric clause (CR 400.7's back-reference to the first clause's own
    target, not a target of its own) this wave could not read.

    This is Solitude's own defect, recorded rather than repeated: "exile up to
    one other target creature. That creature's controller gains life equal to
    its power." used to have no registry row and nothing that could read its
    second sentence, so `_parse_mixed_clauses` correctly refused the whole
    effect (CR 608.2c has no notion of running half an instruction) - but
    silently, with no record anywhere that anything had gone unread, which is
    why a legally-targeted Solitude could exile nothing and gain no life with
    no trace of why. The same "unreadable is not the same as no effect"
    record `TargetingNotice`, `InterveningIfNotice`, `ModeNotice`,
    `LayerNotice`, and `CostModifierNotice` already keep for their own gaps.

    It also covers the other direction of back-reference: a clause that names
    an object the *cost* consumed rather than one an earlier clause moved.
    Neoform and Eldritch Evolution both read "the sacrificed creature's mana
    value", where the sacrificed creature was an additional cost (CR 118.8a)
    paid during announcement. `AbilityOnStack` records what an activated
    ability's cost sacrificed (`cost_sacrificed_card_ids`); a *spell* records
    nothing of the kind - `machines/casting.py`'s `add_additional_cost` puts
    the paid components on the `Casting`, which is gone by the time the spell
    resolves - so the number simply cannot be read. Recorded here rather than
    left silent, and named as the blocker it is.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable second sentence itself, as printed."""


class ImprintNotice(EngineModel):
    """One "you may exile a `<quality>` card ... from your hand" effect (CR
    207.2c's "Imprint" ability word, and its plain-English relatives) whose
    stated quality this wave could not read.

    This is the shape Ugin's Labyrinth's own defect was found in: a card whose
    ETB trigger offered no decision at all and simply resolved doing nothing,
    with nothing anywhere recording that a choice had gone unoffered. Once the
    shape itself is read (`_parse_imprint_clause`), the only way this can
    still happen is a quality word this wave does not recognise - and that gap
    gets this notice instead of the same silence, the same "unreadable is not
    the same as no effect" record `TargetingNotice`, `InterveningIfNotice`,
    `ModeNotice`, `AnaphoricClauseNotice`, `LayerNotice`, and
    `CostModifierNotice` already keep for their own.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


class CastFromHandExileNotice(EngineModel):
    """One "Whenever a player casts a spell from their hand, that player
    exiles it[, ...]" effect (Knowledge Pool's and Possibility Storm's shared
    opening clause, confirmed identical with `resolve_cards` in the session
    that wrote this) whose *tail* - what happens after the exile - this wave
    could not read.

    This is Knowledge Pool's own reported defect, recorded rather than
    repeated: the trigger fired and resolved, the cast spell stayed on the
    stack, and nothing anywhere said a clause had gone unread. Once the
    shared head is recognised (`_parse_cast_from_hand_then_exile_clause`),
    every printing this wave knows about is read to the end - Knowledge
    Pool's "if the player does, they may cast ..." and Possibility Storm's
    dig-until-shared-type tail both parse in full - so this notice exists for
    a *third* printing of the same opening this wave has not seen, the same
    "unreadable is not the same as no effect" record `AnaphoricClauseNotice`,
    `ImprintNotice`, `ModeNotice`, `LayerNotice`, and `CostModifierNotice`
    already keep for their own gaps. One paragraph is one ability
    (`docs/scenario-tests.md`'s own convention): the exile and the tail are
    one CR 608.2c instruction, so an unread tail refuses the *whole* thing -
    the spell is **not** exiled either - rather than running the readable
    half and silently dropping the rest, which would be a half-applied
    effect masquerading as a correct one.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable tail, as printed - everything after "that player
    exiles it"."""


class PlayerSubjectSplitNotice(EngineModel):
    """The player half of a "You and `<group>` gain `<keyword(s)>` until end
    of turn" compound subject (Veil of Summer's own "You and permanents you
    control gain hexproof from blue and from black until end of turn") -
    read (`_parse_you_and_group_gain_clause` splits the subject, and the
    group half already applies through the ordinary mass-grant reader), but
    deliberately not yet granted.

    `Game.grant_player_hexproof`/`grant_player_shroud` and their own clause
    reader (`_player_gains_hexproof_clause`, `_PLAYER_GAINS_HEXPROOF_RE`)
    already exist and already read this exact sentence once its subject is
    narrowed to "You" alone - see `test_the_clause_parser_reads_hexproof_
    from_two_qualities_on_you` - but wiring the *player* half of this split
    to them is a separate, later piece of work, scoped on purpose so the
    two halves land independently. Until then this fails closed the same
    way every other unread-clause gap in this file does: recorded, not
    silently dropped and not silently applied.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The player-subject sentence this wave reads but does not yet grant,
    as it would print alone ("You gain hexproof from blue and from black
    until end of turn")."""


class LayerRemainderNotice(EngineModel):
    """One sentence of a multi-sentence resolution that *is* a CR 611.2
    continuous-effect shape - a pump, a keyword grant, a base P/T set - runs
    fine on its own, but a sibling sentence in the same paragraph is not one
    of those shapes and this wave cannot read it either.

    `_is_layer_effect_text` decides whether a whole piece of resolving text
    should route to `create_continuous_effect`/`create_continuous_effect_of_
    ability` (or, for one mode of a modal spell or trigger, their mode-scoped
    twins) by asking whether *any* sentence in it looks like a layer shape -
    right for that routing decision, but the routed-to dispatcher itself
    (`parsed_layer_effects`, `machines/layers.py`) silently skips whatever
    sentence it does not recognise, which is correct when it is sweeping a
    permanent's whole oracle text off the battlefield (a static line and a
    triggered ability's own body sit side by side there on purpose) and wrong
    when it is reading a *resolving* spell's or ability's own multi-sentence
    effect: Academic Ascent's own "Empower Jace 2." used to never reach any
    parser at all, with nothing anywhere recording that it had gone unread.
    `_compose_layer_effect_with_remainder`/`_compose_layer_effect_with_
    remainder_for_ability` still run the layer sentence, and now record this
    instead of losing the sibling sentence with no trace - the same
    "unreadable is not the same as no effect" record `AnaphoricClauseNotice`,
    `ModeNotice`, and `LayerNotice` already keep for their own gaps.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The sibling sentence(s) this wave could not read, as printed."""


#: A literal mana symbol or run of them - "{G}". Read by several clause
#: parsers below; a triggered mana ability's own mana is read by
#: `machines/abilities.parse_triggered_mana`.
_MANA_SYMBOL_RE = re.compile(r"\{([WUBRGC])\}", re.IGNORECASE)


#: --- The "see the top N, then optionally move one of them" family ---------
#:
#: One printed shape, not one card. A player sees the top N cards of their own
#: library - either by **milling** them (CR 701.17a: "that player puts that
#: many cards from the top of their library into their graveyard", so the cards
#: have already changed zones by the time the choice is offered) or by **looking
#: at** them (CR 401.2 keeps a library face down and unlookable; an effect
#: saying "look at" lifts that for itself alone and moves nothing) - and is then
#: offered an optional follow-up: "you may put a <kind> card from among them"
#: into the hand, onto the battlefield, or into the graveyard.
#:
#: Every part after the look is a choice the *resolving* effect asks its own
#: controller for as it resolves (CR 608.2d), so both halves are asked rather
#: than assumed: `Game.may` for whether to take the follow-up at all, and a
#: `DecisionKind.CHOOSE_CARDS` question for *which* card - the same pair
#: `_merge_reveal_top_to_hand_rest_to_graveyard_clauses` and
#: `_parse_look_top_n_may_battlefield_creature_bonus_clause` already use. No
#: new `DecisionKind` is needed: "choose 1 of these candidates" is exactly what `CHOOSE_CARDS` is
#: documented to be general over.
#:
#: "From among them" is what keeps the candidate pool honest. For the mill arm
#: it is the cards *this* mill just moved (CR 701.17c: an effect referring to a
#: milled card finds it in the zone it moved to, as long as that zone is
#: public) - not every card already sitting in the graveyard, which is what
#: `_MILL_THEN_MAY_RETURN_CREATURE_RE`'s "from your graveyard" reads instead.
#:
#: Printings this reads, each verified with `resolve_cards` in the session that
#: wrote it:
#:   Six              "Mill three cards. You may put a land card from among
#:                     them into your hand."
#:   Ostrich-Horse    the same, plus "If you don't, put a +1/+1 counter on this
#:                     creature." (CR 122.1a)
#:   Ainok Wayfarer   the same text again, on a different creature - which is
#:                     the point of templating the shape rather than the card.
#:   Scout the City   "Mill three cards. You may put a permanent card from among
#:                     them into your hand. You gain 3 life." (CR 110.4a's
#:                     "permanent card"; CR 119.3's life gain)
_SELECT_FROM_TOP_KINDS: dict[str, Callable[[CardState], bool]] = {
    "": lambda state: True,
    "permanent": lambda state: state.is_permanent,
    "land": lambda state: Type.LAND in state.types,
    "creature": lambda state: Type.CREATURE in state.types,
    "artifact": lambda state: Type.ARTIFACT in state.types,
    "enchantment": lambda state: Type.ENCHANTMENT in state.types,
    "instant": lambda state: Type.INSTANT in state.types,
    "sorcery": lambda state: Type.SORCERY in state.types,
    "planeswalker": lambda state: Type.PLANESWALKER in state.types,
    "saga": lambda state: state.is_saga,
}


#: Normalises an Oxford-or-not "X, Y, and Z" / "X or Y" list to plain commas,
#: so a type list reads the same however it is punctuated - Wrath of the
#: Skies and a hypothetical "artifact or creature" both split the same way.
_MASS_TYPE_JOIN_RE = re.compile(r",?\s+(?:and|or)\s+", re.IGNORECASE)


def _parse_mass_type_qualifier(phrase: str) -> Callable[[Characteristics], bool] | None:
    """A predicate for the qualifier half of a mass destruction/sacrifice
    clause, read off the *computed* board (CR 613.5) rather than the raw
    printing - `game.characteristics_of` is what a layer-6 type change or a
    layer-5 colour change would otherwise be missed by.

    <qualifier> is an optional "nonland " prefix (CR 205.2a's negation) ahead
    of either:

    - the bare word "permanent"/"permanents" - no restriction at all,
    - "colored permanent"/"colorless permanent" (CR 105.2b, CR 105.2c), or
    - one or more CR 205.2a card types joined by a comma, "and", or "or",
      with no trailing "permanent" word - Wrath of the Skies's own
      "artifact, creature, and enchantment".

    Returns `None` for anything else - a subtype list, a colour name, a
    controller restriction - so an unread qualifier fails the whole clause
    rather than silently matching everything or nothing.
    """
    lowered = phrase.strip().lower()
    #: CR 205.4a's supertypes, named or negated ahead of the rest (Invasion of
    #: Fiora's "Destroy all legendary creatures." / "Destroy all nonlegendary
    #: creatures."): read off the computed supertypes, ANDed with the rest.
    supertype_wanted: tuple[Supertype, bool] | None = None
    supertype_prefix = re.match(r"^(?P<non>non-?)?(?P<word>legendary|basic|snow)\s+", lowered)
    if supertype_prefix is not None:
        supertype_wanted = (
            Supertype(supertype_prefix.group("word")),
            supertype_prefix.group("non") is None,
        )
        lowered = lowered[supertype_prefix.end() :].strip()
    #: CR 105.2's colour word ahead of the rest (Wrath of Marit Lage's "tap
    #: all red creatures"), or its negation ("nonred"), read off the computed
    #: colours (CR 613.1e) and ANDed with the rest.
    color_wanted: tuple[Color, bool] | None = None
    color_prefix = re.match(r"^(?P<non>non-?)?(?P<word>white|blue|black|red|green)\s+", lowered)
    if color_prefix is not None:
        color_wanted = (
            Color[color_prefix.group("word").upper()],
            color_prefix.group("non") is None,
        )
        lowered = lowered[color_prefix.end() :].strip()
    #: CR 205.2a's negation prefix, read for *any* card type rather than only
    #: "nonland": Whipflare's "each nonartifact creature" is the same grammar
    #: "nonland permanent" is, and a word this cannot resolve to a real type
    #: fails the whole qualifier rather than being dropped.
    excluded: Type | None = None
    negation = re.match(r"^non([a-z]+)\s+", lowered)
    if negation is not None:
        excluded = _singular_card_type(negation.group(1))
        if excluded is None:
            return None
        lowered = lowered[negation.end() :].strip()
    bare = re.sub(r"(?:^|\s+)permanents?$", "", lowered).strip()

    type_predicate: Callable[[Characteristics], bool]
    if bare == "":

        def type_predicate(chars: Characteristics) -> bool:
            return True

    elif bare == "colored":

        def type_predicate(chars: Characteristics) -> bool:
            return bool(chars.colors)

    elif bare == "colorless":

        def type_predicate(chars: Characteristics) -> bool:
            return not chars.colors

    else:
        words = [word for word in _MASS_TYPE_JOIN_RE.sub(", ", bare).split(",") if word.strip()]
        types: list[Type] = []
        for word in words:
            # Plural is read the same as singular here - "artifacts" (a bare
            # plural type noun, Brotherhood's End's own "Destroy all
            # artifacts with mana value 3 or less") names the same CR 205.2a
            # type as "artifact"; Wrath of the Skies's own list never needs
            # this since its own members are already singular.
            card_type = _singular_card_type(word.strip())
            if card_type is None:
                return None
            types.append(card_type)
        if not types:
            return None
        type_tuple = tuple(types)

        def type_predicate(chars: Characteristics, types: tuple[Type, ...] = type_tuple) -> bool:
            return any(one_type in chars.types for one_type in types)

    def matches(chars: Characteristics) -> bool:
        if excluded is not None and excluded in chars.types:
            return False
        if supertype_wanted is not None:
            supertype, present = supertype_wanted
            if (supertype in chars.supertypes) is not present:
                return False
        if color_wanted is not None:
            color, present = color_wanted
            if (color in chars.colors) is not present:
                return False
        return type_predicate(chars)

    return matches


#: "<Source> deals N damage to each <type>[ and each <type>]*." -
#: Brotherhood's End's own first mode: "Brotherhood's End deals 3 damage to
#: each creature and each planeswalker." Unlike `_DAMAGE_EACH_OPPONENT_RE`'s
#: single implicit player, this names one or more of CR 300.1's card types,
#: ORed together - a permanent counts once even if it is more than one of the
#: named types. The leading `.*` reads past the card naming itself, the same
#: way `_DAMAGE_EACH_OPPONENT_RE` does.
_DAMAGE_EACH_GROUP_RE = re.compile(
    rf"^.*\bdeals? {count_pattern('n', x=True)} damage to each "
    rf"(?P<groups>[a-z]+(?:\s+and\s+each\s+[a-z]+)*){where_x_pattern()}\.?$",
    re.IGNORECASE,
)


#: "<Source> deals N damage to each <filtered group>." - the same CR 120.1
#: non-targeted damage `_DAMAGE_EACH_GROUP_RE` deals, but to a *subset* of a
#: card type rather than the whole type. Three printed filters, all in the
#: pool: a negated type ("each nonartifact creature", Whipflare), a keyword
#: ("each creature without flying" / "each creature with flying", Rough //
#: Tumble), and a controller group that also includes the players themselves
#: ("each opponent and each creature and planeswalker they control", End the
#: Festivities).
#:
#: Tried only after `_parse_damage_each_group_clause`, which owns the
#: unfiltered shapes; anything neither reads stays unread rather than being
#: guessed at, because a mass-damage filter read too widely wipes a board the
#: card never touched.
#:
#: "X, where X is `<expr>`" (Cavalier of Flame's "it deals X damage to each
#: opponent and each planeswalker they control, where X is the number of land
#: cards in your graveyard") is read once as the effect applies (CR 608.2h),
#: through `_resolve_multiplied_amount`, the same reader the unfiltered
#: "each opponent"/"each creature" shapes use.
_DAMAGE_EACH_FILTERED_RE = re.compile(
    rf"^.*\bdeals? (?P<n>{AMOUNT}) damage to each (?P<filter>.+?){where_x_pattern()}\.?$",
    re.IGNORECASE,
)


#: A group predicate that also needs the resolving object's controller - CR
#: 109.5's "you" - for a "you control" / "your opponents control" qualifier:
#: `(game, permanent, controller username) -> bool`.
GroupPredicate = Callable[["Game", CardState, str], bool]


def _players_in_apnap_order(game: "Game") -> list[Player]:
    """Everyone still in the game, active player first (CR 101.4).

    Falls back to seating order before a turn exists at all, which is the only
    state in which there is no active player to start from.
    """
    players = game.players_in_game
    turn = game.turn
    if turn is None:
        return players
    order = {username: index for index, username in enumerate(turn.players)}
    start = order.get(turn.players[turn.active_index % len(turn.players)], 0)
    return sorted(players, key=lambda p: (order.get(p.username, len(order)) - start) % len(order))


# --------------------------------------------------------------------------
# OBJECT anaphors: "It ...", "They ...", "... on it" (CR 400.7, CR 608.2c)
# --------------------------------------------------------------------------
#
# `_ANAPHORIC_SUBJECT_RE` above reads only **player** anaphors - "its
# controller", "that X's controller", "that player". A rider whose subject or
# object is the *thing itself* reached no parser at all, so the clause failed
# and CR 608.2c's fail-closed guard correctly threw the readable half away
# with it - silently, which is the defect. Measured:
#
#     Tap target creature.                                -> parses
#     Put two stun counters on target creature.           -> parses
#     Tap target creature. Put two stun counters on it.   -> None
#
# CR 608.2c names this shape outright: "In some cases, later text on the card
# may modify the meaning of earlier text (for example, 'Destroy target
# creature. It can't be regenerated' ...). Don't just apply effects step by
# step without thinking in these cases - read the whole text and apply the
# rules of English to the text."
#
# **The referent is derived from the antecedent's own subject phrase**, not
# from the antecedent's parser. That is what keeps this general: every
# existing clause parser is reused untouched, and this only has to answer the
# separate question "which objects did that sentence act on".
#
# **`_SUBJECT` in `machines/layers.py` is deliberately not widened to accept
# "it".** `_is_layer_effect_text` is an any-sentence test over the *whole*
# ability, so teaching the layer parser the pronoun would route The Wandering
# Emperor's entire `+1` to `create_continuous_effect_of_ability`: first strike
# granted, the +1/+1 counter never placed, and the card scoring HANDLED. The
# pair is merged here instead, ahead of that fallback, and the rider's layer
# effect is built off a canonical rewrite of its own sentence alone.

#: The object pronouns this wave reads, wherever they sit in the rider - "It
#: gains first strike" (subject) and "Put two stun counters on it" (object)
#: are the same anaphor in two syntactic positions, so a subject-anchored
#: regex like `_ANAPHORIC_SUBJECT_RE`'s cannot serve.
#:
#: "He"/"she"/"him"/"her" belong here too: recent templating gives a
#: legendary permanent with an established character its own gendered
#: pronoun once the antecedent clause has already named it (by printed name,
#: normalised to "this permanent" by `self_normalized_effect_text` before
#: this ever runs) - Edgar, Ancient Bloodlord's "Put a +1/+1 counter on
#: Edgar. He gains menace until end of turn." is exactly the pattern "It
#: gains first strike." already reads, spelled with the character's own
#: pronoun instead of "it". A player is never referred to this way in
#: current templating (CR wording always says "that player"/"you"/
#: "opponent"), so there is no ambiguity with the player anaphor family
#: below.
#:
#: "That player" is **not** here: it is a player anaphor and
#: `_ANAPHORIC_SUBJECT_RE`/`_parse_referent_clause` already own it.
#:
#: "Each of them" is the same plural anaphor as bare "them", written the way
#: CR templating spells it when the rider's own verb is distributive rather
#: than collective - Seasoned Cryomancer's own "tap up to that many target
#: creatures and put a stun counter on **each of them**" is "on them" with
#: the same referent, not a different antecedent shape; `_parse_object_
#: anaphor_clause_pair`'s per-referent rider loop already applies every
#: rider to each object in the list one at a time; either wording runs it.
#:
#: "That creature or planeswalker" is the two-noun form a "target creature or
#: planeswalker" antecedent is referred back with (Scorching Dragonfire's and
#: Bouncer's Beatdown's "If that creature or planeswalker would die this
#: turn, exile it instead.") - one object, named by the same noun list its
#: own target phrase printed.
_ANAPHOR_NOUN = r"(?:creature|planeswalker|permanent|artifact|enchantment|land|battle|token|card)"
_OBJECT_ANAPHOR = (
    r"(?:it|they|them|each of them|he|she|him|her|"
    rf"that {_ANAPHOR_NOUN}(?: or {_ANAPHOR_NOUN})?)"
)
_OBJECT_ANAPHOR_RE = re.compile(rf"\b{_OBJECT_ANAPHOR}\b", re.IGNORECASE)


#: What an antecedent clause's own words say its objects are - the three
#: shapes this wave can answer, and nothing else.
ReferentReader = Callable[["Game", "StackObject"], list[CardState]]


#: "all creatures", "each creature" - the antecedent acted on a whole group.
_MASS_CREATURE_SUBJECT_RE = re.compile(r"\b(?:all|each) creatures?\b", re.IGNORECASE)


#: What a rider does to the objects its antecedent found. `stack_object` is
#: passed through for the source name a prompt or a continuous effect needs.
ReferentObjectClause = Callable[["Game", list[CardState], "StackObject"], None]


#: The self-reference a *standalone* clause (not a rider with an antecedent
#: of its own) names when nothing else established a referent - CR 601.2c's
#: ordinary anaphor resolution, the ability's own source: `_OBJECT_ANAPHOR`'s
#: pronouns (Encumbered Reejerey's "remove a -1/-1 counter from **it**") or
#: CR 700.7's own "this <noun>" (Bristlebane Battler's "... from **this
#: creature**", Clockwork Steed's own intervening-if subject).
_SELF_ANAPHOR = (
    rf"(?:{_OBJECT_ANAPHOR}|this (?:creature|permanent|artifact|enchantment|land|token|card))"
)


#: "Draw cards equal to `<expr>`." - Rise of the Deathbringer's own mode 1.
_DRAW_CARDS_EQUAL_TO_RE = re.compile(r"^draw cards? equal to (?P<expr>.+?)$", re.IGNORECASE)


#: "Imprint" and its plain-English relatives - "you may exile a `<quality>`
#: card [with mana value N or greater/less] from your hand" (Ugin's
#: Labyrinth). CR 207.2c: "Imprint" is an ability word and "[has] no special
#: rules meaning" of its own, so nothing here reads the word itself - only the
#: sentence that follows it, the same CR 608.2d "you may" shape
#: `_parse_optional_player_clause` reads for a plain player clause, with a
#: quality restriction on top the way `_SEARCH_AND_PUT_RE` restricts a search.
_HAND_EXILE_RE = re.compile(
    r"you may exile (?:a|an) (?P<quality>.+?) card"
    r"(?: with mana value (?P<mv>\d+) or (?P<cmp>greater|less))?"
    r" from your hand",
    re.IGNORECASE,
)

#: CR 105.2c: "A colorless object has no color" - colorless is not one of CR
#: 105.1's five colours, so it is not `Color.COLORLESS` matched against
#: `Card.colors` (never populated with it), it is the absence check itself.
_HAND_EXILE_COLOR_WORDS: dict[str, Color | None] = {
    "colorless": None,
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _permanent_id_and_name(stack_object: "StackObject", *, for_spell: bool) -> tuple[UUID, str]:
    """The id and display name of whatever ability this clause is printed on -
    the spell's own id and name if it resolves as a permanent (a spell keeps
    its `id` once it becomes the battlefield object, see `CardState.move_to`),
    or the resolving ability's `source_id`/`source_name` (CR 113.7a: the
    source may already be gone, which is why the name travels separately).
    """
    if for_spell:
        assert isinstance(stack_object, CardState)
        return stack_object.id, stack_object.card.name
    assert isinstance(stack_object, AbilityOnStack)
    source_id = stack_object.source_id
    assert source_id is not None
    return source_id, stack_object.source_name


# --------------------------------------------------------------------------
# "You may sacrifice ... If you do, ..." (CR 118.12)
# --------------------------------------------------------------------------
#
# Verified this session with `knowledge_search(q="...", type="rules")`, then
# read in full off the local CR mirror at the tail `knowledge_search`'s own
# 180-character truncation cut off, at CR 118.12 (the search's own excerpt
# confirmed that number and no other):
#
#   "Some spells, activated abilities, and triggered abilities read, '[Do
#   something]. If [a player] [does, doesn't, or can't], [effect].' Or '[A
#   player] may [do something]. If [that player] [does, doesn't, or can't],
#   [effect].' The action [do something] is a cost, paid when the spell or
#   ability resolves. The 'If [a player] [does, doesn't, or can't]' clause
#   checks whether the player chose to pay an optional cost or started to pay
#   a mandatory cost, regardless of what events actually occurred."
#
# Two consequences of that last sentence drive everything below:
#
# - "If you do" is not a check on the *board* after the sacrifice - it is a
#   check on the *choice*. Once CR 608.2d's "you may" comes back yes, the
#   sacrifice always succeeds (CR 701.21a has no failure mode for sacrificing
#   a permanent you control - unlike `destroy`, nothing refuses it), so this
#   never has to ask "did it actually happen"; it only has to ask "did the
#   player say yes", exactly the `Game.may`/`Game.ask(MAY)` question
#   `_optional_clause` and `_optional_targeted_clause` already put for every
#   other "you may".
# - CR 608.2d then forbids offering a choice with no legal way to pay it: a
#   "you may sacrifice another creature" with no other creature to sacrifice
#   is not merely a bad idea, it is impossible, the same `affirmative_is_
#   legal` shape `may_pay_life` (CR 119.4) and `_parse_imprint_clause`
#   (CR 608.2d generally) already use. Disciple of Freyalise with no other
#   creature on the battlefield is never asked the question at all.
#
# The sacrificed permanent's power is read **before** `Game.sacrifice` moves
# it to the graveyard, the same CR 608.2i snapshot `_parse_anaphoric_clause_
# pair` already takes for "its controller gains life equal to its power" -
# reading it afterward would see the empty post-`move_to` husk instead of the
# real, possibly anthemed or +1/+1-countered, value.

#: The whole shape, read off the ability's own printed text with the clause
#: splitter never touched: `split_effect_clauses`'s bare `\band\b` cut would
#: otherwise slice Disciple of Freyalise's own "you gain X life and draw X
#: cards, where X is that creature's power" into three unrelated fragments,
#: the same reason `_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE` is read whole
#: ahead of the ordinary dispatcher rather than through it.
_MAY_SACRIFICE_IF_YOU_DO_RE = re.compile(
    r"^you may sacrifice (?P<restriction>[^.]+)\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


#: One permanent - "this `<type>`", "another `<type>`", "a `<type>`".
_ONE_PERMANENT = Quantity(amount=1, minimum=1, source=QuantitySource.FIXED)


class _SacrificeRestriction(NamedTuple):
    """What `_sacrifice_restriction` read: whether the permanent is the
    ability's own source, how many to sacrifice, and a function reading the
    legal candidates off the battlefield as the effect resolves."""

    is_self: bool
    candidates: Callable[["Game", Player, UUID | None], list[CardState]]
    quantity: Quantity


class ConditionalClauseNotice(EngineModel):
    """One "you may sacrifice `<restriction>`. If you do, `<consequence>`."
    effect (CR 118.12) whose restriction or consequence this wave could not
    read.

    The same unreadable-is-not-the-same-as-no-effect record `TargetingNotice`,
    `InterveningIfNotice`, `ModeNotice`, `AnaphoricClauseNotice`, `ImprintNotice`,
    `LayerNotice`, and `CostModifierNotice` already keep for their own gaps -
    this shape's own defect, before this wave, was every card printing it
    (Disciple of Freyalise, Sanctum of Ugin, and Necrodominance's variable-life
    cousin) resolving with no effect and no trace of why.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


class SuspendRedirectNotice(EngineModel):
    """Retired: the notice Delay's counter-into-suspend paragraph used to
    fail closed into, before `_parse_exile_into_suspend_clauses` executed it.
    Nothing constructs one any more; the model is kept only because
    `Game.suspend_redirect_notices` still names it, so the persisted shape of
    a `Game` does not change."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


class ReflexiveClauseNotice(EngineModel):
    """One "`<action>`. When you do, `<consequence>`." effect (CR 603.12)
    whose action or consequence this wave could not read.

    Guide of Souls' "you may pay {E}{E}{E}. When you do, put two +1/+1
    counters and a flying counter on target attacking creature ..." is the
    reason this exists rather than the ability simply resolving as nothing:
    paying energy is a missing primitive (`docs/engine-coverage.md`), but a
    trigger that does nothing must still say why, the same unreadable-is-not-
    the-same-as-no-effect record `ConditionalClauseNotice` and its siblings
    already keep."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unreadable clause itself, as printed."""


def pay_consequence_effect(text: str) -> AbilityEffect | None:
    """The consequence of a paid "you may pay `<cost>`. If you do, ..." (CR
    118.12), run on the same ability that paid: an ordinary clause sequence
    (`parse_mixed_effect`), the whole-text control-steal shape
    (`_parse_untap_and_gain_control_ability` - Eldrazi Obligator's own "gain
    control of target creature until end of turn, untap that creature, and
    it gains haste until end of turn.", which needs its three clauses read
    together rather than split at `parse_mixed_effect`'s own clause
    boundaries), the whole-text token-creation shape (`_parse_whole_text_
    token_clause` - Vile Redeemer's own "create ... token for each ....
    Those tokens have "...".", the following-sentence grant `_parse_mixed_
    clauses`'s per-clause split would otherwise strand on its own unreadable
    sentence), or one of `_layer_consequence`'s one-shot continuous effects.
    `None` when none of them reads it."""
    copy_that_spell = _parse_copy_that_spell_clause(text, for_spell=False)
    if copy_that_spell is not None:
        return copy_that_spell
    control_steal = _parse_untap_and_gain_control_ability(text)
    if control_steal is not None:
        return control_steal
    whole_text_token = _parse_whole_text_token_clause(text)
    if whole_text_token is not None:
        return whole_text_token
    from .counters import _parse_counters_on_group_then_grant_clause

    return (
        parse_mixed_effect(text)
        or _parse_counters_on_group_then_grant_clause(text)
        or _layer_consequence(text)
    )


# --------------------------------------------------------------------------
# Delayed-trigger clauses (CR 603.7)
# --------------------------------------------------------------------------
#
# "At the beginning of the next end step, return that card to the battlefield
# under its owner's control" is not something that happens *now* - it is an
# instruction to create a delayed triggered ability (`machines/delayed.py`)
# that fires later. Phelia, Exuberant Shepherd's attack trigger used to resolve
# and do nothing: its first clause ("exile up to one other target nonland
# permanent") is `_EXILE_TARGET_RE`'s ordinary shape, but its second and third
# clauses had no reader, so `parse_mixed_effect` correctly refused the *whole*
# ability (CR 608.2c has no notion of running half an instruction) - silently.
#
# The linkage this needs that no other clause pair does: clause two's "that
# card" is not a target of its own (CR 400.7's anaphora, same idea as
# `_ANAPHORIC_SUBJECT_RE`), it is whichever object clause one's own verb just
# moved - discovered only once clause one actually runs, at resolution. So the
# combined effect below runs clause one itself (rather than delegating to
# `exile_ability_targets`, which throws the moved object away) and closes over
# the result when it builds the `DelayedTrigger`.

#: The timing phrases this wave reads live in `machines/delayed.py` as
#: `ANAPHORIC_TIMING_STEPS`, which carries the CR 511.2 / CR 513.2 reasoning
#: for why waiting for the *next* occurrence of a step needs no bookkeeping.
#: This file used to keep a byte-identical private copy; the copy is gone, and
#: the two word orders below are now derived from the one table rather than
#: restating its contents. The import can only run this way round -
#: `effects.py` imports `delayed.py`, never the reverse.
_DELAYED_TIMING_PATTERN = "|".join(re.escape(phrase) for phrase in ANAPHORIC_TIMING_STEPS)

#: "At <timing>, <verb>." - Phelia's own word order.
_DELAYED_TIMING_LEADING_RE = re.compile(
    rf"^at (?P<timing>{_DELAYED_TIMING_PATTERN}),\s*(?P<verb>.+)$", re.IGNORECASE
)
#: "<Verb> at <timing>." - Postmortem Lunge's, Nahiri's, Aether Membrane's,
#: Mishra's Bauble's, and dash's reminder text's word order.
_DELAYED_TIMING_TRAILING_RE = re.compile(
    rf"^(?P<verb>.+?)\s+at (?P<timing>{_DELAYED_TIMING_PATTERN})$", re.IGNORECASE
)


def _parse_delayed_timing_clause(clause: str) -> tuple[Step, str] | None:
    """Split `clause` into the step it waits for and the verb phrase left
    over, in whichever of the two word orders `ANAPHORIC_TIMING_STEPS` prints
    it in - or `None` if it names no timing phrase this wave reads at all."""
    clause = clause.strip().rstrip(".")
    match = _DELAYED_TIMING_LEADING_RE.fullmatch(clause) or _DELAYED_TIMING_TRAILING_RE.fullmatch(
        clause
    )
    if match is None:
        return None
    step = ANAPHORIC_TIMING_STEPS.get(match.group("timing").lower())
    if step is None:
        return None
    return step, match.group("verb").strip()


#: "draw a card"/"draw N cards" - Mishra's Bauble's own bare "draw a card"
#: (no object at all), used where a count word may appear (Artist's Talent's
#: "If you do, draw a card" as a `_parse_sacrifice_consequence` shape, and a
#: delayed "draw N cards at the beginning of ..." in `_parse_delayed_single_
#: clause`).
_DRAW_N_CARDS_RE = re.compile(rf"^draw (?P<count>{COUNT}) cards?$", re.IGNORECASE)


class DelayedClauseNotice(EngineModel):
    """One delayed-trigger clause (CR 603.7) whose timing this wave recognised
    - "at the beginning of the next end step", "at end of combat", "at the
    beginning of the next turn's upkeep" - but whose antecedent or verb it
    still could not read, so `parse_mixed_effect`/`parse_mixed_effect_for_
    spell` refused the whole ability rather than exiling (say) a permanent it
    could never guarantee returning. Postmortem Lunge's "Exile it at the
    beginning of the next end step" (the antecedent is a reanimation target
    with a variable mana value, not this wave's shape) and Nahiri, the
    Harbinger's -8 (the antecedent is a search result, not a target or an
    event subject) are both this: the same "unreadable is not the same as no
    effect" record `AnaphoricClauseNotice` and its siblings already keep.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str


class ControlReplacementNotice(EngineModel):
    """A resolving spell's own "if [a permanent] would enter the battlefield
    under [a player]'s control [this turn], it enters under [another
    player]'s control instead" (CR 614.1a's `IF_WOULD_INSTEAD` shape) whose
    subject or players `machines/replacement.created_replacement_spec` does
    not read - recognised by shape, not built.

    Gather Specimens itself is read (`EnterUnderYourControl`, created by
    `_parse_created_replacement_spell_text` ahead of this in the dispatch
    chain); this is the fail-closed net for a differently worded sentence of
    the same shape, recorded rather than silently dropped, the same
    "unreadable is not the same as no effect" convention every other notice
    class here keeps.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str


class UnmodeledTriggerEffectNotice(EngineModel):
    """One triggered ability whose *condition* this engine reads and fires
    for real - CR 120.2a's "deals combat damage to a player"/"to an opponent",
    matched generically off any card's printed text by
    `machines/triggers.condition_matches` - but whose resolution clause names
    a mechanism this engine has nowhere to put: a choice
    between zero and many cards with no fixed count whose surrounding sentences
    this file cannot read (the bare-clause case; **Nashi, Searcher in the Dark
    is no longer one of these** - `Decision.exact=False` is CR 107.1c's "any
    number" and `_parse_mill_that_many_then_take_from_among_them` reads its
    whole three-sentence paragraph), or a target chosen at CR 603.3d announcement but
    restricted to what a upstream game *event* says rather than what the
    ability's own printed text says (Questing Beast's "target planeswalker
    **that player** controls", where "that player" is whoever the trigger's
    own combat damage was dealt to - `machines/targeting.profile_for_text`
    only ever reads a targeting restriction off the ability's static text).

    Each of these is a missing primitive, not a hard-to-parse sentence, so the
    ability still triggers and goes on the stack (CR 603.3), and this is the
    "unreadable is not the same as no effect" record every other notice list
    in this module already keeps, rather than the ability silently doing
    nothing with no trace of why.

    **Ragavan, Nimble Pilferer used to be the third card here** - "until end of
    turn, you may cast that card" - and is not any more: the per-instance,
    time-boxed permission it names is built, as `machines/casting.
    PlayPermission` and `Game.grant_play_permission`. What is left of that
    shape here is `_unreadable_cast_permission_clause`, which now only fires
    for a permission sentence whose *antecedent* clause this file cannot read -
    a "you may cast that card" with no recognisable exiling clause in front of
    it to say which card - since granting a permission over nothing at all
    would be the silent half-run this notice exists to prevent.

    **A spell records it too.** An instant or sorcery whose printed text
    `effect_for` has no reader for resolves and goes to the graveyard
    (`Game.resolve`), and used to do so with no trace - Stock Up in a live
    game. It now appends this same notice, `source_id` the spell's own id,
    `source_name` the face's name, `text` the face's whole printed text. Not
    for a permanent spell (CR 608.3a) or a spell that left a replacement
    effect (Plagiarize, CR 614.1a).

    **So does any triggered ability no reader answers for.** When
    `trigger_effect_for` returns None for a triggered ability with printed
    effect text, `Game._note_unread_trigger` appends this notice as the
    ability resolves, with the ability's whole effect text. Nothing records it
    at trigger time; Dress Down's end step trigger used to resolve as CHANGED
    NOTHING with no trace.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    text: str
    """The unread portion of the ability's printed effect, or the whole of it
    when none of it runs."""


# --------------------------------------------------------------------------
# "Until end of turn, you may cast/play [it|that card|those cards]"
# (CR 601.3, CR 601.1a, CR 514.2)
# --------------------------------------------------------------------------
#
# Two cards in the pool print this, and they differ in every way that matters:
# Ragavan, Nimble Pilferer exiles **one** card, from an **opponent's** library,
# and may cast it for its own mana cost; Ugin, Eye of the Storms' −11 exiles
# **any number** of cards, from **its own controller's** library, and casts
# them for nothing (CR 118.9's "without paying its mana cost"). Both halves are
# read off the printed sentence pair rather than keyed by card name, so a
# future card printing the same shape is covered with no registry row.
#
# The permission itself is `machines/casting.PlayPermission`, handed out by
# `Game.grant_play_permission`. This module only reads the sentence and names
# the cards; see that class for why the permission is per-object and bounded.

#: The second sentence of the pair. "Play" and "cast" are kept apart on purpose
#: (CR 601.1a, CR 701.18b: playing a card is playing it as a land *or* casting
#: it as a spell), and "without paying its/their mana cost(s)" is CR 118.9's
#: alternative cost of nothing, which CR 107.3b keeps distinct from an
#: alternative cost with something in it.
#:
#: The duration is printed either way round - "Until end of turn, you may cast
#: that card" (Ragavan) or "You may cast that card this turn" (Emry, Lurker of
#: the Loch) - and CR 514.2 ends both in the same cleanup step: "all 'until end
#: of turn' and 'this turn' effects end". Exactly one of the two is required.
#:
#: The permission's own subject pronoun is "you" on nearly every card, because
#: nearly every one grants the permission to its own caster or controller -
#: but a *third-person* triggered ability whose CR 607.1 antecedent is some
#: other player (Urabrask, Heretic Praetor's "the next time **they** would
#: draw ..., instead **they** exile ... **They** may play it this turn.")
#: prints "they"/"that player" instead, naming exactly the same permission.
#: Nothing downstream reads which pronoun matched - only `action`, `subject`,
#: `free`, `leading`, and `trailing` are ever inspected - so widening the
#: front of the sentence costs nothing and reads every printing generally.
#:
#: A third shape carries no turn-bounded duration at all - "You may play that
#: card for as long as it remains exiled" (Court of Locthwain, Thought-String
#: Analyst) - and needs none: `PlayPermission.names` already refuses once the
#: card's own `zone_change_stamp` changes (CR 400.7), which is exactly what
#: leaving exile does, so `until_end_of_turn=False` is what this shape grants.
#: A trailing "... and mana of any type can be spent to cast it" rider -
#: Hostage Taker's, Gonti, Lord of Luxury's, and roughly three dozen other
#: real printings' own shared sentence tail on this exact permission shape
#: (`PlayPermission.any_type_mana`) - is read separately, by
#: `_ANY_TYPE_MANA_STANDALONE_RE` below: `split_effect_clauses` cuts it off
#: this sentence as its own clause (the same mid-sentence ", and" boundary
#: it already splits everywhere else), so this pattern never actually sees
#: it and does not try to match it inline.
#:
#: Two longer durations are printed on the same sentence, either way round
#: too: "Until the end of your next turn, you may play those cards" (Cori
#: Mountain Monastery, Burning Curiosity, Reckless Impulse) and "Until your
#: next end step, you may play those cards" (Riveteers Charm) / "You may play
#: it until your next end step" (Haste Magic). CR 611.2a: each lasts exactly
#: as long as stated - `_permission_duration` names which one was printed,
#: and every reader of this pattern either honours that name or refuses it.
_PLAY_PERMISSION_RE = re.compile(
    r"^(?P<leading>(?:until end of turn|until the end of your next turn"
    r"|until your next end step), )?"
    r"(?:you|they|that player) may (?P<action>cast|play) "
    r"(?P<subject>it|that card|those cards|them|one of (?:those cards|them)"
    r"|spells from among those cards)"
    r"(?P<free> without paying (?:its|their) mana costs?)?"
    r"(?P<trailing> this turn| for as long as (?:it remains|they remain) exiled"
    r"| until the end of your next turn| until your next end step)?$",
    re.IGNORECASE,
)


class PermissionDuration(StrEnum):
    """Which duration a `_PLAY_PERMISSION_RE` sentence printed (CR 611.2a)."""

    THIS_TURN = "this turn"
    """"Until end of turn"/"this turn" - CR 514.2's cleanup."""
    NEXT_TURN = "the end of your next turn"
    """Until the cleanup of the controller's own next turn."""
    NEXT_END_STEP = "your next end step"
    """Until the controller's next end step begins."""
    WHILE_EXILED = "as long as it remains exiled"
    """No turn-bounded duration at all (CR 400.7 ends it)."""


def _permission_duration(match: re.Match[str]) -> PermissionDuration | None:
    """The one duration a `_PLAY_PERMISSION_RE` match printed, or `None` when
    it printed none or two."""
    leading = (match.group("leading") or "").strip().rstrip(",").lower()
    trailing = (match.group("trailing") or "").strip().lower()
    if not leading and not trailing and match.group("action").lower() == "play":
        # "You may play them." with no duration (Dungeon of the Mad Mage's
        # Runestone Caverns): CR 611.2a - no stated duration lasts until the
        # end of the game, and CR 400.7 ends it the moment the card leaves
        # exile. "Play" cannot be a CR 608.2g play during the resolution (a
        # land is never played then), so this is the permission.
        return PermissionDuration.WHILE_EXILED
    if bool(leading) == bool(trailing):
        return None
    phrase = leading or trailing
    if phrase in ("until end of turn", "this turn"):
        return PermissionDuration.THIS_TURN
    if phrase == "until the end of your next turn":
        return PermissionDuration.NEXT_TURN
    if phrase == "until your next end step":
        return PermissionDuration.NEXT_END_STEP
    return PermissionDuration.WHILE_EXILED


#: The plural pronouns. CR 607.1's within-one-ability anaphora has to agree in
#: number with the clause it points back at: "that card" cannot refer to a
#: search that exiled four cards, and "those cards" cannot refer to a single
#: exiled top card. Refusing a mismatch is what keeps a future card's sentence
#: from being read as a shape it is not.
_PLURAL_PERMISSION_SUBJECTS = frozenset(
    {"those cards", "them", "one of those cards", "one of them", "spells from among those cards"}
)


#: A clause that exiles cards, read as "which objects the next sentence's
#: pronoun points at" (CR 607.1). Returns the cards it exiled, in the order it
#: exiled them, so the permission clause can be granted against exactly those
#: objects and no others.
ExileAntecedent = Callable[["Game", AbilityOnStack], list[CardState]]


#: "exile the top card of your library" - the controller's own library, the
#: antecedent Experimental Synthesizer prints in front of "Until end of turn,
#: you may play that card."
_EXILE_TOP_OF_YOUR_LIBRARY_RE = re.compile(
    rf"^exile (?:the top (?:card|{count_pattern('n', x=True)} cards) of your library"
    rf"{where_x_pattern('where_x')}"
    r"|(?P<that_many>that many) cards from the top of your library)$",
    re.IGNORECASE,
)


#: "exile cards from the top of your library until you exile a <quality> card"
#: (Territorial Bruntar's "a nonland card") and "... until you exile cards with
#: total mana value N or greater" (Improvisation Capstone) - the two stop
#: conditions `machines/keywords.exile_until` is given here. Cascade and
#: discover are the same process with their own keyword-defined stop.
_EXILE_UNTIL_QUALITY_RE = re.compile(
    r"^exile cards from the top of your library until you exile an? "
    r"(?P<quality>[\w' ,-]+?) card$",
    re.IGNORECASE,
)


#: "that player exiles cards from the top of their library until they exile a
#: `<quality>` card" - Black Widow, Super Spy's own combat-damage trigger, the
#: identical `keywords.exile_until` process `_EXILE_UNTIL_QUALITY_RE` already
#: reads, third-person over CR 120.2a's damaged player instead of first-person
#: over the controller - the same anaphora `_EXILE_TOP_OF_THAT_PLAYERS_
#: LIBRARY_RE` already reads for a fixed count.
_EXILE_UNTIL_QUALITY_THIRD_PERSON_RE = re.compile(
    r"^that player exiles cards from the top of (?:their|his or her) library until "
    r"(?:they|that player|he or she) exiles? an? (?P<quality>[\w' ,-]+?) card$",
    re.IGNORECASE,
)


#: "... and mana of any type can be spent to cast it/that spell/them." -
#: `split_effect_clauses` cuts this off the permission sentence as its own
#: clause (a mid-sentence ", and" join, the same boundary it already splits
#: on everywhere else), so it is matched as its own optional clause rather
#: than folded into `_PLAY_PERMISSION_RE`, which only ever sees the sentence
#: up to that comma.
_ANY_TYPE_MANA_STANDALONE_RE = re.compile(
    r"^(?:if you cast a spell this way, )?mana of any type can be spent to cast "
    r"(?:it|that spell|them|those spells)\.?$",
    re.IGNORECASE,
)


#: Manamorphose: "Add two mana in any combination of colors." CR 106.4's
#: mana-to-the-pool instruction again, but with a colour chosen per unit
#: (CR 107.4h: "any combination of" divides the total into individually
#: chosen parts) rather than `_ADD_MANA_RE`'s literal run of printed symbols.
#: `DecisionKind.CHOOSE_A_QUALITY` is the same kind `_parse_destroy_each_
#: then_add_mana_per_destroyed` already asks through for Culling Ritual's own
#: per-unit colour choice.
#:
#: The whole phrase family reads here, on a resolving spell or ability (a
#: loyalty ability is never a mana ability, CR 605.1a, so Xenagos, the
#: Reveler's "+1" resolves through this too):
#:
#: - the universe: CR 106.1a's five ("colors") or a printed palette ("{R}
#:   and/or {G}"; "{U}, {B}, and/or {R}"), each unit chosen among it;
#: - the count: a printed number (Manamorphose's "two"), CR 107.3's X with a
#:   "where X is <count>" the board answers as it resolves (Xenagos's "the
#:   number of creatures you control", CR 608.2h), or "that much" - CR 607.1's
#:   anaphora onto the triggering event (Grand Warlord Radha's attackers).
_ADD_ANY_COMBINATION_MANA_RE = re.compile(
    rf"^add (?:(?P<that_much>that much)|{count_pattern('n', x=True)}) mana in any combination of "
    r"(?P<palette>colors|\{[wubrg]\}(?:, \{[wubrg]\})*,? and/or \{[wubrg]\})"
    rf"{where_x_pattern()}\.?$",
    re.IGNORECASE,
)


class _CopyExceptionList(NamedTuple):
    """`_read_copy_exception_list`'s answer, in `token_copy_of`'s terms."""

    not_legendary: bool
    added_creature_type: str | None
    power: int | None
    toughness: int | None
    added_abilities: tuple[str, ...]


def _nonland_or_typed_card_matcher(quality: str) -> Callable[[CardState], bool] | None:
    """A predicate for "a `<quality>` card", where `<quality>` is either a
    bare type `_quality_matcher` already reads, that type's negation,
    spelled "non`<type>`" (Thoughtseize's own "nonland"), CR 110.4a's
    "permanent" noun with an optional "non`<type>`" qualifier in front of it
    (Solve for Disappointment's own "nonland permanent"), or a comma/"or"
    list of qualities (Chandra, Chill of Compliance's own "a noncreature,
    nonland card"). `_quality_matcher` has no notion of "non" on its own,
    and no notion of "permanent" as a card-type group rather than a single
    `Type` either - every caller before this one only ever named what to
    *include*, and only ever a single printed type - so this reads the
    negation and the compound noun itself and delegates everything else.
    """
    quality = quality.strip().lower()
    if quality.endswith(" permanent"):
        prefix = quality.removesuffix(" permanent").strip()
        prefix_matches = _nonland_or_typed_card_matcher(prefix) if prefix else None
        if prefix and prefix_matches is None:
            return None

        def is_permanent_card(state: CardState) -> bool:
            if not (_PERMANENT_CARD_TYPES & set(state.types)):
                return False
            return prefix_matches is None or prefix_matches(state)

        return is_permanent_card
    # A comma or "or" joins several qualities - Chandra, Chill of
    # Compliance's own "a noncreature, nonland card" among them -
    # `_quality_matcher` already reads each word's own "non" prefix (via
    # `_named_type_matcher`) and already combines an all-negation list as a
    # conjunction (De Morgan) rather than a disjunction, so this delegates
    # straight to it rather than reading `quality.split()` on whitespace,
    # which would instead see "noncreature," (a stray comma still attached)
    # and "nonland" as if they were the two words of the single-negation
    # compound below - the wrong shape entirely.
    if "," in quality or " or " in quality:
        return _quality_matcher(quality)
    if quality == "nonland permanent":
        # CR 110.1: a permanent is a card on the battlefield of the six
        # types CR 300.1 lists minus instant and sorcery - "nonland
        # permanent card" (Solve for Disappointment) is CR 108.3's own
        # object still in a player's hand, judged by the same type list.
        def is_nonland_permanent(state: CardState) -> bool:
            permanent_types = {
                Type.ARTIFACT,
                Type.BATTLE,
                Type.CREATURE,
                Type.ENCHANTMENT,
                Type.PLANESWALKER,
            }
            return bool(permanent_types & set(state.types)) and Type.LAND not in state.types

        return is_nonland_permanent
    if quality.startswith("non"):
        words = quality.split()
        if len(words) == 2:
            try:
                excluded = Type(words[0].removeprefix("non").strip())
            except ValueError:
                return None
            included = _quality_matcher(words[1])

            def not_matches_but_is(state: CardState) -> bool:
                return excluded not in state.types and included(state)

            return not_matches_but_is
        try:
            excluded = Type(quality.removeprefix("non").strip())
        except ValueError:
            return None

        def not_matches(state: CardState) -> bool:
            return excluded not in state.types

        return not_matches
    return _quality_matcher(quality)


#: Shared by every "owner puts it into a library" subject form below - CR
#: 608.2d's own choice, worded either as Subtlety's/Aether Gust's/Sudden
#: Setback's/Misleading Motes' bare "puts it on their choice of the top or
#: bottom of `<library>`", or as Wan Shi Tong's/Deem Inferior's "puts it into
#: `<library>` `<ordinal>` from the top or on the bottom", whose own top side
#: lands at a printed depth (CR 609.3's "as much as it can" when the library
#: is shallower than that) rather than the very top. Written once so every
#: subject form only has to name its own target and spell "puts it" a single
#: time between them.
_OWNER_PUTS_IT_INTO_LIBRARY_TAIL = (
    r"puts it (?:on their choice of the top or bottom of (?:their|its owner'?s) library"
    rf"|into (?:their|its owner'?s) library (?P<ordinal>{ORDINAL}) "
    r"from the top or on the bottom)\.?$"
)


#: "create a number of `<descriptor>` tokens equal to its power|toughness" -
#: the returned object's own number, read from its last existence on the
#: battlefield (CR 608.2h).
_TOKENS_EQUAL_TO_ITS_STAT_RE = re.compile(
    r"^create a number of (?P<desc>.+?) tokens equal to its (?P<stat>power|toughness)\.?$",
    re.IGNORECASE,
)


#: Moved to `machines/abilities.self_normalized_effect_text` so
#: `machines/layers.py` (which `machines/effects.py` itself imports from, so
#: cannot be imported *by* it without a cycle) can share the same rewrite for
#: the continuous-effect sentences it reads straight off `CardState.
#: oracle_text` - Ruby, Daring Tracker's "Ruby gets +2/+2 until end of turn."
#: needs the identical CR 201.5 self-reference handling there, not only on the
#: `effect_text` this module's own parsers see. Aliased under the old private
#: name so every existing call site below is unchanged.
_self_normalized_effect_text = self_normalized_effect_text


# --------------------------------------------------------------------------
# Reading a *card's* description, for a clause that names cards in a zone
# --------------------------------------------------------------------------
#
# `_parse_mass_type_qualifier` above reads the description in a mass
# battlefield clause ("each nonland permanent", "all artifacts") through
# `Game.characteristics_of`, which only exists for something on the
# battlefield (the computed board holds only what is on the battlefield, and a graveyard is not).
# A clause naming *cards* in a graveyard - Raise the Past's "all creature
# cards with mana value 2 or less from your graveyard" - has no computed
# characteristics to read at all: CR 400.7 makes a card in a graveyard a new
# object with only its printed characteristics, so this reads `Card` directly.
#
# The two qualifiers this reads, on top of the card types
# `_singular_card_type` already knows:
#
# - a **subtype negation** - Overlord of the Balemurk's "non-Avatar creature
#   card", Sunderflock's "non-Elemental creatures" - CR 205.3's subtypes,
#   negated the way CR 205.2a's "nonland" negates a card type.
# - a **mana value bound** - "with mana value N or less"/"or greater"
#   (CR 202.3), the same comparison `_MASS_MANA_VALUE_RE` already reads on the
#   battlefield side.

#: "non-Avatar creature card", "non-Elemental creature" - one negated
#: subtype (CR 205.3) ahead of the rest of the description.
_NON_SUBTYPE_PREFIX_RE = re.compile(r"^non-(?P<subtype>[A-Za-z]+)\s+(?P<rest>.+)$")

#: "<description> with mana value N or less"/"or greater" (CR 202.3).
_CARD_MANA_VALUE_BOUND_RE = re.compile(
    r"^(?P<inner>.+?) with mana value (?P<n>\d+) or (?P<dir>less|greater)$", re.IGNORECASE
)

#: The bare noun a card description ends in. "permanent card(s)" is CR 110.4a's
#: group - a card of any type that would become a permanent - and is read here
#: rather than through `_singular_card_type`, which only knows CR 205.2a's
#: individual types.
_PERMANENT_CARD_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)


def _parse_card_group_qualifier(phrase: str) -> Callable[[CardState], bool] | None:
    """A predicate over a **card** (not a battlefield permanent) for one
    description in a clause that names a group of cards - "creature cards
    with mana value 2 or less", "non-Avatar creature card", "permanent card".

    Read off `CardState.card`'s printed characteristics, which is what
    CR 400.7 leaves a card in a graveyard, hand or library with: "an object
    that moves from one zone to another becomes a new object with no memory
    of ... its previous existence", and nothing on the battlefield's computed
    board applies to it.

    Returns `None` - fail-closed, per this file's rule - for any description
    it cannot read whole, so a caller never runs a mass instruction over a
    group it only half understood. "or" between two descriptions ("a
    non-Avatar creature card **or** a planeswalker card") is not read here:
    that is a *list* of descriptions, and `_parse_card_group_alternatives`
    below is what splits it before each half reaches this.
    """
    text = phrase.strip()
    named = re.fullmatch(r"cards? named (?P<name>.+)", text, re.IGNORECASE)
    if named is not None:
        # CR 201.2a: "Two or more objects have the same name if they have at
        # least one name in common." Demigod of Revenge's own cast trigger
        # ("return all cards named Demigod of Revenge from your graveyard to
        # the battlefield.") is the reported shape, but the name compared
        # here is read straight off whatever `phrase` itself prints, not a
        # literal fitted to that one card - a future "cards named `<Y>`" on
        # any other printing reads the identical way for whatever `<Y>` it
        # names, self-referential or not.
        name = named.group("name").strip()

        def matches_name(state: CardState) -> bool:
            return state.name == name

        return matches_name
    if re.fullmatch(r"historic(?: cards?)?", text, re.IGNORECASE):
        # CR 700.6 (Ballad of the Black Flag's "a historic card from among
        # them") - the same `_historic` the search-quality reader uses.
        return _historic
    if re.fullmatch(r"cards? with \{x\} in (?:its|their) mana cost", text, re.IGNORECASE):
        # Paradox Surveyor's own "a card with {X} in its mana cost" - CR
        # 202.1's printed mana cost carrying a variable symbol (CR 107.3,
        # `ManaCost.x_count`), read off the card as printed (a library card
        # is never on the computed board, CR 613.5's layers do not apply)
        # rather than a mana-value bound (`_CARD_MANA_VALUE_BOUND_RE`
        # above): a card with {X} in its cost has mana value 0 outside the
        # stack (CR 202.3e), which a "mana value N or less" reading would
        # get wrong for this exact quality.
        return _has_x_in_mana_cost
    ceiling: int | None = None
    floor: int | None = None
    bound = _CARD_MANA_VALUE_BOUND_RE.fullmatch(text)
    if bound is not None:
        if bound.group("dir").lower() == "less":
            ceiling = int(bound.group("n"))
        else:
            floor = int(bound.group("n"))
        text = bound.group("inner").strip()

    excluded_subtype: str | None = None
    negated = _NON_SUBTYPE_PREFIX_RE.fullmatch(text)
    if negated is not None:
        excluded_subtype = negated.group("subtype").lower()
        text = negated.group("rest").strip()

    lowered = re.sub(r"\s+cards?$", "", text.strip().lower()).strip()
    # R0a-T7: United Battlefront's own "noncreature, nonland permanent
    # cards" - CR 205.2a's negation, printed as a run of one or more
    # "non<type>" words rather than just the single "nonland " this reader
    # used to special-case (Ajani, Outland Chaperone's own "nonland
    # permanent"). Generalised to any number of them, each a card type this
    # module already knows how to name (`_singular_card_type`), so a comma
    # (or none, for exactly one) joins them the same way CR 205.2a's own
    # multi-word negation always reads: every named type excluded, not any
    # one of them.
    excluded_card_types: set[Type] = set()
    while True:
        prefix = re.match(r"non([a-z]+),?\s+", lowered)
        if prefix is None:
            break
        excluded_type = _singular_card_type(prefix.group(1))
        if excluded_type is None:
            break
        excluded_card_types.add(excluded_type)
        lowered = lowered[prefix.end() :].strip()
    # A bare printed subtype names a card group as well as a card type does -
    # Fell Gravship's "a creature or Spacecraft card" (CR 205.3). Only a
    # single word the subtype vocabulary knows, never a guess.
    required_subtype: str | None = None
    #: "`<A>` and `<B>` cards" - Wisdom of Ages' own "instant and sorcery
    #: cards", Fix What's Broken's "artifact and creature card" - the union
    #: of two card types, never a card that is somehow both at once. Read
    #: ahead of the single-type branch below so a two-word type list is not
    #: sent down the `" " in lowered: return None` path meant for a phrase
    #: this function genuinely does not understand.
    type_list = re.fullmatch(r"([a-z]+) and ([a-z]+)", lowered)
    if type_list is not None:
        card_type_1 = _singular_card_type(type_list.group(1))
        card_type_2 = _singular_card_type(type_list.group(2))
        if card_type_1 is None or card_type_2 is None:
            return None
        types = frozenset({card_type_1, card_type_2})
    elif lowered in ("permanent", "permanents"):
        types = frozenset(_PERMANENT_CARD_TYPES)
    else:
        card_type = _singular_card_type(lowered)
        if card_type is None:
            if excluded_card_types or " " in lowered:
                return None
            required_subtype = _singular_subtype_for_count_expression(lowered)
            if required_subtype is None:
                return None
            types = frozenset()
        else:
            types = frozenset({card_type})

    def matches(state: CardState) -> bool:
        card = state.card
        if excluded_card_types and excluded_card_types & set(card.types):
            return False
        if required_subtype is not None:
            if required_subtype not in {subtype.lower() for subtype in state.subtypes}:
                return False
        elif not (types & set(card.types)):
            return False
        # `CardState.subtypes` rather than the printing's type line: a
        # changeling card is every creature type in every zone (CR 604.3).
        if excluded_subtype is not None and excluded_subtype in {
            subtype.lower() for subtype in state.subtypes
        }:
            return False
        mana_value = card.cmc or 0
        if ceiling is not None and mana_value > ceiling:
            return False
        return not (floor is not None and mana_value < floor)

    return matches


# --------------------------------------------------------------------------
# Put or create, [grant,] then take away at the next end step (S22)
# --------------------------------------------------------------------------
#
#     <antecedent>. [<It|That token|That creature|They|Those tokens> gain(s)
#     <keywords>[ until end of turn| until your next turn].]
#     [<Sacrifice|Exile|Destroy|Return> <it|them|that creature|...>[ to your
#     hand] at the beginning of the next end step.]
#
# One printed tail on many antecedents: a token copy (Reflection of Kiki-Jiki,
# Kiki-Jiki, Mirror Breaker), a created token (Lagomos, Hand of Hatred;
# Lightning Coils; Feral Lightning), a searched-for card (Nahiri, the
# Harbinger), a card put from hand (Through the Breach), a card put from a
# linked exile (Emperor of Bones) or a token copy of a card exiled from a
# graveyard (Nahiri, the Unforgiving; Offspring's Revenge).
#
# The pronoun is CR 400.7 anaphora to whatever the antecedent put onto the
# battlefield, discovered only as it runs - so the antecedent is parsed by
# the ordinary dispatchers and run with a before/after diff of the
# battlefield (id *and* zone-change stamp, so an object that left and came
# back during the antecedent is a new one), the same technique
# `_parse_token_then_object_anaphor_clause_pair` uses for its own tokens.
# The delayed sentence is `machines/delayed.py`'s anaphoric primitive
# (CR 603.7a creates it, CR 603.7c checks the object at resolution).

#: "<pronoun> gain(s) <keywords>[ <duration>]" - the grant between the
#: antecedent and the delayed sentence.
_ANAPHOR_GAINS_KEYWORDS_RE = re.compile(
    r"^(?P<anaphor>it|they|that token|those tokens|that creature|those creatures"
    r"|that card|that permanent) gains? (?P<keywords>[a-z ,]+?)"
    r"(?: (?P<duration>until end of turn|until your next turn))?$",
    re.IGNORECASE,
)


from .amounts import _has_x_in_mana_cost  # noqa: E402
from .continuous import _layer_consequence, _parse_untap_and_gain_control_ability  # noqa: E402
from .control_copy import _parse_copy_that_spell_clause  # noqa: E402
from .dispatch import parse_mixed_effect  # noqa: E402
from .returns import _rejoin_search_clauses  # noqa: E402
from .text import (  # noqa: E402
    _named_type_word_is_readable,
    _quality_word_matcher,
    _singular_card_type,
    _singular_subtype_for_count_expression,
    _strip_non_effect_preamble,
    split_effect_clauses,
)
from .tokens import _parse_whole_text_token_clause  # noqa: E402
