import functools
import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from ...data.subtypes import subtype_vocabulary
from ...models.card import Layout, Supertype, Type
from ...models.card_state import (
    CardState,
    TargetRef,
)
from ...models.player import Player
from ...models.token import (
    PREDEFINED,
    create_tokens,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    parse_count,
)
from ..abilities import (
    _ABILITY_WORD,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    _parse_line,
)
from ..counter_effects import expand_compound_counter_puts
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    DelayedTrigger,
    RevokeGrantedAbility,
    anaphoric_delayed_trigger,
    chosen_object_turn_trigger_line,
    create_chosen_object_turn_trigger,
)
from ..layers import (
    KNOWN_KEYWORDS,
    ContinuousEffect,
    Duration,
    Layer,
    add_subtype,
    grant_ability,
    is_retention_clause,
    only_this_incarnation,
    parsed_layer_effects,
)
from ..targeting import (
    ControllerRestriction,
    TargetingProfile,
    permanent_description,
    profile_for_text,
    spell_profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
    triggers_only_off_the_stack,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, MIXED_CLAUSE, SPELL_TEXT
from ._common import (
    _OBJECT_ANAPHOR,
    AbilityEffect,
    ClauseEffect,
    Effect,
    ReferentObjectClause,
    ReferentReader,
    TargetedClause,
)


def _as_sentence(text: str) -> str:
    """`text` ending in a period, the way `machines/layers.py` reads one."""
    stripped = text.strip()
    return stripped if stripped.endswith(".") else f"{stripped}."


def _singular_card_type(word: str) -> Type | None:
    """ "creatures" / "creature" -> `Type.CREATURE` (CR 205.2a), or `None` for
    anything not one of the fifteen printed card types - a coloured, named, or
    compound qualifier ("green creatures", "Human creatures") is deliberately
    left unread rather than guessed at.
    """
    singular = word[:-1] if word.lower().endswith("s") else word
    try:
        return Type(singular.lower())
    except ValueError:
        return None


def _singular_subtype_for_count_expression(word: str) -> str | None:
    """ "Faeries" -> "faerie", "Elves" -> "elf", "Shrines" -> "shrine": a
    plural subtype word as `subtype_vocabulary` stores it (lowercased,
    singular), or None when the word is no printed subtype in any of those
    spellings.

    Named for its original one caller (`count_expression`; `_for_each_
    qualifier_count`'s G1 "for each `<qualifier>` you control" reader gained
    a second call to it during the number-sweep integration merge, once the
    shadow below was gone and the bare name it had been calling no longer
    existed) rather than plainly `_singular_subtype`, because this file
    already defines two other
    functions under that exact name for two other mechanics (amass token
    creation, and a mass-transform clause) - three module-level `def`s
    sharing one name silently overwrote each other as the module loaded, so
    by the time any of the three actually ran, all three callers got
    whichever definition was written last in the file, never their own.
    That is how "the number of Shrines you control" (Sanctum of Fruitful
    Harvest, G7-3) read zero Shrines with Sanctum itself on the battlefield:
    this function's own vocabulary-checked, properly-lowercased answer was
    unreachable, silently replaced by a same-named helper elsewhere in the
    file that only drops a trailing "s" and keeps the printed case ("Shrine",
    not "shrine" - `Counters`-style case-sensitive comparison then never
    matched). The number-sweep integration merge renamed the other two
    (`_singular_subtype_for_transform_all`, `_singular_subtype_for_amass`),
    which left no bare `_singular_subtype` defined anywhere - a third caller,
    `_for_each_qualifier_count`'s "for each `<subtype>` you control" branch,
    still called that now-undefined name and raised `NameError` on every
    subtype qualifier (Honden of Cleansing Fire's "for each Shrine you
    control") until it was pointed at this function too, its natural home
    since it is the general vocabulary-checked singulariser, not one scoped
    to amass or transform-all."""
    lowered = word.lower()
    vocabulary = subtype_vocabulary()
    candidates = [lowered, lowered.removesuffix("s")]
    if lowered.endswith("ves"):
        candidates.append(lowered.removesuffix("ves") + "f")
    return next((candidate for candidate in candidates if candidate in vocabulary), None)


#: The "and"/"or"/comma-joined card-type list `machines/replacement.
#: _COUNTER_FOR_EACH`'s own "for each `<types>` card(s)/spell(s) ..." tail
#: names - "instant and sorcery", Murktide Regent's and Ral, Leyline
#: Prodigy's own shared wording, CR 205.2a's card types read the same
#: "comma/and/or" grammar `machines/triggers._SPELLS_CAST_THIS_TURN` already
#: reads for Arclight Phoenix's "you've cast three or more instant and
#: sorcery spells this turn" - written fresh here rather than imported, since
#: this module's own `_amount_term` is the reading site and the two live in
#: different files for different callers (a triggered ability's intervening
#: if there, an entering permanent's counter count here).
_TYPE_LIST_SPLIT_RE = re.compile(r",|\band\b|\bor\b", re.IGNORECASE)


def _read_type_word_list(text: str) -> frozenset[Type] | None:
    """ "instant and sorcery" -> `{Type.INSTANT, Type.SORCERY}`, or `None` for
    a list naming anything that is not one of CR 205.2a's fifteen card types -
    fail closed rather than guess at an unlisted word."""
    types: set[Type] = set()
    for word in _TYPE_LIST_SPLIT_RE.split(text):
        word = word.strip().lower()
        if not word:
            continue
        card_type = next((kind for kind in Type if kind.value == word.rstrip("s")), None)
        if card_type is None:
            return None
        types.add(card_type)
    return frozenset(types) or None


#: "Shuffle <card's own name> into its owner's library" (Green Sun's Zenith).
#: CR 304.2/307.2's "the actions stated in its rules text are followed" runs
#: this sentence during resolution the same as any other, but the *result* -
#: the spell leaving the stack for the library instead of the graveyard - is
#: applied by `machines/replacement.py`'s `_stack_replacements` off the same
#: sentence (see its own docstring): the destination is not something a
#: spell-resolution clause *runs*, it is what CR 608.2n/CR 304.2/CR 307.2's own
#: final "put into its owner's graveyard" step is replaced by, the same split
#: `_strip_keyword_ability_lines` already draws for CR 702.88a's rebound line. Left in the text,
#: this sentence matches no clause shape `_parse_mixed_clause` reads and fails
#: the whole effect closed (CR 608.2c has no half-effect) - which is exactly
#: the bug this exists to fix: Green Sun's Zenith's search never ran because
#: its second sentence poisoned the first (`_parse_mixed_clauses`' fail-closed
#: policy, working as intended, on a clause nothing yet read). Stripping it
#: here by the resolving card's own name, not a name table, keeps this generic
#: for any future card of the same shape.
def _strip_self_shuffle_clause(card_name: str, text: str) -> str:
    if "shuffle " not in text.lower():
        return text
    pattern = re.compile(
        rf"(?:^|(?<=[.\s]))Shuffle {re.escape(card_name)} into its owner's library\.?\s*",
        re.IGNORECASE,
    )
    return pattern.sub("", text)


#: "`<self>` is all colors." (Awaken the Maelstrom, Sphinx of the Guildpact's
#: identical line on a permanent) and "`<self>` is colorless." (Ghostfire, CR
#: 105.2c - the card's colour is already the printing's empty `colors`, never
#: derived from its {2}{R} cost, CR 202.2's cost-derived colour being the
#: default a CDA overrides) are CR 604.3's characteristic-defining
#: ability: it functions in every zone, including on the stack, and - unlike
#: everything else `effect_for` reads - it is not a CR 608.2c resolution
#: instruction at all, so it never goes on the stack and never "runs".
#: `machines/layers._self_all_colors_builder` is what makes the identical
#: sentence a real `ContinuousEffect` once the object carrying it *is* a
#: permanent (Sphinx of the Guildpact); a spell face (Awaken the Maelstrom)
#: is never a permanent, so there is nothing for a layer to compute here -
#: the sentence is simply true throughout, and is stripped off the resolution
#: text the same way a keyword line already is, rather than fed to
#: `_spell_effect_or_notice` as though it were one of the spell's own
#: instructions (CR 608.2c has no verb "is" among its resolution steps).
def _strip_self_is_all_colors_sentence(card_name: str, text: str) -> str:
    lowered = text.lower()
    if " is all colors" not in lowered and " is colorless" not in lowered:
        return text
    names = {card_name, card_name.split("//")[0].strip()}
    pattern = re.compile(
        r"^(?:" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r") "
        r"is (?:all colors|colorless)\.\s*",
        re.IGNORECASE,
    )
    return pattern.sub("", text, count=1)


#: "return this card from your graveyard to your hand" - a widely templated
#: CR 112.6c ability shape ("some effects state that an ability of a card
#: functions from a zone other than the zone the card is normally in") that
#: real instants and sorceries print as a *second*, independent paragraph
#: below their own effect - Command the Stage, Repeating Barrage, Rekindled
#: Flame, Hammer of Bogardan, and dozens more, all genuine printings, not a
#: shape invented for one card. Matched narrowly on this exact phrase, not on
#: "any paragraph that happens to parse as a complete ability" - Summoner's
#: Pact's own second paragraph ("At the beginning of the next upkeep, pay
#: {2}{G}{G}. If you don't, you lose the game.") *also* parses as one
#: complete triggered ability on its own, and is nonetheless genuinely part
#: of the spell's own CR 608.2c resolution (the delayed trigger it creates,
#: read by `_parse_delayed_pay_or_lose_clauses` elsewhere in this file) - a
#: broader "strip anything ability-shaped" rule stripped that clause too and
#: silently dropped the whole delayed-cost mechanic.
_RETURNS_ITSELF_FROM_GRAVEYARD_RE = re.compile(
    r"return this card from your graveyard to your hand", re.IGNORECASE
)


def _strip_trailing_standalone_triggered_ability(text: str) -> str:
    """A printed paragraph after the first whose own effect is CR 112.6c's
    "return this card from your graveyard to your hand" is never part of
    this spell's own resolution - it is a different ability entirely, one
    that functions while the card sits in the graveyard, merely printed on
    the same card (Command the Stage's own second line is exactly this
    shape).

    Concatenating the two paragraphs into one effect text (as `Game.
    resolve_top` does, reading `spell.oracle_text` whole) let that second
    paragraph poison the first: `split_effect_clauses`'s own `\n+` separator
    cut it off as its own "clause", which of course reads as nothing this
    file's clause parsers understand, and CR 608.2c's no-half-effect
    discipline then failed the *entire* card closed - including the token
    creation the first paragraph alone would have read fine.

    Read through `_parse_line` - the same per-line reader `parse_abilities`
    itself uses - to confirm the trailing paragraph really is one complete
    ability on its own before checking its shape, so a future card's
    genuinely continued resolution text that happens to also start with a
    capital "At" or "When" mid-sentence is never mistaken for one (a real
    continuation line does not *parse* as a complete ability by itself).

    The same holds for a trailing "When you discard this card, ..." or
    "When you cycle this card, ..." paragraph (Edgar's Awakening, Choking
    Tethers): CR 113.6k makes it an ability of the card wherever the discard
    or cycle leaves it, triggered off `machines/triggers.py`
    (`triggers_only_off_the_stack`), never part of the spell's resolution.
    Trailing paragraphs are stripped one at a time from the end, so a
    keyword line printed between them (Choking Tethers' "Cycling {1}{U}")
    is left for the spell's own reader, which already skips it.
    """
    lines = text.split("\n")
    while len(lines) >= 2:
        tail = lines[-1].strip()
        if not tail:
            return "\n".join(lines)
        parsed = _parse_line(tail, [], lines[-1])
        if not (
            parsed
            and all(isinstance(ability, TriggeredAbility) for ability in parsed)
            and (
                _RETURNS_ITSELF_FROM_GRAVEYARD_RE.search(parsed[0].effect)
                # CR 113.6k: "When you discard/cycle this card" can never
                # occur while this card is a spell on the stack either, so
                # it is its own ability (Edgar's Awakening, Choking Tethers),
                # triggered off `machines/triggers.py`, never resolution text.
                or any(triggers_only_off_the_stack(ability) for ability in parsed)
            )
        ):
            break
        lines = lines[:-1]
    return "\n".join(lines)


def _strip_leading_standalone_cast_trigger(text: str) -> str:
    """A printed paragraph *before* the spell's own resolution text whose own
    ability is a `TriggerEvent.CAST_SPELL` trigger - Dash Hopes' and Temporal
    Extortion's own "When you cast this spell, any player may pay ... . If a
    player does, counter `<this spell>`." printed ahead of their real
    resolution line ("Counter target spell.").

    CR 601.2i: "Any abilities that trigger when a spell is cast ... trigger at
    this time" - the moment the spell becomes cast, which has already passed
    by the time this spell resolves (CR 608). CR 603.3 puts it on the stack as
    its own object, above the spell. So it is never part of what this spell's
    own resolution does, the identical "second paragraph, different ability"
    shape `_strip_trailing_standalone_triggered_ability` already strips for a
    *trailing* paragraph - mirrored here for a *leading* one, which
    `split_effect_clauses`'s own `\n+` separator would otherwise cut off as
    its own clause, unread by any plain player-effect parser, and CR 608.2c's
    no-half-effect rule would then fail the *whole* spell closed - including
    the "Counter target spell." sentence the second paragraph alone reads
    fine.

    Narrowed to `TriggerEvent.CAST_SPELL` specifically, unlike the trailing
    stripper's broader "any `TriggeredAbility`" shape: a genuinely
    resolution-time instruction that *creates* a delayed trigger ("At the
    beginning of the next end step, ...") also parses as a `TriggeredAbility`
    on its own, and stripping that away would silently drop part of the
    spell's own effect. A cast trigger cannot be that - CR 601.2i's moment has
    already passed by the time this spell resolves, so a leading paragraph
    that parses as one is unambiguously a separate ability, never resolution
    text of this spell. Only *this spell's own* cast trigger ("When you cast
    this spell, ...") is stripped: Dual Strike's "When you next cast an
    instant or sorcery spell ..., copy that spell." also parses as a
    CAST_SPELL trigger, but it is the resolution text that creates a delayed
    triggered ability (CR 603.7a), never a separate printed ability.
    """
    lines = text.split("\n")
    while len(lines) >= 2:
        head = lines[0].strip()
        if not head:
            return "\n".join(lines[1:])
        parsed = _parse_line(head, [], lines[0])
        if not (
            parsed
            and all(
                isinstance(ability, TriggeredAbility)
                and ability.event is TriggerEvent.CAST_SPELL
                and "this spell" in (ability.condition or "").lower()
                for ability in parsed
            )
        ):
            break
        lines = lines[1:]
    return "\n".join(lines)


def _strip_trailing_standalone_activated_ability(text: str) -> str:
    """A printed paragraph after the first whose own ability is an activated
    ability that CR 113.6j/113.6m already say functions somewhere other than
    the battlefield - Visionary's Dance's own "{2}, Discard this card: Look
    at the top two cards of your library. ..." - is never part of this
    spell's own resolution text: it is a distinct ability, one that
    functions while the card sits in a player's hand (or whatever zone the
    line itself names), merely printed on the same card, the identical
    "second paragraph, different ability" shape `_strip_trailing_standalone_
    triggered_ability` already strips for a graveyard-returning trigger.

    Left in the resolving text, `Game.resolve_top` reads `spell.oracle_text`
    whole and `split_effect_clauses`'s own `\\n+` separator cuts the
    activated ability's own cost-colon-effect shape into fragments none of
    this file's clause parsers read, and CR 608.2c's no-half-effect rule then
    fails the *entire* card closed - including a token-creation sentence the
    first paragraph alone would read fine, which is the defect this fixes.

    `ActivatedAbility.zone` is already computed (`abilities._activated_
    ability_zone`, CR 113.6j/113.6m) by the same `_parse_line` reader
    `parse_abilities` itself uses, so this only has to check that a trailing
    line parses as one or more whole activated abilities and that every one
    of them already carries a non-`None` zone - an ordinary battlefield-only
    activated ability (`zone is None`) is left untouched, because nothing
    about *it* says it is a separate object from the spell resolving on the
    stack. Trailing paragraphs are stripped one at a time from the end, the
    same as the triggered-ability sibling above.
    """
    lines = text.split("\n")
    while len(lines) >= 2:
        tail = lines[-1].strip()
        if not tail:
            return "\n".join(lines)
        parsed = _parse_line(tail, [], lines[-1])
        if not (
            parsed
            and all(isinstance(ability, ActivatedAbility) for ability in parsed)
            and all(ability.zone is not None for ability in parsed)  # type: ignore[union-attr]
        ):
            break
        lines = lines[:-1]
    return "\n".join(lines)


#: "Flashback—`<cost>`[. (reminder text)]" - CR 702.34a's own keyword line,
#: always printed last and never part of what CR 608 has a resolving spell
#: actually do: it is CR 601.3's own alternative-casting permission, read by
#: `machines/casting.py`'s `_option_from_keyword` and paid at CR 601.2b, not
#: an instruction a resolving spell carries out. Left in `effect_text`, it
#: is one more paragraph `split_effect_clauses`'s own `\n+` separator cuts
#: into a fragment none of this file's clause parsers read - usually
#: harmless (the fragment is simply its own failed clause and the body
#: above it still resolves), but Kindle the Inner Flame's own body ends in a
#: quoted granted ability, and a quote's own internal punctuation can shift
#: where the *body's* clause itself gets split, corrupting a clause that
#: would otherwise read cleanly - the identical "second paragraph poisons
#: the first" failure `_strip_trailing_standalone_triggered_ability` already
#: documents, just from a keyword line rather than a second ability.
#: Stripped once, generically, by the printed keyword shape itself, ahead of
#: every spell's own dispatch - narrowly Flashback for now, since it is the
#: one keyword-cast-option line this pool has printed after a multi-clause
#: body; a future card doing the same with Evoke, Escape, or another
#: CR 601.3 keyword-cost line widens the alternation rather than adding a
#: second stripper.
_TRAILING_FLASHBACK_LINE_RE = re.compile(r"\n+flashback[—–-]\s*\S.*$", re.DOTALL | re.IGNORECASE)


def _strip_trailing_flashback_line(text: str) -> str:
    """`_TRAILING_FLASHBACK_LINE_RE`'s shape, or `text` unchanged."""
    return _TRAILING_FLASHBACK_LINE_RE.sub("", text)


def _strip_self_exile_sentence(card_name: str, text: str) -> str | None:
    """`text` without its closing "Exile `<this spell's name>`." sentence -
    Eldritch Evolution's, Flood of Recollection's, Restock's, and every other
    instant or sorcery that ends its own resolution by exiling itself (CR
    201.5: a card referring to itself by name means that object) - or `None`
    when `text` does not end that way. The front face's name counts too, for
    a spell printed on a double-faced card.

    `_strip_keyword_ability_lines` runs first so a keyword line printed after
    the self-exile sentence - Step Between Worlds' own "Plot {4}{U}{U} (...)"
    - does not stop this from finding it at the new end: a keyword line is
    cast-time information (an alternative cost here), never part of what the
    spell's resolution does, and CR 207.2 already draws that line for
    `_strip_non_effect_preamble`'s own callers - this is the identical
    distinction applied to a spell's raw printed text instead of an ability's.
    """
    # `_INLINE_REMINDER_RE` first, the same order `_strip_non_effect_preamble`
    # already uses: a keyword line's own reminder text can carry internal
    # periods (Plot's own three-sentence parenthetical), which is what stops
    # `_is_keyword_ability_line` from recognising the line at all until that
    # parenthetical is gone.
    text = _strip_keyword_ability_lines(_INLINE_REMINDER_RE.sub("", text))
    names = {card_name, card_name.split("//")[0].strip()}
    pattern = re.compile(
        r"(?:^|(?<=[.\s]))Exile (?:"
        + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
        + r")\.\s*$",
        re.IGNORECASE,
    )
    stripped = pattern.sub("", text.strip()).strip()
    return None if stripped == text.strip() or not stripped else stripped


def _self_names_pattern(card_name: str) -> str:
    names = {card_name, card_name.split("//")[0].strip()}
    return "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))


def _strip_self_exile_with_time_counters_sentence(
    card_name: str, text: str
) -> tuple[str, int] | None:
    """`text` without its "Exile `<this spell's name>` with `<n>` time
    counters on it." sentence, and `n` - the line the self-recurring suspend
    spells close their resolution text with (Arc Blade, Suspended Sentence,
    Rousing Refrain, Reality Strobe) - or `None` when `text` has no such
    sentence ending a line. CR 201.5: the name means this very object.

    Only the end of a *line* is required, not the end of the text: every one
    of these cards prints its "Suspend N-[cost]" keyword on the line after,
    which the rest of the dispatch already reads past.
    """
    pattern = re.compile(
        r"(?:^|(?<=[.\s]))Exile (?:"
        + _self_names_pattern(card_name)
        + rf") with (?P<n>{COUNT}) time counters? on it\.(?=[ \t]*(?:\n|$))",
        re.IGNORECASE | re.MULTILINE,
    )
    match = pattern.search(text)
    if match is None:
        return None
    counters = parse_count(match.group("n"))
    if counters is None:
        return None
    stripped = (text[: match.start()] + text[match.end() :]).strip()
    if not stripped:
        return None
    return stripped, counters


def has_land_type(*subtypes: str) -> Callable[[CardState], bool]:
    """A card with any of these land subtypes, basic or not (CR 305.6).

    The fetchlands say "Search your library for a Mountain or Plains card" -
    the *land types*, not the card names - which is exactly why a shockland
    (`Land - Mountain Plains`) is a legal find and a Wastes is not.
    """
    wanted = {subtype.lower() for subtype in subtypes}

    def matches(state: CardState) -> bool:
        return bool(wanted & {subtype.lower() for subtype in state.subtypes})

    return matches


def _named_type_matcher(word: str) -> Callable[[CardState], bool]:
    """One word of a search's stated quality: a land type or a card type.

    "Mountain or Plains" names land *types* (CR 305.6, CR 205.3i), which is why
    a shockland is a legal find under its own name; a search naming a card type
    instead ("artifact or creature card") is CR 205.2a's list. Trying both and
    taking either is exactly what a one-word quality needs, since a word is
    never both at once.

    A **"non<type>"** word is CR 109.2's negation of one of CR 205.2a's card
    types - Ugin, Eye of the Storms' "colorless nonland cards". Only a card
    *type* is negated here, never a land subtype or a supertype: "nonbasic"
    reads as a supertype (CR 205.4a) this function has no access to, and
    answering "everything" for it would be a fails-open guess, so it comes back
    matching nothing, exactly as it did before this branch existed.
    `_search_quality_is_readable` is what stops such a word ever reaching a
    resolving effect in the first place.
    """
    if word.lower() == "permanent":
        # CR 110.4a: "an artifact, battle, creature, enchantment, land, or
        # planeswalker card" - one word for six card types.
        return lambda state: state.is_permanent
    if word.lower() == "double-faced":
        # "a land or double-faced card" (Invasion of Pyrulea's own ETB,
        # Track Down's identical "a creature or land card" sibling shape
        # widened to name a card's *shape* rather than a type) - CR 712.1's
        # "double-faced card": one printed on two card faces (`Card.layout`
        # is `Layout.TRANSFORM`/`Layout.MODAL_DFC` for exactly those, the
        # same check `Nick Fury, Agent of S.H.I.E.L.D.'s` own "if it's a
        # double-faced card, you may transform it" already reads off a card
        # just put onto the battlefield).
        return lambda state: state.card.layout in (Layout.TRANSFORM, Layout.MODAL_DFC)
    if word.lower().startswith("non"):
        try:
            excluded = Type(word[3:].lower())
        except ValueError:
            excluded = None
        if excluded is not None:
            return lambda state: excluded not in state.types
        # "non-Human creature" (Invasion of Ikoria's own ETB, CR 702.140a's
        # identical "non-Human creature" in mutate's own reminder-free rules
        # text) - CR 109.2's negation of a *subtype* (CR 205.3m's creature
        # types, e.g. "Human") rather than one of CR 205.2a's card types, with
        # the un-negated type word (CR 205.2a) still following it. The exact
        # negated-subtype-then-type shape `_NON_SUBTYPE_PREFIX_RE` already
        # reads for a mass instruction's own card-group qualifier
        # (`_parse_card_group_qualifier`, proven on Overlord of the Balemurk's
        # "non-Avatar creature card" and Sunderflock's "non-Elemental
        # creatures") - reused here rather than a second copy, so a search's
        # stated quality and a mass instruction's stated quality read the
        # identical negated-subtype grammar.
        negated = _NON_SUBTYPE_PREFIX_RE.fullmatch(word)
        if negated is not None:
            excluded_subtype = negated.group("subtype").lower()
            rest_type = _singular_card_type(negated.group("rest").strip())
            if rest_type is not None and excluded_subtype in {
                s.lower() for s in subtype_vocabulary()
            }:

                def non_subtype_matches(
                    state: CardState,
                    rest_type: Type = rest_type,
                    excluded_subtype: str = excluded_subtype,
                ) -> bool:
                    return rest_type in state.types and excluded_subtype not in {
                        subtype.lower() for subtype in state.subtypes
                    }

                return non_subtype_matches
        return lambda state: False
    land_type = has_land_type(word)
    try:
        card_type: Type | None = Type(word.lower())
    except ValueError:
        card_type = None
    # CR 205.4a: "The supertypes are basic, legendary, ongoing, snow, and
    # world." A supertype word stands beside a card type in exactly the same
    # "or" list - Nashi, Searcher in the Dark's "legendary and/or enchantment
    # cards" names one of each - and reading only the card type left
    # "legendary" matching nothing at all, which is a fails-open answer (an
    # effect that quietly offers fewer cards than it should), not a missed
    # one. The "basic" branch in `_quality_matcher` above stays where it is:
    # it is a *prefix* on a longer phrase ("a basic land card"), not a
    # standalone alternative.
    try:
        supertype: Supertype | None = Supertype(word.lower())
    except ValueError:
        supertype = None
    # A bare creature type (CR 205.3m) standing alone as the whole quality -
    # Last Light of Durin's Day's own "search your hand and/or library for a
    # Dragon card". `subtype_vocabulary()` is closed (CR 205.3's own printed
    # list), unlike `has_land_type`'s open string test above, so a typo still
    # fails to match rather than silently validating - the same readability
    # concern `_type_word_is_readable`'s own docstring already raises for why
    # a land subtype is not read this way. Gated on the found card actually
    # being a creature, the way every real printing of this exact search
    # shape is templated (a Dragon *card* found this way is always a
    # creature card in the pool and every off-pool printing checked for
    # this wave).
    creature_subtype = word.lower() if word.lower() in subtype_vocabulary() else None
    # CR 301.5a's Equipment - Thor, God of Thunder's own "exile target
    # Equipment, instant, or sorcery card from your graveyard" is the pool's
    # first quality phrase naming an artifact subtype rather than a creature
    # one. Only this one word: unlike `subtype_vocabulary()`'s closed
    # CR 205.3m creature list, there is no equivalent closed artifact-subtype
    # vocabulary read anywhere else in this codebase yet to reuse, and
    # guessing at the other dozen (Vehicle, Fortification, ...) with no
    # printed quality phrase in the pool to prove them against is exactly
    # the unproven generality `CLAUDE.md` asks this project not to assert.
    is_equipment_word = word.lower() == "equipment"

    def matches(state: CardState) -> bool:
        return (
            land_type(state)
            or (card_type is not None and card_type in state.types)
            or (supertype is not None and supertype in state.supertypes)
            or (
                creature_subtype is not None
                and Type.CREATURE in state.types
                and any(subtype.lower() == creature_subtype for subtype in state.subtypes)
            )
            or (
                is_equipment_word and Type.ARTIFACT in state.types and "Equipment" in state.subtypes
            )
        )

    return matches


def _quality_word_matcher(word: str) -> Callable[[CardState], bool]:
    """One space-separated word of a search's stated quality - `_named_type_
    matcher`'s bare type or land type, or that same type qualified by a color
    adjective: "a colorless creature card" (Sanctum of Ugin) names a color
    *and* a type together, not two alternatives the way "artifact or creature"
    does, so `_named_type_matcher("colorless creature")` alone would try to
    read the whole two-word phrase as one type name, fail, and match nothing
    at all - a search that silently never finds anything is exactly the kind
    of quiet gap this wave is closing, not a new one to open. `_HAND_EXILE_
    COLOR_WORDS` is reused rather than duplicated - CR 105.2c's five colors
    plus colorless mean the same thing here as they do for Ugin's Labyrinth's
    own imprint quality.
    """
    parts = word.split()
    if parts and parts[0] in _COLOR_COUNT_WORDS:
        count_matches = _COLOR_COUNT_WORDS[parts[0]]
        if len(parts) == 1:
            return lambda state: count_matches(len(state.colors))
        counted_type_matches = _named_type_matcher(parts[1])
        return lambda state: count_matches(len(state.colors)) and counted_type_matches(state)
    if len(parts) == 2 and parts[0] in _HAND_EXILE_COLOR_WORDS:
        color = _HAND_EXILE_COLOR_WORDS[parts[0]]
        type_matches = _named_type_matcher(parts[1])
        if color is None:
            return lambda state: not state.colors and type_matches(state)
        return lambda state: color in state.colors and type_matches(state)
    if len(parts) == 1 and parts[0] in _HAND_EXILE_COLOR_WORDS:
        # A colour word standing **alone** is the whole quality, with no type
        # after it to qualify: Ancient Stirrings' "a colorless card" (CR
        # 105.2c, "A colorless object has no color") and Unearth's cousins'
        # "a green card". Without this the bare word fell through to
        # `_named_type_matcher`, which tried to read "colorless" as a card
        # type or land type, found neither, and matched **nothing at all** -
        # so Ancient Stirrings looked at five cards, could legally take none
        # of them, bottomed all five, and every sweep scored it handled.
        # Silently offering fewer cards than the card says is a fails-open
        # answer, not a missed one.
        lone_color = _HAND_EXILE_COLOR_WORDS[parts[0]]
        if lone_color is None:
            return lambda state: not state.colors
        return lambda state: lone_color in state.colors
    if len(parts) == 2 and parts[0] in subtype_vocabulary():
        try:
            named_type: Type | None = Type(parts[1])
        except ValueError:
            named_type = None
        if named_type is not None:
            # "`<subtype>` `<type>` card" - Sphinx's Approach's own "a Sphinx
            # creature card" (CR 205.3, `subtype_vocabulary`) - a conjunction
            # of the named type and the named subtype, the identical "type
            # qualified by a second word" idiom the colour branch above
            # already reads for "colorless creature". Without this,
            # `_named_type_matcher` tried to read the whole two-word phrase
            # as one type or land type, found neither, and matched
            # **nothing at all** - the same fails-open gap that branch's own
            # docstring already documents for a bare colour word.
            subtype_word = parts[0]

            def subtype_and_type_matches(state: CardState) -> bool:
                return named_type in state.types and any(
                    subtype.lower() == subtype_word for subtype in state.subtypes
                )

            return subtype_and_type_matches
    return _named_type_matcher(word)


def _named_type_word_is_readable(word: str) -> bool:
    """Whether `_named_type_matcher` really reads this one word: a card type
    (CR 205.2a), a "non"-prefixed card type, a supertype (CR 205.4a), or a
    subtype WOTC has printed (CR 205.3, `subtype_vocabulary`). `has_land_type`
    accepts any string, so it cannot be the test - a typo would validate."""
    lowered = word.strip().lower()
    if lowered == "double-faced":
        return True  # CR 712.1's own shape, read by `_named_type_matcher`
    if lowered == "permanent":
        return True  # CR 110.4a's six-type umbrella, read by `_named_type_matcher`
    if lowered.startswith("non"):
        try:
            Type(lowered[3:])
        except ValueError:
            return False
        return True
    for kind in (Type, Supertype):
        try:
            kind(lowered)
        except ValueError:
            continue
        return True
    return lowered in subtype_vocabulary()


def _split_destination_zone(dest_text: str) -> Zone:
    lowered = dest_text.lower()
    if lowered.startswith("into your hand"):
        return Zone.HAND
    if lowered.startswith("into your graveyard"):
        return Zone.GRAVEYARD
    return Zone.BATTLEFIELD


def _parse_unsplittable_whole_text(text: str, *, for_spell: bool) -> TargetedClause | None:
    """Readers that need the paragraph whole, ahead of `_parse_mixed_clauses`'
    clause split: Eldritch Evolution's two-sentence search ("... where X is 2
    plus the sacrificed creature's mana value. Put that card onto the
    battlefield, then shuffle."), whose ". Put that card" the split would cut
    away from the search it completes, and Avacyn, the Purifier's "it deals
    3 damage to each other creature and each opponent", whose bare "and" the
    split would cut in two."""
    whole = " ".join(_strip_non_effect_preamble(text).split())
    return _parse_search_mv_equal_to_sacrificed_clause(
        whole, for_spell=for_spell
    ) or _parse_damage_each_other_type_and_each_opponent_clause(whole, for_spell=for_spell)


def _parse_comma_chained_player_clause(clause: str) -> ClauseEffect | None:
    """A run of plain player instructions joined by bare commas - Faithful
    Mending's "You gain 2 life, draw two cards".

    `split_effect_clauses` cuts on a period, a newline, "then" and "and", but
    not on a bare comma, because a comma inside a single instruction is
    common ("search your library for a creature card, put it onto the
    battlefield"). So a comma-joined *list* of instructions arrives here
    whole and matches nothing. CR 608.2c is the reading: the parts run in the
    order written.

    Fail-closed in the usual way - every part must be readable on its own, or
    this returns `None` and the whole clause stays unread. The subject is
    printed once, on the first part ("You gain 2 life, draw two cards"), so
    later parts are retried with "you " restored the same way
    `_parse_optional_player_clause` already retries a "you may" body.
    """
    parts = [part.strip() for part in clause.split(",") if part.strip()]
    if len(parts) < 2:
        return None
    chain: list[ClauseEffect] = []
    for part in parts:
        parsed = parse_clause_effect(part) or parse_clause_effect(f"you {part}")
        if parsed is None:
            return None
        chain.append(parsed)

    def run(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        for step in chain:
            step(game, player, source, source_id)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return run


#: "other than Werewolves and Wolves" - an exclusion list, whose "and" joins
#: two names inside one clause rather than two instructions. Bounded to the
#: sentence so it cannot swallow a following instruction.
_EXCLUSION_LIST_AND_RE = re.compile(r"other than [^.\n]+", re.IGNORECASE)
_AND_SENTINEL = "\x00and\x00"

#: "You and permanents you control gain hexproof ..." (Veil of Summer) - a
#: compound *subject* joined by "and", not two CR 608.2c instructions. The
#: left side of this particular "and" is a bare player subject with no verb
#: of its own yet ("You"), and the right side opens a plural group noun
#: phrase ("permanents you control") that shares the verb still to come.
#: Splitting there would cut the subject in half and leave a bare "You" with
#: nothing to do, the same way `_EXCLUSION_LIST_AND_RE` protects an
#: exclusion list's "and" from being read as a second instruction.
#:
#: Anchored to the start of the clause (start of text, right after a
#: sentence-ending ". ", or right after a line break) so it only fires when
#: "you and" itself opens the subject - the shape this guard exists for -
#: and never masks a genuine two-instruction "and" that happens to follow
#: "you" somewhere later in a sentence.
_PLAYER_GROUP_SUBJECT_AND_RE = re.compile(
    r"(?:\A|(?<=\.\s)|(?<=\n))you and (?=(?:permanents|creatures|players?)\s+you\s+control\b)",
    re.IGNORECASE,
)

#: "You and target opponent each ..." (Secret Rendezvous, Farsight Adept) -
#: `_PLAYER_GROUP_SUBJECT_AND_RE`'s compound subject with a targeted player as
#: the second half, read whole by `_parse_you_and_target_player_each_clause`.
_YOU_AND_TARGET_PLAYER_SUBJECT_AND_RE = re.compile(
    r"(?:\A|(?<=\.\s)|(?<=\n)|(?<=,\s))you and (?=target (?:player|opponent) each\b)",
    re.IGNORECASE,
)

#: CR 702.11f: "'Hexproof from [quality A] and from [quality B]' is
#: shorthand for 'hexproof from [quality A]' and 'hexproof from [quality
#: B]'; it behaves as two separate hexproof abilities" - one clause, not two
#: CR 608.2c instructions in sequence (Veil of Summer: "hexproof from blue
#: and from black"). CR 702.16g reads protection's own "from [quality A] and
#: from [quality B]" list the identical way, so this is bound to the shared
#: "from ... and from ..." shape rather than to either keyword's own name.
#: Bounded to the line so it cannot reach across a sentence boundary into an
#: unrelated later instruction.
_QUALITY_LIST_AND_FROM_RE = re.compile(r"\bfrom\s+[^.\n]*?\s+and\s+from\b", re.IGNORECASE)

#: "all hands and graveyards" (Worldfire's "Exile all cards from all hands and
#: graveyards.") / "target player's hand and graveyard" (Identity Crisis) - a
#: list of zones one instruction acts on (CR 400.1), not two instructions.
#: Bounded to a zone noun on *both* sides of the "and", so a trailing "and
#: draw ..." after "hand" still splits.
_ZONE_PAIR_AND_RE = re.compile(
    r"\b(?:hands?|graveyards?|librar(?:y|ies)) and (?:hands?|graveyards?|librar(?:y|ies))\b",
    re.IGNORECASE,
)

#: A "then" standing at the **head** of its own sentence - "Look at the top
#: five cards ... Then put the rest on the bottom of your library." (Ancient
#: Stirrings), "earthbend 2. Then search your library ..." (Earthbender
#: Ascension), "... deals 1 damage to any target. Then amass Orcs 1."
#: (Orcish Bowmasters).
#:
#: `_CLAUSE_SEPARATOR` eats "then" only where it *joins* two clauses inside
#: one sentence ("Scry 2, then draw a card"), so this one survives the split
#: glued to the front of the clause it introduces and no downstream parser
#: can read what is left. Stripped **after** the split rather than folded
#: into the separator, because the separator has already found the sentence
#: boundary by then and there is nothing left for a head-anchored alternative
#: to match against.
#:
#: Dropping the word is sound, not a guess: CR 608.2c is "The controller of
#: the spell or ability follows its instructions in the order written", and a
#: sentence-initial "then" is that order stated out loud. It carries no
#: instruction of its own, and every other ordering the engine reads - the
#: infix "then" the separator already eats, and the bare sentence break -
#: runs the clauses in exactly this order anyway.
_LEADING_THEN_RE = re.compile(r"^then\s+", re.IGNORECASE)

#: "a 3/3 blue and red Elemental creature token" (Artistic Process), "a 4/3
#: white and black Vampire Demon creature token" (Vito, Fanatic of
#: Aclazotz) - two of CR 105.1's colour words joined by "and" are one
#: adjective phrase naming a multicoloured object, never two CR 608.2c
#: instructions: an instruction never opens on a bare colour word.
_COLOUR_PAIR_AND_RE = re.compile(
    r"\b(?:white|blue|black|red|green)\s+and\s+(?:white|blue|black|red|green)\b",
    re.IGNORECASE,
)

#: "lose all abilities and have base power and toughness 0/2" (Sudden
#: Spoiling) - one CR 611.2 instruction setting two characteristics at once
#: (CR 613.1f and CR 613.4b), not three instructions joined by "and".
_LOSE_ALL_AND_BASE_PT_RE = re.compile(
    r"\blos(?:e|es) all abilities and (?:have|has) base power and toughness \d+/\d+",
    re.IGNORECASE,
)

#: "instant and sorcery cards" (Wisdom of Ages, Steal the Show, Blitz of the
#: Thunder-Raptor), "artifact and creature card" (Fix What's Broken) - two of
#: CR 205.2a's fifteen printed card types joined by "and" naming one group of
#: cards, the identical "and is really an adjective pair" shape `_COLOUR_
#: PAIR_AND_RE` already masks for two colour words - never two CR 608.2c
#: instructions, since an instruction never opens on a bare type word either.
#: Built from `Type`'s own values rather than a hand-copied word list, so a
#: type this engine adds later is covered here for free; bounded by a
#: lookahead for "card(s)" immediately after (never consuming it, so the
#: unmasked text still reads "cards" for whichever reader wants it next) so
#: this never masks an unrelated "and" that happens to follow a type word for
#: some other reason.
#: "permanents you own and control" (Yorion, Sky Nomad) - one ownership-and-
#: control qualifier, not two instructions.
_YOU_OWN_AND_CONTROL_AND_RE = re.compile(r"\byou own and control\b", re.IGNORECASE)
_CARD_TYPE_PAIR_AND_RE = re.compile(
    rf"\b(?:{'|'.join(t.value for t in Type)})\s+and\s+"
    rf"(?:{'|'.join(t.value for t in Type)})(?=\s+cards?\b)",
    re.IGNORECASE,
)


#: A sentence that opens "[Then ]if `<condition>`," and whose consequence
#: runs to the sentence's end with no further comma (a comma would mean a
#: compound condition or a list this does not judge) - see
#: `split_effect_clauses`. CR 118.12's "if you do/don't" riders are left to
#: the optional-action readers that already pair them with their "you may".
_IF_SENTENCE_CONSEQUENCE_RE = re.compile(
    r"(?P<head>(?:^|(?<=\.\s))(?:then\s+)?if (?!(?:you|they|a player|that player) "
    r"(?:do|does|don't|doesn't)\b)[^,.]+,\s*)(?P<consequence>[^.,]*)(?=\.|$)",
    re.IGNORECASE,
)


def split_effect_clauses(text: str) -> list[str]:
    """Break an effect into the clauses CR 608.2c executes in order.

    "The controller of the spell or ability follows its instructions in the
    order written" - so a multi-clause effect is not one opaque blob, it is a
    sequence, and each piece is checked and run on its own.
    """
    text = text.strip()
    # CR 207.2a: a spell's own printed text is not run through
    # `machines/abilities.py`'s reminder stripping the way an ability's
    # `effect` field is, so Preordain's trailing "(To scry 2, look at ...)"
    # is still here and would otherwise be split into clauses of its own.
    while True:
        stripped = re.sub(r"\s*\([^()]*\)\s*$", "", text).strip()
        if stripped == text:
            break
        text = stripped
    text = expand_compound_counter_puts(text).rstrip(".")
    # CR 111.3: a token's (or a granted object's) own quoted ability is that
    # object's *stated text*, never part of the outer spell's own CR 608.2c
    # instruction sequence - Valor's Reach Tag Team's own "Create two 3/2 red
    # and white Warrior creature tokens with 'Whenever this token and at
    # least one other creature token attack, put a +1/+1 counter on this
    # token.'" has an "and" *inside* the quoted ability (CR 700.4's own
    # "another") that is not a second instruction at all, and every generic
    # "and"/comma/period this function or `_CLAUSE_SEPARATOR` reads as a
    # clause boundary could equally fall inside a quoted span - masked here,
    # before any of it runs, and restored once the whole split is done, the
    # identical technique `_parse_token_list_clause` already uses for its own
    # narrower comma-separated-tokens case.
    quoted: list[str] = []

    def _mask_quote(match: re.Match[str]) -> str:
        quoted.append(match.group(0))
        return f"\x00q{len(quoted) - 1}\x00"

    text = _QUOTED_SPAN_RE.sub(_mask_quote, text)
    # "by creatures other than Werewolves and Wolves" is one exclusion list,
    # not two instructions: the "and" joins two creature types inside a single
    # clause, where everywhere else it joins two things CR 608.2c does in
    # order. Masked across the split and restored after, so the separator
    # stays the simple thing it is.
    masked = _EXCLUSION_LIST_AND_RE.sub(lambda m: m.group(0).replace(" and ", _AND_SENTINEL), text)
    # "You and permanents you control gain hexproof ..." - a compound subject,
    # not two instructions (see `_PLAYER_GROUP_SUBJECT_AND_RE`'s docstring).
    # Same replace-in-place idiom as `_EXCLUSION_LIST_AND_RE` above, so the
    # restore below (a plain "and" -> " and " swap) round-trips it exactly.
    masked = _PLAYER_GROUP_SUBJECT_AND_RE.sub(
        lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked
    )
    # "You and target opponent each draw three cards." - the same compound
    # subject, with a targeted player in place of the group.
    masked = _YOU_AND_TARGET_PLAYER_SUBJECT_AND_RE.sub(
        lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked
    )
    # "hexproof from blue and from black" (CR 702.11f/702.16g) - one clause,
    # not two instructions.
    masked = _QUALITY_LIST_AND_FROM_RE.sub(
        lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked
    )
    masked = _ZONE_PAIR_AND_RE.sub(lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked)
    # "blue and red Elemental creature token" - one colour phrase.
    masked = _COLOUR_PAIR_AND_RE.sub(lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked)
    # "instant and sorcery cards" / "artifact and creature card" - one card
    # type list, not two instructions.
    masked = _CARD_TYPE_PAIR_AND_RE.sub(
        lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked
    )
    masked = _YOU_OWN_AND_CONTROL_AND_RE.sub(
        lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked
    )
    masked = _LOSE_ALL_AND_BASE_PT_RE.sub(
        lambda m: m.group(0).replace(" and ", _AND_SENTINEL), masked
    )
    # "Then if it has two or more velocity counters on it, sacrifice it and
    # draw two cards." (Daredevil Dragster): the condition governs the whole
    # consequence, both halves of its "and" (CR 608.2c) - kept one clause so
    # `_parse_condition_clause` reads it whole, never split into a
    # conditional sacrifice and an unconditional draw.
    masked = _IF_SENTENCE_CONSEQUENCE_RE.sub(
        lambda m: m.group("head") + m.group("consequence").replace(" and ", _AND_SENTINEL),
        masked,
    )
    split = (
        re.sub(
            r"\x00q(\d+)\x00",
            lambda m: quoted[int(m.group(1))],
            _LEADING_THEN_RE.sub("", clause.strip()).replace(_AND_SENTINEL, " and "),
        )
        for clause in _CLAUSE_SEPARATOR.split(masked)
    )
    return [clause for clause in split if clause.strip()]


#: A cost paid before the spell is cast (CR 118.8a) - never part of what the
#: spell does on resolution, but printed on the same line block Bone
#: Splinters, Fumarole, and Cathartic Reunion put ahead of their effect.
_ADDITIONAL_COST_LINE_RE = re.compile(
    r"^As an additional cost to cast this spell, [^.]+\.\s*", re.IGNORECASE | re.MULTILINE
)
#: "X can't be greater than <bound>." (Soul Immolation's own cap on its
#: "blight X" additional cost) - a second sentence restricting *how* the
#: additional cost's own X may be chosen (CR 601.2b), printed right after
#: `_ADDITIONAL_COST_LINE_RE`'s own sentence and, like it, no part of what
#: the spell does once it resolves. `machines/casting._X_CAP` reads this
#: same sentence for the bound it actually enforces while X is announced;
#: this only strips it, the same way `_ADDITIONAL_COST_LINE_RE` strips its
#: own sentence, so the real effect sentence behind it - "Soul Immolation
#: deals X damage to ..." - is what `_strip_non_effect_preamble` leaves
#: for `parse_mixed_effect_for_spell` to read.
#:
#: `(?:X|\d+)`, not a bare "X": `effect_for`'s own substitution retry
#: (`substitute_x`) runs on the *whole* unstripped text before this ever
#: sees it, so a real X of 2 turns the printed "X can't be greater than
#: ..." into "2 can't be greater than ..." first - a literal "X"-only
#: pattern would stop matching on exactly the substituted pass that was
#: supposed to make the rest of the text readable.
_X_CAP_LINE_RE = re.compile(
    r"^(?:X|\d+) can'?t be greater than [^.]+\.\s*", re.IGNORECASE | re.MULTILINE
)
#: A static quality of the spell itself, not an instruction it carries out -
#: Abrupt Decay prints this ahead of its "Destroy target nonland permanent
#: with mana value 3 or less."
_CANT_BE_COUNTERED_LINE_RE = re.compile(
    r"^This spell can't be countered\.\s*", re.IGNORECASE | re.MULTILINE
)
#: The same static quality behind a condition - Exquisite Firecraft's spell
#: mastery line, "If there are two or more instant and/or sorcery cards in
#: your graveyard, this spell can't be countered." It functions on the stack
#: (CR 113.6g, CR 604.5) and is read there by `casting_restrictions.
#: conditionally_cannot_be_countered`; it is not an instruction, so it is
#: stripped here only when that reader can read the condition - an unread
#: condition stays in the text and leaves the spell unread.
_CONDITIONAL_CANT_BE_COUNTERED_LINE_RE = re.compile(
    r"^(?:[A-Z][A-Za-z' -]{2,30}? \u2014 )?if (?P<condition>[^,\n]+), "
    r"this spell can't be countered(?: and the damage can't be prevented)?\.[ \t]*\n?",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_conditional_cant_be_countered_line(text: str) -> str:

    return _CONDITIONAL_CANT_BE_COUNTERED_LINE_RE.sub(
        lambda found: (
            "" if _effect_condition_is_readable(found.group("condition")) else found.group(0)
        ),
        text,
    )


#: A genuinely modal card (CR 700.2 - a bulleted list preceded by a "Choose
#: ..." instruction) needs a registry keyed by mode, not by card - a later
#: wave's job. Bailing here keeps a modal card's one parseable mode from being
#: read as the card's one and only effect - true whether that mode happens to
#: be a targeted clause (Abrade's "Destroy target artifact.") or a plain
#: player clause, which is exactly the fails-open shape a modal card with
#: every mode player-parseable would hit if this check lived only on the
#: targeted side.
#:
#: `is_modal_text` (backed by `machines/modes.py`'s real CR 700.2 parser) is
#: used rather than a prefix match on "Choose", because plenty of cards read
#: "Choose target creature ..." or "Choose a creature type" as ordinary
#: instruction text with no bulleted list at all - Galvanic Discharge and
#: Surgical Extraction, among this pool's fixtures, were losing their entire
#: effect to that over-broad match before this fix.


#: A whole line that is nothing but reminder text (CR 207.2a: "Reminder text
#: is italicized text within parentheses that summarizes a rule that applies
#: to that card"). `split_effect_clauses` already strips one trailing at the
#: very end of the text; Dismember and Mutagenic Growth print theirs *first*
#: instead - "({G/P} can be paid with either {G} or 2 life.)\nTarget creature
#: gets +2/+2 until end of turn." - so a line-anywhere strip is needed too.
#: Reminder text is never rules text regardless of where it sits, so this is
#: safe wherever it matches.
_REMINDER_LINE_RE = re.compile(r"^[ \t]*\([^()]*\)[ \t]*\n+", re.MULTILINE)

#: Reminder text that sits mid-sentence rather than on its own line
#: (`_REMINDER_LINE_RE`'s shape) or at the very end of the whole text
#: (`split_effect_clauses`'s own trailing strip) - Opt's "Scry 1. (Look at
#: the top card of your library. You may put that card on the bottom.)\nDraw
#: a card." prints its reminder text right after the first clause's period,
#: mid-line. Left alone, the periods *inside* the parenthetical get read by
#: `_CLAUSE_SEPARATOR` as clause boundaries of their own, producing
#: unparseable fragments ("(Look at the top card of your library", "You may
#: put that card on the bottom.)") that took the whole spell down to no
#: effect (CR 608.2c's fail-closed-per-clause-run has no notion of a clause
#: that is really reminder text wearing a period). CR 207.2a: reminder text
#: is never rules text wherever it sits, so stripping it anywhere is safe.
_INLINE_REMINDER_RE = re.compile(r"[ \t]*\([^()]*\)")


#: Force of Will's and Force of Negation's own CR 118.9 pitch line - "You may
#: pay 1 life and exile a blue card from your hand rather than pay this
#: spell's mana cost." or, gated on a plain timing condition rather than a
#: numbered rule, "If it's not your turn, you may exile a blue card from your
#: hand rather than pay this spell's mana cost."
#: Read (and paid) by `machines/cost.alternative_cost_offers`/`machines/
#: casting.Casting.use_pitch_cost` - never part of what the *spell* does on
#: resolution, so it is stripped here the same way `_ADDITIONAL_COST_LINE_RE`
#: strips CR 118.8a's "As an additional cost to cast this spell, ...".
_PITCH_ALTERNATIVE_COST_LINE_RE = re.compile(
    # The leading condition is read generally, not as the one Force of Negation
    # happens to print: every Trap gates its own alternative cost on a
    # condition of its own ("If an opponent cast three or more spells this
    # turn, you may pay {0} rather than pay this spell's mana cost." -
    # Mindbreak Trap). CR 118.9 makes the whole sentence a cost, "a cost listed
    # in a spell's text ... that its controller may pay rather than paying the
    # spell's mana cost", so it is never part of what the spell does on
    # resolution, whatever gates it. The `[^.]` guards keep the match inside
    # one sentence.
    r"^(?:If [^.]+?, )?You may [^.]+? rather than pay this spell's mana cost\.\s*",
    re.IGNORECASE | re.MULTILINE,
)

#: "If you control a commander, you may cast this spell without paying its mana
#: cost." (Deflecting Swat) - the free half of the same CR 118.9 family
#: `_PITCH_ALTERNATIVE_COST_LINE_RE` reads: "an alternative cost is a cost
#: listed in a spell's text ... that its controller may pay rather than paying
#: the spell's mana cost". CR 118.9b adds that alternative costs are generally
#: optional, which is the "you may". Either way it is a cost, never part of
#: what the spell *does* on resolution, so it is stripped here for the same
#: reason - left in, it is one unreadable clause and, the paragraph being
#: atomic, it would take the sentence printed beside it down with it.
#:
#: The leading condition is read generally rather than as the commander one
#: Deflecting Swat happens to print, exactly as the pitch line above does.
_FREE_ALTERNATIVE_COST_LINE_RE = re.compile(
    r"^(?:If [^.]+?, )?You may cast this spell without paying its mana cost\.\s*",
    re.IGNORECASE | re.MULTILINE,
)

#: CR 103.6b's "You may reveal this card from your opening hand." (plus
#: whatever rider it carries, up to the end of that one printed line) and CR
#: 103.6a's "If this card is in your opening hand, ..." - Providence's own
#: "You may reveal this card from your opening hand. If you do, at the
#: beginning of the first upkeep, your life total becomes 26." CR 103.6's
#: whole sequence runs before the mulligan process is even over (CR 103.5),
#: long before this card could ever be cast - `machines/opening_hand.py` owns
#: it entirely, reading the same paragraph directly off `Card.oracle_text`.
#: Left in here, it is one clause `effect_for`'s dispatch cannot read (it
#: describes something that happens before a game turn exists, never a
#: resolution instruction) and, the paragraph being atomic, it would take
#: Providence's own second line - "Your life total becomes 26." - down with
#: it, the identical preamble-poisoning failure `_SELF_COST_REDUCTION_LINE_RE`
#: already documents for a cost line ahead of an unrelated resolving one.
_OPENING_HAND_ACTION_LINE_RE = re.compile(
    r"^(?:You may reveal this card from your opening hand"
    r"|If this card is in your opening hand)\b[^\n]*\.\s*",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_keyword_ability_lines(text: str) -> str:
    """Drop every keyword-ability line from a multi-line block of rules text.

    Multi-line only, and deliberately so. The bug being fixed is a keyword
    line *poisoning a sentence printed beside it*, which cannot happen when
    there is only one line; and a single line is also what every caller that
    hands this function something other than a card's whole printed text
    passes - one activated ability's effect ("draw a card", with the full stop
    already trimmed off by `machines/abilities`), one mode of a modal spell,
    one clause. Applying the shape rule to those would strip the instruction
    itself, so it is not applied to them at all.
    """
    lines = text.split("\n")
    if len(lines) < 2:
        return text
    return "\n".join(line for line in lines if not _is_keyword_ability_line(line))


#: CR 207.2c's own closed list: "The ability words are adamant, addendum,
#: alliance, battalion, bloodrush, celebration, channel, chroma, cohort,
#: constellation, converge, council's dilemma, coven, delirium, descend 4,
#: descend 8, disappear, domain, eerie, eminence, enrage, fateful hour,
#: fathomless descent, ferocious, flurry, formidable, grandeur, hellbent,
#: heroic, imprint, infusion, inspired, join forces, kinship, landfall,
#: lieutenant, magecraft, metalcraft, morbid, opus, pack tactics, paradox,
#: parley, radiance, raid, rally, renew, repartee, revolt, secret council,
#: spell mastery, strive, survival, sweep, tempting offer, threshold,
#: undergrowth, valiant, vivid, void, and will of the council." Looked up in
#: this session with `mise run rules:find 207.2`.
#:
#: The rule goes on to say an ability word "[has] no special rules meaning
#: and no individual entries in the Comprehensive Rules" - which is exactly
#: what makes this list also the proof that a same-shaped CR 702 *keyword*
#: label is never one of these. Companion (CR 702.139a: "Companion is a
#: keyword ability ... written as 'Companion—[Condition]'") prints with the
#: identical spaced em dash a real ability word does (Yorion, Sky Nomad:
#: "Companion — Your starting deck contains ..."), but "companion" is absent
#: from this list, and CR 702.139a very much is an "individual entry in the
#: Comprehensive Rules" - so the two vocabularies are disjoint by
#: construction, not by a per-card guess. Channel and Imprint (Boseiju, Who
#: Endures's "Channel — {1}{G}, Discard this card: ..."; Isochron Scepter's
#: "Imprint — When this artifact enters, ...") *are* on this list - CR 207.2c
#: is explicit that they carry no rule of their own beyond being an ability
#: word, so stripping their label here is correct, not a gap.
_ABILITY_WORDS = frozenset(
    {
        "adamant",
        "addendum",
        "alliance",
        "battalion",
        "bloodrush",
        "celebration",
        "channel",
        "chroma",
        "cohort",
        "constellation",
        "converge",
        "council's dilemma",
        "coven",
        "delirium",
        "descend 4",
        "descend 8",
        "disappear",
        "domain",
        "eerie",
        "eminence",
        "enrage",
        "fateful hour",
        "fathomless descent",
        "ferocious",
        "flurry",
        "formidable",
        "grandeur",
        "hellbent",
        "heroic",
        "imprint",
        "infusion",
        "inspired",
        "join forces",
        "kinship",
        "landfall",
        "lieutenant",
        "magecraft",
        "metalcraft",
        "morbid",
        "opus",
        "pack tactics",
        "paradox",
        "parley",
        "radiance",
        "raid",
        "rally",
        "renew",
        "repartee",
        "revolt",
        "secret council",
        "spell mastery",
        "strive",
        "survival",
        "sweep",
        "tempting offer",
        "threshold",
        "undergrowth",
        "valiant",
        "vivid",
        "void",
        "will of the council",
    }
)


def _strip_ability_word_labels(text: str) -> str:
    """Strip a line-leading CR 207.2c ability word off every line of `text`.

    "Metalcraft — Galvanic Blast deals 4 damage instead if you control three
    or more artifacts." is one instruction with a label glued to the front of
    it, not two - CR 207.2c says the word itself "[has] no special rules
    meaning", so the clause underneath is exactly "Galvanic Blast deals 4
    damage instead if you control three or more artifacts." once the label is
    gone. `machines/abilities.py` already strips the identical label shape
    off an *ability* line (`_parse_line`); this is the spell-text twin,
    reusing that module's own `_ABILITY_WORD` regex rather than a second copy
    of it.

    Guarded by `_ABILITY_WORDS`, CR 207.2c's own closed list: a label that is
    not on it is left alone, which is what keeps a same-shaped CR 702 keyword
    (Companion) from being misread as a bare label and having its own cost or
    restriction text corrupted. See `_ABILITY_WORDS`'s docstring for why
    membership in that list is a sound test rather than a guess.

    Applied per line, after `_strip_keyword_ability_lines` has already
    dropped whichever lines are nothing but a keyword (that check only
    matches a line with no " —" in it - see `_is_keyword_ability_line` -
    so it never sees an ability-word line to begin with, and running this
    first would strip the label and make a genuine multi-word ability line
    such as "Threshold — Whenever ~ attacks, ..." look like a bare keyword
    line once "Threshold — " were gone).
    """
    lines = text.split("\n")
    stripped: list[str] = []
    for line in lines:
        match = _ABILITY_WORD.match(line)
        if match is not None:
            label = match.group(1).strip().replace("’", "'").lower()
            if label in _ABILITY_WORDS:
                line = line[match.end() :]
        stripped.append(line)
    return "\n".join(stripped)


@functools.lru_cache(maxsize=16384)
def _strip_non_effect_preamble(text: str) -> str:
    """Sentences that describe the spell but are not part of resolving it.

    Memoised: a pure function of `text` (every step is a regex over it), and
    the reader chain asks it of the same effect text hundreds of times."""
    text = _ADDITIONAL_COST_LINE_RE.sub("", text)
    text = _X_CAP_LINE_RE.sub("", text)
    text = _CANT_BE_COUNTERED_LINE_RE.sub("", text)
    text = _strip_conditional_cant_be_countered_line(text)
    text = _OPENING_HAND_ACTION_LINE_RE.sub("", text)
    text = _PITCH_ALTERNATIVE_COST_LINE_RE.sub("", text)
    text = _FREE_ALTERNATIVE_COST_LINE_RE.sub("", text)
    text = _SELF_COST_REDUCTION_LINE_RE.sub("", text)
    text = _PER_COUNT_COST_REDUCTION_LINE_RE.sub("", text)
    text = _TIMING_COST_REDUCTION_LINE_RE.sub("", text)
    text = _COST_INCREASE_PER_TARGET_LINE_RE.sub("", text)
    text = _REMINDER_LINE_RE.sub("", text)
    text = _INLINE_REMINDER_RE.sub("", text)
    # Last, so the shape rule sees each line with its CR 207.2a reminder text
    # already gone - "Improvise (Your artifacts can help cast this spell. ...)"
    # carries two full stops inside the parenthetical and would fail the
    # no-full-stop test with them still attached.
    text = _strip_keyword_ability_lines(text)
    # CR 207.2c: an ability word is a label, not an instruction (see
    # `_ABILITY_WORDS`). Last, so it sees the same already-shape-checked
    # lines `_strip_keyword_ability_lines` did.
    return _strip_ability_word_labels(text)


#: A plain sentence boundary - a full stop (or ! or ?) followed by
#: whitespace and a capital letter, digit, or opening parenthesis, or a bare
#: line break. Deliberately simpler than English sentence-splitting in
#: general: this only ever sees text already narrowed to one resolving
#: object's own effect body (see `_plain_resolution_sentences`'s docstring),
#: never a run-on abbreviation or a decimal number.
#:
#: "this permanent" also opens a sentence: `abilities.self_normalized_effect_
#: text` rewrites a sentence-initial self-name ("Adrestia becomes an Assassin
#: ...") to that lowercase CR 201.5 spelling, so the capital the boundary
#: looked for is gone.
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(0-9]|this permanent\b)|\n+")


def _plain_resolution_sentences(text: str) -> list[str]:
    """`text` - a single spell's or ability's own already-isolated resolution
    effect body - split into sentences on plain full-stop/line-break
    boundaries, with reminder text (`_REMINDER_LINE_RE`/`_INLINE_REMINDER_RE`)
    stripped first so a reminder's own internal periods (Empower Jace's own
    parenthetical explanation) are never read as sentence boundaries.

    Deliberately **not** `machines/layers.resolution_effect_sentences`: that
    splitter is built to read a *permanent's whole printed oracle text* for
    the battlefield sweep (`machines/layers.py::effects_for`), and as part of
    that job it also strips a triggered ability's own leading condition and
    an activated ability's own leading cost - exactly right when the input
    is a permanent's raw lines, and exactly wrong here. `effect_for`,
    `trigger_effect_for`, and `activated_effect_for` are each called with one
    object's own resolution text, already separated from any such prefix -
    except for a **permanent spell**, whose full, unfiltered oracle text
    (keyword lines and a granted triggered ability's own body included) is
    still handed to `effect_for` every time it resolves (CR 608.3a: there is
    nothing there for any parser to read, by design). Reusing the smart
    splitter for this composition wave's own sentence-level checks read
    Craterhoof Behemoth's leading "When this creature enters," off as noise
    and matched its *triggered* ability's own pump sentence as though it
    were the permanent spell's own effect - the pump ran once, with the
    wrong board, during the spell's own resolution, and again, correctly,
    when the triggered ability itself resolved afterward.

    A bare "It's still a `<type>`." (CR 205.1b) is folded back onto the
    sentence before it, the same way `machines/layers._fold_retention_
    clauses` already folds it for the smart splitter: it is CR 205.1b's own
    qualifier on the type change in front of it, never an instruction of its
    own, so leaving it as a separate "sentence" here would misread Jolrael,
    Voice of Zhalfir's animation as carrying an unread sibling clause.
    """
    without_reminders = _INLINE_REMINDER_RE.sub("", _REMINDER_LINE_RE.sub("", text))
    stripped = without_reminders.strip()
    if not stripped:
        return []
    parts = [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(stripped) if part.strip()]
    folded: list[str] = []
    for part in parts:
        if folded and is_retention_clause(part):
            folded[-1] = f"{folded[-1].rstrip()} {part}"
            continue
        folded.append(part)
    return folded


#: "Until end of turn, any number of target creatures each gain "`<ability>`"."
#: (Launch the Fleet) and "Until end of turn, up to two target creatures you
#: control each gain "`<ability>`"." (Warriors' Lesson, off-pool - proves this
#: generalises past "any number of" to "up to N" and past no-controller-
#: qualifier to "you control") - CR 611.2's "until end of turn" duration on
#: CR 113.10a's ability-adding grant, aimed at *targets* rather than at a
#: static source's own board-wide group (`_GRANT_QUOTED_ABILITY_THEN_RETURN_
#: FRONT_FACE_RE`'s "creatures you control", a `Selector` re-evaluated every
#: sweep) or at the source itself (`_GAINS_ABILITY_RE`).
#:
#: The whole-paragraph "quoted ability ends in a full stop of its own" problem
#: `_GRANT_QUOTED_ABILITY_THEN_RETURN_FRONT_FACE_RE`'s own docstring explains
#: applies here even harder: Launch the Fleet's own granted ability text
#: carries an internal comma too ("Whenever this creature attacks, create
#: a..."), which `split_effect_clauses`'s naive top-level comma cut slices
#: mid-sentence - so this is matched whole, ahead of any clause split, the
#: same way every other quoted-whole-paragraph shape in this module is.
#:
#: The phrase capture is handed to `_targets_understood(..., count_agnostic=
#: True)` rather than re-deriving its own grammar for "any number of"/"up to
#: N"/"you control": `machines/targeting.py`'s `profile_for_text` already
#: reads every one of those shapes for the *casting* side (Launch the Fleet's
#: own strive cost already depends on it), so re-parsing the count here would
#: only be able to disagree with what casting already decided was legal.
#:
#: The grant itself is `CardState.granted_ability_texts` (CR 113.10a: "These
#: instructions become part of the ability that's added to the object"),
#: exactly the way `_parse_target_gains_ability_until_cast_from_exile_clause`
#: grants one - the *expiry* is the only thing that differs: a `DelayedTrigger`
#: watching `TriggerEvent.BEGINNING_OF_STEP`/`Step.CLEANUP` rather than a
#: named game event, because CR 514.2's own cleanup-step turn-based action is
#: where every "until end of turn" effect ends, and CR 514.3a keeps that
#: cleanup step itself open for priority ("a cleanup step in which any of
#: these things happen ... will be followed by another cleanup step") when
#: something genuinely triggers there - which this does, once, per target.
_PLURAL_TARGET_GAIN_QUOTED_ABILITY_RE = re.compile(
    r"^(?:until end of turn,\s*)?"
    r"(?P<phrase>[a-z][a-z0-9 ]*? target creatures?(?: you control)?) each gain "
    r'["“](?P<ability>.+?)["”]'
    r"(?:\s+until end of turn)?\s*\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_plural_target_gain_quoted_ability_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_PLURAL_TARGET_GAIN_QUOTED_ABILITY_RE`'s shape."""
    whole = _strip_non_effect_preamble(text).strip()
    match = _PLURAL_TARGET_GAIN_QUOTED_ABILITY_RE.fullmatch(" ".join(whole.split()))
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    if not _targets_understood(phrase, count_agnostic=True, battlefield_only=True):
        return None
    ability_text = match.group("ability").strip()
    if not ability_text:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            if ability_text not in target.granted_ability_texts:
                target.granted_ability_texts = (*target.granted_ability_texts, ability_text)
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=f'{target.name} gains "{ability_text}" until end of turn.',
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.CLEANUP,
                    controller=controller.username,
                    source_id=source_id_of(stack_object),
                    source_name=source_name,
                    remaining=1,
                    expires_end_of_turn=False,
                    effect=RevokeGrantedAbility(
                        land_id=target.id,
                        land_stamp=target.zone_change_stamp,
                        granted_text=ability_text,
                    ),
                )
            )

    return effect


def _has_period_outside_quotes(text: str) -> bool:
    """Whether `text` has a "." sitting outside of any double-quoted span.

    The same quote-depth toggle `machines/abilities._split_top_level_
    sentences` uses to split a permanent's own printed lines - needed here
    too, for the identical reason: a quoted grant (CR 113.10a) can carry a
    period of its own without that period ending the *outer* instruction
    around it.
    """
    in_quotes = False
    for char in text:
        if char == '"':
            in_quotes = not in_quotes
        elif char == "." and not in_quotes:
            return True
    return False


#: "Its controller/that player may search ..." with the subject already
#: stripped by `_ANAPHORIC_SUBJECT_RE` - the same tail `_SEARCH_AND_PUT_RE`
#: reads, but with no subject group of its own to match against (there is
#: nothing left in `rest` for one), because the "may" here is never optional
#: in the way `_build_search_clause`'s own "you may" prefix is: every card
#: this shape reaches prints it. The count slot is `_SEARCH_AND_PUT_RE`'s own
#: (see its comment) - Dire-Strain Rampage's "may search ... for up to two
#: basic land cards" is the same widening this family needed.
_REFERENT_SEARCH_RE = re.compile(
    rf"^may search (?:your|their) library for "
    rf"(?P<upto>up to )?(?:(?P<n>{COUNT})|(?P<that_many>that many)) "
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?"
    r", put (?:it|them|that card|those cards) "
    r"(?P<dest>into your hand|into your graveyard|onto the battlefield(?P<tapped> tapped)?)"
    r"(?:, then shuffle)?\.?$",
    re.IGNORECASE,
)

#: "creates a[n] [tapped] <token descriptor> token[s]" - the referent-subject
#: twin of `_TOKEN_CLAUSE_RE`, for Cityscape Leveler's "Its controller creates
#: a tapped Powerstone token." "Create"/"creates" is not optional here the way
#: `_TOKEN_CLAUSE_RE`'s own leading "(?:create )?" is, because this text is
#: always third-person ("creates"), never the imperative "create" a spell's
#: own clause prints.
_REFERENT_TOKEN_RE = re.compile(
    rf"^creates? (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "gains life equal to its power" (Solitude, Swords to Plowshares) or "gains
#: N life" (Nature's Claim, Last Breath) - the referent's controller's own
#: second sentence, either a look-back value expression or a plain printed
#: count. `its power` is the only value expression this wave reads for the
#: first shape; anything else (toughness, a modified power) is refused, which
#: is what `_read_referent_power_expression` enforces. The pinned defect this
#: wave fixes was that the second shape had no alternative here at all -
#: `_REFERENT_GAIN_LIFE_RE` matched only "equal to <expr>", so Nature's
#: Claim's whole two-clause instruction (destroy, then gain 4 life) failed
#: closed with no notice, the entire spell doing nothing (the destroy half
#: too - `_parse_referent_clause` returning `None` for the second clause
#: makes `_parse_anaphoric_clause_pair` refuse the pair as a whole, CR 608.2c
#: having no notion of running half an instruction).
_REFERENT_GAIN_LIFE_RE = re.compile(
    rf"^gains? (?:life equal to (?P<expr>.+)|(?P<n>{COUNT}) life\.?)$", re.IGNORECASE
)

#: "loses N life." - Inevitable Defeat's and Certain Death's own "Its
#: controller loses 3 life", and Punish Ignorance's after a counter (CR
#: 119.3: that player's life total "is adjusted accordingly"). The "and you gain N
#: life" half those cards print after it is its own clause by the time this
#: is read (`split_effect_clauses` cuts at ", and you"/" and you"), run by the
#: ordinary per-clause dispatch against the spell's own controller.
_REFERENT_LOSE_LIFE_RE = re.compile(rf"^loses? (?P<n>{COUNT}) life\.?$", re.IGNORECASE)

#: "draws a/N card(s)." - Introduction to Annihilation's own "Its controller
#: draws a card.", CR 121.2's ordinary draw dealt to whichever player the
#: antecedent's referent reader found.
_REFERENT_DRAW_RE = re.compile(rf"^draws? (?P<n>{COUNT}) cards?\.?$", re.IGNORECASE)


def _read_referent_power_expression(expr: str) -> bool:
    """Whether `expr` is exactly "its power" - the only value expression this
    wave reads off a referent (`its power` being the LKI snapshot
    `_parse_anaphoric_clause_pair` already took before the antecedent's verb
    moved the referent - CR 608.2i, a look-back effect uses information as it
    was, not the current game state, and CR 400.7's new object has none of
    its own left to read afterward)."""
    return expr.strip().rstrip(".").strip().lower() == "its power"


#: A second, anaphoric clause's effect, given the referent's controller and
#: LKI power (`None` if it could not be read - a `*` power CDA the layers
#: engine itself failed to resolve, not something this wave should crash or
#: silently zero on).
ReferentClause = Callable[["Game", Player, int | None, str, str | None], None]


def _referent_gain_life(
    game: "Game", player: Player, power: int | None, source: str, source_id: str | None
) -> None:
    """ "<Referent's controller> gains life equal to its power" (CR 119.3).

    CR 107.1b: "You can't ... gain negative life" - a negative last-known
    power floors at zero rather than reducing the total. A `None` power (the
    LKI snapshot could not be read) gains nothing, which is `Game.power_of`'s
    existing "the layers engine could not answer" case, not a new one
    invented here.
    """
    if power is None:
        return
    player.gain_life(max(power, 0))


#: "manifests dread" as the referent player's own verb (CR 701.62a).
_REFERENT_MANIFEST_DREAD_RE = re.compile(r"^manifests dread\.?$", re.IGNORECASE)


def _parse_referent_clause(rest: str) -> ReferentClause | None:
    """ "<rest>" is the tail of "its controller"/"that player" with the
    subject already stripped off by `_ANAPHORIC_SUBJECT_RE` - read as a life
    gain, a search, or a token creation, in that order, or `None` if this wave
    cannot read it (Craterous Stomp's "Each other creature that player
    controls becomes a Coward..." is none of the three and is left unscripted
    - see `docs/engine-coverage.md`).
    """
    rest = rest.strip()

    if match := _REFERENT_GAIN_LIFE_RE.fullmatch(rest):
        if match.group("expr") is not None:
            if not _read_referent_power_expression(match.group("expr")):
                return None
            return _referent_gain_life
        amount = parse_count(match.group("n"))
        if amount is None:
            return None

        def fixed_referent_gain_life(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            player.gain_life(amount)

        return fixed_referent_gain_life

    if match := _REFERENT_LOSE_LIFE_RE.fullmatch(rest):
        loss = parse_count(match.group("n"))
        if loss is None:
            return None

        def fixed_referent_lose_life(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            game.lose_life(player, loss)

        return fixed_referent_lose_life

    if match := _REFERENT_DRAW_RE.fullmatch(rest):
        amount = parse_count(match.group("n"))
        if amount is None:
            return None

        def draw_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            game.draw_cards(player, amount)

        return draw_effect

    if _REFERENT_MANIFEST_DREAD_RE.fullmatch(rest):
        # CR 701.62a, performed by the referent player (Fear of Impostors'
        # "Its controller manifests dread.").
        def manifest_dread_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            manifest_dread(game, player.username, source, source_id=source_id)

        return manifest_dread_effect

    if match := _REFERENT_SEARCH_RE.fullmatch(rest):
        run = _search_and_place_for(match, optional=True)
        if run is None:
            return None

        def search_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            run(game, player, source, source_id)

        return search_effect

    if match := _REFERENT_TOKEN_RE.fullmatch(rest):
        count = parse_count(match.group("n"))
        words = match.group("desc").strip().split()
        tail = match.group("tail")
        tapped = bool(words) and words[0].lower() == "tapped"
        if tapped:
            words = words[1:]
        if not words:
            return None
        predefined_name = " ".join(words)
        if tail is None and predefined_name in PREDEFINED:
            definition = PREDEFINED[predefined_name]
        else:
            definition = _parse_generic_token_descriptor(words, tail)
        if definition is None:
            return None

        def token_effect(
            game: "Game", player: Player, power: int | None, source: str, source_id: str | None
        ) -> None:
            create_tokens(game, definition, player.username, count, tapped=tapped)

        return token_effect

    # R0a-T2: Magmatic Hellkite's own "Its controller searches their
    # library for a basic land card, puts it onto the battlefield tapped
    # with a stun counter on it, then shuffles." reaches the engine only
    # through the whole-paragraph reader in `machines/map_tokens.py`
    # (`parse_destroy_then_referent_mandatory_search_tapped_clause`,
    # registered in `_parse_mixed_clauses` below) - never through this
    # function, because `rest` here is one fragment of `split_effect_
    # clauses`'s own comma-based cut, and that cut always lands inside this
    # exact tail ("... tapped[ with a stun counter on it]" / "then
    # shuffles"), so there is no whole "rest" for a same-shape reader
    # registered here to ever actually see.

    return None


#: The two plural forms Oracle text spells for a creature type: the ordinary
#: "-s" (Humans, Zombies is "-es") and the "-ves" of Wolves, Elves, Dwarves,
#: Werewolves. Anything else is left unread rather than guessed at - a type
#: this cannot singularise would silently sweep nothing, which is the same
#: silence as a card doing nothing at all.
#:
#: Named for its one caller (`_parse_transform_all_subtype_clause`, right
#: below) rather than the bare `_singular_subtype` this module already has
#: two other same-named, differently-behaved singularisers of (`count_
#: expression`'s own, and `amass`'s own `_singular_subtype_for_amass`) - three
#: functions sharing one name meant only the textually-last definition was
#: ever reachable (Python resolves a module-level name at call time, not by
#: which `def` sits nearest), silently shadowing the other two's callers onto
#: behaviour neither was written for. This wave's number sweep found it by
#: way of `count_expression("number of Elf you control")` always coming back
#: 0: the shadowing amass version neither lowercases nor checks
#: `subtype_vocabulary()`, so "Elf" never matched a board's lowercase "elf".
#: Keeps the printed capitalisation rather than lowercasing, unlike its two
#: siblings: `_TRANSFORM_ALL_SUBTYPE_RE`'s own subtype capture is
#: case-sensitive, matched straight against `Characteristics.subtypes`'s own
#: capitalised storage.
def _singular_subtype_for_transform_all(plural: str) -> str | None:
    if plural.endswith("ves"):
        return f"{plural[:-3]}f"
    if plural.endswith("ies"):
        return f"{plural[:-3]}y"
    if plural.endswith("es") and plural[-3:-2].lower() in {"s", "x", "z", "h"}:
        return plural[:-2]
    if plural.endswith("s"):
        return plural[:-1]
    return None


def _as_capitalized_sentence(text: str) -> str:
    """`text` as one capitalized sentence with a single closing period."""
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:] + "."


#: The same attached-object phrase anywhere in an antecedent clause - what
#: `_referent_reader` reads "it" as when no other referent shape applies.
_ATTACHED_SUBJECT_RE = re.compile(
    r"\b(?:enchanted|equipped) (?:creature|permanent|artifact|land)\b", re.IGNORECASE
)


def _parse_anaphoric_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "<Destroy/exile> target X. Its/that X's controller <player clause>."
    as one combined clause, or `None` if this shape does not match or its
    second sentence cannot be read.

    CR 608.2b's target-legality recheck belongs only to the *first*
    sentence's own target - the only thing this ability ever targets. The
    second sentence's "its controller"/"that player" is CR 400.7's plain
    anaphora back to whatever the first sentence found (see
    `_ANAPHORIC_SUBJECT_RE`), not a second target of its own, so it is never
    put through `Game.resolve_targets` again (that would apply CR 608.2b to
    an object CR 400.7 says is not even the same one any more, and reproduce
    Solitude's original bug of gaining no life whenever the exiled object
    itself would obviously no longer be a legal target of anything).

    This is the fix for Solitude's live defect: "exile up to one other target
    creature. That creature's controller gains life equal to its power." used
    to have no registry row and no clause parser that could read its second
    sentence, so `_parse_mixed_clauses` correctly refused the *whole* effect
    (CR 608.2c has no notion of running half an instruction) - but silently,
    with no record anywhere that anything had gone unread. `trigger_effect_for`
    now leaves an `AnaphoricClauseNotice` for exactly that failure mode.

    The referent's controller and power are read from the battlefield
    **before** the first sentence's verb runs it off the battlefield
    (CR 608.2i): reading them afterward would see `CardState.move_to`'s empty
    husk - counters cleared to `last_known_counters`, and
    `machines/layers.py` only computing continuous effects for a permanent
    still on the battlefield - so an anthemed, +1/+1-countered creature would
    silently gain its printed power back rather than its real one.
    """
    verb_match = _DESTROY_TARGET_RE.fullmatch(first) or _EXILE_TARGET_RE.fullmatch(first)
    if verb_match is None:
        return None
    is_destroy = first.strip().lower().startswith("destroy")
    if not _targets_understood(
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=is_destroy
    ):
        return None
    subject_match = _ANAPHORIC_SUBJECT_RE.fullmatch(second.strip())
    if subject_match is None:
        return None
    second_clause = _parse_referent_clause(subject_match.group("rest"))
    if second_clause is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            # CR 115.6: "up to one" chose zero, or CR 608.2b left nothing
            # legal - either way the second sentence has nothing to refer
            # back to and does not run either (CR 608.2c: one instruction,
            # not two independent ones).
            return
        target = targets[0]
        referent = game.controller_of(target)
        power = game.power_of(target)
        if is_destroy:
            game.destroy(target)
        else:
            game.exile_permanent(target)
        # A legal target the first verb failed to move - CR 702.12b's
        # indestructible refusing `destroy` - still has a controller for "its
        # controller" to name, so the second sentence runs regardless (CR
        # 608.2b: a legal target "will resolve normally"). The printed
        # rulings for this exact templating say so: Beast Within (2021-03-19)
        # "If the target is legal but not destroyed (most likely because it
        # has indestructible), its controller does create a Beast token", and
        # Assassin's Trophy (2024-02-02) the same for its search.
        second_clause(game, referent, power, source, source_id_of(stack_object))

    return effect


#: "Exile all attacking creatures target player controls." (Settle the
#: Wreckage) - a mass removal (CR 406.2 / CR 701.8a) of every permanent that
#: fits `<description>` among one target player's own, read with
#: `machines/targeting.permanent_description`, the grammar a "target" phrase
#: already uses ("attacking" is CR 508.1k's attacking creature).
_ALL_OF_TARGET_PLAYERS_RE = re.compile(
    r"^(?P<verb>destroy|exile) all (?P<description>.+?) target player controls$",
    re.IGNORECASE,
)


def _parse_all_of_target_player_then_referent_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Exile all `<description>` target player controls. That player
    `<referent clause>`." - Settle the Wreckage.

    The first sentence moves every fitting permanent the target player
    controls and records how many actually moved (CR 608.2c), which is what
    the second sentence's "that many" reads (`that_many`). "That player" is
    the target player itself (CR 400.7 anaphora back to it), read through
    `_parse_referent_clause` the same way `_parse_anaphoric_clause_pair`
    reads "its controller" after a single-target removal. A target player
    who is no longer legal (CR 608.2b) leaves both sentences undone.
    """
    match = _ALL_OF_TARGET_PLAYERS_RE.fullmatch(first.strip())
    if match is None:
        return None
    requirement = permanent_description(match.group("description"))
    if requirement is None:
        return None
    subject_match = _ANAPHORIC_SUBJECT_RE.fullmatch(second.strip())
    if subject_match is None or not second.strip().lower().startswith("that player"):
        return None
    second_clause = _parse_referent_clause(subject_match.group("rest"))
    if second_clause is None:
        return None
    is_destroy = match.group("verb").lower() == "destroy"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        players = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        ]
        if not players:
            return
        player = players[0]
        group = [
            permanent
            for permanent in game.permanents_controlled_by(player.username)
            if requirement.rejects(permanent, player.username, game) is None
        ]
        moved = 0
        for permanent in group:
            if is_destroy:
                game.destroy(permanent)
            else:
                game.exile_permanent(permanent)
            if permanent.zone is not Zone.BATTLEFIELD:
                moved += 1
        game.record_count(moved)
        second_clause(game, player, None, source, source_id_of(stack_object))

    return effect


#: "this creature", "this permanent", "this artifact" - CR 109.2's
#: self-reference, which is the resolving object's own source.
_SELF_SUBJECT_RE = re.compile(
    r"\bthis (?:creature|permanent|artifact|enchantment|land|card)\b", re.IGNORECASE
)
#: The "this `<noun>` deals" that opens a damage clause: the source of the
#: damage, not the thing it is dealt to.
_DAMAGE_SOURCE_PREFIX_RE = re.compile(
    r"^this (?:creature|permanent|artifact|enchantment|land|card) deals\b", re.IGNORECASE
)


def _referent_reader(first: str) -> ReferentReader | None:
    """How to find "it"/"they" for an antecedent clause reading `first`, or
    `None` when this wave cannot say - in which case the pair is refused and
    the card fails closed, exactly as it did before.

    Three shapes, in the order they are tested:

    - **the antecedent targets** ("Tap target creature.") - the referent is
      what CR 608.2b still leaves legal now, read through `resolve_targets`,
      which is the same list the antecedent's own parser is about to act on.
      **Not** re-resolved as a second target: CR 400.7's anaphora is not
      CR 115.1's targeting, and the rider is never a fresh instance of the
      word "target".
    - **a group** ("Destroy all creatures.") - every creature on the
      battlefield right now, snapshotted before the antecedent runs
      (CR 608.2f: the action is processed simultaneously, so the set cannot
      change under it).
    - **the source itself** ("put a +1/+1 counter on this creature.") -
      CR 109.2's self-reference.

    An antecedent that is more than one of these is refused rather than
    guessed at: "Destroy all creatures and target land" names two groups and
    "it" would be ambiguous, which is a question for whoever writes that
    card's wave, not a coin to flip here.
    """
    lowered = first.lower()
    # "this enchantment deals 15 damage to target creature ..." (Form of the
    # Dinosaur): when the clause also names a target, the self-reference is
    # only the damage's *source* (CR 120.1), not an object "it"/"that
    # creature" could mean - the target is the referent.
    self_text = (
        _DAMAGE_SOURCE_PREFIX_RE.sub("", lowered, count=1) if "target" in lowered else lowered
    )
    matches = [
        "target" in lowered,
        bool(_MASS_CREATURE_SUBJECT_RE.search(lowered)),
        bool(_SELF_SUBJECT_RE.search(self_text)),
    ]
    if sum(matches) == 0 and _ATTACHED_SUBJECT_RE.search(lowered):
        # "tap enchanted creature and remove all counters from it" - the
        # object the source is attached to (CR 303.4b), read only when no
        # other shape above applies, so no existing antecedent changes.

        def from_attached(game: "Game", stack_object: "StackObject") -> list[CardState]:
            attached = _attached_object(game, stack_object)
            return [] if attached is None else [attached]

        return from_attached
    if sum(matches) != 1:
        return None
    if matches[0]:

        def from_targets(game: "Game", stack_object: "StackObject") -> list[CardState]:
            return [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState)
            ]

        return from_targets
    if matches[1]:

        def from_all_creatures(game: "Game", stack_object: "StackObject") -> list[CardState]:
            return [
                permanent
                for permanent in list(game.battlefield)
                if game.characteristics_of(permanent).is_creature
            ]

        return from_all_creatures

    def from_source(game: "Game", stack_object: "StackObject") -> list[CardState]:
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return []
        return [source]

    return from_source


#: "Put N `<kind>` counters on it/them/that creature." - Kaito, Bane of
#: Nightmares' `-2`. The counter kind is any single word, exactly as
#: `_COUNTER_TARGET_RE` reads it, because CR 122.1 leaves the set open.
_RIDER_PUT_COUNTERS_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on {_OBJECT_ANAPHOR}$",
    re.IGNORECASE,
)

#: "Put X `<kind>` counters on it, where X is `<expr>`." - Emil, Vastlands
#: Roamer's own "Put X +1/+1 counters on it, where X is the number of
#: differently named lands you control." `_RIDER_PUT_COUNTERS_RE` above only
#: reads a fixed count (or a spell's own {X}, already substituted to a
#: literal number by `effect_for`'s `substitute_x` before this ever runs -
#: Wild Hypothesis's identical-looking "Put X +1/+1 counters on it." is that
#: case, not this one); this is the sibling for a card that spells its own X
#: out with a "where X is ..." tail instead, read through `count_expression`
#: the same way `_parse_draw_equal_to_then_lose_life_clause_pair` above
#: already reads one for a draw amount rather than a counter one.
_RIDER_PUT_VARIABLE_COUNTERS_RE = re.compile(
    rf"^put x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on {_OBJECT_ANAPHOR},\s*"
    r"where x is (?P<expr>.+?)$",
    re.IGNORECASE,
)

#: "It gains `<keyword>` until end of turn." / "It gets +N/+N until end of
#: turn." / "They gain ... " - The Wandering Emperor's `+1`.
#:
#: Read by **rewriting the subject** to "Target creature" and handing the
#: rewritten sentence to `machines/layers.parsed_layer_effects`, rather than
#: by teaching that module the pronoun. Two reasons, and the first is the
#: sharper: `_is_layer_effect_text` is an any-sentence test over the whole
#: ability, so a layer parser that recognised "It gains first strike until end
#: of turn." would swallow The Wandering Emperor's *whole* `+1` and skip the
#: counter (see this section's header). The second is that "target creature"
#: is not a claim about targeting here at all - `parsed_layer_effects` never
#: re-derives who was targeted, it only recognises which shape of sentence it
#: has, and the objects it applies to are handed in as `targets`.
_RIDER_LAYER_SUBJECT_RE = re.compile(
    rf"^(?P<pronoun>{_OBJECT_ANAPHOR})\s+(?P<predicate>(?:gain|get)s?\s+.+)$", re.IGNORECASE
)

#: "It becomes an Angel in addition to its other types and gains flying." -
#: Archangel Elspeth's -2 rider, read the same rewrite-the-subject way as
#: the "gains"/"gets" rider just above, by `machines/layers.py`'s own
#: `_BECOMES_SUBTYPE_IN_ADDITION_RE` (layer 4 plus layer 6, CR 613.1d/f).
#: Kept to the "in addition to its other types" shape: a bare "becomes a
#: <type>" replaces types instead (CR 205.1a) and is a different sentence.
_RIDER_BECOMES_IN_ADDITION_SUBJECT_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR}\s+(?P<predicate>becomes\s+.+\bin addition to its other types\b.*)$",
    re.IGNORECASE,
)

