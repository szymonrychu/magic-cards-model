import functools
import re
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Literal

from ...models.card import Card, Color, Supertype, Type
from ...models.card_state import CardState, ChoiceKind
from ...models.token import TokenDefinition, is_token
from ...models.zone import Zone
from ...numbers import COUNT, MULTIPLIER, parse_count, parse_multiplier
from ..abilities import keywords_in_lines, self_reference_names
from ..combat import Keyword
from ..damage_modification import (
    DamageCantBePreventedReplacement,
    DamageModifierReplacement,
    DamageRedirectReplacement,
    PreventDamageByReplacement,
    TurnDamageGroup,
    compile_damage_plus_source_characteristic,
    compile_heal_other_damage,
)
from ..decisions import source_id_of

if TYPE_CHECKING:
    from ...models.game import Game
    from ...models.player import Player
from .enters import (
    _compile_enters_uncast_exile,
    _compile_lands_you_control_enter_untapped,
    _compile_opponents_permanents_enter_tapped,
)
from .model import (
    Applies,
    Apply,
    CardReplacement,
    CopyException,
    CreatedReplacementSpec,
    DieToExileReplacement,
    ManaProductionReplacement,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)

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
#: "it's legendary and snow in addition to its other types" (Moritte of the
#: Frost) - supertypes gained on top of the copied ones (CR 707.9b, CR
#: 205.1b), with no card type or subtype named.
_COPY_EXCEPT_SUPERTYPES = re.compile(
    r"^(?:he|she|it|they)(?:'s| is|'re| are) "
    r"(?P<supertypes>(?:legendary|snow)(?: and (?:legendary|snow))*) in addition to "
    r"(?:his|her|its|their) other types$",
    re.IGNORECASE,
)

#: CR 707.9f's gated exception, split off the rest of the tail - "..., and,
#: if it's a creature, it enters with two additional +1/+1 counters on it and
#: has changeling" (Moritte of the Frost).
_COPY_EXCEPT_IF_TYPE = re.compile(
    r"^(?P<head>.+?),? and, if (?:he|she|it|they)(?:'s| is|'re| are) an? "
    r"(?P<type>artifact|creature|enchantment|land|planeswalker), (?P<tail>.+)$",
    re.IGNORECASE,
)

#: CR 707.9e's additional effect, as a gated exception prints it: "it enters
#: with two additional +1/+1 counters on it".
_COPY_EXCEPT_ENTERS_WITH_COUNTERS = re.compile(
    rf"^(?:he|she|it|they) enters? with (?P<n>{COUNT}) additional "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?:him|her|it|them)$",
    re.IGNORECASE,
)

_SUPERTYPE_WORDS = {"legendary": Supertype.LEGENDARY, "snow": Supertype.SNOW}

#: A copy exception's own colour word ("black", "blue", ...) - kept local
#: rather than imported, the identical per-module convention `machines/
#: layers.py::_card_type_word`'s own docstring explains (this module already
#: imports `Color` for `CopyException.added_colors`, but not a shared word
#: table for it).
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}

_COPY_EXCEPT_PT_AND_TYPES = re.compile(
    r"^(?:he|she|it|they)(?:'s| is|'re| are) an? (?:(?P<power>\d+)/(?P<toughness>\d+) )?"
    r"(?P<types>[A-Za-z][\w'-]*(?: [A-Za-z][\w'-]*)*) in addition to "
    r"(?:his|her|its|their) other (?:colors? and types|types)$",
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

    Split by `_split_exception_parts`: " and " / ", " before the next
    clause's pronoun is how the printed tails join their clauses, and a quoted
    granted ability (CR 707.9a) is never cut.
    """
    if not clause:
        return None
    name: str | None = None
    power: int | None = None
    toughness: int | None = None
    added_types: list[Type] = []
    added_subtypes: list[str] = []
    added_abilities: list[str] = []
    added_supertypes: list[Supertype] = []
    added_colors: list[Color] = []
    if_type: Type | None = None
    if_type_abilities: list[str] = []
    enters_with_counters: list[tuple[str, int]] = []

    clause = clause.strip()
    if gated := _COPY_EXCEPT_IF_TYPE.match(clause):
        # CR 707.9f: the gated tail is read on its own; the head is read
        # below exactly as an ungated tail would be.
        if_type = _CARD_TYPE_WORDS.get(gated.group("type").lower())
        clause = gated.group("head")
        tail = gated.group("tail").strip().rstrip(".")
        # "it enters with ... on it and has changeling": the second clause
        # drops its pronoun, sharing the first one's subject.
        for piece in re.split(r"\s+and\s+(?=has\b|have\b)", tail):
            piece = piece.strip()
            if match := _COPY_EXCEPT_ENTERS_WITH_COUNTERS.match(piece):
                amount = parse_count(match.group("n"))
                if amount is None:
                    return None
                enters_with_counters.append((match.group("kind").lower(), amount))
                continue
            if re.match(r"^(?:has|have) ", piece, re.IGNORECASE):
                piece = f"it {piece}"
            if match := _COPY_EXCEPT_HAS.match(piece):
                granted = _granted_abilities(match.group("what"))
                if granted is None:
                    return None
                if_type_abilities.extend(granted)
                continue
            return None

    for part in _split_exception_parts(clause.strip()):
        if match := _COPY_EXCEPT_NAME.match(part):
            name = match.group("name").strip()
            continue
        if match := _COPY_EXCEPT_PT_AND_TYPES.match(part):
            if match.group("power") is not None:
                power = int(match.group("power"))
                toughness = int(match.group("toughness"))
            for word in match.group("types").split():
                color = _COLOR_WORDS.get(word.lower())
                card_type = _CARD_TYPE_WORDS.get(word.lower())
                if color is not None:
                    # Lazotep Convert's own "a 4/4 black Zombie in addition
                    # to its other colors and types" (CR 105.3) - a colour
                    # word here is never also a card type or subtype word
                    # (CR 105.1's five colours share no spelling with any
                    # CR 205.2a card type or real CR 205.3 subtype), so
                    # checking it first cannot misread a genuine subtype.
                    added_colors.append(color)
                elif card_type is not None:
                    added_types.append(card_type)
                else:
                    # CR 205.3: anything that is not one of CR 300.1's card
                    # types in this position is a subtype - "Spider Human
                    # Hero", stored capitalised the way every subtype is.
                    added_subtypes.append(word)
            continue
        if match := _COPY_EXCEPT_HAS.match(part):
            granted = _granted_abilities(match.group("what"))
            if granted is None:
                return None
            added_abilities.extend(granted)
            continue
        if match := _COPY_EXCEPT_SUPERTYPES.match(part):
            added_supertypes.extend(
                _SUPERTYPE_WORDS[word.lower()] for word in match.group("supertypes").split(" and ")
            )
            continue
        return None

    if (
        name is None
        and power is None
        and not added_types
        and not added_subtypes
        and not added_abilities
        and not added_supertypes
        and not added_colors
        and not if_type_abilities
        and not enters_with_counters
    ):
        return None
    return CopyException(
        name=name,
        power=power,
        toughness=toughness,
        added_colors=tuple(added_colors),
        added_types=tuple(added_types),
        added_subtypes=tuple(added_subtypes),
        added_abilities=tuple(added_abilities),
        added_supertypes=tuple(added_supertypes),
        if_type=if_type,
        if_type_abilities=tuple(if_type_abilities),
        enters_with_counters=tuple(enters_with_counters),
    )


#: Where one exception ends and the next begins, outside quoted text: ", and "
#: / ", " / " and " followed by the pronoun that opens every exception clause
#: ("his name is ... and he's a 4/4 ...", "it's a Bird ... and it has
#: flying"). Anchoring on the pronoun is what keeps a keyword list's own "and"
#: ("it has flying and haste") inside its clause.
_EXCEPTION_SEPARATOR = re.compile(
    r"(?:,\s*and\s+|,\s+|\s+and\s+)(?=(?:he|she|it|they|his|her|its|their)\b)",
    re.IGNORECASE,
)


def _split_exception_parts(clause: str) -> list[str]:
    """An "except ..." tail cut into its clauses, never inside a quoted ability.

    Phantasmal Image's granted trigger - "When this creature becomes the
    target of a spell or ability, sacrifice it." - carries its own comma and
    would otherwise be cut at it; quoted spans are masked before splitting
    and restored in the pieces.
    """
    masked = re.sub(r'"[^"]*"', lambda quoted: "\x00" * len(quoted.group(0)), clause)
    parts: list[str] = []
    start = 0
    for separator in _EXCEPTION_SEPARATOR.finditer(masked):
        parts.append(clause[start : separator.start()])
        start = separator.end()
    parts.append(clause[start:])
    return [part.strip().rstrip(".").strip() for part in parts if part.strip()]


#: CR 707.9a's granted ability: "it has flying" / "it has "<ability>"".
_COPY_EXCEPT_HAS = re.compile(
    r"^(?:he|she|it|they) (?:has|have) (?P<what>.+)$", re.IGNORECASE | re.DOTALL
)

_QUOTED_ABILITY = re.compile(r'"(?P<ability>[^"]+)"')


def _granted_abilities(what: str) -> list[str] | None:
    """The ability lines a copy exception's "it has ..." grants, or `None`.

    Two shapes, the two a copy exception prints: one or more quoted abilities
    joined by "and" (read whole, quotes removed - CR 707.9a's gained ability
    is exactly that text), or a keyword list validated against the same
    whitelist every layer 6 keyword grant uses. Anything else - Sakashima of a
    Thousand Faces' "it has Sakashima's other abilities" - is `None`, which
    fails the whole tail closed.
    """
    # Imported here: `machines/layers.py` imports this module.
    from ..layers import split_and_validate_keywords

    what = what.strip().rstrip(".").strip()
    if what.startswith('"'):
        quoted = [match.group("ability").strip() for match in _QUOTED_ABILITY.finditer(what)]
        leftover = _QUOTED_ABILITY.sub("", what)
        if not quoted or re.sub(r"[\s,]|\band\b", "", leftover):
            return None
        return quoted
    if what.lower() in _COPY_EXCEPTION_CDA_KEYWORDS:
        # Omni-Changeling's "except it has changeling": CR 702.73a's
        # characteristic-defining ability, gained as a copiable value (CR
        # 707.9a) - so it defines the copy's creature types in layer 4 the
        # way a printed changeling does (`machines/layers._changeling_
        # effects` reads it off the board as layer 1 left it).
        return [what.capitalize()]
    return split_and_validate_keywords(what)


#: Keywords a copy exception may grant that are not combat keywords and so
#: are not on `split_and_validate_keywords`' layer 6 whitelist: CR 702.73a's
#: changeling, a characteristic-defining ability that only means something as
#: a copiable value (CR 604.3a: one granted by a later effect is no CDA).
_COPY_EXCEPTION_CDA_KEYWORDS = frozenset({"changeling"})


# CR 614.1e.
_AS_TURNED_FACE_UP = re.compile(
    r"^As (?P<subject>.+?) is turned face up,\s*(?P<effect>.+?)\.?$", re.IGNORECASE
)
#: Multiversal Passage's own "As this land enters, choose a basic land type.
#: Then you may pay 2 life. If you don't, it enters tapped." - CR 614.12a's
#: payment offer spread over a sentence of its own rather than fused into
#: the leading "As [this] enters, ..." clause the way a shockland's "As this
#: land enters, you may pay 2 life." always has been, because that clause is
#: already spent on the type choice here. "Then" is the only connective
#: printed for this shape in the pool; the payment itself (`_optional_
#: enters_payment`) and the pairing with the following "If you don't, it
#: enters tapped." (`_self_enters_modifiers`) are unchanged, since both work
#: off `ReplacementKind.AS_ENTERS`/`.replacement`/`.optional` alone and never
#: look at how the choice was introduced.
_THEN_OPTIONAL_PAYMENT_RE = re.compile(r"^Then (?P<effect>you may .+?)\.?$", re.IGNORECASE)

# CR 615.
_PREVENT_NEXT = re.compile(
    r"^Prevent the next (?P<amount>[\w-]+) (?P<combat>combat )?damage that would be dealt"
    r"(?: to (?P<target>.+?))? this turn\.?$",
    re.IGNORECASE,
)
_PREVENT_ALL = re.compile(
    r"^Prevent all (?P<combat>(?P<noncombat>non)?combat )?damage that would be dealt"
    r"(?P<rest>.*?)\.?$",
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
    the battlefield tapped"), and legendary cards use their short name - the
    part before a comma ("Kalitas, Bloodchief of Ghet" -> "Kalitas") or, when
    there is no comma, the bare first word ("Shimatsu the Bloodcloaked" ->
    "Shimatsu", whose own text reads "As Shimatsu enters, ...") - so the full
    name, its comma-split head, and its first word all count. CR 201.5c:
    "Text printed on some cards refers to that card by a shortened version of
    its name. Instances of a card's shortened name used in this manner are
    treated as though they used the card's full name."
    """
    names: list[str] = []
    for name in [card.name, *(face.name for face in card.card_faces or [])]:
        for part in name.split("//"):
            part = part.strip()
            if not part:
                continue
            names.append(part)
            names.append(part.split(",")[0].strip())
            if Supertype.LEGENDARY in card.supertypes:
                # CR 201.5c's shortened name is a legendary card's usage;
                # a nonlegendary "Goblin Guide" is never "Goblin".
                names.append(part.split()[0].strip())
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
        rules_text = _expand_devour(rules_text)

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
                if linked is not None and (
                    effect.kind in ENTERS_KINDS or effect.kind is ReplacementKind.IF_WOULD_INSTEAD
                ):
                    update["linked_trigger"] = linked
                effects.append(effect.model_copy(update=update))
    return effects


#: CR 702.82a/c's keyword line: "Devour N" or "Devour [quality] N" (Famished
#: Worldsire's "Devour land 3").
_DEVOUR_KEYWORD = re.compile(r"^devour(?: (?P<quality>[a-z]+))? (?P<n>\d+)$", re.IGNORECASE)


def _expand_devour(rules_text: str) -> str:
    """A Devour keyword line spelled out as the two sentences CR 702.82 says
    it means, or `rules_text` unchanged.

    CR 702.82a: "'Devour N' means 'As this object enters, you may sacrifice
    any number of creatures. This permanent enters with N +1/+1 counters on
    it for each creature sacrificed this way.'" CR 702.82c: "'Devour
    [quality] N' means 'As this object enters, you may sacrifice any number
    of [quality] permanents. ...'" - the same CR 614.12a sacrifice-then-
    counters pair Devouring Hellion prints in full, so it is read by the
    same `_sacrifice_any_number_choice`/"`<multiplier>` that many" readers
    rather than a second implementation of its own.
    """
    match = _DEVOUR_KEYWORD.match(rules_text.strip().rstrip("."))
    if match is None:
        return rules_text
    quality = match.group("quality")
    what = f"{quality.lower()}s" if quality else "creatures"
    n = int(match.group("n"))
    multiplier = "" if n == 1 else f"{n} times "
    return (
        f"As this creature enters, you may sacrifice any number of {what}. "
        f"If you do, it enters with {multiplier}that many +1/+1 counters on it."
    )


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
        _try_first_time_would,
        _try_source_damage_plus_recipient_list,
        _try_if_would,
        # "As X enters or is turned face up" must be read by the enters parser
        # first, or the face-up parser swallows "X enters or" as the subject.
        _try_as_enters,
        _try_as_turned_face_up,
        _try_enters_as_copy,
        _try_enters_tapped,
        _try_enters_prepared,
        _try_enters_untapped,
        _try_enters_with,
        _try_escapes_with,
        _try_skip,
        _try_player_skips,
        _try_instead_of,
        _try_rather_than,
        _try_then_optional_payment,
    ):
        found = parser(sentence, names)
        if found:
            return found

    if _CUE.search(sentence) and not _PREVENTED_BACKREFERENCE.search(sentence):
        return [ReplacementEffect(kind=ReplacementKind.UNPARSED, raw=sentence, text=sentence)]
    return []


