"""Reading a card's abilities off its oracle text, following WOTC templating.

This module is **parsing only**. Nothing here activates, triggers, or applies an
ability - it turns printed text into structured objects and stops.

CR 113.3 lists four categories of ability (the rule was numbered 112.3 in older
Comprehensive Rules; 113.3 is the current number, confirmed against the CR):

- **113.3a spell abilities** - instructions on an instant or sorcery, followed
  while the spell resolves.
- **113.3b / CR 602.1 activated abilities** - written ``[Cost]: [Effect.]
  [Activation instructions (if any).]``. CR 602.1a: the activation cost is
  everything before the colon.
- **113.3c / CR 603.1 triggered abilities** - written ``[When/Whenever/At]
  [trigger condition], [effect]. [Instructions (if any).]``. CR 603.4 covers the
  *intervening if*: ``When/Whenever/At [trigger event], if [condition],
  [effect].``
- **113.3d / CR 604.1 static abilities** - "do something all the time rather
  than being activated or triggered. They are written as statements, and
  they're simply true."

CR 702 keyword abilities are shorthand: a line that is nothing but a keyword, or
a keyword with a cost or parameter, optionally followed by reminder text.

What this parser does with each printed line of oracle text, in order:

1. Reminder text (CR 207.2a: italicised text in parentheses) is stripped before
   anything else and kept on the model as ``reminder``. A line that is *only*
   reminder text is not an ability and is dropped.
2. A Saga chapter marker (``I, II —``) is reported as ``unparsed``. Chapter
   abilities are triggered abilities (CR 714) but are not templated with
   when/whenever/at, and guessing at them would be worse than admitting it.
3. A keyword line is matched against the printing's own ``keywords`` list, which
   comes from Scryfall - there is no hand-written keyword table here. Lists on
   one line (``Vigilance, deathtouch, haste``, ``Defender; reach``) yield one
   ``KeywordAbility`` each. A keyword's cost (CR 702.1a) is read whether it is
   printed after a space (``Flashback {2}{R}``) or after an em dash
   (``Evoke—Exile a black card from your hand.``, ``Suspend 3—{2}{B}{B}``).
   **The em dash carries no space on either side**, which is the only thing
   separating that form from step 4's ability word - ``Channel`` is a keyword on
   Boseiju's own ``keywords`` list, and ``Channel — {1}{G}, Discard this card:
   ...`` is an activated ability, not a keyword cost.
4. An ability word prefix (CR 207.2c, ``Landfall — ...``) is stripped and kept.
5. A line beginning with When/Whenever/At is a triggered ability.
6. A line with a colon outside quotes is an activated ability. Quoting matters:
   ``Lands you control have "{T}: Add one mana of any color."`` grants an
   ability, it does not have one, so the colon inside the quotes is ignored and
   the line reads as static.
7. A line that is a statement ending in a full stop is static.
8. Anything left is ``unparsed``.

Deliberate limits, all of them visible as tests:

- **A leftover line is called static even on an instant or sorcery**, where CR
  113.3a would call it a spell ability. The card's type line tells the two
  apart; this parser does not.
- **An intervening-if clause containing its own comma mis-splits.** The clause
  is taken up to the next top-level comma, which is right for
  ``if you control no Thopters other than this creature,`` and wrong for a
  clause with an internal list.
- **``parse_mana_abilities`` still reads only a ``{T}``-costed mana ability.** A
  mana ability with a non-tap cost (Skirk Prospector's ``Sacrifice a Goblin:
  Add {R}.``) is parsed by ``parse_abilities`` as an activated ability, but it
  is not returned by ``parse_mana_abilities`` and so is invisible to mana
  payment. It now shares its parsing with ``parse_abilities`` (both read one
  ``ManaAbility`` off the same ``ActivatedAbility.mana`` field, plus the
  intrinsic ability a basic land type grants - see ``intrinsic_land_ability``)
  rather than running a second, separately-maintained regex, so the two can no
  longer disagree about what a card's ability actually produces.
- **A basic land reports no abilities from ``parse_abilities``.** Its mana
  ability is printed as reminder text (Forest's whole oracle text is
  ``({T}: Add {G}.)``), and reminder text is not rules text. ``{T}: Add {G}.``
  is intrinsic to a basic land rather than printed (CR 305.6), so reading it
  back off the reminder would be reading the wrong source.
  ``parse_mana_abilities`` and ``activated_abilities_of`` both fall back to
  ``intrinsic_land_ability`` when a card has the basic supertype and no
  printed activated ability of its own, which is what the mana payment path
  and in-game activation both rely on. ``parse_abilities`` itself still
  reports nothing for a basic land - that function is about what is *printed*.
- **A mana ability's output can depend on live game state.** Urza's Tower's
  ``{T}: Add {C}. If you control an Urza's Mine and an Urza's Power-Plant, add
  {C}{C}{C} instead.`` names land *types*, not card names, and needs the board
  to be evaluated at activation time - see ``ManaCondition`` and
  ``ManaAbility.resolve``. This module stays data/parsing-only: it can tell you
  what a condition asks for, but only `models/game.py` knows the board well
  enough to check whether it holds, which is why ``resolve`` takes the
  controlled land types and self counters as plain arguments rather than a
  `Game`.
- **Three more board facts a mana ability's output can wait on**, all of them
  read here and narrowed in ``ManaAbility.effective`` the same plain-data way:

  - **CR 106.7's "could produce"** (Reflecting Pool, Exotic Orchard) -
    ``ManaAbility.could_produce`` says whose lands to survey. A caller with a
    real survey passes ``could_produce_colors``; without one, "a land you
    control" falls back to ``colors_land_types_could_produce`` over the land
    types the caller already supplies, and "a land an opponent controls" has
    nothing to fall back on and produces no mana (CR 106.5).
  - **CR 614.12a's chosen colour** (Sunken Citadel) -
    ``ManaAbility.uses_chosen_color`` says the colour was fixed as the
    permanent entered; ``effective`` takes it as ``chosen_color``, and
    without it the type is undefined and CR 106.5 applies again.
  - **CR 106.6's spend effect** (Arena of Glory's "If that mana is spent on a
    creature spell, it gains haste until end of turn") - kept verbatim on
    ``ManaAbility.spend_effect``. Nothing applies it; it is recorded so the
    gap is queryable rather than a silently dropped sentence, and it is
    deliberately *not* an ``unparsed_rider``, which would make
    ``Game.why_cannot_activate`` refuse the whole ability.
"""

import functools
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID

from pydantic import Field

from ..models.card import Card, Color, Type, subtypes_of, types_of
from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, count_pattern, parse_count, where_x_pattern
from ..snapshot import EngineModel

if TYPE_CHECKING:
    from ..models.game import Game

# --------------------------------------------------------------------------
# Mana abilities (CR 605)
# --------------------------------------------------------------------------


_SYMBOL = re.compile(r"\{([WUBRGC])\}")
#: "Add one mana of any color." (Cavern of Souls, Delighted Halfling), "Add
#: two mana of any one color." (Shang-Chi, Master of Kung Fu), and "Add X
#: mana of any one color, where X is ..." (Seance Board, Woodland
#: Weavemaster): the second and third shapes add more than one mana and
#: require them all to be the same colour, which is what "any **one** color"
#: says. `count` matches CR 107.3's X too, in which case `where_x` carries the
#: printed definition, read back by `_read_mana_count`; the count is kept so
#: `resolve` adds that many rather than always one.
_ANY_COLOR = re.compile(
    rf"{count_pattern('count', x=True)} mana of any (?:one )?color{where_x_pattern()}",
    re.IGNORECASE,
)
#: "Add two mana in any combination of colors." (Interdimensional Web Watch and
#: Smokebraider, both in the pool and both played in
#: `tests/scenarios/test_mana_spend_restrictions.py`). The same amount as
#: `_ANY_COLOR`'s "two mana of any **one** color" and a different freedom: "any
#: one color" makes every mana the same colour, "any combination of colors"
#: chooses each one independently.
#: CR 106.1a's five colors are the universe for both; colorless is a type and
#: not a color (CR 106.1b), so neither reaches it. `count`/`where_x` read the
#: same way `_ANY_COLOR`'s do.
_ANY_COLOR_COMBINATION = re.compile(
    rf"{count_pattern('count', x=True)} mana in any combination of colors{where_x_pattern()}",
    re.IGNORECASE,
)
#: Nykthos, Shrine to Nyx: "Choose a color. Add an amount of mana of that
#: color equal to your devotion to that color." Still a mana ability under
#: every one of CR 605.1a's criteria - no target, it could add mana, it is
#: not a loyalty ability - so it never uses the stack (CR 605.3b); the only
#: thing it needs beyond `_ANY_COLOR`'s shape is that the *count* is
#: CR 700.5's devotion rather than a printed number, which cannot be known
#: until the ability is actually activated.
_DEVOTION_AMOUNT = re.compile(
    r"^an amount of mana of that color equal to your devotion to that color$", re.IGNORECASE
)
#: Loot, the Nexus: "Choose a color. Add one mana of that color for each
#: different power among creatures you control." The same "Choose a color"
#: preamble and "that color" reference `_DEVOTION_AMOUNT` already reads for
#: Nykthos, with a board count in place of devotion - "for each
#: <count-expression>" rather than "where X is <count-expression>", read
#: through the identical `_mana_count_expression_readable`/`resolve_mana_
#: count_expression` pair so any future "... of that color for each ..."
#: printing is answered the same way, not only this one card's own count.
_CHOSEN_COLOR_FOR_EACH_RE = re.compile(
    r"^one mana of that color for each (?P<expression>.+)$", re.IGNORECASE
)
#: The sentence that precedes it. CR 605.1a says nothing about a mana
#: ability having only one sentence, and this one is simply where the colour
#: `Game.activate_ability` already takes for any `any_color` ability is
#: chosen - so it is stripped before `_ADD` reads the rest.
_CHOOSE_A_COLOR_PREAMBLE = re.compile(r"^Choose a color\.\s*", re.IGNORECASE)
_MANA_COST_IN_COST = re.compile(r"\{(\d+|[WUBRGCX])\}")

#: CR 106.7: "Some abilities produce mana based on the type of mana another
#: permanent or permanents 'could produce.' The type of mana a permanent could
#: produce at any time includes any type of mana that an ability of that
#: permanent would produce if it were to resolve at that time." Two printings
#: in the pool ask it, from opposite sides of the table:
#:
#:   Reflecting Pool  "{T}: Add one mana of any **type** that a land **you
#:                     control** could produce."
#:   Exotic Orchard   "{T}: Add one mana of any **color** that a land **an
#:                     opponent controls** could produce."
#:
#: Both texts confirmed with `resolve_cards` this session. The clause must be
#: read *before* `_ANY_COLOR`, whose "one mana of any color" would otherwise
#: swallow the Orchard's opening words and drop the whole survey - which is
#: exactly the defect this replaces: the Orchard used to make red off an
#: opponent whose only land was a Plains.
#:
#: "type" and "color" are different universes and the difference is printed:
#: CR 106.1a has five colors of mana, CR 106.1b six *types*, colorless
#: included. So Reflecting Pool can copy a Wastes and Exotic Orchard cannot.
_COULD_PRODUCE = re.compile(
    rf"(?P<count>{COUNT}) mana of any (?P<kind>type|color) that a land "
    r"(?P<whose>you control|an opponent controls) could produce",
    re.IGNORECASE,
)
#: "one mana of the chosen color" / "two mana of the chosen color" (Sunken
#: Citadel, text confirmed with `resolve_cards`). The colour is CR 614.1c's
#: "As it enters, choose a color", recorded on the permanent as it enters
#: (CR 614.12a) and read back here by name; CR 105.4 limits it to one of the
#: five colors, so colorless is never an answer. Until the choice is known
#: the ability's type is undefined and CR 106.5 makes it produce no mana -
#: see `ManaAbility.effective`.
_CHOSEN_COLOR_MANA = re.compile(rf"(?P<count>{COUNT}) mana of the chosen color", re.IGNORECASE)

#: `Add {G}, {R}, or {W}` is a choice; `Add {C}{C}` is both at once. The comma
#: is what separates them in WOTC templating.
_CHOICE_SEPARATOR = re.compile(r",|\bor\b")

#: "this creature's power" (Kami of Whispered Hopes, Woodland Weavemaster) -
#: the one "where X is ..." shape that names a characteristic of the source
#: itself rather than a board count. CR 613.5: the *computed* value, so a
#: continuous effect that has pumped the source by the time the mana ability
#: resolves is read, not the printed number - `Game.power_of`/`toughness_of`
#: already answer that. Mirrors `_FIREBENDING_X_IS_POWER_RE` in
#: `machines/effects.py`, which reads the identical clause for Firebending's
#: own "add N {R}" (CR 702.189a) - kept separate because that one X is read
#: as a triggered ability resolves, off `AbilityOnStack`, not as a mana
#: ability resolves, off a tapped permanent.
_SELF_CHARACTERISTIC_RE = re.compile(
    r"^(?:(?i:this (?:creature|permanent|artifact|land|source))"
    # Doc Samson, Super Psychiatrist's and Helga, Skittish Seer's own "where
    # X is Doc Samson's power" / "Helga's power": CR 201.5, a card naming
    # itself means that object, and a mana ability is always printed on (and
    # read off) its own source. Oracle capitalises a name, never a pronoun.
    r"|(?-i:[A-Z][\w'-]*(?: [A-Z][\w'-]*)*))"
    r"'?s (?P<characteristic>power|toughness)$",
    re.IGNORECASE,
)
#: "the number of soul counters on this artifact" (Seance Board) - CR 122.1's
#: counters on the ability's own source, any kind a card invents included
#: (`models/card_state.CounterKind`'s own "or any string a card invents").
_SELF_COUNTERS_ON_RE = re.compile(
    r"^the number of (?P<kind>[a-z]+) counters on this \w+$", re.IGNORECASE
)


def _mana_count_expression_readable(expression: str) -> bool:
    """Whether `resolve_mana_count_expression` can answer this "where X is
    ..." text, checked without a board so `_read_mana_count` can fail the
    whole mana ability closed - the same way an unreadable count word already
    does - on a definition this parser will never be able to answer, rather
    than accepting the ability now and discovering the gap only once a
    player taps it.
    """
    stripped = expression.strip().rstrip(".")
    if _SELF_CHARACTERISTIC_RE.fullmatch(stripped) or _SELF_COUNTERS_ON_RE.fullmatch(stripped):
        return True
    # Lazy: `machines/effects.py` imports this module for `parse_mana_abilities`
    # and friends, so importing it back at module scope would cycle. The
    # counted-board shapes `count_expression` reads ("the number of Shrines
    # you control", Sanctum of Fruitful Harvest) are pure text -> callable, no
    # board needed to ask whether one exists.
    from .effects import count_expression

    return count_expression(stripped) is not None


def resolve_mana_count_expression(
    game: "Game", controller: str, source: CardState, expression: str
) -> int:
    """The board-derived count a mana ability's "where X is ..." definition
    asks for, read at the moment the ability resolves (CR 605.3b: immediately,
    so this is the only time that matters) - Woodland Weavemaster's "this
    creature's power", Seance Board's "the number of soul counters on this
    artifact" (CR 122.1), or one of `effects.count_expression`'s board-count
    shapes (Sanctum of Fruitful Harvest's "the number of Shrines you
    control"). CR 107.1b: a result that would be negative is 0 instead - only
    reachable here through a pumped-negative power/toughness, since a counter
    count and every `count_expression` shape are already non-negative.

    Only ever called with an `expression` `_mana_count_expression_readable`
    has already accepted, so this does not itself fail closed - `Game.
    activate_ability` would have refused the activation earlier if the parser
    had not been able to read the definition at all.
    """
    stripped = expression.strip().rstrip(".")
    characteristic = _SELF_CHARACTERISTIC_RE.fullmatch(stripped)
    if characteristic is not None:
        wants_power = characteristic.group("characteristic").lower() == "power"
        value = game.power_of(source) if wants_power else game.toughness_of(source)
        return max(value, 0) if value is not None else 0
    counters = _SELF_COUNTERS_ON_RE.fullmatch(stripped)
    if counters is not None:
        return max(source.counter_count(counters.group("kind").lower()), 0)
    from .effects import count_expression

    reader = count_expression(stripped)
    assert reader is not None, (
        f"{expression!r} was accepted as readable but count_expression refused it"
    )
    return max(reader(game, controller), 0)


def _read_mana_count(match: "re.Match[str]") -> tuple[int, str | None] | None:
    """The `(any_color_count, any_color_count_expression)` a mana-count regex
    captured - `_ANY_COLOR`'s or `_ANY_COLOR_COMBINATION`'s own `count`/
    `where_x` groups - or `None` when the count cannot be read at all: an
    unknown word, or CR 107.3's X with no "where X is ..." definition this
    module or `effects.count_expression` can answer (`_parse_effect` fails
    the whole ability closed on either, the same as it always has for an
    unread word).

    A printed number reads as `(count, None)`. A readable X reads as
    `(1, expression)` - `1` is a placeholder never used for anything:
    `ManaAbility.resolve` takes the real count from `count=`, computed by
    `Game.activate_ability` calling `resolve_mana_count_expression` once a
    board exists to read it, mirroring `amount_from_devotion`'s own
    placeholder `any_color_count` of 1.
    """
    word = match.group("count")
    if word.lower() == "x":
        where_x = match.groupdict().get("where_x")
        if where_x is None or not _mana_count_expression_readable(where_x):
            return None
        return 1, where_x.strip()
    count = parse_count(word)
    if count is None:
        return None
    return count, None


class CouldProduce(StrEnum):
    """Whose lands a CR 106.7 "could produce" survey looks at.

    Which side is asked is the whole difference between the two printings
    that ask it, so it is named rather than folded into one flag. It also
    decides how much of the rule the engine currently reaches without help:
    `ManaAbility.effective` already receives the land types its *controller*
    controls (the same `Game._controlled_land_types` answer Urza's Tower's
    conditional clause runs on), so `LANDS_YOU_CONTROL` has a fallback;
    `LANDS_AN_OPPONENT_CONTROLS` has none and produces no mana until a
    caller runs the survey and passes `could_produce_colors` - CR 106.5:
    "If an ability would produce one or more mana of an undefined type, it
    produces no mana instead."
    """

    LANDS_YOU_CONTROL = "lands_you_control"
    LANDS_AN_OPPONENT_CONTROLS = "lands_an_opponent_controls"


def named_colors(color: "Color | Sequence[Color] | str | None") -> list[Color] | None:
    """The colours a caller named, as a list, or None if they named none.

    One colour may be named either way and means the same thing both times: a
    bare `Color`, or a sequence holding it. A longer sequence is one colour per
    mana, which is what "N mana in any combination of colors" asks for and what
    `Action.color_choice_count` counts out for a caller working from an
    enumerated action alone.

    A bare `str` is refused rather than iterated. `Color` is a `StrEnum`, so
    "WU" satisfies `Sequence[Color]` at runtime and comes apart into "W" and
    "U" - plain strings, not `Color` members, which would reach the mana pool
    as keys nothing else in the engine can match. Anything in the sequence that
    is not a `Color` is refused for the same reason: this is the engine's one
    chance to say what was wrong with the request, and a `ManaPool` keyed by a
    stray string says nothing at all.
    """
    if color is None:
        return None
    if isinstance(color, Color):
        return [color]
    if isinstance(color, str):
        raise ValueError(
            f"a colour is a Color or a sequence of them, not a string ({color!r}) - "
            "name each colour as its own Color"
        )
    named = list(color)
    unknown = [entry for entry in named if not isinstance(entry, Color)]
    if unknown:
        raise ValueError(f"{unknown!r} is not a colour (CR 105.1's five, as Color members)")
    return named


def one_named_color(color: "Color | Sequence[Color] | str | None") -> Color | None:
    """The single colour a caller named, or None if they named none or several.

    `Game.activate_ability` needs it before `ManaAbility.resolve` is reached:
    CR 700.5's devotion is counted to the colour the player chose, and a caller
    that named that colour as a one-element list has still named exactly one.
    Reading the bare `Color` alone made the same choice, spelled the other way,
    count as no choice at all - and then quietly add one mana where devotion
    said several.
    """
    named = named_colors(color)
    return named[0] if named is not None and len(named) == 1 else None


class ManaCondition(EngineModel):
    """CR 605.1a's ability still, but a later ``instead`` clause overrides what
    the base effect adds when the board matches (Urza's Tower, Gemstone
    Caverns). Two shapes are read, matching the pool:

    - ``land_types``: "If you control an Urza's Mine and an Urza's
      Power-Plant, ..." - land *types* (CR 205.3i), not card names.
    - ``counter``: "If Gemstone Caverns has a luck counter on it, ..." - a
      counter (CR 122.1) on the permanent itself.
    - ``imprinted``: "If a card is exiled with this land, ..." (Ugin's
      Labyrinth) - whether some card in exile is linked to this permanent by
      `ExileMarker.IMPRINTED` (CR 207.2c: "Imprint" is an ability word with no
      rules meaning of its own, so this is just CR 605.1a's ordinary
      conditional templating with a third kind of thing to check).

    Exactly one of the three is set. `ManaAbility.resolve` is the only thing
    that reads this model; `models/game.py` supplies the live board state as
    plain data (a set of land types the controller controls, a set of counter
    kinds this permanent carries, whether a card is exiled with it) so this
    module never has to import `Game`.
    """

    land_types: tuple[str, ...] | None = None
    counter: str | None = None
    imprinted: bool = False
    #: What replaces the base effect's `options`/`any_color` when this
    #: condition holds.
    options: list[list[Color]]
    any_color: bool = False

    def holds(
        self,
        controlled_land_types: frozenset[str],
        own_counters: frozenset[str],
        has_imprinted_card: bool = False,
    ) -> bool:
        if self.land_types is not None:
            return all(land_type in controlled_land_types for land_type in self.land_types)
        if self.counter is not None:
            return self.counter in own_counters
        if self.imprinted:
            return has_imprinted_card
        return False


class ManaAbilityRider(EngineModel):
    """CR 405.6c: "If a mana ability both produces mana and has another
    effect, the mana is produced and the other effect happens immediately."

    Talisman of Resilience's `{T}: Add {B} or {G}. This artifact deals 1
    damage to you.` is one paragraph and one ability (CR 605.1a's four
    criteria say nothing about a second sentence disqualifying it, and CR
    605.5 only disqualifies an ability that fails one of them) - so the
    damage is not a separate triggered ability and never uses the stack
    (CR 605.3b applies to the whole ability, not just its "Add" half). This
    is the immediate side effect read off that second sentence, applied by
    `Game.activate_ability` at the same instant the mana lands in the pool.
    """

    kind: Literal["damage_to_controller", "lose_life", "gain_life"]
    amount: int


#: "This artifact/land/creature deals N damage to you." - the shape every
#: rider in the current fixture pool (Talisman of Resilience, Karplusan
#: Forest) uses. The noun is not checked against the card's own type line;
#: WOTC always prints "this <the permanent's own type>", so the noun itself
#: carries no information a caller needs.
_RIDER_DAMAGE_TO_YOU = re.compile(r"^this \S+ deals (?P<n>\d+) damage to you\.?$", re.IGNORECASE)
_RIDER_LOSE_LIFE = re.compile(r"^you lose (?P<n>\d+) life\.?$", re.IGNORECASE)
_RIDER_GAIN_LIFE = re.compile(r"^you gain (?P<n>\d+) life\.?$", re.IGNORECASE)
#: Arena of Glory's "If that mana is spent on a creature spell, it gains
#: haste until end of turn." CR 106.6's *other* two things a mana-producing
#: sentence can do beyond restricting spend: "have an additional effect that
#: affects the spell or ability that mana is spent on, or create a delayed
#: triggered ability". Neither is CR 405.6c's "another effect happens
#: immediately" - both are conditional on what the mana is later spent on,
#: which has not happened yet when the mana ability itself resolves - so
#: this is a real, separately-documented gap (see the "mana spend
#: restrictions" row in docs/engine-coverage.md), not an unreadable
#: CR 405.6c rider, and must not make `Game.why_cannot_activate` refuse the
#: whole ability the way a genuine unreadable rider does.
_SPEND_EFFECT_ON_SPELL = re.compile(r"^if (?:that|this) mana is spent on\b", re.IGNORECASE)