#: "It can't be blocked this turn." - Kappa Cannoneer's own rider. Granted as
#: a layer 6 ability (CR 613.1f) whose text is the self-referential sentence
#: `machines/combat._evasion_restriction_sentences` already reads off the
#: computed board ("this creature can't be blocked"), so the restriction is
#: enforced by the existing CR 509.1b machinery rather than a second copy of
#: it. "This turn" is `Duration.UNTIL_END_OF_TURN` (CR 611.2a).
_RIDER_CANT_BE_BLOCKED_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} can'?t be blocked this turn$", re.IGNORECASE
)

#: "It can't block this turn." - CR 509.1b's mirror restriction, printed as an
#: anaphoric rider after an earlier clause (SOS's Duel Tactics: "Duel Tactics
#: deals 1 damage to target creature. It can't block this turn.") rather than
#: `_TARGET_CANT_BLOCK_RE`'s own direct "target creature can't block this
#: turn" grant. Granted the identical way `_RIDER_CANT_BE_BLOCKED_RE` grants
#: its own mirror keyword: the self line "This creature can't block."
#: `machines/combat.py`'s blocker restriction already reads, for the rest of
#: the turn (CR 611.2a).
#: "This combat" (Forgestoker Dragon's "That creature can't block this
#: combat.") is the same restriction for the rest of the combat phase only
#: (`Duration.UNTIL_END_OF_COMBAT`, CR 500.5a/511.2).
_RIDER_CANT_BLOCK_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} can'?t block (?P<span>this turn|this combat)$", re.IGNORECASE
)


