import contextlib
import operator
import re
from functools import cache
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...data.subtypes import subtype_vocabulary
from ...models.card import Card, Color, Supertype, Type
from ...models.card_state import CardState, ChoiceKind, Counter
from ...models.zone import Zone
from ...numbers import COUNT, parse_count, parse_ordinal
from ..abilities import (
    TriggeredAbility,
    TriggerEvent,
    self_normalized_effect_text,
    self_reference_names,
    self_reference_pattern,
    self_reference_re,
)
from ..turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ...models.game import CastRecord, Game

    # `.cost` imports names from this module and `.keywords` imports
    # `AbilityOnStack` itself, so neither can be imported for real up here -
    # `keyword_activation`/`unless_payment` below carry these as string
    # annotations, and `keywords.py`'s own `model_rebuild()` call, run once
    # both classes exist, is what resolves them for real.
from .events import ExtraTriggerEvent, GameEvent, _ReturnedSubject, _TypedWhose

# --------------------------------------------------------------------------
# Matching an event against printed trigger conditions
# --------------------------------------------------------------------------

#: The non-type words modern templating also uses to mean "this object
#: itself" - CR 608.2b's own "spell" for an object on the stack, CR 110.1's
#: "permanent", and "card"/"token", none of which is one of CR 205.2a's card
#: types (`Type`) or a printed subtype (`subtype_vocabulary`) but every one
#: of which still names the source and nothing else.
_SELF_REFERENCE_EXTRA_WORDS = frozenset({"permanent", "spell", "card", "token"})


@cache
def _self_reference_type_words() -> frozenset[str]:
    """Every word "this " can be followed by and still mean *itself*
    (CR 700.7, CR 201.5c) - not a fixed list of examples the way
    `_SELF_PHRASES` used to be, which had no entry for Smuggler's Copter's
    own "this Vehicle" (CR 205.3g) until this file was told to add one card
    at a time. Built instead from the same data every other subtype reader
    in this codebase already shares: CR 205.2a's card types (`Type`) and
    every printed CR 205.3 subtype (`subtype_vocabulary`, the flat artifact/
    battle/creature/enchantment/land/planeswalker/spell-type set `layers.py`
    and `replacement.py` already read off `data/subtypes.json`), plus the
    handful of non-type self-reference words `_SELF_REFERENCE_EXTRA_WORDS`
    names. A card's own subtype line is never consulted here - the point of
    reading "this Vehicle" as self-referential is that it is CR 700.7's
    templating convention for *any* Vehicle naming itself, not a fact about
    one particular printing.
    """
    return (
        frozenset(member.value for member in Type)
        | subtype_vocabulary()
        | _SELF_REFERENCE_EXTRA_WORDS
    )


#: "this " followed by the word(s) that say what it is - one word ("this
#: artifact") or CR 205.3m's own two-word creature type ("this Time Lord").
#: Matched here and checked against `_self_reference_type_words` rather than
#: matched by a fixed alternation, so a *new* subtype needs no edit to this
#: file, and "this way"/"this turn"/"this ability" - none of them a type or
#: subtype word - are never mistaken for a self-reference the way a bare
#: "this " substring test would read them.
_SELF_REFERENCE_WORD_RE = re.compile(r"\bthis ([a-z]+(?: [a-z]+)?)\b")


def has_self_reference_type_word(condition: str) -> bool:
    """Whether `condition` (already lowercased by the caller) names its own
    source through "this `<type or subtype word>`" (CR 700.7).

    `_SELF_REFERENCE_WORD_RE` greedily grabs up to two words after "this ",
    to catch a two-word subtype ("this Time Lord") - so a condition whose
    "this `<word>`" is immediately followed by another word of its own
    ("this Vehicle attacks") is checked both as that two-word span and, when
    the span itself names nothing, as its first word alone; either reading
    naming a type or subtype word is enough.
    """
    words = _self_reference_type_words()
    for match in _SELF_REFERENCE_WORD_RE.finditer(condition):
        phrase = match.group(1)
        if phrase in words:
            return True
        first_word = phrase.split(" ", 1)[0]
        if first_word in words:
            return True
    return False


_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
    "enchantment": Type.ENCHANTMENT,
    "instant": Type.INSTANT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "sorcery": Type.SORCERY,
    "battle": Type.BATTLE,
}

#: "At the beginning of [your] upkeep" and friends, mapped onto the turn machine.
#: Ordered longest-phrase-first so "end step" is not mistaken for "step".
_STEP_PHRASES: tuple[tuple[str, Step], ...] = (
    ("end step", Step.END_STEP),
    ("upkeep", Step.UPKEEP),
    ("draw step", Step.DRAW),
    ("untap step", Step.UNTAP),
    ("precombat main phase", Step.PRECOMBAT_MAIN),
    # CR 505.1: "the first main phase (also known as the precombat main
    # phase)" - Static Prison's own "the beginning of your first main phase"
    # is this same phase under its other name, not a step this table was
    # missing a mapping for.
    ("first main phase", Step.PRECOMBAT_MAIN),
    ("postcombat main phase", Step.POSTCOMBAT_MAIN),
    # CR 505.1: "the first main phase (also known as the precombat main
    # phase) and the second main phase (also known as the postcombat main
    # phase)" - Kona, Rescue Beastie's own *survival* trigger says "your
    # second main phase", which is the same phase under its other name.
    # CR 505.1a's corner ("All other main phases are postcombat main phases.
    # This includes the second main phase of a turn in which the combat phase
    # has been skipped") does not arise here: this engine's turn machine has
    # exactly the two main phases CR 500.1 lists.
    ("second main phase", Step.POSTCOMBAT_MAIN),
    # CR 511.2: "at end of combat" is the end of combat step's beginning -
    # ahead of the bare "combat" below, which it contains.
    ("end of combat", Step.END_OF_COMBAT),
    ("combat", Step.BEGINNING_OF_COMBAT),
)


#: Chalice of the Void's shape: "a player casts a spell with mana value equal
#: to the number of charge counters on this artifact". Read here rather than
#: left to `_types_match`'s "no type word means anything matches" default,
#: which would otherwise make Chalice counter every spell cast regardless of
#: mana value - the counter-count comparison is the entire point of the card.
_MANA_VALUE_EQUALS_COUNTERS = re.compile(
    r"with mana value equal to the number of (?P<kind>[a-z]+) counters on "
)

#: Gollum, Riddle Master's own "a spell with mana value of the chosen
#: quality" - CR 614.12a's own "odd or even" choice (`ChoiceKind.ODD_OR_
#: EVEN`), read off the source's own `CardState.choice` rather than a fixed
#: number the way `_MANA_VALUE_EQUALS_COUNTERS` reads Chalice's counters.
_MANA_VALUE_OF_CHOSEN_QUALITY = re.compile(r"with mana value of the chosen quality")


def _is_legendary_source(source: CardState) -> bool:
    """Whether `source`'s own printed card carries CR 205.4a's Legendary
    supertype - the printed fact `self_reference_names`' epithet and
    bare-two-word shortenings are gated on, not the computed board (CR
    613.5): Oracle's own shortened-self-reference convention is a property
    of how a card is *templated*, fixed at print time, not something a
    continuous effect making a permanent legendary this turn should turn on
    for it.
    """
    card = getattr(source, "card", None)
    return card is not None and Supertype.LEGENDARY in card.supertypes


def _self_referential(condition: str, source_name: str, *, legendary: bool = True) -> bool:
    """Whether `condition` refers to its own source (CR 700.7, 201.5, 201.5c) -
    "this creature"/"this permanent" and friends, or the source's own name in
    any of the shortened forms `machines/abilities.self_reference_names`
    reads: the short form before a comma ("Whenever Ragavan deals..."), and -
    only for a legendary source (`legendary`, default `True` for a caller
    with no supertype to check) - a no-comma legend's own epithet short form
    (Kiora of Fire and Ashes' own "When Kiora enters" - CR 201.5's short name
    of a no-comma "of" legend, not read as self before this) and a bare
    two-word name's own short form (Ajani Resolute's own "Ajani") - see
    `self_reference_names`'s own docstring for why those two shapes are a
    legendary-only convention.

    Reads through `self_reference_pattern`'s shared, word-bounded,
    longer-name-guarded regex rather than a plain substring test, so a
    shortened candidate that happens to be the start of a *different*,
    longer capitalized name mentioned in the same condition is never
    mistaken for this source naming itself.
    """
    lowered = condition.lower()
    if has_self_reference_type_word(lowered):
        return True
    # Case-sensitive, like `self_normalized_effect_text`'s own substitution:
    # Oracle templating always spells a card's own name (and its shortened
    # forms) with the same capitalization it prints on the card, which is
    # also what `_LONGER_NAME_CONTINUATION_LOOKAHEAD`'s capital-letter check
    # needs to tell a genuine continuation apart from an ordinary lowercase
    # word - folding the whole search case-insensitive would blind that
    # lookahead to the difference.
    return any(
        name in condition and self_reference_re(name).search(condition) is not None
        for name in self_reference_names(source_name, legendary=legendary)
    )


def _plural_type_word_pattern(word: str) -> str:
    """`word`'s own singular-or-plural regex fragment (CR 205.2a's card
    types, pluralized the ordinary English way Scryfall's own oracle text
    already uses: "creature" -> "creatures", "sorcery" -> "sorceries").

    Gardenize's and Scavenger's Talent's own "Whenever a/one or more
    creature**s** you control di**e**" both name the type in the plural -
    `\bcreature\b`'s trailing word boundary refuses to match inside
    "creatures" at all (the 's' is a word character, not a boundary), so a
    condition naming a type only in its plural form was read as naming no
    type, which `_types_match` then reads as "no restriction" rather than
    "the source doesn't have to be a creature to match" - the wrong kind of
    permissive for a noncreature source to widen past CR 603.10a's
    "another"/"other" requirement on. `-y` words (only "sorcery" in this
    pool's `_TYPE_WORDS`) pluralize by swapping the 'y' for '-ies', same as
    English; everything else just takes a trailing 's'.
    """
    if word.endswith("y"):
        return f"{word[:-1]}(?:y|ies)"
    return f"{word}s?"


def _required_types(condition: str) -> tuple[set[Type], set[Type]]:
    """The types a condition asks the subject to have, and the ones it forbids.

    `"an instant or sorcery spell"` requires one of instant or sorcery;
    `"a noncreature spell"` forbids creature. A condition naming no type at all
    requires nothing, which is what "whenever you cast a spell" means. Reads
    either the singular or the plural form of each type word (`_plural_type_
    word_pattern`) - "one or more creatures die" is exactly as much a
    creature-type restriction as "a creature dies" is.
    """
    lowered = condition.lower()
    forbidden = {
        card_type
        for word, card_type in _TYPE_WORDS.items()
        if re.search(rf"\bnon-?{_plural_type_word_pattern(word)}\b", lowered)
    }
    required = {
        card_type
        for word, card_type in _TYPE_WORDS.items()
        if card_type not in forbidden
        and re.search(rf"\b{_plural_type_word_pattern(word)}\b", lowered)
    }
    return required, forbidden


def _types_match(types: tuple[Type, ...] | None, condition: str) -> bool:
    """Whether `types` satisfies a condition's type words (CR 712.8f).

    Takes the subject's *actual* types - `GameEvent.subject_types`, up-face
    aware - rather than a raw `Card`, whose `.types` reads the front face only
    (CR 712.8a) and is wrong for an MDFC on the battlefield for its back face.
    """
    required, forbidden = _required_types(condition)
    if types is None:
        return not required and not forbidden
    type_set = set(types)
    if forbidden & type_set:
        return False
    return not required or bool(required & type_set)


#: "one or more other Cats you control die" names a creature *subtype*
#: (CR 205.3m), not one of `_TYPE_WORDS`'s card types. Captured non-greedily
#: so "Cats" yields "Cat" rather than swallowing the trailing "s".
_OTHER_SUBTYPE = re.compile(r"\bother ([A-Za-z]+?)s?\s+you control\b", re.IGNORECASE)


def _parse_subtype_list(text: str) -> tuple[str, ...] | None:
    """ "Goblin, Orc, or Army" (CR 205.3m) - a comma/or-separated list of
    capitalized subtype words, or a single one, as `_DYING_SUBTYPE`'s own
    `subtype` group (or a future widened sibling) captures it whole. `None`
    if any item is not a bare capitalized word (a lowercase qualifier or a
    multi-word phrase among them is not a shape this reads).

    The Great Goblin's own condition prints every item already singular
    ("Goblin, Orc, or Army"), so no plural-stripping is attempted here the
    way `_required_dying_subtype`'s own single-subtype callers already do for
    their own subject - a future printing with a plural item in a list is
    left unread rather than guessed at.
    """
    text = text.strip()
    if not text:
        return None
    if "," in text:
        parts = [part.strip() for part in text.split(",")]
        parts = [part for part in parts if part]
        if parts:
            parts[-1] = re.sub(r"^or\s+", "", parts[-1], flags=re.IGNORECASE).strip()
    else:
        parts = [part.strip() for part in re.split(r"\s+or\s+", text, flags=re.IGNORECASE)]
    words: list[str] = []
    for word in parts:
        if not re.fullmatch(r"[A-Z][A-Za-z]*", word):
            return None
        words.append(word)
    return tuple(words) if words else None


#: "that targets only a single creature [you control | other than
#: `<self-reference>`]" - Frontline Heroism's own "you control" and Ivy,
#: Gleeful Spellthief's own "other than Ivy" are the identical CR 601.2c
#: target-count restriction (CR 115.3's exactly-one) with two different
#: qualifiers on *which* single creature counts, read by one template rather
#: than a card-specific reader for each - see `condition_matches`'s
#: `CAST_SPELL` branch for why either has to be stripped before `_types_match`
#: sees it. The "you control" half needs no card name and stays a fixed
#: module-level pattern; the "other than" half is built per-source
#: (`_targets_only_single_creature_other_than_re`), the same reason
#: `_self_referential` cannot be a fixed pattern either - it has to recognise
#: *this* card's own self-reference forms (`self_reference_names`), never a
#: hardcoded name.
_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE = re.compile(
    r"that targets only a single creature you control", re.IGNORECASE
)


def _targets_only_single_creature_other_than_re(
    source_name: str, *, legendary: bool = True
) -> re.Pattern[str]:
    """ "that targets only a single creature other than `<self-reference>`" -
    Ivy, Gleeful Spellthief's own shape, built for `source_name`'s own
    self-reference forms rather than a literal name: the mechanic is "other
    than itself", never "other than Ivy" as a hardcoded string, so a
    differently-named card printing the identical template is read the same
    way.
    """
    alternatives = "|".join(
        self_reference_pattern(name)
        for name in self_reference_names(source_name, legendary=legendary)
    )
    return re.compile(
        rf"that targets only a single creature other than\s+(?:{alternatives})",
        re.IGNORECASE,
    )


#: Danitha, Spear of Agony's own "a spell that targets an opponent or a
#: creature an opponent controls" and Danitha, Sword of Hope's own "a spell
#: that targets a creature you control" (CR 601.2c) - a general "that
#: targets `<restriction>`" tail on a CAST_SPELL condition, read *after*
#: `_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE` has already taken Frontline
#: Heroism's own narrower "that targets only a single creature you control"
#: out of the text, so the two clauses can never both match the same
#: condition - Frontline Heroism's own count-and-controller reading of its
#: target (CR 115.3) stays exactly as it was; this is the general shape for
#: every other restriction a "spell that targets ..." condition can name.
#: "during an opponent's turn" on a cast trigger (Voracious Tome-Skimmer).
_DURING_AN_OPPONENTS_TURN_RE = re.compile(r"\s*during an opponent'?s turn", re.IGNORECASE)
#: "... spell with a single target" on a cast trigger (Spinerock Tyrant),
#: CR 115.9a.
_WITH_A_SINGLE_TARGET_RE = re.compile(r"\s*with a single target\b", re.IGNORECASE)
_SPELL_THAT_TARGETS_RE = re.compile(r"\bthat targets (?P<target>.+)$", re.IGNORECASE)
_MODIFIED_TARGET_RE = re.compile(
    r"modified (?P<noun>permanent|creature)(?: (?P<who>you control|an opponent controls))?",
    re.IGNORECASE,
)

#: Geometer's Arthropod's and Matterbending Mage's own "a spell with {X} in
#: its mana cost" (CR 107.3's X, CR 202.1's mana cost as printed symbols).
#: The restriction is about the cast spell's own *printed* mana cost - which
#: symbols it names at all, not the mana value or colour those symbols pay
#: for - so it is read off `CardState.mana_cost` directly rather than through
#: `_types_match`/`_color_matches`, which know nothing about mana symbols.
#: One template, keyed by whichever symbol the card prints, not a hardcoded
#: "{X}": a future card restricting on some other symbol in this same
#: position reads for free.
_CAST_SPELL_MANA_COST_SYMBOL_RE = re.compile(
    r"with \{(?P<symbol>[a-z0-9/]+)\} in its mana cost", re.IGNORECASE
)

#: Where a CAST_SPELL condition names more than one kind of qualifying spell
#: (Danitha, Sword of Hope's own "an Equipment spell or a spell that targets
#: a creature you control") splits: an " or " immediately followed by
#: another complete "[a/an] ... spell" or "a spell that targets ..." clause,
#: never an " or " sitting *inside* one description's own noun list (a
#: colour list, a target restriction's own "an opponent or a creature an
#: opponent controls") - the lookahead only fires when a fresh clause
#: actually starts at that exact position, which a bare colour or noun
#: alternative never does.
_CAST_CLAUSE_BOUNDARY = re.compile(r"\s+or\s+(?=an?\s+.*?\bspell\b)", re.IGNORECASE)

#: The shared lead-in every CAST_SPELL condition in this pool begins with
#: (CR 601.2) - `_cast_spell_alternatives` re-prefixes it onto every
#: alternative clause it splits off, so `_controller_clause_holds` still
#: sees who has to have done the casting in each one.
_CAST_LEAD = re.compile(r"^(?P<lead>(?:you|an opponent) casts?)\s+", re.IGNORECASE)


def _cast_spell_alternatives(condition: str) -> list[str]:
    """`condition` split into its alternative spell-description clauses when
    it names more than one kind of qualifying spell, each carrying its own
    copy of the shared "you cast"/"an opponent casts" lead-in - or `[condition]`
    unchanged, its own one and only alternative, when there is no such split
    (every CAST_SPELL condition in the pool but Danitha, Sword of Hope's)."""
    lead_match = _CAST_LEAD.match(condition)
    if lead_match is None:
        return [condition]
    lead, body = lead_match.group("lead"), condition[lead_match.end() :]
    parts = [part.strip() for part in _CAST_CLAUSE_BOUNDARY.split(body) if part.strip()]
    if len(parts) < 2:
        return [condition]
    return [f"{lead} {part}" for part in parts]


#: A leading "a"/"an" - at the very start of the restriction, or right after
#: an "or" that opens a fresh item of a noun list (Danitha, Spear of Agony's
#: own "an opponent or **a** creature an opponent controls") - is stripped
#: everywhere it introduces a noun, not only the first: `machines/targeting.
#: _read_phrase`'s own grammar reads a "target ..." phrase, or one item of
#: its own noun list, with no article at all (CR 601.2c's own templating
#: never prints one), and a lone leading strip used to leave the *second*
#: item's own article behind, which that grammar could not read either.
_LEADING_ARTICLE = re.compile(r"(^|\bor\s+)(?:a|an)\s+", re.IGNORECASE)


def _strip_leading_article(text: str) -> str:
    """`text` with every list-item-introducing "a"/"an" removed - see
    `_LEADING_ARTICLE`."""
    return _LEADING_ARTICLE.sub(r"\1", text.strip())


_THIS_OBJECT_RE = re.compile(
    r"this (?:creature|permanent|artifact|enchantment|land|planeswalker)", re.IGNORECASE
)


def _cast_spell_targets_condition_holds(
    game: "Game", target_text: str, controller: str, event: GameEvent, source: CardState
) -> bool | None:
    """Whether a CAST_SPELL condition's own "... that targets
    `<restriction>`" clause (CR 601.2c) is satisfied by the spell `event`
    names - true when at least one of the spell's own announced targets fits
    the restriction. `None` when the restriction cannot be read at all, so
    the caller can record a `CastConditionNotice` the same way an unreadable
    mana-value comparison already does, rather than silently treat an
    unreadable restriction as satisfied.

    Reuses `machines/targeting._read_phrase` - the identical grammar a
    "target `<description>`" phrase on the spell itself is read with - so a
    restriction here and an ordinary targeting requirement can never disagree
    about what "a creature you control" means. Imported at call time: `.
    targeting` imports `.combat`, which imports this module for `GameEvent`,
    so the two cannot import each other at module scope.

    A restriction naming this ability's own source by name - Speedball, New
    Warrior's own "a player casts a spell that targets Speedball" - is CR
    201.5/201.5c self-reference, not one of `_read_phrase`'s target
    *descriptions* (a type, a controller, a keyword): "Speedball" is a
    proper name `_read_phrase`'s noun-phrase grammar has no way to read, the
    same reason `self_reference_names`/`_self_referential` exist for every
    other self-referential sentence in this module. Checked first, before
    `_read_phrase` ever sees the text, so a self-naming restriction is a
    literal identity check against `source.id` rather than an unreadable
    phrase that falls to `None` and a spurious `CastConditionNotice`.
    """
    from ..abilities import self_reference_names
    from ..targeting import _read_phrase

    # Storm, Windrider's "a spell that targets one or more creatures": any
    # one of the spell's targets fitting is enough, the same test as "a
    # creature".
    target_text = re.sub(r"^one or more\s+", "", target_text.strip(), flags=re.IGNORECASE)
    stripped = _strip_leading_article(target_text).strip()
    # Heroic's own "a spell that targets this creature" (Favored Hoplite) -
    # CR 201.5's "this creature" is the same self-reference as the name.
    if stripped in self_reference_names(
        source.name, legendary=_is_legendary_source(source)
    ) or _THIS_OBJECT_RE.fullmatch(stripped):
        if event.subject_id is None:
            return False
        spell = game.find_by_id(event.subject_id)
        if spell is None:
            return False
        return any(
            not target_ref.is_player and target_ref.card_id == source.id
            for target_ref in spell.targets
        )

    modified = _MODIFIED_TARGET_RE.fullmatch(stripped)
    if modified is not None:
        # Pearl-Ear, Imperial Advisor's "an Aura spell that targets a modified
        # permanent you control" (CR 700.9: a counter, an Equipment, or an Aura
        # its controller controls). Read off the computed board (CR 613.5).
        from ..conditions.board import permanent_is_modified

        spell = game.find_by_id(event.subject_id) if event.subject_id is not None else None
        if spell is None:
            return False
        board = game.computed_board()
        for target_ref in spell.targets:
            if target_ref.is_player:
                continue
            found = game.find_by_id(target_ref.card_id)
            if found is None or found.zone is not Zone.BATTLEFIELD:
                continue
            chars = board.of(found)
            who = (modified.group("who") or "").lower()
            if who == "you control" and chars.controller != controller:
                continue
            if who == "an opponent controls" and chars.controller in (None, controller):
                continue
            if modified.group("noun") == "creature" and Type.CREATURE not in chars.types:
                continue
            if permanent_is_modified(game, found, chars):
                return True
        return False

    requirement = _read_phrase("", stripped, strict=True)
    if requirement is None:
        return None
    if event.subject_id is None:
        return False
    spell = game.find_by_id(event.subject_id)
    if spell is None:
        return False
    for target_ref in spell.targets:
        candidate: Any
        if target_ref.is_player:
            candidate = target_ref.username
        else:
            found = game.find_by_id(target_ref.card_id)
            if found is None:
                continue
            candidate = found
        if requirement.rejects(candidate, controller, game, source_id=spell.id) is None:
            return True
    return False


def _required_subtype(condition: str) -> tuple[str, ...] | None:
    match = _OTHER_SUBTYPE.search(condition)
    if match is not None:
        return (match.group(1),)
    return _required_dying_subtype(condition)


#: A subtype named as a DIES condition's own plain subject (CR 205.3m,
#: CR 712.8f), outside the "other `<X>`s you control" shape `_OTHER_SUBTYPE`
#: already reads - Ygra, Eater of All's own "a Food is put into a graveyard
#: from the battlefield" (CR 700.4's own wording for "dies"). The same
#: capitalization discriminator `_ENTERING_SUBTYPE` already relies on: Oracle
#: templating capitalizes a subtype and never a card-type word, so "a
#: creature dies" (no subtype at all) and "a nontoken creature you control
#: dies" (Lightning Coils - "nontoken" is lowercase and "creature" is a card
#: type, not a subtype) never match this.
#: The Great Goblin's own "another Goblin, Orc, or Army you control dies" -
#: `_DYING_SUBTYPE`'s single-subtype subject widened to a comma/or list, read
#: by `_parse_subtype_list`. Every single-subtype printing this pool already
#: has (Lightning Coils' "a nontoken creature", Archangel Avacyn's own
#: non-Angel qualifier read separately by `_excluded_subtype_absent`) still
#: matches: a lone word is a list of one.
#: Magda, Brazen Outlaw's own "Whenever a Dwarf you control becomes tapped,
#: ..." - the identical subtype-subject shape `_DYING_SUBTYPE` reads for a
#: DIES condition, read here for BECOMES_TAPPED's own verb ending instead
#: (CR 701.26a).
_BECOMES_TAPPED_SUBTYPE = re.compile(
    r"^(?:an?|another|one or more) (?:nontoken )?"
    r"(?P<subtype>[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,?\s+or\s+[A-Z][A-Za-z]*)?)"
    r" you control becomes tapped\b"
)


def _required_becomes_tapped_subtype(condition: str) -> tuple[str, ...] | None:
    """The subtype(s) `_BECOMES_TAPPED_SUBTYPE` names, or `None` - the
    BECOMES_TAPPED twin of `_required_dying_subtype`, read the same
    `_parse_subtype_list` way for a comma/or list."""
    match = _BECOMES_TAPPED_SUBTYPE.match(condition)
    if match is None:
        return None
    return _parse_subtype_list(match.group("subtype"))


#: "a `<Subtype>` you control deals [combat] damage" (Greatbow Doyen's own
#: "Whenever an Archer you control deals damage to a creature") -
#: `_ATTACKS_SUBTYPE`'s bare-subtype-subject shape for the dealer of a
#: DEALS_DAMAGE event (CR 120.1: the object that deals damage is its source).
_DEALS_DAMAGE_SUBTYPE = re.compile(
    r"^(?:an?|another|one or more) (?:nontoken )?"
    r"(?P<subtype>[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,?\s+or\s+[A-Z][A-Za-z]*)?)"
    r"(?: (?:artifact|creature|enchantment|land|planeswalker|permanent)s?)?"
    r"(?: you control| an opponent controls)?"
    r" deals? (?:combat |noncombat )?damage\b"
)
#: "... deals [combat] damage to a creature" - the recipient must be a
#: creature (CR 120.3e's damage to a creature, `GameEvent.target_types`).
_DEALS_DAMAGE_TO_A_CREATURE = re.compile(
    r"\bdeals? (?:combat |noncombat )?damage to an? creature\b"
)


def _required_dealing_subtype(condition: str) -> tuple[str, ...] | None:
    """The subtype(s) `_DEALS_DAMAGE_SUBTYPE` names, or `None`."""
    match = _DEALS_DAMAGE_SUBTYPE.match(condition)
    if match is None:
        return None
    return _parse_subtype_list(match.group("subtype"))


#: "a `<Subtype>` you control attacks" (Defiant Thundermaw's own back face's
#: "Whenever a Dragon you control attacks, it deals 2 damage to any
#: target.") - `_BECOMES_TAPPED_SUBTYPE`'s own bare-subtype-subject shape
#: reused for the ATTACKS event's verb instead (CR 508.1, 508.3d).
_ATTACKS_SUBTYPE = re.compile(
    r"^(?:an?|another|one or more) (?:nontoken )?"
    r"(?P<subtype>[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,?\s+or\s+[A-Z][A-Za-z]*)?)"
    r"(?: (?:artifact|creature|enchantment|land|planeswalker|permanent)s?)?"
    r"(?: you control| an opponent controls)?"
    r" attacks?\b"
)


def _required_attacking_subtype(condition: str) -> tuple[str, ...] | None:
    """The subtype(s) `_ATTACKS_SUBTYPE` names, or `None` - the ATTACKS twin
    of `_required_becomes_tapped_subtype`, read the same `_parse_subtype_
    list` way for a comma/or list."""
    match = _ATTACKS_SUBTYPE.match(condition)
    if match is None:
        return None
    return _parse_subtype_list(match.group("subtype"))


#: An optional card-type word may follow the subtype - Boggart Mischief's "a
#: Goblin creature you control dies" (CR 205.3m's subtype, then CR 205.2a's
#: card type, which `_types_match` checks separately).
_DYING_SUBTYPE = re.compile(
    r"^(?:an?|another|one or more) (?:nontoken )?"
    r"(?P<subtype>[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*(?:,?\s+or\s+[A-Z][A-Za-z]*)?)"
    r"(?: (?:artifact|creature|enchantment|land|planeswalker|permanent)s?)?"
    r"(?: you control| an opponent controls)?"
    r" (?:dies\b|die\b|is put into a graveyard from the battlefield\b|"
    r"are put into a graveyard from the battlefield\b)"
)


def _required_dying_subtype(condition: str) -> tuple[str, ...] | None:
    """The subtype(s) `_DYING_SUBTYPE` names, or `None` - `_required_entering_
    subtype`'s own reading, mirrored for a DIES condition's subject rather
    than an ENTERS_THE_BATTLEFIELD one, and widened to a list the way that
    one's own single subject does not need to be (no pool printing yet lists
    more than one entering subtype).

    Each word is singularised the same way the single-subtype shape always
    was - a trailing "s" dropped, except for CR 305.6's basic land types
    ("Plains" keeps its own plural spelling) - applied per list item so
    "Goblin, Orc, or Army" and a future plural list both read the same way.
    """
    match = _DYING_SUBTYPE.match(condition.strip())
    if match is None:
        return None
    words = _parse_subtype_list(match.group("subtype"))
    if words is None:
        return None
    from ..layers import BASIC_LAND_TYPES

    return tuple(
        word
        if word in BASIC_LAND_TYPES
        else word[:-1]
        if word.endswith("s") and len(word) > 1
        else word
        for word in words
    )


#: "a Mountain you control enters" (Valakut, the Molten Pinnacle) - a *subtype*
#: named on an entry condition (CR 205.3i's land types here, but the shape is
#: subtype-generic). Capitalization is the discriminator, the same one
#: `_CAST_SUBTYPE`'s own comment relies on: Oracle templating always
#: capitalizes a subtype, and never capitalizes the card-type and colour words
#: `_types_match`/`_color_matches` already read, so "a creature you control
#: enters" and "a nonland permanent enters" cannot match this. Anchored at the
#: start so it reads the condition's *subject*, not a qualifier buried later
#: in the sentence.
#:
#: `another` sits alongside `a`/`an`/`one or more` - Miirym, Sentinel Wyrm's
#: own "another nontoken Dragon you control enters" (CR 205.3a's subtype) -
#: rather than in a second regex, because it is still the condition's subject,
#: read the identical way; self-exclusion for "another" is a separate general
#: rule `condition_matches` already applies to every ENTERS_THE_BATTLEFIELD
#: condition, not something this regex has to encode. An optional "nontoken"
#: (lowercase, so it can never itself be mistaken for the capitalized
#: subtype word right after it - Miirym's own reason to exist) sits between
#: the lead-in and the subtype for the identical reason: Miirym's subject is
#: not "a Dragon" but "another **nontoken** Dragon", and without skipping it
#: the capture would land on "nontoken" itself and fail the `[A-Z]` class.
_ENTERING_SUBTYPE = re.compile(
    r"^(?:an?|one or more|another) (?:nontoken )?(?P<subtype>[A-Z][A-Za-z]*?)(?P<plural_s>s?) "
    r"(?:you control |an opponent controls )?enters?\b"
)


