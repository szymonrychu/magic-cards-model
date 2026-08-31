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
| `[This] enters tapped.` | CR 614.1c | `ENTERS_TAPPED` |
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
  their next untap step." is a trigger even though it contains "skips". Nothing
  is returned for it. Contrast CR 614.1e's "As [this] is turned face up, ...",
  which is a replacement effect.
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
  has neither "would" nor a prevention word and is not claimed.
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

from pydantic import BaseModel

from ..models.card import Card, Color, Type
from ..models.card_state import CardState, Choice, ChoiceKind
from ..models.token import is_token
from ..models.zone import Zone
from .decisions import Decision, DecisionKind

if TYPE_CHECKING:
    from ..models.game import Game
    from ..models.player import Player

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
    #: CR 614.1c - "[This permanent] enters tapped."
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


class ReplacementEffect(BaseModel):
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
    #: What the permanent enters as a copy of.
    copy_of: str | None = None
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

_NUMBER_WORDS = {
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
    "eleven": 11,
    "twelve": 12,
    "a": 1,
    "an": 1,
}

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
_IF_WOULD = re.compile(r"^If (?P<event>.+?\bwould\b.+?),\s*(?P<rest>.+?)\.?$", re.IGNORECASE)

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

# CR 614.1c. `condition` picks up the "If you don't, it enters tapped" form used
# by the modal double-faced lands, and the "unless ..." form used by the duals.
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
    r" as a copy of (?P<copy_of>.+?)(?:,\s*except\s+.+)?\.?$",
    re.IGNORECASE,
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
        # part of the trigger, so the whole paragraph belongs to it.
        if _TRIGGER_OPENER.match(rules_text):
            continue

        body = _COST_PREFIX.sub("", rules_text)
        for sentence in _SENTENCE_SPLIT.split(body):
            sentence = sentence.strip()
            if not sentence:
                continue
            effects.extend(
                effect.model_copy(update={"raw": paragraph, "reminder": reminder, "face": face})
                for effect in _parse_sentence(sentence, names)
            )
    return effects


# --------------------------------------------------------------------------
# Sentence dispatch
# --------------------------------------------------------------------------