#: "Put twice X `<kind>` counters on it." - SOS's Procrastinate: "Tap target
#: creature. Put twice X stun counters on it." CR 107.3a's announced X,
#: doubled (CR 107.3b's own "twice X" reading a plain arithmetic multiplier,
#: not CR 701.10e's "double the number of counters *already there*" - there
#: are none yet on a freshly-tapped creature). `_RIDER_PUT_COUNTERS_RE`'s own
#: literal-count sibling, for the one shape a fixed `COUNT` cannot spell.
_RIDER_PUT_TWICE_X_COUNTERS_RE = re.compile(
    rf"^put twice x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on {_OBJECT_ANAPHOR}$", re.IGNORECASE
)

#: "Goad it." / "Goad them." / "Goad that creature." - Oceanus Dragon's own
#: rider after its tap (CR 701.15a): the goader is the resolving object's
#: controller, the objects are whatever the antecedent sentence acted on.
_RIDER_GOAD_RE = re.compile(rf"^goad {_OBJECT_ANAPHOR}$", re.IGNORECASE)

#: "Untap it." - Tethermage's Advantage's own rider, after its pump. CR
#: 701.18a: "To untap a permanent means to remove the tapped status from it."
_RIDER_UNTAP_RE = re.compile(rf"^untap {_OBJECT_ANAPHOR}$", re.IGNORECASE)