#: "you tap a Swamp for mana" (Nirkana Revenant), "a Forest is tapped for mana"
#: (Vernal Bloom) - a subtype named as the tapped permanent (CR 205.3i's land
#: types). Capitalization tells it from the lowercase card-type words
#: `_types_match` reads ("a creature", "a land"), as `_ENTERING_SUBTYPE` does.
_TAPPED_SUBTYPE = re.compile(
    r"(?:\btaps? an? |^an? )(?P<subtype>[A-Z][A-Za-z]*) (?:for mana|is tapped for mana)"
)


def _required_tapped_subtype(condition: str) -> str | None:
    """The subtype a tapped-for-mana condition names, or `None`."""
    match = _TAPPED_SUBTYPE.search(condition)
    return match.group("subtype") if match else None


#: "another Elf or Faerie you control enters" (Maralen, Fae Ascendant's other
#: half once `_self_or_other_enters_match` has split the self off) - the
#: single-subtype `_ENTERING_SUBTYPE` widened to a comma/or list of singular
#: subtypes, read by `_parse_subtype_list` the way The Great Goblin's own
#: dying list is; any one of them is enough (CR 205.3m).
_ENTERING_SUBTYPE_LIST = re.compile(
    r"^(?:an?|one or more|another) (?:nontoken )?"
    r"(?P<subtypes>[A-Z][A-Za-z]*(?:,\s*[A-Z][A-Za-z]*)*,?\s+or\s+[A-Z][A-Za-z]*) "
    r"(?:you control |an opponent controls )?enters?\b"
)


def _required_entering_subtype(condition: str) -> str | tuple[str, ...] | None:
    """The subtype an ENTERS_THE_BATTLEFIELD condition demands, or `None`.

    Split from `_required_subtype` because that one reads only the "other ...
    you control" shape CR 603.10a's death triggers print, which never matches
    an entry condition's plain "a Mountain you control enters".

    `_ENTERING_SUBTYPE`'s own optional trailing `s?` is there to turn a
    plural subject - "one or more Cats you control enter" - back into the
    singular subtype name `_subtype_matches` compares against. CR 305.5's
    "Plains" is the one basic land type this stripping corrupts: it is
    spelled with a trailing s in both its singular and plural form, so
    Koth of the Homestead's own singular "a Plains you control enters"
    used to have its captured subtype trimmed to "Plain" - a name the game
    has never printed - and its own trigger could never match a real Plains
    entering. `BASIC_LAND_TYPES` (CR 305.6) is what tells "Plains" apart
    from an ordinary pluralizable subtype rather than a hardcoded name.
    """
    listed = _ENTERING_SUBTYPE_LIST.match(condition.strip())
    if listed is not None:
        return _parse_subtype_list(listed.group("subtypes"))
    match = _ENTERING_SUBTYPE.match(condition.strip())
    if match is None:
        return None
    subtype, plural_s = match.group("subtype"), match.group("plural_s")
    whole = subtype + plural_s
    # Imported here, not at module scope: `machines/combat.py` imports this
    # module for `GameEvent`, and `machines/layers.py` (where
    # `BASIC_LAND_TYPES` lives) imports `machines/combat.py` in turn - the
    # same real, call-time-only cycle `triggered_abilities_of` already routes
    # its own `from .keywords import keyword_triggered_abilities` around.
    from ..layers import BASIC_LAND_TYPES

    return whole if whole in BASIC_LAND_TYPES else subtype


#: "a non-Angel creature you control dies" (Archangel Avacyn) - CR 205.3's
#: subtype, negated by a hyphenated "non-" (the capital is Oracle's own
#: subtype capitalisation, so "nontoken"/"noncreature" never match).
_NON_SUBTYPE_WORD = re.compile(r"\bnon-(?P<subtype>[A-Z][A-Za-z]*)\b")


def _excluded_subtype_absent(subtypes: tuple[str, ...] | None, condition: str) -> bool:
    """Whether the subject lacks every subtype a "non-`<Subtype>`" word in
    `condition` excludes (CR 205.3), read off the event's up-face-aware
    `subject_subtypes` the way `_subtype_matches` reads the required one."""
    excluded = {match.group("subtype").lower() for match in _NON_SUBTYPE_WORD.finditer(condition)}
    if not excluded:
        return True
    return not any(word.lower() in excluded for word in subtypes or ())


def _subtype_matches(
    subtypes: tuple[str, ...] | None, subtype: str | tuple[str, ...] | None
) -> bool:
    """Whether `subtypes` names `subtype` (CR 712.8f), or *any* of them when
    `subtype` is a list (The Great Goblin's own "Goblin, Orc, or Army" -
    CR 205.3m names each a distinct subtype, and the condition is an "or", not
    an "and", of the three). See `_types_match`'s docstring for why this
    reads `GameEvent.subject_subtypes`, not a raw `Card`."""
    if subtype is None:
        return True
    if subtypes is None:
        return False
    wanted = (subtype,) if isinstance(subtype, str) else subtype
    lowered = {word.lower() for word in subtypes}
    return any(word.lower() in lowered for word in wanted)


#: Tetsuko Umezawa, Pursuer's own "with power or toughness 1 or less" -
#: which characteristic is not fixed to the pool's one printing (a
#: differently worded card could as easily say "power 4 or greater" or
#: "toughness 3 or less").
_POWER_OR_TOUGHNESS_QUALIFIER = re.compile(
    rf"\bwith (?P<stat>power|toughness|power or toughness) "
    rf"(?P<count>{COUNT}) or (?P<direction>less|greater|more)\b"
)


def _power_or_toughness_qualifier_holds(
    game: "Game", condition: str, subject_id: "UUID | None"
) -> bool | None:
    """Whether a trigger condition's "with power [or toughness] N or
    less/greater" qualifier (CR 208.1) is true of `subject_id` right now, or
    `None` when the condition carries no such qualifier at all - which
    `condition_matches`'s BLOCKS branch reads as "nothing to check", not as a
    refusal.

    Read off the live, computed board (CR 613.5) rather than anything the
    event snapshot carries: power and toughness are exactly the
    characteristics a static ability can still be changing the moment this
    is asked, and `GameEvent` was never meant to snapshot every one of a
    permanent's numbers."""
    match = _POWER_OR_TOUGHNESS_QUALIFIER.search(condition.lower())
    if match is None:
        return None
    if subject_id is None:
        return False
    subject = game.find_by_id(subject_id)
    if subject is None:
        return False
    threshold = parse_count(match.group("count"), article=False)
    if threshold is None:
        return None
    chars = game.characteristics_of(subject) if subject.zone is Zone.BATTLEFIELD else None
    power = chars.power if chars is not None else subject.power
    toughness = chars.toughness if chars is not None else subject.toughness
    values = [value for value in (power, toughness) if value is not None]
    if match.group("stat") == "power":
        values = [power] if power is not None else []
    elif match.group("stat") == "toughness":
        values = [toughness] if toughness is not None else []
    if not values:
        return False
    compare = operator.le if match.group("direction") == "less" else operator.ge
    return any(compare(value, threshold) for value in values)


def _counter_kind_word(word: str) -> Counter | str:
    """Normalise a printed counter-kind word the identical way `machines/
    effects._counter_kind` does - the two CR 122.1a power/toughness spellings
    as `Counter.PLUS_ONE`/`Counter.MINUS_ONE`, any other named `Counter`
    member by its own value, and a plain lower-cased string for CR 122.1's
    open set otherwise. Kept as its own small copy rather than imported:
    `machines/effects.py` imports this module for `GameEvent`/`condition_
    matches`, so an import the other way would close the cycle.
    """
    lowered = word.lower()
    if lowered == "+1/+1":
        return Counter.PLUS_ONE
    if lowered == "-1/-1":
        return Counter.MINUS_ONE
    try:
        return Counter(lowered)
    except ValueError:
        return lowered


#: "a creature you control with a +1/+1 counter on it leaves the battlefield"
#: (The Ooze) - CR 122.1's "with a `<kind>` counter on it" qualifier on a
#: LEAVES_THE_BATTLEFIELD condition's own subject, the identical shape CR
#: 603.6d's `_ENTERS_WITH_COUNTER_RE` already reads for an *entering*
#: permanent, mirrored here for a *leaving* one.
#: The kind is optional: Shadow Urchin's "a creature you control with one or
#: more counters on it dies" names no kind (CR 122.1's counters of any kind).
_LEAVES_WITH_COUNTER_QUALIFIER_RE = re.compile(
    r"\bwith (?:a|an|one or more|\d+) (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on it\b"
)


def _leaves_battlefield_counter_qualifier_holds(
    game: "Game", condition: str, subject_id: "UUID | None"
) -> bool | None:
    """Whether a LEAVES_THE_BATTLEFIELD condition's "with a `<kind>` counter
    on it" qualifier holds for `subject_id`, or `None` when the condition
    names no such qualifier at all - the same "nothing to check" reading
    `_power_or_toughness_qualifier_holds` gives its own callers.

    Read off `last_known_counters` (CR 603.10a's look-back, CR 704.8) rather
    than the live `.counters`: CR 122.2 empties a permanent's counters the
    instant it leaves the battlefield, the same "gone by the time anyone
    asks" moment `_COUNTER_ON_IT_RE`'s own ternary in `machines/effects.py`
    already reads around for a dies trigger's own "for each ... counter on
    it".
    """
    match = _LEAVES_WITH_COUNTER_QUALIFIER_RE.search(condition.lower())
    if match is None:
        return None
    if subject_id is None:
        return False
    subject = game.find_by_id(subject_id)
    if subject is None:
        return False
    counters = subject.counters if subject.zone is Zone.BATTLEFIELD else subject.last_known_counters
    if match.group("kind") is None:
        return any(amount > 0 for amount in counters.counts.values())
    kind = _counter_kind_word(match.group("kind"))
    return bool(counters[kind])


#: Flanking's own qualifier (CR 702.25a): "becomes blocked by a creature
#: without `<keyword>`". Not fixed to "flanking" - a differently worded card
#: could as easily name any other keyword here, the same reasoning
#: `_POWER_OR_TOUGHNESS_QUALIFIER` above already gives for staying generic
#: rather than hardcoding the one word the pool happens to print.
_BECOMES_BLOCKED_BY_WITHOUT_KEYWORD = re.compile(
    r"\bbecomes blocked by a creature without (?P<keyword>[a-z][a-z '-]*?)\s*$"
)


def _equipped_blocks_or_is_blocked_once(
    game: "Game", event: GameEvent, creature_id: UUID | None
) -> bool:
    """ "Whenever equipped creature blocks or becomes blocked by one or more
    creatures" (CR 509.3a, 509.3c, 509.3e): the equipped creature blocks, or is
    blocked, and the ability triggers once each combat for it however many
    creatures that involves - so only the first blocking pair
    `Game.declare_blockers` emits for the creature counts. That pair is the
    first of the blocker's attackers in attack order when the creature blocks,
    and the creature's first blocker (`Attack.blocked_by[0]`) when it is
    blocked."""
    if event.subject_id == creature_id:
        blocked = [a for a in game.combat.attacks if creature_id in a.blocked_by]
        return not blocked or blocked[0].attacker_id == event.related_id
    if event.related_id == creature_id:
        attack = game.combat.attack_by(creature_id)
        return attack is None or not attack.blocked_by or attack.blocked_by[0] == event.subject_id
    return False


def _becomes_blocked_by_qualifier_holds(
    game: "Game", condition: str, blocker_id: "UUID | None"
) -> bool | None:
    """Whether a "becomes blocked by a creature without `<keyword>`" qualifier
    (Flanking, CR 702.25a) is true of the blocker `blocker_id` names, or
    `None` when the condition carries no such qualifier at all - the same
    "nothing to check" reading `_power_or_toughness_qualifier_holds` gives
    `condition_matches`'s BLOCKS branch for its own qualifier.

    CR 509.3f: a "becomes blocked by a creature with certain characteristics"
    condition is checked "at the point it becomes a blocking creature" - this
    is read the moment the `BLOCKS` event itself is matched, off the live
    board (CR 613.5), so there is no later moment for the check to have
    drifted from.
    """
    match = _BECOMES_BLOCKED_BY_WITHOUT_KEYWORD.search(condition.lower())
    if match is None:
        return None
    if blocker_id is None:
        return False
    blocker = game.find_by_id(blocker_id)
    if not isinstance(blocker, CardState):
        return False

    from ..combat import has_keyword

    return not has_keyword(blocker, match.group("keyword").strip(), game)


#: "a Dragon spell", "the first Otter spell" - a subtype named on a "cast a
#: ... spell" condition (CR 205.3a). Templating always capitalizes a subtype
#: the way Scryfall's Oracle text does, which is what tells this apart from
#: the lowercase color and card-type words `_color_condition`/`_types_match`
#: already read - "a colorless spell" and "a noncreature spell" never match
#: here because "colorless" and "noncreature" are not capitalized.
_CAST_SUBTYPE_WORD = re.compile(r"\b(?:a|an)\s+([A-Z][a-z]+)\s+spell\b")


def _required_cast_subtype(condition: str) -> str | None:
    match = _CAST_SUBTYPE_WORD.search(condition)
    return match.group(1) if match else None


#: Cori-Steel Cutter's own *Flurry* shape: "you cast your second spell each
#: turn" (the ability word itself, CR 207.2c, carries no rules meaning and is
#: stripped before this text is ever seen), and The Queen of Dale's own "an
#: opponent casts their first noncreature spell each turn" - the identical
#: ordinal read for whoever the trigger's own subject is rather than always
#: the ability's controller, with an optional type qualifier
#: (`_required_types` reads it back off the whole condition) between the
#: ordinal and "spell(s)". Unlike Alania, Divergent Storm's "it's the
#: first ... spell ... you've cast this turn" - an intervening *if* read by
#: `_first_spell_this_turn_holds`, rechecked at resolution (CR 603.4,
#: 608.2a) - this ordinal sits in the trigger condition itself (CR 603.2): the
#: ability triggers (or doesn't) once, at the moment of casting, and is never
#: revisited.
_ORDINAL_SPELL_EACH_TURN = re.compile(
    r"(?:your|their) (?P<ordinal>[a-z]+) (?:[a-z]+ )?spells? each turn"
)


def _ordinal_spell_this_turn_matches(
    game: "Game", condition: str, controller: str, event: GameEvent
) -> bool | None:
    """Whether `event`'s spell is exactly its own caster's Nth spell cast
    this turn (CR 603.2), for "you cast your [ordinal] spell each turn" /
    "an opponent casts their [ordinal] spell each turn". `None`, not False,
    when `condition` isn't this shape at all, so the caller can tell "read
    and false" from "not this pattern" the same way `_first_spell_this_turn_
    holds` already does for its own clause.

    Indexed by `event.player` - the spell's own caster - rather than always
    `controller`: for "your" that is already the same player (the earlier
    "an opponent"/`_controller_clause_holds` check has already refused any
    other caster by the time this runs), and for "their" it is whichever
    opponent actually cast the spell, not the ability's own controller.

    `game.spells_cast_this_turn` (`Game.put_on_stack`) already holds this very
    spell by the time the CAST_SPELL event reaches here - CR 601.2a's casting
    event has already happened - so its 1-indexed position in that per-turn,
    per-caster list *is* the ordinal this clause asks about, with no
    separate counter to maintain.

    The Queen of Dale's own "noncreature" is CR 712.8f's ordinary type word
    (`_required_types`, the same reader `_types_match` uses elsewhere in this
    module): when the condition names one, both the ordinal *and* the type
    have to match - the count is taken only over the caster's spells of that
    type this turn, and a spell of the wrong type never satisfies the clause
    at all, whatever position it fell in.
    """
    match = _ORDINAL_SPELL_EACH_TURN.search(condition.lower())
    if match is None:
        return None
    ordinal = parse_ordinal(match.group("ordinal"))
    if ordinal is None:
        return False
    if event.player is None:
        return False
    if not _types_match(event.subject_types, condition):
        return False
    required, forbidden = _required_types(condition)
    cast_this_turn = game.spells_cast_this_turn.get(event.player, [])
    if required or forbidden:
        cast_this_turn = [
            state
            for state in cast_this_turn
            if not (forbidden & set(state.types)) and (not required or required & set(state.types))
        ]
    position = next(
        (
            index
            for index, state in enumerate(cast_this_turn, start=1)
            if state.id == event.subject_id
        ),
        None,
    )
    return position == ordinal


#: CR 105.2's five colors, as the adjective a "cast a ... spell" condition
#: names them with.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


#: "exactly `<N>` colors" (Invasion of Ravnica // Guildpact Paragon's own
#: "Whenever you cast a spell that's exactly two colors") - CR 105.2's color
#: *count* spelled out with its own number, the identical restriction
#: "monocolored"/"multicolored" already name for exactly 1 or 2-or-more, just
#: never spelled this way before. `machines/effects._EXACTLY_N_COLORS_RE`
#: reads the identical phrase for a *card's* own quality (a search/reveal's
#: "a card that's exactly two colors"); this is the same words for a *cast
#: spell*'s own condition instead, kept as its own compiled pattern rather
#: than imported, the same way this module already keeps `_COLOR_WORDS`
#: separate from `machines/effects.py`'s own colour vocabulary.
_EXACTLY_N_COLORS_CONDITION_RE = re.compile(r"\bexactly (?P<n>\w+) colors?\b", re.IGNORECASE)


def _color_condition(condition: str) -> tuple[str, frozenset[Color]] | int | None:
    """The color restriction a "cast a ... spell" condition names, or `None`
    when it names none at all - which is what a plain "whenever you cast a
    spell" means.

    Reads CR 105.2's whole vocabulary for an object's color: "colorless"
    (CR 105.2c, 202.2b - no colored mana symbols), "monocolored" (CR 105.2a -
    exactly one color), "multicolored" (CR 105.2b - two or more), a spelled-
    out "exactly N colors" (an `int`, read before "colored" and "multi/mono"
    below so "exactly two colors" is never instead swallowed by a later,
    looser branch that would find no keyword at all in it and fall through
    to "no restriction"), and one or more of the five color adjectives named
    outright (Frontline Heroism's "red" is not this shape - it colors a
    token the effect creates, not the spell the condition restricts, so this
    is only ever consulted for the condition clause itself, never the effect
    that follows it).
    """
    lowered = condition.lower()
    exact = _EXACTLY_N_COLORS_CONDITION_RE.search(lowered)
    if exact is not None:
        n = parse_count(exact.group("n"))
        if n is not None:
            return n
    if re.search(r"\bcolorless\b", lowered):
        return "colorless", frozenset()
    if re.search(r"\bmonocolored\b", lowered):
        return "monocolored", frozenset()
    if re.search(r"\bmulticolored\b", lowered):
        return "multicolored", frozenset()
    named = frozenset(
        color for word, color in _COLOR_WORDS.items() if re.search(rf"\b{word}\b", lowered)
    )
    if named:
        return "named", named
    return None


def _color_matches(colors: tuple[Color, ...] | None, condition: str) -> bool:
    """Whether `colors` satisfies a "cast a ... spell" condition's color
    restriction, if it has one (CR 105.2). No restriction named matches
    anything, the same "nothing required" default `_types_match` uses.
    """
    requirement = _color_condition(condition)
    if requirement is None:
        return True
    color_set = set(colors or ())
    if isinstance(requirement, int):
        return len(color_set) == requirement
    kind, named = requirement
    if kind == "colorless":
        return not color_set
    if kind == "monocolored":
        return len(color_set) == 1
    if kind == "multicolored":
        return len(color_set) >= 2
    return bool(color_set & named)


#: The zone words a "cast a ... spell **from** [zone]" clause names -
#: Knowledge Pool's and Possibility Storm's "from their hand" (also "from
#: your hand", the singular-controller phrasing prowess-style keyword
#: expansions would use if one ever named a zone) and Appa, Steadfast
#: Guardian's "from exile" are the two shapes actually printed in the pool
#: (grepped across `tests/fixtures/cards/*.json` rather than guessed), but
#: the word list is zone-generic so a future graveyard- or library-scoped
#: cast trigger reads correctly with no further parser work. "Exile" takes no
#: possessive ("from exile", never "from your exile" - exile is a shared
#: zone, CR 400.1: "Each player has their own library, hand, and graveyard.
#: The other zones are shared by all players."), so it is matched on its own
#: rather than through the
#: `their|your|his or her` possessive `_CAST_ORIGIN_ZONE_RE` group the other
#: four zones share.
_CAST_ORIGIN_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "battlefield": Zone.BATTLEFIELD,
    "exile": Zone.EXILE,
}

_CAST_ORIGIN_ZONE_RE = re.compile(
    r"\bfrom (?:(?:their|your|his or her) (?P<possessive>hand|graveyard|library|battlefield)"
    r"|(?P<bare>exile))\b",
    re.IGNORECASE,
)


#: "from anywhere other than your hand" (Vega, the Watcher; Shadow of the
#: Goblin): every origin but the one zone named - the complement of the
#: `_CAST_ORIGIN_ZONE_RE` reading.
_CAST_ORIGIN_EXCLUDED_ZONE_RE = re.compile(
    r"\bfrom anywhere other than (?:their|your|his or her) "
    r"(?P<zone>hand|graveyard|library)\b",
    re.IGNORECASE,
)


def _excluded_cast_origin_zone(condition: str) -> Zone | None:
    """The one zone a "from anywhere other than [zone]" condition rules out,
    or `None` when it names no such exclusion."""
    match = _CAST_ORIGIN_EXCLUDED_ZONE_RE.search(condition)
    if match is None:
        return None
    return _CAST_ORIGIN_ZONE_WORDS[match.group("zone").lower()]


def _required_cast_origin_zone(condition: str) -> Zone | None:
    """The zone a "cast a ... spell from [zone]" condition restricts the cast
    to, or `None` when the condition names no origin at all - which is what a
    plain "whenever you cast a spell" means (CR 603.2: no restriction is no
    restriction).
    """
    match = _CAST_ORIGIN_ZONE_RE.search(condition)
    if match is None:
        return None
    word = (match.group("possessive") or match.group("bare") or "").lower()
    return _CAST_ORIGIN_ZONE_WORDS.get(word)


def _origin_zone_matches(origin_zone: Zone | None, condition: str) -> bool:
    """Whether a `CAST_SPELL` event's `GameEvent.origin_zone` satisfies a
    condition's "from [zone]" restriction, if it has one.

    `origin_zone is None` matches anything: every real `CAST_SPELL` event
    populates it (`Game.put_on_stack` is the only emitter), so `None` here
    means the condition asked about something this engine doesn't track
    rather than a cast this engine knows happened from nowhere - the same
    "nothing required" default `_types_match` and `_color_matches` already
    fall back to, kept on the permissive side rather than refusing a
    legitimate trigger over missing data.
    """
    excluded = _excluded_cast_origin_zone(condition)
    if excluded is not None:
        return origin_zone is not None and origin_zone is not excluded
    required = _required_cast_origin_zone(condition)
    if required is None:
        return True
    if origin_zone is None:
        return True
    return origin_zone is required


#: CR 202.3's ordinary mana-value comparisons, as a "cast a ... spell"
#: condition phrases them. Order matters: the "or greater"/"or less"/
#: "greater than"/"less than" forms are tried before the bare-number
#: equality form, since a bare `\d+` would otherwise match the leading digit
#: of "7 or greater" and read it as equality.
_MANA_VALUE_OR_GREATER = re.compile(r"mana value (?:of )?(\d+) or greater")
_MANA_VALUE_OR_LESS = re.compile(r"mana value (?:of )?(\d+) or less")
_MANA_VALUE_GREATER_THAN = re.compile(r"mana value (?:of )?greater than (\d+)")
_MANA_VALUE_LESS_THAN = re.compile(r"mana value (?:of )?less than (\d+)")
_MANA_VALUE_EQUALS = re.compile(r"mana value (?:of )?(\d+)\b")


def _entering_mana_value_qualifier_holds(
    game: "Game", condition: str, subject_id: UUID | None
) -> bool | None:
    """Whether "`<permanent>` ... with mana value N or greater/or less/..."
    holds for the entering object (CR 202.3, read off its computed
    characteristics, CR 613.5) - Simulacrum Synthesizer's own "another
    artifact you control with mana value 3 or greater enters". `None` when
    the condition names no literal mana-value qualifier at all; unread, the
    trigger fired on every artifact - its own 0/0 Construct token included,
    which retriggered it forever."""
    lowered = condition.lower()
    if "with mana value" not in lowered:
        return None
    comparison = _mana_value_comparison(lowered)
    if comparison is None:
        return None
    subject = game.find_by_id(subject_id) if subject_id is not None else None
    if subject is None:
        return False
    threshold, comparator = comparison
    ops = {
        ">=": operator.ge,
        "<=": operator.le,
        ">": operator.gt,
        "<": operator.lt,
        "==": operator.eq,
    }
    return bool(ops[comparator](game.characteristics_of(subject).mana_value, threshold))


def _mana_value_comparison(condition: str) -> tuple[int, str] | None:
    """The `(threshold, comparator)` a "with mana value ..." clause names, or
    `None` when the condition names no mana-value restriction at all.

    `comparator` is one of `">="`, `"<="`, `">"`, `"<"`, `"=="`. Chalice of the
    Void's "equal to the number of ... counters" shape is read earlier, by
    `_MANA_VALUE_EQUALS_COUNTERS`, before this is ever reached - its threshold
    is not a literal number in the condition text, so it cannot be one of
    these five.
    """
    lowered = condition.lower()
    or_greater = _MANA_VALUE_OR_GREATER.search(lowered)
    if or_greater is not None:
        return int(or_greater.group(1)), ">="
    or_less = _MANA_VALUE_OR_LESS.search(lowered)
    if or_less is not None:
        return int(or_less.group(1)), "<="
    greater_than = _MANA_VALUE_GREATER_THAN.search(lowered)
    if greater_than is not None:
        return int(greater_than.group(1)), ">"
    less_than = _MANA_VALUE_LESS_THAN.search(lowered)
    if less_than is not None:
        return int(less_than.group(1)), "<"
    equals = _MANA_VALUE_EQUALS.search(lowered)
    if equals is not None:
        return int(equals.group(1)), "=="
    return None


#: CR 506.2/508.1b: an attack on the ability's controller, or on a
#: planeswalker they control - "Whenever a creature attacks you or a
#: planeswalker you control" (Slumbering Dragon, Isperia, Circle of Flame).
#: The "you control" here is the planeswalker's, never the attacker's.
_ATTACKS_YOU_RE = re.compile(r"\battacks you(?P<planeswalker> or a planeswalker you control)?$")

#: "Whenever this creature and at least one other creature attack, ..."
#: (Arthur, Marigold Knight; Sokka, Lateral Strategist; Glimmer Lens' own
#: "equipped creature" subject) and Valor's Reach Tag Team's own granted
#: "Whenever this token and at least one other creature token attack, ..." -
#: a compound self-plus-group attack condition CR 508.1a's ordinary per-
#: attacker trigger reading has no room for on its own: both the source
#: *and* at least one other creature (optionally narrowed to a token, CR
#: 111.1) must be among the creatures declared as attackers this combat.
_SELF_AND_OTHER_CREATURE_ATTACKS_RE = re.compile(
    r"^this [a-z]+ and at least one other creature(?P<token> tokens?)? attacks?$",
    re.IGNORECASE,
)

#: "an equipped creature you control" as a trigger subject (CR 301.5a) - the
#: indefinite article is what separates it from an Equipment's own "equipped
#: creature", the one creature that Equipment is attached to.
_AN_EQUIPPED_CREATURE_RE = re.compile(r"\ban equipped creature\b")


def _has_equipment_attached(game: "Game", subject_id: "UUID | None") -> bool:
    """Whether an Equipment (CR 301.5) is attached to this permanent now."""
    if subject_id is None:
        return False
    return any(
        permanent.attached_to == subject_id
        and "Equipment" in game.characteristics_of(permanent).subtypes
        for permanent in game.battlefield
    )


def _attacks_you_holds(
    game: "Game",
    attacker_text: str,
    defended: "re.Match[str]",
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether `event`'s attack is on `controller` (or, when the condition
    says so, a planeswalker `controller` controls) by an attacker matching
    the condition's own description ("a creature without flying")."""
    defender = event.defender
    if defender is None:
        return False
    if defender.username is not None:
        attacked_you = defender.username == controller
    else:
        attacked = game.find_by_id(defender.card_id) if defender.card_id is not None else None
        attacked_you = (
            defended.group("planeswalker") is not None
            and isinstance(attacked, CardState)
            and attacked.controller == controller
            and Type.PLANESWALKER in attacked.types
        )
    if not attacked_you:
        return False
    from ..targeting import permanent_description

    description = re.sub(r"^(?:a|an)\s+", "", attacker_text.strip())
    requirement = permanent_description(description)
    attacker = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    if requirement is None or not isinstance(attacker, CardState):
        return False
    return requirement.rejects(attacker, controller, game, None) is None


#: "Whenever an opponent attacks a planeswalker you control with one or more
#: creatures" (Oath of Kaya): one trigger for each of the controller's
#: planeswalkers an opponent attacks (the card's ruling: "If an opponent
#: attacks more than one planeswalker you control, the last ability of Oath
#: of Kaya triggers once for each of those attacked planeswalkers"), however
#: many creatures attack it (CR 508.3d's per-declaration reading, here per
#: attacked planeswalker).
_OPPONENT_ATTACKS_YOUR_PLANESWALKER_RE = re.compile(
    r"^an opponent attacks (?:a|one or more) planeswalkers? you control with one or more "
    r"creatures$"
)


def opponent_attacks_your_planeswalker_condition(condition: str) -> bool:
    """Whether `condition` is `_OPPONENT_ATTACKS_YOUR_PLANESWALKER_RE`'s shape
    - read off a real declared attack, which `support`'s synthetic board
    never has."""
    return _OPPONENT_ATTACKS_YOUR_PLANESWALKER_RE.fullmatch(condition.strip().lower()) is not None


def _opponent_attacks_your_planeswalker_holds(
    game: "Game", controller: str, event: GameEvent
) -> bool:
    """`_OPPONENT_ATTACKS_YOUR_PLANESWALKER_RE`'s match: an opponent's
    attacker declared at one of `controller`'s planeswalkers (CR 508.1a), and
    the first attacker declared at it, so each attacked planeswalker
    triggers once."""
    if event.subject_id is None or event.subject_controller in (None, controller):
        return False
    defender = event.defender
    if defender is None or defender.card_id is None:
        return False
    attacked = game.find_by_id(defender.card_id)
    if not (
        isinstance(attacked, CardState)
        and attacked.zone is Zone.BATTLEFIELD
        and game.controller_of(attacked).username == controller
        and Type.PLANESWALKER in game.characteristics_of(attacked).types
    ):
        return False
    first = next((attack for attack in game.combat.attacks if attack.defender == defender), None)
    return first is not None and first.attacker_id == event.subject_id


def _controller_clause_holds(
    condition: str, controller: str, subject_controller: str | None
) -> bool:
    """Honour "you control" / "an opponent controls" in a trigger condition.

    A condition that names neither is true for anybody, which is what
    "whenever a creature dies" means.
    """
    lowered = condition.lower()
    if "you control" in lowered or lowered.startswith("you "):
        return subject_controller == controller
    if "an opponent controls" in lowered or "your opponents control" in lowered:
        return subject_controller is not None and subject_controller != controller
    return True


