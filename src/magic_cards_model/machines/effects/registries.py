import re
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.player import Player
from ...models.zone import Zone
from ..abilities import (
    TriggerEvent,
    legendary_self_pronoun_normalized,
)
from ..delayed import (
    DelayedTrigger,
    GrantExtraTurn,
)
from ..layers import (
    ContinuousEffects,
)
from ..modes import (
    is_modal_text,
    strip_x_restrictions,
    substitute_x,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game
from ._common import AbilityEffect, Effect
from .damage import damage_the_attacked_player, damage_the_other_combatant
from .removal import hangarback_dies

#: The narrower half of the pattern above, on its own: CR 602.5d's "Activate
#: only as a sorcery." / "Activate only once each turn." printed as a trailing
#: sentence on an activated ability. Budding Insurgent's own "Sacrifice this
#: creature: Destroy target artifact or enchantment. If that permanent was a
#: legendary enchantment, draw a card. Activate only as a sorcery." is one
#: CR 608.2c instruction sequence plus this timing rule tacked on at the end -
#: not itself an instruction, so `_prepare_effect_clauses`/`_parse_mixed_
#: clause` should never see it at all. Stripped once, generically, ahead of
#: every activated ability's own dispatch, rather than case by case: this
#: restriction is un-worded (CR 602.5d gives no other shape), so nothing here
#: is a card-specific fit.
_TRAILING_ACTIVATION_TIMING_RESTRICTION_RE = re.compile(
    r"\s*\bactivate only [^.]*\.\s*$", re.IGNORECASE
)

#: "This ability costs `<N>` less to activate if it targets a `<quality>`
#: with power `<M>` or less/greater." (Raft Security Officer) - `machines/
#: abilities.py` (locked to another C02 task this round) reads this trailing
#: sentence as part of the ability's own *effect* rather than splitting it
#: into `ActivatedAbility.cost_reduction` the way it already does for a
#: "for each `<quality>` you control" cost reduction, so "Tap target
#: creature." never reached any effect parser with this rider still glued
#: onto it. `Game._activation_target_cost_reduction` is what actually reads
#: and applies the rider (CR 601.2f via CR 602.2b); this only clears it out
#: of the way so the sentence in front of it parses.
_TRAILING_ACTIVATION_TARGET_COST_REDUCTION_RE = re.compile(
    r"\s*this ability costs \{\d+\} less to activate if it targets "
    r"an? [a-z]+ with power \d+ or (?:less|greater)\.\s*$",
    re.IGNORECASE,
)


#: Effects by card name. Everything absent resolves without doing anything.
#
# "Lightning Bolt": "Lightning Bolt deals 3 damage to any target." is not
# entered here any more - a single clause of exactly the shape
# `parse_targeted_effect_for_spell` reads off the card's own printed text, so
# `effect_for`'s fallback reaches it (and any future card with the same
# shape, for free). Re-adding a row here would silently shadow the parser
# again; see `test_no_card_has_a_registry_entry_that_would_shadow_the_targeted_effect_parser`.
#
# "Lightning Helix": "Lightning Helix deals 3 damage to any target and you
# gain 3 life." is not entered here any more either - it mixes a targeted
# clause and a player clause, which `parse_mixed_effect_for_spell` now reads
# clause by clause, trying the targeted parser and then the player parser on
# each one. See `test_registry_is_minimal.py`.
#
# "Counterspell": "Counter target spell." is not entered here any more
# either (this wave): `_COUNTER_TARGET_SPELL_RE`, added for a modal card's
# own unconditional "Counter target spell." mode (Cryptic Command), is read
# by `_parse_targeted_clause` off the card's own text with no row needed, so
# `effect_for`'s fallback reaches it too. See `test_registry_is_minimal.py`.
EFFECTS: dict[str, Effect] = {
    # "Swords to Plowshares": "Exile target creature. Its controller gains
    # life equal to its power." is not entered here any more (this wave):
    # `_parse_anaphoric_clause_pair` reads both sentences as one CR 608.2c
    # instruction off the card's own printed text, so `effect_for`'s fallback
    # reaches it - and reads the life gain the old `exile_targets` row never
    # did. See `test_registry_is_minimal.py`.
    # "Electrolyze deals 2 damage divided as you choose among one or two
    # targets. Draw a card." is not entered here any more: `_DIVIDED_DAMAGE_RE`
    # reads the first clause off the card's own printed text (CR 601.2d), the
    # draw is `parse_clause_effect`'s ordinary player clause, and
    # `effect_for`'s fallback reaches both in printed order. See
    # `test_registry_is_minimal.py`.
    # "Twisted Image": "Switch target creature's power and toughness until
    # end of turn. Draw a card." is not entered here any more:
    # `_parse_switch_power_toughness_then_draw_clause` reads the whole text,
    # ahead of the ordinary clause split, off the card's own printed text
    # (CR 608.2c: the switch first, then the draw, in the order printed), so
    # `effect_for`'s fallback reaches it and a future card sharing the
    # template with a different draw count is covered for free.
    # "Giant Growth" and "Dismember" are not entered here any more (W5): both
    # are exactly `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s shape, read off the
    # card's own printed text (Dismember's Phyrexian-mana reminder line
    # stripped like any other), so `effect_for`'s fallback reaches them. See
    # `test_registry_is_minimal.py`.
    # "Lava Dart" is not entered here any more: its first line is exactly
    # `_DAMAGE_TARGET_RE`'s shape (Lightning Bolt's own), and its second -
    # "Flashback—Sacrifice a Mountain." (CR 702.34a) - is now recognised as a
    # keyword-ability line by shape rather than by keyword and stripped before
    # the clause split (`_strip_keyword_ability_lines`), so the fallback
    # reaches the damage. The row was only ever there because the em-dash cost
    # form of a keyword line had no regex of its own. See
    # `tests/test_targeted_effects.py::
    # test_a_flashback_line_no_longer_takes_the_whole_effect_down`.
    # "Unholy Heat": "Unholy Heat deals 2 damage to target creature or
    # planeswalker. Delirium - Unholy Heat deals 6 damage instead if there
    # are four or more card types among cards in your graveyard." is not
    # entered here any more: `_parse_delirium_damage_instead_clause` reads
    # the whole text off the card's own printed name and numbers, so
    # `effect_for`'s fallback reaches it and a future card sharing the
    # template with a different pair of damage amounts is covered for free.
    # -- tokens (CR 111, CR 701.7a) -------------------------------------
    # Spectral Procession's "Create three 1/1 white Spirit creature tokens
    # with flying." is not entered here any more (W4): the whole spell is one
    # clause of `_parse_token_clause`'s shape, read off the card's own printed
    # text, so `effect_for`'s fallback reaches it. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # Malevolent Rumble's reveal-four, take-a-permanent, rest-to-graveyard run
    # is not entered here any more: it is
    # `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`'s template, shared
    # with Grisly Salvage and Satyr Wayfinder, and its Eldrazi Spawn is
    # `_parse_token_clause`'s. See `tests/scenarios/test_registry_is_minimal.py`.
    # "Monstrous Rage": "Target creature gets +2/+0 until end of turn. Create
    # a Monster Role token attached to it." is not entered here any more:
    # the pump is `_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s existing shape and the
    # token creation is `_parse_create_role_token_clause`'s (CR 111.10j-r),
    # both read off the card's own printed text, so `effect_for`'s fallback
    # reaches both clauses. See `tests/scenarios/test_registry_is_minimal.py`.
    # "Savor the Moment": "Take an extra turn after this one. Skip the untap
    # step of that turn." is not entered here any more: `_TAKE_EXTRA_TURNS_RE`
    # and `_SKIP_UNTAP_STEP_OF_THAT_TURN_RE` read both sentences as
    # `parse_clause_effect` clauses off the card's own printed text, so
    # `effect_for`'s fallback reaches it. See `test_registry_is_minimal.py`.
    # Preordain's "Scry 2, then draw a card." is not entered here any more:
    # it is two clauses of exactly the shape `parse_player_effect_for_spell`
    # reads off the card's own printed text (`scry N`, then `draw a card`),
    # so `effect_for`'s fallback reaches it. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # -- decisions during resolution (CR 608.2d) ------------------------
    # -- prevention (CR 615) --------------------------------------------
    # "Fog"/"Angelsong": "Prevent all combat damage that would be dealt this
    # turn." are not entered here any more: `_PREVENT_ALL_COMBAT_DAMAGE_RE`
    # reads the sentence verbatim off the card's own printed text, so
    # `effect_for`'s fallback reaches both (Angelsong's cycling is a way to
    # discard it rather than cast it, CR 702.29a, and never reaches this
    # parser at all). See `test_registry_is_minimal.py`.
    #
    # "Bandage": "Prevent the next 1 damage that would be dealt to any target
    # this turn. Draw a card." is not entered here any more either:
    # `_PREVENT_NEXT_DAMAGE_TO_TARGET_RE` reads the first clause, the draw is
    # the ordinary player clause, and `effect_for`'s fallback runs both in
    # printed order (CR 608.2c). See `test_registry_is_minimal.py`.
    #
    # "Awe Strike": "The next time target creature would deal damage this
    # turn, prevent that damage. You gain life equal to the damage prevented
    # this way." is not entered here any more either:
    # `_merge_prevent_damage_from_target_clauses` reads both sentences as one
    # CR 608.2c instruction (the second is CR 615.5's rider, not independent
    # of the first), so `effect_for`'s fallback reaches it. See
    # `test_registry_is_minimal.py`.
}


#: CR 601.3b's own timing restriction, printed on the card itself (distinct
#: from `machines/casting_restrictions.py`'s "who may cast when" statics) -
#: Reset's "Cast this spell only during an opponent's turn after their upkeep
#: step." A restriction on *when* the spell may be cast is not one of CR
#: 608.2c's resolution instructions, so left in the text it poisons the real
#: instruction after it exactly the way `_strip_self_shuffle_clause` above
#: describes for Green Sun's Zenith - stripped here, once, generically by its
#: own un-worded shape, ahead of every spell's own dispatch.
_CAST_TIMING_RESTRICTION_RE = re.compile(r"\s*\bcast this spell only [^.]*\.\s*", re.IGNORECASE)


def effect_for(
    card_name: str, effect_text: str | None = None, *, x_value: int | None = None
) -> Effect | None:
    """A spell's effect: an explicit `EFFECTS` row if there is one, otherwise
    `parse_mixed_effect_for_spell` on the card's own oracle text - one
    per-clause dispatcher that tries each clause as a targeted clause and then
    as a player clause, so a card mixing both kinds (Lightning Helix) parses
    without needing a row. An explicit row always wins, so nothing already
    scripted changes behaviour.

    A modal card (CR 700.2's bulleted "Choose one/two/...") is dispatched to
    `resolve_modal_spell` instead: `_prepare_effect_clauses` refuses modal text
    outright (a bulleted list is not a linear sequence of clauses), so nothing
    would otherwise reach it. `resolve_modal_spell` reads which modes were
    chosen off `Game.cast_record` and runs each one's own clause, keyed by
    nothing but the card's own printed text - no per-card row needed here
    either.

    `x_value` is CR 107.3a's X as the caster announced it, read by the caller
    off `Game.cast_record` - `None` for a spell with no `{X}` in its own mana
    cost, which leaves every bare "X" in the text alone. That matters: a card
    that defines its own X in its rules text instead (Craterhoof Behemoth's
    "get +X/+X ... where X is the number of creatures you control") is CR
    107.3f's X, not CR 107.3a's, and substituting the cast X into it would be
    wrong, not merely unhelpful - `None` keeps this function out of that
    card's way entirely.

    Given a real value, the *unsubstituted* text is still tried first:
    Wrath of the Skies's `_parse_x_energy_pay_destroy_by_mana_value` and
    Galvanic Discharge's `_parse_target_get_energy_pay_damage` already read
    `Game.cast_record` for themselves at resolution and match the literal
    word "X" in their own regex - substituting it away first would silently
    turn a working parser into a non-match. Only if that first pass reads
    nothing is the text substituted (the same way `machines/modes.py`'s
    `substitute_x` already does for a modal spell's own mode text) and tried
    again, which is what makes a search's "mana value X or less" readable by
    `_SEARCH_AND_PUT_RE`'s `\\d+` group.
    """
    explicit = EFFECTS.get(card_name)
    if explicit is not None:
        return explicit
    if effect_text is None:
        return None
    effect_text = spell_resolution_text(card_name, effect_text)
    if is_modal_text(effect_text):
        return resolve_modal_spell
    effect = _spell_effect_or_notice(effect_text)
    if (effect is None or _is_notice_only(effect)) and x_value is not None:
        # A notice on the literal "X" is not the last word: Fractalize's
        # "base power and toughness each equal to X plus 1" reads only once
        # the announced X is written in (CR 107.3a).
        substituted = _spell_effect_or_notice(substitute_x(effect_text, x_value))
        if substituted is not None and (effect is None or not _is_notice_only(substituted)):
            effect = substituted
    if (
        effect is not None
        and not _is_notice_only(effect)
        and getattr(effect, "unparsed_remainder", None) is None
    ):
        return effect
    time_counters: int | None = None
    rest_text = _strip_self_exile_sentence(card_name, effect_text)
    if rest_text is None:
        with_counters = _strip_self_exile_with_time_counters_sentence(card_name, effect_text)
        if with_counters is None:
            return effect
        rest_text, time_counters = with_counters
    rest = _spell_effect_or_notice(rest_text)
    if rest is None and x_value is not None:
        rest = _spell_effect_or_notice(substitute_x(rest_text, x_value))
    if rest is None or _is_notice_only(rest):
        return effect
    return _then_exile_self(rest, time_counters=time_counters)


#: A deck-construction line - "A deck can have any number of cards named
#: `<name>`." (the Approach cycle, Persistent Petitioners) or "... up to
#: `<n>` cards named ..." - which CR 100.2a's four-copy rule defers to and
#: `models/deck.py` reads. It says nothing about resolving the spell.
_DECK_CONSTRUCTION_LINE_RE = re.compile(
    r"^A deck can have (?:any number of|up to \w+) cards named [^\n]*\.[ \t]*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)


def spell_resolution_text(card_name: str, effect_text: str) -> str:
    """A spell's printed text less every paragraph and sentence `effect_for`
    knows is not part of its own resolution: the self-shuffle a replacement
    effect performs (`machines/replacement.py`), a trailing flashback line, a
    leading cast trigger (CR 601.2i) and a trailing triggered or activated
    ability (each its own object, CR 113.6k/113.6j), and a cast-timing
    restriction (read at casting), and a deck-construction line
    (`_DECK_CONSTRUCTION_LINE_RE`). What is left is what the resolution
    readers are handed - and what the support oracle's ablation probe
    removes sentences from."""
    effect_text = _strip_self_is_all_colors_sentence(card_name, effect_text)
    effect_text = _strip_self_shuffle_clause(card_name, effect_text)
    effect_text = _strip_trailing_flashback_line(effect_text)
    effect_text = _strip_leading_standalone_cast_trigger(effect_text)
    effect_text = _strip_trailing_standalone_triggered_ability(effect_text)
    effect_text = _strip_trailing_standalone_activated_ability(effect_text)
    effect_text = _DECK_CONSTRUCTION_LINE_RE.sub("", effect_text)
    effect_text = strip_x_restrictions(effect_text)
    return _CAST_TIMING_RESTRICTION_RE.sub(" ", effect_text).strip()


def delver_upkeep(game: "Game", ability: AbilityOnStack) -> None:
    """Delver of Secrets: "look at the top card of your library. You may reveal
    that card. If an instant or sorcery card is revealed this way, transform this
    creature."

    Not an intervening *if* (CR 603.4) - the condition is inside the effect, so
    the ability triggers and goes on the stack whatever is on top of the library,
    and only the transform is conditional. The optional reveal is always taken.
    """
    player = game.player(ability.controller)
    if not player.library:
        return
    top = player.library[0]
    if not set(top.card.types) & {Type.INSTANT, Type.SORCERY}:
        return
    source = ability.source(game)
    if source is not None and source.zone is Zone.BATTLEFIELD:
        source.transform()  # CR 701.27a


def tishanas_tidebinder(game: "Game", ability: AbilityOnStack) -> None:
    """ "Counter up to one target activated or triggered ability."

    CR 113.9: "Activated and triggered abilities on the stack aren't spells, and
    therefore can't be countered by anything that counters only spells.
    Activated and triggered abilities on the stack can be countered by spells
    and abilities that specifically counter abilities." `Game.counter` handles
    both, removing the ability from the stack and putting it nowhere (CR 405.1).

    The target is looked for on the stack by id rather than through
    `Game.resolve_target`, which only ever finds `CardState`s - the same reason
    `counter_targets` walks the stack itself.

    **The second sentence** - "If an ability of an artifact, creature, or
    planeswalker is countered this way, that permanent loses all abilities for
    as long as this creature remains on the battlefield" - is a layer 6
    continuous effect (CR 613.1f) created by this resolving ability (CR 611.2),
    with the "for as long as" duration of CR 611.2b. It is recorded in the
    game's `ContinuousEffects` store, and CR 611.2b's corner case is handled
    there: a Tidebinder that has already left the battlefield when this trigger
    resolves creates nothing, because the duration never starts.

    The countered ability's *source* is the permanent that loses its abilities,
    which is why the source is read off the ability before it is countered - by
    then the ability object is gone from the stack (CR 405.1).

    None of this is reachable yet. `Game.resolve_target` only ever finds a
    `CardState`, so the trigger's target resolves to nothing and CR 608.2b
    removes the trigger before this runs at all - see `docs/engine-coverage.md`
    and the xfails in `tests/scenarios/test_countering_an_ability.py`.
    """
    store: ContinuousEffects | None = continuous_effects(game)
    tidebinder = ability.source(game)
    for reference in ability.targets:
        if not reference.is_card:
            continue
        target = next(
            (item for item in game.stack if is_ability(item) and item.id == reference.card_id),
            None,
        )
        if target is None:
            continue
        permanent = game.find_by_id(target.source_id) if target.source_id else None
        game.counter(target)
        if store is None or tidebinder is None:
            continue
        if permanent is not None and permanent.zone is Zone.BATTLEFIELD:
            store.create(tidebinder, targets=[permanent], game=game)


def emrakul_cast_trigger(game: "Game", ability: AbilityOnStack) -> None:
    """Emrakul, the Promised End: "When you cast this spell, you gain control of
    target opponent during that player's next turn. After that turn, that player
    takes an extra turn."

    Two things happen, in the order printed (CR 608.2c), but only the first
    happens *now*.

    **The extra turn has to be a delayed triggered ability (CR 603.7), not part
    of this resolution.** CR 500.7 adds an extra turn "directly after the
    specified turn", so granting it while this trigger resolves would insert it
    directly after the current turn - which is *before* the turn Emrakul's
    controller is about to steal - and the victim would take their extra turn
    first. "After that turn" is a later moment, and CR 603.7 is what says a later
    moment is expressed as a delayed trigger: "An effect may create a delayed
    triggered ability that can do something at a later time."

    CR 603.7e gives it Emrakul's controller and Emrakul as its source, since a
    triggered ability created it. It waits for the end step of the controlled
    player's turn - `only_when_active` is how "that turn" is named, there being
    no turn object to point at - and CR 603.7b's default of triggering once is
    exactly right for a one-off extra turn.

    The control itself is CR 723.1's: `Game.gain_control_of_player` queues it
    for the player's next turn and `TurnMachine` ends it as the following
    turn begins.

    There being no target chosen leaves this doing nothing, which is CR 608.2b's
    outcome for a trigger whose targets are all gone anyway.
    """
    for target in game.resolve_targets(ability):
        username = target.username if isinstance(target, Player) else None
        if username is None or username == ability.controller:
            continue
        game.gain_control_of_player(ability.controller, username)
        game.create_delayed_trigger(
            DelayedTrigger(
                text="After that turn, that player takes an extra turn.",
                effect=GrantExtraTurn(),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name="Emrakul, the Promised End",
                subject_player=username,
                only_when_active=username,
            )
        )


#: One triggered ability, identified: the card it is printed on, the event it
#: watches, and a lowercase fragment of its own printed text. The fragment is
#: empty for a card whose triggers on that event are all one entry's business.
TriggerKey = tuple[str, TriggerEvent, str]

#: What a triggered ability does, by `(card name, trigger event, marker)`.
TRIGGER_EFFECTS: dict[TriggerKey, AbilityEffect] = {
    # White Orchid Phantom's "When this creature enters, destroy up to one
    # target nonbasic land. Its controller may search their library for a
    # basic land card, put it onto the battlefield tapped, then shuffle." is
    # not entered here any more (W3): the destroy is `_parse_targeted_clause`'s
    # shape and the search is `_parse_search_clause`'s "its controller may"
    # shape (see `_build_search_clause`), two clauses `parse_mixed_effect`
    # reads in the order printed (CR 608.2c). See
    # `tests/scenarios/test_registry_is_minimal.py`.
    #
    # Solemn Simulacrum's two triggers are not entered here any more. Its
    # enters trigger - "you may search your library for a basic land card,
    # put that card onto the battlefield tapped, then shuffle." - is exactly
    # `parse_search_and_put_effect`'s shape; its dies trigger - "you may draw
    # a card." - is a single `parse_player_effect` clause. Both are reached by
    # `trigger_effect_for`'s fallback. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # Guttersnipe's "this creature deals 2 damage to each opponent" is not
    # entered here any more: `_DAMAGE_EACH_OPPONENT_RE` reads it off the
    # ability's own printed text, so `trigger_effect_for`'s fallback reaches
    # it. See `tests/scenarios/test_registry_is_minimal.py`.
    ("Hellrider", TriggerEvent.ATTACKS, ""): damage_the_attacked_player(1),
    ("Ashmouth Hound", TriggerEvent.BLOCKS, ""): damage_the_other_combatant(1),
    ("Delver of Secrets", TriggerEvent.BEGINNING_OF_STEP, ""): delver_upkeep,
    # Thopter Assembly's own "return this creature to its owner's hand and
    # create five 1/1 colorless Thopter artifact creature tokens with
    # flying." is not entered here any more: it is
    # `_parse_return_self_then_create_tokens_clause`'s shape, read off the
    # card's own printed text ("this creature" is CR 201.5's own self-
    # reference, not the literal name), so `trigger_effect_for`'s fallback
    # reaches it and a future card sharing the template with a different
    # token count is covered for free.
    # Devourer of Destiny's cast trigger - "exile target permanent that's one
    # or more colors" - is not entered here any more: it is the single-clause
    # shape `parse_targeted_effect` reads off the ability's own printed text
    # (the "that's one or more colors" restriction is not enforced either way -
    # see `docs/engine-coverage.md`), so
    # `trigger_effect_for`'s fallback reaches it. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    ("Tishana's Tidebinder", TriggerEvent.ENTERS_THE_BATTLEFIELD, ""): tishanas_tidebinder,
    # Ulamog, the Ceaseless Hunger's "When you cast this spell, exile two
    # target permanents." and both of Ugin, Eye of the Storms' CAST_SPELL
    # triggers - "exile up to one target permanent that's one or more colors"
    # on each - are not entered here any more: `_targets_understood` now
    # accepts a count-agnostic exile ("two target ...", "up to one target
    # ...") the same way it already accepted exactly one, so
    # `parse_targeted_effect` reads all three off the ability's own printed
    # text and `trigger_effect_for`'s fallback (still keyed by marker for
    # Ugin's two entries) reaches them. The "that's one or more colors"
    # restriction is still not enforced either way. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # Sowing Mycospawn's "When you cast this spell, if it was kicked, exile
    # target land" - deliberately has no entry: once its intervening *if*
    # (CR 603.4, CR 702.33d - read off `Game.cast_record(spell).kicked` by
    # `machines/triggers.intervening_if_holds`) lets it trigger at all, "exile
    # target land" is one clause of `parse_targeted_effect`'s shape, read off
    # the ability's own printed text, so `trigger_effect_for`'s fallback
    # reaches it the same way Devourer of Destiny's does above.
    #
    #
    # Ranger-Captain of Eos's "you may search your library for a creature card
    # with mana value 1 or less, reveal it, put it into your hand, then
    # shuffle." is not entered here any more either (W3): the mana-value bound
    # is `_SEARCH_AND_PUT_RE`'s own `max_mv` group now, so the whole sentence -
    # one clause - is `_parse_search_clause`'s shape and `trigger_effect_for`'s
    # fallback reaches it. See `tests/scenarios/test_registry_is_minimal.py`.
    ("Emrakul, the Promised End", TriggerEvent.CAST_SPELL, ""): emrakul_cast_trigger,
    # -- tokens (CR 111, CR 701.7a) -------------------------------------
    # Ajani, Nacatl Pariah's enters trigger - "create a 2/1 white Cat Warrior
    # creature token." - is not entered here any more (W4): one clause of
    # `_parse_token_clause`'s shape, read off the ability's own printed text,
    # so `trigger_effect_for`'s fallback reaches it.
    #
    # Drowner of Truth's cast trigger - "create two 0/1 colorless Eldrazi
    # Spawn creature tokens with 'Sacrifice this token: Add {C}.'" - is not
    # entered here any more either: the same shape, quoted rules text
    # included. Its intervening *if* ("if {C} was spent to cast it") now reads
    # `Game.cast_record(spell).mana_of_color_spent(Color.COLORLESS)` off
    # CR 601.2h's payment (`machines/triggers.intervening_if_holds`), so the
    # trigger only reaches the stack - and this fallback only runs - when
    # colorless mana genuinely paid for it.
    #
    # Wurmcoil Engine's dies trigger - two tokens, "with deathtouch and a ...
    # token with lifelink" - is not entered here any more either: CR 608.2c's
    # clause split cuts the sentence at "and" into two noun phrases, and each
    # is `_parse_token_clause`'s shape on its own. This is the entry that
    # makes a **token copy of Wurmcoil Engine** behave: CR 707.2 copies the
    # printed text, so the copy has this trigger too, and CR 111.7's
    # parenthesis - "if a token changes zones, applicable triggered abilities
    # will trigger before the token ceases to exist" - is what lets a dying
    # Wurm token fire it.
    #
    # See `tests/scenarios/test_registry_is_minimal.py` for all three.
    #
    # Ocelot Pride's end-step trigger - "if you gained life this turn, create
    # a 1/1 white Cat creature token. Then if you have the city's blessing,
    # for each token you control that entered this turn, create a token
    # that's a copy of it." - is not entered here either. Every ability in
    # this project must be read as a whole paragraph (see the design ruling in
    # `docs/engine-coverage.md`): a card-name row that ran only the first
    # sentence, unconditionally, while the second - the whole point of
    # *ascend* and the city's blessing - silently never ran, is exactly the
    # half-execution CR 608.2c forbids, and this project's history has a real
    # game where that bug went unnoticed for two whole turns. Both sentences
    # are readable now: the first is `_parse_token_clause`'s ordinary shape,
    # and the second is `_parse_city_blessing_token_copy_clause`'s (CR 702.131,
    # CR 707.2), so `trigger_effect_for`'s fallback reads the whole ability
    # with no row at all, and a future ascend card with the same "for each
    # token you control that entered this turn, create a token that's a copy
    # of it" shape is covered for free. See `tests/scenarios/test_ascend.py`.
    # Seasoned Pyromancer's own "discard two cards, then draw two cards. For
    # each nonland card discarded this way, create a 1/1 red Elemental
    # creature token." is not entered here any more: it is
    # `_parse_discard_then_draw_token_per_nonland_clause`'s shape, read off
    # the card's own printed text, so `trigger_effect_for`'s fallback reaches
    # it and a future card sharing the template with a different discard,
    # draw, or token count is covered for free.
    ("Hangarback Walker", TriggerEvent.DIES, ""): hangarback_dies,
    # Ragavan, Nimble Pilferer's, Nashi, Searcher in the Dark's, and Questing
    # Beast's combat-damage-to-a-player triggers are not entered here at all
    # (CR 120.2a): the condition - "whenever [this creature] deals combat
    # damage to a player"/"to an opponent" - is read generically off any
    # card's own printed text by `TriggerEvent.DEALS_DAMAGE` and
    # `machines/triggers.condition_matches`, and the *resolution* is now
    # `parse_mixed_effect`'s business too. "Create a Treasure token" is
    # `_parse_token_clause`'s shape; "exile the top card of that player's
    # library" is `_parse_exile_that_players_library_clause`'s, reading "that
    # player" off `ability.event.player` (CR 607.1's within-one-ability
    # anaphora back to the trigger's own object) rather than a target the
    # ability ever announces. Ragavan's third sentence - "Until end of turn,
    # you may cast that card" - is read too, as the second half of
    # `_parse_exile_then_play_permission_pair`: one CR 608.2c instruction with
    # the exiling clause it points back at, granting a `machines/casting.
    # PlayPermission` over exactly the card just exiled. So Ragavan's whole
    # paragraph now runs and leaves no notice. **Nashi's does too**: its three
    # sentences are read together by
    # `_parse_mill_that_many_then_take_from_among_them` - the mill for
    # `GameEvent.amount`, the "from among them" choice over exactly the cards
    # that mill put in the graveyard (CR 400.7), and the counter that depends
    # on whether any were taken. Only Questing Beast's still leaves a notice
    # (CR 608.2c has no notion of running half an effect - see
    # `_ability_effect_or_notice`): "target planeswalker that player controls"
    # is a missing-primitive shape, read by
    # `_unreadable_event_player_target_clause` - see
    # `tests/scenarios/test_trigger_events.py` for the trigger firing and
    # `tests/scenarios/test_combat_damage_to_player_effects.py` for the
    # resolution.
    # Soul Warden's "Whenever another creature enters, you gain 1 life." and
    # the surveil lands' (Elegant Parlor, Thundering Falls) and Dragon's Rage
    # Channeler's "surveil 1" are deliberately **not** entered here any more.
    # Each is one clause of exactly the shape `parse_player_effect` reads off
    # the ability's own printed text, so `trigger_effect_for`'s fallback
    # covers all of them - and a card added to the pool later for free. A
    # per-card entry re-added for any of them would silently shadow that
    # fallback; see `test_no_card_has_a_registry_entry_that_would_shadow_the_player_effect_parser`.
    # Dragon's Rage Channeler's *delirium* static ability - +2/+2, flying, and
    # attacks each combat if able - is a layer 6 and 7c continuous effect and
    # belongs in LAYER_EFFECTS, not here.
}

#: What an activated ability does, by `(card name, index among that card's
#: activated abilities)`.
ACTIVATED_EFFECTS: dict[tuple[str, int], AbilityEffect] = {
    # Vampiric Rites' "You gain 1 life and draw a card." is not entered here
    # any more - two clauses `parse_player_effect` reads directly, in the
    # order printed (CR 608.2c).
    # Basking Rootwalla's "{1}{G}: This creature gets +2/+2 until end of
    # turn." (index 0) and Karn, the Great Creator's "+1: Until your next
    # turn, up to one target noncreature artifact becomes an artifact
    # creature with power and toughness each equal to its mana value." (index
    # 0 - his static ability line has no cost, so +1 is the first ability
    # that does) are not entered here any more either: both rows existed only
    # to route the ability to `create_continuous_effect_of_ability`, the
    # generic resolution effect that reads the card's own oracle text through
    # `machines/layers.py`'s `parsed_layer_effects` - the actual pump, type
    # change, and mana-value P/T were never this table's business. Routing is
    # text-driven now: `_is_layer_effect_text` in `_ability_effect_or_notice`
    # recognises the ability's own effect text as one of `parsed_layer_
    # effects`'s shapes and reaches the same function with no row, which also
    # lights up a triggered ability of the same shape that never had a row at
    # all - Oliphaunt's "another target creature you control gets +2/+0 and
    # gains trample until end of turn." attack trigger. See
    # `tests/scenarios/test_registry_is_minimal.py`.
    # The Zendikar/Khans fetchlands - Arid Mesa, Flooded Strand, Bloodstained
    # Mire, Marsh Flats, Scalding Tarn, Windswept Heath, Wooded Foothills,
    # Misty Rainforest, Verdant Catacombs - are deliberately **not** entered
    # here. Each is one activated ability, index 0, of the exact shape
    # `parse_search_and_put_effect` reads off the card's own printed text, so
    # `activated_effect_for`'s fallback covers all nine without a table row
    # each - and covers a fetchland added to the pool later for free. Adding a
    # per-card entry for one of them would silently shadow that fallback; see
    # `test_fetching_a_land.py::test_the_registry_does_not_shadow_the_parser`.
    # The horizon lands' second ability - "{1}, {T}, Sacrifice this land: Draw
    # a card." - is not entered here any more either: it is one clause of the
    # same parseable shape, so `activated_effect_for`'s fallback reaches it
    # (and Mind Stone's and Nurturing Peatland's identical ability, which
    # never had a row at all).
    # Goblin Bombardment's "Sacrifice a creature: This enchantment deals 1
    # damage to any target." is not entered here any more either: the effect
    # half, on its own, is the same single-clause shape
    # `parse_targeted_effect` reads off the ability's own printed text, so
    # `activated_effect_for`'s fallback reaches it.
    # Ghost Quarter's "{T}, Sacrifice this land: Destroy target land. Its
    # controller may search their library for a basic land card, put it onto
    # the battlefield, then shuffle." (index 1, behind "{T}: Add {C}") is not
    # entered here any more either (W3): the same two-clause shape as White
    # Orchid Phantom's trigger, read by `parse_mixed_effect` with no row. See
    # `tests/scenarios/test_registry_is_minimal.py`.
}


def trigger_effect_for(
    card_name: str,
    event: TriggerEvent | None,
    effect_text: str | None = None,
    *,
    x_value: int | None = None,
    legendary: bool = True,
) -> AbilityEffect | None:
    """The effect of a card's trigger on `event`, or None if it is not scripted.

    `event` is `None` for a trigger the condition parser could not reduce to a
    `TriggerEvent` at all - CR 603.8's state triggers among them ("Some
    triggered abilities trigger when a game state ... is true, rather than
    triggering when an event occurs"), which `machines/triggers.
    state_triggers_for` recognises by their condition rather than by an event.
    No `TRIGGER_EFFECTS` key can be written for such an ability, so the
    lookup below finds nothing and the whole question falls to the
    text-driven fallback - which is where The Millennium Calendar's own
    "sacrifice it and each opponent loses 1,000 life" is read.

    A double-faced card is keyed by the face the ability is printed on, so
    Delver of Secrets is found under `"Delver of Secrets"` and not under the full
    `"Delver of Secrets // Insectile Aberration"`.

    **A card may have more than one trigger on one event**, and this is called
    with the card and the event and nothing else, because `Game._effect_of` has
    only those to hand. So when a card has several entries for an event, what
    comes back is a dispatcher: it reads the resolving ability's own printed text
    and runs the entry whose marker that text carries. A trigger matching no
    marker does nothing, which is the same silence a card with no entry gets.

    A card with **no** entry for the event falls back to `parse_mixed_effect`
    on `effect_text` - the per-clause dispatcher that reads a search, a
    targeted clause, or a plain player clause in any order or mix (W3 folded
    search into it; before that this fell back through
    `parse_search_and_put_effect`, then `parse_targeted_effect`, then
    `parse_player_effect` in turn, which could not read a card whose clauses
    mixed those shapes - Ghost Quarter's destroy-then-search among them).
    Flagstones of Trokair's death trigger is written this way rather than as a
    table row, but does not fire yet in a real game - its condition never
    reaches this function at all, because `_trigger_event` does not recognise
    it (see `docs/engine-coverage.md`).

    `x_value` is CR 107.3a's X, carried onto the permanent this trigger fires
    off of by `Game.cast_record` (CR 400.7d's "an ability of a permanent can
    reference information about the spell that became that permanent") -
    Fblthp, Knows the Way's own "search your library for up to X basic land
    cards" is unreadable with a literal "X" left in it, the identical gap
    `activated_effect_for`'s own `x_value` already closes for an activated
    ability's announced X. Substituted text is tried first, the same order
    and for the same reason `activated_effect_for` tries it first: an
    unsubstituted parse that happens to accept a bare "X" (CR 107.3f's own
    self-defined kind) would otherwise win with no real value behind it.
    """
    front = card_name.split("//")[0].strip()
    entries = [
        (marker, effect)
        for (name, keyed_event, marker), effect in TRIGGER_EFFECTS.items()
        if keyed_event is event and name in (card_name, front)
    ]
    if not entries:
        if effect_text is None:
            return None
        if x_value is not None:
            substituted = _ability_effect_or_notice(substitute_x(effect_text, x_value))
            if substituted is not None:
                return substituted
        raw = _ability_effect_or_notice(effect_text)
        if raw is create_continuous_effect_of_ability:
            # The generic layer fallback reads the sentence's *shape* only and
            # fails closed at resolution on anything it cannot size - War
            # Machine, Legacy of Iron's "where X is War Machine's power" is
            # readable once CR 201.5's own name is "this permanent", so the
            # normalized text gets its say before the fallback wins.
            normalized_first = _ability_effect_or_notice(
                _self_normalized_effect_text(card_name, effect_text, legendary=legendary)
            )
            if normalized_first is not None:
                raw = normalized_first
        if raw is not None:
            # The literal printed name is what some parsers are *reading
            # for* - `_parse_may_exile_self_then_return_clause`'s own CR
            # 201.5 guard on Ajani, Nacatl Pariah's "you may exile Ajani,
            # then return him ..." checks that the captured name is a
            # substring of the actual source's name, and would refuse a
            # normalized "this permanent" outright. Tried unnormalized
            # first, always, so a shape already reading the literal name
            # keeps doing so; only a miss falls through to the normalized
            # attempt below.
            return raw
        # Ruby, Daring Tracker's own "Ruby gets +2/+2 until end of turn." -
        # CR 201.5 self-reference by literal printed name (Grist and The
        # Filigree Sylex's shape, `_self_normalized_effect_text`'s own
        # docstring), on a *triggered* ability rather than the activated one
        # that function was first written for. `activated_effect_for`
        # already normalizes before parsing; a triggered ability's text
        # reached `_ability_effect_or_notice` unnormalized until now, so a
        # pump clause spelled with the card's own name instead of CR 700.7's
        # "this creature" fell through every clause parser and resolved
        # silently.
        normalized = _self_normalized_effect_text(card_name, effect_text, legendary=legendary)
        named = _ability_effect_or_notice(normalized)
        if named is not None or not legendary:
            return named
        # Hydro-Man, Fluid Felon's own "he gets +1/+1 until end of turn." - a
        # legend's gendered pronoun as the sentence's subject is the card
        # itself (`legendary_self_pronoun_normalized`).
        pronoun = legendary_self_pronoun_normalized(normalized)
        if pronoun == normalized:
            return None
        return _ability_effect_or_notice(pronoun)
    if len(entries) == 1 and not entries[0][0]:
        return entries[0][1]
    return _dispatch_by_printed_text(entries)


def _dispatch_by_printed_text(
    entries: list[tuple[str, AbilityEffect]],
) -> AbilityEffect:
    """Pick between several triggers of one card on one event, by their text.

    The most specific marker wins, so a longer fragment is tried before a shorter
    one, and an empty marker is the catch-all a card uses when one entry really
    does cover every trigger it has on that event.
    """
    ordered = sorted(entries, key=lambda entry: -len(entry[0]))

    def dispatch(game: "Game", ability: AbilityOnStack) -> None:
        printed = (getattr(ability.ability, "text", "") or "").lower()
        for marker, effect in ordered:
            if not marker or marker in printed:
                effect(game, ability)
                return

    return dispatch


def activation_resolution_text(effect_text: str) -> str:
    """An activated ability's effect text less the trailing sentences read at
    activation rather than at resolution: a timing restriction (CR 602.5d)
    and a target-gated cost reduction (CR 601.2f via CR 602.2b, applied by
    `Game._activation_target_cost_reduction`). What is left is what the
    resolution readers are handed - and what the support oracle's ablation
    probe removes sentences from."""
    effect_text = _TRAILING_ACTIVATION_TIMING_RESTRICTION_RE.sub("", effect_text).strip()
    effect_text = strip_x_restrictions(effect_text).strip()
    return _TRAILING_ACTIVATION_TARGET_COST_REDUCTION_RE.sub("", effect_text).strip()


def activated_effect_for(
    card_name: str,
    index: int,
    effect_text: str | None = None,
    *,
    x_value: int | None = None,
    legendary: bool = True,
) -> AbilityEffect | None:
    """The effect of a card's activated ability at `index`, or a parsed one.

    A card with no `ACTIVATED_EFFECTS` row falls back to `parse_mixed_effect`
    on `effect_text` - every fetchland and Expedition Map reach the model
    through its search-clause path, Icy Manipulator and Kiora's Follower
    through its targeted-clause path, Vexing Bauble's "Draw a card" and the
    horizon lands' own sacrifice ability through its player-clause path, and
    Ghost Quarter's "Destroy target land. Its controller may search ..."
    through a targeted clause and a search clause together, with no row of
    its own.

    `x_value` is CR 107.3a's X as `Game.activate_ability` recorded it on the
    `AbilityOnStack`, mirroring `effect_for`'s own handling for a spell:
    `None` for an ability whose printed cost carries no `{X}` at all, which
    leaves a bare "X" written into the effect's own rules text (CR 107.3f, not
    this one) untouched. Fiend Artisan's "Search your library for a creature
    card with mana value X or less" is unreadable by `_SEARCH_AND_PUT_RE`
    until X is substituted for a real number.

    The substituted text is tried **first** whenever an X was announced.
    CR 107.3a: "While an activated ability is on the stack, any X in its
    activation cost equals the announced value", and a cost whose X the player
    chose never has an X its own text defines (CR 107.3c is the other case), so
    the number is the only reading. Trying the bare text first let a parser
    that accepts a literal "X" win with no value behind it: Martyr of Spores's
    "Target creature gets +X/+X until end of turn" became a +0/+0 pump. The
    unsubstituted text stays the fallback for a shape only it matches.
    """
    front = card_name.split("//")[0].strip()
    explicit = ACTIVATED_EFFECTS.get((card_name, index)) or ACTIVATED_EFFECTS.get((front, index))
    if explicit is not None:
        return explicit
    if effect_text is None:
        return None
    effect_text = activation_resolution_text(effect_text)
    effect_text = _self_normalized_effect_text(card_name, effect_text, legendary=legendary)
    if x_value is not None:
        substituted = _ability_effect_or_notice(substitute_x(effect_text, x_value))
        if substituted is not None:
            return substituted
    named = _ability_effect_or_notice(effect_text)
    if named is not None and not getattr(named, "__name__", "").endswith("notice_only"):
        return named
    if not legendary:
        return named
    # Abomination, Terrifying Titan's power-up rider: "Put a +1/+1 counter
    # on Abomination. He fights up to one target creature an opponent
    # controls." - name substitution above turns "Abomination" into "this
    # permanent" in the first sentence, but the second sentence's own
    # CR 201.5c self-reference is the gendered pronoun "He", which name
    # substitution does not touch. `trigger_effect_for`'s own fallback tries
    # this for a triggered ability's text; an activated ability's power-up
    # rider is the identical shape and had no equivalent fallback until now.
    #
    # `named` is checked for a `..._notice_only` stand-in, not merely for
    # `None`, and the pronoun attempt is tried whenever it is one: the first
    # sentence's own self-name substitution ("this permanent") can leave the
    # *second* sentence's unresolved "He" looking anaphoric rather than
    # unreadable outright, so a bare `named is not None` check would return
    # the wrong notice before the pronoun rewrite ever ran.
    pronoun = legendary_self_pronoun_normalized(effect_text)
    if pronoun == effect_text:
        return named
    pronoun_effect = _ability_effect_or_notice(pronoun)
    return pronoun_effect if pronoun_effect is not None else named


from ._common import _self_normalized_effect_text  # noqa: E402
from .continuous import continuous_effects  # noqa: E402
from .dispatch import _ability_effect_or_notice, _spell_effect_or_notice  # noqa: E402
from .modal import resolve_modal_spell  # noqa: E402
from .removal import _then_exile_self  # noqa: E402
from .text import (  # noqa: E402
    _strip_leading_standalone_cast_trigger,
    _strip_self_exile_sentence,
    _strip_self_exile_with_time_counters_sentence,
    _strip_self_is_all_colors_sentence,
    _strip_self_shuffle_clause,
    _strip_trailing_flashback_line,
    _strip_trailing_standalone_activated_ability,
    _strip_trailing_standalone_triggered_ability,
)
from .tokens import _is_notice_only, create_continuous_effect_of_ability  # noqa: E402