#: "Tap it." - Tyvar, the Pummeler's and Vanguard of the Rose's own rider,
#: after the source grants itself indestructible. CR 701.26a: "To tap a
#: permanent, turn it sideways from an upright position. Only untapped
#: permanents can be tapped."
_RIDER_TAP_RE = re.compile(rf"^tap {_OBJECT_ANAPHOR}$", re.IGNORECASE)

#: "Remove all counters from it." / "... from that creature." - Enchanted
#: River's Grasp's and Honest Work's second half, Blitz Leech's own second
#: sentence. Every kind at once (CR 122.1: counters of every name are
#: markers on the object), or one named kind ("remove all +1/+1 counters
#: from it") - the same kind grammar `_REMOVE_ALL_COUNTERS_FROM_TARGET_RE`
#: reads for its targeted twin.
_RIDER_REMOVE_ALL_COUNTERS_RE = re.compile(
    rf"^remove all (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters from {_OBJECT_ANAPHOR}$",
    re.IGNORECASE,
)


#: "If it would die this turn, exile it instead." - Essence Burn's own
#: rider (CR 614.1a); Combustion Technique's identical wording is the real,
#: off-set printing of the same shape. `Game.die_to_exile_this_turn` is the
#: marker `machines/replacement.py`'s own `_die_to_exile_this_turn_effects`
#: reads for the rest of the current turn (CR 514.2 clears it at cleanup).
_RIDER_DIE_TO_EXILE_THIS_TURN_RE = re.compile(
    rf"^if {_OBJECT_ANAPHOR} would die this turn, exile it instead$", re.IGNORECASE
)

