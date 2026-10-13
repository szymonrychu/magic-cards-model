"""Infusion (CR 207.2c's ability word) and its "if/unless/as long as you
gained life this turn" family of effect shapes, plus the round's other
symmetric/edict/halving/skip-turn templates that share no better home.

Infusion itself needs no code (CR 207.2c: an ability word "[has] no special
rules meaning" - `machines/effects._ABILITY_WORDS` already strips the label).
The gap this module closes is the *effect shapes* that follow it: the boolean
fact "you gained life this turn" is already read generically by `machines/
conditions/history.py`'s H4 `_life_this_turn` reader, reached through `Game.
condition_holds`/`machines.conditions.read_condition` - this module never
re-derives that fact, only wires new printed sentence shapes onto the same
call so they ask it the identical way `_parse_condition_clause` and `_parse_
condition_instead_clause` already do for the shapes they cover.

Entry points `infusion_ability_effect`/`infusion_spell_effect` are tried by
`machines/effects.py` ahead of its clause split, the same precedent
`machines/copy_effects.py`'s `copy_ability_effect`/`copy_spell_effect` set:
every shape here is either a whole-text instruction chain (a cast trigger
that copies itself, a conditional consequence riding a targeted pump) or a
verb `parse_mixed_effect`'s per-clause dispatcher has no reader for at all
(a plain "sacrifice a permanent unless <condition>", an unbounded "any number
of target players each discard").
"""

from __future__ import annotations

import re
from random import Random
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import count_pattern, parse_count, quantity_pattern
from .decisions import Decision, DecisionKind, source_id_of
from .triggers import AbilityOnStack as StackAbility

if TYPE_CHECKING:
    from ..models.game import Game, StackObject
    from .effects import AbilityEffect, Effect, TargetedClause
    from .triggers import AbilityOnStack

#: The one fact every reader below asks about - already read generically by
#: `machines/conditions/history.py`'s H4 `_life_this_turn` reader through
#: `Game.condition_holds`. Never re-derived here; every effect shape below
#: only ever calls `game.condition_holds(controller, _GAINED_LIFE, source)`.
_GAINED_LIFE = "you gained life this turn"


