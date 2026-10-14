"""Counters coming *off* an object as the whole (or the tail) of a
resolution, read by shape and never by card (CR 122.5):

- **"Remove a[n]/`<n>` `<kind>` counter(s) from this creature/permanent/
  artifact/it."** with no "if you do", no "you may" - Bristlebane Battler's
  and Reluctant Dounguard's own self-removal on "another creature you
  control enters while this creature has a `<kind>` counter on it" (the CR
  603.4 intervening *if* itself is already read generically by
  `machines/conditions/objects._has_counters`, reused unchanged - this
  module only ever adds the *removal*, never a second copy of that
  condition), Encumbered Reejerey's "it", Moonshadow's "this creature",
  Creakwood Safewright's own end-step trigger. Removing more than is present
  simply takes what is there (CR 122.5 has no floor below zero).
- **"`<any clause>`, then remove a `<kind>` counter from this creature/it."**
  - Heirloom Auntie's own "surveil 1, then remove a -1/-1 counter from this
    creature.": the leading clause is read by the ordinary single-clause
    resolver (`machines/effects._ability_effect_or_notice`, so a leading
    surveil, a leading damage clause, or anything else that already resolves
    on its own reaches this the same way), and the trailing clause is this
    module's own bare removal above, so nothing about "then remove a
    counter" is duplicated between the two.
- **"Return it to the battlefield under its owner's/your control and it
  loses all abilities."** - Retched Wretch's dies trigger, once its own
  intervening *if* ("if it had a `<kind>` counter on it") has already
  answered true through the identical generic `_has_counters` reader above
  (CR 603.10a's look-back, `CardState.last_known_counters`). CR 400.7: the
  returned permanent is a new object, so the "it" that loses all abilities
  is that new incarnation, not the one that died - the selector is keyed to
  its own `zone_change_stamp`, and `machines/layers.lose_all_abilities` is
  reused rather than reimplemented (CR 613.1f).
- **"Put `<n>` `<kind>` counter(s) on each creature."** with no "you
  control"/"target player controls" qualifier at all - Darkness Descends'
  own "Put two -1/-1 counters on each creature.", a true CR 608.2c
  mass-affect-every-creature-on-the-battlefield instruction, distinct from
  `machines/effects._parse_counter_each_creature_target_player_clause`'s
  targeted-player scope and `_parse_counter_each_creature_with_counter_
  clause`'s "you control ... with a counter" filter, neither of which this
  duplicates or widens.
- **"Remove any number of counters from target `<description>`."** - Rhys,
  the Evermore's own activated ability (CR 122.5). No second Modern/
  Pioneer/Standard-legal printing of this exact phrase exists (Scryfall's
  own full-text search turns up only Rhys itself and Eventide's Shadow,
  which is legal nowhere - recorded in MEMORY.md); CR 608.2d does let the
  resolving controller choose fewer than every counter present, but - since
  no `DecisionKind` exists yet for an open-ended amount unconnected to a
  cost - this takes the same scoped simplification `machines/effects._parse_
  remove_up_to_n_counters_from_target_clause` already records for its own
  "remove up to N" sibling: every counter of every kind comes off, the
  maximum a legal choice could ever reach.
- **"Target opponent exiles `<n>` cards from their hand."** - Perfect
  Intimidation's own modal bullet (CR 700.2's "Choose one or both", already
  fully generic in `machines/modes.py` - only this one clause shape was
  missing). The identical CR 701.9b default-chooser shape `machines/
  effects._parse_target_player_discards_clause` already gives its own
  discard sibling, read for CR 406's exile instead.

Every reader here is registered into `machines/counter_effects.parse_
resolution_text`'s own `_WHOLE_TEXT_READERS` tuple (an additive import and
tuple entry there, since that module and this one are both this task's to
add to) rather than into `machines/effects.py` directly, so no reader owned
by another task in this round is ever touched.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .triggers import AbilityOnStack

if TYPE_CHECKING:
    from ..models.game import Game


# ---------------------------------------------------------------------------
# Bristlebane Battler / Reluctant Dounguard / Encumbered Reejerey / Moonshadow
# / Creakwood Safewright: "remove a[n]/N <kind> counter(s) from this
# creature/permanent/artifact/it." with no "if you do" and no "you may".
# ---------------------------------------------------------------------------

_REMOVE_A_COUNTER_FROM_SELF_RE = re.compile(
    rf"^remove (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from "
    r"(?:this (?:creature|permanent|artifact)|it)\.?$",
    re.IGNORECASE,
)


def _remove_counter_from_self_effect(kind: str, amount: int):  # noqa: ANN202
    """The shared effect `_parse_remove_a_counter_from_self_clause` and
    `_parse_then_remove_a_counter_from_self_clause` both build: take up to
    `amount` `kind` counters off the resolving ability's own source, or
    whatever is there if fewer remain (CR 122.5 has no floor)."""

    def effect(game: Game, ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        present = source.counter_count(kind)
        take = min(present, amount)
        if take > 0:
            source.remove_counters(kind, take)

    return effect


def _parse_remove_a_counter_from_self_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`_REMOVE_A_COUNTER_FROM_SELF_RE`'s shape; see the module banner."""
    if for_spell:
        return None
    match = _REMOVE_A_COUNTER_FROM_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount < 1:
        return None
    from . import effects

    kind = effects._counter_kind(match.group("kind"))
    return _remove_counter_from_self_effect(kind, amount)