#: "gains your choice of `<keyword>`[, `<keyword>`, ...] until end of turn."
#: - Hungering Puppetbeast's own rider (CR 608.2d: the choice is the
#: resolving object's controller's, asked once - the same shape
#: `_choose_mana_color` already asks for a mana ability's own colour).
_RIDER_KEYWORD_CHOICE_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} gains? your choice of "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:,\s*[a-z]+(?: [a-z]+)?)*(?:,?\s+or\s+[a-z]+(?: [a-z]+)?)?) "
    r"until end of turn$",
    re.IGNORECASE,
)


def _split_choice_keywords(raw: str) -> list[str] | None:
    """ "trample, hexproof, or haste" -> each keyword, capitalised - or
    `None` if any of them is not on `KNOWN_KEYWORDS`'s whitelist, the exact
    same fail-closed rule `machines.layers._split_and_validate_keywords`
    already enforces for a plain (non-choice) keyword list - kept as its
    own small copy here rather than shared, since a *choice* needs each
    option offered on its own, one per string, not folded into one combined
    grant the way an "and"-joined list is.
    """
    parts = [part.strip() for part in re.split(r",\s*(?:or\s+)?|\s+or\s+", raw) if part.strip()]
    if not parts or any(part.lower() not in KNOWN_KEYWORDS for part in parts):
        return None
    return [part.capitalize() for part in parts]


#: "Put a `<kind>` counter on it if it's a `<type>`." - Teyo, Lightshield
#: Expert's and Teyo, Diamondblade Mage's own "Put a +1/+1 counter on it if
#: it's a creature. Put a loyalty counter on it if it's a planeswalker.",
#: each a separate rider sentence rather than one compound clause. CR 608.2h:
#: "the effect uses the current information of that object" is what backs
#: checking the referent's type *now*, when this rider runs, rather than at
#: whatever type it had when targeted. `<type>` is any of CR 300.1's card
#: types, not the two Teyo happens to print - a future "... if it's an
#: artifact." reads the identical way with no new vocabulary.
_RIDER_COUNTER_IF_TYPE_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on {_OBJECT_ANAPHOR} "
    r"if (?:it'?s|they'?re) an? (?P<type>[a-z]+)$",
    re.IGNORECASE,
)

#: "That creature is a `<creature type>` in addition to its other types." -
#: Sorin, Vengeful Bloodlord's own `-X` rider, after returning a creature
#: card from a graveyard to the battlefield. CR 205.1b: "in addition to its
#: other types" is the phrase that keeps every type the object already has
#: rather than replacing them (unlike a bare "becomes a `<type>`"), and
#: CR 205.3m lists creature types as CR 205's own subtype vocabulary, so
#: `<type>` is read as a subtype, not a card type - `add_subtype`, not
#: `add_type`. No stated duration, so this is CR 611.3b's ordinary lasting
#: grant (`Duration.INDEFINITE`), the same choice `_amass` already makes for
#: an Army token's own name-becomes-subtype line.
_RIDER_BECOMES_TYPE_IN_ADDITION_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} is an? (?P<type>[A-Za-z][a-z]*) in addition to its other types$",
    re.IGNORECASE,
)


#: "... to its controller" / "... to its owner" - the damage goes to the player
#: who controls (CR 108.4's controller, CR 108.3's owner) the very object that
#: deals it: Traitor's Roar and Ana Battlemage's "Tap target untapped
#: creature. It deals damage equal to its power to its controller." The
#: holder is read off the dealer as the rider runs, never targeted.
_RIDER_DAMAGE_HOLDER_PHRASE = (
    r"(?:its|that (?:creature|permanent)'s|their) (?P<holder>controller|owner)"
)


#: "It deals damage equal to its power to target creature." - Crush
#: Underfoot's rider, after "Choose a Giant creature you control." The
#: referent is the source of the damage (CR 120.1: "An object that deals damage is the
#: source of that damage"), one-sided - not a fight (CR 701.14a) - and the amount is its
#: power as the rider runs (CR 608.2h). The target phrase is the resolving
#: object's own target, rechecked on resolution (CR 608.2b).
#: "That creature deals damage equal to its power to you." - Form of the
#: Dinosaur's rider after its 15 damage: the same one-sided damage (CR 120.1)
#: with the resolving ability's controller as the recipient (CR 119.2).
#: "That creature deals damage equal to its power to this creature." -
#: Karplusan Yeti / Vein Drinker, after "This creature deals damage equal to
#: its power to target creature.": the same one-sided damage back to the
#: ability's source. Not fight (CR 701.14b): the antecedent's damage still
#: happens off the source's last known power (CR 608.2h) if it has left, and
#: then "this creature" names nothing to damage (CR 400.7).
_RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_POWER_TO_YOU_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} deals damage equal to its power to you$", re.IGNORECASE
)
_RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_POWER_RE = re.compile(
    rf"^{_OBJECT_ANAPHOR} deals damage equal to its power to "
    rf"(?:(?P<phrase>.*\btarget\b.+)|{_RIDER_DAMAGE_HOLDER_PHRASE}|(?P<self>this creature))$",
    re.IGNORECASE,
)


#: "If `<condition>`, `<anaphor>` [also] `<rider>`" / "`<anaphor>` [also]
#: `<rider>` if `<condition>`" - Violent Urge's Delirium sentence ("If there
#: are four or more card types among cards in your graveyard, that creature
#: gains double strike until end of turn."), Temur Battle Rage's Ferocious
#: one ("That creature also gains trample until end of turn if you control a
#: creature with power 4 or greater.") and Crumb and Get It's gift one ("If
#: the gift was promised, that creature also gains indestructible until end
#: of turn."). The ability word in front (CR 207.2c) is already gone by the
#: time a clause reaches here. "also" only says the rider adds to what the
#: antecedent did; it changes nothing, so it is dropped before the rider
#: itself is read.
#: The rider half is not required to *start* with the anaphor - SOS's Rapier
#: Wit: "Tap target creature. If it's your turn, put a stun counter on it."
#: puts "it" at the end, as the counter clause's own object, not as the
#: rider's subject. `_parse_conditional_referent_clause` below still checks
#: the body through `_parse_referent_object_clause`, the same reader every
#: unconditional rider goes through, so nothing here is read more loosely
#: than an unconditional rider already is - and the caller
#: (`_parse_object_anaphor_clause_pair`) has already confirmed the *whole*
#: second sentence contains the anaphor somewhere before this is even tried.
_CONDITIONAL_REFERENT_LEADING_RE = re.compile(
    r"^if (?P<condition>[^,]+), (?P<rider>.+)$", re.IGNORECASE
)
_CONDITIONAL_REFERENT_TRAILING_RE = re.compile(
    rf"^(?P<rider>{_OBJECT_ANAPHOR}\b.+?) if (?P<condition>.+)$", re.IGNORECASE
)
_RIDER_ALSO_RE = re.compile(rf"^(?P<anaphor>{_OBJECT_ANAPHOR}) also\b", re.IGNORECASE)