def _half_rounded(n: int, *, round_up: bool) -> int:
    """CR 107.1a: "If a spell or ability could generate a fractional number,
    the spell or ability will tell you whether to round up or down" - half of
    `n`, rounded the printed direction. Plain floor/ceiling integer division;
    `n` is always a non-negative count (a life total, a hand size, a board
    count), so no sign case needs handling."""
    return -(-n // 2) if round_up else n // 2


# ---------------------------------------------------------------------------
# "When you cast this spell, copy it if <condition>. [new targets]" -
# Lumaret's Favor's own Infusion trigger.
# ---------------------------------------------------------------------------

#: "copy it if <condition>.[ You may choose new targets for the copy.]" -
#: CR 607.1's "it" anaphora back to the very spell this cast trigger is
#: printed on (CR 113.6k), copied (CR 707.10) only if `condition` holds as
#: the trigger resolves - the conditional twin of `machines/copy_effects.
#: _parse_copy_it_n_times_clause`'s fixed/X counts, here a boolean instead.
_COPY_IT_IF_CONDITION_RE = re.compile(
    r"^copy it if (?P<condition>[^.]+)\."
    r"(?P<new_targets>\s*you may choose new targets for the copy\.?)?$",
    re.IGNORECASE,
)


def _parse_copy_it_if_condition_clause(text: str) -> AbilityEffect | None:
    match = _COPY_IT_IF_CONDITION_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import ConditionalClauseNotice, _effect_condition_is_readable

    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    offer_new_targets = match.group("new_targets") is not None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        spell = ability.source(game)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        held = game.condition_holds(ability.controller, condition_text, spell)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(ability),
                source_name=ability.source_name,
                text=text.strip(),
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if not held:
            return
        copy = game.copy_spell(spell, controller=ability.controller)
        if offer_new_targets:
            game.offer_new_targets_for_copy(
                copy,
                ability.controller,
                source_name=ability.source_name,
                source_id=source_id_of(ability),
            )

    return effect


# ---------------------------------------------------------------------------
# "target <description> gets/has <effect> if <condition>." - Poisoner's
# Apprentice's own ETB: a resolution-time conditional (CR 608.2c) on a
# targeted continuous effect, not CR 603.4's intervening *if* (the ability
# itself always triggers and always resolves; only the pump is conditional).
# ---------------------------------------------------------------------------

#: A targeted one-shot pump/keyword grant with a trailing "if <condition>" -
#: the ability-side gap `_parse_condition_clause` (in `machines/effects.py`)
#: leaves: its own `consequence = parse_mixed_effect(consequence_text)`
#: cannot read a bare continuous-effect sentence like "target creature ...
#: gets -4/-4 until end of turn" on its own (that shape is read only by the
#: *whole-ability* fallback `create_continuous_effect_of_ability`, which
#: keys the built effect's existence to the source's own printed line
#: (`machines.layers._still_exists`, CR 613.6) - wrong for a one-shot
#: resolution effect whose printed line includes the very "if" clause this
#: reader strips to parse the pump, and so would never match). This reader
#: builds the `ContinuousEffect`s directly instead, the same
#: `source_id=None` shape `machines.layers._mass_pump_until_eot_builder`
#: already uses for every other "until end of turn" pump: CR 611.2c fixes a
#: resolved instruction's effect independently of the source once it begins,
#: so nothing here should be re-checking the source's characteristics at all.
_CONDITIONAL_TARGET_PUMP_RE = re.compile(
    r"^(?P<phrase>target .+?) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and (?:gains|have) (?P<keywords>[a-z][a-z ,]*?))? until end of turn "
    r"if (?P<condition>.+?)\.?$",
    re.IGNORECASE,
)


def _parse_conditional_targeted_layer_clause(text: str) -> AbilityEffect | None:
    match = _CONDITIONAL_TARGET_PUMP_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import ConditionalClauseNotice, _effect_condition_is_readable, _targets_understood
    from .layers import (
        ContinuousEffect,
        Duration,
        Layer,
        Sublayer,
        _split_and_validate_keywords,
        grant_ability,
        modify_power_toughness,
        only_this_incarnation,
    )

    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    power, toughness = int(match.group("power")), int(match.group("toughness"))
    keywords = (
        _split_and_validate_keywords(match.group("keywords"))
        if match.group("keywords") is not None
        else []
    )
    if keywords is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        controller = ability.controller
        held = game.condition_holds(controller, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(ability),
                source_name=ability.source_name,
                text=text.strip(),
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if not held:
            return
        targets = [
            target
            for target in game.resolve_card_targets(ability)
            if target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        store = game.continuous_effects
        for target in targets:
            selector = only_this_incarnation(target, target.zone_change_stamp)
            if power or toughness:
                store.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {target.name} gets "
                        f"{power:+d}/{toughness:+d}",
                        layer=Layer.POWER_TOUGHNESS,
                        sublayer=Sublayer.MODIFY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=selector,
                        modification=modify_power_toughness(power, toughness),
                    ),
                    game,
                )
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=f"{ability.source_name}: {target.name} gains {keyword}",
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=selector,
                        modification=grant_ability(keyword),
                    ),
                    game,
                )

    return effect


# ---------------------------------------------------------------------------
# "sacrifice a/an <description> unless <condition>." - Tragedy Feaster's own
# end step trigger (CR 118.12: "unless" is the something happening only when
# the other thing did not), the sacrifice twin of `machines/effects._parse_
# discard_unless_condition_clause`'s identical discard shape.
# ---------------------------------------------------------------------------

_SACRIFICE_UNLESS_CONDITION_RE = re.compile(
    r"^sacrifice (?:an? (?P<description>[a-z][a-z '/-]*?)"
    r"|(?:this|self) (?P<self_noun>[a-z]+)|it) unless (?P<condition>.+?)\.?$",
    re.IGNORECASE,
)


def _parse_sacrifice_unless_condition_clause(text: str) -> AbilityEffect | None:
    match = _SACRIFICE_UNLESS_CONDITION_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from ..phrases import with_indefinite_article
    from .effects import ConditionalClauseNotice, _effect_condition_is_readable
    from .targeting import permanent_description

    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    description = match.group("description")
    self_reference = description is None
    requirement = None
    wanted_words = "this permanent"
    if not self_reference:
        description = description.strip()
        requirement = permanent_description(description)
        if requirement is None:
            return None
        wanted_words = with_indefinite_article(description)

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        controller = ability.controller
        held = game.condition_holds(controller, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(ability),
                source_name=ability.source_name,
                text=text.strip(),
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            return
        if self_reference:
            # "sacrifice this creature"/"sacrifice it" (CR 700.7's own
            # self-reference) - the ability's own source, no choice to make.
            if source is not None and source.zone is Zone.BATTLEFIELD:
                game.sacrifice(source)
            return
        assert requirement is not None
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller)
            if requirement.rejects(permanent, controller, game) is None
        ]
        if not candidates:
            return
        if len(candidates) == 1:
            chosen: CardState | None = candidates[0]
        else:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"sacrifice {wanted_words}",
                    source=ability.source_name,
                    amount=1,
                    exact=True,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id_of(ability),
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen = by_id.get(chosen_ids[0]) if chosen_ids else None
        if chosen is not None and chosen.zone is Zone.BATTLEFIELD:
            game.sacrifice(chosen)

    return effect


