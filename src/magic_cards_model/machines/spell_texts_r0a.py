"""R0a-T7: spell-resolution texts the engine did not read - a grab bag of
independent shapes bundled into one task, each its own mechanic rather than
one card's own private row (`docs/card_coverage/`'s own round-of-work split,
not a single templating family the way `blight_effects.py` or
`linked_exile.py` are). Every reader here is registered additively into
`machines/effects.py`'s existing dispatch chain - the whole-text tries in
`_parse_mixed_clauses` mostly, since every shape below carries an anaphor
("that permanent", "it", "the revealed card") across a sentence boundary
`split_effect_clauses`'s bare "."/" and " split would otherwise cut, the
identical reason `blight_effects.py`'s own readers are tried the same way.

`.effects`/`.combat`/`.targeting` are imported lazily inside each function
(never at module scope) so this module's own `from . import spell_texts_r0a`
inside `effects.py` never closes an import cycle - the same convention
`blight_effects.py` documents for itself.

Rules verified with `mise run rules:find` in the session that wrote this
file (`.rules/MagicCompRules.txt`, effective 2026-09-25):

- **CR 700.12a** - outlaws (Shoot the Sheriff) are read entirely in
  `machines/targeting.py`'s own `_Adjectives`/`TargetRequirement` and
  `machines/conditions/board.py`'s `OUTLAW_TYPES` - no reader of this
  module's own is needed for that card.
- **CR 201.2a** - "Two or more objects have the same name if they have at
  least one name in common ... An object with no name doesn't have the same
  name as any other object" (Maelstrom Pulse, Echoing Truth).
- **CR 700.2 / CR 701.6a** - modal spells, and countering a spell (Get Out).
- **CR 509.1c** - a blocking requirement, "must block" or "must block if
  some condition is met" (Academic Dispute).
- **CR 701.48a** - Learn (Academic Dispute's own second sentence, already
  read by `machines/keywords.py` - untouched by this module).
- **CR 111.1 / CR 702.10a** - a token, and haste (Song of Totentanz).
- **CR 701.20e / CR 401.4** - looking at cards, and a library's owner
  arranging cards put back into it (United Battlefront's own reader lives in
  `machines/effects.py`'s existing `_parse_card_group_qualifier` widening;
  Break Out is this module's own).
- **CR 701.17a** - milling (Cache Grab's own reader is `machines/effects.py`'s
  existing `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE` widening, not this module).
- **CR 608.2b** - a target rechecked for legality at resolution, including
  the "each have a different mana value" cross-target restriction Agadeem's
  Awakening's own targeting reads through `machines/targeting.py`'s
  `distinct_mana_values`.
- **CR 406.2 / CR 701.13a** - exile, from whatever zone an object is in
  (Strategic Betrayal).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count

if TYPE_CHECKING:
    from ..models.game import Game, StackObject
    from .effects import TargetedClause


# ---------------------------------------------------------------------------
# Maelstrom Pulse / Echoing Truth: destroy or return a target and every
# other permanent with the same name as it (CR 201.2a)
# ---------------------------------------------------------------------------


def _same_name_battlefield_group(game: Game, target: CardState) -> list[CardState]:
    """`target` plus every *other* permanent on the battlefield sharing at
    least one name with it (CR 201.2a).

    "An object with no name doesn't have the same name as any other object,
    including another object with no name" - a face-down permanent's own
    `CardState.name` is empty, so that branch never runs the board scan at
    all and the group is `target` alone, never every other face-down
    permanent in play.
    """
    if not target.name:
        return [target]
    return [target] + [
        permanent
        for permanent in game.battlefield
        if permanent.id != target.id and permanent.name == target.name
    ]


#: Maelstrom Pulse: "Destroy target nonland permanent and all other
#: permanents with the same name as that permanent." `split_effect_clauses`'s
#: bare "and" would cut this in two - a verbless "all other permanents ..."
#: fragment next to a plain "destroy target nonland permanent" - so this is
#: tried on the whole, unsplit text (`_parse_mixed_clauses`'s own pre-split
#: dispatch), the identical treatment `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s own
#: "and all other creatures with the same name as that creature" already
#: gets there.
_DESTROY_TARGET_AND_SAME_NAME_RE = re.compile(
    r"^destroy target (?P<phrase>.+?) and all other permanents "
    r"with the same name as that permanent\.?$",
    re.IGNORECASE,
)

#: Echoing Truth (Modern-legal proof printing, not in this task's own list
#: and not in `code/magic-cards-model-api/decks/*.txt`): "Return target
#: nonland permanent and all other permanents with the same name as that
#: permanent to their owners' hands." - the identical CR 201.2a grouping,
#: `return` in place of `destroy`. `machines/effects.py`'s own
#: `_RETURN_TARGET_AND_SAME_NAME_FROM_GRAVEYARD_RE` is a *different* shape
#: (Rat King, Verminister's own graveyard-scoped "and all other **cards**
#: with the same name as that card") - this one is the battlefield, "**all
#: other permanents**", the destroy reader's own noun.
_RETURN_TARGET_AND_SAME_NAME_TO_OWNERS_HANDS_RE = re.compile(
    r"^return target (?P<phrase>.+?) and all other permanents "
    r"with the same name as that permanent to (?:their owners'?|its owner'?s) hands?\.?$",
    re.IGNORECASE,
)


def parse_destroy_target_and_same_name_permanents_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DESTROY_TARGET_AND_SAME_NAME_RE`'s shape, or `None` - Maelstrom
    Pulse's whole text."""
    whole = collapsed(text.strip())
    match = _DESTROY_TARGET_AND_SAME_NAME_RE.fullmatch(whole)
    if match is None:
        return None

    from .effects import _targets_understood

    if not _targets_understood(f"target {match.group('phrase')}", count_agnostic=True):
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        if target.zone is not Zone.BATTLEFIELD:
            return
        for permanent in _same_name_battlefield_group(game, target):
            if permanent.zone is Zone.BATTLEFIELD:
                game.destroy(permanent)

    return effect


