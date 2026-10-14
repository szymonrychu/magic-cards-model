import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import canonical_subtype, creature_type_vocabulary
from ...models.card import Color, Supertype, Type
from ...models.card_state import (
    CardState,
    Counter,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.token import (
    PREDEFINED,
    TokenDefinition,
    copiable_card_of,
    create_tokens,
    is_token,
    token_copy_of,
)
from ...models.zone import Zone
from ...numbers import (
    AMOUNT,
    COUNT,
    count_pattern,
    halve,
    parse_count,
    parse_multiplier,
    where_x_pattern,
)
from .. import (
    token_riders,
)
from ..abilities import (
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    parse_triggered_mana,
    self_reference_names,
)
from ..cost import (
    cost_announces_x,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    ANAPHORIC_TIMING_STEPS,
    CreatedTriggeredAbility,
    CreateTokenCopyOfLastKnown,
    DelayedTrigger,
    ReflexiveAttachSubjectToTargetConsequence,
    ReflexiveReturnThenAttachToSubjectConsequence,
    SacrificeSubject,
    anaphoric_delayed_trigger,
    parse_anaphoric_delayed_clause,
)
from ..ep02_r1_counter_amounts import counters_counted_text, counters_read_from
from ..layers import (
    ContinuousEffect,
    Duration,
    Layer,
    add_subtype,
    grant_ability,
    only_this_incarnation,
    split_and_validate_keywords,
)
from ..modes import (
    substitute_x,
)
from ..replacement import (
    CreatedReplacement,
    DrawSkipReplacement,
    created_replacement_spec,
    strip_reminder_text,
)
from ..targeting import (
    profile_for_text,
    spell_profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    event_subject_power,
    event_subject_toughness,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import _OBJECT_ANAPHOR, AbilityEffect, Effect, TargetedClause


def create_continuous_effect(game: "Game", spell: CardState) -> None:
    """The spell's effect is a continuous one, so record it (CR 611.2, CR 611.2a).

    What the spell generates, and how long it lasts, comes from `LAYER_EFFECTS`
    in `machines/layers.py`. The objects it applies to are the targets that are
    still legal now, and they are fixed here for good (CR 611.2c); the effect is
    timestamped now (CR 613.7b).

    The `LayerContext` carries what the builder cannot see from the battlefield:
    every graveyard, and separately the *controller's* graveyard, which is what
    a card printing "cards in your graveyard" means.
    Both are read now, as the spell resolves, which is the moment the effect's
    one-off conditions are locked in (CR 611.2c).

    `game=game` on the call below is not optional bookkeeping: `ContinuousEffects.
    create` calls `effect.holds(game)` on everything it builds, and `holds`
    raises rather than guessing when a built effect carries a CR 611.2b "for as
    long as" condition and no `game` was given to check it against. No row in
    `LAYER_EFFECTS` reaches this generic path with one yet - Tishana's Tidebinder,
    the only conditioned row today, resolves through its own dedicated function -
    but the next one that does must not crash resolution outright for a missing
    keyword (see `tests/test_continuous_effects_create_game_param.py`).
    """
    continuous_effects(game).create(
        spell,
        targets=game.resolve_card_targets(spell),
        context=layer_context_for(game, game.controller_of(spell)),
        ability_text=_x_substituted_spell_text(game, spell),
        game=game,
    )


def create_continuous_effect_of_ability(game: "Game", ability: AbilityOnStack) -> None:
    """The same for a resolving ability (CR 611.2 covers spells and abilities alike).

    Two shapes share this one function, told apart by whether the ability's
    *own printed text* names a target at all - not by whether `ability.targets`
    happens to be empty, which is ambiguous between them. When the ability
    names no target - Basking Rootwalla's "{1}{G}: This creature gets +2/+2
    until end of turn." - the affected object is the ability's own source.
    When it does - Karn, the Great Creator's "+1: ... up to one target
    noncreature artifact becomes an artifact creature ..." - the affected
    object is whatever it targeted, rechecked for legality now exactly as a
    spell's targets are (CR 608.2b): `game.resolve_card_targets` is the same
    call `create_continuous_effect` makes for a spell, so a loyalty ability
    reaches the layer engine through the ordinary activated-ability path
    rather than a planeswalker-specific one.

    `profile_for_text(ability.ability.text)` (the same call `Game.
    activate_ability` already made to check the announced targets' legality,
    CR 601.2c/602.2b) is what answers "does this ability's text require a
    target at all" - `ability.targets` being empty cannot answer that on its
    own, because CR 115.6 makes "up to one target ..." legally choosing zero a
    *different reason* for the same empty list. Reported defect: Karn's +1,
    activated with zero targets chosen (CR 115.6), used to fall through to
    `[source]` here and animate **Karn himself** into a 4/4 - wrong twice
    over, since a legendary planeswalker was never a legal "target noncreature
    artifact" to begin with (CR 601.2c) and CR 115.6's zero-targets case is
    required to leave the ability targeted at nothing, not silently
    redirected to its own source (CR 608.2, no target chosen affects nothing).
    "Up to one" legally choosing zero, or every chosen target having since
    become illegal (CR 608.2b), both leave `targets` empty and the ability
    resolves doing nothing - never a fallback to `source`.

    `game=game` on the call below matters the same way it does in `create_
    continuous_effect` just above: without it, `ContinuousEffects.create`
    crashes rather than resolving the moment this path ever reaches a
    `LAYER_EFFECTS` row that builds a CR 611.2b "for as long as" condition.
    """
    source = ability.source(game)
    if source is None:
        return
    mana_spent_text = _cast_trigger_mana_spent_x_ability_text(game, ability)
    if mana_spent_text is not None:
        ability_text = mana_spent_text
        profile = profile_for_text(ability_text)
        requires_target = profile.understood and bool(profile.requirements)
        if not requires_target and source.zone is not Zone.BATTLEFIELD:
            return
        targets = game.resolve_card_targets(ability) if requires_target else [source]
        if not targets:
            return
        continuous_effects(game).create(
            source,
            targets=targets,
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=_as_sentence(ability_text),
            game=game,
        )
        return
    # `x_value` substituted in first when the ability's own printed cost
    # announces one (CR 107.3a, announced before targets are chosen -
    # CR 601.2b/602.2b then CR 601.2c) - The Mycosynth Gardens' own "target
    # nontoken artifact you control with mana value X" is unreadable by
    # `profile_for_text` with a literal "X" left in it, which without this
    # would make `requires_target` false and silently fall back to `[source]`
    # (the Gardens targeting itself) instead of the real, paid X.
    #
    # `cost_announces_x` (not a bare `"{X}" in ...cost`) is CR 107.3a's own
    # wider reading: X is announced whenever the *cost's own text* names it,
    # never only when it is spelled as the `{X}` mana symbol - Chatterfang,
    # Squirrel General's "Sacrifice X Squirrels" announces X in plain English,
    # with no `{X}` anywhere in the cost, and the narrower check used to leave
    # this function reading the *unsubstituted* "Target creature gets +X/-X
    # until end of turn" - a magnitude no continuous-effect parser can read a
    # bare, non-numeric X out of - so the ability's cost paid but its pump did
    # nothing. `Game.activate_ability`'s own `x_value` gating and
    # `scripts/sweep_pool.py`'s own X-probe already read a cost's X this same
    # general way; this is the one caller that had not caught up.
    ability_text = (
        substitute_x(ability.ability.text, ability.x_value)
        if isinstance(ability.ability, ActivatedAbility) and cost_announces_x(ability.ability.cost)
        else ability.ability.text
    )
    # CR 122.1/CR 603.10a: "for each <kind> counter on this artifact" is the
    # count on the ability's source as it resolves.
    with counters_read_from(source):
        ability_text = counters_counted_text(
            ability_text, self_reference_names(source.name, legendary=True)
        )
    profile = profile_for_text(ability_text)
    requires_target = profile.understood and bool(profile.requirements)
    # CR 113.7a: "Once activated or triggered, an ability exists on the stack
    # independently of its source. Destruction or removal of the source after
    # that time won't affect the ability." A targeted ability still animates
    # or pumps what it targeted after its source is gone (Nissa, Who Shakes
    # the World destroyed in response to her own +1); only an ability that
    # affects its source itself has nothing left to affect.
    if not requires_target and source.zone is not Zone.BATTLEFIELD:
        return
    targets = game.resolve_card_targets(ability) if requires_target else [source]
    if not targets:
        return
    continuous_effects(game).create(
        source,
        targets=targets,
        context=layer_context_for(game, game.controller_of(ability)),
        # The ability's own text, which is not always a sentence printed on
        # `source`: a reflexive ability's (CR 603.12) text carries the count
        # its creating ability moved, written in as a digit (`_carry_count`),
        # and lost its period when it was cut out of the printed sentence.
        ability_text=_as_sentence(ability_text),
        game=game,
    )


def _create_continuous_effect_for_mode_text(mode_text: str) -> Effect:
    """`create_continuous_effect`, scoped to one chosen mode's own text
    rather than the whole card (`parse_mode_effect`).

    The bare `create_continuous_effect` sentinel always re-reads `spell.card`'s
    *whole* printed text through `parsed_layer_effects` (see its own
    docstring) - right for an ordinary, non-modal spell, but wrong for one
    mode of a modal spell (CR 700.2a): a card with two modes that each happen
    to be a CR 611.2 layer shape would apply *both* the moment either one
    reached the bare sentinel, even though only one was chosen and the other
    mode's own targets were never even asked for. `ContinuousEffects.create`'s
    `ability_text` override - the same mechanism `create_continuous_effect_
    of_ability` already relies on to read a granted ability's own text
    instead of its permanent's - reads `mode_text` alone instead.
    """

    def effect(game: "Game", spell: CardState) -> None:
        continuous_effects(game).create(
            spell,
            targets=game.resolve_card_targets(spell),
            context=layer_context_for(game, game.controller_of(spell)),
            ability_text=mode_text,
            game=game,
        )

    return effect


def _create_continuous_effect_of_ability_for_mode_text(mode_text: str) -> AbilityEffect:
    """The ability-side twin of `_create_continuous_effect_for_mode_text`,
    for one chosen mode of a modal *triggered* ability
    (`_resolve_modal_triggered_ability_clause` - Elder Gargaroth, Abiding
    Grace, and any modal trigger whose own chosen mode is itself a layer
    shape).

    A mode that names no target - Voltstorm Angel's "This creature gains
    vigilance and lifelink until end of turn." - affects the ability's own
    source, the same split `create_continuous_effect_of_ability` makes off
    the text's own targeting profile.
    """
    profile = profile_for_text(mode_text)
    requires_target = profile.understood and bool(profile.requirements)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        continuous_effects(game).create(
            source,
            targets=game.resolve_card_targets(ability) if requires_target else [source],
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=mode_text,
            game=game,
        )

    return effect


def _is_notice_only(effect: object) -> bool:
    """Whether a dispatcher answered with one of its fail-closed stand-ins
    (`anaphoric_notice_only`, `delayed_notice_only`, ...) rather than a real
    effect - named that way by `_spell_effect_or_notice` itself."""
    return getattr(effect, "__name__", "").endswith("notice_only")


#: Back from the Brink: "Exile a creature card from your graveyard and pay
#: its mana cost: Create a token that's a copy of that card." "That card" is
#: not a target (CR 115.1 - the sentence never says "target") - it is CR
#: 607.1's anaphora back to whatever `machines/cost.exile_and_pay_mana_cost_
#: cost` chose while the cost was paid, carried onto the stack as `AbilityOn
#: Stack.cost_exiled_card_id` (see that field's own docstring).
_CREATE_TOKEN_COPY_OF_THAT_CARD_RE = re.compile(
    r"^create a token that'?s a copy of that card\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s36")
def _parse_create_token_copy_of_cost_exiled_card_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_COPY_OF_THAT_CARD_RE`'s shape.

    CR 707.2's copiable values travel through `token_copy_of`, the same
    primitive Ocelot Pride's own token-copy clause already uses. Nothing to
    do if the cost was never actually paid with a card this ability
    remembers - CR 113.7a lets the ability resolve regardless, it simply has
    nothing left to copy.
    """
    if _CREATE_TOKEN_COPY_OF_THAT_CARD_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if ability.cost_exiled_card_id is None:
            return
        original = game.find_by_id(ability.cost_exiled_card_id)
        if not isinstance(original, CardState):
            return
        controller = game.controller_of(ability).username
        token_copy_of(game, original, controller)

    return effect


@ABILITY_TEXT.rung("s30")
def _parse_whole_text_token_clause(text: str) -> AbilityEffect | None:
    """A "Create ... token ..." ability read as *one whole, unsplit clause* -
    The Legend of Roku's `{8}` ability, "Create a 4/4 red Dragon creature
    token with flying and firebending 4.", and Minsc, Beloved Ranger's own
    ETB, "create Boo, a legendary 1/1 red Hamster creature token with
    trample and haste." (the CR 111.9 named-token shape of the identical
    problem).

    `_ability_effect_or_notice`'s ordinary path is `parse_mixed_effect`, which
    runs `split_effect_clauses` first - and that splitter's `_CLAUSE_SEPARATOR`
    cuts on a bare "and" (built for a sentence that joins two independent
    instructions, Lightning Helix's shape), which is wrong for a *comma-free
    two-item list inside one token's own "with" tail*: "with flying and
    firebending 4" would be cut into "with flying" and "firebending 4" before
    `_parse_token_clause` ever saw the whole tail, and the leftover
    "firebending 4" clause matches no shape at all - the whole ability failed
    closed over one keyword list, not because the token itself was unreadable.
    `_parse_token_clause` and `_parse_named_token_clause` are each tried
    directly against the untouched text instead; their own regexes only ever
    fullmatch a *complete* token-creation sentence, so a card whose token
    clause is one instruction among several is meant to fall through to the
    ordinary per-clause path unaffected - which needs an explicit guard, not
    just leaving it to either regex to fail: both regexes' own "named
    <name>" and "with <tail>" groups are a bare `.+?` with only a final `$`
    to anchor against, so hunting for a match against a genuinely
    multi-sentence text (Ingris Stingerquill's own "Create a 2/2 ... token
    named Cadet. Then creatures you control gain haste until end of turn.")
    lets the "name" backtrack straight through the interior period and
    swallow the second sentence whole, rather than failing the way "one
    instruction among several" promises. A period anywhere in the stripped
    text *outside of the token's own quoted ability* is exactly that second
    sentence, so this refuses before ever calling either parser at all - a
    period *inside* the quoted ability itself (CR 113.10a: a token's
    granted ability is free to be as many sentences as it needs, Wrenn and
    Seven's own "reach and \"This token's power and toughness are each
    equal to the number of lands you control.\"" among them) is never one
    of those, the same distinction `machines/abilities._split_top_level_
    sentences` draws for a permanent's own printed lines.
    """
    # `split_effect_clauses` always strips one trailing "." before a clause
    # ever reaches `_parse_token_clause`; going around that splitter (see the
    # docstring above) means doing the same trim here - `_TOKEN_CLAUSE_RE`'s
    # own trailing `\.?` never gets the chance to, since its greedy DOTALL
    # `tail` group is satisfied first and simply absorbs the period instead.
    stripped = _fold_following_token_grant(_strip_non_effect_preamble(text).strip()).rstrip(".")
    if _has_period_outside_quotes(stripped):
        return None
    return _parse_token_clause(stripped, for_spell=False) or _parse_named_token_clause(
        stripped, for_spell=False
    )


#: CR 702.175a's own second half, written out verbatim by `machines/
#: keywords._offspring_ability`: "create a token that's a copy of it, except
#: it's 1/1." Self-referential ("it" is the entering permanent, CR 607.1's
#: within-one-ability anaphora), not a target - the same reason
#: `_parse_regenerate_self_clause` above is ability-only.
_OFFSPRING_TOKEN_COPY_RE = re.compile(
    r"^create a token that'?s a copy of it, except it'?s 1/1\.?$", re.IGNORECASE
)


def _parse_offspring_token_copy_clause(clause: str) -> AbilityEffect | None:
    """`_OFFSPRING_TOKEN_COPY_RE`'s shape - CR 702.175a's own token, 1/1
    regardless of the original's printed power and toughness (CR 707.9a's
    "except" override, `token_copy_of`'s own `power=`/`toughness=`).
    """
    if _OFFSPRING_TOKEN_COPY_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            token_copy_of(game, source, ability.controller, power=1, toughness=1)

    return effect


#: "N" keyword abilities: CR 702.189a - "Firebending is a triggered ability.
#: 'Firebending N' means 'Whenever this creature attacks, add N {R}. Until end
#: of combat, you don't lose this mana as steps and phases end.'" The Legend
#: of Roku's `{8}` ability grants exactly this on the Dragon token it creates.
#: Recorded on the token as a plain keyword string - the same shape
#: `_TOKEN_KEYWORDS` already stores a bare keyword under - rather than as a
#: real triggered ability: nothing in `machines/triggers.py` fires it, so a
#: token with "Firebending 4" attacks without ever adding the mana. That gap
#: is left open rather than guessed at (`docs/engine-coverage.md`); what this
#: wave fixes is that the token itself, and its other keyword (flying), are
#: created at all, which used to fail the whole clause and create nothing.
#:
_LEVELED_TOKEN_KEYWORDS = {"firebending"}
#: "Toxic N" (CR 702.164a) is the other kind: `machines/combat.
#: total_toxic_value` counts it off a computed rules line (CR 702.164b), so
#: `_parse_token_tail` keeps the bare name in `keywords` and prints "Toxic N"
#: as the token's own first rules line.
_COUNTED_TOKEN_KEYWORDS = {"toxic"}


#: The opening/closing quote characters a token's own quoted ability can be
#: wrapped in (straight or curly, double or single - `_parse_token_tail`'s
#: own docstring explains why both levels are read). Matched non-greedily on
#: the opening side so a straight apostrophe *inside* the quoted ability's
#: own text - Wrenn and Seven's own "This token's power and toughness ..." -
#: is never mistaken for the mark that opens it: the real opening quote is
#: always the first quote-shaped character in the tail, before any the
#: ability's own sentence carries internally.
_TOKEN_TAIL_QUOTE_RE = re.compile(r"""^(?P<pre>.*?)["“'‘](?P<text>.+)["”'’]$""", re.DOTALL)
#: The join word/punctuation a keyword list leaves in front of a quoted
#: ability that follows it - "reach and " (Wrenn and Seven's own -3), "with
#: flying, " - stripped off before the keyword half is split on its own.
_TOKEN_TAIL_KEYWORD_JOIN_RE = re.compile(r"(?:,?\s+and\s*|,\s*)$", re.IGNORECASE)


#: One double-quoted ability of a token's tail. The "and"/comma between two of
#: them is the only thing `_several_quoted_abilities` lets sit between.
_TOKEN_TAIL_DOUBLE_QUOTED_RE = re.compile(r"[\"“](?P<text>[^\"”]+)[\"”]")
_TOKEN_TAIL_QUOTE_GAP_RE = re.compile(r"^\s*(?:,\s*(?:and\s+)?|and\s+)?$", re.IGNORECASE)


def _several_quoted_abilities(tail: str) -> tuple[str, str] | None:
    """`(keyword_part, rules_text)` for a tail carrying two or more double-quoted
    abilities - Relic Robber's "with "This token can't block" and "At the
    beginning of your upkeep, this token deals 1 damage to you."" - each quoted
    ability a rules line of its own (CR 111.3: a token has whatever abilities
    its creating effect gives it), or `None` for one quote or none (the
    single-quote readers handle those) and for anything but join words between
    and after them."""
    spans = list(_TOKEN_TAIL_DOUBLE_QUOTED_RE.finditer(tail))
    if len(spans) < 2:
        return None
    for left, right in zip(spans, spans[1:], strict=False):
        if not _TOKEN_TAIL_QUOTE_GAP_RE.fullmatch(tail[left.end() : right.start()]):
            return None
    if tail[spans[-1].end() :].strip():
        return None
    keyword_part = _TOKEN_TAIL_KEYWORD_JOIN_RE.sub("", tail[: spans[0].start()]).strip()
    lines = [span.group("text").strip() for span in spans]
    # The oracle prints the first of two quoted sentences with no full stop
    # inside its quotes ("This token can't block"); each is a sentence of its
    # own once it is a rules line, and the restriction readers need the stop.
    return keyword_part, "\n".join(line if line[-1] in ".!?" else line + "." for line in lines)


def _parse_token_tail(tail: str | None) -> tuple[tuple[str, ...], str | None] | None:
    """The "with <...>" part of a token's noun phrase, or `None` if this wave
    cannot read it.

    Three shapes, in order of how much of the tail they cover:

    - A single quoted ability and nothing else, printed on the token as its
      `rules_text` exactly as the card prints it - Drowner of Truth's "with
      \"Sacrifice this token: Add {C}.\"" - CR 111.3 makes that quoted
      sentence the token's stated text and this is a faithful transcription
      of it, not a hand-written ability. The quote mark itself may be either
      a straight or curly double quote (Drowner's own printing) *or* a
      straight or curly single quote - Urza's Saga chapter II's own "Create
      a 0/0 colorless Construct artifact creature token with 'This token
      gets +1/+1 for each artifact you control.'" is a token ability nested
      one quoting level *inside* the whole chapter's own double-quoted grant
      (CR 113.10a), so its own tail is printed with single quotes to avoid a
      double quote inside a double quote - the identical convention
      Scryfall's own oracle text uses everywhere else in the game (double at
      the outer level, single one level deeper).
    - A comma/"and"-joined list of bare keywords from `_TOKEN_KEYWORDS` and
      nothing else - Spectral Procession's "with flying", Wurmcoil Engine's
      "with deathtouch"/"with lifelink".
    - Both together, keywords first - Wrenn and Seven's own -3, "reach and
      \"This token's power and toughness are each equal to the number of
      lands you control.\"" CR 111.3's "any number of characteristics" is
      not only one ability at a time, and a real printing combines them the
      same way a permanent's own printed text does (a keyword line beside a
      sentence).

    Nothing else is read: a tail that mixes a keyword with something that is
    neither another keyword nor a quoted ability (Hangarback Walker's "with
    flying for each +1/+1 counter on this creature") returns `None` and
    takes the whole token clause with it.

    No tail at all - most of the pool's plain vanilla tokens - is the empty
    case, returned as `((), None)` rather than `None`, since "no tail" is a
    fully read clause and not a refusal.
    """
    if tail is None:
        return (), None
    tail = tail.strip()
    quoted_text: str | None = None
    keyword_part = tail
    if (several := _several_quoted_abilities(tail)) is not None:
        keyword_part, quoted_text = several
    elif quoted := _TOKEN_TAIL_QUOTE_RE.match(tail):
        # A quoted ability followed by ", where X is ..." is printed with the
        # comma inside the quote (Vren's `"This token gets +1/+1 for each other
        # Rat you control,"`): that comma stands for the sentence's full stop.
        quoted_text = quoted.group("text")
        if quoted_text.endswith(","):
            quoted_text = quoted_text[:-1] + "."
        keyword_part = _TOKEN_TAIL_KEYWORD_JOIN_RE.sub("", quoted.group("pre")).strip()
    if not keyword_part:
        return (), quoted_text
    parts = [
        part.strip()
        for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", keyword_part)
        if part.strip()
    ]
    if not parts:
        return (), quoted_text
    keywords: list[str] = []
    counted_lines: list[str] = []
    for part in parts:
        lowered = part.lower()
        if lowered in _TOKEN_KEYWORDS:
            keywords.append(part.title())
            continue
        if re.fullmatch(r"protection from (?:white|blue|black|red|green)", lowered):
            # CR 702.16a's protection from a colour - Hunted Horror's
            # Centaurs, "with protection from black".
            keywords.append(part[:1].upper() + part[1:].lower())
            continue
        leveled = re.fullmatch(r"(?P<word>[a-z]+) (?P<n>\d+)", lowered)
        if leveled is not None and leveled.group("word") in _COUNTED_TOKEN_KEYWORDS:
            # CR 702.164a: held the way a printing holds a parameterized
            # keyword (`TokenDefinition.keywords`' own docstring) - the bare
            # name in `keywords`, the full "Toxic 1" as a rules line, which is
            # what `combat.total_toxic_value` counts.
            keywords.append(leveled.group("word").title())
            counted_lines.append(f"{leveled.group('word').title()} {leveled.group('n')}")
            continue
        if leveled is not None and leveled.group("word") in _LEVELED_TOKEN_KEYWORDS:
            keywords.append(f"{leveled.group('word').title()} {leveled.group('n')}")
            continue
        return None
    rules_lines = [*counted_lines, *([quoted_text] if quoted_text is not None else [])]
    return tuple(keywords), "\n".join(rules_lines) or None


#: A bare non-creature type word ending a token's noun phrase with no
#: "creature" at all - Weapons Manufacturing's own "a colorless **artifact**
#: token named Munitions" (Munitions is never a creature). CR 205.2a's other
#: types, for the shapes the pool's quoted-ability tokens actually use;
#: "creature" itself is handled by the branch above this one and is not
#: repeated here.
_BARE_TOKEN_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "battle": Type.BATTLE,
}


def _parse_generic_token_descriptor(words: list[str], tail: str | None) -> TokenDefinition | None:
    """ "[P/T] [color(s)] subtype(s) [artifact] creature", or "[color(s)]
    <bare type>" with no subtype at all, as a `TokenDefinition`.

    Read right to left, the way the type line itself is built: "creature" -
    CR 205.2a - names the last word, an optional "artifact" ahead of it adds
    CR 205.2a's other type (Wurmcoil Engine's Wurms, Hangarback Walker's
    Thopters), an optional leading `P/T` sets power and toughness (CR 208.1),
    then zero or more colour words - or the explicit "colorless" CR 105.2
    calls out - and whatever capitalized words are left are the token's
    subtypes (CR 205.3, CR 111.4).

    A descriptor that does not end in "creature" is read the same way but
    against `_BARE_TOKEN_TYPE_WORDS` instead - Munitions' own "a colorless
    artifact token" has no subtype at all (its name is stated separately, by
    `_TOKEN_CLAUSE_RE`'s own "named" group, not derived from one), so this
    shape is the one place `words` being empty is not a refusal. A creature
    token still needs at least one subtype left over once the rest is
    stripped away, exactly as before - CR 111.4 derives an unnamed token's
    name from its subtypes, and a creature token naming none would be
    guessing at a shape nothing in the pool prints.
    """
    if not words:
        return None
    types: tuple[Type, ...]
    if words[-1].lower() == "creature":
        words = words[:-1]
        types = (Type.CREATURE,)
        if words and words[-1].lower() == "artifact":
            types = (Type.ARTIFACT, Type.CREATURE)
            words = words[:-1]
        elif words and words[-1].lower() == "land":
            # "land creature" - Verdant Kraken's Forest Tentacle, Awaken the
            # Woods' Forest Dryad. CR 305.6 grants the basic-land mana ability
            # intrinsically off the token's own "Forest" subtype below, so no
            # quoted tail is needed for that half of it to work.
            types = (Type.LAND, Type.CREATURE)
            words = words[:-1]
    elif words[-1].lower() in _BARE_TOKEN_TYPE_WORDS:
        types = (_BARE_TOKEN_TYPE_WORDS[words[-1].lower()],)
        words = words[:-1]
    else:
        return None
    supertypes: tuple[Supertype, ...] = ()
    if words and words[0].lower() == "legendary":
        # CR 205.4a's supertype, printed ahead of the P/T the same way it is
        # on a real card's own type line - Jiang Yanggu, Never Alone's "a
        # legendary 3/3 green Dog creature token" (Mowu), off-set Drizzt
        # Do'Urden's "a legendary 4/1 green Cat creature token" (Guenhwyvar).
        supertypes = (Supertype.LEGENDARY,)
        words = words[1:]
    power = toughness = None
    if words and re.fullmatch(r"\d+/\d+", words[0]):
        power_text, toughness_text = words[0].split("/")
        power, toughness = int(power_text), int(toughness_text)
        words = words[1:]
    colors: list[Color] = []
    while words and words[0].lower() in (*_TOKEN_COLOR_WORDS, "and"):
        if words[0].lower() != "and":
            colors.append(_TOKEN_COLOR_WORDS[words[0].lower()])
        words = words[1:]
    if words and words[0].lower() == "colorless":
        words = words[1:]
    if Type.CREATURE in types and not words:
        return None
    if words and not all(word[:1].isupper() for word in words):
        return None
    read_tail = _parse_token_tail(tail)
    if read_tail is None:
        return None
    keywords, rules_text = read_tail
    return TokenDefinition(
        types=types,
        subtypes=tuple(words),
        supertypes=supertypes,
        colors=tuple(colors),
        power=power,
        toughness=toughness,
        keywords=keywords,
        rules_text=rules_text,
    )


#: "Create X `<desc>` tokens[ with `<tail>`], where X is `<expr>`." - The
#: Mycotyrant's own "create X 1/1 black Fungus creature tokens with 'This
#: token can't block,' where X is the number of times you descended this
#: turn." `<expr>` is read through the shared `amount_expression` (the same
#: reader `_OBJECT_CHARACTERISTIC_RE`'s power/toughness terms and CR 700.11's
#: descend count both feed `_amount_term` through), so this generalises to
#: any magnitude that reader can already answer - devotion, a count of a type
#: you control, twice X, and so on - not only a descend count. The narrower
#: `_CREATE_TOKENS_WHERE_X_IS_THAT_SPELLS_MANA_VALUE_RE` above stays separate:
#: "that spell's mana value" needs CR 400.7's anaphora back to a *specific*
#: countered spell from a preceding clause, which `amount_expression` has no
#: term for.
_CREATE_X_TOKENS_WHERE_X_IS_RE = re.compile(
    r"^create x (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?"
    r",?\s*where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s28")
def _parse_create_x_tokens_where_x_is_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_X_TOKENS_WHERE_X_IS_RE`'s shape.

    CR 107.1b: a magnitude that reads negative is zero instead
    (`amount_expression`'s own docstring), so no tokens are created rather
    than a negative count reaching `create_tokens`.
    """
    match = _CREATE_X_TOKENS_WHERE_X_IS_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    words = match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None
    magnitude = amount_expression(match.group("expr"))
    if magnitude is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        count = magnitude(game, ability.controller, source, ability.x_value)
        if count > 0:
            create_tokens(game, definition, ability.controller, count, tapped=tapped)

    return effect


#: "create that many `<desc>` tokens[ with `<tail>`]." - Namor the Sub-
#: Mariner's own "Whenever you cast a noncreature spell with one or more
#: blue mana symbols in its mana cost, create that many 1/1 blue Merfolk
#: creature tokens." "That many" here is not `that_many()`'s own count
#: channel (a *preceding* counted instruction in the same ability) - it is
#: the trigger's own condition, "one or more `<color>` mana symbols in its
#: mana cost", counted off the cast spell CR 400.7 anaphora names
#: (`GameEvent.subject_card`).
_CREATE_THAT_MANY_COLOR_PIP_TOKENS_RE = re.compile(
    r"^create that many (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@MIXED_CLAUSE.rung("s10", for_spell=FORWARD)
def _parse_create_that_many_color_pip_tokens_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CREATE_THAT_MANY_COLOR_PIP_TOKENS_RE`'s shape, or `None`.

    Ability-only: `TriggeredAbility.condition`/`GameEvent.subject_card` are
    both a triggered ability's own attributes.
    """
    if for_spell:
        return None
    match = _CREATE_THAT_MANY_COLOR_PIP_TOKENS_RE.fullmatch(text.strip())
    if match is None:
        return None
    words = match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        count = color_pip_count_named_by_trigger(stack_object)
        if count:
            create_tokens(game, definition, stack_object.controller, count, tapped=tapped)

    return effect


#: "that player creates a 0/1 colorless Goblin Construct artifact creature
#: token with "This token can't block" and "At the beginning of your upkeep,
#: this token deals 1 damage to you."" (Relic Robber), "that player creates a
#: Blood token" (Bloodvial Purveyor) - CR 111.2: the player who creates a token
#: is its owner and controller, and here that is the player the trigger's own
#: event is about (CR 603.2: the one who took the combat damage, cast the
#: spell), not the ability's controller. The creation itself is read exactly
#: as "create ..." is; it just runs as the event player, so a quoted "you" in
#: the token's own ability is that player's too (CR 109.5).
_THAT_PLAYER_CREATES_RE = re.compile(
    r"^that player creates (?P<rest>.+)$", re.IGNORECASE | re.DOTALL
)

#: Words that, outside a quoted ability, would be read relative to the player
#: the creation is run as - "if you control a Vampire", "where X is your ..."
#: - while they mean the ability's own controller. Those sentences are refused
#: rather than read for the wrong player.
_CREATOR_RELATIVE_WORD_RE = re.compile(
    r"\b(?:if|unless|you|your|where|for each|equal|as long as|that many|that much)\b",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_that_player_creates_clause(text: str) -> AbilityEffect | None:
    """`_THAT_PLAYER_CREATES_RE`'s shape, or `None`."""
    whole = " ".join(_strip_non_effect_preamble(text).split())
    if not whole.lower().startswith("that player creates "):
        return None
    match = _THAT_PLAYER_CREATES_RE.fullmatch(whole)
    if match is None:
        return None
    rest = match.group("rest")
    if _CREATOR_RELATIVE_WORD_RE.search(_QUOTED_SPAN_RE.sub("", rest)):
        return None
    created = parse_mixed_effect(f"create {rest}") or _ability_effect_or_notice(
        f"you create {rest}"
    )
    if created is None or getattr(created, "__name__", "").endswith("notice_only"):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        event = ability.event
        if event is None or event.player is None:
            return
        created(game, ability.model_copy(update={"controller": event.player}))

    return effect


def _token_creation_clause(
    definition: TokenDefinition, count: int, *, tapped: bool, attacking: bool = False
) -> TargetedClause:
    """ "Create [count] [definition]" (CR 701.7a), as a `TargetedClause`.

    The creating player is CR 111.2's owner and controller - whoever controls
    the resolving spell or ability - so this reads `game.controller_of` the
    same way every other clause in this dispatcher does.

    `attacking` is "tapped and attacking" (CR 508.4): the tokens enter
    attacking whatever the creating ability's own source is attacking, or
    else whatever the controller's attack already names, and with neither
    they simply enter tapped. They were never declared as attackers
    (CR 508.4: "never 'attacked'"), which `create_tokens(attacking=...)` already guarantees.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        defender = _attack_target_of_source(game, stack_object, controller) if attacking else None
        create_tokens(game, definition, controller, count, tapped=tapped, attacking=defender)

    return effect


def _attack_target_of_source(
    game: "Game", stack_object: "StackObject", controller: str
) -> object | None:
    """What the resolving ability's own source is attacking (CR 508.4: a
    permanent put onto the battlefield attacking is attacking the player or
    planeswalker its creator names - here the same one the source attacks),
    falling back to whatever the controller's attack already names when the
    source is no longer attacking."""
    source_id = getattr(stack_object, "source_id", None)
    attack = game.combat.attack_by(source_id) if source_id is not None else None
    if attack is not None:
        return attack.defender
    return _defender_of_controllers_attack(game, controller)


def _token_definition_from_words(desc: str, tail: str | None) -> TokenDefinition | None:
    """A token descriptor ("2/2 black Zombie creature", "Treasure") as a
    definition, the same reading `_parse_token_clause` gives it."""
    words = desc.strip().split()
    predefined = " ".join(words)
    if tail is None and predefined in PREDEFINED:
        return PREDEFINED[predefined]
    return _parse_generic_token_descriptor(words, tail)


#: The literal "X/X" placeholder in a token's printed power/toughness,
#: substituted once the size is known (CR 608.2h: determined only once, when
#: the effect is applied). Narrower than `_X_TOKEN_RE` in
#: `_parse_where_x_is_continuous_effect` on purpose - this reads only the
#: token-descriptor shape, not any standalone X in a sentence.
_X_OVER_X_RE = re.compile(r"\bx/x\b", re.IGNORECASE)


#: A token clause's own trailing " for each `<count>`" - unquoted, so a
#: granted ability's quoted "for each" inside a token's tail is never read as
#: the creation count.
_TOKEN_FOR_EACH_TAIL_RE = re.compile(r"\s+for each (?P<each>[^.\"“”]+?)\.?$", re.IGNORECASE)


#: "create a `<desc>` token[ with ...]" - the one-token clause a "for each"
#: tail multiplies, re-read with the count spelled out by `_counted_token_clause`.
_ONE_TOKEN_CLAUSE_RE = re.compile(
    r"^(?P<lead>(?:you )?create) an? (?P<desc>.+?) token(?P<tail>(?:\s.*)?)$",
    re.IGNORECASE | re.DOTALL,
)


def _counted_token_clause(
    clause: str, *, for_spell: bool
) -> Callable[[int], TargetedClause | None]:
    """`clause` (one token) read again as "create `<n>` ... tokens": CR 701.7a
    creates the whole count in one event, so a CR 701.7b replacement that
    watches the event (Stridehangar Automaton's "those tokens plus an
    additional Thopter") applies once, not once per token. `None` for a count
    no token reader takes, so the caller falls back to one event per token."""
    match = _ONE_TOKEN_CLAUSE_RE.match(clause.strip())

    def counted(count: int) -> TargetedClause | None:
        if match is None:
            return None
        return _parse_token_clause(
            f"{match['lead']} {count} {match['desc']} tokens{match['tail']}", for_spell=for_spell
        )

    return counted


def create_for_each(
    game: "Game",
    stack_object: "StackObject",
    template: TargetedClause,
    counted: Callable[[int], TargetedClause | None] | None,
    times: int,
) -> None:
    """`times` of `template`'s token (CR 107.1b: none for zero or less), the
    count taken once before any is created (CR 608.2h) and, when `counted`
    reads it, created in one event (CR 701.7a)."""
    if times <= 0:
        return
    whole = counted(times) if counted is not None and times > 1 else None
    if whole is not None:
        whole(game, stack_object)
        return
    for _ in range(times):
        template(game, stack_object)


def _token_clause_for_each_of_source(
    template: TargetedClause,
    multiplier: Callable[["Game", str, str | None], int],
    counted: Callable[[int], TargetedClause | None] | None = None,
) -> TargetedClause:
    """`_token_clause_for_each` for a count that reads the resolving object
    (`amounts._for_each_multiplier`'s `(game, controller, source_id)` form)."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        times = multiplier(
            game, game.controller_of(stack_object).username, source_id_of(stack_object)
        )
        create_for_each(game, stack_object, template, counted, times)

    return effect


def _token_clause_for_each(
    template: TargetedClause,
    multiplier: Callable[["Game", str], int],
    counted: Callable[[int], TargetedClause | None] | None = None,
) -> TargetedClause:
    """Run `template` once per unit `multiplier` counts, the count taken once
    before any token is created (CR 608.2h) - as one event when `counted`
    reads the count (`create_for_each`)."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        times = multiplier(game, game.controller_of(stack_object).username)
        create_for_each(game, stack_object, template, counted, times)

    return effect


#: ecl-T8: whether `reminder` is the kind of CR 111.4 "the token's whole
#: definition lives in its own reminder text" parenthetical
#: `_parse_create_named_permanent_token_clause` reads, rather than an
#: ordinary CR 207.2a reminder that only restates a rule read elsewhere
#: (every other trigger's own reminder text is dropped before dispatch, and
#: stays dropped) - shared by `Game._etb_x_effect_text` (a real resolution)
#: and `support.py` (the static sweep), so both put the same text back for
#: the identical shape rather than drifting apart.
_NAMED_TOKEN_REMINDER_RE = re.compile(r"^\(it'?s an? [a-z]+ with ", re.IGNORECASE)
#: The bare name off "create a [tapped] `<Name>` token." - used only to
#: check it against `PREDEFINED` before deciding whether to reattach a
#: reminder; a fuller read of the same shape belongs to
#: `_CREATE_NAMED_PERMANENT_TOKEN_RE` alone.
_CREATE_TOKEN_BARE_NAME_RE = re.compile(
    r"create an? (?:tapped )?(?P<name>[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*) tokens?\.?$",
    re.IGNORECASE,
)


def effect_text_with_named_token_reminder(
    effect_text: str | None, reminder: str | None
) -> str | None:
    """`effect_text`, with `reminder` appended back on when the pair looks
    like Mutable Explorer's own "create a tapped Mutavault token. (It's a
    land with "..." and "...")." - see `_NAMED_TOKEN_REMINDER_RE`'s banner.

    Never for a CR 111.10 predefined token (Food, Treasure, Mutagen, ...):
    Generous Ent's own "create a Food token. (It's an artifact with '{2},
    {T}, Sacrifice this token: You gain 3 life.')" carries the identical
    "It's a[n] `<type>` with" reminder shape, but "Food" already has a real
    row in `PREDEFINED` - reattaching its reminder would hand it to this
    file's *named*-token reader instead, which builds a fresh definition
    named literally "Food" rather than CR 111.4's own derived "Food Token".
    """
    stripped = (effect_text or "").strip()
    name_match = _CREATE_TOKEN_BARE_NAME_RE.search(stripped)
    if name_match is not None and name_match.group("name") in PREDEFINED:
        return effect_text
    if (
        effect_text
        and re.search(r"\btokens?\.?$", stripped, re.IGNORECASE)
        and reminder
        and _NAMED_TOKEN_REMINDER_RE.match(reminder.strip())
    ):
        return f"{stripped} {reminder.strip()}"
    return effect_text


#: ecl-T8: "Create a tapped `<Name>` token. (It's a[n] `<type>` with
#: "`<ability>`"[ and "`<ability>`"].)" - Mutable Explorer's own "create a
#: tapped Mutavault token. (It's a land with "{T}: Add {C}" and "{1}: This
#: token becomes a 2/2 creature with all creature types until end of turn.
#: It's still a land.")" CR 111.4: "a spell or ability that creates a token
#: sets both its name and its subtype(s)" - here the reminder text spells the
#: whole definition out itself, so this reads it structurally (any name, any
#: one of CR 205.2a's card types, any number of quoted abilities) rather than
#: keying off "Mutavault" or any other specific name - a card-name-to-
#: characteristics row is exactly what `CLAUDE.md` bans. The reminder
#: parenthetical's own inner ability can itself carry a period inside its
#: quotes ("... until end of turn. It's still a land."), which is why this
#: is read as one DOTALL span rather than split sentence by sentence.
_CREATE_NAMED_PERMANENT_TOKEN_RE = re.compile(
    r"""^create an? (?P<tapped>tapped )?(?P<name>[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*)*) token\.\s*"""
    r"""[(](?:it'?s|its) an? (?P<typeword>land|artifact|creature) with (?P<abilities>.+)[)]$""",
    re.IGNORECASE | re.DOTALL,
)
_QUOTED_ABILITY_SPAN_RE = re.compile(r"""["“]([^"”]+)["”]""")

_NAMED_TOKEN_TYPE_WORDS: dict[str, Type] = {
    "land": Type.LAND,
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
}


@ABILITY_TEXT.rung("s7")
def _parse_create_named_permanent_token_clause(text: str) -> TargetedClause | None:
    """`_CREATE_NAMED_PERMANENT_TOKEN_RE`'s shape - see the banner above.

    No power/toughness is read off the reminder text at all: a land or
    artifact token like this has none until its own granted ability (already
    captured verbatim in `rules_text`, parsed the ordinary way any printed
    permanent's abilities are) turns it into a creature.
    """
    match = _CREATE_NAMED_PERMANENT_TOKEN_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    name = match.group("name").strip()
    card_type = _NAMED_TOKEN_TYPE_WORDS.get(match.group("typeword").lower())
    if card_type is None:
        return None
    abilities = _QUOTED_ABILITY_SPAN_RE.findall(match.group("abilities"))
    if not abilities:
        return None
    tapped = match.group("tapped") is not None
    definition = TokenDefinition(
        types=(card_type,),
        name=name,
        rules_text="\n".join(line.strip() for line in abilities),
    )
    return _token_creation_clause(definition, 1, tapped=tapped)


#: "create two 1/1 Gnome tokens that are tapped and attacking" - the relative
#: clause form of the "tapped and attacking" the descriptor reader below takes
#: in front of the token's description (CR 508.4).
_TOKENS_THAT_ARE_TAPPED_AND_ATTACKING_RE = re.compile(
    r"^(?P<head>creates? (?:an? |\d+ |x |[a-z]+ )?)(?P<desc>.+?) (?P<noun>tokens?) "
    r"that(?:'s| is| are) tapped and attacking$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s10", for_spell=FORWARD)
def _parse_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of "create ... token(s)" (CR 701.7a), read off the card's
    own printed text - see the section banner above for what this reads and
    what it refuses.
    """
    clause = clause.strip()
    if "tapped and attacking" in clause:
        clause = _TOKENS_THAT_ARE_TAPPED_AND_ATTACKING_RE.sub(
            r"\g<head>tapped and attacking \g<desc> \g<noun>", clause
        )

    if match := _YOU_MAY_RE.match(clause):
        inner_text = match.group("clause").strip()
        inner = _parse_token_clause(inner_text, for_spell=for_spell)
        if inner is None:
            return None
        return _optional_targeted_clause(inner, inner_text, for_spell=for_spell)

    if "copy of" in clause.lower():
        return None  # CR 707.2 copying needs copiable values this wave does not read.

    # "Create a tapped X/X black Zombie Horror creature token, where X is
    # twice the number of cards exiled this way." (Corpseweft): CR 107.3c's
    # X, defined by the text, read once as the ability resolves (CR 608.2h)
    # through `amount_expression`, and written into the token's power and
    # toughness (CR 208.1).
    where_x = _WHERE_X_IS_INLINE_RE.search(clause)
    if where_x is not None and where_x.end() >= len(clause.rstrip(".")):
        size_reader = amount_expression(where_x.group("expr"))
        sized = clause[: where_x.start()].strip()
        if size_reader is None or not _X_OVER_X_RE.search(sized):
            return None
        template = _parse_token_clause(_X_OVER_X_RE.sub("0/0", sized), for_spell=for_spell)
        if template is None:
            return None
        return _x_sized_token_clause(_X_OVER_X_RE.sub("0/0", sized), size_reader)

    # "Create a Food token for each creature you control." (The Battle of
    # Bywater): CR 608.2c's multiplier, the count read once as the clause is
    # applied (CR 608.2h) through the same `count_expression` a damage
    # clause's "for each" tail uses - so it sees the board as an earlier
    # instruction of the same spell left it.
    for_each = _TOKEN_FOR_EACH_TAIL_RE.search(clause)
    if for_each is not None:
        each_phrase = for_each.group("each")
        template = _parse_token_clause(clause[: for_each.start()], for_spell=for_spell)
        if template is None:
            return None
        counted = _counted_token_clause(clause[: for_each.start()], for_spell=for_spell)
        multiplier = count_expression(each_phrase)
        if multiplier is not None:
            return _token_clause_for_each(template, multiplier, counted)
        # "create a Mutagen token for each +1/+1 counter on it" (The Ooze) -
        # not a board-wide `count_expression` at all: "it" is the *other*
        # object this trigger's own condition named (CR 603.10a's look-back),
        # read off the resolving ability's own `event` rather than off the
        # controller's battlefield.
        event_subject_multiplier = token_riders.event_subject_counter_multiplier(each_phrase)
        if event_subject_multiplier is not None:
            return token_riders.token_clause_for_each_event_subject_counter(
                template, event_subject_multiplier, counted
            )
        # "create a Treasure token for each creature that crewed it this turn"
        # (Luxurious Locomotive): a count read off the ability's own source.
        source_multiplier = _for_each_multiplier(each_phrase)
        if source_multiplier is not None:
            return _token_clause_for_each_of_source(template, source_multiplier, counted)
        return None

    match = _TOKEN_CLAUSE_RE.fullmatch(clause)
    if match is None:
        return None
    count = parse_count(match.group("n"))
    words = match.group("desc").strip().split()
    tail = match.group("tail")
    name = match.group("name")

    attacking = False
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
        if [word.lower() for word in words[:2]] == ["and", "attacking"]:
            # "create a tapped and attacking 1/1 ... token" (CR 508.4).
            attacking, words = True, words[2:]
    if not words:
        return None
    tapped = tapped or attacking

    predefined_name = " ".join(words)
    if tail is None and name is None and predefined_name in PREDEFINED:
        return _token_creation_clause(
            PREDEFINED[predefined_name], count, tapped=tapped, attacking=attacking
        )

    definition = _parse_generic_token_descriptor(words, tail)
    if definition is None:
        return None
    if name is not None:
        # CR 111.4: "a spell or ability that creates a token sets both its
        # name and its subtype(s) ... if the spell or ability doesn't specify
        # the name of the token, its name is the same as its subtype(s)".
        # Weapons Manufacturing's Munitions states one, so it overrides
        # whatever `card_name` would otherwise derive.
        definition = definition.model_copy(update={"name": name.strip()})
    return _token_creation_clause(definition, count, tapped=tapped, attacking=attacking)


#: "create `<Name>`, a[n] `<descriptor>` token[s]" (CR 111.9) - the name-first
#: twin of `_TOKEN_CLAUSE_RE`'s own trailing "named `<Name>`": Jiang Yanggu,
#: Never Alone's "create Mowu, a legendary 3/3 green Dog creature token", the
#: model's own worked example, Boo's "create Boo, a legendary 1/1 red
#: Hamster creature token" (`TokenDefinition.name`'s own docstring), and the
#: real, off-set printing Drizzt Do'Urden's "create Guenhwyvar, a legendary
#: 4/1 green Cat creature token with trample". Always exactly one token
#: (CR 111.9 never prints a count ahead of a name), so this reads no
#: `{COUNT}` group at all - a card creating several distinctly-named tokens
#: in one sentence is outside this shape.
_NAMED_TOKEN_CLAUSE_RE = re.compile(
    r"^create (?P<name>[^,]+), an? (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_named_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_NAMED_TOKEN_CLAUSE_RE`'s shape; see the banner above.

    `for_spell` is accepted only for symmetry with every other clause parser
    in `_parse_mixed_clause`'s chain - CR 111.9 naming applies equally to a
    spell and an ability, and nothing here reads the resolving object beyond
    its controller.
    """
    match = _NAMED_TOKEN_CLAUSE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if "copy of" in clause.lower():
        return None  # CR 707.2 copying needs copiable values this wave does not read.
    name = match.group("name").strip()
    if not name or name[:1].islower():
        return None  # a real CR 111.9 name is a proper noun, capitalized.
    words = match.group("desc").strip().split()
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None
    definition = definition.model_copy(update={"name": name})
    return _token_creation_clause(definition, 1, tapped=False)


# --------------------------------------------------------------------------
# Token creation (wave 4): lists of different tokens, and a following-sentence
# grant
# --------------------------------------------------------------------------
#
# Two templates every token parser above misses, both CR 111.3 ("The spell or
# ability that creates a token may define the values of any number of
# characteristics for the token"):
#
# - one "create" naming a *list* of different tokens - "Create a 2/1 white and
#   black Inkling creature token with flying, a 3/2 red and white Spirit
#   creature token, and a 4/4 blue and red Elemental creature token." (Mascot
#   Exhibition, Bestial Menace, Trostani's Summoner). `_CLAUSE_SEPARATOR` only
#   cuts on the final "and", so the first piece reaches `_parse_token_clause`
#   with a second token glued onto the first one's "with" tail and nothing is
#   created at all.
# - a token's quoted ability printed as the *next* sentence - "Create a 1/1
#   colorless Eldrazi Scion creature token. It has "Sacrifice this token: Add
#   {C}."" (Warping Wail, Blisterpod, Spawning Breath). CR 608.2c: "later text
#   on the card may modify the meaning of earlier text" - the "It has" sentence
#   is part of the token's definition, identical in meaning to the "token with
#   "<ability>"" shape `_parse_token_tail` already reads, not an instruction of
#   its own.

#: The following-sentence grant: a token noun phrase ending its sentence, then
#: "It has"/"They have"/"Those tokens have" and one quoted ability (straight or
#: curly double quotes). `head` keeps the token noun and any "with <keywords>"
#: tail already printed on it, so the quoted ability can be folded in beside
#: them.
#:
#: Vile Redeemer's own cast trigger prints a "for each `<count>`" multiplier
#: (CR 608.2c) *before* the sentence break: "create a 1/1 ... token for each
#: nontoken creature that died under your control this turn. Those tokens
#: have "..."." - `each` captures that tail separately from `tail`'s "with
#: `<keywords>`" so `fold` can put it back *after* the folded-in quoted
#: ability, where `_TOKEN_FOR_EACH_TAIL_RE`'s own `$`-anchored search
#: (`_parse_token_clause`) still finds it at the true end of the rewritten
#: sentence.
_TOKEN_FOLLOWING_GRANT_RE = re.compile(
    r"(?P<noun>\btokens?\b)(?:\s+with\s+(?P<tail>[^.\"“”]+?))?"
    r"(?:\s+for each\s+(?P<each>[^.\"“”]+?))?\.\s+"
    r"(?:it has|they have|those tokens have|each of them has)\s+"
    r"(?P<quoted>[\"“][^\"“”]+[\"”])\.?",
    re.IGNORECASE,
)


def _fold_following_token_grant(text: str) -> str:
    """`text` with every "... token. It has "<ability>"" rewritten to the
    single-sentence "... token with "<ability>"" CR 608.2c says it means, so
    every token reader (`_parse_token_clause`, `_parse_target_player_token_
    mode`, the list reader below) sees the ability on the token it belongs to.

    A token that already carries a "with <keywords>" tail keeps it, the quoted
    ability joined after an "and" - the "reach and "<ability>"" shape
    `_parse_token_tail` already reads (Wrenn and Seven). A "for each `<count>`"
    multiplier printed ahead of the sentence break is kept too, moved after the
    folded-in ability so it stays the rewritten sentence's own trailing clause
    (see the banner above). Text without the shape comes back unchanged.
    """

    def fold(match: re.Match[str]) -> str:
        tail = match.group("tail")
        each = match.group("each")
        with_part = f"{tail.strip()} and " if tail else ""
        each_suffix = f" for each {each.strip()}" if each else ""
        return f"{match.group('noun')} with {with_part}{match.group('quoted')}{each_suffix}"

    return _TOKEN_FOLLOWING_GRANT_RE.sub(fold, text)


#: Where one item of a token list ends and the next begins: a comma (the
#: serial "and" optional) or a bare "and", followed by the next item's own
#: count word (CR 701.7a's "the specified number of tokens"). A colour pair's
#: "white and black" and a keyword list's "flying and vigilance" never have a
#: count word after the "and", so neither is a boundary.
_TOKEN_LIST_BOUNDARY_RE = re.compile(
    rf",\s+(?:and\s+)?(?={COUNT}\s)|\s+and\s+(?={COUNT}\s)", re.IGNORECASE
)


def _parse_token_list_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Create <item>, <item>, and <item>." - one CR 701.7a instruction naming
    several different tokens, each item read by `_parse_token_clause` on its
    own so its "with" tail (CR 111.3) stays on that item alone.

    Read only when the whole text is that one sentence and every item is a
    token `_parse_token_clause` reads; anything else returns `None` and falls
    through to the ordinary per-clause path, so one unreadable item fails the
    whole instruction closed rather than creating part of the list.
    """
    stripped = _fold_following_token_grant(_strip_non_effect_preamble(text).strip()).rstrip(".")
    if not re.match(r"^(?:you )?create\s", stripped, re.IGNORECASE):
        return None
    if _has_period_outside_quotes(stripped):
        return None
    quoted: list[str] = []

    def mask(match: re.Match[str]) -> str:
        quoted.append(match.group(0))
        return f"\x00{len(quoted) - 1}\x00"

    masked = _QUOTED_SPAN_RE.sub(mask, stripped)
    items = _TOKEN_LIST_BOUNDARY_RE.split(masked)
    if len(items) < 2:
        return None
    clauses: list[TargetedClause] = []
    for item in items:
        restored = re.sub(r"\x00(\d+)\x00", lambda m: quoted[int(m.group(1))], item.strip())
        clause = _parse_token_clause(restored, for_spell=for_spell)
        if clause is None:
            return None
        clauses.append(clause)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for clause in clauses:
            clause(game, stack_object)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


# --------------------------------------------------------------------------
# Modal spells (CR 700.2): one chosen mode's own effect
# --------------------------------------------------------------------------
#
# Every parser above reads a whole card's or ability's text, on the working
# assumption that whoever controls it is the one doing everything in it -
# "you" for a player clause, the resolving spell's own controller for a
# targeted or token clause. That assumption breaks for a mode printed with a
# *player* as its own grammatical subject: Kozilek's Command's "Target player
# creates X ... tokens ..." and "Target player scries X, then draws a card."
# are not the caster's own actions at all - they belong to whichever player
# was targeted, who is very often an opponent. Nothing above reads that
# shape, so it gets its own two parsers here, tried before the ordinary
# per-clause dispatcher (`parse_mixed_effect_for_spell`) that already reads
# every mode with no player-subject of its own - Abrade's "Destroy target
# artifact.", Thraben Charm's "Destroy target enchantment.", Mystic
# Confluence's "Return target creature to its owner's hand." and "Draw a
# card.", and Kozilek's Command's own "Exile target creature with mana value
# X or less." and "Exile up to X target cards from graveyards.".

#: "Target player creates N <token descriptor> tokens[ with <tail>]." - the
#: token twin of `_TOKEN_CLAUSE_RE`, with the count and the tail read exactly
#: the same way (`_parse_generic_token_descriptor`/`_parse_token_tail`, quoted
#: granted ability included), but the *creator* is whichever player this mode
#: targets, not the caster (CR 111.2's owner-and-controller is decided by who
#: creates the token, and CR 700.2 puts that choice on the sentence's own
#: subject). `creates?` reads both "creates" (third person, as printed here)
#: and a hypothetical "create".
_TARGET_PLAYER_TOKEN_RE = re.compile(
    rf"^target player creates? (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b"
    rf"(?:\s+with\s+(?P<tail>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_target_player_token_mode(text: str) -> Effect | None:
    """Kozilek's Command's mode 1: "Target player creates X 0/1 colorless
    Eldrazi Spawn creature tokens with "Sacrifice this token: Add {C}.""

    X has already been substituted by the time this is called
    (`substitute_x`, not `mode_rules_text` - the quoted granted ability has to
    survive, which `mode_rules_text`'s quote-blanking would not let it), so
    "creates X ..." arrives as "creates 1 ...", a plain `COUNT` the same
    `_parse_generic_token_descriptor`/`_parse_token_tail` already read for
    every other token-creating card - CR 111.3's "This becomes the token's
    'text'" applies exactly the same to a token a target player creates as to
    one the caster creates.

    The descriptor goes through `_token_definition_from_words`, so a
    predefined token named by its bare name reads too - Prismari Command's
    "Target player creates a Treasure token." (CR 111.10a), Ashling's
    Command's "creates two Treasure tokens" - and a leading "tapped" is the
    same rider `_parse_token_clause` reads (Verdant Command's "creates two
    tapped 1/1 green Squirrel creature tokens"). CR 111.2 makes the targeted
    player the owner and controller either way.
    """
    match = _TARGET_PLAYER_TOKEN_RE.fullmatch(_fold_following_token_grant(text.strip()))
    if match is None:
        return None
    if "copy of" in text.lower():
        return None  # CR 707.2 copying needs copiable values this wave does not read.
    count = parse_count(match.group("n"))
    words = match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    tail = match.group("tail")
    if tail is not None:
        # `_TARGET_PLAYER_TOKEN_RE`'s own `tail` group is DOTALL-greedy to
        # the end of the (already sentence-split) mode text, so a tail with
        # no further sentence after it - Atlantis Attacks' own "... token
        # with hexproof." - keeps the sentence's closing full stop, which
        # `_token_definition_from_words` (built for `_parse_token_clause`'s
        # own already-stripped tail) does not expect and refuses. Stripped
        # here the same way `_parse_token_clause` starts from `text.strip()`
        # with no trailing punctuation of its own to begin with.
        tail = tail.strip().rstrip(".").strip() or None
    definition = _token_definition_from_words(" ".join(words), tail)
    if definition is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                create_tokens(game, definition, target.username, count, tapped=tapped)

    return effect


#: Grist, the Hunger Tide's `+1`, read whole: "Create a 1/1 black and green
#: Insect creature token, then mill a card. If an Insect card was milled this
#: way, put a loyalty counter on this permanent and repeat this process." -
#: the token descriptor is read the same way `_parse_generic_token_descriptor`
#: reads any other, so only the mill-then-repeat half is templated here.
#: Grist's own name has already become "this permanent" by the time this
#: runs (`_self_normalized_effect_text`).
_CREATE_TOKEN_MILL_REPEAT_RE = re.compile(
    r"^create (?P<n>a|one) (?P<desc>.+?) tokens?, then mill a card\. "
    r"if an? (?P<kind>[a-z]+) card was milled this way, "
    r"put a loyalty counter on this permanent and repeat this process\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s32")
def _parse_create_token_mill_repeat_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_MILL_REPEAT_RE`'s shape - Grist, the Hunger Tide's `+1`.

    CR 118.4's own "repeat this process" reads here as an ordinary Python loop
    inside one resolution, not a second stack object (nothing in CR 603.12
    covers "repeat" the way it covers "when you do") - each pass creates one
    token, mills one card, and only continues if *that* card was the named
    subtype (CR 205.3, checked against the card's own `CardState.subtypes`,
    since a card in the graveyard carries no continuous effect to compute a
    layer 4 change from - but does carry a changeling CDA, CR 604.3). The
    loop terminates on its own: `_mill` mills nothing once the library is
    empty (CR 701.17a's "as many ... as possible"), which reads
    here as "no card was milled", never true to the "if" condition.
    """
    match = _CREATE_TOKEN_MILL_REPEAT_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    words = match.group("desc").strip().split()
    definition = _parse_generic_token_descriptor(words, None)
    if definition is None:
        return None
    kind_word = match.group("kind").strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        while True:
            create_tokens(game, definition, player.username, 1)
            milled = _mill(game, player, 1)
            # `CardState.subtypes`: the milled card's own CDA, changeling
            # included (CR 604.3), not just the type line.
            if not milled or kind_word.lower() not in {s.lower() for s in milled[0].subtypes}:
                return
            source = ability.source(game)
            if source is not None and source.zone is Zone.BATTLEFIELD:
                game.add_counters(source, Counter.LOYALTY, 1)

    return effect


#: "Create `<n>` `<descriptor>` tokens[ named `<Name>`]. [Then ]if this spell
#: was cast from a graveyard, put `<base>` `<kind>` counters on {that token|
#: each of them}[ for every `<divisor>` cards in your graveyard]." - Recursive
#: Recruitment's own "put a +1/+1 counter on each of them for every three
#: cards in your graveyard" and off-set Retrieve the Esper's "Then if this
#: spell was cast from a graveyard, put two +1/+1 counters on that token."
#: Read whole, ahead of the ordinary per-clause split - the sentence boundary
#: (a period) is one `_CLAUSE_SEPARATOR` would cut on too, and the second
#: sentence's "each of them"/"that token" refers back to the first sentence's
#: own tokens, which only a whole-text reader can carry forward.
_CREATE_TOKENS_GRAVEYARD_CAST_COUNTERS_RE = re.compile(
    rf"^create (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b(?:\s+named (?P<name>.+?))?\.\s*"
    r"(?:then\s+)?if this spell was cast from a graveyard,\s*"
    rf"put (?P<base>{COUNT}) (?P<kind>\+1/\+1|-1/-1) counters? on "
    r"(?:that token|each of them)"
    rf"(?:\s+for every (?P<divisor>{COUNT}) cards? in your graveyard)?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_create_tokens_graveyard_cast_counters_clause(text: str) -> Effect | None:
    """`_CREATE_TOKENS_GRAVEYARD_CAST_COUNTERS_RE`'s shape, or `None`.

    `Game.cast_record(spell).origin_zone` (CR 601.2, already recorded by
    `Game.note_cast` for every keyword-cast case, flashback's own exile
    included) is CR 608.2c's "this spell" - the resolving object itself, not
    the target of anything - so no target-resolution step is needed the way
    the copy-token shapes above need one. `<base>` counters "for every
    `<divisor>` cards in your graveyard" is CR 107.1's plain integer
    division: one `<base>`-sized helping per whole `<divisor>` cards, applied
    identically to every token the first sentence created, the same way
    Recursive Recruitment's own plural "each of them" reads. No divisor tail
    at all is Retrieve the Esper's own flat count instead.
    """
    match = _CREATE_TOKENS_GRAVEYARD_CAST_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    if "copy of" in text.lower():
        return None
    count = parse_count(match.group("n"))
    words = match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    predefined_name = " ".join(words)
    name = match.group("name")
    if name is None and predefined_name in PREDEFINED:
        definition = PREDEFINED[predefined_name]
    else:
        definition = _parse_generic_token_descriptor(words, None)
        if definition is None:
            return None
        if name is not None:
            definition = definition.model_copy(update={"name": name.strip()})

    kind = _counter_kind(match.group("kind"))
    base = parse_count(match.group("base"))
    divisor_text = match.group("divisor")
    divisor = parse_count(divisor_text) if divisor_text is not None else None
    if divisor_text is not None and not divisor:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        created = create_tokens(game, definition, controller, count, tapped=tapped)
        if not created:
            return
        if game.cast_record(spell).origin_zone is not Zone.GRAVEYARD:
            return
        if divisor is not None:
            graveyard_count = len(game.player(controller).graveyard)
            amount = base * (graveyard_count // divisor)
        else:
            amount = base
        if amount <= 0:
            return
        for token in created:
            game.add_counters(token, kind, amount)

    return effect


#: "Create `<n>` `<descriptor>` tokens[ named `<Name>`], then put `<base>`
#: `<kind>` counters on each other `<subtype>`[ token(s)] you control." -
#: Command the Stage's own "Create a 2/2 colorless Wizard Soldier creature
#: token named Cadet, then put a +1/+1 counter on each other Wizard token you
#: control." "Other" here means other than the token(s) this same sentence
#: just created (CR 608.2c's own instructions in order) - a different
#: referent from `_parse_put_counters_on_group_clause`'s own "other", which
#: excludes an *ability's* source and has no created-tokens list to exclude
#: instead. Read whole, ahead of the per-clause split: the ", then " join is
#: exactly what `_CLAUSE_SEPARATOR` cuts on, which would otherwise strand the
#: second half with no "it"/"they" left to say what was just made.
_CREATE_TOKENS_THEN_COUNTER_OTHER_SUBTYPE_RE = re.compile(
    rf"^create (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b(?:\s+named (?P<name>.+?))?,\s*then\s+"
    rf"put (?P<base>{COUNT}) (?P<kind>\+1/\+1|-1/-1) counters? on each other "
    r"(?P<subtype>[A-Za-z]+)(?:\s+tokens?)? you control\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_create_tokens_then_counter_other_subtype_clause(text: str) -> Effect | None:
    """`_CREATE_TOKENS_THEN_COUNTER_OTHER_SUBTYPE_RE`'s shape, or `None`.

    `<subtype>` is read off the **computed** board (CR 613.5), the same
    convention `_parse_put_counters_on_group_clause` already uses for its own
    "each `<group>` you control".
    """
    match = _CREATE_TOKENS_THEN_COUNTER_OTHER_SUBTYPE_RE.fullmatch(text.strip())
    if match is None:
        return None
    if "copy of" in text.lower():
        return None
    count = parse_count(match.group("n"))
    words = match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    predefined_name = " ".join(words)
    name = match.group("name")
    if name is None and predefined_name in PREDEFINED:
        definition = PREDEFINED[predefined_name]
    else:
        definition = _parse_generic_token_descriptor(words, None)
        if definition is None:
            return None
        if name is not None:
            definition = definition.model_copy(update={"name": name.strip()})

    kind = _counter_kind(match.group("kind"))
    base = parse_count(match.group("base"))
    subtype = match.group("subtype").lower()

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        created = create_tokens(game, definition, controller, count, tapped=tapped)
        created_ids = {token.id for token in created}
        board = game.computed_board()
        for permanent in game.battlefield:
            if permanent.id in created_ids:
                continue
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if subtype not in (word.lower() for word in chars.subtypes):
                continue
            game.add_counters(permanent, kind, base)

    return effect


#: Fractal Anomaly: "Create a 0/0 green and blue Fractal creature token and
#: put X +1/+1 counters on it, where X is the number of cards you've drawn
#: this turn." One sentence joining the token-creation and counter-count
#: templates `_parse_token_clause`/`count_expression` already read
#: separately with "and" rather than the usual sentence break - generalised
#: over both (any token description, any `count_expression` phrase), not
#: fixed to a Fractal or to "cards you've drawn this turn": a future card
#: sharing this exact "create ... and put X ..., where X is ..." shape with
#: a different token or a different count is covered for free.
_TOKEN_AND_PUT_X_COUNTERS_RE = re.compile(
    r"^(?P<token_clause>create .+? tokens?) and put x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? "
    r"on it,\s*where x is (?P<expr>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_fractal_token_by_cards_drawn_this_turn_clause(effect_text: str) -> Effect | None:
    """`_TOKEN_AND_PUT_X_COUNTERS_RE`'s shape, or `None`."""
    match = _TOKEN_AND_PUT_X_COUNTERS_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    counted = count_expression(match.group("expr"))
    if counted is None:
        return None
    token_effect = _parse_token_clause(match.group("token_clause").strip(), for_spell=True)
    if token_effect is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        amount = counted(game, controller.username)
        before_ids = {existing.id for existing in game.battlefield}
        token_effect(game, spell)
        if amount <= 0:
            return
        created = [state for state in game.battlefield if state.id not in before_ids]
        for token in created:
            game.add_counters(token, kind, amount)

    return effect


#: Antiquities on the Loose: "Create two 2/2 red and white Spirit creature
#: tokens. Then if this spell was cast from anywhere other than your hand,
#: put a +1/+1 counter on each Spirit you control." `CastRecord.origin_zone`
#: (CR 601.2a) already carries exactly this fact - Rebound's own "cast from
#: your hand" read the same field the other way - so no new cast-zone
#: tracking is needed, only a reader of the existing one. Otterball Antics'
#: own printing of the identical rider - "Create a 1/1 blue and red Otter
#: creature token with prowess. If this spell was cast from anywhere other
#: than your hand, put a +1/+1 counter on that creature." - proves this
#: generalises to the *other* shape a card prints it in: a plural "each
#: `<subtype>` you control" naming a whole board-wide group, or a singular
#: "that creature"/"it" naming only the just-created token(s) (the same
#: before/after id-diff `_parse_token_then_object_anaphor_clause_pair`
#: already uses for its own single-sentence-pair rider). Generalised over
#: the created token's own description and the counter kind/amount, not
#: fixed to a Spirit or an Otter.
_TOKENS_THEN_COUNTER_IF_NOT_CAST_FROM_HAND_RE = re.compile(
    r"^(?P<token_clause>create [^.]+)\.\s*(?:then )?"
    r"if this spell was cast from anywhere other than your hand,\s*"
    r"put (?P<amount>a|an|\d+|[a-z]+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?:each (?P<subtype>[a-z]+) you control|(?:that creature|it))\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_tokens_then_counter_if_not_cast_from_hand_clause(effect_text: str) -> Effect | None:
    """`_TOKENS_THEN_COUNTER_IF_NOT_CAST_FROM_HAND_RE`'s shape, or `None`.

    Otterball Antics' own reminder text for prowess (CR 207.2) sits inline,
    right after this ability's own two sentences and before its Flashback
    line - `strip_reminder_text` drops it the same way `_parse_oracle_text`
    already does per paragraph, since this whole-text matcher never goes
    through that reader itself.
    """
    rules_text, _reminder = strip_reminder_text(effect_text.strip())
    match = _TOKENS_THEN_COUNTER_IF_NOT_CAST_FROM_HAND_RE.fullmatch(rules_text.strip())
    if match is None:
        return None
    token_effect = _parse_token_clause(match.group("token_clause").strip(), for_spell=True)
    if token_effect is None:
        return None
    amount = parse_count(match.group("amount"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))
    wanted_subtype = (
        canonical_subtype(match.group("subtype")) if match.group("subtype") is not None else None
    )
    if match.group("subtype") is not None and wanted_subtype is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        before_ids = {existing.id for existing in game.battlefield}
        token_effect(game, spell)
        record = game.cast_record(spell)
        if record.origin_zone is Zone.HAND and not record.is_copy:
            return
        if wanted_subtype is None:
            for token in game.battlefield:
                if token.id not in before_ids:
                    game.add_counters(token, kind, amount)
            return
        controller = game.controller_of(spell).username
        board = game.computed_board()
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if chars.controller != controller:
                continue
            if wanted_subtype not in {word.lower() for word in chars.subtypes}:
                continue
            game.add_counters(permanent, kind, amount)

    return effect


#: CR 111.10j-r: "Create a(n) <Role> Role token attached to <X>." - one shape
#: shared by every CR 111.10 Role (Monster, Cursed, Royal, Sorcerer, Virtuous,
#: Wicked, Young Hero), read off the printed sentence rather than by card
#: name. `X` is either an object anaphor (Monstrous Rage's "attached to it",
#: referring back to a target an earlier clause of the same spell already
#: established) or this clause's own "target ..." phrase (Spiteful Hexmage's
#: "attached to target creature you control") - `_OBJECT_ANAPHOR` above and
#: the ordinary "target" grammar `_targets_understood` already vets are both
#: already-built vocabularies, not new ones.
_CREATE_ROLE_TOKEN_RE = re.compile(
    rf"create an? (?P<role>[A-Za-z][A-Za-z ]*?) role token attached to "
    rf"(?P<phrase>{_OBJECT_ANAPHOR}|(?:up to one )?(?:other )?target .+)",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_create_role_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Create a(n) <Role> Role token attached to <X>." (CR 111.10j-r).

    Not entered by card name: `models/token.PREDEFINED` carries every CR
    111.10 Role's own text (each an Aura enchantment token, CR 303.7a), and
    this only has to find the target the Role attaches to - CR 701.3a's
    "never spends a moment unattached" is what `create_tokens`'s own
    `attached_to=` already guarantees, so CR 704.5m has nothing to do the
    instant the token arrives.

    Both the anaphoric shape (a pump clause targets first; this clause's "it"
    is that same target) and the self-targeting shape (this clause is the
    whole ability and names its own "target creature you control") resolve
    through `game.resolve_targets(stack_object)` - CR 601.2c/603.3c settle a
    spell's or ability's targets once, before any of its clauses run, so it
    does not matter which clause's own words put the target requirement on
    the stack object.
    """
    match = _CREATE_ROLE_TOKEN_RE.fullmatch(clause.strip())
    if match is None:
        return None
    definition = PREDEFINED.get(match.group("role").strip().title())
    if definition is None or definition.subtypes != ("Aura", "Role"):
        return None
    phrase = match.group("phrase").strip()
    if not _OBJECT_ANAPHOR_RE.fullmatch(phrase) and not _targets_understood(
        phrase, count_agnostic=True
    ):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                create_tokens(game, definition, controller, attached_to=target)

    return effect


#: "create a(n) `<Role>` Role token attached to up to one target `<...>`" as a
#: whole sentence - the optional-target Role of Cut In, Shatter the Oath,
#: Eriette's Whisper, Witch's Mark. `_CREATE_ROLE_TOKEN_RE` reads the clause;
#: this only recognises that the sentence is one, so `_parse_sentence_then_role_
#: on_up_to_one_target_clauses` can tell it apart from a sentence that merely
#: mentions a Role.
_ROLE_ON_UP_TO_ONE_TARGET_SENTENCE_RE = re.compile(
    r"^create an? [A-Za-z][A-Za-z ]*? role token attached to up to one (?:other )?target .+$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_sentence_then_role_on_up_to_one_target_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`<sentence with its own targets>. Create a `<Role>` Role token attached to
    up to one target `<...>`." (CR 303.7, CR 111.10) - Cut In's "deals 4 damage
    to target creature", Shatter the Oath's "Destroy target creature or
    enchantment", Eriette's Whisper's "Target opponent discards two cards".

    Both sentences use the word "target", so CR 601.2c puts every target on
    the one stack object in the order the text names them, and
    `Game.resolve_targets` hands each clause the *whole* list - the damage
    would also land on the Role's creature and the Role would also attach to
    the damaged one. The first sentence's requirements are all mandatory and
    fixed-size (an "up to"/variable one would make the split ambiguous), so
    its targets are exactly the first `n` of `stack_object.targets` and the
    Role's are the rest. Splitting the *references* rather than the resolved
    objects keeps CR 608.2b honest: a first target that has become illegal
    stays in its own slot and is simply not affected, it does not shift the
    Role's target into its place. Zero targets for the "up to one" half is a
    legal announcement (CR 115.6) and then no Role is created.
    """
    if "role token" not in text.lower():
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if len(sentences) != 2:
        return None
    first, second = sentences
    second = second.strip().rstrip(".")
    if _ROLE_ON_UP_TO_ONE_TARGET_SENTENCE_RE.fullmatch(second) is None:
        return None
    role_clause = _parse_create_role_token_clause(second, for_spell=for_spell)
    first_clauses = _parse_mixed_clauses(first, for_spell=for_spell)
    if role_clause is None or first_clauses is None:
        return None
    profile_reader = spell_profile_for_text if for_spell else profile_for_text
    requirements = profile_reader(first).requirements
    if any(r.unbounded or r.variable_count or r.minimum != r.count for r in requirements):
        return None
    first_target_count = sum(requirement.count for requirement in requirements)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = list(stack_object.targets)
        first_object = stack_object.model_copy(update={"targets": targets[:first_target_count]})
        role_object = stack_object.model_copy(update={"targets": targets[first_target_count:]})
        for clause in first_clauses:
            clause(game, first_object)
            game.announce_batched_events()  # CR 603.2c: one event per instruction
        role_clause(game, role_object)

    return [effect]


#: A token sentence whose "with" tail ends in `and "<quoted ability>"` - the
#: keyword(s) and the quoted ability are one tail (CR 111.3), Awaken the Blood
#: Avatar's "3/6 black and red Avatar creature token with haste and "Whenever
#: this token attacks, ...", Into the Fae Court's "Faerie creature token with
#: flying and "This token can block only creatures with flying."".
_TOKEN_WITH_KEYWORDS_AND_QUOTED_ABILITY_RE = re.compile(
    r"^(?:you )?create .*?\btokens?\b[^\"\u201c]*?\s+with\s+[^\"\u201c]*?\band\s+[\"\u201c]",
    re.IGNORECASE | re.DOTALL,
)

#: A token sentence that carries a quoted ability after its "with" (any
#: shape: a bare quote, keywords and a quote), or that is "tapped and
#: attacking": `split_effect_clauses` masks the quote but a trailing `."`
#: never ends a sentence for `_plain_resolution_sentences`, and the bare " and
#: " of a keyword list is still a clause boundary, so these are read whole.
_TOKEN_SENTENCE_RE = re.compile(
    r"^(?:you )?create\b.*?\btokens?\b(?!.*\bcopy of\b)",
    re.IGNORECASE | re.DOTALL,
)

#: Where one sentence of a token paragraph ends and the next begins, outside
#: any quotation: `_plain_resolution_sentences`'s own boundary applied to the
#: text with every quoted span masked, so a quoted ability's own closing `."`
#: never hides the sentence break behind it ("... any target." They gain
#: haste ...).
_QUOTE_AWARE_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?\x01])\s+(?=[A-Z])|\n+")
_QUOTE_ENDS_A_SENTENCE_RE = re.compile(r"[.!?][\"\u201d']$")


def _quote_aware_sentences(text: str) -> list[str]:
    """`text` split into sentences with every quoted ability kept inside the
    sentence it belongs to (CR 111.3: a token's quoted ability is that
    token's own text, never an instruction of the outer spell)."""
    quoted: list[str] = []

    def mask(match: re.Match[str]) -> str:
        quoted.append(match.group(0))
        mark = "\x01" if _QUOTE_ENDS_A_SENTENCE_RE.search(match.group(0)) else "\x00"
        return f"{mark}{len(quoted) - 1}{mark}"

    masked = _QUOTED_SPAN_RE.sub(mask, text)
    return [
        re.sub(r"[\x00\x01](\d+)[\x00\x01]", lambda m: quoted[int(m.group(1))], part).strip()
        for part in _QUOTE_AWARE_SENTENCE_BOUNDARY_RE.split(masked)
        if part.strip()
    ]


#: "with `<...>` and ..." in the unquoted part of a token sentence: the bare
#: " and " of a keyword list, which `split_effect_clauses` cuts through. A
#: colour pair ("blue and red") has no "with" in front of it.
_TOKEN_WITH_AND_LIST_RE = re.compile(r"\bwith\b[^\"\u201c]*\band\b", re.IGNORECASE)


def _token_sentence_needs_whole_reading(sentence: str, *, has_riders: bool) -> bool:
    """Whether the sentence is one the clause splitter would cut wrongly (a
    keyword list ending in a quoted ability, an "and"-joined keyword list,
    "tapped and attacking") or one an anaphoric rider follows - the only
    token sentences this reads, so every ordinary token clause keeps its
    existing path."""
    if _TOKEN_SENTENCE_RE.match(sentence) is None:
        return False
    return (
        has_riders
        or _TOKEN_WITH_KEYWORDS_AND_QUOTED_ABILITY_RE.match(sentence) is not None
        or _TOKEN_WITH_AND_LIST_RE.search(sentence) is not None
        or "tapped and attacking" in sentence.lower()
    )


def apply_token_riders(
    game: "Game",
    stack_object: "StackObject",
    created: list[CardState],
    grants: list[tuple[list[str], str | None]],
    delayed: list[Any],
    *,
    for_spell: bool,
) -> None:
    """Every anaphoric rider that follows a token sentence, applied to exactly
    the permanents it put onto the battlefield (CR 608.2c: "They"/"It" is the
    token(s) just created).

    `grants` are CR 613.1f layer-6 keyword grants and `delayed` are CR 603.7a
    delayed triggered abilities about those objects, in the order printed.
    Nothing is created when no token was (CR 101.3).
    """
    if not created:
        return
    controller = game.controller_of(stack_object).username
    source_id, source_name = _permanent_id_and_name(stack_object, for_spell=for_spell)
    for keywords, duration in grants:
        for permanent in created:
            _grant_keywords_to(
                game,
                permanent,
                keywords,
                duration,
                controller=controller,
                source_name=source_name,
            )
    for clause in delayed:
        triggers = clause.triggers_for_all(
            created,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            game=game,
        )
        for trigger in triggers or []:
            game.create_delayed_trigger(trigger)


def _token_rider_clause(
    token_clause: TargetedClause,
    grants: list[tuple[list[str], str | None]],
    delayed: list[Any],
    *,
    for_spell: bool,
) -> TargetedClause:
    """`token_clause`, then every anaphoric rider the sentences after it
    carried (`apply_token_riders`), applied to the permanents it created
    (CR 400.7: a before/after diff on the zone-change stamp names them,
    whatever the descriptor)."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        before = {(state.id, state.zone_change_stamp) for state in game.battlefield}
        token_clause(game, stack_object)
        created = [
            state for state in game.battlefield if (state.id, state.zone_change_stamp) not in before
        ]
        apply_token_riders(game, stack_object, created, grants, delayed, for_spell=for_spell)

    return effect


def _read_token_rider(
    sentence: str,
) -> tuple[str, Any] | None:
    """One rider sentence as ("grant", (keywords, duration)) or ("delayed",
    the anaphoric delayed clause), or `None` when it is neither. Plural and
    singular pronouns are checked by the delayed clause itself against the
    number of tokens that exist when it runs."""
    body = sentence.strip().rstrip(".")
    grant = _ANAPHOR_GAINS_KEYWORDS_RE.fullmatch(body)
    if grant is not None:
        keywords = split_and_validate_keywords(grant.group("keywords"))
        if keywords is None:
            return None
        return "grant", (list(keywords), (grant.group("duration") or "").lower() or None)
    delayed = parse_anaphoric_delayed_clause(sentence)
    if delayed is not None and not delayed.self_referential:
        return "delayed", delayed
    return None


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_token_with_keywords_and_quoted_ability_sentences(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """Every sentence of `text`, with each token sentence the clause splitter
    would cut wrongly read whole and every other sentence through the ordinary
    clause pipeline; `None` when no sentence has that shape, or any sentence
    fails to read (CR 608.2c has no notion of running half an instruction).

    `split_effect_clauses` masks the quoted span but still cuts the sentence at
    the bare " and " in front of it, so "... token with haste" and a lone
    quotation came out as two clauses and neither read - every "token with
    `<keyword>` and "`<ability>`"" card was silent; the same cut turned
    "token with trample and haste" (Purphoros's Intervention, Elemental
    Appeal) into "with trample" and an unreadable "haste". The token reader
    (`_parse_token_clause`) already reads the whole sentence correctly, so
    this only hands it the sentence the splitter should not have cut.

    The sentences right after a token sentence that name its tokens
    anaphorically are read with it, as one CR 608.2c instruction: "They gain
    haste until end of turn." (Burn Down the House) and "Sacrifice it at the
    beginning of the next end step." / "Exile it ..." (Purphoros's
    Intervention, a CR 603.7a delayed trigger about that token alone). Both
    are read by the same machinery `_parse_put_then_grant_then_delayed_whole_
    text` uses for any other antecedent; this only lets the antecedent carry
    a quoted ability, which that reader's own quote stash refuses.
    """
    lowered = text.lower()
    if "token" not in lowered or not (
        '"' in text
        or "\u201c" in text
        or " and " in lowered
        or "tapped and attacking" in lowered
        or "gain" in lowered
        or " it at " in lowered
    ):
        return None
    sentences = _quote_aware_sentences(_strip_non_effect_preamble(text))
    # First pass: which sentences are token sentences read whole, and which
    # rider sentences each one takes. Nothing to read whole means this is not
    # the rung's shape (and the ordinary pipeline below must not be re-entered
    # with the same text).
    plan: list[tuple[str, list[tuple[str, Any]] | None]] = []
    index = 0
    while index < len(sentences):
        riders: list[tuple[str, Any]] = []
        following = index + 1
        while (
            following < len(sentences)
            and (rider := _read_token_rider(sentences[following])) is not None
        ):
            riders.append(rider)
            following += 1
        if _token_sentence_needs_whole_reading(sentences[index], has_riders=bool(riders)):
            plan.append((sentences[index], riders))
            index = following
        else:
            plan.append((sentences[index], None))
            index += 1
    if all(riders is None for _, riders in plan):
        return None
    clauses: list[TargetedClause] = []
    for sentence, riders in plan:
        if riders is None:
            parsed = _parse_mixed_clauses(sentence, for_spell=for_spell)
            if parsed is None:
                return None
            clauses.extend(parsed)
            continue
        token_clause = _parse_token_clause(
            sentence.strip().rstrip("."), for_spell=for_spell
        ) or _parse_create_copies_of_self_attacking_clause(
            sentence.strip().rstrip("."), for_spell=for_spell
        )
        if token_clause is None:
            return None
        if riders:
            token_clause = _token_rider_clause(
                token_clause,
                [value for kind, value in riders if kind == "grant"],
                [value for kind, value in riders if kind == "delayed"],
                for_spell=for_spell,
            )
        clauses.append(token_clause)
    return clauses


def _parse_token_then_object_anaphor_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Create `<token(s)>`. It/They `<rider>`." - Stingerquill Charm's own
    "Create a 2/2 colorless Wizard Soldier creature token named Cadet. It
    gains haste until end of turn."

    `_parse_object_anaphor_clause_pair`'s own `_referent_reader` cannot serve
    this antecedent: it reads the referent *before* the antecedent runs
    (that function's own docstring explains why, CR 608.2h), and a token
    this clause is about to create does not exist yet to read. This instead
    runs the token-creation clause first and keeps exactly what it put onto
    the battlefield (CR 701.7a) - a before/after id diff on `game.
    battlefield` rather than re-deriving "the token(s) just created" from any
    printed description, so it works for every token shape `_parse_token_
    clause` already reads (a full characteristics list, a predefined token,
    a copy) with no new vocabulary of its own.
    """
    if not _OBJECT_ANAPHOR_RE.search(second):
        return None
    token_clause = _parse_token_clause(first, for_spell=for_spell)
    if token_clause is None:
        return None
    rider = _parse_referent_object_clause(second)
    if rider is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        before_ids = {existing.id for existing in game.battlefield}
        token_clause(game, stack_object)
        created = [state for state in game.battlefield if state.id not in before_ids]
        if not created:
            return
        rider(game, created, stack_object)

    return effect


#: "Create a `<token>`. Then if you control `<n>` or more `<subtype>`s,
#: sacrifice this Saga. If you do, create a `<token>`." - The Misty Mountains
#: Cold's own chapter effect (CR 714.4's chapter ability), printed identically
#: on chapters I through IV rather than escalating - only the reader for this
#: text belongs here; the lore-counter machinery that fires this ability once
#: per chapter (CR 714.2c/714.2d) is a shared, pre-existing part of the
#: engine. CR 608.2c's plain sequential instructions, the same "Then if ..."
#: shape `_parse_each_sacrifices_then_if_you_did_clause` reads elsewhere for
#: a different antecedent - here the first instruction (a token creation) has
#: nothing to do with whether the second one (the threshold check) holds, so
#: it always runs, and the sacrifice-and-consequence pair is CR 118.12's own
#: "[do], if you do, [effect]" gated on the count already being met rather
#: than on a choice.
_CREATE_TOKEN_THEN_IF_CONTROL_N_SACRIFICE_SELF_THEN_RE = re.compile(
    r"^(?P<first_token>create an? .+?\btokens?\b(?:\s+with\s+.+?)?)\.\s*"
    r"then if you control (?P<n>[a-z0-9]+) or more (?P<subtype>[A-Za-z]+?)s?,\s*"
    r"sacrifice this (?P<noun>[a-z]+)\.\s*"
    r"if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_create_token_then_if_control_n_sacrifice_self_then_clause(
    text: str,
) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_IF_CONTROL_N_SACRIFICE_SELF_THEN_RE`'s shape.

    Ability-only: "this Saga" (CR 700.7) is the resolving ability's own
    source, which only a triggered ability - never a spell - has (CR 714's
    chapter abilities are always triggered abilities of a permanent). The
    count is read through the shared `count_expression("`<subtype>`s you
    control")` reader, the same one every other "the number of `<X>` you
    control" clause in this module already goes through, so a future card
    naming a different subtype or threshold reaches this the same way.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _CREATE_TOKEN_THEN_IF_CONTROL_N_SACRIFICE_SELF_THEN_RE.fullmatch(whole)
    if match is None:
        return None
    token_effect = parse_mixed_effect(match.group("first_token").strip() + ".")
    if token_effect is None:
        return None
    threshold = parse_count(match.group("n"))
    if threshold is None:
        return None
    count_reader = count_expression(f"{match.group('subtype')}s you control")
    if count_reader is None:
        return None
    consequence = parse_mixed_effect(match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        token_effect(game, ability)  # type: ignore[arg-type]
        controller = game.controller_of(ability).username
        if count_reader(game, controller) < threshold:
            return
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.sacrifice(source)
        if source.zone is Zone.BATTLEFIELD:
            return  # CR 118.12: the sacrifice did not happen after all.
        consequence(game, ability)  # type: ignore[arg-type]

    return effect


#: "Create a `<token>`. Then if you control `<n>` or more `<subtype>`s, that
#: player loses half their life, rounded up." - Dark Leo & Shredder's own
#: combat-damage trigger. The same CR 608.2c "Then if ..." shape
#: `_CREATE_TOKEN_THEN_IF_CONTROL_N_SACRIFICE_SELF_THEN_RE` just above reads,
#: with a different consequence: "that player" (CR 607.1's anaphora back to
#: whichever player the trigger's own `DEALS_DAMAGE` event named,
#: `AbilityOnStack.event.player` - the same subject `_parse_that_player_
#: clause` elsewhere in this module reads off the identical field) loses half
#: their own current life total (CR 119.1), rounded the way CR 107.1a's own
#: printed direction says (`numbers.parse_half`/`halve` - the same halving
#: primitive `_parse_half_life_loss_clause` above and `machines/replacement.
#: py`'s enters-with-counters position both already reuse).
_CREATE_TOKEN_THEN_IF_CONTROL_N_THAT_PLAYER_HALF_LIFE_RE = re.compile(
    r"^(?P<first_token>create an? .+?\btokens?\b(?:\s+with\s+.+?)?)\.\s*"
    r"then if you control (?P<n>[a-z0-9]+) or more (?P<subtype>[A-Za-z]+?)s?,\s*"
    r"that player loses half (?:their|his|her) life,\s*rounded (?P<direction>up|down)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_create_token_then_if_control_n_that_player_half_life_clause(
    text: str,
) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_IF_CONTROL_N_THAT_PLAYER_HALF_LIFE_RE`'s shape.

    Ability-only: `ability.event.player` (CR 607.1's anaphora referent) is an
    `AbilityOnStack`'s own attribute, the same restriction `_parse_that_
    player_clause` states for the identical field.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _CREATE_TOKEN_THEN_IF_CONTROL_N_THAT_PLAYER_HALF_LIFE_RE.fullmatch(whole)
    if match is None:
        return None
    token_effect = parse_mixed_effect(match.group("first_token").strip() + ".")
    if token_effect is None:
        return None
    threshold = parse_count(match.group("n"))
    if threshold is None:
        return None
    count_reader = count_expression(f"{match.group('subtype')}s you control")
    if count_reader is None:
        return None
    round_up = match.group("direction").lower() == "up"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        token_effect(game, ability)  # type: ignore[arg-type]
        controller = game.controller_of(ability).username
        if count_reader(game, controller) < threshold:
            return
        event = ability.event
        if event is None or event.player is None:
            return
        player = game.player(event.player)
        game.lose_life(player, halve(player.life, round_up=round_up))

    return effect


#: Cori-Steel Cutter's *Flurry* trigger: "create a 1/1 white Monk creature
#: token with prowess. You may attach this Equipment to it." CR 701.3a's
#: "attach" is the general action - "take it from where it currently is and
#: put it onto that object" - not one CR 702.6a's own Equip ability alone
#: performs, so a resolving ability naming the attach directly is this same
#: action reached a different way, offered as CR 608.2d's ordinary "you may"
#: once the token exists to be attached to. Written as one shape
#: ("...token[s]. You may attach this Equipment to it/them.") rather than
#: keyed to this one card's name, so any future Equipment printed the same
#: way reaches it too.
_CREATE_TOKEN_THEN_MAY_ATTACH_RE = re.compile(
    r"^(?P<action>create .+?)\.\s*"
    r"you may attach this (?:equipment|permanent) to (?:it|them)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_create_token_then_may_attach_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_MAY_ATTACH_RE`'s shape.

    The token is always created (CR 603.12's "instruct" half); only the
    attachment is optional (`DecisionKind.MAY`, CR 608.2d), asked once the
    token is real so a declined attachment leaves the Equipment right where
    it was. Only the single-token case is handled - the only shape the pool
    prints - since "it" has no well-defined referent once more than one token
    was created (CR 407.4's "it" is singular).
    """
    match = _CREATE_TOKEN_THEN_MAY_ATTACH_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    # No trailing period appended, unlike the reflexive-mandatory-token
    # sibling above: `_TOKEN_CLAUSE_RE`'s own `tail` group is greedy, so a
    # period handed to it becomes part of the tail ("prowess.") and
    # `_parse_token_tail` reads that as an unknown keyword - `split_effect_
    # clauses`'s `text.rstrip(".")` is what keeps every *other* caller of
    # this regex from ever presenting one.
    action_text = match.group("action").strip()
    token_match = _TOKEN_CLAUSE_RE.fullmatch(action_text)
    if token_match is None:
        return None
    count = parse_count(token_match.group("n"))
    if count != 1:
        return None
    words = token_match.group("desc").strip().split()
    tail = token_match.group("tail")
    if not words:
        return None
    predefined_name = " ".join(words)
    definition = (
        PREDEFINED[predefined_name]
        if tail is None and predefined_name in PREDEFINED
        else _parse_generic_token_descriptor(words, tail)
    )
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        created = create_tokens(game, definition, controller.username, count)
        if not created:
            return
        token = created[0]
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        decision = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=controller.username,
                prompt=f"attach {source.name} to {token.name}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=True,
            )
        )
        if decision:
            source.attach_to(token)

    return effect


#: "create `<token(s)>`, then attach this Equipment to it." (no "you may") -
#: Dwarven Shortsword's and Kyoshi Battle Fan's own ETB trigger.
#: `_CREATE_TOKEN_THEN_MAY_ATTACH_RE`'s own twin, mandatory rather than
#: CR 608.2d-optional: CR 701.3a's attach always happens once the token
#: exists, the identical "instruct" half `_CREATE_TOKEN_THEN_MAY_ATTACH_RE`'s
#: own docstring already reads for the token creation itself.
_CREATE_TOKEN_THEN_ATTACH_RE = re.compile(
    r"^(?P<action>create .+?), then attach this (?:equipment|permanent) to (?:it|them)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_create_token_then_attach_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_ATTACH_RE`'s shape - see the banner above.

    Read the identical way `_parse_create_token_then_may_attach_clause`
    already does (single-token only, `_TOKEN_CLAUSE_RE`'s own generic
    descriptor), the only difference being that the attach here is CR
    701.3a's unconditional "instruct", never a `Decision`.
    """
    match = _CREATE_TOKEN_THEN_ATTACH_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    action_text = match.group("action").strip()
    token_match = _TOKEN_CLAUSE_RE.fullmatch(action_text)
    if token_match is None:
        return None
    count = parse_count(token_match.group("n"))
    if count != 1:
        return None
    words = token_match.group("desc").strip().split()
    tail = token_match.group("tail")
    if not words:
        return None
    predefined_name = " ".join(words)
    definition = (
        PREDEFINED[predefined_name]
        if tail is None and predefined_name in PREDEFINED
        else _parse_generic_token_descriptor(words, tail)
    )
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        created = create_tokens(game, definition, controller.username, count)
        if not created:
            return
        token = created[0]
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        attach_permanent(game, source, token)

    return effect


#: "create a colorless Equipment artifact token named `<Name>` with
#: \"`<ability>`\" and equip `<cost>`[. When you do, attach it to target
#: creature you control.]" - Dain Ironfoot's and Iron Hills Blacksmith's own
#: ETB trigger, Blacksmith's Talent's identically-shaped Class-enters one.
#: `_TOKEN_CLAUSE_RE`'s own tail grammar (`_parse_token_tail`) reads a single
#: quoted ability, or bare keywords, or both together - never a quoted
#: ability *and* a full "and equip `{cost}`" activated-ability sentence
#: riding along after it, which is exactly this shape - so it is read here as
#: its own whole sentence instead of widening that shared reader for one
#: printed shape no other pool card needs.
#:
#: The token's own "Equip `<cost>`" line is put straight into its
#: `rules_text` beside the quoted ability, exactly as a real Equipment
#: printing carries both on separate lines - `parse_abilities`/`has_equip`
#: read a token's synthesised `Card.oracle_text` the same way they read any
#: other card's, so the token equips like any other Equipment with no extra
#: plumbing.
_NAMED_EQUIPMENT_TOKEN_RE = re.compile(
    r"^create a colorless equipment artifact token named "
    r"(?P<name>[A-Z][\w' -]*?) with "
    r"[\"“‘'](?P<ability>[^\"”’']+)[\"”’'] "
    r"and equip (?P<cost>(?:\{[^}]+\})+)\.?"
    r"(?P<attach> when you do, attach it to target creature you control\.?)?"
    # U.S.Agent, John Walker's "... and equip {2}. Attach it to U.S.Agent." -
    # the token attached to the ability's own source (CR 701.3a), no target.
    r"(?P<attach_self> attach it to this (?:creature|permanent)\.?)?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_named_equipment_token_clause(text: str) -> AbilityEffect | None:
    """`_NAMED_EQUIPMENT_TOKEN_RE`'s shape - see the banner above.

    The token is always created; the "When you do, attach it ..." tail, when
    printed, is CR 603.12's reflexive trigger, created only once the token is
    real (a `DecisionKind`-free, mandatory attach: CR 603.12's own "when [a
    player] does" needs no "may" here because nothing about creating the
    token was optional either).
    """
    match = _NAMED_EQUIPMENT_TOKEN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    name = match.group("name").strip()
    ability = match.group("ability").strip()
    cost = match.group("cost").strip()
    has_reflexive_attach = match.group("attach") is not None
    attaches_to_source = match.group("attach_self") is not None
    definition = TokenDefinition(
        types=(Type.ARTIFACT,),
        subtypes=("Equipment",),
        name=name,
        # The quoted ability is a whole sentence of the token's text (CR
        # 111.3); Oracle drops its full stop inside the "with "..." and equip"
        # list, and without it the static line is no sentence the layer
        # system reads - the bonus never applied.
        rules_text=f"{ability if ability.endswith('.') else ability + '.'}\nEquip {cost}",
    )

    def effect(game: "Game", ability_on_stack: AbilityOnStack) -> None:
        controller = game.controller_of(ability_on_stack)
        created = create_tokens(game, definition, controller.username, 1)
        if not created:
            return
        token = created[0]
        if attaches_to_source:
            source = ability_on_stack.source(game)
            if source is not None and source.zone is Zone.BATTLEFIELD:
                attach_permanent(game, token, source)
            return
        if not has_reflexive_attach:
            return
        reflexive_text = "When you do, attach it to target creature you control."
        game.create_reflexive_trigger(
            text=reflexive_text,
            controller=controller.username,
            source_id=ability_on_stack.source_id,
            source_name=ability_on_stack.source_name,
            subject_id=token.id,
            callback=ReflexiveAttachSubjectToTargetConsequence(),
        )

    return effect


#: "create `<token>`. When you do, return target `<card>` from your graveyard
#: to the battlefield, then attach it to that token." - Ratonhnhake:ton's
#: combat damage trigger: CR 603.12's mandatory ("instruct") action, then a
#: reflexive ability that returns a card and attaches it to the new token.
_TOKEN_THEN_REFLEXIVE_RETURN_ATTACH_RE = re.compile(
    r"^(?P<action>create .+? tokens?(?: with [^.]+)?)\.\s*when you do,\s*"
    r"(?P<consequence>return target .+? from your graveyard to the battlefield, "
    r"then attach it to that token)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_token_then_reflexive_return_and_attach_clause(text: str) -> AbilityEffect | None:
    """`_TOKEN_THEN_REFLEXIVE_RETURN_ATTACH_RE`'s shape. The token is always
    created; the reflexive ability exists only once it is real (CR 603.12)
    and carries the token as its subject for "that token"."""
    match = _TOKEN_THEN_REFLEXIVE_RETURN_ATTACH_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    token_match = _TOKEN_CLAUSE_RE.fullmatch(match.group("action").strip())
    if token_match is None:
        return None
    count = parse_count(token_match.group("n"))
    words = token_match.group("desc").strip().split()
    if not words or count is None:
        return None
    name = " ".join(words)
    tail = token_match.group("tail")
    definition = (
        PREDEFINED[name]
        if tail is None and name in PREDEFINED
        else _parse_generic_token_descriptor(words, tail)
    )
    if definition is None:
        return None
    reflexive_text = f"When you do, {match.group('consequence').strip()}."

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        created = create_tokens(game, definition, controller.username, count)
        if not created:
            return
        game.create_reflexive_trigger(
            text=reflexive_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=ability.source_name,
            subject_id=created[0].id,
            callback=ReflexiveReturnThenAttachToSubjectConsequence(),
        )

    return effect


# --------------------------------------------------------------------------
# Triggered abilities a resolving spell or ability creates for the turn
# --------------------------------------------------------------------------
#
# "Whenever `<condition>` this turn, `<effect>`" (First Day of Class, Beck,
# Rite of Harmony) and "Until end of turn, whenever `<condition>`,
# `<effect>`" (Dovin, Grand Arbiter's +1, Mistway Spy's face-up trigger).
# CR 603.7/603.7a: resolving the instruction creates a delayed triggered
# ability; CR 603.7b: "this turn"/"until end of turn" is a stated duration, so
# it fires on every matching event rather than once, and CR 514.2 ends it in
# the cleanup step.
#
# The created ability is rewritten as the printed trigger it reads as - the
# duration words off, nothing else changed - and handed to the same readers a
# printed trigger goes through: `machines/triggers.granted_triggered_
# abilities_of` for the condition (matched later by `condition_matches`) and
# `trigger_effect_for` for the effect. So the template is closed for every
# condition and effect a printed trigger already reads, and a created ability
# whose condition or effect is *not* read is refused here rather than created
# to do nothing.
#
# The other "this turn" delayed-trigger readers above (Dalkovan Encampment's,
# Lyra's, Summon: Good King Mog XII's, The Last Ronin's) stay ahead of this
# one in the dispatch chain; they carry riders ("that are tapped and
# attacking. Sacrifice them ...", "attacks alone") this reader does not.

_CREATED_TRIGGER_THIS_TURN_RE = re.compile(
    r"^whenever (?P<condition>[^,]+?) this turn,\s*(?P<effect>\S.*)$",
    re.IGNORECASE | re.DOTALL,
)
_CREATED_TRIGGER_UNTIL_END_OF_TURN_RE = re.compile(
    r"^until end of turn,\s*(?P<ability>whenever\s+\S.*)$", re.IGNORECASE | re.DOTALL
)


def created_trigger_line(paragraph: str) -> str | None:
    """The printed-trigger reading of a created "this turn" ability, or `None`
    when `paragraph` is not one of the two shapes above."""
    text = " ".join(paragraph.strip().split())
    this_turn = _CREATED_TRIGGER_THIS_TURN_RE.fullmatch(text)
    if this_turn is not None:
        return f"Whenever {this_turn.group('condition')}, {this_turn.group('effect')}"
    until_eot = _CREATED_TRIGGER_UNTIL_END_OF_TURN_RE.fullmatch(text)
    if until_eot is not None:
        ability = until_eot.group("ability")
        return ability[0].upper() + ability[1:]
    return None


def _readable_created_trigger(line: str) -> TriggeredAbility | None:
    """`line` read as a printed trigger, when both halves are readable: a
    condition `machines/triggers.condition_matches` can match (an event, no
    intervening "if" - CR 603.4's recheck is `triggers_for`'s, not a delayed
    trigger's) and an effect `trigger_effect_for` answers with a real effect,
    not a fail-closed notice."""
    from ..triggers import granted_triggered_abilities_of

    found = granted_triggered_abilities_of([line])
    if len(found) != 1:
        return None
    (ability,) = found
    if ability.event is None or ability.intervening_if is not None or ability.once_per_turn:
        return None
    if ability.event is TriggerEvent.TAPPED_FOR_MANA or parse_triggered_mana(ability.effect):
        # CR 605.1b: a created ability that triggers on tapping for mana and
        # adds mana is a mana ability - it resolves on the spot, never on the
        # stack - and `_parse_until_end_of_turn_tap_land_additional_mana_
        # clause` builds it that way (High Tide's shape).
        return None
    effect = trigger_effect_for("", ability.event, ability.effect)
    if effect is None or _is_notice_only(effect):
        return None
    return ability


def _create_turn_scoped_trigger(
    game: "Game",
    line: str,
    event: TriggerEvent,
    *,
    controller: str,
    source: CardState | None,
    source_id: UUID | None,
    source_name: str,
) -> None:
    """CR 603.7a/603.7d-e: the ability exists from now, controlled by whoever
    controlled the creating spell or ability as it resolved, with that spell's
    or ability's source as its own. The source's printing rides along - see
    `CreatedTriggeredAbility.source_card` - because a resolving spell is in no
    zone at all while it resolves (a fused Beck // Call's own Birds enter
    then), and a copy (CR 707.10a) or a token (CR 111.7) may cease to exist."""
    game.create_delayed_trigger(
        DelayedTrigger(
            text=line,
            event=event,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            remaining=None,
            expires_end_of_turn=True,
            effect=CreatedTriggeredAbility(
                ability_text=line, source_card=source.card if source is not None else None
            ),
        )
    )


@SPELL_TEXT.rung("s10")
def _parse_created_trigger_spell_text(text: str) -> Effect | None:
    """The spell side: see the banner above."""
    split = _split_created_trigger_paragraph(text)
    if split is None:
        return None
    line, ability, rest_text = split
    event = ability.event
    assert event is not None
    rest: Effect | None = None
    if rest_text:
        rest = _spell_effect_or_notice(rest_text)
        if rest is None or _is_notice_only(rest):
            return None

    def effect(game: "Game", spell: CardState) -> None:
        _create_turn_scoped_trigger(
            game,
            line,
            event,
            controller=game.controller_of(spell).username,
            source=spell,
            source_id=spell.id,
            source_name=spell.name,
        )
        if rest is not None:
            rest(game, spell)

    return effect


@ABILITY_TEXT.rung("s20")
def _parse_created_trigger_ability_text(text: str) -> AbilityEffect | None:
    """The ability side (a loyalty ability, a triggered ability's effect)."""
    split = _split_created_trigger_paragraph(_strip_non_effect_preamble(text))
    if split is None:
        return None
    line, ability, rest_text = split
    event = ability.event
    assert event is not None
    rest: AbilityEffect | None = None
    if rest_text:
        rest = _ability_effect_or_notice(rest_text)
        if rest is None or _is_notice_only(rest):
            return None

    def effect(game: "Game", stack_object: AbilityOnStack) -> None:
        _create_turn_scoped_trigger(
            game,
            line,
            event,
            controller=stack_object.controller,
            source=stack_object.source(game),
            source_id=stack_object.source_id,
            source_name=stack_object.source_name,
        )
        if rest is not None:
            rest(game, stack_object)

    return effect


def _split_instruction_then_created_trigger(
    text: str,
) -> tuple[str, str, TriggeredAbility, str] | None:
    """(the paragraphs before, printed line, its parse, the paragraphs after)
    when a created "this turn" trigger is not the first paragraph: Mage
    Hunters' Onslaught's "Destroy target creature or planeswalker." and then,
    as its own paragraph, "Whenever a creature blocks this turn, its
    controller loses 1 life." CR 608.2c: the instructions run in the order
    written, the trigger being created when its paragraph is reached."""
    paragraphs = [part for part in text.strip().split("\n") if part.strip()]
    for position in range(1, len(paragraphs)):
        split = _split_created_trigger_paragraph("\n".join(paragraphs[position:]))
        if split is not None and split[1].event is not None:
            line, ability, rest = split
            return "\n".join(paragraphs[:position]).strip(), line, ability, rest
    return None


@SPELL_TEXT.rung("s10")
def _parse_instruction_then_created_trigger_spell_text(text: str) -> Effect | None:
    """The spell side of `_split_instruction_then_created_trigger`."""
    split = _split_instruction_then_created_trigger(text)
    if split is None:
        return None
    head_text, line, ability, rest_text = split
    event = ability.event
    assert event is not None
    head = _spell_effect_or_notice(head_text)
    if head is None or _is_notice_only(head):
        return None
    rest: Effect | None = None
    if rest_text:
        rest = _spell_effect_or_notice(rest_text)
        if rest is None or _is_notice_only(rest):
            return None

    def effect(game: "Game", spell: CardState) -> None:
        head(game, spell)
        _create_turn_scoped_trigger(
            game,
            line,
            event,
            controller=game.controller_of(spell).username,
            source=spell,
            source_id=spell.id,
            source_name=spell.name,
        )
        if rest is not None:
            rest(game, spell)

    return effect


@ABILITY_TEXT.rung("s20")
def _parse_instruction_then_created_trigger_ability_text(text: str) -> AbilityEffect | None:
    """The ability side of `_split_instruction_then_created_trigger`."""
    split = _split_instruction_then_created_trigger(_strip_non_effect_preamble(text))
    if split is None:
        return None
    head_text, line, ability, rest_text = split
    event = ability.event
    assert event is not None
    head = _ability_effect_or_notice(head_text)
    if head is None or _is_notice_only(head):
        return None
    rest: AbilityEffect | None = None
    if rest_text:
        rest = _ability_effect_or_notice(rest_text)
        if rest is None or _is_notice_only(rest):
            return None

    def effect(game: "Game", stack_object: AbilityOnStack) -> None:
        head(game, stack_object)
        _create_turn_scoped_trigger(
            game,
            line,
            event,
            controller=stack_object.controller,
            source=stack_object.source(game),
            source_id=stack_object.source_id,
            source_name=stack_object.source_name,
        )
        if rest is not None:
            rest(game, stack_object)

    return effect


# --------------------------------------------------------------------------
# Replacement effects a resolving spell or ability creates for the turn
# --------------------------------------------------------------------------
#
# "Until end of turn, if target player would draw a card, instead ..."
# (Plagiarize), "Until end of turn, if you would put one or more +1/+1
# counters on a creature you control, put that many plus one ... instead"
# (Prairie Dog), "If a creature would enter the battlefield under an
# opponent's control this turn, it enters under your control instead"
# (Gather Specimens), Crafty Cutpurse's token-creation twin. Resolving the
# sentence *is* creating the effect (CR 614.1a, CR 611.2a), the same way a
# resolved prevention spell's shield is; `machines/replacement.
# created_replacement_spec` reads the shape and `Game.created_replacements`
# holds it until CR 514.2's cleanup step.


def _created_replacement_record(
    text: str,
    *,
    controller: str,
    source_id: UUID | None,
    source_name: str,
    target_player: str | None,
    game: "Game | None" = None,
    stack_object: object = None,
) -> CreatedReplacement | None:
    spec = created_replacement_spec(text)
    if spec is None:
        return None
    bind = getattr(spec, "bind", None)
    if bind is not None and game is not None:
        # A spec naming the creating object's targets or a source of its
        # controller's choice (`damage_modification.DamageRedirectReplacement`)
        # is completed now, as it resolves (CR 608.2b, CR 609.7a).
        spec = bind(game, stack_object)
        if spec is None:
            return None
    if isinstance(spec, DrawSkipReplacement) and spec.affected == "player":
        # CR 115.1: "target player" was chosen on announcement and rechecked
        # at CR 608.2b; no legal one left means nothing to replace.
        if target_player is None:
            return None
        spec = spec.model_copy(update={"affected_player": target_player})
    return CreatedReplacement(
        spec=spec,
        label=" ".join(text.split()),
        controller=controller,
        source_id=source_id,
        source_name=source_name,
    )


@SPELL_TEXT.rung("s10")
def _parse_created_replacement_spell_text(text: str) -> Effect | None:
    """The spell side: the whole resolution text is the one sentence."""
    if created_replacement_spec(text) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        target = next(
            (
                ref.username
                for ref in spell.targets
                if ref.username is not None and game.is_in_game(ref.username)
            ),
            None,
        )
        record = _created_replacement_record(
            text,
            controller=game.controller_of(spell).username,
            source_id=spell.id,
            source_name=spell.name,
            target_player=target,
            game=game,
            stack_object=spell,
        )
        if record is not None:
            game.created_replacements.append(record)

    return effect


#: A created replacement's sentence followed by more resolution text -
#: Hallowed Moonlight's "Until end of turn, if a creature would enter and it
#: wasn't cast, exile it instead. Draw a card." CR 608.2c: the instructions
#: are followed in the order written, so the effect is created first.
_LEADING_SENTENCE_RE = re.compile(r"^(?P<first>[^\n]+?\.)\s+(?P<rest>\S.*)$", re.DOTALL)


@SPELL_TEXT.rung("s10")
def _parse_created_replacement_then_rest_spell_text(text: str) -> Effect | None:
    """A spell whose first sentence creates a replacement effect
    (`_parse_created_replacement_spell_text`) and whose remaining text the
    ordinary spell dispatcher reads. Either half unread leaves the whole
    unread (fail closed)."""
    match = _LEADING_SENTENCE_RE.match(text.strip())
    if match is None:
        return None
    created = _parse_created_replacement_spell_text(match.group("first"))
    if created is None:
        return None
    rest = _spell_effect_or_notice(match.group("rest"))
    if rest is None or _is_notice_only(rest):
        return None

    def created_replacement_then_rest(game: "Game", spell: CardState) -> None:
        created(game, spell)
        rest(game, spell)

    return created_replacement_then_rest


@ABILITY_TEXT.rung("s20")
def _parse_created_replacement_ability_text(text: str) -> AbilityEffect | None:
    """The ability side (Prairie Dog's activated ability, Crafty Cutpurse's
    enters trigger)."""
    if created_replacement_spec(text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        target = next(
            (
                found.username
                for found in game.resolve_targets(ability)
                if isinstance(found, Player) and game.is_in_game(found.username)
            ),
            None,
        )
        record = _created_replacement_record(
            text,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            target_player=target,
            game=game,
            stack_object=ability,
        )
        if record is not None:
            game.created_replacements.append(record)

    return effect


#: Fire Navy Trebuchet's whole attack trigger, once `machines/abilities.py` has
#: split the "Whenever you attack," condition off the front: "create a 2/1
#: colorless Construct artifact creature token with flying named Ballistic
#: Boulder that's tapped and attacking. Sacrifice that token at the beginning
#: of the next end step."
#:
#: The singular sibling of `_ATTACK_THIS_TURN_TAPPED_ATTACKING_TOKENS_RE`
#: above, and the differences are all grammar rather than rules:
#:
#: - The trigger is an ordinary one on `TriggerEvent.ATTACKS`, not mobilize's
#:   activated ability that first *creates* a "whenever you attack this turn"
#:   delayed trigger (CR 603.7a), so the outer `DelayedTrigger` that wrapper
#:   builds has no counterpart here. Only the inner half - create the tokens,
#:   then hang a one-shot sacrifice on each - is shared, and it is reused
#:   verbatim.
#: - Singular throughout: "a ... token", "that's tapped and attacking",
#:   "Sacrifice that token". "That token" is CR 400.7 anaphora back to the
#:   token the sentence before it just created, which is why the two sentences
#:   are read as one paragraph - the second cannot name its subject alone.
#: - `named <Name>` sets `TokenDefinition.name` (CR 111.9: a name the creating
#:   effect states, rather than CR 111.4 deriving one from the subtypes).
#:
#: CR 603.7e is what makes the delayed sacrifice the Trebuchet's controller's:
#: "If an activated or triggered ability creates a delayed triggered ability,
#: the source of that delayed triggered ability is the same as the source of
#: that other ability." CR 701.21a is the sacrifice itself - "its controller
#: moves it from the battlefield directly to its owner's graveyard."
_ATTACK_TAPPED_ATTACKING_TOKENS_THEN_SACRIFICE_RE = re.compile(
    rf"^create (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b"
    r"(?:\s+with\s+(?P<tail>.+?))?"
    r"(?:\s+named (?P<name>.+?))?"
    r"\s+that(?:'s|’s| is| are) tapped and attacking\.\s*"
    r"sacrifice (?:that token|them|those tokens) at the beginning of the next end step\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_create_tapped_attacking_tokens_then_sacrifice(text: str) -> AbilityEffect | None:
    """`_ATTACK_TAPPED_ATTACKING_TOKENS_THEN_SACRIFICE_RE`'s shape - see it for
    what this reads and why it is one paragraph rather than two clauses.

    Fail-closed on the token descriptor, as every token clause in this file is:
    a tail `_parse_token_tail` cannot read takes the whole ability down rather
    than creating a token missing an ability it was printed with (CR 608.2c).
    """
    match = _ATTACK_TAPPED_ATTACKING_TOKENS_THEN_SACRIFICE_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    count = parse_count(match.group("n"))
    definition = _parse_generic_token_descriptor(
        match.group("desc").strip().split(), match.group("tail")
    )
    if definition is None:
        return None
    if name := match.group("name"):
        # CR 111.9: the creating effect stated a name, so it is the token's
        # name rather than CR 111.4's subtype-derived default.
        definition = definition.model_copy(update={"name": name.strip()})

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        created = create_tokens(
            game,
            definition,
            controller.username,
            count,
            tapped=True,
            attacking=_defender_of_controllers_attack(game, controller.username),
        )
        for token in created:
            game.create_delayed_trigger(
                DelayedTrigger(
                    text="Sacrifice that token at the beginning of the next end step.",
                    effect=SacrificeSubject(),
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.END_STEP,
                    controller=controller.username,
                    source_id=source_id,
                    source_name=source_name,
                    subject_id=token.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=token.zone_change_stamp,
                )
            )

    return effect


# --------------------------------------------------------------------------
# "You may <cost>. If you do, create ... tapped and attacking[. Sacrifice
# that token at <timing>.]" (CR 118.12, CR 508.4, CR 603.7a)
# --------------------------------------------------------------------------
#
# `_ATTACK_TAPPED_ATTACKING_TOKENS_THEN_SACRIFICE_RE` above is this shape with
# the choice removed and the timing fixed to the end step. The two cards this
# section is for both put a CR 118.12 optional cost in front of it:
#
#   Kavaron Harrier - "you may pay {2}. If you do, create a 2/2 colorless
#   Robot artifact creature token that's tapped and attacking. Sacrifice that
#   token at end of combat."
#
#   Gut, True Soul Zealot - "you may sacrifice another creature or an
#   artifact. If you do, create a 4/1 black Skeleton creature token with
#   menace that's tapped and attacking."
#
# CR 118.12 is the shape: "[A player] may [do something]. If [that player]
# [does, doesn't, or can't], [effect]." The choice belongs to *resolution*, not
# to putting the ability on the stack - CR 603.3d imports only CR 601.2c-d's
# targets and divisions, and neither of these abilities targets anything - which
# is exactly why DDR#983's trick works: order the Harrier's trigger to resolve
# first (CR 603.3b) and the Robot exists by the time Gut asks for a sacrifice.
#
# Read whole rather than per clause: "If you do" and "that token" both point
# back at earlier sentences of the same paragraph, so `split_effect_clauses`
# would leave fragments naming nothing (CR 608.2c).
#
# CR 701.21a is the sacrifice on both ends of it - the optional cost and the
# delayed clean-up: "To sacrifice a permanent, its controller moves it from the
# battlefield directly to its owner's graveyard."

#: The restriction nouns `_attacking_token_sacrifice_candidates` reads - one of
#: CR 205.2a's card types, per item of an "or" list.
_SACRIFICE_ITEM_RE = re.compile(r"^(?:a|an|another)?\s*(?P<noun>[a-z]+)$", re.IGNORECASE)

_MAY_COST_THEN_ATTACKING_TOKEN_RE = re.compile(
    r"^you may (?:pay (?P<mana>(?:\{[^}]+\})+)|sacrifice (?P<restriction>[^.]+))\.\s*"
    rf"if you do, create (?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b"
    r"(?:\s+with\s+(?P<tail>.+?))?"
    r"(?:\s+named (?P<name>.+?))?"
    r"\s+that(?:'s|’s| is| are) tapped and attacking\."
    r"(?:\s*sacrifice (?:that token|them|those tokens) at (?P<timing>[^.]+)\.?)?$",
    re.IGNORECASE | re.DOTALL,
)


def _attacking_token_sacrifice_candidates(
    restriction: str,
) -> Callable[["Game", Player, UUID | None], list[CardState]] | None:
    """Read "another creature or an artifact" into the permanents that satisfy
    it, or `None` if this wave cannot read the restriction at all.

    `_sacrifice_restriction` above reads only a *single* card type, fail-closed
    on anything compound, which is right for the shape it serves and wrong for
    this one - so this reads the "or" list CR 109.2's descriptions allow. Each
    item is one of CR 205.2a's card types, optionally with its own "a"/"an"; a
    word that is not a card type takes the whole clause down rather than
    offering the player permanents the card never named.

    **"Another" is applied to the whole list**, not only to the item it
    precedes. Read strictly, Gut's "another creature or an artifact" excludes
    Gut only from the creature half - but Gut is not an artifact, and no other
    card in the pool prints this shape, so the two readings cannot be told
    apart here. The whole-list reading is the one that can never let a
    permanent sacrifice itself to its own ability by accident; if a printing
    ever needs the narrow one, this is the line to split.
    """
    wanted: set[Type] = set()
    excludes_source = False
    for item in re.split(r",\s*|\s+or\s+", restriction.strip().lower()):
        if not item:
            continue
        match = _SACRIFICE_ITEM_RE.fullmatch(item.strip())
        if match is None:
            return None
        if item.strip().startswith("another"):
            excludes_source = True
        try:
            wanted.add(Type(match.group("noun")))
        except ValueError:
            return None
    if not wanted:
        return None

    def candidates(game: "Game", player: Player, source_id: UUID | None) -> list[CardState]:
        # CR 613.5: the type test is the computed one, so an animated land is
        # a legal "another creature" to sacrifice here.
        return computed_permanents(
            game,
            (
                state
                for state in game.battlefield
                if state.controller == player.username
                and (not excludes_source or state.id != source_id)
            ),
            lambda chars: bool(set(chars.types) & wanted),
        )

    return candidates


@ABILITY_TEXT.rung("s22")
def _parse_may_cost_then_attacking_token_clause(text: str) -> AbilityEffect | None:
    """`_MAY_COST_THEN_ATTACKING_TOKEN_RE`'s shape - see the section note.

    Fail-closed on every part: a token descriptor `_parse_generic_token_
    descriptor` cannot read, a sacrifice restriction
    `_attacking_token_sacrifice_candidates` cannot read, an unparseable mana
    cost, or a timing phrase `delayed.ANAPHORIC_TIMING_STEPS` does not know
    each take the whole ability down rather than doing part of it (CR 608.2c).

    The mana half goes through `Game.may_pay_mana_cost`, which counts floating
    mana and the controller's untapped mana sources (CR 608.2g: "they may
    activate mana abilities before taking that action"); a controller who
    cannot find the {2} either way is refused and the "if you do" branch does
    not run.

    CR 508.4 places the token into the combat already in progress, against
    whatever the controller's own attack already named
    (`_defender_of_controllers_attack`); a controller attacking nothing gets a
    tapped token that is not attacking anything, which is the honest outcome
    rather than an invented defender.
    """
    match = _MAY_COST_THEN_ATTACKING_TOKEN_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None

    cost: ManaCost | None = None
    candidates_of = None
    prompt = ""
    if match.group("mana") is not None:
        cost = ManaCost.try_parse(match.group("mana"))
        if cost is None:
            return None
        prompt = f"pay {cost}"
    else:
        restriction = match.group("restriction")
        candidates_of = _attacking_token_sacrifice_candidates(restriction)
        if candidates_of is None:
            return None
        prompt = f"sacrifice {restriction.strip()}"

    count = parse_count(match.group("n"))
    definition = _parse_generic_token_descriptor(
        match.group("desc").strip().split(), match.group("tail")
    )
    if definition is None:
        return None
    if name := match.group("name"):
        # CR 111.9: a name the creating effect states, rather than CR 111.4's
        # subtype-derived default.
        definition = definition.model_copy(update={"name": name.strip()})

    step: Step | None = None
    if timing := match.group("timing"):
        step = ANAPHORIC_TIMING_STEPS.get(timing.strip().lower())
        if step is None:
            return None
    sacrifice_text = "" if step is None else f"Sacrifice that token at {match.group('timing')}."

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        if cost is not None:
            if not game.may_pay_mana_cost(
                controller, cost, source=source_name, source_id=source_id_of(ability)
            ):
                return
        else:
            assert candidates_of is not None
            available = candidates_of(game, controller, source_id)
            decision = Decision(
                kind=DecisionKind.MAY,
                player=controller.username,
                prompt=prompt,
                source=source_name,
                affirmative_is_legal=bool(available),
                source_id=source_id_of(ability),
            )
            if not game.ask(decision):
                return
            # Each "or" item prints its own article, so the count is one; the
            # shared chooser asks for it the way every "you may sacrifice" does.
            chosen = _choose_permanents_to_sacrifice(
                game,
                controller,
                _SacrificeRestriction(False, candidates_of, _ONE_PERMANENT),
                available,
                source_name=source_name,
                source_id=source_id_of(ability),
            )
            if not chosen:
                return
            game.sacrifice(chosen[0])

        created = create_tokens(
            game,
            definition,
            controller.username,
            count,
            tapped=True,
            attacking=_defender_of_controllers_attack(game, controller.username),
        )
        if step is None:
            return
        for token in created:
            # CR 603.7a creates this now, and CR 603.7e makes it the same
            # controller and source as the ability that created it. CR 603.7c
            # is `expected_zone`/`expected_stamp`: a token that has already
            # left the battlefield - fed to Gut, in DDR#983's own line - is a
            # different object, so the delayed sacrifice affects nothing.
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=sacrifice_text,
                    effect=SacrificeSubject(),
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=controller.username,
                    source_id=source_id,
                    source_name=source_name,
                    subject_id=token.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=token.zone_change_stamp,
                )
            )

    return effect


# --------------------------------------------------------------------------
# Amass (CR 701.47) - the same shape as earthbend just above: a CR 701 keyword
# action embedded in another ability's effect text rather than an ability of
# its own. Orcish Bowmasters' "... Then amass Orcs 1." is the pool's printing,
# and it was silent twice over - the sentence-initial "Then" made the clause
# unreadable, which correctly refused the damage half with it (CR 608.2c), and
# nothing anywhere in the engine knew what the word meant.
# --------------------------------------------------------------------------

#: "amass `<subtype>` N" - CR 701.47d is why the subtype is not optional here:
#: "Some older cards were printed with amass N without including a subtype.
#: Those cards have received errata in the Oracle card reference so that they
#: read 'amass Zombies N.'" Every printing this engine can be handed carries
#: one, so a bare "amass 1" is left unread rather than defaulted to Zombies -
#: guessing the subtype would be a fails-open answer on a card whose real
#: subtype is something else.
#:
#: The subtype is printed **plural** ("amass Orcs 1") and the token it names
#: is singular ("Orc Army"), which `_singular_subtype_for_amass` undoes.
_AMASS_RE = re.compile(
    rf"^amass (?P<subtype>[A-Za-z][a-z]*) {count_pattern('n', x=True)}{where_x_pattern()}$",
    re.IGNORECASE,
)


def amass(
    game: "Game",
    controller: str,
    subtype: str,
    amount: int,
    source_name: str,
    *,
    source_id: str | None,
) -> CardState | None:
    """CR 701.47a: "To amass [subtype] N means 'If you don't control an Army
    creature, create a 0/0 black [subtype] Army creature token. Choose an Army
    creature you control. Put N +1/+1 counters on that creature. If it isn't a
    [subtype], it becomes a [subtype] in addition to its other types.'"

    Four steps in the order the rule writes them, and every one of them is a
    step this engine can decline to take without the whole thing failing - CR
    701.47b: "A player 'amassed' after the process described in rule 701.47a
    is complete, **even if some or all of those actions were impossible**."
    That is why nothing here raises: an amass with no Army to choose (the
    token creation was replaced away) simply finishes having done less.

    The choice is CR 608.2d's, and it is only *asked* when there is more than
    one Army to choose between - a single candidate is not a choice, and
    asking anyway would put a question on the tape that a decoded replay of
    the same game would have to answer identically for no reason.

    The last step is a layer 4 addition (CR 205.1b's "in addition to its other
    types"), scoped to this incarnation of the permanent (CR 400.7, CR 611.2c)
    exactly as `earthbend` above scopes its own, and `Duration.INDEFINITE`
    because CR 701.47a states no end (CR 611.2a). It is skipped outright when
    the chosen Army already has the subtype, which is the ordinary case: the
    token this same call may have just created is printed with it.
    """
    armies = _armies_controlled_by(game, controller)
    singular = _singular_subtype_for_amass(subtype)
    if not armies:
        create_tokens(
            game,
            TokenDefinition(
                types=(Type.CREATURE,),
                subtypes=(singular, "Army"),
                colors=(Color.BLACK,),
                power=0,
                toughness=0,
            ),
            controller,
            1,
        )
        armies = _armies_controlled_by(game, controller)
    if not armies:
        return None  # CR 701.47b: the player still amassed.
    if len(armies) == 1:
        army = armies[0]
    else:
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose an Army creature to amass {subtype} {amount} onto",
                source=source_name,
                amount=1,
                cards=tuple(state.id for state in armies),
                source_id=source_id,
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {state.id: state for state in armies}
        army = by_id[chosen[0]]
    game.add_counters(army, Counter.PLUS_ONE, amount)
    if any(
        existing.lower() == singular.lower() for existing in game.characteristics_of(army).subtypes
    ):
        return army
    game.continuous_effects.add(
        ContinuousEffect(
            description=f"amass {subtype}: {army.name} becomes {with_indefinite_article(singular)}",
            layer=Layer.TYPE,
            timestamp=game.continuous_effects.tick(),
            duration=Duration.INDEFINITE,
            selector=only_this_incarnation(army, army.zone_change_stamp),
            modification=add_subtype(singular),
        )
    )
    return army


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_amass_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Amass `<subtype>` N." or "Amass `<subtype>` X, where X is `<expr>`." -
    `_AMASS_RE`'s shape, as one clause among however many the card prints
    around it.

    Amass targets nothing (CR 701.47a's "Choose an Army creature you control"
    is CR 608.2d's choice, not CR 115.1's target), so this reads nothing off
    the stack object but its controller and its name for the prompt - which
    means the same clause works identically for a spell and for an ability,
    unlike earthbend just above. Invade the City's "Amass Zombies X, where X
    is the number of instant and sorcery cards in your graveyard" is CR
    107.3f's X, read the same way earthbend's own X is: through
    `_fixed_or_where_x_amount`, refusing the clause rather than amassing for
    zero when the definition is not one this engine can evaluate.
    """
    match = _AMASS_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    subtype = match.group("subtype")
    reader = _fixed_or_where_x_amount(match.group("n"), match.group("where_x"))
    if reader is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        source_state = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        )  # type: ignore[union-attr]
        x_value = stack_object.x_value if isinstance(stack_object, AbilityOnStack) else 0
        amount = reader(game, controller, source_state, x_value)
        amass(
            game,
            controller,
            subtype,
            amount,
            source,
            source_id=source_id_of(stack_object),
        )

    return effect


#: "Amass `<subtype>` `<n>`, then attach this Equipment to the amassed
#: Army." - Goblin Plate Mail's own ETB trigger. CR 701.47a's "amass" already
#: names which Army the process acted on ("Choose an Army creature you
#: control. Put N +1/+1 counters on that creature."); "the amassed Army" is
#: CR 607.1 anaphora back to that same creature, not a second target, so this
#: only has to keep what `amass` (above) hands back and attach the Equipment
#: (`attach_permanent`, CR 701.3a) to it - never a target list of its own,
#: for the identical reason `_parse_amass_clause` above needs none.
_AMASS_THEN_ATTACH_RE = re.compile(
    rf"^amass (?P<subtype>[A-Za-z][a-z]*) {count_pattern('n', x=True)}{where_x_pattern()}, "
    r"then attach this (?:equipment|permanent) to the amassed army\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_amass_then_attach_clause(clause: str) -> AbilityEffect | None:
    """`_AMASS_THEN_ATTACH_RE`'s shape - see the banner above."""
    match = _AMASS_THEN_ATTACH_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    subtype = match.group("subtype")
    reader = _fixed_or_where_x_amount(match.group("n"), match.group("where_x"))
    if reader is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = ability.controller
        amount = reader(game, controller, source, 0)
        army = amass(
            game,
            controller,
            subtype,
            amount,
            ability.source_name,
            source_id=source_id_of(ability),
        )
        if army is not None:
            attach_permanent(game, source, army)

    return effect


#: CR 701.16a: "'Investigate' means 'Create a Clue token.'" A bare keyword
#: action, the same shape as amass/fight above - "investigate" alone
#: (Tamiyo, Inquisitive Student), or "investigate [word] times"/"investigate
#: [word]" for the fixed-count multiples the pool actually prints (Armed
#: with Proof's "investigate twice"). Deliberately narrower than every
#: shape Scryfall prints: "investigate X times, where X is ..." (a
#: resolution-time count, CR 608.2h) and "[player] investigates" naming a
#: subject other than the resolving object's own controller (Fateful
#: Absence's "Its controller investigates.") are both real templates this
#: does not read - fail closed rather than guess a count or a controller.
#:
#: A trailing "for each `<phrase>`" scales it by `_for_each_multiplier`'s
#: count, read once as the ability applies (CR 608.2h): Tamiyo Meets the
#: Story Circle's "investigate twice for each card discarded this way" (CR
#: 608.2c's "this way" onto the discard the same ability just made) and
#: Teysa, Opulent Oligarch's "investigate for each opponent who lost life
#: this turn".
_INVESTIGATE_RE = re.compile(
    r"^investigate(?:\s+(?P<multiplier>twice|thrice|once|\d+|(?!for\b)[a-z]+)(?:\s+times?)?)?"
    r"(?:\s+for each (?P<each>.+))?$",
    re.IGNORECASE,
)


def investigate(game: "Game", controller: str, amount: int = 1) -> None:
    """CR 701.16a, CR 111.10f: create `amount` Clue tokens for `controller`."""
    create_tokens(game, PREDEFINED["Clue"], controller, amount)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_investigate_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Investigate[, [word] times]." - `_INVESTIGATE_RE`'s shape.

    Investigate targets nothing and names no object of its own (CR 701.16a),
    so - like amass above - this reads only the stack object's controller,
    and the same clause works for a spell or an ability alike.
    """
    match = _INVESTIGATE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    word = match.group("multiplier")
    # The group holds "twice" or the "three" of "three times".
    amount = 1 if word is None else parse_multiplier(word) or parse_multiplier(f"{word} times")
    if amount is None:
        return None
    each = match.group("each")
    multiplier = _for_each_multiplier(each) if each is not None else None
    if each is not None and multiplier is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        times = amount
        if multiplier is not None:
            times *= multiplier(game, controller, source_id_of(stack_object))
        if times > 0:
            investigate(game, controller, times)

    return effect


#: "create a token that's a copy of it" - the verb half of Ochre Jelly's
#: delayed "... at the beginning of the next end step", once
#: `_parse_delayed_timing_clause` has taken the timing off either end.
_DELAYED_TOKEN_COPY_OF_IT_VERB_RE = re.compile(
    r"^create a token that'?s a copy of (?:it|this creature|this permanent)$", re.IGNORECASE
)
#: "The token enters with half that many +1/+1 counters on it, rounded down."
#: - CR 614.1c's "enters with" said of the token the previous clause makes.
#: "that many" is the number of that kind of counter "it" had (CR 603.10a's
#: look-back for a dies trigger); a fixed number reads as itself.
_THE_TOKEN_ENTERS_WITH_COUNTERS_RE = re.compile(
    r"^(?:the|that) token enters with "
    rf"(?:(?P<half>half )?(?P<that_many>that many)|(?P<n>{AMOUNT})) "
    r"(?P<kind>\S+) counters? on it(?:, rounded (?P<rounding>down|up))?$",
    re.IGNORECASE,
)


def _parse_delayed_token_copy_of_it_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_DELAYED_TOKEN_COPY_OF_IT_VERB_RE` behind a delayed timing (CR 603.7a),
    optionally followed by `_THE_TOKEN_ENTERS_WITH_COUNTERS_RE` - Ochre
    Jelly's "create a token that's a copy of it at the beginning of the next
    end step. The token enters with half that many +1/+1 counters on it,
    rounded down."

    "It" is the trigger's event subject (the creature that died), else the
    ability's source, as it last existed (CR 603.10a, `source_or_last_known`
    for a token that ceased to exist, CR 704.5d). Its copiable values (CR
    707.2) and the entering counter count are fixed now, as the creating
    ability resolves, and persisted on `CreateTokenCopyOfLastKnown` - by the
    time the delayed ability resolves the object may be nowhere at all.
    Ability-only: a spell has no "it" of this kind.
    """
    if for_spell:
        return None
    timing = _parse_delayed_timing_clause(clauses[index])
    if timing is None:
        return None
    step, verb = timing
    if _DELAYED_TOKEN_COPY_OF_IT_VERB_RE.fullmatch(verb.strip()) is None:
        return None
    consumed = 1
    counters_match = None
    if index + 1 < len(clauses):
        counters_match = _THE_TOKEN_ENTERS_WITH_COUNTERS_RE.fullmatch(
            clauses[index + 1].strip().rstrip(".")
        )
        if counters_match is not None:
            consumed = 2
    kind = _counter_kind(counters_match.group("kind")) if counters_match is not None else None
    fixed = (
        parse_count(counters_match.group("n"))
        if counters_match is not None and counters_match.group("n") is not None
        else None
    )
    if counters_match is not None and counters_match.group("n") is not None and fixed is None:
        return None
    text = ". ".join(clauses[index : index + consumed]) + "."

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        subject: CardState | None = None
        event = ability.event
        if event is not None and event.subject_id is not None:
            found = game.find_by_id(event.subject_id)
            if isinstance(found, CardState):
                subject = found
        if subject is None:
            subject = ability.source_or_last_known(game)
        if subject is None:
            return
        enters_with: tuple[tuple[str, int], ...] = ()
        if counters_match is not None and kind is not None:
            if fixed is not None:
                amount = fixed
            else:
                had = (
                    subject.counter_count(kind)
                    if subject.zone is Zone.BATTLEFIELD
                    else subject.last_known_counters[kind]
                )
                if counters_match.group("half") is not None:
                    up = (counters_match.group("rounding") or "down").lower() == "up"
                    amount = (had + 1) // 2 if up else had // 2
                else:
                    amount = had
            if amount > 0:
                enters_with = ((kind, amount),)
        game.create_delayed_trigger(
            DelayedTrigger(
                text=text,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                effect=CreateTokenCopyOfLastKnown(
                    # CR 707.2 as it last existed (CR 603.10a): a copy
                    # effect on the dying object is part of what is copied.
                    copiable=(
                        subject.last_known_copiable or subject.card
                        if subject.zone is not Zone.BATTLEFIELD
                        else copiable_card_of(game, subject)
                    ),
                    subject_id=subject.id,
                    enters_with_counters=enters_with,
                ),
            )
        )

    return consumed, effect


#: Replicate (the sorcery half of Repudiate // Replicate): "Create a token
#: that's a copy of target creature you control." (CR 707.2, CR 111.13's
#: "created" token, not CR 111.13's exempt copy-of-a-spell), and Three Steps
#: Ahead's own second Spree mode: "Create a token that's a copy of target
#: artifact or creature you control." - the identical shape with a two-word
#: "artifact or creature" target description in place of the bare "creature"
#: `phrase` only used to read literally; `machines/targeting.py` is what
#: actually resolves either description (`_targets_understood` below only
#: asks whether that module read it), so widening the noun phrase costs
#: nothing here beyond recognising it. Deliberately not `_parse_token_
#: clause`'s job - that parser bails out on any "copy of" phrase by name (see
#: `test_repudiates_copy_clause_fails_closed`, which checks the *combined*
#: split-card printing's blank top-level text and stays true either way)
#: because it has no target-resolution step at all; this one does, reusing
#: `token_copy_of` the same way `_parse_city_blessing_token_copy_clause`
#: below reuses it for Ocelot Pride's anaphoric "it" instead of a real
#: target.
#:
#: Widened (R0b-T5) with the temporary-copy tail every "copy it for a turn"
#: printing carries, each part optional and each about the token just made
#: (CR 608.2c), never the targeted original:
#:
#: - CR 707.9b's ", except it's an artifact in addition to its other types"
#:   (Molten Duplication) - a card type written into the copiable values -
#:   or any exception `_read_copy_exception_list`/`_read_token_copy_except`
#:   already reads;
#: - "It gains haste[ until end of turn]." / "That token gains haste."
#:   (Molten Duplication, Cogwork Assembler) - a layer 6 grant on the token;
#: - "(Sacrifice|Exile) it at the beginning of the next end step." (The Fire
#:   Crystal, Molten Duplication, Cogwork Assembler) - CR 603.7a's delayed
#:   trigger, built by `anaphoric_delayed_trigger` against the token's own
#:   incarnation, so a token already gone by then is left alone.
#:
#: The target's "you control" is optional too: Cogwork Assembler's bare
#: "target artifact" may name an opponent's artifact, and the token is still
#: created under the ability's controller (CR 111.2).
#:
#: Widened again (E5-U8) with the "tapped and attacking" family and
#: "another" (Chrome Dome's "another target artifact you control", Flamerush
#: Rider's "another target attacking creature"), each part optional:
#:
#: - ", and that's tapped and attacking" / "The token enters tapped and
#:   attacking." (CR 508.4): the token enters tapped and already attacking
#:   whatever its original attacks, never declared as an attacker (CR 508.4c),
#:   so no "whenever this creature attacks" ability of the copy triggers;
#: - "Exile the token at end of combat." (Flamerush Rider): the same CR 603.7a
#:   delayed trigger, at CR 511.2's end of combat step.
#: The token copy's own "tapped and attacking" sentence (CR 508.4), shared by
#: `_CREATE_TOKEN_COPY_OF_TARGET_RE` (Flamerush Rider) and
#: `_CREATE_TOKEN_COPIES_EXCEPT_RE` (Thousand-Faced Shadow).
_TOKEN_COPY_ENTERS_TAPPED_AND_ATTACKING = r"(?:the tokens? enters?|they enter) tapped and attacking"


def _token_copy_tapped_and_attacking(
    game: "Game", original: CardState, controller: str
) -> dict[str, Any]:
    """`token_copy_of`'s options for a copy that enters tapped and attacking
    (CR 508.4: its controller chooses what it attacks): whatever its original
    attacks, or else whatever the controller's attack already names. With
    neither, the copy enters tapped but not attacking."""
    original_attack = game.combat.attack_by(original.id)
    defender = (
        original_attack.defender
        if original_attack is not None
        else _defender_of_controllers_attack(game, controller)
    )
    options: dict[str, Any] = {"tapped": True}
    if defender is not None:
        options["attacking"] = defender
    return options


#: "Create X tokens that are copies of it and that are tapped and attacking,
#: where X is the number of creatures defending player controls." - Nacatl
#: War-Pride's attack trigger (CR 508.4: the copies enter tapped and attacking
#: and are never declared as attackers, so no "whenever this attacks" ability
#: of a copy triggers). "It" is the ability's own source, copied as it last
#: existed (CR 707.2, 608.2h): a source that has left the battlefield by now
#: still gives its copiable values. The count is a fixed number, or X defined
#: by the number of `<quality>` defending player controls (CR 508.5's
#: defending player, from the attack that triggered the ability). The rider
#: sentence ("Exile the tokens at the beginning of the next end step.") is
#: read with it by `_parse_token_with_keywords_and_quoted_ability_sentences`.
_CREATE_COPIES_OF_SELF_ATTACKING_RE = re.compile(
    rf"^create (?P<n>x|{COUNT}|an?) tokens? that(?:['’]s| is| are) "
    r"(?:a copy|copies) of (?P<object>it|this [a-z]+),? and that(?:['’]s| is| are) "
    r"tapped and attacking(?:, where x is the number of (?P<quality>[a-z -]+?) "
    r"defending player controls)?\.?$",
    re.IGNORECASE,
)


def _parse_create_copies_of_self_attacking_clause(
    sentence: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_CREATE_COPIES_OF_SELF_ATTACKING_RE`'s shape, or `None`."""
    if for_spell or "tapped and attacking" not in sentence.lower():
        return None
    match = _CREATE_COPIES_OF_SELF_ATTACKING_RE.fullmatch(" ".join(sentence.split()))
    if match is None:
        return None
    from ...models.game import _permanent_quality
    from ..combat import defending_player

    quality = match.group("quality")
    if (match.group("n").lower() == "x") != (quality is not None):
        return None  # an X with no definition, or a definition with no X
    fixed = None if quality is not None else parse_count(match.group("n"))
    counts = _permanent_quality(quality) if quality is not None else None
    if (quality is not None and counts is None) or (quality is None and fixed is None):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None:
            return
        controller = stack_object.controller
        options = _token_copy_tapped_and_attacking(game, source, controller)
        if counts is None:
            amount = fixed or 0
        else:
            event = stack_object.event
            defender = options.get("attacking")
            defending = (
                event.defender_controller
                if event is not None and event.defender_controller is not None
                else defending_player(game, defender)
                if defender is not None
                else None
            )
            if defending is None:
                return
            amount = sum(
                1
                for permanent in game.permanents_controlled_by(defending)
                if counts(game.characteristics_of(permanent))
            )
        token_copy_of(game, source, controller, count=amount, **options)

    return effect


_CREATE_TOKEN_COPY_OF_TARGET_RE = re.compile(
    r"^create a token that['’]?s a copy of "
    r"(?P<phrase>(?:another )?target (?:(?:attacking|blocking|nonlegendary|nontoken) )?"
    r"[a-z]+(?: or [a-z]+)?(?: you control)?)"
    r"(?:, except (?P<except>[^.]+?))?"
    r"(?P<attacking>,? and that['’]?s tapped and attacking)?\.?"
    r"(?P<haste>\s*(?:it|that token) gains haste(?P<eot> until end of turn)?\.)?"
    rf"(?P<enters_attacking>\s*{_TOKEN_COPY_ENTERS_TAPPED_AND_ATTACKING}\.?)?"
    r"(?P<end_step>\s*(?:(?:exile|sacrifice) it at the beginning of the next end step"
    r"|exile the token at end of combat)\.?)?\s*$",
    re.IGNORECASE,
)

#: "Create a token that's a copy of enchanted|equipped creature[, except
#: <exception>]." - Ghastly Mimicry's upkeep trigger ("..., except it's a
#: Spirit in addition to its other types."). No target: the object is the one
#: the ability's source is attached to as it resolves (CR 303.4, CR 301.5);
#: none, and nothing is created (CR 608.2b's spirit for an untargeted
#: referent that is gone). The exception is `_read_copy_exception_list`'s.
_CREATE_TOKEN_COPY_OF_ATTACHED_RE = re.compile(
    r"^create a token that['’]?s a copy of (?:enchanted|equipped) creature"
    r"(?:, except (?P<except>[^.]+?))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s21")
def _parse_create_token_copy_of_attached_clause(clause: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_COPY_OF_ATTACHED_RE`'s shape, or `None`."""
    if "copy of" not in clause:
        return None
    match = _CREATE_TOKEN_COPY_OF_ATTACHED_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    listed = _read_copy_exception_list(match.group("except")) if match.group("except") else None
    if match.group("except") and listed is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD or source.attached_to is None:
            return
        attached = game.find_by_id(source.attached_to)
        if not isinstance(attached, CardState) or attached.zone is not Zone.BATTLEFIELD:
            return
        token_copy_of(
            game,
            attached,
            ability.controller,
            added_abilities=listed.added_abilities if listed else (),
            power=listed.power if listed else None,
            toughness=listed.toughness if listed else None,
            added_creature_type=listed.added_creature_type if listed else None,
            not_legendary=listed.not_legendary if listed else False,
        )

    return effect


#: CR 707.9b's card-type exception - "except it's an artifact in addition to
#: its other types" (Molten Duplication): the named card type joins the
#: copy's copiable type line (CR 205.1b's "in addition to").
_EXCEPT_ADDED_CARD_TYPE_RE = re.compile(
    r"^(?:it['’]?s|it is) an? (?P<card_type>artifact|enchantment) "
    r"in addition to its other types$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_create_token_copy_of_target_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_CREATE_TOKEN_COPY_OF_TARGET_RE`'s shape, or `None` if this is not it."""
    match = _CREATE_TOKEN_COPY_OF_TARGET_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    added: tuple[str, ...] = ()
    power: int | None = None
    toughness: int | None = None
    added_type: str | None = None
    added_card_type: str | None = None
    colors: tuple[Color, ...] | None = None
    creature_types: tuple[str, ...] | None = None
    not_legendary = False
    except_text = match.group("except")
    if except_text is not None:
        # The same exception readers, in the same order, as
        # `_parse_create_token_copies_except_clause` - plus CR 707.9b's card
        # type, which neither of them reads.
        card_type = _EXCEPT_ADDED_CARD_TYPE_RE.fullmatch(except_text.strip())
        replacing = _read_token_copy_replacing_except(except_text)
        listed = _read_copy_exception_list(except_text)
        if card_type is not None:
            added_card_type = card_type.group("card_type").title()
        elif replacing is not None:
            power, toughness, colors, creature_types = replacing
        elif listed is not None:
            added, power, toughness, added_type = (
                listed.added_abilities,
                listed.power,
                listed.toughness,
                listed.added_creature_type,
            )
            not_legendary = listed.not_legendary
        else:
            exception = _read_token_copy_except(except_text)
            if exception is None:
                return None
            added, power, toughness, added_type = exception
    haste = match.group("haste") is not None
    haste_duration = (
        Duration.UNTIL_END_OF_TURN if match.group("eot") is not None else Duration.INDEFINITE
    )
    end_step = match.group("end_step")
    tapped_and_attacking = (
        match.group("attacking") is not None or match.group("enters_attacking") is not None
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ..dies_this_turn import source_id_of_object

        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState):
                continue
            options = (
                _token_copy_tapped_and_attacking(game, target, controller.username)
                if tapped_and_attacking
                else {}
            )
            created = token_copy_of(
                game,
                target,
                controller.username,
                added_abilities=added,
                power=power,
                toughness=toughness,
                added_creature_type=added_type,
                added_card_type=added_card_type,
                colors=colors,
                creature_types=creature_types,
                not_legendary=not_legendary,
                **options,
            )
            store = continuous_effects(game)
            for token in created:
                if token.zone is not Zone.BATTLEFIELD:
                    continue
                if haste:
                    store.add(
                        ContinuousEffect(
                            description=f"{source_name}: {token.name} gains haste",
                            layer=Layer.ABILITY,
                            timestamp=store.tick(),
                            selector=only_this_incarnation(token, token.zone_change_stamp),
                            modification=grant_ability("Haste"),
                            duration=haste_duration,
                        ),
                        game,
                    )
                if end_step:
                    trigger = anaphoric_delayed_trigger(
                        end_step.strip(),
                        subject=token,
                        controller=controller.username,
                        source_id=source_id_of_object(stack_object),
                        source_name=source_name,
                        game=game,
                    )
                    if trigger is not None:
                        game.create_delayed_trigger(trigger)

    return effect


#: "Create a token that's a copy of a `<quality>` you control." - Awaken the
#: Maelstrom's own bare "a permanent you control" and Calix, Guided by Fate's
#: "a nonlegendary enchantment you control": CR 608.2d's own choice among the
#: controller's own matching permanents, never a target (Chrome Dome's/
#: Extravagant Replication's "another target ..." siblings are
#: `_CREATE_TOKEN_COPY_OF_TARGET_RE`'s own shape, immediately above). The
#: identical "a permanent you control" noun phrase is also Moritte of the
#: Frost's own enter-as-copy line - not this mechanic, but proof the phrase
#: itself is not this card's own invention.
_CREATE_TOKEN_COPY_OF_QUALITY_YOU_CONTROL_RE = re.compile(
    r"^create an? token that'?s a copy of an? (?P<quality>[a-z][a-z' -]*?) you control\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s22")
def _parse_create_token_copy_of_quality_you_control_clause(clause: str) -> Effect | None:
    """`_CREATE_TOKEN_COPY_OF_QUALITY_YOU_CONTROL_RE`'s shape, or `None`."""
    match = _CREATE_TOKEN_COPY_OF_QUALITY_YOU_CONTROL_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if matches(permanent)
        ]
        if not candidates:
            return
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        chosen = candidates[0]
        if len(candidates) > 1:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"choose {with_indefinite_article(quality)} permanent you control to copy"
                    ),
                    source=source,
                    source_id=source_id_of(stack_object),
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                    card_labels=tuple(permanent.name for permanent in candidates),
                )
            )
            assert isinstance(chosen_ids, tuple)
            if not chosen_ids:
                return
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen = by_id[chosen_ids[0]]
        token_copy_of(game, chosen, controller.username)

    return effect


#: "Create X tokens that are copies of target creature you control, except
#: they have "<ability>"." - Aggressive Biomancy. The plural, counted twin of
#: `_CREATE_TOKEN_COPY_OF_TARGET_RE` above, with CR 707.9's two exception
#: channels: CR 707.9a's granted ability ("except they have '<ability>'",
#: Aggressive Biomancy) and CR 707.9b's characteristic override, unquoted -
#: "except they're `<P>`/`<T>` [`<subtype>`] creatures in addition to their
#: other types[, and they have `<ability list>`]" (Astral Dragon, Rebuild the
#: City). `_read_token_copy_except` reads either shape.
#:
#: The count reads any `numbers.COUNT` word, not only digits/a/an - Orthion,
#: Hero of Lavabrink's own "Create five tokens that are copies of another
#: target creature you control" is the reason - and the target phrase is any
#: "target ..."/"another target ..." descriptor `machines/targeting.py`
#: understands, not only "target creature you control": Astral Dragon's own
#: "target noncreature permanent" is a different restriction on the same
#: shape. CR 107.3a's announced X is substituted by `effect_for` before the
#: second parse attempt, same as before.
#:
#: Matched against the *whole*, unsplit text: an "except" tail ends in a full
#: stop of its own (the quoted-ability shape) or contains its own "and"
#: (the type/P-T shape), either of which `split_effect_clauses` would cut the
#: sentence at, leaving fragments neither of which is a clause at all.
#:
#: A trailing "Put `<n>` +1/+1 counters on it." (Applied Geometry, whose
#: "except it's a 0/0 Fractal creature in addition to its other types" would
#: otherwise die to CR 704.5f the moment it entered) is read as part of the
#: same instruction: "it" is the token just created (CR 608.2c), and the
#: counters go on before state-based actions are next checked (CR 704.3).
_CREATE_TOKEN_COPIES_EXCEPT_RE = re.compile(
    rf"^create {count_pattern('count')} tokens? "
    r"that(?: are copies|'s a copy|’s a copy| is a copy) of "
    r"(?P<phrase>(?:another )?target [^.]+?)"
    r"(?:, except (?P<except>.+?))?"
    rf"(?:\.\s*put {count_pattern('counters')} \+1/\+1 counters? on (?:it|them))?"
    # CR 508.4: Thousand-Faced Shadow's "The token enters tapped and attacking."
    rf"(?P<enters_attacking>\.\s*{_TOKEN_COPY_ENTERS_TAPPED_AND_ATTACKING})?\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: CR 707.9a's granted-ability exception, quoted - Aggressive Biomancy's own
#: "except they have 'When this token enters, it fights up to one target
#: creature you don't control.'"
_TOKEN_COPY_EXCEPT_QUOTED_RE = re.compile(
    r'^(?:they have|it has) ["“](?P<ability>.+?)["”]$', re.IGNORECASE | re.DOTALL
)

#: CR 707.9b's characteristic-override exception, unquoted - "except they're
#: `<P>`/`<T>` [`<subtype>`] creatures in addition to their other types[, and
#: they have `<ability list>`]". The subtype is optional: Astral Dragon names
#: one ("3/3 Dragon creatures"), Rebuild the City does not ("3/3 creatures" -
#: CR 205.1b's "in addition to" already keeps whatever types and subtypes the
#: copied permanent had).
_TOKEN_COPY_EXCEPT_TYPE_PT_RE = re.compile(
    # "a 0/0 Fractal creature" (Applied Geometry) prints the singular with its
    # article; "3/3 Dragon creatures" (Astral Dragon) the bare plural.
    r"^(?:they'?re|it'?s) (?:an? )?(?P<power>\d+)/(?P<toughness>\d+) "
    r"(?:(?P<subtype>[A-Za-z]+) )?creatures? in addition to (?:their|its) other types"
    r"(?:,? and (?:they|it) (?:have|has) (?P<abilities>.+))?$",
    re.IGNORECASE | re.DOTALL,
)


#: CR 707.9a's granted-ability exception, unquoted keywords - "except it has
#: haste", "except they have flying and haste".
_TOKEN_COPY_EXCEPT_KEYWORDS_RE = re.compile(
    r"^(?:it has|they have) (?P<keywords>[a-z ,]+)$", re.IGNORECASE
)

#: CR 707.9b's P/T-only exception - "except it's 1/1".
_TOKEN_COPY_EXCEPT_PT_RE = re.compile(
    r"^(?:it'?s|they'?re) (?P<power>\d+)/(?P<toughness>\d+)$", re.IGNORECASE
)


#: CR 707.9b's *replacing* characteristic exception - Croaking Counterpart's
#: "except it's a 1/1 green Frog": a set P/T, a set colour (or two), and a
#: set creature-type list, with no "in addition to its other types" - so the
#: copy's colour and creature types are exactly those named (CR 205.1a),
#: every other copiable value kept. The type words are checked against CR
#: 205.3m's creature types (`_read_token_copy_replacing_except`).
_TOKEN_COPY_EXCEPT_PT_COLOR_TYPE_RE = re.compile(
    r"^(?:they'?re|it'?s) (?:an? )?(?P<power>\d+)/(?P<toughness>\d+) "
    r"(?P<colors>(?:white|blue|black|red|green)(?: and (?:white|blue|black|red|green))?) "
    r"(?P<subtypes>[a-z][a-z'-]*(?: [a-z][a-z'-]*)*?)(?: creatures?)?$",
    re.IGNORECASE,
)


def _read_token_copy_replacing_except(
    except_text: str | None,
) -> tuple[int, int, tuple[Color, ...], tuple[str, ...]] | None:
    """`_TOKEN_COPY_EXCEPT_PT_COLOR_TYPE_RE`'s tail as `(power, toughness,
    colors, creature_types)`, or `None` when it is not that shape or names a
    word that is not a creature type."""
    if except_text is None:
        return None
    stripped = " ".join(except_text.strip().split()).rstrip(".")
    match = _TOKEN_COPY_EXCEPT_PT_COLOR_TYPE_RE.fullmatch(stripped)
    if match is None:
        return None
    vocabulary = creature_type_vocabulary()
    subtypes = tuple(word[:1].upper() + word[1:] for word in match.group("subtypes").split())
    if not subtypes or any(subtype not in vocabulary for subtype in subtypes):
        return None
    colors = tuple(
        _COLOR_WORD_TO_COLOR[word] for word in match.group("colors").lower().split(" and ")
    )
    return int(match.group("power")), int(match.group("toughness")), colors, subtypes


def _read_token_copy_except(
    except_text: str | None,
) -> tuple[tuple[str, ...], int | None, int | None, str | None] | None:
    """A token-copy clause's optional ", except `<tail>`" (CR 707.9a/707.9b),
    read into `token_copy_of`'s own `(added_abilities, power, toughness,
    added_creature_type)`. `None` only when a tail is present and neither
    `_TOKEN_COPY_EXCEPT_QUOTED_RE` nor `_TOKEN_COPY_EXCEPT_TYPE_PT_RE` reads
    it; an absent tail (`except_text` is `None`) is the plain CR 707.2 copy,
    no exception at all.
    """
    if except_text is None:
        return (), None, None, None
    # `_CREATE_TOKEN_COPIES_EXCEPT_RE`'s own trailing `\.?` is outside this
    # group, so a greedy `.+` swallows the clause's closing full stop along
    # with everything else rather than leaving it there to be matched
    # separately - stripped here once, rather than taught to both readers
    # below, so an added keyword line never carries a stray "Flying." period.
    stripped = " ".join(except_text.strip().split()).rstrip(".")
    if quoted := _TOKEN_COPY_EXCEPT_QUOTED_RE.fullmatch(stripped):
        return (quoted.group("ability").strip(),), None, None, None
    if keywords_only := _TOKEN_COPY_EXCEPT_KEYWORDS_RE.fullmatch(stripped):
        # CR 707.9a, unquoted: "except it has haste" (Kiki-Jiki, Mirror
        # Breaker; Reflection of Kiki-Jiki; Splinter Twin; Twinflame).
        keywords = split_and_validate_keywords(keywords_only.group("keywords"))
        if keywords is None:
            return None
        return (", ".join(keywords),), None, None, None
    if pt_only := _TOKEN_COPY_EXCEPT_PT_RE.fullmatch(stripped):
        # CR 707.9b: "except it's 1/1" (Offspring's Revenge; offspring's own
        # reminder shape) replaces the copiable P/T and nothing else.
        return (), int(pt_only.group("power")), int(pt_only.group("toughness")), None
    if type_pt := _TOKEN_COPY_EXCEPT_TYPE_PT_RE.fullmatch(stripped):
        abilities_text = type_pt.group("abilities")
        added = (_normalize_keyword_list(abilities_text),) if abilities_text else ()
        # "" (never `None`) when the clause names no subtype at all - Rebuild
        # the City's own "3/3 creatures", not "3/3 `<subtype>` creatures" -
        # so `token_copy_of` still adds CR 707.9b's Creature type; `None` is
        # reserved for "no type change at all" (the quoted-ability shape, or
        # no exception clause whatsoever).
        return (
            added,
            int(type_pt.group("power")),
            int(type_pt.group("toughness")),
            type_pt.group("subtype") or "",
        )
    mixed_prefix = re.match(r"^(?:it has|they have)\s+", stripped, re.IGNORECASE)
    if mixed_prefix is not None:
        # CR 707.9a's granted-ability channel, mixed keyword-then-quoted -
        # Kindle the Inner Flame's own flashback token, "except it has haste
        # and 'At the beginning of the end step, sacrifice this token.'" -
        # neither `_TOKEN_COPY_EXCEPT_QUOTED_RE` (quoted only) nor
        # `_TOKEN_COPY_EXCEPT_KEYWORDS_RE` (bare keywords only) reads this by
        # itself, but `_parse_copy_added_ability_lines` already does for
        # `_FOR_EACH_CREATURE_TARGET_PLAYER_COPY_RE`'s identical tail
        # grammar, once its own leading "it has"/"they have" (already
        # stripped off *that* regex's own capture group, but not this one's)
        # is stripped here too.
        mixed = _parse_copy_added_ability_lines(stripped[mixed_prefix.end() :])
        if mixed is not None:
            return mixed, None, None, None
    return None


@ABILITY_TEXT.rung("s15", for_spell=False)
@SPELL_TEXT.rung("s13", for_spell=True)
@MIXED_CLAUSE.rung("s23", for_spell=FORWARD)
def _parse_create_token_copies_except_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_CREATE_TOKEN_COPIES_EXCEPT_RE`'s shape, or `None` if this is not it.

    CR 707.2 is what makes the episode's answer come out right without any
    work here: "the copy acquires the copiable values of the original
    object's characteristics", and an until-end-of-turn animation is not one
    of them - so copying an animated land copies the land. `token_copy_of`
    already shares the original's printed `Card`; the exception this reads
    off `_read_token_copy_except` is CR 707.9's own channel for putting an
    "except" into those copiable values rather than granting it on top of
    them.
    """
    match = _CREATE_TOKEN_COPIES_EXCEPT_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None
    counters = 0
    if match.group("counters") is not None:
        read_counters = parse_count(match.group("counters"))
        if not read_counters:
            return None
        counters = read_counters
    colors: tuple[Color, ...] | None = None
    creature_types: tuple[str, ...] | None = None
    not_legendary = False
    replacing = _read_token_copy_replacing_except(match.group("except"))
    listed = _read_copy_exception_list(match.group("except"))
    if replacing is not None:
        power, toughness, colors, creature_types = replacing
        added: tuple[str, ...] = ()
        added_type: str | None = None
    elif listed is not None:
        added, power, toughness, added_type = (
            listed.added_abilities,
            listed.power,
            listed.toughness,
            listed.added_creature_type,
        )
        not_legendary = listed.not_legendary
    else:
        exception = _read_token_copy_except(match.group("except"))
        if exception is None:
            return None
        added, power, toughness, added_type = exception
    enters_attacking = match.group("enters_attacking") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                attacking = (
                    _token_copy_tapped_and_attacking(game, target, controller.username)
                    if enters_attacking
                    else {}
                )
                created = token_copy_of(
                    game,
                    target,
                    controller.username,
                    count=count,
                    **attacking,
                    added_abilities=added,
                    power=power,
                    toughness=toughness,
                    added_creature_type=added_type,
                    colors=colors,
                    creature_types=creature_types,
                    not_legendary=not_legendary,
                )
                if counters and created:
                    # "it" is each copy just made - not an extra token a
                    # replacement effect added beside it (`token_copy_of`
                    # appends those after the copies, on their own card).
                    copy_card = created[0].card.id
                    for token in created:
                        if token.card.id == copy_card and token.zone is Zone.BATTLEFIELD:
                            game.add_counters(token, "+1/+1", counters, putter=controller.username)

    return effect


#: Ocelot Pride: "Then if you have the city's blessing, for each token you
#: control that entered this turn, create a token that's a copy of it."
#: Templated (CR 702.131 - *ascend* and the city's blessing are both reminder
#: text the rules print on more than one card), read by shape rather than by
#: card name, so a future card with this exact sentence is covered for free.
#: `split_effect_clauses`'s "then" splitting does not strip the leading
#: "Then " off the second half of a two-sentence effect - see
#: `split_effect_clauses` - so the leading word has to be tolerated here.
_CITY_BLESSING_TOKEN_COPY_RE = re.compile(
    r"^(?:then\s+)?if you have the city's blessing,\s*"
    r"for each token you control that entered this turn,\s*"
    r"create a token that's a copy of it\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_city_blessing_token_copy_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """Ocelot Pride's second sentence, read as one instruction (CR 608.2c).

    Two things this is *not*:

    - **Not an intervening *if*** (CR 603.4, CR 608.2a). Ocelot Pride's
      intervening *if* is "if you gained life this turn", the clause
      immediately after the trigger condition itself, already pulled off by
      `abilities._parse_triggered` into `TriggeredAbility.intervening_if`
      before this text is ever seen. "If you have the city's blessing" sits
      mid-effect instead, so it is an ordinary conditional instruction,
      checked once while this half of the ability resolves in printed order -
      CR 608.2c's "the controller ... follows its instructions in the order
      written" - not rechecked as the ability leaves the stack.
    - **Not `_parse_token_clause`'s shape.** That parser refuses any clause
      naming a copy outright (CR 707.2); this is the one place in the file
      that reads a copy, through `token_copy_of` instead.

    "For each token you control that entered this turn" is read as the set of
    such tokens *at the moment this instruction starts to resolve* - the same
    once-counted convention `hangarback_dies` already uses for "for each
    +1/+1 counter on this creature" - so a copy this instruction itself
    creates is not folded back into its own count and copied again in the
    same resolution. It is a token that entered this turn in its own right,
    for the *next* time this ability resolves.

    Ability-only (`for_spell=False`): nothing in the pool prints this shape on
    a spell, and the shape depends on `AbilityOnStack.controller` and on
    `CardState.turn_entered`, neither of which a resolving spell has reason
    to consult the same way.
    """
    if for_spell:
        return None
    if not _CITY_BLESSING_TOKEN_COPY_RE.fullmatch(clause.strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability).username
        player = game.player(controller)
        if not player.has_citys_blessing:
            return
        turn_number = getattr(game.turn, "turns_taken", None)
        if turn_number is None:
            return
        entered_this_turn = [
            state
            for state in game.permanents_controlled_by(controller)
            if is_token(state) and state.turn_entered == turn_number
        ]
        for state in entered_this_turn:
            token_copy_of(game, state, controller)

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_create_tokens_equal_to_event_subject_stat_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TOKENS_EQUAL_TO_ITS_STAT_RE`'s shape read on its own, as a whole
    ability's effect - not only the "if you do" rider
    `_merge_return_self_then_if_you_do_clauses` already reads it as.

    Goldvein Hydra's own dies trigger ("When this creature dies, create a
    number of tapped Treasure tokens equal to its power.", CR 603.10a's
    look-back - Goldvein Hydra's entire power is +1/+1 counters, CR 208.1's
    printed 0/0) and Threefold Thunderhulk's "Whenever this creature enters
    or attacks, create a number of 1/1 colorless Gnome artifact creature
    tokens equal to its power." (the creature is still on the battlefield,
    so "its" reads the live, computed characteristic instead) are the same
    shape with two different trigger events.

    `event_subject_power`/`event_subject_toughness` (`machines/triggers.py`)
    read `CardState.last_known_power_toughness` off the event's own subject:
    the live characteristic while it is still a permanent, CR 608.2h's last
    known information (counters included) once it is not.

    Ability-only: nothing in the pool prints this on a spell, and there is
    no `AbilityOnStack.event` to read one off.
    """
    if for_spell:
        return None
    match = _TOKENS_EQUAL_TO_ITS_STAT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    template = _parse_token_clause(f"create a {match.group('desc')} token", for_spell=False)
    if template is None:
        return None
    read_stat = (
        event_subject_power if match.group("stat").lower() == "power" else (event_subject_toughness)
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        amount = read_stat(game, stack_object.event)
        for _ in range(max(amount or 0, 0)):
            template(game, stack_object)

    return effect


#: "create a number of `<descriptor>` tokens equal to the number of `<count>`" -
#: Hare Apparent's "... equal to the number of other creatures you control named
#: Hare Apparent." The count is any `amount_expression` term, read once as the
#: ability resolves (CR 608.2h); the "its power|toughness" form is
#: `_TOKENS_EQUAL_TO_ITS_STAT_RE`'s.
_TOKENS_EQUAL_TO_AMOUNT_RE = re.compile(
    r"^create a number of (?P<desc>.+?) tokens equal to (?P<expr>the number of .+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_create_tokens_equal_to_amount_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TOKENS_EQUAL_TO_AMOUNT_RE`'s shape, or `None`. CR 107.1b: a zero count
    creates nothing."""
    if "tokens equal to the number of" not in text:
        return None
    match = _TOKENS_EQUAL_TO_AMOUNT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    reader = amount_expression(match.group("expr"))
    template = _parse_token_clause(f"create a {match.group('desc')} token", for_spell=for_spell)
    if reader is None or template is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        controller = game.controller_of(stack_object).username
        for _ in range(reader(game, controller, source, getattr(stack_object, "x_value", 0))):
            template(game, stack_object)

    return effect


def _token_creator_for_count(
    desc: str, tail: str = ""
) -> Callable[["Game", "StackObject", int], None] | None:
    """The token half of "create a number of `<desc>` tokens equal to ...":
    the same one-token reader `_parse_token_clause` already gives "create a
    `<desc>` token" (a 1/1 red Goblin creature, a tapped Treasure, a Blood
    token - CR 111.10a/111.10g's predefined rows), run `count` times, the
    count being whatever the caller read off the rest of the sentence.
    CR 107.1b: a zero or negative count creates nothing. `tail` is what follows
    "token" in the singular clause (" with vigilance").
    """
    text = f"create a {desc.strip()} token{tail}"
    template = _parse_token_clause(text, for_spell=True)
    if template is None:
        return None
    counted = _counted_token_clause(text, for_spell=True)

    def create(game: "Game", stack_object: "StackObject", count: int) -> None:
        create_for_each(game, stack_object, template, counted, count)

    return create


#: "Target player creates a token that's a copy of target creature you
#: control." (Echocasting Symposium) - CR 111.2: the player the instruction
#: names creates the token, so that player owns and controls it; CR 707.2:
#: it copies the targeted creature's copiable values, through the same
#: `token_copy_of` (and CR 707.9 "except" reader) "create a token that's a
#: copy of ..." already uses.
_TARGET_PLAYER_CREATES_TOKEN_COPY_RE = re.compile(
    rf"^(?P<player>target (?:player|opponent)) creates? {count_pattern('count')} tokens? "
    r"that(?: are copies|['’]s a copy| is a copy) of "
    r"(?P<phrase>(?:another )?target [^.]+?)"
    r"(?:, except (?P<except>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_target_player_creates_token_copy_clause(clause: str) -> TargetedClause | None:
    """`_TARGET_PLAYER_CREATES_TOKEN_COPY_RE`'s shape, or `None`."""
    match = _TARGET_PLAYER_CREATES_TOKEN_COPY_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("player"), allow_player_targets=True):
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None
    exception = _read_token_copy_except(match.group("except"))
    if exception is None:
        return None
    added, power, toughness, added_type = exception

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = game.resolve_targets(stack_object)
        creators = [target for target in targets if isinstance(target, Player)]
        originals = [target for target in targets if isinstance(target, CardState)]
        for creator in creators:
            for original in originals:
                token_copy_of(
                    game,
                    original,
                    creator.username,
                    count=count,
                    added_abilities=added,
                    power=power,
                    toughness=toughness,
                    added_creature_type=added_type,
                )

    return effect


@MIXED_CLAUSE.rung("s12")
def _parse_target_player_creates_clause(clause: str) -> TargetedClause | None:
    """ "Target player/opponent creates `<token>`" as one clause of a longer
    effect - Emeritus of Truce's "target player creates a 1/1 white and black
    Inkling creature token with flying. Then if an opponent controls more
    creatures than you, this creature becomes prepared." The token phrase is
    `_parse_target_player_creates_token`'s own (CR 111.2), and a copy is
    `_parse_target_player_creates_token_copy_clause`'s; this only lets
    either sit beside other clauses instead of being the whole text."""
    copy = _parse_target_player_creates_token_copy_clause(clause)
    if copy is not None:
        return copy
    return _parse_target_player_creates_token(clause)  # type: ignore[return-value]


#: Frontline Heroism's own cast trigger effect: "create a `<token>`, then
#: copy that spell. The copy targets that token." The token half is
#: `_TOKEN_CLAUSE_RE`'s ordinary shape (any generic token descriptor - this
#: is not hardcoded to "1/1 red Soldier ... with haste"), and the copy half
#: is CR 707.10's `Game.copy_spell` the same way Alania, Divergent Storm's
#: own clause above already reaches it - the difference is the retarget: "the
#: copy targets that token" is not CR 707.10c's optional "you may choose new
#: targets", it is a forced, specific new target, so `copy.targets` is set
#: directly rather than through `offer_new_targets_for_copy`.
_CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE = re.compile(
    r"^(?P<token_clause>.+?tokens?(?:\s+with\s+.+?)?), then copy that spell\. "
    r"the copy targets? that token\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s35")
def _parse_create_token_then_copy_spell_retargeted_clause(text: str) -> AbilityEffect | None:
    """`_CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE`'s shape, or `None` if
    this is not it, or if the token half is not `_TOKEN_CLAUSE_RE`'s own
    readable shape.
    """
    match = _CREATE_TOKEN_THEN_COPY_SPELL_RETARGETED_RE.fullmatch(text.strip())
    if match is None:
        return None
    token_text = match.group("token_clause").strip()
    if not token_text.lower().startswith("create"):
        token_text = "create " + token_text
    token_match = _TOKEN_CLAUSE_RE.fullmatch(token_text)
    if token_match is None:
        return None
    count = parse_count(token_match.group("n"))
    words = token_match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, token_match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        tokens = create_tokens(game, definition, controller, count, tapped=tapped)
        event = ability.event
        if event is None or event.subject_id is None or not tokens:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        # CR 707.10e: "the copy targets that token" specifies the copy's own
        # new target rather than offering CR 707.10c's optional "you may
        # choose new targets" permission, so `copy_spell_targeting` (not
        # `offer_new_targets_for_copy`) is the one that applies - it builds
        # the copy only if the token is a legal target for every instance of
        # "target" on the spell, and creates nothing at all otherwise.
        game.copy_spell_targeting(spell, controller, tokens[0])

    return effect


# --------------------------------------------------------------------------
# Tokens created already attacking (CR 508.4)
# --------------------------------------------------------------------------
#
# Parhelion II's own attack trigger: "create two 4/4 white Angel creature
# tokens with flying and vigilance that are attacking." CR 508.4: "If a
# creature is put onto the battlefield attacking, its controller chooses
# which defending player ... it's attacking", and CR 508.4c adds that such a
# creature "isn't affected by requirements or restrictions that apply to the
# declaration of attackers" - it was never declared.
#
# The defender is not printed anywhere on the card, so it is read off the
# attack this trigger's own controller has already declared: this is an
# "whenever [this] attacks" trigger (CR 508.3a), so by the time it resolves
# there is a real attack of theirs to join. That is exactly the reading
# `_parse_attack_this_turn_create_tapped_attacking_tokens` already takes for
# Dalkovan Encampment's own tokens, reused here rather than reargued.
#
# Unlike Dalkovan's, these tokens are **not** tapped: the printed text says
# only "that are attacking", and CR 508.4 does not tap what it puts onto the
# battlefield attacking (only CR 508.1f taps a creature actually declared as
# an attacker).

_ATTACKING_TOKEN_CLAUSE_RE = re.compile(
    rf"^(?:create )?(?P<n>{COUNT}) (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?"
    r"\s+that (?:are|is) attacking\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s31", for_spell=False)
@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_attacking_token_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_ATTACKING_TOKEN_CLAUSE_RE`'s shape - Parhelion II's own attack
    trigger. The token itself is read by the same
    `_parse_generic_token_descriptor`/`_parse_token_tail` pair every other
    token clause in this file uses, so a tail this file cannot read still
    fails the whole clause closed rather than creating a token missing its
    keywords (CR 608.2c).
    """
    match = _ATTACKING_TOKEN_CLAUSE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if "copy of" in clause.lower():
        return None  # CR 707.2 copying needs copiable values this file does not read.
    count = parse_count(match.group("n"))
    if count is None:
        return None
    words = match.group("desc").strip().split()
    tapped = bool(words) and words[0].lower() == "tapped"
    if tapped:
        words = words[1:]
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        defender = _defender_of_controllers_attack(game, controller)
        create_tokens(game, definition, controller, count, tapped=tapped, attacking=defender)

    return effect


#: The Last Ronin's Technique's own body: "Create three 1/1 white Ninja
#: Turtle Spirit creature tokens. If this spell's sneak cost was paid, they
#: enter tapped and attacking." CR 702.190b's own second sentence, extended
#: past the sneak spell *itself* becoming a tapped, attacking permanent to
#: tokens a resolving *non*-permanent spell with sneak creates - "the same
#: player, planeswalker, or battle as the creature that was returned to its
#: owner's hand to pay the sneak cost" is `CastRecord.sneak_defender`, read
#: here the identical way `Game._sneak_defender_of` reads it for the spell's
#: own permanent case, off `Game.cast_record(spell)` directly (this file
#: already reaches into `Game`'s own private surface everywhere else it
#: needs a fact only `Game` keeps).
#:
#: The condition is read generally, through `Game.condition_holds`, the same
#: as every other "if `<cost>` was paid" rider in this file - only *which*
#: defender the tokens join is CR 702.190b-specific, since sneak is the only
#: alternative cost in this pool that records one at all.
_CREATE_TOKENS_THEN_INSTEAD_TAPPED_ATTACKING_IF_COST_PAID_RE = re.compile(
    r"^(?P<token>create .+?\btokens?\b(?:\s+with\s+.+?)?)\.\s*"
    r"if (?P<condition>this spell's [a-z][a-z-]* cost was paid), "
    r"they enter tapped and attacking\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s8")
def _parse_create_tokens_then_instead_tapped_attacking_if_cost_paid_clause(
    text: str,
) -> Effect | None:
    """`_CREATE_TOKENS_THEN_INSTEAD_TAPPED_ATTACKING_IF_COST_PAID_RE`'s shape.

    Spell-only: `CastRecord.sneak_defender` is recorded against the spell's
    own cast, which only a resolving spell - never an ability - carries a
    record of at all.
    """
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _CREATE_TOKENS_THEN_INSTEAD_TAPPED_ATTACKING_IF_COST_PAID_RE.fullmatch(whole)
    if match is None:
        return None
    token_match = _TOKEN_CLAUSE_RE.fullmatch(match.group("token").strip())
    if token_match is None:
        return None
    count = parse_count(token_match.group("n"))
    if count is None:
        return None
    words = token_match.group("desc").strip().split()
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, token_match.group("tail"))
    if definition is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        held = game.condition_holds(controller, condition_text, spell)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=spell.id, source_name=spell.card.name, text=whole
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        defender = game.cast_record(spell).sneak_defender if held else None
        create_tokens(
            game, definition, controller, count, tapped=defender is not None, attacking=defender
        )

    return effect


# --------------------------------------------------------------------------
# Witch's Oven: a count that depends on what paid the cost
# --------------------------------------------------------------------------
#
# "{T}, Sacrifice a creature: Create a Food token. If the sacrificed
# creature's toughness was 4 or greater, create two Food tokens instead."
#
# The creature is gone before the ability is even on the stack (CR 602.2b's
# activation pays the costs), so its toughness has to be read off the object
# the payment recorded - `AbilityOnStack.cost_sacrificed_card_ids`, the
# sacrifice twin of the `cost_exiled_card_id` Back from the Brink already
# needed for exactly the same reason. "Was" in the printed text is the
# tell: the sentence is asking about a permanent that no longer exists.
#
# CR 111.10b defines the Food token, so `PREDEFINED` supplies it rather than
# a noun phrase read off the card.

_CONDITIONAL_TOKEN_COUNT_ON_SACRIFICED_RE = re.compile(
    rf"^create (?P<n>{COUNT}) (?P<desc>.+?) tokens?\.\s*"
    r"if the sacrificed creature'?s (?P<attribute>power|toughness) was "
    rf"(?P<threshold>\d+) or greater, create (?P<n2>{COUNT}) (?P<desc2>.+?) tokens? instead\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s32")
def _parse_conditional_token_count_on_sacrificed(text: str) -> AbilityEffect | None:
    """`_CONDITIONAL_TOKEN_COUNT_ON_SACRIFICED_RE`'s shape - Witch's Oven.

    "Instead" is a substitution, not an addition: exactly one of the two
    counts happens (CR 608.2c's "later text on the card may modify the
    meaning" of an earlier instruction). The two token descriptions have to
    name the same token, since a card that swapped the token as well as the
    count would need reading this parser does not do; a mismatch fails the
    whole clause closed.

    The sacrificed permanent's toughness is the printed one on the recorded
    card. `Game.toughness_of` would need it on the battlefield, and it is
    deliberately not - CR 400.7 has already made it a new object in a
    graveyard, whose only characteristics are printed ones.
    """
    match = _CONDITIONAL_TOKEN_COUNT_ON_SACRIFICED_RE.fullmatch(text.strip())
    if match is None:
        return None
    if match.group("desc").strip().lower() != match.group("desc2").strip().lower():
        return None
    base = parse_count(match.group("n"))
    boosted = parse_count(match.group("n2"))
    if base is None or boosted is None:
        return None
    name = match.group("desc").strip()
    definition = PREDEFINED.get(name) or _parse_generic_token_descriptor(name.split(), None)
    if definition is None:
        return None
    attribute = match.group("attribute").lower()
    threshold = int(match.group("threshold"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability).username
        count = base
        for card_id in ability.cost_sacrificed_card_ids:
            sacrificed = game.find_by_id(card_id)
            if sacrificed is None:
                continue
            printed = (
                sacrificed.card.toughness if attribute == "toughness" else sacrificed.card.power
            )
            # Scryfall prints power and toughness as strings, and a card whose
            # own is `*` has no number to compare at all - CR 208.2's
            # characteristic-defining value is worked out from the game state,
            # which a card in a graveyard is no longer part of. Unreadable
            # counts as "not 4 or greater" rather than raising.
            value = int(printed) if printed is not None and printed.lstrip("-").isdigit() else None
            if value is not None and value >= threshold:
                count = boosted
                break
        create_tokens(game, definition, controller, count)

    return effect


#: "target opponent creates The Void, a legendary 5/5 black Horror Villain
#: creature token with flying, indestructible, and "The Void attacks each
#: combat if able."" (The Sentry, Golden Guardian); "target opponent creates
#: two 3/3 green Centaur creature tokens with protection from black." (Hunted
#: Horror) - CR 111.2: the player the instruction names creates the token, so
#: that player owns and controls it. The token phrase is read by the same
#: named (CR 111.4 appositive) and counted token readers "create" already
#: uses. The subject may also be a group - "each opponent creates five 2/2
#: black Zombie creature tokens" (Captive Audience), "each player creates a
#: Food token" (Party Dude) - and then every player in the group creates the
#: tokens for themself, in turn order from the ability's controller.
_TARGET_PLAYER_CREATES_RE = re.compile(
    r"^(?P<subject>target (?:player|opponent)|each opponent|each player) creates? (?P<phrase>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_target_player_creates_token(text: str) -> AbilityEffect | None:
    """`_TARGET_PLAYER_CREATES_RE`'s shape, or `None`."""
    match = _TARGET_PLAYER_CREATES_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    if "copy of" in phrase.lower():
        return None
    if phrase.endswith(".") and not phrase.endswith(('."', ".”")):
        phrase = phrase[:-1].rstrip()
    definition: TokenDefinition | None = None
    count = 1
    tapped = False
    named = _NAMED_TOKEN_CLAUSE_RE.fullmatch(f"create {phrase}")
    if named is not None and named.group("name")[:1].isupper():
        definition = _parse_generic_token_descriptor(
            named.group("desc").strip().split(), named.group("tail")
        )
        if definition is None:
            return None
        definition = definition.model_copy(update={"name": named.group("name").strip()})
    else:
        counted = _TARGET_PLAYER_TOKEN_RE.fullmatch(
            _fold_following_token_grant(f"target player creates {phrase}")
        )
        if counted is None:
            return None
        count = parse_count(counted.group("n")) or 0
        words = counted.group("desc").strip().split()
        tapped = bool(words) and words[0].lower() == "tapped"
        if tapped:
            words = words[1:]
        if not words or not count:
            return None
        definition = _token_definition_from_words(" ".join(words), counted.group("tail"))
        if definition is None:
            return None
    token = definition
    subject = match.group("subject").lower()

    def creators(game: "Game", ability: AbilityOnStack) -> list[str]:
        controller = game.controller_of(ability).username
        if subject == "each opponent":
            return [player.username for player in _opponents(game, controller)]
        if subject == "each player":
            return [player.username for player in game.players_in_game]
        return [t.username for t in game.resolve_targets(ability) if isinstance(t, Player)]

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for username in creators(game, ability):
            create_tokens(game, token, username, count, tapped=tapped)

    return effect


# --------------------------------------------------------------------------
# "Choose target <X>, then roll a d20." and its results table (CR 706.2)
# --------------------------------------------------------------------------

_DIE_TABLE_TOKEN_COPY_RE = re.compile(
    r"^choose (?P<phrase>target [a-z]+(?: you control)?), then roll an? d(?P<sides>\d+)\.\s*"
    r"(?P<low_from>\d+)\s*[-–—]\s*(?P<low_to>\d+)\s*\|\s*"
    r"create an? tapped and attacking token that['’]?s a copy of that [a-z]+"
    r"(?:, except (?P<except>[^|]+?))?\.?\s*"
    r"(?P<high_from>\d+)\s*[-–—]\s*(?P<high_to>\d+)\s*\|\s*"
    r"create one of those tokens\.\s*you may roll again\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_die_table_tapped_attacking_token_copies(text: str) -> AbilityEffect | None:
    """Delina, Wild Mage's template: the chosen creature is copied once as a
    tapped and attacking token (CR 508.4, CR 707.9) on a low roll, and on a
    high roll once more with an optional re-roll - which is read through the
    same table again (CR 706.2). The two ranges must split the die exactly, so
    a table that leaves a result without an outcome is not read."""
    if "|" not in text:
        return None
    match = _DIE_TABLE_TOKEN_COPY_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or not _targets_understood(match.group("phrase")):
        return None
    sides = int(match.group("sides"))
    low = (int(match.group("low_from")), int(match.group("low_to")))
    high = (int(match.group("high_from")), int(match.group("high_to")))
    if low[0] != 1 or high[0] != low[1] + 1 or high[1] != sides:
        return None
    options: dict[str, Any] = {}
    exception = match.group("except")
    if exception is not None:
        listed = _read_copy_exception_list(exception)
        if listed is None:
            return None
        options = {
            "added_abilities": listed.added_abilities,
            "power": listed.power,
            "toughness": listed.toughness,
            "added_creature_type": listed.added_creature_type,
            "not_legendary": listed.not_legendary,
        }
    high_from = high[0]

    def effect(game: "Game", ability: "StackObject") -> None:
        controller = game.controller_of(ability)
        (original, *_) = [t for t in game.resolve_targets(ability) if isinstance(t, CardState)] or [
            None
        ]
        if original is None:
            return
        while True:
            (rolled,) = game.roll_dice(controller, sides)
            token_copy_of(
                game,
                original,
                controller.username,
                **_token_copy_tapped_and_attacking(game, original, controller.username),
                **options,
            )
            if rolled < high_from:
                return
            if not game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=controller.username,
                    prompt=f"roll a d{sides} again (CR 706.2)",
                    source=getattr(ability, "source_name", None),
                    source_id=source_id_of(ability),
                )
            ):
                return

    return effect


from ._common import (  # noqa: E402
    _ANAPHOR_GAINS_KEYWORDS_RE,
    _COLOR_WORD_TO_COLOR,
    _OBJECT_ANAPHOR_RE,
    _ONE_PERMANENT,
    _QUOTED_SPAN_RE,
    _TOKEN_CLAUSE_RE,
    _TOKEN_COLOR_WORDS,
    _TOKEN_KEYWORDS,
    _TOKENS_EQUAL_TO_ITS_STAT_RE,
    _WHERE_X_IS_INLINE_RE,
    _YOU_MAY_RE,
    ConditionalClauseNotice,
    _effect_condition_is_readable,
    _opponents,
    _parse_delayed_timing_clause,
    _permanent_id_and_name,
    _quality_matcher,
    _SacrificeRestriction,
    _targets_understood,
    computed_permanents,
)
from .amounts import (  # noqa: E402
    _fixed_or_where_x_amount,
    _for_each_multiplier,
    _x_sized_token_clause,
    _x_substituted_spell_text,
    amount_expression,
    color_pip_count_named_by_trigger,
    count_expression,
)
from .continuous import (  # noqa: E402
    _defender_of_controllers_attack,
    _grant_keywords_to,
    attach_permanent,
    continuous_effects,
    layer_context_for,
)
from .control_copy import (  # noqa: E402
    _armies_controlled_by,
    _parse_copy_added_ability_lines,
    _read_copy_exception_list,
)
from .counters import _counter_kind  # noqa: E402
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_mixed_clauses,
    _spell_effect_or_notice,
    parse_mixed_effect,
)
from .library import _mill  # noqa: E402
from .mana import _cast_trigger_mana_spent_x_ability_text  # noqa: E402
from .modal import _choose_permanents_to_sacrifice, _optional_targeted_clause  # noqa: E402
from .registries import trigger_effect_for  # noqa: E402
from .search import _search_quality_is_readable  # noqa: E402
from .text import (  # noqa: E402
    _as_sentence,
    _has_period_outside_quotes,
    _normalize_keyword_list,
    _parse_referent_object_clause,
    _plain_resolution_sentences,
    _singular_subtype_for_amass,
    _split_created_trigger_paragraph,
    _strip_non_effect_preamble,
)

#: "Create a 1/1 creature token of the chosen color and type." (Sarpadian
#: Empires, Vol. VII) - the token is described by the source's as-enters
#: answer (CR 614.12a), "white Citizen" for "choose white Citizen, blue
#: Camarid, ...", so the sentence is read with that answer written in.
_CHOSEN_COLOR_AND_TYPE_TOKEN_RE = re.compile(
    r"^create (?P<count>an?|one|two|three|four|five) (?P<pt>\d+/\d+) creature tokens? "
    r"of the chosen color and type\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_chosen_color_and_type_token_text(text: str) -> AbilityEffect | None:
    """`_CHOSEN_COLOR_AND_TYPE_TOKEN_RE`'s shape, read whole (the clause
    splitter would cut "color and type" at its "and"). The answer is read at
    resolution; a source with no "<color> <type>" answer creates nothing."""
    if "the chosen color and type" not in text.lower():
        return None
    match = _CHOSEN_COLOR_AND_TYPE_TOKEN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = match.group("count").lower()
    plural = count not in ("a", "an", "one")
    pt = match.group("pt")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.source(game)  # type: ignore[union-attr]
        choice = None if source is None else source.choice
        if choice is None or len(choice.value.split()) < 2:
            return
        noun = "creature tokens" if plural else "creature token"
        lead = count if plural else "a"
        text = f"Create {lead} {pt} {choice.value} {noun}."
        inner = _ability_effect_or_notice(text)
        if inner is not None and not _is_notice_only(inner):
            inner(game, stack_object)  # type: ignore[arg-type]

    return effect
