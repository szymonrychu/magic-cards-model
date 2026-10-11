"""Layer 6 keyword grants (CR 613.1f) to a group filtered on combat state
(CR 508.1k, "attacking") rather than the token status `machines/layers.
AttackingTokensControlledBy` already covers.

"Attacking creatures you control have double strike." (Raphael, the
Nightwatcher) and "Attacking Ninjas you control have deathtouch." (Dark Leo &
Shredder) are the same shape either way: a keyword granted right now to
whichever of the controller's own creatures - optionally narrowed to a
printed subtype list, CR 205.3m - are attacking at this moment. CR 508.1k's
attacking status is not a characteristic and never reaches the board, so
`AttackingGroupControlledBy` (`machines/layers.py`) reads it fresh off
`LayerContext.attacking` on every computation (CR 613.5): a creature stops
being selected the instant it is removed from combat (CR 506.4), and the
grant never lingers past that.

Double strike matters only "as the combat damage step begins" (CR 702.4b):
this file grants no more than an ordinary layer-6 ability, and it is the
combat machinery that already reads a creature's *current* keywords at that
moment, so nothing here has to special-case the timing itself. Deathtouch
(CR 702.2b) is likewise read live, off the same computed characteristics, at
whatever moment the game actually checks it.

Both regexes are read by `machines/layers._parse_layer_sentence`, imported
there lazily (inside the function, not at module scope) to avoid a cycle -
this module imports the selector and a handful of small helpers *from*
`layers.py` at module scope, so `layers.py` cannot import this module back at
its own module scope without a loop.
"""

import re
from collections.abc import Sequence

from ..models.card_state import CardState
from .combat import _parse_creature_description
from .layers import (
    AttackingGroupControlledBy,
    ContinuousEffect,
    CreaturesControlledByQuality,
    EffectBuilder,
    Layer,
    LayerContext,
    TappedCreaturesControlledBy,
    _source_line_for,
    _split_and_validate_keywords,
    grant_ability,
)
from .layers.model import grant_keyword
from .triggers import _parse_subtype_list

#: "Attacking creatures you control have double strike[, deathtouch, ...]."
#: The generic, case-insensitive "creatures" subject - no subtype filter at
#: all, every creature the controller attacks with.
_ATTACKING_CREATURES_KEYWORD_GRANT_RE = re.compile(
    r"^attacking creatures you control have (?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$",
    re.IGNORECASE,
)

#: "Attacking `<Subtype[, Subtype, or Subtype]>`s you control have
#: `<keyword[, keyword, and keyword]>`." (Dark Leo & Shredder's own
#: "Ninjas"; Crossway Troublemakers' own "Vampires", verified Modern/
#: Pioneer/Standard legal - "have deathtouch and lifelink", a two-keyword
#: proof of generality on a second printing). Matched **case-sensitively**
#: against the sentence as printed - Oracle's own capitalisation is what
#: tells a subtype word from an ordinary lowercase adjective, the identical
#: convention `_parse_subtype_list`'s own callers already rely on - so this
#: is tried only after the all-lowercase "creatures" shape above has already
#: declined.
#:
#: Each word is matched **non-greedily** (`[A-Za-z]*?`) so the trailing plural
#: `s?` outside the group is what consumes "Ninjas"'s own final letter,
#: leaving `_parse_subtype_list` the singular "Ninja" it expects
#: (`_parse_subtype_list`'s own docstring: it does not strip a plural
#: itself). A greedy word class would swallow that "s" into the captured
#: text instead, handing the reader "Ninjas" - a word `canonical_subtype`
#: never recognises - and the grant would parse clean but select nothing.
_ATTACKING_SUBTYPE_KEYWORD_GRANT_RE = re.compile(
    r"^Attacking (?P<subtypes>[A-Z][A-Za-z]*?(?:,\s*[A-Z][A-Za-z]*?)*"
    r"(?:,?\s+or\s+[A-Z][A-Za-z]*?)?)s? "
    r"you control have (?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$"
)


