import hashlib
import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import canonical_subtype, creature_type_vocabulary, subtype_vocabulary
from ...models.card import Color, Supertype, Type
from ...models.card_state import (
    CardState,
    Choice,
    ChoiceKind,
)
from ...models.mana import ManaCost
from ...models.player import Player
from ...models.token import (
    PREDEFINED,
    TokenDefinition,
    create_tokens,
    token_copy_of,
)
from ...models.zone import Zone
from ...numbers import (
    AMOUNT,
    COUNT,
    ORDINAL,
    Quantity,
    QuantitySource,
    count_pattern,
    halve,
    parse_count,
    parse_ordinal,
)
from ..abilities import (
    TriggerEvent,
    keyword_abilities,
)
from ..chosen_type import (
    ask_creature_type,
)
from ..combat import has_keyword
from ..counter_effects import parse_resolution_text as _parse_counter_resolution_text
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    CreatedTriggeredAbility,
    DelayedTrigger,
    DrawACardForController,
    ReflexiveConsequence,
    ReflexiveCounterCountConsequence,
    ReflexiveMandatoryTokenDamageConsequence,
    ReflexivePayEnergyConsequence,
    ReflexivePayManaConsequence,
    ReflexiveWhenYouDoConsequence,
    ReturnThatCardToBattlefieldUnderOwner,
    ThatCreatureDiesConsequence,
    draw_a_card_for_controller,
    return_subject_to_hand,
    sacrificed_by_its_controller,
)
from ..land_animation import (
    choose_and_animate_mode,
)
from ..layers import (
    ContinuousEffect,
    Duration,
    Layer,
    Sublayer,
    _only,
    grant_ability,
    is_genuine_resolution_layer_sentence,
    modify_power_toughness,
    parsed_layer_effects,
)
from ..modes import (
    ModalProfile,
    Mode,
    instruction_rider,
    is_modal_text,
    modal_profile,
    modal_profile_from_text,
    mode_effect_text,
    substitute_x,
)
from ..targeting import (
    RetargetScope,
    permanent_description,
)
from ..triggers import (
    AbilityOnStack,
    GameEvent,
    is_ability,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES, SPELL_TEXT
from ._common import AbilityEffect, ClauseEffect, Effect, TargetedClause, _SacrificeRestriction


def reflexive_consequence_effect(text: str) -> AbilityEffect | None:
    """A reflexive ability's (CR 603.12) consequence as an effect: an
    ordinary clause sequence (`parse_mixed_effect`), or a one-shot
    continuous effect (CR 611.2) such as "up to 2 target creatures gain
    double strike until end of turn" (`create_continuous_effect_of_ability`,
    which reads the ability's own text). `None` when neither reads it."""
    parsed = parse_mixed_effect(text)
    if parsed is not None:
        return parsed
    sentence = _as_sentence(text)
    if _is_layer_effect_text(sentence) and parsed_layer_effects(sentence) is not None:
        # CR 608.2c: a layer sentence with other instructions beside it (Primal
        # Adversary's "put N +1/+1 counters on this creature. Up to N target
        # lands ... become ...") runs them all, in order, not the layer alone.
        return (
            _compose_layer_effect_with_remainder_for_ability(sentence)
            or create_continuous_effect_of_ability
        )
    # A whole-ability sentence whose "it" is the ability's own source ("When you
    # do, prevent all combat damage that would be dealt to it this turn." -
    # Oketra's Avenger, CR 701.43d's linked trigger).
    flat = " ".join(text.split())
    # "target creature gets +X/+X until end of turn, where X is ..." (Hydra
    # Trainer): X is defined in the sentence and fixed as the ability resolves.
    return ABILITY_TEXT.run("s19", flat) or _parse_where_x_is_continuous_effect(flat)


def _choose_a_color(
    game: "Game",
    player: Player,
    source_name: str,
    prompt: str,
    *,
    source_id: str | None,
    colors: "Sequence[Color] | None" = None,
) -> Color:
    """CR 608.2d's "of your choice", asked with `DecisionKind.CHOOSE_A_
    QUALITY` narrowed to CR 105's five colours - the same kind and the same
    narrowing `_parse_destroy_each_then_add_mana_per_destroyed` already uses
    for Culling Ritual's own per-unit colour choice. `colors` narrows it
    further to a printed palette ("any combination of {R} and/or {G}").
    """
    decision = Decision(
        kind=DecisionKind.CHOOSE_A_QUALITY,
        player=player.username,
        prompt=prompt,
        source=source_name,
        options=_COLOR_LETTERS if colors is None else tuple(color.value for color in colors),
        source_id=source_id,
    )
    value = game.ask(decision)
    assert isinstance(value, str)
    return Color(value)


#: CR 702.174f: "'Gift a tapped Fish' means the effect is 'The chosen player
#: creates a tapped 1/1 blue Fish creature token.'" - Into the Flood Maw.
FISH = TokenDefinition(subtypes=("Fish",), colors=(Color.BLUE,), power=1, toughness=1)

#: CR 702.174i: "'Gift an Octopus' means the effect is 'The chosen player
#: creates an 8/8 blue Octopus creature token.'"
OCTOPUS = TokenDefinition(subtypes=("Octopus",), colors=(Color.BLUE,), power=8, toughness=8)

#: CR 702.174d-i: the six "Gift a [something]" effects, keyed by the
#: keyword's own printed parameter ("Gift a tapped Fish" -> "a tapped
#: Fish"). Every shape the rule states, not only Into the Flood Maw's own -
#: a future gift card whose parameter is one of the other five reads
#: through the same table with no new code.
_GIFT_EFFECTS: dict[str, Callable[["Game", str], None]] = {
    "a food": lambda game, chosen: create_tokens(game, PREDEFINED["Food"], chosen),
    "a card": lambda game, chosen: game.draw_cards(chosen, 1),
    "a tapped fish": lambda game, chosen: create_tokens(game, FISH, chosen, tapped=True),
    "an extra turn": lambda game, chosen: game.grant_extra_turn(chosen),
    "a treasure": lambda game, chosen: create_tokens(game, PREDEFINED["Treasure"], chosen),
    "an octopus": lambda game, chosen: create_tokens(game, OCTOPUS, chosen),
}


def gift_effect_for(parameter: str | None) -> Callable[["Game", str], None] | None:
    """CR 702.174d-i's effect for a gift keyword's own printed "[something]",
    or `None` for a shape this wave does not read (fails closed rather than
    guessing - CR 702.174 lists no others as of this writing).
    """
    if parameter is None:
        return None
    return _GIFT_EFFECTS.get(parameter.strip().lower())


def apply_gift_if_promised(game: "Game", spell: CardState) -> None:
    """CR 702.174j: "For instant and sorcery spells, the effect of a gift
    ability always happens before any other spell abilities of the card."

    Called from `Game.resolve_top` immediately before the spell's own
    `effect` runs, and only for an instant or sorcery - CR 702.174b's other
    half, a *permanent's* "when this permanent enters, if its gift cost was
    paid" trigger, is not modelled; see `docs/engine-coverage.md`.
    """
    if spell.is_permanent:
        return
    ability = next(
        (a for a in keyword_abilities(spell.card) if a.canonical.lower() == "gift"), None
    )
    if ability is None:
        return
    record = game.cast_record(spell)
    if not record.gift_promised or record.gift_chosen_player is None:
        return
    effect = gift_effect_for(ability.parameter)
    if effect is not None:
        effect(game, record.gift_chosen_player)


def end_the_turn_if_your_turn_effect(game: "Game", stack_object: "StackObject") -> None:
    """Day's Undoing: "If it's your turn, end the turn." - CR 724.1's
    procedure, gated on CR 102.1's active player being this resolving spell's
    own controller.

    Not CR 608.2a's intervening *if* - that rule is for a *triggered*
    ability's own trigger condition, rechecked as it resolves. This is a
    plain CR 608.2c instruction carrying a condition, read and acted on once,
    the same as any other "if <condition>, <instruction>" clause.

    "Your turn" is the resolving object's own controller's turn, not the
    caster's at some earlier moment: a spell or ability has exactly one
    controller for its whole time on the stack, so there is no second
    reading to weigh against `game.controller_of`'s answer.
    """
    if game.controller_of(stack_object).username != game.active_player.username:
        return
    game.end_the_turn()


#: "You may behold a `<quality>`. If you do, `<consequence>`." - CR 701.4a's
#: keyword action as a plain, standalone resolution-time optional action
#: (CR 608.2d), general rather than pinned to Sarkhan, Dragon Ascendant's own
#: "When Sarkhan enters, you may behold a Dragon. If you do, create a
#: Treasure token." Distinct from `_SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_
#: BEHOLD_UNTAP_RE` above, which reads the identical CR 701.4a action bundled
#: with a search this shape has none of.
#:
#: No off-pool proof: Scryfall's `o:"behold" o:"if you do"` returns only
#: Sarkhan, Theorist's Sanctum ("if you don't" - the opposite polarity), and
#: Elven Passage, whose own "if you do" is consumed whole by that bundled
#: search-first reader above, never reaching this one. See MEMORY.md's dated
#: line.
_OPTIONAL_BEHOLD_THEN_IF_YOU_DO_RE = re.compile(
    r"^you may behold an? (?P<quality>[a-z' -]+?)\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s1")
def _parse_optional_behold_then_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_OPTIONAL_BEHOLD_THEN_IF_YOU_DO_RE`'s shape, or `None`.

    The same single `CHOOSE_CARDS` question `_parse_search_put_battlefield_
    tapped_then_behold_untap_clause` already folds CR 701.4a's own "or" and
    CR 608.2d's "you may" into: every card in either pool - a matching hand
    card or a matching battlefield permanent - is one candidate list,
    `amount=1, exact=False` so declining is a legal answer, offered only
    when non-empty. "If you do" (CR 608.2d) runs the consequence only when a
    card was actually beheld.
    """
    match = _OPTIONAL_BEHOLD_THEN_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    quality = match.group("quality").strip()
    behold_matches = _quality_matcher(quality)
    consequence_text = match.group("consequence").strip()
    if not consequence_text.endswith("."):
        consequence_text += "."
    # `_ability_effect_or_notice`, not `parse_clause_effect`: the consequence
    # is a whole ability effect in its own right (Sarkhan's own "create a
    # Treasure token" reaches `_token_creation_clause` only through that
    # wider dispatcher, which every other whole-ability reader in this file
    # already calls back into for its own "if you do"/"then" tail).
    consequence = _ability_effect_or_notice(consequence_text)
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        source = ability.source_name
        source_id = source_id_of(ability)
        hand_candidates = [state for state in controller.hand if behold_matches(state)]
        battlefield_candidates = [
            state
            for state in game.permanents_controlled_by(controller.username)
            if behold_matches(state)
        ]
        candidates = hand_candidates + battlefield_candidates
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"behold {with_indefinite_article(quality)}",
                source=source,
                source_id=source_id,
                amount=1,
                exact=False,
                cards=tuple(state.id for state in candidates),
            )
        )
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id.get(chosen_ids[0])
        if chosen is None:
            return
        if chosen.zone is Zone.HAND:
            game.reveal(chosen, source=source)
        consequence(game, ability)

    return effect


#: Bloodline Bidding's own convoke spell body: "Choose a creature type.
#: Return all creature cards of the chosen type from your graveyard to the
#: battlefield." CR 608.2c's own two-instruction order: the choice, then a
#: plain "return all `<quality>` cards ... to the battlefield" (CR 401.2, no
#: reveal or shuffle involved) judged against whichever type CR 607.2d's
#: choice just answered.
_CHOOSE_TYPE_RETURN_FROM_GRAVEYARD_RE = re.compile(
    r"^choose a creature type\. return all creature cards of the chosen type from your "
    r"graveyard to the battlefield\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s17", for_spell=True)
def _parse_choose_type_return_from_graveyard_clause(text: str, *, for_spell: bool) -> Effect | None:
    """`_CHOOSE_TYPE_RETURN_FROM_GRAVEYARD_RE`'s shape, or `None`."""
    if not for_spell:
        return None
    whole = _strip_non_effect_preamble(text).strip()
    if _CHOOSE_TYPE_RETURN_FROM_GRAVEYARD_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        chosen = ask_creature_type(
            game, controller.username, spell.name, source_id_of(spell)
        ).lower()
        matches = [
            state
            for state in list(controller.graveyard)
            if Type.CREATURE in state.types and chosen in {s.lower() for s in state.subtypes}
        ]
        if matches:
            with game.entering_together():  # CR 603.6a: one arrival, together
                for state in matches:
                    game.put_onto_battlefield(state, controller.username)

    return effect


#: Harmonized Crescendo's own convoke spell body: "Choose a creature type.
#: Draw a card for each permanent you control of that type." A plain
#: CR 121.1 draw, counted off the live board (CR 613.5) rather than off the
#: graveyard `_CHOOSE_TYPE_RETURN_FROM_GRAVEYARD_RE` reads.
_CHOOSE_TYPE_DRAW_PER_PERMANENT_RE = re.compile(
    r"^choose a creature type\. draw a card for each permanent you control of that "
    r"type\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s17", for_spell=True)
def _parse_choose_type_draw_per_permanent_clause(text: str, *, for_spell: bool) -> Effect | None:
    """`_CHOOSE_TYPE_DRAW_PER_PERMANENT_RE`'s shape, or `None`."""
    if not for_spell:
        return None
    whole = _strip_non_effect_preamble(text).strip()
    if _CHOOSE_TYPE_DRAW_PER_PERMANENT_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        chosen = ask_creature_type(
            game, controller.username, spell.name, source_id_of(spell)
        ).lower()
        count = sum(
            1
            for state in game.permanents_controlled_by(controller.username)
            if chosen in {s.lower() for s in game.characteristics_of(state).subtypes}
        )
        if count:
            game.draw_cards(controller, count)

    return effect


def _choose_lands_from_hand(
    game: "Game", player: Player, source: str, *, quantity: Quantity, source_id: str | None
) -> list[CardState]:
    """CR 601.2d-shaped choice among a player's own land cards already known
    to be in hand ("a land card from your hand" is a choice of *which*
    land(s), not merely whether to act). Callers check `_land_cards_in_hand`
    first, so the "you may" this is nested under is never asked with nothing
    to choose.

    `quantity.amount` bounds how many - `None` (CR 107.1c's "any number of")
    reads as every land in hand - and `quantity.exact` (`False` for "any
    number of") is CR 701.23b's own "need not find everything" shape read
    onto a hand choice instead of a search: `Decision.exact=False` is what
    lets the answer be a legal subset the same way `search_library` already
    asks it. A hand with nothing to choose from is never asked at all, the
    same "no legal option, no question" rule the singular case always had.
    """
    lands = _land_cards_in_hand(player)
    limit = len(lands) if quantity.amount is None else min(quantity.amount, len(lands))
    if limit == 0:
        return []
    decision = Decision(
        kind=DecisionKind.CHOOSE_CARDS,
        player=player.username,
        prompt=f"choose {'a' if limit == 1 else limit} land card(s) to put onto the battlefield",
        source=source,
        amount=limit,
        cards=tuple(state.id for state in lands),
        exact=quantity.exact,
        default_cards=tuple(state.id for state in lands[:limit]),
        source_id=source_id,
    )
    chosen_ids = game.ask(decision)
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in lands}
    return [by_id[card_id] for card_id in chosen_ids]


_EXACTLY_ONE_LAND = Quantity(amount=1, minimum=1, source=QuantitySource.FIXED)


def _choose_land_from_hand(
    game: "Game", player: Player, source: str, *, source_id: str | None
) -> CardState:
    """The always-singular case - Cultivator Colossus's own repeating "put a
    land card" and Spelunking's "you may put a land card" both ever ask for
    exactly one, never a printed quantity - as a thin, one-card wrapper around
    `_choose_lands_from_hand`. Callers check `_land_cards_in_hand` first, the
    same precondition `_choose_lands_from_hand` itself relies on, so the
    single choice it returns is never empty.
    """
    (chosen,) = _choose_lands_from_hand(
        game, player, source, quantity=_EXACTLY_ONE_LAND, source_id=source_id
    )
    return chosen


def _optional_clause(
    inner: ClauseEffect, prompt: str, *, default: bool | None = None
) -> ClauseEffect:
    """Wrap an already-parsed clause so it only runs if `Game.may` says yes.

    CR 608.2d: "if a cost or effect allows a player to choose to do something
    ... that player is not required to make that choice unless the effect
    specifically says the player must." `Game.may`'s own default is to take
    the option, which is the engine-wide convention this reuses rather than
    reargues - `default` is `None` for every clause but one, so this keeps
    that convention unless a caller documents why theirs is the exception
    (see `_parse_optional_player_clause`'s "you may shuffle" case).
    """

    def effect(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        if game.may(player, prompt, source=source, source_id=source_id, default=default):
            inner(game, player, source, source_id)

    return effect


def _parse_you_may_clause(clause: str) -> tuple[str, ClauseEffect, bool | None] | None:
    """`clause`'s `"you may "` prefix peeled off, as its own three parts: the
    printed prompt text, the *unwrapped* inner effect, and the `Game.may`
    default that belongs with it - `_parse_optional_player_clause` wraps
    these three into one asked-and-run `ClauseEffect` for every ordinary
    caller; `_merge_may_then_if_you_do_clauses` asks the same question
    itself instead, so CR 118.12's "if you do" can gate its own consequence
    on the very choice this question returns rather than re-asking it.

    `None` for anything not shaped "you may `<clause>`", or whose inner
    clause `parse_clause_effect` cannot read - fail-closed stays in force
    either way.
    """
    match = _YOU_MAY_RE.match(clause)
    if match is None:
        return None
    inner_text = match.group("clause").strip()
    # "You may gain 1 life" drops the "you" the way "you may draw a
    # card" drops "you" before "draw" - `_DRAW_RE` reads past an absent
    # "you" with `(?:you )?`, but `_GAIN_LIFE_RE`/`_LOSE_LIFE_RE` require
    # it, so a clause that fails without it is retried with it restored
    # before being given up on.
    inner = parse_clause_effect(inner_text) or parse_clause_effect(f"you {inner_text}")
    if inner is None:
        return None
    # "You may shuffle." is the one optional clause this parser reads
    # whose unscripted answer is not "take it": shuffling ends whatever
    # look or order the clauses above it just fixed (CR 701.20d), so the
    # engine-wide "take it" convention would silently undo a rigged
    # library on every unscripted Ponder-shaped cast. Declining is the
    # same "leave the order alone" posture `SCRY`/`SURVEIL`'s own
    # defaults already take - see `Decision.default_may`.
    default = False if _SHUFFLE_RE.fullmatch(inner_text.rstrip(".")) else None
    return inner_text, inner, default


def _parse_optional_player_clause(clause: str) -> ClauseEffect | None:
    """`clause`, or its `"you may "` prefix peeled off and wrapped optional.

    Wrapping only ever happens over a clause `parse_clause_effect` already
    understands - fail-closed stays in force: "you may <something this wave
    cannot read>" comes back `None` here exactly as it would un-wrapped, so
    the caller throws away the whole effect instead of asking a question it
    could not carry out.
    """
    if _PAY_ANY_AMOUNT_OF_LIFE_RE.fullmatch(clause.strip().rstrip(".")):
        return parse_clause_effect(clause)
    if _ADDITIONAL_LAND_PLAY_RE.fullmatch(clause.strip().rstrip(".")):
        # The grant is unconditional (see `_ADDITIONAL_LAND_PLAY_RE`'s own
        # docstring): a "you may" here is never a CR 608.2d question this
        # engine has to ask, so this is read before the generic "you may"
        # strip below would otherwise wrap it in one.
        return parse_clause_effect(clause)
    you_may = _parse_you_may_clause(clause)
    if you_may is not None:
        inner_text, inner, default = you_may
        return _optional_clause(inner, inner_text, default=default)
    # "You draw a card and gain 2 life." (Surgical Precision, Vigorbloom
    # Charm) - `split_effect_clauses`'s own bare-"and" cut leaves the second
    # clause's subject implicit ("gain 2 life", not "you gain 2 life"), the
    # identical trap the "you may" branch above already retries around.
    return (
        parse_clause_effect(clause)
        or parse_clause_effect(f"you {clause}")
        or _parse_comma_chained_player_clause(clause)
    )


#: "Choose target `<X>`[ with `<filter>`]. Return the chosen card to the
#: battlefield." - Too Evil to Stay Dead's own shape: the target is fixed at
#: announcement (CR 601.2c) by a bare "Choose ..." sentence with no verb of
#: its own (`machines/targeting.profile_for_text` already reads "target
#: `<X>`" as an ordinary requirement whether or not a verb follows it in the
#: same sentence), and "the chosen card" (CR 400.7's anaphora back to what
#: was targeted) is a second, separate sentence naming the actual
#: instruction. `Teamwork`'s own "If this spell was cast using teamwork,
#: instead choose ..." rider (`machines/teamwork.teamwork_instead_target_
#: text`) changes only the announced target restriction, read entirely at
#: announcement - by the time this clause resolves there is nothing left to
#: branch on, so one reader covers both the teamwork and non-teamwork casts.
_CHOOSE_TARGET_RETURN_CHOSEN_CARD_RE = re.compile(
    r"^choose (?P<phrase>[^.]*\btarget\b[^.]*)\.\s*"
    # An optional CR 601.2c "instead choose ..." rider (Too Evil to Stay
    # Dead's own teamwork sentence, `machines/teamwork.teamwork_instead_
    # target_text`) sits between the base choice and the resolution
    # instruction - already spent entirely at announcement, so it is only
    # skipped over here, never re-read.
    r"(?:if [^.]+, instead choose [^.]*\btarget\b[^.]*\.\s*)?"
    r"return the chosen card to the battlefield\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s18")
def _parse_choose_target_return_chosen_card_clause(effect_text: str) -> Effect | None:
    """`_CHOOSE_TARGET_RETURN_CHOSEN_CARD_RE`'s shape - see the banner above.

    `return_ability_targets_to_battlefield` already reads whatever this
    spell still legally targets (CR 608.2b) straight off `game.
    resolve_targets`, so nothing here needs "the chosen card" resolved by
    hand - the anaphor and "target `<X>`" mean the identical object.
    """
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _CHOOSE_TARGET_RETURN_CHOSEN_CARD_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None
    return return_ability_targets_to_battlefield


# --------------------------------------------------------------------------
# "Choose target creature you control and target creature <you don't control |
# an opponent controls>. [<rider>.] <fight | bite>."
# --------------------------------------------------------------------------
#
# CR 701.14a (fight), CR 608.2b (a target that is illegal on resolution is not
# affected, so the survivor still gets the rider but nothing fights), CR 608.2c
# (printed order: the pump or counter lands before the damage), CR 207.2c
# (Coven and Delirium are ability words, stripped by the preamble reader).
# One reader for the whole template: the opening "Choose ..." sentence names
# both targets, an optional middle sentence is a conditional pump or counter
# rider on the creature you control, the last sentence is the fight or a bite.

_CHOOSE_PAIR_RE = re.compile(
    r"^choose target creature you control and target creature "
    r"(?:you don'?t control|an opponent controls)$",
    re.IGNORECASE,
)
_PAIR_FIGHT_RE = re.compile(
    r"^then (?:those|the chosen) creatures fight each other$", re.IGNORECASE
)
_PAIR_POWER_BITE_RE = re.compile(
    r"^the creature you control deals damage equal to its power to the creature "
    r"(?:you don'?t control|an opponent controls)$",
    re.IGNORECASE,
)
_PAIR_TOUGHNESS_BITE_RE = re.compile(
    r"^each of those creatures deals damage equal to its toughness to the other$",
    re.IGNORECASE,
)
_PAIR_PUMP = (
    r"the creature you control gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)"
    r"(?: and gains (?P<keywords>[a-z ,]+?))? until end of turn"
)
_PAIR_COUNTER = (
    r"put (?P<n>\w+) \+1/\+1 counters? on "
    r"(?:the (?:chosen )?creature you control|it)"
)
_PAIR_LEADING_IF_RIDER_RE = re.compile(
    rf"^if (?P<condition>.+?), (?:{_PAIR_PUMP}|{_PAIR_COUNTER})$", re.IGNORECASE
)
_PAIR_TRAILING_IF_RIDER_RE = re.compile(
    rf"^(?:{_PAIR_PUMP}|{_PAIR_COUNTER}) if (?P<condition>.+)$", re.IGNORECASE
)
#: The two rider conditions that talk about the creature you control, which
#: `Game.condition_holds` cannot know (an anaphor onto the first sentence's
#: own target, `_effect_condition_is_readable`): read here off that creature.
_PAIR_IT_IS_RE = re.compile(r"^it(?:'s| is) an? (?P<word>.+)$", re.IGNORECASE)
_PAIR_ENTERED_RE = re.compile(
    r"^the creature you control entered (?:the battlefield )?this turn$", re.IGNORECASE
)


def _pair_condition_is_readable(condition: str) -> bool:
    return (
        _PAIR_IT_IS_RE.fullmatch(condition) is not None
        or _PAIR_ENTERED_RE.fullmatch(condition) is not None
        or _effect_condition_is_readable(condition)
    )


def _pair_condition_holds(
    game: "Game", spell: CardState, mine: CardState, condition: str
) -> bool | None:
    """A rider's printed condition, evaluated as the spell resolves (CR 608.2c).
    `None` when the shared reader cannot answer it."""
    is_a = _PAIR_IT_IS_RE.fullmatch(condition)
    if is_a is not None:
        word = is_a.group("word").strip().lower()
        characteristics = game.characteristics_of(mine)
        return word in {s.lower() for s in characteristics.subtypes} or word in {
            t.value.lower() for t in characteristics.types
        }
    if _PAIR_ENTERED_RE.fullmatch(condition) is not None:
        return game._entered_this_turn(mine)
    return game.condition_holds(game.controller_of(spell).username, condition, spell)


@SPELL_TEXT.rung("s12")
def _parse_choose_pair_fight_or_bite_clause(effect_text: str) -> Effect | None:
    """`_CHOOSE_PAIR_RE`'s opening sentence, an optional conditional pump or
    +1/+1-counter rider on the creature you control, then a fight or a bite -
    see the banner above."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    sentences = [part.strip().rstrip(".").strip() for part in re.split(r"(?<=\.)\s+", whole)]
    sentences = [part for part in sentences if part]
    if len(sentences) not in (2, 3) or _CHOOSE_PAIR_RE.fullmatch(sentences[0]) is None:
        return None
    finish = sentences[-1]
    if _PAIR_FIGHT_RE.fullmatch(finish):
        finish_kind = "fight"
    elif _PAIR_POWER_BITE_RE.fullmatch(finish):
        finish_kind = "power"
    elif _PAIR_TOUGHNESS_BITE_RE.fullmatch(finish):
        finish_kind = "toughness"
    else:
        return None
    if not _targets_understood("target creature you control", count_agnostic=True):
        return None
    rider = None
    if len(sentences) == 3:
        rider = _PAIR_LEADING_IF_RIDER_RE.fullmatch(sentences[1]) or (
            _PAIR_TRAILING_IF_RIDER_RE.fullmatch(sentences[1])
        )
        if rider is None or not _pair_condition_is_readable(rider.group("condition").strip()):
            return None
    builder = None
    counter_amount = 0
    if rider is not None:
        if rider.group("power") is not None:
            keywords = rider.group("keywords")
            builder = parsed_layer_effects(
                f"Target creature gets {rider.group('power')}/{rider.group('toughness')}"
                f"{f' and gains {keywords}' if keywords else ''} until end of turn."
            )
            if builder is None:
                return None
        else:
            parsed_amount = parse_count(rider.group("n"))
            if parsed_amount is None:
                return None
            counter_amount = parsed_amount
    condition = rider.group("condition").strip() if rider is not None else None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        targets = [
            target
            for target in game.resolve_targets(spell)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller.username]
        theirs = [t for t in targets if game.controller_of(t).username != controller.username]
        if mine and condition is not None:
            held = _pair_condition_holds(game, spell, mine[0], condition)
            if held is None:
                notice = ConditionalClauseNotice(
                    source_id=spell.id, source_name=spell.card.name, text=effect_text
                )
                if notice not in game.conditional_clause_notices:
                    game.conditional_clause_notices.append(notice)
            elif held and builder is not None:
                effects = game.continuous_effects
                for built in builder(
                    spell, effects.tick(), mine[:1], layer_context_for(game, controller)
                ):
                    effects.add(built, game)
            elif held:
                game.add_counters(mine[0], _counter_kind("+1/+1"), counter_amount)
        if not mine or not theirs:
            return  # CR 608.2b: an illegal target neither deals nor is dealt damage.
        fighter, opponent = mine[0], theirs[0]
        if finish_kind == "power":
            _resolve_bite_damage(game, spell, "power")
        elif finish_kind == "fight":
            if game.characteristics_of(fighter).is_creature and (
                game.characteristics_of(opponent).is_creature
            ):
                _fight(game, fighter, opponent)  # CR 701.14b
        else:
            fighter_toughness = max(game.characteristics_of(fighter).toughness or 0, 0)
            opponent_toughness = max(game.characteristics_of(opponent).toughness or 0, 0)
            game.deal_damage(opponent, fighter_toughness, source=fighter)
            game.deal_damage(fighter, opponent_toughness, source=opponent)

    return effect


# --------------------------------------------------------------------------
# "Choose target creature <...>. When that creature dies this turn, <consequence>.
# [Target creature you control fights that creature.]"
# --------------------------------------------------------------------------
#
# CR 603.7a/603.7c/603.7b: the second sentence creates a delayed triggered
# ability about the one creature the first sentence chose, for the rest of the
# turn; CR 701.14a is the optional last sentence's fight, which happens after
# the watch exists (printed order, CR 608.2c), so a fight that kills the
# creature does trigger it. The creature's own death is read by
# `ThatCreatureDiesConsequence`/`dies_consequence_effect`, never re-derived here.

_CHOOSE_THEN_DIES_THIS_TURN_RE = re.compile(
    r"^choose (?P<phrase>(?:up to one )?target creature"
    r"(?: (?:you don'?t control|an opponent controls))?)\. "
    r"when that creature dies this turn, (?P<consequence>[^.]+)"
    r"(?:\. (?P<rest>target creature you control fights that creature))?$",
    re.IGNORECASE,
)


def _dies_this_turn_consequence_text(consequence: str) -> str | None:
    """The consequence in the form `dies_consequence_effect` reads: as printed,
    or - "you earthbend 4" - with the controller's own "you" dropped from a bare
    imperative, since the delayed ability's controller is already the subject."""
    from ..dies_this_turn import dies_consequence_effect

    if dies_consequence_effect(consequence) is not None:
        return consequence
    if consequence.lower().startswith("you "):
        stripped = consequence[4:].strip()
        if dies_consequence_effect(stripped) is not None:
            return stripped
    return None


@SPELL_TEXT.rung("s12")
def _parse_choose_target_then_dies_this_turn_clause(effect_text: str) -> Effect | None:
    """`_CHOOSE_THEN_DIES_THIS_TURN_RE`'s shape - see the banner above."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split()).rstrip(".")
    match = _CHOOSE_THEN_DIES_THIS_TURN_RE.fullmatch(whole)
    if match is None:
        return None
    phrase = match.group("phrase")
    fights = match.group("rest") is not None
    chosen_is_opposing = re.search(
        r"you don'?t control|an opponent controls", phrase, re.IGNORECASE
    )
    if fights and not chosen_is_opposing:
        return None  # "that creature" could not be told apart from the fighter.
    consequence = _dies_this_turn_consequence_text(match.group("consequence").strip())
    if consequence is None:
        return None
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    if fights and not _targets_understood("target creature you control", count_agnostic=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        from ..dies_this_turn import source_id_of_object

        controller = game.controller_of(spell)
        targets = [
            target
            for target in game.resolve_targets(spell)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if fights:
            mine = [t for t in targets if game.controller_of(t).username == controller.username]
            chosen = [t for t in targets if game.controller_of(t).username != controller.username]
        else:
            mine, chosen = [], targets
        if not chosen:
            return  # CR 608.2b: the chosen creature is gone, nothing to watch.
        game.create_delayed_trigger(
            DelayedTrigger(
                text=consequence,
                event=TriggerEvent.DIES,
                controller=controller.username,
                source_id=source_id_of_object(spell),
                source_name=spell.card.name,
                subject_id=chosen[0].id,
                remaining=1,
                expires_end_of_turn=True,
                effect=ThatCreatureDiesConsequence(),
            )
        )
        if fights and mine:
            fighter, opponent = mine[0], chosen[0]
            if game.characteristics_of(fighter).is_creature and (
                game.characteristics_of(opponent).is_creature
            ):
                _fight(game, fighter, opponent)  # CR 701.14b

    return effect


# --------------------------------------------------------------------------
# "Choose another target creature or artifact. When it's put into a graveyard
# this turn, return that card to the battlefield under its owner's control."
# --------------------------------------------------------------------------
#
# Melira, the Living Cure. CR 603.7a/603.7b: the second sentence creates a
# delayed triggered ability about the one permanent the first chose, for the
# rest of the turn. It was on the battlefield when chosen, so (CR 400.7) the
# only way it is "put into a graveyard" is off the battlefield - the DIES
# event, which `ReturnThatCardToBattlefieldUnderOwner` answers.

_CHOOSE_THEN_PUT_INTO_GRAVEYARD_RETURN_RE = re.compile(
    r"^choose (?P<phrase>(?:another )?target (?:creature or artifact|creature|artifact|"
    r"permanent))\. when (?:it|that (?:creature|artifact|permanent))(?:'s| is) put into "
    r"a graveyard this turn, return that card to the battlefield under its owner'?s "
    r"control$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s35")
def _parse_choose_target_then_put_into_graveyard_return_clause(
    effect_text: str,
) -> AbilityEffect | None:
    """`_CHOOSE_THEN_PUT_INTO_GRAVEYARD_RETURN_RE`'s shape - see the banner."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split()).rstrip(".")
    match = _CHOOSE_THEN_PUT_INTO_GRAVEYARD_RETURN_RE.fullmatch(whole)
    if match is None or not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        chosen = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not chosen:
            return  # CR 608.2b: the chosen permanent is gone, nothing to watch.
        game.create_delayed_trigger(
            DelayedTrigger(
                text="When it's put into a graveyard this turn, return that card to the "
                "battlefield under its owner's control.",
                event=TriggerEvent.DIES,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=chosen[0].id,
                remaining=1,
                expires_end_of_turn=True,
                effect=ReturnThatCardToBattlefieldUnderOwner(),
            )
        )

    return effect


# --------------------------------------------------------------------------
# "Choose [up to one] target creature <...>. Each creature you control <filter>
# deals damage equal to its power to that creature."
# --------------------------------------------------------------------------
#
# A group bite: every qualifying creature you control, read off the computed
# board when the spell resolves (CR 613.5), is its own damage source dealing its
# own power (CR 120.3); the chosen creature is the one target (CR 115.1), and a
# chosen creature that is gone by resolution takes nothing (CR 608.2b).

_CHOOSE_THEN_GROUP_BITE_RE = re.compile(
    r"^(?:support (?P<support>[1-9]\d*)\. )?"
    r"choose (?P<phrase>(?:up to one )?target creature "
    r"(?:you don'?t control|an opponent controls))\. "
    r"each creature you control (?P<filter>that'?s an? \w+(?: or an? \w+)*|with an? "
    r"\+1/\+1 counter on it) deals damage equal to its power to that creature$",
    re.IGNORECASE,
)
_GROUP_BITE_KINDS_RE = re.compile(r"an? (\w+)", re.IGNORECASE)


def _group_bite_predicate(game_filter: str) -> "Callable[[Game, CardState], bool] | None":
    """The printed qualifier as a test on a creature you control, or `None`."""
    lowered = game_filter.lower()
    if lowered.startswith("with"):
        return lambda game, creature: creature.counters["+1/+1"] > 0
    words = {word.lower() for word in _GROUP_BITE_KINDS_RE.findall(lowered)}
    if not words or not all(word in subtype_vocabulary() for word in words):
        return None

    def matches(game: "Game", creature: CardState) -> bool:
        characteristics = game.characteristics_of(creature)
        return bool(words & {sub.lower() for sub in characteristics.subtypes})

    return matches


@SPELL_TEXT.rung("s12")
def _parse_choose_target_then_group_bite_clause(effect_text: str) -> Effect | None:
    """`_CHOOSE_THEN_GROUP_BITE_RE`'s shape - see the banner above."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split()).rstrip(".")
    match = _CHOOSE_THEN_GROUP_BITE_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    qualifies = _group_bite_predicate(match.group("filter"))
    if qualifies is None:
        return None
    support = int(match.group("support")) if match.group("support") else 0

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        chosen = [
            target
            for target in game.resolve_targets(spell)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if support:
            # CR 701.41a first (CR 608.2c): the support targets come first in
            # the announcement; the last one is the bite's victim when it is
            # an opposing creature (the slot "up to one target creature an
            # opponent controls" can only be filled by one).
            victims = (
                chosen[-1:]
                if chosen and (game.controller_of(chosen[-1]).username != controller.username)
                else []
            )
            put_support_counters(game, chosen[: len(chosen) - len(victims)], support)
        else:
            victims = chosen
        if not victims:
            return
        victim = victims[0]
        biters = [
            creature
            for creature in list(game.battlefield)
            if creature.zone is Zone.BATTLEFIELD
            and game.controller_of(creature).username == controller.username
            and game.characteristics_of(creature).is_creature
            and qualifies(game, creature)
        ]
        for biter in biters:
            amount = game.power_of(biter) or 0
            if amount > 0 and victim.zone is Zone.BATTLEFIELD:
                game.deal_damage(victim, amount, source=biter)

    return effect


# --------------------------------------------------------------------------
# A spell's CR 603.12 reflexive ability: "<instruction>. When you do, <that
# creature | it> fights up to one target creature you don't control."
# --------------------------------------------------------------------------
#
# The spell's first sentence acts on the one object it targets (a Role token
# attached to it, a card returned to the battlefield); "that creature"/"it" in
# the reflexive sentence is that object, carried on the reflexive ability's own
# `DelayedTrigger.subject_id` (CR 603.7c) - not re-targeted. The reflexive
# ability's own target is chosen as it goes on the stack (CR 603.3d), so the
# spell announces only the first sentence's target. CR 701.14b: a fighter that
# is gone, or no longer a creature, or an illegal fight target, means no fight.

_PHRASE_FIGHT_TARGET = r"(?:up to one )?target creature (?:you don'?t control|an opponent controls)"
_REFLEXIVE_SUBJECT_FIGHTS_RE = re.compile(
    rf"^(?:that creature|it) fights {_PHRASE_FIGHT_TARGET}$", re.IGNORECASE
)
_FIRST_THEN_REFLEXIVE_FIGHT_RE = re.compile(
    rf"^(?P<first>[^.]*\btarget\b[^.]*)\.\s*when you do, "
    rf"(?P<clause>(?:that creature|it) fights {_PHRASE_FIGHT_TARGET})$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD, before=["damage._parse_self_fights_target_clause"])
def _parse_reflexive_subject_fights_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "`<that creature | it>` fights up to one target creature `<...>`" as a
    reflexive ability's own clause: the fighter is the creature the creating
    spell acted on (`DelayedTrigger.subject_id`), the opponent is this
    ability's own target, rechecked as it resolves (CR 608.2b). An "it"
    with no such subject is `_parse_self_fights_target_clause`'s own plain
    CR 109.2 self-reference, which this rung sits ahead of and defers to."""
    if for_spell:
        return None
    stripped = clause.strip().rstrip(".").strip()
    if _REFLEXIVE_SUBJECT_FIGHTS_RE.fullmatch(stripped) is None:
        return None
    if not _targets_understood(stripped.split(" fights ", 1)[1], count_agnostic=True):
        return None
    self_fight = _parse_self_fights_target_clause(clause, for_spell=False)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        trigger = game.delayed_triggers.trigger_for(ability)
        if trigger is None or trigger.subject_id is None:
            if self_fight is not None:
                self_fight(game, ability)
            return
        fighter = game.find_by_id(trigger.subject_id)
        controller = game.controller_of(ability)
        if not isinstance(fighter, CardState) or fighter.zone is not Zone.BATTLEFIELD:
            return
        opponents = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState)
            and target.zone is Zone.BATTLEFIELD
            and game.controller_of(target).username != controller.username
        ]
        if not opponents:
            return  # CR 115.6's "up to one" chose none, or CR 608.2b removed it.
        if game.characteristics_of(fighter).is_creature and (
            game.characteristics_of(opponents[0]).is_creature
        ):
            _fight(game, fighter, opponents[0])  # CR 701.14b

    return effect


