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
"""

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..models.card import Card, Color, Type
from ..models.zone import Zone

# --------------------------------------------------------------------------
# Mana abilities (CR 605)
# --------------------------------------------------------------------------

_SYMBOL = re.compile(r"\{([WUBRGC])\}")
#: "Add one mana of any color." (Cavern of Souls, Delighted Halfling) and
#: "Add two mana of any one color." (Shang-Chi, Master of Kung Fu). The second
#: shape adds more than one mana and requires them all to be the same colour,
#: which is what "any **one** color" says; the count is kept so `resolve` adds
#: that many rather than always one.
_ANY_COLOR = re.compile(r"(?P<count>one|two|three|a) mana of any (?:one )?color", re.IGNORECASE)
_ANY_COLOR_COUNTS = {"a": 1, "one": 1, "two": 2, "three": 3}
_MANA_COST_IN_COST = re.compile(r"\{(\d+|[WUBRGCX])\}")

#: `Add {G}, {R}, or {W}` is a choice; `Add {C}{C}` is both at once. The comma
#: is what separates them in WOTC templating.
_CHOICE_SEPARATOR = re.compile(r",|\bor\b")


class ManaCondition(BaseModel):
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


class ManaAbility(BaseModel):
    """One `{T}: Add ...` ability read off a card."""

    #: Each option this ability can produce. One entry means no choice.
    options: list[list[Color]]
    #: True if the ability can add mana of any colour.
    any_color: bool = False
    #: How much mana an `any_color` ability adds, all of the one chosen colour.
    #: 1 for "Add one mana of any color"; 2 for Shang-Chi's "Add two mana of
    #: any one color."
    any_color_count: int = 1
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

    @property
    def is_choice(self) -> bool:
        return self.any_color or len(self.options) > 1

    @property
    def amount(self) -> int:
        """How much mana one activation adds, ignoring any conditional clause."""
        return self.any_color_count if self.any_color else len(self.options[0])

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
        """
        options, any_color = self.options, self.any_color
        for condition in self.conditional:
            if condition.holds(controlled_land_types, own_counters, has_imprinted_card):
                options, any_color = condition.options, condition.any_color
        return options, any_color

    def resolve(
        self,
        controlled_land_types: frozenset[str] = frozenset(),
        own_counters: frozenset[str] = frozenset(),
        color: Color | None = None,
        has_imprinted_card: bool = False,
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
        """
        options, any_color = self.effective(controlled_land_types, own_counters, has_imprinted_card)

        if any_color:
            if color is None:
                raise ValueError("this ability adds any colour; pass the colour chosen")
            return [color] * self.any_color_count

        if len(options) == 1:
            only = options[0]
            if color is not None and color not in only:
                raise ValueError(f"this ability adds {[c.value for c in only]}, not {color.value}")
            return list(only)

        if color is None:
            choices = [[c.value for c in option] for option in options]
            raise ValueError(f"this ability offers {choices}; pass the colour chosen")

        for option in options:
            if option == [color]:
                return list(option)
        raise ValueError(f"{color.value} is not one of this ability's options")


def parse_mana_abilities(card: Card) -> list[ManaAbility]:
    """Every `{T}: Add ...` ability a card has itself, front face and backs.

    This is the same `ManaAbility` `parse_abilities` reads onto
    `ActivatedAbility.mana` - see the module docstring - filtered to the ones
    with `{T}` in their own printed cost, which is what the mana-payment path
    (`tests/scenarios/harness.mana_from`) has always meant by "this card's
    mana ability": Skirk Prospector's `Sacrifice a Goblin: Add {R}.` is still
    read by `parse_abilities` as an activated ability with `mana` set, but a
    caller that only wants "what can I tap this for" does not want it.

    A basic land with no printed ability of its own falls back to
    `intrinsic_land_ability` (CR 305.6), the same fallback
    `activated_abilities_of` uses for in-game activation.
    """
    printed = [
        ability.mana
        for ability in parse_abilities(card)
        if isinstance(ability, ActivatedAbility)
        and ability.mana is not None
        and any(piece.kind is CostKind.TAP for piece in ability.costs)
    ]
    if printed:
        return printed
    intrinsic = intrinsic_land_ability(card)
    return [intrinsic.mana] if intrinsic is not None and intrinsic.mana is not None else []


def _parse_effect(effect: str) -> ManaAbility | None:
    any_color = _ANY_COLOR.search(effect)
    if any_color:
        count = _ANY_COLOR_COUNTS[any_color.group("count").lower()]
        return ManaAbility(
            options=[[color] * count for color in _COLORS],
            any_color=True,
            any_color_count=count,
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


def intrinsic_land_ability(card: Card) -> "ActivatedAbility | None":
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
    """
    if Type.LAND not in card.types:
        return None
    colors = [
        _BASIC_LAND_COLORS[subtype] for subtype in card.subtypes if subtype in _BASIC_LAND_COLORS
    ]
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
        face=card.name,
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

    Only these eighteen are recognised; every other condition leaves `event`
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
    #: position." Nothing emits this yet: the taps the engine performs happen
    #: inside cost payment (`machines/cost.py`) and attack declaration
    #: (`machines/combat.py`), which have no emit call.
    BECOMES_TAPPED = "becomes_tapped"
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


class Cost(BaseModel):
    """One piece of an activation cost, as printed."""

    kind: CostKind
    text: str


#: CR 107.7's three loyalty symbol shapes: `[+N]` ("Put N loyalty counters on
#: this permanent"), `[0]` ("Put zero loyalty counters on this permanent"), and
#: `[−N]` ("Remove N loyalty counters from this permanent"), where the rule's
#: "a minus sign followed by a number or an X" is the `−X` form. Scryfall prints
#: the minus as U+2212; the ASCII hyphen is accepted too. Brace-wrapped `{0}` is
#: a mana symbol and never matches - the classification checks it first.
_LOYALTY_SYMBOL = re.compile(r"^\+(?P<plus>\d+)$|^[−-](?P<minus>\d+|[Xx])$|^0$")


class LoyaltyCost(BaseModel):
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


class BaseAbility(BaseModel):
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


class ActivationCostReduction(BaseModel):
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
    #: `Game.activation_cost_reduction_for`; no card name involved.
    quality: str


#: "This ability costs {N} less to activate for each <quality> you control."
#: - matched only as the *last* sentence of an activated ability's effect, so
#: it is read the same way whichever card prints it, never by name.
_TRAILING_ACTIVATION_COST_REDUCTION_RE = re.compile(
    r"^this ability costs \{(?P<amount>\d+)\} less to activate for each "
    r"(?P<quality>.+?) you control\.?$",
    re.IGNORECASE,
)


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
    match = _TRAILING_ACTIVATION_COST_REDUCTION_RE.match(sentences[-1].strip())
    if match is None:
        return effect, None
    reduction = ActivationCostReduction(
        amount=int(match.group("amount")), quality=match.group("quality").strip()
    )
    return " ".join(sentences[:-1]).strip(), reduction


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


class UnparsedAbility(BaseAbility):
    """A line this module could not read. Not a category in the rules."""

    kind: Literal[AbilityKind.UNPARSED] = AbilityKind.UNPARSED


Ability = Annotated[
    ActivatedAbility | TriggeredAbility | StaticAbility | KeywordAbility | UnparsedAbility,
    Field(discriminator="kind"),
]


def parse_abilities(card: Card) -> list[Ability]:
    """Every ability printed on a card, front face and backs, in printed order.

    One entry per ability, not per line: a keyword list on one line yields one
    `KeywordAbility` per keyword. A line that is only reminder text yields
    nothing.
    """
    abilities: list[Ability] = []
    for face_name, text in _faces(card):
        for line in text.split("\n"):
            abilities.extend(_parse_line(line, card.keywords, face_name))
    return abilities


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
    found: set[str] = set()
    for line in lines:
        for ability in _parse_line(line, list(known), face=""):
            if isinstance(ability, KeywordAbility):
                found.add(ability.canonical.lower())
    return found


def keyword_ability(card: Card, keyword: str) -> KeywordAbility | None:
    """One keyword ability by name, case-insensitively. None if it is not printed."""
    for ability in keyword_abilities(card):
        if ability.canonical.lower() == keyword.lower():
            return ability
    return None


def layer_readable_sentences(
    text: str | None, known_keywords: list[str] | None = None
) -> list[str]:
    """Every sentence of `text` this module's own line classifier says a
    continuous effect (CR 611.2, CR 611.3) could plausibly come from.

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
        for ability in _parse_line(line, list(known_keywords or []), face=""):
            body: str | None = None
            if isinstance(ability, StaticAbility):
                body = ability.text
            elif isinstance(ability, (ActivatedAbility, TriggeredAbility)):
                body = ability.effect
            if not body:
                continue
            for sentence in re.split(r"(?<=\.)\s+", body.strip()):
                sentence = sentence.strip()
                if sentence:
                    sentences.append(sentence)
    return sentences


# --------------------------------------------------------------------------
# Line parsing
# --------------------------------------------------------------------------

#: CR 714 Saga chapter markers: `I —`, `I, II —`, `III —`.
_CHAPTER = re.compile(r"^[IVXL]+(?:\s*,\s*[IVXL]+)*\s*—")

#: CR 207.2c ability word: a short capitalised phrase, then an em dash.
_ABILITY_WORD = re.compile(r"^([A-Z][A-Za-z'\- ]{2,30}?)\s+—\s+(?=\S)")

#: CR 603.1's three words, at the start of the line.
_TRIGGER = re.compile(r"^(When|Whenever|At)\b\s*", re.IGNORECASE)

#: CR 602.1b activation instructions, at the end of the effect.
_INSTRUCTIONS = re.compile(r"(?:^|(?<=\.\s))((?:Activate|Any player may activate)\b[^.]*\.)\s*$")

_REMINDER = re.compile(r"\([^()]*\)")
_MANA_SHAPED = re.compile(r"^(?:\{[^{}]+\}\s*)+$|^\d+$|^X$")
#: The base effect is the first sentence; anything after it (an "instead"
#: clause, a spend restriction) is captured as `rest` rather than discarded.
#: Previously anchored to the *whole* effect with `[^.]+`, which cannot cross a
#: full stop - Urza's Power Plant's `{T}: Add {C}. If you control ...` has a
#: second sentence, so that anchoring made `mana=None` for every conditional
#: mana ability, and CR 605.1a's "could add mana" criterion failed, sending it
#: to the stack instead of resolving immediately (CR 605.3b).
_ADD = re.compile(r"^Add\s+(?P<effect>[^.]+)\.?\s*(?P<rest>.*)$", re.DOTALL)
_ONLY_SYMBOLS = re.compile(r"^(?:\{[^{}]+\}|\s)+$")
_PAY_LIFE = re.compile(r"^Pay\s+\S+\s+life$", re.IGNORECASE)


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
    """Split on a separator, ignoring any inside quotes."""
    blanked = _blank_quotes(text)
    parts: list[str] = []
    start = 0
    for index, char in enumerate(blanked):
        if char == separator:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def _parse_line(raw: str, keywords: list[str], face: str) -> list[Ability]:
    text, reminder = _strip_reminder(raw)
    if not text:
        # The line was nothing but reminder text - a Saga's lore-counter note,
        # for instance. Not an ability.
        return []

    common = {"raw": raw.strip(), "text": text, "reminder": reminder, "face": face}

    if _CHAPTER.match(text):
        return [UnparsedAbility(**common)]

    keyword_abilities = _parse_keywords(text, keywords, common)
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
        return [triggered]

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
    # Longest first, so `First strike` wins over any shorter prefix.
    known = sorted(keywords, key=len, reverse=True)

    em_dash = _parse_keyword_cost(text, known, common)
    if em_dash is not None:
        return [em_dash]

    if "." in text or ":" in text:
        return []

    parsed: list[Ability] = []
    for token in _split_top_level(text.replace(";", ","), ","):
        match = _match_keyword(token, known)
        if match is None:
            return []
        parsed.append(KeywordAbility(**common, **match))
    return parsed


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


def _parse_triggered(text: str, common: dict) -> TriggeredAbility | None:
    match = _TRIGGER.match(text)
    if match is None:
        return None

    word = TriggerWord(match.group(1).lower())
    body = text[match.end() :]

    parts = _split_top_level(body)
    if len(parts) < 2:
        # `[Trigger condition], [effect]` needs a comma to separate them.
        return None

    condition, rest = parts[0], ", ".join(parts[1:])

    intervening_if: str | None = None
    if rest.lower().startswith("if "):
        clause_parts = _split_top_level(rest)
        if len(clause_parts) < 2:
            return None
        intervening_if = clause_parts[0][len("if ") :].strip()
        rest = ", ".join(clause_parts[1:])

    return TriggeredAbility(
        **common,
        word=word,
        condition=condition,
        intervening_if=intervening_if,
        effect=rest,
        event=_trigger_event(condition),
    )


def _trigger_event(condition: str) -> TriggerEvent | None:
    lowered = condition.lower()
    if lowered.startswith("the beginning of"):
        return TriggerEvent.BEGINNING_OF_STEP
    # Before the "becomes blocked" test below, which would otherwise claim
    # "becomes the target of ..." for CR 509.
    if "becomes the target" in lowered:
        return TriggerEvent.BECOMES_TARGET
    if re.search(r"\benters\b", lowered):
        return TriggerEvent.ENTERS_THE_BATTLEFIELD
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
    # "Whenever Ragavan deals combat damage to a player" - one event kind for
    # combat and noncombat; the matcher reads the "combat" word off the
    # condition and `GameEvent.combat` off the event.
    if re.search(r"\bdeals (?:combat )?damage\b", lowered):
        return TriggerEvent.DEALS_DAMAGE
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


def _activated_ability_zone(costs: list[Cost], effect: str) -> tuple[Zone | None, str | None]:
    """Which zone this printed activated ability functions in, and the CR
    113.6 sub-rule that says so - `(None, None)` for the CR 113.6 default of
    "on the battlefield".

    Read off the ability's own cost and effect text alone, the way CR 113.6
    itself reads it, so nothing here is a per-card table: any future card
    shaped the same way - discarding itself, or returning itself from its own
    graveyard - is read correctly with no row added.
    """
    if any(
        piece.kind is CostKind.DISCARD and _DISCARDS_ITSELF.match(piece.text) for piece in costs
    ):
        return Zone.HAND, "CR 113.6j"
    if _RETURNS_ITSELF_FROM_GRAVEYARD.search(effect):
        return Zone.GRAVEYARD, "CR 113.6m"
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

    add = _ADD.match(effect_text)
    costs = [_classify_cost(part) for part in _split_top_level(cost)]
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
            mana.costs_mana = any(piece.kind is CostKind.MANA for piece in costs)
            mana.conditional = _parse_conditional_clauses(add.group("rest"))

    zone, zone_rule = _activated_ability_zone(costs, effect_text)

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