def _parse_mana_rider(rest: str) -> tuple[ManaAbilityRider | None, str | None, str | None]:
    """Read the CR 405.6c immediate side effect off a mana ability's text
    beyond its base "Add ..." sentence, if it printed one.

    `rest` is the same trailing text `_parse_conditional_clauses` reads for
    "If ..., add ... instead" clauses and `cost.spend_restriction` reads for
    "Spend this mana only ..." - both are recognised and skipped here rather
    than mistaken for an unreadable rider, since neither is a CR 405.6c
    "other effect" (one only changes what the base effect produces, the
    other only restricts how the mana already produced may be spent).

    The first remaining sentence is checked against the known immediate-
    effect shapes. A match becomes `(rider, None, spend_effect)` - the rider
    `Game.activate_ability` applies alongside the mana. A remaining sentence
    that matches none of them comes back as `(None, sentence, spend_effect)`
    instead: the project's fail-closed rule means the caller must refuse the
    whole activation rather than mint the mana and silently drop the sentence
    that was supposed to come with it (CR 405.6c ties the two together as one
    event, not two).

    The third element is CR 106.6's "additional effect that affects the spell
    or ability that mana is spent on" - Arena of Glory's "If that mana is
    spent on a creature spell, it gains haste until end of turn." It used to
    be skipped and forgotten, which meant a card whose whole point is that
    rider reported `rider=None, unparsed_rider=None` and looked, to every
    caller, exactly like a land with nothing but `{T}: Add {R}{R}`. It is
    returned now so `ManaAbility.spend_effect` can carry it: still unapplied,
    but no longer invisible.
    """
    spend_effect: str | None = None
    rider: ManaAbilityRider | None = None
    unparsed: str | None = None
    for sentence in re.split(r"(?<=\.)\s+", rest.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if rider is not None or unparsed is not None:
            # The rider half is decided; keep walking only to find a
            # CR 106.6 spend effect printed after it.
            if _SPEND_EFFECT_ON_SPELL.match(sentence) and spend_effect is None:
                spend_effect = sentence
            continue
        if _CONDITIONAL_CLAUSE.match(sentence):
            continue
        if "spend this mana only" in sentence.lower():
            continue
        if _SPEND_EFFECT_ON_SPELL.match(sentence):
            if spend_effect is None:
                spend_effect = sentence
            continue
        damage = _RIDER_DAMAGE_TO_YOU.match(sentence)
        if damage:
            rider = ManaAbilityRider(kind="damage_to_controller", amount=int(damage.group("n")))
            continue
        lose = _RIDER_LOSE_LIFE.match(sentence)
        if lose:
            rider = ManaAbilityRider(kind="lose_life", amount=int(lose.group("n")))
            continue
        gain = _RIDER_GAIN_LIFE.match(sentence)
        if gain:
            rider = ManaAbilityRider(kind="gain_life", amount=int(gain.group("n")))
            continue
        unparsed = sentence
    return rider, unparsed, spend_effect


class ManaAbility(EngineModel):
    """One `{T}: Add ...` ability read off a card."""

    #: Each option this ability can produce. One entry means no choice.
    options: list[list[Color]]
    #: True if the ability can add mana of any colour.
    any_color: bool = False
    #: How much mana an `any_color` ability adds. All of the one chosen colour
    #: unless `any_color_mixed` says otherwise: 1 for "Add one mana of any
    #: color"; 2 for Shang-Chi's "Add two mana of any one color."
    any_color_count: int = 1
    #: True for "Add N mana in any combination of colors", where each of the N
    #: is a colour of its own (Interdimensional Web Watch). False for "of any
    #: one color", which is the same count locked to a single colour.
    #:
    #: `resolve` takes a sequence of colours to spell a genuine mixture out;
    #: passing one `Color` still means N of it, which stays a legal
    #: combination, so nothing that only knows how to name one colour breaks.
    #: `Game.mana_color_choice_count` is where that shows for a caller with
    #: no `ManaAbility` in hand: it reports this count, so the enumerated
    #: `Action.color_choice_count` beside `Action.color_options` says how many
    #: colours to name and `{W}{U}` is reachable from the action alone. See
    #: `docs/engine-coverage.md`.
    any_color_mixed: bool = False
    #: True if activating it costs mana. CR 605.1a says nothing about the cost
    #: containing mana - such an ability is still a mana ability - so this is
    #: shape information for callers that need to know what there is to pay,
    #: not rules status.
    costs_mana: bool = False
    #: "If [condition], add [mana] instead" clauses following the base effect,
    #: in printed order. CR 605.1a's criteria are evaluated on the printed
    #: text, but which clause actually applies still depends on the game state
    #: when the ability resolves (CR 605.3b: it resolves immediately) - see
    #: `resolve`. Empty for every mana ability that has no such clause.
    conditional: list[ManaCondition] = Field(default_factory=list)
    #: CR 405.6c's immediate side effect, read generically off the trailing
    #: sentence of this ability's own printed text (Talisman of Resilience's
    #: "This artifact deals 1 damage to you."). `None` when the ability has
    #: no such sentence, or when it has one this parser could not read - see
    #: `unparsed_rider`, which is exactly then set.
    rider: ManaAbilityRider | None = None
    #: True when the count is CR 700.5's devotion rather than a printed
    #: number - Nykthos, Shrine to Nyx's "Add an amount of mana of that color
    #: equal to your devotion to that color." `any_color_count` stays at its
    #: default 1 and is not the answer: the real count is only knowable from
    #: the board at the moment of activation, so `resolve` takes it as an
    #: argument and `Game.activate_ability` is what computes it
    #: (`machines/effects.devotion_to`). A caller with no board to ask -
    #: `produces`, `tests/scenarios/harness.mana_from` - gets one mana of the
    #: chosen colour, which is the shape of the answer if not its size.
    amount_from_devotion: bool = False
    #: The raw "where X is ..." definition, when the count is CR 107.3's X
    #: rather than a printed number - Seance Board's "the number of soul
    #: counters on this artifact", Woodland Weavemaster's "this creature's
    #: power". `any_color_count` stays at its default 1, the same placeholder
    #: `amount_from_devotion` already uses: the real count is only knowable
    #: from the board at the moment of activation, read by
    #: `resolve_mana_count_expression` and passed to `resolve` as `count`, the
    #: same argument devotion already takes it through. `None` for every
    #: ability whose count is a printed number or CR 700.5's devotion.
    any_color_count_expression: str | None = None
    #: The raw trailing sentence, when the ability's text has one beyond
    #: "Add ..." and its own recognised conditional/spend-restriction
    #: clauses, but this parser could not classify it as a known rider shape.
    #: `Game.activate_ability` refuses to activate an ability with this set,
    #: rather than producing the mana and silently dropping the sentence
    #: that was meant to come with it.
    unparsed_rider: str | None = None
    #: Whose lands CR 106.7's "could produce" survey looks at, or None for
    #: the overwhelming majority of abilities that print no such clause.
    #: `options` still holds the whole universe the clause could ever offer
    #: (five colors for "any color", six types for "any type"); `effective`
    #: is what narrows it to what the surveyed lands actually could produce.
    could_produce: CouldProduce | None = None
    #: True when the ability's own printed text says "the chosen color" -
    #: CR 614.1c's as-enters choice, read back by name (Sunken Citadel).
    #: `options` again holds the universe (CR 105.4's five colors, one option
    #: per colour, `any_color_count` mana of it); `effective` narrows it to
    #: the one colour actually chosen, and to nothing at all until a caller
    #: passes one.
    uses_chosen_color: bool = False
    #: CR 106.6's second and third clauses - "have an additional effect that
    #: affects the spell or ability that mana is spent on, or create a
    #: delayed triggered ability" - kept as the raw printed sentence. Arena
    #: of Glory's "If that mana is spent on a creature spell, it gains haste
    #: until end of turn." is the only one in the pool.
    #:
    #: Unlike `unparsed_rider` this does **not** make
    #: `Game.why_cannot_activate` refuse the ability: the sentence is not
    #: CR 405.6c's "another effect happens immediately", it is conditional on
    #: a spend that has not happened yet, so the mana ability itself is
    #: complete without it. It is recorded rather than dropped so the gap is
    #: queryable instead of invisible - nothing applies it yet.
    spend_effect: str | None = None

    @property
    def is_choice(self) -> bool:
        return self.any_color or len(self.options) > 1

    @property
    def amount(self) -> int:
        """How much mana one activation adds, ignoring any conditional clause."""
        if self.any_color:
            return self.any_color_count
        # An ability whose whole universe of options has been narrowed away -
        # a CR 106.7 survey that came back empty, a "the chosen color" with no
        # choice known - adds nothing (CR 106.5). `options` is never empty as
        # parsed, only as narrowed by `effective`, so this is the answer for a
        # narrowed copy rather than for anything the parser produces.
        return len(self.options[0]) if self.options else 0

    def produces(self, color: Color | None = None) -> list[Color]:
        """What this ability adds, given a chosen colour where it has a choice.

        Ignores any conditional clause - equivalent to `resolve` with nothing
        controlled and no counters, which is right for a caller (most of
        `tests/test_abilities.py`, the harness's `mana_from`) that only has the
        card in hand and no board to check against.
        """
        return self.resolve(frozenset(), frozenset(), color)

    def effective(
        self,
        controlled_land_types: frozenset[str] = frozenset(),
        own_counters: frozenset[str] = frozenset(),
        has_imprinted_card: bool = False,
        *,
        could_produce_colors: frozenset[Color] | None = None,
        chosen_color: Color | None = None,
    ) -> tuple[list[list[Color]], bool]:
        """Which `options`/`any_color` this ability effectively offers right
        now, after CR 605.1a's conditional "add X instead" clauses are
        checked against the board - the printed-order, last-one-wins rule
        `resolve` documents - but *before* a colour is chosen for a choice
        ability.

        Shared by `resolve`, which goes on to pick a colour, and
        `cost.py`'s auto-tap solver, which needs to enumerate every colour a
        choice source could make before any colour is chosen (Urza's Tower's
        board-dependent output has to be visible to the solver, not just to a
        real activation) - both need the same answer to "which clause wins",
        so there is exactly one place that decides it.

        Two further narrowings run after the conditional clauses, both of
        them CR 106.5's "an ability that would produce mana of an undefined
        type produces no mana instead" applied to a universe the printed
        text names but the board has to fill in:

        - **`could_produce`** (CR 106.7) - narrowed to the colours the
          surveyed lands could produce. A caller that has run the real survey
          - asking each land's own mana abilities what they would add, which
          is what `Game.could_produce_colorless` already does for one colour
          and one permanent - passes it as `could_produce_colors` and that is
          used verbatim, for either side of the table.

          A caller that has not gets the fallback, and the fallback only
          reaches half the rule: `LANDS_YOU_CONTROL` is answered from
          `controlled_land_types`, which every caller already passes, so
          Reflecting Pool works off basic land types (see
          `colors_land_types_could_produce` for exactly how far that goes);
          `LANDS_AN_OPPONENT_CONTROLS` has no such argument to fall back on,
          so Exotic Orchard narrows to nothing and is not a mana source at
          all. That is a loud, correct-shaped gap in place of the wrong
          answer it replaces (any colour at all, off any opponent).
        - **`uses_chosen_color`** (CR 614.12a) - narrowed to the one colour
          recorded on the permanent as it entered, and to nothing until a
          caller passes it.

        Both surveys are **under-inclusive and never over-inclusive**: see
        `colors_land_types_could_produce` for exactly what a land type does
        and does not tell you.
        """
        options, any_color = self.options, self.any_color
        for condition in self.conditional:
            if condition.holds(controlled_land_types, own_counters, has_imprinted_card):
                options, any_color = condition.options, condition.any_color

        if self.could_produce is not None:
            if could_produce_colors is None:
                could_produce_colors = colors_land_types_could_produce(
                    controlled_land_types
                    if self.could_produce is CouldProduce.LANDS_YOU_CONTROL
                    else frozenset()
                )
            options, any_color = _narrow(options, any_color, could_produce_colors)
        if self.uses_chosen_color:
            allowed = frozenset() if chosen_color is None else frozenset({chosen_color})
            options, any_color = _narrow(options, any_color, allowed)
        return options, any_color

    def offers(
        self, produces: "Sequence[Color]", options: list[list[Color]], any_color: bool
    ) -> bool:
        """Whether this ability could add exactly `produces` right now, given
        the `options`/`any_color` `effective` already worked out for the board.

        The question a caller who names its own mana asks: `CostPayment.
        tap_for_mana(source, colors)` is handed a production rather than
        choosing one, and has to know whether the ability actually offers it
        before the mana reaches the pool.

        `options` enumerates a choice as one entry per colour - "Add two mana
        of any one color" is `[[W,W], [U,U], ...]`, which is exactly what that
        printing offers. **"N mana in any combination of colors" is not that**:
        each of the N chooses its own colour (CR 106.1a's five are the
        universe), so the productions it offers are every multiset of N of
        them, and the enumeration would be `combinations_with_replacement` -
        126 entries for Cascading Cataracts' five mana, and an ability whose
        count comes from the board (a devotion, an X) has no bound at all. So
        the mixture is checked against the rule instead of materialised: the
        right number of mana, every one of them a colour the narrowed options
        still offer. Nothing needs the list, and no caller pays for building
        it.

        The narrowing is what keeps that from being "any five colours": a
        CR 106.5 survey that came back with two colours leaves `options`
        holding those two, and a mixture naming a third is not offered.
        """
        wanted = sorted(produces)
        if any(sorted(option) == wanted for option in options):
            return True
        if not (any_color and self.any_color_mixed):
            return False
        offered = {color for option in options for color in option}
        return len(wanted) == self.any_color_count and all(color in offered for color in wanted)

    def resolve(
        self,
        controlled_land_types: frozenset[str] = frozenset(),
        own_counters: frozenset[str] = frozenset(),
        color: "Color | Sequence[Color] | None" = None,
        has_imprinted_card: bool = False,
        count: int | None = None,
        *,
        could_produce_colors: frozenset[Color] | None = None,
        chosen_color: Color | None = None,
    ) -> list[Color]:
        """What this ability adds right now (CR 605.1a, CR 605.3b resolves it
        immediately, so "right now" is the only time that matters).

        Later conditional clauses are checked in printed order and the last one
        that holds wins - matching WOTC's own "add X instead" templating, where
        a later "instead" clause is the one that actually applies when more
        than one could. Every card in the pool has at most one, so this is
        untested beyond the single-clause case, but printed order is the
        natural reading of "instead" stacking the way a replacement effect
        would (CR 616.1: the affected player or controller chooses one).

        Raises when the winning clause offers a choice and none was made, so a
        caller cannot silently get the wrong colour.

        An ability CR 106.5 leaves with no defined type at all - a CR 106.7
        survey that came back empty, a "the chosen color" whose choice this
        caller does not know - has no option to match and raises rather than
        adding mana of a colour nothing licensed. `cost.py`'s auto-tap asks
        `effective` first and drops such a source before it ever gets here.
        """
        options, any_color = self.effective(
            controlled_land_types,
            own_counters,
            has_imprinted_card,
            could_produce_colors=could_produce_colors,
            chosen_color=chosen_color,
        )

        if not any_color and not options:
            raise ValueError(
                "this ability's mana has no defined type right now, so it produces no mana "
                "(CR 106.5)"
            )

        chosen_colors = named_colors(color)
        # One colour, however it was named. A caller reading `color_options`
        # and `color_choice_count` off an enumerated action hands back a list
        # of the length that field gave it, which is 1 for every ability but
        # "N mana in any combination of colors" - so a list of one is the same
        # choice a bare `Color` is, on every branch below rather than only on
        # the one that was written with a list in mind.
        single = chosen_colors[0] if chosen_colors is not None and len(chosen_colors) == 1 else None

        if any_color:
            if chosen_colors is None:
                raise ValueError("this ability adds any colour; pass the colour chosen")
            # `count` is CR 700.5's devotion for `amount_from_devotion`, or a
            # `resolve_mana_count_expression` answer for
            # `any_color_count_expression` - neither is anything on this
            # object can work out for itself, see those fields' own
            # docstrings. Zero is a real answer (no permanent with a mana
            # symbol of that colour, no counters yet) and produces no mana at
            # all, which CR 605.2 already allows: "A mana ability remains a
            # mana ability even if the game state doesn't allow it to produce
            # mana."
            wanted = (
                max(count, 0)
                if (self.amount_from_devotion or self.any_color_count_expression is not None)
                and count is not None
                else self.any_color_count
            )
            if single is not None:
                return [single] * wanted
            # A spelled-out combination, one colour per mana. Legal only where
            # the printed words allow the mana to differ ("in any combination
            # of colors"); "of any one color" is one colour by its own
            # wording, so a mixture there would be mana the card never offered.
            if len(chosen_colors) != wanted:
                raise ValueError(
                    f"this ability adds {wanted} mana; {len(chosen_colors)} colours were chosen"
                )
            if not self.any_color_mixed and len(set(chosen_colors)) > 1:
                raise ValueError(
                    "this ability adds mana of any one color, so every mana it adds is the "
                    "same colour"
                )
            return chosen_colors

        # Every remaining branch is a choice *between* printed options, one of
        # which is picked whole - so exactly one colour names it, and a longer
        # list is a caller mistake this refuses in its own words rather than
        # reaching for `.value` on a list.
        if chosen_colors is not None and single is None:
            raise ValueError(
                f"this ability chooses one colour from what it prints; "
                f"{len(chosen_colors)} colours were chosen"
            )

        if len(options) == 1:
            only = options[0]
            if single is not None and single not in only:
                raise ValueError(f"this ability adds {[c.value for c in only]}, not {single.value}")
            return list(only)

        if single is None:
            choices = [[c.value for c in option] for option in options]
            raise ValueError(f"this ability offers {choices}; pass the colour chosen")

        for option in options:
            if option == [single]:
                return list(option)
        raise ValueError(f"{single.value} is not one of this ability's options")


def parse_mana_abilities(card: Card, face: str | None = None) -> list[ManaAbility]:
    """Every `{T}: Add ...` ability a card has itself, front face and backs.

    This is the same `ManaAbility` `parse_abilities` reads onto
    `ActivatedAbility.mana` - see the module docstring - filtered to the ones
    with `{T}` in their own printed cost, which is what the mana-payment path
    (`tests/scenarios/harness.mana_from`) has always meant by "this card's
    mana ability": Skirk Prospector's `Sacrifice a Goblin: Add {R}.` is still
    read by `parse_abilities` as an activated ability with `mana` set, but a
    caller that only wants "what can I tap this for" does not want it.

    `face` narrows the result to one face's own abilities, the same
    `CardState.up_face_name` filter `activated_abilities_of` applies (CR
    712.8d/712.8e/712.8f): a modal double-faced permanent has only the
    characteristics of the face that's up, and a mana ability is one of them
    (CR 109.3). Witch Enchanter sitting on the battlefield front face up (a
    creature with no mana ability of its own) must not be offered
    Witch-Blessed Meadow's `{T}: Add {W}.` just because it is printed on the
    other half of the same card. `None` - every single-faced card, and any
    caller that has not resolved which face is up - filters nothing, matching
    `activated_abilities_of`'s own default.

    A basic land with no printed ability of its own falls back to
    `intrinsic_land_ability` (CR 305.6), the same fallback
    `activated_abilities_of` uses for in-game activation.
    """
    printed = _mana_abilities_from(parse_abilities(card), face)
    if printed:
        return printed
    intrinsic = intrinsic_land_ability(card, face)
    return [intrinsic.mana] if intrinsic is not None and intrinsic.mana is not None else []


def _mana_abilities_from(abilities: "Sequence[Ability]", face: str | None) -> list[ManaAbility]:
    """The `{T}: Add ...` filter `parse_mana_abilities` applies to a card's
    own printed abilities, pulled out so `granted_mana_abilities` below can
    apply the identical filter to a runtime-granted line instead."""
    return [
        ability.mana
        for ability in abilities
        if isinstance(ability, ActivatedAbility)
        and ability.mana is not None
        and any(piece.kind is CostKind.TAP for piece in ability.costs)
        and (face is None or ability.face == face)
    ]


def granted_mana_abilities(texts: Sequence[str]) -> list[ManaAbility]:
    """`CardState.granted_ability_texts`'s own `{T}: Add ...` lines, read the
    same way `parse_mana_abilities` reads a card's printed ones - Urza's Saga
    chapter I's "This Saga gains '{T}: Add {C}.'" is what this exists for.

    Callers that tap a permanent for mana (`machines/cost.py`'s `tap_for_
    mana`/`auto_tap`, `tests/scenarios/harness.mana_from`) add this to
    `parse_mana_abilities(card, face)`'s own result rather than calling it
    instead, so a granted ability is additional to whatever is printed, never
    a replacement for it - no card in the pool grants a mana ability onto a
    permanent that already prints one, but nothing here assumes that either.
    """
    return _mana_abilities_from(parse_granted_ability_lines(texts), face=None)


def _parse_effect(effect: str) -> ManaAbility | None:
    if _DEVOTION_AMOUNT.fullmatch(effect.strip().rstrip(".")):
        return ManaAbility(
            options=[[color] for color in _COLORS],
            any_color=True,
            any_color_count=1,
            amount_from_devotion=True,
        )
    chosen_color_for_each = _CHOSEN_COLOR_FOR_EACH_RE.fullmatch(effect.strip().rstrip("."))
    if chosen_color_for_each:
        expression = chosen_color_for_each.group("expression").strip()
        if not _mana_count_expression_readable(expression):
            return None
        return ManaAbility(
            options=[[color] for color in _COLORS],
            any_color=True,
            any_color_count=1,
            any_color_count_expression=expression,
        )
    # Before `_ANY_COLOR`: "one mana of any color that a land an opponent
    # controls could produce" opens with `_ANY_COLOR`'s own words, and reading
    # it as a plain any-colour ability is what made Exotic Orchard tap for red
    # off a Plains. CR 106.7's survey is the whole meaning of the sentence.
    could_produce = _COULD_PRODUCE.search(effect)
    if could_produce:
        count = parse_count(could_produce.group("count"))
        if count is None:
            return None
        # CR 106.1a: five colors of mana. CR 106.1b: six *types*, colorless
        # included. Reflecting Pool says "type" and so can copy a colorless
        # source; Exotic Orchard says "color" and cannot.
        universe = (
            (*_COLORS, Color.COLORLESS)
            if could_produce.group("kind").lower() == "type"
            else _COLORS
        )
        whose = (
            CouldProduce.LANDS_YOU_CONTROL
            if could_produce.group("whose").lower() == "you control"
            else CouldProduce.LANDS_AN_OPPONENT_CONTROLS
        )
        return ManaAbility(
            options=[[color] * count for color in universe],
            any_color_count=count,
            could_produce=whose,
        )

    # "one mana of the chosen color" (Sunken Citadel), CR 614.12a's recorded
    # choice. Also before `_ANY_COLOR`, which does not match it, but keeping
    # the two colour-universe clauses together is what stops a later edit to
    # either regex from silently reordering them.
    chosen = _CHOSEN_COLOR_MANA.search(effect)
    if chosen:
        count = parse_count(chosen.group("count"))
        if count is None:
            return None
        return ManaAbility(
            options=[[color] * count for color in _COLORS],
            any_color_count=count,
            uses_chosen_color=True,
        )

    combination = _ANY_COLOR_COMBINATION.search(effect)
    if combination:
        read = _read_mana_count(combination)
        if read is None:
            return None
        count, expression = read
        return ManaAbility(
            options=[[color] * count for color in _COLORS],
            any_color=True,
            any_color_count=count,
            any_color_mixed=True,
            any_color_count_expression=expression,
        )

    any_color = _ANY_COLOR.search(effect)
    if any_color:
        read = _read_mana_count(any_color)
        if read is None:
            return None
        count, expression = read
        return ManaAbility(
            options=[[color] * count for color in _COLORS],
            any_color=True,
            any_color_count=count,
            any_color_count_expression=expression,
        )

    # A choice reads `{G}, {R}, or {W}`; a multiple reads `{C}{C}`.
    parts = [part for part in _CHOICE_SEPARATOR.split(effect) if _SYMBOL.search(part)]
    if not parts:
        return None

    options = [[Color(symbol) for symbol in _SYMBOL.findall(part)] for part in parts]
    return ManaAbility(options=options)


_COLORS = (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)

#: "If you control an Urza's Mine and an Urza's Power-Plant, add {C}{C}{C}
#: instead." / "If Gemstone Caverns has a luck counter on it, instead add one
#: mana of any color." - the `instead` may sit before or after `add`.
_CONDITIONAL_CLAUSE = re.compile(
    r"If\s+(?P<condition>.+?),\s*(?:instead\s+add|add)\s+(?P<effect>[^.]+?)(?:\s+instead)?\.?\s*$",
    re.IGNORECASE,
)
_CONTROL_LAND_TYPES = re.compile(r"^you control\s+(?P<types>.+)$", re.IGNORECASE)
_HAS_COUNTER = re.compile(
    r"has an? (?P<counter>[\w+/-]+(?: [\w+/-]+)*) counter on it$", re.IGNORECASE
)
#: "a card is exiled with this land" (Ugin's Labyrinth). `ExileMarker.
#: IMPRINTED` is what "with this <permanent>" is read into
#: (`machines/effects.py`'s `_parse_imprint_clause`); the noun itself
#: ("land", "artifact", "permanent") is not checked here - the ability is
#: already printed on the one permanent it can possibly mean.
_IS_IMPRINTED = re.compile(r"^an? card is exiled with this \w+$", re.IGNORECASE)


def _parse_conditional_clauses(rest: str) -> list[ManaCondition]:
    """Every "If [condition], add [mana] instead" sentence following the base
    effect, in printed order. A sentence this cannot classify is dropped
    silently rather than guessed at - the base amount is what CR 605.1a's
    "could add mana" criterion is checked against, and a clause left unread
    just never overrides it (see `docs/engine-coverage.md` for what that means
    for a spend restriction sentence like Eldrazi Temple's, which is not a
    conditional-amount clause at all and is correctly ignored here).
    """
    conditions: list[ManaCondition] = []
    for sentence in re.split(r"(?<=\.)\s+", rest.strip()):
        if not sentence:
            continue
        match = _CONDITIONAL_CLAUSE.match(sentence)
        if match is None:
            continue
        effect = _parse_effect(match.group("effect"))
        if effect is None:
            continue
        condition_text = match.group("condition").strip()

        control_match = _CONTROL_LAND_TYPES.match(condition_text)
        if control_match is not None:
            # CR 305.5: "Land subtypes are always a single word." A card's
            # oracle text names a multi-word land type article-and-all ("an
            # Urza's Mine"), but `Card.subtypes` reads it as separate single
            # words ("Urza's", "Mine"). The last word is always the
            # distinguishing one - "Urza's" alone is shared by all three Tron
            # lands - so that is what is matched against the board.
            types = tuple(
                re.sub(r"^(a|an)\s+", "", part.strip(), flags=re.IGNORECASE).split()[-1]
                for part in re.split(r"\s+and\s+", control_match.group("types"))
                if part.strip()
            )
            conditions.append(
                ManaCondition(land_types=types, options=effect.options, any_color=effect.any_color)
            )
            continue

        counter_match = _HAS_COUNTER.search(condition_text)
        if counter_match is not None:
            conditions.append(
                ManaCondition(
                    counter=counter_match.group("counter").lower(),
                    options=effect.options,
                    any_color=effect.any_color,
                )
            )
            continue

        if _IS_IMPRINTED.match(condition_text):
            conditions.append(
                ManaCondition(imprinted=True, options=effect.options, any_color=effect.any_color)
            )
    return conditions


#: CR 305.6: "Plains", "Island", "Swamp", "Mountain", "Forest" are the basic
#: land types, and each names the colour of mana its intrinsic ability adds.
_BASIC_LAND_COLORS: dict[str, Color] = {
    "Plains": Color.WHITE,
    "Island": Color.BLUE,
    "Swamp": Color.BLACK,
    "Mountain": Color.RED,
    "Forest": Color.GREEN,
}


def colors_land_types_could_produce(land_types: frozenset[str]) -> frozenset[Color]:
    """CR 106.7's "could produce", answered from a set of land subtypes.

    CR 106.7: "The type of mana a permanent could produce at any time includes
    any type of mana that an ability of that permanent would produce if it were
    to resolve at that time." CR 305.6 gives every object with a basic land
    type the matching intrinsic mana ability, so a land that *has* the Island
    subtype could produce {U} - always, whether it is tapped, whether its
    controller could actually activate it, whether some other effect stops it
    being activated. That direction of the rule is exact.

    What this **cannot** see is the other direction: a land with no basic land
    type that still produces mana. Ancient Tomb's {C}{C}, Wastes' {C}, Mana
    Confluence's any colour, and every "Add one mana of any color" land are all
    invisible here, because a subtype set is all `Game._controlled_land_types`
    reports and it is the only board fact `ManaAbility.effective` is handed.

    So the answer is **under-inclusive and never over-inclusive**: every colour
    it names is genuinely one the surveyed lands could produce, and a colour it
    omits may still be one. A Reflecting Pool next to an Island taps for blue;
    a Reflecting Pool next to nothing but an Ancient Tomb taps for nothing,
    which is a refusal rather than a wrong colour. This is a *fallback*, not
    the rule: a caller holding the permanents can run the real survey - ask
    each land's own mana abilities what they would add, which is exactly what
    `Game.could_produce_colorless` already does for one colour and one
    permanent - and hand the answer to `ManaAbility.effective` as
    `could_produce_colors`, which is then used instead of this. The fallback
    exists because this module is handed plain data and never a `Game` (see
    the module docstring), so it can only work from what it is already given.

    Layers are already accounted for by the caller: `Game._controlled_land_
    types` reads `CardState.subtypes`, the computed value, so an Urborg,
    Tomb of Yawgmoth making every land a Swamp shows up here as black, and a
    Blood Moon stripping a nonbasic's types shows up as red.
    """
    return frozenset(
        _BASIC_LAND_COLORS[land_type] for land_type in land_types if land_type in _BASIC_LAND_COLORS
    )


def _narrow(
    options: list[list[Color]], any_color: bool, allowed: frozenset[Color]
) -> tuple[list[list[Color]], bool]:
    """`options`/`any_color` with every colour outside `allowed` dropped.

    An option is kept only if every colour in it is allowed - an ability that
    adds two mana of one chosen colour cannot half-add one - and `any_color`
    survives only if nothing was dropped, since an ability narrowed to a
    subset of the five no longer adds mana of *any* colour. The same shape as
    `cost._narrow_to_defined_colors`, which applies CR 106.5 to the other
    board-dependent colour clause in the pool ("of any color among legendary
    creatures you control"); this one is inside `effective` because the
    clauses it serves are read off the printed text here rather than there.
    """
    kept = [option for option in options if all(color in allowed for color in option)]
    return kept, any_color and len(kept) == len(options)


def _type_line_and_name_for_face(card: Card, face: str | None) -> tuple[str, str]:
    """The type line and name to read a basic land type off of.

    `face` is a face *name* - the same convention `parse_mana_abilities` and
    `activated_abilities_of` use - not a `CardFace` object, so every caller
    can keep passing `CardState.up_face_name` straight through. `None` (a
    single-faced card, or a caller with no face resolved yet) reads the front
    face, same as before this parameter existed. A named face that does not
    match any of `card.card_faces` falls back the same way, rather than
    raising, since a caller is never wrong to ask about a card with no faces
    at all.
    """
    if face is not None:
        for candidate in card.card_faces or []:
            if candidate.name == face:
                return candidate.type_line or "", candidate.name
    return card.front_type_line, card.name


def intrinsic_land_ability(
    card: Card,
    face: str | None = None,
    *,
    computed_subtypes: tuple[str, ...] | None = None,
) -> "ActivatedAbility | None":
    """The unwritten `{T}: Add [colour(s)].` a basic land type carries (CR 305.6).

    CR 305.6 grants the mana ability to "an object with the land card type and
    a basic land type", not to whatever is printed - and every card that
    carries a basic land type prints that ability as reminder text rather than
    rules text, basic land or not. Forest's whole oracle text is reminder
    (`({T}: Add {G}.)`); a shockland (Steam Vents) and a Ravnica dual (Breeding
    Pool) print the same reminder-wrapped line ahead of their real, non-mana
    rules text (the pay-2-life-or-enters-tapped clause). `parse_abilities`
    correctly drops all of that as reminder, so this synthesises the same
    shape of `ActivatedAbility` a printed one would parse into, for the two
    callers that need the ability to actually work: mana payment
    (`parse_mana_abilities`) and in-game activation
    (`activated_abilities_of`). Both call this only when a card has no printed
    *activated* ability of its own, so a land that genuinely prints its mana
    ability as rules text is never second-guessed.

    `face` narrows which face's own type line is read, the same convention
    `parse_mana_abilities`/`activated_abilities_of` use (CR 712.8d/712.8e/
    712.8f: a double-faced permanent has only the characteristics of the face
    that's up). Reading `card.types`/`card.subtypes` unconditionally - the
    front face only - would grant a basic-land intrinsic ability to a
    transformed or land-face permanent whose *front* face happens to carry a
    basic land type, even while some other face is up, and would deny one to
    a land back face that does, while its creature front sits on the top-level
    fields. `None` keeps the old front-face-only behaviour for a single-faced
    card or a caller with no face resolved.

    `computed_subtypes`, when given, overrides the printed subtype line CR 613
    would otherwise start from - a land Blood Moon (CR 305.7) set to "just a
    Mountain", or one Urborg, Tomb of Yawgmoth made a Swamp "in addition to
    its other types", still needs CR 305.6's intrinsic ability, and the
    printed line alone can never see either effect. `None` (the default)
    keeps every existing caller's printed-only behaviour: this function has
    no `game` and no live permanent of its own to ask, so a caller with a
    battlefield permanent in hand is the one that has to read `Characteristics.
    subtypes` (guarded the same way every other computed-vs-printed call site
    in this defect class is) and pass the answer in. Land *type* (whether it
    is a land at all) is still read off the printed line either way - nothing
    in this pool's subtype-changing effects also strips the land type itself.

    **No in-game caller passes it, and none should.** That is a deliberate
    conclusion, checked against the running engine rather than assumed: both
    paths that ask a live permanent for its activated abilities -
    `Game.activated_abilities` and `machines/cost._abilities_of` - already
    reach the layer-4 answer by a different, correct route.
    `layers.rewritten_ability_lines` replaces the whole printed line list when
    CR 305.7 has set a land's subtype (Blood Moon over Steam Vents computes to
    exactly `{T}: Add {R}`), and `layers.added_ability_lines` appends the
    intrinsic ability of a basic land type granted additively (Urborg over a
    Forest computes to `{T}: Add {G}` *and* `{T}: Add {B}`). Both were
    verified live before this note was written.

    Wiring `computed_subtypes` through `triggers.activated_abilities_of` to
    "finish the job" would therefore change no answer, and would break one:
    that function is memoised on `(card.id, face)` alone, so a per-permanent
    override would both survive a subtype change and leak across every other
    permanent sharing the printed card. The parameter stays because it makes
    this function answerable for a caller that genuinely has only computed
    subtypes and no game (`tests/test_abilities.py` covers exactly that), not
    because the engine needs a second route to an answer it already has.
    """
    type_line, name = _type_line_and_name_for_face(card, face)
    if Type.LAND not in types_of(type_line):
        return None
    subtypes = subtypes_of(type_line) if computed_subtypes is None else computed_subtypes
    colors = [_BASIC_LAND_COLORS[subtype] for subtype in subtypes if subtype in _BASIC_LAND_COLORS]
    if not colors:
        return None
    # One basic land type is one option with no choice (Forest: only {G}).
    # More than one (a shockland, a Ravnica dual) is a *choice* between them,
    # each on its own - CR 305.6 does not make Steam Vents add {U}{R} at once.
    options = [[color] for color in colors]
    printed_effect = " or ".join(f"{{{c.value}}}" for c in colors)
    text = f"{{T}}: Add {printed_effect}."
    return ActivatedAbility(
        raw=text,
        text=text,
        face=name,
        cost="{T}",
        costs=[Cost(kind=CostKind.TAP, text="{T}")],
        effect=f"Add {printed_effect}.",
        mana=ManaAbility(options=options),
    )


# --------------------------------------------------------------------------
# The four ability categories (CR 113.3)
# --------------------------------------------------------------------------


class AbilityKind(StrEnum):
    """Which of CR 113.3's categories a line fell into.

    `UNPARSED` is not a category in the rules. It is this module admitting it
    could not read the line, which beats a confident wrong answer.
    """

    ACTIVATED = "activated"
    TRIGGERED = "triggered"
    STATIC = "static"
    KEYWORD = "keyword"
    UNPARSED = "unparsed"


class TriggerWord(StrEnum):
    """CR 603.1: a triggered ability begins with one of these three words."""

    WHEN = "when"
    WHENEVER = "whenever"
    AT = "at"


class TriggerEvent(StrEnum):
    """The common trigger shapes, recognised off the condition text.

    Only these twenty-five are recognised; every other condition leaves `event`
    None with `condition` still holding the printed text.
    """

    #: CR 603.6a, "When [this object] enters, ..."
    ENTERS_THE_BATTLEFIELD = "enters_the_battlefield"
    #: CR 700.4, a creature going from the battlefield to a graveyard.
    DIES = "dies"
    #: CR 508.3c, "Whenever [a creature] attacks, ..."
    ATTACKS = "attacks"
    #: CR 509, "Whenever this creature blocks or becomes blocked, ..."
    BLOCKS = "blocks"
    #: "At the beginning of [a step or phase], ..."
    BEGINNING_OF_STEP = "beginning_of_step"
    #: "Whenever you cast ..." - CR 601 casting, not resolution.
    CAST_SPELL = "cast_spell"
    #: CR 702.35a, "When this card is exiled this way, ...". Madness is the
    #: only thing in the pool that watches an exile, and it prints it as a
    #: keyword rather than as a line.
    EXILED = "exiled"
    #: CR 702.21a, "Whenever this permanent becomes the target of a spell or
    #: ability an opponent controls, ...". Ward is the only thing in the pool
    #: that prints it, and it prints it as a keyword rather than as a line -
    #: see `machines/keywords.keyword_triggered_abilities`.
    BECOMES_TARGET = "becomes_target"
    #: CR 121.2: "Cards may only be drawn one at a time. If a player is
    #: instructed to draw multiple cards, that player performs that many
    #: individual card draws." A draw of three is therefore three of these,
    #: one per card, not one event with a count.
    DRAWS_A_CARD = "draws_a_card"
    #: CR 119.3, "gain life". CR 119.9 treats a trigger written "Whenever [a
    #: player] gains life" as though it were written "Whenever a source causes
    #: [a player] to gain life", and CR 702.15e makes simultaneous lifelink
    #: sources separate life gain events - so one event per gain, no count.
    GAINS_LIFE = "gains_life"
    #: CR 119.3, "lose life". Damage is the usual cause (CR 119.2) but not the
    #: only one, so the event is the loss itself, not the damage.
    LOSES_LIFE = "loses_life"
    #: CR 120.2a: "Damage may be dealt as a result of combat." One event for
    #: both kinds, told apart by `GameEvent.combat`, because the printed
    #: conditions differ only in that word - "deals combat damage" against
    #: plain "deals damage". CR 120.1 makes the object that dealt the damage
    #: its source, and CR 120.9 the source something a trigger can watch for.
    DEALS_DAMAGE = "deals_damage"
    #: CR 701.21a: "To sacrifice a permanent, its controller moves it from the
    #: battlefield directly to its owner's graveyard." Distinct from DIES -
    #: the sacrifice and the graveyard arrival it causes are both true (CR
    #: 700.4), and CR 603.10a lets a trigger written "when a player sacrifices
    #: a permanent" look back in time.
    IS_SACRIFICED = "is_sacrificed"
    #: CR 701.26a: "To tap a permanent, turn it sideways from an upright
    #: position." Raised by `Game.emit_became_tapped` wherever the engine taps
    #: a permanent: a `{T}` or tap cost, a mana ability, an effect
    #: (`Game.tap_permanent`), and an attack declaration (CR 508.1f).
    BECOMES_TAPPED = "becomes_tapped"
    #: CR 701.22a: "put any number of them on the bottom of your library" -
    #: The Temporal Anchor's "Whenever you choose to put one or more cards on
    #: the bottom of your library while scrying". Raised by `Game.scry` once
    #: the choice puts at least one card on the bottom, carrying how many
    #: (`GameEvent.amount`) and the keyword action it was made during
    #: (`GameEvent.keyword_action`).
    LIBRARY_BOTTOM_CHOSEN = "library_bottom_chosen"
    #: CR 701.26b: "To untap a permanent, rotate it back to the upright
    #: position from a sideways position." Printed on Aerie Worshippers as
    #: "Whenever this creature becomes untapped".
    BECOMES_UNTAPPED = "becomes_untapped"
    #: CR 701.6a: "To counter a spell or ability means to cancel it, removing
    #: it from the stack." One event for both a spell and an ability, which
    #: CR 113.9 says are countered alike. CR 603.10e makes abilities that
    #: trigger when a spell is countered look back in time.
    SPELL_IS_COUNTERED = "spell_is_countered"
    #: CR 106.12, 106.12a: "To 'tap [a permanent] for mana' is to activate a
    #: mana ability of that permanent that includes the {T} symbol in its
    #: activation cost", and "an ability that triggers whenever a permanent
    #: 'is tapped for mana' ... triggers whenever such a mana ability resolves
    #: and produces mana". `CostPayment.tap_for_mana` is the only place the
    #: engine taps a permanent for mana, so that is where this is emitted.
    TAPPED_FOR_MANA = "tapped_for_mana"
    #: A permanent moving from the battlefield straight to exile - the "or is
    #: put into exile" half of CR 701.66a's earthbend. Distinct from `EXILED`
    #: (CR 702.35a), which is scoped to madness's own narrower "exiled this
    #: way"; this is the general battlefield-to-exile move, the same shape
    #: `DIES` already is for a battlefield-to-graveyard move. Emitted by
    #: `Game.exile_permanent`, the only place that performs this move.
    LEAVES_BATTLEFIELD_TO_EXILE = "leaves_battlefield_to_exile"
    #: A permanent moving from the battlefield straight to its owner's hand
    #: (CR 701.19a's "return") - the third of the three ways a permanent
    #: actually leaves the battlefield in this pool, alongside `DIES` and
    #: `LEAVES_BATTLEFIELD_TO_EXILE`. Static Prison's own "until this
    #: enchantment leaves the battlefield" needs all three watched: a bounced
    #: Static Prison releases its exiled card exactly as a destroyed or
    #: exiled one does, and until this existed nothing emitted on that path
    #: at all. Emitted by `Game.return_to_hand`, the only place that performs
    #: this move.
    LEAVES_BATTLEFIELD_TO_HAND = "leaves_battlefield_to_hand"
    #: CR 603.6c: "Leaves-the-battlefield abilities trigger when a permanent
    #: moves from the battlefield to another zone" - a printed condition
    #: naming the departure itself, with no destination ("When this creature
    #: leaves the battlefield", Thought-Knot Seer), rather than one of the
    #: three specific destinations above. Emitted alongside whichever of
    #: `DIES`/`LEAVES_BATTLEFIELD_TO_EXILE`/`LEAVES_BATTLEFIELD_TO_HAND`
    #: actually happened, by the same three move functions, so a card
    #: watching only the generic departure and a card watching one specific
    #: destination both see the event that matches what they printed.
    LEAVES_THE_BATTLEFIELD = "leaves_the_battlefield"
    #: CR 702.37e, CR 708.8: "As a face-down permanent is turned face up, its
    #: copiable values revert to its normal copiable values." Brine Elemental
    #: is the only card in the pool that watches its own unmorph this way -
    #: "When this creature is turned face up, ..." - so only the
    #: self-referential form is read. Emitted by `Game.turn_face_up`, the
    #: special action CR 702.37e describes, the only place the engine turns
    #: a face-down permanent face up outside a test poking `CardState.
    #: turn_face_up` directly.
    TURNED_FACE_UP = "turned_face_up"
    #: CR 701.9a: "To discard a card, move it from its owner's hand to that
    #: player's graveyard." Captain Howler, Sea Scourge's "Whenever you
    #: discard one or more cards, ..." is the only printing in the pool.
    #: CR 603.2c: "An ability triggers only once each time its trigger event
    #: occurs. However, it can trigger repeatedly if one event contains
    #: multiple occurrences" - "one or more cards" is the discard *action*
    #: itself named as the event (however many cards it moves at once), not a
    #: per-card occurrence, so this fires once per discard action with a
    #: count on the event (`GameEvent.amount`), emitted by whichever call
    #: site discards more than one card at a time as a single batch.
    DISCARDS_A_CARD = "discards_a_card"
    #: CR 107.15a: "'{rN}—[Effect]' means 'When one or more lore counters are
    #: put onto this Saga, if the number of lore counters on it was less than
    #: N and became at least N, [effect].'" Never printed as a line of
    #: condition text at all - `_parse_chapter_line` synthesizes one
    #: `TriggeredAbility` per chapter number straight off the card's own `I —`
    #: / `I, II —` / `III —` markers, each carrying its own threshold on
    #: `TriggeredAbility.chapter`, the same way a keyword ability's expansion
    #: carries no printed condition either.
    LORE_COUNTERS_ADDED = "lore_counters_added"
    #: CR 701.22a's scry and CR 701.25a's surveil, watched together the way
    #: every printing in the pool asks for it - "Whenever you scry or
    #: surveil, ..." (Denzilore Fatehold, Matoya, Archon Elder) - never one
    #: without the other. CR 701.22b/701.25c both say plainly that scrying or
    #: surveilling for 0 "is not a scry/surveil event" at all, so `Game.scry`/
    #: `Game.surveil` emit this only once `count > 0`.
    SCRY_OR_SURVEIL = "scry_or_surveil"
    #: CR 606.3: "A player may activate a loyalty ability of a permanent
    #: they control any time they have priority and the stack is empty,
    #: during a main phase of their turn." Ajani Unrelenting's own "Whenever
    #: you activate a loyalty ability, ..." and Gideon the Oathless's
    #: "Whenever an opponent activates a loyalty ability, ..." are two of the
    #: printings in the pool. Emitted by `Game.activate_ability`, the one
    #: place CR 606.3's own activation happens, right where `loyalty_
    #: activations` already records the once-per-turn count.
    LOYALTY_ABILITY_ACTIVATED = "loyalty_ability_activated"
    #: CR 701.37a: the Monstrosity keyword action's own "and it becomes
    #: monstrous" half. Printed as "When [this creature] becomes monstrous,
    #: ..." (Polukranos, World Eater; Arbor Colossus) - `Game.become_monstrous`
    #: is the only place this fires, and only on the "wasn't monstrous
    #: already" branch CR 701.37a itself gates the whole action on, so a
    #: second Monstrosity activation on an already-monstrous permanent never
    #: raises a second one of these. `GameEvent.amount` carries the N (or X)
    #: it became monstrous with (CR 701.37c).
    BECOMES_MONSTROUS = "becomes_monstrous"
    #: CR 701.27e: "Some triggered abilities trigger when an object
    #: 'transforms into' an object with a specified characteristic. Such an
    #: ability triggers if the object either transforms or converts ... and
    #: has the specified characteristic immediately after it does so."
    #: `machines/effects.transform_permanent` raises it, once the permanent
    #: has actually turned over.
    TRANSFORMS = "transforms"


class CostKind(StrEnum):
    """What one comma-separated piece of an activation cost is (CR 602.1a)."""

    MANA = "mana"
    TAP = "tap"
    UNTAP = "untap"
    SACRIFICE = "sacrifice"
    DISCARD = "discard"
    PAY_LIFE = "pay_life"
    #: CR 606.2: "An activated ability with a loyalty symbol in its cost is a
    #: loyalty ability." The symbol is CR 107.7's `[+N]`, `[0]`, or `[−N]`, and
    #: it is the whole cost - the rules print no loyalty cost that shares its
    #: line with another piece.
    LOYALTY = "loyalty"
    OTHER = "other"


class Cost(EngineModel):
    """One piece of an activation cost, as printed."""

    kind: CostKind
    text: str


#: CR 107.7's three loyalty symbol shapes: `[+N]` ("Put N loyalty counters on
#: this permanent"), `[0]` ("Put zero loyalty counters on this permanent"), and
#: `[−N]` ("Remove N loyalty counters from this permanent"), where the rule's
#: "a minus sign followed by a number or an X" is the `−X` form. Scryfall prints
#: the minus as U+2212; the ASCII hyphen is accepted too. Brace-wrapped `{0}` is
#: a mana symbol and never matches - the classification checks it first.
#:
#: The brackets are optional. A planeswalker's own printed ability line never
#: carries them (Jace, Reality Sculptor's own oracle text reads "+1: Empower
#: Jace X, ..."), but CR 107.7's symbol *is* bracketed, and Scryfall's own
#: oracle text keeps the brackets whenever the identical ability is quoted
#: inside another card's granted-ability text - Sanctum Lurker's own
#: "Planeswalkers you control have '[+2]: This planeswalker deals ...'",
#: Ichormoon Gauntlet's off-set "'[0]: Proliferate' and '[−12]: Take an extra
#: turn ...'". Without this, `_classify_cost` read every granted loyalty
#: ability's own bracketed cost as `CostKind.OTHER`, and `Game.activation_
#: cost` raised trying to build a cost for the literal text "[+2]" - every
#: quoted grant in the pool broke the moment its own ability was activated,
#: not just Sanctum Lurker's.
_LOYALTY_SYMBOL = re.compile(r"^\[?(?:\+(?P<plus>\d+)|[−-](?P<minus>\d+|[Xx])|0)\]?$")


class LoyaltyCost(EngineModel):
    """One loyalty symbol read out of an activation cost (CR 107.7, CR 606.2)."""

    #: The symbol as printed: `+2`, `0`, `−X`.
    printed: str
    #: The signed counter change the symbol asks for (CR 107.7): positive puts
    #: that many loyalty counters on, negative removes them, zero puts zero -
    #: which is still a cost, just one with no event. None when the symbol is
    #: `−X` and a player chooses the amount.
    amount: int | None

    @property
    def variable(self) -> bool:
        """True when the amount is a chosen X, which this engine cannot choose."""
        return self.amount is None

    @property
    def removes(self) -> int:
        """How many loyalty counters paying takes off, 0 when it removes none."""
        return max(0, -(self.amount if self.amount is not None else 0))


def _loyalty_symbol(text: str) -> LoyaltyCost | None:
    """Read one cost piece as a loyalty symbol, or None if it is not one."""
    match = _LOYALTY_SYMBOL.match(text)
    if match is None:
        return None
    if match.group("plus") is not None:
        return LoyaltyCost(printed=text, amount=int(match.group("plus")))
    if match.group("minus") is not None:
        rest = match.group("minus")
        return LoyaltyCost(printed=text, amount=None if rest.lower() == "x" else -int(rest))
    return LoyaltyCost(printed=text, amount=0)


class BaseAbility(EngineModel):
    """What every parsed line carries, whatever it turned out to be."""

    #: The line exactly as printed, reminder text included.
    raw: str
    #: The line with reminder text removed and whitespace collapsed.
    text: str
    #: Reminder text as printed, parentheses and all. None when there was none.
    #: CR 207.2a - it has no game function, but it is the giveaway for what a
    #: keyword means, so it is kept rather than thrown away.
    reminder: str | None = None
    #: The name of the face this line was printed on.
    face: str
    #: CR 207.2c ability word, as in `Landfall — Whenever ...`. No rules
    #: meaning; kept because it names the mechanic.
    ability_word: str | None = None
    #: CR 716.2a's own class level bar: the paragraph this ability was printed
    #: under is only "in effect" once a Class's `class_level` reaches this
    #: number (`None` for level 1, and for anything not printed on a Class at
    #: all - see `parse_abilities`'s own Class-detection pass). Set on every
    #: kind of ability, not just `TriggeredAbility` (whose own `chapter` field
    #: is the Saga-only sibling of this), because CR 716.2a's "As long as this
    #: Class is level N or greater, it has [Abilities]" reaches a static
    #: ability just as often as a triggered one - Artist's Talent's own level
    #: 2 and 3 are both static.
    class_level: int | None = None


class ActivationCostReduction(EngineModel):
    """CR 601.2f's "reduce the cost" step, applied to an activated ability's
    own cost via CR 602.2b ("the remainder of the process for activating an
    ability is identical to the process for casting a spell"): "This ability
    costs [N] less to activate for each [quality] you control."

    Read as a **separate static ability** from whatever the rest of the
    paragraph's activated ability does, not a third clause of its effect - CR
    702.41a ("Affinity ... means 'This spell costs {1} less to cast for each
    [text] you control.'") and CR 702.125a ("Undaunted ... means 'This spell
    costs {1} less to cast for each opponent you have.'") are the CR's own
    precedent for this exact sentence shape being a static ability in its own
    right, and CR 604.1 ("Static abilities ... are written as statements, and
    they're simply true") is what a sentence like this always is. Boseiju's
    and Otawara's Channel abilities print theirs sharing a line with the
    destroy/bounce effect with no blank line or bullet between them, but
    sharing a printed line is not the same as sharing an ability (CR 607.2h
    is the CR's own example of two abilities linked by sharing one paragraph
    while staying distinct) - so `_parse_activated` splits this sentence off
    `ActivatedAbility.effect` rather than leaving it there to sink the whole
    thing when a clause parser cannot read it.
    """

    amount: int
    #: The quality's own words, as printed - "legendary creature". Read
    #: generically off a CR 205.4a supertype and/or CR 205.2a card type by
    #: `Game.activation_cost_reduction_for`; no card name involved. `None`
    #: when `target_quality` is set instead - exactly one of the two is ever
    #: set, matching which of the two printed shapes this sentence is.
    quality: str | None = None
    #: Dragonfire Blade's own shape: "This ability costs {1} less to
    #: activate for each color of the creature it targets." and Warrior's
    #: Blades' "... for each +1/+1 counter on the creature it targets." -
    #: what is counted on the ability's own *target* rather than among
    #: permanents its controller controls. Kept as the printed words ("color",
    #: "+1/+1 counter") and read generically by
    #: `machines/keywords.target_cost_reduction_amount`, the same "read the
    #: phrase, don't guess a table" approach `quality` above already takes.
    target_quality: str | None = None
    #: SOS's Diary of Dreams: "This ability costs {1} less to activate for
    #: each page counter on this artifact." - counted on the ability's own
    #: *source* rather than among permanents its controller controls
    #: (`quality`) or on the ability's target (`target_quality`); exactly one
    #: of the three is ever set. Kept as the printed counter kind ("page")
    #: and read generically by `Game.activation_cost_reduction_for` off
    #: `CardState.counter_count`, the same open CR 122.1 vocabulary every
    #: other counter-kind read in this codebase already takes.
    self_counter_kind: str | None = None


#: "This ability costs {N} less to activate for each <quality> you control."
#: - matched only as the *last* sentence of an activated ability's effect, so
#: it is read the same way whichever card prints it, never by name.
_TRAILING_ACTIVATION_COST_REDUCTION_RE = re.compile(
    r"^this ability costs \{(?P<amount>\d+)\} less to activate for each "
    r"(?P<quality>.+?) you control\.?$",
    re.IGNORECASE,
)

#: The target-scoped sibling: "... for each color of the creature it
#: targets." (Dragonfire Blade) and "... for each +1/+1 counter on the
#: creature it targets." (Warrior's Blades) - "of" for a characteristic
#: count, "on" for a counter count, and the object word itself left open
#: ("creature" is the only one printed in the pool, but nothing here assumes
#: it - `permanent`/`artifact` would read the same way).
_TRAILING_TARGET_COST_REDUCTION_RE = re.compile(
    r"^this ability costs \{(?P<amount>\d+)\} less to activate for each "
    r"(?P<what>.+?) (?:on|of) the \w+ it targets\.?$",
    re.IGNORECASE,
)

#: `target_cost_reduction_amount`'s own reading of a "<kind> counter[s]"
#: phrase - the counter half of `ActivationCostReduction.target_quality`.
_TARGET_COUNTER_PHRASE_RE = re.compile(r"^(?P<kind>[\w+/−-]+) counters?$", re.IGNORECASE)

#: The self-counter sibling: "... for each <kind> counter on this <type>."
#: (Diary of Dreams) - a count on the ability's own source, not its target
#: (`_TRAILING_TARGET_COST_REDUCTION_RE`'s "the ... it targets") and not a
#: quality among permanents its controller controls
#: (`_TRAILING_ACTIVATION_COST_REDUCTION_RE`'s "... you control").
_TRAILING_SELF_COUNTER_COST_REDUCTION_RE = re.compile(
    r"^this ability costs \{(?P<amount>\d+)\} less to activate for each "
    r"(?P<kind>[\w+/−-]+) counters? on this \w+\.?$",
    re.IGNORECASE,
)


def target_cost_reduction_amount(
    reduction: ActivationCostReduction, target: Any, game: Any = None
) -> int | None:
    """How many of `reduction.target_quality` are on `target` right now, or
    `None` when the printed phrase is not one this reads (CR 601.2f via CR
    602.2b, counted at the ability's own target rather than among permanents
    its controller controls - `Game.activation_cost_reduction_for`'s sibling).

    Two shapes read: a bare "color"/"colors" (Dragonfire Blade), counted off
    the target's *computed* colours (CR 613.5) when a live `game` is given -
    a static ability could still be changing them - and a plain-English
    "<kind> counters?" (Warrior's Blades' "+1/+1 counter"), counted directly
    off the target `CardState`'s own counters (CR 122.1; a counter kind is
    never itself a layer-6 characteristic, so there is no computed board to
    prefer here). Anything else returns `None` rather than a guess, the same
    fail-closed default `Game.activation_cost_reduction_for` already gives an
    unread "you control" quality.
    """
    phrase = (reduction.target_quality or "").strip().lower()
    if phrase in ("color", "colors"):
        colors = game.characteristics_of(target).colors if game is not None else target.colors
        return len(colors)
    match = _TARGET_COUNTER_PHRASE_RE.fullmatch(phrase)
    if match is not None:
        kind = match.group("kind").replace("−", "-")
        return target.counter_count(kind)
    return None


def _split_off_trailing_cost_reduction(effect: str) -> tuple[str, ActivationCostReduction | None]:
    """Peel a trailing "This ability costs [N] less ..." sentence off an
    activated ability's effect text, if it has one (CR 601.2f via CR 602.2b).

    Splits on the same "end of sentence" boundary the rest of this module
    uses (`re.split(r"(?<=\\.)\\s+", ...)`), so a two-sentence effect like
    Otawara's ("Return target ... to its owner's hand. This ability costs
    {1} less ...") is told apart correctly, and a one-sentence effect that
    happens to end the same way a reduction sentence would is not touched
    unless it *is* the whole sentence.
    """
    sentences = [s for s in re.split(r"(?<=\.)\s+", effect.strip()) if s]
    if not sentences:
        return effect, None
    last = sentences[-1].strip()
    match = _TRAILING_ACTIVATION_COST_REDUCTION_RE.match(last)
    if match is not None:
        reduction = ActivationCostReduction(
            amount=int(match.group("amount")), quality=match.group("quality").strip()
        )
        return " ".join(sentences[:-1]).strip(), reduction
    target_match = _TRAILING_TARGET_COST_REDUCTION_RE.match(last)
    if target_match is not None:
        reduction = ActivationCostReduction(
            amount=int(target_match.group("amount")),
            target_quality=target_match.group("what").strip(),
        )
        return " ".join(sentences[:-1]).strip(), reduction
    self_counter_match = _TRAILING_SELF_COUNTER_COST_REDUCTION_RE.match(last)
    if self_counter_match is not None:
        reduction = ActivationCostReduction(
            amount=int(self_counter_match.group("amount")),
            self_counter_kind=self_counter_match.group("kind").strip().lower(),
        )
        return " ".join(sentences[:-1]).strip(), reduction
    return effect, None


class ActivatedAbility(BaseAbility):
    """CR 602.1: `[Cost]: [Effect.] [Activation instructions (if any).]`"""

    kind: Literal[AbilityKind.ACTIVATED] = AbilityKind.ACTIVATED
    #: CR 602.1a: everything before the colon, as printed.
    cost: str
    #: `cost` split on its top-level commas and classified.
    costs: list[Cost]
    #: Everything after the colon, less any activation instructions.
    effect: str
    #: CR 602.1b: trailing `Activate only ...` text restricting when it may be
    #: activated.
    instructions: str | None = None
    #: Set when the effect is `Add ...`, linking to the mana ability model.
    #: Note that a mana ability need not be tappable, so this can be set on an
    #: ability `parse_mana_abilities` does not return.
    mana: ManaAbility | None = None
    #: CR 606.2: "An activated ability with a loyalty symbol in its cost is a
    #: loyalty ability." Set when the whole cost is exactly one loyalty symbol
    #: (CR 107.7), the only form the rules print - which is also what keeps
    #: Ugin's `0: Add {C}{C}{C}.` out of the mana-ability fast path (CR 605.1a:
    #: a mana ability "it's not a loyalty ability").
    loyalty: LoyaltyCost | None = None
    #: The zone this ability functions in, when its own cost or effect says so
    #: (CR 113.6j, CR 113.6m) - `None` for the CR 113.6 default, "on the
    #: battlefield". Read by `_activated_ability_zone` off the printed cost and
    #: effect alone, so a future card built the same way (discarding itself, or
    #: returning itself from its graveyard) needs no table row to be read
    #: correctly. Boseiju's and Otawara's Channel abilities discard themselves
    #: as part of their own printed cost, so this reads `HAND` for both without
    #: either name ever appearing here; World Breaker's "Return this card from
    #: your graveyard to your hand" reads `GRAVEYARD` the same way.
    zone: Zone | None = None
    #: The CR 113.6 sub-rule `zone` was read from, alongside it so a refusal
    #: message can cite the rule it is actually enforcing rather than a
    #: guessed one. `None` exactly when `zone` is `None`.
    zone_rule: str | None = None
    #: A trailing "This ability costs [N] less to activate for each [quality]
    #: you control" sentence, split off `effect` before it was stored - see
    #: `ActivationCostReduction`'s own docstring for why this is a separate
    #: ability rather than a clause of the one above it.
    cost_reduction: ActivationCostReduction | None = None
    #: CR 716.2a: set when this ability *is* a class level bar itself -
    #: "[Cost]: Level N" prints as an ordinary cost-colon-effect line whose
    #: whole "effect" is the literal words "Level N", which `parse_abilities`
    #: recognises and tags here rather than leaving as an effect sentence no
    #: clause parser in `machines/effects.py` was ever meant to read. `None`
    #: for every ordinary activated ability, Class or not.
    class_level_target: int | None = None
    #: CR 702.177a: "Exhaust — [Cost]: [Effect]" means "[Cost]: [Effect].
    #: Activate only once." Set when the CR 207.2c-shaped prefix this line
    #: was stripped of (`ability_word`, `_ABILITY_WORD`'s own em-dash form -
    #: the same shape Channel's "Channel — {1}{G}, ..." uses) is literally
    #: the word "Exhaust", the actual CR 702 keyword, read the same way
    #: `_parse_keyword_cost`/`_parse_keyword_parameter` already recognise a
    #: keyword by its printed name rather than by a lookup table.
    #: `Game.activate_ability` reads this to record the permanent, never-
    #: cleared-per-turn activation (`Game.exhausted`) CR 602.5b's "Activate
    #: only once each turn" cannot express.
    exhaust: bool = False
    #: CR 702.193a: "Power-up — [Cost]: [Effect]" means "[Cost]: [Effect]. If
    #: this permanent entered this turn, this ability's cost is reduced by
    #: this permanent's mana cost. Activate this ability only once." Read off
    #: the printed em-dash prefix exactly the way `exhaust` above is - Power-up
    #: is a real CR 702 keyword, not a CR 207.2c ability word, but WOTC prints
    #: it in the same "Word — cost: effect." shape, so the same parser branch
    #: sees it. `Game.why_cannot_activate`/`Game.activate_ability` reuse the
    #: same `exhausted` bookkeeping `exhaust` already reads (CR 702.193a's
    #: "Activate this ability only once" is exhaust's own "Activate only
    #: once", word for word), and `Game.activation_cost` reads this flag to
    #: apply the entered-this-turn discount (CR 702.193b, CR 118.7).
    power_up: bool = False


class TriggeredAbility(BaseAbility):
    """CR 603.1: `[When/Whenever/At] [trigger condition], [effect].`"""

    kind: Literal[AbilityKind.TRIGGERED] = AbilityKind.TRIGGERED
    #: Which of the three words it began with.
    word: TriggerWord
    #: The trigger condition, without the leading word.
    condition: str
    #: CR 603.4: the `if [condition],` between the trigger event and the effect.
    intervening_if: str | None = None
    #: Everything after the condition and the intervening if.
    effect: str
    #: The recognised shape of the condition, when it is one of the common ones.
    event: TriggerEvent | None = None
    #: The CR 702 keyword this ability is the expansion of, when it was not
    #: printed as a line at all.
    #:
    #: Ward (CR 702.21a), prowess (CR 702.108a), cascade (CR 702.85a), persist
    #: (CR 702.79a) and mobilize (CR 702.181a) are all *triggered abilities* the
    #: card prints as one word. `machines/keywords.keyword_triggered_abilities`
    #: writes the rule's own expansion out as one of these, and this field is
    #: what lets the effect be found afterwards: `machines/effects.py` is keyed
    #: by card name, and a generic keyword has no card name to be keyed under.
    keyword: str | None = None
    #: CR 603.2h: "This ability triggers only once each turn" (or the rule's
    #: own "Do this only once each turn"), stripped out of `effect` and
    #: recorded here so `machines/triggers.triggers_for` can gate on it -
    #: Caretaker's Talent's own token-enters trigger is the only printing in
    #: the pool with this restriction.
    once_per_turn: bool = False
    #: CR 107.15a's `N`: the lore-counter threshold one `{rN}—` chapter symbol
    #: names, for a `TriggeredAbility` `_parse_chapter_line` synthesized off a
    #: Saga's own `I —` / `I, II —` / `III —` marker rather than read off any
    #: printed condition text (`event` is `TriggerEvent.LORE_COUNTERS_ADDED`
    #: for every one of these, and `condition` holds CR 107.15a's own
    #: paraphrase - "one or more lore counters are put onto this saga" - for a
    #: human reading a `LayerNotice`/decision prompt, not for re-parsing).
    #: `None` for every other `TriggeredAbility` - the ordinary, printed kind.
    chapter: int | None = None
    #: CR 603.2: a "while <doing something>" qualifier printed after the
    #: trigger condition - "while casting a spell with emerge" (Foul
    #: Emissary), "while you're activating a craft ability" (Market Gnome),
    #: "while scrying" (The Temporal Anchor). It says how the trigger event
    #: happened, so it is part of the event and is asked of the event as it
    #: occurs (`machines/triggers.condition_matches`), never rechecked on
    #: resolution the way an intervening "if" is (CR 603.4, CR 608.2a) - by
    #: then the casting is over. `condition` holds the event without it.
    event_qualifier: str | None = None


class StaticAbility(BaseAbility):
    """CR 604.1: a statement that is simply true.

    Also where a spell ability lands (CR 113.3a) - the text of an instant or
    sorcery is not a static ability, but this parser does not read type lines.
    """

    kind: Literal[AbilityKind.STATIC] = AbilityKind.STATIC


class KeywordAbility(BaseAbility):
    """CR 702: one keyword, with its cost or parameter if it has one."""

    kind: Literal[AbilityKind.KEYWORD] = AbilityKind.KEYWORD
    #: The keyword as printed on this line, e.g. `Flashback`, `deathtouch`.
    keyword: str
    #: The Scryfall spelling, so `deathtouch` and `Deathtouch` compare equal.
    canonical: str
    #: The cost as printed, whether that is mana (`Flashback {2}{R}`), a number
    #: (`Annihilator 2`), or a whole sentence after an em dash
    #: (`Evoke—Exile a black card from your hand.`).
    cost: str | None = None
    #: A non-cost parameter, as in `Protection from red`.
    parameter: str | None = None
    #: The number in `Suspend 3—{2}{B}{B}` or `Annihilator 2`, when there is one.
    count: int | None = None
    #: True when `cost` is nothing but mana symbols, so a caller can hand it
    #: straight to `ManaCost.parse` instead of reading a sentence.
    cost_is_mana: bool = False
    #: True when the cost was printed after an em dash rather than after a
    #: space. WOTC uses the em-dash form exactly when the cost is not purely
    #: mana - `Evoke—Exile a black card from your hand.` - and the two are
    #: worth telling apart, because only the em-dash form needs a sentence read.
    em_dash: bool = False
    #: A trailing "This ability costs [N] less to activate for each
    #: [quality] ..." sentence sharing this keyword's own paragraph (CR
    #: 607.2h: two abilities can share one printed paragraph) - Warrior's
    #: Blades' and Dragonfire Blade's own "Equip [N]. This ability costs
    #: [M] less ..." lines. Split off by `_parse_line` before keyword
    #: matching runs, the same way `ActivatedAbility.cost_reduction` is
    #: split off an activated ability's own effect text, so the trailing
    #: sentence's full stop cannot disqualify the line from
    #: `_parse_keywords`'s "no full stop" rule.
    cost_reduction: ActivationCostReduction | None = None


class UnparsedAbility(BaseAbility):
    """A line this module could not read. Not a category in the rules."""

    kind: Literal[AbilityKind.UNPARSED] = AbilityKind.UNPARSED


Ability = Annotated[
    ActivatedAbility | TriggeredAbility | StaticAbility | KeywordAbility | UnparsedAbility,
    Field(discriminator="kind"),
]


#: CR 716.2a's own class level bar, once `_parse_line` has already turned it
#: into an `ActivatedAbility`: the whole "effect" after the colon is nothing
#: but the literal words "Level N" - no card in the pool has any other
#: activated ability whose entire effect reads that way, so this is safe to
#: recognise generically rather than pinned to one printing.
_CLASS_LEVEL_BAR_EFFECT_RE = re.compile(r"^Level (?P<n>\d+)$")


#: `parse_abilities`'s memo, keyed on `Card.id` - the Scryfall id that
#: identifies one printing uniquely, so two different printings (even two
#: prints of the same card with the same name) can never collide. Sound only
#: because `Card` is immutable (`frozen=True`, `models/card.py`): a card that
#: could still change after construction would make this cache return a stale
#: parse the moment it did, with nothing to notice. See
#: `tests/test_card.py::test_card_is_immutable`.
#:
#: A real 18-source board asked `_auto_tap_candidates` (`machines/cost.py`)
#: to re-derive the same handful of cards' abilities thousands of times over
#: one affordability question; this and `activated_abilities_of`'s own memo
#: are what stop that from re-running the oracle-text parse every time.
#:
#: The returned list, and every `Ability` object in it, is shared by every
#: caller that asks about the same printing again - nothing here defends
#: against a caller mutating one, the same trust `tests/cards.py`'s own
#: `@cache`d card pool already places in callers not mutating a `Card`.
_ability_cache: dict[UUID, list[Ability]] = {}


def parse_abilities(card: Card) -> list[Ability]:
    """Every ability printed on a card, front face and backs, in printed order.

    One entry per ability, not per line: a keyword list on one line yields one
    `KeywordAbility` per keyword. A line that is only reminder text yields
    nothing.

    CR 716.2a: a Class's text box is one or more "[Cost]: Level N" bars, each
    followed by the paragraph(s) that are only "in effect" once the Class has
    reached that level - text before the first bar belongs to level 1
    implicitly (CR 716.2d). Detected per face by the presence of at least one
    `_CLASS_LEVEL_BAR_EFFECT_RE`-shaped `ActivatedAbility` among that face's
    own lines - a face with none is left exactly as before, so this changes
    nothing for the vast majority of cards that print no Class subtype at all.

    Memoised on `card.id` - see `_ability_cache`.
    """
    cached = _ability_cache.get(card.id)
    if cached is not None:
        return cached
    abilities: list[Ability] = []
    for face_name, text in _faces(card):
        face_abilities: list[Ability] = []
        for line in _merge_modal_bullet_lines(text.split("\n")):
            face_abilities.extend(_parse_line(line, card.keywords, face_name))

        is_class_face = any(
            isinstance(ability, ActivatedAbility)
            and _CLASS_LEVEL_BAR_EFFECT_RE.match(ability.effect.strip())
            for ability in face_abilities
        )
        if is_class_face:
            current_level = 1
            for ability in face_abilities:
                bar_match = None
                if isinstance(ability, ActivatedAbility):
                    bar_match = _CLASS_LEVEL_BAR_EFFECT_RE.match(ability.effect.strip())
                if bar_match is not None:
                    assert isinstance(ability, ActivatedAbility)
                    ability.class_level_target = int(bar_match.group("n"))
                    current_level = ability.class_level_target
                    continue
                ability.class_level = current_level

        abilities.extend(face_abilities)
    _ability_cache[card.id] = abilities
    return abilities


def parse_granted_ability_lines(texts: Sequence[str]) -> list[Ability]:
    """`CardState.granted_ability_texts` read the same way `parse_abilities`
    reads a `Card`'s own printed lines, one `Ability` per line.

    CR 111.3's own licence for a token's stated text ("functionally
    equivalent to the characteristic values that are printed on a card") is
    the reason a token's granted line is *not* what this reads - a token's
    whole rules text goes through `TokenDefinition.oracle_text` into a real
    `Card`, so `parse_abilities` already covers it. This is for the other
    shape: an ability a resolving effect hands to an *existing* object
    without changing what card it is (CR 613.1f's own layer-6 "gains an
    ability", generalised here to the whole ability rather than only a
    keyword) - Urza's Saga's own chapter I/II grants, kept on `CardState.
    granted_ability_texts` rather than on the immutable `Card` (a printing
    never changes once loaded - see `Card`'s own docstring, `models/card.py`).

    No keyword list and no face to filter by: a granted line is not part of
    any card's own keyword-abbreviated line (`Card.keywords` is Scryfall's
    per-*printing* summary, meaningless for a runtime-only grant) and is
    never printed on a specific face, so both of `_parse_line`'s remaining
    parameters are the same empty/blank value for every call.
    """
    abilities: list[Ability] = []
    for text in texts:
        abilities.extend(_parse_line(text, [], ""))
    return abilities


#: A line ending in CR 700.2's own instruction shape - "choose one —",
#: "choose two —", "choose one or more —" - the header of a bulleted modal
#: list. Anchored on the trailing em dash Scryfall prints, so an ordinary
#: sentence that happens to contain the word "choose" ("Choose target
#: creature.") never matches. The instruction may end in its own second
#: sentence instead - "choose one. If there are four or more card types among
#: cards in your graveyard, choose both instead." (Prophetic Titan) - which is
#: still the header of the bullets under it.
_MODAL_INSTRUCTION_TAIL = re.compile(
    r"choose\b.*(?:[-—]|\bchoose [^.]+ instead\.)\s*$", re.IGNORECASE
)


def _merge_modal_bullet_lines(lines: list[str]) -> list[str]:
    """Fold a modal instruction line and the bulleted lines under it back
    into one line (CR 700.2's own "two or more options in a bulleted list").

    Oracle text splits a card's rules text on Scryfall's own newlines, one
    printed line per list entry - `["Whenever this creature attacks or
    blocks, choose one —", "• Create a 3/3 ... token.", "• You gain 3
    life.", "• Draw a card."]` for Elder Gargaroth. `text.split("\\n")` (the
    only caller) hands each of those to `_parse_line` in isolation, so a
    *triggered* ability's own modal tail - everything `_parse_triggered`
    would read as `effect` - never includes its own bullets: each bullet line
    parses instead as an orphaned, un-conditioned `StaticAbility` with no
    link back to "choose one" at all, and Elder Gargaroth's attack/block
    trigger goes on the stack and does nothing (`machines/modes.py`'s
    bulleted-list reader is never even reached, since it is only ever handed
    a *spell's* whole, already-multi-line `oracle_text` by `modal_profile`,
    not a `parse_abilities` line). A modal *spell*'s own oracle text never
    hits this problem, because `modal_profile(card)` reads `Card.
    front_oracle_text` directly rather than going through this per-line
    split at all.

    This is the fix, ahead of the split: any line ending in CR 700.2's own
    "choose N —" instruction absorbs every immediately following bulleted
    line into itself (newline-joined, so `machines/modes.py`'s own
    line-anchored bullet regex still finds each `•` at the start of a line),
    stopping at the first line that is not itself a bullet. A card with no
    modal triggered ability is untouched - no line ends this way, so nothing
    merges and every line reaches `_parse_line` exactly as printed today.
    """
    merged: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _MODAL_INSTRUCTION_TAIL.search(line):
            block = [line]
            index += 1
            while index < len(lines) and lines[index].lstrip().startswith("•"):
                block.append(lines[index])
                index += 1
            merged.append("\n".join(block))
            continue
        merged.append(line)
        index += 1
    return merged


def abilities_of_kind(card: Card, kind: AbilityKind) -> list[Ability]:
    """The abilities of one category, for callers that only want one."""
    return [ability for ability in parse_abilities(card) if ability.kind is kind]


def keyword_abilities(card: Card) -> list[KeywordAbility]:
    """Every CR 702 keyword ability printed on a card, cost and all.

    A printing's Scryfall `keywords` list says *which* keywords are on it; this
    says how each one was printed, so `Flashback {2}{R}` and
    `Flashback—Sacrifice a Mountain.` are told apart by their `cost`.
    """
    return [ability for ability in parse_abilities(card) if isinstance(ability, KeywordAbility)]


def keywords_in_lines(lines: list[str], known: list[str]) -> set[str]:
    """Every CR 702 keyword these oracle-text lines carry, lowercased.

    The same line parser `parse_abilities` uses, pointed at text that did not
    come off a printing - which is what the layer system produces (CR 613.5):
    a permanent's abilities after every continuous effect has been applied are
    a list of *text*, and the card behind it may no longer say any of it.

    `known` is the vocabulary to match against, because there is no keyword
    table in this module: the caller says which keywords it cares about.
    """
    return {ability.canonical.lower() for ability in keyword_abilities_in_lines(lines, known)}


def keyword_abilities_in_lines(lines: list[str], known: list[str]) -> list[KeywordAbility]:
    """Every CR 702 keyword ability these lines carry, one per instance, with
    its parameter and count - `keywords_in_lines` keeps only the names, which
    is not enough for a keyword whose instances add up (CR 702.164b's total
    toxic value)."""
    return [
        ability
        for line in lines
        for ability in _parse_line(line, list(known), face="")
        if isinstance(ability, KeywordAbility)
    ]


def keyword_ability(card: Card, keyword: str) -> KeywordAbility | None:
    """One keyword ability by name, case-insensitively. None if it is not printed."""
    for ability in keyword_abilities(card):
        if ability.canonical.lower() == keyword.lower():
            return ability
    return None


#: The lookbehind `self_normalized_effect_text` guards every substitution
#: with - see that function's own docstring for why "Empower Jace X" must
#: never be misread as a self-reference to a planeswalker named Jace.
_EMPOWER_KEYWORD_LOOKBEHIND = r"(?<!(?i:empower ))"

#: A candidate self-name is never a match when what follows it in the text is
#: the start of a *different*, longer capitalized name - "Hanweir" inside "a
#: creature named Hanweir Garrison" (another card's own full name, `\s+[A-Z]`)
#: or "meld them into Hanweir, the Writhing Township" (a third card's, its
#: own comma-epithet shape - `,\s*(?:the\s+)?[A-Z]`, skipping the lowercase
#: epithet word the way `self_reference_names`' own epithet candidates read
#: past it for *this* card). The comma branch only refuses a comma directly
#: followed by a capitalized continuation (with an optional "the" between
#: them) - never a bare trailing comma on its own, which is ordinary English
#: punctuation an in-sentence self-reference is free to sit in front of (The
#: Millennium Calendar's own "... on The Millennium Calendar, sacrifice
#: it ..." must still normalize).
#:
#: The third branch (`['’]s\s+[A-Z]`) is the identical guard applied to a
#: *possessive* continuation: Ajani Resolute's own "-4" creates a token named
#: "Ajani's Pridemate" (CR 111.3, the token's own fixed name - a different,
#: longer proper noun that merely starts with this card's own short name),
#: which used to normalize into "this permanent's Pridemate" with nothing to
#: stop it. A capitalized word right after the apostrophe is what marks a
#: longer name continuing, exactly as a capital right after a bare space
#: already does for the first branch; a *lowercase* continuation is this
#: card genuinely possessing something of its own and stays refused by
#: nothing here - Fblthp, Impossibly Lost's own "Fblthp's owner shuffles him
#: into their library" still normalizes to "this permanent's owner ...".
#: Both the straight and the typographic apostrophe are read, matching every
#: other possessive this module already reads either way.
#:
#: Applied to every candidate uniformly, not only a bare-short one: by the
#: time a shorter candidate's turn comes (`self_reference_names`' longest-
#: first order), every occurrence that really was this card naming itself
#: has already been consumed by a longer candidate, so anything this
#: lookahead still refuses was never this card to begin with.
_LONGER_NAME_CONTINUATION_LOOKAHEAD = r"(?!,\s*(?:the\s+)?[A-Z]|\s+[A-Z]|['’]s\s+[A-Z])"


def self_reference_pattern(name: str) -> str:
    """The regex `self_normalized_effect_text` and
    `machines/triggers._self_referential` both match a self-reference
    candidate with - one word-bounded, empower-guarded
    (`_EMPOWER_KEYWORD_LOOKBEHIND`), longer-name-guarded
    (`_LONGER_NAME_CONTINUATION_LOOKAHEAD`) pattern shared so the two never
    drift into reading CR 201.5/201.5c self-reference differently.

    The name is bounded by "no word character on either side" rather than by
    `\b`: identical for a name that starts and ends in a letter, and the only
    reading that works for one ending in punctuation - M.O.D.O.K.'s own
    "M.O.D.O.K. connives." has no `\b` after its final period at all."""
    return (
        rf"{_EMPOWER_KEYWORD_LOOKBEHIND}(?<!\w){re.escape(name)}(?!\w)"
        rf"{_LONGER_NAME_CONTINUATION_LOOKAHEAD}"
    )


#: Epithet-boundary words CR 201.5c's shortened names split on: "`<Name>` the
#: `<Epithet>`" (Liliana the Repentant) and "`<Name>` of `<Epithet>`" (Kiora of
#: Fire and Ashes, Koth of the Homestead) both call themselves by their first
#: word alone. Never itself a candidate (`self_reference_names`'s own "never
#: shorten to a bare article" guard) - a name that *starts* with one of these
#: words (`The Millennium Calendar`) must never contribute its own leading
#: "The"/"Of" as though it were a short form of itself.
_EPITHET_BOUNDARY_WORDS = ("the", "of")


def self_reference_names(card_name: str, *, legendary: bool = True) -> tuple[str, ...]:
    """Every string CR 201.5/201.5c lets `card_name`'s own printed text use to
    mean itself, longest first: the full name, the face before a `//`, the
    short form before a comma (Grist, the Hunger Tide -> Grist), and - only
    for a legendary permanent (`legendary=True`, the default a caller with no
    supertype to check keeps) - an epithet short form for a no-comma legend
    (`<Name> the/of <Epithet>` -> `<Name>`) and a bare short form for a plain
    two-word name with no comma or epithet word at all (`Ajani Resolute` ->
    `Ajani`, CR 201.5c).

    **The epithet and bare-short forms are a legendary-permanent
    convention.** Every printing this module has ever seen use either shape
    to name itself is a legendary creature or planeswalker (CR 201.5c gives
    a character its own "call sign"); a non-legendary card's first word is
    an ordinary English or Magic vocabulary word far more often than it is
    the card naming itself - Eldrazi Temple's "cast colorless **Eldrazi**
    spells" names CR 205.3m's creature type, Thopter Assembly's "create ...
    **Thopter** artifact creature tokens" names the token's own type, and
    Fire Magic's own Tiered mode labels ("**Fire** — {0} — ...") are CR
    700.2h's own modal cost-tier names - none of the three is this card
    naming itself, and all three used to be rewritten to "this permanent" as
    though they were. `legendary=False` from a caller that knows the card's
    own supertypes (CR 205.4a) turns both shapes off; the full name and the
    comma-shortened short form stay available regardless, since CR 201.5's
    plain "refers to the object it's on by name" and Oracle's own comma
    convention are not legendary-only the way the epithet and bare-word
    shortenings are.

    Longest first is what lets a caller building a find-and-replace out of
    this win the race a shorter candidate would otherwise lose: "Aerid
    Konstrari" has to replace the whole two-word name before its own shorter
    "Aerid" candidate ever gets a turn, or "When Aerid Konstrari enters"
    becomes "When this permanent Konstrari enters" instead of "When this
    permanent enters" (`self_normalized_effect_text`). `_self_referential`
    (`machines/triggers.py`) only needs membership, where order does not
    matter, but reuses the same ordered tuple rather than keeping a second
    copy of this logic.

    The epithet and bare-short forms are both narrowed on purpose, the same
    way and for the same reason: "Hanweir Battlements"'s own text names two
    *other* cards sharing its first word ("a creature named Hanweir
    Garrison", "meld them into Hanweir, the Writhing Township") - treating
    "Hanweir" as *this* card's own short name would rewrite both into
    nonsense, since neither reference is this card naming itself. Requiring a
    genuine CR 201.5c shape - an epithet word right after the first word, or
    *no* second name segment at all (a bare two-word name) - is what tells
    "Liliana the Repentant"/"Kiora of Fire and Ashes"/"Ajani Resolute" apart
    from "Search for Azcanta" and "Hanweir Battlements", whose own second
    words are an ordinary noun, not an epithet boundary and not the whole of
    a two-word name search would ever need to shorten. The bare-short form
    also refuses to shorten to a bare article, preposition, or conjunction on
    its own (`_EPITHET_BOUNDARY_WORDS` plus `a`/`an`) - a name that itself
    *starts* with one of those words ("The Millennium Calendar") must never
    contribute its own leading word as though it meant the whole card.
    """
    front = card_name.split("//")[0].strip()
    candidates = {card_name, front}
    if "," in front:
        candidates.add(front.split(",", 1)[0].strip())
    words = front.split(" ")
    if legendary and (
        len(words) >= 3
        and words[1].lower() in _EPITHET_BOUNDARY_WORDS
        or (
            len(words) == 2
            and "," not in front
            and words[0].lower() not in (*_EPITHET_BOUNDARY_WORDS, "a", "an")
        )
    ):
        candidates.add(words[0].strip())
    return tuple(sorted((name for name in candidates if name), key=len, reverse=True))


def self_normalized_effect_text(card_name: str, effect_text: str, *, legendary: bool = True) -> str:
    """`effect_text` with every CR 201.5/201.5c self-reference to `card_name`
    rewritten to CR 700.7's own "this permanent" - The Filigree Sylex's "Put
    an oil counter on The Filigree Sylex.", Grist, the Hunger Tide's own "put
    a loyalty counter on Grist" (the short form before the comma), Ruby,
    Daring Tracker's "Ruby gets +2/+2 until end of turn.", and Ajani
    Resolute's own bare "put a loyalty counter on Ajani." are all the same
    reference CR 700.7's "this [something]" makes, just spelled differently -
    rewritten once here, ahead of every shape-specific parser in
    `machines/effects.py` and `machines/layers.py`, so both read a
    self-named sentence the same way they already read "this creature"/"this
    permanent" rather than needing a second copy of every shape keyed on a
    literal name.

    "Empower Jace N" (CR 701.71a) names a fixed keyword-action target, never
    the source's own identity, even when the source's own short name happens
    to collide with it - Jace, Reality Sculptor's own "+1: Empower Jace X,
    where X is the number of Islands you control." is not "+1: Empower this
    permanent X, ..." (CR 201.5 self-reference is about the object using its
    own name to mean itself; the empower token is never the object the
    ability is printed on). A future "empower `<name>`" keyword sharing a
    planeswalker's own short name would hit the identical collision, so the
    guard is on the keyword phrase, not on the literal word "Jace".

    `legendary` (default `True`, preserving this function's own long-
    standing behaviour for a caller with no supertype to check) gates
    `self_reference_names`' own epithet and bare-two-word shortenings -
    see that function's docstring for why those two are a legendary-only
    convention and the full/comma-shortened forms are not.
    """
    normalized = effect_text
    for name in self_reference_names(card_name, legendary=legendary):
        normalized = re.sub(self_reference_pattern(name), "this permanent", normalized)
    return normalized


#: A legendary card's own gendered subject pronoun opening an effect
#: sentence - Hydro-Man, Fluid Felon's "he gets +1/+1 until end of turn." -
#: or opening any *later* sentence of a multi-sentence effect, the same
#: CR 201.5c self-reference in a second clause - Abomination, Terrifying
#: Titan's power-up rider "Put a +1/+1 counter on Abomination. He fights up
#: to one target creature an opponent controls." "^" still matches a
#: single-sentence effect exactly as before; `(?<=\. )` is the added
#: sentence-boundary case, so a caller that hands this a whole multi-sentence
#: effect (`activated_effect_for`'s own fallback, below) gets every self-
#: pronoun sentence rewritten, not only the first.
_LEGENDARY_SELF_PRONOUN_RE = re.compile(r"(?:^|(?<=\. ))(?:he|she) (?=\w)", re.IGNORECASE)

#: The same self-reference, mid-sentence and in object position - Agent
#: Maria Hill's own "... put a +1/+1 counter on her and draw a card."
#: CR 201.5c's rule is the identical one `_LEGENDARY_SELF_PRONOUN_RE` already
#: reads for the leading subject case: Oracle text spells a legend's own
#: gendered pronoun only for the legend it is printed on, in any
#: grammatical position, so "him"/"her"/"himself"/"herself" are read the
#: same way "he"/"she" already are - word-bounded, so "here"/"heron" are
#: never mistaken for the pronoun "her" inside them. Rewritten to "it"/
#: "itself" rather than `_LEGENDARY_SELF_PRONOUN_RE`'s own "this permanent":
#: an object-position anaphor is exactly what every other self-referential
#: "it" in this pool already reads (a trigger's own subject, CR 400.7), and
#: rewriting to a second, longer phrase mid-sentence would only ask every
#: object-pronoun-aware parser (`_parse_counter_on_it_trigger_subject_
#: clause` and its siblings) to recognise a phrase they do not print for
#: any other card.
_LEGENDARY_SELF_OBJECT_PRONOUN_RE = re.compile(r"\b(?:him|her)(self)?\b", re.IGNORECASE)


def legendary_self_pronoun_normalized(sentence: str) -> str:
    """`sentence` with a legend's own gendered pronoun rewritten to its
    neuter, self-referential form - a subject "he"/"she", at the very start
    or opening any later sentence, to CR 700.7's "this permanent"
    (`_LEGENDARY_SELF_PRONOUN_RE`), and any mid-sentence object
    "him"/"her"/"himself"/"herself" to the "it"/"itself" every other
    self-referential object pronoun in this pool already reads
    (`_LEGENDARY_SELF_OBJECT_PRONOUN_RE`). Called only for a legendary
    card's own triggered or activated ability: Oracle text uses these
    pronouns only for the legend it is printed on, the same self-reference
    CR 201.5c's shortened name makes (Hydro-Man, Fluid Felon's "if Hydro-Man
    is a creature, he gets +1/+1"; Agent Maria Hill's own "... put a +1/+1
    counter on her and draw a card."). Every occurrence is rewritten - a
    legend's own pronoun always means the same object."""
    normalized = _LEGENDARY_SELF_PRONOUN_RE.sub("this permanent ", sentence)
    return _LEGENDARY_SELF_OBJECT_PRONOUN_RE.sub(
        lambda match: "itself" if match.group(1) else "it", normalized
    )


def layer_readable_sentences(
    text: str | None,
    known_keywords: list[str] | None = None,
    *,
    static_only: bool = False,
    card_name: str | None = None,
    legendary: bool = True,
) -> list[str]:
    """`_layer_readable_sentences_uncached`, memoised - see that for what the
    sentences are.

    The layer engine asks this for every permanent every time a board is
    computed, and the answer is a pure function of printed text and these
    arguments, so it is cached on all of them (`known_keywords` as a tuple, in
    the order given). Strings are immutable and every caller gets a list of its
    own, so no caller can edit what the next one reads.
    """
    return list(
        _layer_readable_sentences_memo(
            text, tuple(known_keywords or ()), static_only, card_name, legendary
        )
    )


@functools.lru_cache(maxsize=16384)
def _layer_readable_sentences_memo(
    text: str | None,
    known_keywords: tuple[str, ...],
    static_only: bool,
    card_name: str | None,
    legendary: bool,
) -> tuple[str, ...]:
    return tuple(
        _layer_readable_sentences_uncached(
            text,
            list(known_keywords),
            static_only=static_only,
            card_name=card_name,
            legendary=legendary,
        )
    )


def _layer_readable_sentences_uncached(
    text: str | None,
    known_keywords: list[str] | None = None,
    *,
    static_only: bool = False,
    card_name: str | None = None,
    legendary: bool = True,
) -> list[str]:
    """Every sentence of `text` this module's own line classifier says a
    continuous effect (CR 611.2, CR 611.3) could plausibly come from.

    `static_only=True` restricts this to `StaticAbility` bodies alone (CR
    604.1), dropping the `ActivatedAbility`/`TriggeredAbility` bodies the
    default reads too. `machines/layers.py::effects_for`'s battlefield sweep
    needs exactly that restriction: it asks, for every permanent, "does this
    card's *static* ability generate a continuous effect" (CR 611.3), always
    with an empty `targets` sequence. The default's inclusion of a triggered
    or activated ability's own effect body is safe for `parsed_layer_effects`
    itself there - every shape it reads produces nothing for an empty target
    set, per the note below - but `looks_like_unparsed_layer_effect` has no
    such safety net: it does not build an effect, it only asks "does this
    text look like an attempted shape", and a triggered ability's own
    resolution-time magnitude (Kraul Harpooner's "This creature gets +X/+0
    ... where X is the number of creature cards in your graveyard", fully
    handled by `_parse_undergrowth_pump_and_fight_clause` when the trigger
    actually resolves) reads as exactly that - a false `LayerNotice` on a
    card whose ability already works. `static_only=True` is how the
    battlefield sweep asks its notice question without that false positive,
    while `create_continuous_effect_of_ability`'s own call (resolving one
    specific ability, with real targets) keeps reading the default so
    Oliphaunt's and Basking Rootwalla's rowless triggered/activated pumps
    still reach this classifier at all.

    `machines/layers.py`'s shape parser used to derive its sentences by
    stripping reminder text and an activation cost off each raw oracle-text
    line itself, duplicating this module's classification without ever
    consulting it - `StaticAbility` was parsed and thrown away. This is the
    seam that fixes that: it reuses `_parse_line`, the same classifier
    `parse_abilities` runs, on text that may have no card behind it (a
    resolving spell's own printed text is fine; a rebuilt permanent's ability
    list, in `keywords_in_lines`'s style, would be too, though no caller needs
    that yet).

    Three kinds of line can hold a continuous effect and are read here:

    - A `StaticAbility` (CR 604.1) - its `text` verbatim, reminder and any
      ability word already stripped. This is also where a spell's own effect
      lands: `parse_abilities`'s module docstring documents that this parser
      calls a leftover line static even on an instant or sorcery, because it
      does not read type lines - which is exactly right here, since CR 611.2's
      one-shot effect and CR 604.1's continuous one are read by the same
      shapes (a pump's duration is what tells them apart, not which category
      parsed it).
    - An `ActivatedAbility` (CR 602.1) - its `effect`, i.e. everything after
      the cost's colon, cost and any trailing activation instructions already
      split off. Basking Rootwalla's `{1}{G}: This creature gets +2/+2 until
      end of turn.` reaches the pump shape this way, with no separate cost
      regex needed.
    - A `TriggeredAbility` (CR 603.1) - its `effect`, i.e. everything after
      the trigger condition (and any intervening *if*, CR 603.4) has already
      been split off by this same classifier. Oliphaunt's "Whenever this
      creature attacks, another target creature you control gets +2/+0 and
      gains trample until end of turn." reaches the pump-and-keyword shape
      this way, with the leading "Whenever this creature attacks," gone
      before `machines/layers.py` ever sees the sentence - the trigger-side
      twin of the activation-cost split above. `machines/layers.py`'s battlefield
      sweep (`static_effects`) calls into the very same sentence for every
      permanent every turn, but always with an empty `targets` sequence, so a
      triggered ability's own effect body being readable here creates nothing
      there (CR 611.2 vs. 611.3: this is never a static ability's effect,
      only ever a resolving ability's) - it only produces a real effect when
      `create_continuous_effect_of_ability` resolves the ability itself and
      supplies its actual targets. See `machines/layers.py::_effect_sentences`
      for the other half of this.

    A `KeywordAbility` or `UnparsedAbility` line is skipped: neither is a
    continuous effect's own sentence.

    One line can hold more than one sentence (Violent Urge's pump and its
    *Delirium* clause are one `StaticAbility` line), so each classified line
    is split on its own top-level ". " boundaries before being returned.
    """
    sentences: list[str] = []
    for line in (text or "").split("\n"):
        chapter_line_read = False
        for ability in _parse_line(line, list(known_keywords or []), face=""):
            if isinstance(ability, TriggeredAbility) and ability.chapter is not None:
                # CR 714.2c: "I, II - [Effect]" is one effect printed once and
                # triggered at two thresholds - `_parse_chapter_line` returns
                # one ability per numeral, all carrying the same text. Read it
                # once, or a resolving chapter builds its effect once per
                # numeral on the line.
                if chapter_line_read:
                    continue
                chapter_line_read = True
            body: str | None = None
            if isinstance(ability, StaticAbility):
                body = ability.text
            elif not static_only and isinstance(ability, (ActivatedAbility, TriggeredAbility)):
                body = ability.effect
            if not body:
                continue
            for sentence in _split_top_level_sentences(body.strip()):
                sentence = sentence.strip()
                if sentence:
                    if card_name:
                        sentence = self_normalized_effect_text(
                            card_name, sentence, legendary=legendary
                        )
                        if legendary and not isinstance(ability, StaticAbility):
                            sentence = legendary_self_pronoun_normalized(sentence)
                    sentences.append(sentence)
    return sentences


def _split_top_level_sentences(body: str) -> list[str]:
    """Split `body` on its own top-level ". " boundaries - "top-level" now
    actually meaning it, rather than a bare `re.split(r"(?<=\\.)\\s+", ...)`
    that could not tell a sentence-ending period from one sitting inside a
    quoted granted ability (CR 113.10a).

    Way of the Deathbringer's own "Planeswalkers you control have '[-2]: You
    may sacrifice a creature. If you do, create a 4/4 green Beast creature
    token with trample.'" is *one* granted ability, not two: CR 608.2c's own
    instruction is one paragraph, but the quoted text it grants is free to
    contain as many sentences of its own as the granted ability needs, and
    those inner periods must never end the outer sentence around them - the
    bare regex split used to cut this exact line in half, at "creature.",
    leaving `_parse_static_layer_sentence` two unreadable fragments instead
    of the one whole grant it can actually read. Tracked with a simple quote-
    depth toggle rather than a full grammar, since CR 113.10a's own quoting
    is never nested (a granted ability's text cannot itself contain a further
    quoted ability grant in this pool).
    """
    sentences: list[str] = []
    start = 0
    in_quotes = False
    length = len(body)
    index = 0
    while index < length:
        char = body[index]
        if char == '"':
            in_quotes = not in_quotes
        elif char == "." and not in_quotes and (index + 1 >= length or body[index + 1].isspace()):
            sentences.append(body[start : index + 1])
            index += 1
            while index < length and body[index].isspace():
                index += 1
            start = index
            continue
        index += 1
    if start < length:
        sentences.append(body[start:])
    return sentences


# --------------------------------------------------------------------------
# Line parsing
# --------------------------------------------------------------------------

#: CR 714 Saga chapter markers: `I —`, `I, II —`, `III —`. The whole line, not
#: just the marker - `_parse_chapter_line` needs the effect text past the dash
#: too, unlike every other line-classifying regex in this module, which
#: matches only the leading words and leaves the rest to be split out
#: afterwards.
_CHAPTER_LINE = re.compile(
    r"^(?P<numerals>[IVXL]+(?:\s*,\s*[IVXL]+)*)\s*—\s*(?P<effect>.+)$", re.DOTALL
)

#: CR 107.15's Roman numeral, restricted to the additive-only range Sagas
#: print (I through V has covered every Saga to date; L is here only because
#: `_CHAPTER_LINE` already admits it and a genuine subtractive numeral - "IV"
#: - still has to read as 4, not 6, so the subtraction rule is implemented in
#: full rather than assumed away).
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50}