# ---------------------------------------------------------------------------
# Heirloom Auntie: "<any clause>, then remove a <kind> counter from this
# creature/it."
# ---------------------------------------------------------------------------

_THEN_REMOVE_A_COUNTER_FROM_SELF_RE = re.compile(
    r"^(?P<first>.+?), then "
    rf"remove (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from "
    r"(?:this (?:creature|permanent|artifact)|it)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = text[:1].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def _parse_then_remove_a_counter_from_self_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`_THEN_REMOVE_A_COUNTER_FROM_SELF_RE`'s shape: Heirloom Auntie's own
    "surveil 1, then remove a -1/-1 counter from this creature." The leading
    clause is read by `machines/effects._ability_effect_or_notice`, the same
    single-clause resolver every other whole-text reader in this file's
    sibling modules (`machines/counter_payoffs._resolution_clause`) already
    duplicates rather than imports, to keep this module and `machines/
    effects.py` free of a mutual import at load time - both reach the other
    only lazily, the same way `counter_payoffs.py` does.
    """
    if for_spell:
        return None
    match = _THEN_REMOVE_A_COUNTER_FROM_SELF_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount < 1:
        return None
    from . import effects

    first_text = match.group("first").strip()
    first_effect = effects._ability_effect_or_notice(_sentence(first_text))
    if first_effect is None:
        return None
    kind = effects._counter_kind(match.group("kind"))
    remove_effect = _remove_counter_from_self_effect(kind, amount)

    def effect(game: Game, ability: AbilityOnStack) -> None:
        first_effect(game, ability)
        game.announce_batched_events()  # CR 603.2c: one event per instruction
        remove_effect(game, ability)

    return effect


# ---------------------------------------------------------------------------
# Retched Wretch: "return it to the battlefield under its owner's/your
# control and it loses all abilities."
# ---------------------------------------------------------------------------

_RETURN_SELF_LOSES_ALL_ABILITIES_RE = re.compile(
    r"^return (?:it|them|this (?:creature|permanent|card)) to the battlefield "
    r"under (?P<control>its owner'?s|their owners'?|your) control and "
    r"(?:it|they) loses? all abilities\.?$",
    re.IGNORECASE,
)


def _parse_return_self_loses_all_abilities_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`_RETURN_SELF_LOSES_ALL_ABILITIES_RE`'s shape - Retched Wretch's own
    dies trigger, once its "if it had a `<kind>` counter on it" intervening
    *if* has already answered true (CR 603.4, read generically by `machines/
    conditions/objects._has_counters`'s own past-tense branch - nothing here
    duplicates that check).

    CR 400.7: the returned permanent is a *new* object wherever it lands, so
    "it loses all abilities" is a fresh layer 6 removal (CR 613.1f) on that
    new incarnation - `machines/layers.lose_all_abilities`, the identical
    modification `machines/layers._attached_doesnt_untap_builder`'s own
    "loses all abilities and doesn't untap" rider already applies, keyed to
    `zone_change_stamp` so it never reaches back to the card that died. The
    return only happens if the card is still in the graveyard it died into
    (a response that exiled it in the meantime left a new object behind,
    CR 400.7 again) - the same gate every other "return it to the
    battlefield" reader in the pool already uses.
    """
    if for_spell:
        return None
    match = _RETURN_SELF_LOSES_ALL_ABILITIES_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    control = match.group("control").lower()
    under_owner = control.startswith("its") or control.startswith("their")

    def effect(game: Game, ability: AbilityOnStack) -> None:
        from .layers import (
            ContinuousEffect,
            Duration,
            Layer,
            lose_all_abilities,
            only_this_incarnation,
        )

        source = ability.source(game)
        if source is None or source.zone is not Zone.GRAVEYARD:
            return
        controller = (source.owner or ability.controller) if under_owner else ability.controller
        with game.entering_together():
            returned = game.put_onto_battlefield(source, controller)
            if returned.zone is not Zone.BATTLEFIELD:
                return
            game.continuous_effects.add(
                ContinuousEffect(
                    description=f"{returned.name}: loses all abilities",
                    layer=Layer.ABILITY,
                    timestamp=game.continuous_effects.tick(),
                    duration=Duration.INDEFINITE,
                    selector=only_this_incarnation(returned, returned.zone_change_stamp),
                    modification=lose_all_abilities,
                )
            )

    return effect


# ---------------------------------------------------------------------------
# Darkness Descends: "put <n> <kind> counter(s) on each creature." - every
# creature on the battlefield, no controller qualifier at all.
# ---------------------------------------------------------------------------

_COUNTER_EACH_CREATURE_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each creature\.?$",
    re.IGNORECASE,
)