def _parse_sentence(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """Match one sentence against every template, in precedence order.

    Precedence matters: "enter tapped as a copy of" must be read as a copy
    effect, not an enters-tapped one, and a prevention sentence starting with
    "If ... would" must be read as prevention rather than as a bare "instead".
    """
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


def _amount_of(word: str) -> tuple[int | None, bool]:
    """Read a templated count. Returns (amount, variable)."""
    word = word.strip().lower()
    if word in ("x", "that many", "any number"):
        return None, True
    if word.isdigit():
        return int(word), False
    if word in _NUMBER_WORDS:
        return _NUMBER_WORDS[word], False
    return None, True


# --------------------------------------------------------------------------
# Prevention, CR 615
# --------------------------------------------------------------------------


def _try_prevent_next(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _PREVENT_NEXT.match(sentence)
    if not match:
        return []
    amount, variable = _amount_of(match.group("amount"))
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
    return [
        _make(
            ReplacementKind.ENTERS_AS_COPY,
            sentence,
            subject=subject,
            copy_of=match.group("copy_of").strip(),
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
    amount, variable, counter_kind = _read_counters(what)
    return [
        _make(
            ReplacementKind.ENTERS_WITH,
            sentence,
            subject=subject,
            replacement=what,
            amount=amount,
            variable_amount=variable,
            counter_kind=counter_kind,
            condition=(match.group("condition") or "").strip() or None,
            self_replacement=_refers_to_self(subject, names),
        )
    ]


_COUNTERS = re.compile(r"^(?P<amount>[\w+/-]+) (?P<kind>.+?) counters?$", re.IGNORECASE)


def _read_counters(what: str) -> tuple[int | None, bool, str | None]:
    """Read "four +1/+1 counters", "X charge counters", "a shield counter".

    Anything more elaborate - Agent's Toolkit enters with four different kinds
    at once - leaves the counter fields empty rather than picking one.
    """
    match = _COUNTERS.match(what.strip())
    if not match:
        return None, False, None
    amount, variable = _amount_of(match.group("amount"))
    return amount, variable, match.group("kind").strip()


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
    colors = card.colors
    return Color.BLACK in colors or Color.RED in colors


def _kalitas_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "If a nontoken creature an opponent controls would die..."

    CR 700.4: "dies" is "put into a graveyard from the battlefield", so both the
    origin and the destination are part of the condition. "Nontoken" is a real
    condition now that tokens exist (CR 111.1, CR 111.6: "a token isn't a card"),
    and it matters: a token creature that Kalitas exiled instead of letting it
    die would never trigger a dies trigger, and CR 111.7's parenthesis says it
    should.
    """
    card = event.card
    return (
        _to_graveyard(event)
        and event.origin is Zone.BATTLEFIELD
        and card is not None
        and not is_token(card)
        and Type.CREATURE in card.types
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


def _double_life(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    event.amount *= 2


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
    event.amount = 2


def _doubling_season_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
    """ "If an effect would put one or more counters on a permanent you control..."

    CR 122.6: "counters being put on an object ... refers to putting counters on
    that object while it's on the battlefield and also to an object that's given
    counters as it enters the battlefield", which is why the enters-with
    counters of CR 614.1c reach this too.
    """
    return (
        event.kind is EventKind.ADD_COUNTERS
        and event.amount > 0
        and event.card is not None
        and event.card.controller == source.controller
    )


def _double_counters(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    event.amount *= 2


def _doubling_season_tokens_applies(
    game: "Game", source: CardState, event: ReplaceableEvent
) -> bool:
    """ "If an effect would create one or more tokens under your control..."

    "Under your control" is CR 111.2's "the token enters the battlefield under
    that player's control", so the test is against the player *creating* them and
    not against whoever the effect belongs to - Kozilek's Command makes the
    targeted player the creator, and a Doubling Season that player does not
    control does nothing about it.

    "One or more" is why `amount > 0` is checked: creating nothing is not an
    event this can double.
    """
    return (
        event.kind is EventKind.CREATE_TOKENS
        and event.amount > 0
        and event.player is not None
        and event.player.username == source.controller
    )


def _double_tokens(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "...it creates twice that many of those tokens instead."

    "Those tokens" - the characteristics are untouched, only the count changes,
    which is what CR 701.7b's ordering guarantees is still possible: the
    replacement lands before any continuous effect has had a say about what the
    tokens will look like.
    """
    event.amount *= 2


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


# -- "if you would gain life, you gain twice that much life instead" --


def _compile_life_gain_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.event or "").strip().lower() != "you would gain life":
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "you gain twice that much life":
        return None
    return CardReplacement(label=effect.text, applies=_archive_life_applies, apply=_double_life)


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


# -- "if an effect would create one or more tokens under your control, it
#     creates twice that many of those tokens instead" --


def _compile_token_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    expected_event = "an effect would create one or more tokens under your control"
    if (effect.event or "").strip().lower() != expected_event:
        return None
    expected = "it creates twice that many of those tokens"
    if (effect.replacement or "").strip().rstrip(".").lower() != expected:
        return None
    return CardReplacement(
        label=effect.text, applies=_doubling_season_tokens_applies, apply=_double_tokens
    )


# -- "if an effect would put one or more counters on a permanent you control,
#     it puts twice that many of those counters on that permanent instead" --


def _compile_counter_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    expected_event = "an effect would put one or more counters on a permanent you control"
    if (effect.event or "").strip().lower() != expected_event:
        return None
    expected_replacement = "it puts twice that many of those counters on that permanent"
    if (effect.replacement or "").strip().rstrip(".").lower() != expected_replacement:
        return None
    return CardReplacement(
        label=effect.text, applies=_doubling_season_applies, apply=_double_counters
    )


# -- "if one or more <kind> counters would be put on a creature you control,
#    that many <kind> counters minus one are put on it instead" --
#
# Vizier of Remedies: "If one or more -1/-1 counters would be put on a
# creature you control, that many -1/-1 counters minus one are put on it
# instead." CR 614.16 is the same clause `_compile_counter_doubler` already
# leans on - "if an effect would put one or more counters on a permanent"
# replacement effects apply whether the event came from a resolving effect
# *or from a cost* ("even if the original event being modified wasn't itself
# an effect") - so this compiler and `Game.add_counters` together are what
# make Vizier stop Devoted Druid's own activation cost, not only a spell's.
_COUNTER_REDUCER_EVENT_RE = re.compile(
    r"^one or more (?P<kind>[+/\w-]+) counters would be put on a "
    r"(?P<subject>creature|permanent) you control$",
    re.IGNORECASE,
)
_COUNTER_REDUCER_REPLACEMENT_RE = re.compile(
    r"^that many (?P<kind>[+/\w-]+) counters minus one are put on it$", re.IGNORECASE
)


def _counter_reducer_applies(
    kind: str, creature_only: bool
) -> Callable[["Game", CardState, ReplaceableEvent], bool]:
    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.ADD_COUNTERS or event.amount <= 0:
            return False
        if event.card is None or event.card.controller != source.controller:
            return False
        if creature_only and not event.card.is_creature:
            return False
        return (event.counter_kind or "").strip().lower() == kind

    return applies


def _reduce_counters(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "...that many [counters] minus one are put on it instead."

    CR 614.5 gives a replacement effect only one opportunity to affect an
    event, so this is a flat minus one regardless of how many counters were
    headed for the permanent - not a floor applied per counter. When only one
    counter would have been placed, one minus one is zero: no counter is put
    on at all, which `Game.add_counters` already treats as nothing to do for
    a non-positive amount, the same way it already does for the doubler's
    opposite case. There is no numbered CR clause for the zero floor itself -
    it is what "one minus one" already equals; `max(..., 0)` only guards
    against a `-1/-1 counters minus one` misreading a larger single removal as
    negative, which no printed card's wording asks for.
    """
    event.amount = max(event.amount - 1, 0)


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


def _compile_counter_reducer(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _COUNTER_REDUCER_EVENT_RE.match((effect.event or "").strip())
    if event_match is None:
        return None
    replacement_match = _COUNTER_REDUCER_REPLACEMENT_RE.match(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    event_kind = event_match.group("kind").strip().lower()
    replacement_kind = replacement_match.group("kind").strip().lower()
    if event_kind != replacement_kind:
        return None
    creature_only = event_match.group("subject").strip().lower() == "creature"
    return CardReplacement(
        label=effect.text,
        applies=_counter_reducer_applies(event_kind, creature_only),
        apply=_reduce_counters,
    )


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
    _compile_token_doubler,
    _compile_counter_doubler,
    _compile_counter_reducer,
    _compile_lands_you_control_enter_untapped,
)


def parsed_card_replacements(card: Card) -> list[CardReplacement]:
    """Every generic shape above that this card's own oracle text matches."""
    found: list[CardReplacement] = []
    for effect in parse_replacement_effects(card):
        for compiler in _COMPILERS:
            compiled = compiler(effect)
            if compiled is not None:
                found.append(compiled)
                break
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


def replacements_of_state(permanent: CardState) -> list[CardReplacement]:
    """Like `replacements_of`, but reads a *live permanent's* level-gated
    text (CR 716.2a) rather than its printed card wholesale.

    Only a Class needs this: `CardState.class_ability_text` is exactly
    `oracle_text` for anything else, so this is a safe, behaviour-preserving
    substitute for `replacements_of(permanent.card)` at every battlefield
    scan - Artist's Talent's own level 3 must not double as a level 1's
    damage-plus-2, before the Class has actually reached level 3.
    """
    explicit = REPLACEMENTS.get(permanent.card.name)
    if explicit is not None:
        return explicit
    if not permanent.is_class:
        return parsed_card_replacements(permanent.card)
    names = _names_of(permanent.card)
    found: list[CardReplacement] = []
    for effect in _parse_oracle_text(permanent.class_ability_text, face=None, names=names):
        for compiler in _COMPILERS:
            compiled = compiler(effect)
            if compiled is not None:
                found.append(compiled)
                break
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
        if not game.may_pay_life(who, amount, source=card_name):
            event.tapped = True

    return apply


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


class UnwiredChoiceNotice(BaseModel):
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
      `why_cannot_activate`. Disruptor Flute's other line, "Spells with the
      chosen name cost {3} more to cast.", is the same gap on the casting
      side (CR 601.2f's cost-increase step has no per-name lookup).
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
            or _LAYER_HANDLED_SUBJECT_RE.match(sentence)
        ):
            continue
        found.append(UnwiredChoiceNotice(source_id=source_id, source_name=card.name, text=sentence))
    return found


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
            prompt=f"choose a {kind.value.replace('_', ' ')}",
            source=card_name,
            options=_COLOR_OPTIONS if kind is ChoiceKind.COLOR else (),
        )
        value = game.ask(decision)
        assert isinstance(value, str)
        source.choice = Choice(kind=kind, value=value)
        game.unwired_choice_notices.extend(_unwired_choice_notices(source.card, source.id))

    return apply


def _self_enters_modifiers(game: "Game", card_state: CardState) -> list[tuple[str, Apply, str]]:
    """The card's own "enters ..." replacement effects, as things to apply.

    CR 614.12: "Some replacement effects modify how a permanent enters the
    battlefield. Such effects may come from the permanent itself if they affect
    only that permanent." That is why these are read off the entering card while
    it is not yet on the battlefield, unlike every other entry in `REPLACEMENTS`.

    Four shapes are performed:

    - "[This] enters tapped" and "[this] enters with N counters", unconditional
      (CR 614.1c).
    - "As this land enters, you may pay N life. If you don't, it enters tapped"
      - one choice spread over two printed sentences, which the parser reads as
      an optional `AS_ENTERS` followed by an `ENTERS_TAPPED` whose condition is
      the back-reference "you don't". Joined back together here, because they
      are not two effects: CR 614.12a's choice is singular.
    - "As [this] enters, choose a color/card name/creature type" - CR 614.12a's
      choice recorded on the entering object itself (`CardState.choice`) rather
      than changing the `ReplaceableEvent`, since nothing about *this* choice
      is a tapped flag or a counter count. See `_choose_a_quality`.

    A condition about the *board* rather than about a choice - Arena of Glory's
    "unless you control a Mountain" - is still skipped.

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
    performable: list[tuple[str, Apply, str]] = []
    consumed: set[int] = set()

    for index, effect in enumerate(parsed):
        if index in consumed or not effect.self_replacement:
            continue

        payment = _PAY_LIFE_CHOICE.search(effect.replacement or "")
        if effect.kind is ReplacementKind.AS_ENTERS and effect.optional and payment:
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
                        _pay_life_or_tapped(int(payment.group(1)), card_state.card.name),
                        f"{effect.text} {parsed[follower].text}",
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
                    )
                )
                continue

        if effect.condition is not None:
            continue
        amount = effect.amount
        if (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is None
            and effect.variable_amount
        ):
            # CR 107.3m: only a spell that actually resolved into this object
            # defines X here - `game.cast_records` is popped once resolution
            # finishes, so its presence here is exactly that fact, and an
            # entry with no record at all (this object arrived some other
            # way) leaves `amount` `None` and the effect skipped, unchanged
            # from before.
            record = game.cast_records.get(card_state.id)
            if record is not None:
                amount = record.x_value
        readable_counters = (
            effect.kind is ReplacementKind.ENTERS_WITH
            and effect.counter_kind is not None
            and amount is not None
        )
        if effect.kind is ReplacementKind.ENTERS_TAPPED or readable_counters:
            performable.append((f"self:{index}", _apply_self_enters(effect, amount), effect.text))
    return performable


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

    if event.kind is EventKind.ENTERS_BATTLEFIELD and event.card is not None:
        entering = event.card
        for suffix, apply, label in _self_enters_modifiers(game, entering):
            found.append(
                ApplicableEffect(
                    key=f"{entering.id}:{suffix}",
                    source=entering,
                    label=label,
                    apply=apply,
                )
            )

    found.extend(_stack_replacements(game, event))

    for permanent in list(game.battlefield):
        for index, printed in enumerate(replacements_of_state(permanent)):
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
    a time, and there is nobody here to ask - the same gap `Game.put_triggers_on_stack`
    has for CR 603.3b. The stand-in is deterministic: the effects that player
    controls come first, then everybody else's, each group in battlefield order.

    CR 616.1a-d's forced choices are checked first even so, because they are not
    a matter of preference: a self-replacement effect (CR 614.15) must be chosen
    before anything else, then a control-changing one (CR 616.1b), then a
    copy-as-it-enters one (CR 616.1c). No effect the engine can perform is any of
    those yet, so the hook currently never fires - but it is the shape the rule
    demands, and it is where such an effect will plug in.
    """
    ordered = list(candidates)
    chooser = event.chooser(game)
    ordered.sort(key=lambda effect: 0 if effect.controller == chooser else 1)
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