def _roman_to_int(numeral: str) -> int | None:
    """A CR 107.15 chapter numeral as a plain int, or `None` if it is not one."""
    total = 0
    previous = 0
    for char in reversed(numeral.upper()):
        value = _ROMAN_VALUES.get(char)
        if value is None:
            return None
        total += value if value >= previous else -value
        previous = max(previous, value)
    return total if total > 0 else None


#: A chapter's own name in front of its effect - Shiva, Warden of Ice's
#: "I, II — Mesmerize — Target creature can't be blocked this turn." CR 207.2d:
#: a flavor word has "no special rules meaning", and CR 207.2c says the same of
#: an ability word ("III — Domain — ..."), so the effect is the text after it.
#: "Choose one —" is a modal instruction, not a name, and is kept.
_CHAPTER_NAME = re.compile(r"^(?!Choose\b)[A-Z][^{}.:;—\n\"]{0,39}?\s+—\s+(?=\S)")


def _parse_chapter_line(text: str, common: dict) -> list[TriggeredAbility] | None:
    """CR 107.15a: "'{rN}—[Effect]' means 'When one or more lore counters are
    put onto this Saga, if the number of lore counters on it was less than N
    and became at least N, [effect].'"

    `I, II —` (History of Benalia's own first line) names the *same* effect at
    two different thresholds, not one ability that reads both numbers -
    CR 107.15a's paraphrase is written for a single `N`, so this returns one
    `TriggeredAbility` per numeral, each carrying its own `chapter` and the
    identical effect text. `machines/triggers.condition_matches` reads
    `chapter` against the lore count `Game.add_counters` reports on
    `TriggerEvent.LORE_COUNTERS_ADDED`, so two abilities off one line fire
    independently, exactly as two separately-numbered chapters would.
    """
    match = _CHAPTER_LINE.match(text)
    if match is None:
        return None
    chapters: list[int] = []
    for numeral in match.group("numerals").split(","):
        value = _roman_to_int(numeral.strip())
        if value is None:
            return None
        chapters.append(value)
    effect = _CHAPTER_NAME.sub("", match.group("effect").strip(), count=1).strip()
    if not effect:
        return None
    return [
        TriggeredAbility(
            **common,
            word=TriggerWord.WHEN,
            condition="one or more lore counters are put onto this saga",
            effect=effect,
            event=TriggerEvent.LORE_COUNTERS_ADDED,
            chapter=chapter,
        )
        for chapter in chapters
    ]