def parse_return_target_and_same_name_permanents_to_hands_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_TARGET_AND_SAME_NAME_TO_OWNERS_HANDS_RE`'s shape, or `None` -
    Echoing Truth's whole text, the generalisation proof for the shared
    `_same_name_battlefield_group` selector above."""
    whole = collapsed(text.strip())
    match = _RETURN_TARGET_AND_SAME_NAME_TO_OWNERS_HANDS_RE.fullmatch(whole)
    if match is None:
        return None

    from .effects import _targets_understood

    if not _targets_understood(f"target {match.group('phrase')}", count_agnostic=True):
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            return
        target = targets[0]
        if target.zone is not Zone.BATTLEFIELD:
            return
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for permanent in _same_name_battlefield_group(game, target):
                if permanent.zone is Zone.BATTLEFIELD:
                    game.return_to_hand(permanent)

    return effect


# ---------------------------------------------------------------------------
# Academic Dispute: a CR 509.1c block requirement with no named attacker,
# an optional keyword grant on the same target, and Learn (unaffected)
# ---------------------------------------------------------------------------

#: "Target creature blocks this turn if able[. You may have it gain
#: `<keyword>` until end of turn]." - `combat._BLOCKS_NAMED_EACH_COMBAT_RE`'s
#: own attacker-name group widened (this task) to admit the unnamed, general
#: CR 509.1c requirement this grants: "This creature blocks each combat if
#: able." with no attacker at all, obeyed by blocking *any* legal one.
#: `rest` is whatever the card prints after (Academic Dispute's own
#: "Learn."), read the ordinary way and composed after - never swallowed by
#: this reader, which only ever claims its own two anaphoric sentences.
_TARGET_BLOCKS_THIS_TURN_IF_ABLE_RE = re.compile(
    r"^(?P<phrase>(?:up to one )?target (?:[a-z' ]+ )?creature) blocks this turn if able\.\s*"
    r"(?:you may have it gain (?P<keyword>[a-z]+(?: [a-z]+)?) until end of turn\.\s*)?"
    r"(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_target_blocks_if_able_then_may_gain_keyword_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_BLOCKS_THIS_TURN_IF_ABLE_RE`'s shape, or `None` - Academic
    Dispute's own first two sentences, with its trailing "Learn." (or any
    other rider a future printing of this shape carries) composed after
    through the ordinary per-clause dispatcher rather than read here."""
    whole = collapsed(text.strip())
    match = _TARGET_BLOCKS_THIS_TURN_IF_ABLE_RE.fullmatch(whole)
    if match is None:
        return None

    from .effects import _targets_understood, parse_mixed_effect, parse_mixed_effect_for_spell

    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    keyword = match.group("keyword")
    rest_text = match.group("rest").strip()
    rest_effect = None
    if rest_text:
        rest_effect = (
            parse_mixed_effect_for_spell(rest_text) if for_spell else parse_mixed_effect(rest_text)
        )
        if rest_effect is None:
            # CR 101.3 excuses only what is impossible to perform, never an
            # unread instruction - a rider this wave cannot read fails the
            # whole clause closed rather than silently dropping it.
            return None

    def effect(game: Game, stack_object: StackObject) -> None:
        from .effects import _grant_keywords_to, source_id_of

        player = game.controller_of(stack_object)
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            _grant_keywords_to(
                game,
                target,
                ["This creature blocks each combat if able."],
                "until end of turn",
                controller=player.username,
                source_name=source_name,
            )
            if keyword is not None and game.may(
                player,
                f"have {target.name} gain {keyword} until end of turn",
                source=source_name,
                source_id=source_id,
            ):
                _grant_keywords_to(
                    game,
                    target,
                    [keyword.title()],
                    "until end of turn",
                    controller=player.username,
                    source_name=source_name,
                )
        if rest_effect is not None:
            rest_effect(game, stack_object)  # type: ignore[arg-type]

    return effect


# ---------------------------------------------------------------------------
# Song of Totentanz / White Sun's Twilight: a token created with a quoted
# granted ability, followed (or preceded) by another sentence
# ---------------------------------------------------------------------------

#: "Create `<n>` ... tokens with `<toxic N and/or >` "`<quoted ability
#: text>`." `<rest>`" - Song of Totentanz's own "Create X 1/1 black Rat
#: creature tokens with "This token can't block." Creatures you control
#: gain haste until end of turn." and White Sun's Twilight's own "You gain X
#: life. Create X 1/1 colorless Phyrexian Mite artifact creature tokens with
#: toxic 1 and "This token can't block." If X is 5 or more, destroy all
#: other creatures." (Modern/Pioneer-legal proof printing, not this task's
#: own card, not in the deck pool - the generalisation proof this template
#: is not fitted to Song of Totentanz's own sentence).
#:
#: The quoted ability's own period sits *inside* the closing quote
#: (`can't block."`), never followed by whitespace the way an ordinary
#: sentence boundary is (`split_effect_clauses`'s `_CLAUSE_SEPARATOR` only
#: ever splits on `\.\s+` - a period directly followed by a `"` never
#: matches that, so the two sentences straddling the quote arrive here
#: still fused into one unsplittable clause) - this reader is what actually
#: separates them, handing each half to the ordinary per-clause dispatcher
#: rather than teaching the splitter to look inside quotes.
_TOKEN_WITH_QUOTED_ABILITY_THEN_REST_RE = re.compile(
    r"^(?P<pre>(?:[^\"]+?\.\s+)*?)"
    r"(?P<token_clause>create .+?\"[^\"]*\")\.?"
    r"(?:\s+(?P<rest>.+))?$",
    re.IGNORECASE | re.DOTALL,
)


def parse_token_with_quoted_ability_then_rest_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TOKEN_WITH_QUOTED_ABILITY_THEN_REST_RE`'s shape, or `None`."""
    from .effects import parse_mixed_effect, parse_mixed_effect_for_spell

    parser = parse_mixed_effect_for_spell if for_spell else parse_mixed_effect
    whole = collapsed(text.strip())
    match = _TOKEN_WITH_QUOTED_ABILITY_THEN_REST_RE.fullmatch(whole)
    if match is None:
        return None
    pre_text = match.group("pre").strip()
    rest_text = (match.group("rest") or "").strip()
    if not pre_text and not rest_text:
        # No sibling sentence either side of the token clause at all - this
        # is a bare "Create ... tokens with '...'." with nothing this reader
        # adds by claiming it, and re-parsing `token_clause` (identical to
        # `whole` once its own trailing period is put back) would call this
        # same function again with the same text forever. Left for the
        # ordinary token-creation reader to read directly.
        return None
    token_effect = parser(f"{match.group('token_clause')}.")
    if token_effect is None:
        return None
    pre_effect = parser(pre_text) if pre_text else None
    if pre_text and pre_effect is None:
        return None
    rest_effect = parser(rest_text) if rest_text else None
    if rest_text and rest_effect is None:
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        if pre_effect is not None:
            pre_effect(game, stack_object)  # type: ignore[arg-type]
        token_effect(game, stack_object)  # type: ignore[arg-type]
        if rest_effect is not None:
            rest_effect(game, stack_object)  # type: ignore[arg-type]

    return effect