def _parse_conditional_referent_clause(rider: str) -> ReferentObjectClause | None:
    """`_CONDITIONAL_REFERENT_*_RE`'s shape: a referent rider that runs only if
    its condition holds, checked once, on resolution (CR 608.2h), through
    `Game.condition_holds` - the same reader every other printed condition
    goes through. A condition this engine does not read refuses the whole
    rider at parse time (`condition_is_readable`), so the pair fails closed
    rather than running the rider as though the condition were false; the
    rare `None` answer at resolution is recorded as a
    `ConditionalClauseNotice`, the same channel `_parse_condition_clause`
    uses.
    """

    match = _CONDITIONAL_REFERENT_LEADING_RE.fullmatch(rider)
    if match is None:
        match = _CONDITIONAL_REFERENT_TRAILING_RE.fullmatch(rider)
    if match is None:
        return None
    condition_text = match.group("condition").strip()
    body = _RIDER_ALSO_RE.sub(lambda found: found.group("anaphor"), match.group("rider").strip())
    inner = _parse_referent_object_clause(body)
    if inner is None:
        return None

    if not _effect_condition_is_readable(condition_text):
        return None

    def conditional_rider(
        game: "Game", referents: list[CardState], stack_object: "StackObject"
    ) -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.source(game) if is_ability(stack_object) else stack_object  # type: ignore[union-attr]
        held = game.condition_holds(controller.username, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=(
                    stack_object.name
                    if isinstance(stack_object, CardState)
                    else stack_object.source_name  # type: ignore[union-attr]
                ),
                text=rider,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            inner(game, referents, stack_object)

    return conditional_rider


def _parse_referent_object_clause(rider: str) -> ReferentObjectClause | None:
    """A rider sentence read as something to do to the objects its antecedent
    found, or `None` when this wave cannot read it - in which case the pair is
    refused and the whole effect fails closed (CR 608.2c), which is what
    `_unreadable_anaphoric_clause` then records a notice for.
    """
    # CR 207.2c: a leading ability word ("Delirium — ") carries no rules
    # meaning; the rider is the sentence after it.
    rider = _strip_ability_word_labels(rider.strip()).strip().rstrip(".").strip()

    may_attach_if_type = _parse_if_type_may_attach_equipment_referent_clause(rider)
    if may_attach_if_type is not None:
        return may_attach_if_type

    attach_to_chosen = _parse_attach_referent_to_chosen_clause(rider)
    if attach_to_chosen is not None:
        return attach_to_chosen

    conditional = _parse_conditional_referent_clause(rider)
    if conditional is not None:
        return conditional

    if match := _RIDER_PUT_COUNTERS_RE.fullmatch(rider):
        amount = parse_count(match.group("n"))
        kind = _counter_kind(match.group("kind"))
        if amount is None:
            return None

        def put_counters(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            for referent in referents:
                if referent.zone is Zone.BATTLEFIELD:
                    game.add_counters(referent, kind, amount)

        return put_counters

    if match := _RIDER_PUT_VARIABLE_COUNTERS_RE.fullmatch(rider):
        kind = _counter_kind(match.group("kind"))
        counted = count_expression(match.group("expr"))
        if counted is None:
            return None

        def put_variable_counters(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            controller = game.controller_of(stack_object).username
            amount = counted(game, controller)
            if amount <= 0:
                return
            for referent in referents:
                if referent.zone is Zone.BATTLEFIELD:
                    game.add_counters(referent, kind, amount)

        return put_variable_counters

    if _RIDER_CANT_BE_BLOCKED_RE.fullmatch(rider):

        def cant_be_blocked(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            effects = game.continuous_effects
            for referent in referents:
                if referent.zone is not Zone.BATTLEFIELD:
                    continue
                effects.add(
                    ContinuousEffect(
                        description=f"{referent.name} can't be blocked this turn",
                        layer=Layer.ABILITY,
                        timestamp=effects.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(referent, referent.zone_change_stamp),
                        modification=grant_ability("This creature can't be blocked."),
                    )
                )

        return cant_be_blocked

    # "That permanent loses indestructible until end of turn." (Rebel Salvo,
    # Soul Sear): CR 613.1f's removal, read by its family module.
    loses_keyword = _parse_loses_keyword_referent_rider(rider)
    if loses_keyword is not None:
        return loses_keyword

    if cant_block_match := _RIDER_CANT_BLOCK_RE.fullmatch(rider):
        span = cant_block_match.group("span").lower()
        block_duration = _block_restriction_duration(span)

        def cant_block(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            effects = game.continuous_effects
            for referent in referents:
                if referent.zone is not Zone.BATTLEFIELD:
                    continue
                effects.add(
                    ContinuousEffect(
                        description=f"{referent.name} can't block {span}",
                        layer=Layer.ABILITY,
                        timestamp=effects.tick(),
                        duration=block_duration,
                        selector=only_this_incarnation(referent, referent.zone_change_stamp),
                        modification=grant_ability("This creature can't block."),
                    )
                )

        return cant_block

    if match := _RIDER_PUT_TWICE_X_COUNTERS_RE.fullmatch(rider):
        kind = _counter_kind(match.group("kind"))

        def put_twice_x_counters(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            # CR 107.3a's announced X: a spell's own cast record, an
            # ability's own `x_value` (the same two-shape read `counter_
            # effects._announced_x` already gives this identical question).
            x_value = (
                game.cast_record(stack_object).x_value
                if isinstance(stack_object, CardState)
                else getattr(stack_object, "x_value", None) or 0
            )
            amount = 2 * x_value
            if amount <= 0:
                return
            for referent in referents:
                if referent.zone is Zone.BATTLEFIELD:
                    game.add_counters(referent, kind, amount)

        return put_twice_x_counters

    if _RIDER_GOAD_RE.fullmatch(rider):

        def goad_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            goader = game.controller_of(stack_object).username
            for referent in referents:
                if referent.zone is Zone.BATTLEFIELD:
                    game.goad(referent, goader)

        return goad_rider

    if _RIDER_UNTAP_RE.fullmatch(rider):

        def untap_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            for referent in referents:
                if referent.zone is Zone.BATTLEFIELD:
                    referent.untap()

        return untap_rider

    if _RIDER_TAP_RE.fullmatch(rider):

        def tap_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            for referent in referents:
                if referent.zone is Zone.BATTLEFIELD and referent.untapped:
                    game.tap_permanent(referent)

        return tap_rider

    if match := _RIDER_REMOVE_ALL_COUNTERS_RE.fullmatch(rider):
        only_kind = _counter_kind(match.group("kind")) if match.group("kind") else None

        def remove_all_counters_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            for referent in referents:
                if referent.zone is not Zone.BATTLEFIELD:
                    continue
                for each in [only_kind] if only_kind is not None else list(referent.counters):
                    present = referent.counter_count(each)
                    if present:
                        referent.remove_counters(each, present)

        return remove_all_counters_rider

    if _RIDER_DIE_TO_EXILE_THIS_TURN_RE.fullmatch(rider):

        def die_to_exile_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            for referent in referents:
                if referent.id not in game.die_to_exile_this_turn:
                    game.die_to_exile_this_turn.append(referent.id)

        return die_to_exile_rider

    if match := _RIDER_KEYWORD_CHOICE_RE.fullmatch(rider):
        keywords = _split_choice_keywords(match.group("keywords"))
        if keywords is None:
            return None

        def keyword_choice_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            standing = [referent for referent in referents if referent.zone is Zone.BATTLEFIELD]
            if not standing:
                return
            source_name = (
                stack_object.name
                if isinstance(stack_object, CardState)
                else stack_object.source_name  # type: ignore[union-attr]
            )
            controller = game.controller_of(stack_object).username
            chosen = keywords[0]
            if len(keywords) > 1:
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=controller,
                        prompt="choose a keyword",
                        source=source_name,
                        options=tuple(keywords),
                        source_id=source_id_of(stack_object),
                    )
                )
                assert isinstance(answer, str)
                chosen = answer
            effects = game.continuous_effects
            for referent in standing:
                effects.add(
                    ContinuousEffect(
                        description=f"{source_name}: {referent.name} gains {chosen}",
                        layer=Layer.ABILITY,
                        timestamp=effects.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(referent, referent.zone_change_stamp),
                        modification=grant_ability(chosen),
                    )
                )

        return keyword_choice_rider

    if match := _RIDER_LAYER_SUBJECT_RE.fullmatch(
        rider
    ) or _RIDER_BECOMES_IN_ADDITION_SUBJECT_RE.fullmatch(rider):
        rewritten = f"Target creature {match.group('predicate').strip()}."
        builder = parsed_layer_effects(rewritten)
        if builder is None:
            return None

        def layer_rider(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            standing = [referent for referent in referents if referent.zone is Zone.BATTLEFIELD]
            if not standing:
                return
            source = (
                stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
            )
            if source is None:
                return
            effects = game.continuous_effects
            for effect in builder(
                source,
                effects.tick(),
                standing,
                layer_context_for(game, game.controller_of(stack_object)),
            ):
                effects.add(effect, game)

        return layer_rider

    if match := _RIDER_COUNTER_IF_TYPE_RE.fullmatch(rider):
        amount = parse_count(match.group("n"))
        kind = _counter_kind(match.group("kind"))
        if amount is None:
            return None
        try:
            required_type = Type(match.group("type").strip().lower())
        except ValueError:
            return None

        def put_counters_if_type(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            for referent in referents:
                if referent.zone is not Zone.BATTLEFIELD:
                    continue
                if required_type in game.characteristics_of(referent).types:
                    game.add_counters(referent, kind, amount)

        return put_counters_if_type

    if match := _RIDER_BECOMES_TYPE_IN_ADDITION_RE.fullmatch(rider):
        subtype = match.group("type").strip().capitalize()

        def becomes_type_in_addition(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            effects = game.continuous_effects
            for referent in referents:
                if referent.zone is not Zone.BATTLEFIELD:
                    continue
                if any(
                    existing.lower() == subtype.lower()
                    for existing in game.characteristics_of(referent).subtypes
                ):
                    continue
                effects.add(
                    ContinuousEffect(
                        description=(
                            f"{referent.name} is a {subtype} in addition to its other types"
                        ),
                        layer=Layer.TYPE,
                        timestamp=effects.tick(),
                        duration=Duration.INDEFINITE,
                        selector=only_this_incarnation(referent, referent.zone_change_stamp),
                        modification=add_subtype(subtype),
                    )
                )

        return becomes_type_in_addition

    if _RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_POWER_TO_YOU_RE.fullmatch(rider):

        def deals_damage_equal_to_its_power_to_you(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            dealers = [referent for referent in referents if referent.zone is Zone.BATTLEFIELD]
            if not dealers:
                return
            amount = game.power_of(dealers[0]) or 0
            if amount > 0:
                game.deal_damage(game.controller_of(stack_object), amount, source=dealers[0])

        return deals_damage_equal_to_its_power_to_you

    if match := _RIDER_DEALS_DAMAGE_EQUAL_TO_ITS_POWER_RE.fullmatch(rider):
        if match.group("self") is not None:

            def deals_damage_to_this_creature(
                game: "Game", referents: list[CardState], stack_object: "StackObject"
            ) -> None:
                if not isinstance(stack_object, AbilityOnStack):
                    return  # a spell is not "this creature" on the battlefield
                this_creature = stack_object.source(game)
                stamp = stack_object.source_stamp
                if (
                    this_creature is None
                    or this_creature.zone is not Zone.BATTLEFIELD
                    or (stamp is not None and this_creature.zone_change_stamp != stamp)
                ):
                    return  # CR 400.7: the source left; nothing to damage
                dealers = [r for r in referents if r.zone is Zone.BATTLEFIELD]
                if not dealers:
                    return
                amount = game.power_of(dealers[0]) or 0
                if amount > 0:
                    game.deal_damage(this_creature, amount, source=dealers[0])

            return deals_damage_to_this_creature
        holder = match.group("holder")
        if holder is not None:

            def deals_damage_to_its_holder(
                game: "Game", referents: list[CardState], stack_object: "StackObject"
            ) -> None:
                dealers = [r for r in referents if r.zone is Zone.BATTLEFIELD]
                if not dealers:
                    return
                dealer = dealers[0]
                amount = game.power_of(dealer) or 0
                if amount <= 0:
                    return
                username = (
                    game.controller_of(dealer).username
                    if holder.lower() == "controller"
                    else dealer.owner
                )
                game.deal_damage(game.player(username), amount, source=dealer)

            return deals_damage_to_its_holder
        phrase = match.group("phrase").strip()
        if not _targets_understood(phrase, count_agnostic=True, allow_player_targets=True):
            return None

        def deals_damage_equal_to_its_power(
            game: "Game", referents: list[CardState], stack_object: "StackObject"
        ) -> None:
            dealers = [referent for referent in referents if referent.zone is Zone.BATTLEFIELD]
            if not dealers:
                return
            dealer = dealers[0]
            amount = game.power_of(dealer) or 0
            if amount <= 0:
                return
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState) and target.zone is not Zone.BATTLEFIELD:
                    continue
                game.deal_damage(target, amount, source=dealer)

        return deals_damage_equal_to_its_power

    return None


def _parse_object_anaphor_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "`<antecedent>`. `<rider naming what the antecedent acted on>`." as one
    CR 608.2c instruction, or `None` if either half cannot be read.

    The antecedent is run by whatever parser already reads it
    (`_parse_mixed_clause`), so nothing existing has to change to gain a
    rider; this only adds the two things that were missing - *which* objects
    "it" means (`_referent_reader`) and what the rider does to them
    (`_parse_referent_object_clause`).

    **The referent is read before the antecedent runs, and re-checked
    after.** Before, because that is the only moment the antecedent's own
    subject still describes them - CR 608.2h's "the effect uses the current
    information of that object if it's in the public zone it was expected to
    be in". After, because CR 400.7 says an object that changed zones in
    between "becomes a new object with no memory of, or relation to, its
    previous existence", and acting on a stale one is the wrong-but-plausible
    board this whole wave exists to avoid. Every rider here therefore checks
    `zone is Zone.BATTLEFIELD` for itself.

    CR 400.7j is the exception this wave does not need - "If an effect causes
    an object to move to a public zone, other parts of that effect can find
    that object" - because no rider read here acts on a moved object. A rider
    that did (returning something the antecedent exiled) belongs to
    `_parse_exile_then_return_clause_pair`, which already carries the referent
    across the move itself.
    """
    if not _OBJECT_ANAPHOR_RE.search(second):
        return None
    referent_of = _referent_reader(first)
    if referent_of is None:
        return None
    antecedent = _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        antecedent = _layer_antecedent_clause(first, referent_of)
    if antecedent is None:
        return None
    rider = _parse_referent_object_clause(second)
    if rider is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = referent_of(game, stack_object)
        antecedent(game, stack_object)
        if not referents:
            # CR 115.6's "up to one" choosing none, or CR 608.2b leaving
            # nothing legal: the rider has nothing to refer back to and does
            # not run either (CR 608.2c - one instruction, not two
            # independent ones). Never a fallback to the resolving object's
            # own source, which is the bug Karn, the Great Creator's +1 had.
            return
        rider(game, referents, stack_object)

    return effect


def _parse_object_anaphor_clause_series(
    first: str, riders: Sequence[str], *, for_spell: bool, layer_antecedent_first: bool = False
) -> TargetedClause | None:
    """`_parse_object_anaphor_clause_pair`'s own shape, widened to **two or
    more** trailing rider sentences that all refer back to the same
    antecedent - Teyo, Lightshield Expert's "target permanent you control
    gains hexproof until end of turn. Put a +1/+1 counter on it if it's a
    creature. Put a loyalty counter on it if it's a planeswalker." is one
    antecedent with two independent riders, not a rider with a rider of its
    own: CR 608.2c runs every one of a resolving ability's instructions in
    printed order against the same referent, and nothing says there can only
    ever be one instruction after the first.

    `riders` must have at least one entry and every one of them must parse
    (`_parse_referent_object_clause`) - a card whose second rider this wave
    cannot read is refused whole, the same fail-closed-per-instruction rule
    `_parse_object_anaphor_clause_pair` already follows for its own single
    rider.
    """
    if not riders:
        return None
    if not all(_OBJECT_ANAPHOR_RE.search(rider) for rider in riders):
        return None
    referent_of = _referent_reader(first)
    if referent_of is None:
        return None
    # `layer_antecedent_first`: one *mode* of a modal spell (CR 700.2a), where
    # `_parse_mixed_clause` reads a pump as the bare `create_continuous_
    # effect` sentinel - which builds off the whole card's bulleted text and
    # so applies nothing for the chosen mode. The scoped layer antecedent
    # comes first there.
    antecedent = (
        _layer_antecedent_clause(first, referent_of) if layer_antecedent_first else None
    ) or _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        antecedent = _layer_antecedent_clause(first, referent_of)
    if antecedent is None:
        return None
    built_riders = [_parse_referent_object_clause(rider) for rider in riders]
    if any(built is None for built in built_riders):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = referent_of(game, stack_object)
        antecedent(game, stack_object)
        if not referents:
            # CR 115.6's "up to one" choosing none, or CR 608.2b leaving
            # nothing legal: none of the riders have anything to refer back
            # to and none of them run either (CR 608.2c - one instruction,
            # not several independent ones).
            return
        for built in built_riders:
            assert built is not None
            built(game, referents, stack_object)

    return effect


def _parse_controller_split_target_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Two independently targeted clauses, told apart by controller - Awaken
    the Inferno's own "deals 6 damage to target creature or planeswalker an
    opponent controls. Put a +1/+1 counter on up to one target creature you
    control."

    `_parse_mixed_clauses`' own per-clause fallback parses each sentence on
    its own and hands every one of them the *whole* `stack_object.targets`
    list (`Game.resolve_targets` has no notion of "this clause's own
    target") - so the damage clause landed on both of CR 601.2c's targets
    instead of only the one named by its own restriction, and the counter
    clause raced it for the same list. `_parse_pump_then_fight_clause_pair`'s
    own docstring already rules out reading the two apart positionally: CR
    608.2b can remove either target before resolution, so `targets[0]`/
    `targets[1]` is not a stable way to tell them apart even when the
    ordering was right to begin with.

    Read the same way that fight pair is: each clause's own restriction -
    "an opponent controls"/"you don't control" vs "you control" - already
    told the two targets apart at announcement (`machines/targeting.py`'s
    `ControllerRestriction`), so resolution reads it off the same way, by
    asking who controls each *resolved* target right now (CR 608.2b's own
    recheck) rather than by where in the list it happens to sit. `OPPONENT`
    and `NOT_YOU` both read into the same "theirs" bucket below - "not
    mine", which is exactly the check either restriction already enforced at
    announcement - so Closing Statement's "you don't control" reads
    identically to Awaken the Inferno's own "an opponent controls". Only
    matches when each clause names exactly one target requirement and the
    two requirements' controllers are `YOU` paired with one of those two -
    anything else (both `YOU`, an `ANY` restriction on either side, more
    than one requirement in a clause) is left for the ordinary per-clause
    fallback exactly as before.
    """
    first_effect = _parse_mixed_clause(first, for_spell=for_spell)
    if first_effect is None:
        return None
    second_effect = _parse_mixed_clause(second, for_spell=for_spell)
    if second_effect is None:
        return None
    profile_reader = spell_profile_for_text if for_spell else profile_for_text
    first_requirements = profile_reader(first).requirements
    second_requirements = profile_reader(second).requirements
    if len(first_requirements) != 1 or len(second_requirements) != 1:
        return None
    first_controller = first_requirements[0].controller
    second_controller = second_requirements[0].controller
    theirs_restrictions = {ControllerRestriction.OPPONENT, ControllerRestriction.NOT_YOU}
    controllers = {first_controller, second_controller}
    wants_you = ControllerRestriction.YOU in controllers
    wants_theirs = bool(controllers & theirs_restrictions)
    if not (wants_you and wants_theirs and len(controllers) == 2):
        return None
    first_wants_mine = first_controller is ControllerRestriction.YOU

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        mine: list[TargetRef] = []
        theirs: list[TargetRef] = []
        for ref in stack_object.targets:
            resolved = game.legal_target(stack_object, ref)
            if not isinstance(resolved, CardState) or resolved.zone is not Zone.BATTLEFIELD:
                continue
            bucket = (
                mine if game.controller_of(resolved).username == controller.username else theirs
            )
            bucket.append(ref)
        first_bucket = mine if first_wants_mine else theirs
        second_bucket = theirs if first_wants_mine else mine
        first_effect(game, stack_object.model_copy(update={"targets": first_bucket}))
        second_effect(game, stack_object.model_copy(update={"targets": second_bucket}))

    return effect


def _article(phrase: str) -> str:
    """ "a" or "an", by the sound the phrase starts with.

    Cosmetic, and only ever used for a prompt a human reads - but "exile a
    artifact card" is the same class of defect as the scrambled word order
    `_hand_exile_description` documents, and the regex accepts both articles
    ("a|an") without capturing which one the card printed.
    """
    return "an" if phrase[:1].lower() in "aeiou" else "a"


def _bare_subtype_word(description: str) -> str | None:
    """ "Islands" -> "island", "Foods" -> "food": a description that is one
    printed subtype (CR 205.3) in the plural or singular, lowercased, or None.

    Read here rather than through `permanent_description`, whose target
    grammar takes a lone plural noun it does not know as a creature type and
    would demand the Island be a creature. A card type ("creatures") is left
    to that grammar - rejected here before the shared singulariser even
    runs, since this caller's own vocabulary lookup would otherwise still
    fire on a multi-word phrase or a card type word the way `count_
    expression`'s own subtype branch never has to guard against (its match
    groups are already a lone word by construction).
    """
    word = description.strip()
    if " " in word or _singular_card_type(word) is not None:
        return None
    return _singular_subtype_for_count_expression(word)


def _is_referent_power_expression(expr: str) -> bool:
    """Whether `expr` - the tail of a "where X is `<expr>`" clause - is
    exactly a sacrificed permanent's power, read the same two ways CR 400.7's
    anaphora prints it: "its power" and "that `<type>`'s power" (Disciple of
    Freyalise's own wording). The only value expression this wave reads off a
    sacrificed permanent, the same narrow scope `_read_referent_power_
    expression` already draws for a destroyed or exiled one.
    """
    lowered = expr.strip().rstrip(".").strip().lower()
    return lowered == "its power" or bool(re.fullmatch(r"that [a-z]+'s power", lowered))


#: "the number of colors that `<anaphor>` was" - Bound's own X definition
#: (Bound // Determined). CR 400.7's anaphora over CR 105.2's colour count,
#: printed the same two ways `_is_referent_power_expression` above reads for
#: a power: a bare "it" and "that `<type>`" - here followed by "was" rather
#: than possessive "'s", since the sentence reads "colors that `<X>` was",
#: not "`<X>`'s colors". Verified this session: no other card, legal or not,
#: prints this exact past-tense anaphora over a colour count (`mise exec --
#: uv run python scripts/add_card.py` plus a live Scryfall
#: `o:/number of colors.{0,40}was/` search turned up only Bound and Jared
#: Carthalion, and the latter is legal in none of Standard, Pioneer, or
#: Modern) - see `docs/engine-coverage.md`'s row for the documented proof
#: exemption this earns, the same kind D2/T12 already carries for Veil of
#: Summer's player hexproof-from.
_REFERENT_COLOR_COUNT_EXPRESSION_RE = re.compile(
    r"^the number of colou?rs (?:that [a-z]+|it) was$", re.IGNORECASE
)


def _is_referent_color_count_expression(expr: str) -> bool:
    """Whether `expr` - the tail of a "where X is `<expr>`" clause - is
    exactly a departed object's colour count, `_REFERENT_COLOR_COUNT_
    EXPRESSION_RE`'s shape."""
    lowered = " ".join(expr.strip().rstrip(".").strip().split()).lower()
    return bool(_REFERENT_COLOR_COUNT_EXPRESSION_RE.fullmatch(lowered))


def _referent_color_count(referent: CardState) -> int:
    """CR 105.2/202.2's colour count, fixed at CR 608.2h's moment: a
    departed object's colours are read off `CardState.last_known_colors`
    when a continuous effect made them differ from the printing while it was
    still a permanent, or off `CardState.colors` (its printed/current
    colours) when none ever did - `remember_last_known_power_toughness`'s
    own `None`-when-unchanged convention, the identical fallback
    `Game._quality_characteristics_of` already reads for CR 702.11d's
    hexproof-from qualities off a departed source.
    """
    colors = (
        referent.last_known_colors if referent.last_known_colors is not None else referent.colors
    )
    return len(colors)


def _referent_of_it(game: "Game", ability: AbilityOnStack) -> CardState | None:
    """The object a consequence's "it" names: the trigger event's own subject
    (CR 603.2 - "Whenever this creature attacks" names the attacker, "When
    this creature dies" the creature that died), or the ability's source when
    the event names no object. Only a permanent still on the battlefield can
    get or gain anything (CR 400.7: one that left is a new object)."""
    subject_id = ability.event.subject_id if ability.event is not None else None
    referent = game.find_by_id(subject_id) if subject_id is not None else ability.source(game)
    if referent is None or referent.zone is not Zone.BATTLEFIELD:
        return None
    return referent


#: A created trigger whose condition names "that creature" (an object an
#: earlier instruction chose) or a target: the generic created trigger has no
#: object to bind it to and would watch every creature, so it is refused here
#: and read by `_parse_that_object_turn_trigger_*` (CR 603.7c) instead.
_CREATED_TRIGGER_ANAPHORIC_CONDITION_RE = re.compile(
    r"^whenever (?:that|those|target)\b[^,]*,", re.IGNORECASE
)


def _split_created_trigger_paragraph(text: str) -> tuple[str, TriggeredAbility, str] | None:
    """(printed line, its parse, the rest of the text) when `text` opens with
    a readable created "this turn" trigger. CR 603.1: the whole paragraph is
    the trigger - its trailing sentences are its own instructions - so only
    the following *paragraphs* are the spell's or ability's further
    instructions (First Day of Class's "Learn.")."""
    paragraphs = [part for part in text.strip().split("\n") if part.strip()]
    if not paragraphs:
        return None
    line = created_trigger_line(paragraphs[0])
    if line is None or _CREATED_TRIGGER_ANAPHORIC_CONDITION_RE.match(line):
        return None
    ability = _readable_created_trigger(line)
    if ability is None:
        return None
    return line, ability, "\n".join(paragraphs[1:]).strip()


def _singular_subtype_for_amass(word: str) -> str:
    """ "Orcs" -> "Orc". Amass prints its creature type in the plural, and CR
    205.3m's subtype list is singular ("Orc", "Zombie", "Army"), so the two
    have to be reconciled before the token is built or the "is it already
    one" test below would never match.

    Deliberately the narrowest possible rule - drop one trailing "s" - rather
    than a general English pluraliser: every creature type amass has ever
    been printed with pluralises that way, and a subtype that does not
    (there is none in CR 205.3m today) would come out wrong in a way a
    cleverer rule would only hide.

    Named for its one caller, `amass` below - see `_singular_subtype_for_
    transform_all`'s own docstring for why this plain name changed at all.
    A distinct name from `count_expression`'s own `_singular_subtype_for_
    count_expression` on purpose: this one keeps the printed capitalisation
    (the token subtype `create_tokens` builds wants "Orc", not "orc") where
    that one lowercases against a vocabulary. The two used to share the bare
    name `_singular_subtype`, which meant whichever of the module-level
    definitions came *last* in the file silently won for every caller of
    any of them - `count_expression`'s own "the number of Forests you
    control" was quietly reading this function's un-lowercased "Forest" and
    comparing it against a lowercased board subtype, never matching. Never
    reuse a name already defined elsewhere in this module for a function
    with different behaviour: Python has no error for it, only a wrong
    answer with no traceback.
    """
    return word[:-1] if word.endswith(("s", "S")) and len(word) > 1 else word


#: "Choose target <quality> card in your graveyard" - Emry, Lurker of the
#: Loch's tap ability and Silas Renn, Seeker Adept's combat damage trigger. The
#: card is the ability's own target, already validated by `machines/targeting`
#: when it was chosen (CR 601.2c, CR 603.3d) and rechecked on resolution
#: (CR 608.2b), so this antecedent only has to hand back the target still
#: legal. One target, so the permission sentence's pronoun must be singular.
_CHOOSE_TARGET_CARD_RE = re.compile(r"^choose target (?!.*\bcards\b).*\bcard\b.*$", re.IGNORECASE)


def _parse_chosen_target_card_antecedent(
    clause: str,
) -> "tuple[ExileAntecedent, bool] | None":
    """ "choose target <...> card <...>": the referent is the chosen target."""
    if _CHOOSE_TARGET_CARD_RE.fullmatch(clause.strip()) is None:
        return None

    def chosen(game: "Game", stack_object: "StackObject") -> list[CardState]:
        return game.resolve_card_targets(stack_object)

    return chosen, False


def _type_word_is_readable(word: str) -> bool:
    """Whether `_named_type_matcher` can really read this one quality word.

    Only CR 205.2a's card types, optionally negated with "non" (CR 109.2), are
    accepted. A land subtype (CR 205.3i) is deliberately not: `has_land_type`
    matches any string against a card's subtypes and so can never *fail*,
    which makes it useless as a readability test - a typo would validate.
    Failing closed here is what sends an unreadable quality to a notice
    instead of to a search that silently finds nothing.
    """
    if word.strip().lower() == "permanent":
        return True  # CR 110.4a's six permanent types, read by `_named_type_matcher`
    if word.strip().lower() == "equipment":
        return True  # CR 301.5a's artifact subtype - see `_quality_word_matcher`
    if word.strip().lower() == "double-faced":
        return True  # CR 712.1's own shape, read by `_named_type_matcher`
    lowered = word.strip().lower().removeprefix("non")
    try:
        Type(lowered)
    except ValueError:
        # A bare creature type (CR 205.3m) is the other shape `_named_type_
        # matcher` now reads - `subtype_vocabulary()` is closed, so this
        # still fails a genuine typo the same way the card-type branch above
        # does, unlike `has_land_type`'s open test this function's own
        # docstring already excludes for exactly that reason.
        return word.strip().lower() in subtype_vocabulary()
    return True


def _normalize_keyword_list(text: str) -> str:
    """ "vigilance and menace" -> "Vigilance, Menace": an "except they have"
    ability list, joined by "and" and/or commas in the printed sentence, put
    back into the comma-separated capitalised-first-word shape an ordinary
    printed keyword line uses ("Flying, first strike") so the same keyword
    reader that already handles a real card's own line handles an added one.
    """
    words = [word for word in re.split(r",\s*|\s+and\s+", text.strip()) if word]
    return ", ".join(word[:1].upper() + word[1:] for word in words)


#: The base clause's own target phrase, wherever it sits in the sentence -
#: trailing ("Firebending Lesson deals 2 damage **to target creature**") or
#: leading ("**Target creature** gets +3/+3 until end of turn", Colossal
#: Growth) - stopped short of whatever the clause goes on to say: a comma, a
#: full stop, one of CR 608.2c's own resolution verbs (`machines/targeting.
#: py`'s `_TARGET_CLAUSE_VERB_RE` reads the identical boundary for the same
#: reason, over the *whole* card's text rather than one already-isolated
#: clause), or the end of the clause. Used only to find the noun CR 400.7's
#: "that `<noun>`" anaphor below has to match - never to build the splice
#: `_TRAILING_TARGET_PHRASE_RE` above still owns, which only ever reads the
#: trailing shape.
_TARGET_PHRASE_ANYWHERE_RE = re.compile(
    r"\b(?P<phrase>any target|(?:up to [^,.]+ )?target [^,.]+?)"
    r"(?=[,.]|\s+(?:gets?|gains?|becomes?|loses?|deals?|has|have|is|are|unless)\b|$)",
    re.IGNORECASE,
)


#: A target noun made only of permanent-type words ("creature or planeswalker",
#: "artifact", "nonland permanent") - the targets "that permanent" can stand
#: for (CR 110.1).
_PERMANENT_TYPES_ONLY_RE = re.compile(
    r"(?:non)?(?:creature|planeswalker|artifact|enchantment|land|battle|permanent)s?"
    r"(?:(?:,\s*|\s+or\s+|\s+and/or\s+)(?:non)?"
    r"(?:creature|planeswalker|artifact|enchantment|land|battle|permanent)s?)*",
    re.IGNORECASE,
)


def _anaphoric_target_substitution(base_text: str, alternative_text: str) -> str | None:
    """CR 400.7's "that `<noun>`" is anaphora back to the base clause's own
    already-fixed target (CR 601.2c), not a second, elided one - Colossal
    Growth's "If this spell was kicked, instead that creature gets +4/+4 and
    gains trample and haste until end of turn" names its target exactly the
    way Firebending Lesson's "it deals 5 damage to that creature instead"
    does. Swaps the anaphor for the literal phrase the base clause printed
    ("that creature" -> "target creature") so the alternative reads as an
    ordinary targeted clause, rather than leaving the anaphor in place for
    `parse_mixed_effect_for_spell` to fail on or blindly appending a second,
    redundant target phrase the way the elided-tail splice below would.

    `None` when the base names no target noun `_TARGET_PHRASE_ANYWHERE_RE`
    can read, or the alternative uses no matching anaphor at all - the
    elided-tail splice owns every other shape.
    """
    match = _TARGET_PHRASE_ANYWHERE_RE.search(base_text.strip())
    if match is None:
        return None
    bare_noun = re.sub(
        r"^(?:up to [^,]+ )?(?:any )?target\s*", "", match.group("phrase"), flags=re.IGNORECASE
    ).strip()
    if not bare_noun:
        return None
    anaphor = re.compile(rf"\bthat\s+{re.escape(bare_noun)}\b", re.IGNORECASE)
    if anaphor.search(alternative_text):
        return anaphor.sub(match.group("phrase"), alternative_text, count=1)
    # "that permanent" names a target of any permanent type (CR 110.1) - Torch
    # the Tower's bargained "instead it deals 3 damage to that permanent" over
    # its "target creature or planeswalker".
    if _PERMANENT_TYPES_ONLY_RE.fullmatch(bare_noun):
        permanent_anaphor = re.compile(r"\bthat\s+permanent\b", re.IGNORECASE)
        if permanent_anaphor.search(alternative_text):
            return permanent_anaphor.sub(match.group("phrase"), alternative_text, count=1)
    # The pronoun form, "it", as the alternative's own subject - You're Not
    # Alone's "If you control three or more creatures, it gets +4/+4 until
    # end of turn instead" - refers back to the same fixed target. Only the
    # leading subject is swapped: an "it" further in names something the
    # alternative itself introduced, not the base clause's target.
    pronoun = re.compile(r"^it\b", re.IGNORECASE)
    if pronoun.match(alternative_text.strip()):
        return pronoun.sub(match.group("phrase"), alternative_text.strip(), count=1)
    return None


#: "[`<leading clause(s)>`. ]If `<condition>`, `<consequence>`. Otherwise,
#: `<otherwise>`." - Unholy Annex's own end-step trigger ("draw a card. If
#: you control a Demon, each opponent loses 2 life and you gain 2 life.
#: Otherwise, you lose 2 life."). `_parse_condition_clause` above reads a
#: bare "if X, Y"/"Y if X" as one clause; CR 608.2c's "otherwise" branch is
#: the *second* sentence of the same instruction, which `split_effect_
#: clauses`'s ordinary per-period split would cut away from the "if" that
#: governs it, leaving "Otherwise, `<otherwise>`" a fragment no per-clause
#: reader could ever read alone. Read here as one whole-text shape instead,
#: the same "read together, not each alone" reasoning every other entry
#: tried "ahead of everything else" in this ladder already has.
_LEADING_THEN_IF_OTHERWISE_RE = re.compile(
    r"^(?:(?P<leading>.+?)\.\s*)?if (?P<condition>.+?),\s*(?P<consequence>.+?)\.\s*"
    r"otherwise,\s*(?P<otherwise>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


#: "`<consequence>` if `<condition>`. Otherwise, `<otherwise>`." - the
#: trailing-"if" spelling of the same CR 608.2c instruction (Cosmos Elixir:
#: "draw a card if your life total is greater than your starting life total.
#: Otherwise, you gain 2 life."). The condition has no comma to end it, so it
#: runs to the sentence's period.
_TRAILING_IF_OTHERWISE_RE = re.compile(
    r"^(?P<consequence>[^.]+?) if (?P<condition>[^.,]+)\.\s*otherwise,\s*(?P<otherwise>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s2", for_spell=False)
def _parse_leading_then_if_otherwise_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_LEADING_THEN_IF_OTHERWISE_RE`'s shape - see its own docstring.

    `leading`, when printed, is any ordinary clause(s) `parse_mixed_effect`/
    `parse_mixed_effect_for_spell` already read ("draw a card"), run first
    and unconditionally - CR 608.2c's own instruction order. The condition
    is read the identical way `_parse_condition_clause` already does,
    anaphora and all (a triggered ability's own trigger event threaded
    through `Game.condition_holds`), and an unreadable one - by the same
    `_effect_condition_is_readable` gate - leaves the *whole* clause unread
    rather than guessed at.
    """
    match = _LEADING_THEN_IF_OTHERWISE_RE.fullmatch(
        text.strip()
    ) or _TRAILING_IF_OTHERWISE_RE.fullmatch(text.strip())
    if match is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text, allow_anaphor=not for_spell):
        return None
    parser = parse_mixed_effect_for_spell if for_spell else parse_mixed_effect
    leading_text = match.groupdict().get("leading")
    leading_effect = parser(leading_text.strip()) if leading_text else None
    if leading_text and leading_effect is None:
        return None
    consequence = parser(match.group("consequence").strip())
    if consequence is None:
        return None
    otherwise = parser(match.group("otherwise").strip())
    if otherwise is None:
        return None
    stripped = text.strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if leading_effect is not None:
            leading_effect(game, stack_object)
        controller = game.controller_of(stack_object)
        source = stack_object.source(game) if is_ability(stack_object) else stack_object
        if for_spell:
            held = game.condition_holds(controller.username, condition_text, source)
        else:
            assert isinstance(stack_object, AbilityOnStack)
            held = game.condition_holds(
                controller.username,
                condition_text,
                source,
                ability=stack_object.ability,
                event=stack_object.event,
                source_stamp=stack_object.source_stamp,
            )
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=(
                    stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
                ),
                text=stripped,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            consequence(game, stack_object)
        else:
            otherwise(game, stack_object)

    return effect


#: G7: "`<SUBJ>` `<verb1>`[, `<verb2>`, ...][,] and `<verbN>`." - one CR
#: 608.2c instruction naming several actions for a single subject that
#: `_CLAUSE_SEPARATOR`'s own bare "and"/comma split has no notion is shared:
#: split apart, only the *first* fragment still carries the subject, and
#: every later one is an orphaned bare verb phrase.
#:
#: `SUBJ` is one of five shapes:
#: - "target opponent"/"target player" - CR 115.1: the target is announced
#:   once, when the ability or spell is put on the stack, and every later
#:   item in the list names that identical player, never a fresh target.
#:   `Game.resolve_targets` is safe to call again for each item - it re-reads
#:   the same fixed `spell.targets`/`ability.targets` list every time (CR
#:   608.2b's own legality recheck), never asks a new targeting question.
#: - "each opponent"/"each player" - CR 101.4's own APNAP order; every item
#:   of the list runs against one player before the next player's turn
#:   comes, matching CR 608.2c's "in the order written" read per player.
#: - "you" - the resolving spell's or ability's own controller.
#:
#: Archon of Cruelty's own trigger ("target opponent sacrifices a creature
#: or planeswalker of their choice, discards a card, and loses 3 life. You
#: draw a card and gain 3 life.") is two of these in a row, one per subject -
#: the reported card, and the one that exposed the bug below. Dusk Mangler
#: ("each opponent sacrifices a creature of their choice, discards a card,
#: and loses 4 life.") is the "each opponent" shape with three items.
#:
#: **The fail-open this closes**: before this reader existed, an orphaned
#: fragment like "loses 3 life" reached `_parse_mixed_clause`'s own last
#: resort, `_parse_optional_player_clause`, whose generic "you " retry
#: exists for a *genuinely* subjectless sentence ("You gain 2 life, draw two
#: cards" - the subject really is "you", just printed once). That retry has
#: no memory of what the true subject actually was a clause or two back, so
#: for Arbiter of Woe ("each opponent discards a card and loses 2 life")
#: it silently ran "you loses 2 life" against the resolving ability's own
#: *controller* - the wrong player entirely, with no notice, sweep-visible
#: as "handled" only because something ran, not because the something was
#: right. This reader is tried first, whole, ahead of the ordinary split
#: (see its call site in `_parse_mixed_clauses`), so for every sentence
#: shaped like this the true subject is read directly off the sentence and
#: carried to every item in its list - the blind "you" retry is never
#: reached for these sentences at all.
#:
#: "that player" is the player a triggered ability's own event named
#: (`GameEvent.player`, the same referent `_parse_that_player_clause` reads)
#: - Ob Nixilis, Unshackled's "that player sacrifices a creature of their
#: choice and loses 10 life", Sword of Feast and Famine's "that player
#: discards a card and you untap all lands you control". Ability-only: a
#: resolving spell has no event to read it against.
_SHARED_SUBJECT_RE = re.compile(
    r"^(?P<subject>target opponent|target player|each opponent|each player|that player|you)"
    r"\s+(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _split_shared_subject_verb_parts(rest: str) -> list[str] | None:
    """`rest` (everything after `SUBJ`) split at its own list boundaries -
    "sacrifices a creature, discards a card, and loses 3 life" into three
    verb phrases, the same "A, B, and C" grammar `_parse_comma_chained_
    player_clause` already splits for a plain "you" subject, generalised to
    also split the one bare " and " a two-item list carries with no comma at
    all ("discards a card and loses 2 life").

    `None` for anything that is not genuinely a list of two or more items: a
    lone verb phrase is left for the more specific single-clause readers
    that already read it correctly (`_parse_target_player_sacrifices_
    clause`, `_EACH_OPPONENT_DISCARDS_RE`, and the rest), never claimed by
    this more general reader.
    """
    parts = [part.strip() for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", rest) if part.strip()]
    if len(parts) < 2:
        return None
    return parts


def _parse_bare_shared_subject_verb_clause(part: str) -> ClauseEffect | None:
    """One item of a `_SHARED_SUBJECT_RE` list, read as a verb phrase with no
    subject of its own - the identical bare vocabulary `_parse_optional_
    player_clause`'s own "you " retry already reads (`parse_clause_effect`,
    tried bare and then with "you " restored), plus the sacrifice-of-choice
    edict (`_BARE_SACRIFICE_OF_CHOICE_RE`) that shared vocabulary does not
    carry - see that regex's own docstring for why it stays private to this
    caller rather than widening `parse_clause_effect` itself.
    """
    return (
        _parse_bare_sacrifice_of_choice_clause(part)
        or parse_clause_effect(part)
        or parse_clause_effect(f"you {part}")
    )


def _group_shared_subject_parts(
    subject: str, parts: list[str]
) -> list[tuple[str, list[str]]] | None:
    """`parts` (already subject-stripped off the sentence's own head)
    regrouped by *effective* subject: a run of items that carry no subject
    of their own inherits `subject` (the sentence's leading one, or the
    most recent restatement), and an item that restates one of the same
    five shapes (`_SHARED_SUBJECT_RE`, reused here for one item at a time
    rather than the whole sentence) opens a new run from itself onward,
    with that subject word stripped before the verb phrase is read.

    This is what Blood Artist's own "target player loses 1 life **and you**
    gain 1 life." needs: the second item is not an orphaned bare verb at
    all, it names its own subject explicitly, and a different one from the
    first item's "target player" - `_split_shared_subject_verb_parts` alone
    has no way to tell "you gain 1 life" (self-contained) apart from an
    orphaned "gain 1 life" fragment by shape, so every item is re-checked
    against the identical vocabulary the sentence's own head already reads,
    rather than blindly run against the previous item's carried subject.

    Returns groups in order, each `(effective_subject, [verb phrases])`, or
    `None` if a restated subject leaves no verb phrase behind (a malformed
    "and you." with nothing after it).
    """
    groups: list[tuple[str, list[str]]] = []
    current_subject = subject
    current_parts: list[str] = []
    for part in parts:
        restated = _SHARED_SUBJECT_RE.fullmatch(part)
        if restated is not None:
            if current_parts:
                groups.append((current_subject, current_parts))
            current_subject = restated.group("subject").lower()
            current_parts = [restated.group("rest").strip()]
        else:
            current_parts.append(part)
    if not current_parts:
        return None
    groups.append((current_subject, current_parts))
    return groups


def _shared_subject_group_effect(
    subject: str, clause_effects: list[ClauseEffect], *, for_spell: bool
) -> TargetedClause | None:
    """One `_group_shared_subject_parts` group's own `subject`, turned into
    a `TargetedClause` that runs every one of `clause_effects` against
    whichever player(s) that subject names."""

    def run_for_player(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        for clause_effect in clause_effects:
            clause_effect(game, player, source, source_id)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    if subject == "you":

        def you_effect(game: "Game", stack_object: "StackObject") -> None:
            player = game.controller_of(stack_object)
            source = (
                stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
            )
            run_for_player(game, player, source, source_id_of(stack_object))

        return you_effect

    if subject == "that player":
        if for_spell:
            return None

        def that_player_effect(game: "Game", stack_object: "StackObject") -> None:
            if not isinstance(stack_object, AbilityOnStack):
                return
            event = stack_object.event
            if event is None or event.player is None:
                return
            run_for_player(
                game,
                game.player(event.player),
                stack_object.source_name,
                source_id_of(stack_object),
            )

        return that_player_effect

    if subject in ("target opponent", "target player"):
        if not _targets_understood(subject, allow_player_targets=True):
            return None

        def target_effect(game: "Game", stack_object: "StackObject") -> None:
            source = (
                stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
            )
            # CR 608.2b: the target - chosen once, when this spell or ability
            # was put on the stack - is re-checked for legality here, the
            # same recheck every other targeted reader already gets from
            # `resolve_targets`. A player target essentially never becomes
            # illegal mid-resolution (nothing between this ability's own
            # clauses can remove a player from the game), so every item of
            # the list runs against that same, still-legal player.
            for target in game.resolve_targets(stack_object):
                if isinstance(target, Player):
                    run_for_player(game, target, source, source_id_of(stack_object))

        return target_effect

    # "each opponent" / "each player" (CR 101.4's own APNAP order).
    opponents_only = subject == "each opponent"

    def each_effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        controller_username = game.controller_of(stack_object).username
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller_username:
                continue
            run_for_player(game, player, source, source_id_of(stack_object))

    return each_effect


def _parse_shared_subject_sentence(sentence: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SHARED_SUBJECT_RE`'s shape for one whole sentence, or `None`.

    Fail-closed per sentence, the same CR 608.2c "no partial run of the
    instruction" posture every other clause parser in this module already
    takes: every item of the list must itself parse, or the whole sentence
    stays unread rather than running some of its actions and silently
    dropping the rest.
    """
    stripped = sentence.strip().rstrip(".").strip()
    match = _SHARED_SUBJECT_RE.fullmatch(stripped)
    if match is None:
        return None
    subject = match.group("subject").lower()
    parts = _split_shared_subject_verb_parts(match.group("rest").strip())
    if parts is None:
        return None
    groups = _group_shared_subject_parts(subject, parts)
    if groups is None:
        return None
    group_effects: list[TargetedClause] = []
    for group_subject, group_parts in groups:
        clause_effects = [_parse_bare_shared_subject_verb_clause(part) for part in group_parts]
        if any(effect is None for effect in clause_effects):
            return None
        verified_effects = [effect for effect in clause_effects if effect is not None]
        group_effect = _shared_subject_group_effect(
            group_subject, verified_effects, for_spell=for_spell
        )
        if group_effect is None:
            return None
        group_effects.append(group_effect)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for group_effect in group_effects:
            group_effect(game, stack_object)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def _self_referential_delayed_effect(clause: str) -> AbilityEffect:
    """A triggered ability whose whole effect is a delayed clause about its
    own source - Prized Amalgam's "return this card from your graveyard to
    the battlefield tapped at the beginning of the next end step." CR 603.7a
    creates the ability as this one resolves, about the source *as it is
    now*: `expected_stamp` is its current zone-change stamp, so a card that
    has since left the graveyard and come back is a new object CR 603.7c
    will not return (CR 400.7)."""

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game) if ability.source_id is not None else None
        if not isinstance(source, CardState):
            return
        trigger = anaphoric_delayed_trigger(
            clause,
            subject=source,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            game=game,
        )
        if trigger is not None and source.zone is trigger.expected_zone:
            game.create_delayed_trigger(trigger)

    return effect


#: A word that points back at an object named earlier (CR 608.2c) - ahead of
#: a sentence's own "target", it ties that sentence to an earlier one ("Then
#: it fights target creature ..."), so the two cannot be read apart.
_BACK_REFERENCE_RE = re.compile(r"\b(?:then|it|its|they|them|their|that|those)\b", re.I)


#: The words without which `profile_for_text` reads no requirement: "target"
#: itself, and the keyword actions it spells out into targets (Support N, CR
#: 701.41a; Earthbend N, CR 701.66a).
_MAY_NAME_A_TARGET_RE = re.compile(r"target|support|earthbend", re.I)


def _target_sentence_groups(whole: str) -> list[tuple[str, int]] | None:
    """`whole`'s sentences grouped so each group opens with a sentence that
    names its own "target" (CR 601.2c) and carries the targetless sentences
    after it ("Tap target land. That land doesn't untap ..."): each group's
    text and how many target requirements it opens with. `None` when a
    sentence names a target this cannot attribute, or one leans on an
    earlier group's object ahead of its own target."""
    if len(_MAY_NAME_A_TARGET_RE.findall(whole)) < 2:  # two groups, two targets
        return None
    groups: list[tuple[list[str], int]] = []
    leading: list[str] = []
    for sentence in _plain_resolution_sentences(whole):
        count = 0
        if _MAY_NAME_A_TARGET_RE.search(sentence):
            own = profile_for_text(sentence)
            count = len(own.requirements) if own.understood else 0
        if count == 0:
            if re.search(r"\btargets?\b", sentence, re.I):
                return None
            if groups:
                groups[-1][0].append(sentence)
            else:
                leading.append(sentence)
            continue
        word = re.search(r"\btarget", sentence, re.I)
        opening = sentence[: word.start()] if word is not None else sentence
        if groups and _BACK_REFERENCE_RE.search(opening):
            return None
        groups.append(([*leading, sentence], count))
        leading = []
    if leading or len(groups) < 2:
        return None
    return [(" ".join(sentences), count) for sentences, count in groups]


#: One sentence group's own effect: an `Effect` for a spell, an
#: `AbilityEffect` for an ability - called with whichever is resolving.
_GroupStep = Callable[["Game", Any], None]


def _per_target_sentence_steps(
    whole: str, *, for_spell: bool
) -> tuple[list[tuple[_GroupStep, frozenset[int]]], TargetingProfile] | None:
    """Each sentence group of `whole` (`_target_sentence_groups`) read on its
    own, with the requirement slots (CR 601.2c, `TargetRef.slot`) its own
    "target" phrases filled - or `None` when any group does not read cleanly
    or its targets cannot be told apart."""
    from .dispatch import _ability_effect_or_notice, _spell_effect_or_notice
    from .tokens import _is_notice_only

    groups = _target_sentence_groups(whole)
    if groups is None:
        return None
    full = spell_profile_for_text(whole) if for_spell else profile_for_text(whole)
    if not full.understood or len(full.requirements) != sum(n for _, n in groups):
        return None
    # The profile's requirement order is not the printed order (Jeskai
    # Revelation's lists "any target" first), so a group's slots are found by
    # phrase - each phrase printed once, or which slot is whose is unknowable.
    slot_of = {r.phrase.lower(): index for index, r in enumerate(full.requirements)}
    if len(slot_of) != len(full.requirements):
        return None
    steps: list[tuple[_GroupStep, frozenset[int]]] = []
    for group_text, _ in groups:
        phrases = [r.phrase.lower() for r in profile_for_text(group_text).requirements]
        if any(phrase not in slot_of for phrase in phrases):
            return None
        read: _GroupStep | None = (
            _spell_effect_or_notice(group_text)
            if for_spell
            else _ability_effect_or_notice(group_text)
        )
        if (
            read is None
            or _is_notice_only(read)
            or getattr(read, "unparsed_remainder", None) is not None
        ):
            return None
        steps.append((read, frozenset(slot_of[phrase] for phrase in phrases)))
    return steps, full


def _per_target_sentence_effect(whole: str, *, for_spell: bool) -> TargetedClause | None:
    """A spell or ability whose sentences each name their own target - Jeskai
    Revelation's "Return target spell or permanent to its owner's hand.
    Jeskai Revelation deals 4 damage to any target. ...", Everything Pizza's
    "Target player gains 3 life ... This artifact deals 3 damage to any
    target. ..." - read sentence group by sentence group, each group seeing
    only the targets announced for its own phrase.

    CR 601.2c: each target is chosen for one instance of the word "target",
    and `TargetRef.slot` records which. The generic per-clause readers
    (`parse_mixed_effect_for_spell`/`parse_mixed_effect`) hand every clause
    the whole target list, so Jeskai Revelation's bounce sentence also
    returned its damage target. Every group must read on its own (no notice,
    no unread remainder) and the groups' requirements must be the whole
    text's; otherwise this declines and the text reaches the readers it
    always did."""
    read = _per_target_sentence_steps(whole.strip(), for_spell=for_spell)
    if read is None:
        return None
    steps, full = read

    def per_target_sentence_groups(game: "Game", stack_object: "StackObject") -> None:
        refs = list(stack_object.targets)
        division = stack_object.division
        if all(ref.slot is not None for ref in refs):
            slots = [ref.slot for ref in refs]
        else:
            slots = full.assign_slots(
                [game.resolve_target(ref) for ref in refs],
                game.controller_of(stack_object).username,
                game,
                source_id_of(stack_object),
            )
        try:
            for step, wanted in steps:
                keep = [index for index, slot in enumerate(slots) if slot in wanted]
                stack_object.targets = [refs[index] for index in keep]
                if division is not None and len(division) == len(refs):
                    stack_object.division = [division[index] for index in keep]
                step(game, stack_object)
                game.announce_batched_events()  # CR 603.2c: one event per instruction
        finally:
            stack_object.targets = refs
            stack_object.division = division

    return per_target_sentence_groups


@SPELL_TEXT.rung("s23", before=["dispatch.parse_mixed_effect_for_spell"])
def _parse_per_target_sentence_groups(text: str) -> Effect | None:
    """`_per_target_sentence_effect` for a spell."""
    return _per_target_sentence_effect(text, for_spell=True)


@ABILITY_TEXT.rung("s40", before=["dispatch.parse_mixed_effect"])
def _parse_per_target_sentence_groups_ability(text: str) -> AbilityEffect | None:
    """`_per_target_sentence_effect` for an activated or triggered ability."""
    return _per_target_sentence_effect(text, for_spell=False)


# --------------------------------------------------------------------------
# "Choose <target phrase>." openers and the anaphor that refers back to them
# --------------------------------------------------------------------------
#
# CR 115.1a: "An instant or sorcery spell is targeted if its spell ability
# identifies something it will affect by using the phrase 'target
# [something]' ... The target(s) are chosen as the spell is cast". Harnessed
# Lightning, Practiced Tactics, Blast of Genius and Drown in Filth open with a
# bare "Choose target creature." / "Choose any target." sentence that does
# nothing on resolution itself: it only names the target, and a later
# sentence acts on it through an anaphor - "that creature", "that permanent
# or player" (CR 608.2c: "later text on the card may modify the meaning of
# earlier text"). `machines/targeting.py` already reads the target phrase
# wherever it sits, so the spell is cast with the right target; what no
# reader could do was act on "that creature" with no "target" word left in
# the sentence that acts.
#
# The opener is read here once, as a normaliser, and the rest of the spell
# handed back to the ordinary readers in one of three readings, first
# readable wins:
#
# 1. the anaphor replaced by the target phrase itself - "Mill four cards,
#    then target creature gets -1/-1 ... for each land card in your
#    graveyard" - so every reader that already acts on "target creature"
#    acts on the chosen one (`game.resolve_targets`, CR 608.2b's recheck
#    included);
# 2. the rest as printed, for a reader that binds the anaphor to the
#    spell's target itself (a delayed trigger about "that creature",
#    `_parse_that_object_turn_trigger_spell_text` below);
# 3. the opener kept and the anaphor named by its generic noun, "that
#    permanent", for a whole-text reader written against that noun -
#    "that creature" and "that permanent" are the same chosen object.
#
# Only one target requirement, and no other "target" in the rest: a second
# requirement ("Choose target creature you control and target creature you
# don't control") is the fight/bite openers' shape, read elsewhere.
_CHOOSE_TARGET_PRELUDE_RE = re.compile(
    r"^choose (?P<phrase>any target|[^.]*?\btargets?\b[^.]*?)\.\s+(?P<rest>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)

#: The anaphors a "Choose <target>." opener's later sentences refer back with.
_PRELUDE_REFERENT_RE = re.compile(
    r"\b(?:that|the chosen|the) (?P<noun>permanent or player|creature or planeswalker|"
    r"creature|permanent|player|planeswalker|artifact|enchantment|land|card)\b"
    r"|\bthose (?P<plural>cards|creatures|permanents)\b",
    re.IGNORECASE,
)

#: Nouns that name only a permanent, so "that permanent" names the same object.
_PERMANENT_REFERENT_NOUNS = frozenset(
    {"creature", "planeswalker", "artifact", "enchantment", "land", "creature or planeswalker"}
)


def split_choose_target_prelude(text: str) -> "tuple[str, str] | None":
    """(target phrase, the rest) when `text` opens with "Choose <one target
    phrase>." and the rest names no target of its own, else `None`."""
    match = _CHOOSE_TARGET_PRELUDE_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    rest = match.group("rest").strip()
    if len(re.findall(r"\btargets?\b", phrase, re.IGNORECASE)) != 1:
        return None
    if re.search(r"\btargets?\b", rest, re.IGNORECASE):
        return None
    return phrase, rest


def _prelude_readings(phrase: str, rest: str) -> list[str]:
    """The readings of `_CHOOSE_TARGET_PRELUDE_RE`'s banner, in order."""
    readings: list[str] = []
    referents = [
        found
        for found in _PRELUDE_REFERENT_RE.finditer(rest)
        if found.group(0).lower().startswith(("that", "the chosen", "those"))
        or found.start() == 0
        or rest[: found.start()].rstrip().endswith(".")
    ]
    sentence_start = rest.rfind(".", 0, referents[0].start()) + 1 if len(referents) == 1 else 0
    in_trigger_condition = len(referents) == 1 and re.match(
        r"\s*(?:whenever|when)\b", rest[sentence_start:], re.IGNORECASE
    )
    if len(referents) == 1 and not in_trigger_condition:
        # A trigger condition is never bound this way: "Whenever target
        # creature ..." names no object at all (CR 603.7c needs the one the
        # opener chose), so reading 2 below reads it instead.
        found = referents[0]
        bound = phrase[0].upper() + phrase[1:] if found.group(0)[0].isupper() else phrase
        readings.append(rest[: found.start()] + bound + rest[found.end() :])
    readings.append(rest)
    if (
        len(referents) == 1
        and (referents[0].group("noun") or "").lower() in _PERMANENT_REFERENT_NOUNS
    ):
        found = referents[0]
        readings.append(
            f"Choose {phrase}. {rest[: found.start()]}that permanent{rest[found.end() :]}"
        )
    return readings


def _readable(effect: object) -> bool:
    return (
        effect is not None
        and not _is_notice_only(effect)
        and getattr(effect, "unparsed_remainder", None) is None
    )


@SPELL_TEXT.rung("s21")
def _parse_choose_target_prelude_spell_text(text: str) -> Effect | None:
    """A "Choose <target phrase>." opener and the rest of the spell; see the
    banner above. The opener itself does nothing on resolution (the target
    was chosen on casting, CR 115.1a), so the spell is exactly its rest."""
    split = split_choose_target_prelude(_strip_non_effect_preamble(text))
    if split is None:
        return None
    phrase, rest = split
    if not _targets_understood(
        phrase, count_agnostic=True, battlefield_only=False, allow_player_targets=True
    ):
        return None
    for reading in _prelude_readings(phrase, rest):
        effect = _spell_effect_or_notice(reading)
        if _readable(effect):
            return effect
    return None


#: "that player" in a spell's later sentence or instruction is the player its
#: one "target player"/"target opponent" named (CR 608.2c: later text on the
#: card may modify the meaning of earlier text; CR 115.1a: the target was
#: chosen as the spell was cast) - Aggressive Sabotage's "Target player
#: discards two cards. If this spell was kicked, it deals 3 damage to that
#: player.", Hidetsugu's Second Rite's "If target player has exactly 10 life,
#: <self> deals 10 damage to that player.". The same normalisation as the
#: "Choose <target>." opener's reading 1: the anaphor is written back as the
#: target phrase, and every reader that acts on "target player" acts on the
#: chosen one (`game.resolve_targets`, CR 608.2b's recheck included). Only
#: when that is the one "target" in the whole text, so there is exactly one
#: player the anaphor could mean.
_TARGET_PLAYER_PHRASE_RE = re.compile(r"\btarget (?:player|opponent)\b", re.IGNORECASE)
_THAT_PLAYER_RE = re.compile(r"\bthat player\b(?!\s+or\b)", re.IGNORECASE)


@SPELL_TEXT.rung("s22")
def _parse_that_player_anaphor_spell_text(text: str) -> Effect | None:
    """`_THAT_PLAYER_RE`'s anaphor bound to the one targeted player; see the
    banner above."""
    lowered = text.lower()
    if "that player" not in lowered or "target " not in lowered:
        return None
    if len(re.findall(r"\btargets?\b", text, re.IGNORECASE)) != 1:
        return None
    phrase = _TARGET_PLAYER_PHRASE_RE.search(text)
    anaphor = _THAT_PLAYER_RE.search(text)
    if phrase is None or anaphor is None or anaphor.start() < phrase.start():
        return None
    bound = phrase.group(0).lower()
    rewritten = _THAT_PLAYER_RE.sub(
        lambda found: bound[0].upper() + bound[1:] if found.group(0)[0].isupper() else bound, text
    )
    effect = _spell_effect_or_notice(rewritten)
    return effect if _readable(effect) else None


def _the_one_chosen_permanent(game: "Game", stack_object: "StackObject") -> CardState | None:
    """The one permanent the resolving object targets and still may affect
    (CR 608.2b), the referent of its later "that creature"; `None` when it
    chose none ("up to one", CR 115.6) or that one is gone."""
    chosen = [
        target
        for target in game.resolve_targets(stack_object)
        if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
    ]
    return chosen[0] if len(chosen) == 1 else None


@SPELL_TEXT.rung("s10", before=["tokens._parse_created_trigger_spell_text"])
def _parse_that_object_turn_trigger_spell_text(text: str) -> Effect | None:
    """ "Whenever that creature `<condition>` this turn, `<effect>`" about the
    spell's own target (`machines/delayed.ChosenObjectTriggeredAbility`):
    the creature the spell targets, not every creature - the generic created
    "this turn" trigger (`tokens._parse_created_trigger_spell_text`) has no
    object to bind "that creature" to, so this reads first."""
    line = chosen_object_turn_trigger_line(text)
    if line is None:
        return None
    printed = " ".join(text.strip().split())

    def effect(game: "Game", spell: CardState) -> None:
        chosen = _the_one_chosen_permanent(game, spell)
        if chosen is None:
            return
        create_chosen_object_turn_trigger(
            game,
            line,
            chosen,
            text=printed,
            controller=game.controller_of(spell).username,
            source_id=spell.id,
            source_name=spell.name,
        )

    return effect


@MIXED_CLAUSE.rung("s2")
def _parse_that_object_turn_trigger_clause(clause: str) -> TargetedClause | None:
    """One clause of a mixed effect: the same sentence after a targeted
    clause the clause splitter already read (Niko Aris's "+1: Up to one
    target creature you control can't be blocked this turn. Whenever that
    creature deals damage this turn, return it to its owner's hand.")."""
    line = chosen_object_turn_trigger_line(clause)
    if line is None:
        return None
    printed = " ".join(clause.strip().split())

    def effect(game: "Game", stack_object: "StackObject") -> None:
        chosen = _the_one_chosen_permanent(game, stack_object)
        if chosen is None:
            return
        if isinstance(stack_object, AbilityOnStack):
            source_id, source_name = stack_object.source_id, stack_object.source_name
        else:
            source_id, source_name = stack_object.id, stack_object.name
        create_chosen_object_turn_trigger(
            game,
            line,
            chosen,
            text=printed,
            controller=game.controller_of(stack_object).username,
            source_id=source_id,
            source_name=source_name,
        )

    return effect


@ABILITY_TEXT.rung("s20", before=["tokens._parse_created_trigger_ability_text"])
def _parse_that_object_turn_trigger_ability_text(text: str) -> AbilityEffect | None:
    """The ability side of `_parse_that_object_turn_trigger_spell_text`:
    Niko Aris's "+1: Up to one target creature you control can't be blocked
    this turn. Whenever that creature deals damage this turn, return it to
    its owner's hand." - its second sentence, bound to the ability's target."""
    line = chosen_object_turn_trigger_line(_strip_non_effect_preamble(text))
    if line is None:
        return None
    printed = " ".join(text.strip().split())

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        chosen = _the_one_chosen_permanent(game, ability)
        if chosen is None:
            return
        create_chosen_object_turn_trigger(
            game,
            line,
            chosen,
            text=printed,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
        )

    return effect


from ._common import (  # noqa: E402
    _ANAPHORIC_SUBJECT_RE,
    _CLAUSE_SEPARATOR,
    _COLOR_COUNT_WORDS,
    _COST_INCREASE_PER_TARGET_LINE_RE,
    _DESTROY_TARGET_RE,
    _EXILE_TARGET_RE,
    _HAND_EXILE_COLOR_WORDS,
    _MASS_CREATURE_SUBJECT_RE,
    _NON_SUBTYPE_PREFIX_RE,
    _OBJECT_ANAPHOR_RE,
    _PER_COUNT_COST_REDUCTION_LINE_RE,
    _QUOTED_SPAN_RE,
    _SELF_COST_REDUCTION_LINE_RE,
    _TIMING_COST_REDUCTION_LINE_RE,
    ConditionalClauseNotice,
    ExileAntecedent,
    _effect_condition_is_readable,
    _players_in_apnap_order,
    _targets_understood,
)
from .amounts import count_expression  # noqa: E402
from .continuous import (  # noqa: E402
    _attached_object,
    _block_restriction_duration,
    _is_keyword_ability_line,
    _layer_antecedent_clause,
    _parse_attach_referent_to_chosen_clause,
    _parse_if_type_may_attach_equipment_referent_clause,
    _parse_loses_keyword_referent_rider,
    layer_context_for,
)
from .counters import _counter_kind  # noqa: E402
from .damage import _parse_damage_each_other_type_and_each_opponent_clause  # noqa: E402
from .dispatch import (  # noqa: E402
    _parse_mixed_clause,
    _spell_effect_or_notice,
    parse_clause_effect,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .library import manifest_dread  # noqa: E402
from .removal import _parse_bare_sacrifice_of_choice_clause  # noqa: E402
from .search import _parse_search_mv_equal_to_sacrificed_clause, _search_and_place_for  # noqa: E402
from .tokens import (  # noqa: E402
    _is_notice_only,
    _parse_generic_token_descriptor,
    _readable_created_trigger,
    created_trigger_line,
)