#: CR 207.2c ability word: a short capitalised phrase, then an em dash.
#: Capped at two words, which is how Oracle prints them - except "descend
#: 4"/"descend 8", whose second word is a bare number rather than another
#: capitalised word (CR 207.2c's own closed list has both spellings; see
#: `machines/effects.py`'s `_ABILITY_WORDS` for the full list and its
#: citation), so the second slot accepts one too - the same shape `machines/
#: layers.py`'s own `_ABILITY_WORD_RE` already reads for the static half of
#: this ability word. Without this, "Descend 4 —"/"Descend 8 —" never
#: stripped here, so a *triggered* descend clause (Coati Scavenger, Starving
#: Revenant) never started with "When"/"Whenever" once this far and fell
#: through to `StaticAbility` - harmless for the pump/grant shape, which
#: `machines/layers.py` reads straight off the card's raw oracle text and
#: never consults this module's own `Ability` classification, but fatal for
#: a triggered one, whose `abilities_triggered_by`/`intervening_if_holds`
#: only ever see a `TriggeredAbility`.
#:
#: An optional trailing "!"/"?" is the same story, one punctuation mark
#: over: Spider-Man, To the Rescue's own "No One Dies! — When Spider-Man
#: enters, ..." carries the exclamation point as part of its own printed
#: ability word (a Marvel Super Heroes convention this pool's older
#: ability words never used), and the plain [A-Za-z'\- ] class refused to
#: match past it at all - not merely leaving the mark in `text`, but
#: failing the whole match, so `ability_word` stayed unset and the
#: untouched "No One Dies! — When ..." line never started with
#: "When"/"Whenever" either, falling through to `StaticAbility` the
#: identical fatal way the digit case above already documents. The mark
#: is captured inside the ability-word group (dropped along with the rest
#: of it once `text` is sliced past `word_match.end()`), never left for
#: `_parse_triggered` to trip over.
#:
#: The bare "∞" alternative is CR 702.186a's own Infinity keyword: "∞ (the
#: mathematical symbol for infinity) is a keyword found on Infinity cards.
#: '∞' is followed by ability text." Not a capitalised word at all, so the
#: ordinary `[A-Z]...` branch never matched it - The Mind Stone's own
#: "∞ — At the beginning of your end step, ..." fell through to
#: `StaticAbility` with the whole line as its text, the same fate an
#: unstripped "Landfall —" would leave a triggered ability in. Stripped here
#: the identical way every other em-dash keyword/ability-word is, so the rest
#: reaches `_parse_triggered` as an ordinary "At the beginning of ..."
#: condition; CR 702.186b's own "as long as this permanent is harnessed, it
#: has [Ability]" gate is enforced elsewhere (`Game.characteristics_of`),
#: not by this classification.
#:
#: A flavor word may end in its own punctuation - The Unbeatable Squirrel
#: Girl's "Do You Like Squirrels? —" and "I LOVE Squirrels! —" (CR 207.2d:
#: flavor words have no rules meaning either) - so "?" and "!" are allowed.
_ABILITY_WORD = re.compile(r"^(∞|[A-Z][A-Za-z'\-?! ]{2,30}?(?: \d+)?[!?]?)\s+—\s+(?=\S)")