#: "you may have it fight target creature you don't control" (Affectionate
#: Indrik, Temur War Shaman), "you may have this creature fight another target
#: creature" (Nessian Wilds Ravager, Atzocan Archer) - CR 701.14a's fight,
#: optional, the "you may" answered as the ability resolves (CR 608.2d). The
#: target is announced as the ability goes on the stack (CR 603.3d) and
#: rechecked as it resolves (CR 608.2b): with none left, nothing is asked.
#: "this creature" is the source (CR 700.7). "it" is the object the trigger
#: event named when that is a permanent other than the source - Temur War
#: Shaman's "Whenever a permanent you control is turned face up, ..., you may
#: have it fight" names the turned-up permanent - and otherwise the source.
_MAY_HAVE_FIGHT_RE = re.compile(
    r"^you may have (?P<subject>it|this creature|this permanent) fight "
    r"(?P<phrase>(?:up to one )?(?:other )?target [^.]+|another target [^.]+?)\.?$",
    re.IGNORECASE,
)


def _may_have_fight_fighter(
    game: "Game", ability: AbilityOnStack, subject: str
) -> CardState | None:
    """The creature `subject` names for `_MAY_HAVE_FIGHT_RE` (see its banner)."""
    if subject == "it":
        event = ability.event
        if (
            event is not None
            and event.subject_id is not None
            and event.subject_id != ability.source_id
        ):
            found = game.find_by_id(event.subject_id)
            return found if isinstance(found, CardState) else None
    return ability.source(game)


@ABILITY_TEXT.rung("s16")
def _parse_may_have_fight_clause(text: str) -> AbilityEffect | None:
    """`_MAY_HAVE_FIGHT_RE`'s shape; see the banner above."""
    stripped = " ".join(text.split())
    if not stripped.lower().startswith("you may have "):
        return None
    match = _MAY_HAVE_FIGHT_RE.fullmatch(stripped)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    subject = match.group("subject").lower()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        fighter = _may_have_fight_fighter(game, ability, subject)
        if fighter is None or fighter.zone is not Zone.BATTLEFIELD:
            return
        opponents = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not opponents:
            return  # CR 608.2b, or "up to one" chose none.
        opponent = opponents[0]
        if not game.may(
            ability.controller,
            f"have {fighter.name} fight {opponent.name}?",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        board = game.characteristics_of
        if board(fighter).is_creature and board(opponent).is_creature:
            _fight(game, fighter, opponent)  # CR 701.14b: both must be creatures

    return effect


@SPELL_TEXT.rung("s12")
def _parse_first_then_reflexive_subject_fights_clause(effect_text: str) -> Effect | None:
    """`_FIRST_THEN_REFLEXIVE_FIGHT_RE`'s shape - see the banner above. The
    first sentence is read as an ordinary clause sequence and runs first (CR
    608.2c); the reflexive ability exists only if the object it acted on is
    still a creature on the battlefield afterwards."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _FIRST_THEN_REFLEXIVE_FIGHT_RE.fullmatch(whole.rstrip("."))
    if match is None:
        return None
    first = _parse_mixed_clauses(match.group("first").strip() + ".", for_spell=True)
    if first is None:
        return None
    reflexive_text = f"When you do, {match.group('clause').strip()}."
    if reflexive_consequence_effect(reflexive_text.removeprefix("When you do, ")) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        subjects = [
            target for target in game.resolve_targets(spell) if isinstance(target, CardState)
        ]
        for clause in first:
            clause(game, spell)
        if not subjects:
            return
        subject = game.find_by_id(subjects[0].id)
        if (
            not isinstance(subject, CardState)
            or subject.zone is not Zone.BATTLEFIELD
            or not game.characteristics_of(subject).is_creature
        ):
            return
        game.create_reflexive_trigger(
            text=reflexive_text,
            controller=game.controller_of(spell).username,
            source_id=spell.id,
            source_name=spell.card.name,
            callback=ReflexiveWhenYouDoConsequence(),
            subject_id=subject.id,
        )

    return effect


# --------------------------------------------------------------------------
# A spell's optional action, then a CR 603.12 reflexive consequence:
# "<instruction>. Then you may <discard N cards | sacrifice <restriction>>.
# When you do, <consequence>."
# --------------------------------------------------------------------------
#
# `_parse_reflexive_may_discard_clause`/`_parse_reflexive_sacrifice_clause`
# already read this on an ability; a spell's own text is the same grammar with
# a leading instruction. The reflexive ability exists only when the action was
# actually taken (CR 603.12): a discard of fewer cards than the spell asked for
# does not count, since "you may discard two cards" is only performed in full.
# "where X is the greatest mana value among cards discarded this way" is
# worked out from the cards actually discarded and written into the reflexive
# ability's text as a number (CR 107.3a), the same way a cast X is.

_GREATEST_DISCARDED_RE = re.compile(
    r", where X is the greatest mana value among cards discarded this way$", re.IGNORECASE
)
_FIRST_THEN_MAY_ACTION_REFLEXIVE_RE = re.compile(
    rf"^(?P<first>[^.]+)\.\s*then you may "
    rf"(?:discard (?P<n>{COUNT}) cards?|sacrifice (?P<restriction>[^.]+))\.\s*"
    r"when you do, (?P<consequence>[^.]+)$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s12")
def _parse_first_then_may_action_reflexive_clause(effect_text: str) -> Effect | None:
    """`_FIRST_THEN_MAY_ACTION_REFLEXIVE_RE`'s shape - see the banner above."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _FIRST_THEN_MAY_ACTION_REFLEXIVE_RE.fullmatch(whole.rstrip("."))
    if match is None:
        return None
    first = _parse_mixed_clauses(match.group("first").strip() + ".", for_spell=True)
    if first is None:
        return None
    consequence = match.group("consequence").strip()
    discard_count = parse_count(match.group("n")) if match.group("n") else None
    restriction = None
    if match.group("restriction") is not None:
        restriction = _sacrifice_restriction(match.group("restriction"))
        if restriction is None:
            return None
    elif discard_count is None:
        return None
    greatest = _GREATEST_DISCARDED_RE.search(consequence)
    if greatest is not None:
        if discard_count is None:
            return None
        consequence = consequence[: greatest.start()]
    if re.search(r"\bX\b", consequence) and greatest is None:
        return None
    if reflexive_consequence_effect(_carry_count(consequence, 2, x=True)) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for clause in first:
            clause(game, spell)
        player = game.controller_of(spell)
        source_id = source_id_of(spell)
        source_name = spell.card.name
        if restriction is not None:
            candidates = restriction.candidates(game, player, spell.id)
            decision = Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=f"sacrifice {match.group('restriction').strip()}",
                source=source_name,
                affirmative_is_legal=_sacrifice_is_payable(restriction.quantity, candidates),
                source_id=source_id,
            )
            if not game.ask(decision):
                return
            chosen = _choose_permanents_to_sacrifice(
                game, player, restriction, candidates, source_name=source_name, source_id=source_id
            )
            if not chosen:
                return
            for permanent in chosen:
                game.sacrifice(permanent)
            game.record_count(len(chosen))
            amount = len(chosen)
        else:
            assert discard_count is not None
            decision = Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=f"discard {discard_count} card(s)",
                source=source_name,
                affirmative_is_legal=len(player.hand) >= discard_count,
                source_id=source_id,
            )
            if not game.ask(decision):
                return
            discarded = _discard_cards(
                game, player, discard_count, source_name, source_id=source_id, exact=True
            )
            if len(discarded) < discard_count:
                return
            amount = int(max((card.mana_value for card in discarded), default=0))
        game.create_reflexive_trigger(
            text=f"When you do, {_carry_count(consequence, amount, x=True)}.",
            controller=player.username,
            source_id=spell.id,
            source_name=source_name,
            callback=ReflexiveWhenYouDoConsequence(),
        )

    return effect


def _linked_pile(game: "Game", ability: AbilityOnStack) -> list[CardState]:
    """The cards exiled with the object this ability came from (CR 607.2a) -
    that incarnation of it (CR 400.7, `AbilityOnStack.source_stamp`), which
    is still the right pile when the source was sacrificed to pay for the
    ability (CR 113.7a)."""
    if ability.source_id is None:
        return []
    return game.cards_exiled_with(ability.source_id, ability.source_stamp)