# ---------------------------------------------------------------------------
# "Any number of target players each discard a card." - Ral Zarek, Guest
# Lecturer's own "−1": CR 107.1c's unbounded target count (`machines.
# targeting` already reads "any number of target players" whole), the
# discard twin of `machines/effects._parse_n_target_players_each_draw_clause`'s
# fixed-count "Two target players each draw a card."
# ---------------------------------------------------------------------------

_QUANTIFIED_TARGET_PLAYERS_EACH_DISCARD_RE = re.compile(
    rf"^{quantity_pattern('players')} target players each discards? "
    rf"{count_pattern('n')} cards?\.?$",
    re.IGNORECASE,
)


def _parse_quantified_target_players_each_discard_clause(text: str) -> AbilityEffect | None:
    match = _QUANTIFIED_TARGET_PLAYERS_EACH_DISCARD_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from ..numbers import QuantitySource, parse_quantity
    from .effects import _discard_cards, _targets_understood

    phrase = f"{match.group('players')} target players"
    if not _targets_understood(phrase, allow_player_targets=True, count_agnostic=True):
        return None
    quantity = parse_quantity(match.group("players"))
    if quantity is None or quantity.source not in (
        QuantitySource.FIXED,
        QuantitySource.ANY_NUMBER,
    ):
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if not isinstance(target, Player):
                continue
            _discard_cards(
                game, target, count, ability.source_name, source_id=source_id_of(ability)
            )

    return effect


# ---------------------------------------------------------------------------
# "Flip five coins. Target opponent skips their next X turns, where X is the
# number of coins that came up heads." - Ral Zarek, Guest Lecturer's own
# "−7" (CR 705's coin flip family, CR 614.10's skip-a-turn replacement).
# ---------------------------------------------------------------------------

_FLIP_COINS_THEN_SKIP_TURNS_RE = re.compile(
    rf"^flip {count_pattern('coins')} coins\. target opponent skips their next x turns, "
    r"where x is the number of coins that came up heads\.?$",
    re.IGNORECASE,
)


def _parse_flip_coins_then_skip_turns_clause(text: str) -> AbilityEffect | None:
    match = _FLIP_COINS_THEN_SKIP_TURNS_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import _targets_understood

    if not _targets_understood("target opponent", allow_player_targets=True):
        return None
    n_coins = parse_count(match.group("coins"))
    if n_coins is None or n_coins <= 0:
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        heads = sum(1 for _ in range(n_coins) if game.flip_coin())
        targets = [target for target in game.resolve_targets(ability) if isinstance(target, Player)]
        if not targets:
            return
        opponent = targets[0]
        if heads > 0:
            game.skip_next_turns(opponent.username, heads)

    return effect


# ---------------------------------------------------------------------------
# "Destroy/exile target creature. If <condition>, that creature's controller
# <referent clause>." - Foolish Fate's own Infusion consequence: a resolution-
# time conditional (CR 608.2c) riding `machines/effects._parse_anaphoric_
# clause_pair`'s "its controller ..." anaphora (CR 400.7), the destroy
# itself unconditional and only the referent clause gated.
# ---------------------------------------------------------------------------

_LEADING_IF_THEN_REFERENT_RE = re.compile(
    r"^if (?P<condition>.+?), (?P<rest>.+)$", re.IGNORECASE | re.DOTALL
)


