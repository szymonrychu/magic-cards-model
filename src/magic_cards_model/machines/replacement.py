"""Replacement (CR 614) and prevention (CR 615) effects: reading them, applying them.

Two halves live here.

**The parser** reads what a card's text *claims* about replacing or preventing
events. It is documented immediately below, and it is deliberately text-only:
it never touches a game.

**The application path** (see "Applying them", further down) is the other half.
It defines the events that can be replaced, gathers the effects that apply to
one, lets the affected object's controller order them (CR 616.1), applies each
at most once (CR 614.5), and hands the modified event back to `Game` to carry
out (CR 614.6).

## What is parsed

WOTC templates these effects tightly, which is what makes them readable:

| Template | Rule | Kind |
|---|---|---|
| `If ... would ..., ... instead.` | CR 614.1a | `IF_WOULD_INSTEAD` |
| `If ... would ..., prevent ...` | CR 615.1a | `PREVENT_IF_WOULD` |
| `... instead of ...` | CR 614.1a | `INSTEAD_OF` |
| `... rather than ...` | CR 614.1a shape | `RATHER_THAN` |
| `Skip ...` | CR 614.1b, 614.10 | `SKIP` |
| `[This] enters tapped.` | CR 614.1d | `ENTERS_TAPPED` |
| `[This] enters with N counters on it.` | CR 614.1c | `ENTERS_WITH` |
| `... enter as a copy of ...` | CR 614.1c, 616.1c | `ENTERS_AS_COPY` |
| `As [this] enters, ...` | CR 614.1c | `AS_ENTERS` |
| `As [this] is turned face up, ...` | CR 614.1e | `AS_TURNED_FACE_UP` |
| `Prevent the next N damage ... this turn.` | CR 615.1a | `PREVENT_NEXT` |
| `Prevent all [combat] damage that would be dealt ...` | CR 615.1a | `PREVENT_ALL` |
| `The next time ... would deal damage ..., prevent that damage.` | CR 615.8 | `PREVENT_NEXT_TIME` |

Both era's wordings are accepted. WOTC shortened "enters the battlefield" to
"enters" in 2024; Scryfall's oracle text was rewritten wholesale, so nearly
every card now reads "enters", while a handful (Forsaken Crossroads, Gather
Specimens, Lupine Harbingers) still carry the long form. `(?: the battlefield)?`
is optional everywhere it appears.

## The boundary against triggered abilities

Triggered abilities are somebody else's job, and telling the two apart is the
one thing this parser must not get wrong.

**The rule: an ability paragraph whose first word is "When", "Whenever", or "At"
is a triggered ability, and nothing in that paragraph is claimed here.** CR
603.1 writes a trigger as "[When/Whenever/At] [trigger condition], [effect].
[Instructions (if any).]" - the trailing instructions belong to the trigger too,
so the whole paragraph is skipped, not just its first sentence. Oracle text puts
one ability per line, so a paragraph is a line.

That rule is what keeps these apart:

- Rest in Peace's "When this enchantment enters, exile all graveyards." is a
  trigger; its second line "If a card or token would be put into a graveyard
  from anywhere, exile it instead." is a replacement effect. Only the second is
  returned.
- Brine Elemental's "When this creature is turned face up, each opponent skips
  their next untap step." is a trigger even though it contains "skips". Its
  skip *is* a CR 614.1b replacement effect - but one that the trigger creates
  when it resolves, not one the permanent generates while it sits there. It is
  returned with `from_trigger=True` and is never compiled into behaviour, so no
  battlefield scan can pick it up as a static ability. Contrast CR 614.1e's
  "As [this] is turned face up, ...", which is a replacement effect outright.
- Forsaken Crossroads' "When Forsaken Crossroads enters the battlefield, scry 1.
  If you weren't the starting player, you may untap Forsaken Crossroads
  instead." is one trigger across two sentences. The "instead" in the second
  sentence is part of the trigger's effect, not a replacement effect.

The word "instead" alone is not enough either way. `IF_WOULD_INSTEAD` requires
the event clause to contain "would", which is what separates a replacement
effect from a conditional inside a resolving effect - Urza's Tower's "If you
control an Urza's Mine and an Urza's Power-Plant, add {C}{C}{C} instead." is
not a replacement effect and is not claimed as one.

## What is deliberately not parsed

- **Alternative costs.** "You may exile two green cards from your hand rather
  than pay this spell's mana cost" is CR 118.9, not CR 614. Sentences whose
  "rather than" governs paying or casting are dropped outright.
- **"Can't be prevented."** CR 615.12 - unpreventable damage is the absence of
  a prevention effect, not one. Questing Beast's line comes back `UNPARSED`.
- **Opening-hand effects.** Leyline of the Void's "If this card is in your
  opening hand, you may begin the game with it on the battlefield" (CR 103.6a)
  has neither "would" nor a prevention word and is not claimed here. It is read
  by `machines/opening_hand.py` instead, which owns CR 103.6's whole sequence -
  it is a start-of-game action, not a replacement effect.
- **Turning a parsed sentence into behaviour.** Parsing "exile it instead" tells
  you the shape, not what to do; the application path below is a hand-written
  registry for that reason. The two generic exceptions are `ENTERS_TAPPED` and
  `ENTERS_WITH`, which are unambiguous enough to execute straight off the parse.

## Honesty over coverage

A sentence that carries a replacement or prevention cue word - "instead",
"prevent", "skip", "rather than" - but matches no template is returned with
`kind=UNPARSED` and its text, rather than forced into the nearest shape. A
sentence with no cue word at all is not returned: otherwise every vanilla
creature would report a list of non-effects.

Reminder text in parentheses is stripped before parsing and kept on the model in
`reminder`. That matters here more than elsewhere: dredge's reminder text is
itself a textbook "If you would draw a card, you may mill N cards instead", and
parsing it would report a replacement effect the card does not have while it is
on the battlefield. Dakmor Salvage therefore reports only "This land enters
tapped."
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ConfigDict

from magic_cards_model.phrases import with_indefinite_article

from ..data.creature_types import creature_types
from ..models.card import Card, Color, Type
from ..models.card_state import CardState, Choice, ChoiceKind, Counter, ExileMarker
from ..models.token import TokenDefinition, is_token
from ..models.zone import Zone
from ..numbers import COUNT, MULTIPLIER, parse_count, parse_multiplier
from ..snapshot import EngineModel
from .abilities import keywords_in_lines
from .combat import Keyword
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import ReflexiveExileCopiedCard

if TYPE_CHECKING:
    from ..models.game import Game
    from ..models.player import Player
    from .layers import ComputedBoard

# --------------------------------------------------------------------------
# Kinds
# --------------------------------------------------------------------------


class ReplacementKind(StrEnum):
    """Which template a sentence matched. `UNPARSED` means none of them did."""

    #: CR 614.1a - "If [event] would [happen], [replacement] instead."
    IF_WOULD_INSTEAD = "if_would_instead"
    #: CR 614.1a - "[replacement] instead of [event]" / "Instead of [event], [replacement]".
    INSTEAD_OF = "instead_of"
    #: CR 614.1a shape - "[replacement] rather than [event]". Not every sentence
    #: of this shape is a CR 614 replacement effect; see `RATHER_THAN` notes.
    RATHER_THAN = "rather_than"
    #: CR 614.1b, 614.10 - "Skip [something]".
    SKIP = "skip"
    #: CR 614.1d - "[This permanent] enters tapped." Verified in this session:
    #: CR 614.1d is "Continuous effects that read '[This permanent] enters . . .'
    #: or '[Objects] enter [the battlefield] . . .' are replacement effects",
    #: which is the bare form. CR 614.1c is the *other* three shapes -
    #: "[This permanent] enters with . . . ," "As [this permanent] enters . . . ,"
    #: and "[This permanent] enters as . . ." - so it is `ENTERS_WITH`,
    #: `AS_ENTERS` and `ENTERS_AS_COPY`'s rule, not this one. This line cited
    #: 614.1c until that was looked up; the wrong number is recorded here the
    #: same way the parser docstring records the CR 113.3 correction.
    ENTERS_TAPPED = "enters_tapped"
    #: CR 614.1d - "[Objects] enter [the battlefield] untapped." A general
    #: effect watching a *class* of permanent, not the printing permanent's own
    #: CR 614.12 self-modification - Spelunking's "Lands you control enter
    #: untapped" is the pool's only printing, overriding whatever tapped state
    #: another effect (a search's own "tapped", a shockland's own "enters
    #: tapped") would otherwise have given the entering land.
    ENTERS_UNTAPPED = "enters_untapped"
    #: CR 614.1c - "[This permanent] enters with [counters] on it."
    ENTERS_WITH = "enters_with"
    #: CR 614.1c, 616.1c - "... enter as a copy of ...".
    ENTERS_AS_COPY = "enters_as_copy"
    #: CR 614.1c - "As [this permanent] enters, ...".
    AS_ENTERS = "as_enters"
    #: CR 614.1e - "As [this permanent] is turned face up, ...".
    AS_TURNED_FACE_UP = "as_turned_face_up"
    #: CR 615.1a - "Prevent the next N damage that would be dealt to X this turn."
    PREVENT_NEXT = "prevent_next"
    #: CR 615.1a - "Prevent all [combat] damage that would be dealt ...".
    PREVENT_ALL = "prevent_all"
    #: CR 615.8 - "The next time [source] would deal damage ..., prevent that damage."
    PREVENT_NEXT_TIME = "prevent_next_time"
    #: CR 615.1a - "If [event] would [happen], prevent ...".
    PREVENT_IF_WOULD = "prevent_if_would"
    #: Cue word present, no template matched. Read `text`, do not trust the rest.
    UNPARSED = "unparsed"


#: The kinds that are prevention effects (CR 615) rather than plain replacement
#: effects (CR 614). Note CR 615.1 makes prevention a species of continuous
#: effect alongside replacement, so these are returned from the same call.
PREVENTION_KINDS = frozenset(
    {
        ReplacementKind.PREVENT_NEXT,
        ReplacementKind.PREVENT_ALL,
        ReplacementKind.PREVENT_NEXT_TIME,
        ReplacementKind.PREVENT_IF_WOULD,
    }
)

#: The kinds that modify how a permanent enters the battlefield (CR 614.12).
ENTERS_KINDS = frozenset(
    {
        ReplacementKind.ENTERS_TAPPED,
        ReplacementKind.ENTERS_UNTAPPED,
        ReplacementKind.ENTERS_WITH,
        ReplacementKind.ENTERS_AS_COPY,
        ReplacementKind.AS_ENTERS,
    }
)


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


class CopyException(EngineModel):
    """CR 707.9b's modifications to a copy, read off an "except ..." tail.

    CR 707.9b: "Some copy effects modify a characteristic as part of the
    copying process. The final set of values for that characteristic becomes
    part of the copiable values of the copy." So these are not effects layered
    on top of the copy - they are part of what layer 1a writes (CR 613.2a,
    CR 613.2c: "After all rules and effects in layer 1 have been applied, the
    object's characteristics are its copiable values").

    Superior Spider-Man prints all three at once: "except his name is Superior
    Spider-Man and he's a 4/4 Spider Human Hero in addition to his other
    types" - a name, a base power and toughness, and subtypes *added* rather
    than replacing (CR 205.1b's retaining form, spelled out by "in addition to
    his other types").
    """

    model_config = ConfigDict(frozen=True)

    #: The name the copy has instead of the copied object's (CR 707.9b).
    name: str | None = None
    #: The copy's power and toughness, both or neither.
    power: int | None = None
    toughness: int | None = None
    #: Card types gained on top of the copied ones (CR 205.1b).
    added_types: tuple[Type, ...] = ()
    #: Subtypes gained on top of the copied ones (CR 205.1b, CR 205.3).
    added_subtypes: tuple[str, ...] = ()


class ReplacementEffect(EngineModel):
    """One replacement or prevention effect read off a card.

    Most fields are per-kind and stay `None` when the kind does not carry them.
    `kind`, `raw`, and `text` are always populated, so an `UNPARSED` result is
    still usable - it says "this sentence is about replacement and I could not
    read it", which is the honest answer.
    """

    kind: ReplacementKind
    #: The whole ability paragraph as printed, reminder text included.
    raw: str
    #: The one sentence this effect was parsed from, reminder text removed.
    text: str
    #: Reminder text found in the paragraph, joined, or None. Never parsed.
    reminder: str | None = None
    #: Face name for a multifaced card, None for a single-faced one.
    face: str | None = None

    #: True when this sentence is the *effect* of a triggered ability rather
    #: than a static ability's own continuous effect (CR 603.1 vs CR 604.2).
    #:
    #: Brine Elemental's "When this creature is turned face up, each opponent
    #: skips their next untap step" is the only shape read this way, and the
    #: flag is what keeps reading it from being a lie: the skip does not exist
    #: while the permanent sits on the battlefield, it comes into being when
    #: the trigger resolves. `parsed_card_replacements` therefore never
    #: compiles a `from_trigger` effect into a `CardReplacement`, so nothing
    #: `applicable_effects` gathers off the battlefield can come from one.
    #: Reporting the shape and refusing to perform it is the honest answer;
    #: performing it as a static ability would be a wrong board state.
    from_trigger: bool = False

    #: The event being replaced or prevented, as templated.
    event: str | None = None
    #: What happens in its place.
    replacement: str | None = None
    #: What enters, is turned face up, or is skipped - the subject of the clause.
    subject: str | None = None
    #: A leading or trailing condition: "unless you control a basic land",
    #: "you don't".
    condition: str | None = None

    #: True when the effect is worded as a choice ("you may", "You may have").
    optional: bool = False
    #: True when the effect only concerns the object it is printed on, rather
    #: than being a general effect watching every object. CR 614.12 draws this
    #: line for effects that modify how a permanent enters: they "may come from
    #: the permanent itself if they affect only that permanent". Mox Diamond's
    #: "If this artifact would enter" is one; Gather Specimens' "If a creature
    #: would enter the battlefield under an opponent's control" is not.
    #:
    #: This is NOT CR 614.15's "self-replacement effect", which is a different
    #: thing: an effect of a resolving spell replacing part of its own effect.
    self_replacement: bool = False

    #: How many: counters entered with, damage prevented. None when absent or
    #: variable.
    amount: int | None = None
    #: True when the amount is X or otherwise not a fixed number.
    variable_amount: bool = False
    #: The kind of counter, as printed: "+1/+1", "shield", "charge".
    counter_kind: str | None = None
    #: How many, when the card states it as an expression rather than a number
    #: or an X - Ulamog, the Defiler's "equal to the greatest mana value among
    #: cards in exile". Kept as the printed phrase; `_self_enters_modifiers`
    #: evaluates it against the game as the permanent enters, and refuses the
    #: whole effect if it recognises no resolver for the phrase.
    amount_expression: str | None = None
    #: What the permanent enters as a copy of.
    copy_of: str | None = None
    #: CR 707.9b's "except ..." tail, already read into the values it overrides:
    #: "except his name is Superior Spider-Man and he's a 4/4 Spider Human Hero
    #: in addition to his other types". CR 707.9b: "Some copy effects modify a
    #: characteristic as part of the copying process. The final set of values
    #: for that characteristic becomes part of the copiable values of the copy."
    #: `None` when the clause has no exception at all - never when there was
    #: one this parser could not read; that case is `copy_exception_unparsed`
    #: instead, so the two `None`-shaped facts ("nothing was printed" and
    #: "something was printed and I could not read it") stay distinguishable
    #: downstream instead of collapsing into the same default.
    copy_exception: CopyException | None = None
    #: The raw "except ..." text, set only when the clause existed and
    #: `_parse_copy_exception` could not read it. CR 707.9b treats the copy and
    #: its exception as one atomic computation of copiable values ("The final
    #: set of values ... becomes part of the copiable values of the copy"), so
    #: a caller that cannot compute the exception must not silently apply the
    #: copy without it either - that would be running half the instruction,
    #: which CR 608.2c has no notion of. `_enters_as_copy` reads this field to
    #: fail closed *loudly*: a notice, and the "enter as a copy" replacement
    #: skipped, rather than the copy silently missing whatever the "except"
    #: tail was supposed to change. Exclusive with `copy_exception` being set:
    #: at most one of the two is non-`None`.
    copy_exception_unparsed: str | None = None
    #: The "When you do, ..." sentence printed immediately after this one, as
    #: printed. CR 603.12: "A resolving spell or ability may allow or instruct
    #: a player to take an action and create a triggered ability that triggers
    #: 'when [a player] [does or doesn't]' take that action" - Superior
    #: Spider-Man's "When you do, exile that card." is linked to the "you may
    #: have ... enter as a copy" choice above it and happens only if that
    #: choice was taken. Held here rather than parsed as its own effect
    #: because a reflexive ability has no independent existence: without the
    #: action it reflects, it is never created at all.
    linked_trigger: str | None = None
    #: True when the permanent also enters tapped alongside another `enters`
    #: clause, as on Vesuva.
    tapped: bool = False
    #: True when prevention is limited to combat damage.
    combat_only: bool = False
    #: Who or what the damage would be dealt to, as printed.
    damage_target: str | None = None

    @property
    def is_prevention(self) -> bool:
        """True for CR 615 prevention effects."""
        return self.kind in PREVENTION_KINDS

    @property
    def modifies_entering(self) -> bool:
        """True for CR 614.12 effects that change how a permanent enters."""
        return self.kind in ENTERS_KINDS

    @property
    def parsed(self) -> bool:
        return self.kind is not ReplacementKind.UNPARSED


# --------------------------------------------------------------------------
# Text preparation
# --------------------------------------------------------------------------

_REMINDER = re.compile(r"\(([^()]*)\)")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!])\s+")
#: An activated ability's cost, as in `{T}: Prevent the next 1 damage ...`. Only
#: stripped when the prefix looks like a cost, so `Choose one -` survives.
_COST_PREFIX = re.compile(r"^[^:\n]{0,80}\{[^}]+\}[^:\n]{0,40}:\s*")
_TRIGGER_OPENER = re.compile(r"^(When|Whenever|At)\b")


def strip_reminder_text(text: str) -> tuple[str, str | None]:
    """Split oracle text into rules text and the reminder text in parentheses.

    Reminder text is never rules text (CR 207.2a), and it routinely contains the
    very words this parser looks for - dredge's reminder is a complete
    "if you would draw a card ... instead" sentence.
    """
    reminders = [match.strip() for match in _REMINDER.findall(text)]
    cleaned = _REMINDER.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = "\n".join(line.strip() for line in cleaned.splitlines())
    return cleaned.strip(), "; ".join(r for r in reminders if r) or None


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

#: Cue words that make a sentence worth reporting as `UNPARSED` when nothing
#: matched. Without this gate every vanilla line would come back as a non-effect.
_CUE = re.compile(r"\b(instead|prevent|prevents|prevented|skip|skips|rather than)\b", re.IGNORECASE)

#: CR 118.9 alternative costs, which read like replacement effects and are not.
_ALTERNATIVE_COST = re.compile(
    r"rather than (pay|paying|cast|casting)\b|rather than its mana cost", re.IGNORECASE
)

#: "this creature", "this land", "this permanent", "this" - a self reference.
_THIS = re.compile(
    r"^(this|it)\b|^this (creature|land|permanent|artifact|enchantment|"
    r"planeswalker|battle|card|spell|vehicle|equipment|token)\b",
    re.IGNORECASE,
)

_ENTERS = r"enters?(?: the battlefield)?"


# --------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------

# CR 614.1a. The event clause must contain "would": that is what separates a
# replacement effect from a conditional inside a resolving effect.
#
# The optional "As long as [condition]," prefix is CR 604.2's own wording for a
# static ability whose continuous effect only exists while something is true -
# Quantum Riddler's "As long as you have one or fewer cards in hand, if you
# would draw one or more cards, ... instead". The condition is kept in
# `condition` rather than folded into the event, because it is not part of the
# event at all: it decides whether the replacement effect exists right now.
_IF_WOULD = re.compile(
    r"^(?:As long as (?P<condition>[^,]+),\s*)?"
    r"If (?P<event>.+?\bwould\b.+?),\s*(?P<rest>.+?)\.?$",
    re.IGNORECASE,
)

_INSTEAD_OF_LEADING = re.compile(
    r"^Instead of (?P<event>.+?),\s*(?P<replacement>.+?)\.?$", re.IGNORECASE
)
_INSTEAD_OF_TRAILING = re.compile(
    r"^(?:If (?P<condition>[^,]+),\s*)?(?P<replacement>.+?)\s+instead of\s+(?P<event>.+?)\.?$",
    re.IGNORECASE,
)
_RATHER_THAN = re.compile(
    r"^(?P<replacement>.+?)\s+rather than\s+(?P<event>.+?)\.?$", re.IGNORECASE
)

# CR 614.1b / 614.10.
_SKIP = re.compile(r"^Skip (?P<skipped>.+?)\.?$")
#: The same rule, worded about a player rather than as an imperative - "each
#: opponent skips their next untap step". Only the third-person "skips" is
#: matched, which is what keeps the imperative "Skip your draw step" on
#: `_SKIP` above, and the subject is kept short and comma-free so a longer
#: sentence that merely contains the word does not get claimed. Tried after
#: `_try_if_would`, so Plagiarize's "instead that player skips that draw and
#: you draw a card" stays the `IF_WOULD_INSTEAD` it is.
_PLAYER_SKIPS = re.compile(r"^(?P<who>[^,]{1,40}?) skips (?P<skipped>.+?)\.?$", re.IGNORECASE)

# CR 614.1d (the bare "[This permanent] enters ..." form; CR 614.1c is
# "enters with"/"As ... enters"/"enters as"). `condition` picks up the "If you
# don't, it enters tapped" form used by the modal double-faced lands, and
# `unless` the "unless ..." form used by the duals. The two groups are kept
# apart on purpose: they carry opposite polarity - a leading "If <cond>," taps
# when the condition *holds*, a trailing "unless <cond>" taps when it does
# *not* - and `_enters_tapped_condition` below reads that polarity back off the
# retained "unless" word.
_ENTERS_TAPPED = re.compile(
    rf"^(?:If (?P<condition>[^,]+),\s*)?(?P<subject>[^,]+?) {_ENTERS} tapped"
    r"(?:\s+(?P<unless>unless .+?))?\.?$",
    re.IGNORECASE,
)
# CR 614.1d - "[Objects] enter [the battlefield] untapped." Spelunking's own
# "Lands you control enter untapped": a plural, class-scoped subject ("Lands
# you control"), not `_ENTERS_TAPPED`'s singular "[this permanent]" - and the
# opposite tapped state, which is why this is not folded into that regex with
# an alternation. `subject` is read back for `_refers_to_self` the same way
# every other entering-shape regex here does, though a "you control" subject
# never actually matches it (it names a class, not the printing card itself).
_ENTERS_UNTAPPED = re.compile(rf"^(?P<subject>.+?) {_ENTERS} untapped\.?$", re.IGNORECASE)
_ENTERS_WITH = re.compile(
    rf"^(?:If (?P<condition>[^,]+),\s*)?(?P<subject>[^,]+?) {_ENTERS} with (?P<what>.+?)"
    r"(?:\s+on it)?(?:,\s*(?P<tail>where .+?))?\.?$",
    re.IGNORECASE,
)
_ENTERS_AS_COPY = re.compile(
    rf"^(?:You may have\s+)?(?P<subject>.+?) (?:{_ENTERS}|enter)(?P<tapped> tapped)?"
    r" as a copy of (?P<copy_of>.+?)(?:,\s*except\s+(?P<exception>.+?))?\.?$",
    re.IGNORECASE,
)

#: "his name is Superior Spider-Man" - CR 707.9b's name modification. The
#: possessive pronoun is whichever one the card prints; CR 707.9b puts no
#: constraint on it, and Oracle uses "its" for most cards and a gendered
#: pronoun for the ones whose characters have them.
_COPY_EXCEPT_NAME = re.compile(r"^(?:his|her|its|their) name is (?P<name>.+)$", re.IGNORECASE)

#: "he's a 4/4 Spider Human Hero in addition to his other types" - an optional
#: base P/T and a run of gained types. "in addition to ... other types" is
#: CR 205.1b's retaining form, which is why the types are *added* rather than
#: replacing; a clause without it is refused rather than guessed at, since
#: CR 205.1a's replacing form would strip the copied object's own types and no
#: card in the pool prints that shape yet. The power/toughness pair is
#: optional because a land's own exception - Echoing Deeps' "it's a Cave in
#: addition to its other types" - has no body to give one: CR 205.1b's
#: retaining language names only card type/supertype/subtype, and nothing
#: requires a creature's stats to come along with it.
_COPY_EXCEPT_PT_AND_TYPES = re.compile(
    r"^(?:he|she|it|they)(?:'s| is|'re| are) an? (?:(?P<power>\d+)/(?P<toughness>\d+) )?"
    r"(?P<types>[A-Za-z][\w'-]*(?: [A-Za-z][\w'-]*)*) in addition to "
    r"(?:his|her|its|their) other types$",
    re.IGNORECASE,
)


def _parse_copy_exception(clause: str | None) -> CopyException | None:
    """CR 707.9b's "except ..." tail, or `None` if any part of it is unreadable.

    Fail closed, and closed on the *whole* clause: a tail whose first half
    reads and whose second does not would otherwise produce a copy with the
    right name and the wrong body, which is worse than a plain copy. CR 608.2c
    has no notion of running half an instruction, and CR 707.9b's "the final
    set of values ... becomes part of the copiable values" is a single answer,
    not a list of independent edits.

    Split on " and " because that is how the printed tails join their clauses.
    """
    if not clause:
        return None
    name: str | None = None
    power: int | None = None
    toughness: int | None = None
    added_types: list[Type] = []
    added_subtypes: list[str] = []

    for part in re.split(r"\s+and\s+", clause.strip().rstrip(".")):
        part = part.strip()
        if match := _COPY_EXCEPT_NAME.match(part):
            name = match.group("name").strip()
            continue
        if match := _COPY_EXCEPT_PT_AND_TYPES.match(part):
            if match.group("power") is not None:
                power = int(match.group("power"))
                toughness = int(match.group("toughness"))
            for word in match.group("types").split():
                card_type = _CARD_TYPE_WORDS.get(word.lower())
                if card_type is not None:
                    added_types.append(card_type)
                else:
                    # CR 205.3: anything that is not one of CR 300.1's card
                    # types in this position is a subtype - "Spider Human
                    # Hero", stored capitalised the way every subtype is.
                    added_subtypes.append(word)
            continue
        return None

    if name is None and power is None and not added_types and not added_subtypes:
        return None
    return CopyException(
        name=name,
        power=power,
        toughness=toughness,
        added_types=tuple(added_types),
        added_subtypes=tuple(added_subtypes),
    )


_AS_ENTERS = re.compile(
    rf"^As (?P<subject>.+?) {_ENTERS}(?P<also> or is turned face up)?,\s*(?P<effect>.+?)\.?$",
    re.IGNORECASE,
)
# CR 614.1e.
_AS_TURNED_FACE_UP = re.compile(
    r"^As (?P<subject>.+?) is turned face up,\s*(?P<effect>.+?)\.?$", re.IGNORECASE
)

# CR 615.
_PREVENT_NEXT = re.compile(
    r"^Prevent the next (?P<amount>[\w-]+) (?P<combat>combat )?damage that would be dealt"
    r"(?: to (?P<target>.+?))? this turn\.?$",
    re.IGNORECASE,
)
_PREVENT_ALL = re.compile(
    r"^Prevent all (?P<combat>combat )?damage that would be dealt(?P<rest>.*?)\.?$",
    re.IGNORECASE,
)
_PREVENT_NEXT_TIME = re.compile(
    r"^The next time (?P<source>.+?) would deal damage(?P<when>[^,]*),\s*prevent that damage\.?$",
    re.IGNORECASE,
)
_PREVENT_TARGET = re.compile(r"\bto (?P<target>.+?)$", re.IGNORECASE)
_CANT_BE_PREVENTED = re.compile(r"can'?t be prevented", re.IGNORECASE)
#: A back-reference to prevention that already happened, not a new effect.
#: CR 615.5 lets a prevention effect carry an additional effect that refers to
#: the amount prevented; Awe Strike's "You gain life equal to the damage
#: prevented this way" is that clause, and reporting it would be noise.
_PREVENTED_BACKREFERENCE = re.compile(r"\b(damage )?prevented (this way|that way)\b", re.IGNORECASE)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------


def parse_replacement_effects(card: Card) -> list[ReplacementEffect]:
    """Every replacement and prevention effect on a card, all faces included.

    A multifaced card is read face by face and each result carries the face name
    in `face`, so Shatterskull Smashing reports the back face's "As this land
    enters, you may pay 3 life" against `Shatterskull, the Hammer Pass`.
    """
    names = _names_of(card)

    if card.card_faces:
        sources = [(face.name, face.oracle_text or "") for face in card.card_faces]
    else:
        sources = [(None, card.oracle_text or "")]

    effects: list[ReplacementEffect] = []
    for face_name, text in sources:
        effects.extend(_parse_oracle_text(text, face=face_name, names=names))
    return effects


def _names_of(card: Card) -> tuple[str, ...]:
    """Every name the card may refer to itself by, longest first.

    Older templating spells the card's own name out ("Forsaken Crossroads enters
    the battlefield tapped"), and legendary cards use their short name
    ("Kalitas"), so both the full name and its first word count.
    """
    names: list[str] = []
    for name in [card.name, *(face.name for face in card.card_faces or [])]:
        for part in name.split("//"):
            part = part.strip()
            if not part:
                continue
            names.append(part)
            names.append(part.split(",")[0].strip())
    return tuple(sorted(set(names), key=len, reverse=True))


def _parse_oracle_text(
    text: str, face: str | None, names: tuple[str, ...]
) -> list[ReplacementEffect]:
    effects: list[ReplacementEffect] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        rules_text, reminder = strip_reminder_text(paragraph)
        if not rules_text:
            continue

        # CR 603.1: a triggered ability is "[When/Whenever/At] [condition],
        # [effect]. [Instructions (if any).]" - the trailing instructions are
        # part of the trigger, so the whole paragraph belongs to it. Nothing in
        # it is claimed as a static ability's own effect; the one shape read
        # out of it is flagged `from_trigger` and never compiled into
        # behaviour - see `_parse_trigger_effect`.
        if _TRIGGER_OPENER.match(rules_text):
            effects.extend(
                effect.model_copy(update={"raw": paragraph, "reminder": reminder, "face": face})
                for effect in _parse_trigger_effect(rules_text, names)
            )
            continue

        body = _COST_PREFIX.sub("", rules_text)
        sentences = [part.strip() for part in _SENTENCE_SPLIT.split(body) if part.strip()]
        for index, sentence in enumerate(sentences):
            # CR 603.12's reflexive ability is linked to the sentence in front
            # of it and has no existence apart from it, so it is carried on
            # that sentence's effect rather than parsed as one of its own.
            following = sentences[index + 1] if index + 1 < len(sentences) else None
            linked = following if following and _REFLEXIVE_OPENER.match(following) else None
            for effect in _parse_sentence(sentence, names):
                update = {"raw": paragraph, "reminder": reminder, "face": face}
                if linked is not None and effect.kind in ENTERS_KINDS:
                    update["linked_trigger"] = linked
                effects.append(effect.model_copy(update=update))
    return effects


#: "When you do, ..." - CR 603.12's reflexive opener. "When you don't, ..." is
#: the rule's other half ("triggers 'when [a player] [does or doesn't]' take
#: that action") and is admitted here so a card printing it is recognised
#: rather than silently read as an ordinary sentence.
_REFLEXIVE_OPENER = re.compile(r"^When you (?:do|don[’']?t),\s*(?P<effect>.+)$", re.IGNORECASE)


#: A triggered ability's own "[When/Whenever/At] [condition]," opener, split
#: off so what follows can be read as the ability's effect (CR 603.1).
_TRIGGER_CONDITION = re.compile(r"^(?:When|Whenever|At)\b[^,]*,\s*(?P<effect>.+)$", re.IGNORECASE)


def _parse_trigger_effect(rules_text: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """The one shape read out of a triggered ability's effect: "[player] skips ...".

    CR 603.1 keeps the whole paragraph inside the trigger, and this does not
    change that. What it acknowledges is that the trigger's *effect*, once it
    resolves, can itself be a CR 614.1b skip - Brine Elemental's "each opponent
    skips their next untap step" is a real replacement effect, it just does not
    exist until the ability has resolved.

    So exactly one template is tried, and every result is flagged
    `from_trigger`. `parsed_card_replacements` refuses to compile a flagged
    effect, so nothing here can be picked up off the battlefield as a static
    ability - which is the behaviour the CR 603.1 boundary is really protecting.
    Reporting the shape while refusing to perform it is this module's
    honesty-over-coverage rule applied to a trigger.

    Nothing that is *not* a bare "[player] skips ..." is claimed: no `UNPARSED`
    is emitted from a trigger paragraph either, so Forsaken Crossroads' "you may
    untap Forsaken Crossroads instead" and Rest in Peace's "exile all
    graveyards" still come back with nothing, exactly as before.
    """
    match = _TRIGGER_CONDITION.match(rules_text)
    if match is None:
        return []
    found: list[ReplacementEffect] = []
    for sentence in _SENTENCE_SPLIT.split(match.group("effect")):
        sentence = sentence.strip()
        if not sentence:
            continue
        found.extend(
            effect.model_copy(update={"from_trigger": True})
            for effect in _try_player_skips(sentence, names)
        )
    return found


# --------------------------------------------------------------------------
# Sentence dispatch
# --------------------------------------------------------------------------


#: CR 207.2c's ability word, or CR 207.2d's flavor word, as Scryfall prints
#: it: a short capitalised phrase and an em dash in front of the real ability.
#: CR 207.2c: "An ability word appears in italics at the beginning of some
#: abilities ... they have no special rules meaning"; CR 207.2d says the same
#: of a flavor word and adds that they "are not included in Oracle card text"
#: for rules purposes. Bounded to a short run of characters so a sentence that
#: merely contains an em dash is left alone.
#:
#: Written here rather than imported from `machines/targeting.py`'s identical
#: `_ABILITY_WORD_PREFIX`: that one is a private name in a module this one does
#: not otherwise depend on, and reaching across for a one-line regex would
#: couple two parsers that share a rule, not an implementation.
#:
#: Superior Spider-Man is the card that needed it. "Mind Swap — You may have
#: Superior Spider-Man enter as a copy of any creature card in a graveyard..."
#: matched `_ENTERS_AS_COPY` with the flavor word still attached, so `subject`
#: came back as "Mind Swap — You may have Superior Spider-Man" - which made
#: `_refers_to_self` false (the phrase does not start with the card's name)
#: and `optional` false (the sentence does not *start* with "you may have").
#: Both are read off the stripped sentence now.
_ABILITY_WORD_PREFIX = re.compile(r"^[A-Z][^—\n]{0,40}?\s+—\s+")


def _parse_sentence(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """Match one sentence against every template, in precedence order.

    Precedence matters: "enter tapped as a copy of" must be read as a copy
    effect, not an enters-tapped one, and a prevention sentence starting with
    "If ... would" must be read as prevention rather than as a bare "instead".

    A CR 207.2c ability word or CR 207.2d flavor word in front of the sentence
    is cut before any template is tried - neither has rules meaning, and left
    in place both would be swallowed into whichever group the template opens
    with.
    """
    sentence = _ABILITY_WORD_PREFIX.sub("", sentence.strip())
    if _ALTERNATIVE_COST.search(sentence):
        # CR 118.9, not CR 614. Not a replacement effect at all, so it is not
        # reported even as UNPARSED.
        return []

    for parser in (
        _try_prevent_next,
        _try_prevent_all,
        _try_prevent_next_time,
        _try_if_would,
        # "As X enters or is turned face up" must be read by the enters parser
        # first, or the face-up parser swallows "X enters or" as the subject.
        _try_as_enters,
        _try_as_turned_face_up,
        _try_enters_as_copy,
        _try_enters_tapped,
        _try_enters_untapped,
        _try_enters_with,
        _try_skip,
        _try_player_skips,
        _try_instead_of,
        _try_rather_than,
    ):
        found = parser(sentence, names)
        if found:
            return found

    if _CUE.search(sentence) and not _PREVENTED_BACKREFERENCE.search(sentence):
        return [ReplacementEffect(kind=ReplacementKind.UNPARSED, raw=sentence, text=sentence)]
    return []


def _make(kind: ReplacementKind, sentence: str, **fields) -> ReplacementEffect:
    return ReplacementEffect(kind=kind, raw=sentence, text=sentence, **fields)


def _refers_to_self(phrase: str | None, names: tuple[str, ...]) -> bool:
    if not phrase:
        return False
    phrase = phrase.strip().strip('"').lower()
    if _THIS.match(phrase):
        return True
    return any(phrase.startswith(name.lower()) for name in names)


def _is_optional(phrase: str | None) -> bool:
    return bool(phrase) and bool(re.search(r"\byou may\b", phrase, re.IGNORECASE))


def _amount_of(word: str) -> tuple[int | None, bool] | None:
    """Read a templated count. Returns (amount, variable), or None when the
    word is not a count at all.

    A word that is not a count - the "that" a split "that many" leaves, the
    "twice" of "twice that many", the "your" of "your choice of" - is refused,
    never read as CR 107.3m's X: that would take the count from the cast's
    announcement, which has nothing to do with the sentence.
    """
    word = word.strip().lower()
    if word in ("x", "that many", "any number"):
        return None, True
    amount = parse_count(word)
    return None if amount is None else (amount, False)


# --------------------------------------------------------------------------
# Prevention, CR 615
# --------------------------------------------------------------------------


def _try_prevent_next(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _PREVENT_NEXT.match(sentence)
    if not match:
        return []
    read = _amount_of(match.group("amount"))
    if read is None:
        return []
    amount, variable = read
    return [
        _make(
            ReplacementKind.PREVENT_NEXT,
            sentence,
            amount=amount,
            variable_amount=variable,
            combat_only=bool(match.group("combat")),
            damage_target=(match.group("target") or "").strip() or None,
            event=_damage_event(sentence),
        )
    ]


def _try_prevent_all(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _PREVENT_ALL.match(sentence)
    if not match:
        return []
    rest = (match.group("rest") or "").strip()
    target = None
    if rest.startswith("to "):
        target_match = _PREVENT_TARGET.match(rest)
        if target_match:
            target = target_match.group("target").strip()
    return [
        _make(
            ReplacementKind.PREVENT_ALL,
            sentence,
            combat_only=bool(match.group("combat")),
            damage_target=target,
            event=_damage_event(sentence),
        )
    ]


def _damage_event(sentence: str) -> str:
    """The damage description a `Prevent ...` sentence names, minus the verb."""
    return re.sub(r"^Prevent\s+", "", sentence, flags=re.IGNORECASE).rstrip(".").strip()


def _try_prevent_next_time(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _PREVENT_NEXT_TIME.match(sentence)
    if not match:
        return []
    source = match.group("source").strip()
    return [
        _make(
            ReplacementKind.PREVENT_NEXT_TIME,
            sentence,
            event=f"{source} would deal damage{match.group('when')}".strip(),
            subject=source,
            self_replacement=_refers_to_self(source, names),
        )
    ]


# --------------------------------------------------------------------------
# "If ... would ..., ... instead", CR 614.1a
# --------------------------------------------------------------------------


def _try_if_would(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _IF_WOULD.match(sentence)
    if not match:
        return []

    event = match.group("event").strip()
    rest = match.group("rest").strip()

    has_instead = re.search(r"\binstead\b", rest, re.IGNORECASE)
    has_prevent = re.search(r"\bprevent\b", rest, re.IGNORECASE)
    if not has_instead and not has_prevent:
        # "If this card is in your opening hand, you may begin the game with it
        # on the battlefield" has neither, and is not claimed.
        return []
    if _CANT_BE_PREVENTED.search(rest):
        return []

    # "instead" may lead, trail, or sit mid-clause ("you may instead choose").
    # All three mean the same thing; drop the word to get the replacement.
    replacement = re.sub(r"\s*\binstead\b\s*", " ", rest, flags=re.IGNORECASE).strip()
    replacement = re.sub(r"\s{2,}", " ", replacement).rstrip(".").strip()

    kind = ReplacementKind.IF_WOULD_INSTEAD if has_instead else ReplacementKind.PREVENT_IF_WOULD
    return [
        _make(
            kind,
            sentence,
            event=event,
            replacement=replacement or None,
            condition=(match.group("condition") or "").strip() or None,
            optional=_is_optional(rest),
            self_replacement=_refers_to_self(event, names),
        )
    ]


# --------------------------------------------------------------------------
# Entering the battlefield, CR 614.1c / 614.1e
# --------------------------------------------------------------------------


def _try_as_turned_face_up(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _AS_TURNED_FACE_UP.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    return [
        _make(
            ReplacementKind.AS_TURNED_FACE_UP,
            sentence,
            subject=subject,
            replacement=match.group("effect").strip(),
            optional=_is_optional(match.group("effect")),
            self_replacement=_refers_to_self(subject, names),
        )
    ]


def _try_as_enters(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _AS_ENTERS.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    effect = match.group("effect").strip()
    shared = {
        "subject": subject,
        "replacement": effect,
        "optional": _is_optional(effect),
        "self_replacement": _refers_to_self(subject, names),
    }
    found = [_make(ReplacementKind.AS_ENTERS, sentence, **shared)]
    if match.group("also"):
        # Aquamorph Entity folds CR 614.1c and 614.1e into one sentence. It is
        # two replacement effects watching two different events, so report both.
        found.append(_make(ReplacementKind.AS_TURNED_FACE_UP, sentence, **shared))
    return found


def _try_enters_as_copy(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    if " as a copy of " not in sentence.lower():
        return []
    match = _ENTERS_AS_COPY.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    raw_exception = match.group("exception")
    parsed_exception = _parse_copy_exception(raw_exception)
    # `raw_exception` is only truthy when the card actually printed an
    # "except ..." tail. `parsed_exception is None` is ambiguous on its own -
    # see `ReplacementEffect.copy_exception`'s docstring - so the two are
    # combined here, once, into the distinction every downstream reader needs:
    # a tail that existed and did not parse, kept as text rather than dropped.
    unparsed_exception = (
        raw_exception.strip() if raw_exception and parsed_exception is None else None
    )
    return [
        _make(
            ReplacementKind.ENTERS_AS_COPY,
            sentence,
            subject=subject,
            copy_of=match.group("copy_of").strip(),
            copy_exception=parsed_exception,
            copy_exception_unparsed=unparsed_exception,
            tapped=bool(match.group("tapped")),
            optional=sentence.lower().startswith("you may have"),
            self_replacement=_refers_to_self(subject, names),
        )
    ]


def _try_enters_tapped(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _ENTERS_TAPPED.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    condition = match.group("condition") or match.group("unless")
    return [
        _make(
            ReplacementKind.ENTERS_TAPPED,
            sentence,
            subject=subject,
            tapped=True,
            condition=(condition or "").strip() or None,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


def _try_enters_untapped(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _ENTERS_UNTAPPED.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    return [
        _make(
            ReplacementKind.ENTERS_UNTAPPED,
            sentence,
            subject=subject,
            tapped=False,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


def _try_enters_with(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _ENTERS_WITH.match(sentence)
    if not match:
        return []
    subject = match.group("subject").strip()
    what = match.group("what").strip()
    counters = _read_counters(what)
    if counters is None:
        # A counter count this cannot read fails closed as UNPARSED rather
        # than as an enters-with effect with a made-up amount or kind.
        return [ReplacementEffect(kind=ReplacementKind.UNPARSED, raw=sentence, text=sentence)]
    amount, variable, counter_kind, expression = counters
    return [
        _make(
            ReplacementKind.ENTERS_WITH,
            sentence,
            subject=subject,
            replacement=what,
            amount=amount,
            variable_amount=variable,
            counter_kind=counter_kind,
            amount_expression=expression,
            condition=(match.group("condition") or "").strip() or None,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


_COUNTERS = re.compile(r"^(?P<amount>[\w+/-]+) (?P<kind>.+?) counters?$", re.IGNORECASE)

#: "a number of +1/+1 counters on it equal to the greatest mana value among
#: cards in exile" - Ulamog, the Defiler. The count is neither a literal nor
#: CR 107.3m's X: it is an expression evaluated as the permanent enters, which
#: is what `amount_expression` carries and what
#: `_ENTERS_WITH_AMOUNT_RESOLVERS` further down turns into a number. The kind
#: of counter is still plainly readable, so it is read here rather than the
#: whole clause being abandoned to `variable_amount`.
_COUNTERS_EQUAL_TO = re.compile(
    r"^an? number of (?P<kind>.+?) counters?(?: on it)? equal to (?P<expression>.+?)$",
    re.IGNORECASE,
)


def _read_counters(what: str) -> tuple[int | None, bool, str | None, str | None] | None:
    """Read "four +1/+1 counters", "X charge counters", "a shield counter",
    and "a number of +1/+1 counters on it equal to [expression]".

    Returns `(amount, variable, kind, expression)`. Only the last shape fills
    `expression`, and it always leaves `amount` unset and `variable` true - the
    count is not knowable from the text alone.

    Anything more elaborate - Agent's Toolkit enters with four different kinds
    at once - leaves the counter fields empty rather than picking one. A count
    word that is not a count ("that many", "twice that many", "your choice
    of") is None: unreadable, not a variable.
    """
    text = what.strip()
    equal_to = _COUNTERS_EQUAL_TO.match(text)
    if equal_to:
        return None, True, equal_to.group("kind").strip(), equal_to.group("expression").strip()
    match = _COUNTERS.match(text)
    if not match:
        return None, False, None, None
    read = _amount_of(match.group("amount"))
    if read is None:
        return None
    amount, variable = read
    return amount, variable, match.group("kind").strip(), None


# --------------------------------------------------------------------------
# Skip, CR 614.1b
# --------------------------------------------------------------------------


def _try_skip(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _SKIP.match(sentence)
    if not match:
        return []
    skipped = match.group("skipped").strip()
    # CR 614.10: "Skip [something]" is "Instead of doing [something], do
    # nothing", so the skipped thing is the event and there is no replacement.
    return [_make(ReplacementKind.SKIP, sentence, event=skipped)]


def _try_player_skips(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """ "[player] skips [something]" - CR 614.1b's other wording.

    Same rule as the imperative form, said about a named player instead of at
    one, so `subject` carries who is doing the skipping and `event` carries
    what is skipped, exactly as `_try_skip` fills it.
    """
    match = _PLAYER_SKIPS.match(sentence)
    if not match:
        return []
    return [
        _make(
            ReplacementKind.SKIP,
            sentence,
            subject=match.group("who").strip(),
            event=match.group("skipped").strip(),
        )
    ]


# --------------------------------------------------------------------------
# "Instead of" and "rather than"
# --------------------------------------------------------------------------


def _try_instead_of(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    if " instead of " not in sentence.lower() and not sentence.lower().startswith("instead of "):
        return []
    match = _INSTEAD_OF_LEADING.match(sentence) or _INSTEAD_OF_TRAILING.match(sentence)
    if not match:
        return []
    event = match.group("event").strip()
    replacement = match.group("replacement").strip()
    condition = (match.groupdict().get("condition") or "").strip() or None
    return [
        _make(
            ReplacementKind.INSTEAD_OF,
            sentence,
            event=event,
            replacement=replacement,
            condition=condition,
            optional=_is_optional(replacement),
            self_replacement=_refers_to_self(event, names),
        )
    ]


def _try_rather_than(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """ "[replacement] rather than [event]", minus the alternative costs.

    CR 614.1a names "instead" as the replacement keyword, and "rather than" is
    the looser sibling. CR 604.2 says static abilities create continuous
    effects "some of which are prevention effects or replacement effects" -
    some, not all. Doran's "assigns combat damage equal to its toughness rather
    than its power" modifies the combat damage assignment rule of CR 510.1a
    instead of replacing an event. This parser reports the shape and the two
    halves without asserting which it is, which is why it gets its own kind
    rather than being folded into `IF_WOULD_INSTEAD`.
    """
    match = _RATHER_THAN.match(sentence)
    if not match:
        return []
    return [
        _make(
            ReplacementKind.RATHER_THAN,
            sentence,
            event=match.group("event").strip(),
            replacement=match.group("replacement").strip(),
            optional=_is_optional(match.group("replacement")),
        )
    ]


# --------------------------------------------------------------------------
# Convenience
# --------------------------------------------------------------------------


def effects_of_kind(card: Card, *kinds: ReplacementKind) -> list[ReplacementEffect]:
    """Just the effects of the given kinds, in printed order."""
    wanted = set(kinds)
    return [effect for effect in parse_replacement_effects(card) if effect.kind in wanted]


def prevention_effects(card: Card) -> list[ReplacementEffect]:
    """Just the CR 615 prevention effects."""
    return [effect for effect in parse_replacement_effects(card) if effect.is_prevention]


def unparsed_effects(card: Card) -> list[ReplacementEffect]:
    """Sentences that read like replacement effects and could not be parsed."""
    return [effect for effect in parse_replacement_effects(card) if not effect.parsed]


# ==========================================================================
# Applying them
# ==========================================================================
#
# CR 614.1: "replacement effects apply continuously as events happen - they
# aren't locked in ahead of time. Such effects watch for a particular event
# that would happen and completely or partially replace that event."
#
# CR 614.6: "If an event is replaced, it never happens. A modified event occurs
# instead, which may in turn trigger abilities." That is the shape of everything
# below: `Game` builds a `ReplaceableEvent` describing what *would* happen, runs
# it through `apply_replacements`, and then carries out whatever the event says
# afterwards. Nothing is undone, because the original never happened.
#
# CR 616.1 orders competing effects: "If two or more replacement and/or
# prevention effects are attempting to modify the way an event affects an object
# or player, the affected object's controller (or its owner if it has no
# controller) or the affected player chooses one to apply." CR 616.1f then
# repeats the process "taking into account only replacement or prevention
# effects that would now be applicable", and CR 614.5 stops any one effect
# applying twice: "a replacement effect doesn't invoke itself repeatedly; it
# gets only one opportunity to affect an event or any modified events that may
# replace that event."


class EventKind(StrEnum):
    """The events this engine can put through the replacement machinery."""

    #: A permanent is about to enter the battlefield (CR 614.1c, 614.1d, 614.12).
    ENTERS_BATTLEFIELD = "enters_battlefield"
    #: An object is about to move zones (CR 400.6, 400.7). Only moves *to* a
    #: graveyard are raised so far, since that is where the pool's cards watch.
    ZONE_CHANGE = "zone_change"
    #: Damage is about to be dealt to a permanent or a player (CR 119.3, 615.1).
    DAMAGE = "damage"
    #: A permanent is about to be destroyed (CR 701.8a).
    #:
    #: Deliberately narrower than the graveyard move it usually becomes.
    #: CR 701.8b: "The only ways a permanent can be destroyed are as a result
    #: of an effect that uses the word 'destroy' or as a result of the
    #: state-based actions that check for lethal damage (see rule 704.5g) or
    #: damage from a source with deathtouch (see rule 704.5h). If a permanent
    #: is put into its owner's graveyard for any other reason, it hasn't been
    #: 'destroyed.'" So sacrificing, bouncing, the legend rule and CR 704.5f's
    #: toughness of 0 or less raise no `DESTROY` - they are `ZONE_CHANGE`s,
    #: and a destruction-replacement must not save a permanent from them.
    #: CR 704.5f says so in as many words: "Regeneration can't replace this
    #: event."
    #:
    #: This is what CR 614.8's regeneration and umbra armor replace, so the
    #: event is raised *before* the move and carries `replaced` rather than
    #: an amount: there is nothing to reduce, only something to call off.
    DESTROY = "destroy"
    #: A player is about to draw one card (CR 121.1, 121.6, 614.11).
    DRAW = "draw"
    #: A player is about to gain life (CR 119.3).
    GAIN_LIFE = "gain_life"
    #: Counters are about to be put on a permanent (CR 122.1, 122.6).
    ADD_COUNTERS = "add_counters"
    #: One or more tokens are about to be created (CR 111.1, 701.7a, 701.7b).
    #:
    #: Raised *before* anything is put onto the battlefield, which is the whole
    #: point of the event: CR 701.7b says "if a replacement effect applies to a
    #: token being created, that effect applies before considering any continuous
    #: effects that will modify the characteristics of that token", and it draws
    #: the line against the second sentence of the same rule - a replacement
    #: effect that applies to a token *entering the battlefield* applies after
    #: them, and is an `ENTERS_BATTLEFIELD` event like any other permanent's.
    #:
    #: `player` is the player who would create them (CR 111.2: "the player who
    #: creates a token is its owner"), and `amount` is how many.
    CREATE_TOKENS = "create_tokens"


@dataclass
class ReplaceableEvent:
    """One event on its way to happening, as replacement effects see it.

    Mutable on purpose: applying a replacement effect *is* editing this object.
    CR 614.6 says the original event never happens and a modified one happens in
    its place, so there is only ever one event here - the current version of it.

    `Game` reads the fields back after `apply_replacements` returns and does what
    they now say.
    """

    kind: EventKind

    #: The object the event affects, when it is an object.
    card: CardState | None = None
    #: The player the event affects, when it is a player.
    player: "Player | None" = None
    #: Where the object is going, for a zone change or an entering permanent.
    destination: Zone | None = None
    #: Where it is coming from, as CR 400.6 asks.
    origin: Zone | None = None

    #: How much: damage, life, cards drawn, counters placed.
    amount: int = 0
    #: The counter kind being placed, for `ADD_COUNTERS`.
    counter_kind: str | None = None
    #: Counters the entering permanent will arrive with (CR 614.1c), summed by
    #: kind. `Game` places them after the permanent is on the battlefield, which
    #: raises its own `ADD_COUNTERS` event - CR 616.1g's "event contained within
    #: the first event", and what lets Doubling Season see them (CR 122.6).
    counters: dict[str, int] = field(default_factory=dict)
    #: Whether the permanent arrives tapped (CR 614.1c).
    tapped: bool = False

    #: The object dealing the damage (CR 120.1, CR 120.7). `None` when the
    #: caller did not say - CR 609.7b, CR 615.8 and CR 702.16e all ask about the
    #: source's properties, and an anonymous source has none to check, so they
    #: simply do not apply rather than applying to everything.
    source: CardState | None = None

    #: True when the permanent got here by resolving as a spell. Containment
    #: Priest asks (CR 601.2 defines what casting is).
    was_cast: bool = True
    #: True while combat damage is being dealt (CR 510.2).
    combat: bool = False
    #: True for the draw an active player takes as the draw step's turn-based
    #: action (CR 504.1, 703.4d). Alhammarret's Archive excepts exactly that one.
    draw_step_draw: bool = False
    #: True only for a spell's own successful CR 608 resolution reaching the
    #: graveyard - not a countered spell (CR 701.6, which never resolves at
    #: all) and not a fizzled one (CR 608.2b: "it doesn't resolve"), both of
    #: which move a card off the stack through this same `ZONE_CHANGE` event.
    #: CR 702.88a's rebound reads "instead of putting it into your graveyard
    #: **as it resolves**" - narrower than flashback's "any time it would
    #: leave the stack" (CR 702.34a), which is why flashback's own entry in
    #: `_stack_replacements` does not gate on this at all and rebound's does.
    resolving: bool = False

    #: False when the effect causing this `DESTROY` printed "can't be
    #: regenerated" (Wrath of God's "Destroy all creatures. They can't be
    #: regenerated.").
    #:
    #: CR 701.19c states the prohibition in exactly these terms: "Effects that
    #: say that a permanent can't be regenerated don't preclude such abilities
    #: from being activated or such spells from being cast; rather, they cause
    #: regeneration shields to **not be applied**." So it belongs on the
    #: destruction event, not on the permanent - a shield the sweeper ignored
    #: is still standing afterwards for the next destruction this turn, which
    #: a flag stamped on the creature would silently have spent.
    #:
    #: This is CR 608.2c's own worked example of a rider modifying its
    #: antecedent rather than running after it: "In some cases, later text on
    #: the card may modify the meaning of earlier text (for example, 'Destroy
    #: target creature. It can't be regenerated' ...)".
    regeneration_allowed: bool = True

    #: What the tokens being created are, for `CREATE_TOKENS` (CR 111.3).
    #:
    #: Without it the event says only *how many*, which is enough for Doubling
    #: Season ("twice that many of **those** tokens") and not enough for
    #: anything that asks what kind - Stridehangar Automaton watches for
    #: "artifact tokens" specifically, and cannot tell one from a Saproling
    #: without this. `None` for a token *copy*, whose characteristics come from
    #: a printed card rather than a definition (CR 707.2); `card` carries the
    #: original in that case, and is the thing to read instead.
    definition: TokenDefinition | None = None
    #: Tokens a replacement effect added to a `CREATE_TOKENS` event that are
    #: *not* more of `definition` - Stridehangar Automaton's "those tokens plus
    #: an additional 1/1 ... Thopter ... are created instead".
    #:
    #: Kept apart from `amount` because CR 614.6's modified event really is one
    #: creation of two different kinds of token, not two creations: they are
    #: created by draining this list inside the same `create_tokens` call, with
    #: no second `CREATE_TOKENS` event raised for them. Raising one would let
    #: the same permanent's effect apply again to its own addition, which
    #: CR 614.5 forbids ("it gets only one opportunity to affect an event or
    #: any modified events that may replace that event") and which would not
    #: terminate.
    extra: list[TokenDefinition] = field(default_factory=list)

    #: A `DESTROY` that a replacement effect called off (CR 614.8, CR 701.8c).
    #: The destruction simply does not happen; the permanent stays where it is.
    replaced: bool = False

    #: The keys of the effects that have already applied (CR 614.5).
    applied: set[str] = field(default_factory=set)
    #: A human-readable trace of what applied, in order. Scenario tests assert
    #: on outcomes, not on this - it exists so a failure says *why*.
    history: list[str] = field(default_factory=list)

    @property
    def happens(self) -> bool:
        """False when the event was replaced with nothing at all.

        Damage prevented down to zero (CR 615.1a) and a draw replaced by
        something else both land here.
        """
        if self.kind is EventKind.DAMAGE:
            return self.amount > 0
        if self.kind is EventKind.DESTROY:
            return not self.replaced
        return True

    def chooser(self, game: "Game") -> str | None:
        """Who orders the applicable effects (CR 616.1).

        "The affected object's controller (or its owner if it has no controller)
        or the affected player." An object on the stack or the battlefield has a
        controller (CR 109.4); anywhere else, fall back to the owner.
        """
        if self.player is not None:
            return self.player.username
        if self.card is None:
            return None
        if self.card.controller:
            return self.card.controller
        owner = game.find_owner(self.card)
        return owner.username if owner is not None else None


#: A test for whether one printed effect applies to an event, and what it does.
#: The source is `None` for an effect with no permanent behind it - a prevention
#: shield created by a spell that has long since resolved (CR 615.1, 615.4).
Applies = Callable[["Game", CardState, ReplaceableEvent], bool]
Apply = Callable[["Game", CardState | None, ReplaceableEvent], None]


@dataclass(frozen=True)
class CardReplacement:
    """One replacement or prevention effect a named card generates."""

    #: Which sentence on the card this is, for the trace and for the CR 614.5 key.
    label: str
    applies: Applies
    apply: Apply


@dataclass(frozen=True)
class ApplicableEffect:
    """One effect that could apply to the event in front of it right now."""

    #: Unique per (source permanent, printed effect). CR 614.5 keys off this, so
    #: two copies of Rest in Peace are two effects and one of them is two.
    key: str
    source: CardState | None
    label: str
    apply: Apply
    #: Who the effect belongs to when there is no source permanent to ask.
    #: A prevention shield (CR 615.1) outlives the object that made it, so the
    #: controller is recorded when the shield is created and carried here.
    controller_username: str | None = None

    #: CR 616.1c: "If any of the replacement and/or prevention effects would
    #: cause an object to become a copy of another object as it enters the
    #: battlefield, one of them must be chosen." True for exactly those, which
    #: is what `order_effects` puts first - the choice is forced, not free.
    copy_as_it_enters: bool = False

    @property
    def controller(self) -> str:
        if self.source is not None:
            return self.source.controller or ""
        return self.controller_username or ""

    @property
    def name(self) -> str:
        """What to call this in the event trace."""
        return self.source.name if self.source is not None else "the game"


# --------------------------------------------------------------------------
# The registry
# --------------------------------------------------------------------------
#
# Keyed by card name, the same way `machines/effects.py` is, and for the same
# reason: parsing "exile it instead" tells you the sentence is a replacement
# effect, not what to do about it. A card with no entry here generates no
# replacement effect, however clearly its text reads.


def _is_opponent(game: "Game", one: str | None, other: str | None) -> bool:
    return bool(one) and bool(other) and one != other


def _owner_username(game: "Game", card: CardState) -> str | None:
    owner = game.find_owner(card)
    return owner.username if owner is not None else card.controller


def _to_graveyard(event: ReplaceableEvent) -> bool:
    return event.kind is EventKind.ZONE_CHANGE and event.destination is Zone.GRAVEYARD


def _exile_instead(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "...exile it instead" - the card goes to exile and never reaches a graveyard."""
    event.destination = Zone.EXILE


def _shuffle_into_library_instead(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "Shuffle <name> into its owner's library" - the card goes to its
    owner's library instead of a graveyard. `Game.put_into_graveyard` reads
    this destination and does the actual move-and-shuffle (CR 701.24a/c).
    """
    event.destination = Zone.LIBRARY


#: "Shuffle <card's own name> into its owner's library." (Green Sun's Zenith).
#: Deliberately not one of `_parse_oracle_text`'s generic "instead" shapes:
#: this sentence never says "instead", it is CR 304.2/307.2's own final
#: graveyard step being pre-empted by an earlier one-shot effect that already
#: moved the object - the same reason flashback/rebound/adventure below are
#: hand-read here rather than through the generic replacement-effect parser.
_SELF_SHUFFLE_INTO_LIBRARY_RE = re.compile(
    r"shuffle (?P<name>.+?) into its owner'?s library", re.IGNORECASE
)


def _graveyard_replacer(label: str, whose: Callable[["Game", CardState, CardState], bool]):
    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return _to_graveyard(event) and event.card is not None and whose(game, source, event.card)

    return CardReplacement(label=label, applies=applies, apply=_exile_instead)


def _any_graveyard(game: "Game", source: CardState, card: CardState) -> bool:
    return True


def _opponents_graveyard(game: "Game", source: CardState, card: CardState) -> bool:
    return _is_opponent(game, _owner_username(game, card), source.controller)


def _your_graveyard(game: "Game", source: CardState, card: CardState) -> bool:
    return _owner_username(game, card) == source.controller


def _black_or_red(game: "Game", source: CardState, card: CardState) -> bool:
    """ "...a black or red permanent...would be put into a graveyard...".

    A permanent still on the battlefield at this point (`card.zone` has not
    moved yet - the event it is part of has not happened, CR 614.6) reads its
    *computed* colours (CR 613.5, CR 613.1e): a layer-5 effect can make a
    permanent red or black on the way to its own death just as easily as one
    can make a land a creature (CR 613.1d). A card anywhere else - a spell on
    the stack, a card in a library - has no continuous effect to ask about, so
    its printed colours are the only answer there is.
    """
    colors = game.characteristics_of(card).colors if card.zone is Zone.BATTLEFIELD else card.colors
    return Color.BLACK in colors or Color.RED in colors


def _kalitas_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "If a nontoken creature an opponent controls would die..."

    CR 700.4: "dies" is "put into a graveyard from the battlefield", so both the
    origin and the destination are part of the condition. "Nontoken" is a real
    condition now that tokens exist (CR 111.1, CR 111.6: "a token isn't a card"),
    and it matters: a token creature that Kalitas exiled instead of letting it
    die would never trigger a dies trigger, and CR 111.7's parenthesis says it
    should.

    The dying object is still on the battlefield at this point (the move to
    the graveyard is exactly the event being checked, CR 614.6), so its
    *computed* types (CR 613.5, CR 613.1d) are what "creature" asks about - a
    land earthbend (CR 701.66a) already made a creature is a creature dying
    here, whatever its printed type line still says.
    """
    card = event.card
    if card is None:
        return False
    types = game.characteristics_of(card).types if card.zone is Zone.BATTLEFIELD else card.types
    return (
        _to_graveyard(event)
        and event.origin is Zone.BATTLEFIELD
        and not is_token(card)
        and Type.CREATURE in types
        and _is_opponent(game, card.controller, source.controller)
    )


def _containment_priest_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "If a nontoken creature would enter and it wasn't cast, exile it instead."

    "Nontoken" is enforced (CR 111.1, CR 111.6). A token exiled by this would be
    a token in a zone other than the battlefield, which CR 704.5d would make
    cease to exist - the card deliberately does not do that, and now neither does
    the engine.
    """
    card = event.card
    return (
        event.kind is EventKind.ENTERS_BATTLEFIELD
        and not event.was_cast
        and card is not None
        and not is_token(card)
        and Type.CREATURE in card.types
    )


def _scale_amount(multiplier: int = 1, addend: int = 0) -> Apply:
    """ "twice that many", "three times that many", "that many plus one",
    "that many minus one", "that much life plus 1" - one replacement, read as
    data: the event's count times `multiplier`, plus `addend`.

    CR 614.5 gives each effect one opportunity at the event, so the addend is
    flat rather than per unit. CR 107.1b: "If a calculation that would
    determine the result of an effect yields a negative number, zero is used
    instead" - a "minus one" on a single counter leaves none, never fewer.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        event.amount = max(event.amount * multiplier + addend, 0)

    return apply


def _archive_life_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    return (
        event.kind is EventKind.GAIN_LIFE
        and event.player is not None
        and event.player.username == source.controller
    )


def _archive_draw_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "...except the first one you draw in each of your draw steps."

    CR 121.6a applies a draw replacement "even if no cards could be drawn", so
    an empty library is not a reason to skip it.
    """
    return (
        event.kind is EventKind.DRAW
        and not event.draw_step_draw
        and event.player is not None
        and event.player.username == source.controller
    )


def _draw_two(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "...draw two cards instead."

    One draw becomes two - and on an event another permanent has *already*
    modified, one more. CR 614.5: "A replacement effect doesn't invoke itself
    repeatedly; it gets only one opportunity to affect an event **or any
    modified events that may replace that event**." A second permanent with the
    same printed line is a second effect, so it gets its own opportunity
    against the modified event; CR 121.2 makes "draw two cards" two individual
    draws, and this effect replaces exactly one of them with two. That is
    `+= 1`, and on the unmodified single draw `+= 1` is plainly "draw a card"
    becoming "draw two cards".

    Written as an increment rather than `= 2` for exactly that reason: `= 2`
    made a second Alhammarret's Archive a no-op, which is CR 614.5 read
    backwards.
    """
    event.amount += 1


def _draw_plus(amount: int) -> Apply:
    """ "...you draw that many cards plus [N] instead." (Quantum Riddler.)

    CR 121.2a: "An instruction to draw multiple cards can be modified by
    replacement effects that refer to the number of cards drawn. This
    modification occurs before considering any of the individual card draws."
    This is one of those - it reads "that many" off the event - so it adds to
    whatever count the event currently carries.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        event.amount += amount

    return apply


def _counter_amount_applies(
    kind: str | None, types: frozenset[Type] | None, you_control: bool
) -> Applies:
    """ "If one or more [kind] counters would be put on [a creature] [you control]..."

    CR 122.6: "counters being put on an object ... refers to putting counters on
    that object while it's on the battlefield and also to an object that's given
    counters as it enters the battlefield", which is why the enters-with
    counters of CR 614.1c reach this too.

    `kind` None is "one or more counters" of any kind; `types` None is "a
    permanent". A permanent already on the battlefield reads its computed types
    (CR 613.5) - a land earthbend (CR 701.66a) made a creature is a creature
    you control, whatever it prints.
    """

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.ADD_COUNTERS or event.amount <= 0:
            return False
        card = event.card
        if card is None:
            return False
        if you_control and card.controller != source.controller:
            return False
        if kind is not None and (event.counter_kind or "").strip().lower() != kind:
            return False
        if types is None:
            return True
        card_types = (
            game.characteristics_of(card).types if card.zone is Zone.BATTLEFIELD else card.types
        )
        return any(wanted in card_types for wanted in types)

    return applies


def _fog_bank_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "Prevent all combat damage that would be dealt to and dealt by this creature."

    Both halves now. CR 120.1 makes "an object that deals damage ... the source
    of that damage" and the damage event carries that object, so "dealt by this
    creature" is a comparison against `event.source` exactly as "dealt to this
    creature" is one against `event.card`.

    The "dealt by" half only fires for a caller that says who is dealing the
    damage. `machines/combat.py` does not yet, and Fog Bank's power is 0, so the
    half remains invisible in play - see `docs/engine-coverage.md`.
    """
    if event.kind is not EventKind.DAMAGE or not event.combat:
        return False
    dealt_to = event.card is not None and event.card.id == source.id
    dealt_by = event.source is not None and event.source.id == source.id
    return dealt_to or dealt_by


def _prevent_all(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """CR 615.1a: prevention says what damage will *not* be dealt."""
    event.amount = 0


def _exile_and_gain_two_life(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """The Darkness Crystal's "instead exile it and you gain 2 life".

    One replacement effect with two halves, so both happen as the event is
    replaced: the card goes to exile rather than a graveyard (CR 614.6 - the
    original event never happens, so it never died, CR 700.4), and the Crystal's
    controller gains the 2. The gain is routed through `Game.gain_life` so it
    is a life-gain event of its own, which is what CR 119.10 needs it to be -
    "Some replacement effects are written, 'If [a player] would gain life,
    . . . .' Such abilities are treated as though they are written, 'If a
    source would cause [a player] to gain life, . . . .'" - and an Alhammarret's
    Archive watching still doubles it.
    """
    _exile_instead(game, source, event)
    if source.controller is not None:
        game.gain_life(source.controller, 2)


def _adamantoise_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "All damage that would be dealt to you and **other** permanents you
    control is dealt to this creature instead."

    CR 614.9: "Some effects replace damage dealt to one creature, planeswalker,
    battle, or player with the same damage dealt to another ...; such effects
    are called redirection effects." Both halves of the "and" are one clause
    about who the damage was aimed at, so a player and a permanent are checked
    the same way, against the source's controller.

    "Other" excludes the Adamantoise itself, which is also what stops this
    recursing: the redirected damage is aimed at the source, and the source is
    never "other" than itself.
    """
    if event.kind is not EventKind.DAMAGE or event.amount <= 0:
        return False
    controller = source.controller
    if controller is None:
        return False
    if event.player is not None:
        return event.player.username == controller
    if event.card is not None:
        return event.card.controller == controller and event.card.id != source.id
    return False


def _redirect_damage_to_the_source(
    game: "Game", source: CardState, event: ReplaceableEvent
) -> None:
    """Deal the damage to the redirecting permanent instead (CR 614.9).

    **A stand-in, and worth saying so.** A true redirection rewrites *who* the
    event affects, but `Game.deal_damage` reads its own `target` argument back
    after `apply_replacements` returns rather than reading `event.card` /
    `event.player`, so changing them here would be ignored. What this does
    instead is zero the original event - CR 614.6's "the original event never
    happens" - and deal the same damage to the source as its own event, which
    reaches the same board state and keeps the redirected damage subject to the
    Adamantoise's own protection, prevention shields and damage-dealt triggers.

    The difference that remains is bookkeeping, not board state: the original
    event's history reads as replaced-to-nothing rather than as retargeted.
    Making `Game.deal_damage` read the event's target back is the real fix and
    belongs in `models/game.py`.
    """
    amount = event.amount
    event.amount = 0
    game.deal_damage(source, amount, source=event.source)


#: Every replacement or prevention effect the engine can actually perform,
#: keyed by card name. A card may generate more than one.
#
# A card only lives here when its text mixes something this module's generic
# parsers below cannot execute with something they can - so a generic parser
# would either under-execute it (silently dropping the part it cannot do,
# which the fail-closed rule below forbids) or need to special-case it anyway.
#
# "Rest in Peace", "Leyline of the Void", "Necrodominance", and "Sanctifier
# en-Vec" are not entered here any more: all four are exactly
# `_compile_graveyard_exile`'s "if [quality] would be put into [whose]
# graveyard, exile it instead" shape, read off each card's own oracle text, so
# `replacements_of`'s fallback reaches them (and any future card with the same
# shape, for free). See `test_replacement_registry_is_minimal.py`.
#
# "Containment Priest" is not entered here either: "if a nontoken creature
# would enter and it wasn't cast, exile it instead" is
# `_compile_enters_uncast_exile`'s shape.
#
# "Alhammarret's Archive" is not entered here either: its life-gain line is
# `_compile_life_gain_doubler`'s "if you would gain life, you gain twice that
# much life instead" shape, and its draw line is
# `_compile_draw_doubler_except_draw_step`'s shape.
#
# "Doubling Season" is not entered here either: both of its lines are
# `_compile_token_doubler`'s and `_compile_counter_doubler`'s "if an effect
# would [create tokens|put counters], it [does] twice that [much] instead"
# shapes.
#
# "Fog Bank" is not entered here either: "prevent all combat damage that would
# be dealt to and dealt by this creature" is
# `_compile_self_prevent_combat_damage`'s shape.
REPLACEMENTS: dict[str, list[CardReplacement]] = {
    "Kalitas, Traitor of Ghet": [
        CardReplacement(
            label="if a nontoken creature an opponent controls would die",
            applies=_kalitas_applies,
            apply=_exile_instead,
        )
    ],
    # Kalitas's shape plus a life gain the generic compilers deliberately
    # refuse to half-read (see the fail-closed note below), so it is written
    # out here in full instead.
    "The Darkness Crystal": [
        CardReplacement(
            label="instead exile it and you gain 2 life",
            applies=_kalitas_applies,
            apply=_exile_and_gain_two_life,
        )
    ],
    "Ancient Adamantoise": [
        CardReplacement(
            label=(
                "all damage that would be dealt to you and other permanents "
                "you control is dealt to this creature instead (CR 614.9)"
            ),
            applies=_adamantoise_applies,
            apply=_redirect_damage_to_the_source,
        )
    ],
}


# --------------------------------------------------------------------------
# Generic shapes, parsed off oracle text
# --------------------------------------------------------------------------
#
# `REPLACEMENTS` above is a hand-written registry for the same reason
# `machines/effects.py`'s `EFFECTS` is: parsing a sentence into a
# `ReplacementEffect` tells you its shape, not what to do about it. The
# functions below close that gap for the shapes common enough to template -
# each reads a card's *parsed* effects (`parse_replacement_effects`, above)
# and, when one matches a known wording exactly, compiles it straight into a
# `CardReplacement` with no row needed. `replacements_of` only reaches these on
# a `REPLACEMENTS` miss, exactly as `effect_for` treats `EFFECTS`.
#
# **Fail-closed.** Every compiler below matches the *whole* event or
# replacement clause (`==`, or a `fullmatch`-shaped `re.match(...)$`), never a
# prefix or a substring search over it. A card whose wording almost matches but
# adds a clause these compilers do not read - Kalitas's token creation, The
# Darkness Crystal's extra life gain - fails every compiler and produces no
# `CardReplacement` at all, rather than running the part that does match and
# silently dropping the rest.


def _mill(game: "Game", player: "Player", count: int) -> None:
    """CR 701.17a: put that many cards from the top of the library into the
    graveyard, routed through `Game.put_into_graveyard` so a graveyard
    replacement effect - this module's own `_compile_graveyard_exile`, or a
    hand-written row - still gets first look at each one (CR 614.1a). The same
    call `machines/effects.py`'s own `_mill` makes for a spell that mills
    directly.
    """
    for card_state in list(player.library[:count]):
        game.put_into_graveyard(card_state)


# -- "if [quality] would be put into [whose] graveyard, exile it instead" --

#: The event clause's shape once `_try_if_would` has split it off the "If ...,"
#: sentence - see `parse_replacement_effects`'s doctable, `IF_WOULD_INSTEAD`.
_GRAVEYARD_EVENT_RE = re.compile(
    r"^(?P<quality>.+?) would be put into (?P<whose>a|your|an opponent's) graveyard"
    r"(?: from anywhere)?$",
    re.IGNORECASE,
)

#: Only these two qualities are read - "any card" and "a black or red one" -
#: because those are the only ones this module can safely apply without
#: reading the rest of the quality clause (an artifact, a creature, mana value
#: 3 or less, ...). Anything else is a real gap this parser reports honestly by
#: matching nothing, rather than exiling regardless of the quality it cannot
#: check.
_GRAVEYARD_QUALITY_RE = re.compile(
    r"^a (?:card|card or token)$"
    r"|^a black or red (?:card|permanent, spell, or card not on the battlefield)$",
    re.IGNORECASE,
)


def _graveyard_owner_matcher(
    whose: str,
) -> Callable[["Game", CardState, CardState], bool] | None:
    whose = whose.strip().lower()
    if whose in ("a", "an"):
        return _any_graveyard
    if whose == "your":
        return _your_graveyard
    if "opponent" in whose:
        return _opponents_graveyard
    return None


def _compile_graveyard_exile(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "exile it":
        return None
    match = _GRAVEYARD_EVENT_RE.match((effect.event or "").strip())
    if match is None:
        return None
    owner = _graveyard_owner_matcher(match.group("whose"))
    if owner is None:
        return None
    quality = match.group("quality").strip()
    if not _GRAVEYARD_QUALITY_RE.match(quality):
        return None
    color_restricted = quality.lower().startswith("a black or red")

    def whose(game: "Game", source: CardState, card: CardState) -> bool:
        if color_restricted and not _black_or_red(game, source, card):
            return False
        return owner(game, source, card)

    return _graveyard_replacer(effect.text, whose)


# -- "if a nontoken creature would enter and it wasn't cast, exile it instead" --

_ENTERS_UNCAST_EVENT_RE = re.compile(
    r"^a nontoken creature would enter and it wasn.?t cast$", re.IGNORECASE
)


def _compile_enters_uncast_exile(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "exile it":
        return None
    if not _ENTERS_UNCAST_EVENT_RE.match((effect.event or "").strip()):
        return None
    return CardReplacement(
        label=effect.text, applies=_containment_priest_applies, apply=_exile_instead
    )


# -- "if a source would deal damage ..., it deals double/triple that damage ... instead" --

#: CR 701.10g: "To double an amount of damage a source would deal, that source
#: instead deals twice that much damage. This is a replacement effect." Tripling
#: reads the same way (Fiery Emancipation-shaped cards), one word different.
_DAMAGE_MULTIPLIER_RE = re.compile(
    r"^it deals (?P<mult>double|triple) that damage to that permanent or player$", re.IGNORECASE
)
_DAMAGE_MULTIPLIERS = {"double": 2, "triple": 3}


def _compile_damage_multiplier(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    expected_event = "a source would deal damage to a permanent or player"
    if (effect.event or "").strip().lower() != expected_event:
        return None
    match = _DAMAGE_MULTIPLIER_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    factor = _DAMAGE_MULTIPLIERS[match.group("mult").lower()]

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return event.kind is EventKind.DAMAGE

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount *= factor

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


#: "If a source you control would deal noncombat damage to an opponent or a
#: permanent an opponent controls, it deals that much damage plus [N]
#: instead." - Artist's Talent's own level-3 (CR 716.2a), the Torbran-shaped
#: template minus Torbran's own color qualifier. Read generically off the
#: amount rather than pinned to this one printing.
_DAMAGE_PLUS_AMOUNT_RE = re.compile(r"^it deals that much damage plus (?P<amount>\d+)$")

_DAMAGE_PLUS_AMOUNT_EVENT = (
    "a source you control would deal noncombat damage to an opponent or a "
    "permanent an opponent controls"
)


def _compile_damage_plus_amount(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.event or "").strip().lower() != _DAMAGE_PLUS_AMOUNT_EVENT:
        return None
    match = _DAMAGE_PLUS_AMOUNT_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    amount = int(match.group("amount"))

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DAMAGE or event.combat:
            return False  # "noncombat damage" (CR 510.2 marks combat damage).
        if event.source is None:
            return False
        source_controller = game.controller_of(source).username
        if game.controller_of(event.source).username != source_controller:
            return False  # "a source *you* control".
        if event.player is not None:
            return _is_opponent(game, source_controller, event.player.username)
        if event.card is not None:
            return _is_opponent(game, source_controller, game.controller_of(event.card).username)
        return False

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.amount += amount

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- "if [damage event], prevent that damage and [someone] mill[s] [N] that many cards" --

#: Two known event templates: a source's controller's own damage to an
#: opponent (The Mindskinner), and damage aimed at the effect's own controller
#: (Angel of Suffering). Each pins down who mills, which is why the compiler
#: below rejects a `subject` word that does not match its own template rather
#: than guessing.
_PREVENT_AND_MILL_RE = re.compile(
    r"^prevent that damage and (?:(?P<subject>each opponent|you) )?"
    r"mills? (?P<mult>twice )?that many cards$",
    re.IGNORECASE,
)


def _compile_prevent_damage_and_mill(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.PREVENT_IF_WOULD:
        return None
    match = _PREVENT_AND_MILL_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    multiplier = 2 if match.group("mult") else 1
    subject = (match.group("subject") or "").strip().lower()
    event_text = (effect.event or "").strip().lower()

    if event_text == "damage would be dealt to you" and subject in ("", "you"):

        def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                event.kind is EventKind.DAMAGE
                and event.player is not None
                and event.player.username == source.controller
            )

        def millers(game: "Game", source: CardState, event: ReplaceableEvent) -> list["Player"]:
            return [] if event.player is None else [event.player]

    elif (
        event_text == "a source you control would deal damage to an opponent"
        and subject == "each opponent"
    ):

        def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                event.kind is EventKind.DAMAGE
                and event.source is not None
                and event.source.controller == source.controller
                and event.player is not None
                and _is_opponent(game, event.player.username, source.controller)
            )

        def millers(game: "Game", source: CardState, event: ReplaceableEvent) -> list["Player"]:
            return [
                player
                for player in game.players_in_game
                if _is_opponent(game, player.username, source.controller)
            ]

    else:
        return None

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        amount = event.amount
        event.amount = 0
        for player in millers(game, source, event):
            _mill(game, player, amount * multiplier)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- "prevent all combat damage that would be dealt to and dealt by this creature" --

_SELF_PREVENT_COMBAT_RE = re.compile(
    r"^prevent all combat damage that would be dealt to and dealt by this creature$", re.IGNORECASE
)


def _compile_self_prevent_combat_damage(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.PREVENT_ALL:
        return None
    if not _SELF_PREVENT_COMBAT_RE.match(effect.text.strip().rstrip(".")):
        return None
    return CardReplacement(label=effect.text, applies=_fog_bank_applies, apply=_prevent_all)


# -- "if you would gain life, you gain twice that much life instead" /
#    "... you gain that much life plus 1 instead" --

#: Alhammarret's Archive's "twice that much life", Angel of Vitality's "that
#: much life plus 1". The number is read, never pinned (CR 107.1: integers).
_LIFE_GAIN_AMOUNT_RE = re.compile(
    rf"^you gain (?:(?P<mult>{MULTIPLIER}) that much life|that much life plus (?P<plus>{COUNT}))$",
    re.IGNORECASE,
)


def _compile_life_gain_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.event or "").strip().lower() != "you would gain life":
        return None
    match = _LIFE_GAIN_AMOUNT_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    if match.group("mult") is not None:
        multiplier = parse_multiplier(match.group("mult"))
        if multiplier is None:
            return None
        apply = _scale_amount(multiplier=multiplier)
    else:
        addend = parse_count(match.group("plus"))
        if addend is None:
            return None
        apply = _scale_amount(addend=addend)
    return CardReplacement(label=effect.text, applies=_archive_life_applies, apply=apply)


# -- "if you would draw a card except the first ... in each of your draw
#     steps, draw two cards instead" --


def _compile_draw_doubler_except_draw_step(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    expected_event = (
        "you would draw a card except the first one you draw in each of your draw steps"
    )
    if (effect.event or "").strip().lower() != expected_event:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "draw two cards":
        return None
    return CardReplacement(label=effect.text, applies=_archive_draw_applies, apply=_draw_two)


# -- "if you would draw a card, draw two cards instead" (no exception clause) --


def _controllers_draw(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    return (
        event.kind is EventKind.DRAW
        and event.player is not None
        and event.player.username == source.controller
    )


def _compile_draw_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    """Thought Reflection's plain wording - every draw, the draw step included.

    Alhammarret's Archive's own line is the same sentence with an "except the
    first one you draw in each of your draw steps" carved out of the event, and
    it has its own compiler above; the two never both claim a sentence, because
    each matches the whole event clause exactly.
    """
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.event or "").strip().lower() != "you would draw a card":
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "draw two cards":
        return None
    return CardReplacement(label=effect.text, applies=_controllers_draw, apply=_draw_two)


# -- "[as long as ...,] if you would draw one or more cards, you draw that many
#     cards plus [N] instead" --

#: Quantum Riddler's event clause. CR 121.2a's "replacement effects that refer
#: to the number of cards drawn" is exactly this wording, and it is what makes
#: the Riddler's effect have to be applied before Thought Reflection's - see
#: `tests/scenarios/judge/test_judge_draw_replacements.py`.
_DRAW_ONE_OR_MORE_EVENT = "you would draw one or more cards"
_DRAW_PLUS_RE = re.compile(r"^you draw that many cards plus (?P<amount>[\w-]+)$", re.IGNORECASE)

#: "As long as you have one or fewer cards in hand" - the only "as long as"
#: qualifier this module reads. Anything else leaves the effect uncompiled.
_FEWER_CARDS_IN_HAND_RE = re.compile(
    r"^you have (?P<count>[\w-]+) or fewer cards in hand$", re.IGNORECASE
)


def _compile_draw_plus(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.event or "").strip().lower() != _DRAW_ONE_OR_MORE_EVENT:
        return None
    match = _DRAW_PLUS_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    amount = parse_count(match.group("amount"))
    if amount is None:
        return None

    hand_limit: int | None = None
    if effect.condition is not None:
        condition = _FEWER_CARDS_IN_HAND_RE.match(effect.condition.strip().rstrip(","))
        if condition is None:
            return None  # an "as long as" clause this cannot check - fail closed.
        hand_limit = parse_count(condition.group("count"))
        if hand_limit is None:
            return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if not _controllers_draw(game, source, event):
            return False
        if hand_limit is None:
            return True
        # CR 604.2: the continuous effect exists only while the "as long as"
        # clause is true, and it is checked as the event happens.
        assert event.player is not None
        return len(event.player.hand) <= hand_limit

    return CardReplacement(label=effect.text, applies=applies, apply=_draw_plus(amount))


# -- "if [an effect would create] one or more [type] tokens [would be created]
#    under your control, [N times that many of those tokens | those tokens
#    plus <count> <token>] ... instead" --
#
# CR 614.16, verified this session: "Some replacement effects apply 'if an
# effect would create one or more tokens' ... These replacement effects apply
# if the effect of a resolving spell or ability creates a token" - so a token
# created by a resolving triggered ability (Hangarback Walker's dies trigger)
# is squarely in scope.
#
# CR 701.7b is what makes a type filter readable at all: "If a replacement
# effect applies to a token being created, that effect applies before
# considering any continuous effects that will modify the characteristics of
# that token." The `CREATE_TOKENS` event is raised before a single token has
# been built, so the `TokenDefinition` on it is still exactly what the creating
# effect stated (CR 111.3) and "creature tokens" is a question that can be
# answered.

#: The event half, shared by both replacement shapes below. `filter` is an
#: optional single word naming a card type, and only `_CARD_TYPE_WORDS` are
#: read - a filter this cannot check ("Thopter tokens") leaves the whole effect
#: uncompiled, per the fail-closed rule above.
_TOKEN_CREATION_EVENT_RE = re.compile(
    r"^(?:an effect would create one or more tokens under your control"
    r"|one or more (?:(?P<filter>\w+) )?tokens would be created under your control)$",
    re.IGNORECASE,
)
#: Doubling Season's "it creates twice that many of those tokens", Adrix and
#: Nev's "twice that many of those tokens are created", Ojer Taq's "three times
#: that many of those tokens are created".
_TOKEN_MULTIPLIER_RE = re.compile(
    rf"^(?:it creates (?P<it_mult>{MULTIPLIER}) that many of those tokens"
    rf"|(?P<mult>{MULTIPLIER}) that many of those tokens are created)$",
    re.IGNORECASE,
)
#: Stridehangar Automaton's "those tokens plus an additional 1/1 ... Thopter
#: ...", Quina's "those tokens plus a 1/1 green Frog creature token",
#: Chatterfang's "those tokens plus that many 1/1 green Squirrel creature tokens".
_EXTRA_TOKEN_REPLACEMENT_RE = re.compile(
    rf"^those tokens plus (?P<count>that many|{COUNT})(?: additional)? "
    r"(?P<descriptor>.+?) are created$",
    re.IGNORECASE,
)


def _token_creation_filter(effect: ReplacementEffect) -> frozenset[Type] | None:
    """The card type a token-creation event names, as a set: empty for "one or
    more tokens", `None` when the event is not this shape or names something
    that cannot be checked."""
    match = _TOKEN_CREATION_EVENT_RE.match((effect.event or "").strip())
    if match is None:
        return None
    word = match.group("filter")
    if word is None:
        return frozenset()
    wanted = _CARD_TYPE_WORDS.get(word.lower())
    return None if wanted is None else frozenset({wanted})


def _compile_token_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    """ "...N times that many of those tokens" - "those tokens" leaves the
    characteristics untouched and only the count changes, which CR 701.7b's
    ordering guarantees is still possible."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    wanted = _token_creation_filter(effect)
    if wanted is None:
        return None
    match = _TOKEN_MULTIPLIER_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    multiplier = parse_multiplier(match.group("it_mult") or match.group("mult"))
    if multiplier is None:
        return None
    return CardReplacement(
        label=effect.text,
        applies=_extra_token_applies(wanted),
        apply=_scale_amount(multiplier=multiplier),
    )


#: The card types a filter may name, as CR 205.2a spells them.
_CARD_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
}

#: Colour words a token descriptor may use (CR 105.1), plus CR 105.2's
#: "colorless", which is handled separately because it names no colour.
_TOKEN_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}

#: The keywords a "... with X" tail may name. Deliberately a short closed list:
#: a tail naming anything else leaves the descriptor unread and the effect
#: uncompiled, rather than a token quietly created without an ability it should
#: have had. `machines/effects.py` keeps its own, longer copy for the *creation*
#: side; duplicated here rather than reached into, since that one is private.
_TOKEN_TAIL_KEYWORDS = frozenset(
    {
        "flying",
        "first strike",
        "double strike",
        "vigilance",
        "haste",
        "trample",
        "lifelink",
        "deathtouch",
        "menace",
        "reach",
        "defender",
        "hexproof",
        "indestructible",
    }
)

_TOKEN_DESCRIPTOR_TAIL_RE = re.compile(r"^(?P<head>.+?) with (?P<tail>[a-z, ]+)$", re.IGNORECASE)
_TOKEN_PT_RE = re.compile(r"^\d+/\d+$")


def _read_token_descriptor(descriptor: str) -> TokenDefinition | None:
    """ "1/1 colorless Thopter artifact creature token with flying" (CR 111.3).

    Read right to left the way the type line is built (CR 205.1a): the word
    "token", then "creature" (CR 205.2a), then an optional "artifact" ahead of
    it, then a leading power/toughness (CR 208.1), then colour words or
    CR 105.2's "colorless", and whatever capitalized words are left are the
    subtypes (CR 205.3), which CR 111.4 also turns into the token's name.

    Anything this cannot read whole returns `None`, which takes the entire
    replacement effect with it - a token created with the wrong
    characteristics is a worse answer than a card that does nothing.
    """
    text = descriptor.strip().rstrip(".")
    keywords: tuple[str, ...] = ()

    tail_match = _TOKEN_DESCRIPTOR_TAIL_RE.match(text)
    if tail_match is not None:
        parts = [
            part.strip()
            for part in re.split(r",\s*|\s+and\s+", tail_match.group("tail"))
            if part.strip()
        ]
        if not parts or any(part.lower() not in _TOKEN_TAIL_KEYWORDS for part in parts):
            return None
        keywords = tuple(part.title() for part in parts)
        text = tail_match.group("head")

    words = text.split()
    # "token", or "tokens" after a count above one or "that many".
    if not words or words[-1].lower() not in ("token", "tokens"):
        return None
    words = words[:-1]
    if not words or words[-1].lower() != "creature":
        return None
    words = words[:-1]

    types: tuple[Type, ...] = (Type.CREATURE,)
    if words and words[-1].lower() == "artifact":
        types = (Type.ARTIFACT, Type.CREATURE)
        words = words[:-1]

    power = toughness = None
    if words and _TOKEN_PT_RE.match(words[0]):
        power_text, toughness_text = words[0].split("/")
        power, toughness = int(power_text), int(toughness_text)
        words = words[1:]

    colors: list[Color] = []
    while words and words[0].lower() in _TOKEN_COLOR_WORDS:
        colors.append(_TOKEN_COLOR_WORDS[words[0].lower()])
        words = words[1:]
    if words and words[0].lower() == "colorless":
        words = words[1:]

    if not words or not all(word[:1].isupper() for word in words):
        return None
    return TokenDefinition(
        types=types,
        subtypes=tuple(words),
        colors=tuple(colors),
        power=power,
        toughness=toughness,
        keywords=keywords,
    )


def _extra_token_applies(wanted: frozenset[Type]) -> Applies:
    """ "If one or more [**artifact**] tokens would be created under your control".

    "Under your control" is CR 111.2's "the token enters the battlefield under
    that player's control", so the test is against the player *creating* them
    and not against whoever the effect belongs to - Kozilek's Command makes the
    targeted player the creator, and a Doubling Season that player does not
    control does nothing about it. "One or more" is why `amount > 0` is
    checked: creating nothing is not an event to replace.

    What kind of token is read off the event's `definition` when the creating
    effect stated one (CR 111.3), and off the original permanent's own types
    when this is a token *copy* instead, whose characteristics are a printed
    card's (CR 707.2, CR 111.3's "functionally equivalent" both ways round).
    An empty `wanted` names no type and takes every token.
    """

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.CREATE_TOKENS or event.amount <= 0:
            return False
        if event.player is None or event.player.username != source.controller:
            return False
        if not wanted:
            return True
        if event.definition is not None:
            types: Iterable[Type] = event.definition.types
        elif event.card is not None:
            types = event.card.types
        else:
            return False
        return any(card_type in wanted for card_type in types)

    return applies


def _create_additional_tokens(extra: TokenDefinition, count: int | None) -> Apply:
    """ "...those tokens plus [an additional | a | that many] [token] are created instead."

    "Those tokens" is the batch untouched - `amount` and `definition` are left
    exactly as they were - and the addition is queued on the event for
    `create_tokens` to drain. One modified event, one creation (CR 614.6).
    `count` None is "that many": the event's own count as this effect applies.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        event.extra.extend([extra] * (event.amount if count is None else count))

    return apply


def _compile_extra_token(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    wanted = _token_creation_filter(effect)
    if wanted is None:
        return None
    replacement_match = _EXTRA_TOKEN_REPLACEMENT_RE.match(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    count_text = replacement_match.group("count")
    count: int | None = None
    if count_text.lower() != "that many":
        count = parse_count(count_text)
        if count is None:
            return None
    extra = _read_token_descriptor(replacement_match.group("descriptor"))
    if extra is None:
        return None
    return CardReplacement(
        label=effect.text,
        applies=_extra_token_applies(wanted),
        apply=_create_additional_tokens(extra, count),
    )


# -- "if [an effect would put] one or more [kind] counters [would be put] on
#    [a subject] you control, [N times | that many plus/minus N] ... instead" --
#
# Doubling Season ("it puts twice that many of those counters on that
# permanent"), Branching Evolution ("twice that many +1/+1 counters are put on
# that creature"), Hardened Scales ("that many plus one +1/+1 counters are put
# on it"), Winding Constrictor ("that many plus one of each of those kinds of
# counters are put on that permanent") and Vizier of Remedies ("that many -1/-1
# counters minus one are put on it") are one replacement: the multiplier or
# the addend is read as data, never pinned.
#
# CR 614.16: "if an effect would put one or more counters on a permanent"
# replacement effects apply whether the event came from a resolving effect *or
# from a cost* ("even if the original event being modified wasn't itself an
# effect") - so this compiler and `Game.add_counters` together are what make
# Vizier stop Devoted Druid's own activation cost, not only a spell's.

_COUNTER_AMOUNT_EVENT_RE = re.compile(
    r"^(?:an effect would put one or more counters on (?P<effect_subject>.+?)"
    r"|one or more (?:(?P<kind>[+/\w-]+) )?counters would be put on (?P<subject>.+?))$",
    re.IGNORECASE,
)
_COUNTER_AMOUNT_REPLACEMENT_RE = re.compile(
    rf"^(?:it puts (?P<it_mult>{MULTIPLIER}) that many of those counters on that permanent"
    rf"|(?:(?P<mult>{MULTIPLIER}) that many|that many(?: plus (?P<plus>{COUNT}))?)"
    r"(?: of each of those kinds of counters"
    rf"| (?P<kind>[+/\w-]+) counters(?: (?P<op>plus|minus) (?P<n>{COUNT}))?)"
    r" are put on (?:it|that creature|that permanent))$",
    re.IGNORECASE,
)
#: "a creature you control", "an artifact or creature you control", "a permanent".
_COUNTER_SUBJECT_RE = re.compile(r"^an? (?P<types>.+?)(?P<you_control> you control)?$")


def _counter_subject_types(types_text: str) -> frozenset[Type] | None | bool:
    """ "permanent" is None (anything), a card-type list is its types (CR
    205.2a), and anything else - a subtype, a name, "another creature" - is
    False, which leaves the effect uncompiled rather than guessed at."""
    words = [word for word in re.split(r",\s*(?:or\s+)?|\s+or\s+", types_text) if word]
    if words == ["permanent"]:
        return None
    types = [_CARD_TYPE_WORDS.get(word.strip()) for word in words]
    if not types or any(wanted is None for wanted in types):
        return False
    return frozenset(wanted for wanted in types if wanted is not None)


def _counter_amount(match: re.Match[str]) -> Apply | None:
    """The multiplier or addend a counter replacement prints, or None."""
    multiplier_text = match.group("it_mult") or match.group("mult")
    if multiplier_text is not None:
        multiplier = parse_multiplier(multiplier_text)
        return None if multiplier is None else _scale_amount(multiplier=multiplier)
    addend_text = match.group("plus") or match.group("n")
    if addend_text is None:
        return None  # a bare "that many" replaces nothing
    addend = parse_count(addend_text)
    if addend is None:
        return None
    return _scale_amount(addend=-addend if match.group("op") == "minus" else addend)


def _compile_counter_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _COUNTER_AMOUNT_EVENT_RE.match((effect.event or "").strip())
    if event_match is None:
        return None
    replacement_match = _COUNTER_AMOUNT_REPLACEMENT_RE.match(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    subject_match = _COUNTER_SUBJECT_RE.match(
        (event_match.group("effect_subject") or event_match.group("subject")).lower()
    )
    if subject_match is None:
        return None
    types = _counter_subject_types(subject_match.group("types"))
    if types is False:
        return None

    event_kind = (event_match.group("kind") or "").lower() or None
    replacement_kind = (replacement_match.group("kind") or "").lower() or None
    if replacement_kind != event_kind:
        # "+1/+1 counters would be put ... that many plus one -1/-1 counters"
        # is no card; "of each of those kinds" answers only a kindless event.
        return None
    apply = _counter_amount(replacement_match)
    if apply is None:
        return None
    return CardReplacement(
        label=effect.text,
        applies=_counter_amount_applies(
            event_kind, types, subject_match.group("you_control") is not None
        ),
        apply=apply,
    )


# -- "lands you control enter untapped" (CR 614.1d, general and non-self) --


def _lands_you_control_enter_untapped_applies(
    game: "Game", source: CardState, event: ReplaceableEvent
) -> bool:
    """ "Lands you control enter untapped" - Spelunking's own second paragraph.

    Unlike `_ENTERS_TAPPED`'s self-only shockland shape, this watches every
    land entering under its controller's control, not only Spelunking's own
    arrival - CR 614.12's "may come from the permanent itself if [it affects]
    only that permanent" is exactly the case this is *not*: "lands you
    control" plainly affects other objects.
    """
    if event.kind is not EventKind.ENTERS_BATTLEFIELD or event.card is None:
        return False
    return (
        Type.LAND in event.card.types
        and event.card.controller is not None
        and event.card.controller == source.controller
    )


def _lands_you_control_enter_untapped(
    game: "Game", source: CardState, event: ReplaceableEvent
) -> None:
    """ "...enter untapped." Overrides whatever tapped state the event already
    carried - a search's own "tapped" (CR 614.1d applies alongside whatever
    other replacement effect already ran, CR 616.1), a shockland's own "enters
    tapped" - CR 110.5b's default the sentence restates rather than a new one.
    """
    event.tapped = False


def _compile_lands_you_control_enter_untapped(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.ENTERS_UNTAPPED:
        return None
    if effect.self_replacement:
        # A self-referential "this land enters untapped" would already be
        # read by `_self_enters_modifiers` instead (CR 614.12) - not printed
        # by any card in this pool, but excluded here so the two paths never
        # double up if one ever is.
        return None
    subject = (effect.subject or "").strip().lower()
    if subject != "lands you control":
        return None
    return CardReplacement(
        label=effect.text,
        applies=_lands_you_control_enter_untapped_applies,
        apply=_lands_you_control_enter_untapped,
    )


# --------------------------------------------------------------------------
# Keyword-only shapes (CR 702)
# --------------------------------------------------------------------------
#
# A keyword ability's meaning is not in the card's rules text at all - it is in
# the rule that defines the keyword, and the parenthetical on the card is
# reminder text, which `strip_reminder_text` drops before a single template is
# tried (CR 207.2a). So `parse_replacement_effects(card("Hyena Umbra"))` is
# empty and always will be: there is no sentence to parse. The keyword itself
# is the sentence, and it is read off `Card.keywords` here.


#: CR 702.89a, verified this session: "Umbra armor is a static ability that
#: appears on some Auras. 'Umbra armor' means 'If enchanted permanent would be
#: destroyed, instead remove all damage marked on it and destroy this Aura.'"
#:
#: The word *instead* is CR 614.1a, so this is a replacement effect on the
#: destruction itself rather than on the graveyard move it would have become -
#: which is exactly why `EventKind.DESTROY` exists and is raised separately.
#: CR 614.6: the replaced event never happens, so the enchanted permanent did
#: not die (CR 700.4) and no dies trigger fires for it.
_UMBRA_ARMOR = "umbra armor"


def _umbra_armor_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "If **enchanted permanent** would be destroyed" (CR 702.89a).

    Three things have to be true and each is checked: the event is a
    destruction (CR 701.8a, and *only* the ways CR 701.8b allows - the engine
    raises `DESTROY` for nothing else), the destruction has not already been
    replaced by something else (CR 614.7: an effect that would replace an event
    that never happens does nothing, which is what stops a second Aura on the
    same creature spending itself for a destruction the first one already
    called off), and this Aura is attached to the permanent being destroyed
    (CR 301.5a - `attached_to` names a card, and an Aura on a *player* names
    none, so it can never match a permanent's destruction).
    """
    if event.kind is not EventKind.DESTROY or event.replaced:
        return False
    if event.card is None:
        return False
    return source.attached_to == event.card.id


def _umbra_armor(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
    """ "...instead remove all damage marked on it and destroy this Aura."

    Both halves of the one replacement, and the destruction itself called off
    (CR 614.6). Removing the marked damage is what stops CR 704.5g destroying
    the creature all over again on the very next state-based check: the damage
    is *marked* on the permanent (CR 120.6) and survives the destruction being
    replaced, so leaving it there would be an infinite loop of Auras.

    Destroying the Aura goes back through `Game.destroy`, so it is a real
    destruction with its own `DESTROY` event - an Aura with umbra armor of its
    own is not attached to itself, so nothing here recurses.
    """
    if event.card is not None:
        event.card.damage = 0
    event.replaced = True
    if source is not None:
        game.destroy(source)


def _has_umbra_armor_in_lines(abilities: tuple[str, ...]) -> bool:
    """Whether `abilities` - a live permanent's *computed* ability-text lines
    (`Characteristics.abilities`, CR 613.1f) - still carry umbra armor.

    Reads the same vocabulary `machines/combat.py::_computed_keywords` builds
    for a layer-aware `has_keyword` check (CR 702's own combat keywords, plus
    the one this call cares about) rather than a single-keyword vocabulary:
    `keywords_in_lines`' own line classifier refuses a whole comma-separated
    keyword line the moment one token in it is not in `known` - "Flying, umbra
    armor" would silently lose *both* keywords to a narrower vocabulary, not
    just the one this function was not asked about.
    """
    vocabulary = [keyword.value for keyword in Keyword] + [_UMBRA_ARMOR]
    return _UMBRA_ARMOR in keywords_in_lines(list(abilities), vocabulary)


def _keyword_replacements(
    card: Card, *, computed_abilities: tuple[str, ...] | None = None
) -> list[CardReplacement]:
    """The replacement effects a card's *keywords* generate (CR 702).

    Only umbra armor so far. Read off `Card.keywords` rather than the oracle
    text because the text says nothing a parser could use - the keyword's
    meaning lives in CR 702.89a and the card's own parenthesis is reminder
    text (CR 207.2a).

    `computed_abilities`, when given, is a live battlefield permanent's
    computed ability list (CR 613.5, CR 613.1f) - a static ability layer 6
    already stripped no longer grants umbra armor's replacement, whatever
    `Card.keywords` still says. `None` (every caller with no permanent behind
    the card - a spell on the stack, `parsed_card_replacements`' generic
    path) keeps the printed-only reading, unchanged.
    """
    has_umbra_armor = (
        _has_umbra_armor_in_lines(computed_abilities)
        if computed_abilities is not None
        else any(keyword.strip().lower() == _UMBRA_ARMOR for keyword in card.keywords)
    )
    if has_umbra_armor:
        return [
            CardReplacement(
                label="umbra armor: destroy this Aura instead (CR 702.89a)",
                applies=_umbra_armor_applies,
                apply=_umbra_armor,
            )
        ]
    return []


# --------------------------------------------------------------------------
# "Can't enter the battlefield" (CR 614.17d)
# --------------------------------------------------------------------------
#
# CR 614.17, verified this session: "Some effects state that something can't
# happen. These effects aren't replacement effects, but follow similar rules."
# CR 614.17d names this family in particular: "Some 'can't' effects modify how
# a permanent enters the battlefield or whether it can enter the battlefield.
# Such effects may come from the permanent itself if they affect only that
# permanent". Grafdigger's Cage's is the general kind - it watches every
# creature card in every graveyard and library, not itself.
#
# "Follow similar rules" is why this is carried on the same `ENTERS_BATTLEFIELD`
# event the real replacement effects use, and the docstring on `_cant_enter`
# says what that costs: CR 614.17c's "if an event can't happen, it can only be
# replaced by a self-replacement effect" is a *precedence* rule this machinery
# has no way to express, so a can't-enter effect here competes for CR 616.1's
# ordering rather than pre-empting it.
#
# The card does not say where the object goes, and CR 400.4a's sibling wording
# for a card that cannot enter - "it remains in its previous zone" - is what
# happens: the event's destination is set back to its origin.

_CANT_ENTER_RE = re.compile(
    r"^(?P<filter>\w+) cards in (?P<zones>[\w, ]+?) can'?t enter the battlefield\.?$",
    re.IGNORECASE,
)

#: The zone words a "cards in ..." clause may name, plural as printed.
_ZONE_PLURALS: dict[str, Zone] = {
    "graveyard": Zone.GRAVEYARD,
    "graveyards": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "libraries": Zone.LIBRARY,
    "hand": Zone.HAND,
    "hands": Zone.HAND,
    "exile": Zone.EXILE,
}


def _read_zone_list(text: str) -> frozenset[Zone] | None:
    """ "graveyards and libraries" as a set of zones, or None if a word is
    one this cannot name - fail closed, exactly as the compilers above do."""
    zones: set[Zone] = set()
    for word in re.split(r",\s*|\s+and\s+", text.strip()):
        word = word.strip().lower()
        if not word:
            continue
        zone = _ZONE_PLURALS.get(word)
        if zone is None:
            return None
        zones.add(zone)
    return frozenset(zones) or None


def _cant_enter(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
    """The object does not enter; it stays where it was.

    CR 400.4a states the same outcome for the rules' own can't-enter case -
    "if an instant or sorcery card would enter the battlefield, it remains in
    its previous zone" - and CR 614.6's "the original event never happens" is
    what makes the rest follow: nothing enters, so no enters-the-battlefield
    ability triggers (CR 603.6a) and any counters or tapped state the event was
    carrying go with it. `Game.enter_the_battlefield` reads the destination
    back and returns the card to that zone.
    """
    if event.origin is not None:
        event.destination = event.origin


def _cant_enter_applies(wanted: Type, zones: frozenset[Zone]) -> Applies:
    """ "**Creature cards** in graveyards and libraries can't enter the battlefield."

    "Cards", so a token is excluded: CR 111.6, "a token isn't a card", and a
    token being created has no origin zone worth the name anyway. The type is
    read off the entering object's own types, and the origin off the event -
    which is why this refuses a creature entering from a hand, from exile, or
    as a resolving spell off the stack, all of which the Cage leaves alone.
    """

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        card_state = event.card
        if event.kind is not EventKind.ENTERS_BATTLEFIELD or card_state is None:
            return False
        if event.origin not in zones or is_token(card_state):
            return False
        return wanted in card_state.types

    return applies


def _cant_enter_replacements(card: Card) -> list[CardReplacement]:
    """Grafdigger's Cage's first line, and anything else printed to that shape.

    Read straight off the oracle text rather than through
    `parse_replacement_effects`: CR 614.17 says these are not replacement
    effects, so the parser at the top of this module correctly refuses to
    claim them (the sentence carries none of its cue words either).
    """
    found: list[CardReplacement] = []
    for line in (card.oracle_text or "").splitlines():
        rules_text, _ = strip_reminder_text(line)
        match = _CANT_ENTER_RE.match(rules_text.strip())
        if match is None:
            continue
        wanted = _CARD_TYPE_WORDS.get(match.group("filter").lower())
        zones = _read_zone_list(match.group("zones"))
        if wanted is None or zones is None:
            continue
        found.append(
            CardReplacement(
                label=f"{rules_text.strip()} (CR 614.17d)",
                applies=_cant_enter_applies(wanted, zones),
                apply=_cant_enter,
            )
        )
    return found


#: Tried in order against every parsed effect on a `REPLACEMENTS` miss. Order
#: does not matter between them - each one's event/replacement match is
#: specific enough that at most one ever claims a given `ReplacementEffect`.
_COMPILERS: tuple[Callable[[ReplacementEffect], CardReplacement | None], ...] = (
    _compile_graveyard_exile,
    _compile_enters_uncast_exile,
    _compile_damage_multiplier,
    _compile_damage_plus_amount,
    _compile_prevent_damage_and_mill,
    _compile_self_prevent_combat_damage,
    _compile_life_gain_doubler,
    _compile_draw_doubler_except_draw_step,
    _compile_draw_doubler,
    _compile_draw_plus,
    _compile_token_doubler,
    _compile_extra_token,
    _compile_counter_doubler,
    _compile_lands_you_control_enter_untapped,
)


#: The compilers that read `ReplacementEffect.condition` themselves. Every
#: other compiler above is condition-blind, so an effect carrying an "as long
#: as ..." qualifier is never offered to one: compiling it there would perform
#: the replacement unconditionally and silently drop the clause, which is the
#: exact failure the fail-closed rule at the top of this section forbids.
_CONDITION_AWARE_COMPILERS = frozenset({_compile_draw_plus})


def _compile(effect: ReplacementEffect) -> CardReplacement | None:
    """The first generic shape above that claims this effect, if any."""
    if effect.from_trigger:
        # CR 603.1: the effect belongs to a triggered ability and does not
        # exist until that ability resolves, so it is never a static ability's
        # continuous effect for `applicable_effects` to find on the
        # battlefield. See `_parse_trigger_effect`.
        return None
    for compiler in _COMPILERS:
        if effect.condition is not None and compiler not in _CONDITION_AWARE_COMPILERS:
            continue
        compiled = compiler(effect)
        if compiled is not None:
            return compiled
    return None


def parsed_card_replacements(card: Card) -> list[CardReplacement]:
    """Every generic shape above that this card's own oracle text matches.

    Plus the shapes its *keywords* generate, which no amount of text parsing
    would ever reach (see `_keyword_replacements`), and CR 614.17d's
    can't-enter effects, which the parser deliberately does not claim.
    """
    found: list[CardReplacement] = _keyword_replacements(card) + _cant_enter_replacements(card)
    for effect in parse_replacement_effects(card):
        compiled = _compile(effect)
        if compiled is not None:
            found.append(compiled)
    return found


def replacements_of(card: Card) -> list[CardReplacement]:
    """The performable replacement effects of a card, or an empty list.

    An explicit `REPLACEMENTS` row always wins; on a miss, `parsed_card_replacements`
    tries every generic shape above against the card's own oracle text - the same
    fallback order `effect_for` in `machines/effects.py` uses for `EFFECTS`.
    """
    explicit = REPLACEMENTS.get(card.name)
    if explicit is not None:
        return explicit
    return parsed_card_replacements(card)


def replacements_of_state(
    game: "Game", permanent: CardState, board: "ComputedBoard | None" = None
) -> list[CardReplacement]:
    """Like `replacements_of`, but reads a *live permanent's* level-gated
    text (CR 716.2a) rather than its printed card wholesale, and its computed
    ability list (CR 613.5, CR 613.1f) rather than its printed keywords.

    A Class needs the level gate: `CardState.class_ability_text` is exactly
    `oracle_text` for anything else, so this is a safe, behaviour-preserving
    substitute for `replacements_of(permanent.card)` at every battlefield
    scan - Artist's Talent's own level 3 must not double as a level 1's
    damage-plus-2, before the Class has actually reached level 3.

    Every permanent needs the computed ability list: `_keyword_replacements`
    would otherwise grant umbra armor's replacement off `Card.keywords` alone,
    missing a layer-6 removal of it.

    `board`, when the caller already has one (`applicable_effects`'s own
    battlefield sweep), is reused rather than asking `game.characteristics_of`
    again - `Game.computed_board` recomputes the whole battlefield on every
    call, so a caller looping over it must hoist one board rather than pay for
    N of them.
    """
    explicit = REPLACEMENTS.get(permanent.card.name)
    if explicit is not None:
        return explicit
    card = permanent.card
    chars = (board or game.computed_board()).of(permanent)
    found: list[CardReplacement] = _keyword_replacements(
        card, computed_abilities=chars.abilities
    ) + _cant_enter_replacements(card)
    if "Class" not in chars.subtypes:
        for effect in parse_replacement_effects(card):
            compiled = _compile(effect)
            if compiled is not None:
                found.append(compiled)
        return found
    names = _names_of(card)
    for effect in _parse_oracle_text(permanent.class_ability_text, face=None, names=names):
        compiled = _compile(effect)
        if compiled is not None:
            found.append(compiled)
    return found


# --------------------------------------------------------------------------
# Effects a permanent generates about itself (CR 614.12)
# --------------------------------------------------------------------------


#: "you may pay 2 life" - the optional half of a shockland's CR 614.12a choice.
_PAY_LIFE_CHOICE = re.compile(r"you may pay (\d+) life", re.IGNORECASE)

#: The other half: "If you don't, it enters tapped." The parser puts "you don't"
#: in `condition`, and it is a back-reference to the payment rather than a
#: condition about the board, which is what makes the pair one choice.
_IF_YOU_DONT = re.compile(r"^(?:if )?you don[’']?t$", re.IGNORECASE)


def _pay_life_or_tapped(amount: int, card_name: str) -> Apply:
    """The shockland branch, as one CR 614.12a choice made before it enters.

    CR 614.12a: "If a replacement effect that modifies how a permanent enters
    the battlefield requires a choice, that choice is made before the permanent
    enters the battlefield." This runs inside `apply_replacements`, which
    `Game.enter_the_battlefield` calls before the card is put onto the
    battlefield, so the timing is right by construction.

    CR 119.4 decides whether paying is even an option, and `Game.may_pay_life`
    asks it: below the life total the payment is illegal, CR 608.2d then forbids
    choosing it, and the land enters tapped with nobody having decided anything.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = event.card.controller if event.card is not None else None
        if who is None:
            event.tapped = True
            return
        if not game.may_pay_life(who, amount, source=card_name, source_id=source_id_of(source)):
            event.tapped = True

    return apply


#: "you may reveal a Plains or Island card from your hand" - the optional half
#: of a reveal land's CR 614.12a choice. The part after "you may" is an
#: ordinary reveal cost, read by the same `total_cost_for_phrase` a spell's
#: "Reveal X white cards from your hand" is.
_REVEAL_CHOICE = re.compile(r"^you may (?P<cost>reveal .+ from your hand)\.?$", re.IGNORECASE)


def _optional_enters_payment(effect: ReplacementEffect, card_name: str) -> Apply | None:
    """What an optional "As this enters, you may ..." (CR 614.1c) does as the
    permanent enters, or `None` when no reader claims its payment.

    Its caller pairs it with the "If you don't, it enters tapped" that
    follows, because the two sentences are one CR 614.12a choice. Two payments
    are read: paying life (the shocklands) and revealing a card of a stated
    quality from hand (the reveal lands, whatever quality they print).
    """
    replacement = (effect.replacement or "").strip()
    payment = _PAY_LIFE_CHOICE.search(replacement)
    if payment:
        return _pay_life_or_tapped(int(payment.group(1)), card_name)
    reveal = _REVEAL_CHOICE.match(replacement)
    if reveal is None:
        return None
    from .cost import ComponentKind, total_cost_for_phrase

    phrase = reveal.group("cost")
    cost = total_cost_for_phrase(phrase)
    if (
        cost is None
        or cost.mana.symbols
        or len(cost.components) != 1
        or cost.components[0].kind is not ComponentKind.REVEAL
        or cost.components[0].variable_count
    ):
        return None
    return _reveal_or_tapped(phrase, card_name)


def _reveal_or_tapped(phrase: str, card_name: str) -> Apply:
    """A reveal land's branch, as one CR 614.12a choice made before it enters.

    With no qualifying card in hand there is nothing to reveal (CR 118.3), so
    nobody is asked and the land enters tapped. Otherwise its controller is
    asked whether to reveal; yes asks which card (`Game.choose_cards_to_reveal`,
    the question a reveal cost on a spell asks) and pays the reveal, which
    shows the card to every player and leaves it in hand (CR 701.20a-b); no
    enters it tapped.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        from .cost import total_cost_for_phrase

        who = event.card.controller if event.card is not None else None
        cost = total_cost_for_phrase(phrase, who) if who is not None else None
        if who is None or cost is None:
            event.tapped = True
            return
        (component,) = cost.components
        component.source = card_name
        entering_id = event.card.id if event.card is not None else None
        eligible = [
            card
            for card in game.player(who).hand
            if card.id != entering_id
            and (
                component.requirement is None
                or component.requirement.why_not(card, game, who) is None
            )
        ]
        source_id = source_id_of(source)
        if not eligible or not game.may(
            who, phrase, source=card_name, source_id=source_id, cards=eligible
        ):
            event.tapped = True
            return
        game.choose_cards_to_reveal(component, who, source=card_name, source_id=source_id)
        if component.why_not(game) is not None:
            event.tapped = True
            return
        component.pay(game)

    return apply


# --------------------------------------------------------------------------
# The condition on a self "enters tapped" line (CR 614.1d)
# --------------------------------------------------------------------------
#
# CR 614.1d is the bare "[This permanent] enters . . ." wording, and most of
# the pool's printings of it carry a condition about the board rather than
# about a choice: "unless you control a Mountain", "if you control two or more
# other lands", "unless a player has 13 or less life". The condition was parsed
# and then dropped, so Arena of Glory entered *untapped* on an empty board -
# a wrong board state, not a missing one.
#
# **Polarity.** A leading "If <cond>, this land enters tapped" taps when the
# condition holds; a trailing "... enters tapped unless <cond>" taps when it
# does not. `_ENTERS_TAPPED` keeps the literal word "unless" on the second
# form, so the two are told apart by the text itself and no extra field is
# needed on `ReplacementEffect`.
#
# **Fail closed.** A condition none of the readers below claims returns `None`
# and the effect is skipped entirely, exactly as every conditional line was
# before this - a land that is silently untapped is the same wrong answer it
# already gave, and it is better than taxing an unread clause into a guess.
# The shockland back-reference "you don't" is one of those: it is not about the
# board at all, it is the other half of the CR 614.12a choice that
# `_self_enters_modifiers` pairs up above, and no reader here matches it.

#: "does this condition hold right now", for the entering permanent.
EntersCondition = Callable[["Game", CardState], bool]

#: "unless you control a Mountain", "unless you control a Plains or an Island".
#: Land subtypes are proper nouns as printed (CR 205.3i, CR 305.5: "Land
#: subtypes are always a single word"), so the capital letter is required -
#: that is what keeps this from claiming an arbitrary "you control a ..."
#: noun phrase it cannot actually check.
_YOU_CONTROL_SUBTYPES_RE = re.compile(r"^you control (an? [A-Z][\w'-]*(?: or an? [A-Z][\w'-]*)*)$")
_A_SUBTYPE_RE = re.compile(r"an? ([A-Z][\w'-]*)")

#: "you control two or more other lands", "you control two or fewer other lands",
#: the battle lands' "you control two or more basic lands" (CR 205.4c), and
#: "you control three or more other Mountains" (Dwarven Mine). A land subtype
#: is a capitalized single word (CR 305.5), so the capital is required even
#: under IGNORECASE - "other creatures" is a noun this cannot check.
_YOU_CONTROL_OTHER_LANDS_RE = re.compile(
    rf"^you control (?P<count>{COUNT}) or (?P<direction>more|fewer) "
    r"(?:(?P<other>other) )?(?:(?P<basic>basic) )?"
    r"(?:lands|(?P<subtype>(?-i:[A-Z])[\w'-]*))$",
    re.IGNORECASE,
)

#: "a player has 13 or less life" - any player at the table, not only the
#: entering permanent's controller (Lakeside Shack).
_A_PLAYER_HAS_LIFE_RE = re.compile(
    r"^a player has (?P<count>\d+) or (?P<direction>less|more) life$", re.IGNORECASE
)

#: "X is 2 or less" - Slumbering Trudge, whose tapped state is decided by the
#: value chosen for X as it was cast (CR 601.2b records the choice;
#: `Game.cast_records` is what holds it here, the same record CR 107.3m's
#: enters-with-X counters already read a few lines below).
_X_IS_RE = re.compile(r"^x is (?P<count>\d+) or (?P<direction>less|greater)$", re.IGNORECASE)


def _controls_a_subtype(subtypes: frozenset[str]) -> EntersCondition:
    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None:
            return False
        # One board, hoisted out of the loop below (CR 613.5: `computed_board`
        # recomputes the whole battlefield every call) - a permanent's
        # *computed* subtypes are what "you control a Mountain" asks about, so
        # a nonbasic land Blood Moon (CR 305.7) already made a Mountain counts
        # even though it prints no subtype at all.
        board = game.computed_board()
        return any(
            subtype in subtypes
            for permanent in game.battlefield
            if permanent.controller == controller
            for subtype in board.of(permanent).subtypes
        )

    return holds


def _controls_other_lands(
    count: int, at_least: bool, basic: bool = False, subtype_plural: str | None = None
) -> EntersCondition:
    """ "you control [N] or more/fewer **other** [lands | Mountains]".

    `subtype_plural` is the printed plural of a land type (CR 205.3i), matched
    against each land's computed subtypes as that word or that word plus "s" -
    "Plains" is its own plural, "Mountains" is "Mountain" plus one.

    "Other" is why the entering permanent is excluded by id: CR 614.12's
    effects are read while the permanent is still on its way in
    (`Game.enter_the_battlefield` calls `apply_replacements` before putting it
    onto the battlefield), so it is not in `game.battlefield` yet - the
    exclusion is belt and braces against a caller that puts it there first.
    """

    def holds(game: "Game", entering: CardState) -> bool:
        controller = entering.controller
        if controller is None:
            return False
        # One board, hoisted the same way `_controls_a_subtype` does: a
        # permanent's *computed* types (CR 613.5) decide "land" here, so a
        # creature a layer-4 effect already made a land (CR 205.1b) counts.
        board = game.computed_board()
        lands = sum(
            1
            for permanent in game.battlefield
            if permanent.controller == controller
            and Type.LAND in board.of(permanent).types
            # CR 205.4c: "basic" is the supertype, never a basic land type.
            and (not basic or board.of(permanent).is_basic)
            and (
                subtype_plural is None
                or any(
                    subtype_plural in (subtype, f"{subtype}s")
                    for subtype in board.of(permanent).subtypes
                )
            )
            and permanent.id != entering.id
        )
        return lands >= count if at_least else lands <= count

    return holds


def _a_player_has_life(count: int, at_most: bool) -> EntersCondition:
    def holds(game: "Game", entering: CardState) -> bool:
        return any(
            (player.life <= count if at_most else player.life >= count)
            for player in game.players_in_game
        )

    return holds


def _x_is(count: int, at_most: bool) -> EntersCondition:
    def holds(game: "Game", entering: CardState) -> bool:
        record = game.cast_record_of(entering)
        if record is None or record.x_value is None:
            # No announcement to read X off (CR 601.2b) - the permanent got
            # here some other way, X is undefined, and there is nothing to
            # decide the tapped state with. Fail closed, as above.
            return False
        return record.x_value <= count if at_most else record.x_value >= count

    return holds


def _enters_tapped_condition(effect: ReplacementEffect) -> EntersCondition | None:
    """Read an `ENTERS_TAPPED` condition into "does it enter tapped", or `None`.

    The returned predicate already folds in the polarity, so its caller only
    has to ask it.
    """
    condition = (effect.condition or "").strip().rstrip(".")
    if not condition:
        return None

    negated = False
    lowered = condition.lower()
    if lowered.startswith("unless "):
        negated = True
        condition = condition[len("unless ") :].strip()

    inner = _read_enters_condition(condition)
    if inner is None:
        return None
    if not negated:
        return inner

    def tapped_unless(game: "Game", entering: CardState) -> bool:
        return not inner(game, entering)

    return tapped_unless


def unread_self_enters_tapped_lines(card_state: CardState) -> list[str]:
    """The entering object's own "enters tapped" lines (CR 614.1d) that
    `_self_enters_modifiers` skips because it cannot read them.

    Two shapes are skipped there, and both are named here from the same parse:
    a condition none of `_read_enters_condition`'s readers claims (a count
    of a noun it cannot check), and an "If you don't" whose
    optional half is not a payment `_optional_enters_payment` reads. Only the
    face that is up is read, the same CR 712.8 filter `_self_enters_modifiers`
    applies. `hypothetical.predict_enters` reports a land with any of these
    tapped, with a notice, rather than repeating the engine's silent untapped
    guess.
    """
    up_face_name = card_state.up_face_name
    pending_payments = 0
    unread: list[str] = []
    for effect in parse_replacement_effects(card_state.card):
        if up_face_name is not None and effect.face not in (None, up_face_name):
            continue
        if not effect.self_replacement:
            continue
        if (
            effect.kind is ReplacementKind.AS_ENTERS
            and effect.optional
            and _optional_enters_payment(effect, card_state.card.name) is not None
        ):
            pending_payments += 1
            continue
        if effect.kind is not ReplacementKind.ENTERS_TAPPED:
            continue
        condition = (effect.condition or "").strip()
        if not condition:
            continue
        if _IF_YOU_DONT.match(condition):
            if pending_payments:
                pending_payments -= 1
            else:
                unread.append(effect.text)
            continue
        if _enters_tapped_condition(effect) is None:
            unread.append(effect.text)
    return unread


def _read_enters_condition(condition: str) -> EntersCondition | None:
    match = _YOU_CONTROL_SUBTYPES_RE.match(condition)
    if match is not None:
        subtypes = frozenset(_A_SUBTYPE_RE.findall(match.group(1)))
        return _controls_a_subtype(subtypes) if subtypes else None

    match = _YOU_CONTROL_OTHER_LANDS_RE.match(condition)
    if match is not None:
        count = parse_count(match.group("count"))
        if count is None:
            return None
        return _controls_other_lands(
            count,
            at_least=match.group("direction").lower() == "more",
            basic=match.group("basic") is not None,
            subtype_plural=match.group("subtype"),
        )

    match = _A_PLAYER_HAS_LIFE_RE.match(condition)
    if match is not None:
        return _a_player_has_life(
            int(match.group("count")), at_most=match.group("direction").lower() == "less"
        )

    match = _X_IS_RE.match(condition)
    if match is not None:
        return _x_is(int(match.group("count")), at_most=match.group("direction").lower() == "less")

    return None


#: "As [this] enters, choose a color/card name/creature type." (CR 614.1c).
#: Three fixed phrases, not a general "choose ..." reader - Kenrith's
#: Transformation's "choose a creature type" (naming an existing permanent's
#: new type, not a card carrying its own choice) is a *targeted* clause of a
#: different shape entirely and is never routed through here.
_CHOOSE_A_COLOR_RE = re.compile(r"^choose a color\.?$", re.IGNORECASE)
_CHOOSE_A_CARD_NAME_RE = re.compile(r"^choose a card name\.?$", re.IGNORECASE)
_CHOOSE_A_CREATURE_TYPE_RE = re.compile(r"^choose a creature type\.?$", re.IGNORECASE)

#: The five colors' letter codes (CR 105.1), the closed universe
#: `Game.ask` checks a color choice against. Card names and creature types
#: have no such closed universe here, so their `Decision.options` stays empty.
_COLOR_OPTIONS = tuple(
    color.value for color in (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)
)


def _classify_choice(replacement_text: str) -> ChoiceKind | None:
    """Which of the three "as [this] enters, choose ..." shapes this is, if any."""
    text = replacement_text.strip()
    if _CHOOSE_A_COLOR_RE.match(text):
        return ChoiceKind.COLOR
    if _CHOOSE_A_CARD_NAME_RE.match(text):
        return ChoiceKind.CARD_NAME
    if _CHOOSE_A_CREATURE_TYPE_RE.match(text):
        return ChoiceKind.CREATURE_TYPE
    return None


class UnwiredChoiceNotice(EngineModel):
    """A card's own sentence reads back "the chosen color/card name/creature
    type" (CR 614.12a's choice, once made), but this wave only performs the
    one shape that adds mana - `machines/effects.py`'s "adds an additional
    ..." clause. Recorded instead of the card silently doing nothing, the
    same shape `AnaphoricClauseNotice`/`ConditionalClauseNotice`/
    `LayerNotice` already use elsewhere in this codebase for a clause this
    read but did not perform.

    Three of the pool's seven "as this enters, choose ..." cards land here:

    - **Runed Halo** - "You have protection from the chosen card name." is a
      layer 6 static ability (CR 613.1f) granted to a *player*, not a
      permanent; nothing in `machines/layers.py` grants protection to a
      player at all yet (its whole static-ability sweep is permanent-only).
    - **Pithing Needle** / **Disruptor Flute** - "Activated abilities of
      sources with the chosen name can't be activated unless they're mana
      abilities." is a cost/legality restriction on *activating* an ability,
      which has no representation anywhere the engine checks
      `why_cannot_activate`. Disruptor Flute's *other* line, "Spells with the
      chosen name cost {3} more to cast.", is no longer here: CR 601.2f's
      cost-increase step reads it as `CostModifierKind.NAMED_INCREASE` and
      `Game.static_cost_modifiers_for` compares the chosen name against the
      spell being cast, so only the activation line of that card still lands
      on this list.
    - **Cavern of Souls** - "Spend this mana only to cast a creature spell of
      the chosen type, and that spell can't be countered." restricts what a
      floating mana symbol may pay for and grants an uncounterable quality to
      whatever it paid for; `models/mana.ManaPool` tracks color and snow-ness
      only, nothing that could carry a spend restriction.

    **Voice of All** is the fourth color-choosing card and is not listed
    here: "This creature has protection from *the chosen color*" already
    matches `machines/layers.py`'s generic `_LOOKS_LIKE_LAYER_EFFECT_RE`
    (subject "this creature" + "has") and fails `_parse_layer_sentence` (no
    shape reads a literal "the chosen color" as a quality), so
    `effects_for` already records a `LayerNotice` for it with no new code -
    proof the generic fail-closed net catches a permanent-targeted grant on
    its own; only the player-targeted and cost/restriction shapes needed a
    notice built here.

    None of the four attempted consumers are wired this wave - CR 614.12a's
    choice itself is (`CardState.choice`), and the one payoff this wave
    performs end to end is the mana clause (Utopia Sprawl, Leyline of
    Abundance, Badgermole Cub).
    """

    source_id: UUID
    source_name: str
    text: str


#: A card's own line reads back the choice ("the chosen color/card name/
#: creature type") outside of the "As [this] enters, choose ..." sentence
#: that asked for it. `_UNWIRED_HINT_RE` tells such a line apart from the one
#: shape this wave *does* perform - "adds an additional ..." - by exclusion:
#: any other sentence naming the anaphora is an attempted consumer this wave
#: does not build, and gets a notice instead of silence.
#: "the chosen color/card name/creature type" and the shorter forms the same
#: cards' own *other* lines use for the same antecedent - Pithing Needle and
#: Disruptor Flute say "the chosen name" once they have already said "choose a
#: card name", and Cavern of Souls says "the chosen type" having already said
#: "choose a creature type". Same referent, shorter noun phrase the second
#: time it is used - ordinary English anaphora, not a fourth kind of choice.
_CHOSEN_QUALITY_ANAPHORA_RE = re.compile(
    r"\bthe chosen (?:color|card name|name|creature type|type)\b", re.IGNORECASE
)
_WIRED_MANA_CLAUSE_HINT_RE = re.compile(r"adds? an additional\b", re.IGNORECASE)
#: The second shape this engine now performs end to end: Disruptor Flute's
#: "Spells with the chosen name cost {3} more to cast.", read by
#: `machines/cost.cost_modifier_effect` as `CostModifierKind.NAMED_INCREASE`
#: and applied against `CardState.choice` in `Game.static_cost_modifiers_for`.
#: Excluded here so a wired consumer stops being reported as an unwired one.
_WIRED_NAMED_COST_INCREASE_HINT_RE = re.compile(
    r"spells with the chosen name cost \{\d+\} more to cast", re.IGNORECASE
)
#: "This creature has/gets/gains ..." (Voice of All) - the shape
#: `machines/layers.py`'s `_LOOKS_LIKE_LAYER_EFFECT_RE` already catches on its
#: own, recording a `LayerNotice` with no help from here. Excluded so a
#: permanent-targeted grant does not get *two* notices for the same gap, one
#: on each of two separate lists.
_LAYER_HANDLED_SUBJECT_RE = re.compile(
    r"^(?:this \w+|target creature|another target creature(?: you control)?)\s+"
    r"(?:has|have|gets?|gains?)\b",
    re.IGNORECASE,
)


def _unwired_choice_notices(card: Card, source_id: UUID) -> list[UnwiredChoiceNotice]:
    """Every sentence of `card`'s own text that reads back a CR 614.12a
    choice this wave does not perform - see `UnwiredChoiceNotice`.

    Read off the whole printed text rather than one line, since a card's
    reference to its own choice is never on the same line as the "As [this]
    enters, choose ..." sentence that asked for it.
    """
    found: list[UnwiredChoiceNotice] = []
    for line in (card.oracle_text or "").splitlines():
        sentence = line.strip()
        if not sentence or not _CHOSEN_QUALITY_ANAPHORA_RE.search(sentence):
            continue
        if (
            sentence.lower().startswith("as ")
            or _WIRED_MANA_CLAUSE_HINT_RE.search(sentence)
            or _WIRED_NAMED_COST_INCREASE_HINT_RE.search(sentence)
            or _LAYER_HANDLED_SUBJECT_RE.match(sentence)
        ):
            continue
        found.append(UnwiredChoiceNotice(source_id=source_id, source_name=card.name, text=sentence))
    return found


def _quality_options(kind: ChoiceKind) -> tuple[str, ...]:
    """Every legal answer to CR 614.12a's choice, where the rules enumerate them.

    A color is one of CR 105.1's five. A creature type is one of CR 205.3m's
    list, read from the rules text (`data/creature_types.py`) - a land type
    such as "Island" is not one, and neither is an empty string. A card name
    has no list to offer, so it stays open.
    """
    if kind is ChoiceKind.COLOR:
        return _COLOR_OPTIONS
    if kind is ChoiceKind.CREATURE_TYPE:
        return creature_types()
    return ()


def _choose_a_quality(kind: ChoiceKind, card_name: str) -> Apply:
    """Ask CR 614.12a's choice and record it on the entering object itself.

    "If a replacement effect that modifies how a permanent enters the
    battlefield requires a choice, that choice is made before the permanent
    enters the battlefield" - so this runs inside `apply_replacements`,
    before `Game.enter_the_battlefield` ever puts the card on the
    battlefield, exactly like the shockland's pay-life-or-tapped choice
    above. Unlike that one, nothing about *this* choice changes the
    `ReplaceableEvent` itself (no tapped flag, no counters) - the whole
    effect is recording an answer for later clauses to read back
    ("the chosen color"), which is why the only side effect is setting
    `source.choice`.

    The player asked is the entering permanent's own controller, who is set
    on `card_state.controller` by `Game.enter_the_battlefield` just before
    replacements are applied - not necessarily the same player who cast it
    (an Aura enchanting an opponent's permanent still asks *its own*
    controller, CR 303.4e), and there is no controller at all to ask if this
    is reached some other way, in which case nothing is recorded rather than
    guessing.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        who = source.controller if source is not None else None
        if who is None:
            return
        decision = Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=who,
            prompt=f"choose {with_indefinite_article(kind.value.replace('_', ' '))}",
            source=card_name,
            source_id=source_id_of(source),
            options=_quality_options(kind),
            quality=kind.value,
        )
        value = game.ask(decision)
        assert isinstance(value, str)
        source.choice = Choice(kind=kind, value=value)
        game.unwired_choice_notices.extend(_unwired_choice_notices(source.card, source.id))

    return apply


# --------------------------------------------------------------------------
# "[This permanent] enters as a copy of ..." (CR 614.1c, 616.1c)
# --------------------------------------------------------------------------
#
# Clone: "You may have this creature enter as a copy of any creature on the
# battlefield." CR 614.1c makes "[This permanent] enters as . . ." a
# replacement effect, and CR 614.12 lets it come from the permanent itself,
# which is why this is gathered by `_self_enters_modifiers` off the entering
# card rather than compiled into `_COMPILERS`: the Clone is not on the
# battlefield when it applies, so no battlefield scan would ever find it.
#
# CR 616.1c gives it its own step ahead of the ordinary free choice: "If any of
# the replacement and/or prevention effects would cause an object to become a
# copy of another object as it enters the battlefield, one of them must be
# chosen." `ApplicableEffect.copy_as_it_enters` carries that, and
# `order_effects` sorts on it.
#
# CR 614.12a is the choice itself: "If a replacement effect that modifies how a
# permanent enters the battlefield requires a choice, that choice is made
# before the permanent enters the battlefield" - both the "you may" and which
# creature, asked from inside `apply_replacements`, which every route onto the
# battlefield runs before the card is put there.
#
# What is copied is CR 707.2's copiable values, and `machines/layers.py`
# already builds exactly that layer-1 effect for "this creature becomes a copy
# of target creature"; `_become_a_copy_builder` is reused rather than
# reimplemented, so the two shapes cannot drift apart.

#: "any creature on the battlefield" (Clone) / "any creature card in a
#: graveyard" (Superior Spider-Man) - the object the entering permanent may
#: copy, and the zone to look for it in. CR 707.2 is written about copying an
#: *object*, not specifically a permanent, and CR 400.1 lists the graveyard as
#: a zone like any other, so "card in a graveyard" needs no special rule -
#: only a second place to look. The noun is "card" there and "permanent" on
#: the battlefield, which is CR 108.2/108.2b's own distinction ("a Magic card ... A
#: token isn't a card"), so the wording is admitted per zone rather than
#: interchangeably.
_COPY_CANDIDATES_RE = re.compile(
    r"^any (?P<filter>artifact|creature|enchantment|land|permanent)"
    r"(?: on the battlefield| card in a graveyard)$",
    re.IGNORECASE,
)

_COPY_FROM_GRAVEYARD_RE = re.compile(r"card in a graveyard$", re.IGNORECASE)


def _copy_candidates(game: "Game", phrase: str, entering: CardState) -> list[CardState] | None:
    """The objects this card may enter as a copy of, or None if the phrase
    is one this cannot read - fail closed, as everywhere else in this module.

    Two zones are read: the battlefield (Clone) and every graveyard (Superior
    Spider-Man's "any creature card in a graveyard" - "a graveyard", not "your
    graveyard", so every player's is searched).

    The entering object is excluded: it is not on the battlefield yet, so this
    is belt and braces against a caller that put it there first.
    """
    cleaned = phrase.strip().rstrip(".")
    match = _COPY_CANDIDATES_RE.match(cleaned)
    if match is None:
        return None
    word = match.group("filter").lower()
    wanted = None if word == "permanent" else _CARD_TYPE_WORDS.get(word)
    if wanted is None and word != "permanent":
        return None
    if _COPY_FROM_GRAVEYARD_RE.search(cleaned):
        # A graveyard card has no continuous effect reaching it (CR 613.5
        # applies to the battlefield), so its printed types are the only
        # answer there is.
        pool: list[CardState] = []
        for player in game.players_in_game:
            pool.extend(player.graveyard)
        return [
            candidate
            for candidate in pool
            if candidate.id != entering.id and (wanted is None or wanted in candidate.types)
        ]
    # The battlefield half: the *selection* of what may be copied reads the
    # computed board (CR 613.5) - a land earthbend (CR 701.66a) already made
    # a creature is a candidate for "any creature on the battlefield", even
    # though the values actually copied stay the copiable ones (CR 707.2,
    # unaffected by this - `Game.enter_the_battlefield` copies the chosen
    # candidate's printed card, not its computed characteristics).
    board = game.computed_board()
    return [
        candidate
        for candidate in game.battlefield
        if candidate.id != entering.id and (wanted is None or wanted in board.of(candidate).types)
    ]


#: "exile that card" - the one reflexive instruction this module performs.
#: "That card" is anaphoric to the object the copy was made from, which is why
#: the copied object is passed in rather than looked up again by name.
_EXILE_THAT_CARD_RE = re.compile(r"^exile that card\.?$", re.IGNORECASE)


def _create_linked_reflexive_trigger(
    game: "Game",
    effect: ReplacementEffect,
    card_name: str,
    entering: CardState,
    copied: CardState,
) -> None:
    """CR 603.12's reflexive ability, now that the action it reflects happened.

    "A resolving spell or ability may allow or instruct a player to take an
    action and create a triggered ability that triggers 'when [a player] [does
    or doesn't]' take that action ... These reflexive triggered abilities
    follow the rules for delayed triggered abilities (see rule 603.7), except
    that they're checked immediately after being created and trigger based on
    whether the trigger event or events occurred earlier during the resolution
    of the spell or ability that created them."

    Superior Spider-Man's is "When you do, exile that card." - created only on
    this path, which runs only when the copy choice was actually taken, so
    "occurred earlier" is true by construction. It goes on the stack as an
    ordinary trigger, which is what lets the episode's ordering question exist
    at all: with Bringer of the Last Gift's own enters trigger waiting
    alongside it, CR 603.3b lets their controller put them on the stack in
    either order.

    **CR 400.7 is why the callback re-reads the zone.** "An object that moves
    from one zone to another becomes a new object with no memory of, or
    relation to, its previous existence" - so a card that has left the
    graveyard by the time this resolves is not "that card" any more and
    nothing is exiled. That is the whole ruling DDR#986 turns on, and it falls
    out of asking rather than of a special case.

    An instruction this cannot read creates nothing rather than a trigger that
    does something else - the module's fail-closed rule.
    """
    linked = effect.linked_trigger
    if linked is None or entering.controller is None:
        return
    match = _REFLEXIVE_OPENER.match(linked)
    if match is None or not _EXILE_THAT_CARD_RE.match(match.group("effect").strip()):
        return
    game.create_reflexive_trigger(
        text=linked,
        controller=entering.controller,
        source_id=entering.id,
        source_name=card_name,
        callback=ReflexiveExileCopiedCard(card_id=copied.id, zone_when_copied=copied.zone),
    )


class UnreadableCopyExceptionNotice(EngineModel):
    """A card's "enter as a copy of X, except ..." tail exists but this parser
    could not read it - recorded instead of the copy silently applying no
    exception at all, the same shape `UnwiredChoiceNotice`/`LayerNotice`/
    `AnaphoricClauseNotice` already use elsewhere in this module for a clause
    that was read but could not be performed.

    CR 707.9b makes the copy and its exception one computation: "The final set
    of values for that characteristic becomes part of the copiable values of
    the copy." An unreadable exception therefore means the *whole* copiable
    result is unknown, not that the exception happens to be empty - applying
    the plain copy anyway would be running half of CR 608.2c's single
    instruction, silently. `_enters_as_copy` records this and skips the entire
    "enter as a copy" replacement rather than guessing: the permanent enters
    as itself.

    This is what closes a real defect found live this session: Echoing Deeps
    - "You may have this land enter tapped as a copy of any land card in a
    graveyard, except it's a Cave in addition to its other types" - has no
    power/toughness in its exception, which the parser required before this
    fix, so `copy_exception` silently defaulted to no modification at all and
    the land entered as a plain copy with no Cave type. Echoing Deeps' own
    tail is genuinely readable (see `_COPY_EXCEPT_PT_AND_TYPES`) and no longer
    reaches this notice; Mockingbird's "... and it has flying" still does,
    since granting an ability is not a shape this module parses yet.
    """

    source_id: UUID
    source_name: str
    text: str


def _enters_as_copy(effect: ReplacementEffect, card_name: str) -> Apply:
    """CR 614.1c's "enters as a copy of", as a thing to do before it enters.

    Nothing about the `ReplaceableEvent` changes - no tapped flag, no counters
    - exactly like `_choose_a_quality` above: what the effect does is register
    the layer-1 copy effect (CR 613.1a, CR 707.2) that decides what the
    permanent's characteristics will be once it is there. `CardState.power`
    already reads the computed characteristics first, so the copy is visible
    the moment the permanent is on the battlefield.

    A board with no legal candidate is not an error: CR 707.2 has nothing to
    copy, so the permanent simply enters as itself. An unreadable "except ..."
    tail is different - see `UnreadableCopyExceptionNotice` - and is checked
    first, ahead of even looking for candidates, because it is a defect in
    what this card's text says, not a fact about the board.
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        # Imported here rather than at module scope: `machines/layers.py` is a
        # sibling this module is imported by, the same reason `keywords` and
        # `casting` are imported inside `_stack_replacements`.
        from .layers import LayerContext, _become_a_copy_builder

        entering = event.card
        if entering is None or entering.controller is None:
            return
        if effect.copy_exception_unparsed is not None:
            game.unreadable_copy_exception_notices.append(
                UnreadableCopyExceptionNotice(
                    source_id=entering.id,
                    source_name=card_name,
                    text=effect.copy_exception_unparsed,
                )
            )
            return
        candidates = _copy_candidates(game, effect.copy_of or "", entering)
        if not candidates:
            return
        if effect.optional and not game.may(
            entering.controller,
            f"have {card_name} enter as a copy of {effect.copy_of}",
            source=card_name,
            source_id=source_id_of(source),
        ):
            # CR 614.12a's choice, declined. The permanent enters as itself.
            return
        chosen_id = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=entering.controller,
                prompt=f"choose {effect.copy_of} for {card_name} to enter as a copy of",
                source=card_name,
                source_id=source_id_of(source),
                amount=1,
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        by_id = {candidate.id: candidate for candidate in candidates}
        chosen = [by_id[card_id] for card_id in chosen_id if card_id in by_id]  # type: ignore[union-attr]
        if not chosen:
            return
        exception = effect.copy_exception or CopyException()
        for built in _become_a_copy_builder(
            until_eot=False,
            name_override=exception.name,
            power_override=exception.power,
            toughness_override=exception.toughness,
            added_types=exception.added_types,
            added_subtypes=exception.added_subtypes,
        )(entering, game.continuous_effects.tick(), chosen, LayerContext()):
            game.continuous_effects.add(built)

        _create_linked_reflexive_trigger(game, effect, card_name, entering, chosen[0])

    return apply


#: "where X is the number of turns you've begun since it was foretold" -
#: Lupine Harbingers' own count, printed on the card in
#: `tests/fixtures/cards/` (`resolve_cards` has no entry for this printing, so
#: the fixture's real Scryfall text is the source read here). Matched on the
#: sentence rather than stored at parse time because `_ENTERS_WITH`'s "where
#: ..." tail is deliberately not routed into `amount_expression`: that field
#: feeds `_ENTERS_WITH_AMOUNT_RESOLVERS`, and its presence is what tells
#: CR 107.3m's announced X apart from an expression, which this is not either.
_TURNS_SINCE_FORETOLD_RE = re.compile(
    r"number of turns you'?ve begun since it was foretold", re.IGNORECASE
)


def _turns_begun_since_foretold(game: "Game", entering: CardState) -> int | None:
    """ "The number of turns you've begun since it was foretold", or `None`.

    CR 702.143a: "Foretell is a keyword that functions while the card with
    foretell is in a player's hand. Any time a player has priority during their
    turn, that player may pay {2} and exile a card with foretell from their
    hand face down." The turn that happened on is the only thing the count
    needs, and `ExileAnnotation.turn_exiled` is where the foretell pile records
    it - read here off `CastRecord.exile_annotation`, because CR 400.7 makes
    the spell a new object and `CardState.move_to` drops the annotation on the
    way to the stack.

    **The reading taken, and why.** The card says turns *you have begun*, not
    turns that have passed, so the count has to be per-player. This engine has
    two candidates and neither is that exactly:

    - `TurnMachine.turns_taken` counts every turn any player begins, so in a
      two-player game it would double the answer - bob's turns are not ones
      alice began.
    - `TurnMachine.turn_number` counts rounds of the table. Every player takes
      exactly one turn per round (CR 500.1 gives the turn its five phases;
      turn order is seating order), so the number of rounds elapsed *is* the
      number of turns the foretelling player has begun since.

    `turn_number` is therefore the right one, and the docstring on
    `TurnMachine.turns_taken` names the single case where it is not: an extra
    turn (CR 500.7) deliberately does not move `turn_number`, so a player given
    one would be counted a turn short. Recorded rather than guessed at - no
    card in the pool combines foretell with an extra turn, and inventing a
    per-player counter to cover it belongs to `machines/turn.py`, not here.

    `None` when there is nothing to count from: no cast record (the permanent
    arrived some other way), no exile annotation, or an annotation from a pile
    that is not foretell's. Fail closed, like every other unreadable count in
    this module - the effect is skipped and the permanent enters with no
    counters rather than with a guessed number.
    """
    record = game.cast_record_of(entering)
    if record is None or record.exile_annotation is None or game.turn is None:
        return None
    annotation = record.exile_annotation
    if annotation.marker is not ExileMarker.FORETOLD or annotation.turn_exiled is None:
        return None
    # Never negative: a stamp from the future is not a state this can reach,
    # and CR 122.1 has no notion of putting a negative number of counters on.
    return max(0, game.turn.turn_number - annotation.turn_exiled)


def _self_enters_modifiers(
    game: "Game", card_state: CardState
) -> list[tuple[str, Apply, str, bool]]:
    """The card's own "enters ..." replacement effects, as things to apply.

    CR 614.12: "Some replacement effects modify how a permanent enters the
    battlefield. Such effects may come from the permanent itself if they affect
    only that permanent." That is why these are read off the entering card while
    it is not yet on the battlefield, unlike every other entry in `REPLACEMENTS`.

    Four shapes are performed:

    - "[This] enters tapped" (CR 614.1d) and "[this] enters with N counters"
      (CR 614.1c), unconditional.
    - "[This] enters tapped unless you control a Mountain" / "If you control
      two or more other lands, this land enters tapped" - the same shape with
      a condition about the *board*, read by `_enters_tapped_condition` and
      evaluated here. A condition no reader there claims is skipped.
    - "As this land enters, you may pay N life. If you don't, it enters tapped"
      - one choice spread over two printed sentences, which the parser reads as
      an optional `AS_ENTERS` followed by an `ENTERS_TAPPED` whose condition is
      the back-reference "you don't". Joined back together here, because they
      are not two effects: CR 614.12a's choice is singular.
    - "As [this] enters, choose a color/card name/creature type" - CR 614.12a's
      choice recorded on the entering object itself (`CardState.choice`) rather
      than changing the `ReplaceableEvent`, since nothing about *this* choice
      is a tapped flag or a counter count. See `_choose_a_quality`.

    "[This] enters with X `<kind>` counters" (Walking Ballista, Hangarback
    Walker, Chalice of the Void, Engineered Explosives) is CR 107.3m's own
    named case: "If an object's enters-the-battlefield ... replacement effect
    refers to X, and the spell that became that object as it resolved had a
    value of X chosen for any of its costs, the value of X for that ... effect
    is that same value." `game.cast_records` still holds that record here -
    `Game.resolve_top` calls `enter_the_battlefield` before it pops the record,
    the same ordering `Wrath of the Skies`'s own X read relies on. A
    `card_state.id` with **no** record at all (put onto the battlefield by
    something other than its own resolution - Green Sun's Zenith finding a
    Walking Ballista, say) leaves X undefined by 107.3m and is still skipped,
    the same as before this fix; a real cast with X=0 is not skipped and
    correctly places zero counters (CR 704.5f then kills a 0/0 the next state-
    based check, which is the right outcome, not a bug to paper over).
    """
    # CR 712.8d/712.8e/712.8f: a double-faced permanent has only the
    # characteristics of the face that's up, and CR 109.3 counts abilities -
    # replacement effects among them - as characteristics. Witch Enchanter
    # cast for its creature front, `up_face_name` names "Witch Enchanter";
    # the back face's "As this land enters, you may pay 3 life" is printed on
    # Witch-Blessed Meadow and is not read here, exactly as a triggered or
    # activated ability off the other face is not (see `triggers.py`'s
    # `triggers_for` and `Game.activated_abilities` for the same filter).
    # `up_face_name` is `None` for an ordinary single-faced card, which keeps
    # every one of its own lines (`effect.face` is also `None` there).
    up_face_name = card_state.up_face_name
    parsed = [
        effect
        for effect in parse_replacement_effects(card_state.card)
        if up_face_name is None or effect.face in (None, up_face_name)
    ]
    #: (key suffix, what to do, label, CR 616.1c copy-as-it-enters).
    performable: list[tuple[str, Apply, str, bool]] = []
    consumed: set[int] = set()

    for index, effect in enumerate(parsed):
        if index in consumed or not effect.self_replacement:
            continue

        choice = (
            _optional_enters_payment(effect, card_state.card.name)
            if effect.kind is ReplacementKind.AS_ENTERS and effect.optional
            else None
        )
        if choice is not None:
            follower = next(
                (
                    other
                    for other, candidate in enumerate(parsed)
                    if other > index
                    and candidate.kind is ReplacementKind.ENTERS_TAPPED
                    and _IF_YOU_DONT.match((candidate.condition or "").strip())
                ),
                None,
            )
            if follower is not None:
                consumed.add(follower)
                performable.append(
                    (
                        f"self:{index}",
                        choice,
                        f"{effect.text} {parsed[follower].text}",
                        False,
                    )
                )
                continue

        if effect.kind is ReplacementKind.ENTERS_AS_COPY and effect.condition is None:
            # CR 614.1c / 616.1c. `_enters_as_copy` refuses a `copy_of` phrase
            # it cannot read, so a card whose candidates this cannot work out
            # enters as itself rather than as a guess.
            performable.append(
                (
                    f"self:{index}",
                    _enters_as_copy(effect, card_state.card.name),
                    effect.text,
                    True,
                )
            )
            continue

        if effect.kind is ReplacementKind.AS_ENTERS and effect.condition is None:
            choice_kind = _classify_choice(effect.replacement or "")
            if choice_kind is not None:
                performable.append(
                    (
                        f"self:{index}",
                        _choose_a_quality(choice_kind, card_state.card.name),
                        effect.text,
                        False,
                    )
                )
                continue

        if effect.condition is not None:
            # CR 614.1d's conditional wordings - "unless you control a
            # Mountain", "if you control two or more other lands". Read into a
            # predicate and *evaluated* here, at gathering time, so an effect
            # whose condition does not hold never reaches CR 616.1's list at
            # all rather than being applied to no effect. A condition no reader
            # claims returns `None` and the effect is skipped, unchanged.
            holds = _enters_tapped_condition(effect)
            if holds is None or not holds(game, card_state):
                continue
        amount = effect.amount
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.variable_amount
            and _TURNS_SINCE_FORETOLD_RE.search(effect.text or "")
        ):
            # Ahead of CR 107.3m's X below on purpose: this card's X is not the
            # announced one (its cost has no {X} at all, so the announcement
            # records 0), it is the count its own sentence names.
            amount = _turns_begun_since_foretold(game, card_state)
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.variable_amount
            # CR 107.3m is "if an object's ... replacement effect **refers to
            # X**". A count stated as an expression instead - Ulamog, the
            # Defiler's "equal to the greatest mana value among cards in
            # exile" - refers to no X at all, and must not be answered with
            # the announcement's own X, which for a card with no {X} in its
            # cost is recorded as 0 rather than left unset.
            and effect.amount_expression is None
        ):
            # CR 107.3m: only a spell that actually resolved into this object
            # defines X here - `game.cast_records` is popped once resolution
            # finishes, so its presence here is exactly that fact, and an
            # entry with no record at all (this object arrived some other
            # way) leaves `amount` `None` and the effect skipped, unchanged
            # from before.
            record = game.cast_record_of(card_state)
            if record is not None:
                amount = record.x_value
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.amount_expression is not None
        ):
            # "...equal to [expression]" - a count worked out against the game
            # as the permanent enters. An X inside it is CR 107.3m's X of the
            # spell that became this object; with no such spell it cannot be
            # determined and CR 107.2 uses 0. An expression nobody can read
            # leaves `amount` None, skips the counters, and says so.
            from .effects import UnreadableCounterAmountNotice, amount_expression

            reader = amount_expression(effect.amount_expression)
            if reader is None:
                game.unreadable_counter_amount_notices.append(
                    UnreadableCounterAmountNotice(
                        source_id=card_state.id,
                        source_name=card_state.name,
                        text=effect.text,
                        expression=effect.amount_expression,
                    )
                )
            else:
                record = game.cast_record_of(card_state)
                x_value = record.x_value if record is not None else 0
                controller = card_state.controller or card_state.owner
                amount = reader(game, controller, card_state, x_value)
        readable_counters = (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is not None
        )
        if effect.kind is ReplacementKind.ENTERS_TAPPED or readable_counters:
            performable.append(
                (f"self:{index}", _apply_self_enters(effect, amount), effect.text, False)
            )

    sunburst = _sunburst_modifier(game, card_state, up_face_name)
    if sunburst is not None:
        performable.append(sunburst)

    return performable


def _sunburst_counter_amount(game: "Game", entering: CardState) -> int | None:
    """CR 702.44b's own count: distinct colors of mana spent paying the total
    cost of the spell that is resolving into `entering` - `None` when this is
    not that (Sunburst adds nothing to an object that reaches the battlefield
    some other way, and CR 702.44b says so in as many words: "only if the
    object with sunburst is entering the battlefield from the stack as a
    resolving spell").

    `CastRecord.mana_spent` already carries exactly this (CR 601.2h,
    `machines/cost.ManaPayment.spend`), "including additional or alternative
    costs" per the same rule - it is filled once, at payment, from whatever
    was actually spent, with no notion of which symbol on the printed cost
    each mana went to. `Color.COLORLESS` is excluded: CR 105.1 lists five
    colors and colorless mana is explicitly "not a color" (CR 105.2c).
    """
    record = game.cast_record_of(entering)
    if record is None:
        return None
    return sum(
        1
        for color, amount in record.mana_spent.items()
        if color is not Color.COLORLESS and amount > 0
    )


def _sunburst_modifier(
    game: "Game", card_state: CardState, up_face_name: str | None
) -> tuple[str, Apply, str, bool] | None:
    """Sunburst (CR 702.44a), read off the keyword rather than off a parsed
    sentence - its own CR 702.44a expansion is reminder text (CR 207.2),
    never a rules-text sentence `_ENTERS_WITH` could match, so it is handled
    here directly rather than through `parse_replacement_effects`.

    No printing in the pool carries Sunburst on a multifaced card, so
    `up_face_name` is accepted only to keep this call symmetric with the
    parsed-sentence loop above rather than to filter anything yet - `Card.
    keywords` is Scryfall's own per-printing summary and is already scoped to
    whichever card this `CardState` actually is.

    "If this object is entering **as a creature**, ignoring any type-changing
    effects that would affect it" (CR 702.44a) reads `Card.types` - the
    printed type, before any layer effect - which is exactly what CR 613.1's
    "ignoring type-changing effects" means and is why this never asks
    `Game.characteristics_of` the way an ordinary battlefield query would.
    """
    del up_face_name
    keywords = {k.lower() for k in card_state.card.keywords}
    if "sunburst" not in keywords:
        return None
    amount = _sunburst_counter_amount(game, card_state)
    if amount is None:
        return None
    is_creature = Type.CREATURE in card_state.card.types
    counter_kind = "+1/+1" if is_creature else "charge"
    effect = _make(
        ReplacementKind.ENTERS_WITH,
        "Sunburst",
        subject=card_state.card.name,
        replacement=f"{amount} {counter_kind} counters",
        amount=amount,
        counter_kind=counter_kind,
        self_replacement=True,
    )
    return ("self:sunburst", _apply_self_enters(effect, amount), "Sunburst (CR 702.44a)", False)


def _leaving_the_stack(event: ReplaceableEvent) -> bool:
    return event.kind is EventKind.ZONE_CHANGE and event.origin is Zone.STACK


def _stack_replacements(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """A spell's own replacement effects for leaving the stack (CR 604.5).

    Two keywords put a static ability on the *spell*, and CR 604.5 - "some
    static abilities apply while a spell is on the stack" - is what lets it
    function there. Flashback says so itself, in as many words: CR 702.34a calls
    it "another [static ability] that functions while the card is on the stack".
    Both replace where the
    card goes when it stops being a spell, so neither can be read off the
    battlefield the way `REPLACEMENTS` entries are - the object generating the
    effect is the object being moved.

    - **CR 702.34a** - "Flashback [cost]" means, in part, "If the flashback cost
      was paid, exile this card instead of putting it anywhere else any time it
      would leave the stack." *Any* time, so this catches a countered or
      fizzled flashback spell as well as a resolved one.
    - **CR 715.3d** - "Instead of putting a spell that was cast as an Adventure
      into its owner's graveyard as it resolves, its controller exiles it. For
      as long as that card remains exiled, that player may play it."

    Whether the cost was paid or the Adventure face was chosen is a fact about
    the announcement, which the `CardState` does not carry; `Game.cast_records`
    does (CR 601.2b).
    """
    card = event.card
    if card is None or not _leaving_the_stack(event):
        return []

    record = game.cast_record(card)
    found: list[ApplicableEffect] = []

    if record.keyword is not None and record.keyword.lower() == "flashback":
        found.append(
            ApplicableEffect(
                key=f"{card.id}:flashback",
                source=card,
                label="if the flashback cost was paid, exile this card instead (CR 702.34a)",
                apply=_exile_instead,
            )
        )
    if record.keyword is not None and record.keyword.lower() == "harmonize":
        # CR 702.180a's third static ability: "If the harmonize cost was
        # paid, exile this card instead of putting it anywhere else any
        # time it would leave the stack." Structurally identical to
        # flashback's own clause just above - a second `record.keyword`
        # value reaching the same `_exile_instead`, not a new mechanism.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:harmonize",
                source=card,
                label="if the harmonize cost was paid, exile this card instead (CR 702.180a)",
                apply=_exile_instead,
            )
        )
    from .keywords import has_rebound  # imported here: casting imports this module's siblings

    if has_rebound(card.card) and record.origin_zone is Zone.HAND and event.resolving:
        # CR 702.88a: "If this spell was cast from your hand, instead of
        # putting it into your graveyard as it resolves, exile it." A spell
        # cast from anywhere else - most pointedly from exile by its own
        # previous rebound recast - never triggers this a second time, which
        # is what stops an infinite exile-and-recast loop; `record.origin_zone`
        # is `Casting.origin_zone` as the spell was actually announced, not a
        # fact about the card's printed text.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:rebound",
                source=card,
                label="cast from hand with rebound: exile this card instead (CR 702.88a)",
                apply=_exile_instead,
            )
        )
    from .keywords import has_paradigm  # imported here: casting imports this module's siblings

    if has_paradigm(card.card) and event.resolving:
        # CR 702.192a: Paradigm "represents two spell abilities ... 'Exile
        # this spell.'" Unlike rebound's "if cast from your hand", this half
        # is unconditional - every resolution of a Paradigm spell is exiled
        # instead of going to the graveyard, whether it is the original cast
        # or a later free-cast copy created by `models/game.py`'s own
        # `_create_paradigm_delayed_trigger`/`ParadigmCopyAndCast`.
        found.append(
            ApplicableEffect(
                key=f"{card.id}:paradigm",
                source=card,
                label="Paradigm: exile this spell instead (CR 702.192a)",
                apply=_exile_instead,
            )
        )
    from .casting import adventure_face  # imported here: casting imports this module's siblings

    adventure = adventure_face(card.card)
    cast_as_adventure = adventure is not None and record.face == adventure.name
    if cast_as_adventure and event.destination is Zone.GRAVEYARD:
        found.append(
            ApplicableEffect(
                key=f"{card.id}:adventure",
                source=card,
                label="a spell cast as an Adventure is exiled instead (CR 715.3d)",
                apply=_exile_instead,
            )
        )
    if event.resolving and event.destination is Zone.GRAVEYARD:
        # CR 304.2/307.2: "the actions stated in its rules text are followed.
        # Then it's put into its owner's graveyard" - a spell whose own text
        # already shuffled itself into the library during that first part
        # never reaches the second, the same "instead of graveyard, elsewhere"
        # shape as rebound just above, gated the same way on `event.resolving`
        # (CR 701.6a: a countered spell "doesn't resolve and none of its
        # effects occur", so this must never fire for one - the whole reason
        # this reads `event.resolving` rather than "leaving the stack" the way
        # flashback's *any*-exit exile does).
        match = _SELF_SHUFFLE_INTO_LIBRARY_RE.search(card.oracle_text)
        if match is not None and _refers_to_self(match.group("name"), _names_of(card.card)):
            found.append(
                ApplicableEffect(
                    key=f"{card.id}:self_shuffle",
                    source=card,
                    label=(
                        "shuffled into its owner's library instead, as it "
                        "resolves (CR 304.2/307.2, 701.24c)"
                    ),
                    apply=_shuffle_into_library_instead,
                )
            )
    return found