def _attacking_group_keyword_grant_builder(
    keywords: list[str], *, subtypes: tuple[str, ...], line: str
) -> EffectBuilder:
    """One `ContinuousEffect` per granted keyword, each selecting the
    controller's own currently-attacking creatures (optionally narrowed to
    `subtypes`) fresh at every computation - see this module's own docstring
    for why the selector, not this builder, is what re-reads combat state."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = AttackingGroupControlledBy(
            username=source.controller,
            attacking_ids=tuple(sorted(context.attacking, key=str)),
            subtypes=subtypes,
        )
        group = "attacking creatures" if not subtypes else f"attacking {'/'.join(subtypes)}s"
        return [
            ContinuousEffect(
                description=f"{source.name}: {group} you control have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def parse_attacking_group_keyword_grant(sentence: str) -> EffectBuilder | None:
    """Either of this module's two shapes, or `None` if `sentence` is
    neither. Tried by `machines/layers._parse_layer_sentence`."""
    match = _ATTACKING_CREATURES_KEYWORD_GRANT_RE.fullmatch(sentence)
    if match is not None:
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _attacking_group_keyword_grant_builder(keywords, subtypes=(), line=sentence)
    match = _ATTACKING_SUBTYPE_KEYWORD_GRANT_RE.fullmatch(sentence)
    if match is not None:
        subtypes = _parse_subtype_list(match.group("subtypes"))
        if subtypes is None:
            return None
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _attacking_group_keyword_grant_builder(keywords, subtypes=subtypes, line=sentence)
    return None


# --------------------------------------------------------------------------
# Tapped-status group keyword grants (CR 110.5) - the tapped/untapped twin of
# this module's own attacking-status grant just above.
# --------------------------------------------------------------------------
#
# "Other tapped creatures you control have indestructible." (Adept
# Watershaper) is CR 110.5's physical tapped status, not a characteristic
# `Characteristics` carries any more than CR 508.1k's attacking status is -
# `TappedCreaturesControlledBy` (`machines/layers.py`) reads a snapshot of
# tapped ids off `LayerContext.tapped_ids` the identical way `AttackingGroup
# ControlledBy` reads `LayerContext.attacking`, rebuilt on every CR 613.5
# computation so a creature stops being selected the instant it untaps.

#: "Other tapped creatures you control have indestructible[, deathtouch,
#: ...]." - the generic "creatures" subject, every one of the controller's
#: own tapped creatures except the source itself. "Other" is not optional
#: here (unlike the attacking-status sibling's plain "attacking creatures"):
#: every printing of this template excludes the source, since the source
#: itself is usually the thing being kept safe from the group's own effect
#: (Adept Watershaper wants indestructible on its *teammates*, not on
#: itself, which never taps to earn it).
#: The Seriema's "Other tapped legendary creatures you control have
#: indestructible." narrows the same group by the legendary supertype
#: (CR 205.4a).
_TAPPED_CREATURES_KEYWORD_GRANT_RE = re.compile(
    r"^other tapped (?P<legendary>legendary )?creatures you control (?:have|has) "
    r"(?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$",
    re.IGNORECASE,
)


def _tapped_group_keyword_grant_builder(
    keywords: list[str], *, line: str, legendary: bool = False
) -> EffectBuilder:
    """One `ContinuousEffect` per granted keyword, selecting the controller's
    own currently-tapped creatures (the source excluded) fresh at every
    computation - see this module's own docstring for why the selector, not
    this builder, is what re-reads tap status."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = TappedCreaturesControlledBy(
            username=source.controller,
            tapped_ids=tuple(sorted(context.tapped_ids, key=str)),
            excludes_self=True,
            source_id=source.id,
            legendary=legendary,
        )
        group = "legendary creatures" if legendary else "creatures"
        return [
            ContinuousEffect(
                description=f"{source.name}: other tapped {group} you control have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def parse_tapped_group_keyword_grant(sentence: str) -> EffectBuilder | None:
    """`_TAPPED_CREATURES_KEYWORD_GRANT_RE`'s shape, or `None`. Tried by
    `machines/layers._parse_layer_sentence`."""
    match = _TAPPED_CREATURES_KEYWORD_GRANT_RE.fullmatch(sentence)
    if match is None:
        return None
    keywords = _split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None
    return _tapped_group_keyword_grant_builder(
        keywords, line=sentence, legendary=match.group("legendary") is not None
    )


# -- self "can't attack/block unless ...", "alone" and "attacks each combat
#    unless ..." restrictions (CR 508.1c, 509.1b, 508.1d, 506.5) --------------

_SELF_UNLESS_RE = re.compile(
    r"^(?P<subject>.+?) can't (?P<what>attack or block|attack|block)"
    r"(?: (?P<alone>alone)| unless (?P<cond>.+?))?\.?$",
    re.IGNORECASE,
)
_GREATER_POWER_COND_RE = re.compile(
    r"^an?(?: other)? creatures? with greater power also (?P<verb>attacks|blocks)$", re.IGNORECASE
)
_REQUIREMENT_UNLESS_RE = re.compile(
    r"^(?P<subject>.+?) attacks each combat if able unless (?P<cond>.+?)\.?$", re.IGNORECASE
)
_MAX_SPEED_RE = re.compile(r"^you have max speed$", re.IGNORECASE)
_EVEN_COUNTERS_RE = re.compile(r"^it has an even number of counters on it$", re.IGNORECASE)
_ONE_ONE_RE = re.compile(r"^you control an? (?P<p>\d+)/(?P<t>\d+) creature$", re.IGNORECASE)
_PAY_COND_RE = re.compile(r"^you (?:pay|return) ", re.IGNORECASE)
_DEFENDING_REWRITES = (
    (re.compile(r"^defending player controls ", re.IGNORECASE), "you control "),
    (re.compile(r"^defending player is ", re.IGNORECASE), "you are "),
    (re.compile(r"^defending player has ", re.IGNORECASE), "you have "),
)


def _defender_form(condition: str) -> str | None:
    """ "defending player controls an Island" as the same condition about "you"
    (to be asked of the defending player), or None when it is not one."""
    for pattern, replacement in _DEFENDING_REWRITES:
        if pattern.match(condition):
            rewritten = pattern.sub(replacement, condition)
            return rewritten.replace("their graveyard", "your graveyard").replace(
                "their hand", "your hand"
            )
    return None


_PAIRED_SOULBOND_RE = re.compile(r"it's paired with a creature with soulbond", re.IGNORECASE)


def _condition_readable(condition: str) -> bool:
    from ..models.game._conditions import condition_is_readable

    text = condition.strip().rstrip(".")
    rewritten = _defender_form(text)
    if rewritten is not None:
        return condition_is_readable(rewritten)
    return bool(
        _PAIRED_SOULBOND_RE.fullmatch(text)
        or _MAX_SPEED_RE.fullmatch(text)
        or _EVEN_COUNTERS_RE.fullmatch(text)
        or _ONE_ONE_RE.fullmatch(text)
        or condition_is_readable(text)
    )


def _condition_holds(game, creature, defender, condition: str) -> bool | None:
    """Whether `condition` holds for `creature` now, or None when unread."""
    from . import speed
    from .combat import defending_player

    text = condition.strip().rstrip(".")
    controller = game.controller_of(creature).username or ""
    rewritten = _defender_form(text)
    if rewritten is not None:
        if defender is None:
            return None
        defending = defending_player(game, defender)
        return None if defending is None else game.condition_holds(defending, rewritten, creature)
    if _MAX_SPEED_RE.fullmatch(text):
        return speed.has_max_speed(game.player(controller))
    if _EVEN_COUNTERS_RE.fullmatch(text):
        return sum(game.characteristics_of(creature).counters.values()) % 2 == 0
    if one := _ONE_ONE_RE.fullmatch(text):
        board = game.computed_board()
        return any(
            board.of(permanent).is_creature
            and board.of(permanent).power == int(one["p"])
            and board.of(permanent).toughness == int(one["t"])
            for permanent in game.permanents_controlled_by(controller)
        )
    if _PAIRED_SOULBOND_RE.fullmatch(text):
        from .soulbond import paired_with_soulbond

        return paired_with_soulbond(game, creature)
    return game.condition_holds(controller, text, creature)


def _self_sentences(game, creature):
    """(sentence, match) for each of this creature's own "can't attack/block"
    sentences, ability word stripped, on the computed board (CR 613.5)."""
    from .combat import (
        _computed_ability_sentences,
        _self_reference_alternatives,
        strip_ability_word,
    )

    subjects = {name.lower() for name in _self_reference_alternatives(creature)}
    for raw in _computed_ability_sentences(creature, game):
        sentence = strip_ability_word(raw).strip()
        match = _SELF_UNLESS_RE.fullmatch(sentence)
        if match is not None and match["subject"].strip().lower() in subjects:
            yield sentence, match


def _condition_refusal(game, creature, defender, action: str) -> str | None:
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for sentence, match in _self_sentences(game, creature):
        if action not in match["what"].lower().split(" or ") or match["cond"] is None:
            continue
        if _PAY_COND_RE.match(match["cond"]) or _GREATER_POWER_COND_RE.fullmatch(match["cond"]):
            continue
        if _condition_holds(game, creature, defender, match["cond"]) is False:
            return f'{creature.name} can\'t {action}: "{sentence}" - that is not so now ({rule})'
    return None


def self_attack_condition_refusal(game, creature, defender) -> str | None:
    return self_owner_attack_refusal(game, creature, defender) or _condition_refusal(
        game, creature, defender, "attack"
    )


def self_block_condition_refusal(game, blocker, attacker) -> str | None:
    return _condition_refusal(game, blocker, None, "block")


def _declaration_refusal(game, members, action: str) -> str | None:
    """`members`: every creature declared as an `action` (attacker/blocker),
    in the declaration. "Alone" and "a creature with greater power also"
    are facts about the whole declaration (CR 506.5, CR 508.1c, CR 509.1b)."""
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for creature in members:
        for sentence, match in _self_sentences(game, creature):
            if action not in match["what"].lower().split(" or "):
                continue
            others = [other for other in members if other.id != creature.id]
            if match["alone"] is not None and not others:
                return f'{creature.name} can\'t {action} alone: "{sentence}" ({rule}, CR 506.5)'
            greater = match["cond"] and _GREATER_POWER_COND_RE.fullmatch(match["cond"])
            if greater is not None and match["cond"]:
                mine = game.power_of(creature)
                if not any(
                    (power := game.power_of(other)) is not None
                    and mine is not None
                    and power > mine
                    for other in others
                ):
                    return (
                        f'{creature.name} can\'t {action}: "{sentence}" - no creature with '
                        f"greater power {action}s with it ({rule})"
                    )
    return None


def self_attack_declaration_refusal(game, attacks) -> str | None:
    """`attacks` is `[(creature, defender)]`, the whole declaration."""
    return _declaration_refusal(game, [creature for creature, _defender in attacks], "attack")


def self_block_declaration_refusal(game, declared) -> str | None:
    """`declared` maps attacker id to its blockers, the whole declaration."""
    blockers = [blocker for group in declared.values() for blocker in group]
    return _declaration_refusal(game, blockers, "block")


# A creature's own compound sentence, "Alexios attacks each combat if able,
# can't be sacrificed, and can't attack its owner." - each clause is its own
# rule: CR 508.1d's requirement, CR 701.21a's sacrifice (CR 101.2: "can't"
# wins), CR 508.1c's restriction.
_REQUIRES_CLAUSE = "attacks each combat if able"
_NO_SACRIFICE_CLAUSE = "can't be sacrificed"
_NOT_OWNER_CLAUSE = "can't attack its owner"
_COMPOUND_CLAUSES = frozenset({_REQUIRES_CLAUSE, _NO_SACRIFICE_CLAUSE, _NOT_OWNER_CLAUSE})
_CLAUSE_SPLIT_RE = re.compile(r",\s*(?:and\s+)?|\s+and\s+", re.IGNORECASE)


def compound_clauses(sentence: str, subjects) -> frozenset[str] | None:
    """The clauses of a compound self sentence made only of the three above
    (at least two of them, or "can't be sacrificed" alone), or None."""
    text = sentence.strip().rstrip(".")
    for subject in sorted(subjects, key=len, reverse=True):
        lead = subject.lower() + " "
        if not text.lower().startswith(lead):
            continue
        parts = [part.strip().lower() for part in _CLAUSE_SPLIT_RE.split(text[len(lead) :])]
        # One clause is enough only for "can't be sacrificed": the other two
        # are read as single sentences elsewhere, and a granted "This token
        # can't be sacrificed." (Zurgo, Thunder's Decree) is read nowhere else.
        if all(part in _COMPOUND_CLAUSES for part in parts) and (
            len(parts) >= 2 or parts == [_NO_SACRIFICE_CLAUSE]
        ):
            return frozenset(parts)
    return None


def _compound_clause_sets(game, creature):
    from .combat import _computed_ability_sentences, _self_reference_alternatives

    subjects = _self_reference_alternatives(creature)
    for raw in _computed_ability_sentences(creature, game):
        clauses = compound_clauses(raw, subjects)
        if clauses is not None:
            yield clauses


def cant_be_sacrificed(game, permanent) -> str | None:
    """Why `permanent`'s own "can't be sacrificed" stops it being sacrificed, or
    None (CR 701.21a, CR 101.2) - read off the computed abilities (CR 613.5)."""
    if permanent.zone.value != "battlefield":
        return None
    for clauses in _compound_clause_sets(game, permanent):
        if _NO_SACRIFICE_CLAUSE in clauses:
            return f"{permanent.name} can't be sacrificed (CR 701.21a, CR 101.2)"
    return None


def self_owner_attack_refusal(game, creature, defender) -> str | None:
    """ "can't attack its owner" (CR 508.1c): an attack on the player who owns
    the creature."""
    if defender is None or not defender.is_player:
        return None
    for clauses in _compound_clause_sets(game, creature):
        if _NOT_OWNER_CLAUSE in clauses and defender.username == creature.owner:
            return f"{creature.name} can't attack its owner {creature.owner} (CR 508.1c)"
    return None


def self_attack_requirements(game, creature) -> list[bool]:
    """One entry per "attacks each combat if able unless <condition>" this
    creature has while the condition does not hold (CR 508.1d)."""
    from .combat import (
        _computed_ability_sentences,
        _self_reference_alternatives,
    )

    subjects = {name.lower() for name in _self_reference_alternatives(creature)}
    found: list[bool] = [
        False for clauses in _compound_clause_sets(game, creature) if _REQUIRES_CLAUSE in clauses
    ]
    for raw in _computed_ability_sentences(creature, game):
        match = _REQUIREMENT_UNLESS_RE.fullmatch(raw.strip())
        if match is None or match["subject"].strip().lower() not in subjects:
            continue
        if _condition_holds(game, creature, None, match["cond"]) is False:
            found.append(False)
    return found


def reads_self_condition_line(printing, text: str, *, card_name: str) -> bool:
    """Whether every sentence of this static line is one of the shapes above
    with a condition `Game.condition_holds` (or the local readers) reads."""
    from .combat import _self_reference_names, strip_ability_word
    from .layers import layer_readable_sentences

    lowered = text.lower()
    if (
        "can't attack" not in lowered
        and "can't block" not in lowered
        and "attacks each" not in lowered
    ):
        return False
    subjects = {name.lower() for name in _self_reference_names(card_name)}
    sentences = [strip_ability_word(s).strip() for s in layer_readable_sentences(text)]
    if not sentences:
        return False
    for sentence in sentences:
        if compound_clauses(sentence, subjects) is not None:
            continue
        if match := _SELF_UNLESS_RE.fullmatch(sentence):
            if match["subject"].strip().lower() not in subjects:
                return False
            cond = match["cond"]
            if cond is None:
                # A bare "can't attack or block" is `combat`'s own unconditional
                # reader's (`_self_attack_restriction_sentence`, block twin).
                if match["alone"] is None and match["what"].lower() != "attack or block":
                    return False
            elif not (
                _GREATER_POWER_COND_RE.fullmatch(cond)
                or (not _PAY_COND_RE.match(cond) and _condition_readable(cond))
            ):
                return False
        elif match := _REQUIREMENT_UNLESS_RE.fullmatch(sentence):
            if match["subject"].strip().lower() not in subjects or not _condition_readable(
                match["cond"]
            ):
                return False
        else:
            return False
    return True


# --------------------------------------------------------------------------
# Keyword-filtered group keyword grants (CR 613.1f)
# --------------------------------------------------------------------------

#: "Other creatures you control with flying have indestructible." (Sephara,
#: Sky's Blade) - the group is picked by a keyword the creature has when
#: layer 6 is applied, through `CreaturesControlledByQuality`'s closed
#: "with <keyword>" grammar, with the granting permanent itself left out.
_KEYWORD_FILTERED_GROUP_GRANT_RE = re.compile(
    r"^other creatures you control with (?P<filter>[a-z]+) (?:have|has) "
    r"(?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$",
    re.IGNORECASE,
)


def parse_keyword_filtered_group_keyword_grant(sentence: str) -> EffectBuilder | None:
    """`_KEYWORD_FILTERED_GROUP_GRANT_RE`'s shape, or `None`. Tried by
    `machines/layers._parse_layer_sentence`."""
    match = _KEYWORD_FILTERED_GROUP_GRANT_RE.fullmatch(sentence)
    if match is None:
        return None
    keywords = _split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None
    quality = f"creatures with {match.group('filter').lower()}"
    if _parse_creature_description(quality) is None:
        # The closed grammar does not know this keyword (flanking, ...): the
        # generic group subject (`layers/group_grants.py`) reads it instead.
        return None

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [
            ContinuousEffect(
                description=f"{source.name}: other {quality} you control have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, sentence),
                selector=CreaturesControlledByQuality(
                    username=source.controller, quality=quality, excluding_card_id=source.id
                ),
                modification=grant_keyword(keyword),
            )
            for keyword in keywords
        ]

    return builder