def _parse_conditional_anaphoric_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    from .effects import (
        _ANAPHORIC_SUBJECT_RE,
        _DESTROY_TARGET_RE,
        _EXILE_TARGET_RE,
        ConditionalClauseNotice,
        _effect_condition_is_readable,
        _parse_referent_clause,
        _targets_understood,
    )

    first = first.strip()
    verb_match = _DESTROY_TARGET_RE.fullmatch(first) or _EXILE_TARGET_RE.fullmatch(first)
    if verb_match is None:
        return None
    is_destroy = first.lower().startswith("destroy")
    if not _targets_understood(
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=is_destroy
    ):
        return None
    leading_if = _LEADING_IF_THEN_REFERENT_RE.fullmatch(second.strip())
    if leading_if is None:
        return None
    condition_text = leading_if.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    subject_match = _ANAPHORIC_SUBJECT_RE.fullmatch(leading_if.group("rest").strip())
    if subject_match is None:
        return None
    second_clause = _parse_referent_clause(subject_match.group("rest"))
    if second_clause is None:
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        referent = game.controller_of(target)
        power = game.power_of(target)
        controller = (
            game.controller_of(stack_object).username
            if not isinstance(stack_object, StackAbility)
            else stack_object.controller
        )
        if is_destroy:
            game.destroy(target)
        else:
            game.exile_permanent(target)
        held = game.condition_holds(controller, condition_text, target)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=source_name,
                text=f"{first}. {second.strip()}.",
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            second_clause(game, referent, power, source_name, source_id_of(stack_object))

    return effect


# ---------------------------------------------------------------------------
# "Look at the top N cards of your library. You may reveal a creature or land
# card from among them and put it into your hand. If you gained life this
# turn, you may instead reveal M creature and/or land cards from among them
# and put them into your hand. Put the rest on the bottom of your library in
# a random order." - Follow the Lumarets's whole Infusion sorcery.
# ---------------------------------------------------------------------------

_LOOK_TOP_REVEAL_CREATURE_OR_LAND_INFUSION_RE = re.compile(
    rf"^look at the top {count_pattern('n')} cards? of your library\. "
    r"you may reveal an? (?P<quality>[a-z][a-z /]*?) cards? from among them "
    r"and put (?:it|them) into your hand\. "
    r"if you gained life this turn, you may instead reveal "
    rf"{count_pattern('m')} (?P<quality2>[a-z][a-z /]*?) cards? from among them "
    r"and put them into your hand\. "
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)


def _parse_look_top_reveal_creature_or_land_infusion_clause(text: str) -> Effect | None:
    match = _LOOK_TOP_REVEAL_CREATURE_OR_LAND_INFUSION_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import _bounded_quality_matcher

    look_n = parse_count(match.group("n"))
    instead_n = parse_count(match.group("m"))
    if look_n is None or instead_n is None or look_n <= 0 or instead_n <= 0:
        return None
    # The "instead" wording ("creature and/or land") describes the identical
    # set the base wording ("creature or land") does - CR 608.2c's inclusive
    # "or" either way - so one matcher, built off the wider of the two
    # phrasings, serves both branches of the reveal.
    quality_text = re.sub(r"\band/or\b", "or", match.group("quality2"), flags=re.IGNORECASE)
    matches = _bounded_quality_matcher(quality_text, None)

    def effect(game: Game, spell: CardState) -> None:
        controller = game.controller_of(spell)
        held = game.condition_holds(controller.username, _GAINED_LIFE, spell)
        quantity = instead_n if held else 1
        moved, rest = game.look_at_top_and_split(
            controller,
            look_n,
            source=spell.name,
            prompt=f"reveal up to {quantity} creature or land card(s) from the top {look_n}",
            moved_label="your hand",
            kept_label="bottom of your library",
            rest_in_random_order=True,
            source_id=source_id_of(spell),
            moved_amount=quantity,
            moved_candidates=matches,
        )
        for state in moved:
            game.reveal(state, source=spell.name)
            controller.add(state, Zone.HAND)
        if rest:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:follow-the-lumarets-bottom"
            )
            rng.shuffle(rest)
            game.shuffles_performed += 1
            for state in rest:
                controller.library.append(state)
            controller.note_library_changed(placed=rest)

    return effect


# ---------------------------------------------------------------------------
# Halving with a trailing "Round up/down each time." declaration - Pox
# Plague's own three-step "each player" sentence and Peer into the Abyss's
# draw-and-lose-life pair, CR 107.1a's rounding direction stated once for
# every fractional count the sentence generates rather than repeated per
# clause the way `numbers.parse_half`'s own ", rounded up/down" suffix is.
# ---------------------------------------------------------------------------

_EACH_PLAYER_HALVES_LIFE_HAND_PERMANENTS_RE = re.compile(
    r"^each player loses half (?:their|his or her) life, then discards half the cards in "
    r"(?:their|his or her) hand, then sacrifices half the permanents "
    r"(?:they control|he or she controls) of (?:their|his or her) choice\. "
    r"round (?P<direction>up|down) each time\.?$",
    re.IGNORECASE,
)