#: CR 603.1's three words, at the start of the line.
_TRIGGER = re.compile(r"^(When|Whenever|At)\b\s*", re.IGNORECASE)

#: CR 602.1b activation instructions, at the end of the effect: "If an
#: activated ability has any activation instructions, they appear last, after
#: the ability's effect." Each one opens either with "Activate" or with who may
#: activate it ("Any player may activate this ability", "Only your opponents
#: may activate this ability" - Knight of the Holy Nimbus), and the previous
#: sentence may end inside a quoted ability's own closing quote (Reef Roads'
#: `... 2 greater." Activate only as a sorcery.`), which is still a sentence
#: boundary.
_INSTRUCTIONS = re.compile(
    r"(?:^|(?<=\.\s)|(?<=\.[\"'”’]\s))"
    r"((?:(?:Activate|Any player may activate|Only your opponents may activate)\b[^.]*\.\s*)+)$"
)

_REMINDER = re.compile(r"\([^()]*\)")
_MANA_SHAPED = re.compile(r"^(?:\{[^{}]+\}\s*)+$|^\d+$|^X$")
#: The base effect is the first sentence; anything after it (an "instead"
#: clause, a spend restriction) is captured as `rest` rather than discarded.
#: Previously anchored to the *whole* effect with `[^.]+`, which cannot cross a
#: second sentence, so that anchoring made `mana=None` for every conditional
#: mana ability, and CR 605.1a's "could add mana" criterion failed, sending it
#: to the stack instead of resolving immediately (CR 605.3b).
_ADD = re.compile(r"^Add\s+(?P<effect>[^.]+)\.?\s*(?P<rest>.*)$", re.DOTALL)
_ONLY_SYMBOLS = re.compile(r"^(?:\{[^{}]+\}|\s)+$")
_PAY_LIFE = re.compile(r"^Pay\s+\S+\s+life$", re.IGNORECASE)