#: CR 603.6d: "Some permanents have text that reads '[This permanent] enters
#: with . . . ,' 'As [this permanent] enters . . . ,' '[This permanent]
#: enters as . . . ,' or '[This permanent] enters tapped.'" - the shapes that
#: qualify *how* a permanent enters, on top of CR 603.6a's bare "enters"/
#: "enters the battlefield". When a trigger condition is itself written with
#: one of these qualifiers - Amulet of Vigor's own "Whenever a permanent you
#: control enters tapped" - the qualifier narrows the CR 603.2 event match
#: itself, checked once when the event occurs; it is not an intervening "if"
#: (CR 603.4, 608.2a) rechecked at resolution, since the condition text never
#: spells "if" for this. `Game.put_onto_battlefield` (`models/game.py`) sets
#: `card_state.tapped` and applies any entering counters *before* emitting
#: `TriggerEvent.ENTERS_THE_BATTLEFIELD` (`Game._enters_event`), so the
#: subject looked up here already carries its real entering state.
_ENTERS_TAPPED_RE = re.compile(r"\benters?\b(?:[^.]*\bthe battlefield\b)?[^.]*?\btapped\b")
_ENTERS_UNTAPPED_RE = re.compile(r"\benters?\b(?:[^.]*\bthe battlefield\b)?[^.]*?\buntapped\b")
_ENTERS_WITH_COUNTER_RE = re.compile(
    r"\benters?\b[^.]*?\bwith\s+(?:a|an|one or more|\d+)\s+"
    r"(?P<kind>[+/\-\w]+(?:[ \-][+/\-\w]+)*?)\s+counters?\s+on\s+(?:it|them)\b"
)


def _entry_qualifier_matches(game: "Game", condition: str, event: "GameEvent") -> bool:
    """Whether an "enters tapped"/"enters untapped"/"enters with a ... counter
    on it" qualifier (CR 603.6d) on an ENTERS_THE_BATTLEFIELD condition holds
    for `event`.

    A condition naming none of these qualifiers imposes none, which is what a
    bare "enters"/"enters the battlefield" already means - this returns True
    for those unconditionally, the same "nothing named, nothing required"
    default `_controller_clause_holds` and `_types_match` already use.
    """
    lowered = condition.lower()
    subject: CardState | None = None
    if event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)

    if _ENTERS_TAPPED_RE.search(lowered) is not None and (subject is None or not subject.tapped):
        return False
    if _ENTERS_UNTAPPED_RE.search(lowered) is not None and (subject is None or subject.tapped):
        return False

    counter_match = _ENTERS_WITH_COUNTER_RE.search(lowered)
    if counter_match is not None:
        if subject is None:
            return False
        kind = counter_match.group("kind").strip()
        if kind not in subject.counters:
            return False

    origin_match = _ENTERS_FROM_ZONE_RE.search(lowered)
    if origin_match is not None:
        # CR 603.6a: "enters from a graveyard"/"from your hand" - the enters
        # event carries the zone the permanent moved from (`origin_zone`);
        # "your" names a zone of the permanent's owner (CR 400.3).
        required = _ENTERS_FROM_ZONE_WORDS[origin_match.group("zone")]
        if event.origin_zone is not required:
            return False
        if origin_match.group("whose") == "your" and (
            subject is None or subject.owner != event.subject_controller
        ):
            return False

    return True


#: "enters from a graveyard" (Treacherous Pit-Dweller), "enters from your
#: graveyard" (Phyrexian Dragon Engine), "enters from your hand"
#: (Thousand-Faced Shadow), "enters from exile" - the origin half of an
#: enters condition (CR 603.6a).
_ENTERS_FROM_ZONE_RE = re.compile(
    r"\benters? from (?:(?P<whose>your|a|their) )?(?P<zone>hand|graveyard|library|exile)\b"
)
_ENTERS_FROM_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "exile": Zone.EXILE,
}


def entering_origin_zone(condition: str) -> Zone | None:
    """The zone an enters condition requires its permanent to have come from
    (`_ENTERS_FROM_ZONE_RE`), or `None` when it names none."""
    match = _ENTERS_FROM_ZONE_RE.search(condition.lower())
    return None if match is None else _ENTERS_FROM_ZONE_WORDS[match.group("zone")]


#: CR 111.1's token, read off a condition's own printed word rather than
#: assumed from a card-name table. `\b` word boundaries so `_TOKEN_WORD`
#: cannot match the "token" inside "nontoken" (a substring, not a word) - see
#: `condition_matches`'s ENTERS_THE_BATTLEFIELD and IS_SACRIFICED branches for
#: why both directions are checked, not just the false-positive one a
#: word-boundary test alone would stop.
_NONTOKEN_WORD = re.compile(r"\bnontoken\b")
_TOKEN_WORD = re.compile(r"\btokens?\b")


#: "this `<noun>` or `<other subject>` enters" - a self-or-other entry
#: condition; `other` is read like any other "`<subject>` enters" condition.
#: The self half is either CR 700.7's "this `<noun>`" or the source's own
#: name in any shortened form `self_reference_names` reads (Mabel, Valley
#: Hero's own "Whenever Mabel or another creature you control enters" -
#: CR 201.5c's short name before the comma, not "this planeswalker").
#: Satoru, the Infiltrator's "Satoru and/or one or more other nontoken
#: creatures you control enter" is the batched spelling of the same pair.
_SELF_OR_OTHER_ENTERS_TAIL = (
    r" (?:and/)?or (?P<other>(?:an?|another|one or more other) .+? enters?"
    r"(?: from (?:your |an? |their )?(?:hand|graveyard|library|exile))?)$"
)
_SELF_OR_OTHER_ENTERS_GENERIC_RE = re.compile(
    rf"^this [a-z]+{_SELF_OR_OTHER_ENTERS_TAIL}", re.IGNORECASE
)


def _self_or_other_enters_match(
    condition: str, source_name: str, *, legendary: bool = True
) -> re.Match[str] | None:
    if " or " not in condition.lower() and " and/or " not in condition.lower():
        return None
    generic = _SELF_OR_OTHER_ENTERS_GENERIC_RE.match(condition)
    if generic is not None:
        return generic
    for name in self_reference_names(source_name, legendary=legendary):
        if name not in condition:
            continue
        named = re.match(rf"^{self_reference_pattern(name)}{_SELF_OR_OTHER_ENTERS_TAIL}", condition)
        if named is not None:
            return named
    return None


#: "this creature or a Dragon you control dies" (Dragon-Kami's Egg) - the
#: self half plus an "a[n] `<subject>`" half that is not "another": the
#: source itself, and any other object the second half describes.
#: "a creature dealt damage by this creature this turn" - the dying
#: creature's own damage history from the trigger's source (CR 120.1).
DEALT_DAMAGE_BY_THIS_RE = re.compile(r"\bdealt damage by this [a-z]+ this turn\b")
_SELF_OR_A_SUBJECT_RE = re.compile(r"\bor an? (?!other\b)[a-z]")

_LEGENDARY_WORD = re.compile(r"\blegendary\b")


#: Orcish Bowmasters' "whenever an opponent draws a card except the first one
#: they draw in each of their draw steps" - CR 504.1's turn-based draw (or
#: whichever card is first drawn in that step, if that one was replaced away,
#: CR 603.2g) does not count.
_EXCEPT_FIRST_DRAW_STEP_DRAW = re.compile(
    r"\bexcept the first one (?:they|you) draws? in each of (?:their|your) draw steps\b"
)


def _is_first_own_draw_step_draw(game: "Game", player: str | None) -> bool:
    """Whether the draw being dispatched is the first card `player` has drawn
    in their own draw step this turn (`Game.cards_drawn_in_own_draw_step`,
    counted before the draw event is emitted)."""
    turn = getattr(game, "turn", None)
    if player is None or turn is None:
        return False
    if turn.step is not Step.DRAW or turn.active_player != player:
        return False
    return game.cards_drawn_in_own_draw_step.get(player, 0) == 1


#: A trigger condition's own trailing "with a[n] [<kind>] counter on it"
#: qualifier on its subject (CR 122.1) - Venus, Torn Between Worlds' own
#: second ability, "Whenever a creature you control with a counter on it
#: deals combat damage to a player, ...". Read the identical way
#: `machines/targeting._WITH_COUNTER_RE` already reads the same clause for a
#: *target* restriction, but here for a trigger's own subject instead: a bare
#: "a counter" (no kind word before "counter") asks CR 122.1's presence
#: question only ("does it have any counter on it at all"), while a named
#: kind ("a +1/+1 counter on it") narrows to that one kind - Venus and Yathan
#: Tombguard both print only the bare form, so only that half is proven by a
#: scenario; the named-kind half stays read but unproven pending a printing.
_SUBJECT_HAS_COUNTER_RE = re.compile(
    r"\bwith an? (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+)\s+)?counters? on (?:it|them)\b",
    re.IGNORECASE,
)


def _subject_has_required_counter(condition: str, game: "Game", subject_id: object) -> bool:
    """Whether `subject_id` satisfies a trailing `_SUBJECT_HAS_COUNTER_RE`
    qualifier in `condition` - `True` when the condition carries no such
    qualifier at all, so every other event's condition (none of which read
    this helper) is unaffected."""
    match = _SUBJECT_HAS_COUNTER_RE.search(condition)
    if match is None:
        return True
    subject = game.find_by_id(subject_id) if subject_id is not None else None
    counters = getattr(subject, "counters", None)
    if counters is None:
        return False
    kind = match.group("kind")
    if kind is None:
        return bool(counters)
    return kind.lower() in counters


#: A batched entry condition - "one or more `<subject>` enter", alone or
#: after a self half ("Satoru and/or one or more other nontoken creatures you
#: control enter").
_ONE_OR_MORE_WORDS = re.compile(r"\bone or more\b")


#: CR 509.3b: "blocks a creature" / "blocks target ..." - one trigger per attacker.
_BLOCKS_A_CREATURE_RE = re.compile(r"\bblocks (?:a|an|another|target|that|each)\b")


def condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether this printed condition is matched by this event (CR 603.2) -
    `_condition_matches`, plus CR 603.2c's "An ability triggers only once
    each time its trigger event occurs": a batched "one or more ... enter"
    condition triggers once for one event that put several permanents onto
    the battlefield (CR 603.6a, `GameEvent.entered_together`), on the first
    member it matches, never again on the others."""
    if not _condition_matches(game, ability, source, controller, event):
        return False
    return not _earlier_batch_member_matched(game, ability, source, controller, event)


def _earlier_batch_member_matched(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether a member entering ahead of `event`'s own subject in the same
    batch already matched this batched entry condition (CR 603.2c)."""
    if (
        ability.event is not TriggerEvent.ENTERS_THE_BATTLEFIELD
        or len(event.entered_together) < 2
        or not _ONE_OR_MORE_WORDS.search(ability.condition.lower())
    ):
        return False
    for member_id, origin in event.entered_together:
        if member_id == event.subject_id:
            return False
        member = game.find_by_id(member_id)
        if not isinstance(member, CardState) or member.zone is not Zone.BATTLEFIELD:
            continue
        member_event = game._enters_event(member).model_copy(
            update={"origin_zone": origin, "entered_together": event.entered_together}
        )
        if _condition_matches(game, ability, source, controller, member_event):
            return True
    return False