def _parse_counter_each_creature_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`_COUNTER_EACH_CREATURE_RE`'s shape; see the module banner. Distinct
    from `machines/effects._parse_counter_each_creature_target_player_
    clause` ("each creature target player controls") and `_parse_counter_
    each_creature_with_counter_clause` ("each creature you control with a
    counter on it") - this is CR 608.2c's unqualified "each creature",
    every creature on the battlefield regardless of controller, and neither
    existing reader's regex matches that bare shape.
    """
    match = _COUNTER_EACH_CREATURE_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount < 1:
        return None
    from . import effects

    kind = effects._counter_kind(match.group("kind"))

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        for permanent in list(game.battlefield):
            if game.characteristics_of(permanent).is_creature:
                game.add_counters(permanent, kind, amount)

    return effect


# ---------------------------------------------------------------------------
# Rhys, the Evermore: "remove any number of counters from target <phrase>."
# ---------------------------------------------------------------------------

_REMOVE_ANY_NUMBER_OF_COUNTERS_FROM_TARGET_RE = re.compile(
    r"^remove any number of counters from (?P<phrase>target .+?)\.?$",
    re.IGNORECASE,
)


def _parse_remove_any_number_of_counters_from_target_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`_REMOVE_ANY_NUMBER_OF_COUNTERS_FROM_TARGET_RE`'s shape; see the
    module banner's note on the scoped simplification this takes."""
    if for_spell:
        return None
    match = _REMOVE_ANY_NUMBER_OF_COUNTERS_FROM_TARGET_RE.fullmatch(text.strip())
    if match is None:
        return None
    from . import effects

    if not effects._targets_understood(match.group("phrase"), count_agnostic=False):
        return None

    def effect(game: Game, ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            for kind in list(target.counters):
                present = target.counter_count(kind)
                if present:
                    target.remove_counters(kind, present)

    return effect


# ---------------------------------------------------------------------------
# Perfect Intimidation: "target opponent exiles <n> cards from their hand."
# ---------------------------------------------------------------------------

_TARGET_OPPONENT_EXILES_FROM_HAND_RE = re.compile(
    rf"^target opponent exiles (?P<n>{COUNT}) cards? from their hand\.?$",
    re.IGNORECASE,
)


def _parse_target_opponent_exiles_from_hand_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`_TARGET_OPPONENT_EXILES_FROM_HAND_RE`'s shape - CR 701.9b's default
    chooser (the affected player themselves) over CR 406's exile instead of
    `machines/effects._parse_target_player_discards_clause`'s graveyard."""
    match = _TARGET_OPPONENT_EXILES_FROM_HAND_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None or count < 1:
        return None
    from . import effects

    if not effects._targets_understood("target opponent", allow_player_targets=True):
        return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        from ..models.player import Player
        from .decisions import Decision, DecisionKind, source_id_of

        source = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            needed = min(count, len(target.hand))
            if needed <= 0:
                continue
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=target.username,
                    prompt=f"exile {needed} card(s) from your hand",
                    source=source,
                    amount=needed,
                    cards=tuple(state.id for state in target.hand),
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in target.hand}
            for card_id in chosen_ids:
                chosen = by_id[card_id]
                target.cards_in(Zone.HAND).remove(chosen)
                chosen.move_to(Zone.EXILE)
                game.exile.append(chosen)

    return effect


_WHOLE_TEXT_READERS = (
    _parse_remove_a_counter_from_self_clause,
    _parse_then_remove_a_counter_from_self_clause,
    _parse_return_self_loses_all_abilities_clause,
    _parse_counter_each_creature_clause,
    _parse_remove_any_number_of_counters_from_target_clause,
    _parse_target_opponent_exiles_from_hand_clause,
)


def parse_resolution_text(text: str, *, for_spell: bool = False):  # noqa: ANN201
    """One of this module's whole-text resolution shapes, or `None`. Chained
    onto `machines/counter_effects.parse_resolution_text` (the counter-effect
    extension point `machines/effects.py` already calls at every whole-text
    resolution attempt, including once per modal bullet - CR 700.2's "Choose
    one or both" is already generic in `machines/modes.py`), so nothing new
    has to be wired into `machines/effects.py` itself for this task's own
    readers to reach a real ability."""
    whole = collapsed(text)
    for reader in _WHOLE_TEXT_READERS:
        effect = reader(whole, for_spell=for_spell)
        if effect is not None:
            return effect
    return None