def printed_production(effect: str) -> str | None:
    """The mana an "Add ..." effect *says* it produces, exactly as printed.

    `"Add {C}{C}. Spend this mana only ..."` gives `"{C}{C}"`; Cavern of
    Souls's gives `"one mana of any color"`; Nykthos, Shrine to Nyx's gives
    `"an amount of mana of that color equal to your devotion to that color"`
    once its "Choose a color." preamble is stripped, the same way
    `parse_mana_abilities` strips it before reading the rest.

    Only the base "Add ..." sentence, never the board: this is the printed
    claim, not `ManaAbility.produces`/`resolve`'s answer for a particular
    board and a particular chosen colour. It exists for a caller describing
    an ability it is *offering* rather than resolving - `machines/legal_
    actions` fills `Action.produces` from it - where a count that depends on
    devotion or on a colour nobody has named yet would be a number that is
    wrong by the time the offer is taken up. `None` when the effect prints
    no "Add ..." phrase this can read.
    """
    match = _ADD.match(_CHOOSE_A_COLOR_PREAMBLE.sub("", effect.strip()))
    if match is None:
        return None
    return match.group("effect").strip() or None


def _faces(card: Card) -> list[tuple[str, str]]:
    """Every face's name and oracle text, front first, empty faces dropped."""
    faces = [(card.name, card.oracle_text or "")]
    faces += [(face.name, face.oracle_text or "") for face in card.card_faces or []]
    return [(name, text) for name, text in faces if text.strip()]


def _strip_reminder(line: str) -> tuple[str, str | None]:
    """Split a line into its rules text and its reminder text (CR 207.2a)."""
    found = _REMINDER.findall(line)
    stripped = _REMINDER.sub(" ", line)
    return re.sub(r"\s+", " ", stripped).strip(), (" ".join(found) if found else None)


def _blank_quotes(text: str) -> str:
    """Replace quoted spans with spaces, keeping every other index the same.

    Text in quotes is an ability being granted to something else, not one this
    card has (Chromatic Lantern). Blanking rather than deleting means an index
    found in the blanked string still points at the right place in the original.
    """
    out = list(text)
    inside = False
    for index, char in enumerate(out):
        if char == '"':
            inside = not inside
            out[index] = " "
        elif inside:
            out[index] = " "
    return "".join(out)


def _split_top_level(text: str, separator: str = ",") -> list[str]:
    """Split on a separator, ignoring any inside quotes or inside a number.

    A comma between two digits is a thousands separator, not a boundary
    between two things: The Millennium Calendar prints "When there are 1,000
    or more time counters on The Millennium Calendar, sacrifice it and each
    opponent loses 1,000 life." CR 603.1 templates a triggered ability as
    "[When/Whenever/At] [trigger condition or event], [effect]", and
    `_parse_triggered` cuts at the first top-level comma to find that
    boundary - which, unguarded, fell inside the number and left the
    condition as "there are 1".

    Written as a property of the separator's *surroundings* rather than of any
    card: any printed number carrying a group separator reads the same way.
    """
    blanked = _blank_quotes(text)
    parts: list[str] = []
    start = 0
    for index, char in enumerate(blanked):
        if char != separator:
            continue
        if separator == "," and _is_digit_group_separator(blanked, index):
            continue
        parts.append(text[start:index])
        start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _is_digit_group_separator(text: str, index: int) -> bool:
    """Whether the comma at `index` sits between two digits ("1,000")."""
    before = text[index - 1] if index else ""
    after = text[index + 1 : index + 2]
    return before.isdigit() and after.isdigit()


#: The cost keywords a genuinely new, top-level cost piece starts with, once
#: `_split_top_level` has cut a printed cost on every comma - used by
#: `_merge_disjunctive_sacrifice_cost` to tell "{1}, Sacrifice a creature"'s
#: two real pieces apart from "Sacrifice an artifact, creature, or land"'s
#: one piece that a comma-and-"or" type list also happens to contain a comma
#: in.
_COST_PIECE_START_WORDS = frozenset(
    {"sacrifice", "discard", "exile", "pay", "tap", "untap", "put", "remove", "exert", "reveal"}
)


def _looks_like_new_cost_piece(part: str) -> bool:
    stripped = part.strip()
    if not stripped or stripped.startswith("{"):
        return True
    first_word = stripped.split(maxsplit=1)[0].lower().rstrip(":")
    return first_word in _COST_PIECE_START_WORDS


def _merge_disjunctive_sacrifice_cost(parts: list[str]) -> list[str]:
    """Re-join `_split_top_level`'s comma cut where the comma was not between
    two costs but inside one cost's own disjunctive type list (CR 602.1a).

    "Sacrifice an artifact, creature, or land" (Greater Gargadon) is one cost,
    read by `cost.cost_component_for_phrase`'s own comma-and-"or" handling -
    but `_split_top_level` cuts on every top-level comma with no way to tell
    that one apart from "{1}, Sacrifice a creature"'s two real pieces, so by
    the time this runs it has already become three fragments: "Sacrifice an
    artifact", "creature", "or land". This walks forward from any fragment
    that opens with "sacrifice " (or "discard "/"exile "), swallowing
    fragments that do not themselves look like the start of a new cost, until
    one starts with "or " - the list's own final connective - and rejoins the
    whole run with commas. A fragment sequence with no such "or " is left
    exactly as split, so an ordinary multi-cost line is untouched.
    """
    merged: list[str] = []
    index = 0
    total = len(parts)
    while index < total:
        part = parts[index]
        lowered = part.strip().lower()
        if lowered.startswith(("sacrifice ", "discard ", "exile ")) and index + 1 < total:
            group = [part]
            cursor = index + 1
            closed = False
            while cursor < total:
                candidate = parts[cursor]
                if candidate.strip().lower().startswith("or "):
                    group.append(candidate)
                    cursor += 1
                    closed = True
                    break
                if _looks_like_new_cost_piece(candidate):
                    break
                group.append(candidate)
                cursor += 1
            if closed:
                merged.append(", ".join(group))
                index = cursor
                continue
        merged.append(part)
        index += 1
    return merged


def _parse_line(raw: str, keywords: list[str], face: str) -> list[Ability]:
    text, reminder = _strip_reminder(raw)
    if not text:
        # The line was nothing but reminder text - a Saga's lore-counter note,
        # for instance. Not an ability.
        return []

    common = {"raw": raw.strip(), "text": text, "reminder": reminder, "face": face}

    chapter_abilities = _parse_chapter_line(text, common)
    if chapter_abilities is not None:
        return list(chapter_abilities)

    keyword_abilities = _parse_keywords(text, keywords, common)
    if not keyword_abilities:
        # A keyword-cost line sharing its paragraph with a trailing "This
        # ability costs [N] less ..." sentence (CR 607.2h: two abilities, one
        # paragraph) fails `_parse_keywords`'s own "no full stop in the line"
        # rule on the *first* try, because the reduction sentence's full stop
        # is still in `text` - Warrior's Blades' and Dragonfire Blade's own
        # "Equip [N]. This ability costs [M] less ..." lines. Retried once
        # with that sentence split off; a retry that still finds no keyword
        # changes nothing; a retry with more than one line does not happen at
        # all, since `_parse_keywords` never yields more than one entry for a
        # single em-dash/parameter keyword-cost line to begin with.
        stripped, reduction = _split_off_trailing_cost_reduction(text)
        if reduction is not None:
            # `_split_off_trailing_cost_reduction` only ever removes a full
            # *sentence*, so the sentence before it keeps its own full stop -
            # "Equip {3}." - which `_parse_keywords` reads as disqualifying
            # all over again (a period anywhere bars a keyword line). The
            # bare param/cost form ("Equip {1}") never carries one to begin
            # with, so this strip only ever removes the one this split left.
            stripped = stripped.rstrip(".")
            retried = _parse_keywords(stripped, keywords, {**common, "text": stripped})
            if retried:
                keyword_abilities = [
                    ability.model_copy(update={"cost_reduction": reduction})
                    if isinstance(ability, KeywordAbility)
                    else ability
                    for ability in retried
                ]
    if keyword_abilities:
        return keyword_abilities

    ability_word: str | None = None
    word_match = _ABILITY_WORD.match(text)
    if word_match:
        ability_word = word_match.group(1)
        text = text[word_match.end() :]
        common = {**common, "ability_word": ability_word}

    triggered = _parse_triggered(text, common)
    if triggered is not None:
        return list(triggered)

    activated = _parse_activated(text, common)
    if activated is not None:
        return [activated]

    if text.endswith(".") or text.endswith('."'):
        # CR 604.1: static abilities "are written as statements".
        return [StaticAbility(**common)]

    return [UnparsedAbility(**common)]


#: `Keyword—cost.` and `Keyword N—cost.`, the em-dash form of a keyword cost.
#:
#: The em dash carries no space on either side, which is what tells this apart
#: from a CR 207.2c ability word (`Landfall — Whenever ...`, `Channel — {1}{G},
#: Discard this card: ...`). WOTC prints the ability word with spaces and the
#: keyword cost without, and the difference matters: `Channel` is a keyword on
#: the printing's own `keywords` list, so without the space rule its activated
#: ability would read as a keyword cost.
_KEYWORD_COST = re.compile(
    r"^(?P<keyword>[A-Z][A-Za-z'’-]*(?: [A-Za-z'’-]+)*?)"
    r"(?: (?P<count>\d+))?"
    r"—(?=\S)(?P<cost>[^:]+?)\.?$"
)


#: CR 702.6c: "Equip abilities may further restrict what creatures may be
#: chosen as legal targets. Such restrictions usually appear in the form
#: 'Equip [quality]' or 'Equip [quality] creature.'" - Steelclaw Lance's
#: "Equip Knight {1}", Blackblade Reforged's "Equip legendary creature {3}",
#: Mjolnir, Hammer of Thor's "Equip worthy {1}" (CR 700.16).
_EQUIP_WITH_QUALITY = re.compile(r"^Equip(?: (?P<quality>[^{}.:]+?))? (?P<cost>(?:\{[^}]+\})+)$")


def _parse_equip_with_quality(
    text: str, keywords: list[str], common: dict
) -> KeywordAbility | None:
    """`_EQUIP_WITH_QUALITY`'s line: the quality goes on `parameter`, the mana
    on `cost`. Also reads a plain "Equip {N}" whose printing's own Scryfall
    `keywords` list leaves Equip out (Mjolnir's lists only "Double") - CR
    702.6a defines the word whatever the list says. A plain equip line on a
    printing that does list Equip is left to the ordinary reader."""
    match = _EQUIP_WITH_QUALITY.match(text.strip())
    if match is None:
        return None
    quality = match.group("quality")
    if quality is None and any(keyword.lower() == "equip" for keyword in keywords):
        return None
    return KeywordAbility(
        **common,
        keyword="Equip",
        canonical="Equip",
        cost=match.group("cost"),
        cost_is_mana=True,
        parameter=quality.strip() if quality else None,
    )


def _parse_keywords(text: str, keywords: list[str], common: dict) -> list[Ability]:
    """Read a line that is nothing but keywords (CR 702).

    The printing's own Scryfall `keywords` list is the authority on what counts,
    so there is no keyword table here to fall out of date. A line with a full
    stop or a colon in it is never a keyword line, which keeps
    `Flying creatures you control get +1/+1.` from reading as `Flying`.

    The one exception is the em-dash cost form, `Evoke—Exile a black card from
    your hand.`, which is a keyword line *and* ends in a full stop. It is tried
    first, before the full stop disqualifies the line.
    """
    equip_quality = _parse_equip_with_quality(text, keywords, common)
    if equip_quality is not None:
        return [equip_quality]

    # Longest first, so `First strike` wins over any shorter prefix.
    known = sorted(keywords, key=len, reverse=True)

    em_dash = _parse_keyword_cost(text, known, common)
    if em_dash is not None:
        return [em_dash]

    parameterised = _parse_keyword_parameter(text, known, common)
    if parameterised is not None:
        return [parameterised]

    split = _split_keyword_line(text, known)
    if split is None:
        return []
    matched, unread = split
    if unread:
        # One token nobody knows discards the whole line, and deliberately so.
        # Extinguisher Battleship's "5+ | Flying, trample" is CR 721.2a's
        # station symbol - "As long as this permanent has N or more charge
        # counters on it, it has [abilities]" - so keeping the `trample` this
        # reader can match would grant unconditionally what the card grants
        # only at five counters. `unread_keyword_tokens` below is how a caller
        # sees that the line went unread instead of it being silent.
        return []
    return [KeywordAbility(**common, **match) for match in matched]


def _split_keyword_line(text: str, known: list[str]) -> tuple[list[dict], tuple[str, ...]] | None:
    """A comma line split into the keywords `known` matches and what it did not.

    None when the line is not that shape at all - a full stop or a colon means
    a sentence rather than CR 702.1's "only the name of the ability", which is
    what keeps `Flying creatures you control get +1/+1.` from reading as
    flying. `known` is expected sorted longest-first by the caller.
    """
    if "." in text or ":" in text:
        return None
    matched: list[dict] = []
    unread: list[str] = []
    for token in _split_top_level(text.replace(";", ","), ","):
        match = _match_keyword(token, known)
        if match is None:
            unread.append(token)
        else:
            matched.append(match)
    return matched, tuple(unread)


def unread_keyword_tokens(line: str, known: list[str]) -> tuple[str, ...]:
    """The tokens that stopped an otherwise keyword-shaped line being read.

    Empty when the line parsed whole, when it is not a keyword line at all, and
    when nothing on it matched - a line with no keyword on it is prose, not a
    keyword line with unread tokens, and reporting every sentence on the board
    would drown the real gap.

    Non-empty is the case worth recording: some of the line is CR 702.1
    keywords and some of it is not, so `_parse_keywords` discarded the keywords
    too. Whoever asked gets to say so rather than reading a permanent that has
    fewer abilities than the text in front of it says - see
    `machines/combat.py::KeywordLineNotice`.
    """
    text, reminder = _strip_reminder(line)
    if not text:
        return ()
    ranked = sorted(known, key=len, reverse=True)
    common = {"raw": line.strip(), "text": text, "reminder": reminder, "face": ""}
    if _parse_keywords(text, ranked, common):
        return ()
    split = _split_keyword_line(text, ranked)
    if split is None:
        return ()
    matched, unread = split
    return unread if matched else ()


#: `Keyword X, where X is ...` - Firebending Student's own "Firebending X,
#: where X is this creature's power." CR 702.189a templates the keyword as
#: "Firebending N", and a card may print the N as a self-defined X rather than
#: a literal number.
_KEYWORD_SELF_DEFINED_X = re.compile(
    r"^(?P<keyword>[A-Za-z' ]+?) (?P<parameter>X, where X is .+?)\.?$", re.IGNORECASE
)


def _parse_keyword_parameter(text: str, known: list[str], common: dict) -> KeywordAbility | None:
    """Read `Keyword X, where X is ...`, a keyword whose numeric parameter the
    card defines in its own words rather than printing as a digit.

    Firebending Student's "Firebending X, where X is this creature's power." is
    the whole of this shape in the pool. Without it the line falls through
    `_parse_keywords` twice over - the trailing full stop disqualifies it as a
    keyword line, and the comma inside would have split it into two tokens of
    which the second matches no keyword anyway - and lands as a
    `StaticAbility`, which is the wrong category for what CR 702.189a says is a
    *triggered* ability.

    The parameter is kept verbatim on `KeywordAbility.parameter` and `count`
    stays None: **CR 608.2h** is why the number is not resolved here. "If an
    effect requires information from the game (such as the number of creatures
    on the battlefield), the answer is determined only once, when the effect is
    applied" - so X is this creature's power *as the firebending ability
    resolves*, not as the line is parsed, and a parser that baked in a number
    would be answering the question at the wrong moment.

    The keyword still has to be on the printing's own Scryfall `keywords` list,
    the same authority `_parse_keywords` and `_parse_keyword_cost` use.
    """
    match = _KEYWORD_SELF_DEFINED_X.match(text.strip())
    if match is None:
        return None
    printed = match.group("keyword").strip()
    canonical = next((k for k in known if k.lower() == printed.lower()), None)
    if canonical is None:
        return None
    return KeywordAbility(
        **common,
        keyword=printed,
        canonical=canonical,
        parameter=match.group("parameter").strip(),
    )


def _parse_keyword_cost(text: str, known: list[str], common: dict) -> KeywordAbility | None:
    """Read `Keyword—cost.`, the em-dash form of a keyword's cost.

    Four of the shapes in the test pool use it - `Evoke—Exile a black card from
    your hand.`, `Cycling—Pay 2 life.`, `Escalate—Discard a card.`,
    `Flashback—Sacrifice a Mountain.` - and one puts a number in front of the
    dash, `Suspend 3—{2}{B}{B}`. Before this, every one of them fell through to
    `StaticAbility`, which is why evoke did nothing.

    The keyword still has to be on the printing's own Scryfall `keywords` list,
    so there is no keyword table here either.
    """
    match = _KEYWORD_COST.match(text)
    if match is None:
        return None

    printed = match.group("keyword")
    canonical = next((k for k in known if k.lower() == printed.lower()), None)
    if canonical is None:
        return None

    cost = match.group("cost").strip()
    count = match.group("count")
    return KeywordAbility(
        **common,
        keyword=printed,
        canonical=canonical,
        cost=cost,
        count=int(count) if count is not None else None,
        cost_is_mana=bool(_ONLY_SYMBOLS.match(cost)),
        em_dash=True,
    )


def _match_keyword(token: str, known: list[str]) -> dict | None:
    for keyword in known:
        lowered = token.lower()
        if not lowered.startswith(keyword.lower()):
            continue
        rest = token[len(keyword) :].strip()
        # `Cycling—Pay 2 life` puts a non-mana cost after an em dash.
        rest = rest.removeprefix("—").strip()
        if not rest:
            return {"keyword": token, "canonical": keyword}
        if _MANA_SHAPED.match(rest):
            return {
                "keyword": token[: len(keyword)],
                "canonical": keyword,
                "cost": rest,
                "count": int(rest) if rest.isdigit() else None,
                "cost_is_mana": bool(_ONLY_SYMBOLS.match(rest)),
            }
        # Only accept a wordy remainder when a separator justified it, so
        # `Flying creatures` is rejected but `Protection from red` is not.
        if token[len(keyword) : len(keyword) + 1] in ("", " ", "—"):
            return {"keyword": token[: len(keyword)], "canonical": keyword, "parameter": rest}
    return None


#: The closing phrase of Alania, Divergent Storm's own intervening *if* shape
#: - "if it's the first instant spell, the first sorcery spell, or the first
#: Otter spell other than Alania you've cast this turn" - captured whole,
#: comma-separated interior and all, up to and including the comma that
#: follows "cast this turn". `machines/triggers._FIRST_SPELL_THIS_TURN` is
#: what actually reads the captured clause; this only finds where it ends.
#: Never across a sentence: Hurkyl, Master Wizard's "if you've cast a
#: noncreature spell this turn, reveal the top five cards of your library.
#: For each card type among noncreature spells you've cast this turn, ..."
#: ends its clause at the first comma, and a lazy `.+?` ran on to the second
#: sentence's "you've cast this turn," and swallowed the effect whole.
_INTERVENING_IF_CAST_THIS_TURN_BOUNDARY = re.compile(
    r"if\s(?P<clause>[^.]+?\byou(?:'ve| have) cast this turn)\s*,\s*", re.IGNORECASE
)

#: "Whenever you cast an artifact, instant, or sorcery spell, `<effect>`."
#: (Jin-Gitaxias, Progress Tyrant) - a comma-separated type list *inside* the
#: trigger condition itself, ahead of the comma that actually separates the
#: condition from the effect (CR 603.1's own "[trigger condition], [effect]"
#: template). `_split_top_level`'s naive first-top-level-comma cut has no way
#: to tell "artifact," (mid-list) from the real boundary, and sliced this
#: condition down to "you cast an artifact", leaving "instant, or sorcery
#: spell" sitting in front of the effect text instead - the same class of
#: defect `_INTERVENING_IF_CAST_THIS_TURN_BOUNDARY` above already exists to
#: fix on the intervening-*if* side. Captured whole, including the trailing
#: comma, so `_parse_triggered` can cut there directly instead of re-running
#: the naive split over ground this regex has already covered.
_CAST_TYPE_LIST_CONDITION_BOUNDARY = re.compile(
    r"^(?P<condition>(?:you|target player|each player|an? opponent|a player) "
    r"casts? an? [a-z]+(?:,\s*[a-z]+)*(?:,)?\s+or\s+[a-z]+ spells?)\s*,\s*",
    re.IGNORECASE,
)

#: Immolation Shaman's "Whenever an opponent activates an ability of an
#: artifact, creature, or land that isn't a mana ability, `<effect>`." - the
#: same comma-separated type list inside the condition that
#: `_CAST_TYPE_LIST_CONDITION_BOUNDARY` reads for a cast, here naming the
#: source of a CR 602.2 activation, with CR 605.1a's "that isn't a mana
#: ability" closing it. `machines/triggers._ABILITY_ACTIVATED_CONDITION`
#: reads the captured condition. Harsh Mentor prints the same list with
#: "on the battlefield" after it and moves the mana-ability test into its
#: intervening "if" ("..., if it isn't a mana ability, ..."), which the list's
#: own commas used to cut in half.
_ACTIVATES_TYPE_LIST_CONDITION_BOUNDARY = re.compile(
    r"^(?P<condition>(?:you|a player|an? opponent) activates? an ability of "
    r"an? [a-z]+(?:,\s*(?:an? )?[a-z]+)*(?:,)?\s+or\s+(?:an? )?[a-z]+"
    r"(?: on the battlefield)?(?: that isn't a mana ability)?)\s*,\s*",
    re.IGNORECASE,
)