# ---------------------------------------------------------------------------
# Break Out: look at the top, reveal one candidate, a conditional choice
# between the battlefield (with haste) and the hand, the rest to the bottom
# ---------------------------------------------------------------------------

#: Break Out: "Look at the top six cards of your library. You may reveal a
#: creature card from among them. If that card has mana value 2 or less,
#: you may put it onto the battlefield and it gains haste until end of
#: turn. If you didn't put the revealed card onto the battlefield this way,
#: put it into your hand. Put the rest on the bottom of your library in a
#: random order." - generalised on the count, the quality word, the mana
#: value ceiling, and the granted keyword, none of them pinned to this
#: card's own numbers.
_LOOK_TOP_REVEAL_CONDITIONAL_BATTLEFIELD_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards? of your library\.\s*"
    r"you may reveal an? (?P<quality>[a-z]+) card from among them\.\s*"
    r"if that card has mana value (?P<mv>\d+) or less, you may put it onto the battlefield "
    r"and it gains (?P<keyword>[a-z]+(?: [a-z]+)?) until end of turn\.\s*"
    r"if you didn'?t put the revealed card onto the battlefield this way, "
    r"put it into your hand\.\s*"
    r"put the rest on the bottom of your library in (?P<random>a random|any) order\.?$",
    re.IGNORECASE,
)