#: Turncoat Kunoichi's own ETB: "choose target creature an opponent
#: controls. Exile that creature until this creature leaves the battlefield.
#: If this creature's sneak cost was paid, instead exile the chosen
#: creature." Two sentences establish `_EXILE_UNTIL_THIS_LEAVES_BATTLEFIELD_
#: RE`'s own temporary exile (CR 610.3) under a "choose target ..." heading
#: rather than naming the target inline the way that regex's own callers do
#: (`_parse_choose_target_then_return_to_your_hand_pair`'s own docstring
#: gives the identical "choose target `<phrase>`." shape its precedent), and
#: a third instead-clause (CR 614.1a) drops CR 610.3's own return-on-leaving
#: watcher entirely when the sneak cost was paid, making the exile
#: permanent - "the chosen creature" (CR 400.7's anaphora) is the same
#: object the first sentence's "choose target" already fixed, read the
#: identical `game.resolve_targets(ability)` way every branch here does,
#: never a second target of its own.
_CHOOSE_TARGET_EXILE_UNTIL_LEAVES_THEN_INSTEAD_PERMANENT_RE = re.compile(
    r"^choose target (?P<phrase>.+?)\.\s*"
    r"exile that [a-z]+ until this (?P<type>creature|artifact|enchantment|planeswalker|permanent)"
    r" leaves the battlefield\.\s*"
    r"if (?P<condition>[^,]+), instead exile the chosen [a-z]+\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_choose_target_exile_until_leaves_then_instead_permanent_clause(
    text: str,
) -> AbilityEffect | None:
    """`_CHOOSE_TARGET_EXILE_UNTIL_LEAVES_THEN_INSTEAD_PERMANENT_RE`'s shape."""
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _CHOOSE_TARGET_EXILE_UNTIL_LEAVES_THEN_INSTEAD_PERMANENT_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('phrase')}", count_agnostic=True):
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            target for target in game.resolve_targets(ability) if isinstance(target, CardState)
        ]
        if not targets:
            return  # CR 608.2b/115.6: no (legal) target chosen; nothing to exile.
        source = ability.source(game)
        if source is None:
            return  # CR 113.7a: the source is already gone; nothing left to watch leave.
        controller = game.controller_of(ability).username
        held = game.condition_holds(controller, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=whole
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        for target in targets:
            exiled = game.exile_permanent(target)
            if exiled.zone is not Zone.EXILE:
                continue  # CR 111.8: a token refused the move.
            if not held:
                _watch_for_departure_and_return_exiled_card(game, source, exiled, controller)

    return effect


def _optional_targeted_clause(
    inner: TargetedClause, prompt: str, *, for_spell: bool
) -> TargetedClause:
    """The targeted twin of `_optional_clause`: "you may destroy target
    artifact" (Batterhorn), "you may exile target nonland permanent" (Angel of
    Sanctions), "you may return target creature to its owner's hand" (Angler
    Drake), "you may tap target creature" (Alaborn Cavalier, Angelic
    Benediction).

    `for_spell` picks how to name the asker and the source the same way
    `_parse_targeted_clause` already does: a spell's controller and its own
    name (CR 120.2b), or an ability's controller and `source_name`.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if game.may(player, prompt, source=source, source_id=source_id_of(stack_object)):
            inner(game, stack_object)

    return effect


#: "Target player <does something>[, then <does something else>]." -
#: Kozilek's Command's mode 2, "Target player scries X, then draws a card."
#: `rest` is everything after the subject, DOTALL so a card printing this
#: across more than one sentence is still read as one phrase.
_TARGET_PLAYER_CLAUSE_RE = re.compile(r"^target player (?P<rest>.+)$", re.IGNORECASE | re.DOTALL)


def _parse_target_player_mode(text: str) -> Effect | None:
    """A mode whose subject is "target player" rather than "you" - the same
    plain-clause vocabulary `parse_clause_effect` already reads (scry, draw,
    mill, surveil, a life total, energy), run against whichever player this
    mode targets instead of the resolving spell's own controller.

    Split the same way `split_effect_clauses` splits a whole card - "scries
    X, then draws a card" is two instructions carried out in the order printed
    (CR 608.2c), both by the *same* named player, which is exactly why this
    cannot simply hand the two halves to `parse_player_effect_for_spell`:
    that function's clauses each independently mean "you", the resolving
    spell's controller, and only the first of these two means "target
    player" on its own - the continuation still refers back to it.
    """
    match = _TARGET_PLAYER_CLAUSE_RE.match(text.strip())
    if match is None:
        return None
    rest = match.group("rest").strip().rstrip(".").strip()
    sub_clauses = [part.strip() for part in _CLAUSE_SEPARATOR.split(rest) if part.strip()]
    if not sub_clauses:
        return None
    parsed: list[ClauseEffect] = []
    for sub in sub_clauses:
        clause_effect = parse_clause_effect(sub) or parse_clause_effect(f"you {sub}")
        if clause_effect is None:
            return None
        parsed.append(clause_effect)

    def effect(game: "Game", spell: CardState) -> None:
        for target in game.resolve_targets(spell):
            if isinstance(target, Player):
                for clause_effect in parsed:
                    clause_effect(game, target, spell.card.name, source_id_of(spell))
                    game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def parse_mode_effect(mode: Mode, x_value: int) -> Effect | None:
    """One chosen mode's own effect (CR 700.2a), read off its printed text
    with X already substituted throughout it (CR 107.3a, CR 107.3c).

    Tries the two "target player ..." shapes first, since nothing else here
    reads a mode whose subject is a targeted player rather than the caster;
    falls back to `parse_mixed_effect_for_spell`, the same per-clause
    dispatcher a whole non-modal card's text goes through, for every other
    mode shape - a mode is exactly one card's worth of CR 608.2c instructions
    once it is standing on its own, X already substituted and no bulleted
    list left for `is_modal_text` to trip over.

    A mode whose own text is a CR 611.2 layer shape (a pump, a keyword
    grant, a base P/T set) - Perfected Theory's "Target creature has base
    power and toughness 1/1 until end of turn.", Charge the Sanctum's
    "Creatures you control get +2/+0 until end of turn.", Witherbloom
    Command's "Target creature gets -3/-1 until end of turn." - goes to
    `_compose_layer_effect_with_remainder_for_mode`, the mode-scoped twin of
    the whole-card fallback `_spell_effect_or_notice` itself uses, *ahead of*
    `parse_mixed_effect_for_spell`: that dispatcher reads a pump as the bare
    `create_continuous_effect` sentinel, which builds off the whole modal
    card's text and so created nothing for the chosen mode.
    """
    raw = mode_effect_text(mode)
    # CR 107.3c: an X the mode's own text defines ("... gains X life, where X
    # is the greatest power among creatures they control") is that value, not
    # the caster's announced one - left in place for the "where X is" reader.
    if _WHERE_X_IS_INLINE_RE.search(raw) is None:
        raw = substitute_x(raw, x_value)
    text = _strip_non_effect_preamble(raw).strip()
    if not text:
        return None
    token_for_player = _parse_target_player_token_mode(text)
    if token_for_player is not None:
        return token_for_player
    # Ahead of `_parse_target_player_mode`: "Target player mills three cards,
    # then you return ..." names a second subject ("you") for its second
    # instruction, which that reader would wrongly run against the target.
    mill_then_return_to_hand = _parse_mill_then_return_to_hand_clause(text)
    if mill_then_return_to_hand is not None:
        return mill_then_return_to_hand
    mill_then_puts_into_own_hand = _parse_target_player_mills_then_puts_milled_into_own_hand_clause(
        text
    )
    if mill_then_puts_into_own_hand is not None:
        return mill_then_puts_into_own_hand
    player_subject = _parse_target_player_mode(text)
    if player_subject is not None:
        return player_subject
    # Read whole, ahead of the per-clause dispatcher: the family's three
    # sentences are one CR 608.2c instruction and its follow-up, and
    # `split_effect_clauses` would hand them over one at a time, losing the
    # "from among them" link between the mill and the choice.
    select_from_top = _parse_select_from_top_spell_clause(text)
    if select_from_top is not None:
        return select_from_top
    # Mastermind's Acquisition's second mode - the whole-text wish reader
    # `_spell_effect_or_notice` runs, which a mode never reaches.
    put_from_outside = _parse_put_from_outside_the_game_into_hand_spell(text)
    if put_from_outside is not None:
        return put_from_outside
    c02_t6 = _c02_t6_spell_effect(text)
    if c02_t6 is not None:
        return c02_t6
    # Grab the Reins's second mode: "Sacrifice a creature. ~ deals damage equal
    # to that creature's power to any target." - an amount that spends a
    # characteristic of the object an earlier sentence of the mode moved, which
    # a mode never reaches the spell-text ladder to have read.
    referenced_stat = referenced_permanent_stat_effect(text, for_spell=True)
    if referenced_stat is not None:
        return referenced_stat
    # Witherbloom Charm's own first mode: "You may sacrifice a permanent. If
    # you do, draw two cards." (CR 118.12) is read whole by `_spell_effect_
    # or_notice` for a non-modal card, but a mode's own text never reaches
    # that function - `parse_mode_effect` is the mode-scoped path, and it had
    # no equivalent try for this exact shape, so the mode fell through to
    # `parse_mixed_effect_for_spell` below and failed closed on the whole
    # card (CR 700.2a: one mode is still one card's worth of CR 608.2c
    # instructions once it stands on its own).
    conditional_sacrifice = _parse_conditional_sacrifice_clause(text, for_spell=True)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    # Mob Rule's modes: the whole three-sentence group steal, read before the
    # layer composer below sees only its "gain control" sentence.
    mass_gain_control = _parse_mass_gain_control_untap_clause(text)
    if mass_gain_control is not None:
        return mass_gain_control
    mode_return_as_creature = _parse_return_as_creature_clause(text)
    if mode_return_as_creature is not None:
        return mode_return_as_creature
    # Ember Island Production's modes: a token copy whose "except" list
    # carries its own "and", which the clause splitter would cut.
    mode_token_copies_except = _parse_create_token_copies_except_clause(text, for_spell=True)
    if mode_token_copies_except is not None:
        return mode_token_copies_except
    # A genuine layer sentence goes to the mode-scoped composer ahead of the
    # per-clause dispatcher: `parse_mixed_effect_for_spell` reads "Target
    # creature gets -3/-1 until end of turn." (Witherbloom Command's third
    # mode) as the bare `create_continuous_effect` sentinel, which builds its
    # effect off the *whole* card's text - for a modal card, a bulleted list
    # `LAYER_EFFECTS` does not read, so the mode silently did nothing.
    animate_chosen = choose_and_animate_mode(text)
    if animate_chosen is not None:
        return animate_chosen
    # A mass pump ("Creatures you control get +1/+2 until end of turn.",
    # Fatehold Charm's third mode, Charge the Sanctum's second) fixes its
    # group at resolution (CR 611.2c) through `_run_mass_pump`; the scoped
    # layer composer below resolves no group, so it would build no effect.
    mass_pump_mode = _mass_pump_spell_effect(text)
    if mass_pump_mode is not None:
        return mass_pump_mode
    layer_mode = _compose_layer_effect_with_remainder_for_mode(text)
    if layer_mode is not None:
        return layer_mode
    # Frontline Rush's own second mode: "Target creature gets +X/+X until
    # end of turn, where X is the number of creatures you control." - a
    # self-defined X (CR 107.3c) the layer composer just above cannot read
    # (its own `genuine_resolution_layer_text` has no notion of a literal
    # "X"), tried ahead of the ordinary per-clause fallback for the same
    # reason `layer_mode` is: a bare "gets +X/+X" sentinel would otherwise
    # build off the whole card's text, not this mode's own.
    where_x_targeted = _parse_where_x_is_continuous_effect_for_spell(text)
    if where_x_targeted is not None:
        return where_x_targeted
    # Plunge into Darkness's second mode: a chosen amount, then a payoff that
    # reads it - the whole-text readers a non-modal spell reaches through
    # `SPELL_TEXT`, which a mode's own text never does. After the mode-scoped
    # "where X is" readers above, which know a mode's own targets.
    from ..ep02_r2_chosen_amounts import chosen_amount_spell_effect

    chosen_amount = chosen_amount_spell_effect(text)
    if chosen_amount is not None:
        return chosen_amount
    # Shriveling Rot's modes: "Until end of turn, whenever a creature is dealt
    # damage, destroy it." - a chosen mode that creates a CR 603.7 delayed
    # trigger, read the way the same sentence on a non-modal spell is.
    created_trigger = _parse_created_trigger_spell_text(text)
    if created_trigger is not None:
        return created_trigger
    gain_control_and_grant = until_eot_gain_control_and_grant_text(text)
    if gain_control_and_grant is not None:
        return parse_mixed_effect_for_spell(gain_control_and_grant)
    return parse_mixed_effect_for_spell(text)


#: "Choose up to two. Return those cards from your graveyard to your hand.
#: - Target artifact card. - Target creature card. ..." (Call Damage
#: Control) - a modal instruction whose own trailing sentence carries the
#: *shared verb* every mode's bare "target `<quality>` card" bullet is
#: missing (CR 700.2's own economy: rather than repeat "return target
#: artifact card from your graveyard to your hand" four times, the card
#: prints the verb once, plural, and each mode is only the noun that fills
#: it). `parse_mode_effect` reads a mode's *own* text alone and has nothing
#: for a bare target phrase with no verb; this substitutes the mode's own
#: singular phrase for the shared sentence's own plural pronoun
#: ("those cards"/"them") and reads the result the ordinary way.
_SHARED_VERB_WITH_PLURAL_PRONOUN_RE = re.compile(
    r"^(?P<lead>.+?)\b(?:those cards|them)\b(?P<tail>.*)$", re.IGNORECASE | re.DOTALL
)
_BARE_TARGET_PHRASE_RE = re.compile(r"^target .+$", re.IGNORECASE)


def _parse_mode_with_shared_verb_fallback(mode: "Mode", instruction: str) -> Effect | None:
    """`_SHARED_VERB_WITH_PLURAL_PRONOUN_RE`'s shape, or `None` when the
    mode's own text is not a bare target phrase, or the instruction carries
    no such shared sentence."""
    mode_text = mode.text.strip().rstrip(".")
    if _BARE_TARGET_PHRASE_RE.fullmatch(mode_text) is None:
        return None
    # The instruction is the whole printed line, "Choose up to two. Return
    # those cards ..." - only the sentence(s) after the "Choose ..." lead
    # carry the shared verb.
    sentences = [s.strip() for s in re.split(r"(?<=[.\-])\s+", instruction) if s.strip()]
    shared = next((s for s in sentences if not s.lower().startswith("choose")), None)
    if shared is None:
        return None
    match = _SHARED_VERB_WITH_PLURAL_PRONOUN_RE.fullmatch(shared.rstrip("."))
    if match is None:
        return None
    synthesized = f"{match.group('lead')}{mode_text}{match.group('tail')}.".strip()
    return parse_mixed_effect_for_spell(synthesized)


def resolve_modal_spell(game: "Game", spell: CardState) -> None:
    """CR 700.2a: run each mode this spell was cast with, independently, in
    the order printed on the card.

    CR 702.42b, entwine's own resolution rule, generalizes past entwine
    itself: "follow the text of each of the modes in the order written on the
    card when the spell resolves" is how *any* modal spell with more than one
    chosen mode resolves, entwined or not - entwine only changes how many
    modes got chosen, never how they are carried out once chosen.

    **Fail-closed per mode, not per spell.** A mode this wave cannot read is
    skipped - recorded as a `ModeNotice` - while every other chosen mode of
    the same spell still happens. That is a deliberate choice, not the
    per-clause "one gap voids the whole card" fail-closed the rest of this
    file uses within a *single* instruction's clauses: CR 101.3 excuses only
    "any part of an instruction that's impossible to perform", and CR 700.2
    already treats each mode as its own instruction, carried out on its own
    (`700.2c`'s targets, `700.2f`'s "different targeting requirements for
    each mode", and 702.42b's "each of the modes" above all describe modes as
    separable units, not sub-clauses of one). Kozilek's Command choosing
    modes 1 and 3 with mode 1 unreadable and mode 3 fine should not throw away
    a legally-resolved exile because a different bullet on the same card is a
    parser gap - that would make the *working* half of the spell depend on an
    unrelated mode nobody chose it for, which is worse than the mode simply
    not happening and saying so.

    Each mode's own targets are `Game.cast_record(spell).mode_targets`, sliced
    per chosen mode instance by `Casting.choose_targets` (CR 700.2f) rather
    than the flat `spell.targets` a non-modal effect reads - so `spell.targets`
    is swapped to just this mode's slice for the duration of its own effect,
    and restored afterward regardless of what ran.
    """
    record = game.cast_record(spell)
    modal = modal_profile(spell.card)
    if modal is None or not modal.understood or not record.modes:
        return
    original_targets = spell.targets
    try:
        for position, mode_number in enumerate(record.modes):
            try:
                mode = modal.mode(mode_number)
            except ValueError:
                continue
            slice_targets = (
                record.mode_targets[position] if position < len(record.mode_targets) else []
            )
            spell.targets = list(slice_targets)
            clause = parse_mode_effect(mode, record.x_value)
            if clause is None:
                clause = _parse_mode_with_shared_verb_fallback(mode, modal.instruction)
            if clause is None:
                game.mode_notices.append(
                    ModeNotice(
                        source_id=spell.id,
                        source_name=spell.card.name,
                        mode_number=mode.number,
                        text=mode.text,
                    )
                )
                continue
            clause(game, spell)
    finally:
        spell.targets = original_targets


#: The option a player names to stop choosing modes once the instruction's
#: minimum is met - "choose one or both" (CR 700.2) takes a second mode only
#: if the player wants one. Offered first, so an unscripted player takes the
#: least they must.
NO_FURTHER_MODES = "Choose no further modes."


def modal_trigger_profile(effect_text: str | None) -> ModalProfile | None:
    """The modes of a triggered ability's "choose ... -" effect (CR 700.2),
    or `None` when the text is not modal or its structure is not read.

    `effect_text` arrives whitespace-collapsed - `machines/abilities.
    _strip_reminder` runs `re.sub(r"\\s+", " ", ...)` on every printed line,
    `TriggeredAbility.effect` included, flattening the newlines
    `_merge_modal_bullet_lines` had reassembled - and `machines/modes._parse`
    reads bullets one per line (CR 700.2's printed shape), so the newline is put
    back before each bullet here rather than teaching two modules two bullet
    grammars.

    Read: every counted instruction - "choose one", "choose one or both",
    "choose one or more", and the minimum-zero "choose up to N" and "choose
    any number" (CR 700.2b: "If no mode is chosen, the ability is removed
    from the stack", which `Game._announce_trigger_modes` does). Pawprint or
    per-mode costs (`understood` False) return `None`.
    """
    text = re.sub(r"\s*\u2022\s*", "\n\u2022 ", effect_text or "").strip()
    if not is_modal_text(text):
        return None
    profile = modal_profile_from_text(text)
    if profile is None or not profile.understood or not profile.modes:
        return None
    if any(mode.cost is not None for mode in profile.modes):
        return None
    return profile


def mode_effect_body(mode: Mode) -> str:
    """One mode's effect text with CR 700.2h's cost prefix and CR 207.2d's
    flavor word taken off (`machines/modes.mode_effect_text` does both - Flash
    Thompson's "Heckle" label comes off "Tap target creature.") - what a
    parser reads and what targeting is read from."""
    return mode_effect_text(mode).strip()


def _run_modal_instruction_rider(game: "Game", ability: AbilityOnStack, rider: str) -> None:
    """Run the modal instruction's own rider sentence (see
    `modes.instruction_rider`), reading the source's printed name as the
    source itself (CR 201.5)."""
    text = _self_normalized_effect_text(ability.source_name, rider)
    clause = parse_mixed_effect(text)
    if clause is None:
        game.mode_notices.append(
            ModeNotice(
                source_id=ability.source_id,
                source_name=ability.source_name,
                mode_number=0,
                text=rider,
            )
        )
        return
    clause(game, ability)


@ABILITY_TEXT.rung("s16")
def _resolve_modal_triggered_ability_clause(text: str) -> AbilityEffect | None:
    """A modal *triggered* ability's own "choose one/one or both -" tail
    (CR 700.2, CR 603.3c) - Elder Gargaroth, Abiding Grace, Flash Thompson.

    CR 603.3c: "its controller announces the mode choice when putting the
    ability on the stack", and CR 700.2c chooses targets only for the modes
    chosen. `Game.put_triggers_on_stack` does both and records them on the
    ability (`AbilityOnStack.modes`, `.mode_targets`); this runs each chosen
    mode in order with `ability.targets` narrowed to that mode's own slice,
    the same per-mode dispatch `resolve_modal_spell` gives a spell. A mode
    whose text is not read records a `ModeNotice` and the others still run.

    An ability that reaches resolution with no mode recorded never went
    through that hook (a copy made elsewhere, for instance); it is asked for
    its first mode now rather than doing nothing.
    """
    profile = modal_trigger_profile(text)
    if profile is None:
        return None
    instruction_lower = profile.instruction.lower()
    exclusive_this_turn = "hasn't been chosen this turn" in instruction_lower
    exclusive = exclusive_this_turn or "hasn't been chosen" in instruction_lower
    rider_text = instruction_rider(profile.instruction)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if rider_text is not None:
            _run_modal_instruction_rider(game, ability, rider_text)
        chosen = list(ability.modes)
        slices = [list(slice_) for slice_ in ability.mode_targets]
        if not chosen:
            # Gollum, Riddle Master's own "that hasn't been chosen" (and The
            # Vision's own "that hasn't been chosen this turn") - see
            # `Game._announce_trigger_modes`'s own docstring for the ordinary
            # path (CR 603.3c chooses modes as the ability goes on the
            # stack); this fallback is only reached for an ability that
            # somehow arrived at resolution with no mode recorded at all
            # (a copy made elsewhere), so the same exclusion is applied here
            # too rather than silently offering an already-used mode.
            available_modes = profile.modes
            source_state = ability.source(game) if exclusive else None
            if exclusive and source_state is not None:
                already = (
                    source_state.chosen_modal_options_this_turn
                    if exclusive_this_turn
                    else source_state.chosen_modal_options
                )
                available_modes = tuple(m for m in profile.modes if m.text not in already)
            if not available_modes:
                return
            chosen_text = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_MODE,
                    player=ability.controller,
                    prompt="choose one",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    options=tuple(mode.text for mode in available_modes),
                )
            )
            mode = next((m for m in available_modes if m.text == chosen_text), available_modes[0])
            chosen = [mode.number]
            slices = [list(ability.targets)]
            if exclusive and source_state is not None:
                if exclusive_this_turn:
                    source_state.chosen_modal_options_this_turn = (
                        *source_state.chosen_modal_options_this_turn,
                        mode.text,
                    )
                else:
                    source_state.chosen_modal_options = (
                        *source_state.chosen_modal_options,
                        mode.text,
                    )
        original_targets = ability.targets
        # CR 608.2c: the chosen modes run in the order printed on the card,
        # however they were announced (the same order `ModalProfile.resolve`
        # gives a spell); each keeps its own target slice (CR 700.2c).
        printed_order = sorted(range(len(chosen)), key=lambda position: chosen[position])
        try:
            for position in printed_order:
                mode = profile.mode(chosen[position])
                ability.targets = list(slices[position]) if position < len(slices) else []
                mode_text = mode_effect_body(mode)
                clause = _parse_counter_resolution_text(mode_text)
                if clause is None:
                    clause = parse_mixed_effect(mode_text)
                if clause is None:
                    clause = _compose_layer_effect_with_remainder_for_ability_mode(mode_text)
                if clause is None:
                    clause = _parse_where_x_is_continuous_effect(mode_text)
                if clause is None:
                    # CR 201.5's bare legendary first-name self-reference
                    # (Gollum, Riddle Master's own "Put a +1/+1 counter on
                    # Gollum.") - none of the three fallback readers above
                    # normalize it themselves, so it is tried again, once,
                    # against `ability.source_name`'s own rewrite to "this
                    # creature" before falling to a notice.
                    normalized_mode_text = _self_normalized_effect_text(
                        ability.source_name, mode_text
                    )
                    if normalized_mode_text != mode_text:
                        clause = parse_mixed_effect(normalized_mode_text)
                        if clause is None:
                            clause = _compose_layer_effect_with_remainder_for_ability_mode(
                                normalized_mode_text
                            )
                        if clause is None:
                            clause = _parse_where_x_is_continuous_effect(normalized_mode_text)
                    if clause is None:
                        # A whole-ability reading the clause parsers above do
                        # not carry: Glorfindel, Dauntless Rescuer's "must be
                        # blocked this turn if able" (CR 509.1c) and "can't be
                        # blocked by more than one creature each combat this
                        # turn" (CR 509.1b) modes.
                        clause = _ability_effect_or_notice(normalized_mode_text)
                if clause is None:
                    game.mode_notices.append(
                        ModeNotice(
                            source_id=ability.source_id,
                            source_name=ability.source_name,
                            mode_number=mode.number,
                            text=mode.text,
                        )
                    )
                    continue
                clause(game, ability)
        finally:
            ability.targets = original_targets

    return effect


#: "If a source would deal damage to a player or battle this turn, it deals
#: that much damage plus 2 instead." (Rankle and Torbran's third mode) - one
#: CR 614.1a turn-long damage modifier (`damage_modification.
#: DamageModifierReplacement`, CR 611.2a's "this turn"), read as one clause
#: so a modal mode or a sentence among others reaches it: the whole-text
#: readers (`_parse_created_replacement_ability_text`) only ever see an
#: ability's entire text. "you" is the controller as it resolves (CR 109.5).
@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_turn_damage_modifier_instead_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    text = _as_sentence(" ".join(clause.split()))
    lowered = text.lower()
    if not lowered.startswith("if ") or " this turn, it deals " not in lowered:
        return None
    spec = read_turn_damage_spec(text)
    if not isinstance(spec, DamageModifierReplacement):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if isinstance(stack_object, CardState):
            source_id, source_name = stack_object.id, stack_object.card.name
        else:
            source_id, source_name = stack_object.source_id, stack_object.source_name
        game.created_replacements.append(
            CreatedReplacement(
                spec=spec,
                label=text,
                controller=game.controller_of(stack_object).username,
                source_id=source_id,
                source_name=source_name,
            )
        )

    return effect


def _choose_mana_color(
    game: "Game",
    player: str,
    ability: AbilityOnStack,
    options: tuple[Color, ...],
    prompt: str,
) -> Color:
    """One mana a resolving triggered mana ability adds, of a colour or type
    the player adding it chooses (CR 608.2d).

    A payment's solver may already have picked it (`Game.take_mana_color_hint`),
    the way it picks a dual land's colour; a single option needs no question.
    """
    hinted = game.take_mana_color_hint(options)
    if hinted is not None:
        return hinted
    if len(options) == 1:
        return options[0]
    value = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=player,
            prompt=prompt,
            source=ability.source_name,
            options=tuple(color.value for color in options),
            source_id=source_id_of(ability),
        )
    )
    assert isinstance(value, str)
    return Color(value)


#: "<discard or mill>. If you discarded a <quality> card this way, <effect>." /
#: "... If at least one <quality> card is milled this way, <effect>." - an
#: instruction gated on what the sentence before it moved, with an optional
#: "Otherwise, <effect>." else-branch (CR 608.2c: later text modifying the
#: meaning of earlier text) for when it did not:
#:
#:   Vohar, Vodalian Desecrator    "Draw a card, then discard a card. If you
#:                                 discarded an instant or sorcery card this
#:                                 way, each opponent loses 1 life and you gain
#:                                 1 life."
#:   Liliana, Untouched by Death   "Mill three cards. If at least one Zombie
#:                                 card is milled this way, each opponent loses
#:                                 2 life and you gain 2 life."
#:   Lorehold Excavation           "At the beginning of your end step, mill a
#:                                 card. If a land card was milled this way,
#:                                 you gain 1 life. Otherwise, this enchantment
#:                                 deals 1 damage to each opponent."
#:
#: "This way" is anaphora for the cards the first sentence itself moved (CR
#: 701.17c: a milled card is found in the zone it moved to), so the reader
#: watches the controller's graveyard and exile across that one sentence
#: rather than trusting a count. `rest` is non-greedy specifically so it stops
#: before a trailing "Otherwise, ..." sentence rather than swallowing it -
#: without that, `rest` and `otherwise` are handed to `_ability_effect_or_
#: notice` as one ordinary multi-sentence clause, whose bare-period split
#: quietly drops whichever half no per-clause parser reads instead of
#: refusing the whole paragraph, so the else-branch never runs and never even
#: shows as a notice (found on Lorehold Excavation by `support.ignored_
#: rider`'s ablation probe).
_THEN_IF_MOVED_THIS_WAY_RE = re.compile(
    r"^(?P<prefix>.+?\.)\s*if (?:you (?P<verb_you>discarded|milled) (?:an?|one or more) "
    r"(?P<quality_you>[a-z ,'-]+?) cards? this way"
    r"|(?:at least one|an?|one or more) (?P<quality>[a-z ,'-]+?) cards? "
    r"(?:is|was|are|were) (?P<verb>discarded|milled) this way), (?P<rest>.+?)\."
    r"(?:\s*otherwise,\s*(?P<otherwise>.+?)\.?)?$",
    re.IGNORECASE | re.DOTALL,
)


def _moved_quality_understood(quality: str) -> bool:
    """Whether every word of a "<quality> card" phrase is one this engine can
    check: a card type, supertype, subtype or colour, "or"/"and", or a
    "non"-negation of one of those."""
    known = (
        {kind.value.lower() for kind in Type}
        | {supertype.value.lower() for supertype in Supertype}
        | {color.name.lower() for color in Color}
        | {"or", "and", "colorless", "multicolored", "monocolored"}
        | {word.lower() for word in subtype_vocabulary()}
    )
    words = [word for word in re.split(r"[\s,]+", quality.lower()) if word]
    return bool(words) and all(
        word in known
        or (word.startswith("non") and word.removeprefix("non-").removeprefix("non") in known)
        for word in words
    )


@ABILITY_TEXT.rung("s43")
def _parse_then_if_moved_this_way_clause(text: str) -> AbilityEffect | None:
    """`_THEN_IF_MOVED_THIS_WAY_RE`'s shape - the first sentence runs, then
    exactly one of `rest` / an optional "Otherwise, ..." branch runs,
    depending on whether any card it moved to the controller's graveyard (or
    exile, where a replacement sent it) matches the quality (CR 608.2c). A
    leading sentence that is not a discard or a mill, a quality this engine
    cannot check, or an unreadable branch leaves the whole paragraph unread."""
    match = _THEN_IF_MOVED_THIS_WAY_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    verb = (match.group("verb_you") or match.group("verb") or "").lower()
    quality = (match.group("quality_you") or match.group("quality") or "").strip()
    prefix_text = match.group("prefix").strip()
    if not re.search(r"\b(?:discard|mill)s?\b", prefix_text, re.IGNORECASE):
        return None
    if verb == "discarded" and not re.search(r"\bdiscard", prefix_text, re.IGNORECASE):
        return None
    if verb == "milled" and not re.search(r"\bmill", prefix_text, re.IGNORECASE):
        return None
    if not _moved_quality_understood(quality):
        return None
    leading = _ability_effect_or_notice(prefix_text)
    rest = _ability_effect_or_notice(match.group("rest").strip())
    otherwise_text = match.group("otherwise")
    otherwise = _ability_effect_or_notice(otherwise_text.strip()) if otherwise_text else None
    if leading is None or rest is None or (otherwise_text is not None and otherwise is None):
        return None
    for part in (leading, rest, otherwise):
        if part is not None and getattr(part, "__name__", "").endswith("notice_only"):
            return part
    matches = _quality_matcher(quality)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)

        def public_objects() -> set[tuple[UUID, UUID]]:
            return {
                (card.id, card.zone_change_stamp)
                for card in [*controller.graveyard, *game.exile]
                if (card.owner or controller.username) == controller.username
            }

        before = public_objects()
        leading(game, ability)
        moved = [
            card
            for card in [*controller.graveyard, *game.exile]
            if (card.id, card.zone_change_stamp) not in before
            and (card.owner or controller.username) == controller.username
        ]
        if any(matches(card) for card in moved):
            rest(game, ability)
        elif otherwise is not None:
            otherwise(game, ability)

    return effect


#: Ajani, Nacatl Avenger's `−4`: "Each opponent chooses an artifact, a
#: creature, an enchantment, and a planeswalker from among the nonland
#: permanents they control, then sacrifices the rest." A "choose one of each
#: of N types, sacrifice everything else" shape, generalised on the type list
#: rather than keyed to this one card - any future ability phrasing the
#: identical sentence with a different mix of types reads the same way.
_EACH_OPPONENT_CHOOSE_ONE_OF_EACH_TYPE_THEN_SACRIFICE_RE = re.compile(
    r"^each opponent chooses (?P<phrase>.+) from among the nonland permanents "
    r"they control, then sacrifices the rest\.?$",
    re.IGNORECASE,
)
#: One item of the comma/"and"-separated list: "an artifact", "a creature".
_TYPE_ITEM_RE = re.compile(r"^an?\s+(?P<type>[a-z]+)$", re.IGNORECASE)


@ABILITY_TEXT.rung("s16")
def _parse_each_opponent_choose_one_of_each_type_then_sacrifice(
    text: str,
) -> AbilityEffect | None:
    """See `_EACH_OPPONENT_CHOOSE_ONE_OF_EACH_TYPE_THEN_SACRIFICE_RE`.

    CR 101.4/601.7a-style "each opponent" choices are each that opponent's
    own (not Ajani's controller's) - `Decision.player=opponent.username` for
    every question this asks, one `CHOOSE_CARDS` per type per opponent, over
    that opponent's *own* nonland permanents. A permanent already claimed for
    an earlier type in the list cannot be claimed again (CR 601.2c's "the same
    target can't be chosen multiple times" logic, applied to a choice rather
    than a target): a creature that is also, say, an artifact could otherwise
    be "kept" twice and let one more permanent slip past the sacrifice.

    An opponent controls zero of a given type keeps nothing of that type
    (CR 107.1a: there is no zero-permanent "artifact" to choose) - the
    question is not even asked, rather than raising or defaulting to some
    other permanent. Everything that ends up unclaimed is then sacrificed
    (CR 701.21a), each by its own controller, in one batch per opponent -
    APNAP order (CR 101.4) is not relevant to what any one opponent's own
    sacrifice contains, only to the order the opponents are asked in, which
    this reads off `game.players_in_game`'s existing turn order.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _EACH_OPPONENT_CHOOSE_ONE_OF_EACH_TYPE_THEN_SACRIFICE_RE.fullmatch(whole)
    if match is None:
        return None
    items = [
        item.strip()
        for item in re.split(r",\s*(?:and\s+)?|\s+and\s+", match.group("phrase"))
        if item.strip()
    ]
    if not items:
        return None
    types: list[Type] = []
    for item in items:
        item_match = _TYPE_ITEM_RE.match(item)
        if item_match is None:
            return None
        try:
            types.append(Type(item_match.group("type").lower()))
        except ValueError:
            return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for opponent in _opponents(game, ability.controller):
            nonland = computed_permanents(
                game,
                game.permanents_controlled_by(opponent.username),
                lambda chars: Type.LAND not in chars.types,
            )
            keep: set[UUID] = set()
            for card_type in types:
                candidates = [
                    permanent
                    for permanent in computed_permanents(
                        game,
                        nonland,
                        lambda chars, wanted=card_type: wanted in chars.types,
                    )
                    if permanent.id not in keep
                ]
                if not candidates:
                    # CR 107.1a: no such permanent to choose, so none of this
                    # type is kept - not a required-but-unmet choice.
                    continue
                article = "an" if card_type.value[0] in "aeiou" else "a"
                decision = Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=opponent.username,
                    prompt=f"choose {article} {card_type.value} to keep",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                )
                chosen_ids = game.ask(decision)
                keep.add(chosen_ids[0])
            for permanent in nonland:
                if permanent.id in keep:
                    continue
                if permanent.zone is Zone.BATTLEFIELD:
                    game.sacrifice(permanent)

    return effect