def _condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether this printed condition is matched by this one event (CR 603.2).

    The shapes read, one per `TriggerEvent`:

    - **enters** (CR 603.6a) - "When this creature enters" fires for the source
      itself; "Whenever [another] [type] you control enters" fires for another
      permanent of that type. A condition additionally qualified "... enters
      tapped"/"... enters untapped"/"... enters with a[n] [kind] counter on
      it" (CR 603.6d) only matches an event whose subject actually entered
      that way - see `_entry_qualifier_matches`.
    - **dies** (CR 700.4, 603.10a) - "When this creature dies" for the source
      itself, and "Whenever another creature you control dies" / "... one or
      more other Cats you control die" for anything else that dies, optionally
      narrowed by type or subtype. The plural "die" and the spelled-out CR
      700.4 form ("is put into a graveyard from the battlefield", Flagstones
      of Trokair) are both read as this event by `_trigger_event`. Simultaneous
      deaths are not deduplicated: the engine emits one DIES event per
      permanent that dies rather than batching a single state-based-action
      sweep, so a plural "one or more ... die" condition fires once per death
      that matches rather than once per sweep the way CR 603.2c's "one event,
      multiple occurrences" reading of the printed plural would - untested
      beyond one creature dying at a time, which is what the pool exercises.
    - **leaves the battlefield** (CR 603.6c) - "When this creature leaves the
      battlefield" (Thought-Knot Seer), self-referential only in this pool:
      the generic departure, distinct from `DIES`'s graveyard-specific one,
      emitted by all three of `Game.put_into_graveyard`, `Game.exile_
      permanent`, and `Game.return_to_hand` whenever the move actually
      started on the battlefield, regardless of which of those three it
      became.
    - **attacks** (CR 508.1, 508.3d) - "Whenever this creature attacks" for the
      source, "Whenever a creature you control attacks" for any attacker under
      the same control, and "Whenever you attack" for the controller once per
      combat regardless of how many creatures were declared - the last of
      those reads a second, playerwide event `Game.declare_attackers` emits
      once per attacking player after every per-creature attack event, and
      only that shape of condition is matched against it.
    - **blocks** (CR 509.1) - only the self-referential forms, "Whenever this
      creature blocks" and "... or becomes blocked".
    - **beginning of a step** (CR 500.6) - "At the beginning of your upkeep",
      "... of each upkeep", end step, draw step, untap step, the two main
      phases, and "combat on your turn".
    - **cast** (CR 601.2) - "When you cast this spell" for the spell itself, and
      "Whenever you cast a[n] [restriction] spell" for anything that player
      casts, where the restriction can name a card type/non-type
      (`_types_match`), a subtype (`_required_cast_subtype`,
      `_subtype_matches`), a color/colorless/monocolored/multicolored
      restriction (CR 105.2, `_color_matches`), or a mana-value comparison
      (CR 202.3, `_mana_value_comparison`) - Sanctum of Ugin's "a colorless
      spell with mana value 7 or greater" is all three of the last kinds at
      once. Chalice of the Void's "mana value equal to the number of ...
      counters" is its own shape, read first and separately, since its
      threshold is not a literal number in the condition text. A mana-value
      clause that names one but whose comparison shape none of the five
      regexes read fails closed and is recorded on
      `game.cast_condition_notices` (`CastConditionNotice`) - a restriction
      genuinely present but unrecognised must never be treated as satisfied,
      the same reasoning `intervening_if_holds` already applies to an
      unreadable intervening *if*.
    - **draws a card** (CR 121.2) - "Whenever you draw a card" for the
      controller's own draws and "Whenever an opponent draws a card" for the
      others. The subject is the card drawn; the player is the one who drew it.
    - **gains life** (CR 119.9) - "Whenever you gain life" for the
      controller's own gains, "Whenever an opponent gains life" against the
      others. The player is the one who gained it.
    - **deals damage** (CR 120.1, 120.2a) - "Whenever [this] deals combat
      damage to a player" and the same "to an opponent": combat damage only,
      aimed at a player, and an opponent is one who is not the source's
      controller. Damage to a creature carries no player, so neither clause
      matches; damage with no known source matches nothing self-referential.
    - **is sacrificed** (CR 701.21a, 603.10a) - "Whenever you sacrifice a
      [type]" for what the controller sacrifices, and the self-referential
      "when this [type] is sacrificed". The subject is the permanent that went.
    - **becomes tapped / untapped** (CR 701.26a/b) - only the self-referential
      forms, "Whenever [this] becomes tapped" and "Whenever this creature
      becomes untapped".
    - **is tapped for mana** (CR 106.12, 106.12a) - "Whenever you tap a
      creature for mana" for the controller's own taps, and "Whenever
      enchanted [land] is tapped for mana" for the permanent an Aura source is
      attached to. Emitted by `machines/cost.CostPayment.tap_for_mana`, the
      only place the engine taps a permanent for mana.

    - **becomes the target** (CR 115.1, 601.2c, 602.2b) - ward's and
      Bonecrusher Giant's self-referential forms, and Loki, God of Mischief's
      general "a player or permanent becomes the target of an ability you
      control", which asks nothing about *what* was targeted and everything
      about who controls the targeting object and whether it was a spell or an
      ability (`_targeting_object_matches`).

    An ability the parser left with `event=None` is matched from its printed
    condition instead, by `_unread_condition_matches` - the counters-put,
    leaves-a-graveyard, put-into-a-library, exiled-from-a-graveyard and
    Nth-draw shapes.

    Anything else returns False. A condition this module cannot read never fires
    a trigger, which is the safe direction to be wrong in.
    """
    ability_word = (getattr(ability, "ability_word", None) or "").lower()
    if ability_word == "solved" and not getattr(source, "solved", False):
        return False  # CR 702.169c: "triggers only if this Case is solved"
    if ability_word == "to solve" and getattr(source, "solved", False):
        return False  # CR 719.3a: "... and this Case is not solved"
    condition = ability.condition

    if ability.event is TriggerEvent.CAST_SPELL:
        # Danitha, Sword of Hope's own "you cast an Equipment spell or a
        # spell that targets a creature you control" (CR 601.2, two
        # independent descriptions of the cast spell joined by an ordinary
        # English "or", not a single description's own internal
        # disjunction the way "a red or green creature spell"'s colour list
        # is). `_cast_spell_alternatives` finds the boundary only where the
        # text after "or" itself starts a new "[a/an] ... spell"/"a spell
        # that targets ..." clause, so an ordinary condition with no such
        # boundary returns unchanged and falls straight through to the
        # single-clause reading below - every other CAST_SPELL card in the
        # pool is unaffected.
        alternatives = _cast_spell_alternatives(condition)
        if len(alternatives) > 1:
            return any(
                condition_matches(
                    game,
                    ability.model_copy(update={"condition": clause}),
                    source,
                    controller,
                    event,
                )
                for clause in alternatives
            )

    lowered = condition.lower()
    mine = _self_referential(condition, source.name, legendary=_is_legendary_source(source))

    if ability.event is None:
        # A condition `machines/abilities._trigger_event` could not read at
        # all. It still names a real trigger event (CR 603.1's "[trigger
        # condition or event]"), and `_unread_condition_matches` reads the
        # handful of those shapes this module knows - see
        # `_unread_trigger_events`.
        return _unread_condition_matches(game, ability, source, controller, event)

    if event.event is not ability.event:
        return False

    if ring_bearer := _RING_BEARER_SUBJECT.match(condition):
        # CR 701.54e: "your Ring-bearer" is one particular creature - the
        # ability's controller's Ring-bearer right now - so the condition is
        # that creature's own self-referential one ("Whenever your
        # Ring-bearer attacks" is "Whenever this creature attacks", asked of
        # the Ring-bearer). The Ring's own abilities (CR 701.54c) are printed
        # this way on an emblem, which is never itself the subject.
        bearer = game.ring_bearer_of(controller)
        if bearer is None:
            return False
        rebound = ability.model_copy(update={"condition": f"this creature {ring_bearer['rest']}"})
        return condition_matches(game, rebound, bearer, controller, event)

    if ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD:
        if not _entry_qualifier_matches(game, condition, event):
            return False
        either = _self_or_other_enters_match(
            condition, source.name, legendary=_is_legendary_source(source)
        )
        if mine and either is None:
            return event.subject_id == source.id
        if either is not None:
            # "this enchantment or a legendary creature you control enters"
            # (Campsite Cuisine): the source itself, or anything that fits
            # the other half, read as its own condition below.
            if event.subject_id == source.id:
                return True
            condition = either.group("other")
            lowered = condition.lower()
        # "another creature" and Enduring Innocence's plural "one or more
        # other creatures" both exclude the source's own entry.
        if re.search(r"\b(?:another|other)\b", lowered) and event.subject_id == source.id:
            return False
        if _LEGENDARY_WORD.search(lowered):
            # CR 205.4a: "legendary" is a supertype, read off the computed
            # object (CR 613.5) - not a card type `_types_match` knows.
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if (
                subject is None
                or Supertype.LEGENDARY not in game.characteristics_of(subject).supertypes
            ):
                return False
        if _color_condition(condition) is not None:
            # Eldrazi Mimic's "another colorless creature you control enters"
            # (CR 105.2c) and any colour adjective on the entering object,
            # read off its computed colours (CR 613.1e) - unread, a green
            # Grizzly Bears fired a colorless-only trigger.
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or not _color_matches(
                game.characteristics_of(subject).colors, condition
            ):
                return False
        if not _controller_clause_holds(
            condition, controller, event.subject_controller
        ) or not _types_match(event.subject_types, condition):
            return False
        # A subtype named as the entry condition's subject (CR 205.3i,
        # CR 712.8f) - Valakut, the Molten Pinnacle's "Whenever a Mountain you
        # control enters". `_types_match` reads *card* types only and so
        # answers True for any permanent at all here, which let a plain Forest
        # entering fire a Mountain trigger. `GameEvent.subject_subtypes` is the
        # computed, layer-aware read (CR 613.5), so a land that is a Mountain
        # only because of Blood Moon or Dryad of the Ilysian Grove counts, and
        # one that is not does not.
        if not _subtype_matches(event.subject_subtypes, _required_entering_subtype(condition)):
            return False
        if "of the chosen type" in lowered:
            # Dawn-Blessed Pennant's own "a permanent you control of the
            # chosen type enters" (CR 614.12a's choice, read back off
            # `source.choice` - `source` is this ability's own permanent,
            # the one that made the choice, never the entering object
            # itself). `_required_entering_subtype`'s own `_ENTERING_SUBTYPE`
            # only recognises a printed, capitalised subtype word, so a
            # lowercase "the chosen type" left this filter unread and the
            # trigger fired on *any* permanent entering, itself included -
            # Panharmonicon-style CR 603.6a self-entry among them.
            choice = source.choice
            if choice is None or choice.kind is not ChoiceKind.CREATURE_TYPE:
                return False
            if choice.value.lower() not in {
                subtype.lower() for subtype in event.subject_subtypes or ()
            }:
                return False
        # "Whenever one or more tokens you control enter" (Caretaker's
        # Talent) - CR 111.1's token, not a card type `_types_match` already
        # reads, so it is checked separately: whatever just entered must be
        # a token, not merely a permanent of some named type.
        #
        # "nontoken" contains "token" as a substring, so a plain `"token" in
        # lowered` test used to match Weapons Manufacturing's "a nontoken
        # artifact you control enters" and Miirym's "another nontoken Dragon
        # you control enters" too - and, since the guard demanded the
        # entering permanent *be* a token, it fired those two conditions on
        # exactly the class of permanent their own text excludes. `nontoken`
        # is checked first and enforces the opposite requirement; only when
        # it is absent does a bare `\btoken\b` (word-boundary, so "nontoken"
        # itself cannot match it) ask for the Caretaker's Talent/Belladonna
        # Took shape.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        elif _TOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if not (subject is not None and getattr(subject, "token", False)):
                return False
        # "a creature you control with power 4 or greater enters" (Garruk,
        # Curse Breaker, CR 208.1) - the same "with power [or toughness] N
        # or less/greater" qualifier `BLOCKS` already reads for Tetsuko
        # Umezawa, Pursuer's non-self form, wired in here too rather than
        # kept BLOCKS-only: nothing about the qualifier's own grammar is
        # specific to blocking, and leaving it unread here silently dropped
        # Garruk's own filter, firing his draw on any creature at all.
        power_or_toughness = _power_or_toughness_qualifier_holds(game, condition, event.subject_id)
        if power_or_toughness is False:
            return False
        mana_value = _entering_mana_value_qualifier_holds(game, condition, event.subject_id)
        return mana_value is None or mana_value

    if ability.event is TriggerEvent.DIES:
        if "enchanted" in lowered:
            # Ferocity of the Hunt's own "When enchanted creature dies, ..."
            # (CR 303.4b/303.4m's "enchanted [object]"), the DIES twin of
            # `TAPPED_FOR_MANA`'s own "enchanted [land]" read above -
            # `source.attached_to` is CR 603.10a's look-back: the Aura's own
            # SBA-triggered fall (CR 303.4c, CR 704.5m) has not run the
            # sweep yet at the moment this event fires, so it still names
            # the creature that just died rather than nothing.
            return event.subject_id is not None and event.subject_id == source.attached_to
        if DEALT_DAMAGE_BY_THIS_RE.search(lowered):
            # Vein Drinker's and Sengir Vampire's "a creature dealt damage by
            # this creature this turn dies": CR 120.1's damage events this
            # turn, from this object to the one that died (CR 603.10a looks
            # back at it), not this creature's own death.
            return (
                event.subject_id is not None
                and _types_match(event.subject_types, condition)
                and any(
                    record.source_id == source.id and record.recipient_id == event.subject_id
                    for record in game.damage_dealt_this_turn
                )
            )
        if event.subject_id == source.id:
            # Covers "When this creature dies" and the self half of
            # "Whenever this creature or another creature dies" (Blood
            # Artist) - either way the source's own death matches only if
            # the condition names itself at all.
            return mine
        # Not the source's own death: only a condition that also names
        # something else - "another"/"other" - can still match (CR 700.4,
        # 603.10a). A pure "When this creature dies" does not; a condition
        # naming no object of its own at all ("Whenever a creature dies",
        # an emblem's, Gardenize's own "Whenever a creature you control
        # dies" on an Enchantment) is about any creature, since it never
        # named itself as the one being asked about in the first place -
        # `mine` is false the moment the condition names no self-phrase and
        # no self-name (`_self_referential`), and only a condition that
        # *does* self-reference needs "another"/"other" to say "besides me
        # too" rather than "instead of me" (CR 603.10a).
        if (
            mine
            and "another" not in lowered
            and "other" not in lowered
            and _SELF_OR_A_SUBJECT_RE.search(lowered) is None
        ):
            return False
        subtype = _required_subtype(condition)
        if "into your graveyard" in lowered:
            # Enduring Renewal's "a creature is put into your graveyard from
            # the battlefield": the graveyard is its owner's (CR 404.1).
            died = game.find_by_id(event.subject_id) if event.subject_id else None
            if not isinstance(died, CardState) or died.owner != controller:
                return False
        if not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, subtype)
            and _excluded_subtype_absent(event.subject_subtypes, condition)
        ):
            return False
        # CR 111.1's token, read the identical way `ENTERS_THE_BATTLEFIELD`
        # already reads it above (Weapons Manufacturing's own "nontoken", and
        # the plain Caretaker's Talent/Belladonna Took "token" without it) -
        # this branch used to skip both, so Lightning Coils' own "a nontoken
        # creature you control dies" charged its counter off a token
        # creature's death too, exactly what "nontoken" is printed to
        # exclude.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        elif _TOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if not (subject is not None and getattr(subject, "token", False)):
                return False
        power_or_toughness = _power_or_toughness_qualifier_holds(game, condition, event.subject_id)
        if power_or_toughness is False:
            return False
        # CR 603.10a: "a creature you control with one or more counters on it
        # dies" looks back at the creature as it last existed.
        counter_qualifier = _leaves_battlefield_counter_qualifier_holds(
            game, condition, event.subject_id
        )
        return counter_qualifier is None or counter_qualifier

    if ability.event is TriggerEvent.TRANSFORMS:
        # CR 701.27e: "this creature transforms into `<face>`" - this object
        # turned over, and the face now up is the one named.
        named = lowered.split("transforms into", 1)[1].strip()
        return (
            mine
            and event.subject_id == source.id
            and (source.up_face_name or source.name or "").lower() == named
        )

    if ability.event is TriggerEvent.LEAVES_THE_BATTLEFIELD:
        # CR 603.6c: "When this creature leaves the battlefield" (Thought-
        # Knot Seer) is the source's own departure. "When another creature
        # you control leaves the battlefield" (Aang, at the Crossroads) is
        # anyone else's, read the way `DIES` reads its own "another"/"other"
        # widening (CR 603.10a: a leaves-the-battlefield ability looks back
        # at the object as it last existed, which the event carries).
        if event.subject_id == source.id:
            return mine
        if mine and "another" not in lowered and "other" not in lowered:
            return False
        counter_qualifier = _leaves_battlefield_counter_qualifier_holds(
            game, condition, event.subject_id
        )
        if counter_qualifier is False:
            return False
        return (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_subtype(condition))
            and _excluded_subtype_absent(event.subject_subtypes, condition)
        )

    if ability.event is TriggerEvent.ATTACKS_UNBLOCKED:
        # CR 508.3f/509.3g: only the self-referential form is in the pool
        # ("Whenever this creature attacks a player and isn't blocked, ...",
        # Master of Cruelties) - a future "another creature you control
        # attacks and isn't blocked" would need the same "another"/"other"
        # widening `DIES` already gets, not built here since nothing prints
        # it yet. "a player" narrows to CR 508.3f's own attack: an attack on
        # a planeswalker or battle never satisfies it, read off the same
        # `event.defender`/`is_player` this event carries for that reason.
        if event.subject_id != source.id:
            return False
        return "a player" not in lowered or (
            event.defender is not None and event.defender.is_player
        )

    if ability.event is TriggerEvent.ATTACKS:
        if _OPPONENT_ATTACKS_YOUR_PLANESWALKER_RE.fullmatch(lowered.strip()):
            return _opponent_attacks_your_planeswalker_holds(game, controller, event)
        threshold = total_power_attack_threshold(condition)
        if threshold is not None:
            # CR 508.3d: "you attack" is one trigger for the whole
            # declaration, read off `Game.declare_attackers`' own
            # subject-less event, not once per attacker - the identical
            # batched-declaration reading `_YOU_ATTACK_WITH_ONE_OR_MORE_RE`
            # gets just below.
            if event.subject_id is not None or event.player != controller:
                return False
            total_power = sum(
                (game.power_of(attacker) or 0)
                for attacker in game.attacking_creatures()
                if game.controller_of(attacker).username == controller
            )
            return total_power >= threshold
        attacks_with = PLAYER_ATTACKS_WITH_N_OR_MORE_RE.fullmatch(lowered.strip())
        if attacks_with is not None:
            # CR 508.3d: "Whenever a player attacks with five or more creatures"
            # (Aurelia, the Law Above) is one trigger for the whole declaration,
            # read off `Game.declare_attackers`' own subject-less event - never
            # once per attacker - and only when that player declared enough.
            who = attacks_with.group("who")
            needed = parse_count(attacks_with.group("n"))
            if event.subject_id is not None or event.player is None or needed is None:
                return False
            if (who == "you") != (event.player == controller) and who != "a player":
                return False
            return (
                sum(
                    1
                    for attacker in game.attacking_creatures()
                    if game.controller_of(attacker).username == event.player
                )
                >= needed
            )
        batch = batched_attackers(game, condition, controller)
        if batch is not None:
            # CR 603.2c: "one or more <description> attack" is one trigger
            # event for the whole declaration, read off `Game.declare_
            # attackers`' own subject-less event, not once per attacker.
            return (
                event.subject_id is None
                and len(batch) >= batched_attack_minimum(condition)
                and (event.player == controller or not _ONE_OR_MORE_ATTACK_YOURS.search(condition))
            )
        if batched_attack_minimum(condition) > 1:
            # "two or more <description> attack" counts the whole
            # declaration; a description this file cannot read must not
            # fall through to the one-attacker reading below.
            return False
        # CR 508.3d: "Whenever [a player] attacks, ..." triggers once when one
        # or more creatures that player controls are declared as attackers -
        # not once per attacker. `Game.declare_attackers` emits that as its
        # own event, with no subject, once per attacking player.
        if lowered.strip() == "you attack":
            return event.subject_id is None and event.player == controller
        if event.subject_id is None:
            return False
        # CR 506.6: Jiang Yanggu, Alone's and Yuriko, Blade of the Mighty's
        # own "attacks a player alone" - checked first since the phrase
        # contains "alone" too and would otherwise also satisfy the plainer
        # CR 506.5 branch below.
        if "a player alone" in lowered and not event.attacking_player_alone:
            return False
        # CR 506.5, Exalted's own defining shape (Agents of S.H.I.E.L.D.'s
        # "a creature you control attacks alone").
        if "a player alone" not in lowered and "alone" in lowered and not event.attacking_alone:
            return False
        if "equipped" in lowered and not _AN_EQUIPPED_CREATURE_RE.search(lowered):
            # S.H.I.E.L.D. Spy Kit's own "Whenever equipped creature attacks
            # alone, ..." - the attacker has to be the one this Equipment is
            # attached to (CR 301.5a), not merely any lone attacker the
            # controller happens to have.
            return event.subject_id is not None and event.subject_id == source.attached_to
        defended = _ATTACKS_YOU_RE.search(lowered)
        if defended is not None:
            return _attacks_you_holds(
                game, lowered[: defended.start()], defended, controller, event
            )
        self_and_other = _SELF_AND_OTHER_CREATURE_ATTACKS_RE.match(
            self_normalized_effect_text(
                source.name, condition, legendary=_is_legendary_source(source)
            ).lower()
            if mine
            else lowered
        )
        if self_and_other is not None:
            # CR 508.3d's own self-attack trigger, plus Arthur, Marigold
            # Knight's/Sokka, Lateral Strategist's real "and at least one
            # other creature attack" widening: read here, ahead of `mine`'s
            # own bare self-check just below, or the "and at least one
            # other..." qualifier is silently dropped and this fires the
            # moment the source alone attacks - the identical bug class the
            # `mine` branch's own docstring warns every other event reader
            # about. Sokka, Lateral Strategist prints its own name ("Sokka
            # and at least one other creature attack") rather than "this
            # creature" - `self_normalized_effect_text` (CR 201.5/201.5c)
            # rewrites that to "this creature" first, the same way every
            # other self-referential condition in this module already
            # reads a name and "this `<kind>`" as one thing. Valor's Reach
            # Tag Team's own Warrior tokens narrow "other" to "creature
            # token" - Warrior Token's own printed "with at least one other
            # creature token attack" - which is
            # checked by requiring the other attacker's own `token` flag too.
            if event.subject_id != source.id:
                return False
            require_token = self_and_other.group("token") is not None
            return any(
                attacker.id != source.id
                and (not require_token or getattr(attacker, "token", False))
                for attacker in game.attacking_creatures()
            )
        if mine:
            return event.subject_id == source.id
        if _AN_EQUIPPED_CREATURE_RE.search(lowered) and not _has_equipment_attached(
            game, event.subject_id
        ):
            # CR 301.5a: "equipped creature" is a creature an Equipment is
            # attached to - Swordsman, Sharp Scoundrel's "Whenever an
            # equipped creature you control attacks" skips a bare attacker.
            return False
        return (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_attacking_subtype(condition))
        )

    if ability.event is TriggerEvent.BLOCKS:
        # CR 301.5a: "equipped creature becomes blocked" is the creature this
        # Equipment is attached to (Simian Sling's "this creature or equipped
        # creature becomes blocked" - attached through reconfigure, CR
        # 702.151a, the Sling itself is no creature and never blocked).
        equipped_blocked = (
            "equipped creature becomes blocked" in lowered
            and not _AN_EQUIPPED_CREATURE_RE.search(lowered)
            and source.attached_to is not None
            and event.related_id == source.attached_to
        )
        if (
            source.attached_to is not None
            and "equipped creature blocks or becomes blocked by one or more creatures" in lowered
        ):
            return _equipped_blocks_or_is_blocked_once(game, event, source.attached_to)
        if mine:
            blocks = "blocks" in lowered and event.subject_id == source.id
            if blocks and not _BLOCKS_A_CREATURE_RE.search(lowered):
                # CR 509.3a: a plain "Whenever [a creature] blocks" triggers
                # once each combat for that creature however many attackers it
                # blocks - only the pair of its first blocked attacker counts
                # (CR 509.3b's "blocks a creature" form is once per attacker).
                first = game.combat.attack_blocked_by(source.id)
                blocks = first is None or first.attacker_id == event.related_id
            blocked = "becomes blocked" in lowered and (
                event.related_id == source.id or equipped_blocked
            )
            if blocked:
                # Flanking's own "... by a creature without `<keyword>`"
                # (CR 702.25a) - checked against the blocker, `event.
                # subject_id`, which is always the blocker of the pair
                # `Game.declare_blockers` emits (never the source itself,
                # even when the source is what "becomes blocked").
                qualifier = _becomes_blocked_by_qualifier_holds(game, condition, event.subject_id)
                blocked = qualifier is None or qualifier
            if blocked and "becomes blocked by" not in lowered:
                # CR 509.3c: a plain "becomes blocked" triggers once each
                # combat for that creature however many block it - only the
                # pair of its first blocker (`Attack.blocked_by` is in the
                # order they began to block, CR 509.1h) counts, and one made
                # to block an attacker already blocked never does.
                attack = game.combat.attack_by(source.id)
                blocked = (
                    attack is None
                    or not attack.blocked_by
                    or attack.blocked_by[0] == event.subject_id
                )
            return blocks or blocked
        # Tetsuko Umezawa, Pursuer's own non-self-referential form: "a
        # creature an opponent controls with power or toughness 1 or less
        # blocks" (CR 509.1a) - the subject is the blocker, not the source,
        # so the controller/type/subtype clause is read the same general
        # way `ATTACKS`'s own non-self branch reads an attacker.
        if equipped_blocked:
            return True
        if "blocks" not in lowered:
            return False
        if not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_subtype(condition))
        ):
            return False
        power_or_toughness = _power_or_toughness_qualifier_holds(game, condition, event.subject_id)
        return power_or_toughness is None or power_or_toughness

    if ability.event is TriggerEvent.BEGINNING_OF_STEP:
        return _step_matches(condition, controller, event, source)

    if ability.event is TriggerEvent.LOYALTY_ABILITY_ACTIVATED:
        # CR 606.3. "you activate ..." (Ajani Unrelenting) - the ability's
        # own controller; "an opponent activates ..." (Gideon the Oathless)
        # - anyone but them, the same bare-"an opponent" reading `DRAWS_A_
        # CARD`/`GAINS_LIFE` already use rather than `_controller_clause_
        # holds`'s own "an opponent controls" phrasing, which this condition
        # never prints. `event.player` is whoever actually activated it
        # (`Game.activate_ability`'s own emit).
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.CAST_SPELL:
        mv_match = _MANA_VALUE_EQUALS_COUNTERS.search(lowered)
        if mv_match is not None:
            if event.subject_card is None:
                return False
            threshold = source.counters[mv_match.group("kind")]
            # CR 202.3e: on the stack, an {X} spell's mana value is the value
            # chosen for X, not the printed cost's X-as-0 reading -
            # `event.amount` is `Game.put_on_stack`'s own computation of that
            # real number (see `GameEvent.amount`'s docstring); a spell with
            # no {X} at all has `event.amount` equal to `subject_card.cmc`
            # anyway, so this is not a narrower read for the ordinary case.
            mana_value = event.amount if event.amount is not None else event.subject_card.cmc
            return mana_value == threshold
        if _MANA_VALUE_OF_CHOSEN_QUALITY.search(lowered) is not None:
            if event.subject_card is None:
                return False
            if source.choice is None or source.choice.kind is not ChoiceKind.ODD_OR_EVEN:
                # CR 614.12a: nothing was chosen (or the wrong kind was), so
                # there is no "chosen quality" for the mana value to be of.
                return False
            mana_value = event.amount if event.amount is not None else event.subject_card.cmc
            is_even = int(mana_value) % 2 == 0  # (Zero is even.)
            if (source.choice.value == "even") != is_even:
                return False
        if mine and "this spell" in lowered:
            # Banish into Fable's own "When you cast this spell **from your
            # hand**, ..." carries a CR 601.2a origin-zone qualifier on top
            # of the plain self-reference every other "this spell" cast
            # trigger in the pool has (Ulamog, the Ceaseless Hunger, Ugin,
            # Eye of the Storms, ...) - none of which print a "from
            # `<zone>`"/"from anywhere other than `<zone>`" clause at all, so
            # `_origin_zone_matches`'s own "nothing named, nothing required"
            # default (see its docstring) leaves every one of them reading
            # exactly as before. Checked here rather than falling through to
            # the ordinary origin-zone check below this early `return`,
            # which it would otherwise skip entirely.
            return event.subject_id == source.id and _origin_zone_matches(
                event.origin_zone, condition
            )
        # Frontline Heroism's own "that targets only a single creature you
        # control" clause is stripped first (CR 115.3/109.4's own vocabulary,
        # read directly by the dedicated block near the end of this branch,
        # which still asks the *original*, unstripped `lowered` whether it is
        # present at all), so Danitha, Spear of Agony's/Danitha, Sword of
        # Hope's own general "that targets `<restriction>`" reader just below
        # never mistakes Frontline's narrower clause for a *different*
        # restriction it would have to fail closed on trying to read.
        targets_only_single_creature_you_control_match = (
            _TARGETS_ONLY_SINGLE_CREATURE_CLAUSE.search(condition)
        )
        targets_only_single_creature_other_than_pattern = (
            _targets_only_single_creature_other_than_re(
                source.name, legendary=_is_legendary_source(source)
            )
        )
        targets_only_single_creature_other_than_match = (
            targets_only_single_creature_other_than_pattern.search(condition)
        )
        without_frontline_clause = _TARGETS_ONLY_SINGLE_CREATURE_CLAUSE.sub("", condition)
        without_frontline_clause = targets_only_single_creature_other_than_pattern.sub(
            "", without_frontline_clause
        )
        target_match = _SPELL_THAT_TARGETS_RE.search(without_frontline_clause)
        target_clause = target_match.group("target").strip() if target_match is not None else None
        # `caster_condition` also serves as the type/colour/subtype checks'
        # own `type_condition` below - both need the identical text with
        # Frontline's clause and this restriction's own tail gone, so one
        # strip does for both rather than two copies of the same substitution.
        caster_condition = (
            without_frontline_clause
            if target_clause is None
            else _SPELL_THAT_TARGETS_RE.sub("", without_frontline_clause)
        )
        if _DURING_AN_OPPONENTS_TURN_RE.search(caster_condition) is not None:
            # Voracious Tome-Skimmer's and Brineborn Cutthroat's "Whenever you
            # cast a spell during an opponent's turn" (CR 102.1: the active
            # player is the player whose turn it is) - a window on the turn,
            # not a caster: stripped before the "an opponent" caster check
            # below, which would otherwise read it as "an opponent casts".
            turn = getattr(game, "turn", None)
            if turn is None or turn.active_player == controller:
                return False
            caster_condition = _DURING_AN_OPPONENTS_TURN_RE.sub("", caster_condition)
        if _WITH_A_SINGLE_TARGET_RE.search(caster_condition) is not None:
            # Spinerock Tyrant's "an instant or sorcery spell with a single
            # target" - CR 115.9a counts every time an object or player was
            # chosen as a target of the spell as it was put on the stack, the
            # same count `machines/targeting.py`'s own "target spell with a
            # single target" requirement makes (`required_target_count`).
            spell = game.find_by_id(event.subject_id) if event.subject_id is not None else None
            if not isinstance(spell, CardState) or len(spell.targets) != 1:
                return False
            caster_condition = _WITH_A_SINGLE_TARGET_RE.sub("", caster_condition)
        mana_cost_symbol_match = _CAST_SPELL_MANA_COST_SYMBOL_RE.search(caster_condition)
        if mana_cost_symbol_match is not None:
            # "a spell with {X} in its mana cost" (CR 107.3, CR 202.1): the
            # cast spell's own printed mana cost has to carry that exact
            # symbol - checked here, off the object the event names, and the
            # clause stripped out before `_types_match`/`_color_matches` see
            # it below, the same treatment `_SPELL_THAT_TARGETS_RE` already
            # gets for the identical reason (those two only know card types
            # and colours, never mana symbols).
            spell = game.find_by_id(event.subject_id) if event.subject_id is not None else None
            symbol = f"{{{mana_cost_symbol_match.group('symbol').upper()}}}"
            if spell is None or symbol not in (spell.mana_cost or "").upper():
                return False
            caster_condition = _CAST_SPELL_MANA_COST_SYMBOL_RE.sub("", caster_condition)
        if "an opponent" in caster_condition.lower():
            # Jin-Gitaxias, Progress Tyrant's own "Whenever an opponent
            # casts ..." - `_controller_clause_holds` only ever recognises
            # "an opponent **controls**"/"your opponents **control**"
            # (CR 613.5's board-control question), never "casts", so a
            # condition worded this way fell through its default "nothing
            # named, nothing required" branch and matched *any* caster,
            # controller included - the same "an opponent" fallback
            # `TriggerEvent.DRAWS_A_CARD`/`GAINS_LIFE` already use just below.
            # Read off `caster_condition`, not `lowered`: Danitha, Spear of
            # Agony's own "an opponent" names her *target*, not who cast the
            # spell, and the raw text used to collide with this check the
            # identical way Frontline Heroism's own "creature" once collided
            # with the type-word scan below - refusing the caster's own cast
            # outright for a restriction that was never about the caster.
            if event.player is None or event.player == controller:
                return False
        elif not _controller_clause_holds(condition, controller, event.player):
            return False
        if not _origin_zone_matches(event.origin_zone, condition):
            return False
        if "prepared spell" in lowered:
            # CR 722.3c/722.3d, Codie, Ravenous Codex's own "Whenever you
            # cast a prepared spell, ...": a spell cast as a prepare spell -
            # the CR 722.3c exile copy itself, or (722.3d) any further copy
            # of one - is `CardState.prepare_spell_face`, the same flag its
            # own characteristics are read off.
            spell = game.find_by_id(event.subject_id) if event.subject_id is not None else None
            if spell is None or not spell.prepare_spell_face:
                return False
        if "during your turn" in lowered or "during their turn" in lowered:
            # Ral, Monsoon Mage's own condition: the cast has to have
            # happened during *this ability's controller's* own turn, not
            # merely by that controller - CR 500.1's turn structure is what
            # "your turn" points at, read off the live `TurnMachine` rather
            # than any snapshot, since the trigger is checked as the cast
            # event fires, before anything else has moved the turn along.
            turn = getattr(game, "turn", None)
            if turn is None or turn.active_player != controller:
                return False
        ordinal_match = _ordinal_spell_this_turn_matches(game, condition, controller, event)
        if ordinal_match is not None:
            return ordinal_match
        # Frontline Heroism's own clause names a type word ("creature") that
        # describes the *target*, not the cast spell itself - `_required_
        # types`/`_types_match` cannot tell the two apart on sight (it just
        # scans the whole condition for a known type word) and used to
        # misread the clause as "cast a creature spell", which Lightning
        # Bolt aimed at your own creature is not, wrongly refusing to fire
        # at all. Danitha's own "that targets ..." tail has the identical
        # problem with "opponent"/"creature you control" - both are already
        # gone from `caster_condition`, computed above.
        type_condition = caster_condition
        if not _types_match(event.subject_types, type_condition):
            return False
        if not _color_matches(event.subject_colors, type_condition):
            return False
        subtype = _required_cast_subtype(type_condition)
        if not _subtype_matches(event.subject_subtypes, subtype):
            return False
        if target_clause is not None:
            holds = _cast_spell_targets_condition_holds(
                game, target_clause, controller, event, source
            )
            if holds is None:
                game.cast_condition_notices.append(
                    CastConditionNotice(
                        source_id=source.id, source_name=source.name, condition=condition
                    )
                )
                return False
            if not holds:
                return False
        if (
            targets_only_single_creature_you_control_match is not None
            or targets_only_single_creature_other_than_match is not None
        ):
            # Frontline Heroism's own "you control" and Ivy, Gleeful
            # Spellthief's own "other than Ivy" - not a fact about the cast
            # spell's own printed characteristics at all (CR 105, CR 202.3),
            # but about *what it targets* (CR 601.2c), read off the spell's
            # own `CardState.targets` now that it sits on the stack. "only a
            # single" is CR 115.3's exactly-one; "creature you control" is
            # CR 109.4/608.2b's ordinary target-legality vocabulary and
            # "other than `<self-reference>`" is CR 201.5/115.5's own
            # exclusion of the source itself - both read directly here
            # rather than through `machines/targeting.py`, since this is a
            # *condition on an already-legal announcement*, not a targeting
            # requirement of the trigger source's own.
            if event.subject_id is None:
                return False
            spell = game.find_by_id(event.subject_id)
            if spell is None or len(spell.targets) != 1:
                return False
            (only_target,) = spell.targets
            if only_target.is_player:
                return False
            target = game.find_by_id(only_target.card_id)
            if target is None or target.zone is not Zone.BATTLEFIELD:
                return False
            # CR 613.5: the target's computed types, not the printed line -
            # an earthbent land (CR 701.66a) is a creature only there.
            if not game.characteristics_of(target).is_creature:
                return False
            if targets_only_single_creature_you_control_match is not None:
                if game.controller_of(target).username != controller:
                    return False
            elif target.id == source.id:
                return False
        if "mana value" in lowered and _MANA_VALUE_OF_CHOSEN_QUALITY.search(lowered) is None:
            # Gollum, Riddle Master's own "with mana value of the chosen
            # quality" already answered the mana-value question above - it
            # is not `_mana_value_comparison`'s own "greater than/less
            # than/equal to N" shape, and must not fail closed here for not
            # being one.
            comparison = _mana_value_comparison(condition)
            if comparison is None:
                game.cast_condition_notices.append(
                    CastConditionNotice(
                        source_id=source.id,
                        source_name=source.name,
                        condition=condition,
                    )
                )
                return False
            threshold, comparator = comparison
            if event.amount is None:
                return False
            ops = {
                ">=": operator.ge,
                "<=": operator.le,
                ">": operator.gt,
                "<": operator.lt,
                "==": operator.eq,
            }
            if not ops[comparator](event.amount, threshold):
                return False
        return True

    if ability.event is TriggerEvent.EXILED:
        # CR 702.35a: "When this card is exiled this way". Only the
        # self-referential form is read, which is the only form madness prints;
        # the "this way" is enforced by the emitter, which raises the event only
        # for the exile the madness replacement performed.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.BECOMES_TARGET:
        if getattr(ability, "keyword", None) == "ward":
            from ..targeting import ward_is_switched_off

            if ward_is_switched_off(game, source):
                # "Ward abilities of those creatures don't trigger." (Nowhere
                # to Run) - CR 702.21a's trigger never happens.
                return False
        # CR 115.1: "Some spells and abilities require their controller to
        # choose one or more targets for them ... These targets are declared as
        # part of the process of putting the spell or ability on the stack"
        # (CR 601.2c for a spell, imported wholesale for an ability by
        # CR 602.2b). Two shapes are read:
        #
        # - the self-referential one, which is what ward prints (CR 702.21a,
        #   "Whenever this permanent becomes the target of a spell or ability
        #   an opponent controls") and what Bonecrusher Giant prints
        #   ("Whenever this creature becomes the target of a spell");
        # - the general one, which names no particular object: Loki, God of
        #   Mischief's "Whenever a player or permanent becomes the target of
        #   an ability you control". Nothing about *what* was targeted is
        #   asked there - "a player or permanent" is every legal target of an
        #   ability - so the whole question is who controls the targeting
        #   object and whether it is a spell or an ability.
        #
        # - the object-subject one, which names *what* was targeted by type
        #   and controller: Venerated Rotpriest's "Whenever a creature you
        #   control becomes the target of a spell". Its "you control" is the
        #   targeted object's, so only the part after "the target of" is left
        #   for the targeting object's own controller check below.
        if mine:
            if event.subject_id != source.id:
                return False
        elif (host := _HOST_BECOMES_TARGET_RE.match(lowered.strip())) is not None:
            # CR 303.4b/301.5a: Brinebound Gift's "enchanted creature becomes
            # the target of ..." - the permanent the source is attached to.
            if source.attached_to is None or event.subject_id != source.attached_to:
                return False
            lowered = host.group("by")
            condition = lowered
        elif (object_subject := _OBJECT_TARGET_SUBJECT.match(lowered.strip())) is not None:
            if event.subject_id is None and object_subject.group("you"):
                # Reidane's "you or another permanent you control": CR 115.1
                # lets a player be targeted, and "you" is that player.
                if event.subject_controller != controller:
                    return False
            elif not _targeted_object_matches(
                game, object_subject.group("subject"), event, source, controller
            ):
                return False
            lowered = object_subject.group("by")
            condition = lowered
        elif not _target_subject_matches(condition):
            return False
        elif (targeted_spell := game.find_by_id(event.subject_id)) is not None and (
            targeted_spell.zone is Zone.STACK
        ):
            return False  # "a player or permanent": a spell on the stack is neither
        if not _targeting_object_matches(game, condition, event):
            return False
        if "an opponent controls" in lowered:
            return event.player is not None and event.player != controller
        if "you control" in lowered:
            # `GameEvent.player` on a becomes-target event is the controller
            # of the spell or ability that did the targeting (that is what
            # `machines/casting.Casting` puts there), which is exactly whose
            # "you control" this asks about.
            return event.player == controller
        return True

    if ability.event is TriggerEvent.DRAWS_A_CARD:
        if _EXCEPT_FIRST_DRAW_STEP_DRAW.search(lowered) and _is_first_own_draw_step_draw(
            game, event.player
        ):
            return False
        if lowered.startswith("the chosen player "):
            # Booby Trap's "When the chosen player draws a card with the
            # chosen name": the player its CR 614.12a choice named
            # (`CardState.chosen_player`), and "with the chosen name" the
            # drawn card's name against the recorded card-name choice.
            if event.player is None or event.player != source.chosen_player:
                return False
            if "with the chosen name" in lowered:
                choice = source.choice
                return (
                    choice is not None
                    and choice.kind is ChoiceKind.CARD_NAME
                    and event.subject_name == choice.value
                )
            return True
        if _DURING_AN_OPPONENTS_TURN_RE.search(lowered) is not None:
            # The Watcher in the Water's "Whenever you draw a card during an
            # opponent's turn" (CR 102.1): a window on the turn, not a
            # drawer - stripped before the "an opponent" check below, which
            # would otherwise read it as "an opponent draws".
            turn = getattr(game, "turn", None)
            if turn is None or turn.active_player == controller:
                return False
            lowered = _DURING_AN_OPPONENTS_TURN_RE.sub("", lowered)
            condition = _DURING_AN_OPPONENTS_TURN_RE.sub("", condition)
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.GAINS_LIFE:
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.DEALS_DAMAGE:
        single = _SINGLE_CREATURE_SPELL_DAMAGE_RE.fullmatch(lowered.strip())
        if single is not None:
            return _single_creature_spell_damage_matches(game, single, controller, event)
        if re.search(r"\b(?:is|are) dealt\b", lowered):
            # Passive voice reads the *recipient*, not the dealer - Hexhaven
            # Invigorator's self-referential "this creature is dealt damage"
            # and Master of Barbs'/Massacre Girl, Most Wanted's/Fblthp,
            # Impossibly Lost's "an opponent is/one or more opponents are
            # dealt [non]combat damage[, during your turn]" none of them say
            # anything about who *dealt* it, so the dealer-oriented checks
            # below (which read `subject_id`/`subject_controller`, the
            # dealer) do not apply at all; `target_id`/`player` (the
            # recipient) are read instead.
            if mine:
                if event.target_id != source.id:
                    return False
            elif "enchanted player is dealt" in lowered:
                # CR 303.4m: Grievous Wound's "Whenever enchanted player is
                # dealt damage" - the player the Aura is attached to.
                from ..group_attack_statics import _enchanted_player

                if event.player is None or event.player != _enchanted_player(source):
                    return False
            elif _HOST_IS_DEALT_DAMAGE_RE.match(lowered.strip()):
                # CR 303.4b: Pain for All's and Spiteful Shadows' "Whenever
                # enchanted creature is dealt damage" - the permanent the
                # source is attached to, as the damage is dealt.
                if source.attached_to is None or event.target_id != source.attached_to:
                    return False
            elif "opponent" in lowered:
                if event.player is None or event.player == controller:
                    return False
            elif event.target_id is not None and re.search(
                r"\b(?:a|an|another)\b[^,]*\b(?:creature|planeswalker|permanent)\b", lowered
            ):
                # CR 120.1's recipient with a type and controller clause:
                # The Sensational She-Hulk's "Whenever a creature you control
                # is dealt damage" ("another" excludes the source itself).
                if "another" in lowered and event.target_id == source.id:
                    return False
                if not (
                    _controller_clause_holds(condition, controller, event.target_controller)
                    and _types_match(event.target_types, condition)
                ):
                    return False
            else:
                return False
            if "noncombat damage" in lowered:
                if event.combat:
                    return False
            elif "combat damage" in lowered and not event.combat:
                return False
            if "during your turn" in lowered or "during their turn" in lowered:
                turn = getattr(game, "turn", None)
                if turn is None or turn.active_player != controller:
                    return False
            return True
        # CR 120.1: "An object that deals damage is the source of that
        # damage" - the subject is the source, so the self-referential
        # form ("this creature deals damage") checks the source and the
        # general form checks the controller clause and types of whatever
        # dealt it. Damage with no known source carries neither an id nor a
        # controller and matches nothing here. The passive form ("this
        # creature is dealt damage") is caught above, before this point is
        # ever reached, through `target_id`/`player` instead.
        if mine:
            if event.subject_id != source.id:
                return False
        elif "enchanted creature deals" in lowered:
            # CR 303.4b: Visions of Brutality's "Whenever enchanted creature
            # deals damage" - the permanent the Aura is attached to.
            if source.attached_to is None or event.subject_id != source.attached_to:
                return False
        elif not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_dealing_subtype(condition))
        ):
            return False
        if not _subject_has_required_counter(condition, game, event.subject_id):
            return False
        if "noncombat damage" in lowered:
            # CR 120.2a: damage not dealt as a result of combat.
            if event.combat:
                return False
        elif "combat damage" in lowered and not event.combat:
            return False
        if "to a planeswalker" in lowered and Type.PLANESWALKER not in (event.target_types or ()):
            return False
        if _DEALS_DAMAGE_TO_A_CREATURE.search(lowered) and (
            event.target_id is None or Type.CREATURE not in (event.target_types or ())
        ):
            return False
        if "to an opponent" in lowered:
            return event.player is not None and event.player != controller
        if "to a player" in lowered:
            return event.player is not None
        return True

    if ability.event is TriggerEvent.IS_SACRIFICED:
        if mine:
            return event.subject_id == source.id
        # Ashling, the Limitless: "Whenever you sacrifice a nontoken
        # Elemental, ...". "Elemental" is CR 205.3a's creature subtype, not
        # one of `_TYPE_WORDS`'s card types, so `_types_match` cannot see
        # "nontoken" at all - it has to be read the same way
        # ENTERS_THE_BATTLEFIELD's own guard reads it, off the event's actual
        # subject rather than a type word.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event in (TriggerEvent.BECOMES_TAPPED, TriggerEvent.BECOMES_UNTAPPED):
        if "equipped" in lowered and not _AN_EQUIPPED_CREATURE_RE.search(lowered):
            # Hawkeye's Bow's own "Whenever equipped creature becomes
            # tapped, ..." - the same CR 301.5a "equipped creature" look-up
            # `TAPPED_FOR_MANA`'s own "enchanted [land]" branch already
            # reads below, generalised to CR 703.4h's own Equipment case.
            return event.subject_id is not None and event.subject_id == source.attached_to
        if mine:
            if "teamwork cost" in lowered:
                # Agent Maria Hill's own "becomes tapped to pay a teamwork
                # cost" - narrower than a plain self-referential tap (CR
                # 400.7): the event has to be the specific reason named,
                # not merely that she became tapped at all.
                return event.subject_id == source.id and event.tapped_for_teamwork
            return event.subject_id == source.id
        # Captain America, Living Legend's own "a creature you control
        # becomes tapped[ during your turn]" - not self-referential at all
        # (CR 700.7 only reads "this creature"/the source's own name as
        # itself), so any creature the controller controls matches, gated
        # the ordinary "you control" way (`_controller_clause_holds`) and,
        # when the condition adds it, by whose turn it is right now
        # (`turn.active_player`, the same "during your turn" idiom read
        # elsewhere in this module).
        if not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(
                event.subject_subtypes, _required_becomes_tapped_subtype(condition)
            )
        ):
            return False
        if "during your turn" in lowered or "during their turn" in lowered:
            turn = game.turn
            if turn is None or turn.active_player != controller:
                return False
        return True

    if ability.event is TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE:
        # "When this creature is exiled from the battlefield" (Market Gnome),
        # a leaves-the-battlefield ability that looks back (CR 603.10a).
        if mine:
            return event.subject_id == source.id
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event is TriggerEvent.LIBRARY_BOTTOM_CHOSEN:
        # CR 701.22a's choice: "you choose" is the controller's own, "an
        # opponent chooses" anyone else's.
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return event.player == controller

    if ability.event is TriggerEvent.BECOMES_MONSTROUS:
        # CR 701.37a. Every printing in the pool - Polukranos, World Eater;
        # Arbor Colossus - prints only the self-referential "When [this
        # creature] becomes monstrous, ...", so only that form is read, the
        # same narrowing `BECOMES_TAPPED`/`BECOMES_UNTAPPED` apply above.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.TAPPED_FOR_MANA:
        # CR 106.12a. "Whenever enchanted Forest is tapped for mana" (Utopia
        # Sprawl) asks about the land the Aura is attached to, not the Aura
        # itself - `source.attached_to` is that land's id (CR 303.4).
        if "enchanted" in lowered:
            return event.subject_id is not None and event.subject_id == source.attached_to
        # "Whenever you tap a creature for mana" (Badgermole Cub, Leyline of
        # Abundance) - the controller's own tap, of a permanent of the named
        # type - and "you tap a Swamp for mana" (Nirkana Revenant), "a Forest is
        # tapped for mana" (Vernal Bloom), naming a land subtype instead.
        # Nothing in the pool prints the self-referential form.
        if "an opponent" in lowered:
            # Vorinclex, Voice of Hunger's own "Whenever an opponent taps a
            # land for mana, ..." - `_controller_clause_holds` only ever
            # recognises "an opponent **controls**"/"your opponents
            # **control**" (CR 613.5's board-control question), never
            # "taps", so this fell through its default "nothing named,
            # nothing required" branch and matched *any* tap, controller
            # included - the same "an opponent" fallback `TriggerEvent.
            # CAST_SPELL`/`DRAWS_A_CARD`/`GAINS_LIFE` already use for their
            # own branches.
            controller_ok = event.subject_controller is not None and (
                event.subject_controller != controller
            )
        else:
            controller_ok = _controller_clause_holds(
                condition, controller, event.subject_controller
            )
        return (
            controller_ok
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_tapped_subtype(condition))
        )

    if ability.event is TriggerEvent.TURNED_FACE_UP:
        # CR 702.37e/708.8. Brine Elemental's own "When this creature is
        # turned face up, ..." is self-referential (`mine`); Mastery of the
        # Unseen's "Whenever a permanent you control is turned face up, ..."
        # is not - it watches every permanent its controller turns face up,
        # not only itself, the same self-vs-general split every other event
        # branch in this function reads off `mine` rather than hardcoding.
        if event.subject_id == source.id and mine:
            return True
        # Pyrotechnic Performer's "Whenever this creature or another
        # creature you control is turned face up" names itself *and* every
        # other creature its controller turns up - the DIES branch's own
        # "another"/"or a" reading of a self-referential condition.
        if mine and "another" not in lowered and _SELF_OR_A_SUBJECT_RE.search(lowered) is None:
            return False
        subject_types = event.subject_types
        if subject_types is None and event.subject_id is not None:
            # The event carries no types: the permanent as it is now, just
            # turned up (CR 708.8: it is the same permanent, face up).
            turned = game.find_by_id(event.subject_id)
            if isinstance(turned, CardState) and turned.zone is Zone.BATTLEFIELD:
                subject_types = tuple(game.characteristics_of(turned).types)
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(subject_types, condition)

    if ability.event is TriggerEvent.DISCARDS_A_CARD:
        # Titanbones, Towering Heart's own "When you discard this card, ..."
        # - self-referential (CR 603.10a's look-back shape: the card is
        # already gone from the hand by the time this is checked), matched
        # against the whole batch a single discard instruction moved
        # (`GameEvent.discarded_ids`), since a discard fires once per
        # instruction rather than once per card. Checked ahead of the plain
        # controller-clause read below, which would otherwise treat "you
        # discard this card" as nothing narrower than "you discard".
        if mine:
            return source.id in event.discarded_ids
        # CR 701.9a. "Whenever you discard one or more cards" (Captain
        # Howler, Sea Scourge) asks about the controller's own discards -
        # `event.player` is who did the discarding, `_controller_clause_
        # holds`'s "you " prefix already reads "you discard" the same way
        # every other "you [verb]" condition does.
        if not _controller_clause_holds(condition, controller, event.player):
            return False
        return discard_occurrences(game, ability, source, event) > 0

    if ability.event is TriggerEvent.LORE_COUNTERS_ADDED:
        # CR 107.15a: always self-referential (a chapter symbol is never
        # printed any other way) and always about the Saga's own threshold,
        # not the event's raw amount - `ability.chapter` is `N`, `source.
        # lore_counters` is the total *after* `event.amount` were just put
        # on, and CR 107.15a's own "was less than N and became at least N"
        # is exactly the range `event.amount` spans.
        if event.subject_id != source.id or ability.chapter is None:
            return False
        added = event.amount or 0
        new_total = source.lore_counters
        old_total = new_total - added
        return old_total < ability.chapter <= new_total

    if ability.event is TriggerEvent.SCRY_OR_SURVEIL:
        # CR 701.22a/701.25a. "Whenever you scry or surveil" (Denzilore
        # Fatehold, Matoya, Archon Elder) is the only shape this pool prints.
        # "an opponent [verb]" is read directly - the same way `DRAWS_A_CARD`/
        # `GAINS_LIFE` read it - rather than through `_controller_clause_
        # holds`, which only recognises the "controls" phrasing ("an
        # opponent controls"), not an action verb like "scries"/"surveils".
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.LOYALTY_ABILITY_ACTIVATED:
        # CR 606.2/602.2. Ajani Unrelenting's "Whenever you activate a
        # loyalty ability" and Gideon the Oathless's "Whenever an opponent
        # activates a loyalty ability" - the subject is the permanent whose
        # ability was activated. "an opponent activates" is read the same
        # direct way `SCRY_OR_SURVEIL` just did, for the same reason: CR
        # 602.2's "activates" is not `_controller_clause_holds`'s "controls".
        if mine:
            return event.subject_id == source.id
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    return False


#: Loki, God of Mischief's own subject: "a **player or permanent** becomes the
#: target of an ability you control". The only non-self-referential
#: becomes-target subject read at all - anything else (a condition naming a
#: type, a controller, or a subtype for the *target*) is left unread, because
#: "you control" in such a condition can attach either to the target or to the
#: targeting object and reading it wrong fires a trigger that should not fire.
_ANY_TARGET_SUBJECT = re.compile(r"^(?:a player or permanent|a permanent or player)\b")


#: A becomes-target condition whose subject is an object described by type
#: and controller (CR 115.1's "object(s) ... the spell or ability will
#: affect"): "a creature you control", "another permanent an opponent
#: controls". `by` is the rest - "a spell", "a spell or ability an opponent
#: controls" - which is about the targeting object, not the targeted one.
_TARGETED_OBJECT = (
    r"(?:a|an|another) (?:[a-z]+ )*?"
    r"(?:creature|permanent|artifact|enchantment|land|planeswalker)"
    r"(?: spell)?(?: you control| an opponent controls)?"
)
#: "enchanted creature becomes the target of an Aura spell" (Brinebound Gift)
#: - the attached permanent as the targeted object; `by` is the rest.
_HOST_BECOMES_TARGET_RE = re.compile(
    r"^(?:enchanted|equipped) creature becomes the target of (?P<by>.+)$"
)
_OBJECT_TARGET_SUBJECT = re.compile(
    rf"^(?P<you>you or )?(?P<subject>{_TARGETED_OBJECT}(?: or {_TARGETED_OBJECT})*)"
    r" becomes the target of (?P<by>.+)$"
)


def _targeted_object_matches(
    game: "Game", subject: str, event: GameEvent, source: CardState, controller: str
) -> bool:
    """Whether the object a becomes-target event names fits `subject`'s type
    and controller words, read off the computed board (CR 613.5) - the
    targeted object is a permanent, so an animated land is a creature there
    and nowhere else.

    `subject` may join several objects with "or" (Surrak, Elusive Hunter's "a
    creature you control or a creature spell you control"); the event matches
    when any one of them fits. An alternative that says "spell" names an
    object on the stack (CR 601.2c lets a spell be targeted there) and one
    that does not names a permanent on the battlefield (CR 110.1), so a
    creature spell is never a "creature you control" and the reverse."""
    if event.subject_id is None:
        return False
    targeted = game.find_by_id(event.subject_id)
    if targeted is None:
        return False
    for alternative in subject.split(" or "):
        if alternative.startswith("another ") and event.subject_id == source.id:
            continue
        names_spell = " spell" in alternative
        if names_spell != (targeted.zone is Zone.STACK):
            continue
        if not names_spell and targeted.zone is not Zone.BATTLEFIELD:
            continue
        types = (
            game.characteristics_of(targeted).types
            if targeted.zone is Zone.BATTLEFIELD
            else targeted.types
        )
        if _types_match(tuple(types), alternative) and _controller_clause_holds(
            alternative, controller, event.subject_controller
        ):
            return True
    return False


def _target_subject_matches(condition: str) -> bool:
    """Whether a non-self-referential becomes-target condition's *subject* is
    one this module reads (CR 115.1's "object(s) and/or player(s) the spell or
    ability will affect")."""
    return _ANY_TARGET_SUBJECT.match(condition.lower().strip()) is not None


def _targeting_object_matches(game: "Game", condition: str, event: GameEvent) -> bool:
    """Whether the spell or ability that did the targeting is the kind this
    condition names.

    CR 115.1 lets either kind target, and the printed conditions distinguish
    them: ward says "a spell or ability" (CR 702.21a), Bonecrusher Giant says
    "a spell", Loki, God of Mischief says "an ability". `GameEvent.targeted_by`
    is the id of whichever it was, and CR 113.1c makes an ability on the stack
    an object with an id of its own, so the two are told apart by looking for
    that id among the abilities on the stack.

    An event with no `targeted_by` at all answers only a condition that names
    neither kind, since an unknown kind is not known to be the named one.
    """
    lowered = condition.lower()
    names_spell = "spell" in lowered
    names_ability = "ability" in lowered
    if not names_spell and not names_ability:
        return True
    if event.targeted_by is None:
        return False
    is_ability_object = any(item.id == event.targeted_by for item in game.abilities_on_stack)
    if names_spell and names_ability:
        return True
    if names_ability:
        return is_ability_object
    if is_ability_object:
        return False
    quality = _TARGETING_SPELL_QUALITY.search(lowered)
    if quality is None:
        return True
    # Brine Comber's "an Aura spell", Wild Defiance's "an instant or sorcery
    # spell" (CR 115.1): the targeting spell itself must have the quality.
    from ..next_spell import spell_has_quality

    spell = game.find_by_id(event.targeted_by)
    return spell is not None and spell_has_quality(spell, quality.group("quality"))


#: The quality a becomes-target condition puts on the targeting spell: "an
#: Aura spell", "an instant or sorcery spell" - the words between the article
#: and "spell", read by `machines/next_spell.spell_has_quality`.
_TARGETING_SPELL_QUALITY = re.compile(
    r"(?:^|\bthe target of )(?:an?|one or more) (?P<quality>(?!spell\b)[a-z][a-z ]*?) spells?\b"
)


#: The subject of a `_COUNTERS_PUT_CONDITION` that is not the source itself:
#: Botanical Brawler's "another permanent you control", Stalwart Successor's
#: "a creature you control" - a quality (`models.game._permanent_quality`)
#: of a permanent its controller controls, "another" excluding the source.
#: The article is optional for the plural form (Bioessence Hydra's "planeswalkers
#: you control").
_COUNTERS_PUT_ON_QUALITY_SUBJECT = re.compile(
    r"^(?:(?P<article>another|an?) )?(?P<quality>[a-z -]+?) you control$"
)


def _player_counter_kind(match: re.Match[str]) -> str:
    """The counter kind `_PLAYER_COUNTERS_PUT_CONDITION` matched, as the plain
    string `GameEvent.counter_kind`/`models.card_state.Counter.ENERGY` use."""
    return "energy" if match.group("symbol") is not None else match.group("kind")


#: A permanent returned from the battlefield to a hand - `TriggerEvent.
#: LEAVES_BATTLEFIELD_TO_HAND`, a leaves-the-battlefield event (CR 603.6c).
#: Azorius Aethermage's "a permanent is returned to your hand", Tameshi,
#: Reality Architect's "one or more noncreature permanents are returned to
#: hand", Justice, Vance Astrovik's "another nonland permanent you control is
#: returned to its owner's hand": a subject (read by `_returned_subject`),
#: whose hand, and an optional "from the battlefield" that only says out loud
#: what "permanent" already means.
_RETURNED_TO_HAND_CONDITION = re.compile(
    r"^(?P<subject>.+?) (?:is|are) returned to "
    r"(?P<hand>your hand|hand|its owner's hand|their owner's hand|their owners' hands)"
    r"(?: from the battlefield)?$"
)

#: The subject of `_RETURNED_TO_HAND_CONDITION`, split into its quantifier
#: and its description.
_RETURNED_SUBJECT = re.compile(
    r"^(?:(?P<plural>one or more)|(?P<another>another)|an?)"
    r" (?P<description>.+)$"
)
_RETURNED_CONTROLLER = re.compile(r"^(?P<types>.+?)(?: (?P<controller>you control))?$")
#: The words a returned-subject description may be built from - a card type
#: or its negation (CR 205.2a), and "permanent". Anything else (a subtype, a
#: colour, "token") is not read, so the whole condition stays unread rather
#: than matching more than it says.
_RETURNED_DESCRIPTION_WORD = re.compile(
    r"^(?:non-?)?(?:"
    + "|".join(_plural_type_word_pattern(word) for word in _TYPE_WORDS)
    + r"|permanents?)$"
)


def _returned_subject(condition: str) -> _ReturnedSubject | None:
    """`condition` read as a returned-to-hand condition, or None."""
    match = _RETURNED_TO_HAND_CONDITION.match(condition)
    if match is None:
        return None
    subject = _RETURNED_SUBJECT.match(match.group("subject"))
    if subject is None:
        return None
    description = _RETURNED_CONTROLLER.match(subject.group("description"))
    if description is None:
        return None
    words = description.group("types").replace(",", " ").split()
    if not words or any(
        _RETURNED_DESCRIPTION_WORD.match(word) is None for word in words if word != "or"
    ):
        return None
    return _ReturnedSubject(
        plural=subject.group("plural") is not None,
        another=subject.group("another") is not None,
        types=" ".join(words),
        controller=description.group("controller"),
        hand=match.group("hand"),
    )


def _returned_event_described(
    read: _ReturnedSubject,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether one returned-to-hand `event` is what `read` describes, for an
    ability of `source` controlled by `controller`."""
    if event.event is not TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND:
        return False
    if read.another and event.subject_id == source.id:
        return False
    if not _types_match(event.subject_types, read.types):
        return False
    # "your hand": the hand is its owner's (CR 108.3), which the event carries
    # as `player`; "its owner's hand" and bare "hand" are anybody's.
    if read.hand == "your hand" and event.player != controller:
        return False
    # "you control": control as it last existed on the battlefield (CR
    # 603.10a's look-back), captured before the move.
    return read.controller != "you control" or event.subject_controller == controller


def _returned_to_hand_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
    read: _ReturnedSubject,
) -> bool:
    """`_RETURNED_TO_HAND_CONDITION` against one returned permanent's event.

    CR 603.10a: a leaves-the-battlefield ability looks back in time, so every
    permanent returned by the same event is asked, the source included even
    though it is already in a hand (Azorius Aethermage's ruling: it triggers
    for its own return) - `Game.returned_to_hand_batch` is that event, and a
    source off the battlefield is heard only if it is one of them.

    CR 603.2c: the singular "a permanent is returned" triggers once per
    permanent the event moved; the plural "one or more ... are returned"
    triggers once for the whole event, so only the first described permanent
    in the batch answers for it.
    """
    batch = game.returned_to_hand_batch or (event,)
    if source.zone is not Zone.BATTLEFIELD and source.id not in {
        returned.subject_id for returned in batch
    }:
        return False
    if not _returned_event_described(read, source, controller, event):
        return False
    if not read.plural:
        return True
    first = next(
        returned
        for returned in (*batch, event)
        if _returned_event_described(read, source, controller, returned)
    )
    return first.subject_id == event.subject_id


#: CR 701.54e's "your Ring-bearer" as a trigger condition's subject.
_RING_BEARER_SUBJECT = re.compile(r"^your ring-bearer (?P<rest>.+)$", re.IGNORECASE)


#: "Whenever day becomes night or night becomes day" (Gavony Dawnguard,
#: Brimstone Vandal), and either half on its own. CR 731.1a's two phrases,
#: in either order.
_DAY_NIGHT_PHRASE = r"(?:day becomes night|night becomes day)"
_DAY_NIGHT_CONDITION = re.compile(rf"^{_DAY_NIGHT_PHRASE}(?: or {_DAY_NIGHT_PHRASE})?$")
_DAY_NIGHT_EVENTS: dict[str, ExtraTriggerEvent] = {
    "day becomes night": ExtraTriggerEvent.DAY_BECOMES_NIGHT,
    "night becomes day": ExtraTriggerEvent.NIGHT_BECOMES_DAY,
}


def _activated_source_subtype(types: str) -> str | None:
    """The one subtype an "an ability of `<a quality>`" names, lowercased,
    when that quality is a single subtype rather than card types - `None`
    for a card-type list `_types_match` reads."""
    from ...data.subtypes import canonical_subtype

    words = types.split()
    if len(words) != 2 or words[0].lower() not in {"a", "an"}:
        return None
    word = words[1]
    if word.lower() in _TYPE_WORDS:
        return None
    subtype = canonical_subtype(word)
    return subtype.lower() if subtype is not None else None


def _day_night_events_named(condition: str) -> frozenset[ExtraTriggerEvent]:
    """Every CR 731.1a change `condition` watches, or an empty set."""
    if _DAY_NIGHT_CONDITION.match(condition) is None:
        return frozenset()
    return frozenset(
        _DAY_NIGHT_EVENTS[phrase] for phrase in re.findall(_DAY_NIGHT_PHRASE, condition)
    )


#: CR 701.67c's own words, "whenever a player waterbends", read off however
#: the condition actually names the bending verbs - a bare "you waterbend"
#: (nothing printed prints this alone yet, but CR 701.67c's rule is written
#: as though something might) or Avatar Aang's own four-way "you waterbend,
#: earthbend, firebend, or airbend" list, in any order and with any subset
#: of the four bending verbs (CR 207.2's own listing-order convention is not
#: pinned to). Every named word maps onto its own `ExtraTriggerEvent`
#: member, and all four are raised (see those members' own docstrings).
_BENDING_WORD = r"(?:waterbend|earthbend|firebend|airbend)"
_BENDING_CONDITION = re.compile(
    rf"^you {_BENDING_WORD}(?:,\s*{_BENDING_WORD})*(?:,)?\s*(?:or\s+{_BENDING_WORD})?$",
    re.IGNORECASE,
)
_BENDING_EVENTS: dict[str, ExtraTriggerEvent] = {
    "waterbend": ExtraTriggerEvent.WATERBENDS,
    "earthbend": ExtraTriggerEvent.EARTHBENDS,
    "firebend": ExtraTriggerEvent.FIREBENDS,
    "airbend": ExtraTriggerEvent.AIRBENDS,
}


def _bending_events_named(condition: str) -> frozenset[ExtraTriggerEvent]:
    """Every bending event `_BENDING_CONDITION` names in `condition`, or an
    empty set if the condition is not that shape at all."""
    if _BENDING_CONDITION.match(condition) is None:
        return frozenset()
    words = re.findall(_BENDING_WORD, condition, re.IGNORECASE)
    return frozenset(_BENDING_EVENTS[word.lower()] for word in words)


def _unread_condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """`condition_matches` for an ability the parser left with `event=None`.

    The shapes read, and what each asks beyond the event itself:

    - **counters put on this permanent** (CR 122.6) - self-referential only,
      which is the only form printed in this pool, and the counter kind has to
      be the kind named.
    - **you get one or more [kind] counters** (CR 122.6, CR 109.5) -
      Fabrication Module's and Territorial Gorger's own "whenever you get one
      or more {E}": "you" is the ability's controller at the moment it
      triggered, and the counter kind has to be the kind named (CR 107.14
      normalises `{e}` to `"energy"`, the same string `Game.
      add_player_counters` stamps the event with for an ordinary `Counter.
      ENERGY` call).
    - **cards leave your graveyard** (CR 603.10a) - "your" is the ability's
      controller, and an optional type restriction ("an instant or sorcery
      card") is checked against what left.
    - **cards put into a library** (CR 401.1) - "from anywhere", by anyone,
      into any library: nothing further is asked.
    - **cards put into exile from graveyards and/or the battlefield during
      your turn** (CR 406.2) - either origin, and only while the ability's
      controller is the active player.
    - **you draw your Nth card in a turn** (CR 121.2) - the controller's own
      draws, counted over the turn.

    Anything else is False, the same safe direction `condition_matches` fails
    in for a condition it cannot read.
    """
    condition = ability.condition.lower().strip()
    mine = _self_referential(ability.condition, source.name, legendary=_is_legendary_source(source))

    match = _ONE_OR_MORE_BECOME_TAPPED_CONDITION.match(ability.condition.strip())
    if match is not None:
        if event.event is not ExtraTriggerEvent.PERMANENTS_TAPPED:
            return False
        return bool(_tapped_batch_matching(game, match.group("description"), controller))

    match = _ONE_OR_MORE_CARDS_INTO_YOUR_GRAVEYARD_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.PUT_INTO_GRAVEYARD:
            return False
        if match.group("your_turn") and game.active_player.username != controller:
            return False
        from_library = match.group("origin") == "your library"
        any_graveyard = match.group("whose") == "graveyards"
        for arrival in game.graveyard_batch:
            if arrival.player != controller and not any_graveyard:
                continue
            if from_library and arrival.origin_zone is not Zone.LIBRARY:
                continue
            card = game.find_by_id(arrival.card_id) if arrival.card_id else None
            if card is None or getattr(card, "token", False):
                continue  # CR 108.2: a token is not a card.
            if _types_match(tuple(card.types), match.group("types")):
                return True
        return False

    match = _SELF_PUT_INTO_GRAVEYARD_FROM_ANYWHERE_CONDITION.match(condition)
    if match is not None and mine:
        # CR 603.2/603.10: the source's own arrival at a graveyard, from any
        # zone (not only the battlefield, unlike `DIES`) - checked against
        # the object as it exists right now (CR 603.10's own default, since
        # this shape is not one of 603.10a's enumerated look-back
        # exceptions), which is exactly the graveyard card `game.
        # graveyard_batch` - the live batch this event is being matched
        # against - already names by id.
        if event.event is not ExtraTriggerEvent.PUT_INTO_GRAVEYARD:
            return False
        return any(arrival.card_id == source.id for arrival in game.graveyard_batch)

    match = _NTH_COUNTER_PUT_CONDITION.match(condition)
    if match is not None:
        # CR 122.6, as a threshold: `source`'s count of the named kind is the
        # total *after* `event.amount` were just put on, so the event crossed
        # N exactly when the count before it was below N.
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        if event.counter_kind != match.group("kind") or not mine:
            return False
        if event.subject_id != source.id:
            return False
        threshold = parse_ordinal(match.group("ordinal"))
        if threshold is None:
            return False
        new_total = source.counter_count(match.group("kind"))
        return new_total - (event.amount or 0) < threshold <= new_total

    match = _COUNTERS_PUT_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        # No kind ("one or more counters") is every kind (CR 122.1).
        if match.group("kind") is not None and event.counter_kind != match.group("kind"):
            return False
        # CR 122.6 is about counters put on *an object*: the source itself
        # ("on this creature"), or any permanent its controller controls with
        # the named quality ("on another permanent you control").
        subject = _COUNTERS_PUT_ON_QUALITY_SUBJECT.match(match.group("subject"))
        if subject is None:
            return mine and event.subject_id == source.id
        from ...models.game import _permanent_quality

        quality = _permanent_quality(subject.group("quality"))
        if quality is None:
            return False
        if subject.group("article") == "another" and event.subject_id == source.id:
            return False
        permanent = game.find_by_id(event.subject_id) if event.subject_id else None
        if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
            return False
        if game.controller_of(permanent).username != controller:
            return False
        return quality(game.characteristics_of(permanent))

    match = _YOU_PUT_A_COUNTER_ON_QUALITY_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        kind = match.group("kind")
        if kind is not None and event.counter_kind != kind:
            return False
        from ...models.game import _permanent_quality

        quality = _permanent_quality(match.group("quality"))
        if quality is None:
            return False
        permanent = game.find_by_id(event.subject_id) if event.subject_id else None
        if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
            return False
        if match.group("article") == "another" and permanent.id == source.id:
            return False
        # CR 122.6a: "you put" is whoever put them - `event.player`, the
        # putter `Game._emit_counters_put` records - so an opponent putting a
        # counter on your creature does not count. "you control" then also
        # asks whose permanent it landed on; absent (Ant-Man's own bare "a
        # creature"), any creature at all qualifies.
        if event.player != controller:
            return False
        if (
            match.group("yours") is not None
            and game.controller_of(permanent).username != controller
        ):
            return False
        return quality(game.characteristics_of(permanent))

    if _OPPONENTS_ARE_ATTACKED_CONDITION.match(condition):
        # CR 603.2c: the same subject-less, once-per-declaration event "you
        # attack" fires - only `controller`'s own declaration counts, and
        # whether it happened at all is `event.subject_id is None`.
        if event.event is not TriggerEvent.ATTACKS or event.subject_id is not None:
            return False
        if event.player != controller:
            return False
        from ..combat import defending_player

        opponents = {player.username for player in game.players if player.username != controller}
        for attack in game.combat.attacks:
            attacker = game.find_by_id(attack.attacker_id)
            if not isinstance(attacker, CardState):
                continue
            if game.controller_of(attacker).username != controller:
                continue
            if defending_player(game, attack.defender) in opponents:
                return True
        return False

    match = _LOYALTY_COUNTERS_PUT_ON_PLANESWALKER_CONDITION.match(condition)
    if match is not None:
        # CR 122.6/606.4: any planeswalker, not only the source - the
        # subject here is whichever permanent the loyalty counters actually
        # landed on, read straight off the event the same way the
        # self-referential branch above reads it, minus the self-reference.
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        if event.counter_kind != "loyalty":
            return False
        if Type.PLANESWALKER not in (event.subject_types or ()):
            return False
        if match.group("who") == "you put":
            return event.subject_controller == controller
        return event.subject_controller is not None and event.subject_controller != controller

    # The Great Goblin's own "you put one or more counters on a Goblin, Orc,
    # or Army you control" - matched against `ability.condition` unlowered
    # (not the `condition` local above), the same reason `_DYING_SUBTYPE`'s
    # own subject is read off the unlowered text from `condition_matches`
    # itself: Oracle's subtype capitalisation is the only thing telling a
    # subtype from a card-type word.
    description_match = _COUNTERS_PUT_ON_DESCRIPTION_CONDITION.match(ability.condition.strip())
    if description_match is not None:
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        subtypes = _parse_subtype_list(description_match.group("subtypes"))
        if not _subtype_matches(event.subject_subtypes, subtypes):
            return False
        return event.subject_controller == controller

    match = _PLAYER_COUNTERS_PUT_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.PLAYER_COUNTERS_PUT:
            return False
        if event.counter_kind != _player_counter_kind(match):
            return False
        # CR 109.5: "you" on a triggered ability's own text is the ability's
        # controller at the moment it triggered - an opponent's own energy
        # (or any other kind) is a real `PLAYER_COUNTERS_PUT` event, just not
        # one that matches "whenever *you* get".
        return event.player == controller

    match = _LEAVES_GRAVEYARD_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.LEAVES_GRAVEYARD:
            return False
        # "your graveyard" / "an opponent's graveyard": whose graveyard the
        # card left, which the event carries as `player` (the graveyard's
        # owner), not the controller of whatever effect moved it.
        if (event.player == controller) != (match.group("whose") == "your"):
            return False
        types = match.group("types")
        return types is None or _types_match(event.subject_types, types)

    if _PUT_INTO_LIBRARY_CONDITION.match(condition):
        return event.event is ExtraTriggerEvent.PUT_INTO_LIBRARY

    if _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION.match(condition):
        if event.event not in (
            ExtraTriggerEvent.EXILED_FROM_GRAVEYARD,
            TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
        ):
            return False
        # "during your turn" - read off the live turn machine, the same way
        # the CAST_SPELL branch already reads Ral, Monsoon Mage's identical
        # clause, since the condition is checked as the event fires.
        turn = getattr(game, "turn", None)
        return turn is not None and turn.active_player == controller

    match = _NTH_DRAW_CONDITION.match(condition)
    if match is not None:
        if event.event is not TriggerEvent.DRAWS_A_CARD or event.player is None:
            return False
        if match.group("who") == "you":
            if event.player != controller:
                return False
        elif match.group("who") == "a player":
            pass
        elif event.player == controller:
            # "an opponent draws their Nth card each turn" (Gleaming
            # Splendor) - never the ability's own controller.
            return False
        ordinal = parse_ordinal(match.group("ordinal"))
        if ordinal is None:
            return False
        # CR 121.2 makes each card its own draw, so the ordinal is a count of
        # this player's draws so far this turn - a running total nothing in
        # `models/game.py` keeps yet (`Game.draw_cards` emits one event per
        # card and counts nothing). Without it the answer is not known, and an
        # unknown answer does not trigger.
        drawn = getattr(game, "cards_drawn_this_turn", None)
        if not isinstance(drawn, dict):
            return False
        return drawn.get(event.player, 0) == ordinal

    if _LAND_ADDED_CHOSEN_MANA_CONDITION.match(condition):
        # CR 605.1b's triggered mana ability: Caged Sun's own condition, read
        # off `GameEvent.mana_added` (the colours CR 106.12a's event now
        # carries) and `CardState.choice` (CR 614.12a's as-enters choice).
        if event.event is not ExtraTriggerEvent.MANA_ADDED:
            return False
        if event.subject_controller != controller:
            return False  # "causes **you** to add".
        if Type.LAND not in (event.subject_types or ()):
            return False  # "a **land's** ability".
        chosen = source.choice
        if chosen is None or chosen.kind is not ChoiceKind.COLOR:
            # CR 106.5: with no choice recorded there is no "chosen color" for
            # the condition to be about, so it does not trigger.
            return False
        return any(color.value == chosen.value for color in event.mana_added)

    play_or_cast = _PLAY_A_LAND_OR_CAST_CONDITION.match(condition.lower().strip())
    if play_or_cast is not None:
        # CR 601.1a: playing a card is playing it as a land (CR 116.2a) or
        # casting it as a spell (CR 601.2). Both events carry the zone the
        # card was played out of (`GameEvent.origin_zone`), which is what a
        # "from ..." restriction reads (CR 603.2: it is part of the event).
        if event.event not in (TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND):
            return False
        who = play_or_cast.group("who")
        if who == "you" and event.player != controller:
            return False
        if who == "an opponent" and (event.player is None or event.player == controller):
            return False
        return _origin_zone_matches(event.origin_zone, play_or_cast.group("origin") or "")

    loses_life = _LOSES_LIFE_CONDITION.match(condition)
    if loses_life is not None:
        if event.event is not TriggerEvent.LOSES_LIFE or event.player is None:
            return False
        who = loses_life.group("who")
        if who == "you":
            return event.player == controller
        if who == "an opponent":
            return event.player != controller
        return True  # "a player" - anyone, CR 119.3.

    if _PLAY_A_CARD_EXILED_WITH_CONDITION.match(condition):
        # CR 601.1a: "Playing a card" means playing it as a land or casting it
        # as a spell. "You" is this
        # ability's controller, and the card has to have come out of *this*
        # object's own CR 607.2a pile - the annotation the play event carries
        # from before CR 400.7 wiped it, matched against this incarnation of
        # the source (a Visionary that left and came back reads nothing its
        # earlier self exiled).
        if event.event not in (TriggerEvent.CAST_SPELL, ExtraTriggerEvent.PLAYS_LAND):
            return False
        if event.player != controller:
            return False
        annotation = event.origin_exile_annotation
        return annotation is not None and annotation.links_to(source.id, source.zone_change_stamp)

    if _UNTAPPED_DURING_UNTAP_STEP_CONDITION.match(condition):
        # CR 502.3: only the active player untaps in their untap step, so
        # "you" and "your untap step" are both the event's own player.
        return (
            event.event is ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP
            and event.player == controller
        )

    if _TIME_COUNTER_REMOVED_WHILE_EXILED_CONDITION.match(condition):
        return (
            event.event is ExtraTriggerEvent.TIME_COUNTER_REMOVED and event.subject_id == source.id
        )

    if _LAST_TIME_COUNTER_CONDITION.match(condition):
        # CR 702.62a's third ability ("this card") and CR 702.63a's own third
        # ability ("this permanent") - both name the source itself and
        # nothing else. `machines/casting.remove_suspend_time_counter` and
        # `machines/keywords._remove_vanishing_time_counter` each raise the
        # event only for the object they just took the last counter off, so
        # two cards or permanents reaching zero in the same upkeep each match
        # only their own.
        return (
            event.event is ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED
            and event.subject_id == source.id
        )

    if last_counter := _LAST_COUNTER_CONDITION.match(condition):
        # The source's own count of that kind just reached zero.
        return (
            event.event is ExtraTriggerEvent.LAST_COUNTER_REMOVED
            and event.subject_id == source.id
            and event.counter_kind == last_counter.group("kind")
        )

    if _REVEALED_THIS_WAY_CONDITION.match(condition):
        # CR 702.94a / CR 607.2h: "this card ... this way" - the source
        # itself, revealed by its own miracle ability, by the player who drew
        # it ("you").
        return (
            event.event is ExtraTriggerEvent.REVEALED_FOR_MIRACLE
            and event.subject_id == source.id
            and event.player == controller
        )

    if _REVEALED_FIRST_DRAW_CONDITION.match(condition):
        # CR 607.2h: only a reveal the static "reveal the first card you draw
        # each turn" made, by the controller of this source, of an instant or
        # sorcery card.
        if event.event is not ExtraTriggerEvent.REVEALED_FIRST_DRAW or event.player != controller:
            return False
        if event.subject_card is None:
            return False
        revealed = set(event.subject_card.types)
        if "land card" in condition:
            return (Type.LAND in revealed) != condition.startswith("you reveal a nonland")
        return bool({Type.INSTANT, Type.SORCERY} & revealed)

    if _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE.fullmatch(condition):
        # CR 603.2c: one trigger per step's damage to a player, however many
        # of the described creatures dealt it.
        if event.event is not ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS:
            return False
        return bool(batched_combat_damage_sources(game, ability.condition, controller, event))

    returned = _returned_subject(condition)
    if returned is not None:
        return _returned_to_hand_matches(game, ability, source, controller, event, returned)

    match = _CLASS_BECOMES_LEVEL_CONDITION.match(condition)
    if match is not None:
        # CR 716.2a: the level of *this* Class, and exactly that level - a
        # level 3 bar resolving is not this Class becoming level 2 again.
        return (
            event.event is ExtraTriggerEvent.CLASS_BECOMES_LEVEL
            and event.subject_id == source.id
            and event.amount == int(match.group("level"))
            and _self_referential(
                match.group("subject"), source.name, legendary=_is_legendary_source(source)
            )
        )

    match = _CYCLE_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.CYCLED:
            return False
        if not _acting_player_matches(match.group("who"), controller, event.player):
            return False
        # CR 702.29c's "this card" is the source itself; "another card" is
        # anything but it.
        if match.group("what") == "this card":
            return event.subject_id == source.id
        if match.group("what") == "another card":
            return event.subject_id != source.id
        return True

    match = _FORETELL_CONDITION.match(condition)
    if match is not None:
        return event.event is ExtraTriggerEvent.FORETOLD and _acting_player_matches(
            match.group("who"), controller, event.player
        )

    match = _ABILITY_ACTIVATED_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.ABILITY_ACTIVATED:
            return False
        if not _acting_player_matches(match.group("who"), controller, event.player):
            return False
        keyword = match.group("keyword")
        if keyword is not None:
            return event.keyword_action == keyword.lower()
        if match.group("not_mana") is not None and event.mana_ability:
            return False
        types = match.group("types")
        if types is None:
            return True
        # CR 109.2: a type named without "card", "spell" or "source" means a
        # permanent of that type on the battlefield - a creature card cycled
        # from a hand is not "a creature".
        if event.origin_zone is not Zone.BATTLEFIELD:
            return False
        subtype = _activated_source_subtype(types)
        if subtype is not None:
            # CR 205.3: "an Elemental" (Ceaseless Searblades) - a subtype,
            # read off the source as it was activated.
            return subtype in {word.lower() for word in event.subject_subtypes or ()}
        return _types_match(event.subject_types, types)

    if _RING_TEMPTS_YOU_CONDITION.match(condition):
        # CR 701.54d: "Whenever the Ring tempts you" - the ability's own
        # controller has to be the player tempted.
        return event.event is ExtraTriggerEvent.RING_TEMPTS_YOU and event.player == controller

    if _CRIME_COMMITTED_CONDITION.match(condition):
        # CR 700.13: "you commit a crime" - always the ability's own
        # controller, never an opponent's crime.
        return event.event is ExtraTriggerEvent.CRIME_COMMITTED and event.player == controller

    match = _SEARCHES_LIBRARY_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.SEARCHES_LIBRARY or event.player is None:
            return False
        who = match.group("who")
        if who == "you":
            return event.player == controller
        if who == "an opponent":
            return event.player != controller
        return True  # "a player" - anyone.

    match = _ROLLS_DICE_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.ROLLS_DICE or event.player is None:
            return False
        who = match.group("who")
        if who == "you":
            return event.player == controller
        if who == "an opponent":
            return event.player != controller
        return True  # "a player" - anyone.

    if _DOOR_UNLOCKED_CONDITION.match(condition):
        # CR 709.5h: the permanent this ability is printed on, and only the
        # door it is printed on (`BaseAbility.face`) - Ritual Chamber's own
        # "you unlock this door" never fires for Unholy Annex's door.
        return (
            event.event is ExtraTriggerEvent.DOOR_UNLOCKED
            and event.subject_id == source.id
            and event.subject_name == ability.face
        )

    if _SOLVE_A_CASE_CONDITION.match(condition):
        # CR 719.3a-b: you solve a Case when a Case you control becomes
        # solved; the event's player is that Case's controller.
        return event.event is ExtraTriggerEvent.CASE_SOLVED and event.player == controller

    if _FINAL_CHAPTER_RESOLVES_CONDITION.match(condition):
        # CR 714.2e: "a Saga you control" - the event's player is the Saga's
        # controller, and only its final chapter ability raises the event.
        return (
            event.event is ExtraTriggerEvent.FINAL_CHAPTER_RESOLVED and event.player == controller
        )

    if _ENLISTS_A_CREATURE_CONDITION.match(condition) and mine:
        # CR 702.154b: Guardian of New Benalia's own "Whenever this creature
        # enlists a creature, scry 2." - self-referential only (CR 700.7's
        # "this creature" is the enlisting creature), so the event's own
        # subject has to be this source, not any other enlist on the board.
        return event.event is ExtraTriggerEvent.ENLISTS and event.subject_id == source.id

    bending_events = _bending_events_named(condition)
    if bending_events:
        # CR 701.67c: "whenever a player waterbends" - "you", so the event's
        # own player has to be the ability's controller, exactly like every
        # other "whenever you `<verb>`" condition this module reads.
        return event.event in bending_events and event.player == controller

    day_night_events = _day_night_events_named(condition)
    if day_night_events:
        # CR 731.1a: the game's own designation changed - nobody's, so there
        # is no player or subject to compare.
        return event.event in day_night_events

    from ..counter_effects import counter_condition_matches

    return bool(counter_condition_matches(game, ability, source, controller, event))


def _acting_player_matches(who: str, controller: str, actor: str | None) -> bool:
    """Whether `actor` is the "you" / "a player" / "an opponent" a condition
    names, relative to the ability's `controller` (CR 109.5)."""
    if actor is None:
        return False
    if who == "you":
        return actor == controller
    if who == "an opponent":
        return actor != controller
    return True


def _step_matches(
    condition: str, controller: str, event: GameEvent, source: CardState | None = None
) -> bool:
    """ "At the beginning of [whose] [step]" against the step that just began."""
    lowered = condition.lower()
    if "main phases" in lowered:
        # CR 505.1: "each of your main phases" is both of them - Frontier
        # Siege's Khans half adds its mana at the start of the precombat and
        # of the postcombat main phase alike.
        if event.step not in (Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN):
            return False
    else:
        step = next((step for phrase, step in _STEP_PHRASES if phrase in lowered), None)
        if step is None or step is not event.step:
            return False
    if "the chosen player" in lowered:
        # The Rack's "At the beginning of the chosen player's upkeep": the
        # player its as-enters choice named (`CardState.chosen_player`).
        return (
            source is not None
            and event.player is not None
            and event.player == source.chosen_player
        )
    if "your" in lowered:
        return event.player == controller
    if "opponent" in lowered:
        # "At the beginning of each opponent's upkeep" (Sheoldred, Whispering
        # One; Urabrask, Heretic Praetor) - CR 102.2's opponent, not "whoever's
        # step it is": without this, the bare "each upkeep" default just below
        # matched the ability's own controller's step too, firing the trigger
        # on the wrong player's turn as well as the right one.
        return event.player is not None and event.player != controller
    # "each upkeep", "the end step" - whoever's step it is.
    return True


#: Alania, Divergent Storm's shape: "it's the first instant spell, the first
#: sorcery spell, or the first Otter spell other than Alania you've cast this
#: turn". The excluded name is optional - most cards of this shape (there is
#: only the one in the pool) name themselves so a recast copy of the permanent
#: doesn't retroactively make itself not-the-first.
_FIRST_SPELL_THIS_TURN = re.compile(
    r"^it'?s (?P<segments>.+?)"
    r"(?: other than (?P<excluded>[a-z][a-z' ]*?))?"
    r" you(?:'ve| have)? cast this turn$"
)
_FIRST_SPELL_SEGMENT = re.compile(r"^(?:the )?first (?P<word>[a-z]+) spell$")


def _first_spell_this_turn_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """CR 603.4: "if it's the first [type] spell ... you've cast this turn".

    Returns `None`, not False, when the clause isn't this shape at all, so the
    caller can tell "read and false" from "not this pattern" - and False, a
    read answer, when it is this shape but there is no cast event to name
    the spell "it" means.
    """
    match = _FIRST_SPELL_THIS_TURN.match(clause)
    if match is None:
        return None
    segments = [piece.strip() for piece in re.split(r",|\bor\b", match.group("segments"))]
    words: list[str] = []
    for segment in segments:
        if not segment:
            continue
        segment_match = _FIRST_SPELL_SEGMENT.match(segment)
        if segment_match is None:
            return None
        words.append(segment_match.group("word"))
    if not words:
        return None
    if event is None or event.subject_card is None:
        return False

    excluded = (match.group("excluded") or "").strip()
    controller = source.controller or game.active_player.username
    subject_types = event.subject_types or ()
    subject_subtypes = event.subject_subtypes or ()
    cast_this_turn = game.spells_cast_this_turn.get(controller, [])

    def _category_matches(word: str, types: tuple[Type, ...], subtypes: tuple[str, ...]) -> bool:
        type_ = _TYPE_WORDS.get(word)
        if type_ is not None:
            return type_ in types
        return any(subtype.lower() == word for subtype in subtypes)

    for word in words:
        if not _category_matches(word, subject_types, subject_subtypes):
            continue
        earlier = [
            state
            for state in cast_this_turn
            if state.id != event.subject_id
            and not (excluded and excluded in state.name.lower())
            # `state.types`/`state.subtypes` are `CardState`'s own up-face-aware
            # read (CR 712.8f) rather than `state.card`'s front-face-only one -
            # never actually different for a *cast* spell, since a card is
            # never cast as its MDFC land face, but reading the same field the
            # rest of this module now reads is what keeps this in step with it.
            and _category_matches(word, state.types, state.subtypes)
        ]
        if not earlier:
            return True
    return False


#: `machines/teamwork.py`'s own intervening *if*, the same shape as
#: `conditions/cast_record.py`'s kicked reader for a card whose "If this spell was cast using
#: teamwork" rider is written as a trailing intervening if instead of a
#: leading "If ..." sentence - none in this pool yet, but the reader is
#: general rather than tied to the one shape the pool happens to print.
_CAST_USING_TEAMWORK_CLAUSE = re.compile(r"^this spell was cast using teamwork$")

#: Captain America, Living Legend's own "if it's the first time that
#: creature has become tapped this turn" - `abilities._parse_triggered`
#: splits this off as `intervening_if` the ordinary CR 603.4 way, since the
#: sentence is written as a plain "Whenever ..., if ..., ..." trigger.
_FIRST_TIME_TAPPED_THIS_TURN_CLAUSE = re.compile(
    r"^it'?s the first time (?:that creature|it) has become tapped this turn$"
)

#: CR 702.56a's own intervening *if*, written out by
#: `machines/keywords._replicate_ability` - "a replicate cost was paid for it".
_REPLICATE_CLAUSE = re.compile(r"^a replicate cost was paid for it$")

#: CR 702.153a's own intervening *if*, written out by
#: `machines/keywords._casualty_ability` - "a casualty cost was paid for it".
_CASUALTY_CLAUSE = re.compile(r"^a casualty cost was paid for it$")
#: `machines/keywords._conspire_ability` - "its conspire cost was paid".
_CONSPIRE_CLAUSE = re.compile(r"^its conspire cost was paid$")

#: CR 601.2h's "no mana was spent to cast it" (Vexing Bauble) and "[mana
#: symbols] was spent to cast it" (Wistfulness's "{G}{G}", Drowner of Truth's
#: "{C}") - both always phrased as "... to cast it" in the pool, never "...
#: to cast this spell/creature".
#: Roiling Vortex spells the event's spell out: "if no mana was spent to cast
#: that spell" - the same anaphor as Vexing Bauble's "it".
_NO_MANA_SPENT_CLAUSE = re.compile(r"^no mana was spent to cast (?:it|that spell)$")
_MANA_SPENT_CLAUSE = re.compile(
    r"^(?P<symbols>(?:\{[wubrgc]\})+) was spent to cast (?:it|that spell)$"
)
_MANA_SYMBOL_LETTER = re.compile(r"\{([wubrgc])\}")
#: "mana from a Treasure was spent to cast it" (Smaug, Wicked Worm; Hired
#: Hexblade) - CR 601.2h's spent mana by its CR 106.3 source,
#: `CastRecord.treasure_mana_spent`.
_TREASURE_MANA_SPENT_CLAUSE = re.compile(
    r"^mana from a treasure was spent to cast (?:it|that spell)$"
)

#: CR 207.2c's Revolt ability word, both printed phrasings in the pool:
#: Renegade Rallier's and Fatal Push's own "a permanent left the battlefield
#: under your control this turn", and the generic reminder-text order
#: "a permanent you controlled left the battlefield this turn".
#: Pack tactics (CR 207.2c's ability word): "you attacked with creatures
#: with total power N or greater this combat" - Werewolf Pack Leader, Gnoll
#: Hunter.
_PACK_TACTICS_CLAUSE = re.compile(
    r"^you attacked with creatures with total power (?P<threshold>\d+) or greater this combat$"
)

_REVOLT_CLAUSES = frozenset(
    {
        "a permanent left the battlefield under your control this turn",
        "a permanent you controlled left the battlefield this turn",
    }
)
_COLOR_LETTERS: dict[str, Color] = {
    "w": Color.WHITE,
    "u": Color.BLUE,
    "b": Color.BLACK,
    "r": Color.RED,
    "g": Color.GREEN,
    "c": Color.COLORLESS,
}


#: CR 702.191a's increment clause - "[this permanent is a creature and ]the
#: amount of mana [you ]spent[ to cast that spell] is greater than this
#: creature's power or [this creature's ]toughness" - the rule's wording and
#: the reminder text's.
_INCREMENT_CLAUSE = re.compile(
    r"^(?P<creature>this permanent is a creature and )?the amount of mana (?:you )?spent"
    r"(?: to cast that spell)? is greater than this creature's power or"
    r" (?:this creature's )?toughness$"
)


def _cast_record_for_clause(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None",
    source_stamp: UUID | None = None,
) -> "CastRecord | None":
    """The `CastRecord` a mana-spent or kicked clause's "it" refers to, or
    `None` if there is no longer one to read.

    A self-referential clause - Sowing Mycospawn's "if it was kicked" ("it" is
    "this spell"), Wistfulness's and Drowner of Truth's "if ... was spent to
    cast it" ("it" is "this creature"/"this spell") - means the ability's own
    source, whose record follows it from the stack onto the battlefield (CR
    400.7d) and no further: `Game.cast_record_of` keys it by the object, so a
    permanent that left and returned is a new object with no record (CR 400.7).
    Vexing Bauble's "Whenever a player casts a spell, if no mana was spent to
    cast it" is not self-referential at all: "it" is *that* spell, the trigger
    event's own subject, not Vexing Bauble itself.

    CR 601.2h's spend is recorded by `Game.note_cast` before the CAST_SPELL
    event that reaches this is ever emitted (`Game.put_on_stack`), so the
    record exists by the time this is first asked about, whichever object it
    belongs to. It does not necessarily still exist by CR 608.2a's *recheck*:
    `Game.resolve_top` (both the successful and the fizzled branches) and
    `Game.counter` all discard a spell's `CastRecord` once nothing on the
    normal path will read it again, but an intervening *if* one stack level up
    can still be waiting to ask about that exact spell after it fizzles or is
    countered. Reading `Game.cast_records` directly here, instead of going
    through `Game.cast_record`'s empty-record default, is what keeps "nobody
    ever recorded a cast" and "the record was cleaned up" both distinguishable
    from a genuine "no mana was spent" - the caller is the one that turns a
    missing record into a fail-closed `InterveningIfNotice` rather than a
    silent, wrong-object-shaped true.
    """
    if event is not None and not _self_referential(
        ability.condition, source.name, legendary=_is_legendary_source(source)
    ):
        subject = game.find_by_id(event.subject_id) if event.subject_id else None
        if subject is None:
            return None
        return game.cast_record_of(subject)
    if source_stamp is not None:
        # CR 113.7a, CR 608.2h: the recheck on resolution reads the object
        # the ability came from, even if that object has since moved on.
        return game.cast_record_as_last_known(source_stamp)
    return game.cast_record_of(source)


#: Ruby, Daring Tracker's own clause, split off `condition` into
#: `intervening_if` by `abilities._parse_triggered`'s "while" handling: "you
#: control a creature with power 4 or greater". CR 208.1 is power; the
#: three comparison shapes mirror `_mana_value_comparison`'s above, reused
#: here for a different characteristic rather than duplicated wholesale since
#: the vocabulary ("or greater"/"or less"/a bare number) is the same across
#: both.
_CONTROL_CREATURE_WITH_POWER = re.compile(
    r"^you control a creature with power (?P<threshold>\d+)"
    r"(?P<comparator> or greater| or less)?$"
)


def _control_creature_with_power_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 208.1's power, compared against every creature the controller has on
    the battlefield right now (CR 613.5's `characteristics_of`, not the
    printed `CardState.power`, so a pumped or shrunk creature is read
    correctly). `None`, not False, when `clause` isn't this shape at all."""
    match = _CONTROL_CREATURE_WITH_POWER.match(clause)
    if match is None:
        return None
    threshold = int(match.group("threshold"))
    comparator = (match.group("comparator") or "").strip()
    ops = {
        "or greater": operator.ge,
        "or less": operator.le,
        "": operator.eq,
    }
    op = ops[comparator]
    controller = source.controller or game.active_player.username
    for state in game.permanents_controlled_by(controller):
        characteristics = game.characteristics_of(state)
        if characteristics.is_creature and op(characteristics.power or 0, threshold):
            return True
    return False


#: Might Makes Right's "you control each creature on the battlefield with
#: the greatest power": every creature tied for the highest power among all
#: creatures on the battlefield (CR 208.1, computed per CR 613) is yours.
_CONTROL_EACH_GREATEST_POWER = re.compile(
    r"^you control each creature on the battlefield with the greatest power$"
)


def _control_each_greatest_power_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_CONTROL_EACH_GREATEST_POWER`'s shape, or `None` if the clause is not
    it. False with no creature on the battlefield at all: there is then no
    creature with the greatest power for "each" to be true of, and the
    ability's own point (you have the biggest creature) does not hold."""
    if _CONTROL_EACH_GREATEST_POWER.match(clause) is None:
        return None
    controller = source.controller or game.active_player.username
    creatures = []
    for state in game.battlefield:
        characteristics = game.characteristics_of(state)
        if characteristics.is_creature:
            creatures.append((characteristics.power or 0, state))
    if not creatures:
        return False
    greatest = max(power for power, _ in creatures)
    return all(state.controller == controller for power, state in creatures if power == greatest)


#: "there are N or more permanent cards in your graveyard" - the "descend
#: 4"/"descend 8" ability words' own condition (CR 207.2c) read as a plain
#: triggered ability's intervening *if* rather than as `machines/layers.py`'s
#: gated-self-static shape: Coati Scavenger's "When this creature enters, if
#: there are four or more permanent cards in your graveyard, return target
#: permanent card from your graveyard to your hand." and Starving Revenant's
#: "Whenever you draw a card, if there are eight or more permanent cards in
#: your graveyard, target opponent loses 1 life and you gain 1 life." -
#: distinct from CR 700.11's own per-turn "you descended this turn" event
#: count (the clause immediately below): the two mechanics only share the
#: English word "descend". This one is a live graveyard count, re-checked at
#: CR 603.4 and again at CR 608.2a, the same live count `machines/layers.py`'s
#: `count_permanent_cards` answers for the static shape.
_DESCEND_PERMANENT_CARD_COUNT_CLAUSE = re.compile(
    rf"^there are (?P<n>{COUNT}) or more permanent cards in your graveyard$"
)


def _descend_permanent_card_count_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """`_DESCEND_PERMANENT_CARD_COUNT_CLAUSE`'s shape, or `None` when `clause`
    is not it. `count_permanent_cards` is imported locally, the same way
    `intervening_if_holds` already imports `meld_condition_holds` from
    `.meld` - `machines/layers.py` imports `machines/combat.py`, which
    imports this module for `GameEvent`, so a module-level import here would
    be circular.
    """
    match = _DESCEND_PERMANENT_CARD_COUNT_CLAUSE.fullmatch(clause)
    if match is None:
        return None
    threshold = parse_count(match.group("n"), article=False)
    if threshold is None:
        # Not actually reachable: every string `_DESCEND_PERMANENT_CARD_
        # COUNT_CLAUSE` accepts for its `n` group is itself a `COUNT`
        # alternative, and `parse_count` (with `article=False`, matching how
        # this group was matched) is total over that vocabulary. `None` here
        # would mean the two had drifted apart - return `None` rather than a
        # `bool` so the caller's own `_fail_closed` catches that drift
        # instead of this function silently answering for a shape it does
        # not actually recognise.
        return None

    from ..layers import count_permanent_cards

    controller = source.controller or game.active_player.username
    return count_permanent_cards(game.player(controller).graveyard) >= threshold


#: CR 702.176a's own intervening *if*, read over the keyword and the counter
#: kind rather than over one card: "this permanent's impending cost was paid
#: and it has a time counter on it". The paid half is
#: `CardState.cast_with_keyword`, which belongs to this object only (CR
#: 400.7), the same way `Game.cast_record_of` answers only for this object.
_PERMANENT_KEYWORD_COST_PAID_WITH_COUNTER = re.compile(
    r"^this permanent's (?P<keyword>[a-z]+) cost was paid and it has an? "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counter on it$"
)

#: "it had power greater than `<name>`'s power" - Drizzt Do'Urden's own dies
#: trigger, `<name>` printed as the card's own name (CR 201.5) rather than
#: CR 700.7's "this creature". `clause` arrives lowercased (see below), so
#: `<name>` is matched case-insensitively and checked against the source's
#: own printed name the same way `_parse_may_exile_self_then_return_clause`
#: already does for its own CR 201.5 self-reference.
_POWER_GREATER_THAN_SELF_RE = re.compile(r"^it had power greater than (?P<name>.+)'s power$")


def _opponent_cast_color_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Sandstalker Moloch's own intervening if: "if an opponent cast a blue
    and/or black spell this turn" - the identical board fact Veil of
    Summer's trailing "if" reads, in different words.

    Read through `Game.condition_holds`'s own `_CONDITION_OPPONENT_CAST_
    COLOR` branch rather than a second copy of the colour/turn logic here,
    so the two cards can never drift apart on what counts as "cast" or
    which player is "an opponent" of whom - the shape check
    (`fullmatch`, not just importing `condition_is_readable`, which would
    also route every *other* board condition `condition_holds` reads
    through this ability's intervening if, well beyond this one clause)
    is the only thing duplicated, and only so this stays a plain `None`
    for every clause shape this reader is not meant for.
    """
    from ...models.game import _CONDITION_OPPONENT_CAST_COLOR

    if _CONDITION_OPPONENT_CAST_COLOR.fullmatch(clause) is None:
        return None
    controller = source.controller or game.active_player.username
    return game.condition_holds(controller, clause, source)


def _opponent_comparison_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Ticket Tortoise's own intervening if: "if an opponent controls more
    lands than you" - the comparison `Game.condition_holds` reads for Beza,
    the Bounding Spring's and Sunset Revelry's plain "if"s
    (`_CONDITION_OPPONENT_COMPARISON`), asked by CR 603.4 as the event occurs
    and again as the ability resolves. `None` for any other clause."""
    from ...models.game import _CONDITION_OPPONENT_COMPARISON

    if _CONDITION_OPPONENT_COMPARISON.fullmatch(clause) is None:
        return None
    return game.condition_holds(controller_of_source(game, source), clause, source)


def _self_is_a_creature_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Hydro-Man, Fluid Felon's own intervening if: "if Hydro-Man is a
    creature" - `Game.condition_holds`' `_CONDITION_SELF_IS_A_CREATURE`, the
    source on the computed board (CR 613.5), asked by CR 603.4 as the event
    occurs and again as the ability resolves. `None` for any other clause,
    including one whose subject is not this source."""
    from ...models.game import _CONDITION_SELF_IS_A_CREATURE

    if _CONDITION_SELF_IS_A_CREATURE.fullmatch(clause) is None:
        return None
    return game.condition_holds(controller_of_source(game, source), clause, source)


#: The Enduring cycle's "if it was a creature" on its own death trigger - a
#: past-tense type check on the source as it left the battlefield. "they
#: were" is the identical clause on a plural-subject source - Tom, Bert, and
#: William's own "if they were a creature" (three trolls as one legendary
#: creature, CR 201.5's own printed-name self-reference already reads the
#: plural verb on the condition side; this is the same plurality carried
#: into the intervening *if*).
_SELF_WAS_A_TYPE = re.compile(
    r"^(?:it was|they were) an? (?P<type>artifact|battle|creature|enchantment|land|planeswalker)$"
)


def _self_was_a_type_holds(clause: str, source: CardState, event: GameEvent | None) -> bool | None:
    """ "if it was a `<card type>`"/"if they were a `<card type>`" on a
    leaves-the-battlefield trigger of the source itself, or `None` for any
    other clause.

    CR 603.10a: a leaves-the-battlefield ability looks back in time, so the
    answer is the permanent's types as it last existed on the battlefield -
    the event's own look-back snapshot (`GameEvent.subject_types`, taken
    before the move) when the event is the source's own departure, and
    otherwise the `last_known_types` the move recorded. CR 700.4's "dies" is
    any permanent put into a graveyard from the battlefield, so the Enduring
    cycle's returned enchantment dying again is the same event, refused here.
    """
    match = _SELF_WAS_A_TYPE.fullmatch(clause)
    if match is None:
        return None
    wanted = Type(match.group("type"))
    if event is not None and event.subject_id == source.id and event.subject_types is not None:
        return wanted in event.subject_types
    types = source.last_known_types if source.last_known_types is not None else source.types
    return wanted in types


def _you_control_a_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Birthing Ritual's own intervening if: "if you control a creature" -
    the "you control a(n) `<quality>`" board fact `Game.condition_holds`
    already reads for Flame of Anor's trailing "if" (`_CONDITION_CONTROLS_A`),
    asked by CR 603.4 as the event occurs and again by CR 608.2a as the
    ability resolves. `None` for any other clause, and for a quality
    `condition_is_readable` refuses, so those still fail closed."""
    from ...models.game import _CONDITION_CONTROLS_A, condition_is_readable

    if _CONDITION_CONTROLS_A.fullmatch(clause) is None or not condition_is_readable(clause):
        return None
    controller = source.controller or game.active_player.username
    return game.condition_holds(controller, clause, source)


def intervening_if_holds(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None" = None,
    source_stamp: UUID | None = None,
) -> bool:
    """Whether an intervening *if* clause is true right now (CR 603.4, 608.2a),
    failing closed on a clause nobody reads.

    `intervening_if_answer` is the reading; this is the one place its None -
    "no reader claims this clause" - becomes False with an
    `InterveningIfNotice` recorded (`_fail_closed`), so CR 603.4's event check
    and CR 608.2a's recheck on resolution both go through the same answer.
    """
    answer = intervening_if_answer(game, ability, source, event, source_stamp)
    if answer is None:
        return _fail_closed(game, ability, source)
    return answer


def event_qualifier_holds(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether the trigger event happened the way `ability`'s own "while
    <doing something>" qualifier says (CR 603.2) - True when it prints none.

    Asked of the event as it occurs, through the shared condition readers
    (`machines/conditions/events.py`). A qualifier nobody reads fails closed:
    the ability does not trigger, and an `InterveningIfNotice` naming the
    qualifier is recorded, the same trail an unread intervening "if" leaves.
    """
    qualifier = ability.event_qualifier
    if not qualifier:
        return True
    from .. import conditions

    answer = conditions.read_condition(
        conditions.ConditionContext(game, controller, source=source, event=event, ability=ability),
        qualifier,
    )
    if answer is None:
        game.intervening_if_notices.append(
            InterveningIfNotice(source_id=source.id, source_name=source.name, clause=qualifier)
        )
        return False
    return answer


def event_qualifier_readable(ability: TriggeredAbility) -> bool:
    """Whether the engine reads `ability`'s "while <doing something>"
    qualifier: a reader claims it, and its bare trigger event is one the
    engine raises. True when it prints none."""
    if not ability.event_qualifier:
        return True
    from .. import conditions

    has_event = ability.event is not None or bool(_unread_trigger_events(ability.condition))
    return has_event and conditions.claims(ability.event_qualifier)


def intervening_if_readable(printing: Card, ability: TriggeredAbility) -> bool:
    """Whether the engine reads `ability`'s intervening *if* at all - the probe
    the support classifier asks, with no game of its own to ask it in.

    Asked on a throwaway two-player `Game` with `printing` on the battlefield
    as the ability's source and no event: every claimed clause answers True or
    False there (False where it needs an event), so only an unclaimed clause
    answers None. Any exception is read as unreadable, never raised.
    """
    if not (ability.intervening_if or "").strip():
        return True
    from ...models.game import Game
    from ...models.player import Player

    try:
        game = Game(
            players=[Player(username="you"), Player(username="opponent")],
            schema_version=Game.CURRENT_SCHEMA_VERSION,
        )
        source = CardState(card=printing, zone=Zone.BATTLEFIELD, controller="you", owner="you")
        source.bind_to_game(game)
        game.battlefield.append(source)
        return intervening_if_answer(game, ability, source, None) is not None
    except Exception:  # noqa: BLE001 - a probe that raises is a clause not read
        return False


def intervening_if_answer(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None" = None,
    source_stamp: UUID | None = None,
) -> bool | None:
    """Whether an intervening *if* clause is true right now (CR 603.4, 608.2a),
    or None when no reader claims it.

    "When the trigger event occurs, the ability checks whether the stated
    condition is true. The ability triggers only if it's true" (CR 603.4);
    CR 608.2a rechecks the same clause again as the ability resolves.

    Clause shapes read: persist's "it had no -1/-1 counters on it"
    (CR 702.79a), Thopter Assembly's "you control no [subtype]s other than
    this creature", Ocelot Pride's "you gained life this turn", Renegade
    Rallier's own Revolt clause "a permanent left the battlefield under your
    control this turn" (CR 207.2c, `_REVOLT_CLAUSES`, `Game.
    revolt_active_for`), Alania,
    Divergent Storm's "it's the first [type] spell ... you've cast this turn",
    kicker's "if it was kicked" (CR 702.33a, 702.33d), replicate's "a
    replicate cost was paid for it" (CR 702.56a), CR 601.2h's "if no
    mana was spent to cast it" / "if [mana symbols] was spent to cast it"
    (Vexing Bauble, Wistfulness, Drowner of Truth), Transcendent Dragon's
    plain "if you cast it" (CR 601.2's cast, as opposed to any other way a
    permanent reaches the battlefield), Ayara's Oathsworn's counter-count
    comparison "it has fewer than four +1/+1 counters on it"
    (`_counter_count_holds`, CR 122.1), Vengevine's ordinal "it's the second
    creature spell you cast this turn" (`_ordinal_spell_cast_this_turn_holds`),
    and Phoenix Fleet Airship's "you sacrificed a permanent this turn"
    (`_sacrificed_this_turn_holds`, CR 701.21a).

    The mana/kicker/cast clauses all read
    `Game.cast_record` - see `_cast_record_for_clause` for whose record "it"
    means, and `machines/casting.Casting.cast`/`Game.note_cast` for where the
    record comes from: `CostPayment.mana_payment.spend` at the moment CR 601.2h
    pays the total cost, and `Casting.kicked` at the moment CR 601.2b announces
    which optional additional costs are being paid.

    A clause none of those shapes reads is handed to the shared condition
    reader, `machines/conditions.read_condition`, with this ability's event,
    source, controller and source stamp - which reads `Game.condition_holds`'
    own built-in board shapes, every registered template, and a compound of
    two read halves. Only a clause nothing claims answers None, and
    `intervening_if_holds` turns that None into a fail-closed False (CR 603.4
    only lets the ability trigger if the condition is true, and a condition
    nobody read is not *known* to be true) with an `InterveningIfNotice`, so it
    reads as an engine gap, not as a legal "nothing happened". A branch whose
    shape is read but whose `CastRecord` is gone answers False itself, with
    the same notice.
    """
    clause = (ability.intervening_if or "").lower().strip()
    if not clause:
        return True

    from ..meld import meld_condition_holds

    meld_holds = meld_condition_holds(game, clause, source)
    if meld_holds is not None:
        # CR 701.42a's "you both own and control this <type> and a[nother]
        # <type> named <partner>" - Graf Rats' own triggered meld shape.
        # Answered directly rather than through `_fail_closed`: this clause
        # is fully readable (`machines/meld.py`'s regex is generic across
        # every meld pair, not keyed to a card name), so a `False` here is
        # a genuine "only one half is present right now", not an unreadable
        # shape.
        return meld_holds

    if clause in (
        "you cast it",
        "you cast him",
        "you cast her",
        "you cast them",
        # The passive spelling (Doomsday Excruciator's "if it was cast") asks
        # the same CR 601.2 question - was this object cast at all - and is
        # answered by the same `CastRecord`.
        "it was cast",
    ):
        # CR 601.2's cast is a defined action distinct from every other way a
        # permanent can reach the battlefield (reanimation, a search-and-put
        # effect, ...); `Game.note_cast` (CR 601.2h) only ever records a
        # `CastRecord` when a card actually went through that process, so its
        # mere presence for the self-referential source (see
        # `_cast_record_for_clause`) already answers this clause. Unlike the
        # mana-spent clauses above, a missing record here is not an unreadable
        # shape to fail closed on - it is the legitimate, expected answer for
        # a creature that entered some other way, so this returns `False`
        # directly rather than through `_fail_closed`.
        #
        # "Him"/"her"/"them" are the identical CR 700.7 self-reference as
        # "it", spelled with a legendary character's own established pronoun
        # (`machines/abilities.self_normalized_effect_text`'s own gendered
        # candidates read the same idiom for a printed name) - Uldaros
        # Theorix's own "if you cast him" is the reported shape.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None

    paid_with_counter = _PERMANENT_KEYWORD_COST_PAID_WITH_COUNTER.fullmatch(clause)
    if paid_with_counter is not None:
        # CR 702.176a, see the regex above. Fully readable, so a False here is
        # a real "not paid" or "no counter left", never a fail-closed notice.
        return (
            source.zone is Zone.BATTLEFIELD
            and (source.cast_with_keyword or "").lower() == paid_with_counter.group("keyword")
            and source.counter_count(paid_with_counter.group("kind")) > 0
        )

    increment = _INCREMENT_CLAUSE.fullmatch(clause)
    if increment is not None:
        # CR 702.191a's own intervening "if" (`machines/keywords.
        # _increment_ability`), and the reminder text's shorter wording of
        # it. "That spell" is the trigger event's own subject, whose mana
        # spent is its `CastRecord` (CR 601.2h); the source's power and
        # toughness are its computed ones now (CR 613.5). A spell whose
        # record is gone (countered in response) fails closed.
        characteristics = game.characteristics_of(source)
        if increment.group("creature") is not None and not characteristics.is_creature:
            return False
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        spent = sum(record.mana_spent.values())
        return spent > (characteristics.power or 0) or spent > (characteristics.toughness or 0)

    if clause == "its evoke cost was paid":
        # CR 702.74a's own intervening *if*, written out by
        # `machines/keywords._evoke_ability`. What makes it answerable is
        # `CastRecord.keyword`: CR 118.9a allows one alternative cost per spell
        # and `machines/casting.Casting.cast` records which keyword's cost was
        # announced, so "was it evoked" is a lookup rather than an inference
        # from what was spent. A permanent that reached the battlefield without
        # being cast at all has no record, and that is the legitimate answer -
        # its evoke cost was not paid - not an unreadable clause, so this
        # returns False directly rather than through `_fail_closed`, exactly as
        # "you cast it" above does.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None and (record.keyword or "").lower() == "evoke"

    if clause == "its offspring cost was paid":
        # CR 702.175a: "'Offspring [cost]' means 'You may pay an additional
        # [cost] as you cast this spell' and 'When this permanent enters, if
        # its offspring cost was paid, create a token that's a copy of it,
        # except it's 1/1.'" Offspring is an *additional* cost (CR 118.8a),
        # not an alternative one, so unlike evoke this reads
        # `CastRecord.offspring_paid` rather than `.keyword` - a spell can be
        # both kicked and offspring-paid at once, and each linked ability
        # only ever asks about its own cost (CR 702.175b).
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None and record.offspring_paid

    if _CAST_USING_TEAMWORK_CLAUSE.match(clause):
        # `machines/teamwork.py`'s own additional cost, read off
        # `CastRecord.cast_using_teamwork`.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.cast_using_teamwork

    if _FIRST_TIME_TAPPED_THIS_TURN_CLAUSE.match(clause):
        # Captain America, Living Legend's own "if it's the first time that
        # creature has become tapped this turn" - CR 701.26a's tap action,
        # counted per permanent per turn on `Game.became_tapped_count_this_
        # turn` (incremented once, at `Game.emit`'s own single write site,
        # so it can never drift from the `BECOMES_TAPPED` event this
        # ability's own trigger condition is watching). "That creature" is
        # the trigger event's own subject (CR 603.2's "the tapped object"),
        # not the ability's source - a controller with several creatures
        # tapping in one turn tracks each of them separately.
        if event is None or event.subject_id is None:
            return _fail_closed(game, ability, source)
        return game.became_tapped_count_this_turn.get(event.subject_id, 0) == 1

    if _REPLICATE_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.replicated > 0

    if _CASUALTY_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.casualty_paid > 0

    if _CONSPIRE_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.conspire_paid > 0

    if _NO_MANA_SPENT_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return not record.any_mana_spent

    if _TREASURE_MANA_SPENT_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.treasure_mana_spent > 0

    mana_match = _MANA_SPENT_CLAUSE.match(clause)
    if mana_match is not None:
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        required: dict[Color, int] = {}
        for letter in _MANA_SYMBOL_LETTER.findall(mana_match.group("symbols")):
            color = _COLOR_LETTERS[letter]
            required[color] = required.get(color, 0) + 1
        return all(record.mana_of_color_spent(color) >= count for color, count in required.items())

    if clause == "this card is suspended":
        # CR 702.62a's second ability, and CR 702.62b is its whole definition:
        # "A card is 'suspended' if it's in the exile zone, has suspend, and
        # has a time counter on it." `CardState.is_suspended` is that rule,
        # word for word, so a card already cast, already gone from exile some
        # other way, or already down to zero counters answers False here -
        # on the event (CR 603.4) and again on resolution (CR 608.2a).
        return source.is_suspended

    if clause == "it's exiled":
        # CR 702.62a's third ability. "It" is the card the last time counter
        # came off, which is this ability's own source; CR 406.1's exile zone
        # is the only thing asked about, not the marker that put it there -
        # by this point the card has no time counters left, so CR 702.62b's
        # "suspended" is deliberately *not* what the rule reaches for here.
        return source.zone is Zone.EXILE

    if clause == "this permanent is on the battlefield":
        # CR 702.24a's own intervening *if* for cumulative upkeep, written out
        # by `machines/keywords._cumulative_upkeep_ability`: a zone question
        # (CR 400.1), fully readable, so False is a real answer.
        return source.zone is Zone.BATTLEFIELD

    if clause == "this permanent came under your control since the beginning of your last upkeep":
        # CR 702.30a's own intervening *if* for echo, written out by
        # `machines/keywords._echo_ability`, read off the control stamp
        # `Game.note_control_changes` keeps against `Game.upkeeps_begun`.
        return source.zone is Zone.BATTLEFIELD and game.came_under_control_since_last_upkeep(source)

    if clause == "this permanent has a time counter on it":
        # CR 702.63a's second ability, written out by `machines/keywords.
        # _vanishing_abilities`. Fully readable off the object itself, so a
        # permanent whose last time counter already came off some other way
        # (or that has since left the battlefield) answers False here rather
        # than through `_fail_closed` - both on the event (CR 603.4) and again
        # on resolution (CR 608.2a), which is what stops the tick once the
        # counters are gone.
        return source.zone is Zone.BATTLEFIELD and source.counter_count(Counter.TIME) > 0

    if clause == "it had no time counters on it":
        # Deadly Grub's own dies trigger ("if it had no time counters on it"),
        # the identical look-back shape persist's "it had no -1/-1 counters on
        # it" already reads just above, generalised to time counters: CR
        # 603.10a's look-back plus CR 122.2's counters ceasing to exist on the
        # move is what makes `last_known_counters` the answer, for any
        # permanent's own dies trigger that asks this about its counters as it
        # last existed on the battlefield - not only a permanent with
        # vanishing, since nothing about the clause names the keyword.
        return not source.last_known_counters[Counter.TIME]

    if match := _POWER_GREATER_THAN_SELF_RE.fullmatch(clause):
        if match.group("name") not in (source.name or "").lower():
            return _fail_closed(game, ability, source)
        dying = event_subject_power(game, event)
        if dying is None:
            return _fail_closed(game, ability, source)
        return dying > (game.power_of(source) or 0)

    if clause in (
        "it isn't a token",
        "it's not a token",
        "they aren't a token",
        "they're not a token",
        "they aren't tokens",
        "they're not tokens",
    ):
        # The Notary Hobbits' plural "if they're not a token" names the one
        # permanent as "they" (its name is plural) - the same question.
        # Gruff Triplets' own ETB ("if it isn't a token, create two tokens
        # that are copies of it") and Sphinx of False Conclusions' dies
        # trigger ("if it isn't a token, create a token that's a copy of
        # it") - CR 111.1/CR 111.6's own distinction, read straight off
        # `CardState.token` (CR 603.10a's look-back keeps it set on the last
        # known information for a dies trigger the same way every other
        # last-known field here is read).
        return not source.token

    if clause in ("it had no -1/-1 counters on it", "it had no +1/+1 counters on it"):
        # CR 702.79a (persist) and CR 702.93a (undying) ask about the
        # permanent as it last existed on the battlefield, and CR 122.2 has
        # already destroyed its counters on the way to the graveyard. CR 704.8
        # and CR 603.10a are what make that question answerable at all, and
        # `last_known_counters` is the answer.
        kind = Counter.MINUS_ONE if "-1/-1" in clause else Counter.PLUS_ONE
        return not source.last_known_counters[kind]

    match = re.match(r"you control no (\w+?)s? other than this \w+", clause)
    if match is not None:
        subtype = match.group(1)
        controller = source.controller or game.active_player.username
        # CR 613.5: the computed subtypes, not the printed line - hoisted
        # once for the whole scan rather than asked per permanent (see
        # `Game._state_based_actions_once`'s own pattern).
        board = game.computed_board()
        others = [
            state
            for state in game.permanents_controlled_by(controller)
            if state.id != source.id
            and any(word.lower() == subtype for word in board.of(state).subtypes)
        ]
        return not others

    if clause == "you gained life this turn":
        controller = source.controller or game.active_player.username
        return controller in game.life_gained_this_turn

    if clause in (
        "you've scried or surveilled this turn",
        "you have scried or surveilled this turn",
    ):
        # CR 701.22a/701.25a. Surveillance Phantasm prints the same fact as a
        # static "as long as" (S9's own layer-conditional reading);
        # Desperate Futurescribe's own printing folds it into an "instead"
        # continuous-effect upgrade rather than a bare intervening *if* - the
        # predicate is the same fact either way, and this is that predicate,
        # exposed for whichever clause parser needs to ask it. CR 109.5's
        # "you" (`controller_of_source`) rather than the bare `source.
        # controller or active_player` fallback most of this function's
        # older branches still use - Command the Stage's own graveyard-
        # functioning ability is exactly the case that fallback gets wrong,
        # crediting whoever's turn it happens to be instead of the card's
        # own owner (`test_turn_history_predicates.py` caught this live).
        return game.turn_fact_holds("scried_or_surveilled", controller_of_source(game, source))

    if clause == "you've activated a loyalty ability this turn":
        # Kiora of Salt and Sand's own "Whenever you attack, if you've
        # activated a loyalty ability this turn, ..." (CR 606.2).
        return game.turn_fact_holds("loyalty_ability_activated", controller_of_source(game, source))

    noncombat_damage = _opponent_dealt_noncombat_damage_holds(game, clause, source)
    if noncombat_damage is not None:
        return noncombat_damage

    creatures_died = _creatures_died_this_turn_holds(game, clause)
    if creatures_died is not None:
        return creatures_died

    other_subtype_count = _controls_at_least_other_subtype_count_holds(game, clause, source)
    if other_subtype_count is not None:
        return other_subtype_count

    if clause == "you descended this turn":
        # CR 700.11: "This means that a permanent card has been put into
        # that player's graveyard from anywhere this turn." Broodrage
        # Mycoid's own end-step trigger, and every other "if you descended
        # this turn" printing - `Game.descended` is the one shared answer,
        # reading FRA S5's `graveyard_arrivals_this_turn` ledger (see that
        # method's own docstring for the merge note).
        controller = source.controller or game.active_player.username
        return game.descended(controller)

    descend_count = _descend_permanent_card_count_holds(game, clause, source)
    if descend_count is not None:
        return descend_count

    pack_tactics = _PACK_TACTICS_CLAUSE.fullmatch(clause)
    if pack_tactics is not None:
        # CR 207.2c's pack tactics: the attack as declared (CR 508.1) - the
        # power its attackers had then (`CombatMachine.declared_attacking_
        # power`), which a later pump or departure does not rewrite. Only the
        # active player declares attackers.
        controller = source.controller or game.active_player.username
        if controller != game.active_player.username:
            return False
        return game.combat.declared_attacking_power >= int(pack_tactics.group("threshold"))

    if clause in _REVOLT_CLAUSES:
        # CR 207.2c: Revolt is an ability word, so no numbered rule spells out
        # the condition itself; the wording is the card's own. Renegade
        # Rallier's own ETB prints "a permanent left the battlefield under
        # your control this turn" - the identical clause Fatal Push carries,
        # except Fatal Push's is read directly by `machines/targeting.py`'s
        # `comparison_value_if_revolt` because it modifies a *target
        # restriction* rather than gating a triggered ability at all
        # (`test_fatal_push_revolt.py`). `Game.revolt_active_for` is the one
        # shared answer both readings ask.
        controller = source.controller or game.active_player.username
        return game.revolt_active_for(controller)

    greatest_power = _control_each_greatest_power_holds(game, clause, source)
    if greatest_power is not None:
        return greatest_power
    power_control = _control_creature_with_power_holds(game, clause, source)
    if power_control is not None:
        return power_control

    first_spell = _first_spell_this_turn_holds(game, clause, source, event)
    if first_spell is not None:
        return first_spell

    last_turn = _spells_cast_last_turn_holds(game, clause)
    if last_turn is not None:
        return last_turn

    this_turn = _spells_cast_this_turn_holds(game, clause, source)
    if this_turn is not None:
        return this_turn

    another_spell = _another_spell_cast_this_turn_holds(game, clause, source)
    if another_spell is not None:
        return another_spell

    didnt_cast = _didnt_cast_spell_this_turn_holds(game, clause, source)
    if didnt_cast is not None:
        return didnt_cast

    drawn_count = _drawn_card_count_holds(game, clause, source)
    if drawn_count is not None:
        return drawn_count

    hand_count = _hand_card_count_holds(game, clause, source)
    if hand_count is not None:
        return hand_count

    self_tapped = _source_tapped_holds(clause, source)
    if self_tapped is not None:
        return self_tapped

    self_prepared = _source_prepared_holds(clause, source)
    if self_prepared is not None:
        return self_prepared

    counter_count = _counter_count_holds(clause, source)
    if counter_count is not None:
        return counter_count

    ordinal_spell = _ordinal_spell_cast_this_turn_holds(game, clause, source, event)
    if ordinal_spell is not None:
        return ordinal_spell

    sacrificed = _sacrificed_this_turn_holds(game, clause, source)
    if sacrificed is not None:
        return sacrificed

    subtype_count = _controlled_subtype_count_holds(game, clause, source)
    if subtype_count is not None:
        return subtype_count

    opponent_cast_color = _opponent_cast_color_holds(game, clause, source)
    if opponent_cast_color is not None:
        return opponent_cast_color

    you_control_a = _you_control_a_holds(game, clause, source)
    if you_control_a is not None:
        return you_control_a

    opponent_comparison = _opponent_comparison_holds(game, clause, source)
    if opponent_comparison is not None:
        return opponent_comparison

    self_is_a_creature = _self_is_a_creature_holds(game, clause, source)
    if self_is_a_creature is not None:
        return self_is_a_creature

    self_was_a_type = _self_was_a_type_holds(clause, source, event)
    if self_was_a_type is not None:
        return self_was_a_type

    entered_or_cast_from_graveyard = _entered_or_cast_from_graveyard_holds(
        game, clause, source, event
    )
    if entered_or_cast_from_graveyard is not None:
        return entered_or_cast_from_graveyard

    equipped = _source_equipped_holds(game, clause, source)
    if equipped is not None:
        return equipped

    typed_turn_fact = _typed_turn_fact_holds(game, clause, source)
    if typed_turn_fact is not None:
        return typed_turn_fact

    from .. import conditions

    return conditions.read_condition(
        conditions.ConditionContext(
            game=game,
            controller=controller_of_source(game, source),
            source=source,
            event=event,
            ability=ability,
            source_stamp=source_stamp,
        ),
        clause,
    )


#: "he's equipped" (Whiplash, Vengeful Engineer), "this creature is equipped"
#: (Avacynian Missionaries) - CR 301.5a: a creature is equipped while an
#: Equipment is attached to it. A legend's own pronoun is the source itself.
_SOURCE_EQUIPPED_CLAUSE = re.compile(
    r"^(?:it's|it is|he's|he is|she's|she is|this (?:creature|permanent) is) equipped$"
)


def _source_equipped_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_SOURCE_EQUIPPED_CLAUSE`: whether an Equipment (its subtype read off
    the computed board, CR 613.5) is attached to the source right now."""
    if _SOURCE_EQUIPPED_CLAUSE.fullmatch(clause) is None:
        return None
    if source.zone is not Zone.BATTLEFIELD:
        return False
    return any(
        permanent.attached_to == source.id
        and "Equipment" in game.characteristics_of(permanent).subtypes
        for permanent in game.battlefield
    )


#: "an artifact entered the battlefield under your control this turn" (Iron
#: Man, Master of Machines), "a Hero entered the battlefield under your
#: control this turn" and "you attacked with a Hero this turn" (Avengers
#: Assemble!, the two joined by "or") - facts of the turn `Game` records as
#: they happen (`models.game.entered_type_facts`/`attacked_with_type_facts`),
#: so a permanent that entered or attacked and has since left still counts.
_ENTERED_UNDER_YOUR_CONTROL_THIS_TURN = re.compile(
    r"^(?:an?|another) (?P<quality>[a-z]+) entered the battlefield under your control this turn$"
)
_ATTACKED_WITH_THIS_TURN = re.compile(r"^you attacked with an? (?P<quality>[a-z]+) this turn$")


def _typed_turn_fact_key(prefix: str, quality: str) -> str | None:
    """The `turn_facts` key a card type or subtype word stands for."""
    if quality in {member.value for member in Type}:
        return f"{prefix}_type:{quality}"
    from ...data.subtypes import canonical_subtype

    subtype = canonical_subtype(quality)
    return None if subtype is None else f"{prefix}_subtype:{subtype}"


def _typed_turn_fact_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_ENTERED_UNDER_YOUR_CONTROL_THIS_TURN`/`_ATTACKED_WITH_THIS_TURN`, or
    an "or"-joined pair of them (either being true is enough); `None` unless
    every part is one of the two shapes."""
    keys: list[str] = []
    for part in clause.split(" or "):
        entered = _ENTERED_UNDER_YOUR_CONTROL_THIS_TURN.fullmatch(part.strip())
        attacked = _ATTACKED_WITH_THIS_TURN.fullmatch(part.strip())
        if entered is not None:
            key = _typed_turn_fact_key("entered", entered.group("quality"))
        elif attacked is not None:
            key = _typed_turn_fact_key("attacked_with", attacked.group("quality"))
        else:
            return None
        if key is None:
            return None
        keys.append(key)
    controller = controller_of_source(game, source)
    return any(game.turn_fact_holds(key, controller) for key in keys)


#: One alternative of Prized Amalgam's and Archfiend's Vessel's clause: "it
#: entered from your graveyard" / "you cast it from your graveyard", and
#: Breathless Knight's "that creature entered from a graveyard" - the same
#: trigger-event subject (CR 603.2) named by a demonstrative instead.
_FROM_GRAVEYARD_ALTERNATIVE = re.compile(
    r"^(?:(?:it|that creature) entered(?: the battlefield)? from (?P<entered>your|a) graveyard"
    r"|you cast it from (?P<cast>your|a) graveyard)$"
)


def _entered_or_cast_from_graveyard_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """CR 603.4's "if it entered from your graveyard or you cast it from your
    graveyard" - `None` when the clause is not this shape.

    "It" is the enters event's own object (the entering creature, which is
    the source itself for Archfiend's Vessel's self-trigger). "Entered from
    your graveyard" reads `GameEvent.origin_zone` - the zone the permanent
    left to enter (`Game.enter_the_battlefield`) - and "your" graveyard is
    the one its owner keeps (CR 400.3) belonging to the ability's
    controller. "You cast it from your graveyard" reads the permanent's own
    `CastRecord` (CR 400.7d): cast from the graveyard, by a player who is the
    ability's controller. Either alternative satisfies the clause (the
    English "or"). Both are recorded facts about that one event, so the
    CR 603.4 recheck on resolution reads the same answer.
    """
    parts = [part.strip() for part in clause.split(" or ")]
    matches = [_FROM_GRAVEYARD_ALTERNATIVE.fullmatch(part) for part in parts]
    if not parts or any(match is None for match in matches):
        return None
    if event is None or event.subject_id is None:
        return False
    you = source.controller or source.owner
    subject = game.find_by_id(event.subject_id)
    owner = subject.owner if isinstance(subject, CardState) else None
    for match in matches:
        assert match is not None
        entered_whose = match.group("entered")
        if entered_whose is not None:
            if event.origin_zone is Zone.GRAVEYARD and (entered_whose == "a" or owner == you):
                return True
            continue
        cast_whose = match.group("cast")
        if not isinstance(subject, CardState):
            continue
        record = game.cast_record_of(subject)
        if record is None or record.origin_zone is not Zone.GRAVEYARD:
            continue
        if subject.controller == you and (cast_whose == "a" or owner == you):
            return True
    return False


#: Ayara's Oathsworn's clause: "it has fewer than four +1/+1 counters on it",
#: and the suffix form most cards print: Lightning Coils' "this artifact has
#: five or more charge counters on it", Earthbender Ascension's "it has four or
#: more quest counters on it". "It" is the source itself - the only subject
#: this shape is printed with in this pool, and CR 603.4's clause is read about
#: the ability's own source unless it plainly names something else.
#: The past tense ("it had two or more +1/+1 counters on it", Ochre Jelly's
#: dies trigger) asks the same question of the object as it last existed on
#: the battlefield (CR 603.10a), whose counters CR 122.2 has already ended.
_COUNTER_COUNT_CLAUSE = re.compile(
    r"^(?:it|this [a-z]+) (?P<tense>has|had) "
    rf"(?:(?P<comparison>fewer than|more than|at least|exactly) (?P<count>{COUNT})"
    rf"|(?P<suffix_count>{COUNT}) or (?P<direction>more|fewer)"
    r"|(?P<none>no))"
    r" (?P<kind>\S+) counters? on it$"
)

#: How each comparison word answers, given the counters actually there and the
#: number the clause names. "N or more" and "N or fewer" are inclusive.
_COUNTER_COMPARISONS = {
    "fewer than": operator.lt,
    "more than": operator.gt,
    "at least": operator.ge,
    "exactly": operator.eq,
    "more": operator.ge,
    "fewer": operator.le,
}


def _counter_count_holds(clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as a counter count on the source (CR 122.1's counters
    as "a marker placed on an object ... that modifies its characteristics
    and/or interacts with a rule, ability, or effect").

    `None`, not False, when the clause is not this shape, so an unrelated
    clause still reaches `_fail_closed`. A count word this does not know is
    left unread the same way, rather than guessed at.
    """
    match = _COUNTER_COUNT_CLAUSE.match(clause)
    if match is None:
        return None
    on_it = (
        source.last_known_counters[match.group("kind")]
        if match.group("tense") == "had"
        else source.counter_count(match.group("kind"))
    )
    if match.group("none") is not None:
        return on_it == 0
    if match.group("suffix_count") is not None:
        count_word, comparison = match.group("suffix_count"), match.group("direction")
    else:
        count_word, comparison = match.group("count"), match.group("comparison")
    wanted = parse_count(count_word, article=False)
    if wanted is None:
        return None
    return _COUNTER_COMPARISONS[comparison](on_it, wanted)


#: Vengevine's clause: "it's the second creature spell you cast this turn".
#: The ordinal twin of `_FIRST_SPELL_THIS_TURN`, which reads only "first" and
#: so left every other ordinal to fail closed.
_ORDINAL_SPELL_CAST_THIS_TURN = re.compile(
    r"^it'?s the (?P<ordinal>[a-z]+) (?P<word>[a-z]+) spell you(?:'ve| have)? cast this turn$"
)


def _ordinal_spell_cast_this_turn_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """Whether the spell this trigger is about is exactly the controller's Nth
    spell of the named kind cast this turn (CR 603.4).

    "It" is the cast spell the CAST_SPELL event carries, not the source - the
    same reading `_first_spell_this_turn_holds` already gives its own "it".
    Answered from `Game.spells_cast_this_turn`, which CR 601.2i's completed
    cast has already appended this very spell to, so the spell's 1-indexed
    position among that turn's spells of the named kind *is* the ordinal.

    `None` when the clause is not this shape, so the caller still fails
    closed; False when it is but there is no event to identify the spell
    with.
    """
    match = _ORDINAL_SPELL_CAST_THIS_TURN.match(clause)
    if match is None:
        return None
    ordinal = parse_ordinal(match.group("ordinal"))
    card_type = _TYPE_WORDS.get(match.group("word"))
    if ordinal is None or card_type is None:
        return None
    if event is None or event.subject_id is None:
        return False
    controller = source.controller or game.active_player.username
    of_that_kind = [
        state
        for state in game.spells_cast_this_turn.get(controller, [])
        if card_type in state.types
    ]
    position = next(
        (
            index
            for index, state in enumerate(of_that_kind, start=1)
            if state.id == event.subject_id
        ),
        None,
    )
    return position == ordinal


def _sacrificed_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Phoenix Fleet Airship's clause: "you sacrificed a permanent this turn"
    (CR 701.21a's sacrifice, asked about the turn rather than about one
    event) - `Game.condition_holds`' `_CONDITION_SACRIFICED_THIS_TURN`, read
    off `Game.permanents_sacrificed_this_turn`. A bounced or destroyed
    permanent left the battlefield without ever being sacrificed, which is
    why `permanents_left_battlefield_this_turn` cannot answer this. `None`
    for any other clause."""
    from ...models.game import _CONDITION_SACRIFICED_THIS_TURN

    if _CONDITION_SACRIFICED_THIS_TURN.fullmatch(clause) is None:
        return None
    return game.condition_holds(controller_of_source(game, source), clause, source)


#: Command the Stage's "an opponent was dealt noncombat damage last turn"
#: and Grim Repriser's activation-restriction twin "an opponent has been
#: dealt noncombat damage this turn" (CR 120.2a) - the same fact, asked
#: about either turn.
_OPPONENT_DEALT_NONCOMBAT_DAMAGE = re.compile(
    r"^an opponent (?:was|has been) dealt noncombat damage (?P<when>this|last) turn$"
)


def _opponent_dealt_noncombat_damage_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """Whether any of `source`'s controller's opponents was dealt noncombat
    damage this turn or last turn, off `Game.turn_facts`' "dealt_noncombat_
    damage" ledger (`Game.deal_damage`'s own record of it).

    `controller_of_source`, not a bare `source.controller or active_player`
    fallback: Command the Stage's own printing of this clause functions from
    a graveyard (CR 113.6m) and is checked at *any* player's upkeep, so the
    active player is frequently not this card's owner at all - Grim
    Repriser's activation-restriction twin has the identical shape.
    """
    match = _OPPONENT_DEALT_NONCOMBAT_DAMAGE.match(clause)
    if match is None:
        return None
    controller = controller_of_source(game, source)
    last_turn = match.group("when") == "last"
    return any(
        game.turn_fact_holds("dealt_noncombat_damage", player.username, last_turn=last_turn)
        for player in game.players_in_game
        if player.username != controller
    )


#: Darklight Phoenix's "two or more creatures died this turn" (CR 700.4),
#: an ordinary count over `Game.creatures_died_this_turn` rather than
#: pinned to the number two - a different printing naming a different
#: threshold reads the same way.
_CREATURES_DIED_THIS_TURN = re.compile(rf"^(?P<count>{COUNT}) or more creatures died this turn$")


def _creatures_died_this_turn_holds(game: "Game", clause: str) -> bool | None:
    match = _CREATURES_DIED_THIS_TURN.match(clause)
    if match is None:
        return None
    needed = parse_count(match.group("count"), article=False)
    if needed is None:
        return None
    return game.creatures_died_this_turn >= needed


#: Roiling Canopy's "you control at least five other Forests" (CR 205.3i's
#: land subtype) - the counted twin of the "you control no [subtype]s other
#: than this [type]" shape already read above, generalised the same way: a
#: subtype word and a count, not a fixed number or a fixed subtype.
_CONTROL_AT_LEAST_OTHER_SUBTYPE = re.compile(
    rf"^you control at least (?P<count>{COUNT}) other (?P<subtype>\w+?)s?$"
)


def _controls_at_least_other_subtype_count_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    match = _CONTROL_AT_LEAST_OTHER_SUBTYPE.match(clause)
    if match is None:
        return None
    needed = parse_count(match.group("count"), article=False)
    if needed is None:
        return None
    subtype = match.group("subtype").lower()
    controller = controller_of_source(game, source)
    # CR 613.5: the computed subtypes, not the printed line - a land that is
    # a Forest only because of an animating/typechanging effect still counts,
    # and one that lost the subtype does not.
    board = game.computed_board()
    others = [
        state
        for state in game.permanents_controlled_by(controller)
        if state.id != source.id
        and any(word.lower() == subtype for word in board.of(state).subtypes)
    ]
    return len(others) >= needed


#: "if Kona is tapped" / "if this creature is untapped" - a clause about the
#: source's own tap state. The subject is either CR 700.7's "this [something]"
#: or CR 201.5's self-reference by printed name, which CR 201.5c lets a card
#: shorten ("Kona" for "Kona, Rescue Beastie").
_SOURCE_TAP_STATE = re.compile(r"^(?P<subject>.+?) is (?P<state>tapped|untapped)$")


def _source_tapped_holds(clause: str, source: CardState) -> bool | None:
    """`_SOURCE_TAP_STATE`'s shape - Kona, Rescue Beastie's *survival* trigger.

    `None` when the clause is not this shape, or when its subject is some
    other object than the source itself: this reads only the source's own tap
    state, so a clause about anything else still reaches `_fail_closed`
    rather than being answered from the wrong permanent.

    CR 201.5 is what makes a printed name mean "just that particular object
    and not any other objects with that name", and CR 201.5c is what lets the
    card print only the first part of it.
    """
    match = _SOURCE_TAP_STATE.match(clause)
    if match is None:
        return None
    subject = match.group("subject").strip().lower()
    name = source.name.lower()
    is_self = re.fullmatch(r"this \w+", subject) is not None or (
        subject
        and (name == subject or name.startswith(f"{subject},") or name.startswith(f"{subject} "))
    )
    if not is_self:
        return None
    return source.tapped if match.group("state") == "tapped" else not source.tapped


#: CR 722.3a's own condition guard, printed on most upkeep-triggered prepare
#: creatures: "if this creature isn't prepared". `_SOURCE_TAP_STATE`'s own
#: subject-reading shape, for "prepared"/"unprepared" instead of "tapped"/
#: "untapped" - both polarities read the same way that pair does, though the
#: pool only ever prints the negative ("isn't prepared", Woodwork Prodigy).
_SOURCE_PREPARED_STATE = re.compile(r"^(?P<subject>.+?) (?:is(?P<negated>n'?t)? )?prepared$")


def _source_prepared_holds(clause: str, source: CardState) -> bool | None:
    """`_SOURCE_PREPARED_STATE`'s shape - see its own docstring."""
    match = _SOURCE_PREPARED_STATE.match(clause)
    if match is None:
        return None
    subject = match.group("subject").strip().lower()
    name = source.name.lower()
    is_self = re.fullmatch(r"this \w+", subject) is not None or (
        subject
        and (name == subject or name.startswith(f"{subject},") or name.startswith(f"{subject} "))
    )
    if not is_self:
        return None
    return (not source.prepared) if match.group("negated") else source.prepared


#: "you've cast three or more instant and sorcery spells this turn" - Arclight
#: Phoenix's own combat trigger - and Loan Shark's untyped "you've cast two or
#: more spells this turn". The type list is optional; when printed it is CR
#: 205.2a's card types, joined with a bare "and"/"or"/comma, and a spell
#: matching *any* of them counts once, which is what the card means (an
#: instant is not also a sorcery). Without one, every spell counts.
_SPELLS_CAST_THIS_TURN = re.compile(
    rf"^you(?:'ve| have) cast (?P<count>{COUNT}) or more "
    r"(?:(?P<types>[a-z, ]+?) )?spells this turn$"
)
#: "you've cast another spell this turn" - Sage of the Skies' own cast
#: trigger. "Another" excludes the spell the trigger is printed on, which is
#: itself already recorded in `Game.spells_cast_this_turn` by the time the
#: trigger is checked (CR 601.2i puts the spell on the stack, and the cast
#: trigger fires off that very event).
_ANOTHER_SPELL_THIS_TURN = re.compile(r"^you(?:'ve| have) cast another spell this turn$")


def _another_spell_cast_this_turn_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """`_ANOTHER_SPELL_THIS_TURN`'s shape, or `None` if the clause is not it.

    Counted off `Game.spells_cast_this_turn`, with the source itself excluded
    by id - CR 201.5's "just that particular object", not "any object with
    that name", so a second copy of the same card cast earlier this turn does
    satisfy the clause.
    """
    if _ANOTHER_SPELL_THIS_TURN.match(clause) is None:
        return None
    controller = source.controller or game.active_player.username
    cast = game.spells_cast_this_turn.get(controller, [])
    return any(state.id != source.id for state in cast)


#: "you didn't cast a spell this turn" (Edgar, Moonlit Sovereign; Nightpack
#: Ambusher) and "that player didn't cast a spell this turn" (Impatience -
#: the same clause read with the third-person subject a per-player "at the
#: beginning of each player's end step" ability prints) - CR 601.2i's
#: already-tracked `Game.spells_cast_this_turn`, negated.
#: `_spells_cast_this_turn_holds` below only ever reads the positive "you've
#: cast N or more spells this turn" form; this is its negated twin, over the
#: identical field.
_DIDNT_CAST_SPELL_THIS_TURN = re.compile(
    r"^(?:you|that player) (?:didn'?t|did not|haven'?t|have not) cast a spell"
    r"(?P<from_hand> from (?:your|their) hand)? this turn$"
)


def _didnt_cast_spell_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_DIDNT_CAST_SPELL_THIS_TURN`'s shape, or `None` if the clause is not
    it.

    "You"/"that player" is the ability's own controller (CR 109.5's default,
    absent an explicit "that player" bound to a different per-player
    trigger) - the same fallback `_spells_cast_this_turn_holds` already uses
    for its positive form, over the identical `Game.spells_cast_this_turn`
    list CR 601.2i keeps.
    """
    match = _DIDNT_CAST_SPELL_THIS_TURN.match(clause)
    if match is None:
        return None
    controller = source.controller or game.active_player.username
    if match.group("from_hand"):
        # Prairie Dog's "if you haven't cast a spell from your hand this
        # turn": only a cast whose CR 601.2a move started in a hand counts,
        # recorded as it happened (`Game.put_on_stack`).
        return not game.turn_fact_holds("cast_spell_from_hand", controller)
    cast = game.spells_cast_this_turn.get(controller, [])
    return len(cast) == 0


#: "you've drawn N or more cards this turn" (Lyra, Tolarian Archangel) and
#: the wider family it belongs to - Lake-town Toymaker's own "if you've
#: drawn two or more cards this turn", the identical clause a dozen "as long
#: as you've drawn ... cards this turn" static abilities print (Evangel of
#: Synthesis, Eyekite, Messenger Hawk, and others - read elsewhere as a
#: static condition, not here). A general count comparison over CR 121.2's
#: individual draws this turn (`Game.cards_drawn_this_turn`, incremented once
#: per card drawn), the same four comparison words `_COUNTER_COUNT_CLAUSE`/
#: `_CONTROLLED_SUBTYPE_COUNT` already read for a counter or subtype count -
#: `_COUNTER_COMPARISONS` (below) is the shared answer all three read.
_DRAWN_CARD_COUNT_CLAUSE = re.compile(
    r"^you(?:'ve| have) drawn "
    rf"(?:(?P<comparison>fewer than|more than|at least|exactly) (?P<count>{COUNT})"
    rf"|(?P<suffix_count>{COUNT}) or (?P<direction>more|fewer))"
    r" cards? this turn$"
)


#: "you have fewer than ten cards in hand" (The Ten Rings; Doctor Octopus,
#: Master Planner's "eight"; Kozilek, the Great Distortion's "seven") - CR
#: 402.1's hand, counted as the clause is checked (CR 603.4: as the ability
#: triggers and again as it resolves). "You" is the ability's controller.
_HAND_CARD_COUNT_CLAUSE = re.compile(
    r"^you have "
    rf"(?:(?P<comparison>fewer than|more than|at least|exactly) (?P<count>{COUNT})"
    rf"|(?P<suffix_count>{COUNT}) or (?P<direction>more|fewer))"
    r" cards? in (?:your )?hand$"
)


def _hand_card_count_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_HAND_CARD_COUNT_CLAUSE`'s comparison, or `None` if the clause is not it."""
    match = _HAND_CARD_COUNT_CLAUSE.match(clause)
    if match is None:
        return None
    if match.group("suffix_count") is not None:
        count_word, comparison = match.group("suffix_count"), match.group("direction")
    else:
        count_word, comparison = match.group("count"), match.group("comparison")
    count = parse_count(count_word)
    if count is None:
        return None
    controller = source.controller or game.active_player.username
    return _SUBTYPE_COUNT_COMPARISONS[comparison](len(game.player(controller).hand), count)


def _drawn_card_count_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_DRAWN_CARD_COUNT_CLAUSE`'s shape, or `None` if the clause is not it.

    Answered from `Game.cards_drawn_this_turn` - the same running per-player
    draw count `_NTH_DRAW_CONDITION`'s own ordinal reading already uses for
    "you draw your Nth card in a turn"'s triggered shape; this is the
    intervening-*if* twin, over a comparison rather than an exact ordinal.
    """
    match = _DRAWN_CARD_COUNT_CLAUSE.match(clause)
    if match is None:
        return None
    if match.group("suffix_count") is not None:
        count_word, comparison = match.group("suffix_count"), match.group("direction")
    else:
        count_word, comparison = match.group("count"), match.group("comparison")
    wanted = parse_count(count_word, article=False)
    if wanted is None:
        return None
    controller = source.controller or game.active_player.username
    drawn = getattr(game, "cards_drawn_this_turn", None)
    if not isinstance(drawn, dict):
        return None
    on_turn = drawn.get(controller, 0)
    return _COUNTER_COMPARISONS[comparison](on_turn, wanted)


def _spells_cast_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_SPELLS_CAST_THIS_TURN`'s shape, or `None` if the clause is not it.

    Answered from `Game.spells_cast_this_turn`, the running list this engine
    already keeps for Alania, Divergent Storm's own "the first instant spell
    ... you've cast this turn" - counted at the moment each spell was cast,
    and emptied as a new turn begins.

    "You" is the ability's own controller. Each recorded spell is measured by
    its printed card types (CR 205.2a): the object it was as a spell is long
    gone from the stack by the time this is asked, and CR 400.7 leaves
    whatever it became with no memory of that existence, so the printing is
    the only thing left to read - which is exact here, since no card in the
    pool changes an instant into a sorcery or back.

    Returns `None`, not `False`, for a count word this does not know, so the
    caller still fails closed and records the gap rather than silently
    answering "no".
    """
    match = _SPELLS_CAST_THIS_TURN.match(clause)
    if match is None:
        return None
    wanted = parse_count(match.group("count"), article=False)
    if wanted is None:
        return None
    controller = source.controller or game.active_player.username
    cast = game.spells_cast_this_turn.get(controller, [])
    if match.group("types") is None:
        return len(cast) >= wanted
    wanted_types: set[Type] = set()
    for word in re.split(r",|\band\b|\bor\b", match.group("types")):
        word = word.strip()
        if not word:
            continue
        card_type = next((t for t in Type if t.value == word.rstrip("s")), None)
        if card_type is None:
            return None
        wanted_types.add(card_type)
    if not wanted_types:
        return None
    matching = sum(
        1 for state in cast if wanted_types & set(state.types_as_a_spell(state.card.types))
    )
    return matching >= wanted


#: "if no spells were cast last turn" - the werewolves' transform condition
#: (Duskwatch Recruiter, and every other card printed with this line).
_NO_SPELLS_LAST_TURN = re.compile(r"^no spells were cast last turn$")
#: "if a player cast two or more spells last turn" - the mirror condition on
#: the back face (Krallenhorde Howler), asked of *each* player separately: one
#: player casting two is what it wants, not two spells between them.
_SPELLS_CAST_LAST_TURN = re.compile(r"^a player cast (?P<count>\w+) or more spells last turn$")

#: Valakut, the Molten Pinnacle's clause: "you control at least five other
#: Mountains". A board count of permanents with a named subtype (CR 205.3i's
#: land types here, but the shape is subtype-generic), optionally excluding the
#: ability's own source - which is what "other" means, and what makes Valakut
#: need *six* Mountains on the battlefield rather than five.
#:
#: `clause` reaches this lowercased, so the subtype cannot be told apart by
#: capitalization the way `_ENTERING_SUBTYPE` tells it apart. That is safe
#: here: the clause names the thing being counted and nothing else, and a
#: card-type word ("creatures", "lands") is counted correctly by
#: `_controlled_subtype_count_holds`'s own card-type branch rather than being
#: mistaken for a subtype.
#: Vraska, the Cutting Glare's own ETB clause: "if you control six or more
#: lands" - the same count-a-card-type shape as Valakut's above, but printed
#: with the count-word suffix rather than a leading comparison word, mirroring
#: how `_COUNTER_COUNT_CLAUSE` reads both "fewer than four ... counters" and
#: "five or more ... counters" as the same underlying comparison.
_CONTROLLED_SUBTYPE_COUNT = re.compile(
    r"^you control "
    r"(?:(?P<comparison>at least|more than|fewer than|exactly) (?P<count>[a-z]+)"
    r"|(?P<suffix_count>[a-z]+) or (?P<direction>more|fewer))"
    r" (?P<other>other )?(?P<subtype>[a-z]+?)s$"
)

#: How each comparison word in `_CONTROLLED_SUBTYPE_COUNT` answers.
_SUBTYPE_COUNT_COMPARISONS = {
    "at least": operator.ge,
    "more than": operator.gt,
    "fewer than": operator.lt,
    "exactly": operator.eq,
    "more": operator.ge,
    "fewer": operator.le,
}


def _controlled_subtype_count_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as "how many <subtype>s do you control right now".

    Valakut, the Molten Pinnacle's "if you control at least five other
    Mountains". Two things make this more than a name count:

    - **CR 613.5** - the subtypes counted are the *computed* ones, so every
      land is a Mountain while Blood Moon is out, and every land you control is
      one while Dryad of the Ilysian Grove is. That is the whole Valakut combo,
      and reading `CardState.subtypes` here would miss all of it.
    - **CR 608.2a** - this same clause is asked again as the ability resolves,
      and the count is taken live both times, so a board that shrank in between
      answers False the second time and the ability is removed from the stack
      doing nothing.

    "Other" excludes the source itself (CR 700.4's "other" is "any object
    other than the object being referred to"). `None`, not False, when the
    clause is not this shape, so anything else still reaches `_fail_closed`.
    """
    match = _CONTROLLED_SUBTYPE_COUNT.match(clause)
    if match is None:
        return None
    comparison_word = match.group("comparison")
    if comparison_word is not None:
        wanted = parse_count(match.group("count"), article=False)
    else:
        comparison_word = match.group("direction")
        wanted = parse_count(match.group("suffix_count"), article=False)
    if wanted is None:
        return None

    subtype = match.group("subtype")
    controller = source.controller or game.active_player.username
    card_type = _card_type_for_word(subtype)

    count = 0
    for state in game.permanents_controlled_by(controller):
        if match.group("other") and state.id == source.id:
            continue
        characteristics = game.characteristics_of(state)
        if card_type is not None:
            if card_type in characteristics.types:
                count += 1
        elif any(word.lower() in (subtype, f"{subtype}s") for word in characteristics.subtypes):
            # "Plains" is its own plural, so the `s$` above strips the letter
            # the subtype ends in ("plain"): accept the word with it restored.
            count += 1

    return _SUBTYPE_COUNT_COMPARISONS[comparison_word](count, wanted)


def _card_type_for_word(word: str) -> Type | None:
    """The CR 300.1 card type a counted noun names, or `None` for a subtype.

    "you control at least three other creatures" counts a card type; "at least
    five other Mountains" counts a subtype (CR 205.3i). The two are counted off
    different fields of the computed characteristics, so they have to be told
    apart before counting.
    """
    for kind in Type:
        if kind.value == word:
            return kind
    return None


def _spells_cast_last_turn_holds(game: "Game", clause: str) -> bool | None:
    """The two "last turn" spell-count clauses, or None if this is neither.

    Both are ordinary CR 603.4 intervening *if* clauses, and both are answered
    from `Game.spells_cast_last_turn` - the snapshot taken as a turn begins,
    counting each spell at the moment it was cast (CR 601.2a, CR 601.2i).
    """
    if _NO_SPELLS_LAST_TURN.match(clause):
        return not any(game.spells_cast_last_turn.values())

    match = _SPELLS_CAST_LAST_TURN.match(clause)
    if match is not None:
        wanted = parse_count(match.group("count"), article=False)
        if wanted is None:
            return None
        return any(len(cast) >= wanted for cast in game.spells_cast_last_turn.values())

    return None


def event_subject_power(game: "Game", event: "GameEvent | None") -> int | None:
    """The power of `event`'s own subject - the creature that died, entered,
    attacked, or whatever else the event names (CR 603.2) - or `None` when
    there is no event, no subject, or the subject cannot be found at all.

    Reads `CardState.power` directly rather than `Game.power_of`
    (`computed_board().of(...)`, CR 613.5's layer system): a dead or
    otherwise departed subject is not part of any battlefield the layer
    system computes over, and `CardState.power` already falls back to
    `last_known_power` (CR 608.2h) the moment the object leaves the
    battlefield, the same last-known-information convention
    `intervening_if_holds`'s own "it had no -1/-1 counters on it" clause
    reads for a dying creature's counters. Shared by Drizzt Do'Urden's own
    "the difference" between a dying creature's power and its own
    (`machines/effects.py`'s `_parse_put_counters_equal_to_clause`) and
    Gruff Triplets' own "a number of +1/+1 counters equal to its power" on
    its own dies trigger - the same dying-creature's-power read, used two
    different ways.
    """
    if event is None or event.subject_id is None:
        return None
    subject = game.find_by_id(event.subject_id)
    if subject is None:
        return None
    return subject.last_known_power_toughness()[0]


def event_subject_toughness(game: "Game", event: "GameEvent | None") -> int | None:
    """`event_subject_power`'s own toughness twin - Goldvein Hydra's own
    "When this creature dies, create a number of tapped Treasure tokens
    equal to its power" reads power, but the shape ("equal to its
    `<power|toughness>`") is the same either characteristic, so both are
    kept here side by side rather than making a caller ask for power and
    compute toughness some other way. Same CR 608.2h last-known-information
    read: `CardState.toughness` already falls back to it once the subject
    has left the battlefield.
    """
    if event is None or event.subject_id is None:
        return None
    subject = game.find_by_id(event.subject_id)
    if subject is None:
        return None
    return subject.last_known_power_toughness()[1]


def _fail_closed(game: "Game", ability: TriggeredAbility, source: CardState) -> bool:
    """Record CR 603.4/608.2a's refusal and answer false - never true - for a
    clause this module cannot currently read, whether that is because nothing
    here recognises its shape or because the `CastRecord` it needs is gone
    (see `_cast_record_for_clause`). Shared so every unreadable clause leaves
    the same trail on `game.intervening_if_notices`.
    """
    game.intervening_if_notices.append(
        InterveningIfNotice(
            source_id=source.id,
            source_name=source.name,
            clause=ability.intervening_if or "",
        )
    )
    return False


def controller_of_source(game: "Game", source: CardState) -> str:
    """Whose "you" a trigger on `source` means (CR 109.5, 108.4, 108.4a).

    CR 109.5: "The words 'you' and 'your' on an object refer to the object's
    controller, its would-be controller (if a player is attempting to play,
    cast, or activate it), or its owner (if it has no controller)."

    CR 108.4: "A card doesn't have a controller unless that card represents a
    permanent or spell", and CR 108.4a: "If anything asks for the controller
    of a card that doesn't have one (because it's not a permanent or spell),
    use its owner instead."

    So the zone is what decides, not whether `CardState.controller` happens
    to be filled in: a card on the battlefield is a permanent and a card on
    the stack is a spell, and each has a real controller. A card anywhere
    else - in exile, in a graveyard, in a hand or a library - has none, and
    its owner answers instead. `CardState.controller` is not cleared by
    `move_to` and a scenario can stage an exiled card with one still on it,
    so reading it first would have quietly kept the stale value.

    This is what makes CR 702.62a's "at the beginning of *your* upkeep" the
    **owner's** upkeep for a suspended card - a card another player exiled
    with time counters (Suspended Sentence's own last line, cast by somebody
    else) still ticks on its owner's turn, exactly as `machines/casting.
    finish_suspend` already reads "you" for the third ability.

    The active player is the last resort, for a card with neither: nothing in
    a real game reaches it, since CR 108.3 gives every card in the game an
    owner.
    """
    if source.zone in (Zone.BATTLEFIELD, Zone.STACK):
        return source.controller or game.active_player.username
    return source.owner or source.controller or game.active_player.username


#: "enchanted|equipped creature is dealt [combat|noncombat] damage" - the
#: passive voice about the source's own host (CR 303.4b).
_HOST_IS_DEALT_DAMAGE_RE = re.compile(r"^(?:enchanted|equipped) creature is dealt\b")

#: Imodane, the Pyrohammer: "an instant or sorcery spell you control that
#: targets only a single creature deals damage to that creature" - the
#: dealer is a spell of the named types under the ability's controller, its
#: targets are exactly one object and that object is a creature (CR 115.1a),
#: and the damage went to that very creature.
_SINGLE_CREATURE_SPELL_DAMAGE_RE = re.compile(
    r"^an? (?P<types>instant or sorcery|instant|sorcery) spell you control that targets only "
    r"a single creature deals damage to that creature$"
)


def _single_creature_spell_damage_matches(
    game: "Game", match: "re.Match[str]", controller: str, event: GameEvent
) -> bool:
    """`_SINGLE_CREATURE_SPELL_DAMAGE_RE`'s test against one damage event."""
    if event.subject_id is None or event.target_id is None:
        return False
    if event.subject_controller != controller:
        return False
    resolving = getattr(game, "resolving", None)
    spell = (
        resolving
        if getattr(resolving, "id", None) == event.subject_id
        else game.find_by_id(event.subject_id)
    )
    if not isinstance(spell, CardState):
        return False
    kinds = {"instant": Type.INSTANT, "sorcery": Type.SORCERY}
    wanted = {kinds[word] for word in match.group("types").split(" or ")}
    types = set(event.subject_types or game.characteristics_of(spell).types)
    if not wanted & types:
        return False
    targets = list(spell.targets)
    if len(targets) != 1 or targets[0].card_id != event.target_id:
        return False
    target = game.find_by_id(event.target_id)
    if not isinstance(target, CardState):
        return False
    return Type.CREATURE in game.characteristics_of(target).types


#: Desert Were-Worm: "you attack with creatures with total power 12 or
#: greater" - the same CR 508.3d subject-less "you attack" declaration event
#: `_YOU_ATTACK_WITH_ONE_OR_MORE_RE` reads, qualified instead by the summed
#: power of everything the declaration just made an attacker (CR 613.5's
#: computed power, the same `Game.power_of` every other combat reader in
#: `machines/combat.py` already asks), rather than by a per-attacker
#: description. `machines/abilities._strip_condition_once_per_turn_trailer`
#: already cut the printed sentence's own trailing "for the first time each
#: turn" off the condition text before this ever sees it, so the count here
#: is asked fresh on every attack declaration and `TriggeredAbility.once_per_
#: turn` (CR 603.2h) is what stops it firing twice in the same turn.
_TOTAL_POWER_ATTACK_RE = re.compile(
    r"^you attack with creatures with total power (?P<threshold>\d+) or greater$",
    re.IGNORECASE,
)


def total_power_attack_threshold(condition: str) -> int | None:
    """The `N` in `_TOTAL_POWER_ATTACK_RE`'s "you attack with creatures with
    total power `N` or greater", or `None` when `condition` is not that
    shape."""
    match = _TOTAL_POWER_ATTACK_RE.fullmatch(condition.strip())
    if match is None:
        return None
    return int(match.group("threshold"))


def _tapped_batch_matching(game: "Game", description: str, controller: str) -> list[CardState]:
    """The permanents of `Game.tapped_batch` a "one or more `<description>`
    become tapped" condition counts - the description read with the grammar
    a "target" phrase uses (`machines/targeting.permanent_description`), "you
    control" as the ability's own controller. Empty when the description does
    not read, so an unread qualifier fails closed."""
    from ..targeting import permanent_description

    yours = _ONE_OR_MORE_ATTACK_YOURS.search(description) is not None
    requirement = permanent_description(_ONE_OR_MORE_ATTACK_YOURS.sub("", description).strip())
    if requirement is None:
        return []
    return [
        permanent
        for permanent in game.tapped_batch
        if permanent.zone is Zone.BATTLEFIELD
        and (not yours or game.controller_of(permanent).username == controller)
        and requirement.rejects(permanent, controller, game) is None
    ]


#: A bare list of plural subtypes - "Assassins", "Allies", "Scouts, Pirates,
#: and/or Rogues" - split on its own separators.
_SUBTYPE_LIST_SEPARATOR_RE = re.compile(
    r"\s*(?:,\s*(?:and/or|and|or)?|\band/or\b|\bor\b|\band\b)\s*"
)


def _singular_subtype(plural: str) -> str | None:
    """`plural` as a subtype in CR 205.3's vocabulary, singular and
    lower-cased, or `None`. English plurals the subtype list actually uses:
    a bare "s" (Assassins), "ies" (Allies), "ves" (Elves, Wolves), and the
    Latin "Fungi"."""
    lowered = plural.lower()
    vocabulary = {word.lower() for word in subtype_vocabulary()}
    candidates = [lowered]
    if lowered.endswith("ies"):
        candidates.append(lowered[:-3] + "y")
    if lowered.endswith("ves"):
        candidates.append(lowered[:-3] + "f")
    if lowered.endswith("s"):
        candidates.append(lowered[:-1])
    if lowered == "fungi":
        candidates.append("fungus")
    return next((candidate for candidate in candidates if candidate in vocabulary), None)


def _bare_subtype_list(description: str) -> frozenset[str] | None:
    """The singular subtypes a bare plural-subtype description names, or
    `None` when any item is not a subtype on its own."""
    items = [item for item in _SUBTYPE_LIST_SEPARATOR_RE.split(description.strip()) if item]
    singular = [_singular_subtype(item) for item in items]
    if not singular or any(item is None for item in singular):
        return None
    return frozenset(item for item in singular if item is not None)


#: One alternative of `_TYPED_ADDITIONAL_TRIGGER_RE`'s "whose": an article
#: ("another" excludes the multiplier itself) and the words every one of which
#: the ability's source has to have.
_TYPED_WHOSE_ALTERNATIVE_RE = re.compile(
    r"^(?P<article>a|an|another)\s+(?P<words>.+)$", re.IGNORECASE
)


def _typed_whose(whose: str) -> _TypedWhose | None:
    """ "a Shaman or another Wizard you control" -> two alternatives, each
    word a supertype ("legendary"), a card type (CR 205.2a) or a subtype
    (CR 205.3) - or None when a word is none of them, so an unreadable
    qualifier ("with power 2 or less") multiplies nothing."""
    text = whose.strip()
    if text.lower() == "equipped creature":
        return _TypedWhose(equipped=True, alternatives=())
    chosen = text.lower().endswith(" of the chosen type")
    if chosen:
        text = text[: -len(" of the chosen type")].strip()
    if not text.lower().endswith(" you control"):
        return None
    text = text[: -len(" you control")].strip()
    card_types = {card_type.value.lower() for card_type in Type}
    supertypes = {supertype.value.lower() for supertype in Supertype}
    subtypes = {subtype.lower() for subtype in subtype_vocabulary()} | {"permanent"}
    alternatives: list[tuple[bool, tuple[str, ...]]] = []
    for part in re.split(r",\s*(?:or\s+)?|\s+or\s+", text):
        match = _TYPED_WHOSE_ALTERNATIVE_RE.match(part.strip())
        if match is None:
            return None
        words = tuple(word.lower() for word in match["words"].split())
        if not words or any(
            word not in card_types and word not in supertypes and word not in subtypes
            for word in words
        ):
            return None
        alternatives.append((match["article"].lower() == "another", words))
    if not alternatives:
        return None
    return _TypedWhose(equipped=False, alternatives=tuple(alternatives), chosen=chosen)


def _typed_source_matches(
    game: "Game", whose: _TypedWhose, multiplier: CardState, source: CardState
) -> bool:
    """Whether `source` - the permanent whose triggered ability just
    triggered - is the one `multiplier`'s "whose" names, read off the
    computed board (CR 613.5)."""
    if whose.equipped:
        return multiplier.attached_to == source.id
    try:
        chars = game.characteristics_of(source)
        have = (
            {card_type.value.lower() for card_type in chars.types}
            | {supertype.value.lower() for supertype in chars.supertypes}
            | {subtype.lower() for subtype in chars.subtypes}
        )
    except KeyError:
        have = (
            {card_type.value.lower() for card_type in source.types}
            | {supertype.value.lower() for supertype in source.card.supertypes}
            | {subtype.lower() for subtype in source.subtypes}
        )
    if whose.chosen:
        choice = multiplier.choice
        if (
            choice is None
            or choice.kind is not ChoiceKind.CREATURE_TYPE
            or choice.value.lower() not in have
        ):
            return False
    # Only a permanent's ability is ever multiplied (`additional_trigger_times`
    # returns early off the battlefield), so "a permanent you control" is met.
    have.add("permanent")
    return any(
        (not another or source.id != multiplier.id) and set(words) <= have
        for another, words in whose.alternatives
    )


def _cause_words(types: str) -> tuple[str, ...] | None:
    """ "artifact or creature" -> ("artifact", "creature"): each alternative
    a card type (CR 205.2a), "permanent", or a subtype (CR 205.3) - or None
    when a word is none of them, so an unreadable cause matches nothing."""
    words = tuple(
        word.strip().lower() for word in re.split(r",\s*|\s+or\s+", types) if word.strip()
    )
    card_types = {card_type.value.lower() for card_type in Type}
    subtypes = {subtype.lower() for subtype in subtype_vocabulary()}
    for word in words:
        if word != "permanent" and word not in card_types and word not in subtypes:
            return None
    return words or None


def _entering_cause_matches(game: "Game", cause: str, event: GameEvent, controller: str) -> bool:
    """Whether this event is the entrance the multiplier names (CR 603.2d's
    own "an ability may state that a triggered ability triggers additional
    times" is gated by the rest of the printed sentence). `controller` is the
    multiplier's own, for "a Wizard you control entering"."""
    match = _ENTERING_CAUSE_RE.match(cause.strip())
    if match is None or event.event is not TriggerEvent.ENTERS_THE_BATTLEFIELD:
        return False
    wanted = _cause_words(match["types"])
    if wanted is None:
        return False
    entering = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    if isinstance(entering, CardState):
        try:
            chars = game.characteristics_of(entering)
            types, subtypes = tuple(chars.types), tuple(chars.subtypes)
        except KeyError:
            types, subtypes = tuple(entering.types), tuple(entering.subtypes)
        entering_controller = entering.controller
    elif event.subject_card is not None:
        types, subtypes = tuple(event.subject_card.types), tuple(event.subject_card.subtypes)
        entering_controller = event.subject_controller
    else:
        return False
    if match["yours"] and entering_controller != controller:
        return False
    if "permanent" in wanted:
        return True
    have = {str(card_type).lower() for card_type in types} | {
        subtype.lower() for subtype in subtypes
    }
    return bool(set(wanted) & have)


def _state_condition_holds(game: "Game", ability: TriggeredAbility, source: CardState) -> bool:
    """Whether this permanent's game state matches its CR 603.8 condition."""
    match = _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip())
    if match is None:
        return False
    subject = match["subject"].strip().rstrip(".").lower()
    names = {source.name.lower(), "it", "this permanent", "this creature", "this artifact"}
    # CR 603.8 reads the source by whichever type word the card prints for
    # itself ("this enchantment", "this land", "this planeswalker").
    names.update(f"this {kind.value.lower()}" for kind in game.characteristics_of(source).types)
    with contextlib.suppress(KeyError):
        names.add(game.characteristics_of(source).name.lower())
    if subject not in names:
        # A condition about some *other* object is not something this matcher
        # can read; answering False keeps CR 603.2's "only if it actually
        # matches" rather than guessing.
        return False
    needed = parse_count(match["count"], article=False)
    if needed is None:
        return False
    return source.counters[match["kind"].strip().lower()] >= needed


from ._common import (  # noqa: E402
    _ABILITY_ACTIVATED_CONDITION,
    _CLASS_BECOMES_LEVEL_CONDITION,
    _COUNTERS_PUT_CONDITION,
    _COUNTERS_PUT_ON_DESCRIPTION_CONDITION,
    _CRIME_COMMITTED_CONDITION,
    _CYCLE_CONDITION,
    _DOOR_UNLOCKED_CONDITION,
    _ENLISTS_A_CREATURE_CONDITION,
    _ENTERING_CAUSE_RE,
    _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION,
    _FINAL_CHAPTER_RESOLVES_CONDITION,
    _FORETELL_CONDITION,
    _LAND_ADDED_CHOSEN_MANA_CONDITION,
    _LAST_COUNTER_CONDITION,
    _LAST_TIME_COUNTER_CONDITION,
    _LEAVES_GRAVEYARD_CONDITION,
    _LOSES_LIFE_CONDITION,
    _LOYALTY_COUNTERS_PUT_ON_PLANESWALKER_CONDITION,
    _NTH_COUNTER_PUT_CONDITION,
    _NTH_DRAW_CONDITION,
    _ONE_OR_MORE_ATTACK_YOURS,
    _ONE_OR_MORE_BECOME_TAPPED_CONDITION,
    _ONE_OR_MORE_CARDS_INTO_YOUR_GRAVEYARD_CONDITION,
    _ONE_OR_MORE_DEAL_COMBAT_DAMAGE_RE,
    _OPPONENTS_ARE_ATTACKED_CONDITION,
    _PLAY_A_CARD_EXILED_WITH_CONDITION,
    _PLAY_A_LAND_OR_CAST_CONDITION,
    _PLAYER_COUNTERS_PUT_CONDITION,
    _PUT_INTO_LIBRARY_CONDITION,
    _REVEALED_FIRST_DRAW_CONDITION,
    _REVEALED_THIS_WAY_CONDITION,
    _RING_TEMPTS_YOU_CONDITION,
    _ROLLS_DICE_CONDITION,
    _SEARCHES_LIBRARY_CONDITION,
    _SELF_PUT_INTO_GRAVEYARD_FROM_ANYWHERE_CONDITION,
    _SOLVE_A_CASE_CONDITION,
    _STATE_COUNTER_TRIGGER_RE,
    _TIME_COUNTER_REMOVED_WHILE_EXILED_CONDITION,
    _UNTAPPED_DURING_UNTAP_STEP_CONDITION,
    _YOU_PUT_A_COUNTER_ON_QUALITY_CONDITION,
)
from .collect import (  # noqa: E402
    PLAYER_ATTACKS_WITH_N_OR_MORE_RE,
    _unread_trigger_events,
    batched_attack_minimum,
    batched_attackers,
    batched_combat_damage_sources,
    discard_occurrences,
)
from .events import CastConditionNotice, InterveningIfNotice  # noqa: E402