def _make(kind: ReplacementKind, sentence: str, **fields) -> ReplacementEffect:
    return ReplacementEffect(kind=kind, raw=sentence, text=sentence, **fields)


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
            # "noncombat" is the opposite restriction, read off the sentence
            # by `_compile_prevent_all_to_group`.
            combat_only=bool(match.group("combat")) and not match.group("noncombat"),
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


#: CR 614.1a's "instead", gated on the event being the first of its kind this
#: turn: "[As long as <condition>, ]the first time you would create one or
#: more tokens each turn, you may instead create that many tokens that are
#: copies of equipped creature." (Mirrormind Crown; Moonlit Meditation
#: without the "as long as").
_FIRST_TIME_WOULD = re.compile(
    r"^(?:As long as (?P<condition>[^,]+),\s*)?the first time (?P<event>.+?\bwould\b.+?) "
    r"each turn,\s*(?P<rest>.+?)\.?$",
    re.IGNORECASE,
)


def _try_first_time_would(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    match = _FIRST_TIME_WOULD.match(sentence)
    if not match:
        return []
    rest = match.group("rest").strip()
    if not re.search(r"\binstead\b", rest, re.IGNORECASE):
        return []
    replacement = re.sub(r"\s*\binstead\b\s*", " ", rest, flags=re.IGNORECASE)
    replacement = re.sub(r"\s{2,}", " ", replacement).rstrip(".").strip()
    return [
        _make(
            ReplacementKind.IF_WOULD_INSTEAD,
            sentence,
            event=match.group("event").strip(),
            replacement=replacement or None,
            condition=(match.group("condition") or "").strip() or None,
            optional=_is_optional(rest),
            first_time_each_turn=True,
        )
    ]


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


#: `_IF_WOULD`'s own event/rest split is `.+?` (non-greedy): it stops at the
#: *first* comma, which is right for the common case (a comma-free event, a
#: replacement clause that may itself list several results). Disciples of the
#: Inferno's "If a noncreature source you control would deal damage to a
#: creature, battle, or opponent, it deals that much damage plus 2 instead."
#: has an Oxford-comma *recipient list inside the event itself*
#: (`_DAMAGE_RECIPIENTS`'s own "a creature, battle, or opponent"), so the
#: first comma falls inside "a creature, battle, or opponent" rather than
#: between event and rest, and `_IF_WOULD` misreads the event as truncated at
#: "... to a creature" with the rest of the recipient list swallowed into
#: "rest" - `_SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE`/`_SOURCE_DAMAGE_MODIFIER_RE`
#: then both fail to `fullmatch` the wrong halves, so a genuinely-templated
#: card (Torbran, Jaya, Pyromancer's Swath and the rest of this same "source
#: you control would deal damage" family, per that family's own docstring)
#: reads unaudited for a splitting defect, not an engine one.
#:
#: This is `_IF_WOULD`'s identical shape, but anchored on the fixed "it
#: deals ... instead" tail `_SOURCE_DAMAGE_MODIFIER_RE`'s own family always
#: prints, which lets the (still non-greedy, still trying the first comma
#: first) event group's regex backtracking find the *right* comma - the one
#: whose tail actually reads as that fixed shape - rather than widening
#: `_IF_WOULD` itself, which would trade this family's bug for the opposite
#: one on any card whose *replacement* clause (not its event) carries the
#: internal comma list instead (a real, more common shape - see the
#: docstring above `_try_if_would`'s own dispatch position). Tried ahead of
#: `_try_if_would` in `_parse_sentence` so it gets first look at exactly this
#: family's own shape; every other sentence falls through to `_try_if_would`
#: unchanged.
_SOURCE_DAMAGE_PLUS_RECIPIENT_LIST_RE = re.compile(
    rf"^If (?P<event>an? (?:[a-z]+ )?source you control would deal "
    rf"(?:noncombat )?damage to .+?),\s*"
    rf"(?P<rest>it deals (?:that much damage plus {COUNT}"
    rf"|(?:double|triple) that damage)"
    rf"(?: to that (?:permanent or player|player or permanent))? instead)\.?$",
    re.IGNORECASE,
)


def _try_source_damage_plus_recipient_list(
    sentence: str, names: tuple[str, ...]
) -> list[ReplacementEffect]:
    match = _SOURCE_DAMAGE_PLUS_RECIPIENT_LIST_RE.match(sentence)
    if not match:
        return []
    event = match.group("event").strip()
    rest = match.group("rest").strip()
    replacement = re.sub(r"\s*\binstead\b\s*", " ", rest, flags=re.IGNORECASE).strip()
    replacement = re.sub(r"\s{2,}", " ", replacement).rstrip(".").strip()
    return [
        _make(
            ReplacementKind.IF_WOULD_INSTEAD,
            sentence,
            event=event,
            replacement=replacement or None,
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


def _try_then_optional_payment(sentence: str, names: tuple[str, ...]) -> list[ReplacementEffect]:
    """`_THEN_OPTIONAL_PAYMENT_RE`'s shape - Multiversal Passage's own "Then
    you may pay 2 life." continuing an earlier "As this land enters, ..."
    clause that was already spent on a different CR 614.12a choice.

    `subject` is left `None` (nothing names one in "Then you may ...") and
    `self_replacement` is `True` unconditionally: this connective only ever
    continues the permanent's own entering paragraph in the pool, the same
    way `_ENTERS_TAPPED`'s trailing "If you don't" back-reference is never
    read as anything but part of the choice that precedes it.
    """
    match = _THEN_OPTIONAL_PAYMENT_RE.match(sentence)
    if not match:
        return []
    effect = match.group("effect").strip()
    return [
        _make(
            ReplacementKind.AS_ENTERS,
            sentence,
            replacement=effect,
            optional=True,
            self_replacement=True,
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

#: "a +1/+1 counter on it for each instant and sorcery card exiled with it"
#: (Murktide Regent) and "an additional loyalty counter on him for each
#: instant and sorcery spell you've cast this turn" (Ral, Leyline Prodigy) -
#: a singular counter, once per matching thing, rather than `_COUNTERS_EQUAL_
#: TO`'s "a number of ... equal to [expression]" or `_COUNTERS`'s literal
#: count. `kind` reads the same as both of those; the "for each ..." tail is
#: carried as `amount_expression` unevaluated, the same field `_COUNTERS_
#: EQUAL_TO` fills, and read the same way by `_self_enters_modifiers` -
#: `machines/effects.amount_expression`'s own terms are what actually know
#: how to count "instant and sorcery card(s) exiled with it" and "instant and
#: sorcery spell(s) you've cast this turn".
_COUNTER_FOR_EACH = re.compile(
    r"^an? (?:additional )?(?P<kind>[\w+/-]+) counters?"
    r"(?: on (?:it|him|her|them))? for each (?P<description>.+?)$",
    re.IGNORECASE,
)

#: "[`<multiplier>`] that many `<kind>` counters" - Shimatsu the Bloodcloaked's
#: bare "that many +1/+1 counters" and Devouring Hellion's "twice that many
#: +1/+1 counters". Unlike `_amount_of`'s own refusal of "that many" as a
#: guessed CR 107.3m X (that count is not knowable from the text alone), this
#: count *is* knowable - it is carried from a sibling `AS_ENTERS` "[you may
#: ]sacrifice any number of `<description>`" choice in the same paragraph, and
#: `_self_enters_modifiers` is what pairs the two and fills it in from how
#: many were actually sacrificed (CR 614.12a).
_THAT_MANY_COUNTERS = re.compile(
    rf"^(?:(?P<multiplier>{MULTIPLIER})\s+)?that many (?P<kind>.+?) counters?$",
    re.IGNORECASE,
)


def _read_counters(
    what: str,
) -> tuple[int | None, bool, str | None, str | None, int | None] | None:
    """Read "four +1/+1 counters", "X charge counters", "a shield counter",
    "a number of +1/+1 counters on it equal to [expression]", and "[`<multiplier>`]
    that many `<kind>` counters".

    Returns `(amount, variable, kind, expression, that_many_multiplier)`. The
    "equal to" shape fills only `expression`, always leaving `amount` unset and
    `variable` true - the count is not knowable from the text alone. The "that
    many" shape fills only `that_many_multiplier` (1 for a bare "that many",
    2 for "twice that many", and so on), also leaving `amount` unset and
    `variable` true - the count is knowable, but only once a sibling clause's
    own choice has been made (see `_THAT_MANY_COUNTERS`).

    Anything more elaborate - Agent's Toolkit enters with four different kinds
    at once - leaves the counter fields empty rather than picking one. A count
    word that is neither of the above ("your choice of") is None: unreadable.
    """
    text = what.strip()
    equal_to = _COUNTERS_EQUAL_TO.match(text)
    if equal_to:
        return (
            None,
            True,
            equal_to.group("kind").strip(),
            equal_to.group("expression").strip(),
            None,
        )
    for_each = _COUNTER_FOR_EACH.match(text)
    if for_each:
        return (
            None,
            True,
            for_each.group("kind").strip(),
            for_each.group("description").strip(),
            None,
        )
    that_many = _THAT_MANY_COUNTERS.match(text)
    if that_many:
        multiplier_text = that_many.group("multiplier")
        multiplier = 1 if multiplier_text is None else parse_multiplier(multiplier_text)
        if multiplier is None:
            return None
        return None, True, that_many.group("kind").strip(), None, multiplier
    match = _COUNTERS.match(text)
    if not match:
        return None, False, None, None, None
    read = _amount_of(match.group("amount"))
    if read is None:
        return None
    amount, variable = read
    return amount, variable, match.group("kind").strip(), None, None


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


#: The step a controller's own static "Skip your <step> step." names - the
#: `_SKIP` event, restricted to "your" (the permanent's controller) and a
#: step the turn machine can skip. Only the draw step is read today; CR 614.10
#: makes every other "skip your X step" the same replacement, and a new step
#: joins by adding its word here and a check where that step begins.
_SKIP_OWN_STEP_RE = re.compile(r"^your (?P<step>draw) step$", re.IGNORECASE)


def skipped_own_step_of_line(line: str) -> str | None:
    """ "Skip your draw step." -> "draw", or `None`. The static form of CR
    614.10's skip, about the permanent's controller."""
    text = strip_reminder_text(line)[0].strip()
    effects = _try_skip(text, ())
    if len(effects) != 1:
        return None
    match = _SKIP_OWN_STEP_RE.match((effects[0].event or "").strip())
    return None if match is None else match.group("step").lower()


def draw_step_skipped_by(game: "Game", username: str) -> CardState | None:
    """The first permanent `username` controls whose static ability skips their
    draw step (CR 614.10), read off its computed ability lines (CR 613.1f), or
    `None`. CR 614.10a/500.11: the step is then passed as though it did not
    exist."""
    for permanent in game.permanents_controlled_by(username):
        try:
            lines = game.characteristics_of(permanent).abilities
        except KeyError:
            lines = (permanent.oracle_text or "").splitlines()
        if any(skipped_own_step_of_line(line) == "draw" for line in lines):
            return permanent
    return None


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


#: "If this creature would leave the battlefield, exile it instead of putting
#: it anywhere else." - the line a permanent is granted (Geth, Thane of
#: Contracts) or prints. The subject is the permanent itself, in either of the
#: two ways a granted line names it: "this <type>" or "it".
_LEAVE_EXILE_LINE_RE = re.compile(
    r"^if (?:this [a-z]+|it) would leave the battlefield, "
    r"exile (?:it|this [a-z]+) instead of putting it anywhere else\.?$",
    re.IGNORECASE,
)


def is_leave_exile_line(text: str) -> bool:
    """Whether `text` is the self "would leave the battlefield, exile it
    instead of putting it anywhere else" replacement this module performs."""
    return _LEAVE_EXILE_LINE_RE.fullmatch(text.strip()) is not None


def _exile_instead(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
    """ "...exile it instead" - the card goes to exile and never reaches a graveyard.

    When the replacement's own source prints another ability about cards
    "exiled with" itself (The Darkness Crystal's activated ability), the two
    are linked (CR 607.1) and the exiled card is recorded as exiled with it.
    """
    event.destination = Zone.EXILE
    if source is not None and event.card is not source and _refers_to_cards_exiled_with(source):
        event.exile_link = source


def _refers_to_cards_exiled_with(source: CardState) -> bool:
    """Whether `source`'s printed text refers to cards "exiled with" itself -
    by "this [object]" or by its own name (CR 201.5)."""
    text = source.card.front_oracle_text or ""
    names = "|".join(re.escape(name) for name in self_reference_names(source.card.name))
    return re.search(rf"exiled with (?:this \w+|{names})\b", text) is not None


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


def _counter_amount_applies_to_player(kind: str | None) -> Applies:
    """ "If you would get one or more [kind] counters, ..." - the player twin
    of `CounterAmountReplacement.applies`. "You" is CR 201.5's own reference to
    whoever controls the source printing the ability (its controller, not
    necessarily the player the counters land on in general - every printing
    of this shape in the pool is self-referential, "you" meaning the
    ability's own controller, so that is the only shape read here).

    `kind` `None` is "one or more counters" of any kind (Winding
    Constrictor's own "you get" line); a named kind (Aether Refinery's "{E}")
    is read the same way `CounterAmountReplacement.applies` reads a card-counter
    replacement's own kind.
    """

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.ADD_COUNTERS or event.amount <= 0:
            return False
        if event.card is not None or event.player is None:
            return False
        if event.player.username != source.controller:
            return False
        return kind is None or (event.counter_kind or "").strip().lower() == kind

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


#: "exile it" or "exile it with a <kind> counter on it" - the replacement
#: half. Dauthi Voidwalker's "instead exile it with a void counter on it"
#: leads with "instead", which the parser already strips into this field.
_GRAVEYARD_EXILE_REPLACEMENT_RE = re.compile(
    r"^exile it(?: with an? (?P<counter>[a-z+\-/0-9]+) counter on it)?$", re.IGNORECASE
)


def _compile_graveyard_exile(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    replacement_match = _GRAVEYARD_EXILE_REPLACEMENT_RE.fullmatch(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    counter = replacement_match.group("counter")
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

    if counter is None:
        return _graveyard_replacer(effect.text, whose)
    kind = counter.lower()

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return _to_graveyard(event) and event.card is not None and whose(game, source, event.card)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        # CR 614.1a + CR 122.1: exiled instead, arriving with the counter
        # (`resolving_exile.after_resolving_exile` places it once in exile).
        _exile_instead(game, source, event)
        event.exile_counters[kind] = event.exile_counters.get(kind, 0) + 1

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- "if a creature [an opponent controls] would die, exile it instead" --
#
# CR 700.4: "dies" means "is put into a graveyard from the battlefield" - a
# narrower event than `_GRAVEYARD_EVENT_RE`'s "would be put into a graveyard
# [from anywhere]", so this is its own shape rather than a third alternative
# folded into that regex: a card milled from a library, or discarded, would
# wrongly match "would die" if the origin were not checked.
_DIES_EVENT_RE = re.compile(
    r"^a creature (?P<whose>an opponent controls|you control) would die$", re.IGNORECASE
)
_SELF_DIES_EVENT_RE = re.compile(r"^this creature would die$", re.IGNORECASE)


def _compile_dies_exile(effect: ReplacementEffect) -> CardReplacement | None:
    """Garruk, Veiled Butcher's "If a creature an opponent controls would
    die, exile it instead."; Gisa, Glorious Resurrector's and Corpseweaver
    Prodigy's identical real printing; Gloomshrieker's self-only "If this
    creature would die, exile it instead."

    The "whose" question here is who *controls* the dying creature
    (CR 108.4), not whose graveyard it would land in - CR 400.3 does not
    require the two to be the same player, so this reads `CardState.
    controller` directly rather than routing through `_graveyard_replacer`'s
    owner-of-the-graveyard matchers.
    """
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "exile it":
        return None
    event_text = (effect.event or "").strip()
    if match := _DIES_EVENT_RE.match(event_text):
        wants_opponent = match.group("whose") == "an opponent controls"

        def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            if not _to_graveyard(event) or event.origin is not Zone.BATTLEFIELD:
                return False
            if event.card is None or event.card.controller is None:
                return False
            is_opponent = _is_opponent(game, event.card.controller, source.controller)
            return is_opponent if wants_opponent else not is_opponent

        if effect.linked_trigger is not None:
            reflexive = _exile_instead_then_reflexive(effect.linked_trigger)
            if reflexive is None:
                # A "When you do, ..." this module cannot read: refuse the
                # whole line rather than exile and silently drop the rest.
                return None
            return CardReplacement(label=effect.text, applies=applies, apply=reflexive)
        return CardReplacement(label=effect.text, applies=applies, apply=_exile_instead)
    if _SELF_DIES_EVENT_RE.match(event_text):

        def self_applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
            return (
                _to_graveyard(event)
                and event.origin is Zone.BATTLEFIELD
                and event.card is not None
                and event.card.id == source.id
            )

        return CardReplacement(label=effect.text, applies=self_applies, apply=_exile_instead)
    return None


def _exile_instead_then_reflexive(linked: str) -> Apply | None:
    """ "... exile it instead. When you do, `<consequence>`." (Head of the
    Hunt's Wolf, Nemata, Primeval Warden's Saproling) - CR 603.12's reflexive
    triggered ability, created only when this replacement was actually
    applied to an event (CR 614.5 gives it one opportunity, so two such
    permanents exiling one creature create one trigger, from whichever
    applied). It goes on the stack the next time a player would receive
    priority (CR 603.3), controlled by the replacement's own controller.

    `None` when the consequence is not something `machines/effects.py`'s
    reflexive reader performs - the caller refuses the line (fail closed).
    """
    from ..delayed import ReflexiveConsequence
    from ..effects import reflexive_consequence_effect

    match = _REFLEXIVE_OPENER.match(linked.strip())
    if match is None or match.group(0).lower().startswith("when you don"):
        return None
    consequence = match.group("effect").strip()
    if reflexive_consequence_effect(consequence) is None:
        return None

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        _exile_instead(game, source, event)
        if source is None or source.controller is None:
            return
        game.create_reflexive_trigger(
            text=consequence,
            controller=source.controller,
            source_id=source.id,
            source_name=source.name,
            callback=ReflexiveConsequence(),
        )

    return apply


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


#: "If a [`<quality>`] source you control would deal [noncombat] damage to
#: `<recipients>`, it deals that much damage plus N / double that damage [to
#: that player or permanent] instead." - Artist's Talent's level 3 (CR
#: 716.2a), Tomik, Izzet Sparkmage's "plus 1", Solphim, Mayhem Dominus's
#: "double that damage to that player or permanent", Torbran's "red source".
#: CR 614.2: a replacement effect that applies to damage from a source; CR
#: 609.7b: the source's properties are checked as the damage would be dealt;
#: CR 701.10g: doubling damage is the source dealing twice that much.
#: The subject is "source" or, narrower, "creature" (Gratuitous Violence's
#: "If a creature you control would deal damage to a permanent or player");
#: the recipient is optional (Insult's "If a source you control would deal
#: damage this turn" - any recipient). "you control" is optional too (Rankle
#: and Torbran's "If a source would deal damage to a player or battle this
#: turn"): without it the source's controller is not asked at all (CR 614.1a
#: applies the replacement to any source), which `yours` records.
_SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE = re.compile(
    r"^an? (?:(?P<quality>[a-z]+) )?(?P<subject>source|creature)(?P<yours> you control)? "
    r"would deal (?P<noncombat>noncombat )?damage(?: to (?P<recipient>.+))?$",
    re.IGNORECASE,
)
_SOURCE_DAMAGE_MODIFIER_RE = re.compile(
    rf"^it deals (?:that much damage plus (?P<plus>{COUNT})"
    r"|(?P<mult>double|triple) that damage)"
    r"(?: to that (?:player or permanent|permanent or player))?$",
    re.IGNORECASE,
)
_DAMAGE_WORD_FACTORS = {"double": 2, "triple": 3}

#: The recipient phrases the template prints, each a test on the damage event
#: for the effect's controller. An unlisted phrase compiles to nothing.
_DamageRecipient = Callable[["Game", str, ReplaceableEvent], bool]


def _recipient_is_opponent(game: "Game", controller: str, event: ReplaceableEvent) -> bool:
    return event.player is not None and _is_opponent(game, controller, event.player.username)


def _recipient_is_opponents_permanent(
    game: "Game", controller: str, event: ReplaceableEvent
) -> bool:
    return event.card is not None and _is_opponent(
        game, controller, game.controller_of(event.card).username
    )


def _recipient_is_creature_battle_or_opponent(
    game: "Game", controller: str, event: ReplaceableEvent
) -> bool:
    """ "a creature, battle, or opponent" (Disciples of the Inferno) - CR
    115.4's own "any target" set for damage minus "player" (narrowed here to
    "opponent", the card's own wording) and "planeswalker": the two card
    types this phrase actually names (CR 205.2a), read off the computed board
    (CR 613.5) since the recipient may be a permanent animated into one of
    them."""
    if event.player is not None:
        return _recipient_is_opponent(game, controller, event)
    if event.card is None:
        return False
    types = game.characteristics_of(event.card).types
    return Type.CREATURE in types or Type.BATTLE in types


_DAMAGE_RECIPIENTS: dict[str, _DamageRecipient] = {
    "an opponent or a permanent an opponent controls": lambda game, you, event: (
        _recipient_is_opponent(game, you, event)
        or _recipient_is_opponents_permanent(game, you, event)
    ),
    "an opponent": _recipient_is_opponent,
    "a permanent an opponent controls": _recipient_is_opponents_permanent,
    "a permanent or player": lambda game, you, event: True,
    "a player or permanent": lambda game, you, event: True,
    "a creature an opponent controls": lambda game, you, event: (
        event.card is not None
        and Type.CREATURE in game.characteristics_of(event.card).types
        and _recipient_is_opponents_permanent(game, you, event)
    ),
    "a creature, battle, or opponent": _recipient_is_creature_battle_or_opponent,
}


#: One noun of a printed recipient list ("a player or battle", "a permanent
#: or player"), as a test on the damage event: a player recipient (CR 120.3a)
#: or a permanent of a card type read off the computed board (CR 613.5;
#: CR 310.6 for a battle).
def _recipient_is_type(card_type: Type) -> _DamageRecipient:
    def test(game: "Game", you: str, event: ReplaceableEvent) -> bool:
        return event.card is not None and card_type in game.characteristics_of(event.card).types

    return test


_RECIPIENT_NOUNS: dict[str, _DamageRecipient] = {
    "player": lambda game, you, event: event.player is not None,
    "opponent": _recipient_is_opponent,
    "permanent": lambda game, you, event: event.card is not None,
    "creature": _recipient_is_type(Type.CREATURE),
    "planeswalker": _recipient_is_type(Type.PLANESWALKER),
    "battle": _recipient_is_type(Type.BATTLE),
}
_RECIPIENT_LIST_SPLIT_RE = re.compile(r"\s*,\s*(?:or\s+)?|\s+or\s+", re.IGNORECASE)


def damage_recipient(phrase: str) -> _DamageRecipient | None:
    """The test a printed recipient phrase puts on a damage event: one of the
    `_DAMAGE_RECIPIENTS` phrases, or a list of `_RECIPIENT_NOUNS` after one
    article ("a player or battle", "a permanent or player", "a creature,
    planeswalker, or battle"), any one of which matches. None for any other
    wording, so an unlisted recipient compiles to nothing."""
    lowered = " ".join(phrase.strip().lower().split())
    listed = _DAMAGE_RECIPIENTS.get(lowered)
    if listed is not None:
        return listed
    article = re.match(r"^an? ", lowered)
    if article is None:
        return None
    nouns = _RECIPIENT_LIST_SPLIT_RE.split(lowered[article.end() :])
    tests = [test for noun in nouns if (test := _RECIPIENT_NOUNS.get(noun)) is not None]
    if len(tests) < 2 or len(tests) != len(nouns):
        return None

    def any_listed(game: "Game", you: str, event: ReplaceableEvent) -> bool:
        return any(test(game, you, event) for test in tests)

    return any_listed


#: "put that many <kind> counters on that creature" - the damage replaced by
#: counters (CR 614.1a, CR 122.1). Soul-Scar Mage's -1/-1 is the printed kind;
#: any counter name reads the same way.
_DAMAGE_AS_COUNTERS_RE = re.compile(
    r"^put that many (?P<kind>[+-]\d+/[+-]\d+|[a-z]+) counters on that "
    r"(?:creature|permanent)$",
    re.IGNORECASE,
)


def _compile_damage_as_counters(effect: ReplacementEffect) -> CardReplacement | None:
    """ "If a source you control would deal [noncombat] damage to <recipient>,
    put that many <kind> counters on that creature instead." (Soul-Scar Mage).

    CR 614.1a: the damage is replaced, not prevented - it is never dealt, so
    nothing marks it and nothing that watches damage dealt sees it; the
    counters are put on by the effect's controller (CR 122.6a) through
    `Game.add_counters`, so a counter replacement still gets its look.
    """
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE.fullmatch((effect.event or "").strip())
    if event_match is None or event_match.group("quality") is not None:
        return None
    if event_match.group("yours") is None or event_match.group("recipient") is None:
        return None
    recipient = damage_recipient(event_match.group("recipient"))
    if recipient is None:
        return None
    replacement_match = _DAMAGE_AS_COUNTERS_RE.fullmatch(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    noncombat = event_match.group("noncombat") is not None
    kind = replacement_match.group("kind").lower()

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DAMAGE or event.source is None or event.card is None:
            return False
        if event.amount <= 0 or (noncombat and event.combat):
            return False
        controller = game.controller_of(source).username
        if game.controller_of(event.source).username != controller:
            return False
        return recipient(game, controller, event)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        amount = event.amount
        event.amount = 0
        if event.card is not None and amount > 0:
            game.add_counters(event.card, kind, amount, putter=game.controller_of(source).username)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def read_damage_modifier(event_text: str, replacement: str) -> DamageModifierReplacement | None:
    """`_SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE` + `_SOURCE_DAMAGE_MODIFIER_RE`, as
    the data both a permanent's static and a resolving spell's turn-long
    effect apply (`damage_modification.DamageModifierReplacement`)."""
    event_match = _SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE.fullmatch(event_text.strip())
    if event_match is None:
        return None
    recipient = event_match.group("recipient")
    if recipient is not None:
        recipient = " ".join(recipient.strip().lower().split())
        if damage_recipient(recipient) is None:
            return None
    match = _SOURCE_DAMAGE_MODIFIER_RE.fullmatch(replacement.strip().rstrip("."))
    if match is None:
        return None
    if match.group("plus") is not None:
        addend = parse_count(match.group("plus"))
        if addend is None:
            return None
        factor = 1
    else:
        addend = 0
        factor = _DAMAGE_WORD_FACTORS[match.group("mult").lower()]
    quality = event_match.group("quality")
    return DamageModifierReplacement(
        subject=event_match.group("subject").lower(),
        quality=quality.lower() if quality is not None else None,
        noncombat=event_match.group("noncombat") is not None,
        recipient=recipient,
        factor=factor,
        addend=addend,
        any_controller=event_match.group("yours") is None,
    )


def _compile_damage_plus_amount(effect: ReplacementEffect) -> CardReplacement | None:
    """A permanent's static `read_damage_modifier` shape: "you" is the
    permanent's controller as the damage would be dealt (CR 609.7b).

    A leading "As long as `<condition>`," (Anthem of Rakdos's hellbent "you
    have no cards in hand", Aether Revolt's revolt) is CR 604.2's bound on
    the effect's existence: asked of `Game.condition_holds` each time damage
    would be dealt (CR 611.3a), never once as the permanent entered. A
    condition no reader claims is not compiled at all - fail closed rather
    than double unconditionally."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    condition = effect.condition
    if condition is not None and not condition_claims(condition):
        return None
    spec = read_damage_modifier(effect.event or "", effect.replacement or "")
    if spec is None:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        controller = game.controller_of(source).username
        if condition is not None and not game.condition_holds(controller, condition, source):
            return False
        return spec.applies(game, controller, event)

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        spec.apply(game, game.controller_of(source).username, event)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- "Double all damage <subject> would deal." --------------------------------

#: Mjolnir, Hammer of Thor's "Double all damage equipped creature would deal."
#: and Collective Inferno's "Double all damage that sources you control of the
#: chosen type would deal." - a static ability with no "instead" (so the
#: sentence parser above never claims it), read line by line here. CR
#: 701.10g: "To double an amount of damage a source would deal, that source
#: instead deals twice that much damage. This is a replacement effect."
_DOUBLE_ALL_DAMAGE_RE = re.compile(
    r"^(?P<mult>double|triple) all damage (?:that )?(?P<subject>.+?) would deal\.?$",
    re.IGNORECASE,
)


def _source_subtypes(game: "Game", source: CardState) -> set[str]:
    if source.zone is Zone.BATTLEFIELD:
        return {subtype.lower() for subtype in game.characteristics_of(source).subtypes}
    return {subtype.lower() for subtype in source.subtypes}


def _double_all_damage_subject(
    subject: str,
) -> Callable[["Game", CardState, CardState], bool] | None:
    """Whether a damage source is the printed subject, for the permanent
    carrying the effect - `None` for a subject this does not read."""
    words = subject.strip().lower()
    if words in ("equipped creature", "enchanted creature"):
        # CR 301.5a / CR 303.4b: the creature this permanent is attached to.
        return lambda game, holder, source: (
            holder.attached_to is not None and holder.attached_to == source.id
        )
    you_control = re.fullmatch(
        r"(?P<what>sources|creatures) you control(?P<chosen> of the chosen type)?", words
    )
    if you_control is None:
        return None
    creatures_only = you_control.group("what") == "creatures"
    chosen_type = you_control.group("chosen") is not None

    def matches(game: "Game", holder: CardState, source: CardState) -> bool:
        if game.controller_of(source).username != game.controller_of(holder).username:
            return False
        if creatures_only:
            chars = game.characteristics_of(source) if source.zone is Zone.BATTLEFIELD else source
            if Type.CREATURE not in chars.types:
                return False
        if chosen_type:
            choice = holder.choice
            if choice is None or choice.kind is not ChoiceKind.CREATURE_TYPE:
                return False
            return choice.value.lower() in _source_subtypes(game, source)
        return True

    return matches


def _double_all_damage_replacements(lines: Iterable[str]) -> list[CardReplacement]:
    """Every "Double all damage `<subject>` would deal." line among `lines`."""
    found: list[CardReplacement] = []
    for line in lines:
        match = _DOUBLE_ALL_DAMAGE_RE.fullmatch(line.strip())
        if match is None:
            continue
        subject = _double_all_damage_subject(match.group("subject"))
        if subject is None:
            continue
        factor = _DAMAGE_WORD_FACTORS[match.group("mult").lower()]

        def applies(
            game: "Game",
            source: CardState,
            event: ReplaceableEvent,
            subject=subject,
        ) -> bool:
            return (
                event.kind is EventKind.DAMAGE
                and event.source is not None
                and subject(game, source, event.source)
            )

        def apply(
            game: "Game", source: CardState | None, event: ReplaceableEvent, factor=factor
        ) -> None:
            event.amount *= factor

        found.append(CardReplacement(label=line.strip(), applies=applies, apply=apply))
    return found


def double_all_damage_line(line: str) -> bool:
    """Whether `line` is a "Double all damage ... would deal." static this
    module performs - `support.py`'s credit for it."""
    match = _DOUBLE_ALL_DAMAGE_RE.fullmatch(line.strip())
    return match is not None and _double_all_damage_subject(match.group("subject")) is not None


# -- "damage that would reduce your life total to less than N reduces it to
#    N instead." (Elderscale Wurm's static, Angel of Grace's until-end-of-turn
#    created form) - CR 119.2/119.3's own damage-as-life-loss, floored -------
#
# Read directly off the raw sentence like `_double_all_damage_replacements`
# above, rather than through the generic `IF_WOULD_INSTEAD` parser: this
# sentence has no leading "If", so `_try_if_would` never claims it (it comes
# back `UNPARSED`), the same reason `_double_all_damage_replacements` is its
# own bespoke reader instead of a `_COMPILERS` row.

#: "damage that would reduce your life total to less than N reduces it to N
#: instead" - both numbers read, not assumed equal, though every printing in
#: the pool repeats the same one.
_DAMAGE_LIFE_FLOOR_RE = re.compile(
    r"^damage that would reduce your life total to less than (?P<less_than>\d+) "
    r"reduces it to (?P<floor>\d+) instead$",
    re.IGNORECASE,
)
#: Elderscale Wurm's own leading condition: "As long as you have N or more
#: life, `<floor clause>`." Read generally - the threshold number, not
#: assumed equal to the floor it happens to match on this printing.
_AS_LONG_AS_LIFE_THRESHOLD_PREFIX_RE = re.compile(
    r"^as long as you have (?P<threshold>\d+) or more life, (?P<rest>.+)$", re.IGNORECASE
)


def _read_damage_life_floor(sentence: str) -> int | None:
    """`_DAMAGE_LIFE_FLOOR_RE`'s floor, or `None` when the two numbers
    printed don't agree with each other (an engine defect to fail closed on,
    not a floor to guess between)."""
    match = _DAMAGE_LIFE_FLOOR_RE.fullmatch(sentence.strip().rstrip("."))
    if match is None:
        return None
    less_than = parse_count(match.group("less_than"))
    floor = parse_count(match.group("floor"))
    if less_than is None or floor is None or less_than != floor:
        return None
    return floor


def _damage_life_floor_replacements(lines: Iterable[str]) -> list[CardReplacement]:
    """Every static "damage that would reduce your life total ..." line among
    `lines`, Elderscale Wurm's own leading "as long as" condition included."""
    found: list[CardReplacement] = []
    for line in lines:
        stripped = line.strip()
        threshold: int | None = None
        rest = stripped
        as_long = _AS_LONG_AS_LIFE_THRESHOLD_PREFIX_RE.fullmatch(stripped.rstrip("."))
        if as_long is not None:
            threshold = parse_count(as_long.group("threshold"))
            rest = as_long.group("rest")
            if threshold is None:
                continue
        floor = _read_damage_life_floor(rest)
        if floor is None:
            continue

        def applies(
            game: "Game",
            source: CardState,
            event: ReplaceableEvent,
            floor: int = floor,
            threshold: int | None = threshold,
        ) -> bool:
            if event.kind is not EventKind.DAMAGE or event.player is None or event.amount <= 0:
                return False
            if event.player.username != source.controller:
                return False
            if threshold is not None and event.player.life < threshold:
                return False
            return event.player.life - event.amount < floor

        def apply(
            game: "Game", source: CardState | None, event: ReplaceableEvent, floor: int = floor
        ) -> None:
            if event.player is None:
                return
            event.amount = max(event.player.life - floor, 0)

        found.append(CardReplacement(label=stripped, applies=applies, apply=apply))
    return found


def damage_life_floor_line(line: str) -> bool:
    """Whether `line` is a "damage that would reduce your life total ..."
    static (Elderscale Wurm's own leading "as long as" included)
    `_damage_life_floor_replacements` performs - `support.py`'s credit."""
    stripped = line.strip()
    as_long = _AS_LONG_AS_LIFE_THRESHOLD_PREFIX_RE.fullmatch(stripped.rstrip("."))
    rest = as_long.group("rest") if as_long is not None else stripped
    if as_long is not None and parse_count(as_long.group("threshold")) is None:
        return False
    return _read_damage_life_floor(rest) is not None


def read_damage_life_floor(sentence: str) -> "DamageLifeFloorReplacement | None":
    """`created_replacement_spec`'s own reader for the shape above, shared
    with the static form's `_read_damage_life_floor`."""
    floor = _read_damage_life_floor(sentence)
    return None if floor is None else DamageLifeFloorReplacement(floor=floor)


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

    return CardReplacement(label=effect.text, applies=applies, apply=apply, prevention=True)


# -- "If [noncombat |combat ]damage would be dealt to you, prevent that damage[.
#    You gain life equal to the damage prevented this way.]" --

#: The event half: damage aimed at the effect's own controller, optionally
#: narrowed to combat (CR 120.2a) or noncombat (CR 120.2b) damage.
_DAMAGE_TO_YOU_EVENT_RE = re.compile(
    r"^(?:(?P<combat>(?P<non>non)?combat) )?damage would be dealt to you$", re.IGNORECASE
)
#: CR 615.5's optional additional effect, the sentence after the prevention on
#: the same printed line (Purity). Any other trailing sentence - Immortal
#: Coil's "Exile a card from your graveyard for each 1 damage prevented this
#: way." - is an unread rider, so the line fails closed rather than being
#: performed with its rider silently dropped.
_GAIN_LIFE_EQUAL_TO_PREVENTED_RE = re.compile(
    r"^you gain life equal to the damage prevented this way\.?$", re.IGNORECASE
)


def _compile_prevent_damage_to_you(effect: ReplacementEffect) -> CardReplacement | None:
    """A permanent's static "If [non]combat damage would be dealt to you,
    prevent that damage." with, optionally, CR 615.5's "You gain life equal
    to the damage prevented this way." (CR 615.1a, CR 604.2).

    Under damage that can't be prevented (CR 615.12) `applicable_effects`
    wraps this in `_prevents_nothing`; the rider then gains nothing, because
    nothing was prevented this way.
    """
    if effect.kind is not ReplacementKind.PREVENT_IF_WOULD:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "prevent that damage":
        return None
    event_match = _DAMAGE_TO_YOU_EVENT_RE.fullmatch((effect.event or "").strip())
    if event_match is None:
        return None
    raw = effect.raw.strip()
    text = effect.text.strip()
    if not raw.startswith(text):
        return None
    rider = raw[len(text) :].strip()
    gains_life = bool(rider)
    if gains_life and _GAIN_LIFE_EQUAL_TO_PREVENTED_RE.fullmatch(rider) is None:
        return None
    combat_word = (event_match.group("combat") or "").lower()

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DAMAGE or event.amount <= 0 or event.player is None:
            return False
        if combat_word == "noncombat" and event.combat:
            return False
        if combat_word == "combat" and not event.combat:
            return False
        return event.player.username == game.controller_of(source).username

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        prevented = 0 if game.damage_cant_be_prevented(event) is not None else event.amount
        event.amount = 0
        if gains_life and prevented > 0 and source is not None:
            game.gain_life(game.controller_of(source).username, prevented)

    return CardReplacement(label=raw, applies=applies, apply=apply, prevention=True)


# -- "prevent all combat damage that would be dealt to and dealt by this creature" --

_SELF_PREVENT_COMBAT_RE = re.compile(
    r"^prevent all combat damage that would be dealt to and dealt by this creature$", re.IGNORECASE
)


def _compile_self_prevent_combat_damage(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.PREVENT_ALL:
        return None
    if not _SELF_PREVENT_COMBAT_RE.match(effect.text.strip().rstrip(".")):
        return None
    return CardReplacement(
        label=effect.text, applies=_fog_bank_applies, apply=_prevent_all, prevention=True
    )


# -- "Prevent all [non]combat damage that would be dealt to <group>" ----------

#: Crystal Barricade's and Tajic, Legion's Edge's "Prevent all noncombat
#: damage that would be dealt to other creatures you control.", Mark of
#: Asylum's "... to creatures you control.", The Wanderer's "... to you and
#: other permanents you control.", Magebane Armor's "... to equipped
#: creature." CR 615.1a: a prevention effect; CR 510.2 marks combat damage.
_PREVENT_ALL_TO_GROUP_RE = re.compile(
    r"^Prevent all (?P<combat>(?P<non>non)?combat )?damage that would be dealt to "
    r"(?P<group>.+?)\.?$",
    re.IGNORECASE,
)

_PreventionRecipient = Callable[["Game", CardState, ReplaceableEvent], bool]


def _creature_on_battlefield(game: "Game", card: CardState) -> bool:
    return card.zone is Zone.BATTLEFIELD and game.characteristics_of(card).is_creature


def _prevention_recipient(group: str) -> _PreventionRecipient | None:
    words = group.strip().lower()
    if words in ("this creature", "this permanent") or re.fullmatch(
        r"[A-Z][\w'-]*(?:[ ,-]+[A-Z][\w'-]*)*", group.strip()
    ):
        # "Prevent all damage that would be dealt to Black Panther." / "... to
        # Cho-Manno." - the permanent naming itself (CR 201.5), checked
        # against the holder's own current face name as the damage arrives.
        printed = group.strip()

        def itself(game: "Game", holder: CardState, event: ReplaceableEvent) -> bool:
            if event.card is None or event.card.id != holder.id:
                return False
            return words in ("this creature", "this permanent") or printed in (
                self_reference_names(holder.name)
            )

        return itself
    if words in ("equipped creature", "enchanted creature"):
        return lambda game, holder, event: (
            event.card is not None
            and holder.attached_to is not None
            and holder.attached_to == event.card.id
        )
    match = re.fullmatch(
        r"(?P<you>you and )?(?P<other>other )?(?P<what>creatures|permanents) you control", words
    )
    if match is None:
        return None
    you_too = match.group("you") is not None
    other = match.group("other") is not None
    creatures_only = match.group("what") == "creatures"

    def recipient(game: "Game", holder: CardState, event: ReplaceableEvent) -> bool:
        controller = game.controller_of(holder).username
        if event.player is not None:
            return you_too and event.player.username == controller
        card = event.card
        if card is None or game.controller_of(card).username != controller:
            return False
        if other and card.id == holder.id:
            return False
        return not creatures_only or _creature_on_battlefield(game, card)

    return recipient


def _compile_prevent_all_to_group(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.PREVENT_ALL:
        return None
    match = _PREVENT_ALL_TO_GROUP_RE.fullmatch(effect.text.strip())
    if match is None:
        return None
    recipient = _prevention_recipient(match.group("group"))
    if recipient is None:
        return None
    combat_word = (match.group("combat") or "").strip().lower()

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DAMAGE or event.amount <= 0:
            return False
        if combat_word == "noncombat" and event.combat:
            return False
        if combat_word == "combat" and not event.combat:
            return False
        return recipient(game, source, event)

    return CardReplacement(label=effect.text, applies=applies, apply=_prevent_all, prevention=True)


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
    (or whoever a control-changing replacement already moved them to,
    `ReplaceableEvent.creating_controller`) and not against whoever the effect
    belongs to - Kozilek's Command makes the
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
        if event.creating_controller is None or event.creating_controller != source.controller:
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


#: Draconic Visitor's "...that many 5/5 red Dragon creature tokens with
#: flying are created instead" - unlike `_EXTRA_TOKEN_REPLACEMENT_RE`'s
#: "those tokens **plus** ...", there is no "those tokens" here at all: the
#: whole batch becomes a different kind, not an addition alongside it.
_TOKEN_SUBSTITUTION_RE = re.compile(r"^that many (?P<descriptor>.+?) are created$", re.IGNORECASE)


def _substitute_tokens(new_definition: TokenDefinition) -> Apply:
    """ "...that many <descriptor> are created instead" - the same count
    (CR 614.6's modified event), a different `TokenDefinition` entirely.
    `event.card` is cleared too: it is the token-*copy* alternative to
    `definition` (CR 707.2), and this effect always states real
    characteristics of its own, never "copy the original".
    """

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        event.definition = new_definition
        event.card = None

    return apply


def _compile_token_substitution(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    wanted = _token_creation_filter(effect)
    if wanted is None:
        return None
    match = _TOKEN_SUBSTITUTION_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    new_definition = _read_token_descriptor(match.group("descriptor"))
    if new_definition is None:
        return None
    return CardReplacement(
        label=effect.text,
        applies=_extra_token_applies(wanted),
        apply=_substitute_tokens(new_definition),
    )


# -- "the first time you would create one or more tokens each turn, you may
#    instead create that many tokens that are copies of <attached object>" --
#
# Mirrormind Crown and Moonlit Meditation. CR 614.1a's replacement, applied
# to the first `CREATE_TOKENS` event of the turn for its controller only:
# `TOKEN_CREATION_FACT` counts every such event per player per turn
# (`models/token.py` notes one after the event's replacements are done), so
# "the first time" is the event with a count of zero - declined, or with the
# Equipment unattached at the time, it is gone for the turn all the same.

_FIRST_TIME_TOKEN_EVENT_RE = re.compile(r"^you would create one or more tokens$", re.IGNORECASE)
_TOKEN_COPIES_OF_ATTACHED_RE = re.compile(
    r"^(?:you may )?create that many tokens that are copies of "
    r"(?P<object>equipped creature|enchanted creature|enchanted permanent|enchanted artifact)$",
    re.IGNORECASE,
)
#: The one "as long as" gate this shape prints: the source is attached to a
#: creature (CR 301.5, CR 303.4) - which "copies of equipped creature" needs
#: anyway, so it is read here rather than left to a general condition reader.
_ATTACHED_TO_A_CREATURE_CONDITION_RE = re.compile(
    r"^this (?:equipment|aura|artifact|enchantment|permanent) is attached to a creature$",
    re.IGNORECASE,
)


def _compile_first_time_token_copies(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or not effect.first_time_each_turn:
        return None
    if _FIRST_TIME_TOKEN_EVENT_RE.match((effect.event or "").strip()) is None:
        return None
    match = _TOKEN_COPIES_OF_ATTACHED_RE.match((effect.replacement or "").strip().rstrip("."))
    if match is None:
        return None
    if effect.condition is not None and not _ATTACHED_TO_A_CREATURE_CONDITION_RE.match(
        effect.condition.strip()
    ):
        return None
    wanted = match.group("object").lower().split()[-1]
    optional = effect.optional

    def attached_host(game: "Game", source: CardState) -> CardState | None:
        if source.attached_to is None:
            return None
        host = game.find_by_id(source.attached_to)
        if not isinstance(host, CardState) or host.zone is not Zone.BATTLEFIELD:
            return None
        types = game.characteristics_of(host).types
        if (wanted == "creature" or effect.condition is not None) and Type.CREATURE not in types:
            return None
        if wanted == "artifact" and Type.ARTIFACT not in types:
            return None
        return host

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        from ...models.token import TOKEN_CREATION_FACT

        if event.kind is not EventKind.CREATE_TOKENS or event.amount <= 0:
            return False
        # "You would create": the player creating them (CR 111.2), who is the
        # source's controller.
        if event.player is None or event.player.username != source.controller:
            return False
        if game.turn_count(TOKEN_CREATION_FACT, event.player.username) > 0:
            return False
        return attached_host(game, source) is not None

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        if source is None:
            return
        host = attached_host(game, source)
        if host is None or source.controller is None:
            return
        if optional and not game.may(
            source.controller,
            f"create {event.amount} token(s) that are copies of {host.name} instead",
            source=source.name,
            source_id=source_id_of(source),
        ):
            return
        event.copy_of = host
        event.definition = None
        event.history.append(f"{source.name}: the tokens are copies of {host.name}")

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


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

#: A counter kind word, as either shape oracle text prints one: a bare word
#: ("+1/+1", "charge", "loyalty") or a mana-symbol kind written the way
#: energy always is ("{E}").
_COUNTER_KIND_WORD = r"(?:\{[^}]+\}|[+/\w-]+)"

_COUNTER_AMOUNT_EVENT_RE = re.compile(
    r"^(?:an effect would put one or more counters on (?P<effect_subject>.+?)"
    rf"|one or more (?:(?P<kind>{_COUNTER_KIND_WORD}) )?counters would be put on (?P<subject>.+?)"
    rf"|you would put one or more (?:(?P<put_kind>{_COUNTER_KIND_WORD}) )?counters on"
    r" (?P<put_subject>.+?)"
    rf"|(?P<player_event>you would get one or more"
    rf" (?:counters?|(?P<player_kind>{_COUNTER_KIND_WORD}))))$",
    re.IGNORECASE,
)
_COUNTER_AMOUNT_REPLACEMENT_RE = re.compile(
    rf"^(?:it puts (?P<it_mult>{MULTIPLIER}) that many of those counters on that permanent"
    rf"|(?:(?P<mult>{MULTIPLIER}) that many|that many(?: plus (?P<plus>{COUNT}))?)"
    r"(?: of each of those kinds of counters"
    rf"| (?P<kind>{_COUNTER_KIND_WORD}) counters(?: (?P<op>plus|minus) (?P<n>{COUNT}))?)"
    r" are put on (?:it|that creature|that permanent)"
    rf"|put that many(?: plus (?P<put_plus>{COUNT}))?"
    r" (?:(?P<put_each>of each of those kinds of counters)"
    rf"|(?P<put_rkind>{_COUNTER_KIND_WORD}) counters)"
    r" on (?:it|that creature|that permanent)"
    rf"|you get (?:(?P<pmult>{MULTIPLIER}) that many|that many(?: plus (?P<pplus>{COUNT}))?)"
    r"(?: of each of those kinds of counters"
    rf"| (?P<pkind>{_COUNTER_KIND_WORD})(?: counters?)?"
    rf"(?: (?P<pop>plus|minus) (?P<pn>{COUNT}))?)?)$",
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
    """`_counter_amount_values` as an `Apply`."""
    values = _counter_amount_values(match)
    if values is None:
        return None
    multiplier, addend = values
    return _scale_amount(multiplier=multiplier, addend=addend)


def _counter_amount_values(match: re.Match[str]) -> tuple[int, int] | None:
    """The (multiplier, addend) a counter replacement prints, or None.

    `p`-prefixed groups are `_COUNTER_AMOUNT_REPLACEMENT_RE`'s player-counter
    branch ("you get twice that many ..."); the rest are its card-counter
    branch ("... are put on it") - exactly one set is ever populated for a
    given match, so reading both costs nothing.
    """
    multiplier_text = match.group("it_mult") or match.group("mult") or match.group("pmult")
    if multiplier_text is not None:
        multiplier = parse_multiplier(multiplier_text)
        return None if multiplier is None else (multiplier, 0)
    addend_text = (
        match.group("plus")
        or match.group("n")
        or match.group("pplus")
        or match.group("pn")
        or match.group("put_plus")
    )
    if addend_text is None:
        return None  # a bare "that many" replaces nothing
    addend = parse_count(addend_text)
    if addend is None:
        return None
    op = match.group("op") or match.group("pop")
    return (1, -addend if op == "minus" else addend)


def _normalized_counter_kind(raw: str | None) -> str | None:
    """A matched kind group, lower-cased, or `None` for "no kind at all" -
    which is both an empty match and the bare word "counters"/"counter"
    itself (`_COUNTER_KIND_WORD` matches that word too, since it is not
    distinguishable from a kind name by shape alone; "you get twice that many
    counters instead" names no kind, the same as "... of each of those kinds
    of counters").

    CR 107.14: "The energy symbol is {E}. It represents one energy counter" -
    `{e}` is normalised to `"energy"`, `Counter.ENERGY`'s own value and what
    `Game.add_player_counters` actually stamps `ReplaceableEvent.counter_kind`
    with, so Aether Refinery's own "one or more {E} (energy counters)" reads
    the same kind a caller passing `Counter.ENERGY` produces.
    """
    lowered = (raw or "").strip().lower()
    if lowered == "{e}":
        return "energy"
    return None if lowered in ("", "counter", "counters") else lowered


#: Vorinclex, Monstrous Raider's and Innkeeper's Talent's "If you would put
#: one or more counters on a permanent or player, ..." and Vorinclex's "If an
#: opponent would put ...": the putter (CR 122.6a) is who the line watches,
#: and "a permanent or player" reaches both halves of CR 122.6 - any
#: permanent, whoever controls it, and any player.
_PUTTER_COUNTER_EVENT_RE = re.compile(
    r"^(?P<who>you|an opponent) would put one or more counters on"
    r" a permanent(?P<or_player> or player)?$",
    re.IGNORECASE,
)
#: "put twice that many ..." / "they put half that many ..., rounded down" -
#: a multiplier, or a halving whose rounding CR 107.1a requires be printed.
_PUTTER_COUNTER_REPLACEMENT_RE = re.compile(
    rf"^(?:they )?put (?:(?P<mult>{MULTIPLIER}) that many|half that many)"
    r" of each of those kinds of counters on that permanent(?P<or_player> or player)?"
    r"(?: ?, rounded (?P<rounding>down|up))?$",
    re.IGNORECASE,
)


def read_putter_counter_amount(effect: ReplacementEffect) -> "CounterAmountReplacement | None":
    """`_PUTTER_COUNTER_EVENT_RE`/`_PUTTER_COUNTER_REPLACEMENT_RE`'s reader.

    "you" is the source's controller (CR 109.5); "an opponent" is any other
    player putting counters. Halving needs its
    rounding printed (CR 107.1a: "If a spell or ability could generate a
    fractional number, the spell or ability will tell you whether to round
    up or down"), so an unrounded "half" is left uncompiled.
    """
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _PUTTER_COUNTER_EVENT_RE.match((effect.event or "").strip())
    if event_match is None:
        return None
    replacement_match = _PUTTER_COUNTER_REPLACEMENT_RE.match(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    if (event_match.group("or_player") is None) != (replacement_match.group("or_player") is None):
        return None
    opponent_puts = event_match.group("who").lower() == "an opponent"
    multiplier_text = replacement_match.group("mult")
    rounding = replacement_match.group("rounding")
    if multiplier_text is not None:
        multiplier = parse_multiplier(multiplier_text)
        if multiplier is None or rounding is not None:
            return None
        divisor = 1
    else:
        if rounding is None:
            return None
        multiplier, divisor = 1, 2
    return CounterAmountReplacement(
        you_put=not opponent_puts,
        opponent_puts=opponent_puts,
        players=event_match.group("or_player") is not None,
        multiplier=multiplier,
        divisor=divisor,
        round_up=rounding is not None and rounding.lower() == "up",
    )


def _compile_counter_doubler(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    putter_spec = read_putter_counter_amount(effect)
    if putter_spec is not None:
        return _static_form(effect.text, putter_spec)
    event_match = _COUNTER_AMOUNT_EVENT_RE.match((effect.event or "").strip())
    if event_match is None:
        return None
    replacement_match = _COUNTER_AMOUNT_REPLACEMENT_RE.match(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None

    if event_match.group("player_event") is not None:
        # "If you would get one or more [kind] counters, ..." - CR 201.5's
        # "you" is the ability's own controller (see
        # `_counter_amount_applies_to_player`'s docstring); there is no card
        # subject or type filter to read at all.
        event_kind = _normalized_counter_kind(event_match.group("player_kind"))
        is_player_replacement = (
            replacement_match.group("pmult") is not None
            or replacement_match.group("pplus") is not None
            or replacement_match.group("pkind") is not None
            or "you get" in (effect.replacement or "").strip().lower()
        )
        if not is_player_replacement:
            return None  # the card-counter branch matched instead - wrong shape
        pkind = _normalized_counter_kind(replacement_match.group("pkind"))
        if pkind != event_kind:
            return None
        apply = _counter_amount(replacement_match)
        if apply is None:
            return None
        return CardReplacement(
            label=effect.text,
            applies=_counter_amount_applies_to_player(event_kind),
            apply=apply,
        )

    spec = read_counter_amount(effect)
    return None if spec is None else _static_form(effect.text, spec)


def read_counter_amount(effect: ReplacementEffect) -> "CounterAmountReplacement | None":
    """`CounterAmountReplacement`'s reader - the card-counter half of
    `_compile_counter_doubler` (Hardened Scales, Doubling Season's counter
    line, Branching Evolution, Vizier of Remedies, Winding Constrictor's card
    line), and Prairie Dog's active-voice created form of the same sentence.
    A multiplier and an addend are data, never pinned."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _COUNTER_AMOUNT_EVENT_RE.match((effect.event or "").strip())
    if event_match is None or event_match.group("player_event") is not None:
        return None
    replacement_match = _COUNTER_AMOUNT_REPLACEMENT_RE.match(
        (effect.replacement or "").strip().rstrip(".")
    )
    if replacement_match is None:
        return None
    active_voice = event_match.group("put_subject") is not None
    # Doc Samson, Super Psychiatrist's "put that many plus one of each of
    # those kinds of counters on that permanent" is the active voice too, with
    # Winding Constrictor's kindless "of each of those kinds" in place of a
    # named kind.
    active_replacement = (
        replacement_match.group("put_rkind") is not None
        or replacement_match.group("put_each") is not None
    )
    if active_voice != active_replacement:
        # "you would put ... put that many" is one voice throughout; a passive
        # event with an active replacement (or the reverse) is no printing.
        return None
    subject_match = _COUNTER_SUBJECT_RE.match(
        (
            event_match.group("effect_subject")
            or event_match.group("subject")
            or event_match.group("put_subject")
        ).lower()
    )
    if subject_match is None:
        return None
    types = _counter_subject_types(subject_match.group("types"))
    if types is False:
        return None

    event_kind = (event_match.group("kind") or event_match.group("put_kind") or "").lower() or None
    replacement_kind = (
        replacement_match.group("kind") or replacement_match.group("put_rkind") or ""
    ).lower() or None
    if replacement_kind != event_kind:
        # "+1/+1 counters would be put ... that many plus one -1/-1 counters"
        # is no card; "of each of those kinds" answers only a kindless event.
        return None
    amount = _counter_amount_values(replacement_match)
    if amount is None:
        return None
    multiplier, addend = amount
    return CounterAmountReplacement(
        counter_kind=event_kind,
        types=None if types is None else tuple(sorted(types)),
        you_control=subject_match.group("you_control") is not None,
        you_put=active_voice,
        multiplier=multiplier,
        addend=addend,
    )


# -- "<permanents> your opponents control enter tapped" (CR 614.1d, non-self) --

#: The plural card-type nouns a "<list> your opponents control enter tapped"
#: subject names, each optionally "nonbasic" (CR 205.4a's supertype).
_PLURAL_PERMANENT_TYPES = {
    "artifacts": Type.ARTIFACT,
    "battles": Type.BATTLE,
    "creatures": Type.CREATURE,
    "enchantments": Type.ENCHANTMENT,
    "lands": Type.LAND,
    "planeswalkers": Type.PLANESWALKER,
}
_OPPONENTS_CONTROL_SUBJECT_RE = re.compile(
    r"^(?P<classes>.+?) your opponents control$", re.IGNORECASE
)
_TYPE_LIST_SPLIT_RE = re.compile(r",\s*(?:and\s+|or\s+)?|\s+(?:and|or)\s+", re.IGNORECASE)


def _read_opponents_permanent_classes(subject: str) -> tuple[tuple[Type, bool], ...] | None:
    """ "Creatures your opponents control", "Artifacts, creatures, and lands
    your opponents control", "Creatures and nonbasic lands your opponents
    control" - each noun as `(type, nonbasic)`, or `None` for any noun this
    does not read (fail closed rather than drop it)."""
    match = _OPPONENTS_CONTROL_SUBJECT_RE.match(subject.strip())
    if match is None:
        return None
    classes: list[tuple[Type, bool]] = []
    for noun in _TYPE_LIST_SPLIT_RE.split(match.group("classes").strip().lower()):
        noun = noun.strip()
        nonbasic = noun.startswith("nonbasic ")
        if nonbasic:
            noun = noun[len("nonbasic ") :]
        card_type = _PLURAL_PERMANENT_TYPES.get(noun)
        if card_type is None:
            return None
        classes.append((card_type, nonbasic))
    return tuple(classes) or None


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


def _rules_lines(text: str) -> list[str]:
    """Each line of `text` with its reminder text stripped (CR 207.2a)."""
    return [strip_reminder_text(line)[0] for line in text.splitlines()]


# -- "If you would lose the game, instead <effects>." (CR 104.3b/c/d/e's own
#    loss, replaced by CR 614.1a) - Exquisite Archangel, Lich's Mirror -------
#
# `_try_if_would` already parses this into `event="you would lose the game"`,
# `replacement="<effects>"` - the general `IF_WOULD_INSTEAD` shape every other
# "if ... would ..., instead ..." sentence in this file goes through. What is
# new here is only the *event* (CR 104.3's loss, `EventKind.LOSE_THE_GAME`) and
# a small vocabulary for the two printed "<effects>" shapes the pool carries:
# CR 201.5's "exile this creature" self-reference (any noun, not just
# Exquisite Archangel's own "creature") joined by a bare "and" to a life-total
# clause, and CR 701.24a's "shuffle your hand, your graveyard, and all
# permanents you own into your library" joined by "then" to a draw and a
# second life-total clause. Both read the life-total half through
# `machines/effects.life_total_becomes_effect_for` - the one place CR 119.5's
# "sets a player's life total to a specific number" is read, so a replacement
# and a resolving spell/trigger never disagree about what "life total becomes
# ..." means.

_LOSE_THE_GAME_EVENT_RE = re.compile(r"^you would lose the game$", re.IGNORECASE)

#: "exile this creature and your life total becomes equal to your starting
#: life total." (Exquisite Archangel). `noun` is read but not constrained to
#: "creature" - CR 201.5 makes "this `<noun>`" a self-reference whatever the
#: permanent's own type happens to be.
_EXILE_SELF_AND_LIFE_TOTAL_BECOMES_RE = re.compile(
    r"^exile this (?P<noun>[a-z]+) and (?P<life_clause>your life total becomes .+)$",
    re.IGNORECASE,
)

#: "shuffle your hand, your graveyard, and all permanents you own into your
#: library, then draw N cards and your life total becomes M." (Lich's
#: Mirror). CR 701.24a's shuffle over three named piles at once (hand,
#: graveyard, and every permanent this player owns - not merely controls,
#: since a stolen permanent is shuffled into *its owner's* library, CR
#: 401.1), then CR 121.1's draw and CR 119.5's life-total-becomes, chained by
#: "then" and a bare "and".
_SHUFFLE_HAND_GRAVEYARD_PERMANENTS_THEN_DRAW_AND_LIFE_TOTAL_RE = re.compile(
    rf"^shuffle your hand, your graveyard, and all permanents you own into "
    rf"your library, then draw (?P<draw>{COUNT}) cards? and "
    rf"(?P<life_clause>your life total becomes .+)$",
    re.IGNORECASE,
)


def _compile_exile_self_and_life_total_becomes(
    effect: "ReplacementEffect",
) -> "CardReplacement | None":
    """Exquisite Archangel's own shape - see the section banner above."""
    from ..effects import life_total_becomes_effect_for

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if _LOSE_THE_GAME_EVENT_RE.fullmatch((effect.event or "").strip()) is None:
        return None
    match = _EXILE_SELF_AND_LIFE_TOTAL_BECOMES_RE.fullmatch(
        (effect.replacement or "").strip().rstrip(".")
    )
    if match is None:
        return None
    life_total = life_total_becomes_effect_for(match.group("life_clause"))
    if life_total is None:
        return None

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        return (
            event.kind is EventKind.LOSE_THE_GAME
            and event.player is not None
            and event.player.username == source.controller
        )

    def apply(game: "Game", source: CardState | None, event: "ReplaceableEvent") -> None:
        event.replaced = True
        if source is None or event.player is None:
            return
        if source.zone is Zone.BATTLEFIELD:
            game.exile_cards([source])
        life_total(game, event.player, source.name, source_id_of(source))

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


def _compile_shuffle_hand_graveyard_permanents_then_draw_and_life_total(
    effect: "ReplacementEffect",
) -> "CardReplacement | None":
    """Lich's Mirror's own shape - see the section banner above."""
    from ..effects import life_total_becomes_effect_for

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if _LOSE_THE_GAME_EVENT_RE.fullmatch((effect.event or "").strip()) is None:
        return None
    match = _SHUFFLE_HAND_GRAVEYARD_PERMANENTS_THEN_DRAW_AND_LIFE_TOTAL_RE.fullmatch(
        (effect.replacement or "").strip().rstrip(".")
    )
    if match is None:
        return None
    draw_count = parse_count(match.group("draw"))
    life_total = life_total_becomes_effect_for(match.group("life_clause"))
    if draw_count is None or life_total is None:
        return None

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        return (
            event.kind is EventKind.LOSE_THE_GAME
            and event.player is not None
            and event.player.username == source.controller
        )

    def apply(game: "Game", source: CardState | None, event: "ReplaceableEvent") -> None:
        event.replaced = True
        player = event.player
        if player is None:
            return
        owned = [
            permanent
            for permanent in list(game.battlefield)
            if (permanent.owner or permanent.controller) == player.username
        ]
        game.put_cards_into_library([*player.hand, *player.graveyard, *owned])
        game.shuffle_library(player)
        game.draw_cards(player.username, draw_count)
        life_total(game, player, source.name if source is not None else "Lich's Mirror", None)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- "If your life total would be reduced to 0 or less, instead <effects>."
#    (Enduring Angel) -----------------------------------------------------
#
# A different `IF_WOULD_INSTEAD` event than the "lose the game" family above:
# this one watches the *life loss itself* (any `DAMAGE` to a player or any
# `LOSE_LIFE`, CR 119.2/119.3 - `Game.deal_damage_to_player` always ends by
# calling `Game.lose_life`, so a combat blow reaches this the same as a plain
# "you lose N life" spell), not CR 104.3's loss that follows it. Enduring
# Angel's own trailing sentence - "Then if this creature didn't transform this
# way, you lose the game." - is not part of the same parsed `ReplacementEffect`
# (the sentence splitter that produces `event`/`replacement` keeps only the
# first sentence of the paragraph), so it is read off `effect.raw`, the whole
# printed paragraph, directly.

#: "your life total would be reduced to 0 or less" - the threshold is read,
#: not hardcoded, so a differently-worded printing (a `less than 1`-shaped
#: sibling naming another number) is not left out.
_LIFE_REDUCED_TO_THRESHOLD_INSTEAD_EVENT_RE = re.compile(
    r"^your life total would be reduced to (?P<threshold>\d+) or less$", re.IGNORECASE
)
#: "transform this creature and your life total becomes 3." `noun` is read but
#: not constrained to "creature", the same CR 201.5 generality `_EXILE_SELF_
#: AND_LIFE_TOTAL_BECOMES_RE` above already gives "exile this `<noun>`".
_TRANSFORM_SELF_AND_LIFE_TOTAL_BECOMES_RE = re.compile(
    r"^transform this (?P<noun>[a-z]+) and (?P<life_clause>your life total becomes .+)$",
    re.IGNORECASE,
)
#: "Then if this creature didn't transform this way, you lose the game." -
#: read off `effect.raw` (see the section banner above), not off `event`/
#: `replacement`.
_THEN_IF_DIDNT_TRANSFORM_LOSE_RE = re.compile(
    r"then if this [a-z]+ didn'?t transform this way, you lose the game\.?\s*$", re.IGNORECASE
)


def _compile_life_reduced_to_threshold_transform(
    effect: "ReplacementEffect",
) -> "CardReplacement | None":
    """Enduring Angel's own shape - see the section banner above."""
    from ..effects import life_total_becomes_effect_for

    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _LIFE_REDUCED_TO_THRESHOLD_INSTEAD_EVENT_RE.fullmatch(
        (effect.event or "").strip()
    )
    if event_match is None:
        return None
    threshold = parse_count(event_match.group("threshold"))
    match = _TRANSFORM_SELF_AND_LIFE_TOTAL_BECOMES_RE.fullmatch(
        (effect.replacement or "").strip().rstrip(".")
    )
    if threshold is None or match is None:
        return None
    life_total = life_total_becomes_effect_for(match.group("life_clause"))
    if life_total is None:
        return None
    then_loses = _THEN_IF_DIDNT_TRANSFORM_LOSE_RE.search(effect.raw) is not None

    def applies(game: "Game", source: CardState, event: "ReplaceableEvent") -> bool:
        if event.kind not in (EventKind.DAMAGE, EventKind.LOSE_LIFE):
            return False
        if event.player is None or event.amount <= 0:
            return False
        if event.player.username != source.controller:
            return False
        return event.player.life - event.amount <= threshold

    def apply(game: "Game", source: CardState | None, event: "ReplaceableEvent") -> None:
        # CR 614.6: the original loss never happens - transforming and
        # setting the life total happens in its place.
        event.amount = 0
        player = event.player
        if source is None or player is None:
            return
        before = source.times_transformed
        if source.zone is Zone.BATTLEFIELD:
            source.transform()
        transformed = source.times_transformed != before
        life_total(game, player, source.name, source_id_of(source))
        if then_loses and not transformed:
            game.player_loses_the_game(player.username)

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


# -- "if <player> would draw a card[ except ...], [instead ]that player skips
#    that draw[ and you draw a card]" (Notion Thief; Plagiarize's created form) --

#: "that player skips that draw[ and you draw a card]" - the replacement half.
_DRAW_SKIP_RE = re.compile(
    r"^that player skips that draw(?P<you> and you draw a card)?$", re.IGNORECASE
)
#: "<who> would draw a card[ except the first one they draw in each of their
#: draw steps]" - the event half.
_DRAW_EVENT_RE = re.compile(
    r"^(?P<who>target player|an opponent|a player|you) would draw a card"
    r"(?P<except> except the first one (?:they|you) draws? in each of (?:their|your) draw steps)?$",
    re.IGNORECASE,
)
_DRAW_WHO: dict[str, Literal["player", "opponent", "you", "any"]] = {
    "target player": "player",
    "an opponent": "opponent",
    "a player": "any",
    "you": "you",
}


def read_draw_skip(effect: ReplacementEffect) -> "DrawSkipReplacement | None":
    """`DrawSkipReplacement`'s reader, shared by the static and created forms.
    "target player" comes back with no `affected_player`; the caller that
    knows the target fills it in (only a resolving spell has one)."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    event_match = _DRAW_EVENT_RE.match((effect.event or "").strip())
    replacement_match = _DRAW_SKIP_RE.match((effect.replacement or "").strip().rstrip("."))
    if event_match is None or replacement_match is None:
        return None
    return DrawSkipReplacement(
        affected=_DRAW_WHO[event_match.group("who").lower()],
        except_first_draw_step_draw=event_match.group("except") is not None,
        you_draw=replacement_match.group("you") is not None,
    )


def _compile_draw_skip(effect: ReplacementEffect) -> CardReplacement | None:
    """Notion Thief's static line - the static form of `DrawSkipReplacement`.
    A "target player" has no meaning on a static ability, so it is refused."""
    spec = read_draw_skip(effect)
    if spec is None or spec.affected == "player":
        return None
    return _static_form(effect.text, spec)


def _static_form(
    label: str, spec: "DrawSkipReplacement | CounterAmountReplacement | EnterUncastExile"
) -> CardReplacement:
    """A created-form spec as a permanent's static replacement: "you" is the
    permanent's controller."""

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        return spec.applies(game, source.controller or "", event)

    def apply(game: "Game", source: CardState | None, event: ReplaceableEvent) -> None:
        spec.apply(game, (source.controller if source is not None else None) or "", event)

    return CardReplacement(label=label, applies=applies, apply=apply)


#: Tried in order against every parsed effect on a `REPLACEMENTS` miss. Order
#: does not matter between them - each one's event/replacement match is
#: specific enough that at most one ever claims a given `ReplacementEffect`.
_COMPILERS: tuple[Callable[[ReplacementEffect], CardReplacement | None], ...] = (
    _compile_graveyard_exile,
    _compile_dies_exile,
    _compile_enters_uncast_exile,
    _compile_damage_multiplier,
    _compile_damage_plus_amount,
    _compile_damage_as_counters,
    compile_damage_plus_source_characteristic,
    compile_heal_other_damage,
    _compile_prevent_damage_and_mill,
    _compile_prevent_damage_to_you,
    _compile_self_prevent_combat_damage,
    _compile_prevent_all_to_group,
    _compile_life_gain_doubler,
    _compile_draw_doubler_except_draw_step,
    _compile_draw_doubler,
    _compile_draw_plus,
    _compile_draw_skip,
    _compile_token_doubler,
    _compile_extra_token,
    _compile_token_substitution,
    _compile_first_time_token_copies,
    _compile_counter_doubler,
    _compile_lands_you_control_enter_untapped,
    _compile_opponents_permanents_enter_tapped,
    _compile_exile_self_and_life_total_becomes,
    _compile_shuffle_hand_graveyard_permanents_then_draw_and_life_total,
    _compile_life_reduced_to_threshold_transform,
)


#: The compilers that read `ReplacementEffect.condition` themselves. Every
#: other compiler above is condition-blind, so an effect carrying an "as long
#: as ..." qualifier is never offered to one: compiling it there would perform
#: the replacement unconditionally and silently drop the clause, which is the
#: exact failure the fail-closed rule at the top of this section forbids.
_CONDITION_AWARE_COMPILERS = frozenset(
    {_compile_draw_plus, _compile_first_time_token_copies, _compile_damage_plus_amount}
)


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
    from .prevention_statics import damage_static_replacements  # imports this module

    found: list[CardReplacement] = (
        _keyword_replacements(card)
        + _cant_enter_replacements(card)
        + _double_all_damage_replacements(_rules_lines(card.oracle_text or ""))
        + _damage_life_floor_replacements(_rules_lines(card.oracle_text or ""))
        + damage_static_replacements(card, _rules_lines(card.oracle_text or ""))
    )
    for effect in parse_replacement_effects(card):
        compiled = _compile(effect)
        if compiled is not None:
            found.append(compiled)
    return found


def performs_static_line(card: Card, text: str) -> bool:
    """Whether one of this card's printed static lines is a replacement or
    prevention effect this module actually performs - a generic compiler
    claims it, or it is a "Double all damage ... would deal." line.
    `support.py`'s credit for such a line (CR 614.1, CR 615.1).

    Matched against either `effect.text` (the one sentence the event/
    replacement split was read from) or `effect.raw` (the whole printed
    paragraph) - the two are equal for an ordinary one-sentence paragraph,
    but Enduring Angel's own "... instead transform this creature and your
    life total becomes 3. Then if this creature didn't transform this way,
    you lose the game." is two: only the first sentence becomes `event`/
    `replacement`, and a compiler that also reads the second off `effect.raw`
    (`_compile_life_reduced_to_threshold_transform`) still needs `text` here
    - the *whole* paragraph `support.py` passes in - to find a match.
    """
    line = strip_reminder_text(text)[0].strip()
    if not line:
        return False
    if double_all_damage_line(line):
        return True
    if damage_life_floor_line(line):
        return True
    return any(
        line in (effect.text.strip(), effect.raw.strip()) and _compile(effect) is not None
        for effect in parse_replacement_effects(card)
    )


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


# --------------------------------------------------------------------------
# Mana production (CR 106.12, CR 106.12b)
# --------------------------------------------------------------------------
#
# "If a land is tapped for two or more mana, it produces {C} instead of any
# other type and amount." (Damping Sphere) and "If you tap a permanent for
# mana, it produces three times as much of that mana instead." (Nyxbloom
# Ancient; Mana Reflection's "twice", Virtue of Strength's "a basic land").
#
# CR 106.12: to "tap [a permanent] for mana" is to activate one of its mana
# abilities with {T} in its cost. CR 106.12b: a replacement effect that
# applies if a permanent "is tapped for mana" or for mana of a specific type
# and/or amount "modifies the mana production event while such an ability is
# resolving and producing mana". So the event is the production itself - what
# the ability would add - and the replacement rewrites that list of mana
# before it reaches the pool. The ability's other effects (Ancient Tomb's 2
# damage) are not production and are untouched.
#
# Not routed through `apply_replacements`: a mana ability resolves inside
# cost payment and inside the auto-tap solver's pure planning pass, which
# asks the same question once per candidate source. `replace_mana_production`
# gathers only these effects (cheaply, off each permanent's printed text) and
# runs CR 616.1's loop itself.

#: The whole sentence. "you tap" is the active voice (the effect's controller
#: must be the one tapping); "is tapped" is anybody's. "for two or more mana"
#: is the amount condition CR 106.12b names ("of a specific ... amount").
_MANA_PRODUCTION_RE = re.compile(
    r"^if (?:(?P<you>you) tap (?P<you_subject>an? [a-z ]+?)|(?P<subject>an? [a-z ]+?) is tapped)"
    r" for (?:(?P<least>[\w-]+) or more )?mana, it produces"
    r" (?:(?P<colorless>\{C\} instead of any other type and amount)"
    rf"|(?P<mult>{MULTIPLIER}) as much of that mana instead)\.?$",
    re.IGNORECASE,
)


def read_mana_production(sentence: str) -> ManaProductionReplacement | None:
    """The mana-production replacement a sentence prints, or `None`."""
    match = _MANA_PRODUCTION_RE.fullmatch(" ".join(sentence.strip().split()))
    if match is None:
        return None
    words = (match.group("you_subject") or match.group("subject")).lower().split()[1:]
    basic = bool(words) and words[0] == "basic"
    if basic:
        words = words[1:]
    if len(words) != 1:
        return None
    if words[0] == "permanent":
        types: tuple[Type, ...] | None = None
    elif words[0] in _CARD_TYPE_WORDS:
        types = (_CARD_TYPE_WORDS[words[0]],)
    else:
        return None
    at_least = 1
    if match.group("least") is not None:
        least = parse_count(match.group("least"))
        if least is None:
            return None
        at_least = least
    multiplier = 1
    if match.group("mult") is not None:
        parsed = parse_multiplier(match.group("mult"))
        if parsed is None:
            return None
        multiplier = parsed
    return ManaProductionReplacement(
        you_tap=match.group("you") is not None,
        types=types,
        basic=basic,
        at_least=at_least,
        colorless_instead=match.group("colorless") is not None,
        multiplier=multiplier,
    )


@functools.cache
def _mana_production_specs(oracle_text: str) -> tuple[ManaProductionReplacement, ...]:
    """Every mana-production replacement in one printed text, one per
    sentence that reads - cached by text, since the auto-tap solver asks for
    every permanent's on every scan."""
    specs: list[ManaProductionReplacement] = []
    for line in oracle_text.split("\n"):
        stripped, _reminder = strip_reminder_text(line)
        for sentence in _SENTENCE_SPLIT.split(stripped.strip()):
            spec = read_mana_production(sentence)
            if spec is not None:
                specs.append(spec)
    return tuple(specs)


def mana_production_effects(
    game: "Game",
) -> list[tuple[str, CardState, ManaProductionReplacement]]:
    """Every mana-production replacement on the battlefield, as (CR 614.5
    key, source permanent, spec), in battlefield order. CR 604.2: a static
    ability's effect exists while its permanent is on the battlefield."""
    found: list[tuple[str, CardState, ManaProductionReplacement]] = []
    for permanent in game.battlefield:
        text = permanent.class_ability_text or ""
        for index, spec in enumerate(_mana_production_specs(text)):
            found.append((f"{permanent.id}:mana:{index}", permanent, spec))
    return found


def replace_mana_production(
    game: "Game",
    source: CardState,
    produced: Iterable[Color],
    *,
    tapper: str | None = None,
    effects: list[tuple[str, CardState, ManaProductionReplacement]] | None = None,
) -> list[Color]:
    """What tapping `source` for `produced` really adds (CR 106.12b).

    CR 616.1: the affected player - the one tapping - chooses which
    applicable effect to apply; CR 616.1f: after each, only the effects that
    now apply are considered, so a Forest's single {G} tripled by Nyxbloom
    Ancient is then a land tapped for three mana that Damping Sphere does
    apply to. CR 614.5: each effect applies at most once. With nobody to ask
    here (this runs mid-payment and inside the solver's planning pass), the
    choice is made for the tapping player the way `auto_tap` picks a dual
    land's colour: the order that leaves the most mana, ties broken by
    battlefield order.

    `effects` is `mana_production_effects(game)`, hoisted by a caller asking
    about many sources over one battlefield.
    """
    mana = list(produced)
    if effects is None:
        effects = mana_production_effects(game)
    if not effects:
        return mana
    who = tapper if tapper is not None else source.controller

    def best(current: list[Color], applied: frozenset[str]) -> list[Color]:
        result = current
        for key, permanent, spec in effects:
            if key in applied:
                continue
            if not spec.applies(game, permanent.controller, source, who, current):
                continue
            candidate = best(spec.apply(current), applied | {key})
            if result is current or len(candidate) > len(result):
                result = candidate
        return result

    return best(mana, frozenset())


def is_mana_production_line(text: str) -> bool:
    """Whether one printed static line is a mana-production replacement this
    module performs."""
    return bool(_mana_production_specs(text))


#: The static-replacement readers `performed_static_replacement_line` vouches
#: for, each proven by a scenario file on a listed card and on a second
#: printing: graveyard-bound exile (`test_graveyard_exile_replacement.py`),
#: uncast-enter exile (`test_uncast_creature_exile_replacement.py`), counter
#: quantity (`test_counter_minus_one_replacement.py`) and draw quantity
#: (`test_draw_plus_one_replacement.py`). A compiler not listed here may well
#: work; it is simply not audited by this function.
_AUDITED_STATIC_COMPILERS: tuple[Callable[[ReplacementEffect], CardReplacement | None], ...] = (
    _compile_graveyard_exile,
    # C01-T7: proven by `test_die_exile_replacement_widened.py` (Head of the
    # Hunt, Nemata, Primeval Warden), with and without its reflexive rider.
    _compile_dies_exile,
    _compile_enters_uncast_exile,
    _compile_counter_doubler,
    _compile_draw_plus,
    _compile_draw_doubler,
    _compile_draw_doubler_except_draw_step,
    # R0a-T5: proven by `test_noncombat_damage_as_minus_counters.py`.
    _compile_damage_as_counters,
    # Proven by `test_static_prevent_damage_to_you.py` (Purity, with its CR
    # 615.5 life-gain rider).
    _compile_prevent_damage_to_you,
)


def performed_static_replacement_line(card: Card, text: str) -> bool:
    """Whether every sentence of one printed static line is a replacement
    effect this module really performs from the battlefield - read by one of
    `_AUDITED_STATIC_COMPILERS` exactly as `replacements_of_state` would read
    it, or a mana-production replacement (`test_mana_production_replacement.py`).

    Fail-closed per sentence: a line where any sentence carrying a
    replacement cue is unread is not vouched for.
    """
    if is_mana_production_line(text):
        return True
    effects = _parse_oracle_text(text, face=None, names=_names_of(card))
    if not effects:
        return False
    for effect in effects:
        if effect.from_trigger or _compile(effect) is None:
            return False
        if not any(
            (effect.condition is None or compiler in _CONDITION_AWARE_COMPILERS)
            and compiler(effect) is not None
            for compiler in _AUDITED_STATIC_COMPILERS
        ):
            return False
    return True


#: The event half of a created die-to-exile replacement, the duration words
#: already taken off: "a creature would die" (Malicious Malfunction, Flaying
#: Tendrils, Cry of the Carnarium) and "a creature an opponent controls would
#: die" (Malicious Eclipse), plus the "you control" twin of the static form.
_CREATED_DIES_EVENT_RE = re.compile(
    r"^a (?P<nontoken>nontoken )?creature(?: (?P<whose>an opponent controls|you control))? "
    r"would die$",
    re.IGNORECASE,
)


def read_die_to_exile(effect: ReplacementEffect) -> DieToExileReplacement | None:
    """`DieToExileReplacement`'s reader, for the created form."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD:
        return None
    if (effect.replacement or "").strip().rstrip(".").lower() != "exile it":
        return None
    match = _CREATED_DIES_EVENT_RE.match((effect.event or "").strip())
    if match is None:
        return None
    whose = match.group("whose")
    return DieToExileReplacement(
        whose=None if whose is None else ("you" if whose.lower() == "you control" else "opponent"),
        nontoken=match.group("nontoken") is not None,
    )


#: The two duration forms a created replacement is printed with: a leading
#: "Until end of turn," (Plagiarize, Prairie Dog) or "this turn" inside the
#: event (Gather Specimens, Crafty Cutpurse).
_UNTIL_END_OF_TURN_PREFIX_RE = re.compile(r"^until end of turn,\s*", re.IGNORECASE)
_THIS_TURN_RE = re.compile(r"\s+this turn\b", re.IGNORECASE)


# -- turn-long damage effects of a resolving spell or ability ------------------

#: "Prevent all [combat] damage that would be dealt by creatures this turn."
#: (Ethereal Haze), with CR 615.5's "You gain life equal to the damage
#: prevented this way." (Chant of Vitu-Ghazi). The dealers are "creatures" or
#: "`<quality>` sources" (CR 609.7b: a quality rechecked as damage is dealt).
_PREVENT_ALL_BY_THIS_TURN_RE = re.compile(
    r"^prevent all (?P<combat>combat )?damage that would be dealt (?:this turn )?by "
    r"(?:(?P<creatures>creatures)|(?P<quality>[a-z]+) sources) this turn\."
    r"(?P<gain> you gain life equal to the damage prevented this way\.)?$",
    re.IGNORECASE,
)
#: "If a source you control would deal damage this turn, it deals double that
#: damage instead." (Insult) - `read_damage_modifier`'s shape for the turn.
_TURN_DAMAGE_MODIFIER_RE = re.compile(
    r"^if (?P<event>.+? would deal (?:noncombat )?damage(?: to .+?)?) this turn, "
    r"(?P<replacement>it deals .+?) instead\.$",
    re.IGNORECASE,
)
#: "[Combat] damage can't be prevented this turn." - only ever read here as
#: one part of a group (CR 615.12): on its own, the clause reader's
#: `CastingRuleEffect` (Skullcrack, Stomp) already performs it.
_CANT_BE_PREVENTED_THIS_TURN_RE = re.compile(
    r"^(?P<combat>combat )?damage can'?t be prevented this turn\.$", re.IGNORECASE
)
#: CR 614.9's redirection, created for the turn: "All [combat] damage that
#: would be dealt [this turn] to `<protected>` [this turn] [by a source of your
#: choice] is dealt to `<new>` instead." (Kor Dirge, Turn the Tables) and "The
#: next N damage that would be dealt to `<protected>` this turn is dealt to
#: `<new>` instead." (Carom, Razia, Boros Archangel).
_REDIRECT_ALL_RE = re.compile(
    r"^all (?P<combat>combat )?damage that would be dealt (?P<early>this turn )?to "
    r"(?P<protected>.+?)(?P<late> this turn)?(?: by (?P<source>a source of your choice))? "
    r"is dealt to (?P<new>.+?) instead\.$",
    re.IGNORECASE,
)
_REDIRECT_NEXT_RE = re.compile(
    rf"^the next (?:(?P<x>x)|(?P<n>{COUNT})) damage that "
    r"(?:would be dealt to (?P<protected>.+?)"
    r"|(?P<source>a source of your choice) would deal to (?P<protected_by>.+?)) this turn "
    r"is dealt to (?P<new>.+?) instead\.$",
    re.IGNORECASE,
)
#: "you and/or permanents you control" / "you and/or creatures you control"
#: (Harm's Way, Shining Shoal): the controller and every permanent of theirs
#: (with that card type) as the damage would be dealt.
_REDIRECT_YOU_AND_YOURS_RE = re.compile(
    r"^you and(?:/or)? (?P<what>permanents|creatures) you control$", re.IGNORECASE
)
#: "is dealt to enchanted creature instead" (Saving Grace): the redirect
#: target is the creature the creating Aura is attached to as the effect is
#: created (CR 303.4b), not a target.
_REDIRECT_TO_ENCHANTED_RE = re.compile(r"^enchanted creature$", re.IGNORECASE)
#: A targeted damage recipient: a creature, planeswalker or battle (CR 614.9's
#: own list), "another" one included.
_REDIRECT_TARGET_PHRASE_RE = re.compile(
    r"^(?:another )?target (?:[a-z]+ )*?(?:creature|planeswalker|battle)(?: you control)?$",
    re.IGNORECASE,
)
_TARGET_WORD_RE = re.compile(r"\btarget\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=\.)\s+(?=[A-Z])")


def _target_index(sentence: str, phrase_start: int, offset: int) -> int:
    """Which of the creating object's targets a phrase names (CR 601.2c: they
    are chosen in the order the text names them)."""
    return offset + len(_TARGET_WORD_RE.findall(sentence[:phrase_start]))


def _read_turn_damage_sentence(sentence: str, offset: int, *, grouped: bool) -> object | None:
    """One sentence of `read_turn_damage_spec`, or None. `offset` is how many
    targets the sentences before it named."""
    prevent = _PREVENT_ALL_BY_THIS_TURN_RE.fullmatch(sentence)
    if prevent is not None:
        quality = "creature" if prevent.group("creatures") else prevent.group("quality").lower()
        return PreventDamageByReplacement(
            source_quality=quality,
            combat_only=prevent.group("combat") is not None,
            gains_life=prevent.group("gain") is not None,
        )
    modifier = _TURN_DAMAGE_MODIFIER_RE.fullmatch(sentence)
    if modifier is not None:
        return read_damage_modifier(modifier.group("event"), modifier.group("replacement"))
    if grouped:
        unpreventable = _CANT_BE_PREVENTED_THIS_TURN_RE.fullmatch(sentence)
        if unpreventable is not None:
            return DamageCantBePreventedReplacement(
                combat_only=unpreventable.group("combat") is not None
            )
    redirect = _REDIRECT_ALL_RE.fullmatch(sentence)
    amount: int | None = None
    amount_is_x = False
    if redirect is None:
        redirect = _REDIRECT_NEXT_RE.fullmatch(sentence)
        if redirect is None:
            return None
        if redirect.group("x") is not None:
            amount_is_x = True  # CR 107.3a: the announced X, read on resolution
        else:
            amount = parse_count(redirect.group("n"))
            if amount is None:
                return None
    elif not (redirect.group("early") or redirect.group("late")):
        return None  # no stated duration (CR 611.2a): not this shape.
    new = redirect.group("new")
    to_enchanted = _REDIRECT_TO_ENCHANTED_RE.fullmatch(new) is not None
    # CR 115.4: "any target" - a creature, player, planeswalker or battle.
    if (
        not to_enchanted
        and new.lower() != "any target"
        and _REDIRECT_TARGET_PHRASE_RE.fullmatch(new) is None
    ):
        return None
    group = "protected" if redirect.groupdict().get("protected") else "protected_by"
    protected = redirect.group(group)
    protected_target: int | None = None
    yours_types: tuple[str, ...] | None = None
    if (yours := _REDIRECT_YOU_AND_YOURS_RE.fullmatch(protected)) is not None:
        yours_types = ("creature",) if yours.group("what").lower() == "creatures" else ()
    elif protected.lower() != "you":
        if _REDIRECT_TARGET_PHRASE_RE.fullmatch(protected) is None:
            return None
        protected_target = _target_index(sentence, redirect.start(group), offset)
    return DamageRedirectReplacement(
        combat_only=bool(redirect.groupdict().get("combat")),
        protected_target=protected_target,
        redirect_target=(
            0 if to_enchanted else _target_index(sentence, redirect.start("new"), offset)
        ),
        redirect_to_enchanted=to_enchanted,
        choose_source=bool(redirect.groupdict().get("source")),
        amount=amount,
        amount_is_x=amount_is_x,
        protects_yours=yours_types is not None,
        protected_types=yours_types or (),
    )


def read_turn_damage_spec(text: str) -> CreatedReplacementSpec | None:
    """The turn-long damage effect(s) a resolving spell's or ability's text
    creates (`damage_modification`'s banner), or None. Several sentences, each
    one such effect, are one `TurnDamageGroup` (CR 608.2c's printed order); a
    sentence this does not read leaves the whole text unread."""
    body = " ".join(text.strip().split())
    single = _read_turn_damage_sentence(body, 0, grouped=False)
    if single is not None:
        return single  # type: ignore[return-value]
    sentences = _SENTENCE_SPLIT_RE.split(body)
    if len(sentences) < 2:
        return None
    parts = []
    offset = 0
    for sentence in sentences:
        part = _read_turn_damage_sentence(sentence, offset, grouped=True)
        if part is None:
            return None
        parts.append(part)
        offset += len(_TARGET_WORD_RE.findall(sentence))
    if all(isinstance(part, DamageCantBePreventedReplacement) for part in parts):
        return None
    return TurnDamageGroup(parts=parts)


def created_replacement_spec(sentence: str) -> CreatedReplacementSpec | None:
    """The resolution-created replacement a sentence prints, or `None`.

    Only a sentence carrying a stated duration is read here ("Until end of
    turn, ..." or "... this turn ..."): without one CR 611.2a would make it
    last the whole game, a shape no printing in the pool has. The duration is
    taken off and the rest is read by the same shape readers the static forms
    use."""
    text = " ".join(sentence.strip().split())
    turn_damage = read_turn_damage_spec(text)
    if turn_damage is not None:
        return turn_damage
    body = _UNTIL_END_OF_TURN_PREFIX_RE.sub("", text, count=1)
    if body == text:
        if _THIS_TURN_RE.search(text) is None:
            return None
        body = _THIS_TURN_RE.sub("", text, count=1)
    body = body[0].upper() + body[1:] if body else body
    entering = _read_enter_under_your_control(body)
    if entering is not None:
        return entering
    # "damage that would reduce your life total to less than N reduces it to
    # N instead" (Angel of Grace's until-end-of-turn form) has no leading
    # "If", so the generic `_parse_sentence` loop below never claims it (see
    # `_damage_life_floor_replacements`'s own banner for why its static twin
    # is read directly off the sentence too, rather than through that parser).
    damage_floor = read_damage_life_floor(body)
    if damage_floor is not None:
        return damage_floor
    for effect in _parse_sentence(body, ()):
        for reader in (
            read_draw_skip,
            read_counter_amount,
            read_enter_uncast_exile,
            read_die_to_exile,
        ):
            spec = reader(effect)
            if spec is not None:
                return spec
    return None


from ..conditions import claims as condition_claims  # noqa: E402
from ._common import _CARD_TYPE_WORDS, _REFLEXIVE_OPENER  # noqa: E402
from .enters import (  # noqa: E402
    _cant_enter_replacements,
    _read_enter_under_your_control,
    _refers_to_self,
    _try_as_enters,
    _try_enters_as_copy,
    _try_enters_prepared,
    _try_enters_tapped,
    _try_enters_untapped,
    _try_enters_with,
    _try_escapes_with,
    read_enter_uncast_exile,
)
from .model import (  # noqa: E402
    ENTERS_KINDS,
    CounterAmountReplacement,
    DamageLifeFloorReplacement,
    DrawSkipReplacement,
    EnterUncastExile,
    EventKind,
)