def _apply_self_enters(effect: ReplacementEffect, amount: int | None) -> Apply:
    """`amount` is `effect.amount` for a fixed count, or CR 107.3m's resolved
    X for a variable one - `_self_enters_modifiers` has already worked out
    which, so this only ever sees a real number by the time it is called.
    """

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        if effect.kind is ReplacementKind.ENTERS_TAPPED:
            event.tapped = True
        else:
            assert effect.counter_kind is not None and amount is not None
            event.counters[effect.counter_kind] = (
                event.counters.get(effect.counter_kind, 0) + amount
            )

    return apply


# --------------------------------------------------------------------------
# Gathering, ordering, applying
# --------------------------------------------------------------------------


def _impending_entering_counters(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """CR 702.176a's second ability: "If you chose to pay this permanent's
    impending cost, it enters with N time counters on it."

    CR 702.176a makes it "a replacement effect that may apply to the permanent
    with impending as it enters the battlefield from the stack", and CR 614.1c
    makes "[this permanent] enters with ..." a replacement effect - so it
    changes the same entering event every other entering counter does, and
    `Game.enter_the_battlefield` places the counters through `add_counters`.

    "From the stack" and "you chose to pay" are one question here:
    `event.was_cast` (a resolving spell) and its own `CastRecord.keyword`,
    which `resolve_top` has not popped yet. A blinked or reanimated permanent
    enters with no cast behind it and gets nothing (CR 400.7). N is read off
    the printed keyword line (`KeywordAbility.count`), never off the card's
    name. CR 118.9a allows one alternative cost per spell, so only the first
    impending line counts even on a card that printed two.
    """
    # Imported here, beside their one use: casting imports this module's siblings.
    from ..models.card_state import Counter
    from .abilities import keyword_abilities

    entering = event.card
    if entering is None or not event.was_cast:
        return []
    record = game.cast_record_of(entering)
    if record is None or (record.keyword or "").lower() != "impending":
        return []
    amount = next(
        (
            ability.count
            for ability in keyword_abilities(entering.card)
            if ability.canonical.lower() == "impending" and ability.count is not None
        ),
        None,
    )
    if amount is None:
        return []

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        event.counters[Counter.TIME] = event.counters.get(Counter.TIME, 0) + amount

    return [
        ApplicableEffect(
            key=f"{entering.id}:impending",
            source=entering,
            label=f"impending: enters with {amount} time counters (CR 702.176a)",
            apply=apply,
        )
    ]


def _protection_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """Protection preventing damage from a source with the stated quality.

    CR 702.16e: "Any damage that would be dealt by sources that have the stated
    quality to a permanent or player with protection is prevented." Protection
    is a static ability (CR 702.16a) of the *damaged* object rather than of a
    third permanent watching, so it cannot be a `REPLACEMENTS` entry - it belongs
    to whatever is being damaged, and the target of the event is where to look.

    `Game.protection_from_damage` does the reading, because the quality matcher
    and the protection parser both live there.
    """
    reason = game.protection_from_damage(event)
    if reason is None or event.card is None:
        return []
    return [
        ApplicableEffect(
            key=f"{event.card.id}:protection",
            source=event.card,
            label=reason,
            apply=_prevent_all,
        )
    ]


def _shield_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """The prevention shields waiting on this damage event (CR 615.1, 615.7-615.9).

    CR 615.1 puts prevention effects in the same machinery as replacement
    effects - "Like replacement effects (see rule 614), prevention effects apply
    continuously as events happen" - and CR 616.1 orders the two kinds together,
    which is why they are gathered here rather than applied separately in
    `Game.deal_damage`.

    A shield has no source permanent: CR 615.4 has it created before the damage
    and CR 615.3 has it last "until [it is] used up or [its] duration has
    expired", both of which can outlive whatever made it.
    """
    if event.kind is not EventKind.DAMAGE:
        return []

    def applier(shield: object) -> Apply:
        def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
            game.apply_prevention_shield(shield, event)

        return apply

    return [
        ApplicableEffect(
            key=f"shield:{index}",
            source=None,
            label=shield.label,
            apply=applier(shield),
            controller_username=shield.controller,
        )
        for index, shield in enumerate(game.prevention_shields)
        if game.shield_applies(shield, event)
    ]


def _regeneration_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """The regeneration shields waiting on this destruction (CR 701.19a).

    CR 701.19a: "If the effect of a resolving spell or ability regenerates a
    permanent, it creates a replacement effect that protects the permanent the
    next time it would be destroyed this turn. In this case, 'Regenerate
    [permanent]' means 'The next time [permanent] would be destroyed this
    turn, instead remove all damage marked on it and its controller taps it.
    If it's an attacking or blocking creature, remove it from combat.'"

    Gathered here rather than checked inside `Game.destroy` so that CR 616.1's
    ordering applies to it exactly as it does to umbra armor and to the
    prevention shields just above - two destruction-replacements on one
    permanent is a choice the rules give somebody, not a fixed precedence this
    function gets to invent.

    Like a prevention shield (and unlike umbra armor) it has no source
    permanent: CR 701.19a's effect outlives whatever created it, right up to
    the end of the turn. `controller_username` is the permanent's own
    controller, since CR 701.19a names them as the player who taps it.

    `event.regeneration_allowed` is CR 701.19c's prohibition - see that field.
    """
    if event.kind is not EventKind.DESTROY or event.replaced:
        return []
    if not event.regeneration_allowed:
        return []
    permanent = event.card
    if permanent is None or permanent.regeneration_shields <= 0:
        return []

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        card = event.card
        if card is None:
            return
        card.regeneration_shields -= 1
        card.damage = 0
        if not card.tapped:
            card.tap()
        game.combat.remove(card.id)  # CR 506.4
        event.replaced = True

    return [
        ApplicableEffect(
            key=f"regeneration:{permanent.id}",
            source=None,
            label="regeneration shield: tap it and remove it from combat instead (CR 701.19a)",
            apply=apply,
            controller_username=game.controller_of(permanent).username,
        )
    ]


class DrawRedirection(EngineModel):
    """One player's draws taken by another, for a duration (CR 614.1a).

    Plagiarize prints the only one in this pool: "Until end of turn, if target
    player would draw a card, instead that player skips that draw and you draw
    a card." That is CR 614.1a's "[if] [Event] would happen, [Something else]
    happens instead" shape, but unlike every other entry in this module it is
    not a static ability of a permanent - the instant that made it is in a
    graveyard by the time it ever applies, and CR 614.6 has the new event
    happen in place of the old one for as long as the duration runs.

    Stored on `Game.draw_redirections` for the same reason
    `Game.prevention_shields` stores a CR 615.1 shield: the effect has to
    outlive its source, and it has a duration of its own that CR 514.2's
    cleanup step ends.
    """

    label: str
    """What the effect says, for the event trace."""

    controller: str
    """Who created it - `ApplicableEffect` needs a controller for CR 616.1's
    ordering, and the spell that made this is long gone."""

    skipping: str
    """The player whose draw is replaced: Plagiarize's "target player"."""

    drawing: str
    """The player who draws instead: Plagiarize's "you" (CR 109.5)."""

    until_end_of_turn: bool = True
    """CR 514.2 ends it in the cleanup step, alongside the marked damage and
    every other "until end of turn" effect."""


#: Plagiarize's whole printed sentence. Matched entire rather than split into
#: `ReplacementEffect`'s event/replacement halves, because the replacement half
#: names two different players ("that player" and "you") and nothing in this
#: module's clause splitter carries that pairing.
_DRAW_REDIRECTION_RE = re.compile(
    r"^until end of turn, if target player would draw a card, instead that player "
    r"skips that draw and you draw a card\.?$",
    re.IGNORECASE,
)


def draw_redirection_for(text: str, controller: str, target: str | None) -> DrawRedirection | None:
    """Read a resolving spell's text into a `DrawRedirection`, or `None`.

    `target` is the player the spell targeted (CR 115.1), rechecked for
    legality by the caller at CR 608.2b before this is ever asked; `None` means
    no player was targeted, and then there is nothing to redirect.
    """
    if target is None:
        return None
    if _DRAW_REDIRECTION_RE.fullmatch(" ".join(text.strip().split())) is None:
        return None
    return DrawRedirection(
        label=" ".join(text.strip().split()),
        controller=controller,
        skipping=target,
        drawing=controller,
    )


def _finality_counter_effects(event: ReplaceableEvent) -> list[ApplicableEffect]:
    """A finality counter's replacement effect (CR 122.1h): "One or more
    finality counters on a permanent create a single replacement effect that
    stops the permanent from going to the graveyard. That effect is 'If this
    permanent would be put into a graveyard from the battlefield, exile it
    instead.'"

    Gathered here rather than checked inside `Game.put_into_graveyard` so CR
    616.1 orders it against every other graveyard replacement (Rest in Peace)
    the way it orders any two. One effect however many counters there are,
    keyed by the permanent, so CR 614.5 applies it once. Like a regeneration
    shield it has no source permanent to ask, so its controller is the
    permanent's own.
    """
    if event.kind is not EventKind.ZONE_CHANGE or event.destination is not Zone.GRAVEYARD:
        return []
    if event.origin is not Zone.BATTLEFIELD:
        return []
    permanent = event.card
    if permanent is None or permanent.counter_count(Counter.FINALITY) <= 0:
        return []
    return [
        ApplicableEffect(
            key=f"finality:{permanent.id}",
            source=None,
            label="finality counter: exile it instead (CR 122.1h)",
            apply=_exile_instead_of_graveyard,
            controller_username=permanent.controller,
        )
    ]


def _exile_instead_of_graveyard(
    game: "Game", source: CardState | None, event: ReplaceableEvent
) -> None:
    event.destination = Zone.EXILE


def _die_to_exile_this_turn_effects(
    game: "Game", event: ReplaceableEvent
) -> list[ApplicableEffect]:
    """Essence Burn's own rider (CR 614.1a): "If that permanent would die this
    turn, exile it instead" - one specific permanent, named by a resolved
    spell that is long gone by the time the replacement ever fires, so the
    marker is kept on `Game.die_to_exile_this_turn` the same way `Game.draw_
    redirections` keeps Plagiarize's own sourceless redirection alive.
    """
    if event.kind is not EventKind.ZONE_CHANGE or event.destination is not Zone.GRAVEYARD:
        return []
    if event.origin is not Zone.BATTLEFIELD:
        return []
    permanent = event.card
    if permanent is None or permanent.id not in game.die_to_exile_this_turn:
        return []
    return [
        ApplicableEffect(
            key=f"die_to_exile_this_turn:{permanent.id}",
            source=None,
            label="if it would die this turn, exile it instead",
            apply=_exile_instead_of_graveyard,
            controller_username=permanent.controller,
        )
    ]


def _draw_redirection_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """The draw redirections waiting on this draw event (CR 614.1a).

    Sourceless, like `_shield_effects`: the spell that created one is in a
    graveyard, and CR 614.6 does not care.
    """
    if event.kind is not EventKind.DRAW or event.player is None:
        return []

    def applier(redirection: DrawRedirection) -> Apply:
        def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
            # "that player skips that draw" - the event's own draw is replaced
            # down to nothing, which CR 603.2g then makes trigger nothing.
            event.amount = 0
            # "and you draw a card" - a *new* draw, by a different player, so
            # it goes through `Game.draw_cards` and is itself replaceable
            # (CR 614.6: the modified event is what happens).
            game.draw_cards(game.player(redirection.drawing), 1)

        return apply

    return [
        ApplicableEffect(
            key=f"draw-redirection:{index}",
            source=None,
            label=redirection.label,
            apply=applier(redirection),
            controller_username=redirection.controller,
        )
        for index, redirection in enumerate(game.draw_redirections)
        if redirection.skipping == event.player.username and event.amount > 0
    ]


def applicable_effects(game: "Game", event: ReplaceableEvent) -> list[ApplicableEffect]:
    """Every effect that would modify this event as it stands (CR 614.1, 616.1).

    Sources are the permanents on the battlefield - CR 604.2 makes a static
    ability's continuous effect active while the permanent is there - plus, for
    a permanent entering the battlefield, the entering object's own CR 614.12
    effects, which are read while it is still on its way in, plus the two kinds
    of prevention effect that have no watching permanent behind them: the
    damaged object's own protection (CR 702.16e) and the shields a resolved
    spell left behind (CR 615.1).
    """
    found: list[ApplicableEffect] = []

    found.extend(_protection_effects(game, event))
    found.extend(_shield_effects(game, event))
    found.extend(_regeneration_effects(game, event))
    found.extend(_finality_counter_effects(event))
    found.extend(_die_to_exile_this_turn_effects(game, event))
    found.extend(_draw_redirection_effects(game, event))

    if event.kind is EventKind.ENTERS_BATTLEFIELD and event.card is not None:
        entering = event.card
        for suffix, apply, label, copy_as_it_enters in _self_enters_modifiers(game, entering):
            found.append(
                ApplicableEffect(
                    key=f"{entering.id}:{suffix}",
                    source=entering,
                    label=label,
                    apply=apply,
                    copy_as_it_enters=copy_as_it_enters,
                )
            )
        found.extend(_impending_entering_counters(game, event))

    found.extend(_stack_replacements(game, event))

    # One board, hoisted out of the loop below: `computed_board()` recomputes
    # the whole battlefield on every call (CR 613.5), and `replacements_of_
    # state` now asks it once per permanent for its computed abilities.
    board = game.computed_board()
    for permanent in list(game.battlefield):
        for index, printed in enumerate(replacements_of_state(game, permanent, board)):
            if printed.applies(game, permanent, event):
                found.append(
                    ApplicableEffect(
                        key=f"{permanent.id}:{index}",
                        source=permanent,
                        label=printed.label,
                        apply=printed.apply,
                    )
                )

    return [effect for effect in found if effect.key not in event.applied]


def order_effects(
    game: "Game", event: ReplaceableEvent, candidates: Iterable[ApplicableEffect]
) -> list[ApplicableEffect]:
    """Put the applicable effects in the order they will be applied (CR 616.1).

    The rules hand the choice to the affected object's controller, one effect at
    a time, and there is nobody here to ask. This was `Game.put_triggers_on_stack`'s
    gap for CR 603.3b too, until `Game._order_triggers_by_controller` started
    putting that one to the player; CR 616.1 has no such question yet. The
    stand-in is deterministic: the effects that player
    controls come first, then everybody else's, each group in battlefield order.

    CR 616.1a-d's forced choices are checked first even so, because they are not
    a matter of preference: a self-replacement effect (CR 614.15) must be chosen
    before anything else, then a control-changing one (CR 616.1b), then a
    copy-as-it-enters one (CR 616.1c). Only the third of those is an effect this
    engine can perform - Clone's "enters as a copy of" - and it is sorted ahead
    of everything else here. The other two are still hooks with nothing to hang
    on them, and remain the shape the rule demands.
    """
    ordered = list(candidates)
    chooser = event.chooser(game)
    ordered.sort(
        key=lambda effect: (
            0 if effect.copy_as_it_enters else 1,  # CR 616.1c, before the free choice
            0 if effect.controller == chooser else 1,
        )
    )
    return ordered


def apply_replacements(game: "Game", event: ReplaceableEvent) -> ReplaceableEvent:
    """Run an event through every replacement effect that applies (CR 616.1).

    One effect is applied at a time; the list is then rebuilt against the
    *modified* event, so an effect that no longer applies does nothing
    (CR 614.7) and one that only now applies gets its turn (CR 616.2). Each
    effect is remembered in `event.applied` so it cannot apply twice (CR 614.5),
    which is also what makes the loop terminate.
    """
    while True:
        candidates = applicable_effects(game, event)
        if not candidates:
            return event
        chosen = order_effects(game, event, candidates)[0]
        event.applied.add(chosen.key)
        event.history.append(f"{chosen.name}: {chosen.label}")
        chosen.apply(game, chosen.source, event)