#: Avatar Aang's own "Whenever you waterbend, earthbend, firebend, or
#: airbend, draw a card." - the same "list of verbs joined by a final 'or',
#: itself followed by the ordinary trigger comma" shape
#: `_CAST_TYPE_LIST_CONDITION_BOUNDARY` above reads for a cast condition's
#: type list, read here for CR 701.67c's own bending verbs (and any subset
#: or order of them, since only "waterbend" has a rule number that reaches
#: this engine - `machines/triggers.py`'s own `_BENDING_CONDITION` is what
#: actually classifies the captured condition, this only finds where it
#: ends). Without this, `_split_top_level`'s bare comma split below would cut
#: the condition off after "you waterbend" and read "earthbend" as the whole
#: of the trigger's effect.
_BENDING_LIST_CONDITION_BOUNDARY = re.compile(
    r"^(?P<condition>you (?:waterbend|earthbend|firebend|airbend)"
    r"(?:,\s*(?:waterbend|earthbend|firebend|airbend))*(?:,)?"
    r"\s+or\s+(?:waterbend|earthbend|firebend|airbend))\s*,\s*",
    re.IGNORECASE,
)

#: The Great Goblin's own "Whenever you put one or more counters on a
#: Goblin, Orc, or Army you control, `<effect>`." - a comma-separated
#: subtype list *inside* the trigger condition itself, the identical class of
#: defect `_CAST_TYPE_LIST_CONDITION_BOUNDARY` above exists to fix for a cast
#: condition's own type list: `_split_top_level`'s naive first-top-level-comma
#: cut would slice this condition down to "you put one or more counters on a
#: Goblin", leaving "Orc, or Army you control" sitting in front of the effect
#: text instead of behind it. Not case-insensitive, on purpose - Oracle's own
#: subtype capitalisation (`[A-Z]`) is what tells a subtype apart from a
#: card-type word here, the same discriminator `machines/triggers.
#: _DYING_SUBTYPE`/`_ENTERING_SUBTYPE` already rely on for their own subjects.
#: `machines/triggers._COUNTERS_PUT_ON_DESCRIPTION_CONDITION` reads the
#: captured condition.
_COUNTERS_PUT_SUBTYPE_LIST_CONDITION_BOUNDARY = re.compile(
    r"^(?P<condition>you put one or more counters on an? "
    r"[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,)?\s+or\s+[A-Z][A-Za-z]*"
    r" you control)\s*,\s*"
)

#: The Great Goblin's own second trigger, "Whenever another Goblin, Orc, or
#: Army you control dies, `<effect>`." - the identical class of comma-list
#: boundary defect, for CR 700.4's own dies condition rather than a
#: counters-put one. `machines/triggers._DYING_SUBTYPE` reads the captured
#: condition (already widened to this same subtype-list shape).
_DIES_SUBTYPE_LIST_CONDITION_BOUNDARY = re.compile(
    r"^(?P<condition>(?:an?|another|one or more) (?:nontoken )?"
    r"[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,)?\s+or\s+[A-Z][A-Za-z]*"
    r"(?: you control| an opponent controls)? (?:dies|die))\s*,\s*"
)

#: CR 603.2h's own trailing restriction, in either the rule's own wording
#: ("Do this only once each turn") or Caretaker's Talent's paraphrase ("This
#: ability triggers only once each turn") - both always the ability's last
#: sentence. The named `quote` group is Kwia Vigorbloom's own shape: "... with
#: '{T}, Sacrifice this token: Add three mana of any one color.' This ability
#: triggers only once each turn." - the quoted token ability's own closing
#: quote mark sits between its sentence-ending period and the trailer,
#: straight or curly, so the bare `\.\s*` this used to be would never match
#: and the whole restriction sentence stayed stuck in `effect`, taking the
#: entire clause down as unreadable (CR 608.2c) instead of being read as
#: CR 603.2h's own once-per-turn limiter. `_strip_once_per_turn_trailer`
#: below restores that closing quote mark rather than deleting it along with
#: the trailer - it is the quoted ability's own punctuation, not the
#: trailer's.
_ONCE_PER_TURN_TRAILER = re.compile(
    r"\.(?P<quote>[\"'“”‘’]?)\s*"
    r"(?:do this|this ability triggers) only once each turn\.?\s*$",
    re.IGNORECASE,
)


def _strip_once_per_turn_trailer(text: str) -> str:
    """`text` with `_ONCE_PER_TURN_TRAILER` cut off, its own closing quote
    mark (if any) put back - see that pattern's own docstring."""
    return _ONCE_PER_TURN_TRAILER.sub(lambda m: "." + m.group("quote"), text)


#: Ruby, Daring Tracker's shape: "Whenever Ruby attacks **while** you control
#: a creature with power 4 or greater, Ruby gets +2/+2 until end of turn." -
#: CR 603.4's intervening *if* clause, worded with "while" in place of "if"
#: and folded into the trigger condition itself rather than sitting after the
#: comma the way Persist's "if it had no -1/-1 counters on it" does. Split off
#: here, before the trigger-event words are ever read, so `condition` carries
#: only "Ruby attacks" - `_trigger_event`/`condition_matches` never see the
#: "while ..." tail - and `intervening_if` carries the clause itself, checked
#: by the same `machines/triggers.intervening_if_holds` (CR 603.4, 608.2a)
#: every other intervening *if* goes through. Matched only ahead of the first
#: top-level comma, so an effect that happens to use the word "while" past
#: that point (none in the pool) is left alone.
_CONDITION_WHILE_CLAUSE = re.compile(r"\bwhile\b", re.IGNORECASE)

#: "... for the first time each turn" - CR 603.2h's own once-per-turn
#: limiter, printed as part of the trigger **condition** itself rather than
#: as `_ONCE_PER_TURN_TRAILER`'s trailing sentence on the ability's effect -
#: Desert Were-Worm's own "Whenever you attack with creatures with total
#: power 12 or greater for the first time each turn, ...". Stripped off the
#: condition text before `_trigger_event`/`machines.triggers.condition_
#: matches` ever see it, the same "read once, tag the ability" treatment
#: `_strip_once_per_turn_trailer` already gives the trailing form -
#: `machines/triggers.triggers_for` reads the resulting `once_per_turn` flag
#: identically either way, keyed by the ability's whole printed text.
_CONDITION_FOR_THE_FIRST_TIME_EACH_TURN_RE = re.compile(
    r"\s+for the first time each turn$", re.IGNORECASE
)


def _strip_condition_once_per_turn_trailer(condition: str) -> tuple[str, bool]:
    """`condition` with `_CONDITION_FOR_THE_FIRST_TIME_EACH_TURN_RE` cut off,
    and whether it was present."""
    stripped_condition = condition.strip()
    stripped = _CONDITION_FOR_THE_FIRST_TIME_EACH_TURN_RE.sub("", stripped_condition)
    return stripped, stripped != stripped_condition


#: CR 603.1b: "A triggered ability may have more than one trigger condition".
#: The printed joint is "[condition] and when[ever] [condition]" ahead of the
#: one comma that starts the shared effect - Cityscape Leveler's "When you cast
#: this spell and whenever this creature attacks", Eldrazi Repurposer's "When
#: you cast this spell and when this creature dies", Voice of Resurgence's
#: "Whenever an opponent casts a spell during your turn and when this creature
#: dies". Only "when"/"whenever" are joints: "and at" also opens ordinary
#: condition text ("... and at least ...").
_COMPOUND_CONDITION_JOINT = re.compile(r"\s+and\s+(when(?:ever)?)\s+", re.IGNORECASE)


def _split_compound_condition(word: TriggerWord, condition: str) -> list[tuple[TriggerWord, str]]:
    """Each trigger condition of a CR 603.1b compound, with its own leading
    word - one entry, unchanged, for an ordinary single condition."""
    halves: list[tuple[TriggerWord, str]] = []
    start = 0
    for joint in _COMPOUND_CONDITION_JOINT.finditer(condition):
        halves.append((word, condition[start : joint.start()].strip()))
        word = TriggerWord(joint.group(1).lower())
        start = joint.end()
    halves.append((word, condition[start:].strip()))
    if any(not half for _, half in halves):
        return [(halves[0][0], condition)]
    return halves


#: "this `<noun>` transforms into " - CR 701.27e's trigger condition, whose
#: named face is matched whole by `_transforms_into_face_boundary`.
_TRANSFORMS_INTO_LEAD = re.compile(r"^this [a-z]+ transforms into ", re.IGNORECASE)


def _self_named_condition_boundary(body: str, face: str) -> tuple[str, str] | None:
    """(condition, effect) when `body` opens with the card's own full printed
    name (CR 201.5) as its plain trigger subject - "When `<Name>` `<verb>`,
    `<effect>`." - and that printed name itself carries an internal comma,
    the way Tom, Bert, and William's own three-name legend does ("Tom, Bert,
    and William"). `_split_top_level`'s naive first-top-level-comma cut has
    no way to tell the name's own internal comma apart from the real
    condition/effect boundary, and sliced the condition down to "Tom",
    leaving "Bert, and William die, if they were a creature, ..." sitting in
    the effect instead - the same class of defect `_transforms_into_face_
    boundary` just below already exists to fix for a different fixed phrase
    (CR 701.27e's "transforms into `<face>`").

    `None` for the overwhelmingly common case: a printed name with no
    internal comma is untouched by this at all (`_split_top_level`'s own cut
    already reads it correctly), and a `body` that does not open with the
    name literally is left to the ordinary split too - self-reference by a
    shortened name or a pronoun (CR 201.5c, `_self_referential`) is read
    downstream of `condition`, not here.
    """
    if not face or "," not in face or not body.startswith(face):
        return None
    rest = body[len(face) :]
    parts = _split_top_level(rest)
    if len(parts) < 2:
        return None
    return f"{face} {parts[0]}", ", ".join(parts[1:])


def _transforms_into_face_boundary(body: str, face: str) -> tuple[str, str] | None:
    """`(condition, effect)` for "this `<noun>` transforms into `<face>`,
    `<effect>`" when `<face>` is the name of the face the ability is printed
    on (Avacyn, the Purifier's own "When this creature transforms into
    Avacyn, the Purifier, it deals 3 damage ..."), else `None`."""
    lead = _TRANSFORMS_INTO_LEAD.match(body)
    if lead is None or not face:
        return None
    named = body[lead.end() :]
    if not named.lower().startswith(f"{face.lower()},"):
        return None
    end = lead.end() + len(face)
    return body[:end].strip(), body[end + 1 :].strip()


def _parse_triggered(text: str, common: dict) -> list[TriggeredAbility] | None:
    """The triggered ability `text` prints, as one `TriggeredAbility` per
    trigger condition (CR 603.1b) - every entry shares the printed `text`,
    the intervening *if*, and the effect, so a compound triggers the one
    effect on each of its events, and each condition keeps its own zone
    (CR 113.6k: "Other trigger conditions of the same triggered ability may
    function in different zones")."""
    match = _TRIGGER.match(text)
    if match is None:
        return None

    word = TriggerWord(match.group(1).lower())
    body = text[match.end() :]

    type_list_boundary = _CAST_TYPE_LIST_CONDITION_BOUNDARY.match(
        body
    ) or _ACTIVATES_TYPE_LIST_CONDITION_BOUNDARY.match(body)
    bending_list_boundary = (
        None if type_list_boundary is not None else _BENDING_LIST_CONDITION_BOUNDARY.match(body)
    )
    subtype_list_boundary = (
        None
        if type_list_boundary is not None or bending_list_boundary is not None
        else (
            _COUNTERS_PUT_SUBTYPE_LIST_CONDITION_BOUNDARY.match(body)
            or _DIES_SUBTYPE_LIST_CONDITION_BOUNDARY.match(body)
        )
    )
    self_named_boundary = _self_named_condition_boundary(body, common.get("face") or "")
    transforms_into_boundary = _transforms_into_face_boundary(body, common.get("face") or "")
    if self_named_boundary is not None:
        condition, rest = self_named_boundary
        if not rest:
            return None
    elif transforms_into_boundary is not None:
        # CR 701.27e's "transforms into `<face>`": the face's own name may
        # hold a comma (Avacyn, the Purifier), which the plain top-level
        # comma split below would cut through.
        condition, rest = transforms_into_boundary
        if not rest:
            return None
    elif type_list_boundary is not None:
        condition = type_list_boundary.group("condition")
        rest = body[type_list_boundary.end() :].strip()
        if not rest:
            return None
    elif bending_list_boundary is not None:
        condition = bending_list_boundary.group("condition")
        rest = body[bending_list_boundary.end() :].strip()
        if not rest:
            return None
    elif subtype_list_boundary is not None:
        condition = subtype_list_boundary.group("condition")
        rest = body[subtype_list_boundary.end() :].strip()
        if not rest:
            return None
    else:
        parts = _split_top_level(body)
        if len(parts) < 2:
            # `[Trigger condition], [effect]` needs a comma to separate them.
            return None

        condition, rest = parts[0], ", ".join(parts[1:])

    condition, condition_once_per_turn = _strip_condition_once_per_turn_trailer(condition)

    # The effect text as printed, before any comma-side "if" is lifted out:
    # a condition carrying its own "while" clause keeps this one (see below).
    printed_rest = rest
    comma_if_unreadable = False
    intervening_if: str | None = None
    if rest.lower().startswith("if "):
        # `_FIRST_SPELL_THIS_TURN_WITH_BOUNDARY` first: Alania, Divergent
        # Storm's own intervening *if* is itself a comma-separated list -
        # "if it's the first instant spell, the first sorcery spell, or the
        # first Otter spell other than Alania you've cast this turn" - so
        # cutting at the *first* top-level comma (the plain path below) would
        # slice the clause in half and leave "the first sorcery spell, ..."
        # sitting in front of the effect text instead. This shape's own
        # closing phrase, "you('ve| have) cast this turn", is the boundary a
        # bare comma-split cannot see, so it is matched for directly and only
        # falls back to the plain single-segment reading when it is absent.
        boundary = _INTERVENING_IF_CAST_THIS_TURN_BOUNDARY.match(rest)
        if boundary is not None:
            intervening_if = boundary.group("clause").strip()
            rest = rest[boundary.end() :].strip()
            comma_if_unreadable = not rest
        else:
            clause_parts = _split_top_level(rest)
            if len(clause_parts) < 2:
                comma_if_unreadable = True
            else:
                end = _intervening_if_end(clause_parts)
                intervening_if = ", ".join(part.strip() for part in clause_parts[:end])[
                    len("if ") :
                ].strip()
                rest = ", ".join(clause_parts[end:])

    once_per_turn = condition_once_per_turn
    stripped = _strip_once_per_turn_trailer(rest).strip()
    if stripped != rest.strip():
        once_per_turn = True
        rest = stripped
        printed_rest = _strip_once_per_turn_trailer(printed_rest).strip()

    abilities: list[TriggeredAbility] = []
    for half_word, half in _split_compound_condition(word, condition):
        # The "while" clause belongs to the one condition it is printed in
        # (Autarch Mammoth's "whenever it attacks while saddled") and is that
        # condition's intervening *if* (CR 603.4); a condition with one keeps
        # the printed effect text, comma-side "if" and all, exactly as the
        # parser read it before compound splitting (no printing carries both
        # yet). Every other condition takes the comma-side "if".
        half_if, half_effect = intervening_if, rest
        event_qualifier: str | None = None
        while_match = _CONDITION_WHILE_CLAUSE.search(half)
        if while_match is not None and _EVENT_QUALIFIER.match(half[while_match.end() :].strip()):
            # "... while casting a spell with emerge" (Foul Emissary), "...
            # while scrying" (The Temporal Anchor), "... while you're
            # activating a craft ability" (Market Gnome): a "while" followed
            # by what a player is *doing* says how the trigger event
            # happened - part of the event itself (CR 603.2), not a state
            # CR 603.4 checks again as the ability resolves (by then the
            # casting is long over). The bare event is the condition, and
            # the qualifier is asked of that event as it happens
            # (`TriggeredAbility.event_qualifier`).
            if comma_if_unreadable:
                return None
            event_qualifier = half[while_match.end() :].strip()
            half = half[: while_match.start()].strip()
        elif while_match is not None:
            half_if = half[while_match.end() :].strip()
            if half_if.lower() == "saddled":
                # CR 702.171b: "saddled" is a designation of the permanent,
                # asked of the attacking permanent itself - "it's saddled",
                # the object-state clause `machines/conditions/objects.py`
                # reads, rather than the bare word.
                half_if = "it's saddled"
            half = half[: while_match.start()].strip()
            half_effect = printed_rest
        elif comma_if_unreadable:
            return None
        abilities.append(
            TriggeredAbility(
                **common,
                word=half_word,
                condition=half,
                intervening_if=half_if,
                effect=half_effect,
                event=_trigger_event(half),
                once_per_turn=once_per_turn,
                event_qualifier=event_qualifier,
            )
        )
    return abilities


#: What follows "while" when it describes how the trigger event happened
#: rather than a state of the game: an action in progress, "while casting
#: ...", "while scrying", "while you're activating ...".
_EVENT_QUALIFIER = re.compile(r"^(?:you(?:'re| are) )?[a-z]+ing\b", re.IGNORECASE)


#: A comma inside an intervening "if" that continues a list rather than ending
#: the clause: the next item of a serial list - a single capitalized word
#: ("a Giant, Wizard, or spell you controlled ...", Aegar, the Freezing
#: Flame) or the list's closing "or"/"and" item - or a second "non-" qualifier
#: after a first ("two or more nonland, nontoken permanents", Chrome
#: Replicator). CR 603.4's clause ends at the comma before the effect, which
#: is none of these.
_IF_LIST_CONTINUATION = re.compile(r"^(?:(?:or|and|and/or)\s|[A-Z][\w'-]*$)")
_IF_QUALIFIER_TAIL = re.compile(r"\bnon-?[a-z]+$", re.IGNORECASE)
_IF_QUALIFIER_LEAD = re.compile(r"^non-?[a-z]+\s", re.IGNORECASE)


def _intervening_if_end(parts: list[str]) -> int:
    """How many of an "if ..., effect" text's top-level comma parts belong to
    the intervening "if" clause - at least one, and never the last, which is
    the effect (see `_IF_LIST_CONTINUATION`)."""
    end = 1
    while end < len(parts) - 1:
        previous, following = parts[end - 1].strip(), parts[end].strip()
        if _IF_LIST_CONTINUATION.match(following) or (
            _IF_QUALIFIER_TAIL.search(previous) and _IF_QUALIFIER_LEAD.match(following)
        ):
            end += 1
            continue
        break
    return end


def _trigger_event(condition: str) -> TriggerEvent | None:
    lowered = condition.lower()
    if lowered.startswith("the beginning of"):
        return TriggerEvent.BEGINNING_OF_STEP
    # CR 511.2: "Abilities that trigger 'at end of combat' trigger as the end
    # of combat step begins" - Kytheon's "At end of combat" and Sidequest:
    # Play Blitzball's "At the end of combat on your turn".
    if re.match(r"^(?:the )?end of combat\b", lowered):
        return TriggerEvent.BEGINNING_OF_STEP
    if _TRANSFORMS_INTO_LEAD.match(lowered):
        return TriggerEvent.TRANSFORMS
    # Before the "becomes blocked" test below, which would otherwise claim
    # "becomes the target of ..." for CR 509.
    if "becomes the target" in lowered:
        return TriggerEvent.BECOMES_TARGET
    # CR 702.37e/708.8. Checked ahead of "enters" below only for grouping -
    # "turned face up" contains no "enter" at all, so the two never compete.
    if "turned face up" in lowered:
        return TriggerEvent.TURNED_FACE_UP
    # CR 701.9a. Checked ahead of "cast"/"sacrific" below, neither of which
    # this phrase contains, again only for grouping with the other
    # special-action-shaped conditions above. "another card" is CR 702.29d's
    # "cycles or discards another card" (Curator of Mysteries, Archfiend of
    # Ifnir): cycling's cost is itself a discard (CR 702.29a), so the one
    # discard event is the whole condition and a cycled card counts once.
    if re.search(r"\bdiscards? (?:a card|another card|one or more cards|this card)\b", lowered):
        return TriggerEvent.DISCARDS_A_CARD
    # CR 701.22a/701.25a, watched together - see `TriggerEvent.SCRY_OR_
    # SURVEIL`'s own docstring. Checked ahead of nothing in particular; the
    # word "scry"/"surveil" never collides with another condition shape.
    if re.search(r"\b(?:scry|surveil)s?\b", lowered):
        return TriggerEvent.SCRY_OR_SURVEIL
    # CR 606.2. "you activate" (Ajani Unrelenting) and "an opponent
    # activates" (Gideon the Oathless) inflect the verb differently, so both
    # forms are read. Checked ahead of nothing else in this pool - CR 602.2
    # targeting triggers are ward's/Loki's own "becomes the target" shape,
    # matched separately above.
    if re.search(r"\bactivates? a loyalty ability\b", lowered):
        return TriggerEvent.LOYALTY_ABILITY_ACTIVATED
    # "enter" (no s) is the plural-subject form printed on "Whenever one or
    # more tokens you control enter" (Caretaker's Talent) - the same
    # singular/plural split `\battacks?\b` already reads for "attacks" versus
    # "you attack".
    if re.search(r"\benters?\b", lowered):
        return TriggerEvent.ENTERS_THE_BATTLEFIELD
    # CR 603.6c: the generic "leaves the battlefield" condition (Thought-Knot
    # Seer), ahead of `dies`'s own narrower "put into a graveyard from the
    # battlefield" phrasing below - a condition naming a graveyard
    # specifically is `DIES`, not this.
    if "leaves the battlefield" in lowered:
        return TriggerEvent.LEAVES_THE_BATTLEFIELD
    # CR 406.2's exile, from the battlefield specifically ("When this creature
    # is exiled from the battlefield", Market Gnome) - the move
    # `Game.exile_permanent` raises as its own event.
    if re.search(r"\b(?:is|are) exiled from the battlefield\b", lowered):
        return TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE
    # CR 701.22a's choice, as The Temporal Anchor prints it.
    if re.search(
        r"\bchooses? to put one or more cards on the bottom of (?:your|their) library\b", lowered
    ):
        return TriggerEvent.LIBRARY_BOTTOM_CHOSEN
    # CR 700.4: "dies" means "is put into a graveyard from the battlefield" -
    # Flagstones of Trokair spells that phrase out instead of saying "dies",
    # and the two are the same event by definition. "die" (no s) is the
    # plural form printed on "one or more other Cats you control die".
    if (
        re.search(r"\bdi(?:es|e)\b", lowered)
        or "put into a graveyard from the battlefield" in lowered
    ):
        return TriggerEvent.DIES
    # "attack" (no s) is the plural-subject form printed on "Whenever you
    # attack" (CR 508.3d) - the player attacks, not "a creature".
    if re.search(r"\battacks?\b", lowered):
        return TriggerEvent.ATTACKS
    # CR 106.12, 106.12a: "tapped for mana" / "tap [a permanent] for mana".
    # Checked ahead of the generic "becomes tapped" match below, which is a
    # different event (CR 701.26a).
    if re.search(r"\btap\w* .*for mana\b", lowered):
        return TriggerEvent.TAPPED_FOR_MANA
    if re.search(r"\bblocks\b|\bbecomes blocked\b", lowered):
        return TriggerEvent.BLOCKS
    # CR 606.3. "you activate a loyalty ability" (Ajani Unrelenting) / "an
    # opponent activates a loyalty ability" (Gideon the Oathless) - checked
    # ahead of no other verb here, since "activate" appears in no other
    # condition shape this reads.
    if re.search(r"\bactivates? a loyalty ability\b", lowered):
        return TriggerEvent.LOYALTY_ABILITY_ACTIVATED
    # CR 601.1a's "play" spelled out - "you play a land or cast a spell"
    # (Shadow of the Goblin) watches two events, a land played and a spell
    # cast, so it is left to `machines/triggers._unread_trigger_events`,
    # ahead of the plain "cast" reading below, which would demand a land
    # *spell* no cast ever is.
    if re.search(r"\bplays? a land or casts? a spell\b", lowered):
        return None
    if re.search(r"\bcasts?\b", lowered):
        return TriggerEvent.CAST_SPELL
    # "Whenever you draw a card" / "Whenever an opponent draws a card" - the
    # count comes from the number of individual draws (CR 121.2), never from
    # the condition. "Draw two cards" as an effect never reaches here: the
    # condition is only the text before the first top-level comma.
    if re.search(r"\bdraw(?:s)? a card\b", lowered):
        return TriggerEvent.DRAWS_A_CARD
    # "Whenever you sacrifice a creature" (Dragon Appeasement). The check runs
    # after `dies`, so "When this creature dies" is never mistaken for one.
    if re.search(r"\bsacrific\w*", lowered):
        return TriggerEvent.IS_SACRIFICED
    if re.search(r"\bgain(?:s)? life\b", lowered):
        return TriggerEvent.GAINS_LIFE
    # "Whenever Ragavan deals combat damage to a player" (the dealer) and
    # "Whenever this creature is dealt damage"/"one or more opponents are
    # dealt noncombat damage" (the recipient, CR 120.1's passive voice) are
    # both this one event - the matcher reads "combat"/"noncombat" and
    # active/passive voice off the condition, `GameEvent.combat` and
    # `target_id` vs `subject_id` off the event. `machines/triggers.
    # condition_matches`'s own DEALS_DAMAGE branch reads the same words
    # ("is dealt" vs "deals") to pick `GameEvent.target_id`/`player` over
    # `subject_id`.
    if re.search(
        r"\bdeals (?:combat )?damage\b|\b(?:is|are) dealt (?:combat |noncombat )?damage\b", lowered
    ):
        return TriggerEvent.DEALS_DAMAGE
    # CR 701.37a: "When [this creature] becomes monstrous" (Polukranos, World
    # Eater; Arbor Colossus). Checked ahead of the "becomes untapped"/
    # "becomes tapped" pair below only because it shares their "becomes ..."
    # shape and nothing else - "monstrous" never collides with either word.
    if "becomes monstrous" in lowered:
        return TriggerEvent.BECOMES_MONSTROUS
    # Aerie Worshippers prints "Whenever this creature becomes untapped".
    if "becomes untapped" in lowered:
        return TriggerEvent.BECOMES_UNTAPPED
    if "becomes tapped" in lowered:
        return TriggerEvent.BECOMES_TAPPED
    return None