#: Thanos, the Mad Titan's own power-up effect: "Put two +1/+1 counters on
#: Thanos. Choose odd or even. Destroy each other creature with mana value
#: of the chosen quality." `pre` is whatever ordinary CR 608.2c instruction
#: (or instructions) comes before the choose/destroy pair - Thanos's own
#: counter placement, read the same "any number of earlier clauses" way
#: `_COUNTER_THRESHOLD_RE`'s own `pre` group already is - so this reads on
#: its own even for a future printing with no leading clause at all.
#:
#: The choice itself is CR 608.2d's, made as the ability resolves - not CR
#: 614.12a's "as [this] enters" choice `replacement.py::ChoiceKind.ODD_OR_
#: EVEN`/`CardState.choice` is built for (Gollum, Riddle Master's own "As
#: Gollum enters, choose odd or even.") - so the answer is read straight
#: back rather than stashed on the permanent; nothing later in this same
#: ability needs to ask "the chosen quality" a second time. "Other" is CR
#: 109.2's exclusion of the ability's own source, spelled out here rather
#: than reused from `_parse_mass_destroy_predicate` (`_DESTROY_EACH_RE`'s
#: own qualifier grammar has no "other" of its own to strip).
_CHOOSE_ODD_OR_EVEN_THEN_DESTROY_RE = re.compile(
    r"^(?P<pre>(?:[^.]+\.\s+)*?)"
    r"choose odd or even\.\s*"
    r"destroy each other (?P<qualifier>.+?) with mana value of the chosen quality\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_choose_odd_or_even_then_destroy_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CHOOSE_ODD_OR_EVEN_THEN_DESTROY_RE`'s shape - see its own docstring.

    `qualifier` reuses `_parse_mass_type_qualifier` - the same card-type-list
    reading `_parse_destroy_each_clause` already draws on - so "creature" is
    read generally, not hardcoded to Thanos's own printing.
    """
    match = _CHOOSE_ODD_OR_EVEN_THEN_DESTROY_RE.fullmatch(text.strip())
    if match is None:
        return None
    pre_text = match.group("pre").strip()
    pre = _parse_mixed_clauses(pre_text, for_spell=for_spell) if pre_text else []
    if pre is None:
        return None
    type_predicate = _parse_mass_type_qualifier(match.group("qualifier").strip())
    if type_predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for clause in pre:
            clause(game, stack_object)
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        controller = game.controller_of(stack_object)
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        decision = Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=controller.username,
            prompt="choose odd or even",
            source=source_name,
            source_id=source_id_of(stack_object),
            options=("odd", "even"),
            quality=ChoiceKind.ODD_OR_EVEN.value,
        )
        answer = game.ask(decision)
        assert isinstance(answer, str)
        wants_even = answer.lower() == "even"

        def predicate(
            game: "Game", permanent: CardState, src: CardState | None, x_value: int | None = None
        ) -> bool:
            if src is not None and permanent.id == src.id:
                return False  # CR 109.2: "other" excludes the ability's own source.
            chars = game.characteristics_of(permanent)
            if not type_predicate(chars):
                return False
            return (int(chars.mana_value) % 2 == 0) == wants_even

        _destroy_matching(game, predicate, source)

    return effect


#: Super-Adaptoid's own "enters or attacks" trigger: "choose another target
#: creature. If that creature has haste and this permanent doesn't, put a
#: haste counter on this permanent. Do the same for flying, first strike,
#: double strike, deathtouch, indestructible, lifelink, menace, reach,
#: trample, and vigilance." - CR 603.3d's targeted triggered ability
#: (targeted the same way Icy Manipulator's activated "Tap target artifact,
#: creature, or land." is, just printed inside the effect text rather than
#: the condition), then one CR 122.1b keyword-counter grant (this module's
#: own `_counter_kind`, `Game.add_counters`) per keyword the comparison
#: creature has and this one does not - "haste" first, "Do the same for
#: `<list>`" repeating the identical comparison for every keyword the list
#: names. The list is read generally, not hardcoded to the ten this card
#: happens to print, so a future printing naming a different (CR 122.1b-
#: legal) subset reads the same way.
_CHOOSE_CREATURE_COPY_KEYWORDS_RE = re.compile(
    r"^choose another target creature\.\s*"
    r"if that creature has (?P<first>[a-z]+(?: [a-z]+)?) and this permanent doesn'?t, "
    r"put an? (?P=first) counter on this permanent\.\s*"
    r"do the same for (?P<rest>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_choose_creature_copy_keywords_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CHOOSE_CREATURE_COPY_KEYWORDS_RE`'s shape - see its own docstring.
    Ability-only: "this permanent" names a permanent (CR 122.1), the same
    restriction every self-counter reader in this file already draws.
    """
    if for_spell:
        return None
    match = _CHOOSE_CREATURE_COPY_KEYWORDS_RE.fullmatch(text.strip())
    if match is None:
        return None
    keywords = [match.group("first").strip().lower()]
    for word in _MASS_TYPE_JOIN_RE.sub(", ", match.group("rest")).split(","):
        word = word.strip().lower()
        if word:
            keywords.append(word)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        target = next(
            (
                found
                for found in game.resolve_targets(ability)
                if isinstance(found, CardState) and found.zone is Zone.BATTLEFIELD
            ),
            None,
        )
        if target is None:
            return
        for keyword in keywords:
            if has_keyword(target, keyword, game) and not has_keyword(source, keyword, game):
                game.add_counters(source, keyword, 1)

    return effect


#: "Any player may `<action>`. If a player does, counter this permanent."
#: (CR 603.2, 601.2i, 113.6k - a `TriggerEvent.CAST_SPELL` trigger, printed
#: before `_self_normalized_effect_text` rewrites "Dash Hopes"/"Temporal
#: Extortion"/"Brain Gorgers"/"Phantasmagorian" to CR 700.7's own "this
#: permanent") - the punisher template: Dash Hopes' "pay 5 life", Temporal
#: Extortion's "pay half their life, rounded up", Brain Gorgers' "sacrifice a
#: creature of their choice", Phantasmagorian's "discard three cards".
#:
#: The Oracle rulings for these cards (all four print the identical two
#: rulings, verified against Scryfall's own rulings text this session) say
#: the offer is CR 101.4's APNAP order - the active player first, then each
#: other player in turn order - and, unlike a plain "unless" cost
#: (`_counter_unless_pays_effect`), **every remaining player still gets the
#: option even after an earlier one has already paid**: "As soon as any
#: player performs the action, the spell is countered, but the remaining
#: players still get the option. If all players decline, the spell remains
#: on the stack." So this asks every player in turn, never stopping early,
#: and counters (CR 701.6a) the moment the first one pays - a later "yes"
#: still pays its own cost (CR 608.2d: a real, asked choice), it just finds
#: nothing left on the stack to counter (Hope-Ender Coatl's own ruling: the
#: trigger "will still resolve as normal" even once its spell is already
#: gone).
_ANY_PLAYER_MAY_PUNISHER_RE = re.compile(
    r"^any player may (?P<action>.+?)\.\s*if a player does,\s*"
    r"counter (?:this permanent|this spell)\.?$",
    re.IGNORECASE | re.DOTALL,
)
#: "pay `<n>` life" - Dash Hopes.
_PUNISHER_PAY_LIFE_RE = re.compile(r"^pay (?P<n>\d+) life$", re.IGNORECASE)
#: "pay half `<their|his|her|your>` life, rounded `<up|down>`" - Temporal
#: Extortion. CR 107.1a: the card states the rounding direction itself, and
#: `halve` (`machines/numbers.py`) is the identical reader `_parse_half_life_
#: loss_clause` already uses for "loses half their life, rounded up" - the
#: same fraction, read for a payment offer rather than an unconditional loss.
#: Always payable (CR 119.4b: "players can always pay 0 life", and half of
#: any life total rounded up is never more than that total), so unlike a flat
#: `_PUNISHER_PAY_LIFE_RE` amount this one never has a player who "cannot
#: perform the action".
_PUNISHER_PAY_HALF_LIFE_RE = re.compile(
    r"^pay half (?:their|his|her|your) life,\s*rounded (?P<direction>up|down)$", re.IGNORECASE
)
#: "sacrifice a[n] `<description>` of `<their|his|her|your>` choice" - Brain
#: Gorgers' own "a creature of their choice" (CR 701.21a's own chooser
#: language), read the same `permanent_description` any other sacrifice-of-
#: choice clause in this file already does.
_PUNISHER_SACRIFICE_RE = re.compile(
    r"^sacrifice an? (?P<description>[a-z][a-z' ]*?) of (?:their|his|her|your) choice$",
    re.IGNORECASE,
)
#: "discard `<n>` cards" - Phantasmagorian.
_PUNISHER_DISCARD_RE = re.compile(rf"^discard (?P<n>{COUNT}) cards?$", re.IGNORECASE)


def _parse_punisher_action(
    action_text: str,
) -> Callable[["Game", Player, str, str | None], bool] | None:
    """One player's own half of `_ANY_PLAYER_MAY_PUNISHER_RE`'s "any player
    may `<action>`" - a function of `(game, player, source, source_id)` that
    asks *this* player CR 608.2d's choice and returns whether they actually
    performed it, or `None` when `action_text` is not a shape this reads.

    Every verb reuses the identical reader this file already has for the
    same action elsewhere - `Game.may_pay_life` (CR 119.4, CR 608.2d;
    `halve` for the half-life shape), `_sacrifice_of_choice_clause_effect`
    (CR 701.21a), `_discard_cards` (CR 701.9a/701.9b) - rather than a new
    per-verb reader: only the *outer* MAY/ability-to-choose-at-all wrapper
    and the reversed consequence (paying causes the counter here, rather
    than avoiding one) are new.

    CR 608.2d offers no impossible choice: sacrifice and discard are never
    even asked of a player who cannot perform them (no matching permanent;
    fewer cards in hand than the printed count - the 2013-07-01 Oracle
    ruling's own example, verified against Scryfall's rulings text this
    session, is exactly this discard case). `may_pay_life` already refuses
    the affirmative itself when the payer's life total is too low, so the
    fixed-amount life shape needs no separate ability check here.
    """
    text = action_text.strip()

    if match := _PUNISHER_PAY_LIFE_RE.fullmatch(text):
        amount = int(match.group("n"))

        def pay_fixed_life(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> bool:
            return game.may_pay_life(player, amount, source=source, source_id=source_id)

        return pay_fixed_life

    if match := _PUNISHER_PAY_HALF_LIFE_RE.fullmatch(text):
        round_up = match.group("direction").lower() == "up"

        def pay_half_life(game: "Game", player: Player, source: str, source_id: str | None) -> bool:
            amount = halve(player.life, round_up=round_up)
            return game.may_pay_life(player, amount, source=source, source_id=source_id)

        return pay_half_life

    if match := _PUNISHER_SACRIFICE_RE.fullmatch(text):
        description = match.group("description").strip()
        requirement = permanent_description(description)
        if requirement is None:
            return None
        wanted_words = with_indefinite_article(description)
        sacrifice_of_choice = _sacrifice_of_choice_clause_effect(description, 1, wanted_words)

        def sacrifice_choice(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> bool:
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if requirement.rejects(permanent, player.username, game) is None
            ]
            if not candidates:
                return False
            if not game.may(
                player,
                f"sacrifice {wanted_words} rather than let {source} resolve",
                source=source,
                source_id=source_id,
            ):
                return False
            sacrifice_of_choice(game, player, source, source_id)
            return True

        return sacrifice_choice

    if match := _PUNISHER_DISCARD_RE.fullmatch(text):
        count = parse_count(match.group("n"))
        if count is None or count < 1:
            return None

        def discard_choice(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> bool:
            if len(player.hand) < count:
                return False
            if not game.may(
                player,
                f"discard {count} card(s) rather than let {source} resolve",
                source=source,
                source_id=source_id,
            ):
                return False
            _discard_cards(game, player, count, source, source_id=source_id, exact=True)
            return True

        return discard_choice

    return None


@ABILITY_TEXT.rung("s7")
def _parse_any_player_may_punisher_clause(text: str) -> AbilityEffect | None:
    """`_ANY_PLAYER_MAY_PUNISHER_RE`'s shape, or `None`."""
    match = _ANY_PLAYER_MAY_PUNISHER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    offer = _parse_punisher_action(match.group("action").strip())
    if offer is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for player in _players_in_apnap_order(game):
            performed = offer(game, player, ability.source_name, source_id_of(ability))
            if not performed:
                continue
            spell = next((item for item in game.stack if item.id == ability.source_id), None)
            if spell is not None:
                game.counter(spell)

    return effect


#: "Choose two target creatures controlled by different players. Return those
#: creatures to their owners' hands." - Run Away Together, and the "choose N
#: target ... / do something to those ..." shape generally.
#:
#: Two sentences, one CR 608.2c instruction pair. The second sentence has no
#: "target" word in it at all: "those creatures" is CR 400.7 anaphora back to
#: whatever the first sentence chose, so neither half is readable alone -
#: `machines/targeting.py` reads the restriction off the *first* sentence, and
#: only the second says what happens. The first sentence's whole "N target ..."
#: phrase is handed to `_targets_understood` exactly as it is printed, count
#: words included, so the parser here never re-derives the restriction
#: ("controlled by different players" is `TargetRequirement.distinct_
#: controllers`, enforced at announcement by CR 601.2c and rechecked at
#: resolution by CR 608.2b, both in `machines/targeting.py`).
_CHOOSE_TARGETS_THEN_RETURN_TO_HAND_RE = re.compile(
    r"^choose (?P<phrase>\w+ target .+?)\.\s*"
    r"return those \w+ to their owners'? hands\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s12")
def _parse_choose_targets_then_return_to_hand_pair(text: str) -> Effect | None:
    """`_CHOOSE_TARGETS_THEN_RETURN_TO_HAND_RE`'s shape - Run Away Together.

    The point of the card, and the reason DDR#995 is about it, is what happens
    when one of the two chosen creatures is gone by the time the spell
    resolves. CR 608.2b: "If the spell or ability specifies targets, it checks
    whether the targets are still legal. A target that's no longer in the zone
    it was in when it was targeted is illegal ... If all its targets, for every
    instance of the word 'target,' are now illegal, the spell or ability
    doesn't resolve." One of two is not all of them, so the spell resolves and
    the survivor is bounced; `Game.resolve_targets` performs exactly that
    recheck and simply does not yield the target `legal_target` now rejects,
    which is what makes the sacrificed creature silently dropped rather than
    an error. CR 608.3b applies the identical check to an ability of this
    shape.

    CR 400.3 is why the destination is the *owner's* hand and not the
    controller's: "If an object would go to any library, graveyard, or hand
    other than its owner's, it goes to its owner's corresponding zone."
    `Game.return_to_hand` already obeys it, so "their owners' hands" needs no
    handling of its own here.
    """
    match = _CHOOSE_TARGETS_THEN_RETURN_TO_HAND_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for target in game.resolve_targets(spell):
                if isinstance(target, CardState):
                    game.return_to_hand(target)

    return effect


#: "Choose target `<phrase>`. Return it to your hand." - Night Nurse, Healer
#: of Heroes's own ETB, the singular twin of `_CHOOSE_TARGETS_THEN_RETURN_
#: TO_HAND_RE` just above: one chosen object, returned to the *controller's*
#: own hand (not necessarily the owner's - Night Nurse's own zone
#: restriction already confines the choice to "your graveyard", so the
#: controller and owner are the same card either way, but the sentence
#: itself says "your hand", not "its owner's hand", so it is read that way
#: rather than reused as a special case of the plural owner's-hand shape).
_CHOOSE_TARGET_THEN_RETURN_TO_YOUR_HAND_RE = re.compile(
    r"^choose (?P<phrase>target .+?)\.\s*return it to your hand\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s9")
def _parse_choose_target_then_return_to_your_hand_pair(text: str) -> AbilityEffect | None:
    """`_CHOOSE_TARGET_THEN_RETURN_TO_YOUR_HAND_RE`'s shape, or `None`.

    Ability-only: no printing in the pool has a spell choose a target this
    way rather than targeting directly, and `game.controller_of` needs a
    resolving ability or permanent, not a bare spell on the stack.
    """
    match = _CHOOSE_TARGET_THEN_RETURN_TO_YOUR_HAND_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                game.return_to_hand(target)

    return effect


#: "Choose target `<type>`. Create N tokens that are copies of it[, except
#: ...]." - Rebuild the City's own whole text: "Choose target land. Create
#: three tokens that are copies of it, except they're 3/3 creatures in
#: addition to their other types and they have vigilance and menace." Two
#: sentences, one CR 608.2c instruction pair, the same shape
#: `_CHOOSE_TARGETS_THEN_RETURN_TO_HAND_RE` just above reads for "those
#: creatures" - except here the second sentence's pronoun is singular ("it"),
#: because the first sentence names exactly one target and the effect that
#: follows never moves or destroys it, only reads it as the thing to copy.
_CHOOSE_TARGET_THEN_CREATE_TOKEN_COPIES_RE = re.compile(
    rf"^choose (?P<phrase>target .+?)\.\s*"
    rf"create {count_pattern('count')} tokens? that (?:are copies|'?s a copy|is a copy) of it"
    r"(?:, except (?P<except>.+))?\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s12")
def _parse_choose_target_then_create_token_copies_pair(text: str) -> Effect | None:
    """`_CHOOSE_TARGET_THEN_CREATE_TOKEN_COPIES_RE`'s shape - Rebuild the
    City.

    "It" is CR 607.1 anaphora back to the first sentence's own chosen target,
    not a second "target" word of its own: the whole text carries exactly one
    "target" (in "choose target land"), and `machines/targeting.py` builds its
    CR 601.2c requirement off the *printed* text as a whole, not per split
    clause - so by the time this effect runs, `game.resolve_targets` already
    has the very land the first sentence named, with nothing left for this
    sentence to announce. The exception tail is CR 707.9's own channel, read
    exactly as `_parse_create_token_copies_except_clause` reads it.
    """
    match = _CHOOSE_TARGET_THEN_CREATE_TOKEN_COPIES_RE.fullmatch(" ".join(text.split()))
    if match is None:
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

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState):
                token_copy_of(
                    game,
                    target,
                    controller.username,
                    count=count,
                    added_abilities=added,
                    power=power,
                    toughness=toughness,
                    added_creature_type=added_type,
                )

    return effect


#: "<instruction>. If you have the city's blessing, <instruction> instead." -
#: Secrets of the Golden City's "Draw two cards. If you have the city's
#: blessing, draw three cards instead." The city's blessing (CR 702.131c) is a
#: designation on the player, read off `Player.has_citys_blessing` as the
#: spell resolves - after CR 702.131a's own ascend instruction has already
#: been followed (`Game._resolve_top`), which is what lets the blessing that
#: very spell granted count. Both halves are read by `parse_clause_effect`,
#: so any plain player instruction it reads (a draw, a life change, a mill,
#: a scry, ...) takes this shape, not only a draw; an instruction it cannot
#: read on either side leaves the whole text unread rather than half-run
#: (CR 608.2c).
_CITYS_BLESSING_INSTEAD_RE = re.compile(
    r"^(?P<base>[^.]+)\.\s*if you have the city(?:'|\u2019)s blessing,\s*"
    r"(?P<blessed>[^.]+?)\s+instead\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s14", before=["modal._parse_condition_instead_clause"])
def _parse_citys_blessing_instead_clause(effect_text: str) -> Effect | None:
    """`_CITYS_BLESSING_INSTEAD_RE`'s shape, or `None`."""
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _CITYS_BLESSING_INSTEAD_RE.fullmatch(whole)
    if match is None:
        return None
    base = parse_clause_effect(match.group("base"))
    blessed = parse_clause_effect(match.group("blessed"))
    if base is None or blessed is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        chosen = blessed if controller.has_citys_blessing else base
        chosen(game, controller, spell.name, source_id_of(spell))

    return effect


#: Into the Flood Maw: "Return target creature an opponent controls to its
#: owner's hand. If the gift was promised, instead return target nonland
#: permanent an opponent controls to its owner's hand." CR 702.174b/m's gift
#: keyword template, not this printing's name - any future gift card whose
#: replacement clause reads "If the gift was promised, instead return
#: target ... to its owner's hand." matches the same way. Read as one
#: CR 608.2c instruction, the same reasoning `_REVOLT_DESTROY_OR_EXILE_RE`
#: already uses for Fatal Push's Revolt line: the conditional half - *which*
#: candidate set a target had to satisfy - is enforced entirely by
#: `machines/targeting.py`'s own `TargetRequirement.if_gift_promised` /
#: `TargetingProfile.for_gift_promise` at CR 601.2c announcement, and by the
#: time this clause resolves that choice has already been made and checked.
#: Both branches print the identical verb ("return ... to its owner's
#: hand"), so there is nothing left for this effect to branch on at
#: resolution - it only has to recognise the two-sentence shape so the whole
#: ability is not thrown away as an unreadable second sentence.
_GIFT_PROMISED_RETURN_INSTEAD_RE = re.compile(
    r"^return (?P<phrase>target .+?) to (?:its owner'?s hand|their owners'? hands)\."
    r"\s*if the gift was promised,\s*instead return (?P<promised_phrase>target .+?) to "
    r"(?:its owner'?s hand|their owners'? hands)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s14")
def _parse_gift_promised_return_instead_clause(effect_text: str) -> Effect | None:
    """`_GIFT_PROMISED_RETURN_INSTEAD_RE`'s shape, or `None` if this is not it.

    Both phrases are read through `_targets_understood` - the not-promised
    one because it is what `return_ability_targets_to_hand` actually acts on,
    and the promised one so a shape this wave cannot read (an unenforced
    trailing condition, a phrase naming a player) fails the whole clause
    closed rather than silently accepting a replacement effect nobody
    checked.
    """
    match = _GIFT_PROMISED_RETURN_INSTEAD_RE.fullmatch(effect_text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    if not _targets_understood(
        match.group("promised_phrase"), count_agnostic=True, battlefield_only=False
    ):
        return None
    return return_ability_targets_to_hand


#: "If it's a `<quality>` card, `<rider>`." - a second sentence whose "it" is
#: the card the first sentence's own target named: Tamiyo, Seasoned Scholar's
#: -3 ("Return target instant or sorcery card from your graveyard to your
#: hand. If it's a green card, add one mana of any color.") and Cemetery
#: Recruitment ("Return target creature card from your graveyard to your
#: hand. If it's a Zombie card, draw a card.").
_IF_ITS_A_QUALITY_CARD_RIDER_RE = re.compile(
    r"^if it'?s an? (?P<quality>[^,]+?) card, (?P<rider>.+?)\.?$", re.IGNORECASE
)


def _ability_only_rider(text: str) -> TargetedClause | None:
    """A rider only an ability can carry: "add one mana of any color"
    (`_parse_add_one_mana_of_any_color_trigger`), which reads the resolving
    `AbilityOnStack`'s own controller and source."""
    add_mana = _parse_add_one_mana_of_any_color_trigger(text)
    if add_mana is None:
        return None

    def rider(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        add_mana(game, stack_object)

    return rider


def _parse_if_target_card_quality_rider_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """`<antecedent naming target card>`. If it's a `<quality>` card, `<rider>`.

    One CR 608.2c instruction: the antecedent runs, then the rider runs if
    the targeted card has the quality. The quality is read **before** the
    antecedent moves the card: returning it to a hand takes it from a public
    zone to a hidden one, and CR 608.2h says "if the effect has moved it from
    a public zone to a hidden zone, the effect uses the object's last known
    information". With no legal target left the ability never resolves at
    all (CR 608.2b), so neither sentence happens.

    The quality is `_nonland_or_typed_card_matcher`'s vocabulary (a colour, a
    card type, a subtype - a changeling is every creature type, CR 702.73a);
    the rider is whatever `_parse_mixed_clause` already reads ("draw a card"),
    or, on an ability, `_parse_add_one_mana_of_any_color_trigger`'s "add one
    mana of any color". Either half unreadable refuses the pair.
    """
    match = _IF_ITS_A_QUALITY_CARD_RIDER_RE.fullmatch(second.strip())
    if match is None or "target" not in first.lower():
        return None
    matches_quality = _nonland_or_typed_card_matcher(match.group("quality"))
    if matches_quality is None:
        return None
    antecedent = _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        return None
    rider_text = match.group("rider").strip()
    rider = _parse_mixed_clause(rider_text, for_spell=for_spell)
    if rider is None and not for_spell:
        rider = _ability_only_rider(rider_text)
    if rider is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        qualifies = any(matches_quality(card) for card in referents)
        antecedent(game, stack_object)
        if qualifies:
            rider(game, stack_object)

    return effect


#: "If it was a `<quality>` card, `<A>`." / "Otherwise, `<B>`." - the two
#: sentences after an instruction that moved a target card, looking back at
#: it: Cling to Dust ("Exile target card from a graveyard. If it was a
#: creature card, you gain 3 life. Otherwise, you draw a card.") and Klothys,
#: God of Destiny's first-main-phase trigger ("... If it was a land card, add
#: {R} or {G}. Otherwise, you gain 2 life and Klothys deals 2 damage to each
#: opponent.").
_IF_IT_WAS_A_QUALITY_CARD_RE = re.compile(
    r"^if it was an? (?P<quality>[^,]+?) card, (?P<then>.+?)\.?$", re.IGNORECASE
)
_OTHERWISE_BRANCH_RE = re.compile(r"^otherwise, (?P<otherwise>.+?)\.?$", re.IGNORECASE)


def _if_it_was_branch(text: str, *, for_spell: bool) -> TargetedClause | None:
    """One branch of `_parse_if_it_was_quality_card_otherwise_triple`, read
    whole (a branch may itself be several instructions joined by "and")."""
    branch = parse_mixed_effect_for_spell(text) if for_spell else parse_mixed_effect(text)
    if branch is not None:
        return branch  # type: ignore[return-value]
    if for_spell:
        return None
    return _parse_add_one_of_listed_mana_clause(text)


def _parse_if_it_was_quality_card_otherwise_triple(
    first: str, second: str, third: str, *, for_spell: bool
) -> TargetedClause | None:
    """`<antecedent naming target card>`. If it was a `<quality>` card, `<A>`.
    Otherwise, `<B>`.

    One CR 608.2c instruction: the antecedent runs, then exactly one branch.
    "It was" is the card the antecedent acted on, as it was before the move:
    CR 608.2h - "if it's no longer in that zone, or if the effect has moved
    it from a public zone to a hidden zone, the effect uses the object's last
    known information" - so the quality is read before the antecedent runs,
    once. With its target illegal the spell or ability does not resolve at
    all (CR 608.2b), and neither branch runs.

    The quality is `_nonland_or_typed_card_matcher`'s vocabulary; each branch
    is whatever `parse_mixed_effect(_for_spell)` reads, or, on an ability,
    "add {X} or {Y}" (`_parse_add_one_of_listed_mana_clause`). Any part
    unreadable refuses the whole triple.
    """
    condition = _IF_IT_WAS_A_QUALITY_CARD_RE.fullmatch(second.strip())
    otherwise = _OTHERWISE_BRANCH_RE.fullmatch(third.strip())
    if condition is None or otherwise is None or "target" not in first.lower():
        return None
    matches_quality = _nonland_or_typed_card_matcher(condition.group("quality"))
    if matches_quality is None:
        return None
    antecedent = _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        return None
    then_branch = _if_it_was_branch(condition.group("then").strip(), for_spell=for_spell)
    else_branch = _if_it_was_branch(otherwise.group("otherwise").strip(), for_spell=for_spell)
    if then_branch is None or else_branch is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not referents:
            return
        qualifies = any(matches_quality(card) for card in referents)
        antecedent(game, stack_object)
        (then_branch if qualifies else else_branch)(game, stack_object)

    return effect


def _parse_if_it_was_target_card_quality_rider_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """`<antecedent naming target card>`. If it was a `<quality>` card,
    `<rider>`. - `_parse_if_target_card_quality_rider_clause_pair`'s own
    past-tense twin, for an antecedent that has already moved its target out
    of the zone that named it (so the card is described as it "was" rather
    than as it presently "is") but prints no "Otherwise" branch at all -
    General's Enforcer's own "{2}{W}{B}: Exile target card from a graveyard.
    If it was a creature card, create a 1/1 white Human Soldier creature
    token." (verified Pioneer/Modern legal by Scryfall search) is the proof
    printing for Invasion of Innistrad // Deluge of the Dead's identically
    shaped "{2}{B}: Exile target card from a graveyard. If it was a creature
    card, create a 2/2 black Zombie creature token." - same verb, same
    "if it was" reading, a different token.

    CR 608.2h: the quality is read off the target's own last known
    information, before the antecedent's own move (exiling it) takes it out
    of the zone that let it be targeted at all - the same ordering
    `_parse_if_target_card_quality_rider_clause_pair` and `_parse_if_it_was_
    quality_card_otherwise_triple` already both apply. With no legal target
    left (CR 608.2b) neither sentence runs.
    """
    match = _IF_IT_WAS_A_QUALITY_CARD_RE.fullmatch(second.strip())
    if match is None or "target" not in first.lower():
        return None
    matches_quality = _nonland_or_typed_card_matcher(match.group("quality"))
    if matches_quality is None:
        return None
    antecedent = _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        return None
    rider_text = match.group("then").strip()
    rider = _parse_mixed_clause(rider_text, for_spell=for_spell)
    if rider is None and not for_spell:
        rider = _ability_only_rider(rider_text)
    if rider is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        referents = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        qualifies = any(matches_quality(card) for card in referents)
        antecedent(game, stack_object)
        if qualifies:
            rider(game, stack_object)

    return effect


#: "Choose a <permanent description> you control." - an untargeted choice
#: (CR 115.10a: no "target", so shroud and hexproof never stop it) made while
#: the spell or ability resolves (CR 608.2d), whose object the next
#: sentence's "It" names. Final Showdown's "Choose a creature you control. It
#: gains indestructible until end of turn."; Crush Underfoot's "Choose a
#: Giant creature you control. It deals damage equal to its power to target
#: creature." The description is read by `machines/targeting.
#: permanent_description`, the same grammar every edict uses.
_CHOOSE_PERMANENT_YOU_CONTROL_RE = re.compile(
    r"^choose (?:a|an|one) (?P<description>.+?) you control$", re.IGNORECASE
)


def _parse_choose_then_object_anaphor_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Choose a `<description>` you control. It `<rider>`." as one CR 608.2c
    instruction: the controller chooses one matching permanent they control
    as it resolves (CR 608.2d), and the rider - any `_parse_referent_object_
    clause` reads - acts on it. Nothing to choose means nothing for "it" to
    name, so the rider does not run (CR 608.2d: an impossible choice is not
    made), and that is not an unread clause.
    """
    if not _OBJECT_ANAPHOR_RE.search(second):
        return None
    match = _CHOOSE_PERMANENT_YOU_CONTROL_RE.fullmatch(first.strip().rstrip(".").strip())
    if match is None:
        return None
    requirement = permanent_description(match.group("description"))
    if requirement is None:
        return None
    rider = _parse_referent_object_clause(second)
    if rider is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if requirement.rejects(permanent, controller.username, game) is None
        ]
        if not candidates:
            return
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        chosen = _choose_one_card(
            game,
            controller,
            candidates,
            prompt=f"choose a {match.group('description')} you control",
            source=source_name,
            source_id=source_id_of(stack_object),
        )
        rider(game, [chosen], stack_object)

    return effect


def _choose_permanents_to_sacrifice(
    game: "Game",
    player: Player,
    restriction: _SacrificeRestriction,
    candidates: list[CardState],
    *,
    source_name: str,
    source_id: str | None,
) -> list[CardState]:
    """Which of `candidates` the player sacrifices, once they have said yes
    to the "you may" (CR 608.2d): the ability's own source when that is the
    only one there is, or one `CHOOSE_CARDS` question asking for exactly the
    printed count - or, for a range, any count from its minimum up to every
    candidate. An answer below a range's minimum is not a payment and returns
    no permanents, so the caller does not run the "if/when you do" half.

    A permanent that "can't be sacrificed" (Alexios) is not offered (CR 101.2).
    """
    from ..attacking_statics import cant_be_sacrificed

    candidates = [c for c in candidates if cant_be_sacrificed(game, c) is None]
    if restriction.is_self:
        return candidates[:1]
    quantity = restriction.quantity
    exact = quantity.exact and quantity.amount is not None
    most = quantity.amount if exact else min(quantity.amount or len(candidates), len(candidates))
    fewest = most if exact else max(quantity.minimum or 0, 1)
    assert most is not None
    prompt = (
        "choose a permanent to sacrifice"
        if exact and most == 1
        else f"choose {most if exact else f'{fewest} to {most}'} permanents to sacrifice"
    )
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=prompt,
            source=source_name,
            amount=most,
            exact=exact,
            default_cards=None if exact else tuple(c.id for c in candidates[:fewest]),
            cards=tuple(candidate.id for candidate in candidates),
            source_id=source_id,
        )
    )
    assert isinstance(chosen_ids, tuple)
    if len(chosen_ids) < fewest:
        return []
    by_id = {candidate.id: candidate for candidate in candidates}
    return [by_id[card_id] for card_id in chosen_ids]


# --------------------------------------------------------------------------
# "You may sacrifice ... When you do, ..." (CR 603.12)
# --------------------------------------------------------------------------
#
# Verified this session with `knowledge_search(q="...", type="rules")`:
#
#   CR 603.12 - "A resolving spell or ability may allow or instruct a player
#   to take an action and create a triggered ability that triggers 'when [a
#   player] [does or doesn't]' take that action or 'when [something happens]
#   this way.' These reflexive triggered abilities follow the rules for
#   delayed triggered abilities (see rule 603.7), except that they're checked
#   immediately after being created and trigger based on whether the trigger
#   event or events occurred earlier during the resolution of the spell or
#   ability that created them."
#
#   CR 405.6a - "Effects don't go on the stack; they're the result of spells
#   and abilities resolving. Effects may create delayed triggered abilities,
#   however, and these may go on the stack when they trigger."
#
# This is the shape CR 118.12's "If you do" is often confused with, and the
# two resolve completely differently. "If you do" (`_parse_conditional_
# sacrifice_clause` above) reads: the consequence is *part of the same
# resolution*, no new stack object, no priority in between (CR 118.12's own
# "regardless of what events actually occurred" is about the cost, not a
# second object). "When you do" creates a *second*, independent triggered
# ability (CR 603.12) that goes on the stack of its own accord the next time
# a player would receive priority (CR 603.3) - which is exactly what lets an
# opponent respond to Grist's "When you do, destroy target creature or
# planeswalker" before it resolves, and exactly what CR 405.6a says an
# ordinary one-shot effect could never do on its own.
#
# Grist, the Hunger Tide's "−2: You may sacrifice a creature. When you do,
# destroy target creature or planeswalker." is the vehicle: sacrifice is
# already a modelled cost with a working `MAY` decision (`_sacrifice_
# restriction` above), so this reuses that and only adds what CR 603.12 adds
# on top - a second stack object, created (not resolved) here, whose own
# target is chosen when *it* goes on the stack (CR 603.3d), not now.
#
# Two traps this shape earns, both guarded against explicitly:
#
# - **The target must not be asked for here.** `machines/targeting.py`'s
#   `profile_for_text` is what `Game._ask_trigger_targets` and `Game.
#   activate_ability` read the *outer* ability's own targeting profile from,
#   and both hand it the ability's raw printed text - which still contains
#   the reflexive clause's "target creature or planeswalker" if nothing
#   strips it. `profile_for_text` now cuts everything from "when you do"
#   onward before parsing, so the outer ability (Grist's `-2`, Guide of
#   Souls' "Whenever you attack") is never asked to announce a target that
#   belongs to an ability that may never even be created (CR 603.3d).
# - **The cost stays paid on a fizzle.** The sacrifice happens here, inside
#   the *parent's* resolution, before the reflexive ability even exists;
#   `Game.create_reflexive_trigger` only ever queues it afterward. If the
#   reflexive ability's own target later becomes illegal (CR 608.2b), only
#   the reflexive ability's effect is skipped - there is no path back to
#   un-sacrifice the creature, because nothing here ever offers one.
#
# Only the "you may sacrifice" shape is read below. A mandatory action
# ("Create a token. When you do, ...", Ajani, Nacatl Avenger's `0`) or an
# optional action that is not a sacrifice ("you may pay {E}{E}{E}", Guide of
# Souls' attack trigger - blocked on there being no general may-pay-a-cost
# primitive at all, see `docs/engine-coverage.md`) is deliberately left
# unread rather than guessed at; `_unreadable_reflexive_clause` is what turns
# that refusal into a `ReflexiveClauseNotice` instead of the silent nothing
# both cards resolved to before this wave.

#: "You may sacrifice `<restriction>`. When you do, `<consequence>`." - the
#: same restriction shape `_MAY_SACRIFICE_IF_YOU_DO_RE` reads, with "when"
#: for "if" so the two can never both match the same text.
_REFLEXIVE_MAY_SACRIFICE_RE = re.compile(
    r"^you may sacrifice (?P<restriction>[^.]+)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_sacrifice_clause(text: str) -> AbilityEffect | None:
    """ "You may sacrifice `<restriction>`. When you do, `<consequence>`."
    (CR 603.12), read off the ability's own printed text so no registry row
    is needed - Grist, the Hunger Tide's `-2`.

    The "you may" half is exactly `_parse_conditional_sacrifice_clause`'s:
    `DecisionKind.MAY` with `affirmative_is_legal` set to whether a legal
    permanent to sacrifice exists (CR 608.2d), then `DecisionKind.CHOOSE_
    CARDS` if there is a real choice of which. What differs is what happens
    once the player says yes: CR 118.12 would run the consequence right here;
    CR 603.12 instead creates a *second* triggered ability
    (`Game.create_reflexive_trigger`) and leaves it for the stack, so
    `<consequence>` is parsed once, up front, into an ordinary `AbilityEffect`
    (`parse_mixed_effect`) that runs when *that* ability resolves - reading
    its own targets off itself (CR 608.2b's recheck included), never off the
    parent.
    """
    match = _REFLEXIVE_MAY_SACRIFICE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    restriction = _sacrifice_restriction(match.group("restriction"))
    if restriction is None:
        return None
    x_count = restriction.quantity.source is QuantitySource.X
    consequence_text = match.group("consequence").strip()
    # "damage equal to the sacrificed creature's power" (CR 608.2h): the
    # power is written in as the sacrifice happens, like the count below.
    by_power = carries_sacrificed_power(consequence_text)
    stand_in = _carry_sacrificed_power(consequence_text, 2) if by_power else consequence_text
    # Read once with a stand-in count, so an unreadable consequence fails
    # the whole ability closed now rather than after the sacrifice.
    if reflexive_consequence_effect(_carry_count(stand_in, 2, x=x_count)) is None:
        return None
    prompt = f"sacrifice {match.group('restriction').strip()}"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        candidates = restriction.candidates(game, player, source_id)
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=prompt,
            source=source_name,
            affirmative_is_legal=_sacrifice_is_payable(restriction.quantity, candidates),
            source_id=source_id_of(ability),
        )
        if not game.ask(decision):
            return
        chosen = _choose_permanents_to_sacrifice(
            game,
            player,
            restriction,
            candidates,
            source_name=source_name,
            source_id=source_id_of(ability),
        )
        if not chosen:
            return
        # CR 608.2h: the sacrificed creature's power as it last existed on
        # the battlefield, read before it leaves.
        carried = consequence_text
        if by_power:
            if len(chosen) != 1:
                return
            carried = _carry_sacrificed_power(consequence_text, game.power_of(chosen[0]) or 0)
        # CR 603.12a: paying a cost several times in one go triggers the
        # reflexive ability once.
        for permanent in chosen:
            game.sacrifice(permanent)
        game.record_count(len(chosen))
        # CR 603.12: the reflexive ability is created *now*, after the action
        # - not before it, and not offered a target of its own until it goes
        # on the stack (CR 603.3d), which `create_reflexive_trigger` defers to
        # `Game.put_triggers_on_stack`. Its "that many"/X is the count just
        # sacrificed.
        game.create_reflexive_trigger(
            text=_carry_count(carried, len(chosen), x=x_count),
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "`<first>`. When this ability resolves for the third time this turn,
#: `<consequence>`." (Gimli, Mournful Avenger): CR 603.12's reflexive ability,
#: whose trigger event is this ability's own resolution - counted per object
#: (CR 400.7: a permanent that returns is a new object) and per turn, and
#: created only by the resolution that makes the count exactly the printed
#: ordinal.
_RESOLVES_FOR_NTH_TIME_RE = re.compile(
    rf"^(?P<first>.+?\.)\s*when this ability resolves for the (?P<ordinal>{ORDINAL}) time "
    r"this turn,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: `Game.turn_counts` key prefix for `_RESOLVES_FOR_NTH_TIME_RE`'s count.
ABILITY_RESOLUTIONS_FACT = "ability_resolutions"


@ABILITY_TEXT.rung("s20")
def _parse_resolves_for_nth_time_reflexive_clause(text: str) -> AbilityEffect | None:
    """`_RESOLVES_FOR_NTH_TIME_RE`'s shape. `<first>` resolves as ordinary
    text; then this resolution is counted in `Game.turn_counts` (reset as
    each turn begins) under a key naming the source object (its id and
    zone-change stamp) and this ability's own text, and the resolution that
    brings the count to the ordinal creates the reflexive ability (CR
    603.12), whose targets are chosen as it goes on the stack (CR 603.3d)."""
    if "when this ability resolves for the" not in text.lower():
        return None
    match = _RESOLVES_FOR_NTH_TIME_RE.fullmatch(text.strip())
    if match is None:
        return None
    nth = parse_ordinal(match.group("ordinal"))
    first = parse_mixed_effect(match.group("first"))
    consequence = match.group("consequence").strip()
    if nth is None or first is None or reflexive_consequence_effect(consequence) is None:
        return None
    fingerprint = hashlib.sha1(text.strip().lower().encode()).hexdigest()[:12]

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        first(game, ability)
        key = f"{ABILITY_RESOLUTIONS_FACT}:{ability.source_id}:{ability.source_stamp}:{fingerprint}"
        game.note_turn_count(key, ability.controller)
        if game.turn_count(key, ability.controller) != nth:
            return
        game.create_reflexive_trigger(
            text=consequence,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "You may discard a card. When you do, `<consequence>`." - Tether
#: Technician's own ETB trigger, the discard-flavoured twin of
#: `_REFLEXIVE_MAY_SACRIFICE_RE`. "up to N cards"/"any number of cards" read
#: the identical quantity grammar `_MAY_DISCARD_N_CARDS_RE` already reads for
#: CR 118.12's "if you do" sibling shape - "when you do" is CR 603.12's own
#: separate reflexive trigger instead (see that regex's own docstring for
#: why the two connectors are never folded into one).
_REFLEXIVE_MAY_DISCARD_RE = re.compile(
    rf"^you may discards? "
    rf"(?:(?P<any>any number of)|(?:(?P<upto>up to )?(?P<n>{AMOUNT})))\s+cards?\.\s*"
    r"when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_may_discard_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_DISCARD_RE`'s shape, or `None`.

    CR 603.12: the discard is the optional action, and "When you do" creates
    a *second* triggered ability that announces its own targets ("any
    target", CR 601.2c) once it goes on the stack - never the parent
    ability's own targets, which is why Tether Technician's "deals 2 damage
    to any target" reached no target at all before this existed (the ETB
    trigger itself has no target for it to be, and nothing ever asked). The
    consequence is parsed once, up front (`reflexive_consequence_effect`),
    with a stand-in count so an unreadable one fails the whole ability closed
    before the discard happens, the same guard `_parse_reflexive_sacrifice_
    clause` already applies.
    """
    match = _REFLEXIVE_MAY_DISCARD_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if match.group("any") is not None:
        amount: int | None = None
        exact = False
    else:
        amount = parse_count(match.group("n"))
        if amount is None:
            return None
        exact = match.group("upto") is None
    consequence_text = match.group("consequence").strip()
    if reflexive_consequence_effect(_carry_count(consequence_text, 2, x=False)) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        needed = amount if amount is not None else len(player.hand)
        prompt = (
            "discard a card"
            if amount == 1 and exact
            else f"discard {'up to ' if not exact else ''}{needed} card(s)"
        )
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=prompt,
            source=source_name,
            affirmative_is_legal=bool(player.hand),
            source_id=source_id_of(ability),
        )
        if not game.ask(decision):
            return
        discarded = _discard_cards(
            game, player, needed, source_name, source_id=source_id_of(ability), exact=exact
        )
        if not discarded:
            return
        # CR 603.12a: paying a cost several times in one go triggers the
        # reflexive ability once.
        game.create_reflexive_trigger(
            text=_carry_count(consequence_text, len(discarded), x=False),
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


# --------------------------------------------------------------------------
# CR 603.12 generalised: a non-sacrifice paid cost, and a mandatory action
# --------------------------------------------------------------------------
#
# `_parse_reflexive_sacrifice_clause` above only reads "you may sacrifice
# ... When you do, ...". Two more CR 603.12 shapes are in the pool:
#
# - Guide of Souls' "Whenever you attack, you may pay {E}{E}{E}. When you
#   do, ..." - the "you may" half is a *cost*, not a sacrifice, and
#   `DecisionKind.PAY_ENERGY`/`Game.may_pay_energy` (built for Static
#   Prison's "unless you pay {E}") is what makes it payable at all now.
# - Ajani, Nacatl Avenger's "Create a token. When you do, if ..., he deals
#   damage ..." - a *mandatory* action, not "you may" at all (CR 603.12's
#   "allow **or instruct**"), with an intervening *if* (CR 603.4) nested in
#   the reflexive clause itself.
#
# Both still create the reflexive ability only once the action has actually
# happened (`_REFLEXIVE_MAY_PAY_ENERGY_RE`'s decline, `_REFLEXIVE_MANDATORY_
# TOKEN_RE`'s replaced-into-nothing token creation), the same trap
# `_parse_reflexive_sacrifice_clause` already guards.

#: "you may pay {E}{E}{E}. When you do, `<consequence>`." - the fixed-amount
#: energy cost `_REFLEXIVE_MAY_SACRIFICE_RE` does not cover.
_REFLEXIVE_MAY_PAY_ENERGY_RE = re.compile(
    r"^you may pay (?P<energy>(?:\{e\})+)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_pay_energy_clause(text: str) -> AbilityEffect | None:
    """ "You may pay {E}{E}{E}. When you do, `<consequence>`." (CR 603.12,
    CR 107.14, CR 118.3) - Guide of Souls' attack trigger, the fixed-amount
    energy-cost twin of `_parse_reflexive_sacrifice_clause`'s sacrifice.

    `Game.may_pay_energy` already asks CR 608.2d's question and pays exactly
    the right amount - built for Static Prison's "unless you pay {E}" - so
    this only has to ask it in the affirmative sense and, only once it comes
    back true, create the reflexive ability the same way the sacrifice
    version does. A "no" answer - unaffordable or declined - spends no energy
    and creates nothing, the same "the cost stays paid, the trigger does not
    exist otherwise" shape as the sacrifice version, just for a cost that
    cannot be un-paid because it never was.

    The consequence is `reflexive_pay_consequence_effect`'s to read - the
    same reader the ordinary-mana twin uses - and it is read once, up front,
    so an unread consequence declines the whole clause now rather than after
    the energy is spent.
    """
    match = _REFLEXIVE_MAY_PAY_ENERGY_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    amount = len(re.findall(r"\{e\}", match.group("energy"), re.IGNORECASE))
    consequence_text = _reflexive_consequence_text(match.group("consequence"))
    if reflexive_pay_consequence_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may_pay_energy(
            player, amount, source=source_name, source_id=source_id_of(ability)
        )
        if not paid:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexivePayEnergyConsequence(),
        )

    return effect


def _reflexive_consequence_text(captured: str) -> str:
    """A reflexive consequence as its ability's own text: stripped, with the
    closing period a modal list's last mode printed put back, so every mode
    reads (and is offered, CR 700.2) exactly as printed."""
    text = captured.strip()
    return _as_sentence(text) if modal_trigger_profile(text) is not None else text


def _modal_mode_is_readable(mode_text: str) -> bool:
    """Whether `_resolve_modal_triggered_ability_clause` reads one mode's
    text - the same readers it tries, in the same order."""
    readers = (
        parse_mixed_effect,
        _compose_layer_effect_with_remainder_for_ability_mode,
        _parse_where_x_is_continuous_effect,
    )
    return any(reader(mode_text) is not None for reader in readers)


def reflexive_pay_consequence_effect(text: str) -> AbilityEffect | None:
    """The consequence of a paid "you may pay `<cost>`. When you do, ..." (CR
    603.12), run when the reflexive ability resolves: Guide of Souls' own
    counters-and-type clause, a modal list whose every mode reads (the mode
    already chosen as the reflexive ability went on the stack, CR 603.3c),
    or `pay_consequence_effect`'s shapes. `None` when none of them reads it,
    so the paying clause declines before anything is paid."""
    counters = _parse_counters_and_becomes_type_clause(text)
    if counters is not None:
        return counters
    modal = modal_trigger_profile(text)
    if modal is not None:
        if not all(_modal_mode_is_readable(mode_effect_body(mode)) for mode in modal.modes):
            return None
        return _resolve_modal_triggered_ability_clause(text)
    return pay_consequence_effect(text)


#: "you may pay `<energy>`. If you do, `<consequence>`." (CR 118.12, CR
#: 107.14) - Aether Chaser's own attack trigger. **Not** CR 603.12's
#: reflexive-ability creation (`_parse_reflexive_pay_energy_clause`'s own
#: "When you do," shape, `_REFLEXIVE_MAY_PAY_ENERGY_RE`): CR 118.12's "[Do
#: something]. If [a player] does, [effect]" reads the payment as a cost paid
#: *within* this same resolution, so `<consequence>` runs right here, on the
#: same `AbilityOnStack` - no new ability is created and nothing needs a
#: target announced for it later. The distinction is Oracle's own choice of
#: connector, not a synonym one regex can fold into the other: "When you do"
#: cards genuinely want CR 603.12's separate reflexive trigger (Guide of
#: Souls' own consequence needs its own CR 608.2b recheck at a later
#: priority), while "If you do" cards do not.
_MAY_PAY_ENERGY_IF_YOU_DO_RE = re.compile(
    r"^you may pay (?P<energy>(?:\{e\})+)\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_may_pay_energy_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_MAY_PAY_ENERGY_IF_YOU_DO_RE`'s shape - see its own docstring for why
    this is CR 118.12, not CR 603.12. The consequence is `pay_consequence_
    effect`'s to read, shared with the ordinary-mana twin."""
    match = _MAY_PAY_ENERGY_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    amount = len(re.findall(r"\{e\}", match.group("energy"), re.IGNORECASE))
    consequence = pay_consequence_effect(match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may_pay_energy(
            player, amount, source=source_name, source_id=source_id_of(ability)
        )
        if not paid:
            return
        consequence(game, ability)

    return effect


#: "Mill `<n>` cards. When you do, `<consequence>`." - CR 603.12's mandatory
#: ("instruct") action read the same general way `_parse_reflexive_sacrifice_
#: clause`'s own "you may" version is, with no decision to ask at all: the
#: mill simply happens, and the reflexive ability is created right after -
#: Primal Witchstalker's own ETB.
_REFLEXIVE_MANDATORY_MILL_RE = re.compile(
    rf"^mill (?P<n>{COUNT}) cards?\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_mandatory_mill_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MANDATORY_MILL_RE`'s shape, or `None`.

    CR 603.12: the reflexive ability is created after the mill actually
    happened, its own consequence read whole and stored as text
    (`ReflexiveConsequence`, the same general callback `_parse_reflexive_
    sacrifice_clause` uses) - a card in the pool prints no intervening *if*
    on this shape, so none is read here, unlike the token/energy versions'
    own condition-carrying variants.
    """
    match = _REFLEXIVE_MANDATORY_MILL_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    consequence_text = match.group("consequence").strip()
    consequence_effect = parse_mixed_effect(consequence_text)
    if consequence_effect is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        milled = _mill(game, controller, count)
        if not milled:
            # CR 701.17c: nothing moved (an empty library), so the mill
            # instruction had nothing to reflect either.
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "you may pay {N}. When you do, `<consequence>`." - Lich's Relic's own ETB
#: trigger, the ordinary-mana twin of `_REFLEXIVE_MAY_PAY_ENERGY_RE`'s energy
#: symbols. The symbol run is only ever mana: `ManaCost.try_parse` declines
#: {E} (CR 107.14) and every other non-mana symbol, so an energy payment the
#: energy reader could not read is never taken for a mana one.
#: Ezio Auditore da Firenze gates the offer itself: "you may pay {W}{U}{B}{R}{G}
#: if that player has 10 or less life. When you do, ..." - the condition is
#: read when the trigger resolves (CR 603.4 reads an intervening if only at
#: the front of a trigger; this one sits inside the instruction), and a
#: payment that was never offered is never made.
_REFLEXIVE_MAY_PAY_MANA_RE = re.compile(
    r"^you may pay (?P<mana>(?:\{[^}]+\})+)(?: if (?P<condition>[^.]+))?\.\s*"
    r"when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_pay_mana_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_PAY_MANA_RE`'s shape (CR 603.12, CR 601.2h, CR 118.3) -
    `Game.may_pay_mana_cost` asks CR 608.2g's payment question and pays it in
    full or not at all, the same "cost stays paid, consequence conditional"
    shape `_parse_reflexive_pay_energy_clause` already reads for energy, and
    the same consequence reader (`reflexive_pay_consequence_effect`).
    """
    match = _REFLEXIVE_MAY_PAY_MANA_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    cost = ManaCost.try_parse(match.group("mana"))
    if cost is None:
        return None
    consequence_text = _reflexive_consequence_text(match.group("consequence"))
    if reflexive_pay_consequence_effect(consequence_text) is None:
        return None
    condition = match.group("condition")
    if condition is not None and not _effect_condition_is_readable(condition, allow_anaphor=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        if condition is not None and not game.condition_holds(
            player.username, condition, ability.source(game), ability=ability, event=ability.event
        ):
            return
        paid = game.may_pay_mana_cost(
            player, cost, source=source_name, source_id=source_id_of(source_id)
        )
        if not paid:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexivePayManaConsequence(),
            event=ability.event,
        )

    return effect


#: "you may pay `<N>` life. When you do, `<consequence>`." - Ambulatory
#: Edifice's own ETB trigger, the pure-life twin of `_REFLEXIVE_MAY_PAY_
#: MANA_RE`. CR 603.12, CR 119.4.
_REFLEXIVE_MAY_PAY_LIFE_RE = re.compile(
    rf"^you may pay (?P<life>{COUNT}) life\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_pay_life_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_PAY_LIFE_RE`'s shape - `Game.may_pay_life` asks CR
    119.4's payment question and pays it in full or not at all, the same
    "cost stays paid, consequence conditional" shape `_parse_reflexive_pay_
    mana_clause` already reads for mana."""
    match = _REFLEXIVE_MAY_PAY_LIFE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    life = parse_count(match.group("life"))
    if life is None:
        return None
    consequence_text = _reflexive_consequence_text(match.group("consequence"))
    if reflexive_pay_consequence_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may_pay_life(
            player, life, source=source_name, source_id=source_id_of(source_id)
        )
        if not paid:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexivePayManaConsequence(),
        )

    return effect


#: "you may pay `<mana>` and `<N>` life. When you do, `<consequence>`." -
#: Zoraline, Cosmos Caller's own "Whenever Zoraline enters or attacks, you
#: may pay {W}{B} and 2 life. When you do, ..." - the combined mana-and-life
#: twin of `_REFLEXIVE_MAY_PAY_MANA_RE`/`_REFLEXIVE_MAY_PAY_LIFE_RE`, neither
#: of which reads a compound cost. CR 603.12, CR 118.3, CR 119.4: one CR
#: 608.2d question for the whole cost (`Game.may_pay_unless_cost`, the same
#: single-decision shape a mixed "unless" cost already asks, rather than two
#: separate mana/life questions), paid atomically or not at all.
_REFLEXIVE_MAY_PAY_MANA_AND_LIFE_RE = re.compile(
    rf"^you may pay (?P<mana>(?:\{{[^}}]+\}})+) and (?P<life>{COUNT}) life\.\s*"
    r"when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_pay_mana_and_life_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_PAY_MANA_AND_LIFE_RE`'s shape - see its own docstring."""
    match = _REFLEXIVE_MAY_PAY_MANA_AND_LIFE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    mana = ManaCost.try_parse(match.group("mana"))
    life = parse_count(match.group("life"))
    if mana is None or life is None:
        return None
    consequence_text = _reflexive_consequence_text(match.group("consequence"))
    if reflexive_pay_consequence_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may_pay_mana_and_life(
            player,
            mana,
            life,
            source=source_name,
            source_id=source_id_of(source_id),
        )
        if not paid:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexivePayManaConsequence(),
        )

    return effect


#: "you may tap him/her/it. When you do, `<consequence>`." - Spider-Man, To
#: the Rescue's own ETB rider: "No One Dies! — When Spider-Man enters, you
#: may tap him. When you do, another target nonattacking creature you
#: control gains indestructible until end of turn." CR 118.12's reflexive
#: "may [cost]. When you do, [consequence]" shape `_parse_reflexive_pay_
#: mana_clause` already reads for a mana payment, with CR 701.26a's tap
#: standing in for the cost instead - the pronoun is read literally rather
#: than relying on `legendary_self_pronoun_normalized`'s own mid-sentence
#: rewrite to have already run first (this is tried ahead of that fallback,
#: the same "raw text first" order every dispatcher in this module keeps),
#: so "him"/"her" match here whichever legendary character the card is
#: printed on, alongside the ordinary self-referential "it"/"itself".
_REFLEXIVE_MAY_TAP_SELF_RE = re.compile(
    r"^you may tap (?:him|her|it|itself|them|themselves)\.\s*when you do,\s*"
    r"(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_may_tap_self_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_TAP_SELF_RE`'s shape - see the banner above. An
    already-tapped source, or one that has since left the battlefield,
    cannot pay the cost (CR 118.3), so the "may" is never even offered and
    the reflexive consequence never triggers - the identical "cost stays
    paid, consequence conditional" shape `_parse_reflexive_pay_mana_clause`
    already reads for a mana cost, with `game.may` standing in for `Game.
    may_pay_mana_cost`'s own CR 608.2g payment question."""
    match = _REFLEXIVE_MAY_TAP_SELF_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    consequence_text = match.group("consequence").strip()
    if parse_mixed_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD or source.tapped:
            return  # CR 118.3: an impossible cost is simply not paid.
        player = game.controller_of(ability)
        if not game.may(
            player,
            f"tap {source.name}",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        source.tap()
        # CR 701.26a: tapping the permanent is the event - the same
        # `BECOMES_TAPPED` `GameEvent` `machines/cost.py`'s own tap
        # component emits for every other cost-tap in this engine.
        game.emit(
            GameEvent(
                event=TriggerEvent.BECOMES_TAPPED,
                subject_id=source.id,
                subject_name=source.name,
                subject_controller=source.controller,
                subject_card=source.card,
                player=source.controller,
            )
        )
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "you may sacrifice `<restriction>` or discard `<quality>`. When you do,
#: `<consequence>`." - Bullseye, Death Dealer's own "you may sacrifice an
#: artifact or discard a nonland card. When you do, Bullseye deals 2 damage
#: to any target." CR 118.8b's own optional cost, with CR 601.2b's "[cost]
#: or [cost]" choice of which resource pays it (the same disjunction
#: `machines/casting.py`'s own `_OR_PAY_TAIL` reads for a mandatory
#: additional cost) standing in for `_REFLEXIVE_MAY_SACRIFICE_RE`'s single
#: restriction. Offered as two sequential CR 608.2d "may" questions - first
#: whether to sacrifice (only when a legal permanent exists), then, only if
#: that was declined, whether to discard instead - rather than one combined
#: question, since neither `Decision` nor any existing `DecisionKind` names
#: a choice between two differently-shaped actions; an unscripted player
#: still reaches the reflexive consequence exactly the same way either
#: branch is taken, and the two questions are also what a human at a real
#: table is actually asked one at a time ("do you want to sacrifice an
#: artifact? ... no? do you want to discard instead?").
_REFLEXIVE_MAY_SACRIFICE_OR_DISCARD_RE = re.compile(
    r"^you may sacrifice (?P<restriction>[^.]+?) or discard an? (?P<quality>[a-z]+) card\.\s*"
    r"when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_sacrifice_or_discard_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_SACRIFICE_OR_DISCARD_RE`'s shape - see the banner
    above."""
    match = _REFLEXIVE_MAY_SACRIFICE_OR_DISCARD_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    restriction = _sacrifice_restriction(match.group("restriction"))
    if restriction is None:
        return None
    quality_matcher = _nonland_or_typed_card_matcher(match.group("quality"))
    if quality_matcher is None:
        return None
    consequence_text = match.group("consequence").strip()
    if reflexive_consequence_effect(_carry_count(consequence_text, 1, x=False)) is None:
        return None
    sacrifice_prompt = f"sacrifice {match.group('restriction').strip()}"
    discard_prompt = f"discard {match.group('quality').strip()} card"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        sacrificed: list[CardState] = []
        discarded: list[CardState] = []
        candidates = restriction.candidates(game, player, source_id)
        if _sacrifice_is_payable(restriction.quantity, candidates) and game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=sacrifice_prompt,
                source=source_name,
                affirmative_is_legal=True,
                source_id=source_id_of(ability),
            )
        ):
            sacrificed = _choose_permanents_to_sacrifice(
                game,
                player,
                restriction,
                candidates,
                source_name=source_name,
                source_id=source_id_of(ability),
            )
            for permanent in sacrificed:
                game.sacrifice(permanent)
        if not sacrificed:
            hand_matches = [card for card in player.hand if quality_matcher(card)]
            if hand_matches and game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt=discard_prompt,
                    source=source_name,
                    affirmative_is_legal=True,
                    source_id=source_id_of(ability),
                )
            ):
                discarded = _discard_cards(
                    game,
                    player,
                    1,
                    source_name,
                    source_id=source_id_of(ability),
                    predicate=quality_matcher,
                )
        if not sacrificed and not discarded:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "you may pay `<mana>` up to `<N>` times. When you do, choose up to that
#: many — • `<Label>` — `<effect>` • ..." - Hawkeye, Master Marksman's own
#: "Trick Arrows — Whenever Hawkeye becomes tapped, you may pay {1} up to
#: three times. When you do, choose up to that many — • Net — ... •
#: Explosive — ... • Boomerang — ...". CR 603.12's reflexive shape, repeated
#: (`_REFLEXIVE_MAY_PAY_MANA_RE`'s single-payment twin) - each of the up to
#: `<N>` payments is its own CR 118.12 "you may pay" question, and "choose
#: up to that many" reads the running total straight off how many of those
#: questions came back yes, the same CR 603.2c "that many" anaphora
#: `_COUNTER_ON_TRIGGER_SUBJECT_RE`'s own "for each" already resolves at
#: resolution rather than at parse time. Each bulleted option is its own
#: labelled clause ("Net — Target creature can't block this turn.") - the
#: label is CR 207.2c's ability-word convention applied to one bullet
#: instead of a whole ability, carrying no rules meaning of its own, so it
#: is stripped before the bullet's own effect is read.
_REFLEXIVE_PAY_UP_TO_N_TIMES_CHOOSE_MODES_RE = re.compile(
    r"^you may pay (?P<mana>(?:\{[^}]+\})+) up to (?P<times>[a-z]+) times\.\s*"
    r"when you do, choose up to that many\s*[—-]\s*(?P<bullets>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_REFLEXIVE_MODE_BULLET_RE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z' ]*?)\s*[—-]\s*(?P<effect>.+)$", re.DOTALL
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_pay_up_to_n_times_choose_modes_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_PAY_UP_TO_N_TIMES_CHOOSE_MODES_RE`'s shape - see the
    banner above. Each mode may be chosen at most once (no "you may choose
    the same mode more than once" is printed), up to however many of the
    repeated payments actually happened."""
    whole = _strip_non_effect_preamble(text).strip()
    match = _REFLEXIVE_PAY_UP_TO_N_TIMES_CHOOSE_MODES_RE.fullmatch(whole)
    if match is None:
        return None
    try:
        cost = ManaCost.parse(match.group("mana"))
    except ValueError:
        return None
    times = parse_count(match.group("times"))
    if times is None or times < 1:
        return None
    bullet_texts = [part.strip() for part in match.group("bullets").split("•") if part.strip()]
    if len(bullet_texts) < 2:
        return None
    modes: list[str] = []
    for bullet in bullet_texts:
        bullet_match = _REFLEXIVE_MODE_BULLET_RE.fullmatch(bullet.strip().rstrip("."))
        if bullet_match is None:
            return None
        mode_text = bullet_match.group("effect").strip()
        # Read once here purely to fail the whole ability closed (CR 608.2c)
        # on an unreadable mode before any payment happens - the real run,
        # per chosen mode, goes through `create_reflexive_trigger` below
        # instead, so each pick announces and resolves its own targets
        # (CR 603.3d) rather than sharing the *triggering* ability's, which
        # were fixed (and may have been none at all) long before this many
        # payments were even known.
        if parse_mixed_effect(mode_text) is None:
            return None
        modes.append(mode_text)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = 0
        for _ in range(times):
            if not game.may_pay_mana_cost(
                player, cost, source=source_name, source_id=source_id_of(ability)
            ):
                break
            paid += 1
        if paid <= 0:
            return
        remaining = list(modes)
        for _ in range(min(paid, len(modes))):
            if not remaining:
                break
            if not game.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=player.username,
                    prompt="choose another mode",
                    source=source_name,
                    affirmative_is_legal=True,
                    source_id=source_id_of(ability),
                )
            ):
                break
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_MODE,
                    player=player.username,
                    prompt="choose a mode",
                    source=source_name,
                    options=tuple(remaining),
                    source_id=source_id_of(ability),
                )
            )
            assert isinstance(answer, str)
            picked = answer if answer in remaining else remaining[0]
            remaining.remove(picked)
            # CR 603.12/603.3d: each chosen mode is its own reflexive
            # triggered ability, announcing and resolving its own targets
            # separately - not run inline against the ability that created
            # it, whose own targets (if any) were fixed long before any of
            # this was known.
            game.create_reflexive_trigger(
                text=picked,
                controller=player.username,
                source_id=ability.source_id,
                source_name=source_name,
                callback=ReflexiveConsequence(),
            )

    return effect


#: CR 608.2d's "may X. If they do, Y. If they didn't, Z." over a target's
#: **owner** (CR 108.3, not the caster): "Choose target `<X>`. Its owner may
#: put it on (the) top of their library. If they do, `<source>` deals N damage
#: to them. If they didn't put the card on (the) top of their library, they
#: put it on the bottom." The target, source and N are variables; the else is
#: CR 401's exhaustive other end of one library. Clash of Elements (current
#: oracle "on top of", pre-release "on the top of") is the only Modern/
#: Pioneer/Standard printing of the shape (Scryfall oracle bulk checked
#: 2026-10-04), so no lose/gain/draw consequence or bottom-first side is read
#: until a real printing needs one.
_CHOOSE_TARGET_OWNER_MAY_TOP_ELSE_BOTTOM_RE = re.compile(
    r"^choose target (?P<desc>.+?)\.\s*its owner may put it on (?:the )?top of their library\.\s*"
    r"if they do,\s*.*?\bdeals (?P<n>\d+) damage to them\.\s*"
    r"if they didn'?t put the card on (?:the )?top of their library, they put it on the bottom\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s11", for_spell=True)
def _parse_choose_target_owner_may_top_else_bottom_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CHOOSE_TARGET_OWNER_MAY_TOP_ELSE_BOTTOM_RE`'s shape; see the banner
    above.
    """
    match = _CHOOSE_TARGET_OWNER_MAY_TOP_ELSE_BOTTOM_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('desc').strip()}"):
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, CardState)
        ]
        if not targets:
            return
        card = targets[0]
        owner = game.player(card.owner)
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        decision = Decision(
            kind=DecisionKind.MAY,
            player=owner.username,
            prompt=f"put {card.name} on top of their library",
            source=source_name,
            affirmative_is_legal=True,
            source_id=source_id_of(stack_object),
        )
        put_on_top = game.ask(decision)
        if card.zone not in (Zone.BATTLEFIELD, Zone.HAND, Zone.GRAVEYARD, Zone.EXILE):
            return  # CR 608.2b: no longer a legal object to move.
        game.put_cards_into_library([card], to_bottom=not put_on_top)
        if put_on_top:
            game.deal_damage(
                owner,
                amount,
                source=stack_object
                if isinstance(stack_object, CardState)
                else stack_object.source_or_last_known(game),
            )

    return effect


#: "[Choose ]target `<X>`. Its owner shuffles it into their library." (CR
#: 701.20a) - Living Library's own activated ability; the real, off-set
#: printing is Deglamer's identical two sentences. "Its owner" is CR 108.3's
#: owner, not `_ANAPHORIC_SUBJECT_RE`'s own "controller"/"that player" family,
#: so this is its own pair reader rather than a widening of that one.
_CHOOSE_TARGET_OWNER_SHUFFLES_IT_RE = re.compile(
    r"^(?:choose )?target (?P<desc>.+?)\.\s*its owner shuffles it into their library\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s17", for_spell=False)
@SPELL_TEXT.rung("s11", for_spell=True)
def _parse_choose_target_owner_shuffles_it_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CHOOSE_TARGET_OWNER_SHUFFLES_IT_RE`'s shape; see the banner above.

    Shuffled in, not placed: the card goes into its owner's library (position
    does not matter, since the very next step randomises the whole library,
    CR 701.20a: "the deck is put in a random order").
    """
    match = _CHOOSE_TARGET_OWNER_SHUFFLES_IT_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('desc').strip()}"):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState):
                continue
            if target.zone not in (Zone.BATTLEFIELD, Zone.HAND, Zone.GRAVEYARD, Zone.EXILE):
                continue  # CR 608.2b: no longer a legal object to move.
            owner = game.player(target.owner)
            game.put_cards_into_library([target])
            game.shuffle_library(owner)

    return effect


#: "Choose a creature type. Destroy all creatures that aren't of the chosen
#: type." (CR 701.6, CR 701.6a) - Kindred Judgment's own text, and the real,
#: off-set printing Kindred Dominance's identical wording.
_CHOOSE_CREATURE_TYPE_DESTROY_EXCEPT_RE = re.compile(
    r"^choose a creature type\.\s*destroy all creatures that aren'?t of the chosen "
    r"type\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s11", for_spell=True)
def _parse_choose_creature_type_destroy_except_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CHOOSE_CREATURE_TYPE_DESTROY_EXCEPT_RE`'s shape; see the banner
    above. CR 701.6a: "the value of that choice may be any creature type,
    even one that's not on the battlefield" - the vocabulary offered is
    every printed creature type (`creature_type_vocabulary`), not only the
    ones currently in play.
    """
    if _CHOOSE_CREATURE_TYPE_DESTROY_EXCEPT_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name  # type: ignore[union-attr]
        )
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt="choose a creature type",
                source=source_name,
                options=tuple(sorted(creature_type_vocabulary())),
                source_id=source_id_of(stack_object),
            )
        )
        assert isinstance(chosen, str)
        board = game.computed_board()
        for permanent in list(game.battlefield):
            chars = board.of(permanent)
            if Type.CREATURE not in chars.types:
                continue
            if chosen in chars.subtypes:
                continue
            if permanent.zone is Zone.BATTLEFIELD:
                game.destroy(permanent)

    return effect


#: "Choose a creature type. Create a Treasure token for each creature you
#: control of that type." - Orcrist, Goblin-cleaver's own combat-damage
#: trigger. CR 701.6a's choice (`creature_type_vocabulary`, the same
#: vocabulary `_parse_choose_creature_type_destroy_except_clause` above
#: offers) counted back against the board the same "of that type" way
#: `_parse_choose_creature_type_destroy_except_clause`'s own "aren't of the
#: chosen type" reads it - CR 111.10a's own predefined Treasure.
_CHOOSE_CREATURE_TYPE_TREASURE_PER_MATCH_RE = re.compile(
    r"^choose a creature type\.\s*create a treasure token for each creature "
    r"you control of that type\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_choose_creature_type_treasure_per_match_clause(text: str) -> AbilityEffect | None:
    """`_CHOOSE_CREATURE_TYPE_TREASURE_PER_MATCH_RE`'s shape; see the banner
    above."""
    if _CHOOSE_CREATURE_TYPE_TREASURE_PER_MATCH_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt="choose a creature type",
                source=ability.source_name,
                options=tuple(sorted(creature_type_vocabulary())),
                source_id=source_id_of(ability),
            )
        )
        assert isinstance(chosen, str)
        board = game.computed_board()
        count = sum(
            1
            for permanent in game.battlefield
            if permanent.zone is Zone.BATTLEFIELD
            and permanent.controller == controller.username
            and Type.CREATURE in board.of(permanent).types
            and chosen in board.of(permanent).subtypes
        )
        if count:
            create_tokens(game, PREDEFINED["Treasure"], controller.username, count)

    return effect


#: CR 607.1's "that many"/"that much" anaphora, and its own "twice `<x>`"
#: multiplier (Borborygmos and Fblthp's own "twice that much damage") - read
#: as one substitution so the multiplied form is never mistaken for two
#: separate occurrences of the bare one. Tried as an alternation, "twice"
#: first, so `re.sub`'s left-to-right, non-overlapping scan consumes the
#: whole "twice that much" span in one match rather than leaving "that much"
#: behind for a second, wrongly-unmultiplied substitution.
_REFLEXIVE_THAT_MANY_RE = re.compile(r"twice that (?:many|much)|that (?:many|much)", re.IGNORECASE)


def _substitute_reflexive_count(text: str, count: int) -> str:
    """`text` with every CR 607.1 "that many"/"that much"/"twice that
    much" replaced by `count` (or `2 * count`), the same "read the count off
    an earlier instruction in this same ability, then substitute it in before
    the rest is parsed" idiom `substitute_x` already applies for CR 107.3a's
    X - just carrying a reflexive trigger's own qualifying count instead of
    an announced one.
    """

    def replace(match: re.Match[str]) -> str:
        return str(count * 2) if match.group(0).lower().startswith("twice") else str(count)

    return _REFLEXIVE_THAT_MANY_RE.sub(replace, text)


#: "`<antecedent, ending in a discard>`. When you discard one or more
#: [`<quality>`] cards this way, `<consequence>`." (CR 603.12, CR 607.1) -
#: Seasoned Cryomancer's own ETB: "draw two cards, then discard two cards.
#: When you discard one or more nonland cards this way, tap up to that many
#: target creatures and put a stun counter on each of them." CR 603.12's
#: own "when [something happens] this way" reflexive family, read with a
#: minimum-one *count* of qualifying cards attached to the trigger
#: description itself, rather than a bare "when you do" - `<quality>` is
#: optional
#: (Borborygmos and Fblthp's own "when you discard one or more cards this
#: way" carries none at all, any card qualifies) and, when printed, is any
#: single word `_nonland_or_typed_card_matcher`/`_quality_matcher` already
#: read - "nonland" is not special-cased here.
#:
#: The singular "When you discard a[n] `<quality>` card this way" (Evie
#: Frye's own "a creature card", Teo, Spirited Glider's and Glacial
#: Dragonhunt's "a nonland card") is the same family with a different count:
#: CR 603.12a, "if the trigger event or events occur multiple times during
#: the resolution of the spell or ability that created it, the reflexive
#: triggered ability will trigger once for each of those times" - one
#: reflexive ability per qualifying card discarded, where "one or more" is
#: one ability for the whole batch.
_REFLEXIVE_DISCARD_COUNT_RE = re.compile(
    r"^(?P<antecedent>.+?)\.\s*when you discard (?:(?P<batch>one or more)|an?) "
    r"(?:(?P<quality>[a-z]+) )?cards? this way,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s32")
def _parse_reflexive_discard_count_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_DISCARD_COUNT_RE`'s shape, or `None`.

    The antecedent is run exactly as it would be on its own, through
    `_ability_effect_or_notice` recursively - nothing here teaches a new way
    to draw or discard. "This way" (CR 608.2c) is read off a graveyard
    before/after diff taken *around the whole antecedent call*, not around
    whichever of its own sub-clauses says "discard": every card that is in
    the controller's graveyard afterward and was not there before is a card
    the antecedent just discarded, since nothing in this family's own
    antecedent shape (draw, then discard) sends a card to the graveyard any
    other way - which also means a card drawn earlier in that very same
    antecedent and then discarded is still counted, unlike a hand-before
    diff would give.

    CR 603.12: a qualifying count of zero means the event this reflexive
    ability describes never occurred, so no reflexive ability is created at
    all - the same "checked immediately, no ability if it didn't happen"
    rule `_parse_reflexive_mandatory_token_clause`'s own intervening *if*
    already follows, one level up from a bare mandatory action.
    """
    match = _REFLEXIVE_DISCARD_COUNT_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    antecedent_text = match.group("antecedent").strip()
    if not antecedent_text.endswith("."):
        antecedent_text += "."
    antecedent_effect = _ability_effect_or_notice(antecedent_text)
    if antecedent_effect is None:
        return None
    batch = match.group("batch") is not None
    quality_word = match.group("quality")
    quality_matcher: Callable[[CardState], bool] | None = None
    if quality_word is not None:
        quality_matcher = _nonland_or_typed_card_matcher(quality_word) or _quality_matcher(
            quality_word
        )
        if quality_matcher is None:
            return None
    consequence_text = match.group("consequence").strip()
    # Fails closed here, at parse time, rather than only discovering at
    # resolution that the consequence was never readable at all - tried with
    # a placeholder count so a "that many"/"that much" clause is exercised
    # the same way it will actually run.
    if parse_mixed_effect(_substitute_reflexive_count(consequence_text, 1)) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        graveyard_before = {card.id for card in controller.graveyard}
        antecedent_effect(game, ability)
        discarded = [card for card in controller.graveyard if card.id not in graveyard_before]
        if quality_matcher is not None:
            discarded = [card for card in discarded if quality_matcher(card)]
        count = len(discarded)
        if count <= 0:
            return
        # CR 603.12a: "one or more" is one ability carrying the count; the
        # singular "a `<quality>` card" triggers once per qualifying card.
        # The reflexive ability's event names the discarded card (the first of
        # the batch), which "its mana value" reads as it last existed (CR 608.2h).
        for index in range(1 if batch else count):
            game.create_reflexive_trigger(
                text=_substitute_reflexive_count(consequence_text, count),
                controller=controller.username,
                source_id=ability.source_id,
                source_name=source_name,
                callback=ReflexiveConsequence(),
                event=GameEvent(
                    event=TriggerEvent.DISCARDS_A_CARD,
                    player=controller.username,
                    amount=count,
                    discarded_ids=tuple(card.id for card in discarded),
                    subject_id=discarded[index].id,
                ),
            )

    return effect


#: "Create `<n>` `<token description>` token[s]." with no "you may" at all -
#: CR 603.12's "allow **or instruct**" read the mandatory way. Ajani, Nacatl
#: Avenger's `0`: "Create a 2/1 white Cat Warrior creature token. When you
#: do, ...".
_REFLEXIVE_MANDATORY_TOKEN_RE = re.compile(
    r"^(?P<action>create .+? tokens?)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_mandatory_token_clause(text: str) -> AbilityEffect | None:
    """ "Create `<n>` `<token>` token[s]. When you do, if ..., `<damage>`."
    (CR 603.12, CR 603.4) - Ajani, Nacatl Avenger's `0`.

    CR 603.12 reads "allow or instruct" - this is the "instruct" half, so
    there is no `MAY` decision at all: the token is simply created, and the
    reflexive ability is created right after, exactly as the sacrifice and
    energy versions do once *their* optional action goes through. What is
    still conditional is CR 603.4's intervening *if*, nested one level in -
    checked here, immediately after the token exists (CR 603.12's own
    "checked immediately after being created"), so a controller who does not
    control a qualifying permanent gets a token and no reflexive ability at
    all, not a reflexive ability that quietly does nothing when it resolves.
    """
    match = _REFLEXIVE_MANDATORY_TOKEN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    action_text = match.group("action").strip() + "."
    consequence_text = match.group("consequence").strip()
    token_match = _TOKEN_CLAUSE_RE.fullmatch(action_text)
    if token_match is None:
        return None
    count = parse_count(token_match.group("n"))
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
    condition_and_damage = _parse_if_control_colored_permanent_damage_clause(consequence_text)
    if condition_and_damage is None:
        return None
    condition_holds, _deal_the_damage = condition_and_damage

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        created = create_tokens(game, definition, controller.username, count)
        if not created:
            # CR 603.12: the action never actually happened (a replacement
            # effect ate it), so there is nothing to reflect.
            return
        if not condition_holds(game, controller.username, ability.source_id):
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveMandatoryTokenDamageConsequence(),
        )

    return effect


#: "put `<n>` `<kind>` counter[s] on this `<permanent>`. When you do, if
#: `<counter-count clause>`, `<consequence>`." - Earthbender Ascension's
#: landfall: "put a quest counter on this enchantment. When you do, if it has
#: four or more quest counters on it, put a +1/+1 counter on target creature
#: you control. It gains trample until end of turn." CR 603.12's mandatory
#: ("instruct") action on the source, with CR 603.4's intervening *if* nested
#: in the reflexive clause and read by `machines/triggers.py`'s own counter
#: count reader, since "it" is the permanent the counter went on.
_REFLEXIVE_SELF_COUNTER_IF_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\S+) counters? on this [a-z]+\.\s*"
    r"when you do,\s*(?P<reflexive>if (?P<condition>[^,]+),\s*(?P<consequence>.+?))\.?$",
    re.IGNORECASE | re.DOTALL,
)
#: The reflexive ability's own text, as `ReflexiveCounterCountConsequence`
#: re-reads it on resolution: "if `<clause>`, `<consequence>`".
_REFLEXIVE_COUNTER_IF_TEXT_RE = re.compile(
    r"^if (?P<condition>[^,]+),\s*(?P<consequence>.+?)\.?$", re.IGNORECASE | re.DOTALL
)


def _reflexive_counter_count_parts(
    text: str,
) -> tuple[Callable[[CardState], bool | None], AbilityEffect] | None:
    """The condition and consequence of a reflexive "if `<counter-count
    clause>`, `<consequence>`" text, or None when either is unreadable. The
    condition answers None for a clause `machines/triggers.py`'s counter-count
    reader does not recognise."""
    from ..triggers import _COUNTER_COUNT_CLAUSE, _counter_count_holds

    match = _REFLEXIVE_COUNTER_IF_TEXT_RE.fullmatch(text.strip())
    if match is None:
        return None
    condition = match.group("condition").strip().lower()
    if _COUNTER_COUNT_CLAUSE.match(condition) is None:
        return None
    consequence = parse_mixed_effect(match.group("consequence").strip() + ".")
    if consequence is None:
        return None

    def holds(source: CardState) -> bool | None:
        return _counter_count_holds(condition, source)

    return holds, consequence


@ABILITY_TEXT.rung("s20")
def _parse_reflexive_self_counter_if_clause(text: str) -> AbilityEffect | None:
    """`_REFLEXIVE_SELF_COUNTER_IF_RE`'s shape (CR 603.12, CR 603.4).

    The counters are put on the ability's own source. CR 603.12 creates the
    reflexive ability only if that happened - a source that has left the
    battlefield, or a counter a replacement effect prevented, reflects
    nothing. Its intervening *if* is checked as it is created ("checked
    immediately after being created"), so a count that is too low creates no
    ability at all; `ReflexiveCounterCountConsequence` checks it again as the
    ability resolves (CR 603.4).
    """
    match = _REFLEXIVE_SELF_COUNTER_IF_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = match.group("kind").lower()
    reflexive_text = match.group("reflexive").strip()
    parts = _reflexive_counter_count_parts(reflexive_text)
    if parts is None:
        return None
    holds, _consequence = parts

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        before = source.counter_count(kind)
        game.add_counters(source, kind, amount)
        if source.counter_count(kind) <= before:
            return
        if not holds(source):
            return
        controller = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        game.create_reflexive_trigger(
            text=reflexive_text,
            controller=controller.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveCounterCountConsequence(),
        )

    return effect


#: "If this spell's additional cost was paid, <consequence>." - Requiting
#: Hex's own linked ability (CR 607, CR 118.8b's optional additional cost).
#: The condition names no keyword, so `CastRecord.optional_additional_cost_
#: paid` is what this reads - any optional additional cost, not blight by
#: name - the same genericity `Game.optional_additional_cost_paid`'s own
#: docstring argues for.
_IF_ADDITIONAL_COST_PAID_RE = re.compile(
    r"^if this spell'?s additional cost was paid, (?P<rest>.+)$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_if_additional_cost_paid_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_IF_ADDITIONAL_COST_PAID_RE`'s shape - a resolution-time conditional
    on the spell's own announcement (CR 608.2b), not a triggered ability's
    intervening *if*, so this is read here rather than through
    `machines/triggers.intervening_if_holds`. Spell-only: an activated or
    triggered ability has no `CastRecord` of its own to ask.
    """
    if not for_spell:
        return None
    match = _IF_ADDITIONAL_COST_PAID_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    rest = match.group("rest").strip()
    clause_effect = parse_clause_effect(rest) or parse_clause_effect(f"you {rest}")
    if clause_effect is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        record = game.cast_record(stack_object)
        if record.optional_additional_cost_paid:
            player = game.controller_of(stack_object)
            clause_effect(game, player, stack_object.name, source_id_of(stack_object))  # type: ignore[union-attr]

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_delayed_single_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """A whole ability whose *only* clause is a delayed-trigger creation, with
    no antecedent clause of its own to supply "it": either there is no object
    at all (Mishra's Bauble's "draw a card"), the object is the trigger's own
    event subject read off `ability.event.related_id` (Aether Membrane's
    "return that creature to its owner's hand at end of combat" - CR 509.1a's
    "the other creature in a blocking pair", the same way
    `damage_the_other_combatant` already does), or the object is the
    ability's own source - decayed's CR 702.147a "sacrifice it at end of
    combat" (CR 511.2's own fixed timing; a delayed "sacrifice it" naming any
    other timing is the anaphoric token-copy-then-sacrifice shape
    `_parse_put_then_grant_then_delayed_whole_text` reads instead, off a
    *preceding* clause's own antecedent, so this only ever claims the "end of
    combat" wording that shape never prints).

    A spell has no `ability.event` to read a bare pronoun off, so on a spell
    only the object-less draw is read (Swift Maneuver's and Mystic Melting's
    "Draw a card at the beginning of the next turn's upkeep", CR 603.7a: the
    spell's resolution creates a delayed triggered ability whose controller is
    the spell's controller, CR 603.7d).
    """
    timing = _parse_delayed_timing_clause(clause)
    if timing is None:
        return None
    step, verb = timing
    if for_spell and _DRAW_N_CARDS_RE.fullmatch(verb) is None:
        return None

    if draw_match := _DRAW_N_CARDS_RE.fullmatch(verb):
        draw_count = parse_count(draw_match.group("count"))
        if draw_count is None:
            return None
        # `draw_a_card_for_controller`'s own shared singleton for the
        # printed-everywhere "draw a card" count; a card naming a different
        # count gets its own `DrawACardForController` instance instead of
        # a new `DelayedTrigger.effect` kind.
        draw_spec = (
            draw_a_card_for_controller
            if draw_count == 1
            else DrawACardForController(count=draw_count)
        )

        def draw_effect(game: "Game", stack_object: "StackObject") -> None:
            if isinstance(stack_object, CardState):
                controller = game.controller_of(stack_object).username
                source_id, source_name = stack_object.id, stack_object.name
            else:
                assert isinstance(stack_object, AbilityOnStack)
                controller = stack_object.controller
                source_id, source_name = stack_object.source_id, stack_object.source_name
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clause,
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    effect=draw_spec,
                )
            )

        return draw_effect

    if _RETURN_TO_HAND_RE.fullmatch(verb):

        def return_to_hand_effect(game: "Game", stack_object: "StackObject") -> None:
            ability = stack_object
            assert isinstance(ability, AbilityOnStack)
            event = ability.event
            subject_id = event.related_id if event is not None else None
            if subject_id is None and event is not None:
                subject_id = event.subject_id
            if subject_id is None:
                return
            subject = game.find_by_id(subject_id)
            if not isinstance(subject, CardState):
                return
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clause,
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=ability.controller,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    subject_id=subject.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=subject.zone_change_stamp,
                    effect=return_subject_to_hand,
                )
            )

        return return_to_hand_effect

    if step is Step.END_OF_COMBAT and _DECAYED_SACRIFICE_IT_RE.fullmatch(verb):

        def sacrifice_it_effect(game: "Game", stack_object: "StackObject") -> None:
            ability = stack_object
            assert isinstance(ability, AbilityOnStack)
            subject = ability.source(game)
            if subject is None or subject.zone is not Zone.BATTLEFIELD:
                return
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=clause,
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=step,
                    controller=ability.controller,
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    subject_id=subject.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=subject.zone_change_stamp,
                    effect=sacrificed_by_its_controller,
                )
            )

        return sacrifice_it_effect

    return None


#: "return it/that card/that creature/that permanent to its owner's/your/
#: their owner's/their hand" - Aether Membrane's own shape.
_RETURN_TO_HAND_RE = re.compile(
    r"^return (?:it|that card|that creature|that permanent) to "
    r"(?:its owner's|your|their owner's|their) hand$",
    re.IGNORECASE,
)

#: CR 702.147a's own triggered half, "sacrifice it at end of combat" -
#: decayed's own wording, self-referential to the ability's own source the
#: same way `_parse_sacrifice_self_clause`'s own (immediate, non-delayed)
#: "sacrifice it" is. Named apart from that function's own `_SACRIFICE_IT_RE`
#: - this one is only ever tried already gated on `step is Step.END_OF_COMBAT`
#: by its caller, which is what keeps it from claiming a Kiki-Jiki/Reflection-
#: style "[create a token ...] Sacrifice it at the beginning of the next end
#: step." - a *different* pronoun, resolved from the antecedent clause by
#: `_parse_put_then_grant_then_delayed_whole_text`, never printed with "end of
#: combat" timing anywhere in the pool.
_DECAYED_SACRIFICE_IT_RE = re.compile(r"^sacrifice it$", re.IGNORECASE)


#: "You may choose new targets for that spell." - Speedball, New Warrior's
#: own trailing rider (CR 115.7d), "that spell" being CR 607.1 anaphora onto
#: whatever this trigger's own `TriggerEvent.CAST_SPELL` event names
#: (`event.subject_id`) - not a copy (`Game.offer_new_targets_for_copy`),
#: the ordinary spell itself, still on the stack.
_CHOOSE_NEW_TARGETS_FOR_THAT_SPELL_RE = re.compile(
    r"^you may choose new targets for that spell\.?$", re.IGNORECASE
)


def _parse_choose_new_targets_for_that_spell_clause(text: str) -> AbilityEffect | None:
    """`_CHOOSE_NEW_TARGETS_FOR_THAT_SPELL_RE`'s shape, or `None`.

    Ability-only: `event.subject_id` is a triggered ability's own attribute.
    """
    if _CHOOSE_NEW_TARGETS_FOR_THAT_SPELL_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object) or stack_object.event is None:
            return
        ability = stack_object
        event = ability.event
        if event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None or spell not in game.stack:
            return
        game.change_targets(
            spell,
            ability.controller,
            scope=RetargetScope.ANY,
            optional=True,
            source_name=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


def _condition_holds_for_stack_object(
    game: "Game", stack_object: "StackObject", condition_text: str, source: "CardState | None"
) -> bool | None:
    """`Game.condition_holds`, with a triggered ability's own `ability`/
    `event`/`source_stamp` threaded through when `stack_object` is one - the
    context an event-anchored clause needs to resolve an anaphor like "that
    spell" correctly (`Game.condition_holds`'s own docstring), which a bare
    3-argument call can never supply."""
    controller = game.controller_of(stack_object).username
    if isinstance(stack_object, AbilityOnStack):
        return game.condition_holds(
            controller,
            condition_text,
            source,
            ability=stack_object.ability,
            event=stack_object.event,
            source_stamp=stack_object.source_stamp,
        )
    return game.condition_holds(controller, condition_text, source)


#: "Choose target opponent and up to one target creature they control. They
#: reveal their hand. You may exile a nonland card from their hand or the
#: chosen creature until `<this>` leave the battlefield." - Cloak and
#: Dagger, Entwined's own ETB. Three sentences, one CR 608.2c instruction:
#: "they"/"their" is CR 607.1 anaphora onto the chosen opponent, and "the
#: chosen creature" is the *other* target, present only when the "up to
#: one" was actually used (CR 115.6). The exile is a genuine choice between
#: two different kinds of object (a hand card the ability names no target
#: for, versus the already-targeted creature) rather than a fresh target
#: of its own - CR 601.2c already fixed both targets in the first sentence.
_CHOOSE_OPPONENT_AND_CREATURE_REVEAL_EXILE_CHOICE_RE = re.compile(
    r"^choose target opponent and up to one target creature they control\.\s*"
    r"they reveal their hand\.\s*"
    r"you may exile a nonland card from their hand or the chosen creature "
    r"until (?:this permanent|this creature|they|it) leaves? the battlefield\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s10", for_spell=False)
def _parse_choose_opponent_and_creature_reveal_exile_choice_whole_text(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_CHOOSE_OPPONENT_AND_CREATURE_REVEAL_EXILE_CHOICE_RE`'s shape, or
    `None`. Ability-only: no printing in the pool has a spell target this
    way."""
    if for_spell:
        return None
    if _CHOOSE_OPPONENT_AND_CREATURE_REVEAL_EXILE_CHOICE_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        opponent: Player | None = None
        creature: CardState | None = None
        for target in game.resolve_targets(ability):
            if isinstance(target, Player):
                opponent = target
            elif isinstance(target, CardState):
                creature = target
        if opponent is None:
            return
        source = ability.source(game)
        for card in list(opponent.hand):
            game.reveal(card, source=ability.source_name)
        candidates = [card for card in opponent.hand if not card.card.is_land]
        if creature is not None:
            candidates.append(creature)
        if not candidates:
            return
        controller = game.controller_of(ability)
        taken = game.may(
            controller,
            "exile a nonland card from their hand or the chosen creature",
            source=ability.source_name,
            source_id=source_id_of(ability),
            cards=tuple(candidates),
        )
        if not taken:
            return
        chosen_id = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a card to exile",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(card.id for card in candidates),
            )
        )
        assert isinstance(chosen_id, tuple)
        by_id = {card.id: card for card in candidates}
        chosen = by_id[chosen_id[0]]
        origin_zone = chosen.zone  # CR 610.3: returns to whichever zone it left.
        moved = game.exile_permanent(chosen)
        if moved.zone is not Zone.EXILE or source is None:
            return
        _watch_for_departure_and_return_exiled_card(
            game, source, moved, controller.username, return_zone=origin_zone
        )

    return effect


#: "`<base>`. [`<ability word>` - ]If `<condition>`, instead `<alternative>`."
#: - Gruesome Discovery: "Target player discards two cards. / Morbid - If a
#: creature died this turn, instead that player reveals their hand, you
#: choose two cards from it, then that player discards those cards." - the
#: trailing order Twinned Vision prints instead of the leading one: "Draw a
#: card. If this spell wasn't cast from your hand, draw two cards instead." -
#: or CR 614.1a's other word order, the condition itself printed last:
#: "`<alternative>` instead if `<condition>`." (Galvanic Blast: "Galvanic
#: Blast deals 2 damage to any target. Metalcraft \u2014 Galvanic Blast deals 4
#: damage instead if you control three or more artifacts."; Brimstone
#: Volley, Morbid, the same shape). CR 614.1a: "Effects that use the word
#: 'instead' are replacement effects" - here the alternative replaces the
#: base instruction whole, whichever end of the sentence "instead" and "if"
#: sit at. The ability word (CR 207.2c) has no rules meaning and is only
#: skipped - `_strip_non_effect_preamble` already removes it from `whole`
#: before this ever runs, but the label is kept optional here too (not
#: required) in case it reaches this some other way, unstripped.
_CONDITION_INSTEAD_RE = re.compile(
    r'^(?P<base>(?:[^."]|"[^"]*")+)(?:\.\s*|(?<=")\s+)'
    r"(?:[a-z][a-z' ]*?\s+[\u2014-]\s+)?"
    r"(?:"
    r"if (?P<condition_leading>[^,]+), "
    r"(?:instead (?P<alternative_leading>.+?)|(?P<alternative_trailing>.+?) instead)"
    r"|"
    r"(?P<alternative_elided>.+?) instead if (?P<condition_elided>[^.]+)"
    r")\.?$",
    re.IGNORECASE,
)

#: The trailing "to `<target phrase>`" an elided alternative leaves out,
#: read off the *base* clause and spliced back onto the alternative before
#: it is parsed again - Galvanic Blast's own "deals 4 damage instead if you
#: control three or more artifacts" names no target of its own at all.
#: CR 601.2c fixes the spell's target once, at announcement; CR 614.1a's
#: alternative is a replacement for the base *instruction*, not a fresh one
#: with a target of its own, so the same phrase the base clause printed is
#: exactly what the alternative means too.
_TRAILING_TARGET_PHRASE_RE = re.compile(
    r"\bto (?P<phrase>any target|(?:up to [^,.]+ )?target [^,.]+)\.?$", re.IGNORECASE
)


def _instead_branch_effect(branch_text: str) -> Effect | None:
    """One branch of a CR 614.1a base-or-alternative pair, read as its own
    instruction.

    A branch that is itself one whole CR 611.2 layer sentence - Colossal
    Growth's base "Target creature gets +3/+3 until end of turn" and its
    kicked alternative "target creature gets +4/+4 and gains trample and
    haste until end of turn" - is built from *that branch's own text*
    (`_create_continuous_effect_for_mode_text`), never through the bare
    `create_continuous_effect` sentinel: the sentinel re-reads the spell's
    whole printed text, which is the base sentence whichever branch was
    chosen, so the resolved alternative's own amount and keywords never
    applied. Every other branch reads through `parse_mixed_effect_for_spell`
    as before.
    """
    parsed = parse_mixed_effect_for_spell(branch_text)
    if parsed is None:
        return None
    sentence = _as_sentence(branch_text)
    if is_genuine_resolution_layer_sentence(sentence):
        return _create_continuous_effect_for_mode_text(sentence)
    return parsed


def _resolve_instead_alternative(base_text: str, alternative_text: str) -> Effect | None:
    """CR 614.1a's alternative, read as its own instruction; with CR 400.7's
    anaphor swapped for the base clause's own literal target phrase
    (`_anaphoric_target_substitution`) when it names one that way; or, when
    it elides the target phrase the base clause already announced rather
    than naming it at all, with that phrase spliced onto it instead
    (`_TRAILING_TARGET_PHRASE_RE`). `None` only when none of the three
    readings works, which - CR 608.2c - fails the whole card closed rather
    than running half of it.
    """
    alternative = _instead_branch_effect(alternative_text)
    if alternative is not None:
        return alternative
    renumbered = _amount_substituted_base(base_text, alternative_text)
    if renumbered is not None:
        resolved = _instead_branch_effect(renumbered)
        if resolved is not None:
            return resolved
    substituted = _anaphoric_target_substitution(base_text, alternative_text)
    if substituted is not None:
        resolved = _instead_branch_effect(substituted)
        if resolved is not None:
            return resolved
    # "instead create X of those tokens, where X is ..." (The Final Days): the
    # base's own token, a different number.
    if _ABILITY_THOSE_TOKENS_ALTERNATIVE_RE.fullmatch(alternative_text.strip()) and (
        rewritten := _ability_instead_alternative_text(base_text, alternative_text)
    ):
        resolved = _instead_branch_effect(rewritten)
        if resolved is not None:
            return resolved
    if re.search(r"\btarget\b", alternative_text, re.IGNORECASE):
        # Already names its own target (or lack of one, "any target") - a
        # failure to parse here is a real gap, not an elision, and splicing
        # a second "to <phrase>" onto it would only make the text worse.
        return None
    tail = _TRAILING_TARGET_PHRASE_RE.search(base_text.strip())
    if tail is None:
        return None
    spliced = f"{alternative_text.strip().rstrip('.')} to {tail.group('phrase')}"
    return parse_mixed_effect_for_spell(spliced)


@SPELL_TEXT.rung("s14", before=["modal._parse_gift_promised_return_instead_clause"])
def _parse_condition_instead_clause(effect_text: str) -> Effect | None:
    """`_CONDITION_INSTEAD_RE`'s shape: the base instruction, or - when the
    condition holds as the spell resolves - the alternative in its place.

    The condition is read by `Game.condition_holds`, not a private table -
    `condition_is_readable` gates the parse at *parse* time, mirroring
    exactly what `condition_holds` would answer at resolution, so a
    condition this engine does not read leaves the whole card unread (CR
    608.2c) rather than the parse quietly assuming it false. At resolution,
    the rare case `condition_holds` itself still answers `None` despite the
    shape being readable (an inner count or quality word it does not know)
    is recorded as a `ConditionalClauseNotice`, the same class a modal
    instruction's own unreadable alternative condition already uses, rather
    than silently treated as false either.

    The alternative may name "that player", the player the base sentence
    targeted, which `_merge_reveal_hand_choose_discard_clauses` reads with
    `anaphoric_revealer`; or it may elide the base clause's own target
    phrase, which `_resolve_instead_alternative` reads. Both halves must
    read whole, or the card is left unread rather than half-run.
    """

    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _CONDITION_INSTEAD_RE.fullmatch(whole)
    if match is None:
        return None
    condition_text = (match.group("condition_leading") or match.group("condition_elided")).strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    base_text = match.group("base")
    base = _instead_branch_effect(base_text)
    if base is None:
        return None
    alternative_text = (
        match.group("alternative_leading")
        or match.group("alternative_trailing")
        or match.group("alternative_elided")
    )
    assert alternative_text is not None
    alternative = _resolve_instead_alternative(base_text, alternative_text)
    if alternative is None:
        # "that player reveals their hand, you choose two cards from it, then
        # that player discards those cards" is one CR 608.2c series of
        # instructions joined by commas, which the ordinary splitter keeps whole.
        clauses = [
            part.strip() for part in re.split(r",\s*(?:then\s+)?", alternative_text) if part.strip()
        ]
        merged = _merge_reveal_hand_choose_discard_clauses(
            clauses, 0, for_spell=True, anaphoric_revealer=True
        )
        if merged is None or merged[0] != len(clauses):
            return None
        alternative = merged[1]  # type: ignore[assignment]
    assert alternative is not None

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
        chosen = alternative if held else base
        chosen(game, spell)

    return effect


#: An ability alternative's elided or back-referring wording, read off the
#: base instruction: "`<subject>` deals M damage" (Akoum Hellkite's "this
#: creature deals 2 damage instead", Scepter of Empires' "It deals 3 damage
#: instead") is the base with only its amount changed; "Create N of those
#: tokens" (Throne of Empires) is the base's own token N times over.
_ABILITY_ELIDED_DAMAGE_ALTERNATIVE_RE = re.compile(
    rf"^(?P<subject>[^.]+?) deals (?P<m>{COUNT}) damage$", re.IGNORECASE
)
_ABILITY_BASE_DAMAGE_AMOUNT_RE = re.compile(rf"\bdeals (?P<n>{COUNT}) damage\b", re.IGNORECASE)
#: ... or "X of those tokens, where X is the number of creature cards in your
#: graveyard" (The Final Days), the count defined by the alternative's own tail.
_ABILITY_THOSE_TOKENS_ALTERNATIVE_RE = re.compile(
    rf"^create (?P<count>{COUNT}|X) of those tokens(?P<where>, where X is .+)?$", re.IGNORECASE
)
_ABILITY_BASE_TOKEN_RE = re.compile(
    rf"^create (?P<count>{COUNT}) (?P<desc>.+?) tokens?(?P<tail>\b.*)$", re.IGNORECASE
)


def _ability_instead_alternative_text(base: str, alternative: str) -> str | None:
    """The alternative rewritten to say in full what it elides or names by
    back-reference to `base` (CR 614.1a replaces the base instruction; the
    target stays the one announced, CR 601.2c/603.3c), or None when it is
    none of the shapes read."""
    alternative = alternative.strip()
    if elided := _ABILITY_ELIDED_DAMAGE_ALTERNATIVE_RE.fullmatch(alternative):
        amounts = list(_ABILITY_BASE_DAMAGE_AMOUNT_RE.finditer(base))
        if len(amounts) != 1:
            return None
        found = amounts[0]
        return f"{base[: found.start('n')]}{elided.group('m')}{base[found.end('n') :]}"
    if those := _ABILITY_THOSE_TOKENS_ALTERNATIVE_RE.fullmatch(alternative):
        token = _ABILITY_BASE_TOKEN_RE.fullmatch(base.strip())
        if token is None:
            return None
        tail = token.group("tail").strip()
        # "those tokens" are the base's tokens, quoted ability included
        # (Anax's Satyr "with "This token can't block."").
        if tail and not re.fullmatch(r'with "[^"]+"', tail):
            return None
        return " ".join(
            f"create {those.group('count')} {token.group('desc')} tokens {tail}".split()
        ) + (those.group("where") or "")
    return _anaphoric_target_substitution(base, alternative)


def _ability_instead_branch_effect(text: str) -> AbilityEffect | None:
    """One branch of an ability's base-or-alternative pair as its own
    instruction: the ordinary clause reader, or the untimed control change
    ("Gain control of target creature", CR 611.2a's indefinite duration) it
    does not read."""
    from ..control_change import parse_gain_control_untimed_clause

    return parse_mixed_effect(text) or parse_gain_control_untimed_clause(text)


#: "it deals 1 damage to target creature defending player controls. If that
#: creature is a Zombie, this creature deals 2 damage to it instead."
#: (Purifying Dragon) - the base damage, replaced whole (CR 614.1a, CR 608.2c)
#: by a larger amount when the one target has a subtype or card type, read off
#: the computed board (CR 613.5) as the ability resolves. One damage event,
#: never both. The source of the alternative must be the base's own (CR 700.7:
#: "it" and "this creature" both name it).
_DAMAGE_INSTEAD_IF_TARGET_QUALITY_RE = re.compile(
    rf"^(?P<subject>it|this creature|this permanent) deals (?P<n>{COUNT}) damage to "
    r"(?P<phrase>target [^.]+?)\.\s*"
    r"if (?:that creature|that permanent|it) is an? (?P<quality>[a-z]+), "
    rf"(?:it|this creature|this permanent) deals (?P<m>{COUNT}) damage to "
    r"(?:it|that creature|that permanent) instead\.?$",
    re.IGNORECASE,
)


def _target_quality_test(word: str) -> Callable[["Game", CardState], bool] | None:
    """A one-word subtype (CR 205.3) or card type (CR 205.2a) as a test on a
    permanent's computed characteristics, or None for any other word."""
    card_type = next((t for t in Type if t.value.lower() == word.lower()), None)
    if card_type is not None:
        return lambda game, permanent: card_type in game.characteristics_of(permanent).types
    subtype = canonical_subtype(word)
    if subtype is None:
        return None
    return lambda game, permanent: (
        subtype in {each.lower() for each in game.characteristics_of(permanent).subtypes}
    )


@ABILITY_TEXT.rung("s16")
def _parse_damage_instead_if_target_quality_clause(text: str) -> AbilityEffect | None:
    """`_DAMAGE_INSTEAD_IF_TARGET_QUALITY_RE`'s shape; see the banner above."""
    stripped = " ".join(text.split())
    if " instead" not in stripped.lower():
        return None
    match = _DAMAGE_INSTEAD_IF_TARGET_QUALITY_RE.fullmatch(stripped)
    if match is None:
        return None
    has_quality = _target_quality_test(match.group("quality"))
    if has_quality is None:
        return None
    subject, phrase = match.group("subject"), match.group("phrase")
    base = parse_mixed_effect(f"{subject} deals {match.group('n')} damage to {phrase}.")
    larger = parse_mixed_effect(f"{subject} deals {match.group('m')} damage to {phrase}.")
    if base is None or larger is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        target = next((t for t in game.resolve_targets(ability) if isinstance(t, CardState)), None)
        if target is not None and target.zone is Zone.BATTLEFIELD and has_quality(game, target):
            larger(game, ability)
        else:
            base(game, ability)

    return effect


@ABILITY_TEXT.rung("s42")
def _parse_condition_instead_clause_for_ability(effect_text: str) -> AbilityEffect | None:
    """`_parse_condition_instead_clause`'s shape on an activated or triggered
    ability: "`<base>`. If `<condition>`, `<alternative>` instead." - Mine
    Worker's "{T}: You gain 1 life. If you control creatures named Power
    Plant Worker and Tower Worker, you gain 3 life instead." and Zimone,
    Quandrix Prodigy's "{4}, {T}: Draw a card. If you control eight or more
    lands, draw two cards instead."

    CR 614.1a: "instead" replaces the base instruction whole - exactly one of
    the two runs. The condition is `Game.condition_holds`', read as the
    ability resolves (CR 608.2h) about its controller, and gated at parse
    time by `condition_is_readable`, so an unread condition leaves the whole
    ability unread rather than guessed false. A base that is a continuous
    effect (Power Plant Worker's "+2/+2 until end of turn") is left to
    `_compose_layer_effect_with_remainder_for_ability`, which already reads
    its counter upgrade.

    An alternative that does not read on its own is read with what it elides
    or back-references filled in from the base (`_ability_instead_
    alternative_text`): Akoum Hellkite's "this creature deals 2 damage
    instead", Scepter of Empires' "It deals 3 damage instead", Crown of
    Empires' "Gain control of that creature instead", Throne of Empires'
    "Create five of those tokens instead". A condition naming an anaphor
    (Akoum Hellkite's "If that land is a Mountain") is read off the trigger's
    own event; with no event to name, it is a `ConditionalClauseNotice` and
    the base runs. CR 608.2b: with the one target illegal, neither branch
    resolves.
    """

    from ..conditions.objects import names_an_anaphor

    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _CONDITION_INSTEAD_RE.fullmatch(whole)
    if match is None:
        return None
    condition_text = (match.group("condition_leading") or match.group("condition_elided")).strip()
    if not _effect_condition_is_readable(condition_text, allow_anaphor=True):
        return None
    anaphoric = not _effect_condition_is_readable(condition_text)
    base_text = match.group("base").strip()
    if is_genuine_resolution_layer_sentence(_as_sentence(base_text)):
        return None
    alternative_text = (
        match.group("alternative_leading")
        or match.group("alternative_trailing")
        or match.group("alternative_elided")
    )
    assert alternative_text is not None
    alternative_text = alternative_text.strip()
    base = parse_mixed_effect(base_text)
    alternative = parse_mixed_effect(alternative_text)
    if base is None or alternative is None or anaphoric:
        rewritten = _ability_instead_alternative_text(base_text, alternative_text)
        if rewritten is None:
            return None
        base = _ability_instead_branch_effect(base_text)
        alternative = _ability_instead_branch_effect(rewritten)
        if base is None or alternative is None:
            return None
        resolves_anaphor = names_an_anaphor(condition_text)
    else:
        # Read whole on its own: the condition is asked exactly as before,
        # with no trigger context.
        resolves_anaphor = None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        controller = game.controller_of(ability).username
        held: bool | None
        if resolves_anaphor is None:
            held = game.condition_holds(controller, condition_text, source)
        else:
            event = getattr(ability, "event", None)
            if resolves_anaphor and event is None:
                held = None  # an anaphor with no trigger event to name
            else:
                held = game.condition_holds(
                    controller, condition_text, source, ability=ability, event=event
                )
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=ability.source_id, source_name=ability.source_name, text=whole
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        (alternative if held else base)(game, ability)

    return effect


#: "Separate all `<quality>` target player controls into two piles.
#: `<consequence>` all `<quality>` in the pile of that player's choice." -
#: CR 700.3's pile primitive, read whole across both sentences the way
#: every other "this way"/anaphoric rider in this module already is: the
#: second sentence's "the pile of their choice" names an object the first
#: sentence's own division created, not something readable on its own.
#:
#: **Two different players, two different questions** - confirmed against
#: Liliana of the Veil's own official ruling ("When Liliana's third ability
#: resolves, **you** put each permanent the player controls into one of the
#: two piles"): the first sentence's unattributed "Separate ..." is CR
#: 608.2c's own default - the resolving ability's *controller* - not the
#: named "target player" the second sentence goes on to single out. That
#: division is read the identical `CHOOSE_CARDS` way `SCRY`/`SURVEIL`
#: already read "which of these move" (`exact=False`, CR 700.3d's "a pile
#: can contain zero or more objects"): the controller names what goes in
#: pile one, and the complement among the same qualifying set is pile two.
#: The *target* player then picks a whole pile - `DecisionKind.CHOOSE_PILE`,
#: the plain-boolean shape `PUT_ON_TOP_OR_BOTTOM` already is for "exactly
#: two answers, neither a color/name/type" - and the named consequence
#: applies to every permanent in the pile they picked.
#:
#: Liliana of the Veil's own `-6` is the reported ability ("... That player
#: sacrifices all permanents in the pile of their choice."). Do or Die (real,
#: non-FRA, non-pool) is the off-set proof: the identical two-sentence shape,
#: narrowed to "creatures" rather than "permanents" and "Destroy" rather than
#: "sacrifices" - the consequence verb genuinely varies, which is why it is
#: its own captured alternative rather than folded into the shared regex.
#: Do or Die's own trailing "They can't be regenerated." is CR 608.2c's
#: rider modifying the destruction in front of it (CR 701.19c: regeneration
#: shields are not applied), captured as `no_regen` and passed through as
#: `Game.destroy(..., regeneration_allowed=False)`.
_SEPARATE_INTO_TWO_PILES_RE = re.compile(
    r"^separate all (?P<quality>.+?) target player controls into two piles\.?$",
    re.IGNORECASE,
)
_THAT_PLAYER_SACRIFICES_PILE_OF_CHOICE_RE = re.compile(
    r"^that player sacrifices all (?P<quality>.+?) in the pile of their choice\.?$",
    re.IGNORECASE,
)
_DESTROY_PILE_OF_CHOICE_RE = re.compile(
    r"^destroy all (?P<quality>.+?) in the pile of that player'?s choice\.?"
    r"(?P<no_regen>\s*they can'?t be regenerated\.?)?$",
    re.IGNORECASE,
)


def _parse_separate_into_two_piles_then_consequence_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEPARATE_INTO_TWO_PILES_RE`'s shape, paired with either
    `_THAT_PLAYER_SACRIFICES_PILE_OF_CHOICE_RE` or
    `_DESTROY_PILE_OF_CHOICE_RE` - see the banner above."""
    sentences = _plain_resolution_sentences(text)
    if len(sentences) < 2:
        return None
    separate_match = _SEPARATE_INTO_TWO_PILES_RE.fullmatch(sentences[0].strip())
    if separate_match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    rest = " ".join(sentence.strip() for sentence in sentences[1:] if sentence.strip())
    sacrifice_match = _THAT_PLAYER_SACRIFICES_PILE_OF_CHOICE_RE.fullmatch(rest)
    destroy_match = (
        None if sacrifice_match is not None else _DESTROY_PILE_OF_CHOICE_RE.fullmatch(rest)
    )
    consequence_match = sacrifice_match or destroy_match
    if consequence_match is None:
        return None
    quality = separate_match.group("quality").strip()
    requirement = permanent_description(quality)
    if requirement is None:
        return None
    verb = "sacrifice" if sacrifice_match is not None else "destroy"
    regeneration_allowed = destroy_match is None or destroy_match.group("no_regen") is None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        divider = game.controller_of(stack_object)
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(target.username)
                if requirement.rejects(permanent, target.username, game) is None
            ]
            if not candidates:
                continue
            # Step 1 (CR 700.3a/700.3d): the ability's own controller - not
            # the target - divides every qualifying permanent into exactly
            # one of two piles. "Pile one" is whatever they name here; the
            # complement among `candidates` is pile two.
            pile_one_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=divider.username,
                    prompt=f"separate {target.username}'s {quality} into pile one",
                    source=source,
                    amount=len(candidates),
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id_of(stack_object),
                    exact=False,
                )
            )
            pile_one_id_set = set(pile_one_ids)
            pile_one = [permanent for permanent in candidates if permanent.id in pile_one_id_set]
            pile_two = [
                permanent for permanent in candidates if permanent.id not in pile_one_id_set
            ]
            # Step 2: the target player - the one the card actually names for
            # this choice - picks a whole pile.
            wants_pile_one = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_PILE,
                    player=target.username,
                    prompt=f"choose a pile to {verb}",
                    source=source,
                    cards=tuple(permanent.id for permanent in pile_one),
                    source_id=source_id_of(stack_object),
                )
            )
            assert isinstance(wants_pile_one, bool)
            chosen = pile_one if wants_pile_one else pile_two
            for permanent in chosen:
                if permanent.zone is not Zone.BATTLEFIELD:
                    continue
                if verb == "sacrifice":
                    game.sacrifice(permanent)
                else:
                    game.destroy(permanent, regeneration_allowed=regeneration_allowed)

    return effect


def _choose_an_opponent(
    game: "Game", controller: Player, source: str, source_id: str | None
) -> Player | None:
    """ "An opponent" with no target and no other qualifier - CR 102.2's
    "the other player" already answers it alone in a two-player game
    (`Game.ask` never runs a one-option question, the same convention
    `_choose_target_of_enchant`'s own `CHOOSE_PLAYERS` branch already keeps);
    with more than one, the resolving spell or ability's own controller
    names which, since nothing on the card picks for them."""
    opponents = _opponents(game, controller.username)
    if not opponents:
        return None
    if len(opponents) == 1:
        return opponents[0]
    picked = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_PLAYERS,
            player=controller.username,
            prompt="choose an opponent",
            source=source,
            amount=1,
            players=tuple(player.username for player in opponents),
            source_id=source_id,
        )
    )
    assert isinstance(picked, tuple)
    return next((player for player in opponents if player.username == picked[0]), None)


def _choose_one_card(
    game: "Game",
    player: Player,
    candidates: Sequence[CardState],
    *,
    prompt: str,
    source: str | None,
    source_id: str | None,
) -> CardState:
    """One card from `candidates` (CR 608.2d): asked as a `CHOOSE_CARDS` when
    there is a choice, the lone candidate otherwise. Unscripted, the engine's
    `CHOOSE_CARDS` default: the last card offered."""
    if len(candidates) == 1:
        return candidates[0]
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=prompt,
            source=source,
            source_id=source_id,
            amount=1,
            exact=True,
            cards=tuple(state.id for state in candidates),
        )
    )
    assert isinstance(chosen_ids, tuple)
    return next(state for state in candidates if state.id == chosen_ids[0])


#: "Ante this artifact. If you do, put all other cards you own from the ante
#: into your graveyard, then draw a card." (Jeweled Bird) - CR 407.3's own
#: family: "A few cards have the text 'Remove this card from your deck before
#: playing if you're not playing for ante.' These are the only cards that can
#: add or remove cards from the ante zone or change a card's ownership."
#:
#: Read whole, ahead of `split_effect_clauses`, for the reason every "if you
#: do" shape in this module is: the consequence is conditional on the first
#: instruction actually happening, and a per-clause split would run it either
#: way.
_ANTE_SELF_IF_YOU_DO_RE = re.compile(
    r"^ante this (?:artifact|creature|enchantment|land|permanent)\.\s*"
    r"if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: The consequence half, as Jeweled Bird prints it, with an optional "then
#: <player clause>" tail read by `parse_clause_effect` rather than spelled out
#: here - so the draw is the same draw every other card in the pool gets.
_ANTE_ZONE_TO_GRAVEYARD_RE = re.compile(
    r"^put all other cards you own from the ante into your graveyard"
    r"(?:,?\s*then\s+(?P<then>.+?))?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s14")
def _parse_ante_self_if_you_do_clause(text: str) -> AbilityEffect | None:
    """Jeweled Bird's whole ability, read as one CR 608.2c instruction.

    CR 407.4: "To ante an object is to put that object into the ante zone from
    whichever zone it's currently in. The owner of an object is the only player
    who can ante that object." `Game.ante` answers whether the move actually
    happened, and that boolean is exactly what "If you do" hangs on: a Bird
    somebody else controls cannot be anted by them, so the ante fails and
    *nothing else in the ability happens* - DDR#666's stolen-Bird ruling, and
    the reason this is one parser rather than a clause each.

    CR 113.7a keeps the ability resolving even if its source has gone; there is
    then nothing to ante, so the condition is false and the rest is undone.
    """
    match = _ANTE_SELF_IF_YOU_DO_RE.fullmatch(text.strip())
    if match is None:
        return None
    consequence = _ANTE_ZONE_TO_GRAVEYARD_RE.fullmatch(match.group("consequence").strip())
    if consequence is None:
        return None
    tail = consequence.group("then")
    tail_effect = parse_clause_effect(tail) if tail else None
    if tail and tail_effect is None:
        # One unreadable clause fails the whole paragraph closed rather than
        # running the readable half beside it (CR 608.2c).
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        # CR 407.4's owner check lives in `Game.ante`; the player anteing is
        # the ability's controller, which is who activated it.
        if not game.ante(source, ability.controller):
            return
        player = game.player(ability.controller)
        for state in list(game.ante_zone):
            if state.id == source.id or state.owner != player.username:
                continue
            game.put_into_graveyard(state)
        if tail_effect is not None:
            tail_effect(game, player, ability.source_name, source_id_of(ability))

    return effect


#: "Choose a[n] <quality> card name." as a triggered ability's whole effect -
#: Petrified Hamlet's "When this land enters, choose a land card name." The
#: same CR 201.4/201.4a choice Pithing Needle's CR 614.12a "As this enters,
#: choose a card name" makes, but made as the trigger resolves (CR 608.2)
#: rather than before the permanent enters, and recorded on the same
#: `CardState.choice` - so every static reader of "the chosen name" (the
#: activation prohibition, the chosen-name groups in `machines/layers.py`)
#: reads it unchanged. The quality words are the ones `machines/replacement`'s
#: own "choose a <quality> card name" reads, judged by the same refusal.
_CHOOSE_A_CARD_NAME_EFFECT_RE = re.compile(
    r"^choose an? (?:(?P<quality>(?:non-?)?[a-z]+(?: (?:non-?)?[a-z]+)?) )?card name\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s3")
def _parse_choose_card_name_for_source_clause(text: str) -> AbilityEffect | None:
    """`_CHOOSE_A_CARD_NAME_EFFECT_RE`'s shape: ask the ability's controller
    for a card name, refuse one whose Oracle text does not match the printed
    characteristics (CR 201.4a), and record it on the ability's source while
    that source is still on the battlefield - a source that has left has no
    static ability left to read it (CR 604.2)."""
    match = _CHOOSE_A_CARD_NAME_EFFECT_RE.fullmatch(text.strip())
    if match is None:
        return None

    from ..replacement import _card_name_quality_refusal

    quality = (match.group("quality") or "").lower() or None
    noun = f"{quality} card name" if quality else "card name"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)
        value = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt=f"choose {with_indefinite_article(noun)}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                quality=ChoiceKind.CARD_NAME.value,
            )
        )
        assert isinstance(value, str)
        if quality is not None:
            refusal = _card_name_quality_refusal(value, quality)
            if refusal is not None:
                raise ValueError(f"{ability.source_name}: {refusal}")
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            source.choice = Choice(kind=ChoiceKind.CARD_NAME, value=value)

    return effect


#: The Stone Brain: "Choose a card name. Search target opponent's graveyard,
#: hand, and library for up to four cards with that name and exile them.
#: That player shuffles, then draws a card for each card exiled from their
#: hand this way." Read off the activated ability's own `effect` field
#: (`{2}, {T}, Exile The Stone Brain:` and the trailing "Activate only as a
#: sorcery." are both already stripped by `machines/abilities.py` before this
#: text is ever seen). The same instruction is a spell's whole text on Unmoored
#: Ego, and with its other printed wording on Ancient Vendetta ("Then that
#: player shuffles" with no draw), Lost Legacy (a nonartifact, nonland name,
#: "any number of" cards) and Cranial Extraction ("all cards").
_STONE_BRAIN_RE = re.compile(
    r"^choose an? (?:(?P<quality>[a-z, -]+?) )?card name\.\s*"
    r"search target (?P<who>opponent|player)'s graveyard, hand, and library for "
    rf"(?:up to (?P<cap>{COUNT}) cards?|(?P<every>any number of|all) cards) "
    r"with that name and exile them\.\s*"
    r"(?P<tail>that player shuffles, then draws a card for each card exiled from "
    r"their hand this way|then that player shuffles)\.?$",
    re.IGNORECASE,
)

#: Surgical Extraction: "Choose target card in a graveyard other than a basic
#: land card. Search its owner's graveyard, hand, and library for any number
#: of cards with the same name as that card and exile them. Then that player
#: shuffles." The leading "({B/P} can be paid with either {B} or 2 life.)"
#: reminder line is already gone by the time this runs - `_strip_non_effect_
#: preamble`'s own `_REMINDER_LINE_RE` strips a leading reminder line for
#: every spell, Dismember and Mutagenic Growth among them.
_SURGICAL_EXTRACTION_RE = re.compile(
    r"^choose target card in a graveyard other than a basic land card\.\s*"
    r"search its owner's graveyard, hand, and library for any number of cards "
    r"with the same name as that card and exile them\.\s*"
    r"then that player shuffles\.?$",
    re.IGNORECASE,
)


def _parse_stone_brain_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_STONE_BRAIN_RE`'s shape - an ability (The Stone Brain) or a
    spell (Unmoored Ego, Lost Legacy, Ancient Vendetta). CR 701.23a: the
    search of each of the three zones is its own single-zone search
    (`_search_and_exile_matching_name`); CR 701.24a / 701.23d: the targeted
    player's shuffle, and the draw for what left their hand, follow."""
    match = _STONE_BRAIN_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    who = match.group("who").lower()
    if not _targets_understood(f"target {who}", allow_player_targets=True):
        return None
    cap = parse_count(match.group("cap")) if match.group("cap") else None
    if match.group("cap") and cap is None:
        return None
    quality = (match.group("quality") or "").replace(",", "").strip().lower() or None
    draws = match.group("tail").lower().startswith("that player shuffles, then draws")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = getattr(stack_object, "source_name", None) or stack_object.name
        target_player = next(
            (target for target in game.resolve_targets(stack_object) if isinstance(target, Player)),
            None,
        )
        if target_player is None:
            return
        name = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt=f"choose {quality + ' ' if quality else ''}card name",
                source=source,
                source_id=source_id_of(stack_object),
                quality=ChoiceKind.CARD_NAME.value,
            )
        )
        assert isinstance(name, str)
        if quality is not None:
            from ..replacement import _card_name_quality_refusal

            refusal = _card_name_quality_refusal(name, quality)
            if refusal is not None:
                raise ValueError(f"{source}: {refusal}")
        _exiled, exiled_from_hand = _search_and_exile_matching_name(
            game,
            target_player,
            name,
            chooser=controller,
            cap=cap,
            source=source,
            source_id=source_id_of(stack_object),
        )
        if draws and exiled_from_hand:
            game.draw_cards(target_player.username, exiled_from_hand)

    return effect


def _parse_surgical_extraction_clause(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SURGICAL_EXTRACTION_RE`'s shape. Spell-only (`for_spell=True`):
    Surgical Extraction is the only card in the pool printing it, and it is a
    spell (an instant); the name comes off the target itself, not off a
    `CHOOSE_A_QUALITY` question, so nothing here needs an ability's own
    `source_name`/`controller` machinery either way.
    """
    if not for_spell:
        return None
    match = _SURGICAL_EXTRACTION_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    if not _targets_understood(
        "target card in a graveyard other than a basic land card",
        count_agnostic=False,
        battlefield_only=False,
    ):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        spell = stack_object
        assert isinstance(spell, CardState)
        controller = game.controller_of(spell)
        target_card = next(
            (target for target in game.resolve_targets(spell) if isinstance(target, CardState)),
            None,
        )
        if target_card is None or target_card.owner is None:
            return
        owner = game.player(target_card.owner)
        _search_and_exile_matching_name(
            game,
            owner,
            target_card.name,
            chooser=controller,
            cap=None,
            source=spell.name,
            source_id=source_id_of(spell),
        )

    return effect


def _parse_choose_name_search_and_exile_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """Try `_parse_stone_brain_clause`, then `_parse_surgical_extraction_
    clause`, against the *whole*, unsplit effect text - see this section's
    own module comment for why a per-clause dispatch cannot read either
    card's own "graveyard, hand, and library"/"with that name and exile
    them" wording.
    """
    stone_brain = _parse_stone_brain_clause(text, for_spell=for_spell)
    if stone_brain is not None:
        return stone_brain
    return _parse_surgical_extraction_clause(text, for_spell=for_spell)


#: A plain CR 608.2c conditional instruction with no "instead" anywhere - a
#: board condition read by `Game.condition_holds`, in either printed word
#: order: the condition first, "If `<condition>`, `<consequence>`." (Giant's
#: Ire: "Giant's Ire deals 4 damage to target player or planeswalker. If you
#: control a Giant, draw a card." - once `_CLAUSE_SEPARATOR` has already cut
#: the sentence apart at its own period, this is the second clause on its
#: own; Peppersmoke: "Target creature gets -1/-1 until end of turn. If you
#: control a Faerie, draw a card." is the same shape), or the condition last,
#: "`<consequence>` if `<condition>`." (Veil of Summer's own "Draw a card if
#: an opponent has cast a blue or black spell this turn." is this order,
#: standing alone as its own clause - the reader T5 builds on top of this
#: one).
#:
#: Tried only this late in `_parse_mixed_clause`'s own ladder - after every
#: more specific reader that already recognises an "if" of its own, `draw_
#: if_control` (Ral, Monsoon Mage's colour-only shape) included, so neither
#: keeps a different winner - and, for the whole-text chains that reach it
#: at all, only once `_parse_condition_instead_clause` has already failed to
#: read the same text as an "instead" replacement (CR 614.1a). A target's
#: own restriction of this exact shape ("Destroy target creature if it has
#: mana value 2 or less.", Fatal Push) never reaches here either: `machines/
#: targeting.py`'s own `profile_for_text` already reads a trailing "if it
#: has ..." comparison as part of the *target phrase*, so `_parse_targeted_
#: clause` - tried first in `_parse_mixed_clause` - already consumes the
#: whole clause before this one ever sees it.
_LEADING_IF_CLAUSE_RE = re.compile(r"^if (?P<condition>.+?), (?P<consequence>.+)$", re.IGNORECASE)
_TRAILING_IF_CLAUSE_RE = re.compile(r"^(?P<consequence>.+?) if (?P<condition>.+)$", re.IGNORECASE)


#: "If target player has exactly 10 life, ..." (Hidetsugu's Second Rite): a
#: condition about the spell's own targeted player, checked as the spell
#: resolves (CR 608.2c) against the player it chose (CR 115.1a), not against
#: the caster. The shared condition readers answer "you ..." for a named
#: controller, so the clause is read as the target's own "you have ..." and
#: asked with the target as that controller.
_TARGET_PLAYER_CONDITION_RE = re.compile(
    r"^target (?:player|opponent) (?P<verb>has|have|controls?) (?P<rest>.+)$", re.IGNORECASE
)


def _target_player_condition(condition: str) -> str | None:
    """`_TARGET_PLAYER_CONDITION_RE`'s condition rewritten as the targeted
    player's own "you have ..."/"you control ...", or `None`."""
    if not condition.lower().startswith("target "):
        return None
    match = _TARGET_PLAYER_CONDITION_RE.fullmatch(condition.strip())
    if match is None:
        return None
    verb = "have" if match.group("verb").lower().startswith("ha") else "control"
    return f"you {verb} {match.group('rest')}"


def _target_players_hold(
    game: "Game", spell: "StackObject", condition: str, source: "StackObject"
) -> bool | None:
    """`condition` (a `_target_player_condition` rewrite) for every player the
    resolving spell still legally targets (CR 608.2b); `False` when it has
    none, `None` when the shared reader cannot answer it."""
    players = [target for target in game.resolve_targets(spell) if isinstance(target, Player)]
    if not players:
        return False
    answers = [game.condition_holds(player.username, condition, source) for player in players]
    if any(answer is None for answer in answers):
        return None
    return all(answers)


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_condition_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_LEADING_IF_CLAUSE_RE`/`_TRAILING_IF_CLAUSE_RE`'s shape - see the
    banner above for the two word orders and why this is tried this late.

    `condition_is_readable` gates the parse itself: a condition this engine
    does not read leaves the *whole* clause unread (CR 608.2c), not silently
    run as though it were false. The rare case `Game.condition_holds` still
    answers `None` at resolution despite the shape reading as recognised at
    parse time (an inner count or quality word this engine does not know) is
    recorded as a `ConditionalClauseNotice` instead, the same class `_parse_
    condition_instead_clause` uses for its own equivalent case.
    """

    stripped = clause.strip()
    leading = _LEADING_IF_CLAUSE_RE.fullmatch(stripped)
    if leading is not None:
        condition_text = leading.group("condition").strip()
        # "If `<condition>`, also `<consequence>`" (Moment of Glory's
        # cast-from-a-graveyard rider): "also" marks the instruction as
        # additional to the ones before it (CR 608.2c), which is already
        # what running it after them means - it names no rule of its own.
        consequence_text = re.sub(
            r"^also\s+", "", leading.group("consequence").strip(), flags=re.IGNORECASE
        )
    else:
        trailing = _TRAILING_IF_CLAUSE_RE.fullmatch(stripped)
        if trailing is None:
            return None
        condition_text = trailing.group("condition").strip()
        consequence_text = trailing.group("consequence").strip()
    about_target = _target_player_condition(condition_text) if for_spell else None
    if not _effect_condition_is_readable(
        about_target if about_target is not None else condition_text,
        allow_anaphor=not for_spell,
    ):
        return None
    consequence = (
        parse_mixed_effect_for_spell(consequence_text)
        if for_spell
        else parse_mixed_effect(consequence_text)
    )
    if consequence is None:
        return None
    return _gated_effect(condition_text, about_target, consequence, stripped, for_spell=for_spell)


def _gated_effect(
    condition_text: str,
    about_target: str | None,
    consequence: TargetedClause,
    printed: str,
    *,
    for_spell: bool,
) -> TargetedClause:
    """`consequence`, run only when `condition_text` holds as the spell or
    ability resolves (CR 608.2c) - `_parse_condition_clause`'s resolution
    half, shared with `_parse_gated_optional_cost_pair_clauses`."""

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.source(game) if is_ability(stack_object) else stack_object
        if for_spell and about_target is not None:
            held = _target_players_hold(game, stack_object, about_target, source)
        elif for_spell:
            held = game.condition_holds(controller.username, condition_text, source)
        else:
            # A triggered ability: thread its own trigger event through, the
            # same way `intervening_if_answer` already does for the
            # intervening "if" this is not - CR 603.2's event, not the
            # source's own state, is what an anaphoric "it"/"that creature"
            # here means (`_effect_condition_is_readable`'s own docstring).
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
                text=printed,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if held:
            consequence(game, stack_object)

    return effect


#: "If `<condition>`, you may `<optional cost>`. If you do, `<consequence>`." -
#: Take Out the Trash's "If you control a Raccoon, you may discard a card. If
#: you do, draw a card." The leading gate (CR 608.2c, checked as the spell or
#: ability resolves) covers the whole optional-cost-then-"if you do" pair: with
#: the condition false the player is never offered the cost, so nothing is
#: discarded and nothing is drawn (CR 608.2d offers only choices that exist).
#: The pair itself is whatever the ordinary clause pipeline already reads as
#: "you may `<cost>`. If you do, `<consequence>`." (discard, sacrifice, pay), so
#: the gate adds only the condition.
_GATED_MAY_SENTENCE_RE = re.compile(
    r"^if (?P<condition>[^,]+?), (?P<rest>you may .+?)\.?$", re.IGNORECASE
)
_IF_YOU_DO_SENTENCE_RE = re.compile(r"^if you do,", re.IGNORECASE)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_gated_optional_cost_pair_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`_GATED_MAY_SENTENCE_RE`'s sentence plus the "If you do," sentence after
    it, among `text`'s sentences; see the banner above. The pair is read before
    the clause split because the split would cut the gate off its own "if you
    do" (`_clauses_around_sentences`)."""
    lowered = text.lower()
    if ", you may " not in lowered or "if you do," not in lowered:
        return None

    def reader(sentences: list[str], index: int) -> tuple[int, TargetedClause] | None:
        if index + 1 >= len(sentences):
            return None
        gate = _GATED_MAY_SENTENCE_RE.fullmatch(sentences[index].strip())
        if gate is None or _IF_YOU_DO_SENTENCE_RE.match(sentences[index + 1].strip()) is None:
            return None
        condition_text = gate.group("condition").strip()
        about_target = _target_player_condition(condition_text) if for_spell else None
        if not _effect_condition_is_readable(
            about_target if about_target is not None else condition_text,
            allow_anaphor=not for_spell,
        ):
            return None
        pair = _parse_mixed_clauses(
            f"{gate.group('rest').strip()}. {sentences[index + 1].strip()}", for_spell=for_spell
        )
        if pair is None:
            return None

        def consequence(game: "Game", stack_object: "StackObject") -> None:
            for clause in pair:
                clause(game, stack_object)

        printed = f"{sentences[index].strip()} {sentences[index + 1].strip()}"
        return 2, _gated_effect(
            condition_text, about_target, consequence, printed, for_spell=for_spell
        )

    return _clauses_around_sentences(text, reader, for_spell=for_spell)


#: Two independently gated instructions in one sentence, joined by "and":
#: "`<A>` if `<C1>` and `<B>` if `<C2>`." - Firespout's "deals 3 damage to
#: each creature without flying if {R} was spent to cast this spell and 3
#: damage to each creature with flying if {G} was spent to cast this spell",
#: Moonhold's, Repel Intruders'. The reminder "(Do both if {R}{G} was
#: spent.)" is CR 608.2c restated (each instruction is checked on its own as
#: it is followed; neither gate reads the other) and is already stripped as
#: reminder text. The bare "and" is what `split_effect_clauses` would cut
#: into two fragments, the second of which is no instruction at all once its
#: subject and verb are elided.
_GATED_PAIR_SENTENCE_RE = re.compile(r" if .+ and .+ if ", re.IGNORECASE)


def _elided_head(first: str, second: str) -> str | None:
    """The words `first` spends before the point where `second` begins -
    "Firespout deals " for the "3 damage to each creature with flying" that
    follows its own "3 damage to ..." - found as the first word of `second`
    inside `first`, so the elided subject and verb are spliced back rather
    than invented. `None` when `second`'s first word is not in `first`."""
    word = second.split(" ", 1)[0]
    index = first.lower().find(f" {word.lower()} ")
    return first[: index + 1] if index > 0 else None


def _split_gated_pair(sentence: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """`_GATED_PAIR_SENTENCE_RE`'s sentence read as two `_parse_condition_
    clause` clauses (each half is a trailing-if instruction on its own, the
    second with the first's subject and verb spliced back when it elides
    them), or `None` when it is not that shape or either half does not read."""
    stripped = sentence.strip().rstrip(".")
    if _GATED_PAIR_SENTENCE_RE.search(stripped) is None:
        return None
    parts = stripped.split(" and ")
    for cut in range(1, len(parts)):
        left, right = " and ".join(parts[:cut]), " and ".join(parts[cut:])
        if " if " not in left or " if " not in right or left.lower().startswith("if "):
            continue
        first = _parse_condition_clause(left, for_spell=for_spell)
        if first is None:
            continue
        second = _parse_condition_clause(right, for_spell=for_spell)
        if second is None:
            head = _elided_head(left.split(" if ", 1)[0], right)
            second = (
                _parse_condition_clause(f"{head}{right}", for_spell=for_spell)
                if head is not None
                else None
            )
        if second is not None:
            return [first, second]
    return None


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_gated_pair_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every sentence of `text`, those of `_GATED_PAIR_SENTENCE_RE`'s shape
    through `_split_gated_pair`, the rest one by one through the ordinary
    pipeline (the `_parse_shared_subject_clauses` pattern); `None` when no
    sentence is such a pair or any sentence fails to read (CR 608.2c: no
    half-run instruction)."""
    lowered = text.lower()
    if " if " not in lowered or " and " not in lowered:
        return None
    sentences = _plain_resolution_sentences(text)
    pairs = [_split_gated_pair(sentence, for_spell=for_spell) for sentence in sentences]
    if not any(pairs):
        return None
    effects: list[TargetedClause] = []
    for sentence, pair in zip(sentences, pairs, strict=True):
        if pair is not None:
            effects.extend(pair)
            continue
        rest = _parse_mixed_clauses(sentence, for_spell=for_spell)
        if rest is None:
            return None
        effects.extend(rest)
    return effects


#: "Choose up to X creatures and/or planeswalkers you control, where X is the
#: number of times this spell was kicked. Those permanents phase out."
#: (Temporal Firestorm; `_THOSE_PREDICATE_RE` is the one predicate this reads,
#: phasing out, the only one a printing in the pool carries) - a choice made as the
#: spell resolves (CR 608.2d), of permanents the controller controls, that the
#: next sentence refers back to (CR 608.2c: later text may modify the meaning
#: of earlier text). Nothing is *targeted* (CR 115.1): the chosen permanents
#: are picked among those that exist as the spell resolves, so shroud or
#: protection never stops the choice, and nothing is rechecked afterwards
#: beyond the permanent still being on the battlefield.
_CHOOSE_YOU_CONTROL_RE = re.compile(
    rf"^choose (?:(?P<upto>up to) )?(?P<count>x|a|an|{COUNT}) (?P<group>[a-z, /]+?) you control"
    r"(?P<kicks>, where x is the number of times this spell was kicked)?\.?$",
    re.IGNORECASE,
)
_THOSE_PREDICATE_RE = re.compile(
    r"^(?:those|each of those) (?:permanents|creatures|planeswalkers|artifacts|enchantments|"
    r"lands) phase out\.?$",
    re.IGNORECASE,
)


def _chosen_group_pair(first: str, second: str) -> "Callable[[Game, StackObject], None] | None":
    """`_CHOOSE_YOU_CONTROL_RE`'s sentence and the `_THOSE_PREDICATE_RE`
    sentence that follows it as one resolution step, or `None` when the pair
    is not that shape or its predicate is not one this reads."""
    lowered = first.lower()
    if " you control" not in lowered or not lowered.startswith("choose "):
        return None
    chosen = _CHOOSE_YOU_CONTROL_RE.fullmatch(first.strip())
    predicate = _THOSE_PREDICATE_RE.fullmatch(second.strip())
    if chosen is None or predicate is None:
        return None
    group = _parse_mass_type_qualifier(chosen.group("group").replace("and/or", "or"))
    if group is None:
        return None
    word = chosen.group("count").lower()
    per_kick = word == "x"
    if per_kick and chosen.group("kicks") is None:
        return None  # an X the card does not define here
    fixed = 1 if word in ("a", "an") else None if per_kick else parse_count(word)
    if fixed is None and not per_kick:
        return None
    up_to = chosen.group("upto") is not None

    def step(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        limit = game.cast_record(stack_object).kicked if per_kick else fixed
        board = game.computed_board()
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller)
            if group(board.of(permanent))
        ]
        assert limit is not None
        limit = min(limit, len(candidates))
        if limit <= 0:
            return
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose {'up to ' if up_to else ''}{limit} permanent(s) you control",
                source=source_name,
                source_id=source_id_of(stack_object),
                amount=limit,
                exact=not up_to,
                default_cards=() if up_to else tuple(c.id for c in candidates[:limit]),
                cards=tuple(candidate.id for candidate in candidates),
            )
        )
        by_id = {candidate.id: candidate for candidate in candidates}
        picked = [by_id[card_id] for card_id in ids]
        for permanent in picked:
            if permanent.zone is Zone.BATTLEFIELD:
                game.phase_out(permanent)  # CR 702.26a

    return step


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_choose_then_those_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every sentence of `text`, a `_CHOOSE_YOU_CONTROL_RE` sentence and the
    `_THOSE_PREDICATE_RE` one after it read together by `_chosen_group_pair`,
    the rest one by one through the ordinary pipeline; `None` when no
    sentence pair is that shape or any other sentence fails to read (CR
    608.2c: no half-run instruction)."""
    lowered = text.lower()
    if "choose " not in lowered or " you control" not in lowered or "those " not in lowered:
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    effects: list[TargetedClause] = []
    found = False
    index = 0
    while index < len(sentences):
        pair = (
            _chosen_group_pair(sentences[index], sentences[index + 1])
            if index + 1 < len(sentences)
            else None
        )
        if pair is not None:
            effects.append(pair)
            found = True
            index += 2
            continue
        rest = _parse_mixed_clauses(sentences[index], for_spell=for_spell)
        if rest is None:
            return None
        effects.extend(rest)
        index += 1
    return effects if found else None


#: "`<instruction on target X>`. [If `<condition>`, ]`<source>` deals N damage
#: to that creature's controller." where the instruction is not a destroy
#: (`merges._merge_destroy_then_damage_controller_clauses` owns that one) -
#: Blur of Blades' -1/-1 counter, Sonic Assault's tap, Searing Barrage's and
#: Draconic Roar's own damage with an adamant / revealed-or-controlled gate.
#: CR 608.2c: the second sentence is one instruction with the first, "that
#: creature" being the first sentence's only target (the second
#: sentence names no target of its own). CR 608.2h: the controller is read
#: from the target before the first instruction can change it, and the
#: damage is dealt whether or not the first instruction did anything to a
#: still-legal target; CR 608.2b: a target that is illegal on resolution
#: contributes no controller, so nothing at all happens to anyone.
_TARGET_THEN_CONTROLLER_DAMAGE_RE = re.compile(
    rf"^(?:if (?P<condition>[^,]+), )?(?P<subject>[^,]+?) deals (?P<n>{COUNT}) damage to "
    r"that (?P<noun>creature|permanent|planeswalker|artifact|enchantment|land)'s controller\.?$",
    re.IGNORECASE,
)


def _single_target_antecedent(sentence: str) -> bool:
    """The sentence names exactly one object target and is not a destroy."""
    lowered = sentence.lower()
    return (
        lowered.count("target ") == 1
        and "up to" not in lowered
        and "each " not in lowered
        and not lowered.lstrip().startswith("destroy ")
    )


def _target_then_controller_damage_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    match = _TARGET_THEN_CONTROLLER_DAMAGE_RE.fullmatch(second.strip())
    if match is None or "target" in match.group("subject").lower():
        return None
    if not _single_target_antecedent(first):
        return None
    condition = match.group("condition")
    if condition is not None and not _effect_condition_is_readable(condition):
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    antecedent = _parse_mixed_clauses(first, for_spell=for_spell)
    if antecedent is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controllers = [
            game.controller_of(target).username
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ][:1]
        for step in antecedent:
            step(game, stack_object)
        if not controllers:
            return
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        )
        if condition is not None:
            holder = game.controller_of(stack_object).username
            if game.condition_holds(holder, condition, source) is not True:
                return
        game.deal_damage(game.player(controllers[0]), amount, source=source)

    return effect


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_target_then_controller_damage_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """Every sentence of `text`, a sentence naming one target and the
    `_TARGET_THEN_CONTROLLER_DAMAGE_RE` sentence after it read together, the
    rest one by one through the ordinary pipeline; `None` when no pair is that
    shape or any other sentence fails to read (CR 608.2c: no half-run
    instruction)."""
    lowered = text.lower()
    if "'s controller" not in lowered or " damage to that " not in lowered:
        return None
    sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if len(sentences) < 2:
        return None
    effects: list[TargetedClause] = []
    found = False
    index = 0
    while index < len(sentences):
        pair = (
            _target_then_controller_damage_pair(
                sentences[index], sentences[index + 1], for_spell=for_spell
            )
            if index + 1 < len(sentences)
            else None
        )
        if pair is not None:
            effects.append(pair)
            found = True
            index += 2
            continue
        rest = _parse_mixed_clauses(sentences[index], for_spell=for_spell)
        if rest is None:
            return None
        effects.extend(rest)
        index += 1
    return effects if found else None


#: "`<source>` deals N damage to you." as one clause of a spell or ability -
#: Sarkhan's Rage's "If you control no Dragons, Sarkhan's Rage deals 2 damage
#: to you.", whose condition `_parse_condition_clause` reads once this inner
#: instruction reads. "You" is the controller of the resolving spell or
#: ability (CR 120.3a, CR 109.5); the source is the spell itself or the
#: ability's source as it last existed (CR 120.1, CR 608.2h).
_DAMAGE_TO_YOU_CLAUSE_RE = re.compile(
    rf"^(?P<subject>[^.,]+?) deals (?P<n>{COUNT}) damage to you\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s36", for_spell=FORWARD)
def _parse_damage_to_you_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_DAMAGE_TO_YOU_CLAUSE_RE`'s shape, or `None`."""
    if " damage to you" not in clause.lower():
        return None
    match = _DAMAGE_TO_YOU_CLAUSE_RE.fullmatch(clause.strip())
    if match is None or "target" in match.group("subject").lower():
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        )
        game.deal_damage(game.controller_of(stack_object), amount, source=source)

    return effect


def _parse_optional_mixed_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "You may <clause>", where `<clause>` is any shape `_parse_mixed_clause`
    reads - Vengevine's "you may return this card from your graveyard to the
    battlefield".

    `_parse_optional_player_clause` already does this for the plain-player
    vocabulary, but that vocabulary is only life totals, draws and mills; a
    "you may" over a *board* instruction had nowhere to go, which is why
    Vengevine's trigger reached the stack correctly and then resolved as
    `None`.

    CR 608.2d: "if a cost or effect allows a player to choose to do something
    ... that player is not required to make that choice unless the effect
    specifically says the player must." Fail-closed as everywhere else - a
    body this engine cannot read is not turned into a question it could not
    then carry out.
    """
    match = _YOU_MAY_RE.match(clause.strip())
    if match is None:
        return None
    body = match.group("clause").strip().rstrip(".")
    from ..ep02_r2_counted_permanents import have_clause_as_plain

    inner = _parse_mixed_clause(have_clause_as_plain(body) or body, for_spell=for_spell)
    if inner is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if game.may(player, body, source=source, source_id=source_id_of(stack_object)):
            inner(game, stack_object)

    return effect


#: "you may exile it. When you do, `<consequence>`." on a dies trigger -
#: Paramecia Coloniex's own shape (TMT), the reflexive (CR 603.12) twin of
#: `_parse_exile_dead_self_clause`'s unconditional "exile it". "It" is CR
#: 603.10a's look-back to the ability's own source, resolved by
#: `_dead_self_found` exactly as that reader's own docstring already
#: explains for the plain form.
_REFLEXIVE_MAY_EXILE_DEAD_SELF_RE = re.compile(
    r"^you may exile it\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s37", for_spell=False)
def _parse_reflexive_may_exile_dead_self_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_REFLEXIVE_MAY_EXILE_DEAD_SELF_RE`'s shape, or `None`.

    The consequence is parsed once, up front (`reflexive_consequence_
    effect`), so an unreadable one fails the whole ability closed before the
    exile happens - the same guard `_parse_reflexive_sacrifice_clause`
    already applies to its own "you may sacrifice ... When you do, ..."
    shape. CR 603.12: the reflexive ability is created *after* the exile
    really happens, with no target of its own until it goes on the stack
    (CR 603.3d) - Paramecia Coloniex's own "put target creature card from
    your graveyard on top of your library" announces that target then, never
    off anything the dies trigger itself chose.

    Ability-only: nothing in the pool prints this on a spell, and there is no
    "it" for a resolving spell to look back at once its own resolution has
    already moved on.
    """
    if for_spell:
        return None
    match = _REFLEXIVE_MAY_EXILE_DEAD_SELF_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    consequence_text = match.group("consequence").strip()
    if reflexive_consequence_effect(consequence_text) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = _dead_self_found(game, ability)
        if source is None:
            return
        player = game.controller_of(ability)
        source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        if not game.may(
            player, f"exile {source.name}", source=source_name, source_id=source_id_of(ability)
        ):
            return
        exiled = game.exile_permanent(source)
        if exiled.zone is not Zone.EXILE:
            return
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "Choose exactly two creatures you control. You draw X cards and the
#: chosen creatures get +X/+X and gain trample until end of turn, where X is
#: the difference between the chosen creatures' powers." - Spry and Mighty's
#: own whole effect. CR 608.2d's choice is not targeting (CR 601.2c) - the two
#: creatures are picked as the ability resolves, so one already tapped,
#: already gone, or that changed control since the spell was cast is still a
#: legal pick - which is why this is its own `Decision` (`DecisionKind.
#: CHOOSE_CARDS`, the identical "choose exactly two" shape `_parse_reveal_
#: two_outside_opponent_chooses_clause` already uses for a different pool of
#: candidates) rather than read through `_targets_understood`'s targeting
#: machinery at all. "The difference between" the two powers (not "its power
#: and toughness", `Doran`'s own shape reusing `amount_expression`'s "the
#: difference between its power and toughness" term) is read off two
#: *different* objects, so this computes it directly rather than through that
#: single-object term - the greater power minus the lesser, never signed,
#: read once as the ability resolves (CR 608.2h) and locked in for the pump,
#: the draw, and the trample grant alike, even when it comes out to zero
#: (trample and the pump both still apply; a draw of zero cards is simply
#: nothing to draw).
_CHOOSE_EXACTLY_TWO_DRAW_PUMP_TRAMPLE_RE = re.compile(
    r"^choose exactly two creatures you control\.\s*"
    r"you draw x cards and the chosen creatures get \+x/\+x and gain trample "
    r"until end of turn, where x is the difference between the chosen "
    r"creatures'? powers\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_choose_exactly_two_draw_pump_trample_clause(
    effect_text: str, *, for_spell: bool
) -> Effect | None:
    """`_CHOOSE_EXACTLY_TWO_DRAW_PUMP_TRAMPLE_RE`'s shape, or `None`. Never an
    ability's own shape - nothing in the pool prints this off a permanent."""
    if not for_spell:
        return None
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    if _CHOOSE_EXACTLY_TWO_DRAW_PUMP_TRAMPLE_RE.fullmatch(whole) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        board = game.computed_board()
        candidates = [
            state
            for state in game.permanents_controlled_by(controller.username)
            if board.of(state).is_creature
        ]
        if len(candidates) < 2:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose exactly two creatures you control",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=2,
                exact=True,
                cards=tuple(state.id for state in candidates),
                card_labels=tuple(state.name for state in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        if len(chosen_ids) < 2:
            return
        by_id = {state.id: state for state in candidates}
        chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        if len(chosen) < 2:
            return
        # CR 608.2h: read once, right now - the board as it stands when this
        # ability resolves, not re-read for the pump or the draw below.
        powers = [board.of(state).numeric_power for state in chosen]
        amount = abs(powers[0] - powers[1])
        if amount > 0:
            game.draw_cards(controller, amount)
        store = continuous_effects(game)
        for state in chosen:
            if amount > 0:
                store.add(
                    ContinuousEffect(
                        description=f"{spell.name}: {state.name} gets {amount:+d}/{amount:+d}",
                        layer=Layer.POWER_TOUGHNESS,
                        sublayer=Sublayer.MODIFY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=_only(state.id),
                        modification=modify_power_toughness(amount, amount),
                    )
                )
            store.add(
                ContinuousEffect(
                    description=f"{spell.name}: {state.name} gains trample until end of turn",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    selector=_only(state.id),
                    modification=grant_ability("trample"),
                )
            )

    return effect


#: "If `<condition>`, you win the game." (CR 104.2b) - Fblthp, Impossibly
#: Lost's own "If your library has no cards in it, you win the game."
#: `<condition>` is read the same general way `Game.condition_holds` already
#: reads an activated ability's "Activate only if ..." restriction and a
#: modal "If ..., choose N instead" - a new `_CONDITION_LIBRARY_EMPTY_RE`
#: branch was added there alongside this parser rather than duplicating a
#: second copy of empty-library reading here, so a future card stating the
#: identical win off a different, already-read condition reads for free too.
_IF_CONDITION_YOU_WIN_THE_GAME_RE = re.compile(
    r"^if (?P<condition>.+?),\s*you win the game\.?$", re.IGNORECASE
)

#: "You win the game if `<condition>`." - the same CR 104.2b statement with
#: its condition trailing (Promising Stairs' "You win the game if there are
#: eight or more different names among unlocked doors of Rooms you
#: control."). Unlike the leading form, an unreadable condition is refused
#: at parse time, so a card whose condition nothing reads stays silent
#: rather than reading as handled while never winning.
_YOU_WIN_THE_GAME_IF_CONDITION_RE = re.compile(
    r"^you win the game if (?P<condition>[^.]+?)\.?$", re.IGNORECASE
)


#: The bare "You win the game." - what is left of a trigger whose condition
#: is CR 603.4's intervening *if* (Liliana's Contract's "At the beginning of
#: your upkeep, if you control four or more Demons with different names, you
#: win the game."), the condition already split off and checked by
#: `machines/triggers.intervening_if_holds` both as the event occurs and on
#: resolution (CR 608.2a).
_YOU_WIN_THE_GAME_RE = re.compile(r"^you win the game\.?$", re.IGNORECASE)


@SPELL_TEXT.rung("s2", for_spell=True)
@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_if_condition_you_win_the_game_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_CONDITION_YOU_WIN_THE_GAME_RE`'s shape - see the banner above.

    An unreadable condition (`Game.condition_holds` answering `None`) simply
    does not win the game - the same conservative fallback a modal "if"
    already applies when it cannot read one - since nothing in the pool
    prints this shape with a condition this wave does not also read.
    """
    condition_text: str | None = None
    if _YOU_WIN_THE_GAME_RE.fullmatch(clause.strip()) is None:
        match = _IF_CONDITION_YOU_WIN_THE_GAME_RE.fullmatch(clause.strip())
        if match is None:
            match = _YOU_WIN_THE_GAME_IF_CONDITION_RE.fullmatch(clause.strip())
            if match is None or not _effect_condition_is_readable(match.group("condition")):
                return None
        condition_text = match.group("condition").strip()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.source(game) if is_ability(stack_object) else stack_object
        if condition_text is None or game.condition_holds(
            controller.username, condition_text, source
        ):
            game.player_wins_the_game(controller.username)

    return effect


#: "For each player, choose a creature that player controls. Each player
#: sacrifices all creatures they control not chosen this way." -
#: The Eternal Wanderer's own `-4`. Two CR 608.2c instructions in order: the
#: first is every player's own protective choice (CR 608.2d), all made
#: before either sacrifice happens (CR 101.4 APNAP order, the same
#: all-choices-before-any-consequence shape `_EACH_SACRIFICES_OF_THEIR_
#: CHOICE_RE` already reads); the second sweeps each player's *other*
#: creatures to the graveyard (CR 701.21a). A player with no creature is
#: never asked (CR 608.2d offers no impossible choice) and loses nothing; a
#: player with exactly one has no real choice either, and it is simply the
#: one kept.
_EACH_PLAYER_CHOOSES_CREATURE_THEN_SACRIFICES_REST_RE = re.compile(
    r"^for each player, choose a creature that player controls\.\s*"
    r"each player sacrifices all creatures they control not chosen this way\.?$",
    re.IGNORECASE,
)


def _parse_each_player_chooses_creature_then_sacrifices_rest_whole_text(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_CHOOSES_CREATURE_THEN_SACRIFICES_REST_RE`'s shape - see
    the banner above. Read whole for the same "this way" reason every other
    two-sentence rider in this module is: the second sentence's "not chosen
    this way" counts a fact about the first sentence's own per-player
    choice, not an independent instruction.
    """
    match = _EACH_PLAYER_CHOOSES_CREATURE_THEN_SACRIFICES_REST_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.source_name
            if isinstance(stack_object, AbilityOnStack)
            else stack_object.name
        )
        kept: dict[str, CardState] = {}
        for player in _players_in_apnap_order(game):
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if Type.CREATURE in game.characteristics_of(permanent).types
            ]
            if not candidates:
                continue
            if len(candidates) == 1:
                kept[player.username] = candidates[0]
                continue
            (chosen_id,) = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt="choose a creature you control",
                    source=source_name,
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            kept[player.username] = by_id[chosen_id]
        for player in _players_in_apnap_order(game):
            keep = kept.get(player.username)
            for permanent in game.permanents_controlled_by(player.username):
                if (
                    permanent is not keep
                    and permanent.zone is Zone.BATTLEFIELD
                    and Type.CREATURE in game.characteristics_of(permanent).types
                ):
                    game.sacrifice(permanent)

    return effect


# --------------------------------------------------------------------------
# "You may choose new targets for target spell or ability." (CR 115.7)
# --------------------------------------------------------------------------
#
# CR 115.7: "Some effects allow a player to change the target(s) of a spell or
# ability, and other effects allow a player to choose new targets for a spell
# or ability." Deflecting Swat is the second kind, and CR 115.7d says what that
# means: "If an effect allows a player to 'choose new targets' for a spell or
# ability, the player may leave any number of the targets unchanged, even if
# those targets would be illegal."
#
# Which is exactly the shape `Game.offer_new_targets_for_copy` already
# implements for CR 707.10c's copies - a plain CR 608.2d `MAY`, then a
# `CHOOSE_TARGETS` question over the legal candidates read out of the *targeted
# object's own* printed text, with declining leaving the targets it already had
# in place rather than emptying them. That method is named for the copy case it
# was written for but is card-agnostic underneath, so this calls it as it
# stands rather than growing a second retargeting reader beside it.

#: "You may choose new targets for target spell or ability." (Deflecting Swat).
#: The retargeting permission itself is CR 115.7d; the "target spell or
#: ability" it applies to is the requirement `machines/targeting.py` reads (see
#: `test_judge_retargeting.py`), so nothing here re-reads it.
_CHOOSE_NEW_TARGETS_RE = re.compile(
    r"^you may choose new targets for target spell or ability\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_choose_new_targets_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_CHOOSE_NEW_TARGETS_RE`'s shape - Deflecting Swat's second sentence.

    The object retargeted is this spell's own single target, taken through
    `Game.resolve_targets` so CR 608.2b's "a target that's no longer in the
    zone it was in when it was targeted is illegal" is honoured first: a Bolt
    that has already resolved is not there to retarget, and the whole clause
    then does nothing rather than reaching for a stale object.

    A spell that has no targets of its own is CR 101.3's case - "any part of
    an instruction that's impossible to perform is ignored" - and comes out
    the far side of `offer_new_targets_for_capture`'s own empty-candidate
    guard doing nothing, which is the ruling
    `test_judge_retargeting.py::test_deflecting_swat_resolving_leaves_a_
    targetless_spell_alone` already asserts.
    """
    if _CHOOSE_NEW_TARGETS_RE.fullmatch(clause.strip()) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targeted = game.resolve_targets(stack_object)
        if not targeted:
            return
        subject = targeted[0]
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if isinstance(subject, AbilityOnStack):
            # `offer_new_targets_for_copy` reads a card's printed text, so an
            # ability's own targets are re-chosen through `Game.change_targets`
            # instead - CR 115.7d's "any number of the targets", each left
            # alone at will, behind the same "you may".
            game.change_targets(
                subject,
                game.controller_of(stack_object).username,
                scope=RetargetScope.ANY,
                optional=True,
                source_name=source_name,
                source_id=source_id_of(stack_object),
            )
            return
        if not isinstance(subject, CardState):
            return
        game.offer_new_targets_for_copy(
            subject,
            game.controller_of(stack_object).username,
            source_name=source_name,
            source_id=source_id_of(stack_object),
        )

    return effect


#: "Choose `<targets>`. If this spell was kicked, instead choose `<targets>`.
#: Return each chosen `<noun>` to `<hand>`.[ At the beginning of the next
#: `<step>`, create `<a token>` for each `<noun>` returned to `<hand>` this
#: way.]" - The Eagles Are Coming!. Which targets were chosen is settled at
#: announcement (CR 601.2c, `machines/targeting.kicked_instead_target_text`),
#: so resolution returns whatever was chosen and still legal (CR 608.2b),
#: together (CR 603.2c), and the delayed tail (CR 603.7a) counts the cards
#: that really arrived in a hand.
_KICKED_CHOOSE_RETURN_DELAYED_RE = re.compile(
    r"^choose (?P<base>[^.]*\btargets?\b[^.]*)\.\s*"
    r"if this spell was kicked, instead choose (?P<kicked>[^.]*\btargets?\b[^.]*)\.\s*"
    r"return each chosen (?P<noun>[a-z]+) to (?:your|its owner's|their owners'?) hands?\.?"
    r"(?:\s*at the beginning of the next (?P<step>upkeep|end step), "
    r"(?P<delayed>create an? .+? tokens?(?: with [^.]+?)?) for each (?P=noun) returned to "
    r"(?:your|its owner's|their owners'?) hands? this way\.?)?$",
    re.IGNORECASE,
)

_SINGLE_TOKEN_CLAUSE_RE = re.compile(
    r"^create an? (?P<desc>.+?) token(?P<tail>(?: with [^.]+)?)$", re.IGNORECASE
)


@SPELL_TEXT.rung("s14")
def _parse_kicked_choose_return_delayed_clause(effect_text: str) -> Effect | None:
    """`_KICKED_CHOOSE_RETURN_DELAYED_RE`'s shape.

    The delayed half is a CR 603.7a delayed triggered ability made from its
    own words (`CreatedTriggeredAbility`, triggering once, CR 603.7b), its
    single token rewritten to the number of cards returned ("create a ...
    token" -> "create N ... tokens"), read by the same token parser a printed
    "create N ..." goes through - so the tokens are created together, as one
    event. Nothing returned, nothing delayed.
    """
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _KICKED_CHOOSE_RETURN_DELAYED_RE.fullmatch(whole)
    if match is None:
        return None
    for phrase in (match.group("base"), match.group("kicked")):
        if not _targets_understood(phrase, count_agnostic=True):
            return None
    step_word = (match.group("step") or "").lower()
    step = {"upkeep": Step.UPKEEP, "end step": Step.END_STEP}.get(step_word)
    delayed_clause = match.group("delayed")
    token_match = None
    if delayed_clause is not None:
        token_match = _SINGLE_TOKEN_CLAUSE_RE.fullmatch(delayed_clause.strip())
        if token_match is None:
            return None
        probe = f"create 2 {token_match.group('desc')} tokens{token_match.group('tail')}"
        if parse_mixed_effect_for_spell(probe) is None:
            return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        returned = 0
        with game.returning_together():
            for target in game.resolve_targets(spell):
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                    moved = game.return_to_hand(target)
                    if moved is not None and moved.zone is Zone.HAND:
                        returned += 1
        if token_match is None or step is None or returned <= 0:
            return
        created = (
            f"At the beginning of each {step_word}, create {returned} "
            f"{token_match.group('desc')} tokens{token_match.group('tail')}."
        )
        game.create_delayed_trigger(
            DelayedTrigger(
                text=f"At the beginning of the next {step_word}, {delayed_clause}.",
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=controller,
                source_id=spell.id,
                source_name=spell.name,
                effect=CreatedTriggeredAbility(ability_text=created, source_card=spell.card),
            )
        )

    return effect


# ---------------------------------------------------------------------------
# C02-T6: copy, control change, loses-all-abilities and type/P-T readers
# ---------------------------------------------------------------------------

#: "If this `<noun>` isn't a creature, it becomes a `<N/N ... creature>` ..."
#: - Iron Man Armor's "{2}: If this Equipment isn't a creature, it becomes a
#: 0/0 Construct Hero artifact creature with flying and "..." until end of
#: turn." and Great Hall of the Biblioplex's "{5}: If this land isn't a
#: creature, it becomes a 2/4 Wizard creature with "..." It's still a land."
#: The condition is checked as the ability resolves (CR 608.2c: an "if"
#: instruction is followed only when it holds); "it" is the source itself, so
#: the rest is read as the source's own animation sentence.
_IF_SELF_ISNT_A_CREATURE_RE = re.compile(
    r"^if this (?:artifact|equipment|land|enchantment|permanent|vehicle) isn'?t a creature, "
    r"it (?P<rest>becomes .+)$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_if_self_isnt_a_creature_clause(effect_text: str) -> AbilityEffect | None:
    """`_IF_SELF_ISNT_A_CREATURE_RE`'s shape, when the rest is one of
    `machines/layers.py`'s own animation sentences - or `None`."""
    match = _IF_SELF_ISNT_A_CREATURE_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    layer_sentence = f"This permanent {match.group('rest')}"
    if parsed_layer_effects(layer_sentence, static_only=False) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if game.characteristics_of(source).is_creature:
            return
        continuous_effects(game).create(
            source,
            targets=[source],
            context=layer_context_for(game, game.controller_of(ability)),
            ability_text=layer_sentence,
            game=game,
        )

    return effect


from ..damage_modification import DamageModifierReplacement  # noqa: E402
from ..ep02_r2_referenced_permanent_stat import (  # noqa: E402
    referenced_permanent_stat_effect,
)
from ..replacement.model import CreatedReplacement  # noqa: E402
from ..replacement.parse import read_turn_damage_spec  # noqa: E402
from ._common import (  # noqa: E402
    _ADDITIONAL_LAND_PLAY_RE,
    _CLAUSE_SEPARATOR,
    _COLOR_LETTERS,
    _DRAW_N_CARDS_RE,
    _MASS_TYPE_JOIN_RE,
    _OBJECT_ANAPHOR_RE,
    _PAY_ANY_AMOUNT_OF_LIFE_RE,
    _SHUFFLE_RE,
    _TOKEN_CLAUSE_RE,
    _WHERE_X_IS_INLINE_RE,
    _YOU_MAY_RE,
    ConditionalClauseNotice,
    ModeNotice,
    _effect_condition_is_readable,
    _nonland_or_typed_card_matcher,
    _opponents,
    _parse_delayed_timing_clause,
    _parse_mass_type_qualifier,
    _permanent_id_and_name,
    _players_in_apnap_order,
    _quality_matcher,
    _self_normalized_effect_text,
    _targets_understood,
    computed_permanents,
    pay_consequence_effect,
)
from .amounts import (  # noqa: E402
    _amount_substituted_base,
    _carry_count,
    _carry_sacrificed_power,
    _parse_where_x_is_continuous_effect,
    _parse_where_x_is_continuous_effect_for_spell,
    carries_sacrificed_power,
)
from .continuous import (  # noqa: E402
    _compose_layer_effect_with_remainder_for_ability,
    _compose_layer_effect_with_remainder_for_ability_mode,
    _compose_layer_effect_with_remainder_for_mode,
    _is_layer_effect_text,
    _mass_pump_spell_effect,
    _parse_mass_gain_control_untap_clause,
    continuous_effects,
    layer_context_for,
    until_eot_gain_control_and_grant_text,  # noqa: E402
)
from .control_copy import _parse_if_control_colored_permanent_damage_clause  # noqa: E402
from .counters import (  # noqa: E402
    _counter_kind,
    _parse_counters_and_becomes_type_clause,
    put_support_counters,
)
from .damage import _fight, _parse_self_fights_target_clause, _resolve_bite_damage  # noqa: E402
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _c02_t6_spell_effect,
    _parse_mixed_clause,
    _parse_mixed_clauses,
    parse_clause_effect,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .draw_discard import _discard_cards, _land_cards_in_hand  # noqa: E402
from .library import (  # noqa: E402
    _dead_self_found,
    _mill,
    _parse_mill_then_return_to_hand_clause,
    _parse_select_from_top_spell_clause,
    _parse_target_player_mills_then_puts_milled_into_own_hand_clause,
)
from .mana import (  # noqa: E402
    _parse_add_one_mana_of_any_color_trigger,
    _parse_add_one_of_listed_mana_clause,
)
from .merges import (  # noqa: E402
    _clauses_around_sentences,
    _merge_reveal_hand_choose_discard_clauses,
)
from .removal import (  # noqa: E402
    _destroy_matching,
    _parse_conditional_sacrifice_clause,
    _sacrifice_is_payable,
    _sacrifice_of_choice_clause_effect,
    _sacrifice_restriction,
)
from .returns import (  # noqa: E402
    _parse_return_as_creature_clause,
    _watch_for_departure_and_return_exiled_card,
    return_ability_targets_to_battlefield,
    return_ability_targets_to_hand,
)
from .search import (  # noqa: E402
    _parse_put_from_outside_the_game_into_hand_spell,
    _search_and_exile_matching_name,
)
from .text import (  # noqa: E402
    _anaphoric_target_substitution,
    _as_sentence,
    _parse_comma_chained_player_clause,
    _parse_referent_object_clause,
    _plain_resolution_sentences,
    _strip_non_effect_preamble,
)
from .tokens import (  # noqa: E402
    _create_continuous_effect_for_mode_text,
    _parse_create_token_copies_except_clause,
    _parse_created_trigger_spell_text,
    _parse_generic_token_descriptor,
    _parse_target_player_token_mode,
    _read_token_copy_except,
    create_continuous_effect_of_ability,
)


@ABILITY_TEXT.rung("s20")
def _parse_choose_target_may_sacrifice_return_chosen_clause(text: str) -> AbilityEffect | None:
    """ "choose target <card> in your graveyard. You may sacrifice <quality>.
    If you do, return the chosen card to the battlefield." -
    `machines/if_you_do_chains.parse_chosen_target_sacrifice_return`."""
    if "the chosen card" not in text.lower():
        return None
    from ..if_you_do_chains import parse_chosen_target_sacrifice_return

    return parse_chosen_target_sacrifice_return(text)