def _parse_each_player_halves_life_hand_permanents_clause(text: str) -> Effect | None:
    match = _EACH_PLAYER_HALVES_LIFE_HAND_PERMANENTS_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import _discard_cards, _players_in_apnap_order

    round_up = match.group("direction").lower() == "up"

    def effect(game: Game, spell: CardState) -> None:
        players = _players_in_apnap_order(game)
        # Step 1 (CR 608.2c's printed order): every player's life total is
        # halved off what it was *before* any of the three steps below has
        # changed anything - none of the three steps' inputs (life, hand
        # size, board count) affects another's, so gathering the amount up
        # front per player and applying it is equivalent to, and simpler
        # than, re-reading it player by player.
        for player in players:
            loss = _half_rounded(player.life, round_up=round_up)
            if loss > 0:
                game.lose_life(player, loss)
        game.announce_batched_events()
        # Step 2: half the hand, CR 701.9b's own choice (no "of their
        # choice" printed - sacrifice is the only one of the three that
        # names it, because a discard's chooser is already CR 701.9b's
        # default).
        for player in players:
            hand_n = _half_rounded(len(player.hand), round_up=round_up)
            if hand_n > 0:
                _discard_cards(game, player, hand_n, spell.name, source_id=source_id_of(spell))
        game.announce_batched_events()
        # Step 3: half the permanents, of the controller's own choice (CR
        # 701.21a) - every choice is asked (CR 101.4 APNAP order) before any
        # of them actually leaves.
        chosen: list[CardState] = []
        for player in players:
            controlled = game.permanents_controlled_by(player.username)
            sac_n = _half_rounded(len(controlled), round_up=round_up)
            if sac_n <= 0:
                continue
            if len(controlled) <= sac_n:
                chosen.extend(controlled)
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"sacrifice {sac_n} permanent(s)",
                    source=spell.name,
                    amount=sac_n,
                    exact=True,
                    cards=tuple(permanent.id for permanent in controlled),
                    source_id=source_id_of(spell),
                )
            )
            by_id = {permanent.id: permanent for permanent in controlled}
            chosen.extend(by_id[card_id] for card_id in chosen_ids if card_id in by_id)
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return effect


#: Peer into the Abyss's own template - the same trailing "Round `<direction>`
#: each time." declaration over a *targeted* player's library and life
#: instead of every player's life/hand/board, proof that the rounding
#: declaration is read off the sentence rather than pinned to Pox Plague's
#: own three actions.
_TARGET_PLAYER_HALF_LIBRARY_DRAW_AND_HALF_LIFE_RE = re.compile(
    r"^target player draws cards equal to half the number of cards in "
    r"(?:their|his or her) library and loses half (?:their|his or her) life\. "
    r"round (?P<direction>up|down) each time\.?$",
    re.IGNORECASE,
)


def _parse_target_player_half_library_draw_and_half_life_clause(text: str) -> Effect | None:
    match = _TARGET_PLAYER_HALF_LIBRARY_DRAW_AND_HALF_LIFE_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None

    from .effects import _targets_understood

    if not _targets_understood("target player", allow_player_targets=True):
        return None
    round_up = match.group("direction").lower() == "up"

    def effect(game: Game, spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            if not isinstance(target, Player):
                continue
            draw_n = _half_rounded(len(target.library), round_up=round_up)
            life_n = _half_rounded(target.life, round_up=round_up)
            if draw_n > 0:
                game.draw_cards(target.username, draw_n)
            if life_n > 0:
                game.lose_life(target, life_n)

    return effect


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def infusion_ability_effect(effect_text: str) -> AbilityEffect | None:
    """A triggered or activated ability's whole text, or `None`. Tried by
    `machines/effects._ability_effect_or_notice` ahead of its clause split,
    the same precedent `machines/copy_effects.copy_ability_effect` sets."""
    for reader in (
        _parse_copy_it_if_condition_clause,
        _parse_conditional_targeted_layer_clause,
        _parse_sacrifice_unless_condition_clause,
        _parse_quantified_target_players_each_discard_clause,
        _parse_flip_coins_then_skip_turns_clause,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def infusion_spell_effect(text: str) -> Effect | None:
    """A resolving spell's whole text, or `None`. Tried by `machines/
    effects._spell_effect_or_notice` ahead of its clause split."""
    for reader in (
        _parse_look_top_reveal_creature_or_land_infusion_clause,
        _parse_each_player_halves_life_hand_permanents_clause,
        _parse_target_player_half_library_draw_and_half_life_clause,
    ):
        effect = reader(text)
        if effect is not None:
            return effect
    return None