#: CR 113.6j: "An object's activated ability that has a cost that can't be
#: paid while the object is on the battlefield functions from any zone in
#: which its cost can be paid." CR 701.9a defines discarding as moving a card
#: from its owner's *hand* to their graveyard, so a cost that discards the very
#: object the ability is printed on can never be paid on the battlefield - the
#: ability functions only in a hand. This is the general shape Channel prints
#: (Boseiju, Otawara) and the one Waker of Waves prints with no ability word at
#: all; neither name appears here, only the cost's own words.
_DISCARDS_ITSELF = re.compile(r"^discard this (?:card|permanent)$", re.IGNORECASE)

#: The same CR 113.6j shape, one zone over: "Exile this card from your
#: graveyard" (Campus Crier's own "{1}, Exile this card from your graveyard:
#: Empower Jace 2.", Seasoned Pyromancer) can never be paid on the
#: battlefield either, so the ability functions only where the cost can be
#: paid. `machines/cost.cost_component_for_phrase` already reads the same
#: sentence for *payment* (its own `_PHRASE_EXILE`); this is the zone-
#: permission half CR 113.6j asks for, read off the identical words rather
#: than a card-specific row. Generalises `_DISCARDS_ITSELF`'s own shape past
#: the hand: Emrakul, the Exigent Doom's "{3}, Exile this card from your
#: hand: ..." reaches the same `Zone.HAND` answer through this one regex too
#: (the "hand" branch), rather than a second, hand-only pattern.
_EXILES_ITSELF_FROM_ZONE = re.compile(
    r"^exile this (?:card|permanent) from (?:your|their) (?P<zone>hand|graveyard|library)$",
    re.IGNORECASE,
)
_EXILE_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
}

#: CR 113.6m: "An ability whose cost or effect specifies that it moves the
#: object it's on out of a particular zone functions only in that zone, unless
#: its trigger condition or a previous part of its cost or effect already
#: established a different zone." World Breaker's "Return this card from your
#: graveyard to your hand" names its own graveyard as where it starts, so the
#: ability functions only there.
_RETURNS_ITSELF_FROM_GRAVEYARD = re.compile(
    r"\bthis (?:card|permanent)\b[^.]{0,60}\bfrom (?:your|their|its owner's) graveyard\b",
    re.IGNORECASE,
)

#: CR 702.62b: "A card is 'suspended' if it's in the exile zone, has suspend,
#: and has a time counter on it." Greater Gargadon's own second ability -
#: "Sacrifice an artifact, creature, or land: Remove a time counter from this
#: card. Activate only if this card is suspended." - carries an "Activate
#: only if" restriction (CR 602.5b) whose *only* way to be met is for the
#: card to already be exiled with a time counter, so the restriction pins the
#: ability to exile just as surely as `_RETURNS_ITSELF_FROM_GRAVEYARD` pins
#: World Breaker's to a graveyard - it is read off the words alone, not this
#: one card's name, so any future "Activate only if this card is suspended"
#: printing reaches it the same way.
_ACTIVATE_ONLY_IF_SUSPENDED = re.compile(
    r"activate only if this (?:card|permanent) is suspended", re.IGNORECASE
)


def _activated_ability_zone(
    costs: list[Cost], effect: str, instructions: str | None = None
) -> tuple[Zone | None, str | None]:
    """Which zone this printed activated ability functions in, and the CR
    113.6 sub-rule that says so - `(None, None)` for the CR 113.6 default of
    "on the battlefield".

    Read off the ability's own cost, effect, and activation-instruction text
    alone, the way CR 113.6 itself reads it, so nothing here is a per-card
    table: any future card shaped the same way - discarding itself, returning
    itself from its own graveyard, or restricted to activating only while
    suspended - is read correctly with no row added.
    """
    if any(
        piece.kind is CostKind.DISCARD and _DISCARDS_ITSELF.match(piece.text) for piece in costs
    ):
        return Zone.HAND, "CR 113.6j"
    for piece in costs:
        if piece.kind is not CostKind.OTHER:
            continue
        match = _EXILES_ITSELF_FROM_ZONE.match(piece.text)
        if match is not None:
            return _EXILE_ZONE_WORDS[match.group("zone").lower()], "CR 113.6j"
    if _RETURNS_ITSELF_FROM_GRAVEYARD.search(effect):
        return Zone.GRAVEYARD, "CR 113.6m"
    if instructions and _ACTIVATE_ONLY_IF_SUSPENDED.search(instructions):
        return Zone.EXILE, "CR 702.62b"
    return None, None


def _parse_activated(text: str, common: dict) -> ActivatedAbility | None:
    """Split at the first colon that is not inside quotes (CR 602.1a).

    Reminder text is already gone, so a colon inside it - `Cycling {U} ({U},
    Discard this card: Draw a card.)` - cannot be mistaken for the real one.
    """
    colon = _blank_quotes(text).find(":")
    if colon <= 0:
        return None

    cost = text[:colon].strip()
    after = text[colon + 1 :].strip()
    if not cost or not after:
        return None

    instructions = None
    instruction_match = _INSTRUCTIONS.search(after)
    if instruction_match:
        instructions = instruction_match.group(1).strip()
        after = after[: instruction_match.start(1)].strip()

    # CR 601.2f via CR 602.2b: a trailing "This ability costs [N] less ..."
    # sentence is a separate static ability (`ActivationCostReduction`'s own
    # docstring), split off before anything below reads `after` as *the*
    # effect - Boseiju's and Otawara's Channel abilities would otherwise carry
    # a third sentence no clause parser in `machines/effects.py` reads,
    # sinking the whole paragraph under the project's own fail-closed rule.
    effect_text, cost_reduction = _split_off_trailing_cost_reduction(after)

    # Nykthos, Shrine to Nyx prints the colour choice as its own leading
    # sentence ahead of the "Add ..." one. That choice is the same one
    # `Game.activate_ability` already takes as `color` for any `any_color`
    # ability, so it is stripped here rather than left to sink the whole
    # paragraph - `_ADD` anchors at the start of the text and would otherwise
    # never see the "Add" at all. `effect` on the returned ability keeps the
    # full printed text, unchanged.
    add = _ADD.match(_CHOOSE_A_COLOR_PREAMBLE.sub("", effect_text))
    cost_parts = _merge_disjunctive_sacrifice_cost(_split_top_level(cost))
    costs = [_classify_cost(part) for part in cost_parts]
    # CR 606.2 makes an ability a loyalty ability when a loyalty symbol is in
    # its cost, and CR 107.7 prints the symbol as the whole cost, so a single
    # LOYALTY piece is the ability's loyalty cost and anything else is left
    # unmarked rather than half-claimed.
    loyalty = None
    if len(costs) == 1 and costs[0].kind is CostKind.LOYALTY:
        loyalty = _loyalty_symbol(costs[0].text)

    mana = None
    if add:
        mana = _parse_effect(add.group("effect"))
        if mana is not None:
            # Built as a copy rather than assigned field by field: the parse is
            # read-only work, and an engine model's field assignment announces a
            # game change (`snapshot.py`) that would drop a board snapshot.
            rider, unparsed_rider, spend_effect = _parse_mana_rider(add.group("rest"))
            mana = mana.model_copy(
                update={
                    "costs_mana": any(piece.kind is CostKind.MANA for piece in costs),
                    "conditional": _parse_conditional_clauses(add.group("rest")),
                    "rider": rider,
                    "unparsed_rider": unparsed_rider,
                    "spend_effect": spend_effect,
                }
            )

    zone, zone_rule = _activated_ability_zone(costs, effect_text, instructions)
    ability_word = (common.get("ability_word") or "").lower()
    exhaust = ability_word == "exhaust"
    power_up = ability_word == "power-up"

    return ActivatedAbility(
        **common,
        cost=cost,
        costs=costs,
        effect=effect_text,
        instructions=instructions,
        mana=mana,
        loyalty=loyalty,
        zone=zone,
        zone_rule=zone_rule,
        cost_reduction=cost_reduction,
        exhaust=exhaust,
        power_up=power_up,
    )


def _classify_cost(part: str) -> Cost:
    lowered = part.lower()
    if part == "{T}":
        kind = CostKind.TAP
    elif part == "{Q}":
        kind = CostKind.UNTAP
    elif _ONLY_SYMBOLS.match(part):
        # Before the loyalty check, and for good reason: `{0}` is a mana
        # symbol, while a bare `0` is CR 107.7's neutral loyalty symbol. The
        # brace is the whole difference, and _ONLY_SYMBOLS only ever matches
        # brace-wrapped pieces.
        kind = CostKind.MANA
    elif _LOYALTY_SYMBOL.match(part):
        # CR 606.2: a loyalty symbol in the cost makes the ability a loyalty
        # ability. `+N`, `0`, `−N`, and `−X` (CR 107.7).
        kind = CostKind.LOYALTY
    elif lowered.startswith("sacrifice "):
        kind = CostKind.SACRIFICE
    elif lowered.startswith("discard "):
        kind = CostKind.DISCARD
    elif _PAY_LIFE.match(part):
        kind = CostKind.PAY_LIFE
    else:
        kind = CostKind.OTHER
    return Cost(kind=kind, text=part)


# -- triggered mana abilities (CR 605.1b) ------------------------------------

#: What a triggered mana ability does when it resolves: "[its controller |
#: that player ]add[s] [an additional ]<mana>." CR 605.1b makes the ability
#: a mana ability when it triggers from an activated mana ability or from mana
#: being added and "could add mana to a player's mana pool when it resolves";
#: this is the "could add mana" half, read off the effect text alone.
#:
#: The subject names who adds the mana, and so whose pool it lands in:
#: nothing ("add", Leyline of Abundance, Nirkana Revenant, Zendikar Resurgent) is
#: the ability's controller; "its controller" (Wild Growth, Utopia Sprawl,
#: Vernal Bloom) is the controller of the permanent that was tapped; "that
#: player" is the player the condition named.
_TRIGGERED_MANA_RE = re.compile(
    r"^(?:(?P<subject>its controller|that player)\s+)?(?P<may>may\s+)?adds?\s+"
    r"(?:an additional\s+|one additional\s+)?(?P<mana>.+?)\.?$",
    re.IGNORECASE,
)
_TRIGGERED_MANA_SYMBOLS_RE = re.compile(r"\{([WUBRGC])\}", re.IGNORECASE)
#: "one mana of the chosen color" (Utopia Sprawl, recorded as it entered) and
#: "one mana of that color" (Caged Sun, the colour its own condition named).
_TRIGGERED_MANA_CHOSEN_RE = re.compile(r"^one mana of (?:the chosen|that) color$", re.IGNORECASE)
#: "one mana of any color" (Fertile Ground) and "two mana in any combination
#: of colors" (Market Festival): one colour chosen per mana (CR 105.1).
_TRIGGERED_MANA_ANY_COLOR_RE = re.compile(
    rf"^(?P<count>{COUNT}) mana (?:of any color|in any combination of colors)$",
    re.IGNORECASE,
)
#: "one mana of any type that land produced" (Zendikar Resurgent, Mirari's
#: Wake, Kinnan's "that permanent"): one of the types (CR 106.1b) the tapped
#: permanent's own mana ability just made.
_TRIGGERED_MANA_PRODUCED_TYPE_RE = re.compile(
    r"^one mana of any type that (?:[a-z]+ )*?[a-z]+ produced$", re.IGNORECASE
)
#: "<mana> for each <phrase>" (Elvish Guidance's "{G} for each Elf on the
#: battlefield"): the mana, that many times, counted as it is added
#: (CR 608.2h).
_TRIGGERED_MANA_FOR_EACH_RE = re.compile(r"^(?P<mana>.+?) for each (?P<phrase>.+)$", re.IGNORECASE)
#: "If that Island is snow, its controller may add an additional {U}{U}
#: instead." (Snowfall): the same instruction with other mana when the tapped
#: permanent is snow (CR 205.4a).
_TRIGGERED_MANA_SNOW_INSTEAD_RE = re.compile(
    r"^if that (?:[a-z]+ )*?[a-z]+ is snow, (?P<rest>.+?) instead\.?$", re.IGNORECASE
)
#: CR 106.6's "Spend this mana only ..." sentence, carried on the mana.
_TRIGGERED_MANA_SPEND_ONLY_RE = re.compile(r"^spend this mana only\b.*$", re.IGNORECASE)
#: What "for each" counts: "<Subtype or card type> on the battlefield" (every
#: player's) or "<Subtype or card type> you control".
_MANA_COUNT_PHRASE_RE = re.compile(
    r"^(?P<word>[A-Za-z]+) (?P<scope>on the battlefield|you control)$", re.IGNORECASE
)
#: "charge counter on this enchantment" (Gardenize) - CR 122.1's counters on
#: the triggered mana ability's own source, the self-referential sibling
#: `parse_mana_count`'s two board-scan scopes do not cover: this counts
#: nothing on the battlefield at all, only what is already on the permanent
#: whose ability this is. Kept separate from `parse_mana_count`'s own
#: `(scope, card_type, subtype)` return shape rather than folded into it,
#: since there is no board scan to describe - `triggered_mana_count` checks
#: this first and only falls through to `parse_mana_count` when it misses.
_SELF_COUNTER_MANA_COUNT_RE = re.compile(
    r"^(?P<kind>[a-z][a-z '/+-]*?) counters? on this [a-z]+$", re.IGNORECASE
)


def self_counter_mana_count(phrase: str) -> str | None:
    """The counter kind `_SELF_COUNTER_MANA_COUNT_RE` reads off a "for each"
    phrase, lowercased (`CardState.counter_count`'s own key), or `None`."""
    match = _SELF_COUNTER_MANA_COUNT_RE.fullmatch(phrase.strip().rstrip("."))
    return match.group("kind").lower() if match else None


def parse_mana_count(phrase: str) -> tuple[str, Type | None, str] | None:
    """A "for each" phrase as `(scope, card type, subtype)`: scope is
    `"battlefield"` or `"you_control"`, and exactly one of the card type
    (CR 205.2a, lowercase in Oracle text) or the subtype (CR 205.3,
    capitalised) is set. `None` for any other phrase, which fails closed."""
    match = _MANA_COUNT_PHRASE_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    word = match.group("word")
    scope = "battlefield" if match.group("scope").lower() == "on the battlefield" else "you_control"
    if word[:1].isupper():
        return scope, None, word
    try:
        return scope, Type(word.lower()), ""
    except ValueError:
        return None


class TriggeredManaShape(EngineModel):
    """The mana a triggered mana ability adds (CR 605.1b), as data.

    Exactly one of `colors`, `chosen_color`, `any_color` or `produced_type`
    describes the mana; `recipient` says whose pool it goes to. `count` is a
    "for each" phrase multiplying it (`parse_mana_count`), `optional` a "may
    add" (CR 608.2d), `snow_colors` the literal mana added instead when the
    tapped permanent is snow, and `restriction` CR 106.6's "Spend this mana
    only" sentence. Read by the resolution (`machines/effects.py`) and by the
    payment search (`machines/cost.py`), so what a tap is expected to add and
    what it adds are one reading of the text.
    """

    recipient: Literal["controller", "its_controller", "that_player"] = "controller"
    colors: tuple[Color, ...] = ()
    chosen_color: bool = False
    any_color: int = 0
    produced_type: bool = False
    optional: bool = False
    count: str | None = None
    snow_colors: tuple[Color, ...] | None = None
    restriction: str | None = None


def _parse_add_mana_sentence(sentence: str) -> TriggeredManaShape | None:
    """One "[subject ][may ]add[s] [an additional ]<mana>[ for each ...]"."""
    match = _TRIGGERED_MANA_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    subject = (match.group("subject") or "").lower()
    recipient: Literal["controller", "its_controller", "that_player"] = (
        "its_controller"
        if subject == "its controller"
        else "that_player"
        if subject == "that player"
        else "controller"
    )
    optional = match.group("may") is not None
    mana = match.group("mana").strip()
    count: str | None = None
    for_each = _TRIGGERED_MANA_FOR_EACH_RE.fullmatch(mana)
    if for_each is not None:
        count = for_each.group("phrase").strip()
        if parse_mana_count(count) is None and self_counter_mana_count(count) is None:
            return None
        mana = for_each.group("mana").strip()
    common = {"recipient": recipient, "optional": optional, "count": count}
    if _TRIGGERED_MANA_CHOSEN_RE.fullmatch(mana):
        return TriggeredManaShape(chosen_color=True, **common)
    if _TRIGGERED_MANA_PRODUCED_TYPE_RE.fullmatch(mana):
        return TriggeredManaShape(produced_type=True, **common)
    any_color = _TRIGGERED_MANA_ANY_COLOR_RE.fullmatch(mana)
    if any_color is not None:
        word = any_color.group("count").lower()
        amount = parse_count(word) or 0
        return TriggeredManaShape(any_color=amount, **common) if amount else None
    symbols = _TRIGGERED_MANA_SYMBOLS_RE.findall(mana)
    round_trip = "".join(f"{{{symbol}}}" for symbol in symbols)
    if not symbols or round_trip.lower() != mana.lower().replace(" ", ""):
        return None
    return TriggeredManaShape(colors=tuple(Color(symbol.upper()) for symbol in symbols), **common)


def parse_triggered_mana(effect: str) -> TriggeredManaShape | None:
    """`effect`'s mana, when the whole effect is an "add ... mana" instruction
    this engine reads, else `None`: one add sentence, then optionally Snowfall's
    "If that <permanent> is snow, <the same instruction with other mana>
    instead." and a CR 106.6 "Spend this mana only ..." sentence. A count this
    does not read ("for each other land you control with the same name as
    it") or any other rider fails closed."""
    sentences = [part for part in re.split(r"(?<=\.)\s+", effect.strip()) if part]
    if not sentences:
        return None
    restriction: str | None = None
    if len(sentences) > 1 and _TRIGGERED_MANA_SPEND_ONLY_RE.fullmatch(sentences[-1]):
        restriction = sentences.pop()
    snow: TriggeredManaShape | None = None
    if len(sentences) == 2:
        instead = _TRIGGERED_MANA_SNOW_INSTEAD_RE.fullmatch(sentences[1])
        if instead is None:
            return None
        snow = _parse_add_mana_sentence(instead.group("rest"))
        if snow is None:
            return None
        sentences.pop()
    if len(sentences) != 1:
        return None
    shape = _parse_add_mana_sentence(sentences[0])
    if shape is None:
        return None
    update: dict[str, object] = {}
    if snow is not None:
        if (
            not shape.colors
            or not snow.colors
            or snow.recipient != shape.recipient
            or snow.optional != shape.optional
            or snow.count != shape.count
        ):
            return None
        update["snow_colors"] = snow.colors
    if restriction is not None:
        update["restriction"] = restriction
    return shape.model_copy(update=update) if update else shape


# -- "a card with a mana ability" (CR 605.1) ---------------------------------

#: CR 605.1a's fourth criterion: "its cost and effect don't move any card to
#: or from a library." Drawing (CR 121.1), milling and surveilling take a card
#: out of a library, and any text naming a library puts one in or takes one
#: out - Chromatic Sphere's "Add one mana of any color. Draw a card." is the
#: shape this keeps out.
_MOVES_A_LIBRARY_CARD_RE = re.compile(
    r"\b(?:draws?|mills?|surveils?|library|libraries)\b", re.IGNORECASE
)
_TARGET_WORD_RE = re.compile(r"\btargets?\b", re.IGNORECASE)
_MANA_WORD_RE = re.compile(r"\bmana\b", re.IGNORECASE)


def has_mana_ability(card: Card, face: str | None = None) -> bool:
    """Whether `card` itself has a mana ability (CR 605.1) - Moonsilver Key's
    "an artifact card with a mana ability".

    - **CR 605.1a**, an activated ability: it adds mana (`ActivatedAbility.
      mana`, whatever else the cost asks for - Lotus Petal's sacrifice,
      Springleaf Drum's tapped creature), it does not require a target, it is
      not a loyalty ability, and neither its cost nor its effect moves a card
      to or from a library.
    - **CR 605.1b**, a triggered ability: it triggers on mana (the condition
      names mana - Caged Sun's "a land's ability causes you to add one or more
      mana"), adds mana (`parse_triggered_mana`), and does not target.
    - **CR 305.6**'s intrinsic ability of a land with a basic land type.

    Only the card's own abilities count: a quoted ability it grants to
    something else (Paradise Mantle's "Equipped creature has "{T}: Add ..."")
    is that other object's, and `parse_abilities` reads the whole line as one
    static ability. `face` is the face whose abilities count (CR 712.8a: the
    front face anywhere but the battlefield or stack), the same convention as
    `parse_mana_abilities`.
    """
    for ability in parse_abilities(card):
        if face is not None and ability.face != face:
            continue
        if isinstance(ability, ActivatedAbility) and _is_activated_mana_ability(ability):
            return True
        if isinstance(ability, TriggeredAbility) and _is_triggered_mana_ability(ability):
            return True
    intrinsic = intrinsic_land_ability(card, face)
    return intrinsic is not None and intrinsic.mana is not None


#: CR 702's keyword abilities, one per subsection heading of the CR effective
#: 2026-09-25, lowercased (CR 702.145's "Daybound and Nightbound" is two words a
#: card can each have). A search for "a card with <keyword>" (Waterlogged
#: Teachings' "a card with flash", CR 702.8a) is read only for a word on this
#: list, so a phrase that is not a keyword never matches silently.
KEYWORD_ABILITY_NAMES: frozenset[str] = frozenset(
    {
        "absorb",
        "affinity",
        "afflict",
        "afterlife",
        "aftermath",
        "amplify",
        "annihilator",
        "ascend",
        "assist",
        "aura swap",
        "awaken",
        "backup",
        "banding",
        "bargain",
        "battle cry",
        "bestow",
        "blitz",
        "bloodthirst",
        "boast",
        "bushido",
        "buyback",
        "cascade",
        "casualty",
        "champion",
        "changeling",
        "cipher",
        "cleave",
        "companion",
        "compleated",
        "conspire",
        "convoke",
        "craft",
        "crew",
        "cumulative upkeep",
        "cycling",
        "dash",
        "daybound",
        "deathtouch",
        "decayed",
        "defender",
        "delve",
        "demonstrate",
        "dethrone",
        "devoid",
        "devour",
        "disguise",
        "disturb",
        "double strike",
        "dredge",
        "echo",
        "embalm",
        "emerge",
        "enchant",
        "encore",
        "enlist",
        "entwine",
        "epic",
        "equip",
        "escalate",
        "escape",
        "eternalize",
        "evoke",
        "evolve",
        "exalted",
        "exhaust",
        "exploit",
        "extort",
        "fabricate",
        "fading",
        "fear",
        "firebending",
        "first strike",
        "flanking",
        "flash",
        "flashback",
        "flying",
        "for mirrodin!",
        "forecast",
        "foretell",
        "fortify",
        "freerunning",
        "frenzy",
        "fuse",
        "gift",
        "graft",
        "gravestorm",
        "harmonize",
        "haste",
        "haunt",
        "hexproof",
        "hidden agenda",
        "hideaway",
        "horsemanship",
        "impending",
        "improvise",
        "increment",
        "indestructible",
        "infect",
        "ingest",
        "intimidate",
        "job select",
        "jump-start",
        "kicker",
        "landwalk",
        "level up",
        "lifelink",
        "living metal",
        "living weapon",
        "madness",
        "max speed",
        "mayhem",
        "melee",
        "menace",
        "mentor",
        "miracle",
        "mobilize",
        "modular",
        "more than meets the eye",
        "morph",
        "mutate",
        "myriad",
        "nightbound",
        "ninjutsu",
        "offering",
        "offspring",
        "outlast",
        "overload",
        "paradigm",
        "partner",
        "persist",
        "phasing",
        "plot",
        "poisonous",
        "power-up",
        "protection",
        "prototype",
        "provoke",
        "prowess",
        "prowl",
        "rampage",
        "ravenous",
        "reach",
        "read ahead",
        "rebound",
        "reconfigure",
        "recover",
        "reinforce",
        "renown",
        "replicate",
        "retrace",
        "riot",
        "ripple",
        "saddle",
        "scavenge",
        "shadow",
        "shroud",
        "skulk",
        "sneak",
        "solved",
        "soulbond",
        "soulshift",
        "space sculptor",
        "spectacle",
        "splice",
        "split second",
        "spree",
        "squad",
        "start your engines!",
        "station",
        "storied",
        "storm",
        "sunburst",
        "surge",
        "suspend",
        "teamwork",
        "tiered",
        "toxic",
        "training",
        "trample",
        "transfigure",
        "transmute",
        "tribute",
        "umbra armor",
        "undaunted",
        "undying",
        "unearth",
        "unleash",
        "vanishing",
        "vigilance",
        "visit",
        "ward",
        "warp",
        "web-slinging",
        "wither",
    }
)


def _is_activated_mana_ability(ability: ActivatedAbility) -> bool:
    """CR 605.1a's four criteria, read off one parsed activated ability."""
    return (
        ability.mana is not None
        and ability.loyalty is None
        and not _TARGET_WORD_RE.search(ability.effect)
        and not _MOVES_A_LIBRARY_CARD_RE.search(f"{ability.cost} {ability.effect}")
    )


def _is_triggered_mana_ability(ability: TriggeredAbility) -> bool:
    """CR 605.1b's criteria, read off one parsed triggered ability."""
    return (
        _MANA_WORD_RE.search(ability.condition) is not None
        and not _TARGET_WORD_RE.search(ability.effect)
        and parse_triggered_mana(ability.effect) is not None
    )