def parse_look_top_reveal_conditional_battlefield_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_LOOK_TOP_REVEAL_CONDITIONAL_BATTLEFIELD_RE`'s shape, or `None`."""
    whole = collapsed(text.strip())
    match = _LOOK_TOP_REVEAL_CONDITIONAL_BATTLEFIELD_RE.fullmatch(whole)
    if match is None:
        return None

    from random import Random

    from .effects import _grant_keywords_to, _singular_card_type, source_id_of

    count = parse_count(match.group("n"))
    if count is None:
        return None
    card_type = _singular_card_type(match.group("quality"))
    if card_type is None:
        return None
    max_mv = int(match.group("mv"))
    keyword = match.group("keyword")
    randomised = match.group("random").lower() == "a random"
    quality_description = match.group("quality").strip()

    def matches(state: CardState) -> bool:
        return card_type in state.types

    def effect(game: Game, stack_object: StackObject) -> None:
        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        moved, rest = game.look_at_top_and_split(
            controller,
            count,
            moved_label="revealed",
            kept_label="bottom of your library",
            source=source_name,
            source_id=source_id,
            prompt=f"reveal a {quality_description} card from the top {count}",
            rest_in_random_order=randomised,
            moved_amount=1,
            moved_candidates=matches,
        )
        for revealed in moved:
            game.reveal(revealed, source=source_name)
            put_onto_battlefield = False
            if revealed.mana_value <= max_mv and game.may(
                controller,
                f"put {revealed.name} onto the battlefield",
                source=source_name,
                source_id=source_id,
            ):
                put = game.put_onto_battlefield(revealed, controller.username)
                _grant_keywords_to(
                    game,
                    put,
                    [keyword.title()],
                    "until end of turn",
                    controller=controller.username,
                    source_name=source_name,
                )
                put_onto_battlefield = True
            if not put_onto_battlefield:
                controller.add(revealed, Zone.HAND)
        if randomised and rest:
            # Not CR 701.24a's shuffle: nobody's arrangement, no shuffle
            # trigger, the same convention every other "in a random order"
            # reader in this pool already follows.
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom")  # noqa: S311
            rng.shuffle(rest)
            game.shuffles_performed += 1
        elif rest:
            rest = game.ask_library_bottom_order(
                controller, rest, source=source_name, source_id=source_id
            )
        for state in rest:
            controller.library.append(state)
        if rest:
            controller.note_library_changed(placed=rest)

    return effect


# ---------------------------------------------------------------------------
# Agadeem's Awakening: reanimate any number of graveyard targets, no two
# sharing a mana value (CR 601.2c/608.2b, `machines/targeting.py`'s own
# `distinct_mana_values`)
# ---------------------------------------------------------------------------

#: "Return from your graveyard to the battlefield any number of target
#: creature cards that each have a different mana value X or less." - the
#: zone phrase sits right after the verb (CR 401's return), before the
#: object noun phrase, unlike every other "return target `<phrase>` from
#: your graveyard" reader in `machines/effects.py`, which all print the zone
#: *after* the noun - so `_targets_understood` is handed the noun phrase
#: with "from your graveyard" appended back on, the identical reattachment
#: `_parse_return_target_and_same_name_from_graveyard_clause` already does
#: for its own differently-ordered phrase.
_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_DISTINCT_RE = re.compile(
    r"^return from your graveyard to the battlefield (?P<phrase>.+?)\.?$", re.IGNORECASE
)


def parse_return_from_graveyard_to_battlefield_distinct_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_DISTINCT_RE`'s shape, or `None`
    - Agadeem's Awakening's whole text. CR 608.2b's own target legality
    recheck (a target already returned by an earlier instruction, or that
    left the graveyard some other way, is simply not affected) is
    `game.resolve_targets`' ordinary job; the "each have a different mana
    value" cross-target restriction is enforced once, at announcement, by
    `machines/targeting.py`'s `distinct_mana_values` - nothing here re-checks
    it, the same trust every other targeted clause in this file already
    places in `TargetingProfile.check` having already run.
    """
    whole = collapsed(text.strip())
    match = _RETURN_FROM_GRAVEYARD_TO_BATTLEFIELD_DISTINCT_RE.fullmatch(whole)
    if match is None:
        return None

    from .effects import _targets_understood

    if not _targets_understood(
        f"{match.group('phrase')} from your graveyard",
        count_agnostic=True,
        battlefield_only=False,
    ):
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD
        ]
        if not targets:
            return
        controller = game.controller_of(stack_object).username
        with game.entering_together():  # CR 603.6a: one arrival, together
            for target in targets:
                if target.zone is Zone.GRAVEYARD:
                    game.put_onto_battlefield(target, controller)

    return effect


# ---------------------------------------------------------------------------
# Strategic Betrayal: one instruction, two objects of the same verb - an
# opponent exiles a chosen creature they control, and their whole graveyard
# ---------------------------------------------------------------------------

#: "Target opponent exiles a creature they control and their graveyard." -
#: CR 701.21a's edict grammar (`machines/effects.py`'s own
#: `_TARGET_PLAYER_SACRIFICES_RE`), widened to "exiles" (CR 701.10a) with a
#: second, unrelated object joined by a bare "and": the opponent's whole
#: graveyard, `exile_target_players_graveyard`'s own move. `split_effect_
#: clauses`'s bare "and" would otherwise cut this into a verbless "their
#: graveyard" fragment, so it is read whole, generalised on the count and
#: description the way `_TARGET_PLAYER_SACRIFICES_RE` already is.
_TARGET_OPPONENT_EXILES_CREATURE_AND_GRAVEYARD_RE = re.compile(
    rf"^target (?P<who>player|opponent) exiles (?P<n>{COUNT}) (?P<description>.+?)"
    r"(?: they control| of their choice)? and (?:their|his or her) graveyard\.?$",
    re.IGNORECASE,
)


def parse_target_player_exiles_creature_and_graveyard_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_OPPONENT_EXILES_CREATURE_AND_GRAVEYARD_RE`'s shape, or
    `None` - Strategic Betrayal's whole text."""
    whole = collapsed(text.strip())
    match = _TARGET_OPPONENT_EXILES_CREATURE_AND_GRAVEYARD_RE.fullmatch(whole)
    if match is None:
        return None

    from magic_cards_model.phrases import with_indefinite_article

    from ..models.player import Player
    from .effects import Decision, DecisionKind, _targets_understood, source_id_of
    from .targeting import permanent_description

    if not _targets_understood(f"target {match.group('who')}", allow_player_targets=True):
        return None
    count = parse_count(match.group("n"))
    description = match.group("description").strip()
    requirement = permanent_description(description)
    if requirement is None or count is None or count < 1:
        return None
    wanted_words = with_indefinite_article(description) if count == 1 else f"{count} {description}"

    def effect(game: Game, stack_object: StackObject) -> None:
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(target.username)
                if requirement.rejects(permanent, target.username, game) is None
            ]
            chosen = candidates
            if len(candidates) > count:
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=target.username,
                        prompt=f"exile {wanted_words}",
                        source=source_name,
                        amount=count,
                        cards=tuple(permanent.id for permanent in candidates),
                        source_id=source_id_of(stack_object),
                    )
                )
                by_id = {permanent.id: permanent for permanent in candidates}
                chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
            for permanent in chosen:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.exile_permanent(permanent)
            for card_state in list(target.graveyard):
                game.exile_permanent(card_state)

    return effect
